"""Regression checks for the saved cross-topic failures and injected boundaries."""
from copy import deepcopy
from contextlib import asynccontextmanager
import json
import re

import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.methods.baseline.stages.reporting import citation_issues
from deepresearch.workflows.components.acquisition import acquire
from deepresearch.workflows.components.quotations import locate_quote
from deepresearch.workflows.components.source_access import read_retained_range, source_descriptor
from deepresearch.workflows.contracts import FetchManifest, SourceRange
from tests.workflows.test_source_access import RetainedPort, context
from tests.methods.test_parallel_baseline import ALPHA, BETA, PLAN, _configured, _distillation, _lines, _request, _settle
from tests.methods.test_selection_baseline import _decision
from tests.methods.test_parallel_baseline import _events, _json


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["snapshot", "range", "length", "span", "cap", "cleanup", "unknown", "recording"])
async def test_followup_uses_primary_slice_and_lifecycle_validation(fault):
    port = RetainedPort(text="Recorded source content.")
    interval = SourceRange(kind="lines", start=1, end_exclusive=2)
    def corrupt(outcome, number):
        value = outcome["result"]
        if fault == "snapshot": value["snapshot_ref"]["snapshot_id"] = "foreign"
        if fault == "range": value["requested_range"]["start"] = 2
        if fault == "length": value["byte_length"] += 1
        if fault == "span": value["spans"][0]["line"] = 99
        if fault == "cap": value.update(text="x" * 101, byte_length=101)
        if fault == "cleanup": outcome["process"] = {"cleanup": {"complete": False}}
        if fault == "unknown": outcome["persistence"] = {"commit_state": "unknown"}
        if fault == "recording": outcome["recording"] = {"status": "incomplete"}
        return outcome
    port.transform = corrupt
    with pytest.raises(EngineError) as caught:
        await read_retained_range(context(port), port.source, interval, max_read_bytes=100)
    assert caught.value.code == {"cleanup": "CLEANUP_INCOMPLETE", "unknown": "OUTCOME_UNKNOWN",
                                 "recording": "RECORDING_INCOMPLETE"}.get(fault, "INTEGRITY_ERROR")
    assert not port.publications


@pytest.mark.asyncio
async def test_followup_preserves_continuations_and_partial_coverage():
    port = RetainedPort(text="x" * 100000)
    result = await read_retained_range(context(port), port.source, SourceRange(kind="lines", start=1, end_exclusive=2), max_read_bytes=70000)
    assert result["read_bytes"] == 70000 and not result["complete_requested_range"]
    assert [call["max_text_bytes"] for call in port.reads] == [65536, 4464]
    assert result["segments"][-1]["end_byte"] == 70000
    assert b'"text":' not in port.publications[0][0]


@pytest.mark.asyncio
async def test_html_cannot_request_physical_pages_even_with_pdf_url():
    port = RetainedPort(text="HTML document")
    port.source.url = "https://example.org/article.pdf"
    descriptor = source_descriptor(port.source)
    assert descriptor["page_count"] is None
    assert [item["kind"] for item in descriptor["supported_ranges"]] == ["lines"]
    with pytest.raises(EngineError, match="Requested range"):
        await read_retained_range(context(port), port.source, SourceRange(kind="pages", start=1, end_exclusive=2))
    assert not port.reads


@pytest.mark.asyncio
async def test_followup_budget_smaller_than_codepoint_returns_explicit_partial_read():
    port = RetainedPort(text="😀unicode")
    result = await read_retained_range(context(port), port.source,
        SourceRange(kind="lines", start=1, end_exclusive=2), max_read_bytes=3)
    assert result["read_bytes"] == 0 and result["segments"] == []
    assert result["complete_requested_range"] is False


