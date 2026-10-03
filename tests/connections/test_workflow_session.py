"""Workflow authority and durability use real Storage and document workers."""
import asyncio
import dataclasses
import json
import time

import httpx
import pytest

from deepresearch.engine.connections import (
    AgentRef, BoundSession, Engine, EngineSettings, EvidenceBinding,
    InvocationOptions, InvocationRule, RunOptions, SnapshotReadRequest,
    WORKFLOW_EVENTS, WORKFLOW_EVENT_MAX_BYTES,
)
from deepresearch.engine.contracts import (
    AgentDefinition, ArtifactMetadata, EngineError, Err, Ok, RunRef, ScopeRef,
    SnapshotProposal, SnapshotRef, StateMutation, ToolRef, canonical_json, digest_bytes,
)
from deepresearch.engine.providers import ProviderConfig, ProviderFactory


READ = ToolRef("document.read")
INTERVAL = {"kind": "lines", "start": 1, "end_exclusive": 3}


@pytest.fixture
async def engine(tmp_path):
    instance = (await Engine.open(EngineSettings(
        workspace=tmp_path, storage_root=tmp_path / "store"))).unwrap()
    try:
        yield instance
    finally:
        await instance.close()


async def session_for(engine, *, tools=(READ,), rules=(), limits=None):
    return (await engine.open_workflow_session(tools=tools, invocation_rules=rules,
        options=RunOptions(timeout_seconds=30, limits=limits or {}))).unwrap()


async def seed(session):
    text = b"selected\nprivate\n"
    index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text),
        "lines": [{"line": 1, "start_byte": 0, "end_byte": 8},
                  {"line": 2, "start_byte": 9, "end_byte": 16}], "pages": None}
    receipt = (await session.binding.storage.snapshots.commit(session.context,
        "source", session.context.scope, SnapshotProposal(text, text,
        canonical_json(index), {"url": "https://example.org/workflow-source"}))).unwrap()
    return {"snapshot_ref": receipt.snapshot_ref.to_dict(), "range": dict(INTERVAL)}


async def events(engine, session):
    page = (await engine.query_run_events(RunRef(engine.storage.store_id,
        session.context.run_id), limit=100)).unwrap()
    return [row["event"] for row in page["events"]]


async def test_model_free_authority_and_workflow_kind_at_provision(engine, monkeypatch):
    def no_profile(*args):
        pytest.fail("Workflow binding must not resolve a profile or credentials")
    monkeypatch.setattr(engine.profiles, "resolve", no_profile)
    observed = []
    native = engine.storage.provision_run
    async def inspect_provision(context, descriptor):
        observed.append((context.context_kind, descriptor["context_kind"], descriptor["definition_ref"]))
        return await native(context, descriptor)
    monkeypatch.setattr(engine.storage, "provision_run", inspect_provision)
    session = await session_for(engine, tools=(READ, ToolRef("web.fetch")))
    assert observed == [("workflow", "workflow", None)]
    assert session.definition is None
    assert session.context.agent_id is None and session.context.definition_ref is None
    assert session.context.context_kind == "workflow"
    assert session.binding.provider_config is None and session.binding.provider_factory is None
    assert session.binding.invoker.definition is None
    session.context.authorize("network.fetch")
    assert not any(grant.operation == "network.search" for grant in session.context.grants.grants)
    with pytest.raises(EngineError, match="outside the bound grants"):
        session.context.authorize("model.generate", object_id="deepseek-flash")
    with pytest.raises(EngineError):
        session.context.authorize("events.append", session.context.scope,
            producer="runtime", event_kind="agent.finished")
    (await session.binding.storage.state.commit(session.context, "phase", [
        StateMutation(session.context.scope, "phase", "put", 0, {"node": "fetch"})])).unwrap()
    assert (await session.binding.storage.state.get(session.context,
        session.context.scope, "phase")).unwrap().value == {"node": "fetch"}
    foreign = ScopeRef("run", "unselected")
    assert isinstance(await session.binding.storage.state.get(session.context, foreign, "phase"), Err)
    assert isinstance(await session.binding.storage.artifacts.put(session.context,
        "foreign", foreign, b"no", ArtifactMetadata("text/plain")), Err)
    catalog = (await engine.list_runs({"context_kind": "workflow"})).unwrap()["runs"]
    assert [row["run_id"] for row in catalog] == [session.context.run_id]
    binding = next(row for row in await events(engine, session) if row["kind"] == "binding.resolved")
    assert binding["payload"]["workflow_policy"]["allowed_tools"] == [READ.to_dict(), ToolRef("web.fetch").to_dict()]
    assert all(not row["kind"].startswith("agent.") for row in await events(engine, session))


