"""Real scoped Storage proves hook audit persistence and recording denial."""
import pytest

from deepresearch.engine.contracts import (
    BudgetLedger, EngineError, ExecutionContext, ExecutionEvent, Grant, GrantSet,
    ScopeRef, deadline_after, digest_json, new_id,
)
from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDecision, HookDispatcher, HookEvent
from deepresearch.engine.storage import StorageSession

HOOK_KINDS = frozenset({"workflow.hook.observed", "workflow.hook.decision", "workflow.hook.failed"})


def host_context(session):
    scope = ScopeRef("run", "hook-run")
    return ExecutionContext(
        "hook-run", "hook-run", "hook-correlation", "host-action",
        principal="hook-host", agent_id="host", deadline=deadline_after(120),
        store_id=session.store_id, scope=scope, ledger=BudgetLedger(),
        grants=GrantSet([
            Grant("admin.provision", scope),
            Grant("events.append", scope, producer="workflow", event_kinds=HOOK_KINDS),
            Grant("events.read", scope),
        ], "hook-host"),
    )


async def test_hook_audit_survives_real_storage_close_reopen_with_replay_facts(tmp_path):
    root = tmp_path / "hook-store"
    session = (await StorageSession.open(root)).unwrap()
    context = host_context(session)
    registry = ExtensionRegistry()
    config = {"rank_limit": 2}

    async def rank(event, ids):
        return HookDecision(("c", "a"))

    async def broken(event):
        raise RuntimeError("private-test-value")

    async def healthy(event):
        assert event.payload["candidate_count"] == 3

    registry.register(ExtensionSpec("ranker", "r4", ("discovery.select",), mode="control", config=config), rank)
    registry.register(ExtensionSpec("a-broken", "r2", ("discovery.select",)), broken)
    registry.register(ExtensionSpec("b-healthy", "r1", ("discovery.select",)), healthy)
    receipts = []

    async def record(kind, payload):
        receipt = (await session.recorder.append(
            context, ExecutionEvent(new_id("hook_"), kind, "workflow", context, payload),
        )).unwrap()
        receipts.append(receipt)
        return receipt

    try:
        (await session.provision_run(context, {"run_id": context.run_id, "context_kind": "agent", "agent_id": "host"})).unwrap()
        dispatcher = HookDispatcher(registry, record)
        event = HookEvent("hook-run", "discovery-node", "discovery.select", {"candidate_count": 3})
        await dispatcher.observe(event)
        selected = await dispatcher.select(event, ["a", "b", "c"])
        assert selected == ["c", "a"] and len(receipts) == 3
    finally:
        await session.close()

    reopened = (await StorageSession.open(root)).unwrap()
    try:
        fresh = host_context(reopened)
        page = (await reopened.activity.query(fresh, {"run_id": "hook-run"}, None, 100)).unwrap()
        events = [row["event"] for row in page.events if row["event"]["kind"] in HOOK_KINDS]
        assert [row["kind"] for row in events] == ["workflow.hook.failed", "workflow.hook.observed", "workflow.hook.decision"]
        assert events[0]["payload"]["failure"] == "error"
        decision = events[-1]["payload"]
        assert decision["extension_id"] == "ranker" and decision["revision"] == "r4"
        assert decision["config_digest"] == digest_json(config)
        assert decision["payload_digest"] == event.payload_digest
        assert decision["original_candidate_ids"] == decision["candidate_ids"] == ["a", "b", "c"]
        assert decision["keep_ids"] == selected
        assert "config" not in decision and "payload" not in decision
        assert "private-test-value" not in str(events)
        assert [receipt.event_id for receipt in receipts] == [row["event_id"] for row in events]
    finally:
        await reopened.close()


async def test_real_recording_authority_failure_is_not_isolated_as_observer_failure(tmp_path):
    session = (await StorageSession.open(tmp_path / "hook-store")).unwrap()
    context = host_context(session)
    registry, called = ExtensionRegistry(), []

    async def first(event):
        called.append("first")
        raise RuntimeError("private-test-value")

    async def later(event):
        called.append("later")

    registry.register(ExtensionSpec("a-first", "r1", ("node.failed",)), first)
    registry.register(ExtensionSpec("b-later", "r1", ("node.failed",)), later)

    async def denied_record(kind, payload):
        return await session.recorder.append(context, ExecutionEvent(new_id("hook_"), kind, "workflow", context, payload))

    try:
        (await session.provision_run(context, {"run_id": context.run_id, "context_kind": "agent", "agent_id": "host"})).unwrap()
        context.grants.revoked = True
        with pytest.raises(EngineError) as caught:
            await HookDispatcher(registry, denied_record).observe(HookEvent("hook-run", "node-a", "node.failed"))
        assert caught.value.code == "ACCESS_DENIED"
        assert called == ["first"]
    finally:
        await session.close()
