"""Real SQLite discovery, metadata inspection and incremental progress."""
from __future__ import annotations

import dataclasses

import pytest

from deepresearch.engine.contracts import (ArtifactContent, ArtifactMetadata, ArtifactRef, BudgetLedger,
    CheckpointEnvelope, ExecutionContext, ExecutionEvent, Grant, GrantSet, ScopeRef,
    SnapshotProposal, StateMutation, canonical_json, deadline_after, digest_bytes)
from deepresearch.engine.storage import StorageSession
from deepresearch.engine.storage._ranges import line_spans


def context(store, run="host-a", principal="host", grants=None):
    scope = ScopeRef("run", run)
    return ExecutionContext(run, run, "correlation", "root-" + run, principal=principal,
        store_id=store.store_id, scope=scope, deadline=deadline_after(120),
        grants=GrantSet(grants if grants is not None else [Grant("*", scope)], principal),
        ledger=BudgetLedger())


async def provision(store, run, owner="host", **fields):
    ctx = context(store, run, owner)
    ctx = dataclasses.replace(ctx, **{key: value for key, value in fields.items()
                                    if key in {field.name for field in dataclasses.fields(ctx)}})
    descriptor = {**ctx.descriptor(), "owner_principal": owner, **fields}
    (await store.provision_run(ctx, descriptor)).unwrap()
    return ctx


def discovery(store, principal="host"):
    return context(store, principal=principal, grants=[
        Grant("runs.list", object_ids=frozenset({principal}))])


async def test_run_catalog_owned_filtered_stable_pages_and_reopen(tmp_path):
    path = tmp_path / "store"
    store = (await StorageSession.open(path)).unwrap()
    await provision(store, "one", agent_id="reader", metadata={"hidden": "not-discovery"})
    await provision(store, "two", root_run_id="one", parent_run_id="one", agent_id="writer")
    await provision(store, "three", agent_id="reader")
    await provision(store, "other", owner="another-host", agent_id="reader")
    await provision(store, "internal", owner="platform-internal", context_kind="standalone_tool")
    ctx = discovery(store)
    first = (await store.list_runs(ctx, limit=1)).unwrap()
    assert [r["run_id"] for r in first["runs"]] == ["one"]
    assert "metadata" not in first["runs"][0]
    await provision(store, "new", agent_id="reader")
    second = (await store.list_runs(ctx, cursor=first["cursor"], limit=1)).unwrap()
    third = (await store.list_runs(ctx, cursor=second["cursor"], limit=1)).unwrap()
    assert [r["run_id"] for r in second["runs"] + third["runs"]] == ["two", "three"]
    assert third["cursor"] is None
    assert [r["run_id"] for r in (await store.list_runs(ctx, {"root_run_id": "one"})).unwrap()["runs"]] == ["one", "two"]
    assert [r["run_id"] for r in (await store.list_runs(ctx, {"agent_id": "reader", "parent_run_id": None})).unwrap()["runs"]] == ["one", "three", "new"]
    assert [r["run_id"] for r in (await store.list_runs(discovery(store, "another-host"))).unwrap()["runs"]] == ["other"]
    assert (await store.list_runs(discovery(store, "platform-internal"))).unwrap()["runs"] == []
    assert (await store.list_runs(ctx, {"agent_id": "reader"}, first["cursor"])).error.code == "INVALID_CURSOR"
    assert (await store.list_runs(discovery(store, "another-host"), cursor=first["cursor"])).error.code == "INVALID_CURSOR"
    await store.close()
    store = (await StorageSession.open(path)).unwrap()
    ctx = discovery(store)
    assert (await store.list_runs(ctx, cursor=first["cursor"])).error.code == "INVALID_CURSOR"
    assert [r["run_id"] for r in (await store.list_runs(ctx)).unwrap()["runs"]] == ["one", "two", "three", "new"]
    await store.close()


