"""Fresh, bounded data access after execution; no executable binding escapes."""
from __future__ import annotations

import dataclasses
import types

from ebd.contracts import *
from .models import *


class IdentityService:
    def __init__(self, session):
        self._session = session
        self._ids = set()

    def allocate(self):
        self._session.context.assert_active()
        value = new_id("operation_")
        self._ids.add(value)
        ctx = self._session.context
        ctx.grants.grants.append(Grant("operation.status", ctx.scope, frozenset({value}), run_id=ctx.run_id))
        return value

    def check(self, value):
        if value not in self._ids:
            raise EngineError("ACCESS_DENIED", "Publication identity was not issued by this session")


class RunAccessSession:
    def __init__(self, engine, context, request, options):
        self._engine, self.context, self.request, self.options = engine, context, request, options
        self.identity_service = IdentityService(self)
        self.lease = context.lease
        self.history = AccessHistory(self)
        self.storage = types.SimpleNamespace(artifacts=AccessArtifacts(self), snapshots=AccessSnapshots(self),
            checkpoints=AccessCheckpoints(self), operations=AccessStatuses(self, False),
            recorder=AccessStatuses(self, True), activity=self.history)
        self._read_bytes = self._write_bytes = self._operations = 0
        self._publication_usage = {}
        self._created = set()
        self._deliveries = {}
        self.descriptor = {"access_session_id": new_id("access_"), "target": RunRef(context.store_id, context.run_id).to_dict(),
            "principal": context.principal, "purpose": context.purpose, "action_id": context.action_id,
            "deadline": context.deadline, "request": request.to_dict(), "options": options.to_dict()}

    def check_context(self, context):
        if context is not self.context:
            raise EngineError("ACCESS_DENIED", "Data session requires its exact live context")
        context.assert_active()

    def charge(self, *, read=0, write=0):
        if self._operations + 1 > self.options.max_operations or self._read_bytes + read > self.options.max_total_read_bytes or self._write_bytes + write > self.options.max_total_write_bytes:
            raise EngineError("LIMIT_EXCEEDED", "Result-access quota is exhausted")
        self._operations += 1
        self._read_bytes += read
        self._write_bytes += write

    def publication(self, operation, scope, byte_count, *, media=None, format=None):
        for index, selector in enumerate(self.request.publications):
            if selector.operation != operation or selector.scope != scope:
                continue
            if media is not None and media not in selector.allowed_media_types:
                continue
            if format is not None and format not in selector.allowed_formats:
                continue
            count, used = self._publication_usage.get(index, (0, 0))
            if byte_count > selector.max_object_bytes or count >= selector.max_operations or used + byte_count > selector.max_total_bytes:
                raise EngineError("LIMIT_EXCEEDED", "Publication exceeds the admitted selector")
            self.charge(write=byte_count)
            self._publication_usage[index] = count + 1, used + byte_count
            return selector
        raise EngineError("ACCESS_DENIED", "Publication is outside the admitted purpose/media/format")

    def created(self, receipt, selector):
        if selector.read_created:
            ref = getattr(receipt, "artifact_ref", None) or getattr(receipt, "checkpoint_ref", None)
            self._created.add(ref)
            kind = "artifact" if isinstance(ref, ArtifactRef) else "checkpoint"
            self.context.grants.grants.append(Grant(kind + ".read", selector.scope, frozenset({ref.id}), run_id=self.context.run_id))

    async def close(self, deadline=None):
        await self.lease.release()
        if self in self._engine._sessions:
            self._engine._sessions.remove(self)
        return CleanupReport()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


