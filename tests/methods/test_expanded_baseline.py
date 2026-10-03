"""Expanded quotas across the actual Workflow, Runtime and saved-read worker."""
import asyncio
import base64
import json

import pytest

from deepresearch.agent_catalog import AgentCatalog, CatalogError
from deepresearch.bootstrap import create_method_registry
from deepresearch.engine.contracts import EngineError
from deepresearch.engine.providers import ModelRequest, ProviderConfig, ProviderFactory
from deepresearch.workflows import ResearchRunRequest
from tests.agent_catalog.test_baseline_roles import role_input
from tests.methods.test_baseline import ACCEPT, PLAN, REPORT, analysis, close, configured, request, settle


@pytest.mark.asyncio
async def test_twenty_attempted_urls_are_shared_across_two_rounds_and_include_failure(tmp_path, monkeypatch):
    outputs = [PLAN, analysis(sufficient=False), analysis(sufficient=False), REPORT, ACCEPT]
    engine, service, _, calls, fetched, searches = await configured(
        tmp_path, monkeypatch, outputs, failed_url="https://example.org/source-3")
    execute = engine.executor.execute

    async def expanded_search(definition, arguments, context, plan):
        result = await execute(definition, arguments, context, plan)
        if definition.name == "web.search":
            start, stop = (1, 10) if arguments["query"] == "literal alpha" else (10, 25)
            result.result = {"results": [{"rank": index - start + 1,
                "url": f"https://example.org/source-{index}"} for index in range(start, stop)]}
        return result

    engine.executor.execute = expanded_search
    expanded = request(max_sources=20, max_rounds=2, context_tokens=32768,
                       max_context_bytes=131072, max_results=10).model_copy(
                           update={"method_revision": 3, "timeout_seconds": 120.0})
    try:
        run_id = (await service.start_run(expanded)).run_id
        async def wait_for_run():
            while True:
                current = await service.get_run(run_id)
                if not current.active:
                    return current
                await asyncio.sleep(.05)
        view = await asyncio.wait_for(wait_for_run(), timeout=120)
        assert view.status == "succeeded", view.error
        assert len(fetched) == len(set(fetched)) == 20
        assert sum(source.status == "failed" for source in view.sources.items) == 1
        assert len(view.context_plan.selections) == 19
        assert searches == ["literal alpha", "alpha follow up"] and len(calls) == 5
        chunks, offset = [], 0
        while True:
            part = await service.read_artifact(view.run_id, view.result_manifest_ref.artifact_id, start=offset)
            chunks.append(base64.b64decode(part["data"]))
            if part["eof"]:
                break
            assert part["next_offset"] > offset
            offset = part["next_offset"]
        result = json.loads(b"".join(chunks))
        assert result["method_revision"] == 3 and len(result["rounds"]) == 2
        assert result["stop_reason"] == "source_limit"
    finally:
        await close(engine, service)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,revision", [
    ("baseline.planner", 2), ("baseline.analyst", 2),
    ("baseline.writer", 3), ("baseline.reviewer", 2),
    ("baseline.writer", 4), ("baseline.reviewer", 3),
])
async def test_expanded_roles_allow_large_inputs_and_apply_256k_token_estimate(role, revision):
    spec = AgentCatalog().load(role, revision)
    value = role_input(role)
    if "evidence" in value:
        value["evidence"] = "retained evidence\n" * 17000
    if "available_source_ids" in value:
        value["available_source_ids"] = [f"source-{index}" for index in range(20)]
    rendered = spec.render_task(value)
    definition = spec.compile_definition(profile_ref="controlled", model_ref="deepseek-flash")
    assert definition.limits["max_context_tokens"] == 262144
    session = (await ProviderFactory.open(ProviderConfig(
        "deepseek", "deepseek-flash", "https://provider.invalid", "controlled-test"))).unwrap()
    try:
        prepared = session.prepare(ModelRequest(spec.instructions, rendered, (), "large-input", "test-pin",
            max_context_tokens=definition.limits["max_context_tokens"],
            max_request_bytes=definition.limits["max_model_request_bytes"]))
        measurement = prepared.audit["context_measurement"]
        assert measurement["estimated_tokens"] == (measurement["text_bytes"] + 3) // 4
        assert measurement["estimator"] == "utf8-byte-size/4" and not measurement["verified_tokenizer"]
        if role != "baseline.planner":
            assert measurement["text_bytes"] > 262144
        with pytest.raises(ValueError, match="advisory"):
            session.prepare(ModelRequest(spec.instructions, "x" * 1048576, (), "oversize", "test-pin",
                max_context_tokens=262144, max_request_bytes=2097152))
    finally:
        await session.aclose()


def test_expanded_parameter_boundaries_and_historical_resources():
    registry = create_method_registry()
    request_value = ResearchRunRequest(client_request_id="expanded-limits", method_id="baseline",
        method_revision=3, input={"question": "Budget test"}, parameters={"max_sources": 20,
        "max_rounds": 2, "context_tokens": 131072, "max_context_bytes": 524288})
    definition, _ = registry.resolve("baseline", 3)
    registry.validate(definition, request_value.input, request_value.parameters)
    for invalid in ({"max_sources": 21}, {"max_rounds": 3}):
        with pytest.raises(EngineError):
            registry.validate(definition, request_value.input, {**request_value.parameters, **invalid})
    catalog = AgentCatalog()
    for role, old, new in (("planner", 1, 2), ("analyst", 1, 2), ("writer", 2, 3), ("reviewer", 1, 2)):
        old_spec = catalog.load("baseline." + role, old)
        new_spec = catalog.load("baseline." + role, new)
        assert old_spec.ref != new_spec.ref
        assert old_spec.compile_definition(profile_ref="controlled", model_ref="deepseek-flash").limits["max_context_tokens"] == 131072
    value = role_input("baseline.analyst")
    value["available_source_ids"] = [f"source-{index}" for index in range(21)]
    with pytest.raises(CatalogError):
        catalog.load("baseline.analyst", 2).render_task(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("method_revision,tool_revision",[(2,1),(3,2),(4,2)])
async def test_workflow_records_exact_search_tool_pin(tmp_path,monkeypatch,method_revision,tool_revision):
    engine,service,_,calls,_,_ = await configured(tmp_path,monkeypatch,[PLAN,analysis(),REPORT,ACCEPT])
    try:
        admitted = await service.start_run(request().model_copy(update={"method_revision":method_revision}))
        view = await settle(service,admitted.run_id)
        assert view.status == "succeeded", view.error
        events,position = [],0
        while True:
            page = await service.events(view.run_id,position)
            events.extend(page["events"])
            position = page["next_after_seq"]
            if not page["has_more"]:
                break
        intents = [row["event"]["payload"] for row in events if row["event"]["kind"] == "tool.intent"]
        searches = [intent["tool"] for intent in intents if intent["tool"]["name"] == "web.search"]
        assert searches == [{"name":"web.search","revision":tool_revision}]
        assert len(calls) == 4
    finally:
        await close(engine,service)
