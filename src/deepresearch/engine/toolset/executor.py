"""Parent mediation; only an acknowledged live attempt can reach a worker."""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import math
import time

from jsonschema import Draft202012Validator

from deepresearch.engine.contracts import (CleanupReport, EngineError, Err, Ok, SnapshotProposal, SnapshotRef,
    ToolExecutionResult, ToolRef, new_id)

from .catalog import ToolCatalog
from .common import LIMITS, ToolFault, closed, encode, strict_json, validate_arguments, wire
from .common import digest
from .process import ProcessRunner
from .retrieval import unpack_component
from .scholarly import ProviderQuota, parse_limits, provider_plan, request_url, validate_schema
from .search import search_plan


def invocation(context):
    return {key: getattr(context, key) for key in ("run_id", "root_run_id", "correlation_id", "action_id", "attempt_id", "context_kind")}


def fault_error(fault):
    if isinstance(fault, EngineError): return fault
    return EngineError(fault.code, fault.message, fault.details, observed_effect_state="unknown")


def terminal(error):
    if error.code in {"CANCELLED"}: return "cancelled"
    if error.code in {"DEADLINE_EXCEEDED"}: return "timed_out"
    if error.code in {"LIMIT_EXCEEDED", "SCHOLAR_QUOTA_EXHAUSTED"}: return "limit_exhausted"
    return "failed"