def test_markdown_quote_mapping_returns_original_text_without_fuzzy_facts():
    source = "The trial [increases](https://example.org/study) reported sleep by 2 minutes."
    rendered = "The trial increases reported sleep by 2 minutes."
    assert locate_quote(rendered, source) is None
    assert locate_quote(rendered, source, markdown_links=True) == source
    assert locate_quote(rendered.replace("2", "20"), source, markdown_links=True) is None
    assert locate_quote("The trial reported sleep by 2 minutes.", source, markdown_links=True) is None


@pytest.mark.parametrize("report", [
    "Claim [source-1].", "Claim.\n## References\n[source-1] https://example.org/source",
    "Claim [source-1].\n## References\n[source-1] https://wrong.example.org/source",
    "Claim [source-1].\n## References\n[source-1] https://example.org/source\n[source-1] https://example.org/source",
])
def test_strict_citation_gate_rejects_reference_structure_and_binding_errors(report):
    assert citation_issues(report, ["source-1"], strict=True, source_urls={"source-1": "https://example.org/source"})


def test_strict_citation_gate_accepts_bound_body_and_reference():
    report = "Claim [source-1].\n## References\n- [source-1] Source — https://example.org/source"
    assert not citation_issues(report, ["source-1"], strict=True, source_urls={"source-1": "https://example.org/source"})


@pytest.mark.parametrize("entry", ["https://example.org/study_(sleep)", "[Title](https://example.org/study_(sleep))."])
def test_citation_urls_preserve_balanced_parentheses(entry):
    report = "Claim [source-1].\n## References\n[source-1] " + entry
    assert not citation_issues(report, ["source-1"], strict=True,
                               source_urls={"source-1": "https://example.org/study_(sleep)"})


def test_declared_publication_dates_reach_source_metadata_separately_from_retrieval():
    port = RetainedPort(text="Article body")
    dates = {"origin": "document_declared_not_verified", "published": [
        {"field": "article:published_time", "value": "2024-02-23"}], "modified": [], "omitted_count": 0}
    port.source.provenance.update(document_dates=dates, retrieved_at="2026-10-03T00:00:00Z")
    descriptor = source_descriptor(port.source)
    assert descriptor["document_dates"] == dates
    assert descriptor["retrieved_at"] == "2026-10-03T00:00:00Z"


