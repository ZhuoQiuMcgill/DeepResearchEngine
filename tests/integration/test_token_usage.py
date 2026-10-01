"""Controlled native HTTP responses through real Engine, tools and durable Storage.

These tests exercise accounting and persistence; live provider acceptance is separate.
"""
from __future__ import annotations

import json

import httpx
import pytest

from ebd.connections import (
    Engine, EngineSettings, HistoryReadRequest, RunAccessOptions, RunAccessRequest,
    RunOptions,
)
from ebd.contracts import (
    AgentDefinition, EngineError, ExecutionEvent, RunRef, SnapshotProposal, ToolRef,
    canonical_json, digest_bytes,
)
from ebd.providers import ProviderConfig, ProviderFactory
from ebd.storage._ranges import line_spans


COUNTERS = ("input_tokens", "output_tokens", "total_tokens",
            "cached_input_tokens", "reasoning_output_tokens", "uncached_input_tokens")
TEXT = b"Retained evidence supplied through the registered document.read tool."


def usage(input_tokens, output_tokens, total_tokens, cached=None, reasoning=None, uncached=None):
    primary = (input_tokens, output_tokens, total_tokens)
    return {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": total_tokens, "cached_input_tokens": cached,
        "reasoning_output_tokens": reasoning, "uncached_input_tokens": uncached,
        "completeness": "complete" if all(x is not None for x in primary)
            else "partial" if any(x is not None for x in primary) else "unknown",
        "source": "provider", "measurement_ref": None,
    }


async def two_turn_run(path, monkeypatch, raw_usages, *, provider="deepseek", lose_ack=False):
    requests, lost_events = [], []
    snapshot = None
    model = "gpt-6-luna" if provider == "openai" else "deepseek-flash"
    config = ProviderConfig(provider, model, "https://provider.invalid/v1", "fixture-credential",
                            profile_name=provider, endpoint_id="controlled-provider")

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        turn = len(requests)
        assert turn in (1, 2), "No API replay is permitted"
        arguments = json.dumps({"snapshot_ref": snapshot.to_dict(),
            "range": {"kind": "lines", "start": 1, "end_exclusive": 2},
            "max_text_bytes": 1024, "continuation": None})
        if provider == "openai":
            assert all(t["type"] == "function" for t in body["tools"])
            name = body["tools"][0]["name"]
            output = [{"type": "function_call", "id": "function-1", "call_id": "native-call-1",
                       "name": name, "arguments": arguments}] if turn == 1 else [
                {"type": "message", "content": [{"type": "output_text", "text": "Complete saved result."}]}]
            if turn == 2:
                tool_result = body["input"][-1]
                assert tool_result["type"] == "function_call_output"
                assert tool_result["call_id"] == "native-call-1"
                assert json.loads(tool_result["output"])["result"]["text"] == TEXT.decode()
            response = {"id": f"response-{turn}", "model": model, "status": "completed", "output": output}
        else:
            assert all(t["type"] == "function" for t in body["tools"])
            name = body["tools"][0]["function"]["name"]
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "native-call-1", "type": "function",
                 "function": {"name": name, "arguments": arguments}}]} if turn == 1 else {
                    "role": "assistant", "content": "Complete saved result."}
            if turn == 2:
                tool_result = body["messages"][-1]
                assert tool_result["role"] == "tool" and tool_result["tool_call_id"] == "native-call-1"
                assert json.loads(tool_result["content"])["result"]["text"] == TEXT.decode()
            response = {"id": f"response-{turn}", "model": model, "choices": [
                {"finish_reason": "tool_calls" if turn == 1 else "stop", "message": message}]}
        if raw_usages[turn - 1] is not None:
            response["usage"] = raw_usages[turn - 1]
        return httpx.Response(200, json=response)

    original_open = ProviderFactory.open
    async def controlled_open(config, context=None):
        return await original_open(config, context, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    settings = EngineSettings(workspace=path, storage_root=path / "store", profiles={provider: config})
    engine = (await Engine.open(settings)).unwrap()
    definition = AgentDefinition("usage-fixture", "Read the supplied retained evidence, then return a complete result.",
        model_ref=model, profile_ref=provider, allowed_tools=[ToolRef("document.read")],
        limits={"max_model_calls": 2, "max_tool_calls": 1, "max_tool_attempts": 1})
    registered = engine.register_agent(definition).unwrap()
    session = (await engine.open_agent_session(registered, RunOptions(timeout_seconds=30))).unwrap()
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(TEXT),
             "lines": line_spans(TEXT), "pages": None}
    snapshot = (await session.binding.snapshots.commit(session.context, "seed-evidence", session.context.scope,
        SnapshotProposal(TEXT, TEXT, canonical_json(index), {"fixture": "retained local evidence"}))).unwrap().snapshot_ref
    if lose_ack:
        backend = engine.storage._backend
        original_append = backend.append
        def commit_then_lose_reply(event, origin, scopes, event_digest):
            receipt = original_append(event, origin, scopes, event_digest)
            if event["kind"] == "model.outcome" and not lost_events:
                lost_events.append(event)
                raise OSError("Controlled acknowledgement loss after the real SQLite COMMIT")
            return receipt
        monkeypatch.setattr(backend, "append", commit_then_lose_reply)
    admission = (await engine.runtime.admit(session.definition, "Read evidence", session.binding, session.context)).unwrap()
    result = await engine.runtime.execute(admission)
    assert result.status == "succeeded" and result.recording_status == "complete", (result.error, result.recording_error)
    assert result.counters["model_calls"] == len(requests) == 2
    assert result.counters["tool_calls"] == result.counters["tool_attempts"] == 1
    return settings, engine, session, result, requests, lost_events


