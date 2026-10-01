"""Result-access acceptance with actual Connections and actual SQLite/files."""
from __future__ import annotations

import dataclasses
import time

from ebd.connections import (Engine, EngineSettings, RunOptions, ArtifactReadRequest,
    SnapshotReadRequest, CheckpointReadRequest, EventStatusRequest, OperationStatusRequest,
    HistoryReadRequest, PublicationRequest, RunAccessRequest, RunAccessOptions)
from ebd.contracts import (AgentDefinition, ArtifactContent, ArtifactMetadata, ByteRange, CheckpointEnvelope,
    Err, ExecutionEvent, Ok, RunRef, ScopeRef, SnapshotProposal, canonical_json, digest_bytes)
from ebd.storage._ranges import line_spans


async def prepared_engine(path):
    engine = (await Engine.open(EngineSettings(workspace=path, storage_root=path / "store"))).unwrap()
    definition = AgentDefinition("result-fixture", "Controlled data fixture, no model invocation.")
    ctx = await engine._new_context(RunOptions(), definition)
    artifact = (await engine.storage.artifacts.put(ctx, "source-output", ctx.scope, b"immutable output", ArtifactMetadata("text/markdown"))).unwrap()
    raw = b"first\nsecond\n"
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(raw), "lines": line_spans(raw), "pages": None}
    snapshot = (await engine.storage.snapshots.commit(ctx, "source-snapshot", ctx.scope, SnapshotProposal(b"source-body", raw, canonical_json(index), {"url": "https://example.org/evidence"}))).unwrap()
    event = ExecutionEvent("terminal-event", "agent.finished", "runtime", ctx, {"status": "succeeded"})
    terminal = (await engine.storage.recorder.append(ctx, event)).unwrap()
    return engine, ctx, artifact, snapshot, event, terminal


async def test_fresh_result_access_real_bytes_history_observer_and_reopen(tmp_path):
    engine, original, artifact, snapshot, event, terminal = await prepared_engine(tmp_path)
    ref = RunRef(engine.storage.store_id, original.run_id)
    expected = digest_bytes(canonical_json(event))
    request = RunAccessRequest(
        read_objects=(ArtifactReadRequest(artifact.artifact_ref, None, 100), SnapshotReadRequest(snapshot.snapshot_ref, {"kind": "lines", "start": 1, "end_exclusive": 3}, 100)),
        history=HistoryReadRequest(max_pages=20, max_events=1000),
        status_operations=(EventStatusRequest(event.event_id, expected), OperationStatusRequest("source-output")))
    original._monotonic_deadline = time.monotonic() - 1
    access = (await engine.open_run_access(ref, request, RunAccessOptions())).unwrap()
    assert access.context.action_id != original.action_id
    assert access.context.purpose == "result_access"
    assert not hasattr(access, "runtime") and not hasattr(access.storage, "model")
    er = (await access.storage.recorder.status(access.context, event.event_id, expected)).unwrap()
    assert er.receipt == terminal
    op = (await access.storage.operations.status(access.context, "source-output")).unwrap()
    assert op.receipt.artifact_ref == artifact.artifact_ref
    reader = (await access.storage.artifacts.open(access.context, artifact.artifact_ref, None, 100)).unwrap()
    assert (await reader.read(access.context, 100)).unwrap().bytes == b"immutable output"
    (await reader.aclose(access.context)).unwrap()
    slice_ = (await access.storage.snapshots.read(access.context, snapshot.snapshot_ref, request.read_objects[1].range, 100)).unwrap()
    assert slice_.text == "first\nsecond"
    page = (await access.history.query(access.context, {"run_id": original.run_id}, None, 100)).unwrap()
    assert event.event_id in [row["event"]["event_id"] for row in page.events]
    await access.close()
    assert (await access.storage.recorder.status(access.context, event.event_id, expected)).error.code == "ACCESS_DENIED"
    await engine.close()
    reopened = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store"))).unwrap()
    fresh = (await reopened.open_run_access(ref, request, RunAccessOptions())).unwrap()
    reader = (await fresh.storage.artifacts.open(fresh.context, artifact.artifact_ref, None, 100)).unwrap()
    assert (await reader.read(fresh.context, 100)).unwrap().bytes == b"immutable output"
    assert (await fresh.storage.recorder.status(fresh.context, event.event_id, expected)).unwrap().receipt == terminal
    await fresh.close()
    await reopened.close()