class AccessArtifacts:
    def __init__(self, session):
        self.s = session

    async def open(self, context, ref, byte_range=None, max_bytes=8388608):
        try:
            self.s.check_context(context)
            selector = next((r for r in self.s.request.read_objects if isinstance(r, ArtifactReadRequest) and r.ref == ref), None)
            if selector is None and ref not in self.s._created:
                raise EngineError("ACCESS_DENIED", "Artifact was not selected")
            if selector and (max_bytes > selector.max_bytes or byte_range != selector.range):
                raise EngineError("ACCESS_DENIED", "Artifact range or byte limit expanded")
            self.s.charge()
            opened = await self.s._engine.storage.artifacts.open(context, ref, byte_range, max_bytes)
            return Ok(AccessArtifactRead(self.s, opened.value)) if isinstance(opened, Ok) else opened
        except EngineError as error:
            return Err(error)

    async def put(self, context, operation_id, scope, content, metadata=None):
        try:
            self.s.check_context(context)
            self.s.identity_service.check(operation_id)
            data = content.data if isinstance(content, ArtifactContent) else content
            size = content.byte_length if isinstance(content, ArtifactContent) else len(data)
            sha256 = content.sha256 if isinstance(content, ArtifactContent) else digest_bytes(data)
            meta = to_json_value(metadata or ArtifactMetadata("application/octet-stream"))
            fingerprint = digest_json({"scope": scope, "metadata": meta, "sha256": sha256, "byte_length": size})
            prior = self.s._deliveries.get(operation_id)
            if prior:
                if prior[0] != fingerprint:
                    raise EngineError("IDEMPOTENCY_CONFLICT", "Publication delivery changed")
                context.authorize("artifact.put", scope, operation_id)
                result = await self.s._engine.storage.artifacts.put(context, operation_id, scope, content, metadata)
                if isinstance(result, Ok):
                    self.s.created(result.value, prior[1])
                return result
            selector = self.s.publication("artifact.put", scope, size, media=meta["media_type"])
            self.s._deliveries[operation_id] = (fingerprint, selector)
            result = await self.s._engine.storage.artifacts.put(context, operation_id, scope, content, metadata)
            if isinstance(result, Ok):
                self.s.created(result.value, selector)
            return result
        except EngineError as error:
            return Err(error)


class AccessArtifactRead:
    def __init__(self, session, handle):
        self.s, self._handle = session, handle

    async def read(self, context, max_bytes=65536):
        try:
            self.s.check_context(context)
            available = self.s.options.max_total_read_bytes - self.s._read_bytes
            if available < max_bytes:
                raise EngineError("LIMIT_EXCEEDED", "Read would exceed the access byte budget")
            result = await self._handle.read(context, max_bytes)
            if isinstance(result, Ok):
                self.s.charge(read=len(result.value.bytes))
            return result
        except EngineError as error:
            return Err(error)

    async def aclose(self, context):
        return await self._handle.aclose(context)


class AccessSnapshots:
    def __init__(self, session):
        self.s = session

    async def read(self, context, ref, range, max_text_bytes=65536, continuation=None):
        try:
            self.s.check_context(context)
            selector = next((r for r in self.s.request.read_objects if isinstance(r, SnapshotReadRequest) and r.ref == ref and r.range == range), None)
            if not selector or range != selector.range or max_text_bytes > selector.max_text_bytes:
                raise EngineError("ACCESS_DENIED", "Snapshot read expanded the selected object/range")
            if max_text_bytes > self.s.options.max_total_read_bytes - self.s._read_bytes:
                raise EngineError("LIMIT_EXCEEDED", "Snapshot read would exceed the access byte budget")
            result = await self.s._engine.storage.snapshots.read(context, ref, range, max_text_bytes, continuation)
            if isinstance(result, Ok):
                self.s.charge(read=result.value.byte_length)
            return result
        except EngineError as error:
            return Err(error)


