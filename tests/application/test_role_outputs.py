"""Explicit role output reads and usage accumulation over real Workflow authority."""
from __future__ import annotations

import asyncio
import base64
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.application import ResearchRunService
from deepresearch.application.platform import RESEARCH_STATE_KEY
from deepresearch.engine.connections import Engine, EngineSettings
from deepresearch.engine.contracts import EngineError, canonical_json
from deepresearch.engine.providers import ProviderConfig, ProviderFactory
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.engine.storage.session import ArtifactRead, ArtifactStore
from deepresearch.workflows import MethodDefinition, MethodRegistry, ResearchRunRequest


ROLE = "baseline.writer"
PROFILE = "role-output-test"
MODEL = "deepseek-flash"
REPORTS = ("# First report\n\nSaved α evidence.\n", "# Second report\n\nRetained 中文 finding.\n")
FIRST_USAGE = {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15,
               "prompt_cache_hit_tokens": 3, "prompt_cache_miss_tokens": 8,
               "completion_tokens_details": {"reasoning_tokens": 2}}
SECOND_USAGE = {"prompt_tokens": 17, "completion_tokens": 6, "total_tokens": 23,
                "prompt_cache_hit_tokens": 5, "prompt_cache_miss_tokens": 12,
                "completion_tokens_details": {"reasoning_tokens": 4}}
COMPLETE_TOTALS = {"input_tokens": 28, "output_tokens": 10, "total_tokens": 38,
                   "cached_input_tokens": 8, "reasoning_output_tokens": 6,
                   "uncached_input_tokens": 20}


def registry_for(method):
    registry = MethodRegistry()
    registry.register(MethodDefinition(
        "test.role-outputs", 1, "Exercise saved role outputs through the Workflow host",
        {"type": "object", "additionalProperties": False},
        {"type": "object", "additionalProperties": False},
        agent_roles=((ROLE, 1),),
    ), method)
    return registry


@asynccontextmanager
async def environment(tmp_path, method):
    profile = ProviderConfig("deepseek", MODEL, "https://provider.invalid", "controlled-test-key",
                             profile_name=PROFILE)
    engine = (await Engine.open(EngineSettings(
        workspace=tmp_path, storage_root=tmp_path / "store", profiles={PROFILE: profile},
    ))).unwrap()
    service = None
    try:
        service = ResearchRunService(engine, registry_for(method), AgentCatalog(), TokenMeter())
        yield engine, service
    finally:
        try:
            if service is not None:
                assert (await service.close()).complete
                assert service.active_count == 0
        finally:
            assert (await engine.close()).complete


async def execute(service, client_id="role-output-case"):
    accepted = await service.start_run(ResearchRunRequest(
        client_request_id=client_id, method_id="test.role-outputs", method_revision=1,
        input={}, profile_ref=PROFILE, model_ref=MODEL, timeout_seconds=30.0,
    ))
    async with asyncio.timeout(10):
        while True:
            view = await service.get_run(accepted.run_id)
            if not view.active:
                return view
            await asyncio.sleep(0.01)


async def events(service, run_id):
    rows, after = [], 0
    for _ in range(10):
        page = await service.events(run_id, after_seq=after, limit=100)
        rows.extend(page["events"])
        if not page["has_more"]:
            return rows
        assert page["next_after_seq"] > after
        after = page["next_after_seq"]
    pytest.fail("Role output execution exceeded the test's event read bound")


class ArtifactMethod:
    def __init__(self, content, operation=None):
        self.content = content
        self.operation = operation
        self.refs = []
        self.reads = []

    async def run(self, context, task_input, parameters):
        async with context.node("artifact.read", "saved-artifact"):
            ref = await context.port.publish(self.content, "application/octet-stream", "saved.bin")
            self.refs.append(ref)
            if self.operation is not None:
                await self.operation(context.port, ref)
            else:
                self.reads.append(await context.port.read_artifact(ref, max_bytes=len(self.content)))
            return {"report_ref": ref}


class TwoWriterMethod:
    def __init__(self):
        self.outcomes = []
        self.reads = []

    async def run(self, context, task_input, parameters):
        evidence = "Selected retained evidence supplied by the host."
        for turn in range(2):
            async with context.node(f"writer.{turn + 1}", "agent"):
                outcome = await context.port.invoke_agent(ROLE, {
                    "question": "Summarize the selected evidence.", "evidence": evidence,
                })
                self.outcomes.append(outcome)
                assert set(outcome) == {"status", "recording_status", "output_ref", "child_run", "usage"}
                assert outcome["status"] == "succeeded" and outcome["recording_status"] == "complete"
                assert REPORTS[turn] not in canonical_json(outcome).decode("utf-8")
                saved = await context.port.read_artifact(outcome["output_ref"])
                assert type(saved) is bytes
                self.reads.append(saved)
                evidence = saved.decode("utf-8")
        # Usage belongs to the host projection. Returning the last child's usage
        # here would hide the cumulative contract this test is intended to check.
        return {"report_ref": self.outcomes[-1]["output_ref"]}


