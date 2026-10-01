import asyncio
import json

import httpx

from ebd.connections import AgentRef, Engine, EngineSettings, InvocationRule, RunOptions
from ebd.contracts import AgentDefinition, ArtifactMetadata, Err, RunRef, StateMutation
from ebd.providers import ProviderConfig, ProviderFactory


async def opened(tmp_path, monkeypatch):
    native = ProviderFactory.open
    async def controlled(config, context=None):
        return await native(config, context, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "id": "reply", "model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "child"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}})))
    monkeypatch.setattr(ProviderFactory, "open", controlled)
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store",
        profiles={"deepseek": ProviderConfig("deepseek", "deepseek-flash", "https://private.invalid", "private-key")})
    engine = (await Engine.open(settings)).unwrap()
    child = engine.register_agent(AgentDefinition("child", "Reply.")).unwrap()
    parent = engine.register_agent(AgentDefinition("parent", "Coordinate."), [InvocationRule(child.ref)]).unwrap()
    session = (await engine.open_agent_session(parent.ref, RunOptions(timeout_seconds=30))).unwrap()
    return engine, session, child, settings


async def test_catalog_history_state_and_objects_reopen_with_fresh_host_authority(tmp_path, monkeypatch):
    engine, parent, child, settings = await opened(tmp_path, monkeypatch)
    ref = RunRef(engine.storage.store_id, parent.context.run_id)
    try:
        catalog = json.dumps(engine.list_profiles())
        assert "private-key" not in catalog and "private.invalid" not in catalog
        assert len(engine.list_agents()) == 2
        (await engine.storage.state.commit(parent.context, "s1", [StateMutation(parent.context.scope, "phase", "put", 0, "discovery")])).unwrap()
        (await engine.storage.state.commit(parent.context, "s2", [StateMutation(parent.context.scope, "phase", "put", 1, "writing")])).unwrap()
        artifact = (await engine.storage.artifacts.put(parent.context, "saved", parent.context.scope,
            b"retained", ArtifactMetadata("text/plain"))).unwrap()
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "child input")
        child_ref = outcome.child_run
        assert outcome.status == "succeeded"
        page = (await engine.query_run_events(ref, limit=2, include_descendants=True)).unwrap()
        rows = list(page["events"])
        while page["has_more"]:
            page = (await engine.query_run_events(ref, after_seq=page["next_after_seq"], limit=2, include_descendants=True)).unwrap()
            rows.extend(page["events"])
        assert any(row["event"]["context"]["run_id"] == child_ref.run_id for row in rows)
        assert len({row["event"]["event_id"] for row in rows}) == len(rows)
        denied = await engine.query_run_events(child_ref, include_descendants=True)
        assert isinstance(denied, Err) and denied.error.code == "ACCESS_DENIED"
        assert (await engine.read_run_state(ref, "phase", version=1)).unwrap().value == "discovery"
        assert (await engine.read_run_state(ref, "phase")).unwrap().value == "writing"
        objects = (await engine.list_run_objects(ref)).unwrap()["objects"]
        assert any(obj["ref"] == artifact.artifact_ref.to_dict() for obj in objects)
        await parent.close()
        await engine.close()
        engine = (await Engine.open(settings)).unwrap()
        assert (await engine.read_run_state(ref, "phase")).unwrap().value == "writing"
        terminal = (await engine.describe_run(child_ref)).unwrap()["terminal_event"]
        assert terminal["event"]["payload"]["status"] == "succeeded"
        assert (await engine.list_runs()).unwrap()["runs"]
        settings.host_principal = "other-host"
        await engine.close()
        engine = (await Engine.open(settings)).unwrap()
        assert (await engine.list_runs()).unwrap()["runs"] == []
        assert isinstance(await engine.describe_run(ref), Err)
        assert isinstance(await engine.read_run_state(ref, "phase"), Err)
    finally:
        await parent.close()
        await engine.close()


async def test_lineage_poll_child_added_after_catalog_is_deferred_without_skip(tmp_path, monkeypatch):
    engine, parent, child, _ = await opened(tmp_path, monkeypatch)
    original = engine.storage.list_runs
    created = None
    async def racing_catalog(context, filters=None, cursor=None, limit=100):
        nonlocal created
        page = await original(context, filters, cursor, limit)
        if created is None:
            created = await parent.binding.invoker.invoke(parent.context, child.ref, "new concurrent child")
        return page
    monkeypatch.setattr(engine.storage, "list_runs", racing_catalog)
    try:
        ref = RunRef(engine.storage.store_id, parent.context.run_id)
        initial = (await engine.query_run_events(ref, include_descendants=True)).unwrap()
        assert created.status == "succeeded"
        assert all(row["event"]["context"]["run_id"] != created.child_run.run_id for row in initial["events"])
        following = (await engine.query_run_events(ref, initial["next_after_seq"], include_descendants=True)).unwrap()
        assert any(row["event"]["context"]["run_id"] == created.child_run.run_id for row in following["events"])
        seqs = [row["receipt"]["recorded_seq"] for row in initial["events"] + following["events"]]
        assert seqs == sorted(set(seqs))
    finally:
        await parent.close()
        await engine.close()
