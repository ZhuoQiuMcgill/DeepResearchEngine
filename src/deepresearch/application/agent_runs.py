"""Single-owner application service over public Engine interfaces."""
from __future__ import annotations

import asyncio
import base64
import dataclasses
from typing import Any

from deepresearch.engine.agent import status_for
from deepresearch.engine.connections import (
    AgentRef, ArtifactReadRequest, RunAccessOptions, RunAccessRequest, RunOptions,
)
from deepresearch.engine.contracts import (
    AgentResult, ArtifactRef, ByteRange, CleanupReport, EngineError, RunRef,
    StateMutation, TERMINALS, canonical_json, digest_json, new_id, to_json_value,
    utc_now,
)


SERVICE_STATE_KEY = "service.run/1"
MAX_RESPONSE_BYTES = 524288
PUBLIC_DESCRIPTOR_FIELDS = frozenset({"schema_version", "run_id", "root_run_id", "correlation_id", "action_id",
    "principal", "context_kind", "agent_id", "definition_ref", "attempt_id", "parent_run_id",
    "parent_action_id", "parent_attempt_id", "root_action_id", "deadline", "depth", "ancestry",
    "binding_ref", "policy_ref", "purpose", "store_id", "scope", "owner_principal"})


@dataclasses.dataclass
class LiveRun:
    session: Any
    admission: Any
    accepted_at: str
    task: asyncio.Task | None = None
    result: AgentResult | None = None
    error: EngineError | None = None
    phase: str = "accepted"