def observe_streams(monkeypatch):
    """Observe real Storage operations, delegating every operation unchanged."""
    trace = {"opens": [], "reads": [], "closes": []}
    native_open, native_read, native_close = ArtifactStore.open, ArtifactRead.read, ArtifactRead.aclose

    async def opened(self, context, artifact_ref, byte_range=None, max_bytes=8 << 20):
        result = await native_open(self, context, artifact_ref, byte_range, max_bytes)
        if context.context_kind == "workflow":
            trace["opens"].append((artifact_ref.artifact_id, max_bytes))
        return result

    async def read(self, context, max_bytes=64 << 10):
        result = await native_read(self, context, max_bytes)
        if context.context_kind == "workflow":
            trace["reads"].append((self.artifact_ref.artifact_id, max_bytes))
        return result

    async def closed(self, context):
        result = await native_close(self, context)
        if context.context_kind == "workflow":
            trace["closes"].append(self.artifact_ref.artifact_id)
        return result

    monkeypatch.setattr(ArtifactStore, "open", opened)
    monkeypatch.setattr(ArtifactRead, "read", read)
    monkeypatch.setattr(ArtifactRead, "aclose", closed)
    return trace


def controlled_provider(monkeypatch, usages, *, second="stop"):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        turn = len(calls) - 1
        assert turn < 2, "The host unexpectedly redispatched a model attempt"
        body = {"id": f"role-response-{turn + 1}", "model": MODEL}
        if usages[turn] is not None:
            body["usage"] = usages[turn]
        if turn == 1 and second == "http_error":
            body["error"] = {"type": "insufficient_quota", "message": "Controlled provider refusal"}
            return httpx.Response(429, json=body)
        if turn == 1 and second == "protocol_error":
            body["choices"] = []
        else:
            body["choices"] = [{"finish_reason": second if turn == 1 else "stop",
                                "message": {"role": "assistant", "content": REPORTS[turn]}}]
        return httpx.Response(200, json=body)

    native_open = ProviderFactory.open

    async def opened(config, context=None):
        return await native_open(config, context, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(ProviderFactory, "open", opened)
    return calls


async def assert_recorded_usage(engine, service, view, totals, completeness, unknown_turns):
    usage = view.usage
    assert usage["known_subtotals"] == totals
    assert usage["completeness"] == completeness
    rows = await events(service, view.run_id)
    outcomes = [row for row in rows if row["event"]["kind"] == "model.outcome"]
    intents = [row for row in rows if row["event"]["kind"] == "model.intent"]
    terminals = [row for row in rows if row["event"]["kind"] == "agent.finished"]
    assert len(outcomes) == len(intents) == len(terminals) == 2
    assert len({row["event"]["context"]["run_id"] for row in outcomes}) == 2
    refs = usage["per_attempt_usage_refs"]
    assert len(refs) == 2 and len({ref["event_id"] for ref in refs}) == 2
    assert refs == [{"store_id": engine.storage.store_id,
                     "event_id": row["event"]["event_id"],
                     "action_id": row["event"]["context"]["action_id"],
                     "attempt_id": row["event"]["context"]["attempt_id"]} for row in outcomes]
    assert usage["unknown_attempt_ids"] == [outcomes[turn]["event"]["context"]["attempt_id"]
                                             for turn in unknown_turns]
    for row in outcomes:
        assert row["receipt"]["event_id"] == row["event"]["event_id"]
        assert row["event"]["context"]["context_kind"] == "agent"
    assert {ref["event_id"] for terminal in terminals
            for ref in terminal["event"]["payload"]["usage"]["per_attempt_usage_refs"]} == {
                ref["event_id"] for ref in refs}
    state = (await engine.read_run_state(service.run_ref(view.run_id), RESEARCH_STATE_KEY)).unwrap()
    assert state.value["view"]["usage"] == usage
    assert state.value["view"]["status"] == view.status
    assert view.recording_status == "complete" and view.terminal_event_receipt is not None
    return outcomes


@pytest.mark.asyncio
async def test_same_workflow_artifact_returns_exact_bytes_through_bounded_storage_stream(tmp_path, monkeypatch):
    content = bytes(range(256)) * 300 + "α 中文\r\n".encode("utf-8")
    method = ArtifactMethod(content)
    trace = observe_streams(monkeypatch)
    async with environment(tmp_path, method) as (engine, service):
        view = await execute(service)
        assert view.status == "succeeded", view.error
        assert method.reads == [content]
        artifact_id = method.refs[0]["artifact_id"]
        assert (artifact_id, len(content)) in trace["opens"]
        reads = [cap for identity, cap in trace["reads"] if identity == artifact_id]
        assert len(reads) >= 2 and all(1 <= cap <= 65536 for cap in reads)
        assert trace["closes"].count(artifact_id) == 1
        objects = (await service.list_objects(view.run_id))["objects"]
        descriptor = next(obj for obj in objects if obj["ref"] == method.refs[0])
        assert descriptor["scope"] == {"kind": "run", "id": view.run_id}
        assert method.refs[0]["store_id"] == engine.storage.store_id


@pytest.mark.asyncio
async def test_artifact_read_enforces_bytes_instead_of_character_count(tmp_path):
    content = "é".encode("utf-8")

    async def operation(port, ref):
        with pytest.raises(EngineError) as error:
            await port.read_artifact(ref, max_bytes=1)
        assert error.value.code == "LIMIT_EXCEEDED"
        assert await port.read_artifact(ref, max_bytes=2) == content

    async with environment(tmp_path, ArtifactMethod(content, operation)) as (_, service):
        view = await execute(service)
        assert view.status == "succeeded", view.error


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [True, False, 0, -1, 1.5, "65536", None, 262145])
async def test_invalid_artifact_caps_reject_before_storage_open(tmp_path, monkeypatch, cap):
    trace = observe_streams(monkeypatch)

    async def operation(port, ref):
        with pytest.raises(EngineError) as error:
            await port.read_artifact(ref, max_bytes=cap)
        assert error.value.code == "INVALID_DATA"

    method = ArtifactMethod(b"saved", operation)
    async with environment(tmp_path, method) as (_, service):
        view = await execute(service)
        assert view.status == "succeeded", view.error
        assert not any(identity == method.refs[0]["artifact_id"] for identity, _ in trace["opens"])


