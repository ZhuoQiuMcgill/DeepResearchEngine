"""Orchestrator-owned recovery of settled, tool-free role failures.

Providers and Runtime still dispatch once. A recovery is a new recorded child
invocation of the same immutable role/input, grouped under a host operation.
No completed Workflow node or unresolved external attempt is replayed.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import math
import random
import time

from deepresearch.engine.contracts import EngineError, new_id


@dataclass(frozen=True)
class RecoveryPolicy:
    max_restarts: int = 3
    initial_delay_seconds: float = 2
    max_delay_seconds: float = 60
    max_wait_seconds: float = 180
    jitter_fraction: float = .25

    def __post_init__(self):
        if type(self.max_restarts) is not int or not 0 <= self.max_restarts <= 5:
            raise ValueError("max_restarts must be an integer in 0..5")
        for name in ("initial_delay_seconds", "max_delay_seconds", "max_wait_seconds", "jitter_fraction"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Recovery intervals must be finite numbers")
        if not 0 < self.initial_delay_seconds <= self.max_delay_seconds <= self.max_wait_seconds <= 600:
            raise ValueError("Recovery intervals must be ordered and bounded by 600 seconds")
        if not 0 <= self.jitter_fraction <= 1:
            raise ValueError("jitter_fraction must be in 0..1")

    def to_dict(self):
        return {"schema_version": 1, **asdict(self),
                "eligible_http_statuses": [429, 500, 502, 503, 504],
                "eligible_native_service_errors": ["server_error", "insufficient_system_resource"],
                "unknown_outcome_replay": False}


def recoverable(error):
    """Only after complete child/invocation recording and cleanup at the port."""
    details = error.details
    if (not details.get("settled_role_attempt")
            or error.commit_state == "unknown" or error.observed_effect_state != "observed"
            or error.retryable_delivery):
        return False
    if error.code == "provider.incomplete":
        if (type(details.get("visible_text_bytes")) is not int or details["visible_text_bytes"] != 0
                or type(details.get("native_tool_call_count")) is not int or details["native_tool_call_count"] != 0
                or details.get("continuation_limit_exceeded") is not False
                or details.get("incomplete_details_capture") != "absent"
                or details.get("provider_incomplete_reason") is not None):
            return False
        return (details.get("provider_status") == "failed" and details.get("provider_error_code") == "server_error"
                or details.get("provider_status") is None and details.get("native_finish_reason") == "insufficient_system_resource")
    if error.code != "provider.http":
        return False
    status = details.get("http_status")
    if status == 429:
        return (details.get("provider_error_code") == "rate_limit_exceeded"
                and details.get("provider_error_type") != "insufficient_quota")
    return status in {500, 502, 503, 504}


class RecoveryCoordinator:
    """Share provider cooldown across a service's concurrent Workflow runs."""

    def __init__(self, policy=None):
        self.policy = policy if policy is not None else RecoveryPolicy()
        if not isinstance(self.policy, RecoveryPolicy):
            raise ValueError("Expected RecoveryPolicy")
        self._not_before = {}

    async def execute(self, context, key, invoke, emit, detail):
        operation = new_id("recovery_")
        common = {**detail, "recovery_id": operation}
        restarts, waited = 0, 0.0
        previous = None
        while True:
            context.assert_active()
            delay = max(0, self._not_before.get(key, 0) - time.monotonic())
            if delay:
                if delay > self.policy.max_wait_seconds - waited or delay >= context.remaining_seconds():
                    error = previous or EngineError("PROVIDER_COOLDOWN", "Provider cooldown exceeds the remaining wait allowance")
                    await emit("workflow.role.recovery_exhausted", {**common, "reason": "wait_allowance",
                        "restarts": restarts, "waited_seconds": waited, "error": error.to_dict()})
                    raise error
                await emit("workflow.role.wait", {**common, "next_attempt": restarts + 1,
                    "delay_seconds": delay, "reason": "provider_cooldown"})
                started = time.monotonic()
                try:
                    await asyncio.wait_for(context.cancellation.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                waited += time.monotonic() - started
                context.assert_active()
                # Another failure may have extended this shared cooldown.
                continue
            await emit("workflow.role.attempt", {**common, "attempt": restarts + 1})
            try:
                result = await invoke()
            except EngineError as error:
                await emit("workflow.role.attempt_finished", {**common, "attempt": restarts + 1,
                    "status": "failed", "error": error.to_dict()},
                    cleanup=context.cancellation.is_set() or context.remaining_seconds() <= 0)
                if not recoverable(error):
                    raise
                if restarts >= self.policy.max_restarts:
                    await emit("workflow.role.recovery_exhausted", {**common, "reason": "restart_allowance",
                        "restarts": restarts, "waited_seconds": waited, "error": error.to_dict()})
                    raise
                retry_after = error.details.get("retry_after_seconds")
                if (isinstance(retry_after, bool) or not isinstance(retry_after, (int, float))
                        or not math.isfinite(retry_after) or retry_after < 0):
                    retry_after = 0
                if retry_after > self.policy.max_delay_seconds:
                    await emit("workflow.role.recovery_exhausted", {**common, "reason": "server_wait_exceeds_policy",
                        "restarts": restarts, "waited_seconds": waited, "error": error.to_dict()})
                    raise
                delay = max(retry_after, min(self.policy.max_delay_seconds,
                    self.policy.initial_delay_seconds * 2 ** restarts))
                delay = min(self.policy.max_delay_seconds, delay * (1 + random.random() * self.policy.jitter_fraction))
                restarts += 1
                previous = error
                # Journal the decision before any replacement invocation. A
                # failed event write stops recovery, just like failed outcomes.
                await emit("workflow.role.restart", {**common, "next_attempt": restarts + 1,
                    "delay_seconds": delay, "error": error.to_dict()})
                self._not_before[key] = max(self._not_before.get(key, 0), time.monotonic() + delay)
                continue
            await emit("workflow.role.attempt_finished", {**common, "attempt": restarts + 1,
                "status": "succeeded", "child_run": result.get("child_run"), "output_ref": result.get("output_ref")})
            if restarts:
                await emit("workflow.role.recovered", {**common, "attempts": restarts + 1,
                    "waited_seconds": waited, "child_run": result.get("child_run")})
            return result