async def test_real_same_scope_worker_and_unique_calls_exhaust_shared_budget(engine):
    session = await session_for(engine, limits={"tool_calls": 2})
    ledger = session.context.ledger
    args = await seed(session)
    first = await engine.run_workflow_tool(session, READ, args)
    second = await engine.run_workflow_tool(session, READ, args)
    third = await engine.run_workflow_tool(session, READ, args)
    assert first.status == second.status == "succeeded", (first.error, second.error)
    assert first.result["text"] == second.result["text"] == "selected\nprivate\n"
    assert first.process["dispatched"] and first.process["cleanup"]["complete"]
    assert second.process["dispatched"] and second.process["cleanup"]["complete"]
    assert third.status == "limit_exhausted" and not third.invocation["dispatched"]
    assert session.context.ledger is ledger and ledger.used["tool_calls"] == 2
    assert len({r.invocation["action_id"] for r in (first, second, third)}) == 3
    assert first.invocation["attempt_id"] != second.invocation["attempt_id"]
    for result in (first, second, third):
        assert result.invocation["run_id"] == session.context.run_id
        assert result.invocation["context_kind"] == "workflow"
        assert result.recording["status"] == "complete"
    rows = await events(engine, session)
    tool_rows = [row for row in rows if row["kind"].startswith("tool.")]
    assert [row["kind"] for row in tool_rows] == [
        "tool.intent", "tool.outcome", "tool.intent", "tool.outcome", "tool.rejected"]
    assert all(row["context"]["scope"] == session.context.scope.to_dict() for row in tool_rows)
    for row in tool_rows:
        assert all(row["payload"][key] is None for key in
            ("provider_call_id", "model_action_id", "model_attempt_id"))
    assert (await engine.list_runs()).unwrap()["runs"][0]["run_id"] == session.context.run_id
    assert len((await engine.list_runs()).unwrap()["runs"]) == 1


async def test_unselected_tool_and_changed_revision_never_dispatch(engine):
    session = await session_for(engine)
    args = await seed(session)
    denied = await engine.run_workflow_tool(session, ToolRef("web.fetch"), {"url": "https://example.org"})
    revision = await engine.run_workflow_tool(session, ToolRef("document.read", 2), args)
    assert all(r.error.code == "tool.unauthorized" and not r.invocation["dispatched"]
               and r.recording["status"] == "complete" for r in (denied, revision))
    assert session.context.ledger.used.get("tool_calls", 0) == 0


@pytest.mark.parametrize("case", ["foreign", "copy", "replaced_binding", "closed", "expired", "cancelled", "revoked"])
async def test_nonlive_or_foreign_session_has_no_tool_or_event_authority(engine, tmp_path, case):
    session = await session_for(engine)
    target = engine
    other = None
    if case == "foreign":
        other = (await Engine.open(EngineSettings(workspace=tmp_path,
            storage_root=tmp_path / "other"))).unwrap()
        target = other
    elif case == "copy":
        session = BoundSession(session.context, session.binding, None)
    elif case == "replaced_binding":
        session = dataclasses.replace(session, binding=dataclasses.replace(session.binding))
    elif case == "closed":
        await session.close()
    elif case == "expired":
        session.context._monotonic_deadline = time.monotonic() - 1
    elif case == "cancelled":
        session.context.cancellation.set()
    elif case == "revoked":
        session.context.grants.revoked = True
    expected = {"expired": "DEADLINE_EXCEEDED", "cancelled": "CANCELLED"}.get(case, "ACCESS_DENIED")
    try:
        result = await target.run_workflow_tool(session, READ, {})
        event = await target.emit_workflow_event(session, "workflow.node.started", {})
        assert result.error.code == expected and not result.invocation["dispatched"]
        assert isinstance(event, Err) and event.error.code == expected
        assert session.context.ledger.used.get("tool_calls", 0) == 0
    finally:
        if other:
            await other.close()


