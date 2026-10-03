"""Bounded retrieval over actual tool payload schemas and captured bad queries."""
from __future__ import annotations

import asyncio
import copy
import json

from jsonschema import Draft202012Validator
import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.engine.toolset import ToolCatalog
from deepresearch.engine.toolset.scholarly import project
from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDispatcher
from deepresearch.workflows.components.retrieval import retrieve_candidates
from tests.workflows.test_components import Port, context

TOPIC = "Environment Based Design"
QUESTION = "What is EBD (Environment Based Design)?"
FOUNDATION = "Axiomatic theory of design modeling"
CAPTURED_RETRIEVAL = ('retrieve full text of Zeng\'s originating EBD publication (e.g., '
    '"Environment-based formulation of design problem", Transactions of the SDPS, 2004) '
    'to obtain the primary definition and core principles of EBD')
CAPTURED_COMPARISON = "Environment-Based Design EBD compared with TRIZ axiomatic design C-K theory situated FBS differences"
CAPTURED_LONG = "Zeng Environment-based design (EBD) methodology for transdisciplinary design core principles environment decomposition conflict identification solution generation"


def web(rows=(), query="query"):
    return {"query": query, "searched_at": "2026-10-02T00:00:00Z",
        "backend_policy": {"configured_order": ["yahoo", "duckduckgo", "google"],
            "active_order": ["yahoo", "duckduckgo"],
            "disabled_backends": [{"backend": "google", "reason": "URL_FIDELITY_GATE_PENDING"}]},
        "backend_attempts": [],
        "results": [{"rank": i, "title": row[0], "url": row[1], "raw_url": row[1],
            "snippet": row[2] if len(row) > 2 else "", "source_date": None,
            "backend": "duckduckgo", "declared_provider": "bing", "discovery_only": True,
            "truncated_fields": []} for i, row in enumerate(rows, 1)]}


def crossref(rows=(), query="query"):
    return project("crossref", {"status": "ok", "message": {"total-results": len(rows), "items": list(rows)}},
                   {"query": query, "max_results": 10})


def openalex(rows=(), query="query"):
    return project("openalex", {"meta": {"count": len(rows)}, "results": list(rows)},
                   {"query": query, "max_results": 10})


def successful(name, payload):
    revision = 2 if name == "web.search" else 1
    schema = ToolCatalog().resolve(name, revision).unwrap().output_schema
    Draft202012Validator(schema).validate(payload)
    return {"status": "succeeded", "recording": {"status": "complete"},
        "result": payload, "error": None}


class SearchPort(Port):
    def __init__(self, respond=None):
        super().__init__()
        self.respond = respond or (lambda name, args: {"web.search": web, "scholar.crossref.search": crossref,
                                                      "scholar.openalex.search": openalex}[name](query=args["query"]))

    async def run_tool(self, name, arguments):
        self.reads.append((name, copy.deepcopy(arguments)))
        value = self.respond(name, arguments)
        if isinstance(value, BaseException):
            raise value
        if "status" in value:
            return copy.deepcopy(value)
        return successful(name, value)

    async def publish(self, content, media_type, filename):
        self.publications.append((content, media_type, filename))
        return {"store_id": "test", "artifact_id": f"artifact-{len(self.publications)}"}

    def artifact(self, ref):
        return json.loads(self.publications[int(ref["artifact_id"].split("-")[-1]) - 1][0])


def candidates(entries):
    return [candidate for entry in entries for candidate in entry["candidates"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [QUESTION, CAPTURED_LONG, CAPTURED_COMPARISON,
    "Environment Based Design definition ecological eco-design sustainability lifecycle assessment green innovation"])
async def test_subject_queries_do_not_expand_into_speculative_definition_vocabulary(query):
    port = SearchPort(lambda name, args: web([(TOPIC, "https://university.edu/research.pdf")], args["query"]))
    original = {"question": QUESTION, "queries": [query]}
    items, entries = await retrieve_candidates(context(port), original["queries"], ["web.search"], 5, topic=TOPIC)
    executed = port.reads[0][1]["query"]
    assert TOPIC in executed and len(executed.split()) <= 8
    assert not any(term.casefold() in executed.casefold() for term in ("eco-design", "sustainability", "TRIZ", "C-K", "FBS", "transdisciplinary"))
    assert original == {"question": QUESTION, "queries": [query]}
    assert items and entries[0]["original_query"] == query
    assert port.artifact(entries[0]["preparation_ref"])["original_query"] == query


@pytest.mark.asyncio
async def test_failed_long_query_recovers_with_standalone_exact_cited_title():
    exact = '"Environment-based formulation of design problem"'
    def respond(name, args):
        rows = [("Environment-based formulation of design problem", "https://users.example.edu/~zeng/foundation.pdf")]
        return web(rows if args["query"] == exact else [], args["query"])
    port = SearchPort(respond)
    items, entries = await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL], ["web.search"], 5, topic=TOPIC)
    assert port.reads[0][1]["query"] == '"Environment Based Design" "Environment-based formulation of design problem" Zeng 2004'
    assert [args["query"] for _, args in port.reads] == [entries[0]["query"], exact]
    assert items[0].url.endswith("foundation.pdf")
    assert entries[1]["recovery_index"] == 1
    assert port.artifact(entries[1]["artifact_ref"])["result"]["query"] == exact


@pytest.mark.asyncio
async def test_global_recovery_limit_and_distinct_queries_span_all_input_queries():
    port = SearchPort()
    queries = [CAPTURED_RETRIEVAL, 'Retrieve Zeng\'s "Axiomatic theory of design modeling" from 2002']
    _, entries = await retrieve_candidates(context(port), queries, ["web.search"], 5, topic=TOPIC, recovery_limit=4)
    recoveries = [entry for entry in entries if entry["recovery_index"]]
    assert [entry["recovery_index"] for entry in recoveries] == [1, 2, 3, 4]
    executed = [args["query"] for _, args in port.reads]
    assert len(set(executed)) == len(executed)
    assert len([entry for entry in entries if not entry["recovery_index"]]) == 2
    assert port.artifact(entries[-1]["candidates_ref"])["recovery_used"] == 4


