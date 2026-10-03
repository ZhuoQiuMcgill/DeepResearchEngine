"""Host-owned configuration and authority-free composition records."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from deepresearch.engine.contracts import (
    AgentDefinition, ArtifactRef, ByteRange, CheckpointRef, CleanupReport,
    ExecutionContext, JsonObject, Record, RunRef, ScopeRef, SnapshotRef, ToolRef,
)


@dataclasses.dataclass(frozen=True)
class AgentRef(Record):
    agent_id: str
    revision: int = 1


@dataclasses.dataclass(frozen=True)
class InvocationRule(Record):
    destination: AgentRef
    allowed_tools: tuple[str, ...] = ()
    allow_model: bool = True
    allow_export: bool = False
    allow_onward: bool = False
    max_depth: int = 4
    timeout_seconds: float = 180
    limits: JsonObject = dataclasses.field(default_factory=dict)
    allow_evidence: bool = False


@dataclasses.dataclass(frozen=True)
class WorkflowPolicy(Record):
    """Host-selected tools and child edges; carries no agent/model definition."""
    allowed_tools: tuple[ToolRef, ...] = ()
    invocation_rules: tuple[InvocationRule, ...] = ()
    cleanup_state_keys: tuple[str, ...] = ()
    schema_version: int = 1


@dataclasses.dataclass(frozen=True)
class RegisteredAgent(Record):
    ref: AgentRef
    definition_ref: JsonObject


@dataclasses.dataclass
class EngineSettings:
    workspace: Path | str = dataclasses.field(default_factory=Path.cwd)
    storage_root: Path | str | None = None
    env_file: Path | str | None = None
    storage_profile: str = "delete"
    host_principal: str = "local-host"
    max_run_seconds: float = 1800
    max_access_seconds: float = 120
    max_depth: int = 4
    max_descendants: int = 16
    max_active_descendants: int = 4
    openalex_admission: bool = False
    fetch_concurrency: int = 1
    profiles: dict[str, Any] = dataclasses.field(default_factory=dict, repr=False)
    limits: JsonObject = dataclasses.field(default_factory=lambda: {
        "model_calls": 32, "tool_calls": 128, "repairs": 2,
        "source_bytes": 67108864, "storage_bytes": 134217728,
        "storage_writes": 4096, "storage_reads": 2048, "status_reads": 2048,
        "storage_read_bytes": 134217728,
        "descendants": 16,
    })


@dataclasses.dataclass
class RunOptions(Record):
    timeout_seconds: float = 600
    limits: JsonObject = dataclasses.field(default_factory=dict)
    metadata: JsonObject = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ToolRunOptions(RunOptions):
    source_run_ref: RunRef | None = None
    read_objects: tuple[SnapshotReadRequest, ...] = ()


@dataclasses.dataclass(frozen=True)
class ArtifactReadRequest(Record):
    ref: ArtifactRef
    range: ByteRange | None = None
    max_bytes: int = 8388608
    kind: str = "artifact"


@dataclasses.dataclass(frozen=True)
class SnapshotReadRequest(Record):
    ref: SnapshotRef
    range: JsonObject
    max_text_bytes: int = 65536
    continuation: str | None = None
    kind: str = "snapshot"


@dataclasses.dataclass(frozen=True)
class CheckpointReadRequest(Record):
    ref: CheckpointRef
    accepted_formats: tuple[str, ...] = ("engine_checkpoint/1",)
    max_bytes: int = 8388608
    kind: str = "checkpoint"


@dataclasses.dataclass(frozen=True)
class StateReadRequest(Record):
    """Read one selected key, including its retained historical versions."""
    scope: ScopeRef
    key: str
    max_bytes: int = 1049600


@dataclasses.dataclass(frozen=True)
class EvidenceBinding(Record):
    """Authority selectors; source references alone are not permission."""
    read_objects: tuple[ArtifactReadRequest | SnapshotReadRequest | CheckpointReadRequest, ...] = ()
    state_reads: tuple[StateReadRequest, ...] = ()


@dataclasses.dataclass
class InvocationOptions(RunOptions):
    evidence: EvidenceBinding | None = None


@dataclasses.dataclass(frozen=True)
class HistoryReadRequest(Record):
    filters: JsonObject = dataclasses.field(default_factory=dict)
    max_pages: int = 16
    max_events: int = 500
    max_total_bytes: int = 8388608


@dataclasses.dataclass(frozen=True)
class PublicationRequest(Record):
    operation: str
    scope: ScopeRef
    purpose: str
    allowed_media_types: tuple[str, ...] = ("application/json", "text/markdown")
    allowed_formats: tuple[str, ...] = ("engine_checkpoint/1",)
    max_object_bytes: int = 8388608
    max_total_bytes: int = 16777216
    max_operations: int = 8
    read_created: bool = False


@dataclasses.dataclass(frozen=True)
class EventStatusRequest(Record):
    event_id: str
    expected_event_digest: str | None = None
    kind: str = "event"


@dataclasses.dataclass(frozen=True)
class OperationStatusRequest(Record):
    operation_id: str
    kind: str = "operation"


@dataclasses.dataclass(frozen=True)
class RunAccessRequest(Record):
    read_objects: tuple[Any, ...] = ()
    history: HistoryReadRequest | None = None
    publications: tuple[PublicationRequest, ...] = ()
    status_operations: tuple[EventStatusRequest | OperationStatusRequest, ...] = ()
    schema_version: int = 1


@dataclasses.dataclass(frozen=True)
class RunAccessOptions(Record):
    timeout_seconds: float = 60
    max_total_read_bytes: int = 16777216
    max_total_write_bytes: int = 16777216
    max_operations: int = 128
    metadata: JsonObject = dataclasses.field(default_factory=dict)
    grant_preset_ref: str = "own-run-results/1"
    schema_version: int = 1


@dataclasses.dataclass
class InvocationOutcome(Record):
    execution: JsonObject
    destination: AgentRef
    status: str
    child_run: RunRef | None = None
    child_result: Any = None
    output: Any = None
    output_ref: ArtifactRef | None = None
    export_receipt: Any = None
    error: Any = None
    dispatched: bool = False
    recording_status: str = "unavailable"
    intent_receipt: Any = None
    outcome_receipt: Any = None
    cleanup: CleanupReport = dataclasses.field(default_factory=CleanupReport)
    schema_version: int = 1


@dataclasses.dataclass
class BoundSession:
    context: ExecutionContext
    binding: Any
    definition: AgentDefinition | None
    _on_close: Any = dataclasses.field(default=None, repr=False)

    async def close(self):
        await self.binding.lease.release()
        await self.context.lease.release()
        if self._on_close:
            self._on_close(self)
        return CleanupReport()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
