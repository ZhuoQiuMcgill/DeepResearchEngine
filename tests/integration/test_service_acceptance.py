"""Console HTTP consumers exercise the real Engine, SQLite and document worker.

Provider HTTP is controlled here; examples/live_service_check.py supplies the
separate bounded acceptance using actual DeepSeek responses.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time

import httpx
import pytest

from deepresearch.engine.connections import (
    Engine, EngineSettings, EvidenceBinding, InvocationOptions, InvocationRule,
    RunOptions, SnapshotReadRequest,
)
from deepresearch.engine.contracts import AgentDefinition, SnapshotProposal, ToolRef, canonical_json, digest_bytes
from deepresearch.engine.providers import ProviderConfig, ProviderFactory
from deepresearch.engine.storage._ranges import line_spans


TEXT = b"Service acceptance evidence.\nThis text is retained in a real READY snapshot."
REPORT = "Verified the retained service acceptance evidence.\r\n"
TERMINAL = {"succeeded", "failed", "validation_failed", "limit_exhausted", "timed_out", "cancelled", "interrupted"}
COUNTERS = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens",
            "uncached_input_tokens", "reasoning_output_tokens")


async def controlled_engine(path, monkeypatch, *, block=False):
    """Replace provider transport only; retain actual native parsing/tool code."""
    config = ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid/v1", "fixture-credential",
                            profile_name="deepseek", endpoint_id="controlled-service-provider")
    settings = EngineSettings(workspace=path, storage_root=path / "store", profiles={"deepseek": config})
    engine = (await Engine.open(settings)).unwrap()
    observed = {"requests": [], "entered": asyncio.Event(), "snapshots": {}, "tool_results": []}
    original_open = ProviderFactory.open

    async def controlled_open(config, context=None):
        snapshot = None
        if not block:
            index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(TEXT),
                     "lines": line_spans(TEXT), "pages": None}
            receipt = (await engine.storage.snapshots.commit(context, "fixture-seed-" + context.run_id, context.scope,
                SnapshotProposal(TEXT, TEXT, canonical_json(index), {"fixture": "local service evidence"}))).unwrap()
            snapshot = receipt.snapshot_ref
            observed["snapshots"][context.run_id] = snapshot
        turns = 0

        async def handler(request):
            nonlocal turns
            turns += 1
            body = json.loads(request.content)
            observed["requests"].append({"run_id": context.run_id, "body": body})
            observed["entered"].set()
            if block:
                await asyncio.sleep(30)
                raise AssertionError("A cancelled provider request cannot return later content")
            assert turns in (1, 2), "No automatic model replay is permitted"
            name = body["tools"][0]["function"]["name"]
            if turns == 1:
                arguments = {"snapshot_ref": snapshot.to_dict(),
                             "range": {"kind": "lines", "start": 1, "end_exclusive": 3},
                             "max_text_bytes": 1024, "continuation": None}
                message = {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "service-native-call", "type": "function", "function": {
                        "name": name, "arguments": json.dumps(arguments)}}]}
            else:
                native_result = body["messages"][-1]
                assert native_result["role"] == "tool" and native_result["tool_call_id"] == "service-native-call"
                observed["tool_results"].append(json.loads(native_result["content"])["result"])
                message = {"role": "assistant", "content": REPORT}
            return httpx.Response(200, json={"id": f"service-response-{turns}", "model": "deepseek-flash",
                "choices": [{"finish_reason": "tool_calls" if turns == 1 else "stop", "message": message}],
                "usage": {"prompt_tokens": 10 + turns, "completion_tokens": 3, "total_tokens": 13 + turns,
                          "prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 8 + turns,
                          "completion_tokens_details": {"reasoning_tokens": 1}}})

        return await original_open(config, context, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    definition = AgentDefinition("service-reader", "Read the supplied retained evidence, then return a brief report.",
        model_ref="deepseek-flash", profile_ref="deepseek", allowed_tools=[ToolRef("document.read")],
        input_schema={"type": "object", "required": ["question"],
                      "properties": {"question": {"type": "string", "minLength": 1}}, "additionalProperties": False},
        limits={"max_model_calls": 2, "max_tool_calls": 1, "max_tool_attempts": 1,
                "max_run_seconds": 30, "max_model_seconds": 20})
    registered = engine.register_agent(definition).unwrap()
    return settings, engine, registered, observed


def start_body(agent_id="service-reader", *, task_input=None):
    return {"schema_version": 1, "agent_id": agent_id, "revision": 1,
            "input": {"question": "Read the retained evidence"} if task_input is None else task_input,
            "timeout_seconds": 30, "limits": {}, "metadata": {}}


async def poll_terminal(client, run_id, *, timeout=5):
    expires = time.monotonic() + timeout
    while time.monotonic() < expires:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
        response.raise_for_status()
        status = response.json()
        if status["status"] in TERMINAL:
            return status
        await asyncio.sleep(0.01)
    raise AssertionError("The accepted run did not settle within its integration bound")


async def http_history(client, run_id):
    rows, after_seq = [], 0
    for _ in range(64):
        response = await client.get(f"/api/v1/runs/{run_id}/events", params={"after_seq": after_seq, "limit": 3})
        assert response.status_code == 200, response.json()
        response.raise_for_status()
        page = response.json()
        rows.extend(page["events"])
        next_seq = page["next_after_seq"]
        assert next_seq >= after_seq
        if not page["has_more"]:
            return rows
        assert next_seq > after_seq and page["events"]
        after_seq = next_seq
    raise AssertionError("History pagination exceeded its explicit bound")


def assert_durable_usage(rows, aggregate):
    outcomes = [row for row in rows if row["event"]["kind"] == "model.outcome"]
    expected_refs = [{"store_id": row["receipt"]["store_id"], "event_id": row["event"]["event_id"],
                      "action_id": row["event"]["context"]["action_id"],
                      "attempt_id": row["event"]["context"]["attempt_id"]} for row in outcomes]
    assert aggregate["per_attempt_usage_refs"] == expected_refs
    for key in COUNTERS:
        values = [row["event"]["payload"]["usage"][key] for row in outcomes
                  if row["event"]["payload"]["usage"][key] is not None]
        assert aggregate["known_subtotals"][key] == (sum(values) if values else None)
    return outcomes


async def http_artifact(client, run_id, ref, *, chunk_size=17):
    parts, position = [], 0
    for _ in range(128):
        response = await client.get(f"/api/v1/runs/{run_id}/artifacts/{ref['artifact_id']}",
                                    params={"start": position, "max_bytes": chunk_size})
        response.raise_for_status()
        chunk = response.json()
        assert chunk["encoding"] == "base64" and chunk["start"] == position
        data = base64.b64decode(chunk["data"], validate=True)
        assert len(data) <= chunk_size and chunk["next_offset"] == position + len(data)
        parts.append(data)
        position = chunk["next_offset"]
        if chunk["eof"]:
            return b"".join(parts)
    raise AssertionError("Artifact consumption exceeded its explicit bound")


@pytest.mark.asyncio
async def test_http_run_real_document_worker_durable_result_usage_and_reopen(tmp_path, monkeypatch):
    from deepresearch.interfaces.http import create_app

    settings, engine, _, observed = await controlled_engine(tmp_path, monkeypatch)
    app = create_app(engine=engine)
    service = app.state.run_service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            accepted = await client.post("/api/v1/runs", json=start_body())
            assert accepted.status_code == 202
            handle = accepted.json()
            assert handle["schema_version"] == 1 and handle["status"] == "accepted"
            run_id = handle["run_id"]
            status = await poll_terminal(client, run_id)
            assert status["status"] == "succeeded" and status["active"] is False, (await service.get_result(run_id)).get("error")
            assert status["recording_status"] == "complete" and status["automatic_resume"] is False
            result_response = await client.get(f"/api/v1/runs/{run_id}/result")
            result_response.raise_for_status()
            result = result_response.json()
            assert result["available"] is True and result["persistence_state"] == "committed"
            assert result["counters"]["model_calls"] == 2 and result["counters"]["tool_calls"] == 1
            assert [item["text"] for item in observed["tool_results"]] == [TEXT.decode()]
            assert "output" not in result
            report = await http_artifact(client, run_id, result["output_ref"])
            assert report == REPORT.encode("utf-8")
            rows = await http_history(client, run_id)
            outcomes = assert_durable_usage(rows, result["usage"])
            assert len(outcomes) == 2 and result["usage"]["known_subtotals"]["total_tokens"] == 29
            assert all(row["event"]["payload"]["usage"]["completeness"] == "complete" for row in outcomes)
            tools = [row for row in rows if row["event"]["kind"] == "tool.outcome"]
            assert len(tools) == 1 and tools[0]["event"]["payload"]["status"] == "succeeded"
            assert tools[0]["event"]["payload"]["tool"]["name"] == "document.read"
            assert tools[0]["event"]["payload"]["result_descriptor"]["text_sha256"] == digest_bytes(TEXT)
            terminal = next(row for row in rows if row["event"]["kind"] == "agent.finished")
            assert terminal["receipt"] == result["terminal_event_receipt"]
            publications = [row for row in rows if row["event"]["kind"] == "artifact.committed"]
            assert publications and all(row["receipt"]["recorded_seq"] < terminal["receipt"]["recorded_seq"] for row in publications)
            usage_response = await client.get(f"/api/v1/runs/{run_id}/usage")
            usage_response.raise_for_status()
            usage = usage_response.json()
            assert usage["available"] is True and usage["usage"] == result["usage"]
            assert "fixture-credential" not in json.dumps([result, rows, usage])
        assert len(observed["requests"]) == 2
    finally:
        await service.close()
        assert (await engine.close()).complete

    reopened = (await Engine.open(settings)).unwrap()
    restored_app = create_app(engine=reopened)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restored_app), base_url="http://127.0.0.1") as client:
            restored_response = await client.get(f"/api/v1/runs/{run_id}/result")
            restored_response.raise_for_status()
            restored = restored_response.json()
            assert restored["status"] == "succeeded" and restored["automatic_resume"] is False
            for key in ("output_ref", "raw_output_ref", "usage", "terminal_event_receipt", "counters"):
                assert restored[key] == result[key]
            assert await http_artifact(client, run_id, restored["output_ref"]) == report
            restored_rows = await http_history(client, run_id)
            # Fresh authorized artifact readers may append new binding records;
            # every previously observed immutable event must remain identical.
            assert restored_rows[:len(rows)] == rows
            assert_durable_usage(restored_rows, restored["usage"])
            assert len(observed["requests"]) == 2, "Restart reads must never execute a provider again"
    finally:
        await restored_app.state.run_service.close()
        assert (await reopened.close()).complete


@pytest.mark.asyncio
async def test_http_start_rejects_invalid_input_before_acceptance_or_api_dispatch(tmp_path, monkeypatch):
    from deepresearch.interfaces.http import create_app

    _, engine, _, observed = await controlled_engine(tmp_path, monkeypatch)
    app = create_app(engine=engine)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            response = await client.post("/api/v1/runs", json=start_body(task_input={"question": ""}))
            assert response.status_code == 422
            missing = await client.post("/api/v1/runs", json=start_body("missing-agent"))
            assert missing.status_code == 404
            assert observed["requests"] == [] and observed["snapshots"] == {}
    finally:
        await app.state.run_service.close()
        assert (await engine.close()).complete


@pytest.mark.asyncio
@pytest.mark.parametrize("shutdown", [False, True])
async def test_http_cancel_or_shutdown_settles_unknown_remote_usage_before_storage_close(tmp_path, monkeypatch, shutdown):
    from deepresearch.interfaces.http import create_app

    settings, engine, _, observed = await controlled_engine(tmp_path, monkeypatch, block=True)
    app = create_app(engine=engine)
    service = app.state.run_service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            accepted = await client.post("/api/v1/runs", json=start_body())
            assert accepted.status_code == 202
            run_id = accepted.json()["run_id"]
            await asyncio.wait_for(observed["entered"].wait(), 3)
            if shutdown:
                await asyncio.wait_for(service.close(timeout_seconds=3), 4)
            else:
                cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel")
                assert cancelled.status_code in (200, 202)
            status = await poll_terminal(client, run_id)
            assert status["status"] == "cancelled" and status["active"] is False
            rows = await http_history(client, run_id)
            result_response = await client.get(f"/api/v1/runs/{run_id}/result")
            result_response.raise_for_status()
            result = result_response.json()
            assert result["available"] is True and result["output_ref"] is None
            assert result["recording_status"] == "complete" and result["cleanup"]["complete"] is True
            assert result["usage"]["completeness"] == "unknown"
            assert all(value is None for value in result["usage"]["known_subtotals"].values())
            outcomes = assert_durable_usage(rows, result["usage"])
            assert len(outcomes) == 1 and outcomes[0]["event"]["payload"]["usage"]["total_tokens"] is None
            assert len(result["usage"]["unknown_attempt_ids"]) == 1
        assert len(observed["requests"]) == 1
    finally:
        await service.close()
        assert (await engine.close()).complete

    reopened = (await Engine.open(settings)).unwrap()
    restored_app = create_app(engine=reopened)
    try:
        restored = await restored_app.state.run_service.get_result(run_id)
        assert restored["status"] == "cancelled" and restored["usage"] == result["usage"]
        assert restored["terminal_event_receipt"] == result["terminal_event_receipt"]
        assert len(observed["requests"]) == 1
    finally:
        await restored_app.state.run_service.close()
        assert (await reopened.close()).complete


@pytest.mark.asyncio
async def test_delegated_parent_snapshot_child_cli_read_is_visible_through_http_lineage(tmp_path, monkeypatch):
    from deepresearch.interfaces.http import create_app

    config = ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid/v1", "fixture-credential", profile_name="deepseek")
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store",
                                              profiles={"deepseek": config}))).unwrap()
    child = engine.register_agent(AgentDefinition("evidence-reader", "Read the explicitly selected saved source, then return its selected text.",
        allowed_tools=[ToolRef("document.read")], limits={"max_model_calls": 2, "max_tool_calls": 1})).unwrap()
    parent_agent = engine.register_agent(AgentDefinition("evidence-strategy", "Coordinate evidence readers.",
        allowed_tools=[ToolRef("document.read")]), (InvocationRule(child.ref,
        allowed_tools=("document.read",), allow_evidence=True),)).unwrap()
    parent = (await engine.open_agent_session(parent_agent, RunOptions(timeout_seconds=30))).unwrap()
    app = create_app(engine=engine)
    turns = 0
    selected_text = "This text is retained in a real READY snapshot."
    expected_report = "Retained evidence: " + selected_text
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(TEXT),
             "lines": line_spans(TEXT), "pages": None}
    snapshot = (await parent.binding.snapshots.commit(parent.context, "delegated-source", parent.context.scope,
        SnapshotProposal(TEXT, TEXT, canonical_json(index), {"source_kind": "supplied", "fixture": "delegation acceptance"}))).unwrap()
    selector = SnapshotReadRequest(snapshot.snapshot_ref, {"kind": "lines", "start": 2, "end_exclusive": 3}, 128)
    original_open = ProviderFactory.open

    def handler(request):
        nonlocal turns
        turns += 1
        body = json.loads(request.content)
        assert turns in (1, 2)
        if turns == 1:
            name = body["tools"][0]["function"]["name"]
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "delegated-native-call", "type": "function", "function": {"name": name,
                "arguments": json.dumps({"snapshot_ref": selector.ref.to_dict(), "range": selector.range,
                                         "max_text_bytes": selector.max_text_bytes, "continuation": None})}}]}
        else:
            native_result = body["messages"][-1]
            assert native_result["tool_call_id"] == "delegated-native-call"
            assert json.loads(native_result["content"])["result"]["text"] == selected_text
            message = {"role": "assistant", "content": expected_report}
        return httpx.Response(200, json={"id": f"delegated-response-{turns}", "model": "deepseek-flash",
            "choices": [{"finish_reason": "tool_calls" if turns == 1 else "stop", "message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})

    async def controlled_open(config, context=None):
        assert context.agent_id == "evidence-reader"
        return await original_open(config, context, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref,
            canonical_json({"snapshot_ref": selector.ref, "range": selector.range}).decode(),
            InvocationOptions(timeout_seconds=30, evidence=EvidenceBinding(read_objects=(selector,))))
        assert outcome.status == "succeeded" and outcome.recording_status == "complete"
        assert outcome.output == expected_report and outcome.child_result.counters["tool_calls"] == 1
        assert parent.context.ledger.used["model_calls"] == turns == 2
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            response = await client.get(f"/api/v1/runs/{parent.context.run_id}/events",
                params={"include_descendants": True, "limit": 100})
            response.raise_for_status()
            rows = response.json()["events"]
            invocation_intent = next(row for row in rows if row["event"]["kind"] == "invocation.intent")
            invocation_outcome = next(row for row in rows if row["event"]["kind"] == "invocation.outcome")
            child_terminal = next(row for row in rows if row["event"]["kind"] == "agent.finished")
            assert invocation_intent["event"]["payload"]["evidence"]["read_objects"][0]["ref"] == selector.ref.to_dict()
            assert invocation_intent["receipt"]["recorded_seq"] < child_terminal["receipt"]["recorded_seq"] < invocation_outcome["receipt"]["recorded_seq"]
            tool = next(row for row in rows if row["event"]["kind"] == "tool.outcome")
            assert tool["event"]["payload"]["result_descriptor"]["returned_range"] == selector.range
            assert tool["event"]["payload"]["result_descriptor"]["text_sha256"] == digest_bytes(selected_text.encode())
            child_usage_response = await client.get(f"/api/v1/runs/{outcome.child_run.run_id}/usage")
            child_usage_response.raise_for_status()
            child_usage = child_usage_response.json()["usage"]
            assert child_usage == outcome.child_result.usage
            child_rows = [row for row in rows if row["event"]["context"]["run_id"] == outcome.child_run.run_id]
            assert_durable_usage(child_rows, child_usage)
            assert await http_artifact(client, outcome.child_run.run_id, outcome.child_result.output_ref.to_dict()) == expected_report.encode()
    finally:
        await app.state.run_service.close()
        await parent.close()
        assert (await engine.close()).complete


@pytest.mark.asyncio
async def test_http_boundary_rejects_remote_origin_credentials_and_duplicate_json_without_dispatch(tmp_path, monkeypatch):
    from deepresearch.interfaces.http import create_app

    _, engine, _, observed = await controlled_engine(tmp_path, monkeypatch)
    app = create_app(engine=engine)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            origin = await client.post("/api/v1/runs", json=start_body(), headers={"origin": "https://untrusted.invalid"})
            assert origin.status_code == 403
            prohibited = "prohibited-placeholder"
            credential = await client.post("/api/v1/agents", json={
                "agent_id": "credential-reader", "instructions": "Read", "api_key": prohibited})
            assert credential.status_code == 422 and prohibited not in credential.text
            duplicate = await client.post("/api/v1/runs", content='{"agent_id":"service-reader","input":"a","input":"b"}',
                                          headers={"content-type": "application/json"})
            assert duplicate.status_code == 422
            unknown = await client.get("/api/v1/runs/missing-run/status")
            assert unknown.status_code == 404
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("203.0.113.1", 1234)),
                                     base_url="http://127.0.0.1") as remote:
            response = await remote.post("/api/v1/runs", json=start_body())
            assert response.status_code == 403
        assert observed["requests"] == []
    finally:
        await app.state.run_service.close()
        assert (await engine.close()).complete


@pytest.mark.asyncio
async def test_http_accepted_cancel_before_execution_keeps_not_started_terminal_after_restart(tmp_path, monkeypatch):
    from deepresearch.interfaces.http import create_app

    settings, engine, _, observed = await controlled_engine(tmp_path, monkeypatch)
    entered, proceed = asyncio.Event(), asyncio.Event()
    original_execute = engine.runtime.execute

    async def gated_execute(admission):
        entered.set()
        await proceed.wait()
        return await original_execute(admission)

    monkeypatch.setattr(engine.runtime, "execute", gated_execute)
    app = create_app(engine=engine)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            accepted = await client.post("/api/v1/runs", json=start_body())
            assert accepted.status_code == 202
            run_id = accepted.json()["run_id"]
            await asyncio.wait_for(entered.wait(), 3)
            cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel")
            assert cancelled.status_code == 200
            proceed.set()
            assert (await poll_terminal(client, run_id))["status"] == "cancelled"
            response = await client.get(f"/api/v1/runs/{run_id}/result")
            response.raise_for_status()
            result = response.json()
            assert result["available"] is True and result["start_state"] == "not_started"
            assert result["recording_status"] == "complete" and result["output_ref"] is None
            assert result["counters"]["model_calls"] == result["counters"]["tool_calls"] == 0
            rows = await http_history(client, run_id)
            kinds = [row["event"]["kind"] for row in rows]
            assert kinds.count("agent.finished") == 1 and "agent.started" not in kinds and "model.intent" not in kinds
            assert_durable_usage(rows, result["usage"])
            assert result["usage"]["unknown_attempt_ids"] == []
        assert observed["requests"] == []
    finally:
        proceed.set()
        await app.state.run_service.close()
        assert (await engine.close()).complete
    reopened = (await Engine.open(settings)).unwrap()
    restored_app = create_app(engine=reopened)
    try:
        restored = await restored_app.state.run_service.get_result(run_id)
        for key in ("status", "start_state", "usage", "counters", "terminal_event_receipt"):
            assert restored[key] == result[key]
        assert restored["automatic_resume"] is False and observed["requests"] == []
    finally:
        await restored_app.state.run_service.close()
        assert (await reopened.close()).complete


@pytest.mark.asyncio
async def test_live_checker_loopback_tcp_lifecycle_runs_real_document_worker_offline(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "examples" / "live_service_check.py"
    spec = importlib.util.spec_from_file_location("ebd_live_service_acceptance", script)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)

    _, engine, _, observed = await controlled_engine(tmp_path, monkeypatch)
    try:
        async with checker.loopback_server(engine) as client:
            health = await checker.request_json(client, "GET", "/api/v1/health")
            assert health["ready"] is True and health["single_owner"] is True
            accepted = await checker.request_json(client, "POST", "/api/v1/runs", expected=202, json=start_body())
            run_id = accepted["run_id"]
            assert (await poll_terminal(client, run_id))["status"] == "succeeded"
            result = await checker.request_json(client, "GET", f"/api/v1/runs/{run_id}/result")
            assert await checker.artifact(client, run_id, result["output_ref"]) == REPORT.encode()
            observations = checker.usage_observations(await checker.events(client, run_id), result["usage"], require_complete=True)
            assert len(observations) == len(observed["requests"]) == 2
    finally:
        assert (await engine.close()).complete
