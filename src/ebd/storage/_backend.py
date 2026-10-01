"""Serialized SQLite/file owner. No public caller is given this backend."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from datetime import datetime, timezone
from typing import Any, Callable
import uuid

from ebd.contracts import EngineError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def encode(value: Any) -> str:
    from ebd.contracts import canonical_json
    return canonical_json(value).decode("utf-8")


class StorageFailure(Exception):
    def __init__(self, code: str, message: str, *, commit_state: str = "not_committed", details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.commit_state = code, message, commit_state
        self.details = details or {}


SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE scopes(scope TEXT PRIMARY KEY, descriptor TEXT NOT NULL);
CREATE TABLE runs(run_id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES scopes(scope), descriptor TEXT NOT NULL);
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL,producer TEXT NOT NULL,run_id TEXT NOT NULL,action_id TEXT NOT NULL,
 attempt_id TEXT,origin TEXT NOT NULL,digest TEXT NOT NULL,envelope TEXT NOT NULL,recorded_at TEXT NOT NULL);
CREATE TABLE event_scopes(event_id TEXT NOT NULL REFERENCES events(event_id),scope TEXT NOT NULL REFERENCES scopes(scope),PRIMARY KEY(event_id,scope));
CREATE INDEX events_run_sequence ON events(run_id,seq);
CREATE INDEX events_action_sequence ON events(action_id,attempt_id,seq);
CREATE UNIQUE INDEX lifecycle_boundary ON events(kind,run_id,action_id,COALESCE(attempt_id,''))
 WHERE kind IN ('agent.started','agent.finished','model.intent','model.outcome','tool.intent','tool.outcome','invocation.intent','invocation.outcome');
CREATE TABLE operations(operation_id TEXT PRIMARY KEY,method TEXT NOT NULL,origin TEXT NOT NULL,
 fingerprint TEXT NOT NULL,phase TEXT NOT NULL CHECK(phase IN ('reserved','writing','sealed','publishing','ready','aborted','interrupted')),
 descriptor TEXT NOT NULL,receipt TEXT,safe_disposition TEXT);
CREATE TABLE state_heads(scope TEXT NOT NULL REFERENCES scopes(scope),key TEXT NOT NULL,version INTEGER NOT NULL CHECK(version>0),
 tombstone INTEGER NOT NULL CHECK(tombstone IN (0,1)),value TEXT,event_id TEXT NOT NULL REFERENCES events(event_id),PRIMARY KEY(scope,key));
CREATE TABLE state_revisions(scope TEXT NOT NULL REFERENCES scopes(scope),key TEXT NOT NULL,version INTEGER NOT NULL CHECK(version>0),
 tombstone INTEGER NOT NULL CHECK(tombstone IN (0,1)),value TEXT,event_id TEXT NOT NULL REFERENCES events(event_id),PRIMARY KEY(scope,key,version));
CREATE TABLE artifacts(object_id TEXT PRIMARY KEY,scope TEXT NOT NULL REFERENCES scopes(scope),operation_id TEXT NOT NULL REFERENCES operations(operation_id),
 relative_key TEXT NOT NULL UNIQUE,stage_key TEXT NOT NULL UNIQUE,phase TEXT NOT NULL CHECK(phase IN ('reserved','writing','sealed','ready','aborted','interrupted')),
 byte_length INTEGER NOT NULL CHECK(byte_length>=0),sha256 TEXT NOT NULL,media_type TEXT NOT NULL,metadata TEXT NOT NULL);
CREATE TABLE snapshots(object_id TEXT PRIMARY KEY,scope TEXT NOT NULL REFERENCES scopes(scope),operation_id TEXT NOT NULL REFERENCES operations(operation_id),descriptor TEXT NOT NULL);
CREATE TABLE checkpoints(object_id TEXT PRIMARY KEY,scope TEXT NOT NULL REFERENCES scopes(scope),operation_id TEXT NOT NULL REFERENCES operations(operation_id),descriptor TEXT NOT NULL);
"""
SCHEMA_DIGEST = digest(SCHEMA.encode())


class RootLock:
    def __init__(self, root: Path):
        self.file = open(root / ".owner.lock", "a+b")
        if self.file.seek(0, os.SEEK_END) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise StorageFailure("STORAGE_BUSY", "Storage root already has an owner") from None

    def close(self) -> None:
        if self.file.closed:
            return
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()


