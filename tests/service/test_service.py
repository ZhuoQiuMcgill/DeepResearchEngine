"""HTTP and service contracts over real Engine/SQLite; provider faults controlled.

These tests do not establish live provider acceptance. Root performs that
separately. No production Runtime, Storage, catalog or service is mocked.
"""
from __future__ import annotations

import asyncio
import base64
import time

import httpx
import pytest

from ebd.connections import (
    AgentRef, Engine, EngineSettings, RunOptions, InvocationRule, SnapshotReadRequest, ToolRunOptions,
)
from ebd.contracts import (
    AgentDefinition, ArtifactMetadata, EngineError, Err, RunRef, SnapshotProposal,
    canonical_json, digest_bytes, new_id,
)
from ebd.providers import ProviderConfig, ProviderFactory
from ebd.service import RunService, create_app
from ebd.service.models import (
    ArtifactChunkView, EventPageView, ResultView, RunPageView, UsageView,
)


def settings(tmp_path):
    return EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store",
        profiles={"service-test": ProviderConfig("deepseek", "deepseek-flash",
            "https://provider.invalid", "controlled-test-key")})


async def terminal(client, run_id):
    for _ in range(200):
        response = await client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        view = response.json()
        if not view["active"]:
            return view
        await asyncio.sleep(0.01)
    pytest.fail("Service run did not settle")