class AccessCheckpoints:
    def __init__(self, session):
        self.s = session

    async def save(self, context, operation_id, scope, checkpoint):
        try:
            self.s.check_context(context)
            self.s.identity_service.check(operation_id)
            data = canonical_json(checkpoint)
            fingerprint = digest_json({"scope": scope, "checkpoint": checkpoint})
            prior = self.s._deliveries.get(operation_id)
            if prior:
                if prior[0] != fingerprint:
                    raise EngineError("IDEMPOTENCY_CONFLICT", "Checkpoint delivery changed")
                context.authorize("checkpoint.save", scope, operation_id)
                result = await self.s._engine.storage.checkpoints.save(context, operation_id, scope, checkpoint)
                if isinstance(result, Ok):
                    self.s.created(result.value, prior[1])
                return result
            selector = self.s.publication("checkpoint.save", scope, len(data), format=checkpoint.format)
            self.s._deliveries[operation_id] = (fingerprint, selector)
            result = await self.s._engine.storage.checkpoints.save(context, operation_id, scope, checkpoint)
            if isinstance(result, Ok):
                self.s.created(result.value, selector)
            return result
        except EngineError as error:
            return Err(error)

    async def load(self, context, ref, accepted_formats=("engine_checkpoint/1",)):
        try:
            self.s.check_context(context)
            selector = next((r for r in self.s.request.read_objects if isinstance(r, CheckpointReadRequest) and r.ref == ref), None)
            if selector is None and ref not in self.s._created:
                raise EngineError("ACCESS_DENIED", "Checkpoint was not selected")
            if selector and not set(accepted_formats) <= set(selector.accepted_formats):
                raise EngineError("ACCESS_DENIED", "Checkpoint formats expanded")
            result = await self.s._engine.storage.checkpoints.load(context, ref, accepted_formats)
            if isinstance(result, Ok):
                size = len(canonical_json(result.value))
                if selector and size > selector.max_bytes:
                    raise EngineError("LIMIT_EXCEEDED", "Checkpoint exceeded the selected byte limit")
                self.s.charge(read=size)
            return result
        except EngineError as error:
            return Err(error)


class AccessHistory:
    def __init__(self, session):
        self.s = session
        self._pages = self._events = self._bytes = 0

    async def query(self, context, filters=None, cursor=None, limit=100):
        try:
            self.s.check_context(context)
            selector = self.s.request.history
            effective = {"run_id": context.run_id, **(filters or {})}
            if not selector or effective.get("run_id") != context.run_id or any(effective.get(k) != v for k, v in selector.filters.items()):
                raise EngineError("ACCESS_DENIED", "History filters are outside this run access")
            if self._pages >= selector.max_pages or self._events + limit > selector.max_events:
                raise EngineError("LIMIT_EXCEEDED", "History page/event limit exhausted")
            result = await self.s._engine.storage.activity.query(context, effective, cursor, limit)
            if isinstance(result, Ok):
                size = len(canonical_json(result.value))
                if self._bytes + size > selector.max_total_bytes:
                    raise EngineError("LIMIT_EXCEEDED", "History byte quota exhausted")
                self._pages += 1
                self._events += len(result.value.events)
                self._bytes += size
                self.s.charge(read=size)
            return result
        except EngineError as error:
            return Err(error)


class AccessStatuses:
    def __init__(self, session, event):
        self.s, self.event = session, event

    async def status(self, context, identity, expected_event_digest=None):
        try:
            self.s.check_context(context)
            selector = next((r for r in self.s.request.status_operations if (isinstance(r, EventStatusRequest) and self.event and r.event_id == identity) or (isinstance(r, OperationStatusRequest) and not self.event and r.operation_id == identity)), None)
            if not selector:
                if not self.event and identity in self.s.identity_service._ids:
                    self.s.charge()
                    return await self.s._engine.storage.operations.status(context, identity)
                raise EngineError("ACCESS_DENIED", "Status identity was not selected")
            self.s.charge()
            if self.event:
                if expected_event_digest != selector.expected_event_digest:
                    raise EngineError("ACCESS_DENIED", "Expected event digest changed")
                return await self.s._engine.storage.recorder.status(context, identity, expected_event_digest)
            return await self.s._engine.storage.operations.status(context, identity)
        except EngineError as error:
            return Err(error)


