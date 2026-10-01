"""Provider-owned native exchange records; none of these carry authority."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PLATFORM_SEARCH_POLICY = (
    "Do not use internal, provider-hosted or implicit web search. "
    "Research only through registered platform function tools; "
    "fetch and read source evidence before citing it."
)


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model_id: str
    base_url: str
    api_key: str = field(default="", repr=False, compare=False, metadata={"secret": True})
    settings: dict[str, Any] = field(default_factory=dict)
    profile_name: str = "default"
    profile_revision: str = "1"
    endpoint_id: str = "configured-endpoint"
    deployment_manifest: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModelTool:
    name: str
    revision: str
    provider_name: str
    description: str
    input_schema: dict[str, Any]
    native_strict: bool = False


@dataclass(frozen=True)
class NativeContinuation:
    provider: str
    model_id: str
    profile_name: str
    run_id: str
    definition_digest: str
    history: tuple[dict[str, Any], ...]
    pending_call_ids: tuple[str, ...] = ()
    codec_revision: str = "1"


@dataclass(frozen=True)
class ModelRequest:
    instructions: str
    task_input: Any
    tools: tuple[ModelTool, ...]
    run_id: str
    definition_digest: str
    step_index: int = 0
    continuation: NativeContinuation | None = None
    tool_results: tuple[dict[str, Any], ...] = ()
    max_output_tokens: int = 4096
    max_request_bytes: int = 1048576
    max_response_bytes: int = 1048576
    max_continuation_bytes: int = 1048576
    max_seconds: float = 45
    settings: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    context_items: tuple[dict[str, Any], ...] = ()
    max_context_tokens: int | None = None


@dataclass(frozen=True)
class ModelCall:
    provider_call_id: str
    index: int
    provider_name: str
    name: str | None
    revision: str | None
    arguments_json: str
    arguments: dict[str, Any] | None
    argument_error: Any = None


@dataclass(frozen=True)
class PreparedRequest:
    request: ModelRequest
    body_bytes: bytes = field(repr=False)
    audit: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    completion: str
    raw_visible_text: str | None = None
    tool_calls: tuple[ModelCall, ...] = ()
    native_finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    continuation: NativeContinuation | None = field(default=None, repr=False)
    request_audit: dict[str, Any] | None = None
    provider_request_id: str | None = None
    provider_response_id: str | None = None
    reported_model_id: str | None = None
    error: Any = None
    dispatched: bool = False