class ToolExecutor:
    def __init__(self, catalog=None, *, openalex_admission=False, fetch_concurrency=1, memory_bytes=512 << 20,
                 quota_checkpoint=None, quota_checkpoint_sink=None, searxng_url="http://127.0.0.1:18888"):
        if type(fetch_concurrency) is not int or not 1 <= fetch_concurrency <= 2:
            raise ValueError("fetch concurrency must be one or two after measurement")
        self.catalog = catalog or ToolCatalog()
        self.runner = ProcessRunner(memory_bytes=memory_bytes)
        from .search_service import service_endpoint
        self.searxng_url = service_endpoint(searxng_url)
        self.quotas = {"crossref": ProviderQuota("crossref"), "openalex": ProviderQuota("openalex", anonymous_admission=openalex_admission)}
        self._quota_sink = quota_checkpoint_sink
        if quota_checkpoint is not None:
            closed(quota_checkpoint, {"schema_version", "owner_scope", "providers"})
            if quota_checkpoint["schema_version"] != 1 or quota_checkpoint["owner_scope"] != "executor_local" or set(quota_checkpoint["providers"]) != set(self.quotas):
                raise ValueError("Invalid trusted executor quota checkpoint")
            for provider, state in quota_checkpoint["providers"].items(): self.quotas[provider].restore_checkpoint(state)
        self._attempts = set()
        self._fetch = asyncio.Semaphore(fetch_concurrency)
        self._closed = False

    def export_quota_checkpoint(self):
        return {"schema_version": 1, "owner_scope": "executor_local",
            "providers": {provider: quota.export_checkpoint() for provider, quota in self.quotas.items()}}

    def execution_policy(self, definition):
        if definition.name == 'web.fetch' and definition.revision == 3:
            return {'id': 'adaptive/2', 'phases': ['static', 'optional_render'],
                'max_worker_dispatches': 2, 'max_snapshot_commits': 1,
                'http_request_limit': 40, 'decoded_byte_limit': 32 << 20,
                'work_seconds_limit': LIMITS['work_seconds'],
                'stdout_bytes_limit': LIMITS['fetch_stdout_bytes'], 'stderr_bytes_limit': LIMITS['stderr_bytes']}
        return None

    async def _persist_quota(self):
        if self._quota_sink is None: return
        value = self._quota_sink(self.export_quota_checkpoint())
        if inspect.isawaitable(value): value = await value
        if isinstance(value, Err): raise value.error

    async def _snapshot_commit(self, plan, context, proposal):
        """Reconcile only the same admitted ID; a lost reply never launches again."""
        try:
            committed = await plan.snapshot_store.commit(context, plan.operation_id, plan.scope, proposal)
        except OSError:
            committed = Err(EngineError("STORAGE_UNAVAILABLE", "Snapshot acknowledgment was lost",
                {"operation_id": plan.operation_id}, commit_state="unknown", retryable_delivery=True))
        if isinstance(committed, Err) and committed.error.commit_state == "unknown" and plan.operation_store is not None:
            try:
                status = await plan.operation_store.status(context.for_cleanup(seconds=5), plan.operation_id)
                if isinstance(status, Ok) and status.value.state == "committed" and status.value.receipt is not None:
                    return Ok(status.value.receipt)
                if isinstance(status, Ok) and status.value.commit_state == "not_committed":
                    committed.error.commit_state = "not_committed"
            except (EngineError, OSError): pass
        return committed

    async def execute(self, definition, arguments, context, storage_plan):
        result = ToolExecutionResult(tool=ToolRef(definition.name, definition.revision), invocation=invocation(context), status="failed",
            process={"dispatched": False, "exit_code": None, "termination_reason": None,
                "stdin_bytes": 0, "stdout_bytes": 0, "stderr_bytes": 0, "stderr_truncated": False,
                "cleanup": {"complete": True, "errors": [], "unconfirmed_resources": []}})
        result.usage = dict.fromkeys({"duration_ms", "search_backend_attempts", "http_request_count", "http_response_count", "decoded_body_bytes", "text_utf8_bytes", "monetary_cost"})
        quota = None; reservation = None; quota_acquired = False; settled = False
        process = None
        started = time.monotonic()
        try:
            if self._closed: raise ToolFault("EXECUTOR_CLOSED", "Tool executor is closed")
            resolved = self.catalog.resolve(definition.name, definition.revision)
            if isinstance(resolved, Err): raise resolved.error
            if wire(definition) != wire(resolved.value): raise ToolFault("TOOL_DEFINITION_MISMATCH", "Definition differs from immutable registry")
            if not isinstance(storage_plan.tool, ToolRef) or storage_plan.tool != definition.ref or storage_plan.context is not context:
                raise ToolFault("ACCESS_DENIED", "Storage plan is not bound to this live attempt")
            storage_plan.assert_recorded()
            if storage_plan.dispatch_policy != self.execution_policy(definition):
                raise ToolFault('ACCESS_DENIED', 'Tool phases differ from their recorded dispatch policy')
            if storage_plan.lease.context is not context or not context.attempt_id:
                raise ToolFault("ACCESS_DENIED", "Attempt lease is not bound to this execution")
            context.authorize("tool.execute", object_id=definition.name)
            key = (context.run_id, context.action_id, context.attempt_id)
            if key in self._attempts: raise ToolFault("ATTEMPT_REUSED", "A recorded logical tool attempt cannot execute twice")
            arguments = validate_arguments(definition.name, arguments, definition.revision)
            if list(Draft202012Validator(definition.input_schema).iter_errors(arguments)):
                raise ToolFault("INVALID_ARGUMENT", "Arguments do not match the registered schema", status="validation_failed")
            self._attempts.add(key)
            limits = dict(LIMITS)
            if set(storage_plan.limits) - set(LIMITS): raise ToolFault("INVALID_ARGUMENT", "Unknown tool limit", status="validation_failed")
            for name, value in storage_plan.limits.items():
                if type(value) is not int or not 0 < value <= limits[name]: raise ToolFault("INVALID_ARGUMENT", "Bound limit must narrow the registered profile", status="validation_failed")
                limits[name] = value
            if storage_plan.request and validate_arguments(definition.name, storage_plan.request, definition.revision) != arguments:
                raise ToolFault("ACCESS_DENIED", "Frozen plan request differs from public arguments")
            if definition.name == "web.search":
                context.authorize("network.search"); plan = search_plan(definition.revision, service_url=self.searxng_url)
            elif definition.name.startswith("scholar."):
                context.authorize("network.search")
                provider = definition.name.split(".")[1]
                request_url(provider, arguments)  # encoded URL validation before quota/dispatch
                quota = self.quotas[provider]; reservation = context.action_id + ":" + context.attempt_id
                await quota.acquire(reservation, context); quota_acquired = True
                await self._persist_quota()  # trusted owner persists pessimistic reservation before dispatch
                plan = provider_plan(provider, reservation)
            elif definition.name == "web.fetch":
                context.authorize("network.fetch")
                if not storage_plan.operation_id or storage_plan.scope is None or storage_plan.snapshot_store is None:
                    raise ToolFault("ACCESS_DENIED", "Fetch has no bound snapshot publication plan")
                plan = {"kind": "fetch", "operation_id": storage_plan.operation_id, "representation": "content_decoded",
                    "extraction_config_ref": "static/1", "normalization_version": "lf/1"}
                if definition.revision >= 2:
                    plan.update(representation="selected_capture", extraction_config_ref="adaptive/1")
                result.persistence = {"required": True, "operation_id": storage_plan.operation_id, "commit_state": "not_committed", "receipt": None}
            else:
                if storage_plan.snapshot_store is None: raise ToolFault("ACCESS_DENIED", "Read has no scoped snapshot client")
                reference = SnapshotRef(**arguments["snapshot_ref"])
                value = await storage_plan.snapshot_store.read(context, reference, arguments["range"], arguments["max_text_bytes"], arguments["continuation"])
                if isinstance(value, Err): raise value.error
                plan = {"kind": "read", "slice": wire(value.value)}
            context.assert_active(); storage_plan.assert_recorded()
            work = min(float(limits["work_seconds"]), context.remaining_seconds())
            if not math.isfinite(work): work = float(limits["work_seconds"])
            from deepresearch.engine.contracts import deadline_after
            request = {"schema_version": 1, "message_type": "worker_request", "request_id": new_id("worker_"),
                "tool": wire(definition.ref), "invocation": invocation(context), "arguments": arguments,
                "execution": {"deadline_utc": deadline_after(work), "limits": limits}, "plan": plan}
            payload = encode(request, limits["stdin_bytes"])
            cap = limits["fetch_stdout_bytes"] if definition.name == "web.fetch" else limits["stdout_bytes"]
            async def dispatch():
                context.assert_active(); storage_plan.assert_recorded()
                result.process["dispatched"] = True
                return await self.runner.run(definition.argv, payload, timeout=min(work, context.remaining_seconds()),
                    stdout_cap=cap, stderr_cap=limits["stderr_bytes"], context_cancelled=context.cancellation.is_set)
            supervised_response = None
            if definition.name == "web.fetch":
                while self._fetch.locked():
                    context.assert_active(); await asyncio.sleep(.02)
                async with self._fetch:
                    if definition.revision == 3:
                        from .fetch_supervisor import supervise
                        async def dispatch_stage(bound, data, seconds, stdout_cap, stderr_cap):
                            context.assert_active(); storage_plan.assert_recorded()
                            result.process['dispatched'] = True
                            return await self.runner.run(definition.argv, data,
                                timeout=min(seconds, context.remaining_seconds()), stdout_cap=stdout_cap,
                                stderr_cap=stderr_cap, context_cancelled=context.cancellation.is_set)
                        def observe_stage(row):
                            stages = result.process.setdefault('stages', [])
                            stages.append(row)
                            result.process['dispatched'] = any(s['dispatched'] for s in stages)
                            result.process.update(exit_code=row['exit_code'], termination_reason=row['termination_reason'],
                                cleanup={'complete': all(s['cleanup_complete'] for s in stages),
                                    'errors': [], 'unconfirmed_resources': [] if all(s['cleanup_complete'] for s in stages) else ['worker-tree-or-pipes']},
                                total_stdout_bytes=sum(s['stdout_bytes'] for s in stages),
                                total_stderr_bytes=sum(s['stderr_bytes'] for s in stages))
                            result.observations['resources'] = {
                                key: max((s[key] for s in stages if s[key] is not None), default=None)
                                for key in ('peak_job_memory_bytes', 'peak_process_memory_bytes')}
                            result.observations['resources'].update(job_memory_ceiling_bytes=self.runner.memory_bytes,
                                memory_scope='WindowsJob' if any(s['peak_job_memory_bytes'] is not None for s in stages) else 'unmeasured')
                        process, request, supervised_response, selected_stage = await supervise(
                            request, definition, limits, context, dispatch_stage, observe_stage)
                        result.process['selected_stage'] = selected_stage
                    else:
                        process = await dispatch()
            else: process = await dispatch()
            result.process.update(exit_code=process.exit_code, termination_reason=process.termination_reason,
                stdin_bytes=process.stdin_bytes, stdout_bytes=process.stdout_bytes, stderr_bytes=process.stderr_bytes,
                stderr_truncated=process.stderr_bytes > limits["stderr_bytes"], cleanup={"complete": process.cleanup_complete,
                    "errors": [], "unconfirmed_resources": [] if process.cleanup_complete else ["worker-tree-or-pipes"]})
            if process.termination_reason == "spawn_failed" and process.pid is None:
                result.process["dispatched"] = False
            result.observations.setdefault("resources", {"peak_job_memory_bytes": process.peak_job_memory_bytes,
                "peak_process_memory_bytes": process.peak_process_memory_bytes, "job_memory_ceiling_bytes": self.runner.memory_bytes,
                "memory_scope": "WindowsJob" if process.peak_job_memory_bytes is not None else "unmeasured"})
            if process.termination_reason:
                mapping = {"deadline": ("DEADLINE_EXCEEDED", "timed_out"), "cancelled": ("CANCELLED", "cancelled"), "stream_limit": ("LIMIT_EXCEEDED", "limit_exhausted"), "memory_limit": ("MEMORY_LIMIT", "limit_exhausted"), "spawn_failed": ("WORKER_START_FAILED", "failed")}
                code, status = mapping.get(process.termination_reason, ("CLEANUP_INCOMPLETE", "failed"))
                raise ToolFault(code, "Worker stopped under parent control", status=status)
            if not process.cleanup_complete: raise ToolFault("CLEANUP_INCOMPLETE", "Worker resources did not settle")
            response = supervised_response if supervised_response is not None else strict_json(process.stdout, cap, limits["json_depth"])
            closed(response, {"schema_version", "message_type", "request_id", "tool", "invocation", "phase", "prepared", "error", "observations", "usage"})
            if response["schema_version"] != 1 or response["message_type"] != "worker_response" or any(response[key] != request[key] for key in ("request_id", "tool", "invocation")):
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker response identity differs from request")
            if response["phase"] not in ("prepared", "failed"):
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Unknown worker phase")
            if not isinstance(response["usage"], dict) or set(response["usage"]) - set(result.usage):
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker usage fields are invalid")
            if any(value is not None and (type(value) is not int or value < 0) for key, value in response["usage"].items() if key != "monetary_cost") or response["usage"].get("monetary_cost") is not None:
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker usage cannot invent billing or negative counts")
            if response["phase"] == "prepared" and (process.exit_code != 0 or response["error"] is not None or response["prepared"] is None):
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Prepared phase/exit/payload is inconsistent")
            if response["phase"] == "failed" and (response["prepared"] is not None or not isinstance(response["error"], dict) or process.exit_code not in range(2, 7)):
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Failed phase/exit/error is inconsistent")
            if quota:
                validate_schema(response["observations"], "worker_scholarly_observations")
                if response["phase"] == "failed":
                    validate_schema(response["error"]["details"], "scholar_error_details")
                    if any(response["error"]["details"][field] is not None for field in ("quota_source", "remaining_microusd", "reset_at", "retry_after_seconds")):
                        raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker supplied parent-only quota authority")
                parsed = parse_limits(provider, response["observations"]["provider_limits"])
                http_status = response["observations"]["scholarly_attempt"]["http_status"]
                quota.settle(reservation, parsed, http_status); settled = True
                try: await self._persist_quota()
                except BaseException:
                    quota.blocked = True
                    raise
                result.observations.update({"scholarly_attempt": response["observations"]["scholarly_attempt"],
                    "provider_limits": parsed, "quota": quota.observation(reservation, parsed)})
            else:
                observation_keys = {"backend_attempts", "disabled_backends"} if definition.name == "web.search" else {"http_status", "redirects", "final_url", "extraction_version"} if definition.name == "web.fetch" else set()
                if definition.name == "web.fetch" and definition.revision >= 2:
                    observation_keys |= {"fetch_attempts", "representation"}
                required_observations = set(observation_keys) if response['phase'] == 'prepared' else set()
                if definition.name == 'web.fetch' and definition.revision == 3:
                    observation_keys.add('fetch_supervision')
                closed(response["observations"], observation_keys, required=required_observations)
                result.observations.update(response["observations"])
            result.usage.update(response["usage"])
            if response["phase"] == "failed":
                error = response["error"]
                closed(error, {"code", "message", "details", "observed_effect_state"})
                if quota:
                    error["details"].update(quota_source="both", remaining_microusd=quota.remote_remaining,
                        reset_at=quota.reset_at, retry_after_seconds=quota.retry_after)
                result.error = EngineError(**error)
                result.status = {2: "validation_failed", 3: "failed", 4: "limit_exhausted", 5: "timed_out", 6: "cancelled"}[process.exit_code]
                return result
            context.assert_active(); storage_plan.assert_recorded()
            prepared = response["prepared"]
            if definition.name == "web.fetch":
                closed(prepared, {"operation_id", "proposal"})
                if prepared["operation_id"] != storage_plan.operation_id: raise ToolFault("WORKER_PROTOCOL_ERROR", "Prepared operation identity changed")
                proposal = closed(prepared["proposal"], {"original", "text", "index", "provenance", "extraction_version", "normalization_version", "media_type"})
                decoded = {key: unpack_component(proposal[key], limits[cap_name]) for key, cap_name in (("original", "raw_bytes"), ("text", "text_bytes"), ("index", "index_bytes"))}
                decoded["text"].decode("utf-8", errors="strict")
                index = strict_json(decoded["index"], limits["index_bytes"])
                encode(proposal["provenance"], limits["provenance_bytes"])
                typed = SnapshotProposal(**{**proposal, **decoded})
                context.ledger.consume("source_bytes", len(decoded["original"]))
                context.assert_active()
                committed = await self._snapshot_commit(storage_plan, context, typed)
                if isinstance(committed, Err):
                    result.persistence["commit_state"] = committed.error.commit_state
                    raise committed.error
                receipt = committed.value
                result.persistence.update(commit_state="committed", receipt=wire(receipt))
                if receipt.operation_id != storage_plan.operation_id or receipt.snapshot_ref.store_id != context.store_id or any(receipt.component_digests.get(key) != digest(decoded[key]) for key in ("original", "text", "index")):
                    raise ToolFault("STORAGE_PROTOCOL_ERROR", "READY receipt differs from the committed proposal")
                result.result = {"snapshot_ref": wire(receipt.snapshot_ref), "extraction_version": receipt.extraction_version,
                    "normalization_version": proposal["normalization_version"], "line_count": receipt.line_count,
                    "page_count": receipt.physical_page_count, "provenance": proposal["provenance"],
                    "preview": decoded["text"][:limits["preview_bytes"]].decode("utf-8", errors="ignore")}
                context.assert_active()  # commitment survives cancellation; public success still requires active work
            elif definition.name == "document.read":
                if prepared != plan["slice"]: raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker changed authoritative immutable slice")
                result.result = prepared
            elif quota:
                validate_schema(prepared, provider + ("_result_v2" if definition.revision == 2 else "_result"))
                if prepared["query"] != arguments["query"]:
                    raise ToolFault("WORKER_PROTOCOL_ERROR", "Scholarly search query changed")
                result.result = prepared
            else:
                fields = {"query", "searched_at", "backend_policy", "backend_attempts", "results"}
                closed(prepared, fields | ({"coverage"} if definition.revision >= 3 else set()))
                if prepared["query"] != arguments["query"]: raise ToolFault("WORKER_PROTOCOL_ERROR", "Search query changed")
                result.result = prepared
            result.status = "succeeded"
            if list(Draft202012Validator(definition.output_schema).iter_errors(result.result)):
                raise ToolFault("WORKER_PROTOCOL_ERROR", "Tool output differs from its closed public schema")
            if (definition.name == "web.search" and definition.revision >= 3 or
                    definition.name.startswith("scholar.") and definition.revision == 2):
                from .discovery_metadata import validate_coverage
                validate_coverage(result.result, arguments, scholarly=definition.name.startswith("scholar."))
            encode(result, limits["stdout_bytes"])
            return result
        except ToolFault as fault:
            result.status, result.error = fault.status, fault_error(fault)
            result.result = None
            return result
        except EngineError as error:
            result.status, result.error = terminal(error), error
            result.result = None
            return result
        except (ValueError, UnicodeError, TypeError, KeyError) as exc:
            result.error = EngineError("WORKER_PROTOCOL_ERROR", "Worker output does not satisfy the bound protocol")
            result.result = None
            return result
        finally:
            if quota_acquired and not settled:
                quota.settle(reservation, None, dispatched=result.process["dispatched"])
                if self._quota_sink is not None:
                    try: await self._persist_quota()
                    except Exception: quota.blocked = True
            result.usage["duration_ms"] = int((time.monotonic() - started) * 1000)

    async def close(self, deadline=None):
        self._closed = True
        state = await self.runner.close(deadline)
        return CleanupReport(complete=state["complete"], unconfirmed_resources=[] if state["complete"] else ["tool-workers"])
