"""Selector policy through the real Workflow/Runtime/SQLite harness.

Only provider HTTP and discovery/fetch payloads are controlled. Selection,
admission, saved reads, hooks and artifact provenance use production code.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from deepresearch.bootstrap import create_method_registry
from deepresearch.engine.contracts import EngineError, canonical_json
from deepresearch.extensions import ExtensionSpec, HookDecision
from deepresearch.methods.baseline.selection_contracts import SelectionChoice, SelectionDecision
from deepresearch.methods.baseline.stages.selection import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATES,
    candidate_cards,
    validate_selection,
)
from deepresearch.workflows import FetchItem, ResearchRunRequest
from deepresearch.workflows.context import WorkflowContext
from tests.methods.test_parallel_baseline import (
    ALPHA,
    BETA,
    _analysis,
    _configured,
    _events,
    _json,
    _lines,
    _request,
    _settle,
)


EBD_QUESTION = "What is EBD (Environment Based Design)?"
GAMMA = "https://example.org/gamma"
DELTA = "https://example.org/delta"


def _selection_request(**parameters):
    return _request(**parameters).model_copy(update={"method_revision": 7})


def _decision(value, selected=None, *, defer=False):
    cards = value["candidates"]
    if selected is None:
        selected = [card["candidate_id"] for card in cards[:value["budget"]["batch_fetch_limit"]]]
    rest = [card["candidate_id"] for card in cards if card["candidate_id"] not in selected]
    choice = lambda identity: {"candidate_id": identity, "reason": "Relevant recorded discovery metadata."}
    return {"schema_version": 1, "selections": [choice(identity) for identity in selected],
            "deferred": [choice(identity) for identity in rest] if defer else [],
            "rejected": [] if defer else [choice(identity) for identity in rest]}


def _inventory(count, metadata=None):
    items = [FetchItem(item_id=f"original-{index}", url=f"https://example.org/paper-{index}",
                       discovery_ref="discovery-1", reason="Discovered candidate") for index in range(count)]
    rows = [{"url": item.url, "title": f"Paper {index}", "rank": index + 1,
             "location": "web.url", "metadata": deepcopy(metadata or {})}
            for index, item in enumerate(items)]
    discoveries = [{"tool": "web.search", "query": "research question", "candidates": rows,
                    "artifact_ref": {"artifact_id": "retained-discovery"}}]
    return items, discoveries, {item.url: f"work-{index}" for index, item in enumerate(items)}


def test_revision_seven_keeps_request_and_parameter_contracts_and_adds_only_selector():
    registry = create_method_registry()
    old, old_method = registry.resolve("baseline", 6)
    new, new_method = registry.resolve("baseline", 7)
    assert new.input_schema == old.input_schema

    def constraints(value):
        if isinstance(value, dict):
            return {key: constraints(item) for key, item in value.items() if key != "description"}
        if isinstance(value, list):
            return [constraints(item) for item in value]
        return value

    assert constraints(new.parameters_schema) == constraints(old.parameters_schema)
    assert new.tool_revisions == old.tool_revisions
    assert tuple(role for role in new.agent_roles if role[0] != "baseline.selector") == old.agent_roles
    assert [role for role in new.agent_roles if role[0] == "baseline.selector"] == [("baseline.selector", 1)]
    assert new_method.agent_selection is True and old_method.agent_selection is False
    request = ResearchRunRequest.model_validate(_selection_request().to_dict())
    assert request.schema_version == 1 and request.method_revision == 7
    registry.validate(new, request.input, request.parameters)
    for invalid in ({"max_sources": 21}, {"max_rounds": 3}, {"selector_urls": [ALPHA]}):
        with pytest.raises(EngineError) as raised:
            registry.validate(new, request.input, {**request.parameters, **invalid})
        assert raised.value.code == "INVALID_DATA"


def test_tool_comparison_revision_keeps_research_and_agent_controls_fixed():
    registry = create_method_registry()
    old, _ = registry.resolve("baseline", 9)
    new, _ = registry.resolve("baseline", 10)
    assert new.input_schema == old.input_schema
    assert new.parameters_schema == old.parameters_schema
    assert new.agent_roles == old.agent_roles
    assert new.tool_revisions == {**old.tool_revisions, "web.search": 4, "web.fetch": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [6, 7, 8, 9, 10])
async def test_foundation_metadata_reaches_selector_and_order_controls_actual_fetch(tmp_path, monkeypatch, revision):
    irrelevant = "https://example.org/cooking"
    bibliography = {"abstract": "A mathematical foundation of Environment Based Design.",
                    "authors": [{"given": "Ada", "family": "Researcher"}],
                    "container_titles": ["Design Research"], "citation_count": 17}
    rows = [
        {"rank": 1, "url": irrelevant, "title": "Cooking recipes", "snippet": "Kitchen techniques."},
        {"rank": 2, "url": ALPHA, "title": "Environment Based Design process", "snippet": "Definition."},
        {"rank": 3, "url": BETA, "title": "Axiomatic theory of design modeling",
         "snippet": "A foundational mathematical account.", "bibliography": bibliography,
         "year": 2002, "publisher": "Research Press", "doi": "10.5555/foundation"},
    ]

    def respond(role, value, ordinal):
        if role == "baseline.selector":
            by_url = {card["url"]: card["candidate_id"] for card in value["candidates"]}
            return _decision(value, [by_url[BETA], by_url[ALPHA]])
        return None

    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("DIRECT"), BETA: _lines("FOUNDATION")},
                           respond=respond, discover=lambda tool, query: deepcopy(rows)) as h:
        request = _selection_request(source_urls=[], queries=["environment based design"],
            max_sources=4, max_rounds=1, min_substantive_sources=1).model_copy(
                update={"method_revision": revision, "input": {"question": EBD_QUESTION}})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert h.fetched == ([BETA, ALPHA] if revision >= 7 else [ALPHA])
        assert irrelevant not in h.fetched
        if revision == 6:
            assert not h.role_calls("selector")
            return
        assert len(h.role_calls("selector")) == 1
        value = h.role_calls("selector")[0]["input"]
        assert value["question"] == EBD_QUESTION
        assert {card["url"] for card in value["candidates"]} == {ALPHA, BETA, irrelevant}
        foundation = next(card for card in value["candidates"] if card["url"] == BETA)
        assert foundation["title"] == rows[2]["title"] and foundation["snippet"] == rows[2]["snippet"]
        assert foundation["bibliography"] == {**bibliography, "authors": [{"name": "Ada Researcher"}],
            "year": 2002, "publisher": "Research Press", "doi": "10.5555/foundation"}
        assert foundation["discovery"]["rank"] == 3
        assert foundation["discovery"]["tool"] == "web.search"
        assert foundation["discovery"]["query"] == "environment based design"
        assert foundation["discovery"]["location"] == "web.url"
        assert foundation["metadata_notes"] == []
        raw = await _json(h.service, view.run_id, foundation["discovery"]["raw_ref"])
        assert raw["result"]["results"] == rows
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        validated = await _json(h.service, view.run_id, result["selections"][0]["validation_ref"])
        decision = validated["decision"]
        assert all(set(choice) == {"candidate_id", "reason"}
                   for group in ("selections", "deferred", "rejected") for choice in decision[group])
        expected_roles = {
            ("baseline.planner", 3), ("baseline.selector", 1), ("baseline.distiller", 1),
            ("baseline.analyst", 3), ("baseline.writer", 5), ("baseline.reviewer", 4)}
        if revision >= 8:
            expected_roles = {("baseline.planner", 4), ("baseline.selector", 2),
                ("baseline.distiller", 2), ("baseline.analyst", 4),
                ("baseline.writer", 6), ("baseline.reviewer", 5)}
        if revision >= 9:
            expected_roles = {("baseline.planner", 4), ("baseline.selector", 3),
                ("baseline.distiller", 3), ("baseline.analyst", 5),
                ("baseline.writer", 6), ("baseline.reviewer", 5)}
        assert {(call["role"], call["revision"]) for call in h.calls} == expected_roles


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["unknown", "duplicate", "omitted", "over_budget", "url"])
async def test_invalid_selector_output_fails_before_fetch_without_heuristic_fallback(tmp_path, monkeypatch, fault):
    def respond(role, value, ordinal):
        if role != "baseline.selector":
            return None
        output = _decision(value)
        if fault == "unknown":
            output["selections"][0]["candidate_id"] = "invented-id"
        elif fault == "duplicate":
            output["rejected"].append(deepcopy(output["selections"][0]))
        elif fault == "omitted":
            output["rejected"].pop()
        elif fault == "over_budget":
            output["selections"].append(output["rejected"].pop())
        else:
            output["selections"][0]["url"] = "https://example.org/model-chosen-url"
        return output

    documents = {url: _lines(url) for url in (ALPHA, BETA, GAMMA)}
    async with _configured(tmp_path, monkeypatch, documents, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_selection_request(
            source_urls=list(documents), max_sources=2, max_rounds=1))).run_id)
        assert view.status == "failed", view.error
        expected = {"duplicate": "INVALID_ROLE_OUTPUT", "url": "agent.validation"}.get(fault, "INVALID_SELECTION")
        assert view.error["code"] == expected
        assert h.fetched == [] and h.reads == []
        assert [call["role"] for call in h.calls] == ["baseline.planner", "baseline.selector"]
        assert view.report_ref is None and view.result_manifest_ref is None


@pytest.mark.asyncio
async def test_rejecting_every_candidate_does_not_fetch_requested_urls_as_a_fallback(tmp_path, monkeypatch):
    def respond(role, value, ordinal):
        return _decision(value, []) if role == "baseline.selector" else None

    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("UNSELECTED")}, respond=respond) as h:
        view = await _settle(h.service, (await h.service.start_run(_selection_request())).run_id)
        assert view.status == "failed" and view.error["code"] == "NO_EVIDENCE"
        assert len(h.role_calls("selector")) == 1
        assert not h.fetched and not h.role_calls("distiller") and view.report_ref is None


@pytest.mark.asyncio
async def test_fallback_and_later_rounds_receive_failures_distillation_and_gaps(tmp_path, monkeypatch):
    documents = {ALPHA: None, BETA: _lines("FALLBACK"), GAMMA: _lines("LATER"), DELTA: _lines("RESERVE")}

    def discover(tool, query):
        if query == "required corroboration":
            return [{"url": url, "rank": index + 1, "title": f"Rediscovered work {index}"}
                    for index, url in enumerate((GAMMA, DELTA))]
        return []

    def respond(role, value, ordinal):
        if role == "baseline.selector":
            return _decision(value, defer=True)
        if role == "baseline.analyst" and ordinal == 1:
            return _analysis(value, sufficient=False, queries=["required corroboration"])
        return None

    async with _configured(tmp_path, monkeypatch, documents, respond=respond, discover=discover) as h:
        view = await _settle(h.service, (await h.service.start_run(_selection_request(
            source_urls=list(documents), max_sources=4, max_rounds=2))).run_id)
        assert view.status == "succeeded", view.error
        assert h.fetched == list(documents)
        values = [call["input"] for call in h.role_calls("selector")]
        assert len(values) == 4
        assert [value["budget"]["round"] for value in values] == [1, 1, 2, 2]
        assert [value["budget"]["remaining_fetches"] for value in values] == [4, 3, 2, 1]
        assert [value["budget"]["batch_fetch_limit"] for value in values] == [1, 1, 1, 1]
        assert values[0]["history"] == []
        failure = values[1]["history"][0]
        assert failure["url"] == ALPHA and failure["status"] == "failed"
        assert failure["error_code"] == "FETCH_HTTP_ERROR"
        assert failure["content_kinds"] == failure["summaries"] == []
        assert failure["complete_read"] is False
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        records = (await _json(h.service, view.run_id, result["distillations_ref"]))["records"]
        for index, value in enumerate(values[2:], 2):
            history = {item["url"]: item for item in value["history"]}
            assert list(history) == list(documents)[:index]
            assert history[ALPHA] == failure
            assert "A required corroborating source remains unavailable." in value["gaps"]
            for url in list(documents)[1:index]:
                prior = history[url]
                digest = next(record for record in records if record["source_id"] == prior["source_id"])
                assert prior["status"] == "succeeded" and prior["complete_read"] is True
                assert prior["content_kinds"] == ["substantive"]
                assert prior["summaries"] == [digest["distillation"]["summary"]]
            assert not set(history) & {card["url"] for card in value["candidates"]}
            # Rediscovery enriches a deferred user URL; it must not erase its
            # user-requested origin when fresh results and backlog are deduped.
            assert all(card["discovery"]["source"] == "requested" for card in value["candidates"])
            assert all(card["title"].startswith("Rediscovered work") for card in value["candidates"])
        assert len(result["rounds"]) == 2
        assert result["selections"] == [selection for row in result["rounds"] for selection in row["selections"]]
        selector_nodes = [node.node_id for node in view.nodes if node.detail.get("role_id") == "baseline.selector"
                          and node.kind == "agent"]
        assert selector_nodes == ["r1.select.sources", "r1.fallback.select.sources",
                                  "r2.select.sources", "r2.recovery.select.sources"]


@pytest.mark.asyncio
async def test_twenty_fetch_cap_is_global_across_selection_batches_including_failures(tmp_path, monkeypatch):
    urls = [f"https://example.org/bounded-{index:02d}" for index in range(25)]
    documents = {url: None if index == 0 else _lines(f"WORK_{index}") for index, url in enumerate(urls)}

    def respond(role, value, ordinal):
        if role == "baseline.selector":
            return _decision(value, defer=True)
        if role == "baseline.analyst":
            return _analysis(value, sufficient=False, queries=["remaining sources"] if ordinal == 1 else [])
        return None

    rows = [{"url": url, "title": f"Additional independent work {index}", "rank": index + 1}
            for index, url in enumerate(urls[20:])]
    async with _configured(tmp_path, monkeypatch, documents, respond=respond,
                           discover=lambda tool, query: deepcopy(rows)) as h:
        view = await _settle(h.service, (await h.service.start_run(_selection_request(
            source_urls=urls[:20], max_sources=20, max_rounds=2))).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.fetched) == len(set(h.fetched)) == view.quality.attempted_sources == 20
        assert h.fetched == urls[:20]
        assert sum(source.status == "failed" for source in view.sources.items) == 1
        values = [call["input"] for call in h.role_calls("selector")]
        assert [value["budget"]["remaining_fetches"] for value in values] == [20, 15, 10, 5]
        assert [value["budget"]["batch_fetch_limit"] for value in values] == [5, 5, 5, 5]
        assert [value["budget"]["round"] for value in values] == [1, 1, 2, 2]
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        manifests = [await _json(h.service, view.run_id, row["fetch_manifest_ref"]) for row in result["rounds"]]
        assert [len(manifest["items"]) for manifest in manifests] == [10, 10]
        assert [item["url"] for manifest in manifests for item in manifest["items"]] == h.fetched
        assert len(h.role_calls("distiller")) == 19


@pytest.mark.asyncio
@pytest.mark.parametrize("expand", [False, True], ids=["subset-reorder", "reject-expansion"])
async def test_hooks_are_bounded_by_selector_and_saved_provenance_links_actual_fetch(tmp_path, monkeypatch, expand):
    outputs, hook_inputs, observed = [], [], []

    def respond(role, value, ordinal):
        if role == "baseline.selector":
            by_url = {card["url"]: card["candidate_id"] for card in value["candidates"]}
            output = _decision(value, [by_url[GAMMA], by_url[BETA], by_url[ALPHA]])
            outputs.append(output)
            return output
        return None

    async def select(event, candidate_ids):
        hook_inputs.append(list(candidate_ids))
        if expand:
            return HookDecision(keep_ids=(*candidate_ids, outputs[0]["rejected"][0]["candidate_id"]))
        return HookDecision(keep_ids=(candidate_ids[2], candidate_ids[0]))

    async def observe(event):
        observed.append((event.node_id, event.point))

    documents = {url: _lines(url) for url in (ALPHA, BETA, GAMMA, DELTA)}
    async with _configured(tmp_path, monkeypatch, documents, respond=respond) as h:
        h.service.extension_registry.register(ExtensionSpec(extension_id="selection.subset", revision="1",
            points=("discovery.select",), mode="control"), select)
        h.service.extension_registry.register(ExtensionSpec(extension_id="selection.observe", revision="1",
            points=("node.before", "node.after", "node.failed"), mode="observe"), observe)
        view = await _settle(h.service, (await h.service.start_run(_selection_request(
            source_urls=list(documents), max_sources=6, max_rounds=1))).run_id)
        assert hook_inputs == [[choice["candidate_id"] for choice in outputs[0]["selections"]]]
        if expand:
            assert view.status == "failed" and view.error["code"] == "extension.invalid_decision"
            assert not h.fetched and view.report_ref is None
            return
        assert view.status == "succeeded", view.error
        assert h.fetched == [ALPHA, GAMMA]
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        record, = result["selections"]
        assert "decision" not in record and "bindings" not in record
        assert record["hook_selected_ids"] == [hook_inputs[0][2], hook_inputs[0][0]]
        assert await _json(h.service, view.run_id, record["input_ref"]) == h.role_calls("selector")[0]["input"]
        assert await _json(h.service, view.run_id, record["output_ref"]) == outputs[0]
        validated = await _json(h.service, view.run_id, record["validation_ref"])
        assert validated["decision"] == outputs[0]
        bindings = validated["bindings"]
        assert set(bindings) == {card["candidate_id"] for card in h.role_calls("selector")[0]["input"]["candidates"]}
        inventory = await _json(h.service, view.run_id, record["inventory_ref"])
        assert [item["url"] for item in inventory["items"]] == list(documents)
        assert inventory["coverage"] == record["coverage"] and inventory["omitted_ids"] == []
        manifest = await _json(h.service, view.run_id, record["fetch_manifest_ref"])
        assert [item["url"] for item in manifest["items"]] == h.fetched
        assert [bindings[identity]["url"] for identity in record["hook_selected_ids"]] == h.fetched
        assert [source.item_id for source in view.sources.items] == [item["item_id"] for item in manifest["items"]]
        assert all(source.snapshot_ref is not None for source in view.sources.items)
        agent_node = next(node for node in view.nodes if node.node_id == "r1.select.sources")
        binding_node = next(node for node in view.nodes if node.node_id == "r1.select.bindings")
        assert agent_node.detail["input_ref"] == binding_node.detail["input_ref"] == record["input_ref"]
        assert binding_node.detail["output_ref"] == record["output_ref"]
        assert binding_node.detail["validation_ref"] == record["validation_ref"]
        assert (agent_node.node_id, "node.before") in observed and (agent_node.node_id, "node.after") in observed
        events = await _events(h.service, view.run_id)
        hook_event, = [event for event in events if event["kind"] == "workflow.hook.decision"]
        assert hook_event["payload"]["candidate_ids"] == hook_inputs[0]
        assert hook_event["payload"]["keep_ids"] == record["hook_selected_ids"]


@pytest.mark.asyncio
async def test_large_selection_audits_stay_in_artifacts_and_checkpoints_remain_bounded(tmp_path, monkeypatch):
    # Four decisions over ~50 candidates fit each role output, but repeating
    # long reasons and URL bindings inline exceeds the 256 KiB checkpoint cap.
    urls = [f"https://example.org/checkpoint-{index:02d}?fixture=" + "x" * 500 for index in range(52)]
    queries = [f"inventory-{index}" for index in range(4)]
    checkpoints = []
    native_checkpoint = WorkflowContext.checkpoint

    async def checkpoint(context, payload):
        checkpoints.append(deepcopy(payload))
        return await native_checkpoint(context, payload)

    monkeypatch.setattr(WorkflowContext, "checkpoint", checkpoint)

    def discover(tool, query):
        start = 12 + (queries.index(query) if query in queries else 0) * 10
        return [{"url": url, "rank": index + 1, "title": f"Independent work {start + index}"}
                for index, url in enumerate(urls[start:start + 10])]

    def respond(role, value, ordinal):
        if role == "baseline.selector":
            output = _decision(value, defer=True)
            for group in ("selections", "deferred", "rejected"):
                for choice in output[group]:
                    choice["reason"] = "Recorded relevance: " + "r" * 980
            assert len(canonical_json(output)) < 65536
            return output
        if role == "baseline.analyst" and ordinal == 1:
            return _analysis(value, sufficient=False, queries=["checkpoint gap"])
        return None

    documents = {url: _lines(f"CHECKPOINT_{index}") for index, url in enumerate(urls[:4])}
    async with _configured(tmp_path, monkeypatch, documents, respond=respond, discover=discover) as h:
        view = await _settle(h.service, (await h.service.start_run(_selection_request(
            source_urls=urls[:12], queries=queries, max_queries=4, max_results=10,
            max_sources=4, max_rounds=2))).run_id)
        assert view.status == "succeeded", view.error
        assert h.fetched == urls[:4]
        assert [len(call["input"]["candidates"]) for call in h.role_calls("selector")] == [52, 51, 50, 49]
        research = [payload for payload in checkpoints if payload["kind"] == "baseline-research/7"]
        assert len(research) == 2
        assert all(len(canonical_json(payload)) <= 262144 for payload in checkpoints)
        result = await _json(h.service, view.run_id, view.result_manifest_ref.to_dict())
        summary_records = [record for row in research[-1]["rounds"] for record in row["selections"]]
        assert summary_records == result["selections"]
        expanded = deepcopy(research[-1])
        for row in expanded["rounds"]:
            for record in row["selections"]:
                assert "decision" not in record and "bindings" not in record
                audit = await _json(h.service, view.run_id, record["validation_ref"])
                assert audit["input_ref"] == record["input_ref"] and audit["output_ref"] == record["output_ref"]
                assert len(audit["bindings"]) == record["coverage"]["delivered_candidates"]
                assert await _json(h.service, view.run_id, record["output_ref"]) == audit["decision"]
                record.update(decision=audit["decision"], bindings=audit["bindings"])
        assert len(canonical_json(expanded)) > 262144


def test_candidate_count_cap_preserves_order_bindings_and_reports_every_omission():
    items, discoveries, work_ids = _inventory(131)
    before = deepcopy((items, discoveries, work_ids))
    cards, bindings, omitted, coverage = candidate_cards(items, discoveries, work_ids, "r2.")
    assert MAX_CANDIDATES == 128 and len(cards) == len(bindings) == 128
    assert [card["url"] for card in cards] == [item.url for item in items[:128]]
    assert omitted == items[128:]
    assert coverage == {"total_candidates": 131, "delivered_candidates": 128,
                        "omitted_candidates": 3, "truncated_candidates": 0}
    for card in cards:
        bound = bindings[card["candidate_id"]]
        assert bound.item_id == card["candidate_id"] and bound.url == card["url"]
        assert card["work_id"] == work_ids[bound.url]
        assert card["discovery"]["ref"] == bound.discovery_ref == "discovery-1"
    assert (items, discoveries, work_ids) == before


def test_candidate_byte_cap_reports_omitted_candidates_without_silently_trimming_metadata(monkeypatch):
    metadata = {"snippet": "é" * 1000, "bibliography": {"abstract": "界" * 1300,
        "authors": [{"name": "A" * 250} for _ in range(8)], "container_titles": ["J" * 500] * 3}}
    items, discoveries, work_ids = _inventory(128, metadata)
    cards, bindings, omitted, coverage = candidate_cards(items, discoveries, work_ids, "r1.")
    assert MAX_CANDIDATE_BYTES == 262144
    assert 0 < len(cards) < 128 and len(canonical_json(cards)) <= MAX_CANDIDATE_BYTES
    assert coverage == {"total_candidates": 128, "delivered_candidates": len(cards),
                        "omitted_candidates": len(omitted), "truncated_candidates": 0}
    assert [card["url"] for card in cards] + [item.url for item in omitted] == [item.url for item in items]
    assert len(bindings) == len(cards)
    assert all(card["bibliography"] == metadata["bibliography"] and card["snippet"] == metadata["snippet"]
               and card["metadata_notes"] == [] for card in cards)
    assert discoveries[0]["candidates"][-1]["metadata"] == metadata
    # Account for the brackets and separating comma, including an exact fit.
    small_items, small_discoveries, small_works = _inventory(2)
    both, _, _, _ = candidate_cards(small_items, small_discoveries, small_works, "r1.")
    exact_bytes = len(canonical_json(both))
    for limit, expected in ((exact_bytes, 2), (exact_bytes - 1, 1)):
        monkeypatch.setattr("deepresearch.methods.baseline.stages.selection.MAX_CANDIDATE_BYTES", limit)
        bounded, _, omitted, coverage = candidate_cards(small_items, small_discoveries, small_works, "r1.")
        assert len(bounded) == coverage["delivered_candidates"] == expected
        assert len(canonical_json(bounded)) <= limit
        assert len(omitted) == coverage["omitted_candidates"] == 2 - expected


def test_candidate_field_truncation_is_utf8_bounded_explicit_and_does_not_mutate_discovery():
    metadata = {"snippet": "界" * 1000, "publisher": "é" * 600,
        "bibliography": {"abstract": "界" * 2000, "authors": [{"name": "é" * 200}] * 10,
                         "container_titles": ["界" * 200] * 4}}
    items, discoveries, work_ids = _inventory(1, metadata)
    discoveries[0]["candidates"][0]["title"] = "é" * 1100
    before = deepcopy(discoveries)
    cards, _, omitted, coverage = candidate_cards(items, discoveries, work_ids, "r1.")
    card, = cards
    assert omitted == [] and coverage["truncated_candidates"] == 1
    for original, actual, limit in (
        (before[0]["candidates"][0]["title"], card["title"], 2048),
        (metadata["snippet"], card["snippet"], 2048),
        (metadata["bibliography"]["abstract"], card["bibliography"]["abstract"], 4096),
        (metadata["publisher"], card["bibliography"]["publisher"], 1024),
        (metadata["bibliography"]["authors"][0]["name"], card["bibliography"]["authors"][0]["name"], 256),
        (metadata["bibliography"]["container_titles"][0], card["bibliography"]["container_titles"][0], 512),
    ):
        assert actual == original.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        assert len(actual.encode("utf-8")) <= limit and "�" not in actual
    assert len(card["bibliography"]["authors"]) == 8 and len(card["bibliography"]["container_titles"]) == 3
    assert set(card["metadata_notes"]) == {"truncated:title", "truncated:snippet", "truncated:abstract",
        "truncated:publisher", "truncated:authors", "truncated:author_name",
        "truncated:container_titles", "truncated:container_title"}
    assert discoveries == before


@pytest.mark.parametrize("fault", [None, "unknown", "duplicate", "omitted", "batch", "remaining"])
def test_host_validation_requires_exhaustive_unique_ids_and_both_fetch_allowances(fault):
    choices = [SelectionChoice(candidate_id=identity, reason="Recorded metadata") for identity in ("c", "a", "b")]
    # Construct bypasses the role contract so host validation itself must catch
    # duplicates, as well as identities/budgets unavailable to the role schema.
    value = SelectionDecision.model_construct(schema_version=1, selections=choices[:2],
        deferred=choices[2:], rejected=[])
    budget = {"remaining_fetches": 2, "batch_fetch_limit": 2}
    if fault == "unknown":
        value.selections[0] = SelectionChoice(candidate_id="not-delivered", reason="Invalid identity")
    elif fault == "duplicate":
        value.rejected.append(choices[0])
    elif fault == "omitted":
        value.deferred.clear()
    elif fault == "batch":
        budget["batch_fetch_limit"] = 1
    elif fault == "remaining":
        budget["remaining_fetches"] = 1
    if fault is None:
        validate_selection(value, ["a", "b", "c"], budget)
        assert [choice.candidate_id for choice in value.selections] == ["c", "a"]
    else:
        with pytest.raises(EngineError) as raised:
            validate_selection(value, ["a", "b", "c"], budget)
        assert raised.value.code == "INVALID_SELECTION"