class RunService:
    """Owns execution tasks; the caller retains ownership of the supplied Engine.

    HTTP disconnection does not cancel owned work. Cancellation signals the
    Runtime context, and shutdown waits for execution and durable recording.
    A saved checkpoint is data, never permission to resume execution.
    """

    def __init__(self, engine, *, max_active_runs: int = 8):
        if type(max_active_runs) is not int or not 1 <= max_active_runs <= 128:
            raise ValueError("max_active_runs must be between 1 and 128")
        self.engine = engine
        self.max_active_runs = max_active_runs
        self._runs: dict[str, LiveRun] = {}
        self._starting: set[asyncio.Task] = set()
        self._start_lock = asyncio.Lock()
        self._closing = False

    @property
    def active_count(self):
        return sum(r.task is not None and not r.task.done() for r in self._runs.values())

    @property
    def accepting(self):
        return not self._closing

    def run_ref(self, run_id: str):
        if not isinstance(run_id, str) or not run_id or len(run_id) > 256:
            raise EngineError("INVALID_DATA", "Invalid run identifier")
        return RunRef(self.engine.storage.store_id, run_id)

    async def start_run(self, agent_ref, task_input, options=None):
        if self._closing:
            raise EngineError("SESSION_CLOSED", "Service admissions have stopped")
        if len(self._starting) >= self.max_active_runs:
            raise EngineError("SERVICE_BUSY", "Pending admission capacity is exhausted")
        # Admission/binding/publication is strongly owned even when its HTTP
        # caller disconnects. Close accounts for these tasks as well as Runtime.
        task = asyncio.create_task(self._start_run(agent_ref, task_input, options),
            name=f"deepresearch-service:admission:{new_id()}")
        self._starting.add(task)
        def settled(done):
            self._starting.discard(done)
            if not done.cancelled():
                done.exception()
        task.add_done_callback(settled)
        return await asyncio.shield(task)

    async def _start_run(self, agent_ref, task_input, options=None):
        canonical_json(task_input, 131072)
        options = options or RunOptions()
        canonical_json(options, 16384)
        async with self._start_lock:
            if self._closing:
                raise EngineError("SESSION_CLOSED", "Service admissions have stopped")
            if self.active_count >= self.max_active_runs:
                raise EngineError("SERVICE_BUSY", "Active run capacity is exhausted")
            session = (await self.engine.open_agent_session(agent_ref, options)).unwrap()
            admission = None
            try:
                admission = (await self.engine.runtime.admit(
                    session.definition, task_input, session.binding, session.context,
                )).unwrap()
                accepted_at = utc_now()
                state = {"schema_version": 1, "agent_ref": {
                    "agent_id": session.definition.agent_id, "revision": session.definition.revision,
                }, "accepted_at": accepted_at, "input_digest": digest_json(task_input),
                    "service_state": "accepted", "automatic_resume": False}
                (await session.binding.storage.state.commit(
                    session.context, new_id("service_accept_"),
                    [StateMutation(session.context.scope, SERVICE_STATE_KEY, "put", 0, state)],
                )).unwrap()
                run_id = session.context.run_id
                live = LiveRun(session, admission, accepted_at)
                if self._closing:
                    session.context.cancellation.set()
                self._runs[run_id] = live
                live.task = asyncio.create_task(self._execute(live), name=f"deepresearch-service:{run_id}")
                self._prune()
                return {"schema_version": 1, "run_id": run_id,
                    "run_ref": self.run_ref(run_id).to_dict(), "status": "accepted",
                    "active": True, "accepted_at": accepted_at,
                    "agent_ref": state["agent_ref"], "recording_status": "pending"}
            except BaseException:
                if admission is not None and admission.state == "reserved":
                    await admission.release()
                await session.close()
                raise

    async def _execute(self, live):
        live.phase = "running"
        try:
            result = await self.engine.runtime.execute(live.admission)
            # Saved artifacts are authoritative; do not retain complete inline
            # reports or intermediate output buffers in the service registry.
            live.result = dataclasses.replace(result, output=None, observed_output=None)
            live.phase = live.result.status
        except asyncio.CancelledError:
            # Runtime records observed terminal facts during its cleanup. Never
            # manufacture an AgentResult from a cancelled Python task.
            live.phase = "interrupted"
            live.error = EngineError("TASK_INTERRUPTED", "Execution task was interrupted; inspect durable history")
            raise
        except Exception as exc:
            live.phase = "interrupted"
            live.error = EngineError("RUN_DEFECT", "Execution raised an unexpected defect",
                {"exception_type": type(exc).__name__})
        finally:
            if live.admission.state == "reserved":
                await live.admission.release()
            await live.session.close()
            self._prune()

    def _prune(self):
        if len(self._runs) > 256:
            for run_id, live in tuple(self._runs.items()):
                if live.task is not None and live.task.done():
                    del self._runs[run_id]
                if len(self._runs) <= 256:
                    break

    async def _descriptor(self, run_id):
        return to_json_value((await self.engine.describe_run(self.run_ref(run_id))).unwrap())

    @staticmethod
    def _terminal(descriptor):
        row = descriptor.get("terminal_event")
        if not row:
            return None, None
        event = row.get("event", row)
        kind = event.get("kind")
        if kind not in {"agent.finished", "tool.outcome", "tool.rejected"}:
            return None, None
        receipt = row.get("receipt")
        payload = dict(event.get("payload", {}))
        payload["terminal_kind"] = kind
        if kind.startswith("tool."):
            # A committed tool outcome/rejection is the standalone lifecycle
            # terminal. It does not imply any model output or model usage.
            payload["recording_status"] = "complete" if receipt else "incomplete"
            if kind == "tool.rejected":
                error = payload.get("error") or {}
                # Earlier v1 producer records lacked this field. Reuse the
                # Runtime-owned mapper rather than inventing a UI terminal.
                payload.setdefault("status", status_for(EngineError(
                    error.get("code", "tool.rejected"), error.get("message", "Tool request was rejected"))))
                payload.setdefault("dispatched", False)
        return payload, receipt

    async def get_run(self, run_id):
        descriptor = await self._descriptor(run_id)
        payload, receipt = self._terminal(descriptor)
        live = self._runs.get(run_id)
        active = bool(live and live.task and not live.task.done())
        if payload is not None:
            status = payload.get("status", "interrupted")
            recording = payload.get("recording_status", "unknown")
        elif active:
            status, recording = live.phase, "pending"
        elif live and live.result is not None:
            status, recording = live.result.status, live.result.recording_status
        else:
            status, recording = "interrupted", "incomplete"
        # A terminal receipt is required to describe a restarted run as complete.
        view = {"schema_version": 1, "run_id": run_id,
            "run_ref": self.run_ref(run_id).to_dict(), "status": status,
            "active": active, "recording_status": recording,
            "context_kind": descriptor.get("context_kind"),
            "terminal_kind": payload.get("terminal_kind") if payload else None,
            "terminal_event_receipt": receipt, "automatic_resume": False,
            "descriptor": {k: v for k, v in descriptor.items() if k in PUBLIC_DESCRIPTOR_FIELDS}}
        if live:
            view["accepted_at"] = live.accepted_at
            view["cancellation_requested"] = live.session.context.cancellation.is_set()
            if live.error:
                view["service_error"] = live.error.to_dict()
        return view

    async def list_runs(self, filters=None, cursor=None, limit=100):
        self._limit(limit)
        page = (await self.engine.list_runs(filters, cursor, limit)).unwrap()
        items = to_json_value(page)["runs"]
        return {"schema_version": 1,
            "runs": [await self.get_run(item["run_id"]) for item in items],
            "cursor": to_json_value(page).get("cursor")}

    async def cancel_run(self, run_id):
        view = await self.get_run(run_id)
        live = self._runs.get(run_id)
        if live and live.task and not live.task.done():
            live.session.context.cancellation.set()
            view.update(cancellation_requested=True, cancellation_state="requested")
        elif view["status"] in TERMINALS or view.get("terminal_event_receipt"):
            view["cancellation_state"] = "already_terminal"
        else:
            view["cancellation_state"] = "not_owned_active"
        return view

    async def get_result(self, run_id):
        descriptor = await self._descriptor(run_id)
        payload, receipt = self._terminal(descriptor)
        view = await self.get_run(run_id)
        if payload is None:
            return {**view, "available": False, "output_ref": None,
                "reason": "No durable agent terminal event is available"}
        keys = ("error", "cleanup", "output_ref", "raw_output_ref", "start_state", "persistence_state",
            "output_publications", "validation", "counters", "usage", "tool", "dispatched",
            "result_descriptor", "persistence", "process", "observations")
        return {**view, "available": True, "terminal_event_receipt": receipt,
            **{key: payload.get(key) for key in keys}}

    async def get_usage(self, run_id):
        result = await self.get_result(run_id)
        # Live partial observations are read through incremental events; this
        # endpoint preserves the Runtime's committed aggregate without estimates.
        return {"schema_version": 1, "run_id": run_id, "status": result["status"],
            "available": result["available"] and result.get("context_kind") == "agent", "usage": result.get("usage"),
            "counters": result.get("counters"),
            "terminal_event_receipt": result.get("terminal_event_receipt"),
            "observations_endpoint": f"/api/v1/runs/{run_id}/events"}

    async def events(self, run_id, after_seq=0, limit=100, include_descendants=False):
        self._limit(limit)
        if type(after_seq) is not int or after_seq < 0 or type(include_descendants) is not bool:
            raise EngineError("INVALID_DATA", "Invalid incremental event selector")
        page = (await self.engine.query_run_events(self.run_ref(run_id),
            after_seq=after_seq, limit=limit, include_descendants=include_descendants)).unwrap()
        page = to_json_value(page)
        # A page limit also has an encoded-byte bound. Return a prefix and its
        # actual sequence so polling never skips omitted committed events.
        kept = []
        for row in page["events"]:
            if len(canonical_json({"events": kept + [row]})) > MAX_RESPONSE_BYTES - 4096:
                if not kept:
                    raise EngineError("LIMIT_EXCEEDED", "One event exceeds the public response bound")
                page.update(events=kept, next_after_seq=kept[-1]["receipt"]["recorded_seq"], has_more=True)
                break
            kept.append(row)
        return {"schema_version": 1, **page}

    async def objects(self, run_id, cursor=None, limit=100):
        self._limit(limit)
        page = (await self.engine.list_run_objects(self.run_ref(run_id), cursor, limit)).unwrap()
        return {"schema_version": 1, **to_json_value(page)}

    async def read_state(self, run_id, key, version=None):
        if not isinstance(key, str) or not key or len(key) > 256:
            raise EngineError("INVALID_DATA", "Invalid state key")
        result = (await self.engine.read_run_state(self.run_ref(run_id), key, version)).unwrap()
        return {"schema_version": 1, **to_json_value(result)}

    async def read_artifact(self, run_id, artifact_id, *, start=0, max_bytes=65536):
        if type(start) is not int or start < 0 or type(max_bytes) is not int or not 1 <= max_bytes <= 65536:
            raise EngineError("INVALID_DATA", "Artifact reads require a positive bounded byte range")
        run_ref = self.run_ref(run_id)
        await self._descriptor(run_id)
        if not isinstance(artifact_id, str) or not artifact_id or len(artifact_id) > 256:
            raise EngineError("INVALID_DATA", "Invalid artifact identifier")
        ref = ArtifactRef(run_ref.store_id, artifact_id)
        # Storage validates actual object ownership. Byte intervals cannot be
        # clamped, so select a complete bounded object first to establish length.
        descriptor = await self._find_object(run_id, ref)
        length = descriptor.get("byte_length")
        if type(length) is not int or start > length:
            raise EngineError("INVALID_RANGE", "Artifact start lies outside the saved object")
        end = min(length, start + max_bytes)
        interval = ByteRange(start, end)
        size = end - start
        admitted_bytes = max(1, size)
        access = (await self.engine.open_run_access(run_ref,
            RunAccessRequest(read_objects=(ArtifactReadRequest(ref, interval, admitted_bytes),)),
            RunAccessOptions(max_total_read_bytes=admitted_bytes, max_operations=8),
        )).unwrap()
        async with access:
            reader = (await access.storage.artifacts.open(access.context, ref, interval, admitted_bytes)).unwrap()
            try:
                chunk = (await reader.read(access.context, max(1, size))).unwrap()
            finally:
                await reader.aclose(access.context)
        return {"schema_version": 1, "run_id": run_id, "artifact_ref": ref.to_dict(),
            "encoding": "base64", "data": base64.b64encode(chunk.bytes).decode("ascii"),
            "start": start, "next_offset": end, "eof": end == length,
            "byte_length": length, "media_type": descriptor.get("media_type"),
            "sha256": descriptor.get("sha256")}

    async def _find_object(self, run_id, ref):
        cursor = None
        for _ in range(32):
            page = await self.objects(run_id, cursor, 100)
            for obj in page["objects"]:
                candidate = obj.get("ref", obj.get("artifact_ref"))
                if candidate == ref.to_dict():
                    return obj
            cursor = page.get("cursor")
            if cursor is None:
                break
        raise EngineError("NOT_FOUND", "Artifact is not in this run's bounded object catalog")

    async def close(self, *, timeout_seconds=30):
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 60:
            raise ValueError("close timeout must be positive and at most 60 seconds")
        self._closing = True
        try:
            # Include lock acquisition and accepted-state publication in the
            # same deadline, not only the later model/tool execution wait.
            async with asyncio.timeout(timeout_seconds):
                async with self._start_lock:
                    tasks = list(self._starting)
                    for live in self._runs.values():
                        if live.task and not live.task.done():
                            live.session.context.cancellation.set()
                            tasks.append(live.task)
                # Queued admissions must be able to acquire the lock, observe
                # closing, and settle. Never await them while holding the lock.
                if tasks:
                    await asyncio.wait(tasks)
                # A startup already past accepted-state publication can create
                # its cancelled Runtime task as it settles; drain that task too.
                remaining = [r.task for r in self._runs.values() if r.task and not r.task.done()]
                for live in self._runs.values():
                    if live.task and not live.task.done():
                        live.session.context.cancellation.set()
                if remaining:
                    await asyncio.wait(remaining)
            return CleanupReport()
        except TimeoutError:
            pending = [task for task in self._starting if not task.done()]
            pending += [r.task for r in self._runs.values() if r.task and not r.task.done()]
            return CleanupReport(False, ["Service admission/execution cleanup exceeded deadline"],
                [task.get_name() for task in pending])

    @staticmethod
    def _limit(limit):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise EngineError("INVALID_DATA", "Page limit must be between 1 and 100")