@pytest.mark.asyncio
async def test_maximum_artifact_cap_is_accepted_without_truncation(tmp_path):
    content = bytes(range(256)) * 1024
    method = ArtifactMethod(content)
    async with environment(tmp_path, method) as (_, service):
        view = await execute(service)
        assert view.status == "succeeded", view.error
        assert method.reads == [content]


@pytest.mark.asyncio
async def test_real_read_budget_failure_still_closes_the_open_artifact_stream(tmp_path, monkeypatch):
    trace = observe_streams(monkeypatch)

    async def operation(port, ref):
        ledger = port.session.context.ledger
        ledger.consume("storage_read_bytes", ledger.remaining("storage_read_bytes") - 4096)
        with pytest.raises(EngineError) as error:
            await port.read_artifact(ref, max_bytes=8192)
        assert error.value.code == "LIMIT_EXCEEDED"

    method = ArtifactMethod(b"x" * 8192, operation)
    async with environment(tmp_path, method) as (_, service):
        view = await execute(service)
        assert view.status == "succeeded", view.error
        identity = method.refs[0]["artifact_id"]
        assert (identity, 8192) in trace["opens"] and (identity, 8192) in trace["reads"]
        assert trace["closes"].count(identity) == 1


@pytest.mark.asyncio
async def test_same_store_artifact_from_another_workflow_is_rejected(tmp_path, monkeypatch):
    foreign = []
    trace = observe_streams(monkeypatch)

    async def operation(port, ref):
        if not foreign:
            foreign.append(ref)
            return
        with pytest.raises(EngineError) as error:
            await port.read_artifact(foreign[0])
        assert error.value.code in {"ACCESS_DENIED", "NOT_FOUND"}
        assert await port.read_artifact(ref) == b"foreign-scope-check"

    method = ArtifactMethod(b"foreign-scope-check", operation)
    async with environment(tmp_path, method) as (_, service):
        first = await execute(service, "owner")
        second = await execute(service, "other-workflow")
        assert first.status == second.status == "succeeded"
        assert first.run_id != second.run_id and method.refs[0] != method.refs[1]
        assert not any(identity == foreign[0]["artifact_id"] for identity, _ in trace["opens"])


@pytest.mark.asyncio
async def test_real_artifact_reference_from_another_store_is_rejected(tmp_path, monkeypatch):
    owner = ArtifactMethod(b"foreign-store-secret")
    async with environment(tmp_path / "foreign", owner) as (foreign_engine, foreign_service):
        assert (await execute(foreign_service)).status == "succeeded"
        foreign_ref = owner.refs[0]
        trace = observe_streams(monkeypatch)

        async def operation(port, ref):
            with pytest.raises(EngineError) as error:
                await port.read_artifact(foreign_ref)
            assert error.value.code == "ACCESS_DENIED"
            assert await port.read_artifact(ref) == b"local-store-content"

        async with environment(tmp_path / "local", ArtifactMethod(b"local-store-content", operation)) as (engine, service):
            assert engine.storage.store_id != foreign_engine.storage.store_id
            view = await execute(service)
            assert view.status == "succeeded", view.error
            assert not any(identity == foreign_ref["artifact_id"] for identity, _ in trace["opens"])