async def test_selected_refs_ranges_and_grants_never_expand(tmp_path):
    engine, original, artifact, snapshot, *_ = await prepared_engine(tmp_path)
    ref = RunRef(engine.storage.store_id, original.run_id)
    request = RunAccessRequest(read_objects=(ArtifactReadRequest(artifact.artifact_ref, ByteRange(1, 4), 3),))
    access = (await engine.open_run_access(ref, request, RunAccessOptions())).unwrap()
    assert (await access.storage.artifacts.open(access.context, artifact.artifact_ref, None, 3)).error.code == "ACCESS_DENIED"
    assert (await access.storage.artifacts.open(access.context, artifact.artifact_ref, ByteRange(1, 4), 4)).error.code == "ACCESS_DENIED"
    assert (await engine.storage.artifacts.open(access.context, artifact.artifact_ref, None, 100)).error.code == "ACCESS_DENIED"
    reader = (await access.storage.artifacts.open(access.context, artifact.artifact_ref, ByteRange(1, 4), 3)).unwrap()
    assert (await reader.read(access.context, 3)).unwrap().bytes == b"mmu"
    assert (await access.storage.snapshots.read(access.context, snapshot.snapshot_ref, {"kind": "lines", "start": 1, "end_exclusive": 2}, 100)).error.code == "ACCESS_DENIED"
    assert (await access.history.query(access.context)).error.code == "ACCESS_DENIED"
    assert (await engine.storage.snapshots.read(access.context, snapshot.snapshot_ref, {"kind": "lines", "start": 1, "end_exclusive": 2}, 100)).error.code == "ACCESS_DENIED"
    try:
        access.context.authorize("model.generate", object_id="deepseek-flash")
    except Exception as error:
        assert error.code == "ACCESS_DENIED"
    else:
        raise AssertionError("Result access unexpectedly has model authority")
    await access.close()
    await engine.close()


async def test_publication_media_quota_read_created_and_final_write_redelivery(tmp_path):
    engine, original, *_ = await prepared_engine(tmp_path)
    ref = RunRef(engine.storage.store_id, original.run_id)
    selector = PublicationRequest("artifact.put", original.scope, "review_export", allowed_media_types=("text/markdown",), max_object_bytes=20, max_total_bytes=20, max_operations=1, read_created=True)
    access = (await engine.open_run_access(ref, RunAccessRequest(publications=(selector,)), RunAccessOptions(max_operations=2, max_total_write_bytes=20))).unwrap()
    identity = access.identity_service.allocate()
    assert (await access.storage.artifacts.put(access.context, identity, original.scope, b"output", ArtifactMetadata("application/json"))).error.code == "ACCESS_DENIED"
    first = (await access.storage.artifacts.put(access.context, identity, original.scope, b"output", ArtifactMetadata("text/markdown"))).unwrap()
    assert access.context.ledger.remaining("storage_writes") == 0
    duplicate = (await access.storage.artifacts.put(access.context, identity, original.scope, b"output", ArtifactMetadata("text/markdown"))).unwrap()
    assert duplicate.duplicate and duplicate.event_receipt.recorded_seq == first.event_receipt.recorded_seq
    assert (await access.storage.artifacts.put(access.context, identity, original.scope, b"changed", ArtifactMetadata("text/markdown"))).error.code == "IDEMPOTENCY_CONFLICT"
    assert (await access.storage.artifacts.put(access.context, access.identity_service.allocate(), original.scope, b"second", ArtifactMetadata("text/markdown"))).error.code == "LIMIT_EXCEEDED"
    await access.close()
    fresh = (await engine.open_run_access(ref, RunAccessRequest(read_objects=(ArtifactReadRequest(first.artifact_ref, None, 20),)), RunAccessOptions())).unwrap()
    handle = (await fresh.storage.artifacts.open(fresh.context, first.artifact_ref, None, 20)).unwrap()
    assert (await handle.read(fresh.context, 20)).unwrap().bytes == b"output"
    await fresh.close()
    await engine.close()


