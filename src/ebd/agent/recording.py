"""Canonical committed-intent boundary shared by agents and standalone tools."""
from __future__ import annotations

import asyncio
import inspect
from typing import Any

from ebd.contracts import (
    EngineError, Err, ExecutionEvent, Ok, ToolRequest, ToolResult,
    canonical_json, digest_bytes, digest_json, new_id, to_json_value,
)
from .validation import validation_errors


async def maybe_await(value):
    return await value if inspect.isawaitable(value) else value


def status_for(error: EngineError) -> str:
    if error.code in {"DEADLINE_EXCEEDED", "provider.timeout"}:
        return "timed_out"
    if error.code == "CANCELLED":
        return "cancelled"
    if error.code in {"LIMIT_EXCEEDED", "LIMIT_EXHAUSTED"}:
        return "limit_exhausted"
    if error.code in {"INVALID_DATA", "tool.invalid_arguments", "agent.validation"}:
        return "validation_failed"
    return "failed"


async def append_event(binding, context, kind, payload, *, cleanup=False, event_id=None, cleanup_seconds=5):
    """A lost acknowledgement reconciles this identity; it never repeats dispatch."""
    event = ExecutionEvent(event_id or new_id("event_"), kind, "runtime", context, to_json_value(payload))
    record_context = context.for_cleanup(min(cleanup_seconds, getattr(binding, "record_cleanup_seconds", 5))) if cleanup else context
    result = await binding.recorder.append(record_context, event)
    if isinstance(result, Ok):
        return result
    result.error.details.setdefault("event_id", event.event_id)
    if result.error.commit_state == "unknown" or result.error.retryable_delivery:
        status = await binding.recorder.status(record_context, event.event_id, digest_json(event))
        if isinstance(status, Ok):
            value = status.value
            receipt = value.get("receipt") if isinstance(value, dict) else getattr(value, "receipt", None)
            phase = value.get("state", value.get("phase")) if isinstance(value, dict) else getattr(value, "state", None)
            if receipt is not None and phase in {"committed", "recorded", "succeeded"}:
                return Ok(receipt)
    return result


