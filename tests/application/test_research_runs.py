"""Application semantics use the real Engine, Storage, recorder and invoker."""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.application import ResearchRunService
from deepresearch.application.platform import RESEARCH_STATE_KEY
from deepresearch.engine.connections import Engine, EngineSettings
from deepresearch.engine.contracts import (
    EngineError, Err, RunRef, SnapshotProposal, ToolExecutionResult,
    canonical_json, digest_bytes, digest_json, new_id,
)
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.methods.baseline.v1 import BaselineMethod, definition as baseline_definition
from deepresearch.engine.providers import ProviderConfig, ProviderFactory
from deepresearch.workflows import MethodDefinition, MethodRegistry, ResearchRunRequest, SourceRange


class ReportMethod:
    def __init__(self, wait=None):
        self.calls = 0
        self.wait = wait
        self.entered = asyncio.Event()

    async def run(self, context, task_input, parameters):
        self.calls += 1
        async with context.node("report", "publication"):
            self.entered.set()
            if self.wait is not None:
                await self.wait.wait()
            ref = await context.port.publish(task_input["message"].encode(), "text/markdown", "report.md")
            await context.checkpoint({"report_ref": ref})
            await context.port.update(report_ref=ref)
        return {"report_ref": ref}


def registry_for(method):
    registry = MethodRegistry()
    registry.register(MethodDefinition("test.report", 1, "Controlled Storage report",
        {"type": "object", "additionalProperties": False,
         "properties": {"message": {"type": "string", "minLength": 1}}, "required": ["message"]},
        {"type": "object", "additionalProperties": False}), method)
    return registry


def request(client_id="first", **fields):
    return ResearchRunRequest(client_request_id=client_id, method_id="test.report",
        input={"message": "Saved α report."}, timeout_seconds=30.0, **fields)


def settings(tmp_path, profiles=None):
    return EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store", profiles=profiles or {})


def service_for(engine, method=None, registry=None):
    return ResearchRunService(engine, registry or registry_for(method), AgentCatalog(), TokenMeter())


async def terminal(service, run_id):
    for _ in range(1000):
        view = await service.get_run(run_id)
        if not view.active:
            return view
        await asyncio.sleep(0.01)
    pytest.fail("Research execution did not settle")