@pytest.mark.asyncio
async def test_explicit_query_is_preserved_byte_for_byte_and_zero_recovery_disables_variants():
    explicit = "  environment-based design + title:axiomatic modeling  "
    port = SearchPort()
    _, entries = await retrieve_candidates(context(port), [explicit], ["web.search"], 5,
        topic=TOPIC, rewrite_queries=False, recovery_limit=0)
    assert port.reads == [("web.search", {"query": explicit, "max_results": 5})]
    assert entries[0]["query"] == explicit
    assert port.artifact(entries[0]["preparation_ref"])["preparation"] == "host_literal_query"


@pytest.mark.asyncio
async def test_retained_source_ids_are_not_external_queries_and_are_archived_as_preparation():
    port = SearchPort()
    items, entries = await retrieve_candidates(context(port),
        ["retrieve complete sections of requested-001 and requested-002 to strengthen evidence"],
        ["web.search"], 5, topic=TOPIC, source_ids=("requested-001", "requested-002"))
    assert items == entries == [] and port.reads == []
    prep = json.loads(port.publications[0][0])
    assert prep["preparation"] == "references_retained_source" and prep["executed_query"] is None


@pytest.mark.asyncio
async def test_only_actual_cited_title_admits_foundation_without_topic_phrase():
    query = 'retrieve Zeng\'s "Axiomatic theory of design modeling" from 2002'
    port = SearchPort(lambda name, args: web([
        ("Evidence-Based Dentistry", "https://example.org/dentistry", "Zeng EBD"),
        ("Evidence-Based Design", "https://example.org/evidence-design", FOUNDATION),
        (FOUNDATION, "https://example.edu/foundation.pdf", "A foundational design theory"),
        ("Another foundation", "https://example.org/zeng", "Zeng's design methodology")], args["query"]))
    items, entries = await retrieve_candidates(context(port), [query], ["web.search"], 5, topic=TOPIC)
    assert {item.url for item in items} == {"https://example.edu/foundation.pdf"}
    decisions = port.artifact(entries[0]["selection_ref"])["decisions"]
    assert [row["reason"] for row in decisions] == ["topic_or_cited_title_missing", "topic_or_cited_title_missing", "cited_title_cue", "topic_or_cited_title_missing"]


@pytest.mark.asyncio
async def test_trial1_crossref_process_dto_rejects_three_unrelated_bsi_standards():
    # Projected DTO rows retained in the closed baseline5 trial1 store. The
    # regression is self-contained and does not require that private database.
    titles = [
        "Building environment design. Indoor environment. Design process for visual environment",
        "Building environment design.Indoor environment. Design process for the visual environment",
        "Building environment design.Indoor environment. Design process for the visual environment"]
    standards = [
        {"doi": doi, "doi_url": "https://doi.org/" + doi, "links": [], "member_id": "1988",
         "published_date_parts": None, "publisher": "BSI British Standards", "rank": index,
         "titles": [title], "work_type": "standard"}
        for index, (doi, title) in enumerate(zip(
            ["10.3403/30228061", "10.3403/30228061u", "10.3403/30296815"], titles), 1)]
    payload = crossref([])
    payload["results"] = standards + [
        {"doi": "10.1201/9781439809136-50", "doi_url": "https://doi.org/10.1201/9781439809136-50",
         "links": [], "member_id": "301", "published_date_parts": [[2009, 6, 5]],
         "publisher": "CRC Press", "rank": 4, "titles": ["Web-Based Modules for Product and Process Design"],
         "work_type": "book-chapter"},
        {"doi": "10.3233/jid-2014-0014", "doi_url": "https://doi.org/10.3233/jid-2014-0014",
         "links": [{"content_type": "unspecified", "content_version": "vor",
                    "intended_application": "similarity-checking",
                    "url": "https://content.iospress.com/download?id=10.3233/jid-2014-0014"}],
         "member_id": "179", "published_date_parts": [[2014]], "publisher": "SAGE Publications",
         "rank": 5, "titles": ["Environment Based Design of Services"], "work_type": "journal-article"}]
    query = "Environment Based Design origin theory design process application case study"
    payload["query"] = '"Environment Based Design" process'
    port = SearchPort(lambda name, args: payload)
    items, entries = await retrieve_candidates(context(port), [query], ["scholar.crossref.search"], 5,
        topic=TOPIC, node_prefix="r1.")
    assert {item.url for item in items} == {
        "https://content.iospress.com/download?id=10.3233/jid-2014-0014",
        "https://doi.org/10.3233/jid-2014-0014"}
    assert port.reads == [("scholar.crossref.search", {"query": payload["query"], "max_results": 5})]
    assert port.artifact(entries[0]["artifact_ref"])["result"] == payload
    decisions = port.artifact(entries[0]["selection_ref"])["decisions"]
    assert [decision["accepted"] for decision in decisions] == [False, False, False, False, True]
    assert [decision["title"] for decision in decisions[:3]] == titles
    assert all(decision["reason"] == "topic_or_cited_title_missing" for decision in decisions[:4])


@pytest.mark.asyncio
@pytest.mark.parametrize("title,snippet,accepted", [
    ("Attribute encryption standards", "", False),
    ("Attribute encoding and encryption based on compliance", "", False),
    ("Encryption based attribute management", "", False),
    ("Attribute-based encryption of files", "", True),
    ("Superattribute-based encryption", "", False),
    ("Attribute Based", "Encryption", False),
    ("Cryptographic primer", "Attribute-based encryption protects files", True),
])
async def test_generic_topic_screen_preserves_complete_phrase_and_field_boundaries(title, snippet, accepted):
    topic = "Attribute Based Encryption"
    port = SearchPort(lambda name, args: web([(title, "https://example.edu/source.pdf", snippet)], args["query"]))
    items, entries = await retrieve_candidates(context(port), [topic], ["web.search"], 5,
        topic=topic, recovery_limit=0)
    assert bool(items) is accepted
    decision = port.artifact(entries[0]["selection_ref"])["decisions"][0]
    assert decision["accepted"] is accepted
    assert decision["reason"] == ("topic_phrase" if accepted else "topic_or_cited_title_missing")


