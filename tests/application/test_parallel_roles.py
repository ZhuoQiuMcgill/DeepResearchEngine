"""Concurrent role settlement through real Engine/Storage and controlled HTTPX."""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager

import httpx
import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.application import ResearchRunService
from deepresearch.application.platform import RESEARCH_STATE_KEY
from deepresearch.engine.connections import Engine, EngineSettings
from deepresearch.engine.connections.engine import AgentInvoker
from deepresearch.engine.contracts import EngineError, Err, ExecutionContext
from deepresearch.engine.providers import ProviderConfig, ProviderFactory
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.engine.storage.session import OperationStore, StateStore
from deepresearch.workflows import MethodDefinition, MethodRegistry, ResearchRunRequest
from deepresearch.workflows.contracts import ResearchQuality
from deepresearch.workflows.components.agents import invoke_role
from deepresearch.workflows.components.parallel import bounded_map


ROLE, PROFILE, MODEL = "baseline.writer", "parallel-role-test", "deepseek-flash"
QUALITY = {"status": "partial", "report_accepted": True, "evidence_sufficient": False,
           "attempted_sources": 4, "substantive_sources": 3, "fully_read_sources": 2,
           "distilled_sources": 2, "gaps": ["One source was unavailable."],
           "reasons": ["The accepted report describes the remaining coverage gap."]}


@asynccontextmanager
async def environment(tmp_path, method, *, max_active=None):
    registry = MethodRegistry()
    registry.register(MethodDefinition(
        "test.parallel-roles", 1, "Concurrent invocations of one pinned role",
        {"type": "object", "additionalProperties": False},
        {"type": "object", "additionalProperties": False}, agent_roles=((ROLE, 1),),
    ), method)
    profile = ProviderConfig("deepseek", MODEL, "https://provider.invalid", "controlled-key",
                             profile_name=PROFILE)
    options = {} if max_active is None else {"max_active_descendants": max_active}
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store",
                              profiles={PROFILE: profile}, **options)
    engine = (await Engine.open(settings)).unwrap()
    service = None
    try:
        service = ResearchRunService(engine, registry, AgentCatalog(), TokenMeter())
        yield engine, service
    finally:
        try:
            if service is not None:
                cleanup = await service.close()
                assert cleanup.complete and not cleanup.errors and not cleanup.unconfirmed_resources
                assert service.active_count == 0
        finally:
            cleanup = await engine.close()
            assert cleanup.complete and not cleanup.errors and not cleanup.unconfirmed_resources


async def start(service, client_id="parallel", *, timeout_seconds=30):
    return await service.start_run(ResearchRunRequest(
        client_request_id=client_id, method_id="test.parallel-roles", input={},
        profile_ref=PROFILE, model_ref=MODEL, timeout_seconds=timeout_seconds,
    ))


async def terminal(service, run_id):
    async with asyncio.timeout(10):
        while True:
            view = await service.get_run(run_id)
            if not view.active:
                return view
            await asyncio.sleep(0.01)


async def events(service, run_id):
    rows, after = [], 0
    for _ in range(20):
        page = await service.events(run_id, after_seq=after, limit=100)
        rows.extend(page["events"])
        if not page["has_more"]:
            return rows
        assert page["next_after_seq"] > after
        after = page["next_after_seq"]
    pytest.fail("Parallel role events exceeded their bounded test query")


def report(index):
    return f"# Saved job={index}\n\nSelected α evidence for job {index}.\r\n"


def native_usage(index):
    return {"prompt_tokens": 11 + index, "completion_tokens": 4 + index,
            "total_tokens": 15 + 2 * index}