async def test_created_reference_read_requires_explicit_opt_in_and_checkpoint_formats(tmp_path):
    engine, original, *_ = await prepared_engine(tmp_path)
    ref = RunRef(engine.storage.store_id, original.run_id)
    publication = PublicationRequest("checkpoint.save", original.scope, "terminal_checkpoint", read_created=False, allowed_formats=("engine_checkpoint/1",), max_operations=2)
    access = (await engine.open_run_access(ref, RunAccessRequest(publications=(publication,)), RunAccessOptions())).unwrap()
    valid = CheckpointEnvelope(original.run_id, {"kind": "baseline_terminal/1", "status": "succeeded"})
    saved = (await access.storage.checkpoints.save(access.context, access.identity_service.allocate(), original.scope, valid)).unwrap()
    assert (await access.storage.checkpoints.load(access.context, saved.checkpoint_ref)).error.code == "ACCESS_DENIED"
    invalid = dataclasses.replace(valid, format="unknown/1")
    assert (await access.storage.checkpoints.save(access.context, access.identity_service.allocate(), original.scope, invalid)).error.code == "ACCESS_DENIED"
    await access.close()
    fresh = (await engine.open_run_access(ref, RunAccessRequest(read_objects=(CheckpointReadRequest(saved.checkpoint_ref),)), RunAccessOptions())).unwrap()
    loaded = (await fresh.storage.checkpoints.load(fresh.context, saved.checkpoint_ref)).unwrap()
    assert loaded.payload == valid.payload
    assert (await fresh.storage.checkpoints.load(fresh.context, saved.checkpoint_ref, ("unknown/1",))).error.code == "ACCESS_DENIED"
    await fresh.close()
    await engine.close()


async def test_foreign_run_host_identity_and_operation_status_denial(tmp_path):
    engine, original, artifact, *_ = await prepared_engine(tmp_path)
    second = await engine._new_context(RunOptions(), AgentDefinition("other", "Fixture."))
    selected = RunAccessRequest(read_objects=(ArtifactReadRequest(artifact.artifact_ref, None, 100),), status_operations=(OperationStatusRequest("source-output"),))
    access = (await engine.open_run_access(RunRef(engine.storage.store_id, second.run_id), selected, RunAccessOptions())).unwrap()
    assert (await access.storage.artifacts.open(access.context, artifact.artifact_ref, None, 100)).error.code == "NOT_FOUND"
    assert (await access.storage.operations.status(access.context, "source-output")).error.code == "ACCESS_DENIED"
    await access.close()
    await engine.close()
    foreign = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", host_principal="other-host"))).unwrap()
    denied = await foreign.open_run_access(RunRef(foreign.storage.store_id, original.run_id), RunAccessRequest(), RunAccessOptions())
    assert denied.error.code == "ACCESS_DENIED"
    await foreign.close()


async def test_positive_created_read_and_current_read_byte_limits(tmp_path):
    engine, original, artifact, *_ = await prepared_engine(tmp_path)
    ref = RunRef(engine.storage.store_id, original.run_id)
    selector = PublicationRequest("artifact.put", original.scope, "review_export", allowed_media_types=("text/markdown",), read_created=True)
    access = (await engine.open_run_access(ref, RunAccessRequest(publications=(selector,)), RunAccessOptions(max_total_read_bytes=6))).unwrap()
    published = (await access.storage.artifacts.put(access.context, access.identity_service.allocate(), original.scope, b"output", ArtifactMetadata("text/markdown"))).unwrap()
    handle = (await access.storage.artifacts.open(access.context, published.artifact_ref, None, 6)).unwrap()
    assert (await handle.read(access.context, 7)).error.code == "LIMIT_EXCEEDED"
    assert (await handle.read(access.context, 6)).unwrap().bytes == b"output"
    assert (await handle.read(access.context, 1)).error.code == "LIMIT_EXCEEDED"
    raw_handle = (await engine.storage.artifacts.open(access.context, published.artifact_ref, None, 6)).unwrap()
    assert (await raw_handle.read(access.context, 1)).error.code == "LIMIT_EXCEEDED"
    await access.close()
    await engine.close()