@pytest.mark.parametrize("case", ["expired", "cancelled"])
async def test_cleanup_records_terminal_without_restoring_business_authority(engine, case):
    session = await session_for(engine)
    if case == "expired":
        session.context._monotonic_deadline = time.monotonic() - 1
    else:
        session.context.cancellation.set()
    assert isinstance(await engine.emit_workflow_event(session, "workflow.finished", {}), Err)
    assert isinstance(await engine.emit_workflow_event(session, "workflow.node.started", {}, cleanup=True), Err)
    terminal = (await engine.emit_workflow_event(session, "workflow.finished",
        {"status": "timed_out" if case == "expired" else "cancelled"}, cleanup=True)).unwrap()
    result = await engine.run_workflow_tool(session, READ, {})
    assert not result.invocation["dispatched"]
    assert session.context.ledger.used.get("tool_calls", 0) == 0
    assert (await engine.describe_run(RunRef(engine.storage.store_id,
        session.context.run_id))).unwrap()["terminal_event"]["receipt"]["event_id"] == terminal.event_id
    await session.close()
    assert isinstance(await engine.emit_workflow_event(session, "workflow.finished", {}, cleanup=True), Err)


@pytest.mark.parametrize("kind,payload,cleanup", [
    ("workflow.unknown", {}, False), ("agent.finished", {}, False),
    ("workflow.measurement", [], False), ("workflow.measurement", {"bad": float("nan")}, False),
    ("workflow.measurement", {"large": "x" * WORKFLOW_EVENT_MAX_BYTES}, False),
    ("workflow.measurement", {"value": 1}, "yes"),
])
async def test_invalid_event_facts_are_rejected_before_storage_admission(engine, kind, payload, cleanup):
    session = await session_for(engine)
    writes = session.context.ledger.used["storage_writes"]
    result = await engine.emit_workflow_event(session, kind, payload, cleanup=cleanup)
    assert isinstance(result, Err) and result.error.code == "INVALID_DATA"
    assert session.context.ledger.used["storage_writes"] == writes


async def test_committed_workflow_events_lost_ack_and_terminal_reopen(engine, monkeypatch):
    session = await session_for(engine)
    settings = engine.settings
    run_ref = RunRef(engine.storage.store_id, session.context.run_id)
    actual = engine.storage.recorder
    appended = []
    class LoseReply:
        async def append(self, context, event):
            result = await actual.append(context, event)
            if event.producer == "workflow":
                assert isinstance(result, Ok)
                appended.append(event.event_id)
                return Err(EngineError("LOST_ACK", "Controlled lost reply", commit_state="unknown"))
            return result
        async def status(self, *args):
            return await actual.status(*args)
    monkeypatch.setattr(engine.storage, "recorder", LoseReply())
    receipts = []
    for kind in sorted(WORKFLOW_EVENTS - {"workflow.finished"}):
        receipts.append((await engine.emit_workflow_event(session, kind, {"node_id": "fetch"})).unwrap())
    assert (await engine.describe_run(run_ref)).unwrap()["terminal_event"] is None
    terminal = (await engine.emit_workflow_event(session, "workflow.finished", {"status": "succeeded"})).unwrap()
    receipts.append(terminal)
    assert len(appended) == len(receipts) == len(WORKFLOW_EVENTS)
    assert appended == [receipt.event_id for receipt in receipts]
    assert session.context.ledger.used["storage_writes"] == len(receipts) + 1
    rows = await events(engine, session)
    assert len([row for row in rows if row["producer"] == "workflow"]) == len(receipts)
    assert not any(row["kind"].startswith("agent.") for row in rows)
    await session.close()
    assert (await engine.close()).complete
    reopened = (await Engine.open(settings)).unwrap()
    try:
        described = (await reopened.describe_run(run_ref)).unwrap()
        assert described["context_kind"] == "workflow" and described["definition_ref"] is None
        assert described["terminal_event"]["event"]["kind"] == "workflow.finished"
        assert described["terminal_event"]["receipt"]["event_id"] == terminal.event_id
        assert described["terminal_event"]["event"]["payload"]["status"] == "succeeded"
        denied = await reopened.run_workflow_tool(session, READ, {})
        assert denied.error.code == "ACCESS_DENIED" and not denied.invocation["dispatched"]
    finally:
        await reopened.close()


