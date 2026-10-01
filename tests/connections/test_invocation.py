"""Child boundaries use real Store/Runtime; controlled HTTP isolates the policy cases."""
import asyncio
import json
import time

import httpx
import pytest

from ebd.connections import AgentRef, Engine, EngineSettings, InvocationRule, RunOptions
from ebd.contracts import AgentDefinition, Err, Grant, GrantSet, Ok, ToolRef
from ebd.providers import ProviderConfig, ProviderFactory


async def bound_parent(tmp_path, monkeypatch, *, rule=None, child_tools=(), artifact=False, handler=None):
    calls = []
    def default_handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "child-response", "model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Exact child\n"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}})
    native_open = ProviderFactory.open
    async def controlled_open(config, context=None):
        return await native_open(config, context, transport=httpx.MockTransport(handler or default_handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", profiles={"deepseek": ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-secret", profile_name="deepseek")})
    engine = (await Engine.open(settings)).unwrap()
    child = AgentDefinition("child", "Return the child candidate", allowed_tools=list(child_tools), output_contract={"delivery": "artifact"} if artifact else {})
    child_registered = engine.register_agent(child).unwrap()
    parent = AgentDefinition("parent", "Parent", allowed_tools=[])
    edge = rule or InvocationRule(AgentRef("child"), allow_export=artifact)
    parent_registered = engine.register_agent(parent, (edge,)).unwrap()
    session = (await engine.open_agent_session(parent_registered, RunOptions(timeout_seconds=30))).unwrap()
    return engine, session, child_registered, calls


