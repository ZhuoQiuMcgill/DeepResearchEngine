"""Keep topic screening, query preparation and fallback out of the Engine."""
import json

import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.workflows import MethodDefinition, MethodRegistry
from deepresearch.workflows.components.discovery import discover
from deepresearch.workflows.components.search_policy import SearchPolicy, infer_topic
from tests.workflows.test_components import Port, context


def test_definition_subject_and_expanded_parenthetical_name():
    assert infer_topic("What is Environment-Based Design (EBD), and what are its principles?") == "Environment-Based Design"
    assert infer_topic("什么是 EBD（Environment Based Design）？") == "Environment Based Design"
    assert infer_topic("What does retained alpha evidence show?") is None


def test_generated_queries_are_quoted_but_host_literal_queries_are_preserved():
    policy = SearchPolicy("Environment-Based Design")
    original = "what is Environment-Based Design EBD definition principles process"
    assert policy.prepare(original) == ('"Environment-Based Design" EBD definition principles process', "quoted_topic")
    assert policy.prepare(original, rewrite=False) == (original, "host_literal_query")
    assert policy.prepare('"Environment-Based Design" principles')[0] == '"Environment-Based Design" principles'
    assert policy.prepare('retrieve full text of "Environment-based formulation of design problem" to obtain a definition')[0] == '"Environment-based formulation of design problem"'
    assert policy.prepare('retrieve full text of Zeng\'s "Environment-based formulation of design problem" from 2004')[0] == '"Environment-based formulation of design problem" Zeng 2004'
    assert policy.prepare("read the discussion of requested-001", ["requested-001"])[0] is None


def test_topic_screen_rejects_acronym_collision_and_accepts_foundational_title():
    rows = [{"rank":1,"title":"Evidence-Based Dentistry (EBD)","snippet":"The EBD process"},
            {"rank":2,"titles":["ENVIRONMENT-BASED FORMULATION OF DESIGN PROBLEM"]},
            {"rank":3,"title":"Environment-Based Design", "snippet":"Methodology"}]
    accepted, decisions = SearchPolicy("Environment-Based Design").screen(rows)
    assert accepted == rows[1:]
    assert decisions[0]["missing_terms"] == ["environment","design"]


@pytest.mark.asyncio
async def test_irrelevant_success_uses_scholarly_fallback_and_archives_decisions():
    class DiscoveryPort(Port):
        async def run_tool(self, name, args):
            self.reads.append((name,args))
            rows = [{"rank":1,"title":"Evidence-Based Dentistry", "url":"https://example.org/dentistry"}] if name == "web.search" else [
                {"rank":1,"titles":["ENVIRONMENT-BASED FORMULATION OF DESIGN PROBLEM"],"doi_url":"https://doi.org/10.1/paper"}]
            return {"status":"succeeded","recording":{"status":"complete"},"result":{"results":rows}}
    port = DiscoveryPort()
    items, retained = await discover(context(port), ["Environment-Based Design EBD principles"],
        ["web.search","scholar.crossref.search"],5,policy=SearchPolicy("Environment-Based Design"))
    assert [name for name,_ in port.reads] == ["web.search","scholar.crossref.search"]
    assert len(items) == 1 and items[0].url == "https://doi.org/10.1/paper"
    selections = [json.loads(raw) for raw,_,filename in port.publications if filename.endswith(".selection.json")]
    assert selections[0]["accepted_count"] == 0 and selections[1]["accepted_count"] == 1
    assert all("selection_ref" in entry and "original_query" in entry for entry in retained)
    assert json.loads(port.publications[0][0])["result"]["results"][0]["url"] == "https://example.org/dentistry"


@pytest.mark.asyncio
async def test_saved_source_request_is_recorded_without_search_dispatch():
    port = Port()
    items, retained = await discover(context(port), ["read sections of requested-001"], ["web.search"],5,
        policy=SearchPolicy("Environment-Based Design"),source_ids=["requested-001"])
    assert items == retained == [] and not port.reads
    assert json.loads(port.publications[0][0])["reason"] == "references_retained_source"


def test_method_tool_pins_are_validated_and_included_in_digest():
    definition = MethodDefinition("search-pin",1,"Test",{}, {}, tool_revisions={"web.search":2})
    value = definition.to_dict()
    assert value["tool_revisions"] == {"web.search":2}
    assert value["sha256"] != MethodDefinition("search-pin",1,"Test",{}, {}).to_dict()["sha256"]
    for invalid in ({"web.search":True},{"web.search":0},{"":1}):
        with pytest.raises(EngineError,match="positive integer"):
            MethodRegistry().register(MethodDefinition("invalid",1,"Test",{}, {},tool_revisions=invalid),object())