class RecordedToolAction:
    async def reject(self, request, binding, context, error):
        action_id = context.action_id if context.context_kind == "standalone_tool" else new_id("tool_")
        rejected = await append_event(binding, context.for_action(action_id, None), "tool.rejected", {
            "tool": request.tool, "provider_call_id": request.provider_call_id,
            "model_action_id": request.model_action_id, "model_attempt_id": request.model_attempt_id,
            "error": error, "status": status_for(error), "dispatched": False,
        }, cleanup=True)
        return ToolResult(request.tool, {"action_id": action_id, "attempt_id": None, "dispatched": False}, status_for(error), error=error,
                          recording={"status": "complete" if isinstance(rejected, Ok) else "incomplete", "error": rejected.error if isinstance(rejected, Err) else None},
                          event_ids={"rejected": rejected.value.event_id if isinstance(rejected, Ok) else None})

    async def preflight(self, request: ToolRequest, binding, context, *, allowed_tools=None):
        context.assert_active()
        canonical_json(request.arguments, max_bytes=65536)
        if context.context_kind == "agent" and not all((request.provider_call_id, request.model_action_id, request.model_attempt_id)):
            raise EngineError("tool.invalid_arguments", "Agent tool requests require native and causal model identities")
        if context.context_kind == "standalone_tool" and any((request.provider_call_id, request.model_action_id, request.model_attempt_id)):
            raise EngineError("tool.invalid_arguments", "Standalone tool requests cannot invent model identities")
        if allowed_tools is not None and request.tool not in allowed_tools:
            raise EngineError("tool.unauthorized", "Requested tool is outside the agent allowance")
        resolved = await maybe_await(binding.catalog.resolve(request.tool.name, request.tool.revision))
        if isinstance(resolved, Err):
            raise resolved.error
        definition = resolved.value if isinstance(resolved, Ok) else resolved
        errors = validation_errors(definition.input_schema, request.arguments)
        if errors:
            raise EngineError("tool.invalid_arguments", "Tool arguments failed the registered schema", {"errors": errors})
        if hasattr(binding.catalog, "validate_arguments"):
            await maybe_await(binding.catalog.validate_arguments(definition, request.arguments))
        context.authorize("tool.execute", object_id=definition.name)
        if context.ledger.remaining("tool_calls") <= 0:
            raise EngineError("LIMIT_EXCEEDED", "Shared tool dispatch allowance is exhausted")
        return definition

    async def run(self, request: ToolRequest, binding, context, *, allowed_tools=None) -> ToolResult:
        action_id = context.action_id if context.context_kind == "standalone_tool" else new_id("tool_")
        preflight_context = context.for_action(action_id, None)
        try:
            definition = await self.preflight(request, binding, preflight_context, allowed_tools=allowed_tools)
        except (EngineError, ValueError) as exc:
            error = exc if isinstance(exc, EngineError) else EngineError("tool.invalid_arguments", "Tool preflight failed", {"exception_type": type(exc).__name__})
            return await self.reject(request, binding, preflight_context, error)
        attempt_id = new_id("attempt_")
        attempt_context = context.for_action(action_id, attempt_id)
        intent = outcome = None
        plan = None
        observed = None
        dispatched = False
        try:
            attempt_context.assert_active()
            attempt_context.ledger.consume("tool_calls")
            plan = await maybe_await(binding.storage_plan_factory.for_attempt(definition, request.arguments, attempt_context))
            if isinstance(plan, Err):
                raise plan.error
            if isinstance(plan, Ok):
                plan = plan.value
            intent = await append_event(binding, attempt_context, "tool.intent", {
                "tool": request.tool, "arguments": request.arguments if len(canonical_json(request.arguments)) <= 16384 else None,
                "arguments_digest": digest_json(request.arguments),
                "provider_call_id": request.provider_call_id,
                "model_action_id": request.model_action_id, "model_attempt_id": request.model_attempt_id,
                "operation_id": getattr(plan, "operation_id", None),
            })
            if isinstance(intent, Err):
                return ToolResult(request.tool, {"action_id": action_id, "attempt_id": attempt_id, "dispatched": False}, "failed", error=intent.error,
                                  recording={"status": "incomplete", "error": intent.error}, event_ids={})
            attempt_context.assert_active()
            attempt_context.authorize("tool.execute", object_id=definition.name)
            plan.lease.mark_recorded(intent.value)
            # Reads and worker launching are downstream of the acknowledged intent.
            dispatched = True
            observed = await binding.executor.execute(definition, request.arguments, attempt_context, plan)
            encoded_result = canonical_json(observed.result)
            result_descriptor = {"sha256": digest_json(observed.result), "encoded_byte_length": len(encoded_result)}
            if isinstance(observed.result, dict):
                for key in ("snapshot_ref", "actual_range", "returned_range", "requested_range", "extraction_version", "normalization_version", "spans", "next_position", "has_more_in_requested_range", "has_more_in_document", "byte_length", "url", "source_url", "continuation", "truncated"):
                    if key in observed.result:
                        result_descriptor[key] = observed.result[key]
                if isinstance(observed.result.get("text"), str):
                    result_descriptor["text_sha256"] = digest_bytes(observed.result["text"].encode("utf-8"))
            if len(canonical_json(result_descriptor)) > 8192:
                spans = result_descriptor.pop("spans", None)
                if spans is not None:
                    result_descriptor["spans_digest"] = digest_json(spans)
                    result_descriptor["spans_count"] = len(spans)
                for key in ("continuation", "url", "source_url"):
                    if len(canonical_json(result_descriptor)) <= 8192:
                        break
                    if key in result_descriptor:
                        value = result_descriptor.pop(key)
                        result_descriptor[key + "_digest"] = digest_json(value)
                if len(canonical_json(result_descriptor)) > 16384:
                    raise EngineError("recording.descriptor_limit", "Required tool evidence descriptor exceeds its recording allowance")
            outcome = await append_event(binding, attempt_context, "tool.outcome", {
                "tool": request.tool, "provider_call_id": request.provider_call_id,
                "dispatched": bool(observed.process.get("dispatched", False)), "status": observed.status, "result_descriptor": result_descriptor,
                "model_action_id": request.model_action_id, "model_attempt_id": request.model_attempt_id,
                "error": observed.error, "observations": observed.observations,
                "process": observed.process, "persistence": observed.persistence,
                "intent_receipt": intent.value,
            }, cleanup=True)
            return ToolResult(
                tool=observed.tool, invocation=observed.invocation, status=observed.status,
                result=observed.result, error=observed.error, observations=observed.observations,
                process=observed.process, usage=observed.usage, persistence=observed.persistence,
                recording={"status": "complete" if isinstance(outcome, Ok) else "incomplete", "error": outcome.error if isinstance(outcome, Err) else None},
                event_ids={"intent": intent.value.event_id, "outcome": outcome.value.event_id if isinstance(outcome, Ok) else None},
            )
        except asyncio.CancelledError:
            await asyncio.shield(append_event(binding, attempt_context, "tool.outcome", {"tool": request.tool, "status": "cancelled", "dispatched": dispatched, "effect_state": "unknown" if dispatched else "not_observed"}, cleanup=True))
            raise
        except EngineError as error:
            if isinstance(intent, Ok):
                outcome = await append_event(binding, attempt_context, "tool.outcome", {"tool": request.tool, "status": status_for(error), "dispatched": dispatched, "error": error}, cleanup=True)
            return ToolResult(request.tool, {"action_id": action_id, "attempt_id": attempt_id, "dispatched": dispatched}, status_for(error), error=error,
                              recording={"status": "complete" if isinstance(outcome, Ok) else "incomplete", "error": outcome.error if isinstance(outcome, Err) else None},
                              event_ids={"intent": intent.value.event_id if isinstance(intent, Ok) else None, "outcome": outcome.value.event_id if isinstance(outcome, Ok) else None})
        except Exception as exc:
            if isinstance(intent, Ok):
                await append_event(binding, attempt_context, "tool.outcome", {"tool": request.tool, "status": "failed", "dispatched": dispatched, "error": EngineError("runtime.defect", "Tool boundary raised an unexpected exception", {"exception_type": type(exc).__name__}, observed_effect_state="unknown" if dispatched else "not_observed")}, cleanup=True)
            raise
        finally:
            if plan is not None and getattr(plan, "lease", None) is not None:
                plan.lease.release()