@pytest.mark.asyncio
async def test_separate_crossref_titles_cannot_invent_a_topic_phrase():
    port = SearchPort(lambda name, args: crossref([
        {"title": ["Attribute Based", "Encryption"], "DOI": "10.1234/unrelated",
         "URL": "https://doi.org/10.1234/unrelated"}], args["query"]))
    items, entries = await retrieve_candidates(context(port), ["Attribute Based Encryption"],
        ["scholar.crossref.search"], 5, topic="Attribute Based Encryption")
    assert items == [] and entries[0]["candidates"] == []


@pytest.mark.asyncio
async def test_cited_title_must_match_returned_title_on_word_boundaries_not_snippet_or_author():
    query = 'retrieve Zeng\'s "Axiomatic theory of design modeling" from 2002'
    port = SearchPort(lambda name, args: web([
        ("Reaxiomatic theory of design modeling", "https://example.edu/partial-word.pdf"),
        ("Another foundation", "https://example.edu/snippet.pdf", FOUNDATION + " by Zeng"),
        ("(PDF) " + FOUNDATION + " | University Library", "https://example.edu/foundation.pdf")], args["query"]))
    items, entries = await retrieve_candidates(context(port), [query], ["web.search"], 5, topic=TOPIC)
    assert [item.url for item in items] == ["https://example.edu/foundation.pdf"]
    decisions = port.artifact(entries[0]["selection_ref"])["decisions"]
    assert [decision["accepted"] for decision in decisions] == [False, False, True]


@pytest.mark.asyncio
async def test_trial1_actual_sage_doi_path_groups_truncated_title_with_crossref_alternatives():
    title = "Environment-Based Design (EBD): a Methodology for Transdisciplinary ..."
    landing = "https://journals.sagepub.com/doi/full/10.3233/jid-2015-0004"
    download = "https://content.iospress.com/download?id=10.3233/jid-2015-0004"
    doi_url = "https://doi.org/10.3233/jid-2015-0004"
    def respond(name, args):
        if name == "web.search":
            return web([(title, landing)], args["query"])
        return crossref([{"title": ["Environment-Based Design (EBD): a Methodology for Transdisciplinary Design+"],
            "DOI": "10.3233/jid-2015-0004", "URL": doi_url,
            "link": [{"URL": download, "content-type": "unspecified", "content-version": "vor",
                      "intended-application": "similarity-checking"}]}], args["query"])
    port = SearchPort(respond)
    items, entries = await retrieve_candidates(context(port), [TOPIC], ["web.search", "scholar.crossref.search"],
        5, topic=TOPIC)
    assert {item.url for item in items} == {landing, download, doi_url}
    assert {json.loads(item.reason.removeprefix("retrieval/1 "))["work_id"] for item in items} == {
        "doi:10.3233/jid-2015-0004"}
    final = port.artifact(entries[0]["candidates_ref"])
    assert final["works"] == {"doi:10.3233/jid-2015-0004": [item.item_id for item in items]}
    assert candidates(entries)[0]["title"] == title


@pytest.mark.asyncio
async def test_a_doi_mention_outside_explicit_doi_url_path_does_not_guess_work_identity():
    url = "https://example.edu/search/10.1234/foundation"
    port = SearchPort(lambda name, args: web([(TOPIC, url)], args["query"]))
    items, _ = await retrieve_candidates(context(port), [TOPIC], ["web.search"], 5, topic=TOPIC)
    assert json.loads(items[0].reason.removeprefix("retrieval/1 "))["work_id"].startswith("title:sha256:")


@pytest.mark.asyncio
async def test_dentistry_is_valid_when_it_is_the_actual_topic():
    port = SearchPort(lambda name, args: web([("Evidence-Based Dentistry", "https://example.org/dentistry")], args["query"]))
    items, _ = await retrieve_candidates(context(port), ["dentistry evidence"], ["web.search"], 5, topic="Evidence-Based Dentistry")
    assert len(items) == 1


@pytest.mark.asyncio
async def test_crossref_enumerates_all_links_and_doi_without_constructing_pdf_routes():
    doi = "10.3233/JID-2004-8404"
    row = {"title": ["Environment-based formulation of design problem"], "DOI": doi,
        "URL": "https://doi.org/"+doi, "link": [
            {"URL": "https://publisher.example/article.pdf", "content-type": "application/pdf"},
            {"URL": "https://author.example.edu/research.pdf", "content-type": "application/pdf"},
            {"URL": "https://publisher.example/article", "content-type": "text/html"}]}
    payload = crossref([row])
    port = SearchPort(lambda name, args: payload)
    items, entries = await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL], ["scholar.crossref.search"], 5, topic=TOPIC)
    assert [item.url for item in items] == ["https://author.example.edu/research.pdf", "https://publisher.example/article.pdf",
                                          "https://publisher.example/article", "https://doi.org/"+doi]
    assert {candidate["work_id"] for candidate in candidates(entries)} == {"doi:10.3233/jid-2004-8404"}
    assert all(item.url in {link["URL"] for link in row["link"]} | {row["URL"]} for item in items)
    assert port.artifact(entries[0]["artifact_ref"])["result"] == payload


