"""Bounded nonstreaming HTTP connectors, with no automatic external retries."""
from __future__ import annotations

import asyncio
import copy
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

import httpx

from ebd.contracts import EngineError, Err, Ok, canonical_json, digest_bytes, digest_json, strict_json_loads
from .models import (
    ModelCall, ModelRequest, ModelResponse, NativeContinuation, PLATFORM_SEARCH_POLICY,
    PreparedRequest, ProviderConfig,
)


def _bytes(value: Any) -> bytes:
    result = canonical_json(value)
    return result if isinstance(result, bytes) else result.encode("utf-8")


def _error(code: str, message: str, **details: Any) -> EngineError:
    return EngineError(code=code, message=message, details=details, observed_effect_state=details.get("effect_state", "not_observed"))


def _safe_id(value: Any) -> str | None:
    return value if isinstance(value, str) and len(value) <= 256 and value.isprintable() else None


PROVIDER_ERROR_ENUMS = frozenset({
    "insufficient_quota", "rate_limit_exceeded", "invalid_api_key",
    "model_not_found", "context_length_exceeded", "billing_not_active",
    "permission_denied", "invalid_request_error", "server_error",
    "unsupported_country_region_territory", "requests", "tokens",
})


def _retry_after(value: str | None) -> float | None:
    if value is None or len(value) > 128:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value).astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return seconds if math.isfinite(seconds) and 0 <= seconds <= 86400 else None


async def _http_error_facts(response) -> dict[str, Any]:
    """Observe allowlisted enums only; messages and other headers never escape."""
    facts = {"provider_error_code": None, "provider_error_type": None,
             "error_capture_state": "unknown", "retry_after_seconds": _retry_after(response.headers.get("retry-after"))}
    retained = bytearray()
    async for chunk in response.aiter_bytes():
        if len(retained) + len(chunk) > 16384:
            facts["error_capture_state"] = "oversize"
            return facts
        retained.extend(chunk)
    try:
        value = strict_json_loads(bytes(retained), max_bytes=16384, max_depth=8)
        error = value.get("error") if isinstance(value, dict) else None
        if isinstance(error, dict):
            for field in ("code", "type"):
                item = error.get(field)
                if isinstance(item, str) and item in PROVIDER_ERROR_ENUMS:
                    facts["provider_error_" + field] = item
            facts["error_capture_state"] = "parsed_allowlist"
        else:
            facts["error_capture_state"] = "unsupported_shape"
    except (ValueError, TypeError):
        facts["error_capture_state"] = "invalid_json"
    return facts


def _usage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    def count(*keys):
        for key in keys:
            item = value.get(key)
            if type(item) is int and item >= 0:
                return item
        return None
    input_tokens = count("input_tokens", "prompt_tokens")
    output_tokens = count("output_tokens", "completion_tokens")
    total_tokens = count("total_tokens")
    breakdown = value.get("output_tokens_details") or value.get("completion_tokens_details") or {}
    reasoning = breakdown.get("reasoning_tokens") if isinstance(breakdown, dict) else None
    if type(reasoning) is not int or reasoning < 0:
        reasoning = None
    input_details = value.get("input_tokens_details") or value.get("prompt_tokens_details") or {}
    cached = input_details.get("cached_tokens") if isinstance(input_details, dict) else None
    if type(cached) is not int or cached < 0:
        cached = count("prompt_cache_hit_tokens")
    return {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached,
        "reasoning_output_tokens": reasoning,
        "completeness": "complete" if None not in (input_tokens, output_tokens, total_tokens) else "partial",
        "source": "provider", "measurement_ref": None,
    }


class ProviderFactory:
    """Opening a connector performs local validation only; generate is the dispatch."""

    @staticmethod
    def capabilities(config: ProviderConfig) -> frozenset[str]:
        return frozenset({"function_tools", "text", "json", "native_continuation"})

    @staticmethod
    async def open(config: ProviderConfig, context: Any = None, *, transport=None):
        try:
            _validate_config(config)
            if context is not None:
                context.assert_active()
            return Ok(ProviderSession(config, transport=transport))
        except (ValueError, TypeError) as exc:
            return Err(_error("provider.configuration", str(exc)))


