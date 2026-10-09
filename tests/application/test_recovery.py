"""Recovery exercises real child admission, provider outcomes and SQLite records."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from deepresearch.application import RecoveryPolicy
from deepresearch.application.recovery import RecoveryCoordinator
from deepresearch.engine.contracts import EngineError
from deepresearch.engine.providers import ProviderFactory
from tests.application.test_role_outputs import (
    MODEL, ROLE, TwoWriterMethod, environment, execute, events,
)


def provider(monkeypatch, *, failures=1, status=429, code="rate_limit_exceeded", retry_after="0", transport_error=None):
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        if len(calls) <= failures:
            if transport_error:
                raise transport_error("Controlled unknown remote outcome", request=request)
            return httpx.Response(status, headers={"Retry-After": retry_after},
                json={"error": {"code": code, "type": "tokens", "message": "Do not copy this message"}})
        return httpx.Response(200, json={"id": f"response-{len(calls)}", "model": MODEL,
            "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "# Saved report\n"}}]})
    native = ProviderFactory.open
    async def opened(config, context=None):
        return await native(config, context, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(ProviderFactory, "open", opened)
    return calls


class OneRole:
    async def run(self, context, task_input, parameters):
        async with context.node("writer", "agent"):
            outcome = await context.port.invoke_agent(ROLE, {"question": "Use the retained evidence.", "evidence": "Known evidence."})
        return {"report_ref": outcome["output_ref"]}


def configure(service, *, restarts=3, delay=.01, cap=.1):
    service.recovery = RecoveryCoordinator(RecoveryPolicy(max_restarts=restarts,
        initial_delay_seconds=delay, max_delay_seconds=cap, max_wait_seconds=1, jitter_fraction=0))


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_response_recovers_same_input_with_recorded_distinct_children(tmp_path, monkeypatch, status):
    calls = provider(monkeypatch, status=status)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status == "succeeded" and len(calls) == 2
        assert calls[0] == calls[1]
        rows = [row["event"] for row in await events(service, view.run_id)]
        models = [r for r in rows if r["kind"] == "model.outcome"]
        assert len(models) == 2
        assert len({r["context"]["run_id"] for r in models}) == 2
        assert len({r["context"]["attempt_id"] for r in models}) == 2
        kinds = [r["kind"] for r in rows]
        assert kinds.count("workflow.role.restart") == kinds.count("workflow.role.recovered") == 1
        retry = next(r["payload"] for r in rows if r["kind"] == "workflow.role.restart")
        assert retry["error"]["details"]["http_status"] == status
        assert retry["error"]["details"]["settled_role_attempt"]["terminal_receipt"]
        assert "Do not copy this message" not in json.dumps(rows)
        # Failed provider usage is unknown, never silently charged as zero.
        assert view.usage["completeness"] != "complete"
        assert len(view.usage["per_attempt_usage_refs"]) == 2


@pytest.mark.parametrize("options", [
    {"status": 401}, {"status": 400}, {"status": 429, "code": "insufficient_quota"},
    {"transport_error": httpx.ReadTimeout}, {"transport_error": httpx.ConnectError},
    {"retry_after": "120"},
])
async def test_permanent_unknown_and_excessive_wait_do_not_replay(tmp_path, monkeypatch, options):
    calls = provider(monkeypatch, **options)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status != "succeeded" and len(calls) == 1


async def test_persistent_failure_stops_at_restart_limit_with_original_cause(tmp_path, monkeypatch):
    calls = provider(monkeypatch, failures=20)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service, restarts=2)
        view = await execute(service)
        assert view.status == "failed" and len(calls) == 3
        assert view.error["details"]["http_status"] == 429
        rows = [r["event"] for r in await events(service, view.run_id)]
        exhausted = [r for r in rows if r["kind"] == "workflow.role.recovery_exhausted"]
        assert exhausted[-1]["payload"]["reason"] == "restart_allowance"


async def test_explicit_zero_restart_policy_keeps_single_dispatch(tmp_path, monkeypatch):
    calls = provider(monkeypatch)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service, restarts=0)
        view = await execute(service)
        assert view.status == "failed" and len(calls) == 1


async def test_recording_failure_prevents_replacement(tmp_path, monkeypatch):
    from deepresearch.application.platform import ResearchPlatformPort
    calls = provider(monkeypatch)
    native = ResearchPlatformPort.emit
    async def emit(self, kind, payload, **kwargs):
        if kind == "workflow.role.restart":
            raise EngineError("RECORDING_INCOMPLETE", "Controlled retry journal failure")
        return await native(self, kind, payload, **kwargs)
    monkeypatch.setattr(ResearchPlatformPort, "emit", emit)
    async with environment(tmp_path, OneRole()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status != "succeeded" and len(calls) == 1


async def test_shared_model_grant_is_not_refilled_by_recovery(tmp_path, monkeypatch):
    calls = provider(monkeypatch)
    async with environment(tmp_path, OneRole()) as (engine, service):
        engine.settings.limits["model_calls"] = 1
        configure(service)
        view = await execute(service)
        assert view.status != "succeeded" and len(calls) == 1
        assert view.error["code"] == "LIMIT_EXCEEDED"


async def test_cancellation_interrupts_cooldown_without_another_request(tmp_path, monkeypatch):
    from deepresearch.application.platform import ResearchPlatformPort
    from deepresearch.workflows import ResearchRunRequest
    from tests.application.test_role_outputs import PROFILE
    calls = provider(monkeypatch)
    waiting = asyncio.Event()
    native = ResearchPlatformPort.emit
    async def emit(self, kind, payload, **kwargs):
        result = await native(self, kind, payload, **kwargs)
        if kind == "workflow.role.wait":
            waiting.set()
        return result
    monkeypatch.setattr(ResearchPlatformPort, "emit", emit)
    async with environment(tmp_path, OneRole()) as (engine, service):
        service.recovery = RecoveryCoordinator(RecoveryPolicy(initial_delay_seconds=30))
        accepted = await service.start_run(ResearchRunRequest(client_request_id="cancel-recovery",
            method_id="test.role-outputs", input={}, profile_ref=PROFILE, model_ref=MODEL, timeout_seconds=90))
        await asyncio.wait_for(waiting.wait(), 5)
        await service.cancel_run(accepted.run_id)
        async with asyncio.timeout(2):
            while (view := await service.get_run(accepted.run_id)).active:
                await asyncio.sleep(.01)
        assert view.status == "cancelled" and len(calls) == 1


async def test_completed_node_is_not_replayed(tmp_path, monkeypatch):
    calls = []
    native = ProviderFactory.open
    def handle(request):
        calls.append(json.loads(request.content))
        if len(calls) == 2:
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded", "type": "tokens"}})
        return httpx.Response(200, json={"model": MODEL, "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": "# Preserved output\n"}}]})
    async def opened(config, context=None):
        return await native(config, context, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(ProviderFactory, "open", opened)
    async with environment(tmp_path, TwoWriterMethod()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status == "succeeded" and len(calls) == 3
        assert calls[0] != calls[1] == calls[2]


async def test_one_rate_limited_role_does_not_cancel_other_workers(tmp_path, monkeypatch):
    from deepresearch.workflows.components.parallel import bounded_map
    calls, cancellations = [0, 0], []
    native = ProviderFactory.open
    both_started = asyncio.Event()
    async def handle(request):
        body = json.loads(request.content)
        job = 1 if "job=1" in json.dumps(body) else 0
        calls[job] += 1
        if all(calls):
            both_started.set()
        await both_started.wait()
        if job == 0 and calls[job] == 1:
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded", "type": "tokens"}})
        try:
            await asyncio.sleep(.03)
        except asyncio.CancelledError:
            cancellations.append(job)
            raise
        return httpx.Response(200, json={"model": MODEL, "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": f"# Finished job={job}\n"}}]})
    async def opened(config, context=None):
        return await native(config, context, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(ProviderFactory, "open", opened)
    class Parallel:
        async def run(self, context, task_input, parameters):
            async def worker(job):
                return await context.port.invoke_agent(ROLE, {"question": f"job={job}", "evidence": "Known evidence."})
            results = await bounded_map([0, 1], worker, concurrency=2)
            return {"report_ref": results[0]["output_ref"]}
    async with environment(tmp_path, Parallel()) as (engine, service):
        configure(service)
        view = await execute(service)
        assert view.status == "succeeded" and calls == [2, 1] and not cancellations


@pytest.mark.parametrize("values", [
    {"max_restarts": True}, {"max_restarts": -1}, {"max_restarts": 10},
    {"initial_delay_seconds": 0}, {"max_wait_seconds": float('nan')},
    {"jitter_fraction": float('inf')}, {"max_delay_seconds": 1000},
])
def test_invalid_recovery_policy_is_rejected(values):
    with pytest.raises(ValueError):
        RecoveryPolicy(**values)