@pytest.mark.asyncio
async def test_openalex_enumerates_every_actual_oa_pdf_landing_and_doi_location():
    row = {"id": "https://openalex.org/W12345", "title": TOPIC, "doi": "https://doi.org/10.1234/paper",
        "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://repository.example/open"},
        "best_oa_location": {"pdf_url": "https://university.edu/paper.pdf", "landing_page_url": "https://university.edu/paper", "is_oa": True},
        "primary_location": {"pdf_url": "https://publisher.example/paper.pdf", "landing_page_url": "https://publisher.example/paper"},
        "locations": [{"pdf_url": "https://authors.example/~zeng/paper.pdf", "landing_page_url": "https://repository.example/paper", "is_oa": True},
            {"pdf_url": "https://other.example/oa.pdf", "landing_page_url": "https://scispace.com/paper", "is_oa": True}]}
    payload = openalex([row])
    port = SearchPort(lambda name, args: payload)
    items, entries = await retrieve_candidates(context(port), [TOPIC], ["scholar.openalex.search"], 5, topic=TOPIC)
    assert {item.url for item in items} == {"https://repository.example/open", "https://university.edu/paper.pdf", "https://university.edu/paper",
        "https://publisher.example/paper.pdf", "https://publisher.example/paper", "https://authors.example/~zeng/paper.pdf",
        "https://repository.example/paper", "https://other.example/oa.pdf", "https://scispace.com/paper", "https://doi.org/10.1234/paper"}
    assert len(items) == 10 and items[0].url.endswith("paper.pdf") and items[-1].url == "https://scispace.com/paper"
    assert {candidate["work_id"] for candidate in candidates(entries)} == {"doi:10.1234/paper"}


@pytest.mark.asyncio
async def test_dedup_and_unique_title_reconciliation_make_alternatives_one_work():
    def respond(name, args):
        if name == "web.search":
            return web([(TOPIC, "https://author.example.edu/full.pdf"), (TOPIC, "https://researchgate.net/paper")], args["query"])
        if name == "scholar.crossref.search":
            return crossref([{"title": [TOPIC], "DOI": "10.1234/FOUNDATION", "URL": "https://doi.org/10.1234/foundation",
                "link": [{"URL": "https://author.example.edu/full.pdf", "content-type": "application/pdf"}]}], args["query"])
        return openalex([{ "id": "https://openalex.org/W9876", "title": TOPIC, "doi": "https://doi.org/10.1234/foundation",
            "locations": [{"pdf_url": "https://oa.example/alternate.pdf", "is_oa": True}]}], args["query"])
    port = SearchPort(respond)
    items, entries = await retrieve_candidates(context(port), [TOPIC], ["web.search", "scholar.crossref.search", "scholar.openalex.search"], 5, topic=TOPIC)
    assert len(items) == 4 and len({item.url for item in items}) == 4
    reasons = [json.loads(item.reason.removeprefix("retrieval/1 ")) for item in items]
    assert {reason["work_id"] for reason in reasons} == {"doi:10.1234/foundation"}
    assert items[-1].url == "https://researchgate.net/paper"
    final = port.artifact(entries[0]["candidates_ref"])
    assert final["works"] == {"doi:10.1234/foundation": [item.item_id for item in items]}
    assert {candidate["work_id"] for candidate in candidates(entries)} == {"doi:10.1234/foundation"}


@pytest.mark.asyncio
async def test_same_title_with_distinct_actual_dois_does_not_merge_them():
    port = SearchPort(lambda name, args: crossref([
        {"title": [TOPIC], "DOI": "10.1234/first", "URL": "https://doi.org/10.1234/first"},
        {"title": [TOPIC], "DOI": "10.1234/second", "URL": "https://doi.org/10.1234/second"}], args["query"]))
    _, entries = await retrieve_candidates(context(port), [TOPIC], ["scholar.crossref.search"], 5, topic=TOPIC)
    assert {candidate["work_id"] for candidate in candidates(entries)} == {"doi:10.1234/first", "doi:10.1234/second"}


@pytest.mark.asyncio
async def test_source_ids_never_collide_across_queries_recoveries_or_caller_prefixes():
    port = SearchPort(lambda name, args: web([(TOPIC, "https://scribd.com/"+str(len(port.reads)))], args["query"]))
    ctx = context(port)
    items, _ = await retrieve_candidates(ctx, [CAPTURED_RETRIEVAL], ["web.search"], 5, topic=TOPIC,
        node_prefix="r1.", source_ids=("r1.source-001", "r1.source-003"), recovery_limit=4)
    more, _ = await retrieve_candidates(ctx, [CAPTURED_RETRIEVAL], ["web.search"], 5, topic=TOPIC,
        node_prefix="r1.recovery.", source_ids=tuple(item.item_id for item in items), recovery_limit=1)
    ids = [item.item_id for item in items + more]
    assert len(ids) == len(set(ids)) and not set(ids) & {"r1.source-001", "r1.source-003"}
    assert any(".discovery.0.1." in node_id for node_id in ctx.nodes)
    assert all(node["status"] == "succeeded" for node in ctx.nodes.values())
    assert any(kind == "workflow.node.started" for kind, _ in port.events)