async def test_unknown_ack_retains_failure_and_does_not_redeliver(engine, monkeypatch):
    session = await session_for(engine)
    actual = engine.storage.recorder
    count = 0
    class UncommittedReply:
        async def append(self, context, event):
            nonlocal count
            count += 1
            return Err(EngineError("LOST_ACK", "Unknown commit", commit_state="unknown"))
        async def status(self, *args):
            return await actual.status(*args)
    monkeypatch.setattr(engine.storage, "recorder", UncommittedReply())
    result = await engine.emit_workflow_event(session, "workflow.measurement", {"count": 1})
    assert isinstance(result, Err) and result.error.commit_state == "unknown" and count == 1
    assert not any(row["producer"] == "workflow" for row in await events(engine, session))


@pytest.mark.parametrize("case", ["missing_destination", "widened_edge", "widened_child", "duplicate_tool",
    "duplicate_edge", "invalid_timeout", "invalid_limits", "untyped_options"])
async def test_invalid_policy_fails_before_workflow_provision(engine, case):
    child = engine.register_agent(AgentDefinition("child", "Write.",
        allowed_tools=[READ] if case == "widened_child" else [])).unwrap()
    edge = InvocationRule(child.ref)
    kwargs = {"tools": (READ,), "invocation_rules": (edge,), "options": RunOptions(timeout_seconds=30)}
    if case == "missing_destination":
        kwargs["invocation_rules"] = (InvocationRule(AgentRef("missing")),)
    elif case == "widened_edge":
        kwargs["invocation_rules"] = (InvocationRule(child.ref, allowed_tools=("web.fetch",)),)
    elif case == "duplicate_tool":
        kwargs["tools"] = (READ, READ)
    elif case == "duplicate_edge":
        kwargs["invocation_rules"] = (edge, edge)
    elif case == "invalid_timeout":
        kwargs["options"] = RunOptions(timeout_seconds=float("inf"))
    elif case == "invalid_limits":
        kwargs["options"] = RunOptions(limits={"tool_calls": -1})
    elif case == "untyped_options":
        kwargs["options"] = {"timeout_seconds": 30}
    result = await engine.open_workflow_session(**kwargs)
    assert isinstance(result, Err)
    assert (await engine.list_runs()).unwrap()["runs"] == []


async def child_setup(engine, monkeypatch, *, handler=None):
    calls = []
    def response(request):
        calls.append(json.loads(request.content))
        if handler:
            return handler(request, len(calls))
        return httpx.Response(200, json={"id": "writer-response", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "written"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}})
    native = ProviderFactory.open
    async def controlled(config, context=None):
        return await native(config, context, transport=httpx.MockTransport(response))
    monkeypatch.setattr(ProviderFactory, "open", controlled)
    engine.settings.profiles["deepseek"] = ProviderConfig("deepseek", "deepseek-flash",
        "https://provider.invalid", "test-key")
    return calls