class ControlledRoles:
    def __init__(self, monkeypatch, first_wave, *, failure=None):
        self.first_wave, self.failure = first_wave, failure
        self.ready, self.release = asyncio.Event(), asyncio.Event()
        self.calls, self.cancelled, self.transports = [], [], []
        self.job_gates = {}
        self.active = self.peak = 0
        native_open = ProviderFactory.open
        owner = self

        class Transport(httpx.MockTransport):
            def __init__(self):
                super().__init__(owner.handle)
                self.closed = False

            async def aclose(self):
                self.closed = True
                await super().aclose()

        async def opened(config, context=None):
            transport = Transport()
            self.transports.append(transport)
            return await native_open(config, context, transport=transport)

        monkeypatch.setattr(ProviderFactory, "open", opened)

    async def handle(self, request):
        body = json.loads(request.content)
        user = next(message["content"] for message in body["messages"] if message["role"] == "user")
        index = int(re.search(r"job=(\d+)", user).group(1))
        assert index not in self.calls, "A settled invocation was redispatched"
        assert not body.get("tools")
        self.calls.append(index)
        self.active += 1
        self.peak = max(self.peak, self.active)
        if len(self.calls) == self.first_wave:
            self.ready.set()
        try:
            await self.release.wait()
            if index in self.job_gates:
                await self.job_gates[index].wait()
            payload = {"id": f"response-{index}", "model": MODEL, "usage": native_usage(index)}
            if index == self.failure:
                payload["error"] = {"type": "insufficient_quota", "message": "Controlled quota failure"}
                return httpx.Response(429, json=payload)
            payload["choices"] = [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": report(index)}}]
            return httpx.Response(200, json=payload)
        except asyncio.CancelledError:
            self.cancelled.append(index)
            raise
        finally:
            self.active -= 1


class ParallelMethod:
    def __init__(self, count):
        self.count = count
        self.tasks, self.outcomes, self.reads = [], [], []
        self.port = None

    async def run(self, context, task_input, parameters):
        self.port = context.port

        async def invoke(index):
            outcome = await context.port.invoke_agent(ROLE, {
                "question": f"Summarize selected evidence, job={index}.",
                "evidence": f"Host-selected retained source for job {index}.",
            })
            assert set(outcome) == {"status", "recording_status", "output_ref", "child_run", "usage"}
            return outcome

        self.tasks = [asyncio.create_task(invoke(index)) for index in range(self.count)]
        self.outcomes = await asyncio.gather(*self.tasks, return_exceptions=True)
        for outcome in self.outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        self.reads = [await context.port.read_artifact(outcome["output_ref"]) for outcome in self.outcomes]
        return {"report_ref": self.outcomes[0]["output_ref"]}


async def assert_settled(engine, service, view, controller, method, count, *, known=True, known_jobs=None):
    assert view.recording_status == "complete" and view.terminal_event_receipt is not None
    live = service._runs[view.run_id]
    assert live.cleanup.complete and not live.cleanup.errors and not live.cleanup.unconfirmed_resources
    assert not live.session.context.lease.active
    assert controller.active == 0 and count <= len(controller.transports) <= method.count
    assert all(transport.closed for transport in controller.transports)
    assert all(task.done() for task in method.tasks) and not engine._tasks
    assert live.session.context.ledger.remaining("model_calls") == engine.settings.limits["model_calls"] - count
    assert not any(not task.done() and task.get_name().startswith(f"deepresearch-role:{view.run_id}:")
                   for task in asyncio.all_tasks())
    rows = await events(service, view.run_id)
    models = [row for row in rows if row["event"]["kind"] == "model.outcome"]
    agents = [row for row in rows if row["event"]["kind"] == "agent.finished"]
    intents = [row for row in rows if row["event"]["kind"] == "invocation.intent"]
    invocations = [row for row in rows if row["event"]["kind"] == "invocation.outcome"]
    workflow = next(row for row in rows if row["event"]["kind"] == "workflow.finished")
    assert len(models) == len(agents) == len(intents) == len(invocations) == count
    children = {row["event"]["context"]["run_id"] for row in agents}
    assert len(children) == count and view.run_id not in children
    assert {row["event"]["payload"]["candidate_child_run"]["run_id"] for row in intents} == children
    intent_children = {row["event"]["context"]["action_id"]:
                       row["event"]["payload"]["candidate_child_run"]["run_id"] for row in intents}
    assert {row["event"]["context"]["action_id"] for row in invocations} == set(intent_children)
    for row in invocations:
        if row["event"]["payload"].get("child_run"):
            assert row["event"]["payload"]["child_run"]["run_id"] == intent_children[row["event"]["context"]["action_id"]]
    spec, registered = live.port.roles[ROLE]
    assert spec.ref == view.pins["roles"][0] and spec.revision == 1
    assert {row["event"]["payload"]["destination"]["agent_id"] for row in intents} == {registered.ref.agent_id}
    for row in agents:
        child = row["event"]["context"]
        assert child["parent_run_id"] == view.run_id
        invocation = next(item for item in invocations if item["event"]["context"]["action_id"] == child["parent_action_id"])
        assert invocation["event"]["context"]["action_id"] == child["parent_action_id"]
        assert invocation["event"]["context"]["attempt_id"] == child["parent_attempt_id"]
        assert invocation["event"]["payload"]["child_terminal_receipt"]["event_id"] == row["event"]["event_id"]
        assert row["receipt"]["recorded_seq"] < invocation["receipt"]["recorded_seq"] < workflow["receipt"]["recorded_seq"]
    refs = view.usage["per_attempt_usage_refs"]
    assert len(refs) == count and len({ref["event_id"] for ref in refs}) == count
    assert {ref["event_id"] for ref in refs} == {row["event"]["event_id"] for row in models}
    for ref in refs:
        row = next(item for item in models if item["event"]["event_id"] == ref["event_id"])
        assert ref == {"store_id": engine.storage.store_id, "event_id": row["event"]["event_id"],
                       "action_id": row["event"]["context"]["action_id"], "attempt_id": row["event"]["context"]["attempt_id"]}
    if known_jobs is None:
        known_jobs = tuple(range(count)) if known else ()
    assert view.usage["completeness"] == ("complete" if len(known_jobs) == count else "partial" if known_jobs else "unknown")
    assert view.usage["known_subtotals"] == {
        "input_tokens": sum(11 + index for index in known_jobs) if known_jobs else None,
        "output_tokens": sum(4 + index for index in known_jobs) if known_jobs else None,
        "total_tokens": sum(15 + 2 * index for index in known_jobs) if known_jobs else None,
        "cached_input_tokens": None, "reasoning_output_tokens": None, "uncached_input_tokens": None,
    }
    assert set(view.usage["unknown_attempt_ids"]) == {
        row["event"]["context"]["attempt_id"] for row in models
        if row["event"]["payload"]["usage"]["completeness"] != "complete"}
    state = (await engine.read_run_state(service.run_ref(view.run_id), RESEARCH_STATE_KEY)).unwrap()
    assert state.value["view"]["usage"] == view.usage and state.value["view"]["status"] == view.status
    return agents, invocations


@pytest.mark.asyncio
@pytest.mark.parametrize("count,max_active,expected_peak", [(4, None, 4), (8, None, 4), (8, 8, 8)],
                         ids=["four-default", "eight-queued", "eight-host-selected"])
async def test_same_pinned_role_concurrently_exports_distinct_children_and_complete_usage(
        tmp_path, monkeypatch, count, max_active, expected_peak):
    controller = ControlledRoles(monkeypatch, expected_peak)
    method = ParallelMethod(count)
    async with environment(tmp_path, method, max_active=max_active) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(controller.ready.wait(), 5)
            assert controller.active == expected_peak
            controller.release.set()
            view = await terminal(service, accepted.run_id)
            assert view.status == "succeeded", view.error
            agents, invocations = await assert_settled(engine, service, view, controller, method, count)
            assert controller.peak == expected_peak and set(controller.calls) == set(range(count))
            assert method.reads == [report(index).encode("utf-8") for index in range(count)]
            exports = [outcome["output_ref"] for outcome in method.outcomes]
            assert len({ref["artifact_id"] for ref in exports}) == count
            assert len({outcome["child_run"]["run_id"] for outcome in method.outcomes}) == count
            child_refs = {row["event"]["payload"]["output_ref"]["artifact_id"] for row in agents}
            assert not child_refs & {ref["artifact_id"] for ref in exports}
            objects = (await service.list_objects(view.run_id))["objects"]
            for ref in exports:
                descriptor = next(obj for obj in objects if obj["ref"] == ref)
                assert descriptor["scope"] == {"kind": "run", "id": view.run_id}
            assert {row["event"]["payload"]["export_receipt"]["artifact_ref"]["artifact_id"]
                    for row in invocations} == {ref["artifact_id"] for ref in exports}
        finally:
            controller.release.set()


@pytest.mark.asyncio
async def test_parallel_failure_settles_every_child_and_keeps_failed_native_usage(tmp_path, monkeypatch):
    controller, method = ControlledRoles(monkeypatch, 4, failure=1), ParallelMethod(4)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(controller.ready.wait(), 5)
            controller.release.set()
            view = await terminal(service, accepted.run_id)
            assert view.status == "failed" and view.report_ref is None
            agents, invocations = await assert_settled(engine, service, view, controller, method, 4)
            assert len([row for row in agents if row["event"]["payload"]["status"] == "failed"]) == 1
            assert len([row for row in invocations if row["event"]["payload"]["export_receipt"] is not None]) == 3
            assert isinstance(method.outcomes[1], EngineError)
        finally:
            controller.release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [4, 8], ids=["all-running", "four-running-four-queued"])
