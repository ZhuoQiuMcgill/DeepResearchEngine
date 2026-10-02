"""Formal method policy over actual Runtime, recorder, SQLite and read workers."""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from deepresearch.bootstrap import create_method_registry, create_research_service
from deepresearch.engine import Engine, EngineSettings
from deepresearch.engine.contracts import SnapshotProposal, ToolExecutionResult, canonical_json, digest_bytes
from deepresearch.engine.providers import ProviderConfig, ProviderFactory
from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDecision
from deepresearch.methods.baseline.contracts import EvidenceAnalysis, ResearchPlan, ReportReview
from deepresearch.methods.baseline.stages.reporting import citation_issues
from deepresearch.workflows import ResearchRunRequest

QUESTION = "What does retained alpha evidence show?"
PLAN = {"schema_version": 1, "objective": "Investigate retained alpha evidence",
        "questions": [QUESTION], "queries": ["literal alpha"], "outline": ["Findings", "Limitations", "References"]}


def analysis(*, sufficient=True, source="requested-001"):
    return {"schema_version": 1, "findings": [{"finding_id": "f1", "question": QUESTION,
        "claim": "Alpha evidence supports a qualified finding.", "source_ids": [source]}],
        "gaps": [] if sufficient else ["Need a second retained source"],
        "follow_up_queries": [] if sufficient else ["alpha follow up"], "sufficient": sufficient}


ACCEPT = {"schema_version": 1, "verdict": "accept", "issues": []}
REPORT = "# Qualified answer\n\nAlpha evidence supports the finding [requested-001].\n\n## Limitations\nOnly selected text was reviewed.\n"


async def settle(service, run_id):
    for _ in range(2000):
        view = await service.get_run(run_id)
        if not view.active:
            return view
        await asyncio.sleep(.01)
    pytest.fail("Formal method did not settle")


async def configured(tmp_path, monkeypatch, outputs, *, failed_url=None, unknown=False, gate=None, extensions=None):
    calls, fetched, searches = [], [], []
    original_open = ProviderFactory.open
    async def handler(request):
        calls.append(json.loads(request.content))
        if gate is not None and len(calls) == 2:
            gate[0].set()
            await gate[1].wait()
        assert len(calls) <= len(outputs), "Method exceeded its expected model-call bound"
        value = outputs[len(calls) - 1]
        content = value if isinstance(value, str) else json.dumps(value)
        return httpx.Response(200, json={"id": "controlled-baseline", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}})
    async def controlled_open(config, context):
        return await original_open(config, context, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    profile = ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "controlled-test-key")
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", profiles={"controlled": profile})
    engine = (await Engine.open(settings)).unwrap()
    native_execute = engine.executor.execute
    async def tool(definition, arguments, context, plan):
        if definition.name == "document.read":
            return await native_execute(definition, arguments, context, plan)
        result = ToolExecutionResult(definition.ref, context.descriptor(), "succeeded",
            process={"dispatched": True, "cleanup": {"complete": True}})
        plan.assert_recorded()
        if definition.name in {"web.search", "scholar.crossref.search"}:
            searches.append(arguments["query"])
            url = "https://example.org/second" if arguments["query"] == "alpha follow up" else "https://example.org/first"
            result.result = {"results": [{"rank": 1, "url": url, "title": "DISCOVERY_ONLY_SECRET_MARKER",
                                           "snippet": "DISCOVERY_SNIPPET_SECRET_MARKER"}]}
            return result
        assert definition.name == "web.fetch"
        fetched.append(arguments["url"])
        if arguments["url"] == failed_url:
            result.status = "failed"
            result.error = {"code": "FETCH_HTTP_ERROR", "message": "Controlled forbidden source"}
            result.persistence = {"required": True, "commit_state": "unknown" if unknown else "not_committed"}
            return result
        text = ("alpha retained evidence\n" + "background\n" * 199 + "UNSELECTED_SECRET_MARKER\n").encode()
        lines, offset = [], 0
        for number, line in enumerate(text.splitlines(keepends=True), 1):
            lines.append({"line": number, "start_byte": offset, "end_byte": offset + len(line.rstrip(b"\n"))})
            offset += len(line)
        index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text), "lines": lines, "pages": None}
        receipt = (await plan.snapshot_store.commit(context, plan.operation_id, plan.scope,
            SnapshotProposal(text, text, canonical_json(index), {"url": arguments["url"]}))).unwrap()
        result.result = {"snapshot_ref": receipt.snapshot_ref.to_dict(), "line_count": len(lines), "page_count": None,
            "provenance": {"text_bytes": len(text), "text_sha256": digest_bytes(text), "url": arguments["url"]}}
        result.persistence = {"required": True, "commit_state": "committed", "operation_id": plan.operation_id,
                              "receipt": receipt.to_dict()}
        return result
    monkeypatch.setattr(engine.executor, "execute", tool)
    service = create_research_service(engine, extensions=extensions)
    return engine, service, settings, calls, fetched, searches