async def test_child_writer_uses_explicit_edge_and_shared_model_budget(engine, monkeypatch):
    calls = await child_setup(engine, monkeypatch)
    child = engine.register_agent(AgentDefinition("writer", "Write.")).unwrap()
    other = engine.register_agent(AgentDefinition("unselected", "Write.")).unwrap()
    session = await session_for(engine, tools=(), rules=(InvocationRule(child.ref),), limits={"model_calls": 1})
    denied = await session.binding.invoker.invoke(session.context, other.ref, "task")
    assert denied.error.code == "ACCESS_DENIED" and not denied.dispatched and calls == []
    first = await session.binding.invoker.invoke(session.context, child.ref, "task")
    assert first.status == "succeeded" and first.output == "written" and first.recording_status == "complete"
    assert first.child_result.execution["context_kind"] == "agent"
    assert first.child_result.execution["parent_run_id"] == session.context.run_id
    assert first.child_result.execution["root_run_id"] == session.context.run_id
    assert first.child_result.execution["parent_action_id"] == first.execution["action_id"]
    assert first.child_result.execution["parent_attempt_id"] == first.execution["attempt_id"]
    assert first.child_result.execution["ancestry"] == []
    assert session.context.ledger.used["model_calls"] == 1
    second = await session.binding.invoker.invoke(session.context, child.ref, "task")
    assert second.status == "limit_exhausted" and len(calls) == 1
    assert session.context.ledger.used["model_calls"] == 1
    assert not any(row["kind"].startswith("agent.") for row in await events(engine, session))