async def test_parallel_cancellation_drains_invokers_and_retains_all_unknown_usage(tmp_path, monkeypatch, count):
    controller, method = ControlledRoles(monkeypatch, 4), ParallelMethod(count)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(controller.ready.wait(), 5)
            await service.cancel_run(accepted.run_id)
            view = await terminal(service, accepted.run_id)
            assert view.status == "cancelled" and view.cancellation_requested and view.report_ref is None
            agents, invocations = await assert_settled(engine, service, view, controller, method, 4, known=False)
            assert set(controller.cancelled) == set(range(4))
            assert all(row["event"]["payload"]["status"] == "cancelled" for row in agents)
            assert all(row["event"]["payload"]["export_receipt"] is None for row in invocations)
            rows = await events(service, view.run_id)
            rejected = [row for row in rows if row["event"]["kind"] == "invocation.rejected"]
            assert len(rejected) == count - 4
            assert all(not row["event"]["payload"]["dispatched"] for row in rejected)
            assert all(not context.lease.active for context in engine._contexts.values())
        finally:
            controller.release.set()


@pytest.mark.asyncio
async def test_root_cancel_is_visible_at_export_authorization_before_any_watcher_runs(tmp_path, monkeypatch):
    controller, method = ControlledRoles(monkeypatch, 1), ParallelMethod(1)
    native_authorize = ExecutionContext.authorize
    cancelled_at_export = []

    def cancel_at_export(self, operation, *args, **kwargs):
        if (method.port is not None and self.run_id == method.port.live.view.run_id
                and operation == "artifact.put" and not cancelled_at_export):
            cancelled_at_export.append(self.run_id)
            method.port.session.context.cancellation.set()
        return native_authorize(self, operation, *args, **kwargs)

    monkeypatch.setattr(ExecutionContext, "authorize", cancel_at_export)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(controller.ready.wait(), 5)
            controller.release.set()
            view = await terminal(service, accepted.run_id)
            assert cancelled_at_export == [view.run_id]
            assert view.status == "cancelled" and view.report_ref is None
            agents, invocations = await assert_settled(engine, service, view, controller, method, 1)
            assert agents[0]["event"]["payload"]["status"] == "succeeded"
            assert invocations[0]["event"]["payload"].get("export_receipt") is None
            rows = await events(service, view.run_id)
            accepted_payload = next(row["event"]["payload"] for row in rows if row["event"]["kind"] == "workflow.accepted")
            objects = (await service.list_objects(view.run_id))["objects"]
            assert {obj["ref"]["artifact_id"] for obj in objects if obj["kind"] == "artifact"} == {
                accepted_payload["request_ref"]["artifact_id"], accepted_payload["method_manifest_ref"]["artifact_id"]}
        finally:
            controller.release.set()