@pytest.mark.asyncio
async def test_real_storage_http_lifecycle_result_usage_and_reopen(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "controlled-response", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Saved report.\n"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}})
    original = ProviderFactory.open
    async def controlled_open(config, context):
        return await original(config, context, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    app = create_app(engine=engine)
    service = app.state.run_service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            registered = await client.post("/api/v1/agents", json={"agent_id": "writer", "instructions": "Answer the task.",
                "profile_ref": "service-test", "model_ref": "deepseek-flash"})
            assert registered.status_code == 201, registered.text
            started = await client.post("/api/v1/runs", json={"agent_id": "writer", "input": "Task", "timeout_seconds": 30})
            assert started.status_code == 202, started.text
            run_id = started.json()["run_id"]
            finished = await terminal(client, run_id)
            assert finished["status"] == "succeeded" and finished["recording_status"] == "complete"
            result = (await client.get(f"/api/v1/runs/{run_id}/result")).json()
            ResultView.model_validate(result)
            output_id = result["output_ref"]["artifact_id"]
            assert result["available"] and result["persistence_state"] == "committed"
            first = (await client.get(f"/api/v1/runs/{run_id}/artifacts/{output_id}?max_bytes=5")).json()
            ArtifactChunkView.model_validate(first)
            assert base64.b64decode(first["data"]) == b"Saved" and not first["eof"]
            rest = (await client.get(f"/api/v1/runs/{run_id}/artifacts/{output_id}?start=5&max_bytes=32")).json()
            assert base64.b64decode(rest["data"]) == b" report.\n" and rest["eof"]
            usage = (await client.get(f"/api/v1/runs/{run_id}/usage")).json()
            UsageView.model_validate(usage)
            assert usage["usage"]["known_subtotals"]["total_tokens"] == 14
            cursor, rows = 0, []
            while True:
                page = (await client.get(f"/api/v1/runs/{run_id}/events?after_seq={cursor}&limit=2")).json()
                EventPageView.model_validate(page)
                rows.extend(page["events"])
                assert page["next_after_seq"] >= cursor
                cursor = page["next_after_seq"]
                if not page["has_more"]:
                    break
            assert len({row["receipt"]["event_id"] for row in rows}) == len(rows)
            assert [row["event"]["kind"] for row in rows].count("agent.finished") == 1
            run_page = await client.get("/api/v1/runs?limit=10")
            assert run_page.status_code == 200
            RunPageView.model_validate(run_page.json())
            assert (await client.post(f"/api/v1/runs/{run_id}/cancel")).json()["cancellation_state"] == "already_terminal"
            assert (await client.get("/openapi.json")).json()["paths"]["/api/v1/runs"]["post"]
            schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]
            assert "output_ref" in schemas["ResultView"]["properties"]
            assert schemas["ArtifactReference"]["properties"]["artifact_id"]["type"] == "string"
            assert {"events", "next_after_seq", "has_more"} <= set(schemas["EventPageView"]["properties"])
            assert "known_subtotals" in schemas["UsageAggregate"]["properties"]
            assert any(item.get("type") == "null" for item in schemas["TokenCounts"]["properties"]["input_tokens"]["anyOf"])
            assert "data" in schemas["ArtifactChunkView"]["properties"]
        assert (await service.close()).complete
        assert len(calls) == 1
    finally:
        await service.close()
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = RunService(reopened)
    try:
        assert (await recovered.get_run(run_id))["status"] == "succeeded"
        assert (await recovered.get_result(run_id))["output_ref"] == result["output_ref"]
        assert (await recovered.get_usage(run_id))["usage"] == usage["usage"]
        assert base64.b64decode((await recovered.read_artifact(run_id, output_id))["data"]) == b"Saved report.\n"
    finally:
        await recovered.close()
        await reopened.close()


@pytest.mark.asyncio
async def test_boundaries_reject_before_dispatch_and_sanitize_validation(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    app = create_app(engine=engine, trusted_origins=("http://localhost:5173",))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            assert (await client.get("/api/v1/health")).json()["single_owner"]
            assert (await client.get("/api/v1/health", headers={"origin": "http://localhost"})).status_code == 200
            denied = await client.post("/api/v1/agents", json={"agent_id": "x", "instructions": "x", "api_key": "must-not-echo"})
            assert denied.status_code == 422 and "must-not-echo" not in denied.text
            assert (await client.post("/api/v1/runs", content='{"agent_id":"x","agent_id":"y","input":"x"}', headers={"content-type": "application/json"})).status_code == 422
            assert (await client.post("/api/v1/runs", content=b"x" * 262145, headers={"content-type": "application/json"})).status_code == 413
            assert (await client.get("/api/v1/health", headers={"origin": "https://untrusted.invalid"})).status_code == 403
            assert (await client.get("/api/v1/health", headers={"host": "untrusted.invalid", "origin": "http://untrusted.invalid"})).status_code == 403
            trusted = await client.get("/api/v1/health", headers={"origin": "http://localhost:5173"})
            assert trusted.status_code == 200 and trusted.headers["access-control-allow-origin"] == "http://localhost:5173"
            assert (await client.get("/api/v1/runs/missing")).status_code == 404
            assert (await client.get("/api/v1/runs?limit=101")).status_code == 422
            assert (await client.get("/api/v1/tools")).status_code == 200
            assert "argv" not in (await client.get("/api/v1/tools")).json()["tools"][0]
            profiles = (await client.get("/api/v1/profiles")).text
            assert "controlled-test-key" not in profiles and "provider.invalid" not in profiles
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("192.0.2.1", 123)), base_url="http://localhost") as remote:
            assert (await remote.get("/api/v1/health")).status_code == 403
    finally:
        await app.state.run_service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_cooperative_cancel_and_service_shutdown(tmp_path, monkeypatch):
    reached = asyncio.Event()
    async def handler(request):
        reached.set()
        await asyncio.sleep(30)
        return httpx.Response(500)
    original = ProviderFactory.open
    async def controlled_open(config, context):
        return await original(config, context, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    engine.register_agent(AgentDefinition("slow", "Answer.", profile_ref="service-test")).unwrap()
    service = RunService(engine)
    try:
        handle = await service.start_run(AgentRef("slow"), "Task", RunOptions(timeout_seconds=60))
        await asyncio.wait_for(reached.wait(), 3)
        cancelled = await service.cancel_run(handle["run_id"])
        assert cancelled["cancellation_requested"]
        assert (await service.close(timeout_seconds=10)).complete
        final = await service.get_run(handle["run_id"])
        assert final["status"] == "cancelled" and final["terminal_event_receipt"]
        assert service.active_count == 0
        assert (await service.get_usage(handle["run_id"]))["usage"]["completeness"] == "unknown"
    finally:
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_unfinished_run_reopen_is_interrupted_and_cross_run_artifact_denied(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    ref = engine.register_agent(AgentDefinition("idle", "Answer.", profile_ref="service-test")).unwrap().ref
    source = (await engine.open_agent_session(ref)).unwrap()
    second = (await engine.open_agent_session(ref)).unwrap()
    source_id, other_id = source.context.run_id, second.context.run_id
    artifact = (await source.binding.storage.artifacts.put(source.context, new_id("artifact_"), source.context.scope,
        b"owned content", ArtifactMetadata("text/plain"))).unwrap()
    service = RunService(engine)
    try:
        assert (await service.get_run(source_id))["status"] == "interrupted"
        with pytest.raises(EngineError) as denied:
            await service.read_artifact(other_id, artifact.artifact_ref.artifact_id)
        assert denied.value.code == "NOT_FOUND"
    finally:
        await source.close()
        await second.close()
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_preflight_rejection_does_not_create_owned_work(tmp_path, monkeypatch):
    async def forbidden_open(*args, **kwargs):
        pytest.fail("Input preflight cannot open a provider")
    monkeypatch.setattr(ProviderFactory, "open", forbidden_open)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    engine.register_agent(AgentDefinition("strict", "Answer.", profile_ref="service-test")).unwrap()
    app = create_app(engine=engine)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            rejected = await client.post("/api/v1/runs", json={"agent_id": "strict", "input": 42})
            assert rejected.status_code == 422, rejected.text
            assert app.state.run_service.active_count == 0
            runs = (await client.get("/api/v1/runs")).json()["runs"]
            for run in runs:
                page = (await client.get(f"/api/v1/runs/{run['run_id']}/events")).json()
                assert not any(row["event"]["kind"] == "model.intent" for row in page["events"])
    finally:
        await app.state.run_service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_lifespan_single_owner_releases_real_store(tmp_path):
    app = create_app(settings(tmp_path))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            health = await client.get("/api/v1/health")
            assert health.status_code == 200 and health.json()["ready"]
    assert app.state.cleanup["complete"] and app.state.engine_cleanup["complete"]
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    await reopened.close()


@pytest.mark.asyncio
async def test_standalone_real_document_read_status_and_reopen(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    ref = engine.register_agent(AgentDefinition("source", "No model dispatch.", profile_ref="service-test")).unwrap().ref
    source = (await engine.open_agent_session(ref, RunOptions(metadata={"private": "catalog-private-marker"}))).unwrap()
    text = b"Stored evidence.\nSecond line.\n"
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text),
        "lines": [{"line": 1, "start_byte": 0, "end_byte": 16},
                  {"line": 2, "start_byte": 17, "end_byte": 29}], "pages": None}
    snapshot = (await source.binding.storage.snapshots.commit(source.context, new_id("source_"), source.context.scope,
        SnapshotProposal(text, text, canonical_json(index), {}))).unwrap()
    interval = {"kind": "lines", "start": 1, "end_exclusive": 3}
    source_ref = RunRef(engine.storage.store_id, source.context.run_id)
    service = RunService(engine)
    try:
        tool = await engine.run_tool("document.read", {"snapshot_ref": snapshot.snapshot_ref.to_dict(),
            "range": interval, "max_text_bytes": 1024}, ToolRunOptions(timeout_seconds=30,
                source_run_ref=source_ref, read_objects=(SnapshotReadRequest(snapshot.snapshot_ref, interval, 1024),)))
        assert tool.status == "succeeded", tool.error
        run_id = tool.invocation["run_id"]
        status = await service.get_run(run_id)
        assert status["status"] == "succeeded" and status["recording_status"] == "complete"
        assert status["terminal_kind"] == "tool.outcome" and not status["active"]
        result = await service.get_result(run_id)
        assert result["available"] and result["dispatched"] and result["output_ref"] is None
        assert result["result_descriptor"]["text_sha256"] == digest_bytes(tool.result["text"].encode())
        assert not (await service.get_usage(run_id))["available"]
        assert "catalog-private-marker" not in str(await service.list_runs())
    finally:
        await source.close()
        await service.close()
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = RunService(reopened)
    try:
        assert (await recovered.get_run(run_id))["status"] == "succeeded"
        assert (await recovered.get_result(run_id))["result_descriptor"] == result["result_descriptor"]
    finally:
        await recovered.close()
        await reopened.close()


@pytest.mark.asyncio
async def test_no_evidence_child_inherits_parent_revocation(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    child = engine.register_agent(AgentDefinition("child", "Answer.", profile_ref="service-test")).unwrap()
    parent = engine.register_agent(AgentDefinition("parent", "Coordinate.", profile_ref="service-test"),
        [InvocationRule(child.ref)]).unwrap()
    session = (await engine.open_agent_session(parent.ref)).unwrap()
    original_admit = engine.runtime.admit
    observed = []
    async def revoke_at_admission(definition, task_input, binding, context):
        if definition.agent_id == "child":
            session.context.grants.revoked = True
            with pytest.raises(EngineError) as denied:
                context.authorize("model.generate", object_id="deepseek-flash")
            assert denied.value.code == "ACCESS_DENIED"
            observed.append(True)
        return await original_admit(definition, task_input, binding, context)
    monkeypatch.setattr(engine.runtime, "admit", revoke_at_admission)
    try:
        outcome = await session.binding.invoker.invoke(session.context, child.ref, "Task")
        assert observed and outcome.status == "failed" and not outcome.dispatched
    finally:
        await session.close()
        await engine.close()


@pytest.mark.asyncio
async def test_close_deadline_includes_blocked_admission_commit(tmp_path, monkeypatch):
    async def forbidden_open(*args, **kwargs):
        pytest.fail("Closing during admission cannot dispatch a model")
    monkeypatch.setattr(ProviderFactory, "open", forbidden_open)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    ref = engine.register_agent(AgentDefinition("admitting", "Answer.", profile_ref="service-test")).unwrap().ref
    service = RunService(engine)
    entered, release = asyncio.Event(), asyncio.Event()
    original_commit = engine.storage.state.commit
    async def gated_commit(context, operation_id, mutations, activity=None):
        if any(m.key == "service.run/1" for m in mutations):
            entered.set()
            await release.wait()
        return await original_commit(context, operation_id, mutations, activity)
    monkeypatch.setattr(engine.storage.state, "commit", gated_commit)
    caller = asyncio.create_task(service.start_run(ref, "Task"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        began = time.monotonic()
        cleanup = await service.close(timeout_seconds=0.05)
        assert not cleanup.complete and cleanup.unconfirmed_resources
        assert time.monotonic() - began < 0.5
        assert not caller.done() and service._starting
        release.set()
        handle = await asyncio.wait_for(caller, 3)
        assert (await service.close(timeout_seconds=3)).complete
        view = await service.get_run(handle["run_id"])
        assert view["status"] == "cancelled" and not view["active"]
        assert not service._starting
    finally:
        release.set()
        await asyncio.gather(caller, return_exceptions=True)
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_actual_tool_rejection_preserves_runtime_status_after_reopen(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = RunService(engine)
    try:
        result = await engine.run_tool("document.read", {})
        run_id = result.invocation["run_id"]
        assert result.invocation["dispatched"] is False
        view = await service.get_run(run_id)
        assert view["status"] == result.status and view["recording_status"] == "complete"
        assert view["terminal_kind"] == "tool.rejected"
        durable = await service.get_result(run_id)
        assert durable["dispatched"] is False and durable["error"]["code"] == result.error.code
    finally:
        await service.close()
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = RunService(reopened)
    try:
        assert (await recovered.get_run(run_id))["status"] == result.status
    finally:
        await recovered.close()
        await reopened.close()