def request(**parameters):
    return ResearchRunRequest(client_request_id="formal-baseline", method_id="baseline", method_revision=2,
        profile_ref="controlled", model_ref="deepseek-flash", input={"question": QUESTION}, timeout_seconds=60.0,
        parameters={"source_urls": ["https://example.org/first"], "search_tools": ["web.search"],
                    "max_scan_bytes": 1024, "context_tokens": 512, **parameters})


async def close(engine, service):
    assert (await service.close()).complete
    assert (await engine.close()).complete


@pytest.mark.asyncio
async def test_two_research_rounds_revision_and_reopen_use_real_saved_artifacts(tmp_path, monkeypatch):
    outputs = [PLAN, analysis(sufficient=False), analysis(source="r2.source-001"),
               "Draft cites an invented source [invented-999].",
               {"schema_version": 1, "verdict": "revise", "issues": ["Replace the unsupported citation"]},
               REPORT + "Follow-up confirms the finding [r2.source-001].\n", ACCEPT]
    engine, service, settings, calls, fetched, searches = await configured(tmp_path, monkeypatch, outputs)
    try:
        admitted = await service.start_run(request())
        view = await settle(service, admitted.run_id)
        assert view.status == "succeeded", view.error
        assert view.recording_status == "complete" and view.report_ref
        assert len(calls) == 7 and view.usage["known_subtotals"]["total_tokens"] == 196
        assert len(view.usage["per_attempt_usage_refs"]) == 7
        assert fetched == ["https://example.org/first", "https://example.org/second"]
        assert searches == ["literal alpha", "alpha follow up"]
        serialized = json.dumps(calls)
        assert "DISCOVERY_SNIPPET_SECRET_MARKER" not in serialized
        assert "DISCOVERY_ONLY_SECRET_MARKER" not in serialized and "UNSELECTED_SECRET_MARKER" not in serialized
        assert all(not call.get("tools") for call in calls)
        assert len(view.sources.items) == 2 and view.context_plan.recipient_role == "baseline.writer"
        assert all(node.status == "succeeded" for node in view.nodes)
        assert {node.node_id for node in view.nodes} >= {"plan.research", "r2.analyze.evidence", "report.2.review", "publish.result"}
        raw = await service.read_report(view.run_id)
        report_bytes = base64.b64decode(raw["data"])
        manifest = await service.read_artifact(view.run_id, view.result_manifest_ref.artifact_id)
        result = json.loads(base64.b64decode(manifest["data"]))
        assert result["method_revision"] == 2 and len(result["rounds"]) == 2
        assert result["stop_reason"] == "evidence_sufficient"
        assert [draft["accepted"] for draft in result["drafts"]] == [False, True]
        assert (await service.start_run(request())).run_id == view.run_id and len(calls) == 7
    finally:
        await close(engine, service)
    engine2 = (await Engine.open(settings)).unwrap()
    service2 = create_research_service(engine2)
    try:
        restored = await service2.start_run(request())
        assert restored.run_id == view.run_id and restored.status == "succeeded"
        assert base64.b64decode((await service2.read_report(view.run_id))["data"]) == report_bytes
        assert len(calls) == 7 and len(fetched) == 2
    finally:
        await close(engine2, service2)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["unknown_citation", "unknown_finding", "unresolved_review"])
