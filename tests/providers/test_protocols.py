import asyncio
import json

import httpx
import pytest

from ebd.contracts import Err, Ok, EngineError
from ebd.providers import ModelRequest, ModelTool, ProviderConfig, ProviderFactory


def run(awaitable):
    return asyncio.run(awaitable)


TOOL = ModelTool("web.search", "1", "t_search", "Search", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False})


def request(**kw):
    return ModelRequest("Use approved tools", "Research test", (TOOL,), "run1", "a" * 64, **kw)


def test_deepseek_preserves_native_reasoning_and_correlates_calls():
    async def exercise():
        bodies = []
        async def handler(req):
            body = json.loads(req.content)
            bodies.append(body)
            if len(bodies) == 1:
                return httpx.Response(200, json={"id": "resp1", "model": "deepseek-flash", "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "reasoning_content": "private native state", "tool_calls": [{"id": "call1", "type": "function", "function": {"name": "t_search", "arguments": '{"query":"EBD"}'}}]}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
            assert body["messages"][-2]["reasoning_content"] == "private native state"
            assert body["messages"][-1]["tool_call_id"] == "call1"
            return httpx.Response(200, json={"id": "resp2", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Exact\nreport\n"}}]})
        opened = await ProviderFactory.open(ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-secret"), transport=httpx.MockTransport(handler))
        assert isinstance(opened, Ok)
        session = opened.value
        prepared = session.prepare(request())
        assert "provider-hosted" in json.loads(prepared.body_bytes)["messages"][0]["content"]
        first = await session.generate(prepared)
        assert first.completion == "tool_calls"
        assert first.tool_calls[0].arguments == {"query": "EBD"}
        with pytest.raises(ValueError, match="exactly one"):
            session.prepare(request(continuation=first.continuation, step_index=1))
        second = await session.generate(request(continuation=first.continuation, step_index=1, tool_results=({"provider_call_id": "call1", "status": "succeeded", "result": {"hits": []}},)))
        assert second.raw_visible_text == "Exact\nreport\n"
        assert second.usage["completeness"] == "unknown"
        assert second.usage["input_tokens"] is None
        assert "test-secret" not in json.dumps(second.request_audit)
        await session.aclose()
    run(exercise())


def test_responses_replays_complete_native_output_and_original_call_id():
    async def exercise():
        seen = []
        async def handler(req):
            body = json.loads(req.content)
            seen.append(body)
            assert body["store"] is False
            assert all(t["type"] == "function" for t in body["tools"])
            if len(seen) == 1:
                return httpx.Response(200, json={"id": "r1", "status": "completed", "output": [{"type": "reasoning", "id": "rs1", "encrypted_content": "opaque-native", "summary": []}, {"type": "function_call", "id": "fc1", "call_id": "call-original", "name": "t_search", "arguments": '{"query":"test"}'}]})
            assert body["input"][-3]["encrypted_content"] == "opaque-native"
            assert body["input"][-2]["call_id"] == "call-original"
            assert body["input"][-1]["call_id"] == "call-original"
            return httpx.Response(200, json={"id": "r2", "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "A"}, {"type": "output_text", "text": "B"}]}]})
        session = (await ProviderFactory.open(ProviderConfig("openai", "gpt-6-luna", "https://provider.invalid/v1", "test-secret"), transport=httpx.MockTransport(handler))).value
        first = await session.generate(request())
        result = await session.generate(request(continuation=first.continuation, step_index=1, tool_results=({"provider_call_id": "call-original", "status": "succeeded", "result": []},)))
        assert result.raw_visible_text == "AB"
        await session.aclose()
    run(exercise())


def test_transport_failure_is_once_and_sanitized():
    async def exercise():
        calls = 0
        def handler(req):
            nonlocal calls
            calls += 1
            raise httpx.ReadError("raw-error-with-test-secret", request=req)
        session = (await ProviderFactory.open(ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-secret"), transport=httpx.MockTransport(handler))).value
        result = await session.generate(request())
        assert calls == 1 and result.completion == "failed"
        assert "raw-error" not in str(result.error)
        assert result.error.details["effect_state"] == "unknown"
        await session.aclose()
    run(exercise())


def test_duplicate_native_calls_and_truncated_calls_never_dispatch():
    async def exercise():
        async def handler(req):
            call = {"id": "same", "type": "function", "function": {"name": "t_search", "arguments": '{}'}}
            return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [call, call]}}]})
        session = (await ProviderFactory.open(ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test-secret"), transport=httpx.MockTransport(handler))).value
        response = await session.generate(request())
        assert response.completion == "failed" and response.tool_calls == ()
        with pytest.raises(ValueError, match="byte allowance"):
            session.prepare(request(max_request_bytes=10))
        await session.aclose()
    run(exercise())


def test_vllm_requires_deployment_manifest_and_unknown_settings_fail():
    assert isinstance(run(ProviderFactory.open(ProviderConfig("vllm", "Qwen", "http://localhost:8000/v1"))), Err)
    assert isinstance(run(ProviderFactory.open(ProviderConfig("openai", "gpt-6-luna", "https://provider.invalid", "test", {"enable_search": False}))), Err)
    assert isinstance(run(ProviderFactory.open(ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "test", {"thinking": "enabled", "temperature": 0.2}))), Err)


def test_http_error_classifier_exposes_only_allowlisted_facts():
    async def exercise():
        def handler(req):
            return httpx.Response(429, headers={"retry-after": "15", "x-private-secret": "must-never-escape"}, json={"error": {"code": "insufficient_quota", "type": "insufficient_quota", "message": "billing diagnostic must-never-escape", "param": "secret-param"}})
        session = (await ProviderFactory.open(ProviderConfig("openai", "gpt-6-luna", "https://provider.invalid/v1", "test-secret"), transport=httpx.MockTransport(handler))).value
        result = await session.generate(request())
        assert result.error.details["http_status"] == 429
        assert result.error.details["provider_error_code"] == "insufficient_quota"
        assert result.error.details["provider_error_type"] == "insufficient_quota"
        assert result.error.details["retry_after_seconds"] == 15
        assert "must-never-escape" not in str(result.error.details)
        await session.aclose()
    run(exercise())


def qwen_manifest():
    # Explicit synthetic declarations exercise the client protocol; these are
    # not descriptions or evidence of a deployed GPU server.
    return {
        "schema_version": 1, "manifest_ref": {"name": "controlled-qwen", "revision": "1"},
        "endpoint_id": "configured-endpoint", "served_model_id": "Qwen-test-alias",
        "model_repository": "controlled/model", "model_revision": "test-revision",
        "tokenizer_repository": "controlled/tokenizer", "tokenizer_revision": "test-revision",
        "chat_template_sha256": "sha256:" + "a" * 64, "vllm_version": "controlled-version",
        "server_image_digest": "sha256:" + "b" * 64,
        "tool_call_parser": "declared-test-parser", "reasoning_parser": "declared-test-reasoning-parser",
        "thinking_mode": "enabled", "enable_auto_tool_choice": True,
        "structured_output_backend": None, "generation_config_digest": "sha256:" + "c" * 64,
        "max_model_len": 32768, "max_output_tokens": 1024,
        "server_limits": {"max_concurrent_requests": 1}, "hardware_description": "controlled transport; no GPU",
        "evidence_refs": ["controlled-protocol-test"],
    }


def test_configured_qwen_native_pairing_omits_deepseek_reasoning_and_caps_output():
    async def exercise():
        bodies = []
        def handler(req):
            body = json.loads(req.content)
            bodies.append(body)
            assert body["model"] == "Qwen-test-alias" and body["max_tokens"] == 1024
            assert "thinking" not in body and "reasoning_effort" not in body
            if len(bodies) == 1:
                return httpx.Response(200, json={"model": "Qwen-test-alias", "usage": {"prompt_tokens": 6, "completion_tokens": 2, "total_tokens": 8,
                    "prompt_tokens_details": {"cached_tokens": 1}, "completion_tokens_details": {"reasoning_tokens": 0}}, "choices": [{"finish_reason": "stop", "message": {
                    "role": "assistant", "content": None, "reasoning_content": "private Qwen reasoning",
                    "tool_calls": [{"id": "qwen-original", "type": "function", "function": {"name": "t_search", "arguments": '{"query":"EBD"}'}}],
                }}]})
            assert "reasoning_content" not in body["messages"][-2]
            assert body["messages"][-1]["tool_call_id"] == "qwen-original"
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Qwen final\r\n"}}]})
        config = ProviderConfig("vllm", "Qwen-test-alias", "http://localhost:8000/v1", deployment_manifest=qwen_manifest())
        session = (await ProviderFactory.open(config, transport=httpx.MockTransport(handler))).unwrap()
        prepared = session.prepare(request(max_context_tokens=8192))
        assert prepared.audit["context_measurement"]["verified_tokenizer"] is False
        assert prepared.audit["deployment_manifest_ref"] == qwen_manifest()["manifest_ref"]
        first = await session.generate(prepared)
        assert first.completion == "tool_calls" and first.native_finish_reason == "stop"
        assert first.usage["input_tokens"] == 6 and first.usage["total_tokens"] == 8
        assert first.usage["cached_input_tokens"] == 1 and first.usage["reasoning_output_tokens"] == 0
        second = await session.generate(request(continuation=first.continuation, step_index=1, tool_results=({"provider_call_id": "qwen-original", "status": "succeeded", "result": []},)))
        assert second.raw_visible_text == "Qwen final\r\n" and len(bodies) == 2
        with pytest.raises(EngineError) as caught:
            session.prepare(request(max_context_tokens=1))
        assert caught.value.code == "CONTEXT_LIMIT_EXCEEDED"
        assert caught.value.details["measurement"] == "utf8_byte_estimate"
        await session.aclose()
    run(exercise())


@pytest.mark.parametrize("change", [
    {"endpoint_id": "different-endpoint"}, {"chat_template_sha256": "unverified"},
    {"enable_auto_tool_choice": "true"}, {"max_output_tokens": 32768},
    {"manifest_ref": {"name": "mutable"}}, {"evidence_refs": []},
])
def test_qwen_manifest_rejects_unverifiable_local_declarations(change):
    config = ProviderConfig("vllm", "Qwen-test-alias", "http://localhost:8000/v1", deployment_manifest={**qwen_manifest(), **change})
    assert isinstance(run(ProviderFactory.open(config)), Err)
