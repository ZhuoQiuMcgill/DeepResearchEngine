"""Discovery information survives projection, worker validation and recording."""
from __future__ import annotations

import asyncio

from jsonschema import Draft202012Validator
import pytest

from deepresearch.engine.agent import RecordedToolAction
from deepresearch.engine.contracts import ToolRef, ToolRequest
from deepresearch.engine.toolset import ToolCatalog
from deepresearch.engine.toolset.common import ToolFault, encode, strict_json
from deepresearch.engine.toolset.discovery_metadata import validate_coverage
from deepresearch.engine.toolset.process import ProcessOutcome
from deepresearch.engine.toolset.scholarly import project
from deepresearch.engine.toolset.search import search, search_plan
from deepresearch.engine.toolset.worker import registered_revision, run
from tests.toolset.test_recorded_pipeline import setup
from tests.toolset.test_search import engines


QUERY = '"Environment Based Design"'
ARGUMENTS = {"query": QUERY, "max_results": 5}


def crossref(row=None, total=1):
    return {"status": "ok", "message": {"total-results": total, "items": [row or {
        "title": ["Environment Based Design"], "DOI": "10.1234/ebd", "URL": "https://doi.org/10.1234/ebd",
        "author": [{"given": "Yong", "family": "Zeng", "ORCID": "https://orcid.org/0000-0000-0000-0000"}],
        "abstract": "<jats:p>Design <jats:italic>changes</jats:italic> environments &amp; artifacts.</jats:p><jats:p>Next paragraph.</jats:p>",
        "container-title": ["Design Journal"], "published": {"date-parts": [[2011, 8, 1]]},
        "is-referenced-by-count": 0,
        "link": [{"URL": "https://example.org/paper%2Fv1.pdf?literal=+&encoded=%2B", "content-type": "application/pdf"}],
    }]}}


def openalex(row=None):
    return {"meta": {"count": 8}, "results": [row or {
        "id": "https://openalex.org/W123", "title": "Environment Based Design", "publication_year": 2023,
        "authorships": [{"author": {"id": "https://openalex.org/A123", "display_name": "Yong Zeng"}}],
        "abstract_inverted_index": {"design": [1, 3], "Environment": [0], "supports": [2]},
        "primary_location": {"landing_page_url": "https://example.org/ebd",
                             "pdf_url": "https://example.org/paper.pdf", "is_oa": True,
                             "source": {"display_name": "Design Journal"}},
        "locations": [], "cited_by_count": 4,
    }]}


def valid(payload, provider):
    definition = ToolCatalog().resolve("scholar." + provider + ".search", 2).unwrap()
    assert not list(Draft202012Validator(definition.output_schema).iter_errors(payload))


def test_crossref_retains_authors_abstract_dates_and_exact_pdf_url():
    payload = project("crossref", crossref(total=20), ARGUMENTS, 2)
    valid(payload, "crossref")
    row = payload["results"][0]
    meta = row["bibliography"]
    assert meta["authors"][0]["name"] == "Yong Zeng"
    assert meta["authors_total"] == 1
    assert meta["abstract"] == "Design changes environments & artifacts. Next paragraph."
    assert meta["abstract_source"] == "crossref.abstract" and meta["abstract_normalization"] == "jats-text/1"
    assert meta["cited_by_count"] == 0 and "cited_by_count" not in meta["missing_fields"]
    assert meta["container_titles"] == ["Design Journal"]
    assert row["published_date_parts"] == [[2011, 8, 1]]
    assert row["links"][0]["url"] == "https://example.org/paper%2Fv1.pdf?literal=+&encoded=%2B"
    assert payload["coverage"] == {"scope": "first_page", "requested_max_results": 5, "returned_results": 1,
        "available_on_page": 1, "omitted_by_max_results": 0, "provider_total_results": 20, "more_results_available": True}
    assert payload["discovery_only"] is True


def test_openalex_reconstructs_actual_abstract_and_preserves_source_locations():
    payload = project("openalex", openalex(), ARGUMENTS, 2)
    valid(payload, "openalex")
    row = payload["results"][0]
    assert row["bibliography"]["abstract"] == "Environment design supports design"
    assert row["bibliography"]["authors"][0]["author_id"] == "https://openalex.org/A123"
    assert row["bibliography"]["authors"][0]["given"] is None
    assert row["primary_location"]["pdf_url"] == "https://example.org/paper.pdf"