async def test_invalid_evidence_or_review_never_publishes_successful_report(tmp_path, monkeypatch, case):
    outputs = [PLAN, analysis(source="not-selected" if case == "unknown_finding" else "requested-001")]
    if case != "unknown_finding":
        outputs += ["Invalid citation [unknown-001]." if case == "unknown_citation" else REPORT,
            ACCEPT if case == "unknown_citation" else {"schema_version": 1, "verdict": "revise", "issues": ["A key finding is unsupported"]}]
    engine, service, _, calls, _, _ = await configured(tmp_path, monkeypatch, outputs)
    try:
        view = await settle(service, (await service.start_run(request(max_report_attempts=1))).run_id)
        assert view.status == "failed" and view.report_ref is None
        assert view.error["code"] == ("INVALID_EVIDENCE_REFERENCE" if case == "unknown_finding" else "REPORT_REVIEW_FAILED")
        assert view.sources.items[0].status == "succeeded" and view.checkpoint_ref
        assert len(calls) == len(outputs)
    finally:
        await close(engine, service)


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [False, True])
async def test_failed_sources_are_retained_and_unknown_commit_is_never_refetched(tmp_path, monkeypatch, unknown):
    outputs = [PLAN, analysis(), REPORT, ACCEPT]
    engine, service, _, calls, fetched, _ = await configured(tmp_path, monkeypatch, outputs,
        failed_url="https://example.org/failed", unknown=unknown)
    try:
        view = await settle(service, (await service.start_run(request(
            source_urls=["https://example.org/first", "https://example.org/failed"]))).run_id)
        assert fetched.count("https://example.org/failed") == 1
        assert view.sources.items[0].status == "succeeded"
        if unknown:
            assert view.status != "succeeded" and view.report_ref is None and len(calls) == 1
        else:
            assert view.status == "succeeded", view.error
            assert view.sources.items[1].status == "failed" and len(calls) == 4
    finally:
        await close(engine, service)


@pytest.mark.asyncio
async def test_cancellation_during_analysis_preserves_sources_plan_and_recorded_usage(tmp_path, monkeypatch):
    gate = (asyncio.Event(), asyncio.Event())
    engine, service, _, calls, fetched, _ = await configured(tmp_path, monkeypatch, [PLAN, analysis()], gate=gate)
    try:
        run_id = (await service.start_run(request())).run_id
        await asyncio.wait_for(gate[0].wait(), 10)
        await service.cancel_run(run_id)
        view = await settle(service, run_id)
        assert view.status == "cancelled", view.error
        assert view.report_ref is None and view.sources.items[0].status == "succeeded"
        assert view.checkpoint_ref and view.usage["known_subtotals"]["total_tokens"] == 28
        assert len(calls) == 2 and len(fetched) == 1
    finally:
        gate[1].set()
        await close(engine, service)