async def test_child_tool_and_evidence_attenuation_charge_same_lineage(engine, monkeypatch):
    source = None
    def tool_response(request, count):
        if count == 1:
            return httpx.Response(200, json={"id": "read", "model": "deepseek-flash", "choices": [{
                "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                    "tool_calls": [{"id": "native-read", "type": "function", "function": {
                        "name": json.loads(request.content)["tools"][0]["function"]["name"],
                        "arguments": json.dumps(source)}}]}}]})
        return httpx.Response(200, json={"id": "written", "model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {"role": "assistant", "content": "selected evidence"}}]})
    calls = await child_setup(engine, monkeypatch, handler=tool_response)
    writer = engine.register_agent(AgentDefinition("writer", "Read selected evidence.", allowed_tools=[READ])).unwrap()
    session = await session_for(engine, rules=(InvocationRule(writer.ref,
        allowed_tools=(READ.name,), allow_evidence=True),), limits={"tool_calls": 1})
    args = await seed(session)
    source = {**args, "range": {"kind": "lines", "start": 1, "end_exclusive": 2}, "max_text_bytes": 32}
    evidence = EvidenceBinding(read_objects=(SnapshotReadRequest(SnapshotRef(**args["snapshot_ref"]),
        source["range"], 32),))
    native = engine.runtime.admit
    async def inspect_child(definition, task, binding, context):
        if context.agent_id == "writer":
            assert context.ledger.ledger_id == session.context.ledger.ledger_id
            assert context.remaining_seconds() <= session.context.remaining_seconds() + .05
            assert context.ancestry == ()
            context.authorize("tool.execute", object_id=READ.name)
            with pytest.raises(EngineError):
                context.authorize("tool.execute", object_id="web.fetch")
            with pytest.raises(EngineError):
                context.authorize("agent.invoke", object_id="writer")
            assert isinstance(await binding.storage.snapshots.read(context,
                SnapshotRef(**args["snapshot_ref"]), INTERVAL, 32), Err)
            assert isinstance(await binding.storage.state.commit(context, "widened-write", [
                StateMutation(session.context.scope, "private", "put", 0, {})]), Err)
            assert (await binding.storage.snapshots.read(context, SnapshotRef(**args["snapshot_ref"]),
                source["range"], 32)).unwrap().text == "selected"
        return await native(definition, task, binding, context)
    monkeypatch.setattr(engine.runtime, "admit", inspect_child)
    outcome = await session.binding.invoker.invoke(session.context, writer.ref, "read", InvocationOptions(evidence=evidence))
    assert outcome.status == "succeeded" and outcome.recording_status == "complete" and len(calls) == 2, (outcome.error, outcome.child_result.error, len(calls))
    assert session.context.ledger.used["tool_calls"] == 1
    assert calls[1]["messages"][-1]["role"] == "tool"
    assert "selected" in calls[1]["messages"][-1]["content"]
    exhausted = await engine.run_workflow_tool(session, READ, args)
    assert exhausted.status == "limit_exhausted" and not exhausted.invocation["dispatched"]


async def test_edge_denies_model_without_provider_dispatch(engine, monkeypatch):
    calls = await child_setup(engine, monkeypatch)
    writer = engine.register_agent(AgentDefinition("writer", "Write.")).unwrap()
    session = await session_for(engine, tools=(), rules=(InvocationRule(writer.ref, allow_model=False),))
    outcome = await session.binding.invoker.invoke(session.context, writer.ref, "task")
    assert outcome.error.code == "ACCESS_DENIED" and not outcome.dispatched and calls == []
    assert session.context.ledger.used.get("model_calls", 0) == 0


async def test_recording_exhaustion_does_not_get_new_budget_or_dispatch(engine):
    session = await session_for(engine, limits={"storage_writes": 1})
    ledger = session.context.ledger
    for _ in range(2):
        denied = await engine.emit_workflow_event(session, "workflow.measurement", {"value": 1})
        assert isinstance(denied, Err) and denied.error.code == "LIMIT_EXCEEDED"
    result = await engine.run_workflow_tool(session, READ, {
        "snapshot_ref": {"schema_version": 1, "store_id": engine.storage.store_id, "snapshot_id": "unread"},
        "range": INTERVAL,
    })
    assert result.error.code == "LIMIT_EXCEEDED" and not result.invocation["dispatched"]
    assert result.recording["status"] == "incomplete"
    assert session.context.ledger is ledger and ledger.used["storage_writes"] == 1
    assert not engine.executor.runner._active


async def test_shutdown_cancels_tool_and_allows_workflow_terminal_cleanup(engine, monkeypatch):
    # A controlled blocked executor makes the cancellation boundary deterministic;
    # its intent, outcome, terminal and reopened inspection use real Storage.
    session = await session_for(engine)
    run_ref = RunRef(engine.storage.store_id, session.context.run_id)
    entered = asyncio.Event()
    async def blocked(definition, arguments, context, plan):
        plan.assert_recorded()
        assert context.ledger is session.context.ledger
        assert context.lease is session.context.lease
        assert context.cancellation is session.context.cancellation
        assert context.deadline == session.context.deadline
        assert context.scope == session.context.scope
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(engine.executor, "execute", blocked)
    terminal = None
    async def workflow():
        nonlocal terminal
        try:
            await engine.run_workflow_tool(session, READ, {
                "snapshot_ref": {"schema_version": 1, "store_id": engine.storage.store_id, "snapshot_id": "unread"},
                "range": INTERVAL,
            })
        except asyncio.CancelledError:
            terminal = (await engine.emit_workflow_event(session, "workflow.finished", {
                "status": "cancelled",
            }, cleanup=True)).unwrap()
            raise
    task = asyncio.create_task(workflow())
    await asyncio.wait_for(entered.wait(), 2)
    assert (await engine.close()).complete
    assert task.cancelled() and terminal is not None
    reopened = (await Engine.open(engine.settings)).unwrap()
    try:
        described = (await reopened.describe_run(run_ref)).unwrap()
        assert described["terminal_event"]["receipt"]["event_id"] == terminal.event_id
        page = (await reopened.query_run_events(run_ref)).unwrap()
        outcome = next(row["event"] for row in page["events"] if row["event"]["kind"] == "tool.outcome")
        assert outcome["payload"]["status"] == "cancelled"
    finally:
        await reopened.close()


async def test_workflow_policy_and_options_are_detached_from_caller_mutation(engine, monkeypatch):
    calls = await child_setup(engine, monkeypatch)
    writer = engine.register_agent(AgentDefinition("writer", "Write.")).unwrap()
    edge_limits = {"model_calls": 1}
    metadata = {"method": "original"}
    options = RunOptions(timeout_seconds=30, limits={"model_calls": 1}, metadata=metadata)
    session = (await engine.open_workflow_session(tools=(),
        invocation_rules=(InvocationRule(writer.ref, limits=edge_limits),), options=options)).unwrap()
    edge_limits["model_calls"] = 0
    metadata["method"] = "mutated"
    options.limits["model_calls"] = 0
    assert session.context.metadata == {"method": "original"}
    assert session.context.ledger.limits["model_calls"] == 1
    outcome = await session.binding.invoker.invoke(session.context, writer.ref, "task")
    assert outcome.status == "succeeded" and len(calls) == 1