@pytest.mark.parametrize("bad", [{"x": [True]}, {"x": [0], "y": [0]}, {"x": [1000000000]},
                                {"x": [-1]}, {"x": []}, [], "invented text"])
def test_bad_optional_abstract_does_not_destroy_valid_discoveries(bad):
    source = openalex()
    source["results"][0]["abstract_inverted_index"] = bad
    payload = project("openalex", source, ARGUMENTS, 2)
    valid(payload, "openalex")
    meta = payload["results"][0]["bibliography"]
    assert meta["abstract"] is None and meta["invalid_fields"] == ["abstract"]
    assert "abstract" not in meta["missing_fields"]


def test_missing_metadata_remains_null_and_is_not_generated_from_title():
    payload = project("crossref", crossref({"title": ["Only a title"]}), ARGUMENTS, 2)
    valid(payload, "crossref")
    meta = payload["results"][0]["bibliography"]
    assert meta["authors"] is meta["authors_total"] is meta["abstract"] is meta["cited_by_count"] is None
    assert meta["missing_fields"] == ["abstract", "authors", "cited_by_count", "container_titles"]
    assert not meta["invalid_fields"] and not meta["truncated_fields"]


def test_repeated_long_index_tokens_are_bounded_before_expansion():
    source = openalex()
    source["results"][0]["abstract_inverted_index"] = {"中" * 10000: list(range(1000))}
    payload = project("openalex", source, ARGUMENTS, 2)
    valid(payload, "openalex")
    meta = payload["results"][0]["bibliography"]
    assert len(meta["abstract"].encode()) == 16383
    assert meta["truncated_fields"] == ["abstract"]


def test_utf8_limits_and_omitted_authors_are_explicit():
    source = crossref()
    row = source["message"]["items"][0]
    row["author"] = [{"name": "中" * 200}] * 40
    row["abstract"] = "<p>" + "中" * 10000 + "</p>"
    payload = project("crossref", source, ARGUMENTS, 2)
    valid(payload, "crossref")
    meta = payload["results"][0]["bibliography"]
    assert len(meta["authors"]) == 32 and meta["authors_total"] == 40
    assert len(meta["abstract"].encode()) <= 16384
    assert len(meta["authors"][0]["name"].encode()) <= 512
    assert {"abstract", "authors", "authors[0].name"} <= set(meta["truncated_fields"])


def test_unsafe_optional_identifier_and_invalid_counter_are_not_published():
    source = crossref()
    source["message"]["items"][0]["author"][0]["ORCID"] = "https://example.org/?token=private"
    source["message"]["items"][0]["is-referenced-by-count"] = True
    meta = project("crossref", source, ARGUMENTS, 2)["results"][0]["bibliography"]
    assert meta["authors"][0]["orcid"] is None and meta["cited_by_count"] is None
    assert meta["invalid_fields"] == ["authors[0].orcid", "cited_by_count"]


def test_web_coverage_distinguishes_capped_page_from_unknown_global_recall(monkeypatch):
    rows = [{"title": "Ad", "href": "https://www.bing.com/aclick?x=ad", "body": "Ad"}]
    rows += [{"title": str(i), "href": f"https://example.org/{i}", "body": "" if i == 0 else "Snippet"} for i in range(4)]
    rows.append(rows[-1])
    engines(monkeypatch, yahoo_status=200, yahoo_rows=rows)
    payload, _, _, fault = search({"query": QUERY, "max_results": 2}, search_plan(3), 30, 3)
    assert fault is None
    assert payload["coverage"] == {"scope": "first_page", "requested_max_results": 2, "returned_results": 2,
        "available_on_page": 4, "omitted_by_max_results": 2, "provider_total_results": None, "more_results_available": True}
    assert payload["results"][0]["rank"] == 1 and payload["results"][0]["provider_rank"] == 2
    assert payload["results"][0]["domain"] == "example.org"
    assert set(payload["results"][0]["missing_fields"]) == {"snippet", "source_date"}
    schema = ToolCatalog().resolve("web.search", 3).unwrap().output_schema
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    payload, _, _, _ = search(ARGUMENTS, search_plan(3), 30, 3)
    assert payload["coverage"]["more_results_available"] is None
    assert payload["coverage"]["omitted_by_max_results"] == 0