@pytest.mark.asyncio
@pytest.mark.parametrize("hooked", [False, True])
async def test_formal_method_runs_with_optional_observation_and_selection_hooks(tmp_path, monkeypatch, hooked):
    extensions = ExtensionRegistry()
    observed = []
    if hooked:
        async def observe(event):
            observed.append((event.node_id, event.point))
            assert set(event.payload) == {"kind", "status", "detail_sha256"}
        async def select(event, candidate_ids):
            return HookDecision(keep_ids=tuple(candidate_ids[:1]))
        extensions.register(ExtensionSpec(extension_id="test.observe", revision="1",
            points=("node.before", "node.after", "node.failed"), mode="observe"), observe)
        extensions.register(ExtensionSpec(extension_id="test.select", revision="1",
            points=("discovery.select", "context.select"), mode="control"), select)
    engine, service, _, calls, fetched, _ = await configured(tmp_path, monkeypatch,
        [PLAN, analysis(), REPORT, ACCEPT], extensions=extensions)
    try:
        view = await settle(service, (await service.start_run(request(
            source_urls=["https://example.org/first", "https://example.org/second"]))).run_id)
        assert view.status == "succeeded", view.error
        assert len(calls) == 4 and len(fetched) == (1 if hooked else 2)
        events, position = [], 0
        while True:
            page = await service.events(view.run_id, position)
            events.extend(page["events"])
            position = page["next_after_seq"]
            if not page["has_more"]:
                break
        kinds = [row["event"]["kind"] for row in events]
        if hooked:
            assert {node.node_id for node in view.nodes} == {node_id for node_id, point in observed if point == "node.before"}
            assert {node.node_id for node in view.nodes} == {node_id for node_id, point in observed if point == "node.after"}
            assert "workflow.hook.decision" in kinds and "workflow.hook.failed" not in kinds
        else:
            assert not observed and "workflow.hook.decision" not in kinds
    finally:
        await close(engine, service)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,options", [
    ("source_limit", {"max_sources": 1}),
    ("round_limit", {"max_rounds": 1}),
    ("no_new_queries", {}),
])
async def test_bounded_stop_keeps_evidence_gaps_in_an_accepted_limited_report(tmp_path, monkeypatch, reason, options):
    assessment = analysis(sufficient=False)
    if reason == "no_new_queries":
        assessment["follow_up_queries"] = []
    engine, service, _, calls, fetched, searches = await configured(tmp_path, monkeypatch,
        [PLAN, assessment, REPORT, ACCEPT])
    try:
        view = await settle(service, (await service.start_run(request(**options))).run_id)
        assert view.status == "succeeded", view.error
        result = json.loads(base64.b64decode((await service.read_artifact(view.run_id,
            view.result_manifest_ref.artifact_id))["data"]))
        assert result["stop_reason"] == reason and len(result["rounds"]) == 1
        assert result["rounds"][0]["sufficient"] is False
        assert len(calls) == 4 and len(fetched) == 1 and searches == ["literal alpha"]
        assert "Need a second retained source" in json.dumps(calls[-2:])
    finally:
        await close(engine, service)


@pytest.mark.asyncio
async def test_no_usable_snapshot_stops_before_analysis_and_report(tmp_path, monkeypatch):
    engine, service, _, calls, fetched, _ = await configured(tmp_path, monkeypatch, [PLAN],
        failed_url="https://example.org/first")
    try:
        view = await settle(service, (await service.start_run(request())).run_id)
        assert view.status == "failed" and view.error["code"] == "NO_EVIDENCE"
        assert view.report_ref is None and view.sources.items[0].status == "failed"
        assert len(calls) == 1 and len(fetched) == 1
    finally:
        await close(engine, service)


def test_versions_and_decision_contracts_are_explicit():
    methods = create_method_registry().list()
    assert {(method["method_id"], method["revision"]) for method in methods} == {("baseline", 1), ("baseline", 2), ("example.echo", 1)}
    assert ResearchPlan.model_validate(PLAN).queries == ["literal alpha"]
    assert EvidenceAnalysis.model_validate(analysis()).to_dict()["findings"][0].get("schema_version") is None
    with pytest.raises(ValueError):
        ReportReview.model_validate({"schema_version": 1, "verdict": "accept", "issues": ["Unresolved issue"]})
    assert citation_issues(REPORT, ["requested-001"]) == []
    assert citation_issues(REPORT + "[invented]", ["requested-001"])
