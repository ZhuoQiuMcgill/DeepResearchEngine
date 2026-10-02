"""Read-only evidence delegation, attenuated from a live caller's authority."""
from __future__ import annotations

import copy

from ebd.engine.contracts import (
    EngineError, Grant, ScopeRef, ArtifactRef, SnapshotRef, CheckpointRef,
    ByteRange, Ok, Err, canonical_json, new_id,
)
from .models import (
    ArtifactReadRequest, SnapshotReadRequest, CheckpointReadRequest,
    StateReadRequest, EvidenceBinding,
    BoundSession,
)


def freeze_evidence(evidence):
    if evidence is None:
        return None
    if not isinstance(evidence, EvidenceBinding):
        raise EngineError("INVALID_DATA", "Evidence must be a typed EvidenceBinding")
    try:
        frozen = copy.deepcopy(evidence)
        canonical_json(frozen, 65536)
        if not isinstance(frozen.read_objects, (list, tuple)) or not isinstance(frozen.state_reads, (list, tuple)):
            raise TypeError("selectors")
        return EvidenceBinding(tuple(frozen.read_objects), tuple(frozen.state_reads))
    except (TypeError, ValueError):
        raise EngineError("INVALID_DATA", "Evidence must be bounded serializable selectors") from None


def _cap(value, maximum, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise EngineError("INVALID_DATA", "Invalid evidence byte cap")


def _within(requested, allowed, *, document=False):
    keys = {"kind", "start", "end_exclusive"} if document else {"start", "end_exclusive"}
    lower = 1 if document else 0
    if (not isinstance(requested, dict) or set(requested) != keys
        or type(requested["start"]) is not int or type(requested["end_exclusive"]) is not int
        or not lower <= requested["start"] <= requested["end_exclusive"]
        or (document and requested["kind"] not in {"lines", "pages"})):
        raise EngineError("INVALID_DATA", "Invalid evidence range")
    if allowed is not None and (requested["start"] < allowed["start"]
        or requested["end_exclusive"] > allowed["end_exclusive"]
        or (document and requested["kind"] != allowed["kind"])):
        raise EngineError("ACCESS_DENIED", "Evidence range expands caller authority")


async def evidence_grants(engine, caller, evidence):
    """Validate before admission; returned grants are pinned to source scopes."""
    if evidence is None:
        return []
    if not isinstance(evidence, EvidenceBinding):
        raise EngineError("INVALID_DATA", "Evidence must be a typed EvidenceBinding")
    if len(evidence.read_objects) + len(evidence.state_reads) > 64:
        raise EngineError("LIMIT_EXCEEDED", "At most 64 evidence selectors may be delegated")
    try:
        canonical_json(evidence, 65536)
    except (TypeError, ValueError):
        raise EngineError("INVALID_DATA", "Evidence must be bounded serializable selectors") from None
    grants, seen, snapshots = [], set(), {}
    for selector in evidence.read_objects:
        cls = type(selector)
        if cls not in {ArtifactReadRequest, SnapshotReadRequest, CheckpointReadRequest}:
            raise EngineError("INVALID_DATA", "Unknown evidence selector")
        kind = {ArtifactReadRequest: "artifact", SnapshotReadRequest: "snapshot", CheckpointReadRequest: "checkpoint"}[cls]
        ref_class = {ArtifactReadRequest: ArtifactRef, SnapshotReadRequest: SnapshotRef,
                     CheckpointReadRequest: CheckpointRef}[cls]
        if not isinstance(selector.ref, ref_class) or selector.kind != kind or selector.ref.store_id != engine.storage.store_id:
            raise EngineError("ACCESS_DENIED", "Foreign evidence or mismatched selector kind")
        descriptor = (await engine.storage.describe_object(caller, selector.ref)).unwrap()
        scope = ScopeRef(**descriptor["scope"])
        source = caller.authorize(kind + ".read", scope, selector.ref.id)
        identity = (kind, selector.ref.id)
        constraints = {}
        if cls is ArtifactReadRequest:
            _cap(selector.max_bytes, 8388608)
            if source.max_bytes is not None and selector.max_bytes > source.max_bytes:
                raise EngineError("ACCESS_DENIED", "Evidence byte cap expands caller authority")
            if selector.range is not None and not isinstance(selector.range, ByteRange):
                raise EngineError("INVALID_DATA", "Artifact evidence requires a typed byte range")
            interval = selector.range.to_dict() if selector.range is not None else None
            if interval is None and source.byte_range is not None:
                raise EngineError("ACCESS_DENIED", "Full artifact exceeds caller range")
            if interval is not None:
                _within(interval, source.byte_range)
            constraints = {"byte_range": interval, "max_bytes": selector.max_bytes}
        elif cls is SnapshotReadRequest:
            if selector.continuation is not None:
                raise EngineError("INVALID_DATA", "A parent continuation is not child authority")
            _cap(selector.max_text_bytes, 65536, 1)
            _within(selector.range, source.document_range, document=True)
            if source.max_text_bytes is not None and selector.max_text_bytes > source.max_text_bytes:
                raise EngineError("ACCESS_DENIED", "Evidence text cap expands caller authority")
            if source.document_ranges is not None:
                matches = [entry for entry in source.document_ranges
                    if entry["range"]["kind"] == selector.range["kind"]
                    and entry["range"]["start"] <= selector.range["start"] <= selector.range["end_exclusive"] <= entry["range"]["end_exclusive"]
                    and selector.max_text_bytes <= entry["max_text_bytes"]]
                if not matches:
                    raise EngineError("ACCESS_DENIED", "Evidence is outside caller selected ranges")
            entry = {"range": dict(selector.range), "max_text_bytes": selector.max_text_bytes}
            if identity in snapshots:
                snapshots[identity].document_ranges += (entry,)
                continue
            constraints = {"document_ranges": (entry,)}
        else:
            _cap(selector.max_bytes, 8388608)
            if (not isinstance(selector.accepted_formats, (tuple, list))
                or not all(isinstance(value, str) for value in selector.accepted_formats)):
                raise EngineError("INVALID_DATA", "Checkpoint formats must be strings")
            if (not selector.accepted_formats or set(selector.accepted_formats) - {"engine_checkpoint/1"}
                or (source.allowed_formats is not None and set(selector.accepted_formats) - set(source.allowed_formats))):
                raise EngineError("ACCESS_DENIED", "Checkpoint format expands caller authority")
            if source.max_bytes is not None and selector.max_bytes > source.max_bytes:
                raise EngineError("ACCESS_DENIED", "Checkpoint cap expands caller authority")
            constraints = {"max_bytes": selector.max_bytes, "allowed_formats": selector.accepted_formats}
        if identity in seen:
            raise EngineError("INVALID_DATA", "Duplicate evidence selector")
        seen.add(identity)
        grant = Grant(kind + ".read", scope, frozenset({selector.ref.id}), expires_at=source.expires_at, **constraints)
        grants.append(grant)
        if cls is SnapshotReadRequest:
            snapshots[identity] = grant
    for selector in evidence.state_reads:
        if (not isinstance(selector, StateReadRequest) or not isinstance(selector.scope, ScopeRef)
            or not isinstance(selector.key, str) or not selector.key or len(selector.key) > 256):
            raise EngineError("INVALID_DATA", "Invalid selected state key")
        _cap(selector.max_bytes, 1049600)
        identity = ("state", selector.scope, selector.key)
        if identity in seen:
            raise EngineError("INVALID_DATA", "Duplicate state evidence selector")
        seen.add(identity)
        source = caller.authorize("state.read", selector.scope, selector.key)
        if source.max_bytes is not None and selector.max_bytes > source.max_bytes:
            raise EngineError("ACCESS_DENIED", "State cap expands caller authority")
        grants.append(Grant("state.read", selector.scope, frozenset({selector.key}),
                            max_bytes=selector.max_bytes, expires_at=source.expires_at))
    return grants


async def bind_host_evidence(engine, session, source_run_ref, evidence):
    from .inspection import _owned, _context
    host = None
    try:
        engine._active()
        if (not isinstance(session, BoundSession)
            or engine._contexts.get(id(session.context)) is not session.context
            or not any(item is session for item in engine._sessions)):
            raise EngineError("ACCESS_DENIED", "Evidence binding requires this Engine's live agent session")
        caller = session.context
        caller.assert_active()
        session.binding.lease.assert_active()
        # Validate caller revocation independently of a new host source grant.
        caller.authorize("events.append", caller.scope, producer="connections", event_kind="binding.evidence")
        evidence = freeze_evidence(evidence)
        await _owned(engine, source_run_ref)
        scope = ScopeRef("run", source_run_ref.run_id)
        if not isinstance(evidence, EvidenceBinding) or len(evidence.read_objects) + len(evidence.state_reads) > 64:
            raise EngineError("INVALID_DATA", "Expected a bounded typed EvidenceBinding")
        allowed = []
        for selector in evidence.read_objects:
            cls = type(selector)
            if cls not in {ArtifactReadRequest, SnapshotReadRequest, CheckpointReadRequest}:
                raise EngineError("INVALID_DATA", "Unknown source evidence selector")
            kind, ref_class = {ArtifactReadRequest: ("artifact", ArtifactRef),
                SnapshotReadRequest: ("snapshot", SnapshotRef),
                CheckpointReadRequest: ("checkpoint", CheckpointRef)}[cls]
            if not isinstance(selector.ref, ref_class):
                raise EngineError("INVALID_DATA", "Expected a typed source reference")
            allowed.append(Grant(kind + ".read", scope, frozenset({selector.ref.id}), expires_at=caller.deadline))
        for selector in evidence.state_reads:
            if not isinstance(selector, StateReadRequest) or selector.scope != scope or not isinstance(selector.key, str):
                raise EngineError("ACCESS_DENIED", "Selected state must belong to the source run")
            allowed.append(Grant("state.read", scope, frozenset({selector.key}), expires_at=caller.deadline))
        host = _context(engine, source_run_ref.run_id, allowed)
        selected = await evidence_grants(engine, host, evidence)
        record_context = caller.for_action(new_id("evidence_binding_"), None)
        receipt = (await engine._record(record_context, "binding.evidence", {
            "source_run_ref": source_run_ref.to_dict(), "evidence": evidence.to_dict(),
            "binding_ref": caller.binding_ref, "purpose": "host_selected_evidence",
        })).unwrap()
        caller.assert_active()
        caller.authorize("events.append", caller.scope, producer="connections", event_kind="binding.evidence")
        caller.grants.grants.extend(selected)
        return Ok({"schema_version": 1, "source_run_ref": source_run_ref.to_dict(),
            "evidence": evidence.to_dict(), "event_receipt": receipt.to_dict()})
    except EngineError as error:
        return Err(error)
    finally:
        if host:
            await host.lease.release()
