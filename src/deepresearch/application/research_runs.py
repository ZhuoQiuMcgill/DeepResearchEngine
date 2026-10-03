"""Durable research admission, owned execution and bounded result inspection."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import math
from typing import Any

from deepresearch.engine.connections import (
    ArtifactReadRequest, InvocationRule, PublicationRequest, RunAccessOptions, RunAccessRequest,
    RunOptions, SnapshotReadRequest,
)
from deepresearch.engine.contracts import (
    ArtifactRef, ByteRange, CleanupReport, EngineError, RunRef, ScopeRef, SnapshotRef,
    canonical_json, digest_bytes, digest_json, new_id, to_json_value, utc_now,
)
from deepresearch.extensions import ExtensionRegistry, HookDispatcher
from deepresearch.workflows.context import WorkflowContext
from deepresearch.workflows.contracts import ResearchRunRequest, ResearchRunView, SourceRange
from deepresearch.workflows.runner import WorkflowRunner
from .platform import RESEARCH_STATE_KEY, ResearchPlatformPort

MAX_RESPONSE_BYTES = 524288
MAX_SCAN_PAGES = 32
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out", "interrupted"}


@dataclass
class LiveResearchRun:
    session: Any
    view: ResearchRunView
    fingerprint: str
    tools: tuple
    method_manifest_ref: dict | None = None
    version: int = 0
    task: asyncio.Task | None = None
    port: Any = None
    error: EngineError | None = None
    cleanup: CleanupReport = field(default_factory=CleanupReport)
    hooks: Any = None


class ResearchRunService:
    """The supplied Engine remains caller-owned. Restart never dispatches a run.

    Admission and execution tasks survive HTTP cancellation/disconnection. Client
    identities are reconciled against bounded owned descriptors and CAS state,
    including provisioned admissions whose accepted-state acknowledgement failed.
    """

    def __init__(self, engine, registry, agent_catalog, token_meter,
                 extension_registry=None, max_active_runs=8):
        if type(max_active_runs) is not int or not 1 <= max_active_runs <= 128:
            raise ValueError("max_active_runs must be between 1 and 128")
        self.engine, self.registry = engine, registry
        self.agent_catalog, self.token_meter = agent_catalog, token_meter
        self.extension_registry = extension_registry if extension_registry is not None else ExtensionRegistry()
        self.max_active_runs = max_active_runs
        self._runs: dict[str, LiveResearchRun] = {}
        self._starting: set[asyncio.Task] = set()
        self._start_lock = asyncio.Lock()
        self._closing = False

    @property
    def accepting(self):
        return not self._closing

    @property
    def active_count(self):
        return sum(live.task is not None and not live.task.done() for live in self._runs.values())

    def list_methods(self):
        return {"schema_version": 1, "methods": self.registry.list()}

    def run_ref(self, run_id):
        if type(run_id) is not str or not run_id or len(run_id) > 256:
            raise EngineError("INVALID_DATA", "Invalid run identifier")
        return RunRef(self.engine.storage.store_id, run_id)

    @staticmethod
    def _limit(limit):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise EngineError("INVALID_DATA", "Page limit must be between 1 and 100")

    @staticmethod
    def _error(error):
        if isinstance(error, EngineError):
            return error
        return EngineError("RESEARCH_DEFECT", "Research execution encountered an unexpected defect",
                           {"exception_type": type(error).__name__})

    @staticmethod
    def _status(error):
        if error.commit_state == "unknown":
            return "interrupted"
        if error.code == "CANCELLED":
            return "cancelled"
        if error.code in {"DEADLINE_EXCEEDED", "TIMED_OUT"}:
            return "timed_out"
        if error.code == "TASK_INTERRUPTED" or error.commit_state == "unknown":
            return "interrupted"
        return "failed"

    async def start_run(self, request: ResearchRunRequest) -> ResearchRunView:
        try:
            request = ResearchRunRequest.model_validate(
                request.model_dump(mode="python") if isinstance(request, ResearchRunRequest) else request,
            )
            canonical_json(request.to_dict(), 131072)
        except (ValueError, TypeError):
            raise EngineError("INVALID_DATA", "Research request violates the shared JSON contract") from None
        if self._closing:
            raise EngineError("SESSION_CLOSED", "Research admissions have stopped")
        if len(self._starting) >= self.max_active_runs:
            raise EngineError("SERVICE_BUSY", "Pending research admission capacity is exhausted")
        task = asyncio.create_task(self._start(request), name=f"deepresearch-research:admission:{new_id()}")
        self._starting.add(task)
        def settled(done):
            self._starting.discard(done)
            if not done.cancelled():
                done.exception()
        task.add_done_callback(settled)
        return await asyncio.shield(task)

    async def _find_client_request(self, client_id):
        cursor = None
        for _ in range(MAX_SCAN_PAGES):
            page = to_json_value((await self.engine.list_runs({}, cursor, 100)).unwrap())
            for descriptor in page["runs"]:
                if descriptor.get("context_kind") != "workflow":
                    continue
                saved, _, _ = await self._saved(descriptor["run_id"])
                if saved and saved["view"]["client_request_id"] == client_id:
                    return saved
            cursor = page.get("cursor")
            if cursor is None:
                return None
        raise EngineError("LIMIT_EXCEEDED", "Durable research identity scan exceeds its bound")

    async def _start(self, request):
        fingerprint = digest_json(request.to_dict())
        async with self._start_lock:
            if self._closing:
                raise EngineError("SESSION_CLOSED", "Research admissions have stopped")
            saved = await self._find_client_request(request.client_request_id)
            if saved is not None:
                if saved["request_fingerprint"] != fingerprint:
                    raise EngineError("IDEMPOTENCY_CONFLICT", "Client request identity was already used for different intent")
                return await self.get_run(saved["view"]["run_id"])
            if self.active_count >= self.max_active_runs:
                raise EngineError("SERVICE_BUSY", "Active research run capacity is exhausted")
            definition, method = self.registry.resolve(request.method_id, request.method_revision)
            self.registry.validate(definition, request.input, request.parameters)
            if not any(profile.get("profile_ref") == request.profile_ref
                       and profile.get("model_ref", profile.get("model_id")) == request.model_ref
                       for profile in self.engine.list_profiles()):
                raise EngineError("PROFILE_MISMATCH", "Select a configured profile and its pinned model")
            roles = {}
            try:
                for role_id, revision in definition.agent_roles:
                    if role_id in roles:
                        raise EngineError("INVALID_DATA", "Method repeats an agent role")
                    spec = self.agent_catalog.load(role_id, revision)
                    # Distinct profile bindings keep a pinned role revision immutable.
                    binding_id = "research." + digest_json({"spec": spec.ref,
                        "profile_ref": request.profile_ref, "model_ref": request.model_ref})[7:39]
                    agent = spec.compile_definition(profile_ref=request.profile_ref,
                        model_ref=request.model_ref, tools=(), limits={}, agent_id=binding_id)
                    if agent.allowed_tools or agent.input_schema.get("type") != "string":
                        raise EngineError("INVALID_DATA", "Research roles require a rendered string and no tools")
                    roles[role_id] = (spec, self.engine.register_agent(agent).unwrap())
            except ValueError:
                raise EngineError("INVALID_DATA", "Pinned agent role resources failed catalog validation") from None
            # Names used by a Workflow select exactly one admitted revision.
            # Unpinned methods preserve revision 1; method pins are explicit.
            names = dict.fromkeys(tool.name for tool in self.engine.catalog.definitions)
            tools = tuple(self.engine.catalog.resolve(name, definition.tool_revisions.get(name, 1)).unwrap().ref
                          for name in names)
            for name in definition.tool_revisions:
                if name not in names:
                    raise EngineError("UNKNOWN_TOOL", "Method pins an unregistered tool")
            rules = tuple(InvocationRule(registered.ref, allowed_tools=(), allow_model=True,
                         allow_export=True, allow_evidence=False,
                         timeout_seconds=request.timeout_seconds)
                         for _, registered in roles.values())
            accepted_at = utc_now()
            intent = {"client_request_id": request.client_request_id,
                      "request_fingerprint": fingerprint, "method_id": request.method_id,
                      "method_revision": request.method_revision, "accepted_at": accepted_at}
            session = (await self.engine.open_workflow_session(tools=tools,
                invocation_rules=rules, cleanup_state_keys=(RESEARCH_STATE_KEY,), options=RunOptions(timeout_seconds=request.timeout_seconds,
                    metadata={"research_request": intent}),
            )).unwrap()
            view = ResearchRunView(run_id=session.context.run_id, method_id=request.method_id,
                method_revision=request.method_revision, client_request_id=request.client_request_id,
                accepted_at=accepted_at, status="accepted", active=True,
                profile_ref=request.profile_ref, model_ref=request.model_ref,
                pins={"method": definition.to_dict(), "roles": [spec.ref for spec, _ in roles.values()]})
            live = LiveResearchRun(session, view, fingerprint, tools)
            port = live.port = ResearchPlatformPort(self.engine, live, roles)
            self._runs[view.run_id] = live
            try:
                # First save the identity before manifests/events or method dispatch.
                await port.commit(view)
                request_ref = await port.publish(canonical_json(request.to_dict()),
                    "application/json", "research-request.json")
                manifest = {"schema_version": 1, "method": definition.to_dict(),
                    "request_fingerprint": fingerprint,
                    "request_ref": request_ref,
                    "profile_ref": request.profile_ref, "model_ref": request.model_ref,
                    "tools": [tool.to_dict() for tool in tools],
                    "roles": [spec.ref for spec, _ in roles.values()]}
                live.method_manifest_ref = await port.publish(canonical_json(manifest),
                    "application/json", "research-method.json")
                await port.commit(view)
                await port.emit("workflow.accepted", {**intent, "request_ref": request_ref,
                    "method_manifest_ref": live.method_manifest_ref})
                hooks = live.hooks = HookDispatcher(self.extension_registry, port.record_hook)
                context = WorkflowContext(view.run_id, request.model_ref, port, hooks, self.token_meter)
                if self._closing:
                    session.context.cancellation.set()
                live.task = asyncio.create_task(self._execute(live, definition, method, context, request),
                                               name=f"deepresearch-research:{view.run_id}")
                self._prune()
                return view.model_copy(deep=True)
            except BaseException as error:
                live.error = self._error(error)
                live.view = live.view.model_copy(update={"status": "interrupted", "active": False,
                                                        "recording_status": "incomplete"})
                await self._close_session(live)
                self._prune()
                raise

    async def _method(self, live, definition, method, context, request):
        live.port.assert_active()
        execution = asyncio.create_task(WorkflowRunner().run(
            definition, method, context, request.input, request.parameters,
        ), name=f"deepresearch-research:method:{live.view.run_id}")
        cancellation = asyncio.create_task(live.session.context.cancellation.wait())
        try:
            done, _ = await asyncio.wait((execution, cancellation),
                timeout=live.session.context.remaining_seconds(), return_when=asyncio.FIRST_COMPLETED)
            if cancellation in done:
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                raise EngineError("CANCELLED", "Research cancellation was requested")
            if execution not in done:
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                raise EngineError("DEADLINE_EXCEEDED", "Research deadline elapsed")
            return execution.result()
        finally:
            cancellation.cancel()
            if not execution.done():
                execution.cancel()
            await asyncio.gather(cancellation, execution, return_exceptions=True)

    async def _execute(self, live, definition, method, context, request):
        status, error = "failed", None
        try:
            await live.port.commit(live.view.model_copy(update={"status": "running"}))
            result = await self._method(live, definition, method, context, request)
            live.port.assert_active()
            if live.port.failure:
                raise live.port.failure
            if isinstance(result, dict):
                fields = {key: result[key] for key in ("report_ref", "result_manifest_ref", "usage") if key in result}
                if fields:
                    await live.port.update(**fields)
            if live.view.report_ref is None:
                raise EngineError("REPORT_UNAVAILABLE", "Research method did not publish a report")
            if live.view.result_manifest_ref is None:
                ref = await live.port.publish(canonical_json({"schema_version": 1,
                    "method_manifest_ref": live.method_manifest_ref, "run": live.view.to_dict()}),
                    "application/json", "research-result.json")
                await live.port.update(result_manifest_ref=ref)
            status = "succeeded"
        except asyncio.CancelledError:
            live.session.context.cancellation.set()
            error = EngineError("TASK_INTERRUPTED", "Owned research task was interrupted")
            status = "interrupted"
        except BaseException as exc:
            error = self._error(exc)
            if live.session.context.cancellation.is_set():
                error = live.port.boundary_error("CANCELLED", "Research cancellation was requested", error)
            elif live.session.context.remaining_seconds() <= 0:
                error = EngineError("DEADLINE_EXCEEDED", "Research deadline elapsed")
            status = self._status(error)
        final = ResearchRunView.model_validate({**live.view.to_dict(), "status": status,
            "active": False, "nodes": list(context.nodes.values()),
            "error": error.to_dict() if error else None, "recording_status": "pending"})
        try:
            can_commit = (not live.session.context.cancellation.is_set()
                          and live.session.context.remaining_seconds() > 0)
            if can_commit:
                await live.port.commit(final)
            else:
                try:
                    await live.port.commit(final, cleanup=True)
                    can_commit = True
                except EngineError as cleanup_error:
                    # The current shared permission contract may still forbid
                    # cleanup business writes. Only this known nondispatch can
                    # fall back to the already-authorized terminal projection.
                    if (cleanup_error.code != "ACCESS_DENIED"
                            or cleanup_error.message != "cleanup cannot perform business operations"):
                        raise
                    live.view = final
            terminal_payload = {
                "status": status, "recording_status": "complete", "error": final.error,
                "projection_version": live.version + (1 if can_commit else 0),
                "nodes": [node.to_dict() for node in final.nodes],
                "report_ref": final.report_ref.to_dict() if final.report_ref else None,
                "result_manifest_ref": final.result_manifest_ref.to_dict() if final.result_manifest_ref else None,
                "checkpoint_ref": final.checkpoint_ref,
            }
            if len(canonical_json(terminal_payload)) > 16384:
                # The authoritative projection retains all nodes. Long methods
                # must still be able to acknowledge a bounded terminal event.
                nodes = terminal_payload.pop("nodes")
                terminal_payload.update(node_count=len(nodes), nodes_sha256=digest_json(nodes))
            if status != "succeeded":
                with_sources = {**terminal_payload, "sources": final.sources.to_dict()}
                if len(canonical_json(with_sources)) <= 16384:
                    terminal_payload = with_sources
            receipt = await live.port.emit("workflow.finished", terminal_payload, cleanup=True)
            final = final.model_copy(update={"recording_status": "complete",
                                             "terminal_event_receipt": receipt.to_dict()})
            if can_commit:
                await live.port.commit(final, cleanup=(live.session.context.cancellation.is_set()
                    or live.session.context.remaining_seconds() <= 0))
            else:
                live.view = final
        except BaseException as exc:
            live.error = self._error(exc)
            live.view = final.model_copy(update={"status": "interrupted", "recording_status": "incomplete",
                                                 "error": live.error.to_dict()})
        finally:
            await self._close_hooks(live)
            await self._close_session(live)
            if status == "succeeded" and live.error is None and live.cleanup.complete:
                try:
                    await self._publish_completion(live)
                except BaseException as exc:
                    live.error = self._error(exc)
                    live.view = live.view.model_copy(update={"status": "interrupted",
                        "recording_status": "incomplete", "error": live.error.to_dict()})
            self._prune()

    @staticmethod
    def _merge_cleanup(live, report):
        if not isinstance(report, CleanupReport):
            report = CleanupReport(False, ["Cleanup owner returned an invalid report"], [live.view.run_id])
        live.cleanup = CleanupReport(
            live.cleanup.complete and report.complete and not report.unconfirmed_resources,
            live.cleanup.errors + report.errors,
            list(dict.fromkeys(live.cleanup.unconfirmed_resources + report.unconfirmed_resources)))

    def _cleanup_failure(self, live, error):
        live.error = self._error(error)
        live.view = live.view.model_copy(update={"status": "interrupted", "active": False,
            "recording_status": "incomplete", "error": live.error.to_dict()})

    async def _close_hooks(self, live):
        if live.hooks is None:
            return
        try:
            report = await live.hooks.close(timeout_seconds=5)
            self._merge_cleanup(live, report)
            if not live.cleanup.complete:
                self._cleanup_failure(live, EngineError("CLEANUP_INCOMPLETE", "Workflow Hook cleanup is incomplete"))
        except BaseException as exc:
            error = self._error(exc)
            self._merge_cleanup(live, CleanupReport(False, [error.to_dict()], ["workflow-hooks:" + live.view.run_id]))
            self._cleanup_failure(live, error)

    async def _close_session(self, live):
        try:
            report = await live.session.close()
            self._merge_cleanup(live, report)
            if not live.cleanup.complete:
                self._cleanup_failure(live, EngineError("CLEANUP_INCOMPLETE", "Workflow cleanup is incomplete"))
        except BaseException as exc:
            error = self._error(exc)
            self._merge_cleanup(live, CleanupReport(False, [error.to_dict()], [live.view.run_id]))
            self._cleanup_failure(live, error)

    @staticmethod
    def _completion_bytes(view, version, receipt):
        return canonical_json({"schema_version": 1, "format": "research.completion/1",
            "run_id": view.run_id, "projection_version": version,
            "terminal_event_receipt": receipt, "cleanup": {"complete": True}})

    async def _publish_completion(self, live):
        # The live Workflow has closed. A bounded host review export attests its
        # actual closure without restoring any execution grants or run budgets.
        data = self._completion_bytes(live.view, live.version, live.view.terminal_event_receipt)
        scope = ScopeRef("run", live.view.run_id)
        selector = PublicationRequest("artifact.put", scope, "review_export",
            allowed_media_types=("application/json",), max_object_bytes=len(data),
            max_total_bytes=len(data), max_operations=1)
        access = (await self.engine.open_run_access(self.run_ref(live.view.run_id),
            RunAccessRequest(publications=(selector,)),
            RunAccessOptions(max_total_write_bytes=len(data), max_operations=8),
        )).unwrap()
        async with access:
            (await access.storage.artifacts.put(access.context, access.identity_service.allocate(),
                scope, data, {"media_type": "application/json", "filename": "research-completion.json"})).unwrap()

    async def _has_completion(self, view, version, receipt):
        expected = digest_bytes(self._completion_bytes(view, version, receipt))
        cursor = None
        for _ in range(MAX_SCAN_PAGES):
            page = to_json_value((await self.engine.list_run_objects(self.run_ref(view.run_id), cursor, 100)).unwrap())
            if any(obj.get("kind") == "artifact" and obj.get("sha256") == expected for obj in page["objects"]):
                return True
            cursor = page.get("cursor")
            if cursor is None:
                return False
        raise EngineError("LIMIT_EXCEEDED", "Research completion inspection exceeds its bound")

    def _prune(self):
        if len(self._runs) > 256:
            for run_id, live in tuple(self._runs.items()):
                finished = live.task is not None and live.task.done()
                failed_admission = live.task is None and live.error is not None and not live.session.context.lease.active
                if (finished or failed_admission) and live.cleanup.complete:
                    del self._runs[run_id]
                if len(self._runs) <= 256:
                    break

    async def _saved(self, run_id):
        ref = self.run_ref(run_id)
        descriptor = to_json_value((await self.engine.describe_run(ref)).unwrap())
        if descriptor.get("context_kind") != "workflow":
            return None, descriptor, 0
        state = (await self.engine.read_run_state(ref, RESEARCH_STATE_KEY)).unwrap()
        if state.present:
            saved = state.value
            try:
                view = ResearchRunView.model_validate(saved["view"])
                if view.run_id != run_id or type(saved["request_fingerprint"]) is not str:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise EngineError("INVALID_DATA", "Saved research projection is invalid") from None
            return saved, descriptor, state.version
        intent = descriptor.get("metadata", {}).get("research_request")
        if intent:
            view = ResearchRunView(run_id=run_id, method_id=intent["method_id"],
                method_revision=intent["method_revision"], client_request_id=intent["client_request_id"],
                accepted_at=intent["accepted_at"], status="interrupted", recording_status="incomplete")
            return {"view": view.to_dict(), "request_fingerprint": intent["request_fingerprint"]}, descriptor, 0
        return None, descriptor, 0

    async def get_run(self, run_id) -> ResearchRunView:
        self.run_ref(run_id)
        live = self._runs.get(run_id)
        if live and live.task and not live.task.done():
            return live.view.model_copy(deep=True, update={"active": True,
                "status": "accepted" if live.view.status == "accepted" else "running",
                "recording_status": "pending"})
        saved, descriptor, version = await self._saved(run_id)
        if saved is None:
            raise EngineError("RUN_NOT_FOUND", "Owned research run was not found")
        view = ResearchRunView.model_validate(saved["view"])
        live = self._runs.get(run_id)
        active = bool(live and live.task and not live.task.done())
        row = descriptor.get("terminal_event")
        if active:
            # Completion is visible only after owned cleanup settles.
            return live.view.model_copy(deep=True, update={"active": True,
                "status": "accepted" if live.view.status == "accepted" else "running",
                "recording_status": "pending"})
        if live and live.error:
            return live.view.model_copy(deep=True, update={"active": False, "status": "interrupted",
                "recording_status": "incomplete", "error": live.error.to_dict()})
        if not row or not row.get("receipt"):
            return view.model_copy(update={"status": "interrupted", "active": False, "recording_status": "incomplete"})
        payload = row["event"]["payload"]
        status = payload.get("status", "interrupted")
        if (status not in TERMINAL_STATUSES or payload.get("recording_status") != "complete"
                or status == "succeeded" and (view.status != "succeeded"
                    or payload.get("projection_version") != version or view.report_ref is None
                    or view.recording_status != "complete" or view.terminal_event_receipt != row["receipt"])):
            return view.model_copy(update={"status": "interrupted", "active": False, "recording_status": "incomplete"})
        if status == "succeeded" and not await self._has_completion(view, version, row["receipt"]):
            return view.model_copy(update={"status": "interrupted", "active": False,
                                          "recording_status": "incomplete"})
        fields = {key: payload[key] for key in ("error", "nodes", "sources", "report_ref", "result_manifest_ref", "checkpoint_ref") if key in payload}
        return ResearchRunView.model_validate({**view.to_dict(), **fields,
            "status": status, "recording_status": "complete", "active": False,
            "terminal_event_receipt": row["receipt"]})

    async def list_runs(self, cursor=None, limit=100):
        self._limit(limit)
        page = to_json_value((await self.engine.list_runs({"context_kind": "workflow"}, cursor, limit)).unwrap())
        runs = []
        for descriptor in page["runs"]:
            saved, _, _ = await self._saved(descriptor["run_id"])
            if saved is not None:
                runs.append((await self.get_run(descriptor["run_id"])).to_dict())
        return {"schema_version": 1, "runs": runs, "cursor": page.get("cursor")}

    async def cancel_run(self, run_id) -> ResearchRunView:
        view = await self.get_run(run_id)
        live = self._runs.get(run_id)
        if live and live.task and not live.task.done():
            return await live.port.request_cancellation()
        return view

    async def events(self, run_id, after_seq=0, limit=100):
        self._limit(limit)
        if type(after_seq) is not int or not 0 <= after_seq <= 2**63 - 1:
            raise EngineError("INVALID_DATA", "Invalid committed event sequence")
        await self.get_run(run_id)
        page = to_json_value((await self.engine.query_run_events(self.run_ref(run_id),
            after_seq=after_seq, limit=limit, include_descendants=True)).unwrap())
        kept = []
        for row in page["events"]:
            if len(canonical_json({"events": kept + [row]})) > MAX_RESPONSE_BYTES - 4096:
                if not kept:
                    raise EngineError("LIMIT_EXCEEDED", "One event exceeds the response byte bound")
                page.update(events=kept, next_after_seq=kept[-1]["receipt"]["recorded_seq"], has_more=True)
                break
            kept.append(row)
        return {"schema_version": 1, **page}

    async def read_source(self, run_id, item_id, range: SourceRange, max_text_bytes=65536, continuation=None):
        if not isinstance(range, SourceRange) or type(max_text_bytes) is not int or not 1 <= max_text_bytes <= 65536:
            raise EngineError("INVALID_DATA", "Source reads require a shared range and a bounded byte allowance")
        if continuation is not None and (type(continuation) is not str or len(continuation) > 8192):
            raise EngineError("INVALID_DATA", "Invalid source continuation")
        range = SourceRange.model_validate(range.model_dump(mode="python"))
        view = await self.get_run(run_id)
        source = next((source for source in view.sources.items if source.item_id == item_id), None)
        if source is None or source.status != "succeeded" or source.snapshot_ref is None:
            raise EngineError("NOT_FOUND", "Committed research source was not found")
        if source.source_run_id not in {None, run_id}:
            raise EngineError("ACCESS_DENIED", "Research source is outside this Workflow")
        ref = SnapshotRef(source.snapshot_ref.store_id, source.snapshot_ref.snapshot_id)
        access = (await self.engine.open_run_access(self.run_ref(run_id),
            RunAccessRequest(read_objects=(SnapshotReadRequest(ref, range.tool_range(), max_text_bytes, continuation),)),
            RunAccessOptions(max_total_read_bytes=max_text_bytes, max_operations=8),
        )).unwrap()
        async with access:
            value = (await access.storage.snapshots.read(access.context, ref,
                range.tool_range(), max_text_bytes, continuation)).unwrap()
        return {"run_id": run_id, "item_id": item_id, **to_json_value(value)}

    async def get_sources(self, run_id):
        return (await self.get_run(run_id)).sources

    async def get_context(self, run_id):
        return (await self.get_run(run_id)).context_plan

    async def get_result(self, run_id):
        return await self.get_run(run_id)

    async def get_usage(self, run_id):
        view = await self.get_run(run_id)
        return {"schema_version": 1, "run_id": run_id, "status": view.status,
            "active": view.active, "available": view.usage is not None,
            "usage": view.usage, "terminal_event_receipt": view.terminal_event_receipt}

    async def read_report(self, run_id, start=0, max_bytes=65536):
        view = await self.get_run(run_id)
        if view.report_ref is None:
            raise EngineError("NOT_FOUND", "Research report has not been published")
        return await self.read_artifact(run_id, view.report_ref.artifact_id, start, max_bytes)

    async def read_context(self, run_id, start=0, max_bytes=65536):
        view = await self.get_run(run_id)
        if view.context_plan is None or view.context_plan.context_ref is None:
            raise EngineError("NOT_FOUND", "Selected context has not been published")
        return await self.read_artifact(run_id, view.context_plan.context_ref.artifact_id, start, max_bytes)

    async def list_objects(self, run_id, cursor=None, limit=100):
        await self.get_run(run_id)
        self._limit(limit)
        return {"schema_version": 1, **to_json_value((await self.engine.list_run_objects(
            self.run_ref(run_id), cursor, limit)).unwrap())}

    async def read_artifact(self, run_id, artifact_id, start=0, max_bytes=65536):
        if (type(start) is not int or start < 0 or type(max_bytes) is not int or not 1 <= max_bytes <= 65536
                or type(artifact_id) is not str or not 1 <= len(artifact_id) <= 128):
            raise EngineError("INVALID_DATA", "Artifact reads require an identity and bounded byte range")
        await self.get_run(run_id)
        ref = ArtifactRef(self.engine.storage.store_id, artifact_id)
        cursor, descriptor = None, None
        for _ in range(MAX_SCAN_PAGES):
            page = to_json_value((await self.engine.list_run_objects(self.run_ref(run_id), cursor, 100)).unwrap())
            descriptor = next((obj for obj in page["objects"] if obj.get("ref") == ref.to_dict()), None)
            if descriptor:
                break
            cursor = page.get("cursor")
            if cursor is None:
                break
        if descriptor is None:
            raise EngineError("NOT_FOUND", "Artifact is outside this Workflow's bounded catalog")
        length = descriptor["byte_length"]
        if start > length:
            raise EngineError("INVALID_RANGE", "Report offset is outside the published bytes")
        end = min(length, start + max_bytes)
        interval, allowance = ByteRange(start, end), max(1, end - start)
        access = (await self.engine.open_run_access(self.run_ref(run_id),
            RunAccessRequest(read_objects=(ArtifactReadRequest(ref, interval, allowance),)),
            RunAccessOptions(max_total_read_bytes=allowance, max_operations=8),
        )).unwrap()
        async with access:
            reader = (await access.storage.artifacts.open(access.context, ref, interval, allowance)).unwrap()
            try:
                chunk = (await reader.read(access.context, allowance)).unwrap()
            finally:
                await reader.aclose(access.context)
        return {"schema_version": 1, "run_id": run_id, "artifact_ref": ref.to_dict(),
            "encoding": "base64", "data": base64.b64encode(chunk.bytes).decode("ascii"),
            "start": start, "next_offset": end, "eof": end == length,
            "byte_length": len(chunk.bytes), "total_bytes": length, "media_type": descriptor["media_type"], "sha256": descriptor["sha256"]}

    async def close(self, timeout_seconds=30) -> CleanupReport:
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 60:
            raise ValueError("close timeout must be positive and at most 60 seconds")
        self._closing = True
        for live in self._runs.values():
            if live.task and not live.task.done():
                live.session.context.cancellation.set()
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._start_lock:
                    tasks = list(self._starting)
                    for live in self._runs.values():
                        if live.task and not live.task.done():
                            live.session.context.cancellation.set()
                            tasks.append(live.task)
                if tasks:
                    await asyncio.wait(tasks)
                remaining = [live.task for live in self._runs.values() if live.task and not live.task.done()]
                for live in self._runs.values():
                    if live.task and not live.task.done():
                        live.session.context.cancellation.set()
                if remaining:
                    await asyncio.wait(remaining)
            failures = [live for live in self._runs.values() if not live.cleanup.complete]
            return CleanupReport(not failures,
                [error for live in failures for error in live.cleanup.errors],
                [resource for live in failures for resource in live.cleanup.unconfirmed_resources])
        except TimeoutError:
            tasks = [task for task in self._starting if not task.done()]
            tasks += [live.task for live in self._runs.values() if live.task and not live.task.done()]
            return CleanupReport(False, ["Research admission/execution cleanup exceeded deadline"],
                                 [task.get_name() for task in tasks])
