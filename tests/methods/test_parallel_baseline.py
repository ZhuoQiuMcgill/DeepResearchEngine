"""Baseline 5 through real Engine/Runtime/SQLite and controlled provider HTTP.

Only discovery/fetch responses and model HTTP are controlled. Saved document
reads, role admission, child lifecycle, publication and restart use the platform.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from deepresearch.agent_catalog.catalog import AgentSpec
from deepresearch.bootstrap import create_research_service
from deepresearch.engine import Engine, EngineSettings
from deepresearch.engine.contracts import SnapshotProposal, ToolExecutionResult, canonical_json, digest_bytes
from deepresearch.engine.providers import ProviderConfig, ProviderFactory
from deepresearch.engine.storage._ranges import line_spans
from deepresearch.methods.baseline.parallel_workflow import substantive_work_count
from deepresearch.workflows import ResearchRunRequest
from deepresearch.workflows.contracts import SnapshotReference, SourceManifest, SourceRecord
from deepresearch.workflows.components.parallel import bounded_map


QUESTION = "What does the retained method establish?"
PLAN = {
    "schema_version": 1,
    "objective": "Describe the retained method using documented evidence",
    "questions": ["What is the method?", "Which steps does it use?"],
    "queries": ["retained method"],
    "outline": ["Definition", "Process", "Limitations", "References"],
}
ACCEPT = {"schema_version": 1, "verdict": "accept", "issues": []}
CITED_PUBLICATION_TITLE = "alternate method"
CITED_TITLE_QUERY = '"alternate method"'
ALPHA = "https://example.org/alpha"
BETA = "https://example.org/beta"


def _copy(value):
    return json.loads(json.dumps(value))


@dataclass(frozen=True)
class Document:
    text: str
    pages: tuple[str, ...] | None = None
    media_type: str | None = None

    def index(self):
        raw = self.text.encode("utf-8")
        spans, offset = None, 0
        if self.pages is not None:
            assert self.text == "\n".join(self.pages)
            spans = []
            for number, page in enumerate(self.pages, 1):
                end = offset + len(page.encode("utf-8"))
                spans.append({"page": number, "start_byte": offset, "end_byte": end})
                offset = end + 1
        return {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(raw),
                "lines": line_spans(raw), "pages": spans}


def _paper(marker, *, pages=12, page_words=12):
    bodies = tuple(
        f"{marker} page {number}: the method starts with requirements and resolves contradictions.\n"
        + "Documented process combines environment analysis and solution synthesis. " * page_words
        + f"\n{marker}_TAIL_{number:02d} documents the concluding method step."
        for number in range(1, pages + 1)
    )
    return Document("\n".join(bodies), bodies)


def _lines(marker, *, count=40):
    return Document("\n".join(
        f"{marker} line {number}: documented method requirements, analysis and synthesis."
        for number in range(1, count + 1)
    ) + f"\n{marker}_FINAL_LINE documents the concluding method step.")


def _boilerplate():
    return Document("PAYWALL_ONLY Publisher account access. "
        + "Subscription benefits, institutional account support, terms of service, and privacy preferences. " * 70
        + "\nNo research method is supplied by this account page.")


def _distillation(value):
    segment = next(item for item in reversed(value["segments"]) if item["text"].strip())
    quote = segment["text"].splitlines()[-1][:180]
    return {
        "schema_version": 1, "source_id": value["source"]["source_id"], "chunk_id": value["chunk_id"],
        "content_kind": value["source"]["content_hint"],
        "summary": "The archived passage describes a method and its documented steps.",
        "findings": [{"question": question, "claim": "The recorded passage supports a local method description.",
                      "segment_id": segment["segment_id"], "quote": quote}
                     for question in value["plan"]["questions"]],
        "limitations": [], "reference_queries": [],
    }


def _analysis(value, *, sufficient=True, queries=(), reads=()):
    return {
        "schema_version": 1,
        "findings": [{"finding_id": f"finding-{index}", "question": question,
                      "claim": "The retained source documents requirements, analysis and synthesis.",
                      "source_ids": value["available_source_ids"][:8]}
                     for index, question in enumerate(value["plan"]["questions"], 1)],
        "gaps": [] if sufficient else ["A required corroborating source remains unavailable."],
        "follow_up_queries": list(queries), "follow_up_reads": list(reads), "sufficient": sufficient,
    }


def _report(value):
    citations = " ".join(f"[{source}]" for source in value["analysis"]["findings"][0]["source_ids"])
    gaps = "; ".join(value["quality"]["gaps"] + value["quality"]["reasons"])
    return (f"# Retained method\n\nResearch coverage: {value['quality']['status']}\n\n"
            f"The documented method uses requirements, analysis and synthesis {citations}.\n\n"
            f"## Limitations\n{gaps or 'The answer is scoped to the retained documents.'}\n")


@dataclass
class Harness:
    engine: Any
    service: Any
    settings: EngineSettings
    calls: list = field(default_factory=list)
    fetched: list = field(default_factory=list)
    searches: list = field(default_factory=list)
    reads: list = field(default_factory=list)

    def role_calls(self, role):
        return [call for call in self.calls if call["role"] == "baseline." + role]


@asynccontextmanager
async def _configured(tmp_path, monkeypatch, documents, *, respond=None, discover=None):
    """Observe validated role inputs while preserving native rendering/execution."""
    rendered_inputs = {}
    original_render = AgentSpec.render_task

    def observe_render(spec, value):
        rendered = original_render(spec, value)
        rendered_inputs[rendered] = (spec.role_id, spec.revision, _copy(value))
        return rendered

    monkeypatch.setattr(AgentSpec, "render_task", observe_render)
    original_open = ProviderFactory.open
    harness = None

    async def http(request):
        body = json.loads(request.content)
        task = body["messages"][-1]["content"]
        role, revision, value = rendered_inputs[task]
        assert not body.get("tools"), "Host research roles must not fetch inside their conversations"
        harness.calls.append({"role": role, "revision": revision, "input": value, "request": body})
        ordinal = sum(call["role"] == role for call in harness.calls)
        output = respond(role, value, ordinal) if respond is not None else None
        if inspect.isawaitable(output):
            output = await output
        if output is None:
            if role == "baseline.planner":
                output = _copy(PLAN)
            elif role == "baseline.distiller":
                output = _distillation(value)
            elif role == "baseline.analyst":
                output = _analysis(value)
            elif role == "baseline.writer":
                output = _report(value)
            else:
                assert role == "baseline.reviewer"
                output = ACCEPT
        content = output if isinstance(output, str) else json.dumps(output)
        return httpx.Response(200, json={"id": f"controlled-{role}-{ordinal}", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}})

    async def controlled_open(config, context=None):
        return await original_open(config, context, transport=httpx.MockTransport(http))

    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    profile = ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "controlled-test-key")
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", profiles={"controlled": profile})
    engine = (await Engine.open(settings)).unwrap()
    harness = Harness(engine, create_research_service(engine), settings)
    native_execute = engine.executor.execute

    async def tool(definition, arguments, context, plan):
        if definition.name == "document.read":
            harness.reads.append(_copy(arguments))
            return await native_execute(definition, arguments, context, plan)
        plan.assert_recorded()
        result = ToolExecutionResult(definition.ref, context.descriptor(), "succeeded",
            process={"dispatched": True, "cleanup": {"complete": True}})
        if definition.name in {"web.search", "scholar.crossref.search", "scholar.openalex.search"}:
            harness.searches.append((definition.name, arguments["query"]))
            rows = discover(definition.name, arguments["query"]) if discover is not None else []
            result.result = {"results": rows}
            return result
        assert definition.name == "web.fetch", "Unexpected external tool in controlled research"
        url = arguments["url"]
        harness.fetched.append(url)
        assert url in documents, f"Unexpected unconfigured source: {url}"
        document = documents[url]
        if document is None:
            result.status = "failed"
            result.error = {"code": "FETCH_HTTP_ERROR", "message": "Controlled HTTP 403", "details": {"http_status": 403}}
            result.persistence = {"required": True, "commit_state": "not_committed"}
            return result
        raw = document.text.encode("utf-8")
        index = document.index()
        media = {"media_type": document.media_type} if document.media_type is not None else {}
        receipt = (await plan.snapshot_store.commit(context, plan.operation_id, plan.scope,
            SnapshotProposal(raw, raw, canonical_json(index), {"url": url, "controlled_fixture": True, **media}))).unwrap()
        result.result = {"snapshot_ref": receipt.snapshot_ref.to_dict(), "line_count": len(index["lines"]),
            "page_count": len(document.pages) if document.pages is not None else None,
            "provenance": {"text_bytes": len(raw), "text_sha256": digest_bytes(raw), "url": url, **media}}
        result.persistence = {"required": True, "commit_state": "committed", "operation_id": plan.operation_id,
                              "receipt": receipt.to_dict()}
        return result

    monkeypatch.setattr(engine.executor, "execute", tool)
    try:
        yield harness
    finally:
        await _close(engine, harness.service)


def _request(**parameters):
    return ResearchRunRequest(client_request_id="parallel-baseline", method_id="baseline", method_revision=5,
        profile_ref="controlled", model_ref="deepseek-flash", input={"question": QUESTION}, timeout_seconds=120.0,
        parameters={"source_urls": [ALPHA], "search_tools": ["web.search"], "recovery_queries": 0, **parameters})


async def _settle(service, run_id, *, seconds=90):
    async with asyncio.timeout(seconds):
        while True:
            view = await service.get_run(run_id)
            if not view.active:
                return view
            await asyncio.sleep(.01)


async def _close(engine, service):
    assert (await service.close()).complete
    assert (await engine.close()).complete


async def _bytes(service, run_id, ref):
    parts, offset = [], 0
    while True:
        page = await service.read_artifact(run_id, ref["artifact_id"], start=offset)
        parts.append(base64.b64decode(page["data"]))
        if page["eof"]:
            return b"".join(parts)
        assert page["next_offset"] > offset
        offset = page["next_offset"]


async def _json(service, run_id, ref):
    return json.loads(await _bytes(service, run_id, ref))


async def _events(service, run_id):
    rows, offset = [], 0
    while True:
        page = await service.events(run_id, offset)
        rows.extend(page["events"])
        offset = page["next_after_seq"]
        if not page["has_more"]:
            return [row["event"] for row in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_revision", [5, 6])
async def test_simultaneous_distillers_isolate_sources_and_deliver_saved_pdf_tails(tmp_path, monkeypatch, method_revision):
    both_started, release = asyncio.Event(), asyncio.Event()
    active, peak = 0, 0
    documents = {ALPHA: _paper("ALPHA_ONLY"), BETA: _paper("BETA_ONLY")}

    async def respond(role, value, ordinal):
        nonlocal active, peak
        if role != "baseline.distiller":
            return None
        active += 1
        peak = max(peak, active)
        if active >= 2:
            both_started.set()
        try:
            await release.wait()
            return _distillation(value)
        finally:
            active -= 1

    async with _configured(tmp_path, monkeypatch, documents, respond=respond) as h:
        request = _request(source_urls=[ALPHA, BETA]).model_copy(update={"method_revision": method_revision})
        run_id = (await h.service.start_run(request)).run_id
        try:
            try:
                await asyncio.wait_for(both_started.wait(), 20)
            except TimeoutError:
                current = await h.service.get_run(run_id)
                pytest.fail(f"Two Distillers did not reach the gate: status={current.status}; error={current.error}; calls={len(h.calls)}")
            assert active == peak == 2
            calls = h.role_calls("distiller")
            assert len(calls) == 2
            for call in calls:
                value = call["input"]
                marker, excluded = ("ALPHA_ONLY", "BETA_ONLY") if value["source"]["url"] == ALPHA else ("BETA_ONLY", "ALPHA_ONLY")
                assert value["question"] == QUESTION and value["plan"]["questions"] == PLAN["questions"]
                assert value["source"]["complete_read"] is True
                text = json.dumps(value["segments"])
                assert marker in text and excluded not in text
                raw = documents[value["source"]["url"]].text.encode("utf-8")
                for segment in value["segments"]:
                    exact = raw[segment["start_byte"]:segment["end_byte"]]
                    assert segment["text"].encode("utf-8") == exact
                    assert segment["text_sha256"] == digest_bytes(exact)
                    assert segment["read_action_id"]
        finally:
            release.set()
        view = await _settle(h.service, run_id)
        assert view.status == "succeeded", view.error
        assert view.recording_status == "complete" and view.quality.status == "sufficient"
        assert view.quality.substantive_sources == view.quality.fully_read_sources == 2
        for role in ("analyst", "writer", "reviewer"):
            value = h.role_calls(role)[0]["input"]
            assert value["question"] == QUESTION and value["plan"]["questions"] == PLAN["questions"]
            assert "ALPHA_ONLY_TAIL_12" in value["evidence"]
            assert "BETA_ONLY_TAIL_12" in value["evidence"]
        assert {(call["role"], call["revision"]) for call in h.calls} == {
            ("baseline.planner", 3), ("baseline.distiller", 1), ("baseline.analyst", 3),
            ("baseline.writer", 5), ("baseline.reviewer", 4)}
        assert h.role_calls("analyst")[0]["input"]["available_source_ids"] == ["r1.source-001", "r1.source-002"]
        assert any(read["range"]["kind"] == "pages" and read["range"]["end_exclusive"] > 11 for read in h.reads)
        result = await _json(h.service, run_id, view.result_manifest_ref.to_dict())
        assert result["method_revision"] == method_revision
        access = await _json(h.service, run_id, result["source_access_ref"])
        assert all(item["complete"] and item["read_bytes"] == item["document_bytes"] for item in access["sources"])
        delivered = await _bytes(h.service, run_id, view.context_plan.context_ref.to_dict())
        assert delivered.decode() == h.role_calls("analyst")[0]["input"]["evidence"]
        records = (await _json(h.service, run_id, result["distillations_ref"]))["records"]
        assert len(records) == 2
        events = await _events(h.service, run_id)
        distilled = [event for event in events if event["kind"] == "workflow.evidence.distilled"]
        assert len(distilled) == 2
        for record in records:
            value = next(call["input"] for call in h.role_calls("distiller") if call["input"]["chunk_id"] == record["chunk_id"])
            assert record["input_sha256"] == digest_bytes(canonical_json(value["segments"]))
            assert await _json(h.service, run_id, record["input_ref"]) == value
            node = next(node for node in view.nodes if node.kind == "agent"
                        and node.detail.get("input_ref") == record["input_ref"])
            assert node.detail["role_id"] == "baseline.distiller" and node.status == "succeeded"
            event = next(event for event in distilled
                         if event["payload"]["chunk_id"] == record["chunk_id"])
            assert event["payload"]["input_ref"] == node.detail["input_ref"]
            for finding in record["distillation"]["findings"]:
                segment = next(s for s in value["segments"] if s["segment_id"] == finding["segment_id"])
                assert finding["question"] in PLAN["questions"] and finding["quote"] in segment["text"]
        events = await _events(h.service, run_id)
        outcomes = [event for event in events if event["kind"] == "model.outcome"]
        assert len(outcomes) == len(h.calls) == 6
        assert len({event["context"]["run_id"] for event in outcomes}) == 6
        assert view.usage["known_subtotals"]["total_tokens"] == 28 * 6
        assert len(view.usage["per_attempt_usage_refs"]) == 6


@pytest.mark.asyncio
async def test_saved_line_batches_deliver_last_line_after_first_two_hundred(tmp_path, monkeypatch):
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("LINE_BATCH", count=225)}) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(min_substantive_sources=1))).run_id)
        assert view.status == "succeeded", view.error
        assert any(read["range"]["kind"] == "lines" and read["range"]["end_exclusive"] > 201 for read in h.reads)
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        access = (await _json(h.service, view.run_id, result["source_access_ref"]))["sources"][0]
        raw = _lines("LINE_BATCH", count=225).text.encode("utf-8")
        assert access["complete"] is True and access["read_bytes"] == access["document_bytes"] == len(raw)
        segments = h.role_calls("distiller")[0]["input"]["segments"]
        assert "".join(segment["text"] for segment in segments).encode("utf-8") == raw
        assert segments[0]["start_byte"] == 0 and segments[-1]["end_byte"] == len(raw)
        assert all(left["end_byte"] == right["start_byte"] for left, right in zip(segments, segments[1:]))
        for role in ("distiller", "analyst", "writer"):
            value = h.role_calls(role)[0]["input"]
            supplied = json.dumps(value["segments"]) if role == "distiller" else value["evidence"]
            assert "LINE_BATCH_FINAL_LINE" in supplied
        assert view.quality.fully_read_sources == 1 and view.quality.evidence_sufficient is True


@pytest.mark.asyncio
async def test_analyst_partial_and_reviewer_accept_remain_partial_after_restart_without_rerun(tmp_path, monkeypatch):
    def respond(role, value, ordinal):
        return _analysis(value, sufficient=False) if role == "baseline.analyst" else None

    request = _request(max_rounds=1, min_substantive_sources=1)
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("PARTIAL")}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert view.quality.status == "partial" and view.quality.evidence_sufficient is False
        assert view.quality.report_accepted is True
        assert view.quality.gaps == ["A required corroborating source remains unavailable."]
        report = await _bytes(h.service, view.run_id, view.report_ref.to_dict())
        assert b"Research coverage: partial" in report and b"Research coverage: sufficient" not in report
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        assert result["quality"] == view.quality.to_dict()
        assert result["rounds"][0]["sufficient"] is False and result["drafts"][0]["accepted"] is True
        round_record = result["rounds"][0]
        assert round_record["analysis_adjustments"] == []
        raw_analysis = await _json(h.service, view.run_id, round_record["analyst_output_ref"])
        normalized_analysis = await _json(h.service, view.run_id, round_record["analysis_ref"])
        assert raw_analysis["sufficient"] is False and normalized_analysis == raw_analysis
        assert round_record["analysis_ref"] != round_record["analyst_output_ref"]
        for role in ("writer", "reviewer"):
            assert h.role_calls(role)[0]["input"]["quality"]["status"] == "partial"
        assert (await h.service.start_run(request)).run_id == view.run_id
        counts = (len(h.calls), len(h.fetched), len(h.searches), len(h.reads))
        assert counts[0] == 5
        settings = h.settings
    engine = (await Engine.open(settings)).unwrap()
    service = create_research_service(engine)

    async def forbid_tools(*args, **kwargs):
        pytest.fail("An idempotent saved research request must not dispatch a tool after restart")

    monkeypatch.setattr(engine.executor, "execute", forbid_tools)
    try:
        restored = await service.start_run(request)
        assert restored.run_id == view.run_id and restored.status == "succeeded" and restored.active is False
        assert restored.recording_status == "complete" and restored.quality.to_dict() == view.quality.to_dict()
        assert await _bytes(service, view.run_id, restored.report_ref.to_dict()) == report
        assert (await _json(service, view.run_id, restored.result_manifest_ref.to_dict()))["quality"] == result["quality"]
        assert counts == (len(h.calls), len(h.fetched), len(h.searches), len(h.reads))
    finally:
        await _close(engine, service)


@pytest.mark.asyncio
@pytest.mark.parametrize("unresolved", ["gap", "known_read"])
async def test_analyst_claiming_sufficient_with_unresolved_evidence_publishes_normalized_partial(tmp_path, monkeypatch, unresolved):
    outputs = []
    gap = "Independent validation of the documented method remains unavailable."

    def respond(role, value, ordinal):
        if role != "baseline.analyst":
            return None
        output = _analysis(value, sufficient=True)
        if unresolved == "gap":
            output["gaps"] = [gap]
        else:
            output["follow_up_reads"] = [{
                "source_id": value["available_source_ids"][0],
                "range": {"schema_version": 1, "kind": "lines", "start": 2, "end_exclusive": 4},
                "reason": "Inspect the known method requirements before claiming coverage is sufficient",
            }]
        outputs.append(_copy(output))
        return output

    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("CONTRADICTORY_ANALYST")}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            max_rounds=1, min_substantive_sources=1))).run_id)
        assert view.status == "succeeded", view.error
        assert view.recording_status == "complete" and view.report_ref is not None
        assert view.quality.status == "partial" and view.quality.evidence_sufficient is False
        assert view.quality.report_accepted is True
        assert view.quality.substantive_sources == view.quality.fully_read_sources == 1
        assert h.fetched == [ALPHA]
        assert len(h.calls) == 5
        assert all(len(h.role_calls(role)) == 1 for role in ("planner", "distiller", "analyst", "writer", "reviewer"))
        assert view.usage["known_subtotals"]["total_tokens"] == 28 * 5
        assert len(view.usage["per_attempt_usage_refs"]) == 5
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        assert result["quality"] == view.quality.to_dict() and len(result["rounds"]) == 1
        round_record = result["rounds"][0]
        assert round_record["sufficient"] is False and round_record["quality"]["evidence_sufficient"] is False
        assert round_record["analysis_ref"] != round_record["analyst_output_ref"]
        raw = await _json(h.service, view.run_id, round_record["analyst_output_ref"])
        normalized = await _json(h.service, view.run_id, round_record["analysis_ref"])
        assert raw == outputs[0] and raw["sufficient"] is True
        assert normalized == {**raw, "sufficient": False}
        assert round_record["analysis_adjustments"] == [{"kind": "contradictory_sufficiency",
            "reported_sufficient": True, "validated_sufficient": False}]
        for role in ("writer", "reviewer"):
            value = h.role_calls(role)[0]["input"]
            assert value["analysis"] == normalized
            assert value["quality"]["status"] == "partial" and value["quality"]["evidence_sufficient"] is False
        if unresolved == "gap":
            assert view.quality.gaps == [gap]
        else:
            assert normalized["follow_up_reads"][0]["source_id"] == view.sources.items[0].item_id
            assert any("source ranges" in reason for reason in view.quality.reasons)
        report = await _bytes(h.service, view.run_id, view.report_ref.to_dict())
        assert b"Research coverage: partial" in report and b"Research coverage: sufficient" not in report
        events = await _events(h.service, view.run_id)
        assert len([event for event in events if event["kind"] == "model.outcome"]) == 5


@pytest.mark.asyncio
async def test_known_tail_range_request_is_read_and_delivered_without_redistilling_unchanged_source(tmp_path, monkeypatch):
    document = _paper("TARGETED", page_words=12)
    requested = {"schema_version": 1, "kind": "pages", "start": 11, "end_exclusive": 13}

    def respond(role, value, ordinal):
        if role == "baseline.analyst" and value["round"] == 1:
            return _analysis(value, sufficient=False, reads=[{
                "source_id": value["available_source_ids"][0], "range": requested,
                "reason": "Inspect the documented concluding step on the known last pages",
            }])
        return None

    async with _configured(tmp_path, monkeypatch, {ALPHA: document}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            max_scan_bytes=4096, min_substantive_sources=1))).run_id)
        assert view.status == "succeeded", view.error
        analysts = h.role_calls("analyst")
        assert [call["input"]["round"] for call in analysts] == [1, 2]
        assert "TARGETED_TAIL_12" not in analysts[0]["input"]["evidence"]
        assert "TARGETED_TAIL_12" in analysts[1]["input"]["evidence"]
        assert any(read["range"] == {key: value for key, value in requested.items() if key != "schema_version"} for read in h.reads)
        assert any(selection.range.to_dict() == requested for selection in view.context_plan.selections)
        assert "TARGETED_TAIL_12" in h.role_calls("writer")[0]["input"]["evidence"]
        assert len(h.fetched) == len(h.role_calls("distiller")) == 1
        assert h.role_calls("distiller")[0]["input"]["source"]["complete_read"] is False
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        rounds = result["rounds"]
        assert len(rounds) == 2
        first = await _json(h.service, view.run_id, rounds[0]["distillations_ref"])
        second = await _json(h.service, view.run_id, rounds[1]["distillations_ref"])
        assert first["records"] == second["records"] and first["model_calls"] == second["model_calls"] == 1
        access = await _json(h.service, view.run_id, result["source_access_ref"])
        assert access["supplemental_reads"] and access["supplemental_reads"][0]["range"] == requested
        assert access["sources"][0]["complete"] is False
        assert view.quality.status == "partial" and view.quality.evidence_sufficient is False
        assert any("incomplete" in reason for reason in view.quality.reasons)


@pytest.mark.asyncio
@pytest.mark.parametrize("fabrication", ["quote", "source", "chunk", "segment", "punctuation"])
async def test_fabricated_distillation_is_retried_then_fails_before_synthesis(tmp_path, monkeypatch, fabrication):
    def respond(role, value, ordinal):
        if role != "baseline.distiller":
            return None
        output = _distillation(value)
        if fabrication == "quote":
            output["findings"][0]["quote"] = "FABRICATED_PASSAGE_ABSENT_FROM_SAVED_TEXT"
        elif fabrication == "source":
            output["source_id"] = "unread-source-999"
        elif fabrication == "chunk":
            output["chunk_id"] = "unread-chunk-999"
        elif fabrication == "punctuation":
            output["findings"][0]["quote"] = output["findings"][0]["quote"].replace("step.", "step!")
            assert output["findings"][0]["quote"] not in value["segments"][-1]["text"]
        else:
            output["findings"][0]["segment_id"] = "unread-segment-999"
        return output

    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("REAL")}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(min_substantive_sources=1))).run_id)
        assert view.status == "failed" and view.error["code"] == "INVALID_EVIDENCE_REFERENCE", view.error
        assert view.report_ref is None and view.result_manifest_ref is None
        assert view.recording_status == "complete" and view.sources.items[0].status == "succeeded"
        assert len(h.role_calls("distiller")) == 2
        assert h.role_calls("distiller")[1]["input"]["feedback"]
        assert not h.role_calls("analyst") and not h.role_calls("writer") and not h.role_calls("reviewer")
        events = await _events(h.service, view.run_id)
        assert not any(event["kind"] == "workflow.evidence.distilled" for event in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("dehyphenated", [False, True], ids=["verbatim", "pdf-line-hyphen"])
async def test_known_wrong_segment_rebinds_to_saved_quote_without_changing_raw_output(tmp_path, monkeypatch, dehyphenated):
    saved_quote = "Theorem 5: feasible require-\nments establish the solution space."
    model_quote = saved_quote.replace("require-\nments", "requirements") if dehyphenated else saved_quote
    pages = list(_paper("REBOUND_QUOTE").pages)
    pages[-1] += "\n" + saved_quote
    document = Document("\n".join(pages), tuple(pages))
    outputs, claimed_segments, actual_segments = [], [], []

    def respond(role, value, ordinal):
        if role != "baseline.distiller":
            return None
        actual = next(segment for segment in value["segments"] if saved_quote in segment["text"])
        claimed = next(segment for segment in value["segments"] if saved_quote not in segment["text"])
        assert actual["segment_id"] != claimed["segment_id"]
        output = _distillation(value)
        for finding in output["findings"]:
            finding.update(segment_id=claimed["segment_id"], quote=model_quote)
        outputs.append(_copy(output))
        claimed_segments.append(_copy(claimed))
        actual_segments.append(_copy(actual))
        return output

    async with _configured(tmp_path, monkeypatch, {ALPHA: document}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(min_substantive_sources=1))).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.role_calls("distiller")) == 1, "A quote in another known saved segment needs no model retry"
        assert view.quality.evidence_sufficient is True and view.quality.report_accepted is True
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        digest = await _json(h.service, view.run_id, result["distillations_ref"])
        assert digest["model_calls"] == 1 and len(digest["records"]) == 1
        record = digest["records"][0]
        raw = await _json(h.service, view.run_id, record["output_ref"])
        assert raw == outputs[0], "The original provider output must remain immutable"
        actual, claimed = actual_segments[0], claimed_segments[0]
        for finding in raw["findings"]:
            assert finding["segment_id"] == claimed["segment_id"] and finding["quote"] == model_quote
        for finding in record["distillation"]["findings"]:
            assert finding["segment_id"] == actual["segment_id"] and finding["quote"] == saved_quote
            start = actual["start_byte"] + len(actual["text"].split(saved_quote, 1)[0].encode("utf-8"))
            assert document.text.encode("utf-8")[start:start + len(finding["quote"].encode("utf-8"))] == finding["quote"].encode("utf-8")
        changes = record["validation_changes"]
        assert len(changes) == len(raw["findings"])
        assert {change["finding_index"] for change in changes} == set(range(len(raw["findings"])))
        assert all(change["from_segment_id"] == claimed["segment_id"]
                   and change["to_segment_id"] == actual["segment_id"]
                   and change["quote_normalized"] is dehyphenated for change in changes)
        validated = await _json(h.service, view.run_id, record["validation_ref"])
        assert validated["distillation"] == record["distillation"]
        assert validated["validation_changes"] == changes
        assert await _json(h.service, view.run_id, record["input_ref"]) == h.role_calls("distiller")[0]["input"]
        assert any(selection.source_read_action_id == actual["read_action_id"]
                   and selection.range.to_dict() == actual["range"] for selection in view.context_plan.selections)
        for role in ("analyst", "writer", "reviewer"):
            evidence = h.role_calls(role)[0]["input"]["evidence"]
            assert saved_quote in evidence
            if dehyphenated:
                assert model_quote not in evidence


@pytest.mark.asyncio
async def test_valid_quote_repair_publishes_only_validated_saved_passage(tmp_path, monkeypatch):
    def respond(role, value, ordinal):
        if role == "baseline.distiller":
            output = _distillation(value)
            if ordinal == 1:
                output["findings"][0]["quote"] = "FABRICATED_PASSAGE_ABSENT_FROM_SAVED_TEXT"
            return output
        return None

    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("REPAIRED")}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(min_substantive_sources=1))).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.role_calls("distiller")) == 2 and h.role_calls("distiller")[1]["input"]["feedback"]
        feedback = "\n".join(h.role_calls("distiller")[1]["input"]["feedback"])
        assert "FABRICATED_PASSAGE_ABSENT_FROM_SAVED_TEXT" in feedback
        assert h.role_calls("distiller")[0]["input"]["segments"][-1]["segment_id"] in feedback
        assert all(len(item) <= 1024 for item in h.role_calls("distiller")[1]["input"]["feedback"])
        instruction = feedback.casefold()
        assert any(cue in instruction for cue in ("drop", "remove"))
        assert "short" in instruction and any(cue in instruction for cue in ("verbatim", "copied exactly", "exact passage"))
        assert any(cue in instruction for cue in ("4-6", "4–6", "4 to 6", "four to six"))
        assert "FABRICATED_PASSAGE" not in h.role_calls("analyst")[0]["input"]["evidence"]
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        digest = await _json(h.service, view.run_id, result["distillations_ref"])
        assert digest["model_calls"] == 2 and len(digest["records"]) == 1
        record = digest["records"][0]
        value = h.role_calls("distiller")[1]["input"]
        assert record["distillation"]["findings"][0]["quote"] in value["segments"][-1]["text"]
        assert record["validation_ref"] and record["output_ref"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_report", ["citation", "coverage_label", "language"])
async def test_reviewer_accept_cannot_override_citation_coverage_or_english_checks(tmp_path, monkeypatch, invalid_report):
    def respond(role, value, ordinal):
        if role == "baseline.analyst":
            return _analysis(value, sufficient=False)
        if role == "baseline.writer":
            report = _report(value)
            if invalid_report == "citation":
                return report + "Invented corroboration [unread-source-999].\n"
            if invalid_report == "coverage_label":
                return report.replace("Research coverage: partial", "Research coverage: sufficient")
            return report + "\n这是非英语结论。\n"
        return None

    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("REPORT")}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            max_rounds=1, min_substantive_sources=1, max_report_attempts=1))).run_id)
        assert view.status == "failed" and view.error["code"] == "REPORT_REVIEW_FAILED", view.error
        assert view.report_ref is None and view.quality.evidence_sufficient is False
        assert view.quality.report_accepted is False and view.quality.status == "partial"
        assert len(h.role_calls("writer")) == len(h.role_calls("reviewer")) == 1
        issues = " ".join(view.error["details"]["issues"])
        expected = {"citation": "unknown source", "coverage_label": "Research coverage: partial", "language": "English"}
        assert expected[invalid_report] in issues


@pytest.mark.asyncio
async def test_403_abstract_and_bibliography_recover_within_twenty_attempts_and_two_rounds(tmp_path, monkeypatch):
    denied, abstract, bibliography = (f"https://example.org/{name}" for name in ("denied", "abstract", "bibliography"))
    good_urls = [f"https://example.org/full-{index}" for index in range(1, 26)]
    documents = {
        denied: None,
        abstract: Document("Abstract: the method concerns requirements, analysis and synthesis. See Alternate method (2024)."),
        bibliography: Document("\n".join(f"[{i}] Alternate method, reference {i}." for i in range(1, 85))),
        **{url: _lines(f"FULL_{index}", count=35) for index, url in enumerate(good_urls, 1)},
    }

    def discover(tool, query):
        if query == "initial method":
            urls = [denied, abstract, bibliography]
        elif query == CITED_TITLE_QUERY:
            urls = good_urls[:10]
        elif query == "remaining method":
            urls = [denied, abstract, good_urls[0], *good_urls[10:17]]
        else:
            pytest.fail(f"Unexpected recovery query: {query}")
        return [{"rank": index, "url": url, "title": f"Distinct retained method work {url.rsplit('/', 1)[1]}",
                 "snippet": "DISCOVERY_ONLY_NOT_SOURCE_TEXT"} for index, url in enumerate(urls, 1)]

    def respond(role, value, ordinal):
        if role == "baseline.distiller":
            output = _distillation(value)
            if value["source"]["url"] in {abstract, bibliography}:
                # The host must correct this false full-text claim from saved bytes.
                output["content_kind"] = "substantive"
                output["reference_queries"] = [CITED_PUBLICATION_TITLE]
            return output
        if role == "baseline.analyst":
            return _analysis(value, sufficient=False,
                queries=["remaining method"] if value["round"] == 1 else [])
        return None

    async with _configured(tmp_path, monkeypatch, documents, respond=respond, discover=discover) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            source_urls=[], queries=["initial method"], max_results=10, recovery_queries=4))).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.fetched) == len(set(h.fetched)) == 20
        assert h.fetched[:3] == [denied, abstract, bibliography]
        assert h.fetched.count(denied) == 1 and not set(good_urls[17:]) & set(h.fetched)
        assert [query for _, query in h.searches] == ["initial method", CITED_TITLE_QUERY, "remaining method"]
        assert len(view.sources.items) == 20 and sum(source.status == "failed" for source in view.sources.items) == 1
        assert view.quality.attempted_sources == 20 and view.quality.substantive_sources == 17
        assert view.quality.status == "partial" and view.quality.report_accepted is True
        assert [call["input"]["round"] for call in h.role_calls("analyst")] == [1, 2]
        assert len(h.role_calls("distiller")) == 19 and len(h.calls) == 24
        assert all("DISCOVERY_ONLY_NOT_SOURCE_TEXT" not in json.dumps(call["input"]) for call in h.calls)
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        assert len(result["rounds"]) == 2 and result["stop_reason"] == "source_limit"
        first_sources = await _json(h.service, view.run_id, result["rounds"][0]["source_manifest_ref"])
        assert len(first_sources["items"]) <= 10, "Round 1 must leave half of the twenty attempts for round 2"
        round_fetches = [await _json(h.service, view.run_id, row["fetch_manifest_ref"])
                         for row in result["rounds"]]
        recorded_urls = [item["url"] for manifest in round_fetches for item in manifest["items"]]
        assert recorded_urls == h.fetched
        assert len(round_fetches[0]["items"]) <= 10
        assert len(round_fetches[0]["items"]) > 3, "The round manifest must include the cited-title rescue attempts"
        digest = await _json(h.service, view.run_id, result["distillations_ref"])
        assert all(record["distillation"]["reference_queries"] == [CITED_PUBLICATION_TITLE]
                   for record in digest["records"] if record["distillation"]["reference_queries"])
        assert digest["model_calls"] == 19 and len(digest["records"]) == 19
        by_url = {source.item_id: source.url for source in view.sources.items}
        kinds = {by_url[record["source_id"]]: record["content_kind"] for record in digest["records"]}
        assert kinds[abstract] == "abstract" and kinds[bibliography] == "bibliography"
        assert len(view.usage["per_attempt_usage_refs"]) == len(h.calls)
        assert view.usage["known_subtotals"]["total_tokens"] == 28 * len(h.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("primary_relevant", [True, False])
async def test_failed_and_partial_locations_allow_full_text_alternate_then_suppress_same_work_copies(tmp_path, monkeypatch, primary_relevant):
    denied = "https://publisher.invalid/denied"
    abstract = "https://publisher.invalid/abstract"
    bibliography = "https://publisher.invalid/references"
    full = "https://archive.example.edu/primary.pdf"
    mirror = "https://repository.example.edu/primary-copy.pdf"
    doi_url = "https://doi.org/10.5555/retained-method"
    paper = _paper("SAME_WORK_PRIMARY", pages=3)
    boilerplate = _boilerplate()
    documents = {
        denied: None,
        abstract: Document("Abstract: requirements, analysis and synthesis define the method."),
        bibliography: Document("\n".join(f"[{i}] Retained method reference {i}." for i in range(1, 85))),
        full: paper if primary_relevant else boilerplate, mirror: paper, doi_url: None,
    }

    def discover(tool, query):
        assert tool == "scholar.crossref.search"
        return [{"rank": 1, "titles": ["Retained method primary definition"],
                 "doi": "10.5555/retained-method", "doi_url": doi_url,
                 "links": [{"url": url, "content_type": "application/pdf" if url.endswith(".pdf") else "text/html"}
                           for url in (denied, abstract, bibliography, full, mirror)]}]

    def respond(role, value, ordinal):
        if role == "baseline.distiller" and value["source"]["url"] == full and not primary_relevant:
            assert value["source"]["complete_read"] is True
            assert value["source"]["content_hint"] == "substantive"
            assert value["source"]["document_bytes"] > 2048
            output = _distillation(value)
            output.update(content_kind="irrelevant", findings=[],
                          summary="This archived location does not supply the required method evidence.")
            return output
        return None

    async with _configured(tmp_path, monkeypatch, documents, discover=discover, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            source_urls=[denied, abstract, bibliography], search_tools=["scholar.crossref.search"]))).run_id)
        assert view.status == "succeeded", view.error
        expected_fetches = [denied, abstract, bibliography, full] + ([] if primary_relevant else [mirror])
        assert h.fetched == expected_fetches
        assert doi_url not in h.fetched
        assert len(view.sources.items) == view.quality.attempted_sources == len(expected_fetches)
        assert view.sources.items[0].status == "failed"
        assert len(h.role_calls("distiller")) == len(expected_fetches) - 1
        assert view.quality.substantive_sources == 1
        # A full alternate of this one work does not satisfy the default two
        # independent-document policy even when the Analyst calls it sufficient.
        assert view.quality.status == "partial" and view.quality.evidence_sufficient is False
        assert view.quality.report_accepted is True
        assert any("distinct substantive" in reason for reason in view.quality.reasons)
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        assert 1 <= len(result["rounds"]) <= 2
        round_digests = [await _json(h.service, view.run_id, row["distillations_ref"])
                        for row in result["rounds"]]
        assert all(digest["model_calls"] == len(expected_fetches) - 1 for digest in round_digests)
        assert all(digest["records"] == round_digests[0]["records"] for digest in round_digests)
        records = (await _json(h.service, view.run_id, result["distillations_ref"]))["records"]
        by_id = {source.item_id: source.url for source in view.sources.items}
        kinds = {by_id[record["source_id"]]: record["content_kind"] for record in records}
        expected_kinds = {abstract: "abstract", bibliography: "bibliography",
                          full: "substantive" if primary_relevant else "irrelevant"}
        if not primary_relevant:
            expected_kinds[mirror] = "substantive"
        assert kinds == expected_kinds
        assert "SAME_WORK_PRIMARY_TAIL_03" in h.role_calls("analyst")[0]["input"]["evidence"]
        if not primary_relevant:
            irrelevant_id = next(source.item_id for source in view.sources.items if source.url == full)
            useful_id = next(source.item_id for source in view.sources.items if source.url == mirror)
            for call in h.role_calls("analyst"):
                assert irrelevant_id not in call["input"]["available_source_ids"]
                assert useful_id in call["input"]["available_source_ids"]
                assert "PAYWALL_ONLY" not in call["input"]["evidence"]


@pytest.mark.asyncio
async def test_long_irrelevant_location_is_retained_but_only_genuine_alternate_reaches_synthesis(tmp_path, monkeypatch):
    documents = {ALPHA: _boilerplate(), BETA: _paper("GENUINE_FULL_TEXT", pages=3)}

    def discover(tool, query):
        assert tool == "scholar.crossref.search"
        return [{"rank": 1, "titles": ["Retained method publication"], "doi": "10.5555/same-publication",
                 "links": [{"url": url, "content_type": "application/pdf"} for url in (ALPHA, BETA)]}]

    def respond(role, value, ordinal):
        if role == "baseline.distiller" and value["source"]["url"] == ALPHA:
            assert value["source"]["complete_read"] is True
            assert value["source"]["content_hint"] == "substantive"
            assert value["source"]["document_bytes"] > 2048
            output = _distillation(value)
            output.update(content_kind="irrelevant", findings=[], summary="This is an account page with no method evidence.")
            return output
        return None

    async with _configured(tmp_path, monkeypatch, documents, discover=discover, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            source_urls=[ALPHA], search_tools=["scholar.crossref.search"], min_substantive_sources=1))).run_id)
        assert view.status == "succeeded", view.error
        assert h.fetched == [ALPHA, BETA] and len(h.role_calls("distiller")) == 2
        by_url = {source.url: source for source in view.sources.items}
        assert by_url[ALPHA].text_sha256 != by_url[BETA].text_sha256
        assert view.quality.substantive_sources == 1 and view.quality.evidence_sufficient is True
        for call in h.role_calls("analyst"):
            assert call["input"]["available_source_ids"] == [by_url[BETA].item_id]
        for role in ("analyst", "writer", "reviewer"):
            for call in h.role_calls(role):
                assert "GENUINE_FULL_TEXT_TAIL_03" in call["input"]["evidence"]
                assert "PAYWALL_ONLY" not in call["input"]["evidence"]
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        records = (await _json(h.service, view.run_id, result["distillations_ref"]))["records"]
        assert {record["content_kind"] for record in records} == {"irrelevant", "substantive"}
        ignored = next(record for record in records if record["content_kind"] == "irrelevant")
        retained_input = await _json(h.service, view.run_id, ignored["input_ref"])
        assert retained_input == next(call["input"] for call in h.role_calls("distiller")
                                      if call["input"]["source"]["url"] == ALPHA)
        assert "PAYWALL_ONLY" in json.dumps(retained_input["segments"])
        access = (await _json(h.service, view.run_id, result["source_access_ref"]))["sources"]
        assert len({item["work_id"] for item in access}) == 1


@pytest.mark.parametrize("identities,expected", [
    pytest.param([("doi:first", "first text"), ("doi:first", "revised text")], 1, id="same-work-different-bytes"),
    pytest.param([("doi:first", "same text"), ("doi:second", "same text")], 1, id="different-work-identical-bytes"),
    pytest.param([("doi:first", "first text"), ("doi:second", "second text")], 2, id="independent-works"),
    pytest.param([("doi:first", "text A"), ("doi:second", "text B"),
                  ("doi:first", "text B"), ("doi:independent", "text C")], 2, id="identity-bridge-last"),
    pytest.param([("doi:first", "text B"), ("doi:first", "text A"),
                  ("doi:second", "text B"), ("doi:independent", "text C")], 2, id="identity-bridge-first"),
])
def test_substantive_quality_counts_equivalent_work_and_text_as_one(identities, expected):
    # Revisions of one publication and copies under another publication identity
    # remain one evidentiary work, including a bridge joining both identities.
    sources, accesses, records = [], {}, []
    for index, (work, body) in enumerate(identities, 1):
        source_id = f"source-{index}"
        sources.append(SourceRecord(item_id=source_id, url=f"https://example.org/work-{index}",
            status="succeeded", snapshot_ref=SnapshotReference(store_id="test", snapshot_id=source_id),
            text_sha256=digest_bytes(body.encode()), text_bytes=len(body.encode()),
            recording_status="complete", persistence_state="committed"))
        accesses[source_id] = {"work_id": work, "complete": True}
        records.append({"source_id": source_id, "content_kind": "substantive"})
    assert substantive_work_count(SourceManifest(items=sources), accesses, records) == expected
    assert substantive_work_count(SourceManifest(items=sources), accesses,
                                  [{**record, "content_kind": "irrelevant"} for record in records]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("independent_work", [False, True])
async def test_identical_retained_text_under_distinct_dois_does_not_double_quality(tmp_path, monkeypatch, independent_work):
    gamma = "https://example.org/independent.pdf"
    urls = [ALPHA, BETA] + ([gamma] if independent_work else [])
    copy = _paper("IDENTICAL_COPY", pages=3)
    documents = {ALPHA: copy, BETA: copy, gamma: _paper("INDEPENDENT_WORK", pages=3)}

    def discover(tool, query):
        assert tool == "scholar.crossref.search"
        return [{"rank": index, "titles": [f"Retained method publication {index}"],
                 "doi": f"10.5555/independent-work-{index}",
                 "links": [{"url": url, "content_type": "application/pdf"}]}
                for index, url in enumerate(urls, 1)]

    async with _configured(tmp_path, monkeypatch, documents, discover=discover) as h:
        view = await _settle(h.service, (await h.service.start_run(_request(
            source_urls=urls, search_tools=["scholar.crossref.search"]))).run_id)
        assert view.status == "succeeded", view.error
        assert h.fetched == urls and len(h.role_calls("distiller")) == len(urls)
        by_url = {source.url: source for source in view.sources.items}
        assert by_url[ALPHA].text_sha256 == by_url[BETA].text_sha256
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        access = (await _json(h.service, view.run_id, result["source_access_ref"]))["sources"]
        by_id = {item["source_id"]: item for item in access}
        assert by_id[by_url[ALPHA].item_id]["work_id"] != by_id[by_url[BETA].item_id]["work_id"]
        assert all(item["complete"] for item in access)
        assert view.quality.substantive_sources == (2 if independent_work else 1)
        assert view.quality.attempted_sources == view.quality.distilled_sources == len(urls)
        assert view.quality.evidence_sufficient is independent_work
        assert view.quality.status == ("sufficient" if independent_work else "partial")
        assert view.quality.report_accepted is True and result["quality"] == view.quality.to_dict()
        if independent_work:
            assert by_url[gamma].text_sha256 != by_url[ALPHA].text_sha256
        else:
            assert any("distinct substantive" in reason for reason in view.quality.reasons)
        report = await _bytes(h.service, view.run_id, view.report_ref.to_dict())
        assert f"Research coverage: {view.quality.status}".encode() in report


@pytest.mark.asyncio
async def test_failing_distiller_preserves_original_error_and_drains_sibling_after_validated_event(tmp_path, monkeypatch):
    sibling_started, sibling_drained = asyncio.Event(), asyncio.Event()
    allow_failure, blocker = asyncio.Event(), asyncio.Event()
    cancelled = []
    gamma = "https://example.org/gamma"

    async def respond(role, value, ordinal):
        if role != "baseline.distiller":
            return None
        url = value["source"]["url"]
        if url == ALPHA:
            await allow_failure.wait()
            output = _distillation(value)
            output["findings"][0]["quote"] = "FABRICATED_PASSAGE_ABSENT_FROM_SAVED_TEXT"
            return output
        if url == BETA:
            return _distillation(value)
        assert url == gamma
        sibling_started.set()
        try:
            await blocker.wait()
            return _distillation(value)
        except asyncio.CancelledError:
            cancelled.append(value["source"]["source_id"])
            raise
        finally:
            sibling_drained.set()

    documents = {ALPHA: _lines("FAILURE"), BETA: _lines("VALIDATED"), gamma: _lines("SIBLING")}
    async with _configured(tmp_path, monkeypatch, documents, respond=respond) as h:
        run_id = (await h.service.start_run(_request(source_urls=[ALPHA, BETA, gamma]))).run_id
        try:
            await asyncio.wait_for(sibling_started.wait(), 20)
            # Observe the actual durable event before allowing another source to
            # fail. No event allowlist, recorder, projection or port is mocked.
            async with asyncio.timeout(20):
                while True:
                    events = await _events(h.service, run_id)
                    distilled = [event for event in events if event["kind"] == "workflow.evidence.distilled"]
                    if distilled:
                        assert [event["payload"]["source_id"] for event in distilled] == ["r1.source-002"]
                        break
                    current = await h.service.get_run(run_id)
                    assert current.active, current.error
                    await asyncio.sleep(.01)
            allow_failure.set()
            view = await _settle(h.service, run_id, seconds=35)
            assert view.status == "failed" and view.error["code"] == "INVALID_EVIDENCE_REFERENCE", view.error
            assert sibling_drained.is_set() and cancelled == ["r1.source-003"]
            assert not [task for task in asyncio.all_tasks()
                        if not task.done() and task.get_name().startswith(f"deepresearch-role:{run_id}:")]
            assert not h.role_calls("analyst") and not h.role_calls("writer")
            assert view.report_ref is None and view.recording_status == "complete"
            events = await _events(h.service, run_id)
            outcomes = [event for event in events if event["kind"] == "model.outcome"]
            assert len(outcomes) == len(h.calls) == 5
            assert any(event["payload"].get("status") == "cancelled"
                       or event["payload"].get("completion") == "cancelled" for event in outcomes)
            assert any(event["kind"] == "agent.finished" and event["payload"]["status"] == "cancelled" for event in events)
            expected_error = view.error
            settings, model_calls = h.settings, len(h.calls)
        finally:
            allow_failure.set()
            blocker.set()
    engine = (await Engine.open(settings)).unwrap()
    service = create_research_service(engine)
    try:
        restored = await service.get_run(run_id)
        assert restored.status == "failed" and restored.active is False
        assert restored.recording_status == "complete" and restored.error == expected_error
        assert len(h.calls) == model_calls and restored.report_ref is None
    finally:
        await _close(engine, service)


@pytest.mark.asyncio
async def test_bounded_map_failure_waits_for_sibling_cleanup_and_leaves_no_active_workers():
    entered, draining, finish_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls, settled, workers = [], [], []
    failure = RuntimeError("controlled map failure")

    async def worker(item):
        calls.append(item)
        workers.append(asyncio.current_task())
        if item == "failure":
            await entered.wait()
            raise failure
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            draining.set()
            await finish_cleanup.wait()
            settled.append(item)

    task = asyncio.create_task(bounded_map(["failure", "sibling", "queued"], worker, concurrency=2))
    try:
        await asyncio.wait_for(draining.wait(), 2)
        assert not task.done(), "The map must wait for cancelled sibling cleanup"
        assert calls[:2] == ["failure", "sibling"]
        finish_cleanup.set()
        with pytest.raises(RuntimeError) as failed:
            await asyncio.wait_for(task, 2)
        assert failed.value is failure and sorted(settled) == sorted(calls[1:])
        assert workers and all(child.done() for child in workers)
    finally:
        finish_cleanup.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
