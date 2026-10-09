"""Preserve bounded native failure reasons without exposing response messages."""
import httpx
import pytest

from deepresearch.engine.providers import ModelRequest, ProviderConfig, ProviderFactory


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason,error_code", [
    ("incomplete", "max_output_tokens", None),
    ("incomplete", "content_filter", None),
    ("incomplete", None, None),
    ("failed", None, "server_error"),
    ("failed", None, "rate_limit_exceeded"),
])
async def test_responses_failure_reason_survives_sanitized_error(status, reason, error_code):
    def respond(request):
        return httpx.Response(200, json={"id": "r1", "status": status,
            "incomplete_details": {"reason": reason},
            "error": {"code": error_code, "message": "private-provider-message"},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "partial"}]}]})
    session = (await ProviderFactory.open(ProviderConfig("openai", "gpt-6-luna", "https://provider.invalid", "test"),
        transport=httpx.MockTransport(respond))).unwrap()
    try:
        result = await session.generate(ModelRequest("Instructions", {}, (), "run", "a" * 64))
        assert result.completion == "incomplete"
        assert result.error.details["provider_status"] == status
        assert result.error.details["provider_incomplete_reason"] == reason
        assert result.error.details["incomplete_details_capture"] == ("known_reason" if reason else "absent")
        assert result.error.details["provider_error_code"] == error_code
        assert result.error.details["visible_text_bytes"] == 7
        assert result.error.details["native_tool_call_count"] == 0
        assert result.error.details["continuation_limit_exceeded"] is False
        assert "private-provider-message" not in str(result.error.to_dict())
    finally:
        await session.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("details,error", [
    ({"reason": "untrusted-secret"}, {"code": "untrusted-secret", "type": "untrusted-secret"}),
    (["untrusted-secret"], "untrusted-secret"),
    ({"reason": ["untrusted-secret"]}, {"code": {"private": "untrusted-secret"}}),
])
async def test_native_failure_diagnostic_does_not_copy_unbounded_or_unknown_values(details, error):
    def respond(request):
        return httpx.Response(200, json={"status": "incomplete", "output": [],
            "incomplete_details": details, "error": error})
    session = (await ProviderFactory.open(ProviderConfig("openai", "gpt-6-luna", "https://provider.invalid", "test"),
        transport=httpx.MockTransport(respond))).unwrap()
    try:
        result = await session.generate(ModelRequest("Instructions", {}, (), "run", "a" * 64))
        assert result.error.code == "provider.incomplete"
        assert result.error.details["provider_incomplete_reason"] is None
        assert result.error.details["incomplete_details_capture"] == "unsupported"
        assert result.error.details["provider_error_code"] is None
        assert "untrusted-secret" not in str(result.error.to_dict())
    finally:
        await session.aclose()