class FetchContext:
    def __init__(self, outcome):
        self.port = self
        self.run_id = "controlled"
        self.outcome, self.calls = outcome, []

    @asynccontextmanager
    async def node(self, *args):
        yield {"detail": {}}

    async def update(self, **kwargs): pass

    async def run_tool(self, name, arguments):
        self.calls.append(arguments)
        return deepcopy(self.outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,cleanup,commit,recording,status,continues", [
    ("fetch", True, "not_committed", "complete", "limit_exhausted", True),
    ("run", True, "not_committed", "complete", "limit_exhausted", False),
    (None, True, "not_committed", "complete", "limit_exhausted", False),
    ("fetch", False, "not_committed", "complete", "limit_exhausted", False),
    ("fetch", True, "unknown", "complete", "limit_exhausted", False),
    ("fetch", True, "not_committed", "incomplete", "limit_exhausted", False),
    ("fetch", True, "not_committed", "complete", "cancelled", False),
])
async def test_only_settled_explicit_local_fetch_failures_continue(scope, cleanup, commit, recording, status, continues):
    ctx = FetchContext({"status": status, "recording": {"status": recording},
        "process": {"cleanup": {"complete": cleanup}}, "persistence": {"commit_state": commit},
        "error": {"code": "RESPONSE_LIMIT", "details": {"failure_scope": scope}}})
    manifest = FetchManifest.model_validate({"items": [{"item_id": "first", "url": ALPHA}, {"item_id": "second", "url": BETA}]})
    if continues:
        result = await acquire(ctx, manifest)
        assert [item.status for item in result.items] == ["failed", "failed"]
        assert len(ctx.calls) == 2
    else:
        with pytest.raises(EngineError):
            await acquire(ctx, manifest)
        assert len(ctx.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("commit,status,scope,cleanup,continues", [
    ("not_committed", "failed", "fetch", True, True),
    ("unknown", "failed", "fetch", True, False),
    ("not_committed", "unknown", "fetch", True, False),
    ("not_committed", "failed", None, True, False),
    ("not_committed", "failed", "fetch", False, False),
])
async def test_settled_readonly_network_failure_does_not_invent_unknown_storage_commit(commit, status, scope, cleanup, continues):
    error = {"code": "FETCH_UNAVAILABLE", "commit_state": "not_applicable",
             "observed_effect_state": "unknown", "details": {"failure_scope": scope,
                 "http_request_count": 1, "http_response_count": 0}}
    ctx = FetchContext({"status": status, "recording": {"status": "complete"}, "error": error,
                       "persistence": {"commit_state": commit}, "process": {"cleanup": {"complete": cleanup}}})
    manifest = FetchManifest.model_validate({"items": [{"item_id": "first", "url": ALPHA}, {"item_id": "second", "url": BETA}]})
    if continues:
        result = await acquire(ctx, manifest)
        assert len(ctx.calls) == 2 and [x["url"] for x in ctx.calls] == [ALPHA, BETA]
        assert all(s.status == "failed" and s.persistence_state == "not_committed" and s.error == error for s in result.items)
    else:
        with pytest.raises(EngineError):
            await acquire(ctx, manifest)
        assert len(ctx.calls) == 1


def valid_report(value):
    references = dict(re.findall(r"^\[([A-Za-z0-9_.-]+)\]\nURL: (\S+)", value["evidence"], re.M))
    citations = " ".join(f"[{identity}]" for identity in references)
    return (f"# Result\nResearch coverage: {value['quality']['status']}\nRecorded method {citations}.\n"
            "## Limitations\n" + "; ".join(value["quality"]["gaps"]) + "\n## References\n" +
            "\n".join(f"[{identity}] {url}" for identity, url in references.items()))


@pytest.mark.asyncio
@pytest.mark.parametrize("source_budget", [2, 4])
async def test_revision11_repairs_selector_preserves_queries_time_and_isolates_bad_document(tmp_path, monkeypatch, source_budget):
    query = 'site:example.org "Method C++" -advertisement after:2025-01-01'
    def respond(role, value, ordinal):
        if role == "baseline.planner":
            return {**deepcopy(PLAN), "queries": [query]}
        if role == "baseline.selector":
            decision = _decision(value, defer=True)
            if ordinal == 1:
                decision["rejected"] = decision["selections"][:1]
            return decision
        if role == "baseline.distiller" and value["source"]["url"] == ALPHA:
            return '{"broken":'
        if role == "baseline.writer": return valid_report(value)
        return None
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("BAD"), BETA: _lines("GOOD")}, respond=respond) as h:
        request = _request(source_urls=[ALPHA, BETA], max_sources=source_budget, max_rounds=1,
                           min_substantive_sources=1).model_copy(update={"method_revision": 11})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert view.quality.status == "partial"
        assert query in [q for _, q in h.searches]
        assert all(q == query for _, q in h.searches)
        selector_calls = h.role_calls("selector")
        assert selector_calls[1]["input"]["repair"]["previous_output"]
        assert "duplicates" in json.dumps(selector_calls[1]["input"]["repair"])
        bad = [call for call in h.role_calls("distiller") if call["input"]["source"]["url"] == ALPHA]
        assert len(bad) == 2
        assert bad[1]["input"]["repair"]["previous_output"] == '{"broken":'
        times = {call["input"]["research_context"]["as_of"] for call in h.calls}
        assert len(times) == 1
        analyst = h.role_calls("analyst")[0]["input"]
        assert '"supported_ranges"' in analyst["evidence"] and '"page_count":null' in analyst["evidence"]
        assert "GOOD_FINAL_LINE" in analyst["evidence"] and "BAD_FINAL_LINE" not in analyst["evidence"]


