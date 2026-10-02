"""Real scoped Storage APIs over a single serialized SQLite/file owner."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import dataclasses
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable
import uuid

from deepresearch.engine.contracts import (ArtifactContent, ArtifactReceipt, ArtifactRef, CheckpointRef,
    DocumentSlice, EngineError, Err, EventReceipt, ExecutionContext, ExecutionEvent, GrantSet,
    Ok, ScopeRef, SnapshotProposal, SnapshotReceipt, SnapshotRef, to_json_value as shared_json_value)
from ._backend import Backend, StorageFailure, digest, encode, utc_now
from ._ranges import CursorCodec, canonical_json, strict_json, validate_index, slice_document


def to_json_value(value):
    try:
        return shared_json_value(value)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise StorageFailure("INVALID_DATA", "Value contains unsupported or invalid JSON data") from None


def scope_key(scope: ScopeRef | dict | str) -> str:
    if isinstance(scope, str):
        if not scope.startswith(("run:", "shared:")):
            raise StorageFailure("INVALID_DATA", "Scope must be tagged run or shared")
        kind, identity = scope.split(":", 1)
    else:
        scope = scope.to_dict() if hasattr(scope, "to_dict") else scope
        if not isinstance(scope, dict) or set(scope) != {"kind", "id"}:
            raise StorageFailure("INVALID_DATA", "Scope must have exactly kind and id")
        kind, identity = scope["kind"], scope["id"]
    try:
        length = len(identity.encode("utf-8")) if isinstance(identity, str) else 0
    except UnicodeError:
        raise StorageFailure("INVALID_DATA", "Scope identity is not valid UTF-8") from None
    if kind not in ("run", "shared") or not isinstance(identity, str) or not identity or length > 256:
        raise StorageFailure("INVALID_DATA", "Invalid scope identity")
    return kind + ":" + identity


def scope_ref(key: str) -> ScopeRef:
    return ScopeRef(*key.split(":", 1))


def opaque(value: str) -> str:
    try:
        length = len(value.encode("utf-8")) if isinstance(value, str) else 0
    except UnicodeError:
        raise StorageFailure("INVALID_DATA", "Opaque identity is not valid UTF-8") from None
    if not isinstance(value, str) or not value or length > 256 or any(ord(c) < 32 for c in value):
        raise StorageFailure("INVALID_DATA", "Invalid opaque identity")
    return value


def sha256_value(value: str) -> str:
    if not isinstance(value, str):
        raise StorageFailure("INVALID_DATA", "Expected a SHA-256 descriptor")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise StorageFailure("INVALID_DATA", "Expected a SHA-256 descriptor")
    return value


def error_result(exc: StorageFailure | EngineError | OSError | BaseException):
    if isinstance(exc, EngineError):
        return Err(exc)
    if isinstance(exc, StorageFailure):
        return Err(EngineError(exc.code, exc.message, exc.details, observed_effect_state="committed" if exc.commit_state == "committed" else "not_observed", commit_state=exc.commit_state, retryable_delivery=exc.code in {"OPERATION_PENDING", "STORAGE_UNAVAILABLE", "STORAGE_BUSY"}))
    if isinstance(exc, OSError):
        return Err(EngineError("STORAGE_UNAVAILABLE", "Storage I/O did not complete", commit_state="unknown", retryable_delivery=True))
    raise exc


def event_receipt(value: dict) -> EventReceipt:
    return EventReceipt(**value)


def receipt_value(method: str, value: dict):
    value = dict(value)
    value["event_receipt"] = event_receipt(value["event_receipt"])
    if method == "artifact.put":
        value["artifact_ref"] = ArtifactRef(**value["artifact_ref"])
        value["scope"] = scope_ref(value["scope"]) if isinstance(value["scope"], str) else ScopeRef(**value["scope"])
        value.pop("store_id", None)
        return ArtifactReceipt(**value)
    if method == "snapshot.commit":
        for name in ("manifest_ref", "original_ref", "text_ref", "index_ref"):
            value[name] = ArtifactRef(**value[name])
        value["snapshot_ref"] = SnapshotRef(**value["snapshot_ref"])
        value.pop("store_id", None)
        return SnapshotReceipt(**value)
    if method in {"state.commit", "state.cleanup"}:
        from deepresearch.engine.contracts import StateCommitReceipt
        return StateCommitReceipt(**value)
    if method == "checkpoint.save":
        from deepresearch.engine.contracts import CheckpointReceipt
        value["checkpoint_ref"] = CheckpointRef(**value["checkpoint_ref"])
        value["payload_ref"] = ArtifactRef(**value["payload_ref"])
        return CheckpointReceipt(**value)
    return value


def _page_limit(limit):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise StorageFailure("LIMIT_EXCEEDED", "Page limit must be 1..500")


def _catalog_filters(filters):
    filters = to_json_value({} if filters is None else filters)
    if not isinstance(filters, dict) or set(filters) - {"root_run_id", "parent_run_id", "agent_id", "context_kind"}:
        raise StorageFailure("INVALID_DATA", "Unsupported run discovery filters")
    for key, value in filters.items():
        if value is None and key in {"parent_run_id", "agent_id"}:
            continue
        opaque(value)
        if key == "context_kind" and value not in {"agent", "standalone_tool", "workflow"}:
            raise StorageFailure("INVALID_DATA", "Unsupported run context kind")
    canonical_json(filters, 4096)
    return filters


def _grant_identity(grant):
    value = to_json_value(grant)
    for key in ("object_ids", "event_kinds"):
        if value[key] is not None:
            value[key] = sorted(value[key])
    return value


def _history_selectors(session, context):
    selectors, selected = [], []
    session._live(context)
    if context.grants is None or context.grants.principal != context.principal or context.grants.is_revoked():
        raise EngineError("ACCESS_DENIED", "History authority is revoked or belongs to another principal")
    for grant in context.grants.grants if context.grants else []:
        if grant.operation not in ("events.read", "*") or grant.mode != "originator":
            continue
        if grant.object_ids == frozenset() or grant.event_kinds == frozenset():
            continue
        scope = grant.scope or context.scope
        if scope is None:
            continue
        # Validate this grant itself. A different narrower grant must not
        # authenticate the first selector of an expired broader grant.
        selected_context = dataclasses.replace(context, grants=GrantSet([grant], context.principal,
                                                _parents=(context.grants,)))
        try:
            session.authorize(selected_context, "events.read", scope,
                              next(iter(grant.object_ids)) if grant.object_ids else None,
                              grant.producer, next(iter(grant.event_kinds)) if grant.event_kinds else None)
        except EngineError as exc:
            if exc.code == "ACCESS_DENIED":
                continue
            raise
        selectors.append({"scope": scope_key(scope), "object_ids": sorted(grant.object_ids) if grant.object_ids is not None else None,
                          "event_kinds": sorted(grant.event_kinds) if grant.event_kinds is not None else None,
                          "producer": grant.producer})
        selected.append(_grant_identity(grant))
    if not selectors:
        raise EngineError("ACCESS_DENIED", "No scoped history read authority")
    return selectors, selected


def _recheck_history(session, context, selectors):
    current, _ = _history_selectors(session, context)
    if any(selector not in current for selector in selectors):
        raise EngineError("ACCESS_DENIED", "History authority changed during the read")


class StorageSession:
    """Lifecycle owner; consumers receive scoped facade handles, never SQL/path APIs."""
    def __init__(self, pool: ThreadPoolExecutor, backend: Backend):
        self._pool, self._backend = pool, backend
        self.store_id, self.profile, self.recovery = backend.store_id, backend.profile, backend.recovery
        self._admission = asyncio.Lock()
        self._pending: dict[str, dict] = {}
        self._active: set[asyncio.Future] = set()
        self._writers: set[asyncio.Task] = set()
        self._sources: dict[int, Any] = {}
        self._closing = False
        self._closed = False
        self._close_task: asyncio.Task | None = None
        self._cursors = CursorCodec(os.urandom(32))
        self.state = StateStore(self)
        self.artifacts = ArtifactStore(self)
        self.snapshots = SnapshotStore(self)
        self.checkpoints = CheckpointStore(self)
        self.recorder = ActivityRecorder(self)
        self.activity = ActivityReader(self)
        self.operations = OperationStore(self)

    @classmethod
    async def open(cls, resolved_settings: str | Path | dict, authority=None):
        if isinstance(resolved_settings, dict):
            if set(resolved_settings) - {"root", "profile", "fault_hook"}:
                return Err(EngineError("INVALID_DATA", "Unknown Storage settings", commit_state="not_committed"))
            root, profile, hook = resolved_settings.get("root"), resolved_settings.get("profile", "delete"), resolved_settings.get("fault_hook")
        else:
            root, profile, hook = resolved_settings, "delete", None
        if root is None:
            return Err(EngineError("INVALID_DATA", "Storage root is required", commit_state="not_committed"))
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deepresearch-storage")
        try:
            opening = asyncio.get_running_loop().run_in_executor(pool, lambda: Backend(Path(root).absolute(), profile, hook))
            try:
                backend = await asyncio.shield(opening)
            except asyncio.CancelledError:
                # The owning thread may have opened files already. Keep ownership
                # until it settles, then close on that same worker before re-raising.
                try:
                    owner = await asyncio.shield(opening)
                    await asyncio.shield(asyncio.get_running_loop().run_in_executor(pool, owner.close))
                finally:
                    pool.shutdown(wait=True)
                raise
            return Ok(cls(pool, backend))
        except (StorageFailure, OSError) as exc:
            pool.shutdown(wait=True)
            return error_result(exc)
        except sqlite3.DatabaseError:
            pool.shutdown(wait=True)
            return Err(EngineError("STORAGE_UNAVAILABLE", "Storage database could not be opened or verified", commit_state="not_committed"))
        except BaseException:
            pool.shutdown(wait=True)
            raise

    def scoped_clients(self):
        return self

    def _live(self, context: ExecutionContext):
        if self._closed or self._closing:
            raise StorageFailure("SESSION_CLOSED", "Storage admissions have stopped")
        context.assert_active()
        if type(context.schema_version) is not int or context.schema_version != 1 or context.context_kind not in ("agent", "standalone_tool", "workflow"):
            raise EngineError("ACCESS_DENIED", "Context schema/kind is outside this Storage owner")
        if context.store_id != self.store_id:
            raise EngineError("ACCESS_DENIED", "Context belongs to another Storage owner")

    def authorize(self, context, operation, scope=None, object_id=None, producer=None, event_kind=None, origin=None):
        self._live(context)
        grant = context.authorize(operation, scope_ref(scope) if isinstance(scope, str) else scope, object_id, producer, event_kind, origin)
        if grant.mode == "observer":
            if operation not in ("events.status", "operation.status") or not grant.object_ids or object_id not in grant.object_ids or not grant.target_origin:
                raise EngineError("ACCESS_DENIED", "Observer authority requires exact targets and a frozen origin selector")
            if origin is not None and any(origin.get(k) != v for k, v in grant.target_origin.items()):
                raise EngineError("ACCESS_DENIED", "Target origin is outside the observer selector")
        return grant

    def origin(self, context, scope=None, producer=None):
        value = {"principal": context.principal, "run_id": context.run_id, "action_id": context.action_id, "attempt_id": context.attempt_id}
        if scope is not None:
            value["scope"] = scope
        if producer is not None:
            value["producer"] = producer
        else:
            value["caller"] = context.principal
        return value

    def _visibility_probe(self, context, operation, object_id):
        self._live(context)
        for grant in context.grants.grants if context.grants else []:
            try:
                return self.authorize(context, operation, grant.scope, object_id)
            except EngineError:
                continue
        raise EngineError("ACCESS_DENIED", "Object lookup is outside the bound selectors")

    async def _call(self, function: Callable, *args):
        if self._closed:
            raise StorageFailure("SESSION_CLOSED", "Storage session is closed")
        future = asyncio.get_running_loop().run_in_executor(self._pool, function, *args)
        self._active.add(future)
        future.add_done_callback(self._active.discard)
        try:
            return await asyncio.shield(future)
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            raise StorageFailure("STORAGE_BUSY" if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else "STORAGE_UNAVAILABLE", "SQLite operation did not complete", commit_state="unknown", details={"sqlite_errorname": getattr(exc, "sqlite_errorname", "unknown")}) from None

    async def provision_run(self, admin_context, run_descriptor):
        try:
            descriptor = to_json_value(run_descriptor)
            if not isinstance(descriptor, dict) or "run_id" not in descriptor:
                raise StorageFailure("INVALID_DATA", "Run descriptor requires run_id")
            run_id = opaque(descriptor["run_id"])
            scope = scope_key(ScopeRef("run", run_id))
            self.authorize(admin_context, "admin.provision", scope)
            canonical_json(descriptor, 64 << 10)
            await self._call(self._backend.provision, run_id, scope, descriptor)
            return Ok(scope_ref(scope))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def describe_run(self, context, run_id):
        try:
            run_id = opaque(run_id)
            self.authorize(context, "run.describe", ScopeRef("run", run_id), run_id)
            context.ledger.consume("storage_reads")
            descriptor = await self._call(self._backend.describe_run, run_id)
            if descriptor is None:
                raise StorageFailure("NOT_FOUND", "Authorized run was not found")
            self.authorize(context, "run.describe", ScopeRef("run", run_id), run_id)
            context.ledger.consume("storage_read_bytes", len(canonical_json(descriptor, 64 << 10)))
            return Ok(descriptor)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def list_runs(self, context, filters=None, cursor=None, limit=100):
        """Discover only runs registered to the current host principal."""
        try:
            _page_limit(limit)
            filters = _catalog_filters(filters)
            grant = self.authorize(context, "runs.list", object_id=context.principal)
            context.ledger.consume("storage_reads")
            binding = {"kind": "runs", "store_id": self.store_id,
                       "principal": context.principal, "grant": _grant_identity(grant), "filters": filters}
            last, high = self._catalog_position(cursor, binding)
            rows, high, more = await self._call(self._backend.list_runs, context.principal,
                                               filters, last, high, limit)
            self.authorize(context, "runs.list", object_id=context.principal)
            # Context identity and definition descriptors are public; arbitrary
            # caller metadata is not needed to discover or control runs.
            public_fields = {"schema_version", "run_id", "root_run_id", "correlation_id", "action_id",
                "principal", "context_kind", "agent_id", "definition_ref", "attempt_id",
                "parent_run_id", "parent_action_id", "parent_attempt_id", "root_action_id", "deadline",
                "depth", "ancestry", "binding_ref", "policy_ref", "purpose", "store_id", "scope",
                "owner_principal"}
            descriptors = [{key: value for key, value in row["descriptor"].items() if key in public_fields}
                           for row in rows]
            return self._catalog_page(context, "runs", descriptors, rows, high, more, binding)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def list_objects(self, context, scope, cursor=None, limit=100):
        """List committed immutable objects in one explicitly owned scope."""
        try:
            _page_limit(limit)
            scope = scope_key(scope)
            grant = self.authorize(context, "objects.list", scope)
            context.ledger.consume("storage_reads")
            await self._owned_scope(context, scope)
            binding = {"kind": "objects", "store_id": self.store_id, "principal": context.principal,
                       "scope": scope, "grant": _grant_identity(grant)}
            last, high = self._catalog_position(cursor, binding)
            rows, high, more = await self._call(self._backend.list_objects, scope, last, high, limit)
            descriptors = [await self._object_descriptor(row["kind"], row["row"]) for row in rows]
            self.authorize(context, "objects.list", scope)
            await self._owned_scope(context, scope)
            return self._catalog_page(context, "objects", descriptors, rows, high, more, binding)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def describe_object(self, context, object_ref):
        """Inspect public metadata under its actual scoped object read grant."""
        try:
            kind = next((name for name, cls in (("artifact", ArtifactRef), ("snapshot", SnapshotRef),
                        ("checkpoint", CheckpointRef)) if isinstance(object_ref, cls) or
                        isinstance(object_ref, dict) and name + "_id" in object_ref), None)
            if kind is None:
                raise StorageFailure("INVALID_DATA", "Object description requires a typed immutable reference")
            ref = typed_ref(object_ref, kind, self.store_id)
            self._visibility_probe(context, kind + ".read", ref.id)
            row = await self._call(self._backend.object_row, kind, ref.id)
            if row is None:
                raise StorageFailure("NOT_FOUND", "Authorized object was not found")
            try:
                grant = self.authorize(context, kind + ".read", row["scope"], ref.id)
            except EngineError:
                raise StorageFailure("NOT_FOUND", "Authorized object was not found") from None
            context.ledger.consume("storage_reads")
            descriptor = await self._object_descriptor(kind, row)
            if grant.allowed_media_types is not None and descriptor["media_type"] not in grant.allowed_media_types:
                raise EngineError("ACCESS_DENIED", "Object media type is outside the bound read selector")
            if grant.allowed_formats is not None and descriptor.get("format") not in grant.allowed_formats:
                raise EngineError("ACCESS_DENIED", "Object format is outside the bound read selector")
            self.authorize(context, kind + ".read", row["scope"], ref.id)
            context.ledger.consume("storage_read_bytes", len(canonical_json(descriptor, 64 << 10)))
            return Ok(descriptor)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def latest_run_event(self, context, run_id, kind="agent.finished"):
        """Return the latest visible matching recorded event, without replay."""
        try:
            run_id, kind = opaque(run_id), opaque(kind)
            selectors, _ = _history_selectors(self, context)
            if scope_key(ScopeRef("run", run_id)) not in {entry["scope"] for entry in selectors}:
                raise EngineError("ACCESS_DENIED", "Run event lookup requires target scope history authority")
            context.ledger.consume("storage_reads")
            event = await self._call(self._backend.latest_event, selectors, run_id, kind)
            _recheck_history(self, context, selectors)
            context.ledger.consume("storage_read_bytes", len(canonical_json(event, 1 << 20)))
            return Ok(event)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def history_watermark(self, context):
        """Capture the committed store-wide sequence clock, without event data.

        Connections captures this before discovering a lineage and issuing
        exact-scope history grants, then caps that poll to the captured clock.
        """
        try:
            if context.scope is None:
                raise EngineError("ACCESS_DENIED", "History clock requires a scoped read context")
            self.authorize(context, "events.read", context.scope)
            context.ledger.consume("storage_reads")
            high = await self._call(self._backend.history_watermark)
            self.authorize(context, "events.read", context.scope)
            context.ledger.consume("storage_read_bytes", len(canonical_json(high, 32)))
            return Ok(high)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def _owned_scope(self, context, scope):
        descriptor = await self._call(self._backend.describe_scope, scope)
        if descriptor is None or descriptor.get("owner_principal") != context.principal or context.principal == "platform-internal":
            raise EngineError("ACCESS_DENIED", "Scope discovery requires ownership by the current principal")

    def _catalog_position(self, cursor, binding):
        if cursor is None:
            return 0, None
        saved = self._cursors.open(cursor)
        if any(saved.get(key) != value for key, value in binding.items()):
            raise StorageFailure("INVALID_CURSOR", "Catalog cursor changed owner, scope, filters or authority")
        return saved["last"], saved["high"]

    def _catalog_page(self, context, name, descriptors, rows, high, more, binding):
        bounded, used = [], 2
        for descriptor in descriptors:
            size = len(canonical_json(descriptor, 64 << 10)) + 1
            if used + size > (1 << 20) - (32 << 10):
                more = True
                break
            bounded.append(descriptor)
            used += size
        if more and not bounded:
            raise StorageFailure("LIMIT_EXCEEDED", "One catalog descriptor exceeds the page byte limit")
        cursor = self._cursors.seal({**binding, "last": rows[len(bounded) - 1]["position"],
                                   "high": high, "expires": time.time() + 86400}) if more and bounded else None
        page = {name: bounded, "cursor": cursor, "schema_version": 1}
        context.ledger.consume("storage_read_bytes", len(canonical_json(page, 1 << 20)))
        return Ok(page)

    async def _object_descriptor(self, kind, row):
        descriptor = {"schema_version": 1, "kind": kind, "ref": self._ref(kind, row["object_id"]),
                      "scope": scope_ref(row["scope"]).to_dict()}
        if kind == "artifact":
            if row["phase"] != "ready":
                raise StorageFailure("INCOMPLETE_ARTIFACT", "Object metadata is not READY")
            descriptor.update({key: row[key] for key in ("byte_length", "sha256", "media_type")})
        else:
            value = row["descriptor"]
            role = "text" if kind == "snapshot" else "payload"
            component = await self._call(self._backend.object_row, "artifact", value["refs"][role]["artifact_id"])
            if component is None or component["phase"] != "ready":
                raise StorageFailure("INCOMPLETE_ARTIFACT", "Object component metadata is not READY")
            descriptor.update({key: component[key] for key in ("byte_length", "sha256", "media_type")})
            fields = ("extraction_version", "normalization_version", "line_count", "physical_page_count") if kind == "snapshot" else ("format", "run_id")
            descriptor.update({key: value[key] for key in fields})
        return descriptor

    async def provision_scope(self, admin_context, scope, descriptor=None):
        try:
            scope = scope_key(scope)
            if not scope.startswith("shared:"):
                raise StorageFailure("INVALID_DATA", "Run scopes use provision_run with a run descriptor")
            self.authorize(admin_context, "admin.provision", scope)
            descriptor = to_json_value(descriptor or {})
            canonical_json(descriptor, 64 << 10)
            await self._call(self._backend.provision_scope, scope, descriptor)
            return Ok(scope_ref(scope))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    def _event(self, context, kind, operation_id, payload, *, event_id=None):
        return {"schema_version": 1, "event_id": event_id or "ev_" + uuid.uuid5(uuid.NAMESPACE_URL, self.store_id + ":" + operation_id + ":" + kind).hex, "kind": kind, "producer": "storage", "context": context.descriptor(), "producer_timestamp": utc_now(), "payload": payload}

    def _ref(self, kind, object_id):
        return {"schema_version": 1, "store_id": self.store_id, kind + "_id": object_id}

    async def _write(self, context, operation_id, method, scopes, request, writer, *, byte_count=0, authority_objects=None, owned_sources=()):
        operation_id = opaque(operation_id)
        def authorize_write():
            for scope in scopes:
                for object_id in authority_objects.get(scope, ()) if authority_objects is not None else (operation_id,):
                    grant = self.authorize(context, method, scope, object_id)
                    if grant.max_bytes is not None and byte_count > grant.max_bytes:
                        raise EngineError("LIMIT_EXCEEDED", "Storage publication exceeds the bound byte selector")
        authorize_write()
        origin = self.origin(context, scopes[0] if len(scopes) == 1 else None)
        if len(scopes) > 1:
            origin["scopes"] = scopes
        fingerprint = digest(canonical_json({"method": method, "origin": origin, "request": request}, 8 << 20))
        key = "op:" + operation_id
        async with self._admission:
            # Current authorization precedes receipt/pending disclosure. Dedup comes
            # before all fresh-write reservations and before source consumption.
            pending = self._pending.get(key)
            if pending:
                if pending["fingerprint"] != fingerprint or pending["origin"] != origin:
                    raise StorageFailure("IDEMPOTENCY_CONFLICT", "Admitted operation differs from the original")
                raise StorageFailure("OPERATION_PENDING", "Operation remains admitted", commit_state="unknown", details={"operation_id": operation_id, "phase": pending["phase"]})
            existing = await self._call(self._backend.existing_operation, operation_id, fingerprint, origin)
            if existing is not None:
                context.ledger.consume("status_reads")
                return receipt_value(method, existing)
            authorize_write()
            if len(self._pending) >= 128:
                raise StorageFailure("STORAGE_BUSY", "Storage admission queue is full")
            if any(id(source) in self._sources for source in owned_sources):
                raise StorageFailure("STORAGE_BUSY", "An artifact source is already owned by an admitted operation")
            if context.ledger.remaining("storage_writes") < 1 or (byte_count and context.ledger.remaining("storage_bytes") < byte_count):
                raise EngineError("LIMIT_EXCEEDED", "Storage write or byte reservation exceeds the shared budget")
            context.ledger.consume("storage_writes")
            if byte_count:
                context.ledger.consume("storage_bytes", byte_count)
            self._pending[key] = {"fingerprint": fingerprint, "origin": origin, "phase": "queued"}
            for source in owned_sources:
                self._sources[id(source)] = source
            task = asyncio.create_task(writer(origin, fingerprint))
            self._writers.add(task)
            def settled(done):
                self._writers.discard(done)
                self._pending.pop(key, None)
                if not done.cancelled():
                    done.exception()  # Retrieve a defect even if the borrower was cancelled.
            task.add_done_callback(settled)
        return receipt_value(method, await asyncio.shield(task))

    async def _file_write(self, context, operation_id, method, scope, components, receipt, parent_kind=None, object_descriptor=None):
        scope = scope_key(scope)
        def content_length(c):
            return len(c["data"]) if c.get("data") is not None else c["byte_length"]
        def content_digest(c):
            return digest(c["data"]) if c.get("data") is not None else c["sha256"]
        request = {"scope": scope, "components": [{"role": c["role"], "byte_length": content_length(c), "sha256": content_digest(c), "media_type": c["media_type"], "metadata": c.get("metadata", {})} for c in components], "object_descriptor": object_descriptor}
        parent_id = (parent_kind or "artifact") + "_" + uuid.uuid5(uuid.NAMESPACE_URL, self.store_id + ":" + operation_id).hex
        descriptors, bodies, refs = [], {}, {}
        for component in components:
            role = component["role"]
            child_operation_id = operation_id if parent_kind is None else operation_id + ":" + role
            object_id = parent_id if parent_kind is None else "artifact_" + uuid.uuid5(uuid.NAMESPACE_URL, self.store_id + ":" + operation_id + ":" + role).hex
            ref = self._ref("artifact", object_id)
            refs[role] = ref
            data = component.get("data")
            details = {"artifact_ref": ref, "byte_length": content_length(component), "sha256": content_digest(component), "media_type": component["media_type"], "operation_id": child_operation_id, "component_role": role}
            descriptors.append({"role": role, "operation_id": child_operation_id, "object_id": object_id, "relative_key": "objects/" + object_id + ".bin", "stage_key": "staging/" + object_id + ".stage", "byte_length": content_length(component), "sha256": content_digest(component), "media_type": component["media_type"], "metadata": component.get("metadata", {}), "event": self._event(context, "artifact.committed", child_operation_id, details)})
            bodies[role] = data
        receipt = dict(receipt)
        if parent_kind is None:
            receipt["artifact_ref"] = refs["artifact"]
        elif parent_kind == "snapshot":
            receipt.update({"snapshot_ref": self._ref("snapshot", parent_id), "manifest_ref": refs["manifest"], "original_ref": refs["original"], "text_ref": refs["text"], "index_ref": refs["index"]})
        else:
            receipt.update({"checkpoint_ref": self._ref("checkpoint", parent_id), "payload_ref": refs["payload"]})
        descriptor = {"scope": scope, "object_id": parent_id, "components": descriptors, "receipt": receipt, "object_descriptor": {**(object_descriptor or {}), "refs": refs}, "event": self._event(context, {"snapshot": "snapshot.committed", "checkpoint": "checkpoint.saved"}.get(parent_kind, "artifact.committed"), operation_id, {"operation_id": operation_id, "refs": refs})}
        async def writer(origin, fingerprint):
            def publication_guard():
                # This is the existing reservation, so owner close does not deny
                # it. Current original authority still gates READY publication.
                context.authorize(method, scope_ref(scope), operation_id)
            source = components[0].get("source") if len(components) == 1 else None
            if source is None:
                await self._call(self._backend.reserve_files, operation_id, method, origin, fingerprint, descriptor)
                return await self._call(self._backend.publish_files, operation_id, bodies, publication_guard)
            failure = None
            try:
                await self._call(self._backend.reserve_files, operation_id, method, origin, fingerprint, descriptor)
                await self._call(self._backend.start_stream, operation_id)
                received = 0
                while True:
                    publication_guard()
                    remaining = context.remaining_seconds()
                    request_bytes = min(64 << 10, max(1, content_length(components[0]) - received + 1))
                    try:
                        chunk = await asyncio.wait_for(source.read(request_bytes), remaining)
                    except asyncio.TimeoutError:
                        raise StorageFailure("DEADLINE_EXCEEDED", "Artifact source did not finish within its admitted deadline") from None
                    if not isinstance(chunk, bytes) or len(chunk) > request_bytes:
                        raise StorageFailure("INVALID_DATA", "Artifact source returned an invalid bounded byte chunk")
                    if not chunk:
                        break
                    received += len(chunk)
                    await self._call(self._backend.stream_chunk, operation_id, chunk)
                await self._call(self._backend.seal_stream, operation_id)
            except BaseException as exc:
                failure = exc
            try:
                await asyncio.wait_for(source.aclose(), 2)
                self._sources.pop(id(source), None)
            except BaseException as exc:
                if failure is None:
                    failure = StorageFailure("STORAGE_BUSY", "Owned artifact source cleanup is incomplete", details={"operation_id": operation_id})
            if failure is not None:
                await self._call(self._backend.abort_stream, operation_id, getattr(failure, "code", "SOURCE_FAILED"))
                if isinstance(failure, OSError):
                    raise StorageFailure("STORAGE_UNAVAILABLE", "Artifact source I/O failed before publication", commit_state="not_committed") from None
                if isinstance(failure, EngineError):
                    failure.commit_state = "not_committed"
                raise failure
            try:
                return await self._call(self._backend.finish_files, operation_id, publication_guard)
            except EngineError as exc:
                await self._call(self._backend.abort_stream, operation_id, exc.code)
                exc.commit_state = "not_committed"
                raise
        source = components[0].get("source") if len(components) == 1 else None
        return await self._write(context, operation_id, method, [scope], request, writer, byte_count=sum(content_length(c) for c in components), owned_sources=(source,) if source is not None else ())

    async def close(self, deadline=None):
        if self._close_task is not None:
            return await self._await_close(deadline)
        if self._closed:
            from deepresearch.engine.contracts import CloseReceipt
            return Ok(CloseReceipt(self.store_id, True, [], []))
        self._closing = True
        from deepresearch.engine.contracts import deadline_timestamp
        remaining = max(0, deadline_timestamp(deadline) - time.time())
        tasks = tuple(self._writers | self._active)
        try:
            if tasks:
                await asyncio.wait_for(asyncio.shield(asyncio.gather(*tasks, return_exceptions=True)), remaining)
        except asyncio.TimeoutError:
            return Err(EngineError("STORAGE_BUSY", "Storage is draining admitted operations", {"pending_operation_ids": [k.removeprefix("op:") for k in self._pending if k.startswith("op:")]}, commit_state="unknown", retryable_delivery=True))
        for identity, source in tuple(self._sources.items()):
            try:
                await asyncio.wait_for(source.aclose(), min(2, max(0, deadline_timestamp(deadline) - time.time())))
                self._sources.pop(identity, None)
            except Exception:
                return Err(EngineError("STORAGE_BUSY", "Storage retains an unclosed artifact source", {"pending_sources": len(self._sources)}, commit_state="not_committed", retryable_delivery=True))
        async with self._admission:
            if self._close_task is None:
                async def finish_close():
                    try:
                        receipt = await self._call(self._backend.close)
                        self._closed = True
                        self._pool.shutdown(wait=True)
                        from deepresearch.engine.contracts import CloseReceipt
                        return Ok(CloseReceipt(**receipt))
                    except (StorageFailure, EngineError, OSError) as exc:
                        self._close_task = None
                        return error_result(exc)
                    except BaseException:
                        self._close_task = None
                        raise
                self._close_task = asyncio.create_task(finish_close())
        return await self._await_close(deadline)

    async def _await_close(self, deadline):
        from deepresearch.engine.contracts import deadline_timestamp
        remaining = max(0, deadline_timestamp(deadline) - time.time())
        try:
            return await asyncio.wait_for(asyncio.shield(self._close_task), remaining)
        except asyncio.TimeoutError:
            return Err(EngineError("STORAGE_BUSY", "Storage owner is finalizing admitted publications", {"phase": "draining"}, commit_state="unknown", retryable_delivery=True))


class StateStore:
    def __init__(self, session):
        self.session = session

    async def get(self, context, scope, key):
        return await self._get(context, scope, key, None)

    async def get_version(self, context, scope, key, version):
        return await self._get(context, scope, key, version)

    async def _get(self, context, scope, key, version):
        try:
            scope = scope_key(scope)
            key = opaque(key)
            if version is not None and (type(version) is not int or version <= 0):
                raise StorageFailure("INVALID_DATA", "Historical revision must be positive")
            grant = self.session.authorize(context, "state.read", scope, key)
            context.ledger.consume("storage_reads")
            from deepresearch.engine.contracts import StateLookup
            value = StateLookup(**(await self.session._call(self.session._backend.state_get, scope, key, version)))
            size = len(canonical_json(value.to_dict(), (1 << 20) + (1 << 10)))
            self.session.authorize(context, "state.read", scope, key)
            if grant.max_bytes is not None and size > grant.max_bytes:
                raise EngineError("LIMIT_EXCEEDED", "State lookup exceeds the bound read limit")
            context.ledger.consume("storage_read_bytes", size)
            return Ok(value)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def commit(self, context, operation_id, mutations, activity=None):
        try:
            if not isinstance(mutations, (list, tuple)) or not 1 <= len(mutations) <= 100:
                raise StorageFailure("INVALID_DATA", "State batch must contain 1..100 mutations")
            values, seen = [], set()
            for raw in mutations:
                m = to_json_value(raw)
                if not isinstance(m, dict) or set(m) - {"scope", "key", "kind", "expected_version", "value"} or not {"scope", "key", "kind", "expected_version"}.issubset(m):
                    raise StorageFailure("INVALID_DATA", "Invalid state mutation fields")
                m["scope"], m["key"] = scope_key(m["scope"]), opaque(m["key"])
                if m["kind"] not in ("put", "delete") or type(m["expected_version"]) is not int or not 0 <= m["expected_version"] < 2**63:
                    raise StorageFailure("INVALID_DATA", "Invalid CAS mutation")
                if m["kind"] == "put":
                    if "value" not in m:
                        raise StorageFailure("INVALID_DATA", "Put requires a JSON value")
                    canonical_json(m["value"], 1 << 20)
                elif "value" in m and m["value"] is not None:
                    raise StorageFailure("INVALID_DATA", "Delete cannot contain a value")
                identity = (m["scope"], m["key"])
                if identity in seen:
                    raise StorageFailure("INVALID_DATA", "State batch repeats a key")
                seen.add(identity)
                values.append(m)
            activity = to_json_value(activity or {})
            request = {"mutations": values, "activity": activity}
            byte_count = len(canonical_json(request, 4 << 20))
            scopes = sorted({m["scope"] for m in values})
            event = self.session._event(context, "state.committed", operation_id, {"operation_id": operation_id, "activity": activity})
            async def writer(origin, fingerprint):
                return await self.session._call(self.session._backend.state_commit, operation_id, origin, fingerprint, values, event)
            authority_objects = {scope: [m["key"] for m in values if m["scope"] == scope] for scope in scopes}
            method = "state.cleanup" if context.purpose == "record_cleanup" else "state.commit"
            return Ok(await self.session._write(context, operation_id, method, scopes, request, writer, byte_count=byte_count, authority_objects=authority_objects))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)


class ArtifactStore:
    def __init__(self, session):
        self.session = session

    async def put(self, context, operation_id, scope, content, metadata=None):
        try:
            if isinstance(content, bytes):
                content = ArtifactContent(content)
            if not isinstance(content, ArtifactContent) or (content.data is not None and not isinstance(content.data, bytes)) or ((content.data is None) == (content.source is None)):
                raise StorageFailure("INVALID_DATA", "Artifact content requires immutable bytes or a declared async byte source")
            data = content.data
            if type(content.byte_length) is not int or content.byte_length < 0:
                raise StorageFailure("INTEGRITY_ERROR", "Artifact length descriptor must be a nonnegative integer")
            if content.byte_length > 8 << 20:
                raise StorageFailure("LIMIT_EXCEEDED", "Artifact exceeds 8 MiB")
            expected_digest = sha256_value(content.sha256)
            if data is not None and (content.byte_length != len(data) or expected_digest != digest(data)):
                raise StorageFailure("INTEGRITY_ERROR", "Artifact bytes differ from their declared descriptor")
            if content.source is not None and (not callable(getattr(content.source, "read", None)) or not callable(getattr(content.source, "aclose", None))):
                raise StorageFailure("INVALID_DATA", "Artifact source requires async read/aclose operations")
            metadata = to_json_value(metadata or {"media_type": "application/octet-stream"})
            if not isinstance(metadata, dict) or set(metadata) - {"media_type", "filename", "metadata", "display_filename"}:
                raise StorageFailure("INVALID_DATA", "Artifact metadata fields are unknown")
            media = metadata.get("media_type", "application/octet-stream")
            if not isinstance(media, str) or not re.fullmatch(r"[\w.+-]+/[\w.+-]+(?:;[^\r\n]*)?", media):
                raise StorageFailure("INVALID_DATA", "Artifact media type is invalid")
            canonical_json(metadata, 16 << 10)
            grant = self.session.authorize(context, "artifact.put", scope_key(scope), operation_id)
            if grant.allowed_media_types is not None and media not in grant.allowed_media_types:
                raise EngineError("ACCESS_DENIED", "Artifact media type is outside the bound publication selector")
            receipt = {"scope": scope_key(scope), "byte_length": content.byte_length, "sha256": expected_digest, "media_type": media}
            component = {"role": "artifact", "data": data, "source": content.source, "byte_length": content.byte_length, "sha256": expected_digest, "media_type": media, "metadata": metadata}
            return Ok(await self.session._file_write(context, operation_id, "artifact.put", scope, [component], receipt))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def open(self, context, artifact_ref, byte_range=None, max_bytes=8 << 20):
        try:
            ref = typed_ref(artifact_ref, "artifact", self.session.store_id)
            self.session._visibility_probe(context, "artifact.read", ref.id)
            row = await self.session._call(self.session._backend.object_row, "artifact", ref.id)
            if not row:
                raise StorageFailure("NOT_FOUND", "Authorized artifact was not found")
            try:
                grant = self.session.authorize(context, "artifact.read", row["scope"], ref.id)
            except EngineError:
                raise StorageFailure("NOT_FOUND", "Authorized artifact was not found") from None
            context.ledger.consume("storage_reads")
            raw = await self.session._call(self.session._backend.artifact_bytes, ref.id)
            if byte_range is None:
                interval = {"start": 0, "end_exclusive": len(raw)}
            else:
                interval = to_json_value(byte_range)
            if not isinstance(interval, dict) or set(interval) != {"start", "end_exclusive"} or any(type(v) is not int for v in interval.values()) or not 0 <= interval["start"] <= interval["end_exclusive"] <= len(raw):
                raise StorageFailure("INVALID_DATA", "Artifact byte range is invalid")
            if type(max_bytes) is not int or not 0 <= max_bytes <= 8 << 20 or interval["end_exclusive"] - interval["start"] > max_bytes:
                raise StorageFailure("LIMIT_EXCEEDED", "Artifact selection exceeds its cumulative byte allowance")
            if grant.byte_range is not None and not grant.byte_range["start"] <= interval["start"] <= interval["end_exclusive"] <= grant.byte_range["end_exclusive"]:
                raise EngineError("ACCESS_DENIED", "Artifact selection expands the bound byte range")
            if grant.max_bytes is not None and max_bytes > grant.max_bytes:
                raise EngineError("ACCESS_DENIED", "Artifact selection expands the bound byte allowance")
            return Ok(ArtifactRead(self.session, context, row["scope"], ref, raw, interval, max_bytes))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)


class ArtifactRead:
    def __init__(self, session, context, scope, ref, data, interval, allowance):
        self.session, self.context, self.scope, self.artifact_ref = session, context, scope, ref
        self._data, self._offset, self._end, self._allowance = data, interval["start"], interval["end_exclusive"], allowance
        self._start, self._requested_allowance = interval["start"], allowance
        self._closed = False

    async def read(self, context, max_bytes=64 << 10):
        try:
            if self._closed:
                raise StorageFailure("SESSION_CLOSED", "Artifact read is closed")
            if context.grants is not self.context.grants or context.principal != self.context.principal:
                raise EngineError("ACCESS_DENIED", "Artifact handle belongs to another authority")
            grant = self.session.authorize(context, "artifact.read", self.scope, self.artifact_ref.id)
            if grant.byte_range is not None and not grant.byte_range["start"] <= self._start <= self._end <= grant.byte_range["end_exclusive"]:
                raise EngineError("ACCESS_DENIED", "Artifact handle is outside the current byte range")
            if grant.max_bytes is not None and self._requested_allowance > grant.max_bytes:
                raise EngineError("ACCESS_DENIED", "Artifact handle is outside the current byte allowance")
            if type(max_bytes) is not int or not 1 <= max_bytes <= 8 << 20:
                raise StorageFailure("INVALID_DATA", "Artifact chunk limit must be positive and bounded")
            size = min(max_bytes, self._allowance, self._end - self._offset)
            data = self._data[self._offset:self._offset + size]
            context.ledger.consume("storage_read_bytes", len(data))
            self._offset += size
            self._allowance -= size
            from deepresearch.engine.contracts import ByteChunk
            return Ok(ByteChunk(data, self._offset == self._end, self._offset))
        except (StorageFailure, EngineError) as exc:
            return error_result(exc)

    async def aclose(self, context):
        if context.principal != self.context.principal or context.grants is not self.context.grants:
            return Err(EngineError("ACCESS_DENIED", "Artifact handle belongs to another principal"))
        self._closed, self._data = True, b""
        return Ok(None)


def typed_ref(value, kind, store_id):
    cls = {"artifact": ArtifactRef, "snapshot": SnapshotRef, "checkpoint": CheckpointRef}[kind]
    if isinstance(value, dict):
        try:
            value = cls(**value)
        except TypeError:
            raise StorageFailure("INVALID_DATA", "Typed reference fields are invalid") from None
    if not isinstance(value, cls) or type(value.schema_version) is not int or value.schema_version != 1:
        raise StorageFailure("INVALID_DATA", "Typed reference kind/version is invalid")
    if value.store_id != store_id:
        raise StorageFailure("NOT_FOUND", "Object is outside this Store")
    opaque(value.id)
    return value


class SnapshotStore:
    def __init__(self, session):
        self.session = session

    async def commit(self, context, operation_id, scope, proposal):
        try:
            if isinstance(proposal, dict):
                try:
                    proposal = SnapshotProposal(**proposal)
                except TypeError:
                    raise StorageFailure("INVALID_DATA", "Unknown snapshot proposal fields") from None
            if not isinstance(proposal, SnapshotProposal):
                raise StorageFailure("INVALID_DATA", "Snapshot requires a complete typed proposal")
            original = proposal.original
            text = proposal.text.encode("utf-8") if isinstance(proposal.text, str) else proposal.text
            raw_index = canonical_json(proposal.index, 1 << 20) if isinstance(proposal.index, dict) else proposal.index
            if not isinstance(original, bytes) or not isinstance(text, bytes) or not isinstance(raw_index, bytes):
                raise StorageFailure("INVALID_DATA", "Snapshot components require retained immutable bytes")
            if len(original) > 8 << 20:
                raise StorageFailure("LIMIT_EXCEEDED", "Retained source body exceeds 8 MiB")
            index = validate_index(text, raw_index)
            provenance = to_json_value(proposal.provenance)
            canonical_json(provenance, 64 << 10)
            for version in (proposal.extraction_version, proposal.normalization_version):
                opaque(version)
            scope = scope_key(scope)
            parent_id = "snapshot_" + uuid.uuid5(uuid.NAMESPACE_URL, self.session.store_id + ":" + operation_id).hex
            refs = {role: self.session._ref("artifact", "artifact_" + uuid.uuid5(uuid.NAMESPACE_URL, self.session.store_id + ":" + operation_id + ":" + role).hex) for role in ("original", "text", "index")}
            component_digests = {"original": digest(original), "text": digest(text), "index": digest(raw_index)}
            manifest = {"schema_version": 1, "format": "document_snapshot/1", "snapshot_ref": self.session._ref("snapshot", parent_id), "components": {role: {"ref": refs[role], "sha256": component_digests[role], "byte_length": len(data)} for role, data in (("original", original), ("text", text), ("index", raw_index))}, "extraction_version": proposal.extraction_version, "normalization_version": proposal.normalization_version, "line_count": len(index["lines"]), "physical_page_count": len(index["pages"]) if index["pages"] is not None else None, "provenance": provenance}
            raw_manifest = canonical_json(manifest, 256 << 10)
            component_digests["manifest"] = digest(raw_manifest)
            components = [{"role": "original", "data": original, "media_type": proposal.media_type}, {"role": "text", "data": text, "media_type": "text/plain;charset=utf-8"}, {"role": "index", "data": raw_index, "media_type": "application/json"}, {"role": "manifest", "data": raw_manifest, "media_type": "application/json"}]
            receipt = {"component_digests": component_digests, "extraction_version": proposal.extraction_version, "line_count": len(index["lines"]), "physical_page_count": manifest["physical_page_count"]}
            object_descriptor = {"manifest": manifest, "extraction_version": proposal.extraction_version, "normalization_version": proposal.normalization_version, "line_count": len(index["lines"]), "physical_page_count": manifest["physical_page_count"]}
            return Ok(await self.session._file_write(context, operation_id, "snapshot.commit", scope, components, receipt, "snapshot", object_descriptor))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def read(self, context, snapshot_ref, range, max_text_bytes=64 << 10, continuation=None):
        try:
            ref = typed_ref(snapshot_ref, "snapshot", self.session.store_id)
            self.session._visibility_probe(context, "snapshot.read", ref.id)
            row = await self.session._call(self.session._backend.object_row, "snapshot", ref.id)
            if not row:
                raise StorageFailure("NOT_FOUND", "Authorized snapshot was not found")
            try:
                grant = self.session.authorize(context, "snapshot.read", row["scope"], ref.id)
            except EngineError:
                raise StorageFailure("NOT_FOUND", "Authorized snapshot was not found") from None
            context.ledger.consume("storage_reads")
            requested = to_json_value(range)
            if not isinstance(requested, dict) or set(requested) != {"kind", "start", "end_exclusive"} or requested["kind"] not in ("lines", "pages") or type(requested["start"]) is not int or type(requested["end_exclusive"]) is not int or not 1 <= requested["start"] <= requested["end_exclusive"]:
                raise StorageFailure("INVALID_DATA", "Document range is not one strict half-open range")
            if type(max_text_bytes) is not int or not 1 <= max_text_bytes <= 64 << 10:
                raise StorageFailure("LIMIT_EXCEEDED", "Text byte budget must be positive and bounded")
            if grant.document_ranges is not None:
                matched = False
                for entry in grant.document_ranges:
                    allowed = entry["range"]
                    if requested["kind"] == allowed["kind"] and allowed["start"] <= requested["start"] <= requested["end_exclusive"] <= allowed["end_exclusive"] and max_text_bytes <= entry["max_text_bytes"]:
                        matched = True
                        break
                if not matched:
                    raise EngineError("ACCESS_DENIED", "Snapshot selection is outside all admitted document ranges")
            if grant.document_range is not None and (requested.get("kind") != grant.document_range["kind"] or not grant.document_range["start"] <= requested.get("start", -1) <= requested.get("end_exclusive", -1) <= grant.document_range["end_exclusive"]):
                raise EngineError("ACCESS_DENIED", "Snapshot selection expands the bound document range")
            if grant.max_text_bytes is not None and max_text_bytes > grant.max_text_bytes:
                raise EngineError("ACCESS_DENIED", "Snapshot selection expands the bound text allowance")
            descriptor = row["descriptor"]
            refs = descriptor["refs"]
            text = await self.session._call(self.session._backend.artifact_bytes, refs["text"]["artifact_id"])
            raw_index = await self.session._call(self.session._backend.artifact_bytes, refs["index"]["artifact_id"])
            index = validate_index(text, raw_index)
            authority = digest(canonical_json({"principal": context.principal, "grant": to_json_value(grant), "scope": row["scope"]}, 64 << 10))
            binding = {"store_id": self.session.store_id, "snapshot_id": ref.id, "extraction_version": descriptor["extraction_version"], "normalization_version": descriptor["normalization_version"], "requested_range": requested, "authority": authority}
            position = None
            if continuation is not None:
                cursor = self.session._cursors.open(continuation)
                if any(cursor.get(k) != v for k, v in binding.items()):
                    raise StorageFailure("INVALID_CURSOR", "Continuation changed snapshot/range/authority")
                position = cursor["position"]
            result, next_position = slice_document(text, index, requested, max_text_bytes, position)
            cursor = self.session._cursors.seal({**binding, "position": next_position, "expires": time.time() + 86400}) if next_position else None
            self.session.authorize(context, "snapshot.read", row["scope"], ref.id)
            context.ledger.consume("storage_read_bytes", len(result["text"].encode()))
            return Ok(DocumentSlice(snapshot_ref=ref, extraction_version=descriptor["extraction_version"], normalization_version=descriptor["normalization_version"], requested_range=result["requested_range"], returned_range=result["returned_range"], spans=result["spans"], text=result["text"], byte_length=len(result["text"].encode()), truncated=result["truncated"], has_more_in_requested_range=result["has_more_in_requested_range"], has_more_in_document=result["has_more_in_document"], next_position=next_position, continuation=cursor))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)


class CheckpointStore:
    def __init__(self, session):
        self.session = session

    async def save(self, context, operation_id, scope, checkpoint):
        try:
            checkpoint = to_json_value(checkpoint)
            required = {"schema_version", "format", "envelope_format_version", "payload_schema_version", "run_id", "payload"}
            if not isinstance(checkpoint, dict) or set(checkpoint) != required or checkpoint["schema_version"] != 1 or checkpoint["envelope_format_version"] != 1 or type(checkpoint["payload_schema_version"]) is not int or checkpoint["payload_schema_version"] <= 0 or checkpoint["format"] != "engine_checkpoint/1" or checkpoint["run_id"] != context.run_id or not isinstance(checkpoint["payload"], dict):
                raise StorageFailure("INCOMPATIBLE_CHECKPOINT", "Checkpoint does not match the accepted engine_checkpoint/1 envelope")
            def safe(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key.lower() in {"api_key", "authorization", "access_token", "password", "secret", "credentials", "grants", "cancellation", "monotonic_deadline"}:
                            raise StorageFailure("INCOMPATIBLE_CHECKPOINT", "Checkpoint contains forbidden live/credential fields")
                        safe(item)
                elif isinstance(value, list):
                    for item in value:
                        safe(item)
            safe(checkpoint)
            raw = canonical_json(checkpoint, 4 << 20)
            grant = self.session.authorize(context, "checkpoint.save", scope_key(scope), operation_id)
            if grant.allowed_formats is not None and checkpoint["format"] not in grant.allowed_formats:
                raise EngineError("ACCESS_DENIED", "Checkpoint format is outside the bound publication selector")
            receipt = {"byte_length": len(raw), "sha256": digest(raw), "envelope_format_version": 1}
            return Ok(await self.session._file_write(context, operation_id, "checkpoint.save", scope, [{"role": "payload", "data": raw, "media_type": "application/json"}], receipt, "checkpoint", {"format": checkpoint["format"], "run_id": checkpoint["run_id"]}))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def load(self, context, checkpoint_ref, accepted_formats=("engine_checkpoint/1",)):
        try:
            ref = typed_ref(checkpoint_ref, "checkpoint", self.session.store_id)
            self.session._visibility_probe(context, "checkpoint.read", ref.id)
            row = await self.session._call(self.session._backend.object_row, "checkpoint", ref.id)
            if not row:
                raise StorageFailure("NOT_FOUND", "Authorized checkpoint was not found")
            try:
                grant = self.session.authorize(context, "checkpoint.read", row["scope"], ref.id)
            except EngineError:
                raise StorageFailure("NOT_FOUND", "Authorized checkpoint was not found") from None
            if row["descriptor"]["format"] not in accepted_formats:
                raise StorageFailure("INCOMPATIBLE_CHECKPOINT", "Checkpoint format is outside the accepted formats")
            context.ledger.consume("storage_reads")
            raw = await self.session._call(self.session._backend.artifact_bytes, row["descriptor"]["refs"]["payload"]["artifact_id"])
            if grant.max_bytes is not None and len(raw) > grant.max_bytes:
                raise EngineError("LIMIT_EXCEEDED", "Checkpoint exceeds the bound read byte allowance")
            if grant.allowed_formats is not None and row["descriptor"]["format"] not in grant.allowed_formats:
                raise EngineError("ACCESS_DENIED", "Checkpoint format is outside the bound read selector")
            value = strict_json(raw, 4 << 20)
            self.session.authorize(context, "checkpoint.read", row["scope"], ref.id)
            context.ledger.consume("storage_read_bytes", len(raw))
            from deepresearch.engine.contracts import CheckpointEnvelope
            return Ok(CheckpointEnvelope(**value))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)


class ActivityRecorder:
    def __init__(self, session):
        self.session = session

    async def append(self, context, event):
        try:
            value = to_json_value(event)
            required = {"schema_version", "event_id", "kind", "producer", "context", "payload", "producer_timestamp"}
            if not isinstance(value, dict) or set(value) != required or type(value["schema_version"]) is not int or value["schema_version"] != 1:
                raise StorageFailure("INVALID_DATA", "Event fields/version do not match ExecutionEvent")
            event_id = opaque(value["event_id"])
            kind, producer = opaque(value["kind"]), opaque(value["producer"])
            causal = value["context"]
            for field in ("run_id", "root_run_id", "correlation_id", "action_id", "attempt_id", "principal"):
                if not isinstance(causal, dict) or causal.get(field) != context.descriptor().get(field):
                    raise EngineError("ACCESS_DENIED", "Event cause differs from the bound execution context")
            if kind in {"model.intent", "model.outcome", "tool.intent", "tool.outcome", "invocation.intent", "invocation.outcome"} and not context.attempt_id:
                raise StorageFailure("INVALID_DATA", "Dispatch lifecycle requires an attempt ID")
            if kind in {"agent.started", "agent.finished"} and context.attempt_id is not None:
                raise StorageFailure("INVALID_DATA", "Agent bookkeeping uses its root action without an attempt")
            scope = scope_key(context.scope or ScopeRef("run", context.run_id))
            self.session.authorize(context, "events.append", scope, event_id, producer, kind)
            raw = canonical_json(value, 64 << 10)
            event_digest = digest(raw)
            origin = self.session.origin(context, scope, producer)
            key = "event:" + event_id
            async with self.session._admission:
                pending = self.session._pending.get(key)
                if pending:
                    if pending["fingerprint"] != event_digest or pending["origin"] != origin:
                        raise StorageFailure("IDEMPOTENCY_CONFLICT", "Admitted event differs from its original")
                    raise StorageFailure("OPERATION_PENDING", "Event remains admitted", commit_state="unknown", details={"event_id": event_id})
                existing = await self.session._call(self.session._backend.event_row, event_id)
                if existing:
                    if existing["digest"] != event_digest or existing["origin"] != origin:
                        raise StorageFailure("IDEMPOTENCY_CONFLICT", "Event content/origin differs from its original")
                    context.ledger.consume("status_reads")
                    return Ok(event_receipt(self.session._backend.receipt(existing, True)))
                self.session.authorize(context, "events.append", scope, event_id, producer, kind)
                if len(self.session._pending) >= 128:
                    raise StorageFailure("STORAGE_BUSY", "Storage admission queue is full")
                context.ledger.consume("storage_writes")
                self.session._pending[key] = {"fingerprint": event_digest, "origin": origin, "phase": "appending"}
                task = asyncio.create_task(self.session._call(self.session._backend.append, value, origin, [scope], event_digest))
                self.session._writers.add(task)
                def settled(done):
                    self.session._writers.discard(done)
                    self.session._pending.pop(key, None)
                    if not done.cancelled():
                        done.exception()
                task.add_done_callback(settled)
            return Ok(event_receipt(await asyncio.shield(task)))
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def status(self, context, event_id, expected_event_digest=None):
        try:
            event_id = opaque(event_id)
            if expected_event_digest is not None:
                expected_event_digest = sha256_value(expected_event_digest)
            grant = self.session._visibility_probe(context, "events.status", event_id)
            context.ledger.consume("status_reads")
            pending = self.session._pending.get("event:" + event_id)
            row = None if pending else await self.session._call(self.session._backend.event_row, event_id)
            origin = pending["origin"] if pending else row["origin"] if row else None
            _status_origin(context, grant, origin)
            if origin:
                for scope in origin.get("scopes", [origin.get("scope")]):
                    self.session.authorize(context, "events.status", scope, event_id, origin.get("producer"), row["kind"] if row else None, origin)
            actual_digest = pending["fingerprint"] if pending else row["digest"] if row else None
            if expected_event_digest is not None and actual_digest is not None and sha256_value(expected_event_digest) != actual_digest:
                raise StorageFailure("IDEMPOTENCY_CONFLICT", "Expected event digest differs from the authorized target")
            from deepresearch.engine.contracts import EventStatus
            result = EventStatus(store_id=self.session.store_id, event_id=event_id, state="pending" if pending else "committed" if row else "absent", receipt=event_receipt(self.session._backend.receipt(row)) if row else None, pending_phase="appending" if pending else None)
            context.ledger.consume("storage_read_bytes", len(canonical_json(result.to_dict(), 64 << 10)))
            return Ok(result)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)


def _status_origin(context, grant, origin):
    if origin is None:
        return
    if grant.mode == "observer":
        if not grant.target_origin or any(origin.get(key) != value for key, value in grant.target_origin.items()):
            raise EngineError("ACCESS_DENIED", "Target origin is outside the observer selector")
    elif any(origin.get(key) != getattr(context, key) for key in ("principal", "run_id", "action_id", "attempt_id")):
        raise EngineError("ACCESS_DENIED", "Status belongs to another originating action")


class OperationStore:
    def __init__(self, session):
        self.session = session

    async def status(self, context, operation_id):
        try:
            operation_id = opaque(operation_id)
            grant = self.session._visibility_probe(context, "operation.status", operation_id)
            context.ledger.consume("status_reads")
            pending = self.session._pending.get("op:" + operation_id)
            row = None if pending else await self.session._call(self.session._backend.operation_row, operation_id)
            origin = pending["origin"] if pending else row["origin"] if row else None
            _status_origin(context, grant, origin)
            if origin:
                for scope in origin.get("scopes", [origin.get("scope")]):
                    self.session.authorize(context, "operation.status", scope, operation_id, origin=origin)
            phase = pending["phase"] if pending else row["phase"] if row else None
            state = "committed" if phase == "ready" else phase if phase in ("aborted", "interrupted") else "pending" if phase else "absent"
            from deepresearch.engine.contracts import OperationStatus
            result = OperationStatus(store_id=self.session.store_id, operation_id=operation_id, state=state, commit_state="committed" if phase == "ready" else "not_committed" if state in ("aborted", "interrupted") else "unknown", receipt=receipt_value(row["method"], row["receipt"]) if row and row["receipt"] else None, phase=phase, safe_disposition={"code": row["safe_disposition"], "message": "Publication was interrupted"} if row and row["safe_disposition"] else None)
            context.ledger.consume("storage_read_bytes", len(canonical_json(result.to_dict(), 64 << 10)))
            return Ok(result)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)


class ActivityReader:
    def __init__(self, session):
        self.session = session

    async def poll(self, context, filters=None, after_seq=0, limit=100, through_seq=None):
        """Read currently committed progress after a sequence, including future polls.

        Unlike query's fixed-watermark cursor, next_after_seq is a durable
        position. References/positions confer no history authority on reopen.
        """
        try:
            _page_limit(limit)
            if type(after_seq) is not int or not 0 <= after_seq <= 2**63 - 1:
                raise StorageFailure("INVALID_DATA", "Progress sequence must be a nonnegative signed 64-bit integer")
            if through_seq is not None and (type(through_seq) is not int or not 0 <= through_seq <= 2**63 - 1):
                raise StorageFailure("INVALID_DATA", "Progress watermark must be a nonnegative signed 64-bit integer")
            filters = to_json_value({} if filters is None else filters)
            if not isinstance(filters, dict) or set(filters) - {"run_id", "root_run_id", "action_id", "attempt_id", "correlation_id", "kind", "status"}:
                raise StorageFailure("INVALID_DATA", "Unsupported progress filters")
            for value in filters.values():
                if value is not None:
                    opaque(value)
            canonical_json(filters, 8192)
            selectors, _ = _history_selectors(self.session, context)
            context.ledger.consume("storage_reads")
            events, high, more = await self.session._call(self.session._backend.poll_events,
                                                         selectors, filters, after_seq, through_seq, limit)
            _recheck_history(self.session, context, selectors)
            bounded, used = [], 2
            for event in events:
                size = len(canonical_json(event, 128 << 10)) + 1
                if used + size > (1 << 20) - (32 << 10):
                    more = True
                    break
                bounded.append(event)
                used += size
            if more and not bounded:
                raise StorageFailure("LIMIT_EXCEEDED", "One progress event exceeds the page byte limit")
            page = {"events": bounded, "next_after_seq": bounded[-1]["receipt"]["recorded_seq"] if bounded else after_seq,
                    "has_more": more, "high_water_seq": high, "schema_version": 1}
            context.ledger.consume("storage_read_bytes", len(canonical_json(page, 1 << 20)))
            return Ok(page)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)

    async def query(self, context, filters=None, cursor=None, limit=100):
        try:
            if type(limit) is not int or not 1 <= limit <= 500:
                raise StorageFailure("LIMIT_EXCEEDED", "History page limit must be 1..500")
            filters = to_json_value(filters or {})
            allowed = {"run_id", "action_id", "attempt_id", "correlation_id", "kind", "status"}
            if not isinstance(filters, dict) or set(filters) - allowed:
                raise StorageFailure("INVALID_DATA", "Unsupported history filters")
            for value in filters.values():
                if value is not None:
                    opaque(value)
            query_selectors, selected_grants = _history_selectors(self.session, context)
            scopes = [selector["scope"] for selector in query_selectors]
            context.ledger.consume("storage_reads")
            binding = {"store_id": self.session.store_id, "principal": context.principal, "grants": selected_grants, "scopes": sorted(set(scopes)), "filters": filters}
            last, high = 0, None
            if cursor:
                saved = self.session._cursors.open(cursor)
                if any(saved.get(k) != v for k, v in binding.items()):
                    raise StorageFailure("INVALID_CURSOR", "History cursor changed filters or authority")
                last, high = saved["last"], saved["high"]
            events, high, more = await self.session._call(self.session._backend.query_events, query_selectors, filters, last, high, limit)
            _recheck_history(self.session, context, query_selectors)
            bounded = []
            used = 2
            for event in events:
                size = len(canonical_json(event, 128 << 10)) + 1
                if used + size > (1 << 20) - (32 << 10):
                    more = True
                    break
                used += size
                bounded.append(event)
            events = bounded
            if more and not events:
                raise StorageFailure("LIMIT_EXCEEDED", "A history record exceeds the page byte limit")
            next_cursor = self.session._cursors.seal({**binding, "last": events[-1]["receipt"]["recorded_seq"], "high": high, "expires": time.time() + 86400}) if more and events else None
            from deepresearch.engine.contracts import ActivityPage
            result = ActivityPage(store_id=self.session.store_id, events=events, cursor=next_cursor, high_water_seq=high)
            context.ledger.consume("storage_read_bytes", len(canonical_json(result.to_dict(), 1 << 20)))
            return Ok(result)
        except (StorageFailure, EngineError, OSError) as exc:
            return error_result(exc)
