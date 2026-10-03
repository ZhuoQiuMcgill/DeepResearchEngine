"""Shared, authority-free workflow wire contracts; HTTP uses these same models."""
from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1

    def to_dict(self):
        return self.model_dump(mode="json")


def public_url(value: str) -> str:
    if len(value.encode("utf-8")) > 8192:
        raise ValueError("URL exceeds the UTF-8 bound")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Expected an absolute HTTP(S) URL without credentials")
    return value


class ResearchSnapshotReference(Contract):
    store_id: str = Field(min_length=1, max_length=128)
    snapshot_id: str = Field(min_length=1, max_length=128)


class ResearchArtifactReference(Contract):
    store_id: str = Field(min_length=1, max_length=128)
    artifact_id: str = Field(min_length=1, max_length=128)


# Python aliases retain the concise API without OpenAPI name collisions.
SnapshotReference = ResearchSnapshotReference
ArtifactReference = ResearchArtifactReference


class SourceRange(Contract):
    kind: Literal["lines", "pages"]
    start: int = Field(ge=1)
    end_exclusive: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_exclusive <= self.start or self.end_exclusive - self.start > (200 if self.kind == "lines" else 10):
            raise ValueError("Invalid or oversized source interval")
        return self

    def tool_range(self):
        return self.model_dump(exclude={"schema_version"})


class FetchItem(Contract):
    item_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    url: str = Field(min_length=1, max_length=8192)
    discovery_ref: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="Selected source", max_length=1024)
    _url = field_validator("url")(public_url)


class FetchManifest(Contract):
    items: list[FetchItem] = Field(max_length=32)

    @model_validator(mode="after")
    def unique_items(self):
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate fetch item identities")
        return self


class TokenMeasurement(Contract):
    model_ref: str = Field(min_length=1, max_length=128)
    tokenizer_id: str | None = Field(default=None, max_length=256)
    tokenizer_revision: str | None = Field(default=None, max_length=128)
    text_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rendering_revision: str = Field(default="source-text/1", max_length=128)
    kind: Literal["verified", "estimated", "unknown"]
    count: int | None = Field(default=None, ge=0)
    text_bytes: int = Field(ge=0)
    estimator: str | None = Field(default=None, max_length=128)
    scope: Literal["document", "selected", "assembled"] = "selected"

    @model_validator(mode="after")
    def count_identity(self):
        if self.kind == "verified" and (self.count is None or not self.tokenizer_id or not self.tokenizer_revision):
            raise ValueError("Verified measurement requires a pinned tokenizer and count")
        if self.kind == "estimated" and (self.count is None or not self.estimator):
            raise ValueError("Estimate requires a named estimator and count")
        if self.kind == "unknown" and self.count is not None:
            raise ValueError("Unknown measurement cannot claim a count")
        return self


class SourceRecord(Contract):
    item_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=8192)
    discovery_ref: str | None = Field(default=None, max_length=128)
    status: Literal["pending", "succeeded", "failed", "cancelled", "unknown", "skipped"]
    snapshot_ref: SnapshotReference | None = None
    source_run_id: str | None = Field(default=None, max_length=128)
    line_count: int = Field(default=0, ge=0)
    page_count: int | None = Field(default=None, ge=0)
    text_bytes: int | None = Field(default=None, ge=0)
    text_sha256: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    measurements: list[TokenMeasurement] = Field(default_factory=list, max_length=64)
    error: dict[str, Any] | None = None
    recording_status: str = "pending"
    persistence_state: str = "not_applicable"
    _url = field_validator("url")(public_url)

    @model_validator(mode="after")
    def ready_source(self):
        if self.status == "succeeded" and (self.snapshot_ref is None or self.recording_status != "complete" or self.persistence_state != "committed"):
            raise ValueError("Usable source requires a committed snapshot and complete recording")
        return self


class SourceManifest(Contract):
    items: list[SourceRecord] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_items(self):
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate source item identities")
        return self