async def test_catalog_validation_and_current_authority(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    await provision(store, "one")
    ctx = discovery(store)
    for filters in ([1], {"owner_principal": "host"}, {"root_run_id": None}, {"context_kind": "host"}, {"agent_id": 1}, {"agent_id": "\ud800"}):
        assert (await store.list_runs(ctx, filters)).error.code == "INVALID_DATA"
    for limit in (0, 501, True, "2"):
        assert (await store.list_runs(ctx, limit=limit)).error.code == "LIMIT_EXCEEDED"
    assert (await store.list_runs(context(store))).error.code == "ACCESS_DENIED"
    ctx.grants.revoked = True
    assert (await store.list_runs(ctx)).error.code == "ACCESS_DENIED"
    await store.close()


async def publish_objects(store, ctx):
    artifact = (await store.artifacts.put(ctx, "artifact", ctx.scope, ArtifactContent(b"hello"),
        ArtifactMetadata("text/plain", metadata={"private": "not-in-catalog"}))).unwrap()
    text = b"first\nsecond"
    index = canonical_json({"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text),
                            "lines": line_spans(text), "pages": None})
    snapshot = (await store.snapshots.commit(ctx, "snapshot", ctx.scope,
        SnapshotProposal(b"source", text, index, {"url": "https://example.org"}, "extract/1", "lf/1"))).unwrap()
    checkpoint = (await store.checkpoints.save(ctx, "checkpoint", ctx.scope,
        CheckpointEnvelope(ctx.run_id, {"report": artifact.artifact_ref.to_dict()}))).unwrap()
    return artifact, snapshot, checkpoint


async def test_objects_catalog_metadata_types_stable_pages_reopen(tmp_path):
    path = tmp_path / "store"
    store = (await StorageSession.open(path)).unwrap()
    writer = await provision(store, "one")
    artifact, snapshot, checkpoint = await publish_objects(store, writer)
    ctx = context(store, "one", grants=[Grant("objects.list", writer.scope)])
    first = (await store.list_objects(ctx, writer.scope, limit=2)).unwrap()
    (await store.artifacts.put(writer, "later", writer.scope, ArtifactContent(b"later"))).unwrap()
    objects = list(first["objects"])
    cursor = first["cursor"]
    while cursor:
        page = (await store.list_objects(ctx, writer.scope, cursor, limit=2)).unwrap()
        objects.extend(page["objects"])
        cursor = page["cursor"]
    assert len(objects) == 8  # ordinary artifact, four snapshot parts, snapshot, payload, checkpoint
    assert len({(o["kind"], str(o["ref"])) for o in objects}) == len(objects)
    assert {o["kind"] for o in objects} == {"artifact", "snapshot", "checkpoint"}
    assert len((await store.list_objects(ctx, writer.scope)).unwrap()["objects"]) == 9
    for obj in objects:
        assert set(obj).issuperset({"kind", "ref", "scope", "byte_length", "sha256", "media_type", "schema_version"})
        assert not set(obj) & {"relative_key", "stage_key", "metadata", "origin", "operation_id"}
    reader = context(store, "one", grants=[Grant("artifact.read", writer.scope),
        Grant("snapshot.read", writer.scope), Grant("checkpoint.read", writer.scope)])
    descriptions = [(await store.describe_object(reader, ref)).unwrap() for ref in
                    (artifact.artifact_ref, snapshot.snapshot_ref, checkpoint.checkpoint_ref)]
    assert descriptions[0]["byte_length"] == 5
    assert descriptions[1]["byte_length"] == len(b"first\nsecond")
    assert descriptions[1]["line_count"] == 2 and descriptions[1]["physical_page_count"] is None
    assert descriptions[2]["format"] == "engine_checkpoint/1"
    await store.close()
    store = (await StorageSession.open(path)).unwrap()
    reader = context(store, "one", grants=[Grant("artifact.read", writer.scope),
        Grant("snapshot.read", writer.scope), Grant("checkpoint.read", writer.scope)])
    assert [(await store.describe_object(reader, ref)).unwrap() for ref in
            (artifact.artifact_ref, snapshot.snapshot_ref, checkpoint.checkpoint_ref)] == descriptions
    ctx = context(store, "one", grants=[Grant("objects.list", writer.scope)])
    assert len((await store.list_objects(ctx, writer.scope)).unwrap()["objects"]) == 9
    await store.close()


async def test_owned_scope_and_object_reference_authority(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    writer = await provision(store, "one")
    other = await provision(store, "other", owner="another-host")
    artifact, snapshot, checkpoint = await publish_objects(store, writer)
    foreign_listing = context(store, "one", principal="another-host", grants=[Grant("objects.list", writer.scope)])
    assert (await store.list_objects(foreign_listing, writer.scope)).error.code == "ACCESS_DENIED"
    scope = ScopeRef("shared", "owned")
    admin = context(store, grants=[Grant("admin.provision", scope), Grant("objects.list", scope)])
    (await store.provision_scope(admin, scope, {"owner_principal": "host"})).unwrap()
    assert (await store.list_objects(admin, scope)).unwrap()["objects"] == []
    assert (await store.list_objects(context(store), writer.scope)).error.code == "ACCESS_DENIED"
    scoped = context(store, "one", grants=[Grant("artifact.read", other.scope, frozenset({artifact.artifact_ref.id}))])
    assert (await store.describe_object(scoped, artifact.artifact_ref)).error.code == "NOT_FOUND"
    reader = context(store, "one", grants=[Grant("artifact.read", writer.scope)])
    assert (await store.describe_object(reader, dataclasses.replace(artifact.artifact_ref, store_id="other-store"))).error.code == "NOT_FOUND"
    assert (await store.describe_object(reader, dataclasses.replace(artifact.artifact_ref, schema_version=True))).error.code == "INVALID_DATA"
    assert (await store.describe_object(reader, {**artifact.artifact_ref.to_dict(), "unknown": 1})).error.code == "INVALID_DATA"
    assert (await store.describe_object(reader, ArtifactRef(store.store_id, "missing"))).error.code == "NOT_FOUND"
    assert (await store.describe_object(reader, snapshot.snapshot_ref)).error.code == "ACCESS_DENIED"
    assert (await store.describe_object(reader, checkpoint.checkpoint_ref)).error.code == "ACCESS_DENIED"
    reader.ledger.limits["storage_read_bytes"] = 0
    assert (await store.describe_object(reader, artifact.artifact_ref)).error.code == "LIMIT_EXCEEDED"
    await store.close()


async def append(store, ctx, identity, kind="agent.started"):
    return (await store.recorder.append(ctx, ExecutionEvent(identity, kind, "runtime", ctx, {}))).unwrap()


async def test_incremental_poll_observes_future_records_and_latest(tmp_path):
    path = tmp_path / "store"
    store = (await StorageSession.open(path)).unwrap()
    writer = await provision(store, "one")
    other = await provision(store, "other", owner="another-host")
    first = await append(store, writer, "start-one")
    await append(store, other, "hidden-start")
    ctx = context(store, "one", grants=[Grant("events.read", writer.scope)])
    page = (await store.activity.poll(ctx, {"run_id": "one"}, limit=1)).unwrap()
    assert page["next_after_seq"] == first.recorded_seq and not page["has_more"]
    # The progress watermark is a store sequence clock, without hidden data.
    assert page["high_water_seq"] > first.recorded_seq
    assert (await store.latest_run_event(ctx, "one")).unwrap() is None
    finished = await append(store, writer, "finish-one", "agent.finished")
    resumed = (await store.activity.poll(ctx, {"root_run_id": "one"}, page["next_after_seq"])).unwrap()
    assert [row["event"]["event_id"] for row in resumed["events"]] == ["finish-one"]
    assert resumed["next_after_seq"] == finished.recorded_seq
    assert (await store.latest_run_event(ctx, "one")).unwrap()["receipt"]["event_id"] == "finish-one"
    assert (await store.latest_run_event(ctx, "other")).error.code == "ACCESS_DENIED"
    assert (await store.activity.poll(ctx, {"root_run_id": "other"})).unwrap()["events"] == []
    await store.close()
    store = (await StorageSession.open(path)).unwrap()
    ctx = context(store, "one", grants=[Grant("events.read", writer.scope)])
    assert (await store.activity.poll(ctx, after_seq=first.recorded_seq)).unwrap()["events"][0]["event"]["event_id"] == "finish-one"
    assert (await store.latest_run_event(ctx, "one")).unwrap()["receipt"]["event_id"] == "finish-one"
    await store.close()


async def test_poll_requires_all_event_scopes_and_explicit_child_grants(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    root = await provision(store, "one")
    child = await provision(store, "child", root_run_id="one", parent_run_id="one")
    await append(store, root, "start-one")
    await append(store, child, "start-child")
    writer = context(store, "one", grants=[Grant("state.commit", root.scope), Grant("state.commit", child.scope)])
    receipt = (await store.state.commit(writer, "both", [StateMutation(root.scope, "x", "put", 0, 1),
                                                       StateMutation(child.scope, "x", "put", 0, 1)])).unwrap()
    reader = context(store, "one", grants=[Grant("events.read", root.scope)])
    assert [e["event"]["event_id"] for e in (await store.activity.poll(reader, {"root_run_id": "one"})).unwrap()["events"]] == ["start-one"]
    reader.grants.grants.append(Grant("events.read", child.scope))
    first = (await store.activity.poll(reader, {"root_run_id": "one"}, limit=1)).unwrap()
    assert first["has_more"]
    following = (await store.activity.poll(reader, {"root_run_id": "one"}, first["next_after_seq"])).unwrap()
    assert len(following["events"]) == 2
    assert following["events"][-1]["receipt"]["event_id"] == receipt.event_receipt.event_id
    for value in (-1, True, 2**63, "0"):
        assert (await store.activity.poll(reader, after_seq=value)).error.code == "INVALID_DATA"
    assert (await store.activity.poll(reader, {"owner": "host"})).error.code == "INVALID_DATA"
    assert (await store.activity.poll(reader, limit=501)).error.code == "LIMIT_EXCEEDED"
    reader.grants.revoked = True
    assert (await store.activity.poll(reader)).error.code == "ACCESS_DENIED"
    await store.close()


async def test_catalog_watermark_excludes_earlier_reserved_late_publication(tmp_path):
    fail = True
    def sealed_failure(phase, operation_id):
        nonlocal fail
        if phase == "sealed" and operation_id == "early" and fail:
            fail = False
            raise RuntimeError("controlled sealed interruption")
    store = (await StorageSession.open({"root": tmp_path / "store", "fault_hook": sealed_failure})).unwrap()
    writer = await provision(store, "one")
    with pytest.raises(RuntimeError, match="sealed interruption"):
        await store.artifacts.put(writer, "early", writer.scope, ArtifactContent(b"reserved-first"))
    one = (await store.artifacts.put(writer, "one", writer.scope, ArtifactContent(b"one"))).unwrap()
    two = (await store.artifacts.put(writer, "two", writer.scope, ArtifactContent(b"two"))).unwrap()
    reader = context(store, "one", grants=[Grant("objects.list", writer.scope)])
    first = (await store.list_objects(reader, writer.scope, limit=1)).unwrap()
    # Complete an already-sealed actual publication after the first page.
    await store._call(store._backend.finish_files, "early")
    second = (await store.list_objects(reader, writer.scope, first["cursor"], limit=1)).unwrap()
    assert [first["objects"][0]["ref"], second["objects"][0]["ref"]] == [one.artifact_ref.to_dict(), two.artifact_ref.to_dict()]
    assert second["cursor"] is None
    assert len((await store.list_objects(reader, writer.scope)).unwrap()["objects"]) == 3
    await store.close()


async def test_progress_pages_bound_json_without_skipping_records(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    writer = await provision(store, "one")
    for number in range(20):
        (await store.recorder.append(writer, ExecutionEvent("progress-" + str(number), "progress", "runtime", writer,
                                                          {"text": "x" * 60000}))).unwrap()
    reader = context(store, "one", grants=[Grant("events.read", writer.scope)])
    first = (await store.activity.poll(reader, limit=500)).unwrap()
    assert len(canonical_json(first)) <= 1 << 20 and first["has_more"]
    second = (await store.activity.poll(reader, after_seq=first["next_after_seq"], limit=500)).unwrap()
    assert len(canonical_json(second)) <= 1 << 20 and not second["has_more"]
    assert [row["event"]["event_id"] for row in first["events"] + second["events"]] == ["progress-" + str(n) for n in range(20)]
    reader.ledger.limits["storage_read_bytes"] = reader.ledger.used["storage_read_bytes"]
    assert (await store.activity.poll(reader)).error.code == "LIMIT_EXCEEDED"
    await store.close()


async def test_captured_clock_prevents_new_child_from_being_skipped(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    writer = await provision(store, "one")
    root_receipt = await append(store, writer, "start-one")
    reader = context(store, "one", grants=[Grant("events.read", writer.scope)])
    through = (await store.history_watermark(reader)).unwrap()
    assert through == root_receipt.recorded_seq
    # Host discovered only the root, then a child registered and completed
    # before the root's next observation was recorded.
    child = await provision(store, "child", root_run_id="one", parent_run_id="one")
    await append(store, child, "start-child")
    await append(store, writer, "finish-one", "agent.finished")
    page = (await store.activity.poll(reader, {"root_run_id": "one"}, through_seq=through)).unwrap()
    assert [row["event"]["event_id"] for row in page["events"]] == ["start-one"]
    assert page["high_water_seq"] == through
    # The next fresh capture/discovery grants the registered child before
    # reading its interval, so neither its event nor the parent event is lost.
    through = (await store.history_watermark(reader)).unwrap()
    reader.grants.grants.append(Grant("events.read", child.scope))
    following = (await store.activity.poll(reader, {"root_run_id": "one"}, page["next_after_seq"], through_seq=through)).unwrap()
    assert [row["event"]["event_id"] for row in following["events"]] == ["start-child", "finish-one"]
    for value in (-1, True, 2**63, "0"):
        assert (await store.activity.poll(reader, through_seq=value)).error.code == "INVALID_DATA"
    assert (await store.history_watermark(context(store, grants=[]))).error.code == "ACCESS_DENIED"
    await store.close()


async def test_expired_broad_history_grant_cannot_borrow_narrow_permission(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    writer = await provision(store, "one")
    await append(store, writer, "allowed", "progress")
    await append(store, writer, "hidden", "progress")
    reader = context(store, "one", grants=[
        Grant("events.read", writer.scope, frozenset({"allowed", "hidden"}), expires_at="2000-01-01T00:00:00+00:00"),
        Grant("events.read", writer.scope, frozenset({"allowed"}))])
    page = (await store.activity.poll(reader)).unwrap()
    assert [row["event"]["event_id"] for row in page["events"]] == ["allowed"]
    page = (await store.activity.query(reader)).unwrap()
    assert [row["event"]["event_id"] for row in page.events] == ["allowed"]
    assert (await store.latest_run_event(reader, "one", "progress")).unwrap()["event"]["event_id"] == "allowed"
    reader.grants.principal = "other-host"
    assert (await store.activity.poll(reader)).error.code == "ACCESS_DENIED"
    assert (await store.activity.query(reader)).error.code == "ACCESS_DENIED"
    await store.close()


async def test_expiring_history_selector_cannot_fall_back_after_sqlite_read(tmp_path):
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    writer = await provision(store, "one")
    await append(store, writer, "allowed", "progress")
    await append(store, writer, "hidden", "progress")
    broad = Grant("events.read", writer.scope, frozenset({"allowed", "hidden"}))
    reader = context(store, "one", grants=[broad, Grant("events.read", writer.scope, frozenset({"allowed"}))])
    query = store._backend.query_events
    def expires_on_return(*args):
        result = query(*args)
        broad.expires_at = "2000-01-01T00:00:00+00:00"
        return result
    store._backend.poll_events = expires_on_return
    assert (await store.activity.poll(reader)).error.code == "ACCESS_DENIED"
    broad.expires_at = None
    store._backend.query_events = expires_on_return
    assert (await store.activity.query(reader)).error.code == "ACCESS_DENIED"
    await store.close()


async def test_incremental_sql_range_decodes_only_returned_records(tmp_path, monkeypatch):
    import deepresearch.engine.storage._backend as backend_module
    store = (await StorageSession.open(tmp_path / "store")).unwrap()
    writer = await provision(store, "one")
    foreign = await provision(store, "foreign", owner="other-host")
    for number in range(120):
        old = await append(store, writer, "old-" + str(number), "progress")
    await append(store, foreign, "hidden", "recent")
    await append(store, writer, "wrong-filter", "progress")
    for number in range(4):
        await append(store, writer, "recent-" + str(number), "recent")
    reader = context(store, "one", grants=[Grant("events.read", writer.scope)])
    through = (await store.history_watermark(reader)).unwrap()
    await append(store, writer, "beyond-clock", "recent")
    original_loads, decoded = backend_module.json.loads, []
    def counted_loads(raw, *args, **kwargs):
        result = original_loads(raw, *args, **kwargs)
        if isinstance(raw, str) and isinstance(result, dict) and "context" in result and "event_id" in result:
            decoded.append(result["event_id"])
        return result
    monkeypatch.setattr(backend_module.json, "loads", counted_loads)
    page = (await store.activity.poll(reader, {"kind": "recent"}, old.recorded_seq, 2, through)).unwrap()
    assert decoded == ["recent-0", "recent-1"] and page["has_more"]
    selectors = [{"scope": "run:one", "object_ids": None, "event_kinds": None, "producer": None}]
    where, args = store._backend._event_where(selectors, {"kind": "recent"})
    def query_plan():
        return [row[3] for row in store._backend.db.execute(
            "EXPLAIN QUERY PLAN SELECT e.* FROM events e WHERE e.seq>? AND e.seq<=? AND " +
            where + " ORDER BY e.seq LIMIT ?", [old.recorded_seq, through, *args, 3])]
    plan = await store._call(query_plan)
    assert any("SEARCH e USING INTEGER PRIMARY KEY" in item for item in plan)
    await store.close()
