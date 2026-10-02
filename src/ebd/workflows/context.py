"""Node lifecycle and abstract host services for reusable methods."""
from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from typing import Any, Protocol

from ebd.engine.contracts import EngineError, canonical_json, digest_json
from ebd.extensions import HookEvent


class PlatformPort(Protocol):
    def assert_active(self) -> None: ...
    async def run_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
    async def emit(self, kind: str, payload: dict[str, Any], *, cleanup: bool = False): ...
    async def update(self, *, cleanup: bool = False, **fields): ...
    async def publish(self, content: bytes, media_type: str, filename: str) -> dict[str, Any]: ...
    async def save_checkpoint(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def invoke_agent(self, role_id: str, task_input: dict[str, Any]) -> dict[str, Any]: ...


class WorkflowContext:
    def __init__(self, run_id, model_ref, port: PlatformPort, hooks, token_meter):
        self.run_id, self.model_ref = run_id, model_ref
        self.port, self.hooks, self.tokens = port, hooks, token_meter
        self.nodes = {}

    @asynccontextmanager
    async def node(self, node_id: str, kind: str, detail=None):
        self.port.assert_active()
        if not node_id or node_id in self.nodes:
            raise EngineError("INVALID_DATA", "A logical node identity can execute only once")
        detail = dict(detail or {})
        canonical_json(detail, 16384)
        node = {"schema_version": 1, "node_id": node_id, "kind": kind, "status": "running", "detail": detail}
        self.nodes[node_id] = node
        await self.port.update(nodes=list(self.nodes.values()))
        try:
            await self.port.emit("workflow.node.started", node)
            await self.hooks.observe(HookEvent(self.run_id, node_id, "node.before",
                {"kind": kind, "status": "running", "detail_sha256": digest_json(detail)}))
            yield node
            self.port.assert_active()
        except BaseException as error:
            cancelled = isinstance(error, asyncio.CancelledError) or (isinstance(error, EngineError) and error.code == "CANCELLED")
            node["status"] = "cancelled" if cancelled else "failed"
            node["detail"] = {**detail, "error_code": error.code if isinstance(error, EngineError) else type(error).__name__}
            await self.port.emit("workflow.node.failed", node, cleanup=True)
            await self.port.update(cleanup=True, nodes=list(self.nodes.values()))
            await self.hooks.observe(HookEvent(self.run_id, node_id, "node.failed",
                {"kind": kind, "status": node["status"], "detail_sha256": digest_json(node["detail"])}))
            raise
        else:
            node["status"] = "succeeded"
            await self.port.emit("workflow.node.completed", node)
            await self.hooks.observe(HookEvent(self.run_id, node_id, "node.after",
                {"kind": kind, "status": "succeeded", "detail_sha256": digest_json(node["detail"])}))
            await self.port.update(nodes=list(self.nodes.values()))

    async def select(self, node_id, point, candidate_ids):
        return await self.hooks.select(HookEvent(self.run_id, node_id, point,
            {"candidate_ids": list(candidate_ids)}), list(candidate_ids))

    async def checkpoint(self, payload):
        receipt = await self.port.save_checkpoint(payload)
        await self.port.update(checkpoint_ref=receipt)
        return receipt