@pytest.mark.asyncio
async def test_known_openalex_quota_denial_is_recorded_once_without_escalation():
    def respond(name, args):
        if name == "scholar.openalex.search":
            return {"status": "limit_exhausted", "recording": {"status": "complete"},
                "error": {"code": "SCHOLAR_QUOTA_EXHAUSTED", "observed_effect_state": "unknown", "commit_state": "not_applicable"},
                "process": {"dispatched":False, "cleanup":{"complete":True}},
                "persistence": {"commit_state":"not_applicable"}}
        return web([], args["query"]) if name == "web.search" else crossref([], args["query"])
    port = SearchPort(respond)
    _, entries = await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL],
        ["web.search", "scholar.crossref.search", "scholar.openalex.search"], 5, topic=TOPIC)
    denied = [entry for entry in entries if entry["tool"] == "scholar.openalex.search"]
    assert len(denied) == 1 and denied[0]["status"] == "limit_exhausted"
    assert port.artifact(denied[0]["artifact_ref"])["error"]["code"] == "SCHOLAR_QUOTA_EXHAUSTED"
    assert all(set(args) == {"query", "max_results"} for _, args in port.reads)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,code", [
    ({"status":"failed", "recording":{"status":"incomplete"}}, "RECORDING_INCOMPLETE"),
    ({"status":"cancelled", "recording":{"status":"complete"}, "error":{"code":"CANCELLED"}}, "CANCELLED"),
    ({"status":"timed_out", "recording":{"status":"complete"}, "error":{"code":"DEADLINE_EXCEEDED"}}, "DEADLINE_EXCEEDED"),
    ({"status":"limit_exhausted", "recording":{"status":"complete"}, "error":{"code":"LIMIT_EXCEEDED"}}, "LIMIT_EXCEEDED"),
    ({"status":"unknown", "recording":{"status":"complete"}}, "DISCOVERY_UNKNOWN"),
    ({"status":"failed", "recording":{"status":"complete"}, "error":{"commit_state":"unknown"}}, "DISCOVERY_UNKNOWN"),
    ({"status":"failed", "recording":{"status":"complete"}, "error":{"observed_effect_state":"unknown"}}, "DISCOVERY_UNKNOWN"),
    ({"status":"failed", "recording":{"status":"complete"}, "process":{"cleanup":{"complete":False}}}, "CLEANUP_INCOMPLETE"),
])
async def test_unsafe_outcome_stops_before_any_backend_fallback_or_query_recovery(outcome, code):
    port = SearchPort(lambda name, args: outcome)
    ctx = context(port)
    with pytest.raises(EngineError) as error:
        await retrieve_candidates(ctx, [CAPTURED_RETRIEVAL], ["web.search", "scholar.crossref.search"], 5, topic=TOPIC)
    assert error.value.code == code and len(port.reads) == 1
    assert ctx.nodes["discovery.0.0.0"]["status"] == ("cancelled" if code == "CANCELLED" else "failed")


@pytest.mark.asyncio
async def test_async_cancellation_propagates_without_fallback():
    port = SearchPort(lambda name, args: asyncio.CancelledError())
    ctx = context(port)
    with pytest.raises(asyncio.CancelledError):
        await retrieve_candidates(ctx, [TOPIC], ["web.search", "scholar.crossref.search"], 5, topic=TOPIC)
    assert len(port.reads) == 1 and ctx.nodes["discovery.0.0.0"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_raw_backend_outcome_is_preserved_even_when_every_result_is_screened_out():
    payload = web([("Evidence-Based Dentistry", "https://example.org/dentistry")])
    port = SearchPort(lambda name, args: payload)
    items, entries = await retrieve_candidates(context(port), [TOPIC], ["web.search"], 5, topic=TOPIC, recovery_limit=0)
    assert items == [] and len(entries) == 1
    assert port.artifact(entries[0]["artifact_ref"])["result"] == payload
    assert port.artifact(entries[0]["selection_ref"])["accepted_count"] == 0


@pytest.mark.asyncio
async def test_helper_does_not_apply_parent_fetch_budget_or_drop_location_alternatives():
    row = {"id":"https://openalex.org/W100", "title":TOPIC,
        "locations":[{"pdf_url":f"https://repository.example/{i}.pdf", "is_oa":True} for i in range(24)]}
    port = SearchPort(lambda name, args: openalex([row], args["query"]))
    items, _ = await retrieve_candidates(context(port), [TOPIC], ["scholar.openalex.search"], 5, topic=TOPIC)
    assert len(items) == 24 and all(name.endswith(".search") for name, _ in port.reads)


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"recovery_limit":5},{"recovery_limit":-1},{"recovery_limit":True},
    {"max_results":11},{"search_tools":["web.fetch"]},{"rewrite_queries":"false"}])
async def test_invalid_limits_and_tool_selections_fail_without_external_dispatch(overrides):
    args = {"queries":[TOPIC], "search_tools":["web.search"], "max_results":5, "topic":TOPIC, **overrides}
    port = SearchPort()
    with pytest.raises(EngineError) as error:
        await retrieve_candidates(context(port), **args)
    assert error.value.code == "INVALID_DATA" and not port.reads


@pytest.mark.asyncio
async def test_quoted_author_cue_cannot_admit_a_foundation_without_cited_title():
    port = SearchPort(lambda name, args: web([(FOUNDATION, "https://university.edu/foundation.pdf", "By Yong Zeng")], args["query"]))
    items, entries = await retrieve_candidates(context(port), ['"Environment Based Design" "Yong Zeng"'], ["web.search"], 5, topic=TOPIC, recovery_limit=0)
    assert items == []
    assert port.artifact(entries[0]["preparation_ref"])["author_cues"] == ["Yong Zeng"]
    assert port.artifact(entries[0]["selection_ref"])["decisions"][0]["reason"] == "topic_or_cited_title_missing"


@pytest.mark.asyncio
async def test_standalone_cited_title_is_exact_even_above_keyword_length():
    title = "Axiomatic theory of design modeling " + "and its mathematical foundations " * 8
    title = title.strip()
    exact = '"' + title + '"'
    port = SearchPort(lambda name, args: web([(title, "https://university.edu/foundation.pdf")] if args["query"] == exact else [], args["query"]))
    items, _ = await retrieve_candidates(context(port), ['retrieve Zeng\'s '+exact], ["web.search"], 5, topic=TOPIC)
    assert items and port.reads[1][1]["query"] == exact


@pytest.mark.asyncio
async def test_real_observers_receive_preparation_backend_and_final_selection_nodes():
    observed = []
    async def observe(event):
        observed.append(event.to_dict())
    registry = ExtensionRegistry()
    registry.register(ExtensionSpec("retrieval.observer", "v1", ("node.before", "node.after", "node.failed")), observe)
    port = SearchPort(lambda name, args: web([(TOPIC, "https://example.edu/source.pdf")], args["query"]))
    ctx = context(port)
    ctx.hooks = HookDispatcher(registry, port.emit)
    await retrieve_candidates(ctx, [TOPIC], ["web.search"], 5, topic=TOPIC)
    assert {event["payload"]["kind"] for event in observed} == {"query_preparation", "discovery", "discovery_selection"}
    assert all(set(event["payload"]) == {"kind", "status", "detail_sha256"} for event in observed)
    assert (await ctx.hooks.close()).complete