@pytest.mark.asyncio
@pytest.mark.parametrize("usages,totals,completeness,unknown_turns", [
    ((FIRST_USAGE, SECOND_USAGE), COMPLETE_TOTALS, "complete", []),
    (({"prompt_tokens": 11, "prompt_cache_hit_tokens": 0}, {"completion_tokens": 6, "total_tokens": 23}),
     {"input_tokens": 11, "output_tokens": 6, "total_tokens": 23, "cached_input_tokens": 0,
      "reasoning_output_tokens": None, "uncached_input_tokens": None}, "partial", [0, 1]),
    ((None, None), {"input_tokens": None, "output_tokens": None, "total_tokens": None,
                   "cached_input_tokens": None, "reasoning_output_tokens": None,
                   "uncached_input_tokens": None}, "unknown", [0, 1]),
    (({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None),
     {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_input_tokens": None,
      "reasoning_output_tokens": None, "uncached_input_tokens": None}, "partial", [1]),
], ids=["complete-native-counts", "disjoint-partial-counts", "all-counts-unknown", "reported-zero-then-unknown"])
async def test_two_writer_calls_accumulate_native_usage_and_return_text_only_when_read(
    tmp_path, monkeypatch, usages, totals, completeness, unknown_turns,
):
    calls = controlled_provider(monkeypatch, usages)
    method = TwoWriterMethod()
    async with environment(tmp_path, method) as (engine, service):
        view = await execute(service)
        assert view.status == "succeeded", view.error
        assert len(calls) == 2 and all(not call.get("tools") for call in calls)
        assert len(method.outcomes) == 2 and method.reads == [report.encode("utf-8") for report in REPORTS]
        assert any(REPORTS[0] in message.get("content", "") for message in calls[1]["messages"])
        assert view.report_ref.to_dict() == method.outcomes[1]["output_ref"]
        assert [(pin["role_id"], pin["revision"]) for pin in view.pins["roles"]] == [(ROLE, 1)]
        await assert_recorded_usage(engine, service, view, totals, completeness, unknown_turns)
        published = await service.read_report(view.run_id)
        assert base64.b64decode(published["data"]) == REPORTS[1].encode("utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("second,second_usage,totals,completeness,error_code,unknown_turns", [
    ("length", SECOND_USAGE, COMPLETE_TOTALS, "complete", "provider.incomplete", []),
    ("http_error", {"prompt_tokens": 17, "prompt_cache_hit_tokens": 5},
     {"input_tokens": 28, "output_tokens": 4, "total_tokens": 15, "cached_input_tokens": 8,
      "reasoning_output_tokens": 2, "uncached_input_tokens": 8}, "partial", "provider.http", [1]),
    ("protocol_error", {"prompt_tokens": 17, "prompt_cache_hit_tokens": 5},
     {"input_tokens": 28, "output_tokens": 4, "total_tokens": 15, "cached_input_tokens": 8,
      "reasoning_output_tokens": 2, "uncached_input_tokens": 8}, "partial", "provider.protocol", [1]),
], ids=["truncated-with-complete-usage", "http-failure-with-observed-usage", "malformed-response-with-observed-usage"])
async def test_second_failed_writer_preserves_both_committed_usage_observations(
    tmp_path, monkeypatch, second, second_usage, totals, completeness, error_code, unknown_turns,
):
    calls = controlled_provider(monkeypatch, (FIRST_USAGE, second_usage), second=second)
    method = TwoWriterMethod()
    async with environment(tmp_path, method) as (engine, service):
        view = await execute(service)
        assert view.status == "failed" and view.error["code"] == error_code
        assert view.report_ref is None and len(calls) == 2
        assert len(method.outcomes) == 1 and method.reads == [REPORTS[0].encode("utf-8")]
        outcomes = await assert_recorded_usage(engine, service, view, totals, completeness, unknown_turns)
        assert outcomes[0]["event"]["payload"]["usage"]["input_tokens"] == 11
        assert outcomes[1]["event"]["payload"]["usage"]["input_tokens"] == 17
        first_ref = method.outcomes[0]["output_ref"]
        saved_first = await service.read_artifact(view.run_id, first_ref["artifact_id"])
        assert base64.b64decode(saved_first["data"]) == REPORTS[0].encode("utf-8")
        assert (await service.get_usage(view.run_id))["usage"] == view.usage