@pytest.mark.asyncio
async def test_parallel_deadline_drains_children_without_reclassifying_timeout_as_cancellation(tmp_path, monkeypatch):
    controller, method = ControlledRoles(monkeypatch, 4), ParallelMethod(4)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service, timeout_seconds=1.5)
            await asyncio.wait_for(controller.ready.wait(), 5)
            view = await terminal(service, accepted.run_id)
            assert view.status == "timed_out" and not view.cancellation_requested
            assert not method.port.session.context.cancellation.is_set()
            assert view.report_ref is None
            agents, invocations = await assert_settled(engine, service, view, controller, method, 4, known=False)
            assert set(controller.cancelled) == set(range(4))
            # The application deadline can cancel a child just before its own
            # timer fires; retain that actual child terminal independently.
            assert all(row["event"]["payload"]["status"] in {"timed_out", "cancelled"} for row in agents)
            assert all(row["event"]["payload"]["export_receipt"] is None for row in invocations)
        finally:
            controller.release.set()


@pytest.mark.asyncio
async def test_queued_usage_cleanup_preserves_latest_node_projection(tmp_path, monkeypatch):
    controller, method = ControlledRoles(monkeypatch, 4), ParallelMethod(4)
    outcomes_ready, return_outcomes = asyncio.Event(), asyncio.Event()
    native_invoke = AgentInvoker.invoke
    arrived = 0

    async def gated_invocation(self, *args, **kwargs):
        nonlocal arrived
        outcome = await native_invoke(self, *args, **kwargs)
        arrived += 1
        if arrived == 4:
            outcomes_ready.set()
        await return_outcomes.wait()
        return outcome

    monkeypatch.setattr(AgentInvoker, "invoke", gated_invocation)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(controller.ready.wait(), 5)
            controller.release.set()
            await asyncio.wait_for(outcomes_ready.wait(), 5)
            port = method.port
            commits = []
            native_commit = port._commit

            async def observed_commit(view, *, cleanup=False):
                receipt = await native_commit(view, cleanup=cleanup)
                commits.append(view.model_copy(deep=True))
                return receipt

            monkeypatch.setattr(port, "_commit", observed_commit)
            async with port._lock:
                nodes = [node.model_copy(update={"status": "failed", "detail": {"marker": "latest node"}}).to_dict()
                         for node in port.live.view.nodes]
                queued_update = asyncio.create_task(port.update(cleanup=True, nodes=nodes))
                await asyncio.sleep(0)
                port.session.context.cancellation.set()
                return_outcomes.set()
                # Give all returned role outcomes a chance to queue their
                # cleanup CAS behind the independent node projection.
                for _ in range(10):
                    await asyncio.sleep(0)
            await queued_update
            view = await terminal(service, accepted.run_id)
            assert view.status == "cancelled"
            await assert_settled(engine, service, view, controller, method, 4)
            usage_commits = [item for item in commits if item.usage is not None][:4]
            assert [len(item.usage["per_attempt_usage_refs"]) for item in usage_commits] == [1, 2, 3, 4]
            assert all(all(node.status == "failed" and node.detail == {"marker": "latest node"}
                           for node in item.nodes) for item in usage_commits)
        finally:
            controller.release.set()
            return_outcomes.set()