@pytest.mark.asyncio
async def test_quota_code_cannot_disguise_cancellation_or_unknown_commitment():
    for status, extra in [("cancelled", {}), ("limit_exhausted", {"commit_state":"unknown"})]:
        port = SearchPort(lambda name, args: {"status":status, "recording":{"status":"complete"},
            "error":{"code":"SCHOLAR_QUOTA_EXHAUSTED", **extra}})
        with pytest.raises(EngineError):
            await retrieve_candidates(context(port), [TOPIC], ["scholar.openalex.search"], 5, topic=TOPIC)
        assert len(port.reads) == 1


@pytest.mark.asyncio
async def test_unknown_outcome_keeps_its_raw_artifact_reference_on_the_failed_node():
    outcome = {"status":"unknown", "recording":{"status":"complete"}, "error":{"commit_state":"unknown"}}
    port = SearchPort(lambda name, args: outcome)
    ctx = context(port)
    with pytest.raises(EngineError):
        await retrieve_candidates(ctx, [TOPIC], ["web.search"], 5, topic=TOPIC)
    raw_ref = ctx.nodes["discovery.0.0.0"]["detail"]["artifact_ref"]
    assert port.artifact(raw_ref) == outcome


@pytest.mark.asyncio
async def test_unknown_archive_commitment_stops_without_repeating_discovery():
    class ArchiveFaultPort(SearchPort):
        async def publish(self, content, media_type, filename):
            if filename.endswith("discovery.0.0.0.json"):
                raise EngineError("COMMIT_UNKNOWN", "Controlled archive failure", commit_state="unknown")
            return await super().publish(content, media_type, filename)
    port = ArchiveFaultPort()
    with pytest.raises(EngineError) as error:
        await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL], ["web.search", "scholar.crossref.search"], 5, topic=TOPIC)
    assert error.value.commit_state == "unknown" and len(port.reads) == 1


@pytest.mark.asyncio
async def test_invalid_non_http_locations_are_not_candidates_or_replacement_urls():
    row = {"title":[TOPIC], "DOI":"10.1234/paper", "URL":None,
        "link":[{"URL":"javascript:paper", "content-type":"application/pdf"}]}
    payload = crossref([])
    payload["results"] = [{"rank":1, "titles":row["title"], "doi":row["DOI"], "doi_url":None,
        "member_id":None,"publisher":None,"work_type":None,"published_date_parts":None,
        "links":[{"url":"javascript:paper", "content_type":"application/pdf", "content_version":None, "intended_application":None}]}]
    port = SearchPort(lambda name, args: payload)
    items, entries = await retrieve_candidates(context(port), [TOPIC], ["scholar.crossref.search"], 5, topic=TOPIC)
    assert items == [] and entries[0]["candidates"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"status":"cancelled"}, {"status":"timed_out"},
    {"error":{"code":"LIMIT_EXCEEDED"}},
    {"error":{"commit_state":"unknown"}},
    {"persistence":{"commit_state":"unknown"}},
    {"process":{"dispatched":True}},
    {"process":{"dispatched":None}},
    {"process":{"cleanup":{"complete":False}}},
    {"recording":{"status":"incomplete"}},
])
async def test_admission_exemption_requires_all_proofs_and_never_masks_shared_failure(change):
    outcome = {"status":"limit_exhausted", "recording":{"status":"complete"},
        "error":{"code":"SCHOLAR_QUOTA_EXHAUSTED", "observed_effect_state":"unknown", "commit_state":"not_applicable"},
        "process":{"dispatched":False, "cleanup":{"complete":True}},
        "persistence":{"commit_state":"not_applicable"}}
    for field, value in change.items():
        if isinstance(value,dict): outcome[field].update(value)
        else: outcome[field] = value
    port = SearchPort(lambda name,args: outcome)
    with pytest.raises(EngineError):
        await retrieve_candidates(context(port), [TOPIC], ["scholar.openalex.search", "web.search"], 5, topic=TOPIC)
    assert len(port.reads) == 1


@pytest.mark.asyncio
async def test_default_openalex_admission_denial_uses_real_engine_storage_without_dispatch(tmp_path, monkeypatch):
    from deepresearch.application.platform import ResearchPlatformPort
    from deepresearch.application.research_runs import LiveResearchRun
    from deepresearch.engine import Engine, EngineSettings, RunOptions
    from deepresearch.engine.contracts import ArtifactRef, ToolRef, to_json_value
    from deepresearch.workflows import ResearchRunView
    engine = (await Engine.open(EngineSettings(workspace=tmp_path,storage_root=tmp_path/"store"))).unwrap()
    session = None
    try:
        async def forbidden_worker(*args, **kwargs):
            pytest.fail("Host admission denial must not dispatch a worker")
        monkeypatch.setattr(engine.executor.runner, "run", forbidden_worker)
        ref = ToolRef("scholar.openalex.search")
        session = (await engine.open_workflow_session(tools=(ref,),invocation_rules=(), options=RunOptions(timeout_seconds=20))).unwrap()
        view = ResearchRunView(run_id=session.context.run_id,method_id="retrieval-test",method_revision=1,
            client_request_id="denial-test",accepted_at="2026-10-02T00:00:00Z",status="running",active=True)
        live = LiveResearchRun(session,view,"sha256:"+"0"*64,(ref,))
        port = ResearchPlatformPort(engine,live,{})
        ctx = context(port)
        ctx.run_id = view.run_id
        calls = []
        native = port.run_tool
        async def capture(name,arguments):
            value = await native(name,arguments)
            calls.append(value)
            return value
        monkeypatch.setattr(port,"run_tool",capture)
        items, entries = await retrieve_candidates(ctx, [QUESTION, CAPTURED_RETRIEVAL],
            ["scholar.openalex.search"], 5, topic=TOPIC)
        assert items == [] and len(entries) == len(calls) == 1
        outcome = calls[0]
        assert outcome["error"]["code"] == "SCHOLAR_QUOTA_EXHAUSTED"
        assert outcome["error"]["observed_effect_state"] == "unknown"
        assert outcome["process"]["dispatched"] is False
        assert outcome["recording"]["status"] == "complete"
        assert port.failure is None and ctx.nodes["discovery.0.0.0"]["status"] == "succeeded"
        raw = await port.read_artifact(entries[0]["artifact_ref"])
        assert json.loads(raw) == outcome
        assert not engine.executor.quotas["openalex"].reservations
        assert session.context.ledger.used["tool_calls"] == 1
    finally:
        if session is not None:
            assert (await session.close()).complete
        assert (await engine.close()).complete