def _validate_config(config: ProviderConfig) -> None:
    if config.provider not in {"deepseek", "openai", "vllm"}:
        raise ValueError("Unsupported provider kind")
    if not config.model_id or not isinstance(config.settings, dict):
        raise ValueError("Model and closed settings are required")
    parsed = urlsplit(config.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Provider endpoint must be a plain HTTP(S) base URL")
    if config.provider != "vllm" and (parsed.scheme != "https" or not config.api_key):
        raise ValueError("API provider requires HTTPS and a configured credential")
    allowed = {
        "openai": {"reasoning_effort", "max_output_tokens", "tool_choice"},
        "deepseek": {"thinking", "reasoning_effort", "max_tokens", "temperature", "top_p", "tool_choice"},
        "vllm": {"max_tokens", "temperature", "top_p", "tool_choice"},
    }[config.provider]
    if set(config.settings) - allowed:
        raise ValueError("Unknown provider settings are rejected")
    for key in ("max_output_tokens", "max_tokens"):
        if key in config.settings and (type(config.settings[key]) is not int or config.settings[key] <= 0):
            raise ValueError("Output token settings must be positive integers")
    for key, maximum in (("temperature", 2), ("top_p", 1)):
        if key in config.settings:
            value = config.settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError("Sampling setting is outside the documented numeric range")
    if config.settings.get("tool_choice", "auto") not in {"auto", "none", "required"}:
        raise ValueError("Unsupported tool-choice setting")
    if config.provider == "openai" and config.settings.get("reasoning_effort", "low") not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("Unsupported OpenAI reasoning effort")
    if config.provider == "deepseek":
        thinking = config.settings.get("thinking", "disabled")
        if thinking not in {"enabled", "disabled"}:
            raise ValueError("DeepSeek thinking must be enabled or disabled")
        if thinking == "enabled" and set(config.settings) & {"temperature", "top_p"}:
            raise ValueError("Sampling settings are ineffective in DeepSeek thinking mode")
        if config.settings.get("reasoning_effort", "high") not in {"low", "high", "max"}:
            raise ValueError("Unsupported DeepSeek reasoning effort")
        if thinking == "enabled" and config.settings.get("tool_choice", "auto") != "auto":
            raise ValueError("DeepSeek thinking tools require automatic tool choice")
    if config.provider == "vllm":
        manifest = config.deployment_manifest
        required = {"schema_version", "manifest_ref", "endpoint_id", "served_model_id", "model_repository", "model_revision", "tokenizer_repository", "tokenizer_revision", "chat_template_sha256", "vllm_version", "server_image_digest", "tool_call_parser", "reasoning_parser", "thinking_mode", "enable_auto_tool_choice", "structured_output_backend", "generation_config_digest", "max_model_len", "max_output_tokens", "server_limits", "hardware_description", "evidence_refs"}
        if not isinstance(manifest, dict) or set(manifest) != required:
            raise ValueError("vLLM requires a complete explicit deployment manifest")
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["served_model_id"] != config.model_id or manifest["endpoint_id"] != config.endpoint_id:
            raise ValueError("vLLM deployment manifest/model mismatch")
        if manifest["enable_auto_tool_choice"] is not True or not manifest["tool_call_parser"]:
            raise ValueError("vLLM function tools require a declared enabled parser")
        for key in ("endpoint_id", "served_model_id", "model_repository", "model_revision", "tokenizer_repository", "tokenizer_revision", "vllm_version", "tool_call_parser", "thinking_mode", "hardware_description"):
            if not isinstance(manifest[key], str) or not manifest[key] or len(manifest[key]) > 4096:
                raise ValueError("vLLM deployment identity fields must be bounded nonempty strings")
        for key in ("reasoning_parser", "structured_output_backend"):
            if manifest[key] is not None and (not isinstance(manifest[key], str) or not manifest[key] or len(manifest[key]) > 256):
                raise ValueError("vLLM optional parser/backend fields must be null or bounded names")
        for key in ("chat_template_sha256", "server_image_digest", "generation_config_digest"):
            if not isinstance(manifest[key], str) or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", manifest[key]) is None:
                raise ValueError("vLLM deployment hashes must be explicit SHA-256 digests")
        for key in ("max_model_len", "max_output_tokens"):
            if type(manifest[key]) is not int or manifest[key] <= 0:
                raise ValueError("vLLM deployment token ceilings must be positive integers")
        if manifest["max_output_tokens"] >= manifest["max_model_len"]:
            raise ValueError("vLLM output ceiling must leave room for input context")
        ref = manifest["manifest_ref"]
        if not isinstance(ref, dict) or set(ref) != {"name", "revision"} or not isinstance(ref["name"], str) or not ref["name"] or isinstance(ref["revision"], bool) or not isinstance(ref["revision"], (str, int)) or not str(ref["revision"]):
            raise ValueError("vLLM manifest requires its immutable named revision")
        if not isinstance(manifest["server_limits"], dict) or not isinstance(manifest["evidence_refs"], list) or not manifest["evidence_refs"]:
            raise ValueError("vLLM deployment requires server bounds and evidence references")
        if any(not isinstance(ref, (str, dict)) or not ref for ref in manifest["evidence_refs"]):
            raise ValueError("vLLM evidence references must be nonempty references")
        canonical_json(manifest, max_bytes=65536)


class ProviderSession:
    def __init__(self, config: ProviderConfig, *, transport=None):
        self.config = config
        self.client = httpx.AsyncClient(
            transport=transport if transport is not None else httpx.AsyncHTTPTransport(retries=0),
            follow_redirects=False, trust_env=False, timeout=None,
        )
        self.closed = False

    def prepare(self, request: ModelRequest, context: Any = None) -> PreparedRequest:
        if self.closed:
            raise ValueError("Provider session is closed")
        if context is not None:
            context.assert_active()
        config = replace(self.config, settings={**self.config.settings, **request.settings})
        _validate_config(config)
        if request.max_output_tokens <= 0 or request.max_seconds <= 0:
            raise ValueError("Model dispatch requires positive finite bounds")
        names = [tool.provider_name for tool in request.tools]
        if len(set(names)) != len(names):
            raise ValueError("Provider function names must be unique")
        continuation = request.continuation
        if continuation is not None:
            expected = (config.provider, config.model_id, config.profile_name, request.run_id, request.definition_digest)
            actual = (continuation.provider, continuation.model_id, continuation.profile_name, continuation.run_id, continuation.definition_digest)
            if actual != expected or continuation.codec_revision != "1":
                raise ValueError("Native continuation does not match the bound run/profile")
            result_ids = [result.get("provider_call_id") for result in request.tool_results]
            if result_ids != list(continuation.pending_call_ids) or len(set(result_ids)) != len(result_ids):
                raise ValueError("Every native call requires exactly one ordered correlated result")
        elif request.tool_results:
            raise ValueError("Tool results require native continuation")
        body = self._render(request, config)
        encoded = _bytes(body)
        if len(encoded) > request.max_request_bytes:
            raise ValueError("Rendered request exceeds its byte allowance")
        # This is deliberately an estimate, not a verified tokenizer count. It
        # includes native history, supplied context and function schemas. The
        # real byte bound remains independently enforced above.
        context_value = ({"instructions": body["instructions"], "input": body["input"], "tools": body.get("tools", [])}
                         if config.provider == "openai" else {"messages": body["messages"], "tools": body.get("tools", [])})
        context_estimate = len(_bytes(context_value))
        context_ceiling = request.max_context_tokens
        if config.provider == "vllm":
            server_ceiling = config.deployment_manifest["max_model_len"] - body["max_tokens"]
            context_ceiling = min(context_ceiling, server_ceiling) if context_ceiling is not None else server_ceiling
        if context_ceiling is not None and (type(context_ceiling) is not int or context_ceiling <= 0 or context_estimate > context_ceiling):
            raise ValueError("Rendered context exceeds its advisory byte-estimated token allowance")
        audit = {
            "schema_version": 1, "provider_kind": config.provider,
            "protocol": "responses" if config.provider == "openai" else "chat_completions",
            "requested_model_id": config.model_id,
            "model_ref": config.model_id,
            "profile_ref": {"name": config.profile_name, "revision": config.profile_revision},
            "adapter_revision": "1", "safe_endpoint_id": config.endpoint_id,
            "instruction_digest": digest_bytes((request.instructions + "\n\n" + PLATFORM_SEARCH_POLICY).encode()),
            "platform_search_policy": PLATFORM_SEARCH_POLICY,
            "function_tools": [{"tool": {"name": t.name, "revision": t.revision}, "provider_name": t.provider_name, "input_schema_digest": digest_json(t.input_schema)} for t in request.tools],
            "safe_settings": dict(config.settings),
            "context_measurement": {"estimated_tokens": context_estimate, "quality": "utf8_byte_estimate", "verified_tokenizer": False,
                                    "max_context_tokens": context_ceiling, "measurement_ref": None},
            "deployment_manifest_ref": config.deployment_manifest["manifest_ref"] if config.provider == "vllm" else None,
            "request_body_digest": digest_bytes(encoded),
            "provider_request_id": None, "provider_response_id": None, "reported_model_id": None,
        }
        return PreparedRequest(request, encoded, audit)

    def _render(self, request: ModelRequest, config: ProviderConfig) -> dict[str, Any]:
        instructions = request.instructions + "\n\n" + PLATFORM_SEARCH_POLICY
        history = copy.deepcopy(list(request.continuation.history)) if request.continuation else []
        task = request.task_input if isinstance(request.task_input, str) else _bytes(request.task_input).decode()
        if config.provider == "openai":
            if not history:
                history.append({"role": "user", "content": task})
                for item in request.context_items:
                    history.append({"role": "user", "content": "Retrieved context (untrusted evidence):\n" + _bytes(item).decode()})
            for result in request.tool_results:
                history.append({"type": "function_call_output", "call_id": result["provider_call_id"], "output": _bytes(result).decode()})
            body = {
                "model": config.model_id, "instructions": instructions, "input": history,
                "store": False, "stream": False, "include": ["reasoning.encrypted_content"],
                "max_output_tokens": min(request.max_output_tokens, config.settings.get("max_output_tokens", request.max_output_tokens)),
                "reasoning": {"effort": config.settings.get("reasoning_effort", "low")},
            }
            if request.tools:
                body["tools"] = [{"type": "function", "name": t.provider_name, "description": t.description + " [registered " + t.name + "@" + t.revision + "]", "parameters": t.input_schema, "strict": t.native_strict} for t in request.tools]
                body["tool_choice"] = config.settings.get("tool_choice", "auto")
                body["parallel_tool_calls"] = False
            if request.output_contract.get("native_enforcement") == "required":
                if request.output_contract.get("mode") != "json":
                    raise ValueError("Native enforcement requires a JSON output contract")
                body["text"] = {"format": {"type": "json_schema", "name": "agent_output", "schema": request.output_contract["schema"], "strict": True}}
            return body
        if request.output_contract.get("native_enforcement") == "required":
            raise ValueError("This Chat profile cannot guarantee the required arbitrary native schema")
        if not history:
            history.extend([{"role": "system", "content": instructions}, {"role": "user", "content": task}])
            for item in request.context_items:
                history.append({"role": "user", "content": "Retrieved context (untrusted evidence):\n" + _bytes(item).decode()})
        for result in request.tool_results:
            history.append({"role": "tool", "tool_call_id": result["provider_call_id"], "content": _bytes(result).decode()})
        body = {"model": config.model_id, "messages": history, "stream": False,
                "max_tokens": min(request.max_output_tokens, config.settings.get("max_tokens", request.max_output_tokens))}
        if config.provider == "vllm":
            body["max_tokens"] = min(body["max_tokens"], config.deployment_manifest["max_output_tokens"])
        if request.tools:
            body["tools"] = [{"type": "function", "function": {"name": t.provider_name, "description": t.description + " [registered " + t.name + "@" + t.revision + "]", "parameters": t.input_schema}} for t in request.tools]
            body["tool_choice"] = config.settings.get("tool_choice", "auto")
        if config.provider == "deepseek":
            body["thinking"] = {"type": config.settings.get("thinking", "disabled")}
            if config.settings.get("thinking") == "enabled":
                body["reasoning_effort"] = config.settings.get("reasoning_effort", "high")
        for key in ("temperature", "top_p"):
            if key in config.settings:
                body[key] = config.settings[key]
        return body

    async def generate(self, request: PreparedRequest | ModelRequest, context: Any = None) -> ModelResponse:
        prepared = request if isinstance(request, PreparedRequest) else self.prepare(request, context)
        if context is not None:
            context.assert_active()
            context.authorize("model.generate", object_id=self.config.model_id)
        endpoint = "responses" if self.config.provider == "openai" else "chat/completions"
        url = self.config.base_url.rstrip("/") + "/" + endpoint
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        timeout = prepared.request.max_seconds
        if context is not None and hasattr(context, "remaining_seconds"):
            timeout = min(timeout, context.remaining_seconds())
        try:
            async with asyncio.timeout(timeout):
                async with self.client.stream("POST", url, content=prepared.body_bytes, headers=headers) as response:
                    request_id = _safe_id(response.headers.get("x-request-id"))
                    if response.status_code != 200:
                        facts = await _http_error_facts(response)
                        return ModelResponse("failed", request_audit=prepared.audit, provider_request_id=request_id, error=_error("provider.http", "Provider returned a non-success response", http_status=response.status_code, effect_state="observed", **facts), dispatched=True)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > prepared.request.max_response_bytes:
                            return ModelResponse("incomplete", request_audit=prepared.audit, provider_request_id=request_id, error=_error("provider.response_oversize", "Provider response exceeds its byte allowance", effect_state="observed"), dispatched=True)
                        data.extend(chunk)
                    try:
                        native = strict_json_loads(bytes(data))
                        result = self._parse(native, prepared, request_id)
                    except (ValueError, TypeError, KeyError, IndexError) as exc:
                        return ModelResponse("failed", request_audit=prepared.audit, provider_request_id=request_id, error=_error("provider.protocol", "Provider returned an invalid or unsupported native response", exception_type=type(exc).__name__, effect_state="observed"), dispatched=True)
                    return result
        except TimeoutError:
            return ModelResponse("incomplete", request_audit=prepared.audit, error=_error("provider.timeout", "Provider request deadline elapsed; remote completion is unknown", effect_state="unknown"), dispatched=True)
        except httpx.HTTPError as exc:
            return ModelResponse("failed", request_audit=prepared.audit, error=_error("provider.transport", "Provider transport failed; remote completion is unknown", exception_type=type(exc).__name__, effect_state="unknown"), dispatched=True)

    def _parse(self, native: dict[str, Any], prepared: PreparedRequest, request_id: str | None) -> ModelResponse:
        request = prepared.request
        body = strict_json_loads(prepared.body_bytes)
        names = {t.provider_name: t for t in request.tools}
        calls = []
        text = []
        refusal = False
        if self.config.provider == "openai":
            status = native.get("status")
            if status not in {"completed", "incomplete", "failed"}:
                raise ValueError("Unsupported Responses status")
            outputs = native.get("output", [])
            if not isinstance(outputs, list):
                raise ValueError("Invalid output items")
            for item in outputs:
                kind = item.get("type")
                if kind == "function_call":
                    calls.append((item["call_id"], item["name"], item["arguments"]))
                elif kind == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            text.append(part["text"])
                        elif part.get("type") == "refusal":
                            refusal = True
                        else:
                            raise ValueError("Unsupported message content")
                elif kind == "reasoning":
                    pass  # replay the complete native item, never expose native reasoning
                else:
                    raise ValueError("Unsupported native output item")
            history = body["input"] + outputs
            finish = status
            incomplete = status != "completed"
        else:
            choices = native["choices"]
            if len(choices) != 1:
                raise ValueError("Exactly one native choice is required")
            choice = choices[0]
            message = choice["message"]
            finish = choice["finish_reason"]
            if finish not in {"stop", "tool_calls", "length", "content_filter", "insufficient_system_resource"}:
                raise ValueError("Unsupported Chat finish reason")
            visible = message.get("content")
            if visible is not None:
                if not isinstance(visible, str):
                    raise ValueError("Unsupported visible content")
                text.append(visible)
            for call in message.get("tool_calls") or []:
                if call.get("type") != "function":
                    raise ValueError("Unsupported tool kind")
                calls.append((call["id"], call["function"]["name"], call["function"]["arguments"]))
            assistant = {key: copy.deepcopy(message[key]) for key in ("role", "content", "tool_calls") if key in message}
            assistant["role"] = "assistant"
            if self.config.provider == "deepseek" and "reasoning_content" in message:
                assistant["reasoning_content"] = message["reasoning_content"]
            history = body["messages"] + [assistant]
            refusal = finish == "content_filter" or bool(message.get("refusal"))
            incomplete = finish in {"length", "insufficient_system_resource"}
        parsed_calls = []
        ids = set()
        for index, (call_id, name, arguments_json) in enumerate(calls):
            if not _safe_id(call_id) or call_id in ids or not isinstance(arguments_json, str):
                raise ValueError("Invalid or duplicate native call ID")
            ids.add(call_id)
            tool = names.get(name)
            argument_error = None
            try:
                arguments = strict_json_loads(arguments_json)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be an object")
            except (ValueError, TypeError):
                arguments = None
                argument_error = _error("tool.invalid_arguments", "Native tool arguments are not strict JSON objects")
            if tool is None:
                argument_error = _error("tool.unauthorized", "Provider requested an unregistered function")
            parsed_calls.append(ModelCall(call_id, index, name, tool.name if tool else None, tool.revision if tool else None, arguments_json, arguments, argument_error))
        continuation_bytes = _bytes(history)
        if len(continuation_bytes) > request.max_continuation_bytes:
            incomplete = True
        completion = "refused" if refusal else "incomplete" if incomplete else "tool_calls" if parsed_calls else "final"
        continuation = NativeContinuation(self.config.provider, self.config.model_id, self.config.profile_name, request.run_id, request.definition_digest, tuple(history), tuple(c.provider_call_id for c in parsed_calls)) if not incomplete else None
        reported = _safe_id(native.get("model"))
        response_id = _safe_id(native.get("id"))
        audit = {**prepared.audit, "provider_request_id": request_id, "provider_response_id": response_id, "reported_model_id": reported}
        return ModelResponse(completion, "".join(text), tuple(parsed_calls) if completion == "tool_calls" else (), finish, _usage(native.get("usage")), continuation, audit, request_id, response_id, reported, _error("provider." + completion, "Provider did not return a complete callable/final response", effect_state="observed") if completion in {"refused", "incomplete"} else None, True)

    async def aclose(self):
        if not self.closed:
            await self.client.aclose()
            self.closed = True
        return {"state": "closed", "unconfirmed_resources": []}
