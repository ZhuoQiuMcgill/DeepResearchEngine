"""Real Store and Runtime boundary checks; native HTTP controlled for policy faults."""
import dataclasses

import httpx
import pytest

from deepresearch.engine.connections import (
    AgentRef, Engine, EngineSettings, InvocationRule, InvocationOptions,
    EvidenceBinding, SnapshotReadRequest, ArtifactReadRequest, StateReadRequest,
    RunOptions,
)
from deepresearch.engine.contracts import (
    AgentDefinition, ArtifactMetadata, ByteRange, Err, Grant, GrantSet,
    ScopeRef, SnapshotProposal, StateMutation, canonical_json, digest_bytes,
    RunRef,
)
from deepresearch.engine.providers import ProviderConfig, ProviderFactory


async def fixture(tmp_path, monkeypatch, allow=True):
    native = ProviderFactory.open
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "child", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "read evidence"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14}})
    async def controlled(config, context=None):
        return await native(config, context, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(ProviderFactory, "open", controlled)
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store",
        profiles={"deepseek": ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-key")}))).unwrap()
    child = engine.register_agent(AgentDefinition("reader", "Read evidence.")).unwrap()
    parent = engine.register_agent(AgentDefinition("strategy", "Coordinate.", allowed_tools=[]),
        [InvocationRule(child.ref, allow_evidence=allow)]).unwrap()
    session = (await engine.open_agent_session(parent.ref, RunOptions(timeout_seconds=30))).unwrap()
    text = b"public\nselected\nprivate\n"
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text),
             "lines": [{"line": 1, "start_byte": 0, "end_byte": 6},
                       {"line": 2, "start_byte": 7, "end_byte": 15},
                       {"line": 3, "start_byte": 16, "end_byte": 23}], "pages": None}
    snapshot = (await session.binding.storage.snapshots.commit(session.context, "source", session.context.scope,
        SnapshotProposal(text, text, canonical_json(index), {"url": "https://example.org/evidence"}))).unwrap()
    artifact = (await session.binding.storage.artifacts.put(session.context, "bytes", session.context.scope,
        b"selected-private", ArtifactMetadata("text/plain"))).unwrap()
    (await session.binding.storage.state.commit(session.context, "state", [
        StateMutation(session.context.scope, "shared", "put", 0, {"round": 1}),
        StateMutation(session.context.scope, "private", "put", 0, "secret")])).unwrap()
    return engine, session, child, snapshot.snapshot_ref, artifact.artifact_ref, calls


def selected(snapshot, artifact, scope):
    return EvidenceBinding(read_objects=(
        SnapshotReadRequest(snapshot, {"kind": "lines", "start": 2, "end_exclusive": 3}, 32),
        ArtifactReadRequest(artifact, ByteRange(0, 8), 8)),
        state_reads=(StateReadRequest(scope, "shared", 1024),))