def settled_search_unavailable():
    """Critical native fields inspected in the closed live2 outcome artifact."""
    return {"status": "failed", "tool": {"name": "web.search", "revision": 2}, "result": None,
        "error": {"code": "SEARCH_UNAVAILABLE", "message": "Named backends returned no usable discovery; inspect backend_attempts",
                  "details": {}, "observed_effect_state": "unknown", "commit_state": "not_applicable", "retryable_delivery": False},
        "recording": {"status": "complete", "error": None},
        "process": {"dispatched": True, "exit_code": 3, "termination_reason": None,
                    "cleanup": {"complete": True, "errors": [], "unconfirmed_resources": []}},
        "persistence": {"required": False, "commit_state": "not_applicable", "operation_id": None, "receipt": None}}


@pytest.mark.asyncio
async def test_settled_search_unavailable_keeps_first_candidates_and_allows_backend_then_title_recovery():
    failure = settled_search_unavailable()
    frozen = copy.deepcopy(failure)
    initial = '"Environment Based Design" definition'
    exact = '"Environment-based formulation of design problem"'
    def respond(name, args):
        query = args["query"]
        if name == "web.search":
            if query == initial:
                return web([(TOPIC, "https://university.edu/first.pdf")], query)
            if query == exact:
                return web([("Environment-based formulation of design problem", "https://university.edu/foundation.pdf")], query)
            return failure
        return crossref([{"title": [TOPIC], "DOI": "10.1234/fallback", "URL": "https://doi.org/10.1234/fallback"}], query)
    port = SearchPort(respond)
    ctx = context(port)
    items, entries = await retrieve_candidates(ctx, [TOPIC + " definition", CAPTURED_RETRIEVAL],
        ["web.search", "scholar.crossref.search"], 5, topic=TOPIC, node_prefix="r1.")
    assert {item.url for item in items} == {"https://university.edu/first.pdf", "https://doi.org/10.1234/fallback",
                                         "https://university.edu/foundation.pdf"}
    failed = next(entry for entry in entries if entry["status"] == "failed")
    assert port.artifact(failed["artifact_ref"]) == frozen == failure
    assert failed["candidates"] == []
    assert port.artifact(failed["selection_ref"])["accepted_count"] == 0
    failed_index = next(i for i, (name, args) in enumerate(port.reads) if name == "web.search" and args["query"] not in {initial, exact})
    assert port.reads[failed_index + 1][0] == "scholar.crossref.search"
    assert port.reads[failed_index + 2] == ("web.search", {"query": exact, "max_results": 5})
    assert all(node["status"] == "succeeded" for node in ctx.nodes.values())
    assert max(entry["recovery_index"] for entry in entries) == 1


@pytest.mark.asyncio
async def test_repeated_settled_search_unavailability_is_retained_and_recovery_stays_bounded():
    outcome = settled_search_unavailable()
    port = SearchPort(lambda name, args: outcome)
    items, entries = await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL], ["web.search"], 5,
        topic=TOPIC, recovery_limit=4)
    assert items == [] and len(port.reads) == len(entries) == 5
    assert len({args["query"] for _, args in port.reads}) == 5
    assert [entry["recovery_index"] for entry in entries] == [0, 1, 2, 3, 4]
    assert all(port.artifact(entry["artifact_ref"]) == outcome for entry in entries)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"status": "unknown"}, {"status": "cancelled"}, {"status": "timed_out"}, {"status": "limit_exhausted"},
    {"error": {"code": "WORKER_FAILED"}}, {"error": {"commit_state": "unknown"}},
    {"error": {"retryable_delivery": True}}, {"recording": {"status": "incomplete"}},
    {"recording": {"error": {"code": "STORAGE_UNAVAILABLE"}}},
    {"process": {"dispatched": False}}, {"process": {"exit_code": 4}},
    {"process": {"termination_reason": "deadline"}},
    {"process": {"cleanup": {"complete": False}}},
    {"process": {"cleanup": {"errors": ["unsettled"]}}},
    {"process": {"cleanup": {"unconfirmed_resources": ["worker"]}}},
    {"persistence": {"required": True}}, {"persistence": {"commit_state": "unknown"}},
    {"persistence": {"operation_id": "pending-write"}}, {"persistence": {"receipt": {"operation_id": "write"}}},
    {"tool": {"name": "web.fetch"}}, {"result": {"unexpected": "payload"}},
])
async def test_search_unavailability_exception_never_masks_unknown_commit_or_unsettled_execution(change):
    outcome = settled_search_unavailable()
    def merge(target, changes):
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value
    merge(outcome, change)
    frozen = copy.deepcopy(outcome)
    port = SearchPort(lambda name, args: outcome)
    with pytest.raises(EngineError):
        await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL], ["web.search", "scholar.crossref.search"], 5, topic=TOPIC)
    assert len(port.reads) == 1 and outcome == frozen


