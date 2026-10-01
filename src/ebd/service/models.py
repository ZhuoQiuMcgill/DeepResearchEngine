"""Closed, versioned HTTP requests. These records never carry live authority."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class ToolSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=128)
    revision: int = Field(default=1, ge=1)


class InvocationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    agent_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(default=1, ge=1)
    allowed_tools: list[str] = Field(default_factory=list, max_length=32)
    allow_model: bool = True
    allow_export: bool = False
    allow_onward: bool = False
    max_depth: int = Field(default=4, ge=1, le=32)
    timeout_seconds: float = Field(default=180, gt=0, le=1800)
    limits: dict[str, int] = Field(default_factory=dict, max_length=32)


class RegisterAgentRequest(RequestModel):
    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    revision: int = Field(default=1, ge=1)
    instructions: str = Field(min_length=1, max_length=65536)
    profile_ref: str = Field(default="deepseek", min_length=1, max_length=128)
    model_ref: str = Field(default="deepseek-flash", min_length=1, max_length=128)
    allowed_tools: list[ToolSelection] = Field(default_factory=list, max_length=32)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "string"})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "string"})
    output_mode: Literal["text", "json"] = "text"
    output_media_type: str = Field(default="text/markdown", min_length=1, max_length=128)
    limits: dict[str, int | float] = Field(default_factory=dict, max_length=64)
    invocation_rules: list[InvocationSelection] = Field(default_factory=list, max_length=32)


class StartRunRequest(RequestModel):
    agent_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(default=1, ge=1)
    input: Any
    timeout_seconds: float = Field(default=600, gt=0, le=1800)
    limits: dict[str, int] = Field(default_factory=dict, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=32)


class ResponseModel(BaseModel):
    """Versioned envelopes permit additive response fields within v1."""
    model_config = ConfigDict(extra="allow")
    schema_version: Literal[1] = 1


class RunReference(ResponseModel):
    store_id: str
    run_id: str


class ArtifactReference(ResponseModel):
    store_id: str
    artifact_id: str


class SnapshotReference(ResponseModel):
    store_id: str
    snapshot_id: str


class CheckpointReference(ResponseModel):
    store_id: str
    checkpoint_id: str


class ScopeReference(BaseModel):
    kind: Literal["run", "shared"]
    id: str


class AgentReference(BaseModel):
    agent_id: str
    revision: int = Field(ge=1)


class EventReceiptView(ResponseModel):
    store_id: str
    event_id: str
    recorded_seq: int = Field(ge=1)
    recorded_at: str
    duplicate: bool = False


class EngineErrorView(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    observed_effect_state: str = "not_observed"
    commit_state: str = "not_applicable"
    retryable_delivery: bool = False


class RunView(ResponseModel):
    """Public status separates execution, recording and service ownership."""
    run_id: str
    run_ref: RunReference
    status: str
    active: bool
    recording_status: str
    terminal_event_receipt: EventReceiptView | None = None
    accepted_at: str | None = None
    agent_ref: AgentReference | None = None
    cancellation_requested: bool | None = None
    cancellation_state: str | None = None
    automatic_resume: bool = False
    descriptor: dict[str, Any] | None = None
    context_kind: str | None = None
    terminal_kind: str | None = None


class TokenCounts(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    uncached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)


class AttemptUsageReference(BaseModel):
    store_id: str
    event_id: str
    action_id: str
    attempt_id: str


class UsageAggregate(BaseModel):
    model_config = ConfigDict(extra="allow")
    known_subtotals: TokenCounts
    completeness: Literal["complete", "partial", "unknown"]
    unknown_attempt_ids: list[str]
    per_attempt_usage_refs: list[AttemptUsageReference]


class ResultView(RunView):
    available: bool
    output_ref: ArtifactReference | None = None
    raw_output_ref: ArtifactReference | None = None
    start_state: str | None = None
    persistence_state: str | None = None
    output_publications: list[dict[str, Any]] | None = None
    validation: dict[str, Any] | None = None
    counters: dict[str, int | float] | None = None
    usage: UsageAggregate | None = None
    error: EngineErrorView | None = None
    cleanup: dict[str, Any] | None = None
    reason: str | None = None
    tool: dict[str, Any] | None = None
    dispatched: bool | None = None
    result_descriptor: dict[str, Any] | None = None
    persistence: dict[str, Any] | None = None
    process: dict[str, Any] | None = None
    observations: dict[str, Any] | None = None


class UsageView(ResponseModel):
    run_id: str
    status: str
    available: bool
    usage: UsageAggregate | None
    counters: dict[str, int | float] | None
    terminal_event_receipt: EventReceiptView | None
    observations_endpoint: str


class ExecutionEventView(ResponseModel):
    event_id: str
    kind: str
    producer: str
    context: dict[str, Any]
    payload: dict[str, Any]
    producer_timestamp: str


class RecordedEventView(BaseModel):
    event: ExecutionEventView
    receipt: EventReceiptView


class EventPageView(ResponseModel):
    events: list[RecordedEventView]
    next_after_seq: int = Field(ge=0)
    high_water_seq: int = Field(ge=0)
    has_more: bool


class ObjectDescriptorView(ResponseModel):
    kind: Literal["artifact", "snapshot", "checkpoint"]
    ref: ArtifactReference | SnapshotReference | CheckpointReference
    scope: ScopeReference
    byte_length: int = Field(ge=0)
    media_type: str
    sha256: str
    extraction_version: str | None = None
    normalization_version: str | None = None
    line_count: int | None = Field(default=None, ge=0)
    physical_page_count: int | None = Field(default=None, ge=0)
    format: str | None = None
    run_id: str | None = None


class ObjectPageView(ResponseModel):
    objects: list[ObjectDescriptorView]
    cursor: str | None


class ArtifactChunkView(ResponseModel):
    run_id: str
    artifact_ref: ArtifactReference
    encoding: Literal["base64"]
    data: str
    start: int = Field(ge=0)
    next_offset: int = Field(ge=0)
    eof: bool
    byte_length: int = Field(ge=0)
    media_type: str | None
    sha256: str | None


class StateView(ResponseModel):
    present: bool
    version: int = Field(ge=0)
    value: Any = None
    commit_event_id: str | None = None


class HealthView(ResponseModel):
    ready: bool
    store_id: str
    active_runs: int = Field(ge=0)
    single_owner: Literal[True]
    automatic_resume: Literal[False]


class AgentCatalogItem(BaseModel):
    ref: AgentReference
    definition_ref: dict[str, Any]
    definition: dict[str, Any]
    invocation_rules: list[dict[str, Any]]


class AgentCatalogView(ResponseModel):
    agents: list[AgentCatalogItem]


class RegisteredAgentView(ResponseModel):
    agent_ref: AgentReference
    definition_ref: dict[str, Any]


class ProfileView(BaseModel):
    profile_ref: str
    model_ref: str
    provider: str


class ProfileCatalogView(ResponseModel):
    profiles: list[ProfileView]


class ToolView(ResponseModel):
    name: str
    revision: int
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capabilities: list[str]
    limits: dict[str, Any]


class ToolCatalogView(ResponseModel):
    tools: list[ToolView]


class RunPageView(ResponseModel):
    runs: list[RunView]
    cursor: str | None


class ErrorView(ResponseModel):
    error: EngineErrorView