async def test_selected_evidence_read_only_and_no_reference_authority(tmp_path, monkeypatch):
    engine, parent, child, snapshot, artifact, calls = await fixture(tmp_path, monkeypatch)
    original = engine.runtime.admit
    observed = []
    async def checked(definition, task, binding, context):
        if context.agent_id == "reader":
            piece = await binding.storage.snapshots.read(context, snapshot, {"kind": "lines", "start": 2, "end_exclusive": 3}, 32)
            observed.append(piece)
            assert isinstance(await binding.storage.snapshots.read(context, snapshot, {"kind": "lines", "start": 1, "end_exclusive": 4}, 32), Err)
            assert isinstance(await binding.storage.state.get(context, parent.context.scope, "private"), Err)
            assert isinstance(await binding.storage.state.commit(context, "denied", [StateMutation(parent.context.scope, "shared", "put", 1, {})]), Err)
            if not isinstance(piece, Err):
                assert piece.value.text.strip() == "selected"
                assert (await binding.storage.state.get(context, parent.context.scope, "shared")).unwrap().value == {"round": 1}
                reader = (await binding.storage.artifacts.open(context, artifact, ByteRange(0, 8), 8)).unwrap()
                assert (await reader.read(context, 8)).unwrap().bytes == b"selected"
                await reader.aclose(context)
                assert isinstance(await binding.storage.artifacts.open(context, artifact), Err)
        return await original(definition, task, binding, context)
    monkeypatch.setattr(engine.runtime, "admit", checked)
    try:
        # A locator in task data alone confers no permission.
        first = await parent.binding.invoker.invoke(parent.context, child.ref, str(snapshot.to_dict()))
        assert first.status == "succeeded" and isinstance(observed[0], Err)
        second = await parent.binding.invoker.invoke(parent.context, child.ref, "read", InvocationOptions(
            evidence=selected(snapshot, artifact, parent.context.scope)))
        assert second.status == "succeeded" and not isinstance(observed[1], Err)
        assert second.recording_status == "complete" and len(calls) == 2
        events = (await engine.storage.activity.query(parent.context)).unwrap().events
        assert any(row["event"]["payload"].get("evidence") for row in events if row["event"]["kind"] == "invocation.intent")
    finally:
        await parent.close()
        await engine.close()


async def test_edge_opt_in_required_before_dispatch(tmp_path, monkeypatch):
    engine, parent, child, snapshot, artifact, calls = await fixture(tmp_path, monkeypatch, False)
    try:
        result = await parent.binding.invoker.invoke(parent.context, child.ref, "read", InvocationOptions(
            evidence=selected(snapshot, artifact, parent.context.scope)))
        assert result.error.code == "ACCESS_DENIED" and not result.dispatched and calls == []
    finally:
        await parent.close()
        await engine.close()


async def test_completed_reader_source_can_be_bound_to_parent_then_writer(tmp_path, monkeypatch):
    engine, source, child, snapshot, artifact, calls = await fixture(tmp_path, monkeypatch)
    source_ref = RunRef(engine.storage.store_id, source.context.run_id)
    source_scope = source.context.scope
    await source.close()
    parent = (await engine.open_agent_session("strategy", RunOptions(timeout_seconds=30))).unwrap()
    evidence = selected(snapshot, artifact, source_scope)
    try:
        denied = await parent.binding.invoker.invoke(parent.context, child.ref, "read", InvocationOptions(evidence=evidence))
        assert not denied.dispatched and calls == []
        bound = (await engine.bind_evidence(parent, source_ref, evidence)).unwrap()
        piece = (await parent.binding.snapshots.read(parent.context, snapshot,
            {"kind": "lines", "start": 2, "end_exclusive": 3}, 32)).unwrap()
        assert piece.text.strip() == "selected"
        assert isinstance(await parent.binding.storage.state.commit(parent.context, "no-source-write",
            [StateMutation(source_scope, "shared", "put", 1, {})]), Err)
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "write", InvocationOptions(evidence=evidence))
        assert outcome.status == "succeeded" and len(calls) == 1
        assert bound["event_receipt"]["recorded_seq"] < outcome.intent_receipt.recorded_seq
        # Same-owner objects from a different run cannot be substituted.
        mismatched = await engine.bind_evidence(parent, RunRef(engine.storage.store_id, parent.context.run_id), evidence)
        assert isinstance(mismatched, Err)
        await parent.close()
        assert isinstance(await engine.bind_evidence(parent, source_ref, evidence), Err)
    finally:
        await source.close()
        await parent.close()
        await engine.close()