async def open_access(engine, run_ref, request, options):
    from .engine import finite_seconds, CONNECTION_EVENTS
    try:
        engine._active()
        if not isinstance(run_ref, RunRef) or run_ref.store_id != engine.storage.store_id or run_ref.schema_version != 1:
            raise EngineError("ACCESS_DENIED", "Run reference is outside the current host store")
        if not isinstance(request, RunAccessRequest) or not isinstance(options, RunAccessOptions) or options.grant_preset_ref != "own-run-results/1":
            raise EngineError("INVALID_DATA", "Expected the registered result-access preset")
        if request.schema_version != 1 or options.schema_version != 1:
            raise EngineError("INVALID_DATA", "Unsupported access schema version")
        for field in ("read_objects", "publications", "status_operations"):
            if len(getattr(request, field)) > 64:
                raise EngineError("LIMIT_EXCEEDED", "Too many access selectors")
        canonical_json({"request": request, "options": options}, 65536)
        seconds = finite_seconds(options.timeout_seconds, engine.settings.max_access_seconds)
        for value in (options.max_total_read_bytes, options.max_total_write_bytes, options.max_operations):
            if type(value) is not int or value < 0:
                raise EngineError("INVALID_DATA", "Access quotas must be nonnegative integers")
        scope = ScopeRef("run", run_ref.run_id)
        lookup = ExecutionContext(run_ref.run_id, run_ref.run_id, new_id("correlation_"), new_id("lookup_"),
            principal=engine.settings.host_principal, deadline=deadline_after(seconds), store_id=run_ref.store_id, scope=scope,
            grants=GrantSet([Grant("run.describe", scope, frozenset({run_ref.run_id}))], engine.settings.host_principal))
        descriptor = (await engine.storage.describe_run(lookup, run_ref.run_id)).unwrap()
        if descriptor.get("owner_principal") != engine.settings.host_principal:
            raise EngineError("ACCESS_DENIED", "Run belongs to another host principal")
        await lookup.lease.release()
        ctx = ExecutionContext(run_ref.run_id, descriptor["root_run_id"], descriptor["correlation_id"], new_id("access_action_"),
            principal=engine.settings.host_principal, context_kind=descriptor["context_kind"],
            agent_id=descriptor.get("agent_id"), definition_ref=descriptor.get("definition_ref"),
            parent_run_id=run_ref.run_id, parent_action_id=descriptor["root_action_id"],
            root_action_id=descriptor["root_action_id"], deadline=deadline_after(seconds),
            binding_ref=new_id("access_binding_"), policy_ref=options.grant_preset_ref,
            purpose="result_access", store_id=run_ref.store_id, scope=scope, metadata=dict(options.metadata),
            ledger=BudgetLedger({"storage_reads": options.max_operations, "storage_writes": options.max_operations,
                                 "storage_bytes": options.max_total_write_bytes,
                                 "storage_read_bytes": options.max_total_read_bytes, "status_reads": options.max_operations}))
        grants = [Grant("events.append", scope, producer="connections", event_kinds=frozenset({"binding.resolved", "binding.failed"}))]
        for selector in request.read_objects:
            if not isinstance(selector, (ArtifactReadRequest, SnapshotReadRequest, CheckpointReadRequest)) or selector.ref.store_id != run_ref.store_id:
                raise EngineError("ACCESS_DENIED", "Read selector has an unknown or foreign reference")
            expected_kind = {ArtifactReadRequest: "artifact", SnapshotReadRequest: "snapshot", CheckpointReadRequest: "checkpoint"}[type(selector)]
            if selector.kind != expected_kind:
                raise EngineError("INVALID_DATA", "Read selector tag differs from its reference kind")
            constraints = {}
            if isinstance(selector, ArtifactReadRequest):
                if type(selector.max_bytes) is not int or not 0 <= selector.max_bytes <= 8388608:
                    raise EngineError("INVALID_DATA", "Invalid artifact byte cap")
                if selector.range is not None:
                    if not isinstance(selector.range, ByteRange) or type(selector.range.start) is not int or type(selector.range.end_exclusive) is not int or not 0 <= selector.range.start <= selector.range.end_exclusive:
                        raise EngineError("INVALID_DATA", "Invalid artifact range")
                constraints = {"byte_range": selector.range.to_dict() if selector.range else None, "max_bytes": selector.max_bytes}
            elif isinstance(selector, SnapshotReadRequest):
                interval = selector.range
                if not isinstance(interval, dict) or set(interval) != {"kind", "start", "end_exclusive"} or interval["kind"] not in {"lines", "pages"} or type(interval["start"]) is not int or type(interval["end_exclusive"]) is not int or not 1 <= interval["start"] <= interval["end_exclusive"]:
                    raise EngineError("INVALID_DATA", "Invalid snapshot range")
                if type(selector.max_text_bytes) is not int or not 1 <= selector.max_text_bytes <= 65536:
                    raise EngineError("INVALID_DATA", "Invalid snapshot byte cap")
                constraints = {"document_ranges": tuple({"range": s.range, "max_text_bytes": s.max_text_bytes}
                    for s in request.read_objects if isinstance(s, SnapshotReadRequest) and s.ref == selector.ref)}
            else:
                if type(selector.max_bytes) is not int or not 0 <= selector.max_bytes <= 8388608 or set(selector.accepted_formats) - {"engine_checkpoint/1"}:
                    raise EngineError("INVALID_DATA", "Invalid checkpoint read constraints")
                constraints = {"max_bytes": selector.max_bytes, "allowed_formats": selector.accepted_formats}
            if not any(g.operation == selector.kind + ".read" and g.object_ids == frozenset({selector.ref.id}) for g in grants):
                grants.append(Grant(selector.kind + ".read", scope, frozenset({selector.ref.id}), run_id=ctx.run_id, **constraints))
        if request.history:
            if not isinstance(request.history, HistoryReadRequest) or set(request.history.filters) - {"run_id", "action_id", "attempt_id", "correlation_id", "kind", "status"} or request.history.filters.get("run_id", ctx.run_id) != ctx.run_id:
                raise EngineError("INVALID_DATA", "Invalid result history selector")
            if any(type(v) is not int or v < 0 for v in (request.history.max_pages, request.history.max_events, request.history.max_total_bytes)):
                raise EngineError("INVALID_DATA", "Invalid history limits")
            grants.append(Grant("events.read", scope, run_id=ctx.run_id))
        for selector in request.publications:
            if selector.scope != scope or selector.operation not in {"artifact.put", "checkpoint.save"} or selector.purpose not in {"citation_manifest", "terminal_checkpoint", "review_export"}:
                raise EngineError("ACCESS_DENIED", "Publication is outside the host result preset")
            for value in (selector.max_object_bytes, selector.max_total_bytes, selector.max_operations):
                if type(value) is not int or value < 0:
                    raise EngineError("INVALID_DATA", "Publication quotas must be nonnegative integers")
            grants.append(Grant(selector.operation, scope, run_id=ctx.run_id,
                max_bytes=selector.max_object_bytes, allowed_media_types=selector.allowed_media_types,
                allowed_formats=selector.allowed_formats, publication_purpose=selector.purpose))
        for selector in request.status_operations:
            if isinstance(selector, EventStatusRequest):
                op, identity = "events.status", selector.event_id
            elif isinstance(selector, OperationStatusRequest):
                op, identity = "operation.status", selector.operation_id
            else:
                raise EngineError("INVALID_DATA", "Unknown status selector")
            grants.append(Grant(op, scope, frozenset({identity}), run_id=ctx.run_id,
                                mode="observer", target_origin={"run_id": ctx.run_id}))
        ctx.grants = GrantSet(grants, ctx.principal)
        recorded = await engine._record(ctx, "binding.resolved", {"purpose": "result_access", "target": run_ref.to_dict(), "binding_ref": ctx.binding_ref})
        recorded.unwrap()
        session = RunAccessSession(engine, ctx, request, options)
        engine._sessions.append(session)
        return Ok(session)
    except EngineError as error:
        return Err(error)
