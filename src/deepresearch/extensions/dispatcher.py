"""Deterministic mediation with mandatory recording and cooperative timeouts."""
from __future__ import annotations

import asyncio
from typing import Any

from deepresearch.engine.contracts import CleanupReport, EngineError, Err
from ._snapshot import MAX_ACTIVE_HANDLERS, candidates
from .registry import ExtensionRegistry, _Registration, _async_callable
from .types import HookDecision, HookEvent, RecordCallback


class _HookFailure(Exception):
    def __init__(self, reason: str, code: str) -> None:
        self.reason = reason
        self.code = code
        super().__init__(reason)


class HookDispatcher:
    def __init__(self, registry: ExtensionRegistry, record_async_callback: RecordCallback) -> None:
        if type(registry) is not ExtensionRegistry or not _async_callable(record_async_callback):
            raise EngineError("extension.invalid_dispatcher", "Dispatcher requires a registry and an async recording callback")
        self._registrations = registry._snapshot()
        self._record_callback = record_async_callback
        self._active: set[asyncio.Task] = set()
        self._closed = False

    async def close(self, timeout_seconds: float = 5.0) -> CleanupReport:
        """Drain owned handlers; uncooperative Python callbacks remain visible."""
        if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 30:
            raise EngineError("extension.invalid_timeout", "Extension cleanup must be bounded")
        self._closed = True
        pending = tuple(self._active)
        if not pending:
            return CleanupReport()
        for task in pending:
            task.cancel()
        _, unsettled = await asyncio.wait(pending, timeout=timeout_seconds)
        if unsettled:
            return CleanupReport(False, ["Extension handlers did not settle"],
                [f"extension-handler-{id(task)}" for task in unsettled])
        return CleanupReport()

    @staticmethod
    def _event(event: HookEvent) -> None:
        if type(event) is not HookEvent:
            raise EngineError("extension.invalid_event", "Dispatcher requires a HookEvent snapshot")

    @staticmethod
    def _metadata(entry: _Registration, event: HookEvent) -> dict[str, Any]:
        spec = entry.spec
        return {"schema_version": 1, "run_id": event.run_id, "node_id": event.node_id,
                "point": event.point, "payload_digest": event.payload_digest,
                "extension_id": spec.extension_id, "revision": spec.revision,
                "mode": spec.mode, "config_digest": spec.config_digest,
                "timeout_seconds": spec.timeout_seconds}

    async def _record(self, kind: str, payload: dict[str, Any]) -> None:
        # This await is intentionally outside hook error isolation and timeouts.
        result = await self._record_callback(kind, payload)
        if isinstance(result, Err):
            raise result.error

    def _settled(self, task: asyncio.Task) -> None:
        self._active.discard(task)
        if not task.cancelled():
            task.exception()  # Retrieve late exceptions without recording private messages.

    async def _invoke(self, entry: _Registration, *args: Any) -> Any:
        if self._closed:
            raise _HookFailure("closed", "extension.closed")
        if len(self._active) >= MAX_ACTIVE_HANDLERS:
            raise _HookFailure("capacity", "extension.capacity")

        async def call() -> Any:
            return await entry.handler(*args)

        task = asyncio.create_task(call())
        self._active.add(task)
        task.add_done_callback(self._settled)
        try:
            done, _ = await asyncio.wait((task,), timeout=entry.spec.timeout_seconds)
            if not done:
                # Do not wait indefinitely for a handler that suppresses cancellation.
                task.cancel()
                raise _HookFailure("timeout", "extension.timeout")
            return task.result()
        except asyncio.CancelledError:
            caller = asyncio.current_task()
            if caller is not None and caller.cancelling():
                task.cancel()
                raise
            raise _HookFailure("cancelled", "extension.failed") from None
        except _HookFailure:
            raise
        except Exception as error:
            if isinstance(error, EngineError) and error.code == "extension.invalid_decision":
                raise _HookFailure("invalid_decision", "extension.invalid_decision") from None
            raise _HookFailure("error", "extension.failed") from None

    async def observe(self, event: HookEvent) -> None:
        self._event(event)
        for entry in self._registrations:
            if entry.spec.mode != "observe" or event.point not in entry.spec.points:
                continue
            payload = self._metadata(entry, event)
            try:
                await self._invoke(entry, event)
            except _HookFailure as failure:
                payload["failure"] = failure.reason
                await self._record("workflow.hook.failed", payload)
            except asyncio.CancelledError:
                payload["failure"] = "caller_cancelled"
                await self._record("workflow.hook.failed", payload)
                raise
            else:
                await self._record("workflow.hook.observed", payload)

    @staticmethod
    def _decision(value: Any, current: tuple[str, ...]) -> tuple[str, ...]:
        if type(value) is not HookDecision:
            raise _HookFailure("invalid_decision", "extension.invalid_decision")
        try:
            keep = candidates(value.keep_ids)
        except EngineError:
            raise _HookFailure("invalid_decision", "extension.invalid_decision") from None
        available = set(current)
        if any(item not in available for item in keep):
            raise _HookFailure("invalid_decision", "extension.invalid_decision")
        return keep

    async def select(self, event: HookEvent, candidate_ids: list[str] | tuple[str, ...]) -> list[str]:
        self._event(event)
        original = current = candidates(candidate_ids)
        for entry in self._registrations:
            if entry.spec.mode != "control" or event.point not in entry.spec.points:
                continue
            payload = self._metadata(entry, event)
            payload.update(original_candidate_ids=list(original), candidate_ids=list(current))
            failure = None
            try:
                response = await self._invoke(entry, event, current)
                keep = self._decision(response, current)
            except _HookFailure as error:
                failure = error
            except asyncio.CancelledError:
                payload["failure"] = "caller_cancelled"
                await self._record("workflow.hook.failed", payload)
                raise
            if failure is not None:
                payload["failure"] = failure.reason
                await self._record("workflow.hook.failed", payload)
                raise EngineError(failure.code, "Control hook did not produce a valid recorded selection",
                                  {"extension_id": entry.spec.extension_id,
                                   "revision": entry.spec.revision, "point": event.point,
                                   "failure": failure.reason}) from None
            payload["keep_ids"] = list(keep)
            await self._record("workflow.hook.decision", payload)
            current = keep
        return list(current)