class Backend:
    def __init__(self, root: Path, profile: str = "delete", fault_hook: Callable[[str, str], None] | None = None):
        self.root, self.fault_hook = root, fault_hook
        self.streams: dict[str, dict] = {}
        root.mkdir(parents=True, exist_ok=True)
        self._check_path(root)
        self._check_path(root / ".owner.lock")
        self._check_path(root / "store.sqlite3")
        self.lock = RootLock(root)
        self.db: sqlite3.Connection | None = None
        try:
            for dirname in ("objects", "staging", "quarantine"):
                (root / dirname).mkdir(exist_ok=True)
                self._check_path(root / dirname)
            self.db = sqlite3.connect(root / "store.sqlite3", isolation_level=None, timeout=5)
            self.db.row_factory = sqlite3.Row
            if profile != "delete":
                raise StorageFailure("INCOMPATIBLE_SCHEMA", "Only the verified DELETE durability profile is enabled")
            returned = self.db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()
            self.db.execute("PRAGMA synchronous=EXTRA")
            self.db.execute("PRAGMA foreign_keys=ON")
            if returned != "delete" or self.db.execute("PRAGMA synchronous").fetchone()[0] != 3 or self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise StorageFailure("STORAGE_UNAVAILABLE", "Requested durability settings were not established")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            self.db.execute(statement)
                    entries = {"store_id": str(uuid.uuid4()), "schema_digest": SCHEMA_DIGEST, "profile": "delete-extra", "canonicalizer_version": "1"}
                    self.db.executemany("INSERT INTO metadata VALUES(?,?)", entries.items())
                    self.db.execute("PRAGMA user_version=1")
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
            elif version != 1:
                raise StorageFailure("INCOMPATIBLE_SCHEMA", "Unknown Storage database schema")
            metadata = dict(self.db.execute("SELECT key,value FROM metadata"))
            if metadata.get("schema_digest") != SCHEMA_DIGEST or metadata.get("profile") != "delete-extra":
                raise StorageFailure("INCOMPATIBLE_SCHEMA", "Storage schema or profile differs from the accepted version")
            self.store_id = metadata["store_id"]
            self.profile = {"journal_mode": returned, "synchronous": 3, "foreign_keys": 1, "sqlite_version": sqlite3.sqlite_version, "schema_version": 1, "file_directory_fsync": os.name != "nt"}
            self.recovery = self.recover()
        except BaseException:
            if self.db is not None:
                self.db.close()
            self.lock.close()
            raise

    def _check_path(self, path: Path) -> None:
        current = path
        while True:
            if current.exists():
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise StorageFailure("INTEGRITY_ERROR", "Storage paths cannot contain symlinks or reparse points")
            if current == self.root or current.parent == current:
                break
            current = current.parent
        if path != self.root and not path.resolve().is_relative_to(self.root.resolve()):
            raise StorageFailure("INTEGRITY_ERROR", "Storage object containment failed")

    def path(self, relative_key: str) -> Path:
        if relative_key.startswith(("/", "\\")) or ":" in relative_key or ".." in Path(relative_key).parts:
            raise StorageFailure("INTEGRITY_ERROR", "Invalid internal object location")
        path = self.root / relative_key
        self._check_path(path)
        return path

    def fault(self, phase: str, operation_id: str) -> None:
        if self.fault_hook:
            self.fault_hook(phase, operation_id)

    def close(self) -> dict:
        for operation_id in tuple(self.streams):
            self.abort_stream(operation_id, "INTERRUPTED_SOURCE")
        disposition = self.recover()
        self.db.close()
        self.lock.close()
        return {"schema_version": 1, "store_id": self.store_id, "closed": True, "completed_operation_ids": disposition["completed_operation_ids"], "interrupted_operation_ids": disposition["interrupted_operation_ids"]}

    def provision(self, run_id: str, scope: str, descriptor: dict) -> dict:
        row = self.db.execute("SELECT descriptor FROM runs WHERE run_id=?", (run_id,)).fetchone()
        frozen = encode(descriptor)
        if row and row[0] != frozen:
            raise StorageFailure("IDEMPOTENCY_CONFLICT", "Run registration differs from its original descriptor")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT OR IGNORE INTO scopes VALUES(?,?)", (scope, frozen))
            self.db.execute("INSERT OR IGNORE INTO runs VALUES(?,?,?)", (run_id, scope, frozen))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return descriptor

    def provision_scope(self, scope: str, descriptor: dict) -> None:
        frozen = encode(descriptor)
        row = self.db.execute("SELECT descriptor FROM scopes WHERE scope=?", (scope,)).fetchone()
        if row and row[0] != frozen:
            raise StorageFailure("IDEMPOTENCY_CONFLICT", "Scope registration differs from its original descriptor")
        self.db.execute("INSERT OR IGNORE INTO scopes VALUES(?,?)", (scope, frozen))

    def describe_run(self, run_id: str) -> dict | None:
        row = self.db.execute("SELECT descriptor FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def require_scope(self, scope: str) -> None:
        if not self.db.execute("SELECT 1 FROM scopes WHERE scope=?", (scope,)).fetchone():
            raise StorageFailure("NOT_FOUND", "Registered scope was not found")

    def existing_operation(self, operation_id: str, fingerprint: str, origin: dict) -> dict | None:
        row = self.db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if not row:
            return None
        if row["fingerprint"] != fingerprint or row["origin"] != encode(origin):
            raise StorageFailure("IDEMPOTENCY_CONFLICT", "Operation content or origin differs from the original")
        if row["phase"] == "ready":
            receipt = json.loads(row["receipt"])
            receipt["duplicate"] = True
            receipt["event_receipt"]["duplicate"] = True
            return receipt
        if row["phase"] in ("aborted", "interrupted"):
            raise StorageFailure("INCOMPLETE_ARTIFACT", "The original operation did not publish", details={"operation_id": operation_id, "phase": row["phase"]})
        raise StorageFailure("OPERATION_PENDING", "The original operation is still admitted", commit_state="unknown", details={"operation_id": operation_id, "phase": row["phase"]})

    def event_row(self, event_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["origin"] = json.loads(value["origin"])
        value["envelope"] = json.loads(value["envelope"])
        value["scopes"] = [r[0] for r in self.db.execute("SELECT scope FROM event_scopes WHERE event_id=?", (event_id,))]
        return value

    def operation_row(self, operation_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if row:
            value = dict(row)
            for key in ("origin", "descriptor", "receipt"):
                value[key] = json.loads(value[key]) if value[key] else None
            return value
        return None

    def receipt(self, row: dict | sqlite3.Row, duplicate: bool = False) -> dict:
        return {"schema_version": 1, "store_id": self.store_id, "event_id": row["event_id"], "recorded_seq": row["seq"], "recorded_at": row["recorded_at"], "duplicate": duplicate}

    def _insert_event(self, event: dict, origin: dict, scopes: list[str], event_digest: str) -> dict:
        origin = {**origin, "producer": event["producer"]}
        for scope in scopes:
            self.require_scope(scope)
        existing = self.event_row(event["event_id"])
        if existing:
            if existing["digest"] != event_digest or existing["origin"] != origin:
                raise StorageFailure("IDEMPOTENCY_CONFLICT", "Event content or origin differs from the original")
            return self.receipt(existing, True)
        context = event["context"]
        recorded_at = utc_now()
        try:
            cur = self.db.execute("INSERT INTO events(event_id,kind,producer,run_id,action_id,attempt_id,origin,digest,envelope,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (event["event_id"], event["kind"], event["producer"], context["run_id"], context["action_id"], context.get("attempt_id"), encode(origin), event_digest, encode(event), recorded_at))
            self.db.executemany("INSERT INTO event_scopes VALUES(?,?)", [(event["event_id"], s) for s in scopes])
        except sqlite3.IntegrityError:
            raise StorageFailure("IDEMPOTENCY_CONFLICT", "A lifecycle boundary was already recorded") from None
        return {"schema_version": 1, "store_id": self.store_id, "event_id": event["event_id"], "recorded_seq": cur.lastrowid, "recorded_at": recorded_at, "duplicate": False}

    def append(self, event: dict, origin: dict, scopes: list[str], event_digest: str) -> dict:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            receipt = self._insert_event(event, origin, scopes, event_digest)
            self.db.execute("COMMIT")
            return receipt
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def state_get(self, scope: str, key: str, version: int | None) -> dict:
        table = "state_heads" if version is None else "state_revisions"
        query = f"SELECT * FROM {table} WHERE scope=? AND key=?"
        params = (scope, key) if version is None else (scope, key, version)
        if version is not None:
            query += " AND version=?"
        row = self.db.execute(query, params).fetchone()
        if not row:
            if version is not None:
                raise StorageFailure("NOT_FOUND", "State revision was not found")
            return {"present": False, "version": 0, "value": None, "commit_event_id": None}
        return {"present": not bool(row["tombstone"]), "version": row["version"], "value": json.loads(row["value"]) if row["value"] is not None else None, "commit_event_id": row["event_id"]}

    def state_commit(self, operation_id: str, origin: dict, fingerprint: str, mutations: list[dict], event: dict) -> dict:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            versions = []
            for m in mutations:
                self.require_scope(m["scope"])
                current = self.state_get(m["scope"], m["key"], None)
                if current["version"] != m["expected_version"]:
                    raise StorageFailure("VERSION_CONFLICT", "Expected state revision differs from the current revision")
                if m["kind"] == "delete" and not current["present"]:
                    raise StorageFailure("INVALID_DATA", "Only present state may be deleted")
                if current["version"] >= 2**63 - 1:
                    raise StorageFailure("LIMIT_EXCEEDED", "State revision is exhausted")
                versions.append({"scope": m["scope"], "key": m["key"], "old_version": current["version"], "new_version": current["version"] + 1})
            event["payload"]["mutation_versions"] = versions
            er = self._insert_event(event, origin, sorted({m["scope"] for m in mutations}), digest(encode(event).encode()))
            for m, v in zip(mutations, versions):
                tombstone = int(m["kind"] == "delete")
                value = encode(m.get("value")) if not tombstone else None
                data = (m["scope"], m["key"], v["new_version"], tombstone, value, er["event_id"])
                self.db.execute("INSERT INTO state_revisions VALUES(?,?,?,?,?,?)", data)
                self.db.execute("INSERT INTO state_heads VALUES(?,?,?,?,?,?) ON CONFLICT(scope,key) DO UPDATE SET version=excluded.version,tombstone=excluded.tombstone,value=excluded.value,event_id=excluded.event_id", data)
            receipt = {"schema_version": 1, "store_id": self.store_id, "operation_id": operation_id, "event_receipt": er, "duplicate": False, "mutation_versions": versions}
            descriptor = {"scopes": sorted({m["scope"] for m in mutations})}
            self.fault("state_before_commit", operation_id)
            self.db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?,NULL)", (operation_id, "state.commit", encode(origin), fingerprint, "ready", encode(descriptor), encode(receipt)))
            self.db.execute("COMMIT")
            self.fault("state_after_commit", operation_id)
            return receipt
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def reserve_files(self, operation_id: str, method: str, origin: dict, fingerprint: str, descriptor: dict) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.require_scope(descriptor["scope"])
            self.db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,NULL,NULL)", (operation_id, method, encode(origin), fingerprint, "reserved", encode(descriptor)))
            for c in descriptor["components"]:
                child_operation_id = c["operation_id"]
                if child_operation_id != operation_id:
                    child_component = {**c, "role": "artifact"}
                    child_receipt = {"artifact_ref": c["event"]["payload"]["artifact_ref"], "scope": descriptor["scope"], "byte_length": c["byte_length"], "sha256": c["sha256"], "media_type": c["media_type"]}
                    child_descriptor = {"scope": descriptor["scope"], "object_id": c["object_id"], "components": [child_component], "receipt": child_receipt, "object_descriptor": {}, "event": c["event"], "parent_operation_id": operation_id}
                    self.db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,NULL,NULL)", (child_operation_id, "artifact.put", encode(origin), digest(encode(child_descriptor).encode()), "reserved", encode(child_descriptor)))
                self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?)", (c["object_id"], descriptor["scope"], child_operation_id, c["relative_key"], c["stage_key"], "reserved", c["byte_length"], c["sha256"], c["media_type"], encode(c.get("metadata", {}))))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.fault("reserved", operation_id)

    def publish_files(self, operation_id: str, bodies: dict[str, bytes], guard: Callable | None = None) -> dict:
        row = self.operation_row(operation_id)
        descriptor = row["descriptor"]
        self.db.execute("UPDATE operations SET phase='writing' WHERE operation_id=?", (operation_id,))
        for c in descriptor["components"]:
            stage = self.path(c["stage_key"])
            data = bodies[c["role"]]
            with open(stage, "xb") as f:
                for offset in range(0, len(data), 64 * 1024):
                    f.write(data[offset:offset + 64 * 1024])
                f.flush()
                os.fsync(f.fileno())
            self.verify_file(stage, c["byte_length"], c["sha256"])
            self.db.execute("UPDATE artifacts SET phase='sealed' WHERE object_id=?", (c["object_id"],))
            if c["operation_id"] != operation_id:
                self.db.execute("UPDATE operations SET phase='sealed' WHERE operation_id=?", (c["operation_id"],))
            self.fault("component_sealed", operation_id)
        self.db.execute("UPDATE operations SET phase='sealed' WHERE operation_id=?", (operation_id,))
        self.fault("sealed", operation_id)
        try:
            return self.finish_files(operation_id, guard)
        except EngineError as exc:
            self.abort_publication(operation_id, exc.code)
            exc.commit_state = "not_committed"
            raise

    def start_stream(self, operation_id: str) -> None:
        row = self.operation_row(operation_id)
        c = row["descriptor"]["components"][0]
        stream = open(self.path(c["stage_key"]), "xb")
        self.streams[operation_id] = {"file": stream, "component": c, "sha256": hashlib.sha256(), "byte_length": 0}
        self.db.execute("UPDATE operations SET phase='writing' WHERE operation_id=?", (operation_id,))
        self.db.execute("UPDATE artifacts SET phase='writing' WHERE operation_id=?", (operation_id,))

    def stream_chunk(self, operation_id: str, chunk: bytes) -> None:
        state = self.streams[operation_id]
        if state["byte_length"] + len(chunk) > state["component"]["byte_length"]:
            raise StorageFailure("INTEGRITY_ERROR", "Artifact source exceeds its declared length")
        state["file"].write(chunk)
        state["sha256"].update(chunk)
        state["byte_length"] += len(chunk)

    def seal_stream(self, operation_id: str) -> None:
        state = self.streams[operation_id]
        c = state["component"]
        if state["byte_length"] != c["byte_length"] or "sha256:" + state["sha256"].hexdigest() != c["sha256"]:
            raise StorageFailure("INTEGRITY_ERROR", "Artifact source differs from its declared length or digest")
        state["file"].flush()
        os.fsync(state["file"].fileno())
        state["file"].close()
        self.streams.pop(operation_id)
        self.db.execute("UPDATE artifacts SET phase='sealed' WHERE operation_id=?", (operation_id,))
        self.db.execute("UPDATE operations SET phase='sealed' WHERE operation_id=?", (operation_id,))
        self.fault("sealed", operation_id)

    def abort_stream(self, operation_id: str, code: str) -> None:
        state = self.streams.get(operation_id)
        if state:
            try:
                state["file"].close()
            finally:
                if state["file"].closed:
                    self.streams.pop(operation_id, None)
        if self.operation_row(operation_id):
            self.abort_publication(operation_id, code)

    def abort_publication(self, operation_id: str, code: str) -> None:
        row = self.operation_row(operation_id)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            ids = {operation_id} | {c["operation_id"] for c in row["descriptor"]["components"]}
            for identity in ids:
                self.db.execute("UPDATE operations SET phase='aborted',safe_disposition=? WHERE operation_id=? AND phase!='ready'", (code, identity))
                self.db.execute("UPDATE artifacts SET phase='aborted' WHERE operation_id=? AND phase!='ready'", (identity,))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def verify_file(self, path: Path, byte_length: int, sha256: str) -> bytes:
        self._check_path(path)
        try:
            with open(path, "rb") as f:
                if not Path(os.path.realpath(f.name)).is_relative_to(self.root.resolve()):
                    raise StorageFailure("INTEGRITY_ERROR", "Opened Storage file containment failed")
                data = f.read(byte_length + 1)
        except FileNotFoundError:
            raise StorageFailure("INTEGRITY_ERROR", "Published object bytes are missing") from None
        if len(data) != byte_length or digest(data) != sha256:
            raise StorageFailure("INTEGRITY_ERROR", "Published object bytes failed verification")
        return data

    def sync_directory(self, directory: Path) -> None:
        if os.name != "nt":
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def finish_files(self, operation_id: str, guard: Callable | None = None) -> dict:
        row = self.operation_row(operation_id)
        d = row["descriptor"]
        if row["phase"] in ("aborted", "interrupted"):
            raise StorageFailure("INCOMPLETE_ARTIFACT", "Aborted or interrupted publication cannot be promoted")
        if row["phase"] == "ready":
            return row["receipt"]
        if guard:
            guard()
        for c in d["components"]:
            if c["operation_id"] != operation_id:
                child = self.operation_row(c["operation_id"])
                if child["phase"] != "ready":
                    if child["phase"] != "sealed":
                        raise StorageFailure("INCOMPLETE_ARTIFACT", "Composite component is not completely sealed")
                    self.finish_files(c["operation_id"], guard)
                self.verify_file(self.path(c["relative_key"]), c["byte_length"], c["sha256"])
                continue
            stage, final = self.path(c["stage_key"]), self.path(c["relative_key"])
            if final.exists():
                self.verify_file(final, c["byte_length"], c["sha256"])
            else:
                self.verify_file(stage, c["byte_length"], c["sha256"])
                os.rename(stage, final)
                self.sync_directory(final.parent)
            self.fault("renamed", operation_id)
        if guard:
            guard()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            receipts = {}
            for c in d["components"]:
                if c["operation_id"] != operation_id:
                    er = self.operation_row(c["operation_id"])["receipt"]["event_receipt"]
                else:
                    event = c["event"]
                    er = self._insert_event(event, row["origin"], [d["scope"]], digest(encode(event).encode()))
                    self.db.execute("UPDATE artifacts SET phase='ready' WHERE object_id=?", (c["object_id"],))
                receipts[c["role"]] = er
            er = receipts["artifact"] if row["method"] == "artifact.put" else self._insert_event(d["event"], row["origin"], [d["scope"]], digest(encode(d["event"]).encode()))
            receipt = dict(d["receipt"])
            receipt.update({"schema_version": 1, "store_id": self.store_id, "operation_id": operation_id, "event_receipt": er, "duplicate": False})
            if row["method"] == "snapshot.commit":
                self.db.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (d["object_id"], d["scope"], operation_id, encode(d["object_descriptor"])))
            elif row["method"] == "checkpoint.save":
                self.db.execute("INSERT INTO checkpoints VALUES(?,?,?,?)", (d["object_id"], d["scope"], operation_id, encode(d["object_descriptor"])))
            self.db.execute("UPDATE operations SET phase='ready',receipt=? WHERE operation_id=?", (encode(receipt), operation_id))
            self.fault("before_ready_commit", operation_id)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.fault("after_ready_commit", operation_id)
        return receipt

    def object_row(self, kind: str, object_id: str) -> dict | None:
        table = {"artifact": "artifacts", "snapshot": "snapshots", "checkpoint": "checkpoints"}[kind]
        row = self.db.execute(f"SELECT * FROM {table} WHERE object_id=?", (object_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        if "descriptor" in value:
            value["descriptor"] = json.loads(value["descriptor"])
        return value

    def artifact_bytes(self, object_id: str) -> bytes:
        row = self.object_row("artifact", object_id)
        if not row:
            raise StorageFailure("NOT_FOUND", "Artifact was not found")
        if row["phase"] != "ready":
            raise StorageFailure("INCOMPLETE_ARTIFACT", "Artifact is not READY")
        try:
            return self.verify_file(self.path(row["relative_key"]), row["byte_length"], row["sha256"])
        except StorageFailure as exc:
            if exc.code == "INTEGRITY_ERROR":
                self.integrity_observation(row)
            raise

    def integrity_observation(self, artifact: dict) -> None:
        operation = self.operation_row(artifact["operation_id"])
        if not operation:
            return
        component = next(c for c in operation["descriptor"]["components"] if c["object_id"] == artifact["object_id"])
        event_id = "health_" + uuid.uuid5(uuid.NAMESPACE_URL, self.store_id + ":" + artifact["object_id"] + ":integrity").hex
        if self.event_row(event_id):
            return
        event = {"schema_version": 1, "event_id": event_id, "kind": "storage.integrity_observed", "producer": "storage", "context": component["event"]["context"], "producer_timestamp": utc_now(), "payload": {"artifact_ref": component["event"]["payload"]["artifact_ref"], "operation_id": artifact["operation_id"], "code": "INTEGRITY_ERROR", "availability": "unavailable"}}
        self.append(event, operation["origin"], [artifact["scope"]], digest(encode(event).encode()))

    def recover(self) -> dict:
        completed, interrupted = [], []
        pending = list(self.db.execute("SELECT operation_id,phase,method FROM operations WHERE phase NOT IN ('ready','aborted','interrupted') ORDER BY CASE WHEN method='artifact.put' THEN 0 ELSE 1 END"))
        for row in pending:
            operation_id, phase, method = row
            if self.operation_row(operation_id)["phase"] == "ready":
                continue
            if phase in ("sealed", "publishing"):
                try:
                    self.finish_files(operation_id)
                    completed.append(operation_id)
                    continue
                except StorageFailure:
                    pass
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("UPDATE operations SET phase='interrupted',safe_disposition='INTERRUPTED_PUBLICATION' WHERE operation_id=?", (operation_id,))
                self.db.execute("UPDATE artifacts SET phase='interrupted' WHERE operation_id=? AND phase!='ready'", (operation_id,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            interrupted.append(operation_id)
            descriptor = self.operation_row(operation_id)["descriptor"]
            for component in descriptor.get("components", []):
                stage = self.path(component["stage_key"])
                if stage.exists():
                    quarantine = self.path("quarantine/" + component["object_id"] + ".interrupted")
                    if not quarantine.exists():
                        os.rename(stage, quarantine)
        # READY history stays committed even when bytes are subsequently damaged.
        # Availability is a new origin-linked observation, never a rewritten receipt.
        for row in list(self.db.execute("SELECT * FROM artifacts WHERE phase='ready'")):
            artifact = dict(row)
            try:
                self.verify_file(self.path(artifact["relative_key"]), artifact["byte_length"], artifact["sha256"])
            except StorageFailure as exc:
                if exc.code != "INTEGRITY_ERROR":
                    raise
                self.integrity_observation(artifact)
        quarantined = []
        indexed = {r[0] for r in self.db.execute("SELECT relative_key FROM artifacts")} | {r[0] for r in self.db.execute("SELECT stage_key FROM artifacts")}
        for directory in ("objects", "staging"):
            for file in (self.root / directory).iterdir():
                relative = directory + "/" + file.name
                self._check_path(file)
                if relative in indexed:
                    continue
                if not file.is_file():
                    raise StorageFailure("INTEGRITY_ERROR", "Unexpected Storage object directory entry")
                target = self.path("quarantine/unindexed_" + uuid.uuid4().hex + ".bin")
                os.rename(file, target)
                self.db.execute("INSERT INTO metadata VALUES(?,?)", ("unindexed:" + target.name, encode({"code": "UNINDEXED_OBJECT_QUARANTINED", "observed_at": utc_now()})))
                quarantined.append(target.name)
        return {"completed_operation_ids": completed, "interrupted_operation_ids": interrupted, "unindexed_quarantined": quarantined}

    def query_events(self, selectors: list[dict], filters: dict, last: int, high: int | None, limit: int) -> tuple[list[dict], int, bool]:
        rows = []
        visible_high = 0
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            event = dict(row)
            visible = [s[0] for s in self.db.execute("SELECT scope FROM event_scopes WHERE event_id=?", (event["event_id"],))]
            if not visible or not all(any(selector["scope"] == scope and (selector["object_ids"] is None or event["event_id"] in selector["object_ids"]) and (selector["event_kinds"] is None or event["kind"] in selector["event_kinds"]) and (selector["producer"] is None or event["producer"] == selector["producer"]) for selector in selectors) for scope in visible):
                continue
            envelope = json.loads(event["envelope"])
            ctx = envelope["context"]
            if any(value is not None and (envelope.get(key, ctx.get(key, envelope.get("payload", {}).get(key))) != value) for key, value in filters.items()):
                continue
            visible_high = max(visible_high, event["seq"])
            if event["seq"] > last and (high is None or event["seq"] <= high) and len(rows) <= limit:
                rows.append({"event": envelope, "receipt": self.receipt(event)})
        if high is None:
            high = visible_high
        return rows[:limit], high, len(rows) > limit
