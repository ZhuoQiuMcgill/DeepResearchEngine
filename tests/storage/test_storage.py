from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
import threading
import time
import subprocess
import sys

import pytest

from ebd.contracts import (ArtifactContent, ArtifactMetadata, BudgetLedger, CheckpointEnvelope,
    EngineError, Err, ExecutionContext, ExecutionEvent, Grant, GrantSet, Ok,
    ScopeRef, SnapshotProposal, StateMutation, canonical_json, deadline_after, digest_bytes)
from ebd.storage import StorageSession
from ebd.storage._ranges import line_spans


def context(session, run="run-a", *, action="root-a", attempt=None, principal="agent-a", grants=None, ledger=None):
    scope = ScopeRef("run", run)
    return ExecutionContext(run, run, "corr-a", action, principal=principal, attempt_id=attempt,
        store_id=session.store_id, scope=scope, deadline=deadline_after(120),
        grants=GrantSet(grants or [Grant("*", scope=scope)], principal),
        ledger=ledger or BudgetLedger())


async def opened(path, **settings):
    session = (await StorageSession.open({"root": path, **settings})).unwrap()
    ctx = context(session)
    (await session.provision_run(ctx, {"run_id": ctx.run_id, "root_run_id": ctx.root_run_id, "context_kind": "agent", "agent_id": "a"})).unwrap()
    return session, ctx


def proposal(text, pages=None):
    raw = text.encode()
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(raw), "lines": line_spans(raw), "pages": pages}
    return SnapshotProposal(b"original-body", raw, canonical_json(index), {"url": "https://example.org/source"}, "test-extraction/1", "lf/1")


def interval(kind, start, end):
    return {"kind": kind, "start": start, "end_exclusive": end}


async def read_all(session, ctx, ref):
    reader = (await session.artifacts.open(ctx, ref, None, 8 << 20)).unwrap()
    result = bytearray()
    while True:
        chunk = (await reader.read(ctx, 7)).unwrap()
        result.extend(chunk.bytes)
        if chunk.eof:
            break
    (await reader.aclose(ctx)).unwrap()
    return bytes(result)