@pytest.mark.asyncio
async def test_original_request_and_pins_remain_readable_after_restart(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = service_for(engine, ReportMethod())
    submitted = request()
    try:
        view = await terminal(service, (await service.start_run(submitted)).run_id)
        assert view.status == "succeeded", view.error
        rows = (await service.events(view.run_id))["events"]
        accepted = next(row["event"]["payload"] for row in rows if row["event"]["kind"] == "workflow.accepted")
        request_id = accepted["request_ref"]["artifact_id"]
        manifest_id = accepted["method_manifest_ref"]["artifact_id"]
    finally:
        assert (await service.close()).complete
        assert (await engine.close()).complete
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    unused_method = ReportMethod()
    restored = service_for(reopened, unused_method)
    try:
        saved = await restored.start_run(submitted)
        chunk = await restored.read_artifact(saved.run_id, request_id)
        content = base64.b64decode(chunk["data"])
        assert chunk["eof"] and json.loads(content) == submitted.to_dict()
        assert digest_json(json.loads(content)) == accepted["request_fingerprint"]
        manifest_chunk = await restored.read_artifact(saved.run_id, manifest_id)
        manifest = json.loads(base64.b64decode(manifest_chunk["data"]))
        assert manifest["request_ref"] == accepted["request_ref"]
        assert manifest["method"] == saved.pins["method"]
        assert unused_method.calls == 0
    finally:
        assert (await restored.close()).complete
        assert (await reopened.close()).complete


@pytest.mark.asyncio
async def test_long_method_has_bounded_terminal_without_losing_saved_nodes(tmp_path):
    class LongMethod(ReportMethod):
        async def run(self, context, task_input, parameters):
            for index in range(4):
                async with context.node(f"long.{index}", "discovery", {"query": "x" * 8000}):
                    pass
            return await super().run(context, task_input, parameters)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = service_for(engine, LongMethod())
    try:
        view = await terminal(service, (await service.start_run(request())).run_id)
        assert view.status == "succeeded", view.error
        rows = (await service.events(view.run_id))["events"]
        payload = next(row["event"]["payload"] for row in rows if row["event"]["kind"] == "workflow.finished")
        assert "nodes" not in payload
        assert payload["node_count"] == len(view.nodes)
        assert payload["nodes_sha256"] == digest_json([node.to_dict() for node in view.nodes])
        assert len(canonical_json(payload)) <= 16384
        assert all(node.status == "succeeded" for node in view.nodes)
    finally:
        assert (await service.close()).complete
        assert (await engine.close()).complete
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    restored = service_for(reopened, LongMethod())
    try:
        saved = await restored.get_run(view.run_id)
        assert saved.status == "succeeded" and saved.nodes == view.nodes
    finally:
        assert (await restored.close()).complete
        assert (await reopened.close()).complete


@pytest.mark.asyncio
async def test_real_storage_idempotency_reopen_report_and_no_model_resolution(tmp_path, monkeypatch):
    method = ReportMethod()
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = service_for(engine, method)
    def no_model(*args):
        pytest.fail("Model-free method resolved credentials")
    monkeypatch.setattr(engine.profiles, "resolve", no_model)
    try:
        handles = await asyncio.gather(service.start_run(request()), service.start_run(request()))
        assert handles[0].run_id == handles[1].run_id
        run_id = handles[0].run_id
        view = await terminal(service, run_id)
        assert view.status == "succeeded" and view.recording_status == "complete"
        assert view.checkpoint_ref["checkpoint_id"]
        assert method.calls == 1 and engine.list_agents() == []
        state = (await engine.read_run_state(service.run_ref(run_id), RESEARCH_STATE_KEY)).unwrap()
        assert state.value["view"]["status"] == "succeeded" and state.version > 4
        assert state.value["method_manifest_ref"]["artifact_id"]
        chunks, offset = [], 0
        while True:
            chunk = await service.read_report(run_id, offset, 5)
            data = base64.b64decode(chunk["data"])
            assert chunk["byte_length"] == len(data)
            chunks.append(data)
            offset += chunk["byte_length"]
            assert offset == chunk["next_offset"]
            if chunk["eof"]:
                break
        assert b"".join(chunks).decode() == "Saved α report."
        with pytest.raises(EngineError) as conflict:
            await service.start_run(request(parameters={"different": True}))
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
        rows = (await service.events(run_id))["events"]
        assert [row["event"]["kind"] for row in rows].count("workflow.finished") == 1
        assert not any(row["event"]["kind"] == "agent.finished" for row in rows)
        assert (await service.list_runs())["runs"][0]["run_id"] == run_id
    finally:
        assert (await service.close()).complete
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = service_for(reopened, registry=MethodRegistry())
    try:
        restored = await recovered.start_run(request())
        assert restored.status == "succeeded" and not restored.active
        assert restored.report_ref == view.report_ref
        assert base64.b64decode((await recovered.read_report(run_id))["data"]).decode() == "Saved α report."
        assert recovered.active_count == 0
    finally:
        await recovered.close()
        await reopened.close()


@pytest.mark.asyncio
async def test_validation_and_profile_pins_before_provision(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = service_for(engine, ReportMethod())
    try:
        invalid = [request().model_copy(update={"method_revision": 2}),
                   request().model_copy(update={"input": {"message": 2}}),
                   request().model_copy(update={"model_ref": "unconfigured"}),
                   request().model_copy(update={"method_revision": True}),
                   request().model_copy(update={"parameters": {"unknown": True}})]
        codes = []
        for data in invalid:
            with pytest.raises(EngineError) as error:
                await service.start_run(data)
            codes.append(error.value.code)
        assert codes == ["METHOD_NOT_FOUND", "INVALID_DATA", "PROFILE_MISMATCH", "INVALID_DATA", "INVALID_DATA"]
        assert (await engine.list_runs()).unwrap()["runs"] == []
    finally:
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_http_caller_cancellation_during_admission_leaves_owned_execution(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = ReportMethod()
    service = service_for(engine, method)
    entered, release = asyncio.Event(), asyncio.Event()
    native = engine.open_workflow_session
    async def gated(**kwargs):
        entered.set()
        await release.wait()
        return await native(**kwargs)
    monkeypatch.setattr(engine, "open_workflow_session", gated)
    try:
        caller = asyncio.create_task(service.start_run(request()))
        await entered.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        release.set()
        await asyncio.gather(*tuple(service._starting))
        view = await terminal(service, next(iter(service._runs)))
        assert view.status == "succeeded" and method.calls == 1
    finally:
        release.set()
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_cancel_signals_owned_method_and_records_terminal_without_success(tmp_path):
    method = ReportMethod(asyncio.Event())
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = service_for(engine, method)
    try:
        accepted = await service.start_run(request())
        await method.entered.wait()
        assert (await service.cancel_run(accepted.run_id)).active
        view = await terminal(service, accepted.run_id)
        assert view.status == "cancelled" and view.report_ref is None
        rows = (await service.events(accepted.run_id))["events"]
        terminal_payload = next(row["event"]["payload"] for row in rows if row["event"]["kind"] == "workflow.finished")
        assert terminal_payload["status"] == "cancelled"
        assert any(row["event"]["kind"] == "workflow.node.failed" for row in rows)
        assert (await service.start_run(request())).run_id == accepted.run_id
        assert method.calls == 1
    finally:
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_unknown_admission_is_durably_reserved_and_never_redispatched(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = ReportMethod()
    service = service_for(engine, method)
    native = engine.storage.state.commit
    async def unavailable(context, operation_id, mutations, activity=None):
        if any(mutation.key == RESEARCH_STATE_KEY for mutation in mutations):
            return Err(EngineError("STORAGE_UNAVAILABLE", "Controlled lost acknowledgement", commit_state="unknown"))
        return await native(context, operation_id, mutations, activity)
    monkeypatch.setattr(engine.storage.state, "commit", unavailable)
    try:
        with pytest.raises(EngineError):
            await service.start_run(request())
        assert method.calls == 0
        monkeypatch.setattr(engine.storage.state, "commit", native)
        reserved = await service.start_run(request())
        assert reserved.status == "interrupted" and method.calls == 0
        with pytest.raises(EngineError) as error:
            await service.start_run(request().model_copy(update={"timeout_seconds": 10.0}))
        assert error.value.code == "IDEMPOTENCY_CONFLICT"
        run_id = reserved.run_id
    finally:
        await service.close()
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = service_for(reopened, method)
    try:
        assert (await recovered.start_run(request())).run_id == run_id
        assert method.calls == 0 and recovered.active_count == 0
    finally:
        await recovered.close()
        await reopened.close()


@pytest.mark.asyncio
async def test_failed_terminal_recording_cannot_reopen_as_success(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = ReportMethod()
    service = service_for(engine, method)
    native = engine.emit_workflow_event
    async def lost(session, kind, payload, **kwargs):
        if kind == "workflow.finished":
            return Err(EngineError("STORAGE_UNAVAILABLE", "Controlled recording failure", commit_state="unknown"))
        return await native(session, kind, payload, **kwargs)
    monkeypatch.setattr(engine, "emit_workflow_event", lost)
    try:
        run_id = (await service.start_run(request())).run_id
        view = await terminal(service, run_id)
        assert view.status == "interrupted" and view.recording_status == "incomplete"
        assert method.calls == 1
    finally:
        await service.close()
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = service_for(reopened, method)
    try:
        view = await recovered.start_run(request())
        assert view.run_id == run_id and view.status == "interrupted" and method.calls == 1
    finally:
        await recovered.close()
        await reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["stop", "length"])
async def test_baseline_real_saved_reads_writer_sees_only_selected_text(tmp_path, monkeypatch, finish_reason):
    calls, fetched = [], []
    text = ("alpha research evidence\n" + "background\n" * 199 + "UNSELECTED_SECRET_MARKER\n").encode()
    def handler(request):
        calls.append(request.content.decode())
        return httpx.Response(200, json={"id": "controlled", "model": "deepseek-flash",
            "choices": [{"finish_reason": finish_reason, "message": {"role": "assistant", "content": "A cited report [requested-001]."}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}})
    original_open = ProviderFactory.open
    async def controlled_open(config, context):
        return await original_open(config, context, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ProviderFactory, "open", controlled_open)
    profile = ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "controlled-test-key")
    engine = (await Engine.open(settings(tmp_path, {"controlled": profile}))).unwrap()
    native_execute = engine.executor.execute
    async def controlled_tool(definition, arguments, context, plan):
        if definition.name == "document.read":
            return await native_execute(definition, arguments, context, plan)
        result = ToolExecutionResult(definition.ref, context.descriptor(), "succeeded",
            process={"dispatched": True, "cleanup": {"complete": True}})
        if definition.name == "web.search":
            result.result = {"results": []}
            return result
        assert definition.name == "web.fetch"
        plan.assert_recorded()
        fetched.append(arguments["url"])
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
    monkeypatch.setattr(engine.executor, "execute", controlled_tool)
    registry = MethodRegistry()
    registry.register(baseline_definition(), BaselineMethod())
    service = service_for(engine, registry=registry)
    try:
        accepted = await service.start_run(ResearchRunRequest(client_request_id="baseline", input={"question": "alpha research"},
            parameters={"source_urls": ["https://example.org/source"], "search_tools": ["web.search"],
                        "max_scan_bytes": 4096}, profile_ref="controlled", model_ref="deepseek-flash", timeout_seconds=60.0))
        view = await terminal(service, accepted.run_id)
        if finish_reason == "length":
            assert view.status == "failed" and view.report_ref is None
            assert view.error["code"] == "provider.incomplete"
            assert view.usage["known_subtotals"]["total_tokens"] == 28
            return
        assert view.status == "succeeded", view.error
        assert view.sources.items[0].status == "succeeded" and view.context_plan.selections
        assert len(calls) == 1 and "alpha research evidence" in calls[0]
        assert "UNSELECTED_SECRET_MARKER" not in calls[0]
        assert fetched == ["https://example.org/source"]
        assert view.usage["known_subtotals"]["total_tokens"] == 28
        child = engine.list_agents()[0]["definition"]
        assert child["allowed_tools"] == [] and child["input_schema"]["type"] == "string"
        source = await service.read_source(view.run_id, "requested-001", SourceRange(kind="lines", start=201, end_exclusive=202), 1024)
        assert source["text"] == "UNSELECTED_SECRET_MARKER"
        rows = (await service.events(view.run_id))["events"]
        assert len([row for row in rows if row["event"]["kind"] == "agent.finished"]) == 1
        assert all(row["event"]["context"]["context_kind"] == "agent" for row in rows if row["event"]["kind"] == "agent.finished")
    finally:
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_cleanup_failure_never_reopens_success(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = ReportMethod()
    service = service_for(engine, method)
    native = engine.open_workflow_session
    async def bad_session(**kwargs):
        session = (await native(**kwargs)).unwrap()
        close = session.close
        async def failed_close():
            await close()
            raise RuntimeError("private cleanup detail")
        monkeypatch.setattr(session, "close", failed_close)
        from deepresearch.engine.contracts import Ok
        return Ok(session)
    monkeypatch.setattr(engine, "open_workflow_session", bad_session)
    try:
        run_id = (await service.start_run(request())).run_id
        view = await terminal(service, run_id)
        assert view.status == "interrupted" and view.recording_status == "incomplete"
        assert "private cleanup" not in str(view.error)
        assert not (await service.close()).complete
    finally:
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = service_for(reopened, method)
    try:
        view = await recovered.start_run(request())
        assert view.run_id == run_id and view.status == "interrupted" and method.calls == 1
    finally:
        await recovered.close()
        await reopened.close()


@pytest.mark.asyncio
async def test_swallowed_recording_error_still_prevents_success_and_preserves_unknown_commit(tmp_path, monkeypatch):
    from deepresearch.engine.contracts import ToolResult, ToolRef
    class SwallowingMethod(ReportMethod):
        async def run(self, context, task_input, parameters):
            try:
                await context.port.run_tool("web.search", {"query": "alpha", "max_results": 1})
            except EngineError as error:
                assert error.commit_state == "unknown" and error.observed_effect_state == "unknown"
            return await super().run(context, task_input, parameters)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = SwallowingMethod()
    service = service_for(engine, method)
    async def uncertain(*args):
        return ToolResult(ToolRef("web.search"), {}, "failed",
            recording={"status": "incomplete", "error": EngineError("STORAGE_UNAVAILABLE", "Controlled failure",
                commit_state="unknown", observed_effect_state="unknown")})
    monkeypatch.setattr(engine, "run_workflow_tool", uncertain)
    try:
        run_id = (await service.start_run(request())).run_id
        view = await terminal(service, run_id)
        assert view.status == "interrupted" and view.error["commit_state"] == "unknown"
        assert view.error["observed_effect_state"] == "unknown"
    finally:
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_serialized_projection_updates_preserve_independent_fields(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = ReportMethod(asyncio.Event())
    service = service_for(engine, method)
    try:
        run_id = (await service.start_run(request())).run_id
        await method.entered.wait()
        port = service._runs[run_id].port
        await asyncio.gather(port.update(usage={"controlled": True}),
            port.update(sources={"items": [{"item_id": "one", "url": "https://example.org/one", "status": "pending"}]}))
        state = (await engine.read_run_state(service.run_ref(run_id), RESEARCH_STATE_KEY)).unwrap()
        assert state.value["view"]["usage"] == {"controlled": True}
        assert state.value["view"]["sources"]["items"][0]["item_id"] == "one"
        with pytest.raises(EngineError):
            await port.update(cleanup=True, report_ref={"store_id": engine.storage.store_id, "artifact_id": "new"})
        with pytest.raises(EngineError):
            await port.update(cleanup=True, nodes=[{"node_id": "new", "kind": "test", "status": "succeeded"}])
        method.wait.set()
        assert (await terminal(service, run_id)).status == "succeeded"
    finally:
        method.wait.set()
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_hook_cleanup_is_retained_and_not_overwritten_by_session_close(tmp_path, monkeypatch):
    from deepresearch.engine.contracts import CleanupReport
    from deepresearch.extensions import HookDispatcher

    async def unconfirmed(self, timeout_seconds=5):
        assert timeout_seconds == 5
        return CleanupReport(False, ["Controlled handler did not settle"], ["controlled-hook-task"])
    monkeypatch.setattr(HookDispatcher, "close", unconfirmed)
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = service_for(engine, ReportMethod())
    try:
        run_id = (await service.start_run(request())).run_id
        view = await terminal(service, run_id)
        assert view.status == "interrupted" and view.error["code"] == "CLEANUP_INCOMPLETE"
        live = service._runs[run_id]
        assert live.hooks is not None and not live.cleanup.complete
        assert "controlled-hook-task" in live.cleanup.unconfirmed_resources
        assert not live.session.context.lease.active
        cleanup = await service.close()
        assert not cleanup.complete and "controlled-hook-task" in cleanup.unconfirmed_resources
    finally:
        await engine.close()
