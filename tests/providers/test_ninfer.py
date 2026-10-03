import asyncio
import json

import httpx
import pytest

from deepresearch.engine.providers import ProviderConfig, ProviderFactory, ModelRequest, ModelTool
from deepresearch.engine.providers.factory import _validate_config
from deepresearch.engine.connections.config import local_profiles


def test_ninfer_native_tool_round_trip():
    async def exercise():
        bodies = []
        def handler(req):
            body = json.loads(req.content)
            bodies.append(body)
            assert body["chat_template_kwargs"] == {"enable_thinking": False}
            assert "thinking" not in body
            if len(bodies) == 1:
                return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "tool_calls": [{"id": "call1", "type": "function", "function": {"name": "t_fetch", "arguments": '{"url":"https://example.com"}'}}]}}]})
            assert body["messages"][-1]["tool_call_id"] == "call1"
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Final report"}}], "usage": {"prompt_tokens": 30, "completion_tokens": 4, "total_tokens": 34}})
        config = ProviderConfig("ninfer", "qwen38-ninfer-256k", "http://127.0.0.1:18086/v1")
        session = (await ProviderFactory.open(config, transport=httpx.MockTransport(handler))).unwrap()
        tool = ModelTool("web.fetch", "1", "t_fetch", "Fetch", {"type": "object"})
        def request(**kw):
            return ModelRequest("Use tools", "Read example.com", (tool,), "run1", "a" * 64, **kw)
        first = await session.generate(request())
        assert first.completion == "tool_calls"
        second = await session.generate(request(continuation=first.continuation, tool_results=({"provider_call_id": "call1", "status": "succeeded", "result": "Example Domain"},)))
        assert second.raw_visible_text == "Final report"
        assert second.usage["output_tokens"] == 4
        assert second.request_audit["provider_kind"] == "ninfer"
        await session.aclose()
    asyncio.run(exercise())


def test_ninfer_remote_endpoint_rejected():
    with pytest.raises(ValueError, match="loopback"):
        _validate_config(ProviderConfig("ninfer", "qwen", "http://remote.invalid/v1"))


def test_host_profile_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("NINFER_BASE_URL", raising=False)
    assert local_profiles(tmp_path) == {}
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / ".env").write_text("NINFER_BASE_URL=http://127.0.0.1:18086/v1\nNINFER_MODEL=qwen38-ninfer-256k\n")
    assert local_profiles(tmp_path)["ninfer"].provider == "ninfer"
