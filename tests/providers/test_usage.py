"""Token accounting remains observable when native response content fails."""
import asyncio
import json

import httpx
import pytest

from ebd.providers import ModelRequest, ModelTool, ProviderConfig, ProviderFactory
from ebd.providers.usage import TOKEN_COUNTS, normalize_usage, provider_usage_projection


@pytest.mark.parametrize("native,expected,quality", [
    (None, (None, None, None, None, None, None), "unknown"),
    ({}, (None, None, None, None, None, None), "unknown"),
    ({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, (0, 0, 0, None, None, None), "complete"),
    ({"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16, "prompt_cache_hit_tokens": 8, "prompt_cache_miss_tokens": 4}, (12, 4, 16, 8, None, 4), "complete"),
    ({"input_tokens": 12, "output_tokens": 4, "total_tokens": 16, "input_tokens_details": {"cached_tokens": 3}, "output_tokens_details": {"reasoning_tokens": 2}}, (12, 4, 16, 3, 2, None), "complete"),
    ({"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16, "prompt_tokens_details": {"cached_tokens": 0}, "completion_tokens_details": {"reasoning_tokens": 0}}, (12, 4, 16, 0, 0, None), "complete"),
    ({"input_tokens": 12, "output_tokens": 4}, (12, 4, None, None, None, None), "partial"),
    ({"input_tokens": False, "output_tokens": -1, "total_tokens": "0"}, (None, None, None, None, None, None), "unknown"),
    ({"input_tokens": 2.0, "output_tokens": 0, "total_tokens": None}, (None, 0, None, None, None, None), "partial"),
    ({"input_tokens": 12, "output_tokens": 4, "total_tokens": 16, "input_tokens_details": {"cached_tokens": True}, "output_tokens_details": "bad"}, (12, 4, 16, None, None, None), "complete"),
    ({"completeness": "complete", "input_tokens": -3, "output_tokens": 0, "total_tokens": 0}, (None, 0, 0, None, None, None), "partial"),
])
def test_nullable_normalization_preserves_zero_and_never_infers_counts(native, expected, quality):
    usage = normalize_usage(native)
    assert tuple(usage[key] for key in TOKEN_COUNTS) == expected
    assert usage["completeness"] == quality and usage["source"] == "provider" and usage["measurement_ref"] is None


def test_numeric_projection_reports_conflicts_and_invalid_fields_without_raw_values():
    native = {"input_tokens": 60, "prompt_tokens": 50, "output_tokens": 12, "total_tokens": 62,
              "prompt_cache_miss_tokens": 30, "output_tokens_details": {"reasoning_tokens": 0, "accepted_prediction_tokens": 5, "private": "secret"},
              "input_tokens_details": {"cached_tokens": False}, "message": "private-token-metadata"}
    projected = provider_usage_projection(native)
    assert projected["conflicting_aliases"] == [["input_tokens", "prompt_tokens"]]
    assert projected["invalid_fields"] == ["input_tokens_details.cached_tokens"]
    assert projected["fields"]["prompt_cache_miss_tokens"] == 30
    assert projected["fields"]["output_tokens_details"] == {"reasoning_tokens": 0, "accepted_prediction_tokens": 5}
    assert "private" not in json.dumps(projected)
    # Do not replace either provider figure with a made-up reconciliation.
    assert normalize_usage(native)["input_tokens"] == 60 and normalize_usage(native)["total_tokens"] == 62


TOOL = ModelTool("web.search", "1", "registered_search", "Search", {"type": "object"})


async def response(body, *, provider="deepseek", status=200, request_options=None):
    config = ProviderConfig(provider, "gpt-6-luna" if provider == "openai" else "deepseek-flash", "https://provider.invalid", "controlled-secret")
    session = (await ProviderFactory.open(config, transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body)))).unwrap()
    try:
        return await session.generate(ModelRequest("Approved functions only", "task", (TOOL,), "run", "definition", **(request_options or {})))
    finally:
        await session.aclose()


USAGE = {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16, "prompt_cache_hit_tokens": 8, "prompt_cache_miss_tokens": 4,
         "completion_tokens_details": {"reasoning_tokens": 2}}


@pytest.mark.parametrize("content", [
    {"choices": [{"finish_reason": "unsupported", "message": {"role": "assistant", "content": "candidate"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": ["malformed"]}}]},
    {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "tool_calls": [
        {"id": "duplicate", "type": "function", "function": {"name": "registered_search", "arguments": "{}"}},
        {"id": "duplicate", "type": "function", "function": {"name": "registered_search", "arguments": "{}"}},
    ]}}]},
])
def test_malformed_native_content_keeps_usage_and_safe_response_identity(content):
    result = asyncio.run(response({**content, "id": "native-response", "model": "deepseek-flash", "usage": USAGE}))
    assert result.completion == "failed" and result.error.code == "provider.protocol"
    assert result.usage["total_tokens"] == 16 and result.usage["uncached_input_tokens"] == 4
    assert result.usage["reasoning_output_tokens"] == 2 and result.usage["completeness"] == "complete"
    assert result.provider_response_id == "native-response" and result.reported_model_id == "deepseek-flash"
    assert result.provider_usage["fields"]["prompt_cache_miss_tokens"] == 4


@pytest.mark.parametrize("status,outputs,completion", [
    ("completed", [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}], "refused"),
    ("incomplete", [{"type": "message", "content": [{"type": "output_text", "text": "partial"}]}], "incomplete"),
    ("completed", [{"type": "unsupported"}], "failed"),
])
def test_responses_usage_survives_refusal_incomplete_and_content_protocol_failure(status, outputs, completion):
    result = asyncio.run(response({"status": status, "output": outputs,
        "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10,
                  "input_tokens_details": {"cached_tokens": 2}, "output_tokens_details": {"reasoning_tokens": 1}}}, provider="openai"))
    assert result.completion == completion
    assert tuple(result.usage[key] for key in TOKEN_COUNTS) == (7, 3, 10, 2, 1, None)


def test_continuation_overflow_keeps_successfully_received_usage():
    result = asyncio.run(response({"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "answer"}}], "usage": USAGE},
                                 request_options={"max_continuation_bytes": 1}))
    assert result.completion == "incomplete" and result.continuation is None and result.usage["total_tokens"] == 16


@pytest.mark.parametrize("nested", [False, True])
def test_http_failure_keeps_partial_usage_without_error_message_or_other_fields(nested):
    body = {"error": {"code": "server_error", "message": "controlled-secret must not leak"}}
    (body["error"] if nested else body)["usage"] = {"input_tokens": 9, "output_tokens": None, "total_tokens": "invalid", "request_secret": "controlled-secret"}
    result = asyncio.run(response(body, provider="openai", status=500))
    assert result.completion == "failed" and result.usage["input_tokens"] == 9
    assert result.usage["total_tokens"] is None and result.usage["completeness"] == "partial"
    assert "controlled-secret" not in json.dumps(result.request_audit) + str(result.error) + json.dumps(result.provider_usage)


def test_invalid_json_and_transport_failure_have_explicit_unknown_usage():
    async def exercise():
        for handler in (lambda req: httpx.Response(200, content=b"invalid-json"), lambda req: (_ for _ in ()).throw(httpx.ReadError("controlled-secret", request=req))):
            session = (await ProviderFactory.open(ProviderConfig("deepseek", "deepseek-flash", "https://provider.invalid", "controlled-secret"), transport=httpx.MockTransport(handler))).unwrap()
            result = await session.generate(ModelRequest("policy", "task", (), "run", "definition"))
            assert result.usage["completeness"] == "unknown" and all(result.usage[key] is None for key in TOKEN_COUNTS)
            await session.aclose()
    asyncio.run(exercise())