async def test_multiple_saved_ranges_same_snapshot_do_not_authorize_gap_or_join(tmp_path):
    engine, original, _, snapshot, *_ = await prepared_engine(tmp_path)
    raw = b"one\ntwo\nthree\nfour"
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(raw), "lines": line_spans(raw), "pages": None}
    extra = (await engine.storage.snapshots.commit(original, "multi-range-source", original.scope, SnapshotProposal(b"source", raw, canonical_json(index), {}))).unwrap()
    first = {"kind": "lines", "start": 1, "end_exclusive": 2}
    fourth = {"kind": "lines", "start": 4, "end_exclusive": 5}
    request = RunAccessRequest(read_objects=(SnapshotReadRequest(extra.snapshot_ref, first, 16), SnapshotReadRequest(extra.snapshot_ref, fourth, 16)))
    access = (await engine.open_run_access(RunRef(engine.storage.store_id, original.run_id), request, RunAccessOptions())).unwrap()
    assert (await access.storage.snapshots.read(access.context, extra.snapshot_ref, first, 16)).unwrap().text == "one"
    assert (await access.storage.snapshots.read(access.context, extra.snapshot_ref, fourth, 16)).unwrap().text == "four"
    assert (await engine.storage.snapshots.read(access.context, extra.snapshot_ref, fourth, 16)).unwrap().text == "four"
    gap = {"kind": "lines", "start": 2, "end_exclusive": 3}
    joined = {"kind": "lines", "start": 1, "end_exclusive": 5}
    assert (await engine.storage.snapshots.read(access.context, extra.snapshot_ref, gap, 16)).error.code == "ACCESS_DENIED"
    assert (await engine.storage.snapshots.read(access.context, extra.snapshot_ref, joined, 16)).error.code == "ACCESS_DENIED"
    assert (await engine.storage.snapshots.read(access.context, extra.snapshot_ref, first, 17)).error.code == "ACCESS_DENIED"
    await access.close()
    await engine.close()


async def test_result_publication_source_descriptor_dedup_preserves_caller_source(tmp_path):
    class Source:
        def __init__(self):
            self.data, self.offset, self.reads, self.closes = b"source output", 0, 0, 0
        async def read(self, size):
            self.reads += 1
            result = self.data[self.offset:self.offset + size]
            self.offset += len(result)
            return result
        async def aclose(self):
            self.closes += 1
    engine, original, *_ = await prepared_engine(tmp_path)
    ref = RunRef(engine.storage.store_id, original.run_id)
    selector = PublicationRequest("artifact.put", original.scope, "review_export", allowed_media_types=("text/markdown",), max_total_bytes=32, max_operations=1)
    access = (await engine.open_run_access(ref, RunAccessRequest(publications=(selector,)), RunAccessOptions(max_operations=2))).unwrap()
    first_source = Source()
    identity = access.identity_service.allocate()
    first = (await access.storage.artifacts.put(access.context, identity, original.scope, ArtifactContent(source=first_source, byte_length=len(first_source.data), sha256=digest_bytes(first_source.data)), ArtifactMetadata("text/markdown"))).unwrap()
    assert first_source.reads >= 2 and first_source.closes == 1
    replay = Source()
    duplicate = (await access.storage.artifacts.put(access.context, identity, original.scope, ArtifactContent(source=replay, byte_length=len(replay.data), sha256=digest_bytes(replay.data)), ArtifactMetadata("text/markdown"))).unwrap()
    assert duplicate.duplicate and duplicate.artifact_ref == first.artifact_ref
    assert replay.reads == replay.closes == 0
    await replay.aclose()
    await access.close()
    await engine.close()