class ContextSelection(Contract):
    item_id: str = Field(min_length=1, max_length=128)
    snapshot_ref: SnapshotReference
    range: SourceRange
    max_text_bytes: int = Field(default=16384, ge=1, le=65536)
    text_sha256: str | None = None
    measurement: TokenMeasurement | None = None
    continuation: str | None = Field(default=None, max_length=8192)
    truncated: bool = False
    start_byte: int | None = Field(default=None, ge=0)
    end_byte: int | None = Field(default=None, ge=0)
    source_read_action_id: str | None = None

    @model_validator(mode="after")
    def byte_interval(self):
        if (self.start_byte is None) != (self.end_byte is None):
            raise ValueError("Selected byte bounds must be paired")
        if self.start_byte is not None and self.end_byte <= self.start_byte:
            raise ValueError("Selected byte bounds must describe nonempty evidence")
        return self


class ContextPlan(Contract):
    recipient_role: str = Field(min_length=1, max_length=128)
    model_ref: str = Field(min_length=1, max_length=128)
    token_budget: int = Field(ge=1)
    max_text_bytes: int = Field(ge=1, le=1048576)
    selections: list[ContextSelection] = Field(default_factory=list, max_length=512)
    measurement: TokenMeasurement | None = None
    context_ref: ArtifactReference | None = None
    strict_tokens: bool = False


class ResearchRunRequest(Contract):
    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    method_id: str = Field(default="baseline", min_length=1, max_length=128)
    method_revision: int = Field(default=1, ge=1)
    input: dict[str, Any]
    parameters: dict[str, Any] = Field(default_factory=dict)
    profile_ref: str = Field(default="deepseek", min_length=1, max_length=128)
    model_ref: str = Field(default="deepseek-flash", min_length=1, max_length=128)
    timeout_seconds: float = Field(default=600, gt=0, le=1800)


class NodeView(Contract):
    node_id: str
    kind: str
    status: Literal["running", "succeeded", "failed", "cancelled"]
    detail: dict[str, Any] = Field(default_factory=dict)


class ResearchQuality(Contract):
    """Research coverage is independent of execution and report acceptance."""
    status: Literal["sufficient", "partial", "insufficient"]
    report_accepted: bool = False
    evidence_sufficient: bool
    attempted_sources: int = Field(ge=0, le=32)
    substantive_sources: int = Field(ge=0, le=32)
    fully_read_sources: int = Field(ge=0, le=32)
    distilled_sources: int = Field(ge=0, le=32)
    gaps: list[str] = Field(default_factory=list, max_length=16)
    reasons: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("gaps", "reasons")
    @classmethod
    def bounded_reasons(cls, values):
        if any(not value.strip() or len(value) > 1024 for value in values):
            raise ValueError("Coverage reasons require bounded nonblank text")
        return values

    @model_validator(mode="after")
    def coherent_coverage(self):
        if (self.status == "sufficient") != self.evidence_sufficient:
            raise ValueError("Sufficient coverage must agree with its explicit flag")
        return self


class ResearchRunView(Contract):
    run_id: str
    method_id: str
    method_revision: int
    client_request_id: str
    status: Literal["accepted", "running", "succeeded", "failed", "cancelled", "timed_out", "interrupted"]
    accepted_at: str
    profile_ref: str | None = None
    model_ref: str | None = None
    pins: dict[str, Any] = Field(default_factory=dict)
    active: bool = False
    cancellation_requested: bool = False
    recording_status: str = "pending"
    terminal_event_receipt: dict[str, Any] | None = None
    nodes: list[NodeView] = Field(default_factory=list)
    sources: SourceManifest = Field(default_factory=SourceManifest)
    context_plan: ContextPlan | None = None
    report_ref: ArtifactReference | None = None
    result_manifest_ref: ArtifactReference | None = None
    checkpoint_ref: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    quality: ResearchQuality | None = None
    error: dict[str, Any] | None = None
    automatic_resume: Literal[False] = False
