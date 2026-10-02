"""A real, bounded provider/tool runtime with durable lifecycle boundaries."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import math
import time
from dataclasses import dataclass, field
from typing import Any

from ebd.engine.contracts import (
    AgentDefinition, AgentResult, CleanupReport, EngineError, Err, Ok,
    ToolRequest, ToolRef, canonical_json, deadline_after, digest_bytes, digest_json, new_id,
    strict_json_loads, to_json_value,
)
from ebd.engine.providers import ModelRequest, ModelResponse, ModelTool, ProviderConfig, ProviderFactory
from ebd.engine.providers.usage import PRIMARY_COUNTS, TOKEN_COUNTS, normalize_usage, provider_usage_projection, unknown_usage
from .recording import RecordedToolAction, append_event, maybe_await, status_for
from .validation import validate_schema, validation_errors


DEFAULT_LIMITS = {
    "max_run_seconds": 120, "max_model_seconds": 45, "max_tool_seconds": 30,
    "max_model_calls": 8, "max_tool_calls": 12, "max_tool_attempts": 12,
    "max_output_tokens_per_call": 4096, "max_context_tokens": 32768,
    "max_task_input_bytes": 65536, "max_model_request_bytes": 1048576,
    "max_model_response_bytes": 1048576, "max_continuation_bytes": 1048576,
    "max_final_output_bytes": 65536, "max_public_result_bytes": 524288,
    "max_cleanup_seconds": 5, "max_record_cleanup_seconds": 5,
    "max_source_bytes": 262144, "max_tool_context_bytes": 65536,
    "token_budget": None,
}

RECOVERABLE_SOURCE_ERRORS = frozenset({
    "SEARCH_UNAVAILABLE", "SEARCH_BACKEND_UNAVAILABLE", "SCHOLAR_UNAVAILABLE",
    "SCHOLAR_HTTP_FORBIDDEN", "SCHOLAR_HTTP_ERROR", "SCHOLAR_UNEXPECTED_REDIRECT",
    "SCHOLAR_AUTH_UNSUPPORTED", "SCHOLAR_PROTOCOL_ERROR", "SCHOLAR_RATE_LIMITED",
    "SCHOLAR_QUOTA_EXHAUSTED", "SCHOLAR_RESPONSE_LIMIT", "FETCH_UNAVAILABLE",
    "FETCH_HTTP_ERROR", "REDIRECT_LIMIT", "PARTIAL_RESPONSE", "DESTINATION_DENIED",
    "SOURCE_CHALLENGE", "UNSUPPORTED_CONTENT", "CONTENT_TYPE_MISMATCH",
    "UNSUPPORTED_ENCODING", "DECODING_ERROR", "EXTRACTION_EMPTY", "PDF_NO_TEXT",
    "PDF_ENCRYPTED", "PDF_INVALID", "PDF_PAGE_LIMIT", "TEXT_LIMIT", "RESPONSE_LIMIT",
})


class _ReceivedResponseCancellation(asyncio.CancelledError):
    """Carry completed provider facts without turning cancellation into success."""

    def __init__(self, response: ModelResponse, cancellation: asyncio.CancelledError):
        super().__init__(*cancellation.args)
        self.response = response


@dataclass
class AdmissionLease:
    owner: Any = field(repr=False)
    admission_id: str
    definition: AgentDefinition
    task_input: Any
    binding: Any = field(repr=False)
    context: Any = field(repr=False)
    tools: tuple[ModelTool, ...]
    limits: dict[str, Any]
    context_items: tuple[dict[str, Any], ...] = ()
    state: str = "reserved"
    reservation_id: str = field(default_factory=lambda: new_id("reservation_"))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    start_receipt: Any = None
    terminal_receipt: Any = None
    terminal_status: str | None = None
    reservation_state: str = "reserved"

    def descriptor(self):
        return {"schema_version": 1, "admission_id": self.admission_id,
                "run_id": self.context.run_id, "root_run_id": self.context.root_run_id,
                "correlation_id": self.context.correlation_id, "root_action_id": self.context.root_action_id,
                "definition_ref": self.definition.definition_ref, "binding_id": self.context.binding_ref,
                "ledger_id": self.context.ledger.ledger_id, "reservation_id": self.reservation_id,
                "expires_at_utc": self.context.deadline}

    async def release(self):
        async with self.lock:
            if self.state in {"released", "expired"}:
                return Ok({"schema_version": 1, "admission_id": self.admission_id, "state": self.state, "reservation_id": self.reservation_id, "duplicate": True})
            if self.state != "reserved":
                return Err(EngineError("admission.consumed", "Consumed or uncertain admission cannot be released"))
            self.state = "expired" if self.context.remaining_seconds() <= 0 else "released"
            self.context.ledger.release_reserved(self.reservation_id)
            self.reservation_state = "released"
            return Ok({"schema_version": 1, "admission_id": self.admission_id, "state": self.state, "reservation_id": self.reservation_id, "duplicate": False})


def _provider_config(config):
    if isinstance(config, ProviderConfig):
        return config
    if config is None:
        raise EngineError("provider.configuration", "No model profile is bound")
    return ProviderConfig(
        provider=config.provider, model_id=config.model_id, base_url=config.base_url,
        api_key=config.api_key, settings=dict(config.settings),
        profile_name=getattr(config, "profile_name", None) or getattr(config, "profile_ref", "default") or "default",
        profile_revision=getattr(config, "profile_revision", "1"),
        endpoint_id=getattr(config, "endpoint_id", "configured-endpoint"),
        deployment_manifest=getattr(config, "deployment_manifest", None),
    )


class Runtime:
    def __init__(self, *, tool_action=None, max_live_admissions=32, max_admission_records=128):
        if type(max_live_admissions) is not int or max_live_admissions <= 0 or type(max_admission_records) is not int or max_admission_records < max_live_admissions:
            raise ValueError("Runtime admission bounds require finite positive integer capacity and retention")
        self.tool_action = tool_action or RecordedToolAction()
        self._admissions: dict[str, AdmissionLease] = {}
        self._max_live_admissions = max_live_admissions
        self._max_admission_records = max_admission_records
        self._admitting = 0

    def _prune_admissions(self):
        for lease in self._admissions.values():
            if lease.state == "reserved" and lease.context.remaining_seconds() <= 0:
                lease.state = "expired"
                lease.context.ledger.release_reserved(lease.reservation_id)
                lease.reservation_state = "released"
        removable = [key for key, lease in self._admissions.items() if lease.state in {"terminal", "released", "expired"}]
        for key in removable[:max(0, len(self._admissions) - self._max_admission_records)]:
            del self._admissions[key]

    async def admit(self, definition, task_input, binding, context):
        admitting = False
        try:
            self._prune_admissions()
            live = sum(lease.state in {"reserved", "consumed", "unknown"} for lease in self._admissions.values())
            if live + self._admitting >= self._max_live_admissions:
                raise EngineError("LIMIT_EXCEEDED", "Runtime live admission capacity is exhausted", {"kind": "live_admissions"})
            self._admitting += 1
            admitting = True
            context.assert_active()
            binding.lease.assert_active()
            if not isinstance(definition, AgentDefinition) or not definition.agent_id or not definition.instructions:
                raise EngineError("agent.validation", "A complete AgentDefinition is required")
            if definition.output_contract:
                closed = {"mode", "media_type", "schema", "native_enforcement", "max_bytes", "delivery"}
                if set(definition.output_contract) - closed:
                    raise EngineError("agent.validation", "Unknown output-contract field")
                definition = copy.deepcopy(definition)
                definition.output_mode = definition.output_contract.get("mode", definition.output_mode)
                definition.output_media_type = definition.output_contract.get("media_type", definition.output_media_type)
                definition.output_schema = definition.output_contract.get("schema", definition.output_schema)
            if definition.schema_version != 1 or definition.output_mode not in {"text", "json"}:
                raise EngineError("agent.validation", "Unsupported definition version/output mode")
            if definition.output_media_type not in ({"application/json"} if definition.output_mode == "json" else {"text/plain", "text/markdown"}):
                raise EngineError("agent.validation", "Output media type does not match its mode")
            if definition.output_contract.get("native_enforcement", "optional") not in {"disabled", "optional", "required"} or definition.output_contract.get("delivery", "inline_or_artifact") not in {"inline_or_artifact", "artifact"}:
                raise EngineError("agent.validation", "Unknown output enforcement/delivery mode")
            if len(definition.instructions.encode()) > 32768:
                raise EngineError("agent.validation", "Agent instructions exceed their byte allowance")
            validate_schema(definition.input_schema)
            validate_schema(definition.output_schema)
            if validation_errors(definition.input_schema, task_input):
                raise EngineError("agent.validation", "Task input failed the registered schema")
            if set(definition.limits) - set(DEFAULT_LIMITS):
                raise EngineError("agent.validation", "Unknown execution limit")
            limits = {**DEFAULT_LIMITS, **definition.limits}
            if "max_bytes" in definition.output_contract:
                limits["max_final_output_bytes"] = min(limits["max_final_output_bytes"], definition.output_contract["max_bytes"])
            for key, value in limits.items():
                if key == "token_budget":
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise EngineError("agent.validation", "Limits must be positive finite numbers", {"field": key})
                if not key.endswith("seconds") and type(value) is not int:
                    raise EngineError("agent.validation", "Count/byte limits require integers", {"field": key})
            token_budget = limits["token_budget"]
            if token_budget is not None:
                if not isinstance(token_budget, dict) or set(token_budget) != {"max_total_tokens", "enforcement"} or type(token_budget["max_total_tokens"]) is not int or token_budget["max_total_tokens"] <= 0 or token_budget["enforcement"] not in {"strict", "advisory"}:
                    raise EngineError("agent.validation", "Invalid token-budget declaration")
                if token_budget["enforcement"] == "strict":
                    raise EngineError("agent.unsupported", "Strict token budgeting requires a verified pre-dispatch tokenizer/accounting profile")
            if set(definition.error_policy) - {"recoverable_tool_errors", "unauthorized_tool", "invalid_arguments", "max_model_retries", "max_repairs"}:
                raise EngineError("agent.validation", "Unknown error-policy field")
            if definition.error_policy.get("max_model_retries", 0) != 0 or definition.error_policy.get("max_repairs", 0) != 0:
                raise EngineError("agent.unsupported", "This runtime profile permits no automatic retries or repair dispatches")
            if definition.error_policy.get("recoverable_tool_errors", "return_to_model") not in {"return_to_model", "terminate"} or definition.error_policy.get("unauthorized_tool", "terminate") != "terminate" or definition.error_policy.get("invalid_arguments", "terminate") != "terminate":
                raise EngineError("agent.validation", "Unsupported error policy")
            canonical_json(task_input, max_bytes=limits["max_task_input_bytes"])
            canonical_json(definition, max_bytes=131072)
            if len(set((t.name, t.revision) for t in definition.allowed_tools)) != len(definition.allowed_tools):
                raise EngineError("agent.validation", "Allowed tools must be unique")
            config = _provider_config(binding.provider_config)
            from ebd.engine.providers.factory import _validate_config
            _validate_config(dataclasses.replace(config, settings={**config.settings, **definition.settings}))
            if config.model_id != definition.model_ref:
                raise EngineError("provider.configuration", "Definition/model binding mismatch")
            context.authorize("model.generate", object_id=config.model_id)
            scope = getattr(binding, "output_scope", None) or context.scope
            context.authorize("artifact.put", scope)
            tools = []
            for tool in definition.allowed_tools:
                found = await maybe_await(binding.catalog.resolve(tool.name, tool.revision))
                if isinstance(found, Err):
                    raise found.error
                resolved = found.value if isinstance(found, Ok) else found
                validate_schema(resolved.input_schema)
                context.authorize("tool.execute", object_id=tool.name)
                provider_name = "t_" + digest_json(tool).split(":")[-1][:32]
                tools.append(ModelTool(tool.name, str(tool.revision), provider_name, resolved.description, copy.deepcopy(resolved.input_schema)))
            if len({t.provider_name for t in tools}) != len(tools):
                raise EngineError("agent.validation", "Provider function-name collision")
            seconds = min(limits["max_run_seconds"], context.remaining_seconds())
            if seconds <= 0:
                raise EngineError("DEADLINE_EXCEEDED", "Admission deadline elapsed")
            narrowed = dataclasses.replace(context, deadline=deadline_after(seconds), _monotonic_deadline=time.monotonic() + seconds)
            context_items = await self._context_sources(definition, binding, narrowed, limits)
            binding.record_cleanup_seconds = min(limits["max_record_cleanup_seconds"], getattr(binding, "record_cleanup_seconds", 5))
            lease = AdmissionLease(self, new_id("admission_"), copy.deepcopy(definition), copy.deepcopy(task_input), binding, narrowed, tuple(tools), limits, tuple(context_items))
            narrowed.ledger.reserve("model_calls", 1, lease.reservation_id)
            self._admissions[lease.admission_id] = lease
            self._prune_admissions()
            return Ok(lease)
        except EngineError as error:
            return Err(error)
        except (ValueError, TypeError) as exc:
            return Err(EngineError("agent.validation", "Definition/admission validation failed", {"exception_type": type(exc).__name__}))
        finally:
            if admitting:
                self._admitting -= 1

    async def _context_sources(self, definition, binding, context, limits):
        result = []
        retained = 0
        for source in definition.context_sources:
            if not isinstance(source, dict):
                raise EngineError("agent.validation", "Context sources require a tagged object")
            kind = source.get("kind")
            try:
                if kind == "artifact":
                    maximum = min(source.get("max_bytes", limits["max_source_bytes"]), limits["max_source_bytes"])
                    reader = (await binding.artifacts.open(context, source["artifact_ref"], source.get("byte_range"), maximum)).unwrap()
                    chunks = []
                    accumulated = 0
                    try:
                        while True:
                            chunk = (await reader.read(context, min(65536, max(1, maximum - accumulated)))).unwrap()
                            accumulated += len(chunk.bytes)
                            if accumulated > maximum:
                                raise EngineError("LIMIT_EXCEEDED", "Artifact context exceeds its source allowance")
                            chunks.append(chunk.bytes)
                            if chunk.eof:
                                break
                            if not chunk.bytes:
                                raise EngineError("agent.context", "Artifact reader made no progress")
                    finally:
                        await reader.aclose(context)
                    text = b"".join(chunks).decode("utf-8")
                    item = {"kind": "context", "text": text, "source_ref": source["artifact_ref"], "locator": source.get("byte_range")}
                elif kind == "snapshot":
                    value = (await binding.snapshots.read(context, source["snapshot_ref"], source["range"], source.get("max_text_bytes", 65536), source.get("continuation"))).unwrap()
                    item = {"kind": "context", "text": value.text, "source_ref": source["snapshot_ref"], "locator": value.actual_range}
                elif kind == "state":
                    requested = source.get("version", "latest_at_start")
                    value = (await (binding.storage.state.get(context, source["scope_ref"], source["key"]) if requested == "latest_at_start" else binding.storage.state.get_version(context, source["scope_ref"], source["key"], requested))).unwrap()
                    actual_version = value.get("version") if isinstance(value, dict) else value.version
                    if requested != "latest_at_start" and requested != actual_version:
                        raise EngineError("agent.context_version", "State context version does not match")
                    item = {"kind": "context", "text": canonical_json(value).decode(), "source_version": actual_version, "locator": source["key"]}
                else:
                    raise EngineError("agent.validation", "Unsupported context-source kind")
                retained += len(canonical_json(item))
                if retained > limits["max_source_bytes"]:
                    raise EngineError("LIMIT_EXCEEDED", "Context sources exceed the cumulative byte allowance")
                result.append(item)
            except EngineError:
                if source.get("required", True):
                    raise
        return result

    async def admission_status(self, context, admission_id):
        try:
            context.authorize("admission.status", object_id=admission_id)
            self._prune_admissions()
            lease = self._admissions.get(admission_id)
            if lease is None:
                return Ok({"schema_version": 1, "admission_id": admission_id, "state": "unknown", "reservation_state": "unknown", "start_event_receipt": None, "terminal_event_receipt": None, "terminal_status": None, "error": None})
            if lease.context.run_id != context.run_id:
                raise EngineError("ACCESS_DENIED", "Admission belongs to another run")
            state = "expired" if lease.state == "reserved" and lease.context.remaining_seconds() <= 0 else lease.state
            return Ok({"schema_version": 1, "admission_id": admission_id, "state": state, "reservation_state": lease.reservation_state, "start_event_receipt": lease.start_receipt, "terminal_event_receipt": lease.terminal_receipt, "terminal_status": lease.terminal_status, "error": None})
        except EngineError as error:
            return Err(error)

    async def execute(self, admission_lease) -> AgentResult:
        lease = admission_lease
        if not isinstance(lease, AdmissionLease) or lease.owner is not self or self._admissions.get(lease.admission_id) is not lease:
            raise EngineError("ACCESS_DENIED", "Admission is not owned by this live runtime")
        async with lease.lock:
            if lease.state == "expired":
                # Status lookup or another admission may have pruned this
                # reservation first. Its retained owned identity still permits
                # one cleanup-only terminal, never renewed execution.
                lease.state = "consumed"
                return await self._finish_unstarted(lease, EngineError("DEADLINE_EXCEEDED", "Admission deadline elapsed"))
            if lease.state != "reserved":
                return AgentResult(lease.context.descriptor(), "failed", definition_ref=lease.definition.definition_ref, admission_id=lease.admission_id, error=EngineError("admission.consumed", "Admission is single-use"))
            try:
                lease.context.assert_active()
                lease.binding.lease.assert_active()
            except EngineError as error:
                if error.code in {"CANCELLED", "DEADLINE_EXCEEDED"}:
                    # This owned admission was accepted, but no execution or
                    # provider session started. Preserve a terminal fact that
                    # service consumers can reconstruct after restart.
                    lease.state = "consumed"
                    return await self._finish_unstarted(lease, error)
                lease.state = "expired" if error.code == "DEADLINE_EXCEEDED" else "released"
                lease.context.ledger.release_reserved(lease.reservation_id)
                lease.reservation_state = "released"
                return AgentResult(lease.context.descriptor(), status_for(error), definition_ref=lease.definition.definition_ref, admission_id=lease.admission_id, error=error)
            lease.state = "consumed"
        return await self._execute_consumed(lease)

    async def _finish_unstarted(self, lease, error):
        definition, binding, context = lease.definition, lease.binding, lease.context
        root_context = context.for_action(context.root_action_id, None)
        result = AgentResult(root_context.descriptor(), status_for(error),
            definition_ref=definition.definition_ref, admission_id=lease.admission_id,
            start_state="not_started", error=error,
            validation={"state": "not_run", "schema_digest": digest_json(definition.output_schema), "errors": []},
            counters={"model_calls": 0, "tool_calls": 0, "tool_attempts": 0, "repairs": 0, "elapsed_seconds": 0},
            usage={"known_subtotals": dict.fromkeys(TOKEN_COUNTS), "completeness": "unknown",
                   "unknown_attempt_ids": [], "per_attempt_usage_refs": []})
        result.terminal_state = {"schema_version": 1, "state": "terminal", "start_state": "not_started",
            "run_id": context.run_id, "root_run_id": context.root_run_id,
            "correlation_id": context.correlation_id, "root_action_id": context.root_action_id,
            "definition_ref": definition.definition_ref, "model_ref": definition.model_ref,
            "profile_ref": definition.profile_ref, "source_refs": [],
            "model_outcome_event_ids": [], "tool_outcome_event_ids": [], "limits_snapshot": lease.limits,
            "counters": result.counters, "usage": result.usage, "output_ref": None, "raw_output_ref": None,
            "persistence_state": result.persistence_state, "unfinished_actions": []}
        try:
            # Cleanup extends time only. It cannot revive a closed binding,
            # closed run lease, or revoked event-recording grant.
            binding.lease.assert_active()
            context.lease.assert_active()
            result.recording_status = "complete"
            terminal = await asyncio.shield(append_event(binding, root_context, "agent.finished", {
                "status": result.status, "start_state": "not_started", "recording_status": "complete",
                "error": result.error, "cleanup": result.cleanup,
                "output_ref": None, "raw_output_ref": None, "persistence_state": result.persistence_state,
                "output_publications": [], "validation": result.validation, "counters": result.counters,
                "usage": result.usage, "terminal_state": result.terminal_state,
            }, cleanup=True, cleanup_seconds=lease.limits["max_record_cleanup_seconds"]))
            if isinstance(terminal, Ok):
                result.terminal_event_receipt = lease.terminal_receipt = terminal.value
            else:
                result.recording_status = "unavailable" if terminal.error.code in {"ACCESS_DENIED", "SESSION_CLOSED"} else "incomplete"
                result.recording_error = terminal.error
        except EngineError as recording_error:
            result.recording_status = "unavailable"
            result.recording_error = recording_error
        finally:
            lease.context.ledger.release_reserved(lease.reservation_id)
            lease.reservation_state = "released"
            lease.state = "terminal"
            lease.terminal_status = result.status
            self._prune_admissions()
        return result

    async def _execute_consumed(self, lease):
        definition, binding, context, limits = lease.definition, lease.binding, lease.context, lease.limits
        root_context = context.for_action(context.root_action_id, None)
        result = AgentResult(root_context.descriptor(), "failed", definition_ref=definition.definition_ref, admission_id=lease.admission_id,
                             validation={"state": "not_run", "schema_digest": digest_json(definition.output_schema), "errors": []},
                             counters={"model_calls": 0, "tool_calls": 0, "tool_attempts": 0, "repairs": 0},
                             usage={"known_subtotals": dict.fromkeys(TOKEN_COUNTS), "completeness": "unknown", "unknown_attempt_ids": [], "per_attempt_usage_refs": []})
        session = None
        started_at = time.monotonic()
        model_events = []
        tool_events = []
        pending_cancellation = False
        try:
            start = await append_event(binding, root_context, "agent.started", {"definition_ref": definition.definition_ref, "admission": lease.descriptor(), "task_input_digest": digest_json(lease.task_input), "limits": limits})
            if isinstance(start, Err):
                result.recording_status = "incomplete"
                result.recording_error = result.error = start.error
                result.start_state = "unknown" if start.error.commit_state == "unknown" else "not_started"
                return result
            result.start_state = "started"
            result.start_event_receipt = lease.start_receipt = start.value
            result.recording_status = "complete"
            opened = await (binding.provider_factory or ProviderFactory).open(_provider_config(binding.provider_config), context)
            if isinstance(opened, Err):
                raise opened.error
            session = opened.value
            continuation = None
            tool_results = ()
            step = 0
            failed_source_requests = set()
            while True:
                context.assert_active()
                if result.counters["model_calls"] >= limits["max_model_calls"]:
                    raise EngineError("LIMIT_EXCEEDED", "Agent model-call allowance is exhausted")
                action = new_id("model_")
                attempt = new_id("attempt_")
                model_context = context.for_action(action, attempt)
                request = ModelRequest(definition.instructions, lease.task_input, lease.tools, context.run_id, digest_json(definition), step, continuation, tool_results,
                                       limits["max_output_tokens_per_call"], limits["max_model_request_bytes"], limits["max_model_response_bytes"], limits["max_continuation_bytes"], min(limits["max_model_seconds"], context.remaining_seconds()),
                                       definition.settings, {"mode": definition.output_mode, "schema": definition.output_schema, "native_enforcement": definition.output_contract.get("native_enforcement", "optional")}, lease.context_items,
                                       max_context_tokens=limits["max_context_tokens"])
                prepared = session.prepare(request, model_context)
                model_context.authorize("model.generate", object_id=_provider_config(binding.provider_config).model_id)
                if result.counters["model_calls"] == 0:
                    model_context.ledger.consume_reserved(lease.reservation_id)
                    lease.reservation_state = "consumed"
                else:
                    model_context.ledger.consume("model_calls")
                result.counters["model_calls"] += 1
                intent = await append_event(binding, model_context, "model.intent", {"step_index": step, "request_audit": prepared.audit, "request_digest": prepared.audit["request_body_digest"]})
                if isinstance(intent, Err):
                    result.recording_status = "incomplete"
                    result.recording_error = intent.error
                    result.unfinished_actions.append({"action_id": action, "attempt_id": attempt, "event_id": intent.error.details.get("event_id"), "operation_id": None, "phase": "intent_acknowledgement"})
                    raise intent.error
                dispatched = False
                try:
                    model_context.assert_active()
                    model_context.authorize("model.generate", object_id=_provider_config(binding.provider_config).model_id)
                    dispatched = True
                    response = await self._generate_cancel_aware(session, prepared, model_context)
                except EngineError as error:
                    usage = unknown_usage()
                    self._aggregate_usage(result, usage, attempt)
                    outcome = await append_event(binding, model_context, "model.outcome", {"step_index": step, "dispatched": dispatched, "status": status_for(error), "error": error, "request_audit": prepared.audit,
                                                "usage": usage, "provider_usage": provider_usage_projection(None)}, cleanup=True)
                    self._usage_receipt(result, outcome, model_context)
                    if isinstance(outcome, Err):
                        result.recording_status = "incomplete"
                        result.recording_error = outcome.error
                    raise
                except asyncio.CancelledError as cancellation:
                    received = cancellation.response if isinstance(cancellation, _ReceivedResponseCancellation) else None
                    usage = normalize_usage(received.usage) if received is not None else unknown_usage()
                    self._aggregate_usage(result, usage, attempt)
                    payload = self._model_outcome_payload(received, step, usage) if received is not None else {
                        "step_index": step, "dispatched": dispatched, "effect_state": "unknown",
                        "request_audit": prepared.audit, "usage": usage,
                        "provider_usage": provider_usage_projection(None),
                    }
                    payload["status"] = "cancelled"
                    outcome = await asyncio.shield(append_event(binding, model_context, "model.outcome", payload, cleanup=True))
                    self._usage_receipt(result, outcome, model_context)
                    if isinstance(outcome, Err):
                        result.recording_status = "incomplete"
                        result.recording_error = outcome.error
                    else:
                        model_events.append(outcome.value.event_id)
                    raise
                except Exception as exc:
                    usage = unknown_usage()
                    self._aggregate_usage(result, usage, attempt)
                    defect = EngineError("runtime.defect", "Model boundary raised an unexpected exception", {"exception_type": type(exc).__name__}, observed_effect_state="unknown" if dispatched else "not_observed")
                    outcome = await append_event(binding, model_context, "model.outcome", {"step_index": step, "dispatched": dispatched, "status": "failed", "error": defect, "request_audit": prepared.audit,
                                                "usage": usage, "provider_usage": provider_usage_projection(None)}, cleanup=True)
                    self._usage_receipt(result, outcome, model_context)
                    if isinstance(outcome, Err):
                        result.recording_status = "incomplete"
                        result.recording_error = outcome.error
                    raise
                usage = normalize_usage(response.usage)
                # Preserve the received observation even if Storage cannot
                # acknowledge it; recording failure still halts all new work.
                self._aggregate_usage(result, usage, attempt)
                outcome = await append_event(binding, model_context, "model.outcome", self._model_outcome_payload(response, step, usage), cleanup=True)
                self._usage_receipt(result, outcome, model_context)
                if isinstance(outcome, Err):
                    result.recording_status = "incomplete"
                    result.recording_error = outcome.error
                    result.unfinished_actions.append({"action_id": action, "attempt_id": attempt, "event_id": outcome.error.details.get("event_id"), "operation_id": None, "phase": "outcome_acknowledgement"})
                    raise outcome.error
                model_events.append(outcome.value.event_id)
                token_budget = limits["token_budget"]
                if token_budget and (result.usage["known_subtotals"]["total_tokens"] or 0) > token_budget["max_total_tokens"]:
                    raise EngineError("LIMIT_EXCEEDED", "Advisory token budget has been exceeded")
                context.assert_active()
                if response.completion in {"failed", "refused", "incomplete"}:
                    raise response.error or EngineError("provider.incomplete", "Provider did not return a complete outcome")
                continuation = response.continuation
                if response.completion == "tool_calls":
                    if result.counters["tool_calls"] + len(response.tool_calls) > limits["max_tool_calls"] or result.counters["tool_attempts"] + len(response.tool_calls) > limits["max_tool_attempts"] or context.ledger.remaining("tool_calls") < len(response.tool_calls):
                        raise EngineError("LIMIT_EXCEEDED", "Whole tool batch exceeds the remaining allowance")
                    requests = []
                    for call in response.tool_calls:
                        ref = next((t for t in definition.allowed_tools if t.name == call.name and str(t.revision) == str(call.revision)), None)
                        request_tool = ToolRequest(ref or ToolRef(call.name or call.provider_name, 1), call.arguments or {}, call.provider_call_id, model_action_id=action, model_attempt_id=attempt)
                        try:
                            fingerprint = (request_tool.tool.name, request_tool.tool.revision, digest_json(request_tool.arguments))
                            if fingerprint in failed_source_requests:
                                raise EngineError("tool.failed_request_replay", "Choose a different source or query; a failed read-only attempt cannot be replayed")
                            if call.argument_error is not None:
                                raise call.argument_error
                            if ref is None:
                                raise EngineError("tool.unauthorized", "Provider requested an unregistered tool")
                            await self.tool_action.preflight(request_tool, binding, context, allowed_tools=definition.allowed_tools)
                        except EngineError as error:
                            rejected = await self.tool_action.reject(request_tool, binding, context, error)
                            if rejected.recording.get("status") != "complete":
                                result.recording_status = "incomplete"
                                result.recording_error = rejected.recording.get("error")
                            raise
                        requests.append(request_tool)
                    new_results = []
                    for request_tool in requests:
                        context.assert_active()
                        tool_context = dataclasses.replace(context, deadline=deadline_after(min(context.remaining_seconds(), limits["max_tool_seconds"])), _monotonic_deadline=time.monotonic() + min(context.remaining_seconds(), limits["max_tool_seconds"]))
                        observed = await self.tool_action.run(request_tool, binding, tool_context, allowed_tools=definition.allowed_tools)
                        tool_cleanup = observed.process.get("cleanup", {})
                        if tool_cleanup.get("complete") is False or tool_cleanup.get("unconfirmed_resources"):
                            result.cleanup.complete = False
                            result.cleanup.errors.extend(tool_cleanup.get("errors", []))
                            result.cleanup.unconfirmed_resources.extend(resource for resource in tool_cleanup.get("unconfirmed_resources", []) if resource not in result.cleanup.unconfirmed_resources)
                        if observed.persistence.get("commit_state") == "unknown":
                            result.unfinished_actions.append({"action_id": observed.invocation.get("action_id"), "attempt_id": observed.invocation.get("attempt_id"),
                                                              "operation_id": observed.persistence.get("operation_id"), "phase": "tool_publication_commit"})
                        result.counters["tool_calls"] += 1
                        if observed.invocation.get("attempt_id") is not None:
                            result.counters["tool_attempts"] += 1
                        if observed.recording.get("status") != "complete":
                            result.recording_status = "incomplete"
                            result.recording_error = observed.recording.get("error") or EngineError("recording.incomplete", "Tool lifecycle recording is incomplete")
                            raise result.recording_error
                        if observed.event_ids.get("outcome"):
                            tool_events.append(observed.event_ids["outcome"])
                        model_error = observed.error
                        if observed.status != "succeeded":
                            resolved_definition = (await maybe_await(binding.catalog.resolve(request_tool.tool.name, request_tool.tool.revision))).unwrap()
                            if not self._recoverable_source_failure(observed, resolved_definition, definition, context, limits, result.counters):
                                raise observed.error or EngineError("tool.failed", "Tool execution failed")
                            failed_source_requests.add((request_tool.tool.name, request_tool.tool.revision, digest_json(request_tool.arguments)))
                            model_error = dataclasses.replace(observed.error, details={**observed.error.details,
                                "source_alternative_allowed": True, "retry_previous_attempt": False,
                                "recovery_instruction": "Choose another source URL or discovery query; do not replay this failed request."})
                        new_results.append({"provider_call_id": request_tool.provider_call_id, "tool": to_json_value(request_tool.tool), "status": observed.status, "result": observed.result if observed.status == "succeeded" else None, "error": to_json_value(model_error), "result_refs": []})
                    if len(canonical_json(new_results)) > limits["max_tool_context_bytes"]:
                        raise EngineError("LIMIT_EXCEEDED", "Tool results exceed the model-context allowance")
                    tool_results = tuple(new_results)
                    step += 1
                    continue
                if response.raw_visible_text is None:
                    raise EngineError("provider.protocol", "Final visible content is missing")
                raw = response.raw_visible_text.encode("utf-8")
                if len(raw) > limits["max_final_output_bytes"]:
                    raise EngineError("LIMIT_EXCEEDED", "Final output exceeds its byte allowance")
                try:
                    value = strict_json_loads(raw, max_bytes=limits["max_final_output_bytes"]) if definition.output_mode == "json" else response.raw_visible_text
                    errors = validation_errors(definition.output_schema, value)
                except ValueError:
                    value, errors = None, [{"path": [], "validator": "strict_json"}]
                result.observed_output = {"mode": definition.output_mode, "raw_visible_text": response.raw_visible_text, "parsed_value": value if definition.output_mode == "json" else None, "validation_state": "failed" if errors else "passed", "byte_length": len(raw), "sha256": digest_bytes(raw)}
                result.validation["state"] = "failed" if errors else "passed"
                result.validation["errors"] = errors
                if errors:
                    raise EngineError("agent.validation", "Final output failed its registered schema", {"errors": errors})
                validated = canonical_json(value) if definition.output_mode == "json" else raw
                if len(validated) > limits["max_final_output_bytes"]:
                    raise EngineError("LIMIT_EXCEEDED", "Validated output exceeds its byte allowance")
                await self._publish_output(result, binding, root_context, raw, validated, value, definition)
                result.status = "succeeded"
                break
        except EngineError as error:
            result.status = status_for(error)
            result.error = error
        except (ValueError, TypeError) as exc:
            result.status = "validation_failed"
            result.error = EngineError("agent.validation", "Runtime validation failed", {"exception_type": type(exc).__name__})
        except asyncio.CancelledError:
            result.status = "cancelled"
            result.error = EngineError("CANCELLED", "Caller task was cancelled", observed_effect_state="unknown")
            pending_cancellation = True
        except Exception as exc:
            result.status = "failed"
            result.error = EngineError("runtime.defect", "Runtime raised an unexpected exception", {"exception_type": type(exc).__name__})
            raise
        finally:
            if session is not None:
                try:
                    async with asyncio.timeout(limits["max_cleanup_seconds"]):
                        await asyncio.shield(session.aclose())
                except (TimeoutError, EngineError) as error:
                    result.cleanup.complete = False
                    result.cleanup.errors.append(EngineError("cleanup.provider", "Provider cleanup did not confirm closure", {"exception_type": type(error).__name__}))
                    result.cleanup.unconfirmed_resources.append("provider_session")
            result.counters["elapsed_seconds"] = time.monotonic() - started_at
            if result.start_state == "started":
                result.terminal_state = {"schema_version": 1, "state": "terminal", "run_id": context.run_id, "root_run_id": context.root_run_id,
                                         "correlation_id": context.correlation_id, "root_action_id": context.root_action_id, "definition_ref": definition.definition_ref,
                                         "model_ref": definition.model_ref, "profile_ref": definition.profile_ref, "source_refs": [item.get("source_ref") for item in lease.context_items],
                                         "model_outcome_event_ids": model_events, "tool_outcome_event_ids": tool_events, "limits_snapshot": limits,
                                         "counters": result.counters, "usage": result.usage, "output_ref": result.output_ref, "raw_output_ref": result.raw_output_ref,
                                         "persistence_state": result.persistence_state, "unfinished_actions": result.unfinished_actions}
                terminal = await asyncio.shield(append_event(binding, root_context, "agent.finished", {"status": result.status, "recording_status": result.recording_status,
                                            "error": result.error, "cleanup": result.cleanup, "output_ref": result.output_ref, "raw_output_ref": result.raw_output_ref,
                                            "persistence_state": result.persistence_state, "output_publications": result.output_publications,
                                            "validation": result.validation, "counters": result.counters, "usage": result.usage, "terminal_state": result.terminal_state}, cleanup=True))
                if isinstance(terminal, Ok):
                    result.terminal_event_receipt = lease.terminal_receipt = terminal.value
                else:
                    result.recording_status = "incomplete"
                    result.recording_error = terminal.error
            lease.state = "unknown" if result.start_state == "unknown" else "terminal"
            lease.terminal_status = result.status
            if lease.state != "unknown":
                context.ledger.release_reserved(lease.reservation_id)
                if lease.reservation_state == "reserved":
                    lease.reservation_state = "released"
            self._prune_admissions()
        if len(canonical_json(result)) > limits["max_public_result_bytes"]:
            result.output = None
            result.observed_output = None
            result.output_delivery = "artifact" if result.output_ref is not None else "none"
        if pending_cancellation:
            raise asyncio.CancelledError
        return result

    @staticmethod
    def _recoverable_source_failure(observed, tool_definition, definition, context, limits, counters):
        if definition.error_policy.get("recoverable_tool_errors", "return_to_model") != "return_to_model" or observed.error is None:
            return False
        # Only the declared read-only network/read surface qualifies. Local snapshot
        # publication must be known uncommitted; no write uncertainty is concealed.
        capabilities = set(tool_definition.capabilities)
        if not capabilities or not capabilities <= {"network.search", "network.fetch", "snapshot.read", "snapshot.commit"}:
            return False
        cleanup = observed.process.get("cleanup", {})
        if cleanup.get("complete") is not True or cleanup.get("unconfirmed_resources"):
            return False
        if observed.persistence.get("commit_state") not in {"not_committed", "not_applicable"} or observed.error.commit_state in {"unknown", "committed"}:
            return False
        if observed.recording.get("status") != "complete" or observed.status == "cancelled":
            return False
        try:
            context.assert_active()
        except EngineError:
            return False
        if counters["model_calls"] >= limits["max_model_calls"] or counters["tool_calls"] >= limits["max_tool_calls"] or counters["tool_attempts"] >= limits["max_tool_attempts"]:
            return False
        if context.ledger.remaining("model_calls") <= 0 or context.ledger.remaining("tool_calls") <= 0:
            return False
        error = observed.error
        if error.code == "LIMIT_EXCEEDED" and error.details.get("kind"):
            return False
        reason = observed.process.get("termination_reason")
        return error.code in RECOVERABLE_SOURCE_ERRORS or (error.code == "LIMIT_EXCEEDED" and reason == "stream_limit") or (error.code == "MEMORY_LIMIT" and reason == "memory_limit") or (error.code == "DEADLINE_EXCEEDED" and reason == "deadline")

    @staticmethod
    def _model_outcome_payload(response, step, usage):
        return {"step_index": step, "dispatched": response.dispatched,
                "completion": response.completion, "native_finish_reason": response.native_finish_reason,
                "request_audit": response.request_audit, "usage": usage, "provider_usage": response.provider_usage,
                "tool_calls": [{"provider_call_id": c.provider_call_id, "index": c.index, "provider_name": c.provider_name,
                                "tool": {"name": c.name, "revision": c.revision},
                                "arguments_digest": digest_bytes(c.arguments_json.encode()), "argument_error": c.argument_error}
                               for c in response.tool_calls],
                "visible_text_sha256": digest_bytes((response.raw_visible_text or "").encode()), "error": response.error}

    @staticmethod
    async def _generate_cancel_aware(session, prepared, context):
        generation = asyncio.create_task(session.generate(prepared, context))
        cancelled = asyncio.create_task(context.cancellation.wait())
        try:
            try:
                done, _ = await asyncio.wait({generation, cancelled}, return_when=asyncio.FIRST_COMPLETED)
                if generation in done:
                    return await generation
                if cancelled in done and context.cancellation.is_set():
                    generation.cancel()
                    await asyncio.gather(generation, return_exceptions=True)
                    if not generation.cancelled():
                        return await generation
                    raise EngineError("CANCELLED", "Engine cancellation interrupted the provider request; remote completion is unknown", observed_effect_state="unknown")
                return await generation
            finally:
                cancelled.cancel()
                if not generation.done():
                    generation.cancel()
                await asyncio.gather(generation, cancelled, return_exceptions=True)
        except asyncio.CancelledError as cancellation:
            # Caller cancellation can interrupt either the wait or its final
            # cleanup after generation has already returned. Preserve those
            # received facts for the runtime's cancelled outcome, then stop.
            if generation.done() and not generation.cancelled():
                try:
                    response = generation.result()
                except (Exception, asyncio.CancelledError):
                    pass
                else:
                    if isinstance(response, ModelResponse):
                        raise _ReceivedResponseCancellation(response, cancellation) from None
            raise

    @staticmethod
    def _aggregate_usage(result, usage, attempt):
        usage = normalize_usage(usage)
        if usage["completeness"] != "complete" and attempt not in result.usage["unknown_attempt_ids"]:
            result.usage["unknown_attempt_ids"].append(attempt)
        for key in TOKEN_COUNTS:
            count = usage[key]
            if count is not None:
                result.usage["known_subtotals"][key] = (result.usage["known_subtotals"][key] or 0) + count
        Runtime._usage_completeness(result)

    @staticmethod
    def _usage_completeness(result):
        known = sum(result.usage["known_subtotals"][key] is not None for key in PRIMARY_COUNTS)
        result.usage["completeness"] = "complete" if known == 3 and not result.usage["unknown_attempt_ids"] else "partial" if known else "unknown"

    @staticmethod
    def _usage_receipt(result, outcome, context):
        if isinstance(outcome, Ok):
            result.usage["per_attempt_usage_refs"].append({"store_id": outcome.value.store_id, "event_id": outcome.value.event_id,
                                                         "action_id": context.action_id, "attempt_id": context.attempt_id})
        elif context.attempt_id not in result.usage["unknown_attempt_ids"]:
            result.usage["unknown_attempt_ids"].append(context.attempt_id)
        Runtime._usage_completeness(result)

    @staticmethod
    async def _publish_output(result, binding, context, raw, validated, value, definition):
        scope = getattr(binding, "output_scope", None) or context.scope
        result.persistence_state = "not_committed"
        refs = {}
        for role, data, media in (("raw", raw, "application/json" if definition.output_mode == "json" else definition.output_media_type), ("validated", validated, definition.output_media_type)):
            if role == "validated" and validated == raw:
                refs[role] = refs["raw"]
                continue
            context.assert_active()
            operation = new_id("output_")
            publication = {"role": role, "operation_id": operation, "artifact_ref": None, "receipt": None, "commit_state": "not_committed"}
            result.output_publications.append(publication)
            try:
                written = await binding.artifacts.put(context, operation, scope, data, {"media_type": media, "filename": "report.md" if media == "text/markdown" else "output.json" if media == "application/json" else "output.txt", "metadata": {"role": role, "run_id": context.run_id}})
            except asyncio.CancelledError:
                publication["commit_state"] = result.persistence_state = "unknown"
                result.recording_status = "incomplete"
                result.unfinished_actions.append({"action_id": context.action_id, "attempt_id": context.attempt_id, "event_id": None, "operation_id": operation, "phase": "output_publication"})
                raise
            if isinstance(written, Err):
                if written.error.commit_state == "unknown" and binding.storage is not None:
                    checked = await binding.storage.operations.status(context.for_cleanup(), operation)
                    if isinstance(checked, Ok) and checked.value.state == "committed" and checked.value.receipt is not None:
                        written = Ok(checked.value.receipt)
            if isinstance(written, Err):
                publication["commit_state"] = written.error.commit_state
                result.persistence_state = "unknown" if written.error.commit_state == "unknown" else "not_committed"
                if result.persistence_state == "unknown":
                    result.recording_status = "incomplete"
                raise written.error
            receipt = written.value
            publication.update({"artifact_ref": receipt.artifact_ref, "receipt": receipt, "commit_state": "committed"})
            refs[role] = receipt.artifact_ref
            if role == "raw":
                result.raw_output_ref = receipt.artifact_ref
            else:
                result.output_ref = receipt.artifact_ref
        result.raw_output_ref = refs["raw"]
        result.output_ref = refs["validated"]
        result.persistence_state = "committed"
        result.output_delivery = "artifact" if definition.output_contract.get("delivery") == "artifact" else "inline"
        result.output = None if result.output_delivery == "artifact" else value
        result.output_metadata = {"mode": definition.output_mode, "media_type": definition.output_media_type, "byte_length": len(validated), "sha256": digest_bytes(validated), "raw_media_type": "application/json" if definition.output_mode == "json" else definition.output_media_type, "raw_byte_length": len(raw), "raw_sha256": digest_bytes(raw)}
