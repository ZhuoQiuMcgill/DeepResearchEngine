"""Recorded role invocation and explicit reading of its retained output."""
from __future__ import annotations

from deepresearch.engine.contracts import EngineError


async def invoke_role(context, role_id, task_input, *, node_id, max_output_bytes=65536, input_ref=None):
    task_input = {**getattr(context, "agent_input_defaults", {}), **task_input}
    detail = {"role_id": role_id}
    if input_ref is not None:
        detail["input_ref"] = input_ref
    async with context.node(node_id, "agent", detail):
        outcome = await context.port.invoke_agent(role_id, task_input)
        if (outcome.get("status") != "succeeded" or outcome.get("recording_status") != "complete"
                or not outcome.get("output_ref")):
            raise EngineError("ROLE_FAILED", "Role did not publish a recorded output",
                {"role_id": role_id, "status": outcome.get("status"), "error": outcome.get("error")})
        raw = await context.port.read_artifact(outcome["output_ref"], max_bytes=max_output_bytes)
        return raw, outcome