@pytest.mark.asyncio
async def test_child_links_both_parent_cause_ids_and_shared_budget(tmp_path, monkeypatch):
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch)
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "succeeded" and outcome.recording_status == "complete"
        assert outcome.intent_receipt and outcome.outcome_receipt and len(calls) == 1
        execution = outcome.child_result.execution
        assert execution["parent_run_id"] == parent.context.run_id
        assert execution["parent_action_id"] == outcome.execution["action_id"]
        assert execution["parent_attempt_id"] == outcome.execution["attempt_id"]
        assert parent.context.ledger.used["model_calls"] == 1
        assert parent.context.ledger.used["descendants"] == 1
        events = (await engine.storage.activity.query(parent.context)).unwrap().events
        kinds = [event.get("event", event)["kind"] for event in events]
        assert kinds.index("invocation.intent") < kinds.index("invocation.outcome")
        assert outcome.child_result.terminal_event_receipt.recorded_seq < outcome.outcome_receipt.recorded_seq
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_artifact_export_commits_before_invocation_outcome(tmp_path, monkeypatch):
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, artifact=True)
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "succeeded" and outcome.recording_status == "complete"
        assert outcome.output_ref != outcome.child_result.output_ref
        assert outcome.export_receipt.event_receipt.recorded_seq < outcome.outcome_receipt.recorded_seq
        reader = (await engine.storage.artifacts.open(parent.context, outcome.output_ref)).unwrap()
        assert (await reader.read(parent.context)).unwrap().bytes == b"Exact child\n"
        await reader.aclose(parent.context)
        assert isinstance(await engine.storage.artifacts.open(parent.context, outcome.child_result.output_ref), Err)
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_child_cannot_exceed_parent_tool_delegation(tmp_path, monkeypatch):
    edge = InvocationRule(AgentRef("child"), allowed_tools=())
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, rule=edge, child_tools=(ToolRef("web.search"),))
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "failed" and outcome.error.code == "ACCESS_DENIED"
        assert calls == [] and not outcome.dispatched
        assert outcome.recording_status == "complete"
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_public_strategy_session_binds_without_dispatch_and_closes_authority(tmp_path, monkeypatch):
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch)
    try:
        assert calls == []
        parent.context.assert_active()
        assert parent.binding.invoker is not None and parent.context.agent_id == "parent"
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "succeeded" and len(calls) == 1
        assert (await parent.close()).complete
        denied = await parent.binding.invoker.invoke(parent.context, child.ref, "second task")
        assert denied.status == "failed" and denied.dispatched is False and len(calls) == 1
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_zero_edge_model_allowance_prevents_child_dispatch(tmp_path, monkeypatch):
    edge = InvocationRule(AgentRef("child"), limits={"model_calls": 0})
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, rule=edge)
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "limit_exhausted" and calls == []
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_export_denial_preserves_child_terminal_facts(tmp_path, monkeypatch):
    edge = InvocationRule(AgentRef("child"), allow_export=False)
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, rule=edge, artifact=True)
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert len(calls) == 1 and outcome.child_result.status == "succeeded"
        assert outcome.status == "failed" and outcome.error.code == "ACCESS_DENIED"
        assert outcome.output_ref is None
        events = (await engine.storage.activity.query(parent.context)).unwrap().events
        terminal = next(event.get("event", event) for event in events if event.get("event", event)["kind"] == "invocation.outcome")
        assert terminal["payload"]["child_terminal_receipt"]["event_id"] == outcome.child_result.terminal_event_receipt.event_id
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_parent_cancellation_propagates_to_running_child(tmp_path, monkeypatch):
    entered = asyncio.Event()
    async def handler(request):
        entered.set()
        await asyncio.sleep(20)
        raise AssertionError("Cancelled child cannot return a later candidate")
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, handler=handler)
    try:
        running = asyncio.create_task(parent.binding.invoker.invoke(parent.context, child.ref, "task"))
        await entered.wait()
        parent.context.cancellation.set()
        outcome = await asyncio.wait_for(running, 3)
        assert outcome.status == "cancelled" and outcome.child_result.status == "cancelled"
        assert outcome.child_result.terminal_event_receipt and outcome.outcome_receipt
        assert outcome.recording_status == "complete"
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_expired_parent_starts_no_child(tmp_path, monkeypatch):
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch)
    try:
        parent.context._monotonic_deadline = time.monotonic() - 1
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "timed_out" and calls == [] and not outcome.dispatched
        assert "descendants" not in parent.context.ledger.used
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_cycle_rejection_precedes_child_admission(tmp_path, monkeypatch):
    edge = InvocationRule(AgentRef("parent"))
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, rule=edge)
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, AgentRef("parent"), "task")
        assert outcome.error.code == "INVOCATION_CYCLE" and calls == []
        assert not outcome.dispatched and outcome.recording_status == "complete"
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_lost_invocation_intent_ack_is_reconciled_before_one_child(tmp_path, monkeypatch):
    from ebd.contracts import EngineError
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch)
    actual = engine.storage.recorder
    intents = 0
    class LoseIntent:
        async def append(self, ctx, event):
            nonlocal intents
            result = await actual.append(ctx, event)
            if event.kind == "invocation.intent":
                intents += 1
                assert isinstance(result, Ok)
                return Err(EngineError("LOST_ACK", "Controlled invocation intent reply loss", commit_state="unknown"))
            return result
        async def status(self, *args):
            return await actual.status(*args)
    engine.storage.recorder = LoseIntent()
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.status == "succeeded" and outcome.recording_status == "complete"
        assert len(calls) == 1 and intents == 1
    finally:
        await parent.close()
        await engine.close()


@pytest.mark.asyncio
async def test_parent_revocation_after_child_success_prevents_result_export(tmp_path, monkeypatch):
    holder = {}
    def handler(request):
        holder["parent"].context.grants.revoked = True
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "child complete"}}]})
    engine, parent, child, calls = await bound_parent(tmp_path, monkeypatch, artifact=True, handler=handler)
    holder["parent"] = parent
    try:
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, "task")
        assert outcome.child_result.status == "succeeded"
        assert outcome.export_receipt is None and outcome.output_ref is None
        assert outcome.error.code == "ACCESS_DENIED"
    finally:
        await parent.close()
        await engine.close()
