"""Controlled provider faults against real durable Storage; live acceptance is separate."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from ebd.agent import Runtime
from ebd.contracts import (
    AgentDefinition, BindingSet, BudgetLedger, EngineError, Err, ExecutionContext,
    Grant, GrantSet, Ok, ScopeRef, deadline_after,
)
from ebd.providers import ProviderConfig, ProviderFactory
from ebd.storage import StorageSession


class EmptyCatalog:
    def resolve(self, name, revision):
        return Err(EngineError("NOT_FOUND", "Tool absent"))


async def setup(tmp_path, handler, *, recorder=None, output_schema=None, limits=None):
    storage = (await StorageSession.open(tmp_path / "store")).unwrap()
    scope = ScopeRef("run", "test-run")
    grants = GrantSet([
        Grant("admin.provision", scope), Grant("artifact.put", scope),
        Grant("artifact.read", scope), Grant("events.append", scope, producer="runtime"),
        Grant("events.status", scope), Grant("events.read", scope), Grant("operation.status", scope),
        Grant("model.generate", object_ids=frozenset({"deepseek-flash"})),
        Grant("admission.status"),
    ], "test-principal")
    context = ExecutionContext("test-run", "test-run", "test-correlation", "root-action", principal="test-principal", agent_id="test-agent", deadline=deadline_after(30), scope=scope, store_id=storage.store_id, grants=grants, ledger=BudgetLedger())
    (await storage.provision_run(context, {"run_id": context.run_id, "context_kind": "agent", "agent_id": "test-agent"})).unwrap()
    class BoundFactory:
        @staticmethod
        async def open(config, ctx):
            return await ProviderFactory.open(config, ctx, transport=httpx.MockTransport(handler))
    binding = BindingSet(EmptyCatalog(), None, recorder or storage.recorder, storage.artifacts, storage.snapshots, None,
                         ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-secret"), provider_factory=BoundFactory, storage=storage, output_scope=scope)
    definition = AgentDefinition("test-agent", "Return the final candidate", output_schema=output_schema or {"type": "string"}, limits=limits or {})
    return storage, binding, context, definition


def final_response(text="Exact\r\nreport\n"):
    return httpx.Response(200, json={"id": "response1", "model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9}})


@pytest.mark.asyncio
async def test_exact_output_is_published_before_terminal_and_survives_reopen(tmp_path):
    dispatched = 0
    def handler(request):
        nonlocal dispatched
        dispatched += 1
        return final_response()
    storage, binding, context, definition = await setup(tmp_path, handler)
    runtime = Runtime()
    lease = (await runtime.admit(definition, "task", binding, context)).unwrap()
    assert context.ledger.remaining("model_calls") == 31
    result = await runtime.execute(lease)
    assert result.status == "succeeded" and result.recording_status == "complete"
    assert result.output_ref == result.raw_output_ref
    assert result.output == "Exact\r\nreport\n"
    assert dispatched == 1
    events = (await storage.activity.query(context)).unwrap().events
    kinds = [e["event"]["kind"] if "event" in e else e["kind"] for e in events]
    assert kinds.index("model.intent") < kinds.index("model.outcome") < kinds.index("artifact.committed") < kinds.index("agent.finished")
    duplicate = await runtime.execute(lease)
    assert duplicate.status == "failed" and dispatched == 1
    ref = result.output_ref
    await storage.close()
    reopened = (await StorageSession.open(tmp_path / "store")).unwrap()
    reader = (await reopened.artifacts.open(context, ref)).unwrap()
    chunk = (await reader.read(context)).unwrap()
    assert chunk.bytes == b"Exact\r\nreport\n" and chunk.eof
    await reader.aclose(context)
    await reopened.close()


@pytest.mark.asyncio
async def test_complete_native_tool_batch_is_preflighted_before_first_dispatch(tmp_path):
    import json
    from ebd.toolset import ToolCatalog
    from ebd.contracts import ToolRef
    def handler(req):
        name = json.loads(req.content)["tools"][0]["function"]["name"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "first", "type": "function", "function": {"name": name, "arguments": '{"query":"valid research"}'}},
            {"id": "second", "type": "function", "function": {"name": name, "arguments": '{"query":"bad","forged":"unknown"}'}}
        ]}}]})
    storage, binding, context, definition = await setup(tmp_path, handler)
    binding.catalog = ToolCatalog()
    class NoDispatch:
        async def execute(self, *args):
            raise AssertionError("Whole batch must reject before the first worker")
    binding.executor = NoDispatch()
    definition.allowed_tools = [ToolRef("web.search")]
    context.grants.grants.append(Grant("tool.execute", object_ids=frozenset({"web.search"})))
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "validation_failed" and result.counters["tool_calls"] == 0
    events = (await storage.activity.query(context)).unwrap().events
    kinds = [e.get("event", e)["kind"] for e in events]
    assert "tool.intent" not in kinds and "tool.rejected" in kinds
    await storage.close()


@pytest.mark.asyncio
async def test_missing_start_or_intent_receipt_prevents_model_dispatch(tmp_path):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return final_response()
    storage, binding, context, definition = await setup(tmp_path, handler)
    actual = storage.recorder
    class FailIntent:
        async def append(self, ctx, event):
            if event.kind == "model.intent":
                return Err(EngineError("RECORD_FAILURE", "Controlled intent failure", commit_state="not_committed"))
            return await actual.append(ctx, event)
        async def status(self, *args):
            return await actual.status(*args)
    binding.recorder = FailIntent()
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert calls == 0 and result.recording_status == "incomplete"
    assert result.start_event_receipt is not None and result.terminal_event_receipt is not None
    await storage.close()


@pytest.mark.asyncio
async def test_schema_failure_is_recorded_and_never_published_as_success(tmp_path):
    storage, binding, context, definition = await setup(tmp_path, lambda req: final_response("wrong"), output_schema={"type": "string", "const": "right"})
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "validation_failed" and result.recording_status == "complete"
    assert result.output_ref is None and result.observed_output["raw_visible_text"] == "wrong"
    await storage.close()


@pytest.mark.asyncio
async def test_shared_admission_reservation_and_release_are_real(tmp_path):
    storage, binding, context, definition = await setup(tmp_path, lambda req: final_response())
    context.ledger.limits["model_calls"] = 1
    runtime = Runtime()
    first = (await runtime.admit(definition, "task", binding, context)).unwrap()
    assert isinstance(await runtime.admit(definition, "task", binding, context), Err)
    assert (await first.release()).is_ok
    assert context.ledger.remaining("model_calls") == 1
    assert (await first.release()).value["duplicate"] is True
    assert (await runtime.execute(first)).status == "failed"
    second = (await runtime.admit(definition, "task", binding, context)).unwrap()
    assert (await runtime.execute(second)).status == "succeeded"
    assert context.ledger.remaining("model_calls") == 0
    await storage.close()


@pytest.mark.asyncio
async def test_engine_cancellation_interrupts_remote_request_and_records_terminal(tmp_path):
    entered = asyncio.Event()
    async def handler(req):
        entered.set()
        await asyncio.sleep(20)
        return final_response()
    storage, binding, context, definition = await setup(tmp_path, handler)
    runtime = Runtime()
    task = asyncio.create_task(runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap()))
    await entered.wait()
    context.cancellation.set()
    result = await asyncio.wait_for(task, 3)
    assert result.status == "cancelled" and result.recording_status == "complete"
    assert result.terminal_event_receipt is not None
    await storage.close()


@pytest.mark.asyncio
async def test_json_raw_and_canonical_output_have_separate_durable_artifacts(tmp_path):
    raw = '{ "b": 2, "a": 1 }\n'
    storage, binding, context, definition = await setup(tmp_path, lambda req: final_response(raw))
    definition.output_mode = "json"
    definition.output_media_type = "application/json"
    definition.output_schema = {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"], "additionalProperties": False}
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "succeeded" and result.output == {"a": 1, "b": 2}
    assert result.raw_output_ref != result.output_ref and len(result.output_publications) == 2
    raw_reader = (await storage.artifacts.open(context, result.raw_output_ref)).unwrap()
    validated_reader = (await storage.artifacts.open(context, result.output_ref)).unwrap()
    assert (await raw_reader.read(context)).unwrap().bytes == raw.encode()
    assert (await validated_reader.read(context)).unwrap().bytes == b'{"a":1,"b":2}'
    await raw_reader.aclose(context)
    await validated_reader.aclose(context)
    await storage.close()


@pytest.mark.asyncio
async def test_lost_publication_ack_reconciles_without_second_write(tmp_path):
    storage, binding, context, definition = await setup(tmp_path, lambda req: final_response())
    real = binding.artifacts
    writes = 0
    class LoseReply:
        async def put(self, *args):
            nonlocal writes
            writes += 1
            actual = await real.put(*args)
            assert isinstance(actual, Ok)
            return Err(EngineError("LOST_ACK", "Controlled publication acknowledgement loss", commit_state="unknown"))
    binding.artifacts = LoseReply()
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "succeeded" and result.recording_status == "complete"
    assert result.persistence_state == "committed" and writes == 1
    await storage.close()


@pytest.mark.asyncio
async def test_known_publication_failure_can_be_completely_recorded(tmp_path):
    storage, binding, context, definition = await setup(tmp_path, lambda req: final_response())
    class DenyPublication:
        async def put(self, *args):
            return Err(EngineError("ARTIFACT_IO_FAILURE", "Controlled known publication failure", commit_state="not_committed"))
    binding.artifacts = DenyPublication()
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "failed" and result.recording_status == "complete"
    assert result.persistence_state == "not_committed" and result.output_ref is None
    assert result.observed_output["validation_state"] == "passed" and result.terminal_event_receipt is not None
    await storage.close()


@pytest.mark.asyncio
async def test_lost_outcome_ack_uses_same_recorded_identity(tmp_path):
    storage, binding, context, definition = await setup(tmp_path, lambda req: final_response())
    real = storage.recorder
    outcomes = 0
    class LoseOutcomeReply:
        async def append(self, ctx, event):
            nonlocal outcomes
            actual = await real.append(ctx, event)
            if event.kind == "model.outcome":
                outcomes += 1
                assert isinstance(actual, Ok)
                return Err(EngineError("LOST_ACK", "Controlled outcome acknowledgement loss", commit_state="unknown"))
            return actual
        async def status(self, *args):
            return await real.status(*args)
    binding.recorder = LoseOutcomeReply()
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "succeeded" and result.recording_status == "complete" and outcomes == 1, (result.error, result.recording_error)
    await storage.close()


@pytest.mark.asyncio
async def test_python_task_cancellation_is_recorded_and_reraised(tmp_path):
    entered = asyncio.Event()
    async def handler(req):
        entered.set()
        await asyncio.sleep(20)
        raise AssertionError("Cancelled request cannot produce a candidate")
    storage, binding, context, definition = await setup(tmp_path, handler)
    runtime = Runtime()
    task = asyncio.create_task(runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    events = (await storage.activity.query(context)).unwrap().events
    events = [e.get("event", e) for e in events]
    terminal = next(e for e in events if e["kind"] == "agent.finished")
    assert terminal["payload"]["status"] == "cancelled"
    assert terminal["payload"]["usage"]["completeness"] == "partial"
    assert len(terminal["payload"]["usage"]["unknown_attempt_ids"]) == 1
    assert any(e["kind"] == "model.outcome" for e in events)
    await storage.close()


@pytest.mark.asyncio
async def test_recorded_readonly_source_limit_can_choose_new_url_then_report(tmp_path):
    import json
    from ebd.connections.engine import ToolPlanFactory
    from ebd.contracts import SnapshotProposal, ToolExecutionResult, ToolRef, canonical_json, digest_bytes, to_json_value
    from ebd.storage._ranges import line_spans
    from ebd.toolset import ToolCatalog
    turns = 0
    def handler(req):
        nonlocal turns
        turns += 1
        body = json.loads(req.content)
        name = body["tools"][0]["function"]["name"]
        if turns == 2:
            previous = json.loads(body["messages"][-1]["content"])
            assert previous["error"]["details"]["source_alternative_allowed"] is True
            assert previous["error"]["details"]["retry_previous_attempt"] is False
        if turns < 3:
            url = "https://example.org/blocked.pdf" if turns == 1 else "https://example.org/alternative.txt"
            return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "source" + str(turns), "type": "function", "function": {"name": name, "arguments": json.dumps({"url": url})}}]}}]})
        return final_response("Report from the alternative source\n")
    storage, binding, context, definition = await setup(tmp_path, handler)
    definition.allowed_tools = [ToolRef("web.fetch")]
    context.grants.grants += [Grant("tool.execute", object_ids=frozenset({"web.fetch"})), Grant("snapshot.commit", context.scope)]
    binding.catalog = ToolCatalog()
    binding.storage_plan_factory = ToolPlanFactory(storage, context.scope)
    urls = []
    class ControlledSourceFault:
        async def execute(self, resolved, args, ctx, plan):
            plan.assert_recorded()
            urls.append(args["url"])
            invocation = {"action_id": ctx.action_id, "attempt_id": ctx.attempt_id}
            process = {"dispatched": True, "cleanup": {"complete": True, "unconfirmed_resources": []}, "termination_reason": "stream_limit" if len(urls) == 1 else None}
            persistence = {"required": True, "operation_id": plan.operation_id, "commit_state": "not_committed", "receipt": None}
            if len(urls) == 1:
                return ToolExecutionResult(resolved.ref, invocation, "limit_exhausted", error=EngineError("LIMIT_EXCEEDED", "Controlled source diagnostic flood", observed_effect_state="unknown"), process=process, persistence=persistence)
            text = b"Alternative source evidence\n"
            index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text), "lines": line_spans(text), "pages": None}
            proposal = SnapshotProposal(text, text, canonical_json(index), {"url": args["url"]})
            receipt = (await storage.snapshots.commit(ctx, plan.operation_id, ctx.scope, proposal)).unwrap()
            persistence.update(commit_state="committed", receipt=to_json_value(receipt))
            return ToolExecutionResult(resolved.ref, invocation, "succeeded", result={"snapshot_ref": receipt.snapshot_ref.to_dict()}, process=process, persistence=persistence)
    binding.executor = ControlledSourceFault()
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status == "succeeded" and result.recording_status == "complete"
    assert turns == 3 and urls == ["https://example.org/blocked.pdf", "https://example.org/alternative.txt"]
    assert result.counters["model_calls"] == 3 and result.counters["tool_attempts"] == 2
    await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["lineage_limit", "unknown_commit", "cleanup_incomplete", "model_quota", "missing_outcome", "repeat_request", "terminate_policy"])
async def test_source_recovery_never_bypasses_fatal_boundaries_or_replays(tmp_path, fault):
    import json
    from ebd.connections.engine import ToolPlanFactory
    from ebd.contracts import ToolExecutionResult, ToolRef
    from ebd.toolset import ToolCatalog
    turns = 0
    def handler(req):
        nonlocal turns
        turns += 1
        body = json.loads(req.content)
        name = body["tools"][0]["function"]["name"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "fault" + str(turns), "type": "function", "function": {"name": name, "arguments": '{"url":"https://example.org/failed.pdf"}'}}]}}]})
    storage, binding, context, definition = await setup(tmp_path, handler)
    definition.allowed_tools = [ToolRef("web.fetch")]
    if fault == "terminate_policy":
        definition.error_policy = {"recoverable_tool_errors": "terminate"}
    if fault == "model_quota":
        context.ledger.limits["model_calls"] = 1
    context.grants.grants += [Grant("tool.execute", object_ids=frozenset({"web.fetch"})), Grant("snapshot.commit", context.scope)]
    binding.catalog = ToolCatalog()
    binding.storage_plan_factory = ToolPlanFactory(storage, context.scope)
    attempts = 0
    class SourceFault:
        async def execute(self, resolved, args, ctx, plan):
            nonlocal attempts
            plan.assert_recorded()
            attempts += 1
            return ToolExecutionResult(resolved.ref, {"action_id": ctx.action_id, "attempt_id": ctx.attempt_id}, "limit_exhausted",
                error=EngineError("LIMIT_EXCEEDED", "Controlled source fault", details={"kind": "tool_calls"} if fault == "lineage_limit" else {},
                                  observed_effect_state="unknown", commit_state="unknown" if fault == "unknown_commit" else "not_applicable"),
                process={"dispatched": True, "termination_reason": "stream_limit", "cleanup": {"complete": fault != "cleanup_incomplete", "unconfirmed_resources": ["worker"] if fault == "cleanup_incomplete" else []}},
                persistence={"required": True, "operation_id": plan.operation_id, "commit_state": "unknown" if fault == "unknown_commit" else "not_committed"})
    binding.executor = SourceFault()
    if fault == "missing_outcome":
        real = binding.recorder
        class FailOutcome:
            async def append(self, ctx, event):
                if event.kind == "tool.outcome":
                    return Err(EngineError("RECORD_FAILURE", "Controlled tool outcome failure", commit_state="not_committed"))
                return await real.append(ctx, event)
            async def status(self, *args):
                return await real.status(*args)
        binding.recorder = FailOutcome()
    runtime = Runtime()
    result = await runtime.execute((await runtime.admit(definition, "task", binding, context)).unwrap())
    assert result.status != "succeeded" and attempts == 1, result.error
    assert turns == (2 if fault == "repeat_request" else 1)
    if fault == "repeat_request":
        assert result.error.code == "tool.failed_request_replay"
        events = [(item.get("event", item)) for item in (await storage.activity.query(context)).unwrap().events]
        assert sum(event["kind"] == "tool.intent" for event in events) == 1
        assert any(event["kind"] == "tool.rejected" for event in events)
    assert result.recording_status == ("incomplete" if fault == "missing_outcome" else "complete")
    assert result.output_ref is None and result.terminal_event_receipt is not None
    if fault == "cleanup_incomplete":
        assert result.cleanup.complete is False and "worker" in result.cleanup.unconfirmed_resources
    if fault == "unknown_commit":
        assert result.unfinished_actions[0]["phase"] == "tool_publication_commit"
        assert result.unfinished_actions[0]["operation_id"] is not None
        assert result.terminal_state["unfinished_actions"] == result.unfinished_actions
    await storage.close()


@pytest.mark.asyncio
async def test_large_real_document_read_keeps_citation_locator_and_text_digest(tmp_path):
    from ebd.agent.recording import RecordedToolAction
    from ebd.connections.engine import ToolPlanFactory
    from ebd.contracts import SnapshotProposal, ToolRef, ToolRequest, canonical_json, digest_bytes, digest_json
    from ebd.storage._ranges import line_spans
    from ebd.toolset import ToolCatalog, ToolExecutor
    storage, binding, context, _ = await setup(tmp_path, lambda req: pytest.fail("Document reading cannot call a model"))
    context.grants.grants += [Grant("snapshot.commit", context.scope), Grant("snapshot.read", context.scope),
                             Grant("tool.execute", object_ids=frozenset({"document.read"}))]
    text = ("A saved source line for citation verification.\n" * 200).encode()
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text), "lines": line_spans(text), "pages": None}
    receipt = (await storage.snapshots.commit(context, "fixture-source", context.scope,
                  SnapshotProposal(text, text, canonical_json(index), {"url": "https://example.org/fixture.txt"}))).unwrap()
    binding.catalog = ToolCatalog()
    binding.executor = ToolExecutor(binding.catalog)
    binding.storage_plan_factory = ToolPlanFactory(storage, context.scope)
    interval = {"kind": "lines", "start": 1, "end_exclusive": 201}
    request = ToolRequest(ToolRef("document.read"), {"snapshot_ref": receipt.snapshot_ref.to_dict(), "range": interval},
                          "native-read", model_action_id="model-source", model_attempt_id="model-attempt")
    try:
        result = await RecordedToolAction().run(request, binding, context, allowed_tools=[ToolRef("document.read")])
        assert result.status == "succeeded" and result.recording["status"] == "complete", result.error
        assert result.process["dispatched"] is True and result.process["cleanup"]["complete"] is True
        events = [item.get("event", item) for item in (await storage.activity.query(context)).unwrap().events]
        outcome = next(event for event in events if event["kind"] == "tool.outcome")
        descriptor = outcome["payload"]["result_descriptor"]
        assert descriptor["snapshot_ref"] == receipt.snapshot_ref.to_dict()
        assert descriptor["requested_range"] == descriptor["returned_range"] == interval
        assert descriptor["text_sha256"] == digest_bytes(result.result["text"].encode())
        assert descriptor["normalization_version"] == result.result["normalization_version"]
        assert descriptor["spans_count"] == 200 and descriptor["spans_digest"] == digest_json(result.result["spans"])
        assert "spans" not in descriptor and len(canonical_json(outcome)) < 65536
    finally:
        assert (await binding.executor.close()).complete
        await storage.close()


@pytest.mark.asyncio
async def test_admission_capacity_expiry_and_retention_do_not_replenish_consumed_budget(tmp_path):
    import time
    calls = 0
    def handler(req):
        nonlocal calls
        calls += 1
        return final_response()
    storage, binding, context, definition = await setup(tmp_path, handler)
    runtime = Runtime(max_live_admissions=1, max_admission_records=2)
    expired = (await runtime.admit(definition, "task", binding, context)).unwrap()
    denied = await runtime.admit(definition, "task", binding, context)
    assert denied.error.details["kind"] == "live_admissions" and calls == 0
    expired.context._monotonic_deadline = time.monotonic() - 1
    first = (await runtime.admit(definition, "task", binding, context)).unwrap()
    assert expired.state == "expired" and context.ledger.remaining("model_calls") == 31
    assert (await runtime.execute(first)).status == "succeeded"
    second_storage, second_binding, second_context, second_definition = await setup(tmp_path / "second", handler)
    second_context.ledger = context.ledger
    second = (await runtime.admit(second_definition, "task", second_binding, second_context)).unwrap()
    assert (await runtime.execute(second)).status == "succeeded"
    third_storage, third_binding, third_context, third_definition = await setup(tmp_path / "third", handler)
    third_context.ledger = context.ledger
    third = (await runtime.admit(third_definition, "task", third_binding, third_context)).unwrap()
    assert (await runtime.execute(third)).status == "succeeded"
    assert calls == 3 and context.ledger.remaining("model_calls") == 29
    assert (await runtime.admission_status(context, first.admission_id)).unwrap()["state"] == "unknown"
    latest = (await runtime.admission_status(third_context, third.admission_id)).unwrap()
    assert latest["state"] == "terminal" and latest["terminal_event_receipt"] is not None
    assert len(runtime._admissions) == 2
    await storage.close()
    await second_storage.close()
    await third_storage.close()