@pytest.mark.parametrize("mode", ["bind", "invoke"])
async def test_evidence_audit_and_grants_use_one_frozen_selection(tmp_path, monkeypatch, mode):
    engine, source, child, snapshot, artifact, calls = await fixture(tmp_path, monkeypatch)
    parent = source
    if mode == "bind":
        await source.close()
        parent = (await engine.open_agent_session("strategy", RunOptions(timeout_seconds=30))).unwrap()
    interval = {"kind": "lines", "start": 2, "end_exclusive": 3}
    evidence = EvidenceBinding(read_objects=[SnapshotReadRequest(snapshot, interval, 32)])
    describe = engine.storage.describe_object
    async def mutate_during_lookup(context, ref):
        # Another task mutates the caller's dictionary during an awaited read.
        interval.update(start=1, end_exclusive=4)
        return await describe(context, ref)
    monkeypatch.setattr(engine.storage, "describe_object", mutate_during_lookup)
    try:
        if mode == "bind":
            receipt = (await engine.bind_evidence(parent, RunRef(engine.storage.store_id, source.context.run_id), evidence)).unwrap()
            assert receipt["evidence"]["read_objects"][0]["range"] == {"kind": "lines", "start": 2, "end_exclusive": 3}
            assert isinstance(await parent.binding.snapshots.read(parent.context, snapshot, interval, 32), Err)
        else:
            original = engine.runtime.admit
            async def inspect(definition, task, binding, context):
                if context.agent_id == "reader":
                    assert isinstance(await binding.snapshots.read(context, snapshot, interval, 32), Err)
                    assert (await binding.snapshots.read(context, snapshot,
                        {"kind": "lines", "start": 2, "end_exclusive": 3}, 32)).unwrap().text.strip() == "selected"
                return await original(definition, task, binding, context)
            monkeypatch.setattr(engine.runtime, "admit", inspect)
            result = await parent.binding.invoker.invoke(parent.context, child.ref, "read", InvocationOptions(evidence=evidence))
            assert result.status == "succeeded"
            rows = (await engine.storage.activity.query(parent.context)).unwrap().events
            intent = next(row["event"] for row in rows if row["event"]["kind"] == "invocation.intent")
            assert intent["payload"]["evidence"]["read_objects"][0]["range"] == {"kind": "lines", "start": 2, "end_exclusive": 3}
    finally:
        await parent.close()
        await source.close()
        await engine.close()


@pytest.mark.parametrize("fault", ["range", "bytes", "state", "foreign"])
async def test_delegation_cannot_expand_caller_rights(tmp_path, monkeypatch, fault):
    engine, parent, child, snapshot, artifact, calls = await fixture(tmp_path, monkeypatch)
    try:
        evidence = selected(snapshot, artifact, parent.context.scope)
        # Keep lifecycle/invocation authority, but attenuate the parent's source grant.
        parent.context.grants.grants = [g for g in parent.context.grants.grants if g.operation != "snapshot.read"]
        parent.context.grants.grants.append(Grant("snapshot.read", parent.context.scope, frozenset({snapshot.id}),
            document_range={"kind": "lines", "start": 2, "end_exclusive": 3}, max_text_bytes=32))
        if fault == "range":
            evidence = dataclasses.replace(evidence, read_objects=(SnapshotReadRequest(snapshot,
                {"kind": "lines", "start": 1, "end_exclusive": 4}, 32),))
        elif fault == "bytes":
            evidence = dataclasses.replace(evidence, read_objects=(SnapshotReadRequest(snapshot,
                {"kind": "lines", "start": 2, "end_exclusive": 3}, 64),))
        elif fault == "state":
            evidence = EvidenceBinding(state_reads=(StateReadRequest(ScopeRef("run", "unrelated"), "shared"),))
        else:
            evidence = EvidenceBinding(read_objects=(SnapshotReadRequest(dataclasses.replace(snapshot, store_id="foreign"),
                {"kind": "lines", "start": 2, "end_exclusive": 3}),))
        result = await parent.binding.invoker.invoke(parent.context, child.ref, "read", InvocationOptions(evidence=evidence))
        assert result.status == "failed" and result.error.code == "ACCESS_DENIED"
        assert not result.dispatched and calls == []
    finally:
        await parent.close()
        await engine.close()