async def saved_history(engine, run_ref):
    request = RunAccessRequest(history=HistoryReadRequest(max_pages=20, max_events=1000))
    access = (await engine.open_run_access(run_ref, request, RunAccessOptions())).unwrap()
    rows, cursor = [], None
    try:
        assert access.context.purpose == "result_access"
        for model in ("deepseek-flash", "gpt-6-luna"):
            with pytest.raises(EngineError) as denied:
                access.context.authorize("model.generate", object_id=model)
            assert denied.value.code == "ACCESS_DENIED"
        while True:
            page = (await access.history.query(access.context, {"run_id": run_ref.run_id}, cursor, 5)).unwrap()
            rows.extend(page.events)
            cursor = page.cursor
            if cursor is None:
                return rows
    finally:
        await access.close()


def assert_accounting(rows, result, expected_usage, expected_subtotals, *, require_response_id=True):
    outcomes = [row for row in rows if row["event"]["kind"] == "model.outcome"]
    intents = [row for row in rows if row["event"]["kind"] == "model.intent"]
    assert len(outcomes) == len(intents) == len(expected_usage)
    assert len({r["event"]["context"]["attempt_id"] for r in outcomes}) == len(outcomes)
    assert [r["event"]["payload"]["usage"] for r in outcomes] == expected_usage
    for outcome in outcomes:
        cause = outcome["event"]["context"]
        intent = next(row for row in intents if row["event"]["context"]["attempt_id"] == cause["attempt_id"])
        assert intent["event"]["context"]["action_id"] == cause["action_id"]
        assert intent["receipt"]["recorded_seq"] < outcome["receipt"]["recorded_seq"]
        if require_response_id:
            assert outcome["event"]["payload"]["request_audit"]["provider_response_id"]
    assert result.usage["known_subtotals"] == expected_subtotals
    terminal = next(row for row in rows if row["event"]["kind"] == "agent.finished")
    assert terminal["event"]["payload"]["usage"] == result.usage
    refs = result.usage["per_attempt_usage_refs"]
    assert len(refs) == len(outcomes)
    assert {ref["event_id"] for ref in refs} == {row["event"]["event_id"] for row in outcomes}
    assert all(ref["store_id"] == result.execution["store_id"] for ref in refs)
    assert {(ref["action_id"], ref["attempt_id"]) for ref in refs} == {
        (row["event"]["context"]["action_id"], row["event"]["context"]["attempt_id"]) for row in outcomes}
    return outcomes


@pytest.mark.parametrize("provider", ["deepseek", "openai"])
async def test_each_native_response_usage_survives_fresh_history_and_reopen(tmp_path, monkeypatch, provider):
    def native(inp, out, total, cache, reasoning):
        if provider == "openai":
            return {"input_tokens": inp, "output_tokens": out, "total_tokens": total,
                    "input_tokens_details": {"cached_tokens": cache}, "output_tokens_details": {"reasoning_tokens": reasoning}}
        return {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": total,
                "prompt_cache_hit_tokens": cache, "prompt_cache_miss_tokens": inp - cache,
                "completion_tokens_details": {"reasoning_tokens": reasoning}}
    settings, engine, session, result, requests, _ = await two_turn_run(
        tmp_path, monkeypatch, (native(11, 4, 15, 3, 2), native(17, 6, 23, 5, 4)), provider=provider)
    expected = [usage(11, 4, 15, 3, 2, 8 if provider == "deepseek" else None),
                usage(17, 6, 23, 5, 4, 12 if provider == "deepseek" else None)]
    subtotals = dict(zip(COUNTERS, (28, 10, 38, 8, 6, 20 if provider == "deepseek" else None)))
    run_ref = RunRef(engine.storage.store_id, result.execution["run_id"])
    try:
        rows = await saved_history(engine, run_ref)
        original = assert_accounting(rows, result, expected, subtotals)
        assert result.usage["completeness"] == "complete" and result.usage["unknown_attempt_ids"] == []
        await session.close()
        assert (await engine.close()).complete
        engine = (await Engine.open(settings)).unwrap()
        restored = assert_accounting(await saved_history(engine, run_ref), result, expected, subtotals)
        assert restored == original and len(requests) == 2
    finally:
        await session.close()
        await engine.close()