@pytest.mark.asyncio
async def test_unmatched_finding_is_removed_without_regenerating_verified_findings(tmp_path, monkeypatch):
    def respond(role, value, ordinal):
        if role == "baseline.selector": return _decision(value)
        if role == "baseline.distiller":
            result = _distillation(value)
            result["findings"].append({**result["findings"][0], "quote": "THIS QUOTE IS ABSENT"})
            return result
        if role == "baseline.writer": return valid_report(value)
        return None
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("VALID")}, respond=respond) as h:
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={"method_revision": 11})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.role_calls("distiller")) == 1
        evidence = h.role_calls("analyst")[0]["input"]["evidence"]
        assert "VALID_FINAL_LINE" in evidence and "THIS QUOTE IS ABSENT" not in evidence
        assert "Host excluded 1 findings" in evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("broken_role", ["planner", "selector", "analyst", "reviewer"])
async def test_runtime_rejected_json_is_repaired_without_a_success_outcome(tmp_path, monkeypatch, broken_role):
    # A fenced response is rejected by Runtime BEFORE invoke_role returns.
    # This is the actual failure boundary from the first live repair batch.
    invalid = '```json\n{"schema_version":1}\n```'
    def respond(role, value, ordinal):
        if role == "baseline." + broken_role and ordinal == 1:
            return invalid
        if role == "baseline.selector": return _decision(value)
        if role == "baseline.writer": return valid_report(value)
        return None
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("VALID")}, respond=respond) as h:
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={"method_revision": 11})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        calls = h.role_calls(broken_role)
        assert len(calls) == 2
        assert calls[1]["input"]["repair"]["previous_output"] == invalid
        events = await _events(h.service, view.run_id)
        repairs = [e for e in events if e["kind"] == "workflow.role.repair"]
        assert len(repairs) == 1 and repairs[0]["payload"]["output_ref"]
        assert any(e["kind"] == "invocation.outcome" and e["payload"]["status"] == "validation_failed"
                   and e["payload"]["export_receipt"] is None for e in events)
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        if broken_role == "selector":
            selected = next(s for s in result["selections"] if s["invoked"])
            retained = await _json(h.service, view.run_id, selected["input_ref"])
            assert retained == calls[-1]["input"]


@pytest.mark.asyncio
async def test_planner_query_budget_gets_one_bounded_content_repair(tmp_path, monkeypatch):
    def respond(role, value, ordinal):
        if role == "baseline.planner" and ordinal == 1:
            return {**deepcopy(PLAN), "queries": ["first", "over budget"]}
        if role == "baseline.selector": return _decision(value)
        if role == "baseline.writer": return valid_report(value)
        return None
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("VALID")}, respond=respond) as h:
        request = _request(max_queries=1, max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={"method_revision": 11})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.role_calls("planner")) == 2
        assert "query budget" in json.dumps(h.role_calls("planner")[1]["input"]["repair"])
        assert all(query == PLAN["queries"][0] for _, query in h.searches)


def test_forty_source_revision_preserves_roles_and_old_limits():
    from jsonschema import Draft202012Validator
    from deepresearch.methods.baseline.workflow import resource
    from deepresearch.methods.baseline.selection_workflow import SelectionBaselineMethod
    old = resource("parameters.schema.json", 11)
    new = resource("parameters.schema.json", 12)
    assert list(Draft202012Validator(old).iter_errors({"max_sources": 40}))
    assert not list(Draft202012Validator(new).iter_errors({"max_sources": 40}))
    assert list(Draft202012Validator(new).iter_errors({"max_sources": 41}))
    assert resource("method.json", 11)["agent_roles"] == resource("method.json", 12)["agent_roles"]
    assert SelectionBaselineMethod(12).defaults["max_sources"] == 40
    assert SelectionBaselineMethod(11).defaults["max_sources"] == 20
    assert new["properties"]["max_rounds"] == old["properties"]["max_rounds"]
    assert new["properties"]["max_distillation_calls"]["default"] == 20
