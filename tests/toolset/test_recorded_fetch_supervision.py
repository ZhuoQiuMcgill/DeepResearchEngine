"""Recorded fetch supervision over real SQLite and immutable snapshot storage.

Only fetch processes are controlled. Proposals use production extraction and
packing; document.read launches the native worker against the real saved slice.
The pure supervisor helpers are reused without constructing Scenario or its clock.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sqlite3
from contextlib import asynccontextmanager, closing
from types import SimpleNamespace

import pytest

from deepresearch.engine.agent import RecordedToolAction
from deepresearch.engine.connections.engine import ToolPlanFactory
from deepresearch.engine.contracts import ArtifactRef, EngineError, Err, ToolRef, ToolRequest
from deepresearch.engine.storage import StorageSession
from deepresearch.engine.toolset import browser_capture, fetch_transport
from deepresearch.engine.toolset.common import LIMITS, ToolFault, digest, encode, strict_json
from deepresearch.engine.toolset.process import ProcessOutcome
from deepresearch.engine.toolset.retrieval import build_index, pack_component
from tests.toolset.test_fetch_supervisor import (
    BODY, COUNTS, FACT, OBSERVATIONS, Stage, attempt, components, html_body, proposal_for,
)
from tests.toolset.test_fetch_v2 import ARTICLE, URL
from tests.toolset.test_recorded_pipeline import setup


@pytest.fixture(autouse=True)
def prohibit_acquisition(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Integration tests must not acquire network resources or launch a browser")

    # Leave Windows asyncio's loopback wakeup sockets available for native reads.
    monkeypatch.setattr(fetch_transport.httpx, "Client", forbidden)
    monkeypatch.setattr(fetch_transport, "Session", forbidden)
    monkeypatch.setattr(browser_capture, "sync_playwright", forbidden)


def sql_rows(path, query, parameters=()):
    # A separate read-only connection proves visibility after SQLite COMMIT,
    # rather than trusting an in-memory event receipt or the writer connection.
    with closing(sqlite3.connect((path / "store.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(query, parameters)]


def persisted_events(path):
    return [json.loads(row["envelope"]) for row in sql_rows(path, "SELECT envelope FROM events ORDER BY seq")]


def publication_rows(path):
    return sql_rows(path, "SELECT operation_id, phase FROM operations WHERE method = 'snapshot.commit'")


def expected_policy():
    return {"id": "adaptive/2", "phases": ["static", "optional_render"],
        "max_worker_dispatches": 2, "max_snapshot_commits": 1,
        "http_request_limit": 40, "decoded_byte_limit": 32 << 20,
        "work_seconds_limit": 60, "stdout_bytes_limit": 20 << 20, "stderr_bytes_limit": 64 << 10}


class FetchRunner:
    """Observe durable intent at the last boundary before every fetch process."""

    def __init__(self, path, native, stages):
        self.path, self.native, self.stages = path, native, stages
        self.memory_bytes = native.memory_bytes
        self.calls, self.responses, self.native_reads = [], [], []

    async def run(self, argv, payload, **kwargs):
        request = strict_json(payload, LIMITS["stdin_bytes"])
        events = persisted_events(self.path)
        intents = [event for event in events if event["kind"] == "tool.intent"
            and event["context"]["action_id"] == request["invocation"]["action_id"]]
        assert len(intents) == 1, "Exactly one committed outer intent must precede dispatch"
        intent = intents[0]
        assert all(intent["context"][key] == value for key, value in request["invocation"].items())
        assert intent["payload"]["tool"] == request["tool"]
        assert not any(event["kind"] == "tool.outcome"
            and event["context"]["action_id"] == request["invocation"]["action_id"] for event in events)
        if request["tool"]["name"] == "document.read":
            self.native_reads.append(copy.deepcopy(request))
            return await self.native.run(argv, payload, **kwargs)

        assert request["tool"]["name"] == "web.fetch"
        assert len(self.calls) < len(self.stages), "Unexpected extra worker or replay"
        assert publication_rows(self.path) == [], "No intermediate capture may be committed"
        assert sql_rows(self.path, "SELECT object_id FROM snapshots") == []
        assert intent["payload"]["operation_id"] == request["plan"]["operation_id"]
        assert intent["payload"]["arguments"] == request["arguments"]
        revision = request["tool"]["revision"]
        if revision == 3:
            assert intent["payload"]["dispatch_policy"] == expected_policy()
            assert request["plan"]["stage"] == ("static" if not self.calls else "render")
            assert request["plan"]["extraction_config_ref"] == "adaptive/2"
            assert len(self.calls) < 2
        else:
            assert revision == 2
            assert "dispatch_policy" not in intent["payload"]
            assert "stage" not in request["plan"] and "network_grant" not in request["plan"]
            assert request["plan"]["extraction_config_ref"] == "adaptive/1"
            assert not self.calls
        if self.calls:
            first = self.calls[0]["request"]
            assert request["invocation"] == first["invocation"]
            assert request["plan"]["operation_id"] == first["plan"]["operation_id"]
            assert request["request_id"] != first["request_id"]

        stage = self.stages[len(self.calls)]
        kind = request["plan"].get("stage", "static")
        counts = stage.counts or (1, 1, len(stage.body))
        response = {key: copy.deepcopy(request[key]) for key in ("schema_version", "request_id", "tool", "invocation")}
        response.update(message_type="worker_response", phase="failed" if stage.error else "prepared",
            prepared=None, error=None, observations={}, usage={**dict(zip(COUNTS, counts)),
                "duration_ms": 100, "text_utf8_bytes": None, "monetary_cost": None})
        if stage.error:
            response["error"] = ToolFault(stage.error, "Controlled settled fetch failure",
                details={"failure_scope": "fetch"}).wire("observed")
            response["observations"] = {"http_status": 200, "redirects": [], "final_url": URL,
                "extraction_version": None, "representation": None,
                "fetch_attempts": [attempt(kind, counts, stage.error)]}
        elif not stage.termination and stage.raw is None:
            proposal = proposal_for(stage, kind, counts)
            response["prepared"] = {"operation_id": request["plan"]["operation_id"], "proposal": {
                **proposal, **{key: pack_component(proposal[key]) for key in ("original", "text", "index")}}}
            response["observations"] = {key: copy.deepcopy(proposal["provenance"][key]) for key in OBSERVATIONS}
            response["usage"]["text_utf8_bytes"] = len(proposal["text"])
        if stage.mutate:
            stage.mutate(response, request)
        data = stage.raw if stage.raw is not None else (b'{"prepared":' if stage.termination else encode(response))
        process = ProcessOutcome(exit_code=None if stage.termination else (3 if stage.error else 0),
            stdout=data, stdin_bytes=len(payload), stdout_bytes=len(data), stderr_bytes=11,
            termination_reason=stage.termination, cleanup_complete=stage.cleanup, pid=stage.pid,
            duration_ms=100, peak_job_memory_bytes=32 << 20, peak_process_memory_bytes=16 << 20)
        self.calls.append({"request": copy.deepcopy(request), "payload": payload,
            "process": process, "intent": intent, "limits": kwargs})
        self.responses.append(copy.deepcopy(response))
        return process

    async def close(self, deadline=None):
        return await self.native.close(deadline)


class PublicationProbe:
    def __init__(self, store, runner, lose_ack):
        self.store, self.runner, self.lose_ack = store, runner, lose_ack
        self.commits, self.lookups = [], []

    async def commit(self, context, operation_id, scope, proposal):
        self.commits.append((context, operation_id, scope, proposal))
        assert len(self.commits) == 1, "Snapshot publication must never recommit"
        assert len(self.runner.calls) == len(self.runner.stages)
        assert operation_id == self.runner.calls[0]["request"]["plan"]["operation_id"]
        result = await self.store.snapshots.commit(context, operation_id, scope, proposal)
        if self.lose_ack:
            result.unwrap()  # Lose only the acknowledgment of a real durable commit.
            return Err(EngineError("STORAGE_UNAVAILABLE", "Controlled lost commit acknowledgment",
                commit_state="unknown", retryable_delivery=True))
        return result

    async def status(self, context, operation_id):
        self.lookups.append(operation_id)
        assert self.lose_ack and len(self.lookups) == 1
        assert operation_id == self.commits[0][1]
        return await self.store.operations.status(context, operation_id)


@asynccontextmanager
async def integration(path, stages, *, lose_ack=False):
    store, context, binding = await setup(path)
    try:
        runner = FetchRunner(path, binding.executor.runner, stages)
        probe = PublicationProbe(store, runner, lose_ack)

        class Factory(ToolPlanFactory):
            def for_attempt(self, definition, *args):
                result = super().for_attempt(definition, *args)
                if definition.name == "web.fetch":
                    plan = result.unwrap()
                    plan.snapshot_store = plan.operation_store = probe
                return result

        binding.executor.runner = runner
        binding.storage_plan_factory = Factory(store, context.scope)
        yield SimpleNamespace(path=path, store=store, context=context, binding=binding,
            runner=runner, probe=probe)
    finally:
        try:
            assert (await binding.executor.close()).complete
        finally:
            (await store.close()).unwrap()


async def fetch(env, revision=3):
    return await RecordedToolAction().run(ToolRequest(ToolRef("web.fetch", revision), {"url": URL, "mode": "auto"}),
        env.binding, env.context.for_action("fetch-supervised", root_action_id="fetch-supervised"))


async def artifact_bytes(store, context, reference):
    reader = (await store.artifacts.open(context, ArtifactRef(**reference))).unwrap()
    try:
        chunk = (await reader.read(context, max_bytes=8 << 20)).unwrap()
        assert chunk.eof
        return chunk.bytes
    finally:
        (await reader.aclose(context)).unwrap()


async def assert_saved_components(store, context, result, expected):
    receipt = result.persistence["receipt"]
    assert result.persistence["commit_state"] == "committed"
    assert receipt["snapshot_ref"] == result.result["snapshot_ref"]
    for key, value in expected.items():
        assert await artifact_bytes(store, context, receipt[key + "_ref"]) == value
        assert receipt["component_digests"][key] == digest(value)
    manifest = strict_json(await artifact_bytes(store, context, receipt["manifest_ref"]), 256 << 10)
    assert manifest["provenance"] == result.result["provenance"]
    assert manifest["snapshot_ref"] == result.result["snapshot_ref"]


def assert_lifecycle(env, result, commits):
    events = persisted_events(env.path)
    tools = [event for event in events if event["kind"].startswith("tool.")]
    assert [event["kind"] for event in tools] == ["tool.intent", "tool.outcome"]
    intent, outcome = tools
    assert intent["event_id"] == result.event_ids["intent"]
    assert outcome["event_id"] == result.event_ids["outcome"]
    assert intent["context"]["attempt_id"] == outcome["context"]["attempt_id"] == result.invocation["attempt_id"]
    assert outcome["payload"]["process"] == result.process
    assert outcome["payload"]["observations"] == result.observations
    assert outcome["payload"]["persistence"] == result.persistence
    assert outcome["payload"]["status"] == result.status
    assert outcome["payload"]["intent_receipt"]["event_id"] == intent["event_id"]
    assert len(env.probe.commits) == commits
    assert len(publication_rows(env.path)) == commits
    assert len(sql_rows(env.path, "SELECT object_id FROM snapshots")) == commits
    saved = [event for event in events if event["kind"] == "snapshot.committed"]
    assert len(saved) == commits
    if commits:
        assert publication_rows(env.path) == [{"operation_id": result.persistence["operation_id"], "phase": "ready"}]
        assert saved[0]["payload"]["operation_id"] == result.persistence["operation_id"]
        assert events.index(intent) < events.index(saved[0]) < events.index(outcome)
    assert result.recording["status"] == "complete"


def assert_stage_records(env, result):
    rows = result.process["stages"]
    assert len(rows) == len(env.runner.calls) == 2
    for row, call in zip(rows, env.runner.calls):
        process, request = call["process"], call["request"]
        assert row["stage"] == request["plan"]["stage"]
        assert row["request_id"] == request["request_id"]
        assert row["request_sha256"] == digest(call["payload"])
        assert row["response_sha256"] == digest(process.stdout)
        assert row["cleanup_complete"] is process.cleanup_complete
        assert row["termination_reason"] == process.termination_reason
    assert result.process["total_stdout_bytes"] == sum(call["process"].stdout_bytes for call in env.runner.calls)
    assert result.process["total_stderr_bytes"] == 22
    assert result.process["cleanup"]["complete"] is all(call["process"].cleanup_complete for call in env.runner.calls)


def test_memory_limited_renderer_commits_exact_static_and_native_read_survives_reopen(tmp_path):
    async def check():
        path = tmp_path / "store"
        stages = [Stage(counts=(2, 2, 150000)), Stage(termination="memory_limit")]
        async with integration(path, stages) as env:
            result = await fetch(env)
            assert result.status == "succeeded", result.error
            assert_lifecycle(env, result, 1)
            assert_stage_records(env, result)
            assert env.probe.lookups == []
            assert result.process["selected_stage"] == "static"
            diagnostic = result.observations["fetch_supervision"]
            assert diagnostic == result.result["provenance"]["fetch_supervision"]
            assert diagnostic["decision"] == "static_retained_after_termination"
            assert diagnostic["render_outcome"] == "terminated"
            assert diagnostic["render_error_code"] == "MEMORY_LIMIT"
            assert diagnostic["network_usage_complete"] is False
            assert diagnostic["render_request_grant"] == 38
            assert diagnostic["render_decoded_byte_grant"] == (32 << 20) - 150000
            assert env.runner.calls[1]["request"]["plan"]["network_grant"] == {
                "requests": 38, "decoded_bytes": (32 << 20) - 150000}
            for key, lower_bound in zip(COUNTS, (2, 2, 150000)):
                assert result.usage[key] is None
                assert diagnostic["known_" + key] == lower_bound
                assert diagnostic["render_" + key] is None
                assert result.observations["fetch_attempts"][-1][key] is None
                assert result.process["stages"][-1][key] is None
            assert result.result["provenance"]["http_request_count"] is None
            assert result.result["provenance"]["http_response_count"] is None
            expected = components(env.runner.responses[0])
            assert expected["original"] == stages[0].body
            assert strict_json(expected["index"], LIMITS["index_bytes"]) == build_index(expected["text"], None)
            assert result.usage["text_utf8_bytes"] == len(expected["text"])
            await assert_saved_components(env.store, env.context, result, expected)
            read = await RecordedToolAction().run(ToolRequest(ToolRef("document.read"), {
                "snapshot_ref": result.result["snapshot_ref"], "range": {
                    "kind": "lines", "start": 1, "end_exclusive": result.result["line_count"] + 1}}),
                env.binding, env.context.for_action("native-read", root_action_id="native-read"))
            assert read.status == "succeeded", read.error
            assert read.recording["status"] == "complete" and read.process["cleanup"]["complete"]
            assert read.result["text"].encode() == expected["text"]
            assert read.result["continuation"] is None
            assert len(env.runner.native_reads) == 1 and len(env.runner.calls) == 2
            context, store_id = env.context, env.store.store_id
        reopened = (await StorageSession.open({"root": path})).unwrap()
        try:
            assert reopened.store_id == store_id
            await assert_saved_components(reopened, context, result, expected)
            saved_read = (await reopened.snapshots.read(context, result.result["snapshot_ref"], {
                "kind": "lines", "start": 1, "end_exclusive": result.result["line_count"] + 1})).unwrap()
            assert saved_read.text.encode() == expected["text"]
            assert len(publication_rows(path)) == 1
        finally:
            (await reopened.close()).unwrap()
    asyncio.run(check())


@pytest.mark.parametrize("renderer,error,status", [
    (Stage(termination="memory_limit", cleanup=False), "CLEANUP_INCOMPLETE", "failed"),
    (Stage(cleanup=False), "CLEANUP_INCOMPLETE", "failed"),
    (Stage(termination="cancelled"), "CANCELLED", "cancelled"),
    (Stage(raw=b"{"), "INVALID_JSON", "validation_failed"),
    (Stage(raw=b"{}"), "INVALID_ARGUMENT", "validation_failed"),
], ids=["killed-cleanup-unknown", "prepared-cleanup-unknown", "cancelled", "malformed-json", "malformed-envelope"])
def test_renderer_failure_aborts_recorded_attempt_without_snapshot(tmp_path, renderer, error, status):
    async def check():
        async with integration(tmp_path / "store", [Stage(), renderer]) as env:
            result = await fetch(env)
            assert result.status == status and result.error.code == error
            assert result.result is None
            assert result.persistence["commit_state"] == "not_committed"
            assert result.persistence["receipt"] is None
            assert_lifecycle(env, result, 0)
            assert_stage_records(env, result)
            assert env.probe.lookups == []
    asyncio.run(check())


@pytest.mark.parametrize("kind", ["requests", "responses", "bytes", "negative", "boolean", "missing", "attempt-mismatch"])
@pytest.mark.parametrize("phase", ["prepared", "failed"])
def test_renderer_invalid_network_accounting_never_commits_static(tmp_path, kind, phase):
    def corrupt(response, request):
        key = {"requests": "http_request_count", "responses": "http_response_count",
            "bytes": "decoded_body_bytes"}.get(kind, "http_request_count")
        if kind == "missing":
            # The backend attempt still claims an exact count. Omitting that
            # same stage total must not authorize inconsistent saved accounting.
            response["usage"].pop(key)
            return
        if kind == "attempt-mismatch":
            response["observations"]["fetch_attempts"][0][key] += 1
            if phase == "prepared":
                response["prepared"]["proposal"]["provenance"]["fetch_attempts"][0][key] += 1
            return
        value = {"requests": request["plan"]["network_grant"]["requests"] + 1,
            "responses": 4, "bytes": request["plan"]["network_grant"]["decoded_bytes"] + 1,
            "negative": -1, "boolean": True}[kind]
        response["usage"][key] = value
        response["observations"]["fetch_attempts"][0][key] = value
        if phase == "prepared":
            provenance = response["prepared"]["proposal"]["provenance"]
            provenance["fetch_attempts"][0][key] = value
            if key != "decoded_body_bytes":
                provenance[key] = value

    async def check():
        renderer = Stage(body=html_body(BODY + "<p>" + FACT + "</p>", scripts=False),
            counts=(3, 2, 10000), error="FETCH_UNAVAILABLE" if phase == "failed" else None, mutate=corrupt)
        async with integration(tmp_path / "store", [Stage(counts=(2, 2, 150000)), renderer]) as env:
            result = await fetch(env)
            assert result.status == "failed" and result.error.code == "WORKER_PROTOCOL_ERROR", {
                "status": result.status, "commit_state": result.persistence["commit_state"],
                "snapshot_operations": publication_rows(env.path), "usage": result.usage,
                "fetch_attempts": result.observations.get("fetch_attempts"),
                "supervision": result.observations.get("fetch_supervision")}
            assert result.result is None and result.persistence["commit_state"] == "not_committed"
            assert_lifecycle(env, result, 0)
            assert_stage_records(env, result)
            assert env.probe.lookups == []
    asyncio.run(check())


@pytest.mark.parametrize("render", [False, True], ids=["one-worker", "two-workers"])
def test_lost_snapshot_commit_ack_reconciles_once_without_worker_or_commit_replay(tmp_path, render):
    async def check():
        stages = [Stage(), Stage(body=html_body(BODY + "<p>" + FACT + "</p>", scripts=False))] if render else [Stage(body=ARTICLE)]
        async with integration(tmp_path / "store", stages, lose_ack=True) as env:
            result = await fetch(env)
            assert result.status == "succeeded", result.error
            assert_lifecycle(env, result, 1)
            assert env.probe.lookups == [result.persistence["operation_id"]]
            assert len(env.runner.calls) == len(stages)
            selected = "render" if render else "static"
            assert result.process["selected_stage"] == selected
            if render:
                assert_stage_records(env, result)
                assert result.observations["fetch_supervision"]["decision"] == "rendered_with_preservation"
            expected = components(env.runner.responses[-1])
            await assert_saved_components(env.store, env.context, result, expected)
    asyncio.run(check())


def test_revision_two_remains_single_worker_without_supervision_policy(tmp_path):
    async def check():
        # The same thin scripted body triggers a second stage only in revision 3.
        async with integration(tmp_path / "store", [Stage()]) as env:
            result = await fetch(env, revision=2)
            assert result.status == "succeeded", result.error
            assert_lifecycle(env, result, 1)
            assert len(env.runner.calls) == 1 and env.probe.lookups == []
            assert "stages" not in result.process and "selected_stage" not in result.process
            assert "fetch_supervision" not in result.observations
            assert "fetch_supervision" not in result.result["provenance"]
            for key, count in zip(COUNTS, (1, 1, len(env.runner.stages[0].body))):
                assert result.usage[key] == count
            await assert_saved_components(env.store, env.context, result, components(env.runner.responses[0]))
    asyncio.run(check())
