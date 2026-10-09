"""Native service failures use the same bounded, recorded host recovery."""
from dataclasses import replace
import json

import httpx
import pytest

from deepresearch.engine.providers import ProviderFactory
from tests.application.test_recovery import OneRole, configure
from tests.application.test_role_outputs import environment, execute, events


def install(monkeypatch, *, protocol, status="failed", code="server_error", reason=None, text="", tool=False):
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        if protocol == "responses":
            if len(calls) == 1:
                outputs = [{"type": "message", "content": [{"type": "output_text", "text": text}]}] if text else []
                if tool:
                    outputs.append({"type": "function_call", "call_id": "c1", "name": "unapproved", "arguments": "{}"})
                return httpx.Response(200, json={"status": status, "output": outputs,
                    "error": {"code": code, "message": "private-service-detail"},
                    "incomplete_details": {"reason": reason}})
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "# Saved report"}]}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "insufficient_system_resource" if len(calls) == 1 else "stop",
            "message": {"role": "assistant", "content": text if len(calls) == 1 else "# Saved report"}}]})
    native = ProviderFactory.open
    async def opened(config, context=None):
        if protocol == "responses":
            config = replace(config, provider="openai")
        return await native(config, context, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(ProviderFactory, "open", opened)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["responses", "chat"])
async def test_native_service_failure_restarts_only_failed_role_with_identical_request(tmp_path, monkeypatch, protocol):
    calls = install(monkeypatch, protocol=protocol)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status == "succeeded" and len(calls) == 2, view.error
        assert calls[0] == calls[1]
        rows = [r["event"] for r in await events(service, view.run_id)]
        models = [r for r in rows if r["kind"] == "model.outcome"]
        assert len({r["context"]["run_id"] for r in models}) == 2
        restart = next(r["payload"] for r in rows if r["kind"] == "workflow.role.restart")
        facts = restart["error"]["details"]
        assert facts["settled_role_attempt"]["terminal_receipt"]
        assert facts["visible_text_bytes"] == facts["native_tool_call_count"] == 0
        assert facts["provider_status"] == "failed" if protocol == "responses" else facts["native_finish_reason"] == "insufficient_system_resource"
        assert "private-service-detail" not in json.dumps(rows)
        assert len(view.usage["per_attempt_usage_refs"]) == 2
        assert view.usage["completeness"] != "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [
    {"status": "incomplete", "code": None, "reason": "max_output_tokens"},
    {"status": "incomplete", "code": None, "reason": "content_filter"},
    {"status": "incomplete", "code": None, "reason": None},
    {"status": "incomplete", "code": "server_error", "reason": "content_filter"},
    {"status": "failed", "code": "insufficient_quota"},
    {"status": "failed", "code": "server_error", "text": "partial"},
    {"status": "failed", "code": "server_error", "tool": True},
    {"status": "failed", "code": "server_error", "reason": "unrecognized_reason"},
])
async def test_nontransient_unknown_partial_and_tool_bearing_response_never_replays(tmp_path, monkeypatch, options):
    calls = install(monkeypatch, protocol="responses", **options)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status == "failed" and len(calls) == 1
        assert view.error["details"]["provider_status"] == options["status"]
        assert view.error["details"]["provider_incomplete_reason"] == (None if options.get("reason") == "unrecognized_reason" else options.get("reason"))
        rows = [r["event"] for r in await events(service, view.run_id)]
        assert not any(r["kind"] == "workflow.role.restart" for r in rows)
        assert "private-service-detail" not in json.dumps(rows)


@pytest.mark.asyncio
async def test_native_transient_obeys_zero_restart_policy(tmp_path, monkeypatch):
    calls = install(monkeypatch, protocol="responses")
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service, restarts=0)
        view = await execute(service)
        assert view.status == "failed" and len(calls) == 1
        rows = [r["event"] for r in await events(service, view.run_id)]
        assert any(r["kind"] == "workflow.role.recovery_exhausted" for r in rows)
