from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, Protocol

JsonValue = Any
JsonObject = dict[str, Any]
T = TypeVar("T")
SCHEMA_VERSION = 1
TERMINALS = frozenset({"succeeded", "failed", "validation_failed", "limit_exhausted", "timed_out", "cancelled"})
PLATFORM_SEARCH_POLICY = (
    "Do not use internal, provider-hosted or implicit web search. Research only "
    "through registered platform function tools; fetch and read source evidence "
    "before citing it."
)


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def deadline_after(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("deadline duration must be positive and finite")
    return datetime.fromtimestamp(time.time() + seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def deadline_timestamp(value: str | float | None) -> float:
    if value is None:
        return math.inf
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def to_json_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: to_json_value(getattr(value, f.name)) for f in dataclasses.fields(value)
                if not f.metadata.get("secret") and not f.name.startswith("_")}
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ValueError("JSON object keys must be strings")
        return {k: to_json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [to_json_value(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"nonserializable value: {type(value).__name__}")


def _json_depth(value: Any, level: int = 0, max_depth: int = 32) -> None:
    if level > max_depth:
        raise ValueError("JSON nesting exceeds limit")
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ValueError("JSON object keys must be strings")
        for child in value.values():
            _json_depth(child, level + 1, max_depth)
    elif isinstance(value, list):
        for child in value:
            _json_depth(child, level + 1, max_depth)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite JSON number")


def canonical_json(value: Any, max_bytes: int | None = None) -> bytes:
    value = to_json_value(value)
    _json_depth(value)
    result = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if max_bytes is not None and len(result) > max_bytes:
        raise ValueError("encoded JSON exceeds byte limit")
    return result


def strict_json_loads(value: str | bytes, max_bytes: int = 1048576, max_depth: int = 32) -> Any:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    if len(raw) > max_bytes:
        raise ValueError("JSON input exceeds byte limit")
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result
    def constant(_):
        raise ValueError("nonfinite JSON number")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    _json_depth(result, max_depth=max_depth)
    return result


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


class Record:
    def to_dict(self) -> dict[str, Any]:
        return to_json_value(self)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclasses.dataclass
class EngineError(Exception, Record):
    code: str
    message: str
    details: JsonObject = dataclasses.field(default_factory=dict)
    observed_effect_state: str = "not_observed"
    commit_state: str = "not_applicable"
    retryable_delivery: bool = False

    def __post_init__(self):
        Exception.__init__(self, self.message)


@dataclasses.dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    ok: bool = dataclasses.field(default=True, init=False)

    @property
    def is_ok(self) -> bool:
        return True

    def unwrap(self) -> T:
        return self.value


@dataclasses.dataclass(frozen=True)
class Err:
    error: EngineError
    ok: bool = dataclasses.field(default=False, init=False)

    @property
    def is_ok(self) -> bool:
        return False

    def unwrap(self):
        raise self.error


Result = Ok[T] | Err


@dataclasses.dataclass(frozen=True)
class ScopeRef(Record):
    kind: str
    id: str

    @property
    def scope_id(self) -> str:
        return self.id


@dataclasses.dataclass(frozen=True)
class ArtifactRef(Record):
    store_id: str
    artifact_id: str
    schema_version: int = 1

    @property
    def id(self):
        return self.artifact_id


@dataclasses.dataclass(frozen=True)
class SnapshotRef(Record):
    store_id: str
    snapshot_id: str
    schema_version: int = 1

    @property
    def id(self):
        return self.snapshot_id


@dataclasses.dataclass(frozen=True)
class CheckpointRef(Record):
    store_id: str
    checkpoint_id: str
    schema_version: int = 1

    @property
    def id(self):
        return self.checkpoint_id


@dataclasses.dataclass(frozen=True)
class RunRef(Record):
    store_id: str
    run_id: str
    schema_version: int = 1


@dataclasses.dataclass(frozen=True)
class EventReceipt(Record):
    store_id: str
    event_id: str
    recorded_seq: int
    recorded_at: str
    duplicate: bool = False
    schema_version: int = 1


@dataclasses.dataclass
class Grant(Record):
    operation: str
    scope: ScopeRef | None = None
    object_ids: frozenset[str] | None = None
    run_id: str | None = None
    producer: str | None = None
    event_kinds: frozenset[str] | None = None
    mode: str = "originator"
    target_origin: JsonObject | None = None
    expires_at: str | None = None
    byte_range: JsonObject | None = None
    max_bytes: int | None = None
    document_range: JsonObject | None = None
    document_ranges: tuple[JsonObject, ...] | None = None
    max_text_bytes: int | None = None
    allowed_media_types: tuple[str, ...] | None = None
    allowed_formats: tuple[str, ...] | None = None
    publication_purpose: str | None = None


@dataclasses.dataclass
class GrantSet:
    grants: list[Grant]
    principal: str
    revoked: bool = False
    _parents: tuple[Any, ...] = dataclasses.field(default=(), repr=False)

    def is_revoked(self):
        return self.revoked or any(parent.is_revoked() for parent in self._parents)

    def authorize(self, context, operation: str, scope=None, object_id=None, producer=None, event_kind=None, target_origin=None):
        context.assert_active()
        if self.is_revoked() or context.principal != self.principal:
            raise EngineError("ACCESS_DENIED", "authority is revoked or belongs to another principal")
        if context.purpose == "record_cleanup" and operation not in {"events.append", "events.status", "operation.status", "state.cleanup"}:
            raise EngineError("ACCESS_DENIED", "cleanup cannot perform business operations")
        if operation == "state.cleanup" and (context.purpose != "record_cleanup"
                or context.context_kind != "workflow" or scope != context.scope):
            raise EngineError("ACCESS_DENIED", "Cleanup state requires a same-run Workflow context")
        for grant in self.grants:
            if operation == "state.cleanup" and (grant.operation != "state.cleanup"
                    or grant.scope is None or grant.object_ids is None):
                continue
            if grant.operation not in {operation, "*"}:
                continue
            if grant.expires_at and deadline_timestamp(grant.expires_at) <= time.time():
                continue
            if grant.scope is not None and grant.scope != scope:
                continue
            selected_run = target_origin.get("run_id") if grant.mode == "observer" and target_origin else context.run_id
            if grant.run_id is not None and grant.run_id != selected_run:
                continue
            if grant.object_ids is not None and object_id not in grant.object_ids:
                continue
            if grant.producer is not None and producer != grant.producer:
                continue
            if grant.event_kinds is not None and event_kind not in grant.event_kinds:
                continue
            if grant.mode == "observer":
                if operation not in {"events.status", "operation.status"}:
                    continue
                if not grant.object_ids or not grant.target_origin:
                    continue
                if target_origin is not None and grant.target_origin is not None:
                    if any(target_origin.get(k) != v for k, v in grant.target_origin.items()):
                        continue
            elif grant.mode != "originator":
                continue
            return grant
        raise EngineError("ACCESS_DENIED", "operation is outside the bound grants")


@dataclasses.dataclass
class BudgetLedger:
    limits: dict[str, int] = dataclasses.field(default_factory=lambda: {
        "model_calls": 32, "tool_calls": 64, "repairs": 2, "source_bytes": 33554432,
        "storage_writes": 256, "storage_reads": 1024, "status_reads": 1024,
    })
    used: dict[str, int] = dataclasses.field(default_factory=dict)
    ledger_id: str = dataclasses.field(default_factory=lambda: new_id("ledger_"))
    _reservations: dict[str, tuple[str, int]] = dataclasses.field(default_factory=dict, repr=False)

    def consume(self, kind: str, amount: int = 1):
        aliases = {"model_attempts": "model_calls", "tool_attempts": "tool_calls", "model": "model_calls", "tool": "tool_calls"}
        kind = aliases.get(kind, kind)
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise EngineError("INVALID_DATA", "budget amounts must be nonnegative integers")
        used = self.used.get(kind, 0)
        reserved = sum(n for k, n in self._reservations.values() if k == kind)
        if kind in self.limits and used + reserved + amount > self.limits[kind]:
            raise EngineError("LIMIT_EXCEEDED", "shared lineage budget exhausted", {"kind": kind, "limit": self.limits[kind]})
        self.used[kind] = used + amount

    def remaining(self, kind: str) -> int:
        reserved = sum(n for k, n in self._reservations.values() if k == kind)
        return max(0, self.limits.get(kind, 2**53 - 1) - self.used.get(kind, 0) - reserved)

    def reserve(self, kind: str, amount: int, reservation_id: str):
        if reservation_id in self._reservations:
            if self._reservations[reservation_id] != (kind, amount):
                raise EngineError("IDENTITY_CONFLICT", "Budget reservation identity changed")
            return
        if type(amount) is not int or amount < 0 or not reservation_id:
            raise EngineError("INVALID_DATA", "Invalid budget reservation")
        if self.remaining(kind) < amount:
            raise EngineError("LIMIT_EXCEEDED", "Shared admission budget is exhausted", {"kind": kind})
        self._reservations[reservation_id] = (kind, amount)

    def consume_reserved(self, reservation_id: str):
        if reservation_id not in self._reservations:
            raise EngineError("IDENTITY_CONFLICT", "Budget reservation is absent or already consumed")
        kind, amount = self._reservations.pop(reservation_id)
        self.used[kind] = self.used.get(kind, 0) + amount

    def release_reserved(self, reservation_id: str):
        self._reservations.pop(reservation_id, None)

    def branch(self, limits: dict[str, int]):
        return BudgetView(self, limits)


class BudgetView(BudgetLedger):
    """A local cap over the same lineage owner; ancestor charges are never copied."""
    def __init__(self, parent: BudgetLedger, limits: dict[str, int]):
        selected = {k: min(v, parent.limits.get(k, v)) for k, v in limits.items()}
        super().__init__({**parent.limits, **selected}, ledger_id=parent.ledger_id)
        self._parent = parent

    @staticmethod
    def _kind(kind):
        return {"model_attempts": "model_calls", "tool_attempts": "tool_calls", "model": "model_calls", "tool": "tool_calls"}.get(kind, kind)

    def remaining(self, kind):
        kind = self._kind(kind)
        return min(super().remaining(kind), self._parent.remaining(kind))

    def consume(self, kind, amount=1):
        kind = self._kind(kind)
        if type(amount) is not int or amount < 0 or self.remaining(kind) < amount:
            raise EngineError("LIMIT_EXCEEDED", "Child or ancestor budget is exhausted", {"kind": kind})
        self._parent.consume(kind, amount)
        self.used[kind] = self.used.get(kind, 0) + amount

    def reserve(self, kind, amount, reservation_id):
        kind = self._kind(kind)
        if reservation_id in self._reservations:
            if self._reservations[reservation_id] != (kind, amount):
                raise EngineError("IDENTITY_CONFLICT", "Child reservation identity changed")
            return
        if type(amount) is not int or amount < 0 or self.remaining(kind) < amount:
            raise EngineError("LIMIT_EXCEEDED", "Child or ancestor admission budget is exhausted")
        self._parent.reserve(kind, amount, reservation_id)
        self._reservations[reservation_id] = kind, amount

    def consume_reserved(self, reservation_id):
        if reservation_id not in self._reservations:
            raise EngineError("IDENTITY_CONFLICT", "Child reservation is absent or consumed")
        kind, amount = self._reservations[reservation_id]
        self._parent.consume_reserved(reservation_id)
        self._reservations.pop(reservation_id)
        self.used[kind] = self.used.get(kind, 0) + amount

    def release_reserved(self, reservation_id):
        if reservation_id in self._reservations:
            self._parent.release_reserved(reservation_id)
            self._reservations.pop(reservation_id)


@dataclasses.dataclass
class ResourceLease:
    lease_id: str = dataclasses.field(default_factory=lambda: new_id("lease_"))
    active: bool = True

    def assert_active(self):
        if not self.active:
            raise EngineError("ACCESS_DENIED", "resource lease is closed")

    async def release(self):
        self.active = False
        return Ok(None)


@dataclasses.dataclass
class ExecutionContext(Record):
    run_id: str
    root_run_id: str
    correlation_id: str
    action_id: str
    principal: str = "host"
    context_kind: str = "agent"
    agent_id: str | None = None
    definition_ref: Any = None
    attempt_id: str | None = None
    parent_run_id: str | None = None
    parent_action_id: str | None = None
    parent_attempt_id: str | None = None
    root_action_id: str | None = None
    deadline: str | float | None = None
    depth: int = 0
    ancestry: tuple[str, ...] = ()
    binding_ref: str | None = None
    policy_ref: str | None = None
    purpose: str = "execution"
    store_id: str | None = None
    scope: ScopeRef | None = None
    metadata: JsonObject = dataclasses.field(default_factory=dict)
    schema_version: int = 1
    grants: GrantSet | None = dataclasses.field(default=None, repr=False, metadata={"secret": True})
    ledger: BudgetLedger = dataclasses.field(default_factory=BudgetLedger, repr=False, metadata={"secret": True})
    cancellation: asyncio.Event = dataclasses.field(default_factory=asyncio.Event, repr=False, metadata={"secret": True})
    lease: ResourceLease = dataclasses.field(default_factory=ResourceLease, repr=False, metadata={"secret": True})
    _monotonic_deadline: float | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self):
        if self.root_action_id is None:
            self.root_action_id = self.action_id
        if self._monotonic_deadline is None:
            delta = max(0.0, deadline_timestamp(self.deadline) - time.time())
            self._monotonic_deadline = time.monotonic() + delta

    def remaining_seconds(self) -> float:
        return max(0.0, self._monotonic_deadline - time.monotonic())

    def assert_active(self):
        self.lease.assert_active()
        if self.cancellation.is_set() and self.purpose != "record_cleanup":
            raise EngineError("CANCELLED", "execution was cancelled")
        if self.remaining_seconds() <= 0:
            raise EngineError("DEADLINE_EXCEEDED", "execution deadline elapsed")

    def authorize(self, operation, scope=None, object_id=None, producer=None, event_kind=None, target_origin=None):
        if self.grants is None:
            raise EngineError("ACCESS_DENIED", "no live authority is bound")
        return self.grants.authorize(self, operation, scope, object_id, producer, event_kind, target_origin)

    def for_action(self, action_id: str, attempt_id: str | None = None, **changes):
        return dataclasses.replace(self, action_id=action_id, attempt_id=attempt_id, **changes)

    def for_cleanup(self, seconds: float = 10):
        seconds = min(max(seconds, 0.001), 30)
        return dataclasses.replace(self, purpose="record_cleanup", deadline=deadline_after(seconds),
                                   _monotonic_deadline=time.monotonic() + seconds)

    def descriptor(self):
        return self.to_dict()


@dataclasses.dataclass
class ExecutionEvent(Record):
    event_id: str
    kind: str
    producer: str
    context: ExecutionContext | JsonObject
    payload: JsonObject = dataclasses.field(default_factory=dict)
    producer_timestamp: str = dataclasses.field(default_factory=utc_now)
    schema_version: int = 1


@dataclasses.dataclass
class CleanupReport(Record):
    complete: bool = True
    errors: list[Any] = dataclasses.field(default_factory=list)
    unconfirmed_resources: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ArtifactContent:
    data: bytes | None = None
    byte_length: int | None = None
    sha256: str | None = None
    source: Any = dataclasses.field(default=None, repr=False)

    def __post_init__(self):
        if self.data is not None and self.source is not None:
            raise ValueError("Artifact content requires exactly one byte source")
        if self.data is None and self.source is None:
            raise ValueError("Artifact content requires bytes or an async source")
        if self.data is not None and self.byte_length is None:
            self.byte_length = len(self.data)
        if self.data is not None and self.sha256 is None:
            self.sha256 = digest_bytes(self.data)
        if isinstance(self.sha256, str) and not self.sha256.startswith("sha256:"):
            self.sha256 = "sha256:" + self.sha256
        if self.source is not None and (type(self.byte_length) is not int or self.byte_length < 0 or self.sha256 is None):
            raise ValueError("Async source requires an immutable length and SHA-256 descriptor")


class AsyncByteSource(Protocol):
    async def read(self, max_bytes: int) -> bytes: ...
    async def aclose(self) -> None: ...


@dataclasses.dataclass
class ArtifactMetadata(Record):
    media_type: str
    filename: str | None = None
    metadata: JsonObject = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ArtifactReceipt(Record):
    operation_id: str
    artifact_ref: ArtifactRef
    scope: ScopeRef
    byte_length: int
    sha256: str
    media_type: str
    event_receipt: EventReceipt
    duplicate: bool = False
    schema_version: int = 1
    store_id: str = dataclasses.field(init=False)

    def __post_init__(self):
        self.store_id = self.artifact_ref.store_id


@dataclasses.dataclass
class SnapshotProposal:
    original: bytes
    text: bytes
    index: bytes
    provenance: JsonObject
    extraction_version: str = "document_snapshot/1"
    normalization_version: str = "text_normalization/1"
    media_type: str = "text/plain"

    @property
    def raw_bytes(self):
        return self.original


@dataclasses.dataclass
class SnapshotReceipt(Record):
    operation_id: str
    snapshot_ref: SnapshotRef
    manifest_ref: ArtifactRef
    original_ref: ArtifactRef
    text_ref: ArtifactRef
    index_ref: ArtifactRef
    component_digests: JsonObject
    extraction_version: str
    line_count: int
    physical_page_count: int | None
    event_receipt: EventReceipt
    duplicate: bool = False
    schema_version: int = 1
    store_id: str = dataclasses.field(init=False)

    @property
    def raw_ref(self):
        return self.original_ref

    @property
    def physical_page_count_or_null(self):
        return self.physical_page_count

    def __post_init__(self):
        self.store_id = self.snapshot_ref.store_id


@dataclasses.dataclass
class DocumentSlice(Record):
    snapshot_ref: SnapshotRef
    extraction_version: str
    normalization_version: str
    requested_range: JsonObject
    returned_range: JsonObject
    text: str
    byte_length: int
    truncated: bool
    has_more_in_requested_range: bool
    has_more_in_document: bool
    next_position: Any
    continuation: str | None
    spans: list[JsonObject] = dataclasses.field(default_factory=list)
    schema_version: int = 1

    @property
    def actual_range(self):
        return self.returned_range

    @property
    def locations(self):
        return self.spans

    @property
    def remaining_within_range(self):
        return self.has_more_in_requested_range

    @property
    def remaining_document(self):
        return self.has_more_in_document


@dataclasses.dataclass(frozen=True)
class ToolRef(Record):
    name: str
    revision: int = 1


@dataclasses.dataclass
class ToolDefinition(Record):
    name: str
    revision: int = 1
    description: str = ""
    input_schema: JsonObject = dataclasses.field(default_factory=dict)
    output_schema: JsonObject = dataclasses.field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    limits: JsonObject = dataclasses.field(default_factory=dict)
    argv: tuple[str, ...] = ()
    config: JsonObject = dataclasses.field(default_factory=dict)
    storage_needs: JsonObject = dataclasses.field(default_factory=dict)
    schema_version: int = 1

    @property
    def ref(self):
        return ToolRef(self.name, self.revision)


@dataclasses.dataclass
class ToolRequest(Record):
    tool: ToolRef
    arguments: JsonObject
    provider_call_id: str | None = None
    model_action_id: str | None = None
    model_attempt_id: str | None = None
    schema_version: int = 1


@dataclasses.dataclass
class AttemptLease:
    context: ExecutionContext
    lease_id: str = dataclasses.field(default_factory=lambda: new_id("attempt_"))
    _receipt: EventReceipt | None = dataclasses.field(default=None, repr=False)
    _active: bool = True

    def mark_recorded(self, receipt: EventReceipt):
        if not isinstance(receipt, EventReceipt) or receipt.store_id != self.context.store_id:
            raise EngineError("ACCESS_DENIED", "intent receipt is outside the bound store")
        self.context.assert_active()
        self._receipt = receipt

    def assert_recorded(self):
        self.context.assert_active()
        if not self._active or self._receipt is None:
            raise EngineError("ACCESS_DENIED", "attempt has no acknowledged intent authority")

    def release(self):
        self._active = False


@dataclasses.dataclass
class ToolStoragePlan:
    tool: ToolRef
    context: ExecutionContext
    scope: ScopeRef | None = None
    operation_id: str | None = None
    snapshot_store: Any = None
    operation_store: Any = None
    read_slice: DocumentSlice | None = None
    limits: JsonObject = dataclasses.field(default_factory=dict)
    request: JsonObject = dataclasses.field(default_factory=dict)
    lease: AttemptLease | None = None
    dispatch_policy: JsonObject | None = None

    def assert_recorded(self):
        if self.lease is None:
            raise EngineError("ACCESS_DENIED", "no live attempt lease")
        self.lease.assert_recorded()


@dataclasses.dataclass
class ToolExecutionResult(Record):
    tool: ToolRef
    invocation: JsonObject
    status: str
    result: Any = None
    error: EngineError | None = None
    observations: JsonObject = dataclasses.field(default_factory=dict)
    process: JsonObject = dataclasses.field(default_factory=dict)
    usage: JsonObject = dataclasses.field(default_factory=dict)
    persistence: JsonObject = dataclasses.field(default_factory=lambda: {"required": False, "operation_id": None, "commit_state": "not_applicable", "receipt": None})
    schema_version: int = 1


@dataclasses.dataclass
class ToolResult(ToolExecutionResult):
    recording: JsonObject = dataclasses.field(default_factory=dict)
    event_ids: JsonObject = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class AgentDefinition(Record):
    agent_id: str
    instructions: str
    model_ref: str = "deepseek-flash"
    profile_ref: str = "deepseek"
    allowed_tools: list[ToolRef] = dataclasses.field(default_factory=list)
    input_schema: JsonObject = dataclasses.field(default_factory=lambda: {"type": "string"})
    output_schema: JsonObject = dataclasses.field(default_factory=lambda: {"type": "string"})
    output_mode: str = "text"
    output_media_type: str = "text/markdown"
    limits: JsonObject = dataclasses.field(default_factory=dict)
    settings: JsonObject = dataclasses.field(default_factory=dict)
    context_sources: list[Any] = dataclasses.field(default_factory=list)
    delegation: JsonObject = dataclasses.field(default_factory=dict)
    output_contract: JsonObject = dataclasses.field(default_factory=dict)
    error_policy: JsonObject = dataclasses.field(default_factory=dict)
    revision: int = 1
    schema_version: int = 1

    @property
    def definition_ref(self):
        return {"agent_id": self.agent_id, "revision": self.revision, "sha256": digest_json(self)}


@dataclasses.dataclass
class ProviderConfig:
    provider: str
    model_id: str
    base_url: str
    api_key: str = dataclasses.field(repr=False, metadata={"secret": True})
    settings: JsonObject = dataclasses.field(default_factory=dict)
    profile_ref: str = ""
    model_ref: str = ""


@dataclasses.dataclass
class BindingSet:
    catalog: Any
    executor: Any
    recorder: Any
    artifacts: Any
    snapshots: Any
    storage_plan_factory: Any
    provider_config: ProviderConfig | None = None
    provider_factory: Any = None
    invoker: Any = None
    storage: Any = None
    output_scope: ScopeRef | None = None
    lease: ResourceLease = dataclasses.field(default_factory=ResourceLease)


@dataclasses.dataclass
class AgentResult(Record):
    execution: JsonObject
    status: str
    definition_ref: Any = None
    admission_id: str | None = None
    start_state: str = "not_started"
    output_delivery: str = "none"
    output: Any = None
    output_ref: ArtifactRef | None = None
    raw_output_ref: ArtifactRef | None = None
    output_metadata: JsonObject | None = None
    output_publications: list[JsonObject] = dataclasses.field(default_factory=list)
    validation: JsonObject = dataclasses.field(default_factory=dict)
    observed_output: JsonObject | None = None
    persistence_state: str = "not_applicable"
    error: EngineError | None = None
    recording_error: EngineError | None = None
    recording_status: str = "unavailable"
    cleanup: CleanupReport = dataclasses.field(default_factory=CleanupReport)
    usage: JsonObject = dataclasses.field(default_factory=dict)
    counters: JsonObject = dataclasses.field(default_factory=dict)
    start_event_receipt: EventReceipt | None = None
    terminal_event_receipt: EventReceipt | None = None
    unfinished_actions: list[JsonObject] = dataclasses.field(default_factory=list)
    terminal_state: JsonObject | None = None
    terminal_state_ref: ArtifactRef | None = None
    audit_refs: list[ArtifactRef] = dataclasses.field(default_factory=list)
    schema_version: int = 1


@dataclasses.dataclass(frozen=True)
class StateMutation(Record):
    scope: ScopeRef
    key: str
    kind: str
    expected_version: int
    value: JsonValue = None


@dataclasses.dataclass(frozen=True)
class StateLookup(Record):
    present: bool
    version: int
    value: JsonValue = None
    commit_event_id: str | None = None


@dataclasses.dataclass
class StateCommitReceipt(Record):
    store_id: str
    operation_id: str
    event_receipt: EventReceipt
    mutation_versions: list[JsonObject]
    duplicate: bool = False
    schema_version: int = 1


@dataclasses.dataclass(frozen=True)
class ByteRange(Record):
    start: int
    end_exclusive: int


@dataclasses.dataclass(frozen=True)
class ByteChunk:
    bytes: bytes
    eof: bool
    next_absolute_offset: int


@dataclasses.dataclass
class CheckpointEnvelope(Record):
    run_id: str
    payload: JsonObject
    format: str = "engine_checkpoint/1"
    envelope_format_version: int = 1
    payload_schema_version: int = 1
    schema_version: int = 1


@dataclasses.dataclass
class CheckpointReceipt(Record):
    store_id: str
    operation_id: str
    checkpoint_ref: CheckpointRef
    payload_ref: ArtifactRef
    byte_length: int
    sha256: str
    envelope_format_version: int
    event_receipt: EventReceipt
    duplicate: bool = False
    schema_version: int = 1


@dataclasses.dataclass
class EventStatus(Record):
    store_id: str
    event_id: str
    state: str
    observed_seq: int | None = None
    receipt: EventReceipt | None = None
    pending_phase: str | None = None
    schema_version: int = 1


@dataclasses.dataclass
class OperationStatus(Record):
    store_id: str
    operation_id: str
    state: str
    commit_state: str
    observed_seq: int | None = None
    receipt: Any = None
    phase: str | None = None
    safe_disposition: JsonObject | None = None
    schema_version: int = 1


@dataclasses.dataclass
class ActivityPage(Record):
    store_id: str
    events: list[JsonObject]
    cursor: str | None
    high_water_seq: int
    schema_version: int = 1


@dataclasses.dataclass
class CloseReceipt(Record):
    store_id: str
    closed: bool
    completed_operation_ids: list[str]
    interrupted_operation_ids: list[str]
    schema_version: int = 1
