"""Compiled specs use real Engine/Runtime/Storage with controlled provider IO."""
import json

import httpx
import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.engine.connections import ArtifactReadRequest, Engine, EngineSettings, RunAccessRequest, RunOptions
from deepresearch.engine.contracts import Err, RunRef, ToolRef
from deepresearch.engine.providers import ProviderConfig, ProviderFactory


@pytest.mark.asyncio
async def test_writer_compilation_runs_and_records_through_existing_engine(tmp_path, monkeypatch):
    requests = []
    report = "# Answer\n\nThe selected evidence supports the finding. [source-1]\n"

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "catalog-response", "model": "deepseek-flash", "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": report}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})

    native_open = ProviderFactory.open

    async def controlled_open(config, context=None):
        return await native_open(config, context, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    settings = EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", profiles={
        "catalog-test": ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-secret",
                                       profile_name="catalog-test")})
    engine = (await Engine.open(settings)).unwrap()
    try:
        spec = AgentCatalog().load("baseline.writer", 1)
        definition = spec.compile_definition(profile_ref="catalog-test", model_ref="deepseek-flash", tools=(),
                                             limits={"max_model_calls": 1, "max_run_seconds": 30})
        registered = engine.register_agent(definition).unwrap()
        task = spec.render_task({"question": "What did the source find?", "evidence": "[source-1] A retained finding."})
        result = await engine.run_agent(registered, task, RunOptions(timeout_seconds=30))
        assert result.status == "succeeded" and result.recording_status == "complete"
        assert result.persistence_state == "committed" and result.output_delivery == "artifact"
        assert result.definition_ref == definition.definition_ref and result.output_ref is not None
        assert result.counters["model_calls"] == 1 and result.counters["tool_calls"] == 0
        assert len(requests) == 1 and not requests[0].get("tools")
        assert any(task == message.get("content") for message in requests[0]["messages"])
        run = RunRef(engine.storage.store_id, result.execution["run_id"])
        access = (await engine.open_run_access(run, RunAccessRequest(read_objects=(ArtifactReadRequest(result.output_ref),)))).unwrap()
        async with access:
            reader = (await access.storage.artifacts.open(access.context, result.output_ref)).unwrap()
            try:
                chunk = (await reader.read(access.context)).unwrap()
                assert chunk.eof and chunk.bytes == report.encode("utf-8")
            finally:
                await reader.aclose(access.context)
    finally:
        assert (await engine.close()).complete


@pytest.mark.asyncio
async def test_existing_registration_authority_rejects_changed_bindings(tmp_path):
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store"))).unwrap()
    try:
        catalog = AgentCatalog()
        spec = catalog.load("baseline.researcher", 1)
        first = spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=(ToolRef("web.search"),))
        registered = engine.register_agent(first).unwrap()
        assert engine.register_agent(first).unwrap() == registered
        changed = spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=())
        rejected = engine.register_agent(changed)
        assert isinstance(rejected, Err) and rejected.error.code == "REGISTRATION_CONFLICT"
        distinct = spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=(), agent_id="host.researcher")
        assert engine.register_agent(distinct).unwrap().ref.agent_id == "host.researcher"
        assert registered.ref.revision == 1
    finally:
        assert (await engine.close()).complete