def test_web_rev3_keeps_raw_failure_diagnostics_and_never_fakes_empty_success(monkeypatch):
    engines(monkeypatch, yahoo_status=403, duck_status=202)
    payload, observations, _, fault = search(ARGUMENTS, search_plan(3), 30, 3)
    assert payload is None and fault.code == "SEARCH_UNAVAILABLE"
    assert [row["failure_reason"] for row in observations["backend_attempts"]] == ["http_error", "http_challenge"]


@pytest.mark.parametrize("field,value", [("returned_results", 9), ("requested_max_results", 10),
                                        ("more_results_available", False), ("omitted_by_max_results", 1)])
def test_parent_rejects_inconsistent_worker_coverage(field, value):
    payload = project("crossref", crossref(total=20), ARGUMENTS, 2)
    payload["coverage"][field] = value
    with pytest.raises(ToolFault, match="coverage differs"):
        validate_coverage(payload, ARGUMENTS, scholarly=True)


def test_new_revisions_leave_old_payloads_and_unqualified_resolution_unchanged():
    old = project("crossref", crossref(), ARGUMENTS)
    assert "coverage" not in old and "bibliography" not in old["results"][0]
    assert ToolCatalog().resolve("web.search").unwrap().revision == 1
    assert ToolCatalog().resolve("scholar.crossref.search").unwrap().revision == 1
    assert registered_revision("web.search", 3) and registered_revision("scholar.openalex.search", 2)
    assert ToolCatalog().resolve("web.fetch").unwrap().revision == 1
    assert registered_revision("web.fetch", 3) and not registered_revision("web.fetch", 4)
    assert not registered_revision("web.search", True)


def test_baseline_upgrade_changes_search_bindings_without_changing_research_policy():
    from deepresearch.methods.baseline import definition
    old, new = definition(5), definition(6)
    assert new.tool_revisions == {"web.search": 3, "scholar.crossref.search": 2, "scholar.openalex.search": 2}
    assert new.agent_roles == old.agent_roles
    assert new.input_schema == old.input_schema and new.parameters_schema == old.parameters_schema


@pytest.mark.parametrize("bad_optional_link", [False, True])
def test_enriched_worker_output_is_recorded_and_exactly_readable(tmp_path, monkeypatch, bad_optional_link):
    from deepresearch.engine.toolset import scholarly
    source = crossref(total=20)
    if bad_optional_link:
        source["message"]["items"][0]["link"].append({"URL": "https://example.org/first https://example.org/second"})
    body = encode(source)
    def respond(*args, on_headers, **kwargs):
        facts = {"http_status": 200, "content_type": "application/json", "http_request_count": 1,
                 "http_response_count": 1, "response_transfer_bytes": len(body), "response_decoded_bytes": len(body)}
        on_headers(facts, [])
        return body, facts, None
    monkeypatch.setattr(scholarly, "request_body", respond)

    class ControlledWorker:
        memory_bytes = 512 << 20
        async def run(self, argv, payload, **kwargs):
            request = strict_json(payload, 1 << 20)
            response, code = run(request, argv[-2], int(argv[-1]))
            output = encode(response)
            return ProcessOutcome(exit_code=code, stdout=output, stdin_bytes=len(payload),
                                  stdout_bytes=len(output), cleanup_complete=True)
        async def close(self, deadline=None):
            return {"complete": True}

    async def check():
        store, context, binding = await setup(tmp_path / "store")
        binding.executor.runner = ControlledWorker()
        try:
            result = await RecordedToolAction().run(ToolRequest(ToolRef("scholar.crossref.search", 2), ARGUMENTS), binding, context)
            assert result.status == "succeeded" and result.recording["status"] == "complete"
            assert result.result["results"][0]["bibliography"]["authors"][0]["name"] == "Yong Zeng"
            row = result.result["results"][0]
            assert len(row["links"]) == 1
            assert ("links[1].url" in row["bibliography"]["invalid_fields"]) == bad_optional_link
            events = (await store.activity.query(context, {"run_id": context.run_id}, limit=100)).unwrap().events
            outcome = next(item["event"] for item in events if item["event"]["kind"] == "tool.outcome")
            assert outcome["payload"]["result_descriptor"]["sha256"]
            assert result.process["cleanup"]["complete"]
        finally:
            await binding.executor.close()
            await store.close()
    asyncio.run(check())