async def test_real_close_reopen_all_objects(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    assert session.profile["journal_mode"] == "delete"
    assert session.profile["synchronous"] == 3
    assert session.profile["foreign_keys"] == 1
    state = (await session.state.commit(ctx, "state-a", [StateMutation(ctx.scope, "answer", "put", 0, {"n": 42})])).unwrap()
    artifact = (await session.artifacts.put(ctx, "artifact-a", ctx.scope, ArtifactContent(b"exact \x00\xf0\x9f\x98\x80 bytes"), ArtifactMetadata("application/octet-stream"))).unwrap()
    snapshot = (await session.snapshots.commit(ctx, "snapshot-a", ctx.scope, proposal("first\nsecond\n"))).unwrap()
    checkpoint = (await session.checkpoints.save(ctx, "checkpoint-a", ctx.scope, CheckpointEnvelope(ctx.run_id, {"state": state.to_dict(), "report": artifact.artifact_ref.to_dict()}))).unwrap()
    event = ExecutionEvent("event-a", "agent.started", "runtime", ctx, {"known": True})
    receipt = (await session.recorder.append(ctx, event)).unwrap()
    assert set(receipt.to_dict()) == {"schema_version", "store_id", "event_id", "recorded_seq", "recorded_at", "duplicate"}
    store_id = session.store_id
    assert (await session.close()).unwrap().closed
    reopened = (await StorageSession.open(tmp_path / "store")).unwrap()
    assert reopened.store_id == store_id
    fresh = context(reopened)
    assert (await reopened.state.get(fresh, fresh.scope, "answer")).unwrap().value == {"n": 42}
    assert await read_all(reopened, fresh, artifact.artifact_ref) == b"exact \x00\xf0\x9f\x98\x80 bytes"
    read = (await reopened.snapshots.read(fresh, snapshot.snapshot_ref, interval("lines", 1, 3), 1024, None)).unwrap()
    assert read.text == "first\nsecond"
    assert (await reopened.checkpoints.load(fresh, checkpoint.checkpoint_ref)).unwrap().payload["report"] == artifact.artifact_ref.to_dict()
    assert (await reopened.recorder.status(fresh, "event-a", digest_bytes(canonical_json(event)))).unwrap().receipt == receipt
    assert (await reopened.operations.status(fresh, "state-a")).unwrap().receipt.mutation_versions == state.mutation_versions
    page = (await reopened.activity.query(fresh, {"run_id": ctx.run_id}, None, 100)).unwrap()
    assert page.events[-1]["event"]["event_id"] == "event-a"
    await reopened.close()


async def test_same_id_reconciliation_before_quota_and_cas(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    ctx.ledger.limits["storage_writes"] = 1
    mutation = [StateMutation(ctx.scope, "key", "put", 0, 1)]
    first = (await session.state.commit(ctx, "stable-op", mutation)).unwrap()
    assert ctx.ledger.remaining("storage_writes") == 0
    duplicate = (await session.state.commit(ctx, "stable-op", mutation)).unwrap()
    assert duplicate.duplicate and duplicate.event_receipt.recorded_seq == first.event_receipt.recorded_seq
    assert (await session.state.get(ctx, ctx.scope, "key")).unwrap().version == 1
    changed = await session.state.commit(ctx, "stable-op", [StateMutation(ctx.scope, "key", "put", 0, 2)])
    assert isinstance(changed, Err) and changed.error.code == "IDEMPOTENCY_CONFLICT"
    fresh = await session.state.commit(ctx, "new-op", [StateMutation(ctx.scope, "key", "put", 1, 2)])
    assert fresh.error.code == "LIMIT_EXCEEDED"
    ctx.grants.revoked = True
    denied = await session.state.commit(ctx, "stable-op", mutation)
    assert denied.error.code == "ACCESS_DENIED"
    await session.close()


async def test_lost_actual_committed_reply_same_id_no_replay(tmp_path):
    def lose_reply(phase, operation_id):
        if phase == "state_after_commit":
            raise RuntimeError("controlled lost response")
    session, ctx = await opened(tmp_path / "store", fault_hook=lose_reply)
    ctx.ledger.limits["storage_writes"] = 1
    mutations = [StateMutation(ctx.scope, "key", "put", 0, {"v": 1})]
    with pytest.raises(RuntimeError, match="controlled lost response"):
        await session.state.commit(ctx, "lost-reply", mutations)
    original = (await session.operations.status(ctx, "lost-reply")).unwrap()
    duplicate = (await session.state.commit(ctx, "lost-reply", mutations)).unwrap()
    assert original.state == "committed" and duplicate.duplicate
    assert duplicate.event_receipt.recorded_seq == original.receipt.event_receipt.recorded_seq
    assert ctx.ledger.used["storage_writes"] == 1
    await session.close()


async def test_cas_tombstones_batch_rollback_and_concurrent_winner(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    results = await asyncio.gather(*[session.state.commit(ctx, f"concurrent-{n}", [StateMutation(ctx.scope, "key", "put", 0, n)]) for n in range(2)])
    assert sum(isinstance(value, Ok) for value in results) == 1
    assert next(value for value in results if isinstance(value, Err)).error.code == "VERSION_CONFLICT"
    (await session.state.commit(ctx, "delete", [StateMutation(ctx.scope, "key", "delete", 1)])).unwrap()
    missing = (await session.state.get(ctx, ctx.scope, "key")).unwrap()
    assert not missing.present and missing.version == 2
    bad = await session.state.commit(ctx, "bad-recreate", [StateMutation(ctx.scope, "key", "put", 0, "new")])
    assert bad.error.code == "VERSION_CONFLICT"
    (await session.state.commit(ctx, "recreate", [StateMutation(ctx.scope, "key", "put", 2, "new")])).unwrap()
    historical = (await session.state.get_version(ctx, ctx.scope, "key", 2)).unwrap()
    assert historical.version == 2 and not historical.present
    batch = await session.state.commit(ctx, "bad-batch", [StateMutation(ctx.scope, "fresh", "put", 0, 1), StateMutation(ctx.scope, "key", "put", 1, 2)])
    assert batch.error.code == "VERSION_CONFLICT"
    assert (await session.state.get(ctx, ctx.scope, "fresh")).unwrap().version == 0
    await session.close()


async def test_scope_reference_alone_and_cleanup_do_not_grant_writes(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    artifact = (await session.artifacts.put(ctx, "private", ctx.scope, b"private", {"media_type": "text/plain"})).unwrap()
    other = context(session, run="run-b", principal="agent-b")
    denied = await session.artifacts.open(other, artifact.artifact_ref)
    assert denied.error.code == "NOT_FOUND"
    history = (await session.activity.query(other)).unwrap()
    assert history.events == []
    cleanup = ctx.for_cleanup()
    denied = await session.artifacts.put(cleanup, "cleanup-write", ctx.scope, b"x")
    assert denied.error.code == "ACCESS_DENIED"
    assert (await session.operations.status(ctx, "cleanup-write")).unwrap().state == "absent"
    await session.close()


async def test_exact_host_observer_preserves_identity_denies_delivery(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    ctx = ctx.for_action("action-a", "attempt-a")
    event = ExecutionEvent("observed-event", "tool.intent", "runtime", ctx, {"args_digest": "safe"})
    er = (await session.recorder.append(ctx, event)).unwrap()
    operation = (await session.artifacts.put(ctx, "observed-operation", ctx.scope, b"result")).unwrap()
    frozen = {"principal": ctx.principal, "run_id": ctx.run_id, "action_id": ctx.action_id, "attempt_id": ctx.attempt_id}
    grants = [Grant("events.status", ctx.scope, frozenset({"observed-event"}), mode="observer", target_origin=frozen), Grant("operation.status", ctx.scope, frozenset({"observed-operation"}), mode="observer", target_origin=frozen)]
    host = context(session, action="host-action", principal="host-result", grants=grants)
    ctx._monotonic_deadline = time.monotonic() - 1
    assert (await session.recorder.status(host, "observed-event")).unwrap().receipt == er
    assert (await session.operations.status(host, "observed-operation")).unwrap().receipt.artifact_ref == operation.artifact_ref
    assert host.action_id == "host-action" and host.principal == "host-result"
    assert (await session.recorder.append(host, event)).error.code == "ACCESS_DENIED"
    assert (await session.artifacts.put(host, "observed-operation", ctx.scope, b"result")).error.code == "ACCESS_DENIED"
    assert (await session.operations.status(host, "guessed-operation")).error.code == "ACCESS_DENIED"
    assert (await session.recorder.status(host, "observed-event", "sha256:" + "0" * 64)).error.code == "IDEMPOTENCY_CONFLICT"
    host.grants.grants[0].target_origin = {**frozen, "action_id": "wrong-action"}
    assert (await session.recorder.status(host, "observed-event")).error.code == "ACCESS_DENIED"
    await session.close()


@pytest.mark.parametrize("text,count", [("", 0), ("a", 1), ("a\n", 1), ("\n", 1), ("a\n\n", 2)])
async def test_exact_empty_and_trailing_line_counts(tmp_path, text, count):
    session, ctx = await opened(tmp_path / "store")
    sr = (await session.snapshots.commit(ctx, "snap", ctx.scope, proposal(text))).unwrap()
    assert sr.line_count == count
    empty = (await session.snapshots.read(ctx, sr.snapshot_ref, interval("lines", count + 1, count + 1), 64, None)).unwrap()
    assert empty.text == "" and empty.spans == [] and empty.next_position is None
    assert (await session.snapshots.read(ctx, sr.snapshot_ref, interval("lines", count + 1, count + 2), 64, None)).error.code == "INVALID_DATA"
    await session.close()


async def test_unicode_continuation_reauthorization_and_empty_physical_pages(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    pages = [{"page": 1, "start_byte": 0, "end_byte": 0}, {"page": 2, "start_byte": 1, "end_byte": 9}, {"page": 3, "start_byte": 10, "end_byte": 10}]
    sr = (await session.snapshots.commit(ctx, "unicode", ctx.scope, proposal("\n😀😀\n", pages))).unwrap()
    page = (await session.snapshots.read(ctx, sr.snapshot_ref, interval("pages", 1, 2), 4, None)).unwrap()
    assert page.text == "" and page.spans == [{"line": None, "page": 1, "start_byte": 0, "end_byte": 0}]
    first = (await session.snapshots.read(ctx, sr.snapshot_ref, interval("pages", 2, 3), 4, None)).unwrap()
    assert first.text == "😀" and first.truncated and first.next_position["offset"] == 5
    too_small = await session.snapshots.read(ctx, sr.snapshot_ref, interval("pages", 2, 3), 3, first.continuation)
    assert too_small.error.code == "LIMIT_EXCEEDED" and too_small.error.details["minimum_next_codepoint_bytes"] == 4
    second = (await session.snapshots.read(ctx, sr.snapshot_ref, interval("pages", 2, 3), 4, first.continuation)).unwrap()
    assert first.text + second.text == "😀😀" and not second.truncated
    wrong = await session.snapshots.read(ctx, sr.snapshot_ref, interval("pages", 1, 3), 4, first.continuation)
    assert wrong.error.code == "INVALID_CURSOR"
    ctx.grants.revoked = True
    assert (await session.snapshots.read(ctx, sr.snapshot_ref, interval("pages", 2, 3), 4, first.continuation)).error.code == "ACCESS_DENIED"
    await session.close()


@pytest.mark.parametrize("phase,expected", [("reserved", "interrupted"), ("sealed", "committed"), ("renamed", "committed"), ("before_ready_commit", "committed")])
async def test_real_file_publication_interruption_recovery(tmp_path, phase, expected):
    once = [False]
    def crash(boundary, operation_id):
        if boundary == phase and not once[0]:
            once[0] = True
            raise RuntimeError("controlled interrupted publisher")
    session, ctx = await opened(tmp_path / "store", fault_hook=crash)
    with pytest.raises(RuntimeError, match="controlled interrupted publisher"):
        await session.artifacts.put(ctx, "recover-op", ctx.scope, b"sealed bytes")
    await session.close()
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    ctx = context(session)
    status = (await session.operations.status(ctx, "recover-op")).unwrap()
    assert status.state == expected
    if expected == "committed":
        assert await read_all(session, ctx, status.receipt.artifact_ref) == b"sealed bytes"
        before = status.receipt.event_receipt.recorded_seq
        assert (await session.artifacts.put(ctx, "recover-op", ctx.scope, b"sealed bytes")).unwrap().event_receipt.recorded_seq == before
    await session.close()


async def test_root_exclusivity_integrity_and_fixed_watermark(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    second = await StorageSession.open(tmp_path / "store")
    assert second.error.code == "STORAGE_BUSY"
    for n in range(3):
        (await session.recorder.append(ctx, ExecutionEvent(f"ev-{n}", "validation.observed", "runtime", ctx, {"n": n}))).unwrap()
    first = (await session.activity.query(ctx, {}, None, 1)).unwrap()
    assert first.cursor
    (await session.recorder.append(ctx, ExecutionEvent("late", "validation.observed", "runtime", ctx, {}))).unwrap()
    ids = [first.events[0]["event"]["event_id"]]
    cursor = first.cursor
    while cursor:
        page = (await session.activity.query(ctx, {}, cursor, 1)).unwrap()
        assert page.high_water_seq == first.high_water_seq
        ids.extend(row["event"]["event_id"] for row in page.events)
        cursor = page.cursor
    assert ids == ["ev-0", "ev-1", "ev-2"]
    ar = (await session.artifacts.put(ctx, "bad-bytes", ctx.scope, b"original")).unwrap()
    (tmp_path / "store" / "objects" / (ar.artifact_ref.id + ".bin")).write_bytes(b"altered!")
    assert (await session.artifacts.open(ctx, ar.artifact_ref)).error.code == "INTEGRITY_ERROR"
    await session.close()


async def test_cancelled_borrower_leaves_writer_owned_until_close(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def pause(phase, operation_id):
        if phase == "sealed":
            entered.set()
            release.wait(10)
    session, ctx = await opened(tmp_path / "store", fault_hook=pause)
    task = asyncio.create_task(session.artifacts.put(ctx, "cancelled-writer", ctx.scope, b"bytes"))
    assert await asyncio.to_thread(entered.wait, 5)
    pending = (await session.operations.status(ctx, "cancelled-writer")).unwrap()
    assert pending.state == "pending"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    closing = await session.close(deadline_after(0.02))
    assert closing.error.code == "STORAGE_BUSY"
    assert (await StorageSession.open(tmp_path / "store")).error.code == "STORAGE_BUSY"
    release.set()
    assert (await session.close(deadline_after(5))).unwrap().closed
    reopened = (await StorageSession.open(tmp_path / "store")).unwrap()
    fresh = context(reopened)
    assert (await reopened.operations.status(fresh, "cancelled-writer")).unwrap().state == "committed"
    await reopened.close()


@pytest.mark.parametrize("phase,committed", [("sealed", True), ("component_sealed", False)])
async def test_composite_child_receipts_recover_without_parent_fabrication(tmp_path, phase, committed):
    once = [False]
    def crash(boundary, operation_id):
        if boundary == phase and operation_id == "composite" and not once[0]:
            once[0] = True
            raise RuntimeError("controlled composite interruption")
    session, ctx = await opened(tmp_path / "store", fault_hook=crash)
    with pytest.raises(RuntimeError):
        await session.snapshots.commit(ctx, "composite", ctx.scope, proposal("retained\ntext"))
    await session.close()
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    ctx = context(session)
    parent = (await session.operations.status(ctx, "composite")).unwrap()
    original = (await session.operations.status(ctx, "composite:original")).unwrap()
    assert original.state == "committed"
    assert await read_all(session, ctx, original.receipt.artifact_ref) == b"original-body"
    assert parent.state == ("committed" if committed else "interrupted")
    if committed:
        for role in ("text", "index", "manifest"):
            assert (await session.operations.status(ctx, "composite:" + role)).unwrap().state == "committed"
        assert (await session.snapshots.read(ctx, parent.receipt.snapshot_ref, interval("lines", 1, 3), 100, None)).unwrap().text == "retained\ntext"
    page = (await session.activity.query(ctx)).unwrap()
    events = [row["event"] for row in page.events]
    assert sum(event["kind"] == "artifact.committed" and event["payload"]["operation_id"] == "composite:original" for event in events) == 1
    assert sum(event["kind"] == "snapshot.committed" for event in events) == int(committed)
    await session.close()


async def test_history_selectors_and_foreign_watermark_are_not_disclosed(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    for n, kind in enumerate(("validation.observed", "limit.observed", "validation.observed")):
        (await session.recorder.append(ctx, ExecutionEvent(f"selected-{n}", kind, "runtime", ctx, {}))).unwrap()
    restricted = context(session, grants=[Grant("events.read", ctx.scope, frozenset({"selected-0", "selected-1"}), event_kinds=frozenset({"validation.observed"}))])
    page = (await session.activity.query(restricted)).unwrap()
    assert [row["event"]["event_id"] for row in page.events] == ["selected-0"]
    assert page.high_water_seq == page.events[0]["receipt"]["recorded_seq"]
    other = context(session, run="foreign", principal="foreign")
    page = (await session.activity.query(other)).unwrap()
    assert page.events == [] and page.high_water_seq == 0
    await session.close()


async def test_invalid_json_descriptors_and_missing_store_authority_fail_closed(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    assert (await session.state.commit(ctx, "nonfinite", [StateMutation(ctx.scope, "x", "put", 0, float("nan"))])).error.code == "INVALID_DATA"
    assert (await session.state.commit(ctx, "badkey", [StateMutation(ctx.scope, "x", "put", 0, {1: "bad"})])).error.code == "INVALID_DATA"
    assert (await session.artifacts.put(ctx, "boolean-descriptor", ctx.scope, ArtifactContent(b"", False))).error.code == "INTEGRITY_ERROR"
    unbound = dataclasses.replace(ctx, store_id=None)
    assert (await session.state.get(unbound, ctx.scope, "x")).error.code == "ACCESS_DENIED"
    assert (await session.state.get(ctx, ctx.scope, "\ud800")).error.code == "INVALID_DATA"
    assert (await session.state.get(ctx, ctx.scope, "x")).unwrap().version == 0
    await session.close()


async def test_state_failure_rolls_back_event_receipt_and_entire_batch(tmp_path):
    def fail_before_commit(phase, operation_id):
        if phase == "state_before_commit":
            raise RuntimeError("controlled atomic rollback")
    session, ctx = await opened(tmp_path / "store", fault_hook=fail_before_commit)
    with pytest.raises(RuntimeError):
        await session.state.commit(ctx, "rollback", [StateMutation(ctx.scope, "x", "put", 0, 1), StateMutation(ctx.scope, "y", "put", 0, 2)])
    assert (await session.state.get(ctx, ctx.scope, "x")).unwrap().version == 0
    assert (await session.state.get(ctx, ctx.scope, "y")).unwrap().version == 0
    assert (await session.operations.status(ctx, "rollback")).unwrap().state == "absent"
    assert (await session.activity.query(ctx)).unwrap().events == []
    await session.close()


async def test_concurrent_close_is_one_owned_finalization(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    results = await asyncio.gather(session.close(), session.close())
    assert all(result.unwrap().closed for result in results)
    assert results[0].value == results[1].value
    assert (await session.close()).unwrap().closed
    reopened = (await StorageSession.open(tmp_path / "store")).unwrap()
    await reopened.close()


async def test_reopen_health_observation_preserves_committed_history(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    receipt = (await session.artifacts.put(ctx, "health-object", ctx.scope, b"original")).unwrap()
    await session.close()
    (tmp_path / "store" / "objects" / (receipt.artifact_ref.id + ".bin")).unlink()
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    ctx = context(session)
    status = (await session.operations.status(ctx, "health-object")).unwrap()
    assert status.state == "committed" and status.receipt.event_receipt == receipt.event_receipt
    assert (await session.artifacts.open(ctx, receipt.artifact_ref)).error.code == "INTEGRITY_ERROR"
    history = (await session.activity.query(ctx)).unwrap()
    assert sum(row["event"]["kind"] == "storage.integrity_observed" for row in history.events) == 1
    assert sum(row["event"]["kind"] == "artifact.committed" for row in history.events) == 1
    await session.close()


async def test_revoked_reserved_publication_aborts_and_never_recovers(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def pause(phase, operation_id):
        if phase == "sealed":
            entered.set()
            release.wait(10)
    session, ctx = await opened(tmp_path / "store", fault_hook=pause)
    task = asyncio.create_task(session.artifacts.put(ctx, "revoked-publication", ctx.scope, b"not published"))
    assert await asyncio.to_thread(entered.wait, 5)
    ctx.grants.revoked = True
    release.set()
    failure = await task
    assert failure.error.code == "ACCESS_DENIED" and failure.error.commit_state == "not_committed"
    await session.close()
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    fresh = context(session)
    status = (await session.operations.status(fresh, "revoked-publication")).unwrap()
    assert status.state == "aborted" and status.receipt is None
    assert (await session.activity.query(fresh)).unwrap().events == []
    await session.close()


async def test_shared_scope_registration_multiscope_visibility_and_key_grants(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    shared = ScopeRef("shared", "shared-a")
    ctx.grants.grants.extend([Grant("admin.provision", shared), Grant("state.commit", shared, frozenset({"allowed"})), Grant("state.read", shared), Grant("operation.status", shared)])
    (await session.provision_scope(ctx, shared, {"name": "explicit-shared"})).unwrap()
    assert (await session.state.commit(ctx, "forbidden-key", [StateMutation(shared, "other", "put", 0, 1)])).error.code == "ACCESS_DENIED"
    committed = (await session.state.commit(ctx, "multiscope", [StateMutation(ctx.scope, "local", "put", 0, 1), StateMutation(shared, "allowed", "put", 0, None)])).unwrap()
    assert (await session.state.get(ctx, shared, "allowed")).unwrap().present
    assert (await session.operations.status(ctx, "multiscope")).unwrap().receipt.operation_id == committed.operation_id
    assert (await session.activity.query(ctx)).unwrap().events == []
    ctx.grants.grants.append(Grant("events.read", shared))
    assert len((await session.activity.query(ctx)).unwrap().events) == 1
    await session.close()


async def test_root_lock_denies_real_second_process(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    script = "import asyncio,sys; from ebd.storage import StorageSession; r=asyncio.run(StorageSession.open(sys.argv[1])); print(r.error.code if not r.ok else 'UNEXPECTED_OWNER')"
    result = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", script, str(tmp_path / "store")], capture_output=True, text=True, timeout=10, check=True)
    assert result.stdout.strip() == "STORAGE_BUSY"
    await session.close()


async def test_unindexed_files_are_quarantined_without_fake_run_events(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    await session.close()
    stray = tmp_path / "store" / "objects" / "artifact_unindexed.bin"
    stray.write_bytes(b"not admitted")
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    ctx = context(session)
    assert not stray.exists() and len(session.recovery["unindexed_quarantined"]) == 1
    assert (await session.activity.query(ctx)).unwrap().events == []
    await session.close()


@pytest.mark.parametrize("phase,expected", [("reserved", "interrupted"), ("sealed", "committed"), ("renamed", "committed")])
async def test_actual_process_loss_recovery_preserves_admitted_identity(tmp_path, phase, expected):
    session, ctx = await opened(tmp_path / "store")
    await session.close()
    script = """
import asyncio,os,sys
from ebd.contracts import ExecutionContext,Grant,GrantSet,ScopeRef,deadline_after
from ebd.storage import StorageSession
def crash(boundary,operation_id):
    if boundary==sys.argv[2]: os._exit(61)
async def run():
    s=(await StorageSession.open({'root':sys.argv[1],'fault_hook':crash})).unwrap()
    scope=ScopeRef('run','run-a')
    ctx=ExecutionContext('run-a','run-a','corr-a','root-a',principal='agent-a',store_id=s.store_id,scope=scope,deadline=deadline_after(30),grants=GrantSet([Grant('*',scope)],'agent-a'))
    await s.artifacts.put(ctx,'process-loss',scope,b'crashed bytes')
asyncio.run(run())
"""
    result = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", script, str(tmp_path / "store"), phase], capture_output=True, text=True, timeout=10)
    assert result.returncode == 61
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    ctx = context(session)
    status = (await session.operations.status(ctx, "process-loss")).unwrap()
    assert status.state == expected
    if expected == "committed":
        assert await read_all(session, ctx, status.receipt.artifact_ref) == b"crashed bytes"
        duplicate = (await session.artifacts.put(ctx, "process-loss", ctx.scope, b"crashed bytes")).unwrap()
        assert duplicate.duplicate and duplicate.event_receipt.recorded_seq == status.receipt.event_receipt.recorded_seq
    await session.close()