class ProjectionMethod:
    def __init__(self):
        self.ready, self.release = asyncio.Event(), asyncio.Event()
        self.port = None

    async def run(self, context, task_input, parameters):
        self.port = context.port
        self.ready.set()
        await self.release.wait()
        ref = await context.port.publish(b"# Accepted partial report\n", "text/markdown", "report.md")
        await context.port.update(quality=ResearchQuality.model_validate(QUALITY).to_dict(), report_ref=ref)
        return {"report_ref": ref}


@pytest.mark.asyncio
async def test_quality_projection_is_validated_durable_and_cannot_change_lifecycle_or_publish_foreign_output(tmp_path):
    method = ProjectionMethod()
    async with environment(tmp_path, method) as (engine, service):
        try:
            first = await start(service, "first-projection")
            await asyncio.wait_for(method.ready.wait(), 5)
            method.release.set()
            saved = await terminal(service, first.run_id)
            assert saved.status == "succeeded" and saved.quality == ResearchQuality.model_validate(QUALITY)
            method.ready.clear()
            method.release.clear()
            second = await start(service, "second-projection")
            await asyncio.wait_for(method.ready.wait(), 5)
            port = method.port
            await port.update(quality=QUALITY)
            for fields in ({"quality": {**QUALITY, "status": "sufficient"}},
                           {"quality": {**QUALITY, "extra": "unknown"}},
                           {"quality": QUALITY, "status": "succeeded"}):
                with pytest.raises(EngineError) as error:
                    await port.update(**fields)
                assert error.value.code == "INVALID_DATA"
            with pytest.raises(EngineError) as error:
                await port.update(cleanup=True, quality=QUALITY)
            assert error.value.code == "INVALID_DATA"
            for key in ("report_ref", "result_manifest_ref"):
                with pytest.raises(EngineError) as error:
                    await port.update(**{key: saved.report_ref.to_dict()})
                assert error.value.code in {"ACCESS_DENIED", "NOT_FOUND"}
            current = await service.get_run(second.run_id)
            assert current.status == "running" and current.active and current.report_ref is None
            assert current.quality == saved.quality
            method.release.set()
            view = await terminal(service, second.run_id)
            assert view.status == "succeeded" and view.report_ref != saved.report_ref
            state = (await engine.read_run_state(service.run_ref(view.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert state.value["view"]["quality"] == view.quality.to_dict()
        finally:
            method.release.set()
    async with environment(tmp_path, ProjectionMethod()) as (_, restored):
        reopened = await restored.get_run(view.run_id)
        assert reopened.status == "succeeded" and reopened.quality == view.quality
        assert reopened.report_ref == view.report_ref and reopened.terminal_event_receipt == view.terminal_event_receipt
        assert restored.active_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_ack", [False, True], ids=["delayed-receipt", "delayed-lost-receipt"])
async def test_cancelled_projection_commit_drains_same_operation_before_queued_update(tmp_path, monkeypatch, lost_ack):
    method = ProjectionMethod()
    admitted, release_ack = asyncio.Event(), asyncio.Event()
    native_commit, native_status = StateStore.commit, OperationStore.status
    writes, statuses = [], []

    async def delayed_commit(self, context, operation, mutations, activity=None):
        result = await native_commit(self, context, operation, mutations, activity)
        if (mutations[0].key == RESEARCH_STATE_KEY
                and mutations[0].value["view"].get("quality") is not None and not writes):
            assert result.is_ok
            writes.append((operation, mutations[0].expected_version, result.unwrap()))
            admitted.set()
            await release_ack.wait()
            if lost_ack:
                return Err(EngineError("LOST_ACK", "Controlled state acknowledgement loss", commit_state="unknown"))
        return result

    async def observed_status(self, context, operation):
        statuses.append(operation)
        return await native_status(self, context, operation)

    monkeypatch.setattr(StateStore, "commit", delayed_commit)
    monkeypatch.setattr(OperationStore, "status", observed_status)
    async with environment(tmp_path, method) as (engine, service):
        interrupted = queued = None
        try:
            accepted = await start(service)
            await asyncio.wait_for(method.ready.wait(), 5)
            port = method.port
            interrupted = asyncio.create_task(port.update(quality=QUALITY))
            await asyncio.wait_for(admitted.wait(), 5)
            head = (await engine.read_run_state(service.run_ref(accepted.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert head.version == writes[0][1] + 1 and port.live.version == writes[0][1]
            interrupted.cancel()
            await asyncio.sleep(0)
            interrupted.cancel()
            queued_quality = {**QUALITY, "reasons": ["A newer independent projection must survive."]}
            queued = asyncio.create_task(port.update(quality=queued_quality))
            await asyncio.sleep(0)
            assert not interrupted.done() and not queued.done()
            release_ack.set()
            with pytest.raises(asyncio.CancelledError):
                await interrupted
            next_receipt = await queued
            assert next_receipt.mutation_versions[0]["old_version"] == head.version
            assert port.live.version == head.version + 1 and port.live.view.quality.reasons == queued_quality["reasons"]
            assert port.failure is None
            assert statuses == ([writes[0][0]] if lost_ack else [])
            rows = await events(service, accepted.run_id)
            assert sum(row["event"]["payload"].get("operation_id") == writes[0][0]
                       for row in rows if row["event"]["kind"] == "state.committed") == 1
            method.release.set()
            view = await terminal(service, accepted.run_id)
            assert view.status == "succeeded" and view.recording_status == "complete"
        finally:
            release_ack.set()
            if interrupted is not None:
                await asyncio.gather(interrupted, return_exceptions=True)
            if queued is not None:
                await asyncio.gather(queued, return_exceptions=True)
            method.release.set()


class InterruptedFlushMethod:
    def __init__(self):
        self.count = 4
        self.tasks, self.by_index, self.reads = [], {}, {}
        self.failure_ready, self.fail_now = asyncio.Event(), asyncio.Event()
        self.port = None

    async def run(self, context, task_input, parameters):
        self.port = context.port

        async def worker(index):
            self.by_index[index] = asyncio.current_task()
            self.tasks.append(asyncio.current_task())
            raw, _ = await invoke_role(context, ROLE, {
                "question": f"Summarize selected evidence, job={index}.",
                "evidence": f"Host-selected source for job {index}.",
            }, node_id=f"distill.{index}")
            self.reads[index] = raw
            if index == 1:
                await self.failure_ready.wait()
            async with context.node(f"distill.{index}.validate", "validation"):
                assert raw == report(index).encode("utf-8")
            if index == 0:
                self.failure_ready.set()
                await self.fail_now.wait()
                await context.port.emit("workflow.test.unregistered-event", {})

        await bounded_map(range(4), worker, concurrency=4)
        pytest.fail("The original event rejection must fail this method")


@pytest.mark.asyncio
async def test_sibling_cancellation_during_real_node_commit_preserves_original_failure_and_all_usage(tmp_path, monkeypatch):
    controller, method = ControlledRoles(monkeypatch, 4), InterruptedFlushMethod()
    controller.job_gates = {2: asyncio.Event(), 3: asyncio.Event()}
    admitted, release_ack = asyncio.Event(), asyncio.Event()
    native_commit = StateStore.commit
    writes = []

    async def delayed_commit(self, context, operation, mutations, activity=None):
        result = await native_commit(self, context, operation, mutations, activity)
        nodes = mutations[0].value.get("view", {}).get("nodes", [])
        if (not writes and any(node["node_id"] == "distill.1.validate" and node["status"] == "succeeded"
                               for node in nodes)):
            assert result.is_ok
            writes.append((operation, mutations[0].expected_version))
            admitted.set()
            await release_ack.wait()
        return result

    monkeypatch.setattr(StateStore, "commit", delayed_commit)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(controller.ready.wait(), 5)
            controller.release.set()
            await asyncio.wait_for(method.failure_ready.wait(), 5)
            await asyncio.wait_for(admitted.wait(), 5)
            head = (await engine.read_run_state(service.run_ref(accepted.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert head.version == writes[0][1] + 1 and method.port.live.version == writes[0][1]
            method.fail_now.set()
            async with asyncio.timeout(5):
                while not method.by_index[1].cancelling():
                    await asyncio.sleep(0.001)
            assert not method.by_index[1].done() and method.port._lock.locked()
            release_ack.set()
            view = await terminal(service, accepted.run_id)
            assert view.status == "failed" and view.error["code"] == "INVALID_DATA"
            agents, _ = await assert_settled(engine, service, view, controller, method, 4, known_jobs=(0, 1))
            assert sorted(row["event"]["payload"]["status"] for row in agents) == ["cancelled", "cancelled", "succeeded", "succeeded"]
            assert method.reads == {0: report(0).encode("utf-8"), 1: report(1).encode("utf-8")}
            assert set(controller.cancelled) == {2, 3}
            rows = await events(service, view.run_id)
            root_terminal = next(row["event"]["payload"] for row in rows if row["event"]["kind"] == "workflow.finished")
            assert root_terminal["error"]["code"] == "INVALID_DATA" and root_terminal["recording_status"] == "complete"
            assert all(node.detail.get("error_code") != "VERSION_CONFLICT" for node in view.nodes)
            assert method.port.failure.code == "INVALID_DATA"
            head = (await engine.read_run_state(service.run_ref(view.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert method.port.live.version == head.version
            assert sum(row["event"]["payload"].get("operation_id") == writes[0][0]
                       for row in rows if row["event"]["kind"] == "state.committed") == 1
        finally:
            release_ack.set()
            method.fail_now.set()
            controller.release.set()
            for gate in controller.job_gates.values():
                gate.set()


@pytest.mark.asyncio
async def test_unconfirmed_projection_commit_preserves_unknown_and_never_issues_fresh_cas(tmp_path, monkeypatch):
    method = ProjectionMethod()
    native_commit = StateStore.commit
    writes, statuses = [], []

    async def lost_commit(self, context, operation, mutations, activity=None):
        result = await native_commit(self, context, operation, mutations, activity)
        if (mutations[0].key == RESEARCH_STATE_KEY
                and mutations[0].value["view"].get("quality") is not None):
            assert result.is_ok
            writes.append(operation)
            return Err(EngineError("LOST_ACK", "Controlled uncertain projection commit", commit_state="unknown"))
        return result

    async def unavailable_status(self, context, operation):
        statuses.append(operation)
        return Err(EngineError("STATUS_UNAVAILABLE", "Controlled unavailable operation status"))

    monkeypatch.setattr(StateStore, "commit", lost_commit)
    monkeypatch.setattr(OperationStore, "status", unavailable_status)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(method.ready.wait(), 5)
            old_version = method.port.live.version
            for _ in range(2):
                with pytest.raises(EngineError) as error:
                    await method.port.update(quality=QUALITY)
                assert error.value.code == "LOST_ACK" and error.value.commit_state == "unknown"
            assert len(writes) == 1 and statuses == writes
            assert method.port.live.version == old_version and method.port.failure.commit_state == "unknown"
            head = (await engine.read_run_state(service.run_ref(accepted.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert head.version == old_version + 1
            method.release.set()
            view = await terminal(service, accepted.run_id)
            assert view.status == "interrupted" and view.recording_status == "incomplete"
            assert view.error["code"] == "LOST_ACK" and view.error["commit_state"] == "unknown"
            assert len(writes) == 1 and method.port.live.version == old_version
        finally:
            method.release.set()


@pytest.mark.asyncio
async def test_node_admission_cancelled_after_durable_commit_before_ack_records_terminal_node(tmp_path, monkeypatch):
    class AdmissionMethod:
        body_entered = False

        async def run(self, context, task_input, parameters):
            self.context, self.port, self.task = context, context.port, asyncio.current_task()
            async with context.node("interrupted.admission", "validation"):
                self.body_entered = True
                pytest.fail("Cancellation during admission must prevent the node body")

    method = AdmissionMethod()
    admitted, release_ack = asyncio.Event(), asyncio.Event()
    native_commit = StateStore.commit
    writes = []

    async def delayed_commit(self, context, operation, mutations, activity=None):
        result = await native_commit(self, context, operation, mutations, activity)
        nodes = mutations[0].value.get("view", {}).get("nodes", [])
        if (not writes and any(node["node_id"] == "interrupted.admission" and node["status"] == "running"
                               for node in nodes)):
            assert result.is_ok
            writes.append((operation, mutations[0].expected_version))
            admitted.set()
            await release_ack.wait()
        return result

    monkeypatch.setattr(StateStore, "commit", delayed_commit)
    async with environment(tmp_path, method) as (engine, service):
        try:
            accepted = await start(service)
            await asyncio.wait_for(admitted.wait(), 5)
            head = (await engine.read_run_state(service.run_ref(accepted.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert head.version == writes[0][1] + 1 and method.port.live.version == writes[0][1]
            method.port.session.context.cancellation.set()
            async with asyncio.timeout(5):
                while not method.task.cancelling():
                    await asyncio.sleep(0.001)
            assert not method.task.done()
            release_ack.set()
            view = await terminal(service, accepted.run_id)
            assert view.status == "cancelled" and view.error["code"] == "CANCELLED"
            assert view.recording_status == "complete" and view.terminal_event_receipt is not None
            assert not method.body_entered and method.task.done()
            assert {node.node_id for node in view.nodes} == {"method", "interrupted.admission"}
            assert all(node.status == "cancelled" for node in view.nodes)
            assert all(node["status"] == "cancelled" for node in method.context.nodes.values())
            head = (await engine.read_run_state(service.run_ref(view.run_id), RESEARCH_STATE_KEY)).unwrap()
            assert method.port.live.version == head.version
            assert head.value["view"]["nodes"] == [node.to_dict() for node in view.nodes]
            assert head.value["view"]["status"] == "cancelled"
            rows = await events(service, view.run_id)
            failed = [row for row in rows if row["event"]["kind"] == "workflow.node.failed"
                      and row["event"]["payload"]["node_id"] == "interrupted.admission"]
            assert len(failed) == 1 and failed[0]["event"]["payload"]["status"] == "cancelled"
            assert failed[0]["event"]["payload"]["detail"]["error_code"] == "CancelledError"
            assert failed[0]["receipt"]["recorded_seq"] < view.terminal_event_receipt["recorded_seq"]
            assert sum(row["event"]["payload"].get("operation_id") == writes[0][0]
                       for row in rows if row["event"]["kind"] == "state.committed") == 1
            assert not any(row["event"]["kind"] == "model.intent" for row in rows)
            assert not engine._tasks and service.active_count == 0
            assert method.port.live.cleanup.complete and not method.port.session.context.lease.active
            assert not any(not task.done() and task.get_name() in {
                f"deepresearch-projection:{view.run_id}", f"deepresearch-research:method:{view.run_id}"}
                for task in asyncio.all_tasks())
        finally:
            release_ack.set()