@pytest.mark.parametrize("raw_usages,expected,subtotals", [
    ((None, {"prompt_tokens": 7, "completion_tokens": 3}),
     [usage(None, None, None), usage(7, 3, None)], (7, 3, None, None, None, None)),
    (({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None),
     [usage(0, 0, 0), usage(None, None, None)], (0, 0, 0, None, None, None)),
    ((None, None), [usage(None, None, None), usage(None, None, None)], (None, None, None, None, None, None)),
])
async def test_missing_partial_and_zero_counts_are_durable_without_inferred_totals(
        tmp_path, monkeypatch, raw_usages, expected, subtotals):
    settings, engine, session, result, requests, _ = await two_turn_run(tmp_path, monkeypatch, raw_usages)
    run_ref = RunRef(engine.storage.store_id, result.execution["run_id"])
    try:
        await session.close()
        assert (await engine.close()).complete
        engine = (await Engine.open(settings)).unwrap()
        outcomes = assert_accounting(await saved_history(engine, run_ref), result, expected, dict(zip(COUNTERS, subtotals)))
        unknown = [row["event"]["context"]["attempt_id"] for row, value in zip(outcomes, expected)
                   if value["completeness"] != "complete"]
        assert result.usage["unknown_attempt_ids"] == unknown
        assert result.usage["completeness"] == ("unknown" if all(v["completeness"] == "unknown" for v in expected) else "partial")
        assert len(requests) == 2
    finally:
        await session.close()
        await engine.close()


async def test_committed_usage_lost_reply_reconciles_once_even_at_final_write_quota(tmp_path, monkeypatch):
    raw = ({"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
           {"prompt_tokens": 17, "completion_tokens": 6, "total_tokens": 23})
    settings, engine, session, result, requests, lost_events = await two_turn_run(tmp_path, monkeypatch, raw, lose_ack=True)
    run_ref = RunRef(engine.storage.store_id, result.execution["run_id"])
    expected = [usage(11, 4, 15), usage(17, 6, 23)]
    subtotals = dict(zip(COUNTERS, (28, 10, 38, None, None, None)))
    try:
        rows = await saved_history(engine, run_ref)
        original = assert_accounting(rows, result, expected, subtotals)
        assert len(lost_events) == 1
        frozen = ExecutionEvent(**lost_events[0])
        cause = frozen.context
        context = session.context.for_action(cause["action_id"], cause["attempt_id"])
        session.context.ledger.limits["storage_writes"] = session.context.ledger.used["storage_writes"]
        assert context.ledger.remaining("storage_writes") == 0
        duplicate = (await engine.storage.recorder.append(context, frozen)).unwrap()
        assert duplicate.duplicate and duplicate.recorded_seq == original[0]["receipt"]["recorded_seq"]
        await session.close()
        assert (await engine.close()).complete
        engine = (await Engine.open(settings)).unwrap()
        restored = assert_accounting(await saved_history(engine, run_ref), result, expected, subtotals)
        assert restored == original and len(requests) == 2
    finally:
        await session.close()
        await engine.close()


@pytest.mark.parametrize("response_kind", ["http_error", "malformed_success"])
async def test_failed_api_response_usage_remains_a_committed_partial_observation(tmp_path, monkeypatch, response_kind):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        body = {"id": "failed-response", "model": "deepseek-flash", "usage": {"prompt_tokens": 4}}
        if response_kind == "http_error":
            body["error"] = {"type": "insufficient_quota", "message": "Controlled provider failure"}
        else:
            body["choices"] = []
        return httpx.Response(429 if response_kind == "http_error" else 200, json=body)
    original_open = ProviderFactory.open
    async def controlled_open(config, context=None):
        return await original_open(config, context, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    config = ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid/v1", "fixture-credential", profile_name="deepseek")
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", profiles={"deepseek": config})
    engine = (await Engine.open(settings)).unwrap()
    try:
        registered = engine.register_agent(AgentDefinition("failed-usage-fixture", "Return a complete result.",
            limits={"max_model_calls": 1})).unwrap()
        result = await engine.run_agent(registered, "task", RunOptions(timeout_seconds=30))
        assert result.status == "failed" and result.recording_status == "complete"
        assert result.counters["model_calls"] == len(requests) == 1
        run_ref = RunRef(engine.storage.store_id, result.execution["run_id"])
        assert (await engine.close()).complete
        engine = (await Engine.open(settings)).unwrap()
        rows = await saved_history(engine, run_ref)
        outcomes = assert_accounting(rows, result, [usage(4, None, None)],
            dict(zip(COUNTERS, (4, None, None, None, None, None))), require_response_id=False)
        assert result.usage["completeness"] == "partial"
        assert result.usage["unknown_attempt_ids"] == [outcomes[0]["event"]["context"]["attempt_id"]]
        assert outcomes[0]["event"]["payload"]["error"] and len(requests) == 1
    finally:
        await engine.close()