@pytest.mark.asyncio
async def test_settled_search_failure_does_not_hide_unknown_selection_archive_commit():
    class ArchiveFaultPort(SearchPort):
        async def publish(self, content, media_type, filename):
            if filename.endswith("discovery.0.0.0.selection.json"):
                raise EngineError("COMMIT_UNKNOWN", "Controlled archive failure", commit_state="unknown")
            return await super().publish(content, media_type, filename)
    port = ArchiveFaultPort(lambda name, args: settled_search_unavailable())
    with pytest.raises(EngineError) as error:
        await retrieve_candidates(context(port), [CAPTURED_RETRIEVAL], ["web.search", "scholar.crossref.search"], 5, topic=TOPIC)
    assert error.value.commit_state == "unknown" and len(port.reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("recover", [True, False])
async def test_native_failed_search_retains_first_candidates_real_storage_worker_and_shared_budget(tmp_path, monkeypatch, recover):
    import sys
    from deepresearch.application.platform import ResearchPlatformPort
    from deepresearch.application.research_runs import LiveResearchRun
    from deepresearch.engine import Engine, EngineSettings, RunOptions
    from deepresearch.engine.contracts import RunRef, ToolRef
    from deepresearch.workflows import ResearchRunView
    initial = '"Environment Based Design" definition methodology'
    simpler = '"Environment Based Design"'
    payloads = {initial: web([(TOPIC, "https://university.edu/first.pdf")], initial)}
    if recover:
        payloads[simpler] = web([(TOPIC, "https://university.edu/recovered.pdf")], simpler)
    for payload in payloads.values():
        successful("web.search", payload)
    # Real Windows worker process, native worker error serialization, executor,
    # RecordedToolAction and Storage. Only backend discovery is controlled; no
    # network, model or modified registered tool definition is needed.
    script = """
import json, sys
import deepresearch.engine.toolset.search as search_module
from deepresearch.engine.toolset.common import ToolFault, encode
from deepresearch.engine.toolset.worker import run
payloads = """ + repr(payloads) + """
def backend(arguments, plan, timeout, revision):
    prepared = payloads.get(arguments['query'])
    observations = {'backend_attempts': [], 'disabled_backends': plan['disabled_backends']}
    fault = None if prepared is not None else ToolFault('SEARCH_UNAVAILABLE', 'Named backends returned no usable discovery; inspect backend_attempts')
    return prepared, observations, {'http_request_count': 0, 'http_response_count': 0, 'monetary_cost': None}, fault
search_module.search = backend
response, exit_code = run(json.loads(sys.stdin.buffer.read()), 'web.search', 2)
sys.stdout.buffer.write(encode(response))
sys.stdout.buffer.flush()
sys.exit(exit_code)
"""
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store"))).unwrap()
    session = ctx = None
    try:
        dispatched = []
        runner_run = engine.executor.runner.run
        async def controlled_worker(argv, payload, **kwargs):
            request = json.loads(payload)
            assert request["tool"] == {"name": "web.search", "revision": 2}
            dispatched.append(request)
            return await runner_run([sys.executable, "-c", script], payload, **kwargs)
        monkeypatch.setattr(engine.executor.runner, "run", controlled_worker)
        ref = ToolRef("web.search", 2)
        session = (await engine.open_workflow_session(tools=(ref,), invocation_rules=(),
            options=RunOptions(timeout_seconds=30))).unwrap()
        view = ResearchRunView(run_id=session.context.run_id, method_id="retrieval-test", method_revision=1,
            client_request_id="search-unavailable-test", accepted_at="2026-10-02T00:00:00Z", status="running", active=True)
        live = LiveResearchRun(session, view, "sha256:" + "0" * 64, (ref,))
        port = ResearchPlatformPort(engine, live, {})
        ctx = context(port)
        ctx.run_id = view.run_id
        items, entries = await retrieve_candidates(ctx,
            [TOPIC + " definition methodology", TOPIC + " process"], ["web.search"], 5,
            topic=TOPIC, node_prefix="r1.", recovery_limit=4)
        assert {item.url for item in items} == ({"https://university.edu/first.pdf", "https://university.edu/recovered.pdf"}
                                              if recover else {"https://university.edu/first.pdf"})
        assert len(entries) == len(dispatched) == (3 if recover else 5)
        assert session.context.ledger.used["tool_calls"] == len(dispatched)
        assert session.context.ledger.used.get("model_calls", 0) == 0
        assert len({request["invocation"]["action_id"] for request in dispatched}) == len(dispatched)
        assert len({request["invocation"]["attempt_id"] for request in dispatched}) == len(dispatched)
        assert len({request["arguments"]["query"] for request in dispatched}) == len(dispatched)
        assert all(request["invocation"]["run_id"] == session.context.run_id for request in dispatched)
        assert port.failure is None and all(node["status"] == "succeeded" for node in ctx.nodes.values())
        failed = next(entry for entry in entries if entry["status"] == "failed")
        raw = json.loads(await port.read_artifact(failed["artifact_ref"]))
        assert raw["error"]["code"] == "SEARCH_UNAVAILABLE"
        assert raw["error"]["observed_effect_state"] == "unknown"
        assert raw["error"]["commit_state"] == "not_applicable"
        assert raw["recording"] == {"status": "complete", "error": None}
        assert raw["process"]["exit_code"] == 3 and raw["process"]["termination_reason"] is None
        assert raw["process"]["dispatched"] and raw["process"]["cleanup"]["complete"]
        assert raw["persistence"] == {"required": False, "operation_id": None, "commit_state": "not_applicable", "receipt": None}
        assert json.loads(await port.read_artifact(failed["selection_ref"]))["candidates"] == []
        final = json.loads(await port.read_artifact(entries[0]["candidates_ref"]))
        assert {candidate["url"] for candidate in final["candidates"]} == {item.url for item in items}
        page = (await engine.query_run_events(RunRef(engine.storage.store_id, session.context.run_id), limit=100)).unwrap()
        outcomes = [row["event"] for row in page["events"] if row["event"]["kind"] == "tool.outcome"]
        assert len(outcomes) == len(dispatched)
        assert not engine.executor.runner._active
    finally:
        if ctx is not None:
            assert (await ctx.hooks.close()).complete
        if session is not None:
            assert (await session.close()).complete
        assert (await engine.close()).complete
