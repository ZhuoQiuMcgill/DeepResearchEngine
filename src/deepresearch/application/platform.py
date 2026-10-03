"""A method's host port over one live, model-free Workflow authority."""
from __future__ import annotations

import asyncio
from typing import Any

from deepresearch.engine.contracts import (
    ArtifactRef, CheckpointEnvelope, EngineError, Err, Ok, StateCommitReceipt, StateMutation,
    canonical_json, new_id, to_json_value,
)
from deepresearch.workflows.contracts import ResearchRunView
from .usage import aggregate_usage

RESEARCH_STATE_KEY = "research.run/1"


class _RoleCancellation(asyncio.Event):
    """Local cancellation that also observes the root signal synchronously."""

    def __init__(self, parent):
        super().__init__()
        self._parent = parent

    def is_set(self):
        return super().is_set() or self._parent.is_set()

    async def wait(self):
        if self.is_set():
            return True
        return await super().wait()


class ResearchPlatformPort:
    """Methods never receive credentials, a provider or unscoped Storage.

    Tool and invocation returns retain their complete execution/recording facts.
    Publications return opaque, store-qualified references in the root scope.
    """

    def __init__(self, engine, live, roles):
        self.engine, self.live, self.roles = engine, live, roles
        self._lock = asyncio.Lock()
        self.failure: EngineError | None = None
        self._projection_error: EngineError | None = None
        self._role_usages = []

    @property
    def session(self):
        return self.live.session

    def assert_active(self):
        self.session.binding.lease.assert_active()
        self.session.context.assert_active()
        if self.session.context.grants.is_revoked():
            raise EngineError("ACCESS_DENIED", "Workflow authority is revoked")

    def fail(self, error):
        if self.failure is None:
            self.failure = error
        return error

    async def commit(self, view: ResearchRunView, *, cleanup=False):
        """CAS the projection; never allocate another execution/read budget."""
        async with self._lock:
            return await self._commit(view, cleanup=cleanup)

    async def request_cancellation(self):
        async with self._lock:
            self.session.context.cancellation.set()
            if not self.live.view.cancellation_requested:
                await self._commit(self.live.view.model_copy(update={"cancellation_requested": True}), cleanup=True)
                await self.emit("workflow.cancellation.requested", {"requested": True}, cleanup=True)
            return self.live.view.model_copy(deep=True)

    async def _commit(self, view, *, cleanup=False):
        context = self.session.context.for_cleanup(5) if cleanup else self.session.context
        self.session.binding.lease.assert_active()
        context.assert_active()
        if context.grants.is_revoked():
            raise EngineError("ACCESS_DENIED", "Workflow authority is revoked")
        if self._projection_error is not None:
            raise self._projection_error
        state = {"schema_version": 1, "request_fingerprint": self.live.fingerprint,
                 "method_manifest_ref": self.live.method_manifest_ref,
                 "view": view.to_dict()}
        operation = new_id("research_state_")
        expected_version = self.live.version
        mutation = StateMutation(self.session.context.scope, RESEARCH_STATE_KEY,
                                 "put", expected_version, state)

        async def settle():
            try:
                try:
                    written = await self.session.binding.storage.state.commit(context, operation, [mutation])
                except asyncio.CancelledError:
                    written = Err(EngineError("STATE_COMMIT_UNKNOWN", "Projection commit owner was interrupted",
                                              {"operation_id": operation}, commit_state="unknown"))
                if isinstance(written, Err) and written.error.commit_state == "unknown":
                    checked = await self.session.binding.storage.operations.status(context.for_cleanup(5), operation)
                    if isinstance(checked, Ok) and checked.value.state == "committed" and checked.value.receipt is not None:
                        written = Ok(checked.value.receipt)
                receipt = written.unwrap()
                scope = self.session.context.scope
                versions = [{"scope": f"{scope.kind}:{scope.id}", "key": RESEARCH_STATE_KEY,
                             "old_version": expected_version, "new_version": expected_version + 1}]
                if (not isinstance(receipt, StateCommitReceipt) or receipt.operation_id != operation
                        or receipt.store_id != context.store_id or receipt.mutation_versions != versions):
                    raise EngineError("INTEGRITY_ERROR", "Projection commit receipt differs from its admitted mutation",
                                      {"operation_id": operation}, commit_state="unknown")
                self.live.version = expected_version + 1
                self.live.view = view
                return receipt
            except EngineError as error:
                if error.commit_state == "unknown":
                    # An uncertain head cannot authorize a fresh CAS. Preserve
                    # the original uncertainty rather than masking it later.
                    self._projection_error = error
                self.fail(error)
                raise

        pending = asyncio.create_task(settle(), name=f"deepresearch-projection:{self.live.view.run_id}")
        cancelled = False
        try:
            while True:
                try:
                    return await asyncio.shield(pending)
                except asyncio.CancelledError:
                    if pending.cancelled():
                        raise
                    cancelled = True
        finally:
            if cancelled:
                raise asyncio.CancelledError

    async def update(self, *, cleanup=False, **fields):
        allowed = {"nodes", "sources", "context_plan", "report_ref",
                   "result_manifest_ref", "checkpoint_ref", "usage", "quality"}
        if (not cleanup and set(fields) <= {"nodes", "sources"}
                and (self.session.context.cancellation.is_set()
                     or self.session.context.remaining_seconds() <= 0)):
            cleanup = True
        if type(cleanup) is not bool:
            raise EngineError("INVALID_DATA", "Projection cleanup must be a boolean")
        if cleanup:
            allowed = {"nodes", "sources"}
        if set(fields) - allowed:
            raise EngineError("INVALID_DATA", "Method cannot change application lifecycle or identity")
        async with self._lock:
            try:
                view = ResearchRunView.model_validate({**self.live.view.to_dict(),
                    **{key: to_json_value(value) for key, value in fields.items()}})
            except (ValueError, TypeError):
                raise EngineError("INVALID_DATA", "Invalid research projection fields") from None
            if cleanup:
                old_nodes = {node.node_id: node for node in self.live.view.nodes}
                for node in view.nodes:
                    old = old_nodes.get(node.node_id)
                    if old is None or node.kind != old.kind or (node.status == "succeeded" and node != old):
                        raise EngineError("ACCESS_DENIED", "Cleanup cannot add or succeed an execution node")
                old_sources = {source.item_id: source for source in self.live.view.sources.items}
                for source in view.sources.items:
                    old = old_sources.get(source.item_id)
                    if (old is None or source.url != old.url or source.snapshot_ref != old.snapshot_ref
                            or (source.status == "succeeded" and source != old)):
                        raise EngineError("ACCESS_DENIED", "Cleanup cannot add or succeed a source publication")
            for key in ("report_ref", "result_manifest_ref"):
                ref = getattr(view, key)
                if key in fields and ref is not None:
                    descriptor = (await self.session.binding.storage.describe_object(
                        self.session.context, ArtifactRef(ref.store_id, ref.artifact_id),
                    )).unwrap()
                    if descriptor["scope"] != self.session.context.scope.to_dict():
                        raise EngineError("ACCESS_DENIED", "Research artifacts must belong to this Workflow")
            try:
                return await self._commit(view, cleanup=cleanup)
            except EngineError as error:
                if (not cleanup or error.code != "ACCESS_DENIED"
                        or error.message != "cleanup cannot perform business operations"):
                    raise
                # Older shared grants cannot CAS after cancellation. Keep the
                # validated failure projection for committed terminal recording.
                self.live.view = view
                return None

    async def emit(self, kind, payload, *, cleanup=False):
        try:
            return (await self.engine.emit_workflow_event(
                self.session, kind, payload, cleanup=cleanup,
            )).unwrap()
        except EngineError as error:
            self.fail(error)
            raise

    async def record_hook(self, kind, payload):
        cleanup = kind == "workflow.hook.failed" or (
            kind == "workflow.hook.observed" and payload.get("point") == "node.failed")
        return await self.emit(kind, payload, cleanup=cleanup)

    @staticmethod
    def boundary_error(code, message, original=None):
        original = to_json_value(original) if original is not None else {}
        return EngineError(code, message,
            {"cause_code": original["code"]} if original.get("code") else {},
            observed_effect_state=original.get("observed_effect_state", "not_observed"),
            commit_state=original.get("commit_state", "not_applicable"),
            retryable_delivery=original.get("retryable_delivery", False))

    async def run_tool(self, name: str, arguments: dict[str, Any]):
        self.assert_active()
        tool = next((ref for ref in self.live.tools if ref.name == name), None)
        if tool is None:
            raise EngineError("ACCESS_DENIED", "Tool is outside the selected Workflow catalog")
        result = to_json_value(await self.engine.run_workflow_tool(self.session, tool, arguments))
        if result.get("recording", {}).get("status") != "complete":
            raise self.fail(self.boundary_error("RECORDING_INCOMPLETE", "Workflow tool recording is incomplete",
                result.get("recording", {}).get("error") or result.get("error")))
        if not result.get("process", {}).get("cleanup", {}).get("complete", True):
            raise self.fail(self.boundary_error("CLEANUP_INCOMPLETE", "Workflow tool cleanup is incomplete", result.get("error")))
        if result.get("status") == "unknown":
            raise self.fail(EngineError("OUTCOME_UNKNOWN", "Workflow tool outcome is unknown",
                observed_effect_state="unknown", commit_state="unknown"))
        return result

    async def publish(self, content: bytes, media_type: str, filename: str):
        self.assert_active()
        if not isinstance(content, bytes):
            raise EngineError("INVALID_DATA", "Publications require immutable bytes")
        try:
            receipt = (await self.session.binding.storage.artifacts.put(
                self.session.context, new_id("research_artifact_"), self.session.context.scope,
                content, {"media_type": media_type, "filename": filename},
            )).unwrap()
        except EngineError as error:
            self.fail(error)
            raise
        return receipt.artifact_ref.to_dict()

    async def save_checkpoint(self, payload):
        self.assert_active()
        canonical_json(payload, 262144)
        envelope = CheckpointEnvelope(self.live.view.run_id, {
            "method_id": self.live.view.method_id,
            "method_revision": self.live.view.method_revision,
            "method_manifest_ref": self.live.method_manifest_ref,
            "data": payload,
        })
        try:
            receipt = (await self.session.binding.storage.checkpoints.save(
                self.session.context, new_id("research_checkpoint_"),
                self.session.context.scope, envelope,
            )).unwrap()
            return receipt.checkpoint_ref.to_dict()
        except EngineError as error:
            self.fail(error)
            raise

    async def read_artifact(self, ref, *, max_bytes=65536):
        """Read a bounded saved Workflow artifact; never fetch or inject context."""
        self.assert_active()
        if type(max_bytes) is not int or not 1 <= max_bytes <= 262144:
            raise EngineError("INVALID_DATA", "Artifact read requires a positive bounded byte limit")
        from deepresearch.workflows.contracts import ArtifactReference
        try:
            parsed = ArtifactReference.model_validate(ref)
        except ValueError:
            raise EngineError("INVALID_DATA", "Artifact reference violates the shared contract") from None
        if parsed.store_id != self.session.context.store_id:
            raise EngineError("ACCESS_DENIED", "Artifact belongs to another Store")
        artifact = ArtifactRef(parsed.store_id, parsed.artifact_id)
        descriptor = (await self.session.binding.storage.describe_object(self.session.context, artifact)).unwrap()
        if descriptor["scope"] != self.session.context.scope.to_dict():
            raise EngineError("ACCESS_DENIED", "Only this Workflow's saved artifacts may be read")
        handle = (await self.session.binding.storage.artifacts.open(
            self.session.context, artifact, max_bytes=max_bytes)).unwrap()
        chunks = []
        try:
            while True:
                self.assert_active()
                chunk = (await handle.read(self.session.context, min(max_bytes, 65536))).unwrap()
                chunks.append(chunk.bytes)
                if sum(len(part) for part in chunks) > max_bytes:
                    raise EngineError("LIMIT_EXCEEDED", "Artifact read exceeded the selected byte limit")
                if chunk.eof:
                    return b"".join(chunks)
                if not chunk.bytes:
                    raise EngineError("INTEGRITY_ERROR", "Artifact read made no progress")
        finally:
            (await handle.aclose(self.session.context)).unwrap()

    async def invoke_agent(self, role_id: str, task_input: dict[str, Any]):
        self.assert_active()
        role = self.roles.get(role_id)
        if role is None:
            raise EngineError("ACCESS_DENIED", "Agent role is outside the pinned method manifest")
        spec, registered = role
        try:
            rendered = spec.render_task(task_input)
        except ValueError:
            raise EngineError("INVALID_DATA", "Role input failed its pinned task template/schema") from None
        # Keep the existing caller's authority and lineage budget. A local
        # signal can settle this invocation without changing Workflow status.
        caller = self.session.context.for_action(self.session.context.action_id,
            self.session.context.attempt_id, cancellation=_RoleCancellation(self.session.context.cancellation))
        invocation = asyncio.create_task(self._invoke_agent(role_id, registered, rendered, caller),
                                         name=f"deepresearch-role:{self.live.view.run_id}:{role_id}")
        cancelled = False
        try:
            while True:
                try:
                    return await asyncio.shield(invocation)
                except asyncio.CancelledError:
                    if invocation.cancelled():
                        raise
                    cancelled = True
                    # Let the bound invoker receive a cancelled AgentResult and
                    # record its outcome, rather than interrupting that owner.
                    caller.cancellation.set()
        finally:
            if cancelled:
                raise asyncio.CancelledError

    async def _invoke_agent(self, role_id, registered, rendered, caller):
        async def propagate_cancel():
            await self.session.context.cancellation.wait()
            caller.cancellation.set()

        watcher = asyncio.create_task(propagate_cancel())
        try:
            outcome = await self.session.binding.invoker.invoke(caller, registered.ref, rendered)
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        value = to_json_value(outcome)
        child = value.get("child_result") or {}
        original_error = value.get("error") or child.get("error")
        if child.get("usage") is not None:
            async with self._lock:
                self._role_usages.append(child["usage"])
                total = aggregate_usage(self._role_usages)
                # Merge recorder facts with the latest projection while owning
                # its CAS lock, including after cancellation or deadline expiry.
                cleanup = (self.session.context.cancellation.is_set()
                           or self.session.context.remaining_seconds() <= 0)
                await self._commit(self.live.view.model_copy(update={"usage": total}), cleanup=cleanup)
        if (value.get("recording_status") == "complete" and not child
                and value.get("status") != "succeeded"):
            error = original_error or {}
            raise self.boundary_error(error.get("code", "WRITER_FAILED"),
                f"Role {role_id} invocation did not dispatch successfully", error)
        if (value.get("recording_status") != "complete"
                or child.get("recording_status") != "complete"
                or not value.get("outcome_receipt") or not child.get("terminal_event_receipt")):
            raise self.fail(self.boundary_error("RECORDING_INCOMPLETE", f"Role {role_id} invocation has no complete durable outcome", original_error))
        if not value.get("cleanup", {}).get("complete", False) or not child.get("cleanup", {}).get("complete", False):
            raise self.fail(self.boundary_error("CLEANUP_INCOMPLETE", f"Role {role_id} invocation cleanup is incomplete", original_error))
        if value.get("status") != "succeeded" or value.get("error"):
            error = value.get("error") or child.get("error") or {}
            raise self.boundary_error(error.get("code", "WRITER_FAILED"), f"Role {role_id} did not complete successfully", error)
        if child.get("persistence_state") != "committed":
            raise self.fail(EngineError("PUBLICATION_INCOMPLETE", f"Role {role_id} output publication is incomplete"))
        if not value.get("output_ref") or not value.get("export_receipt"):
            raise self.fail(EngineError("PUBLICATION_INCOMPLETE", f"Role {role_id} output was not exported to the Workflow"))
        return {"status": value["status"], "recording_status": value["recording_status"],
                "output_ref": value["output_ref"], "child_run": value["child_run"],
                "usage": child.get("usage")}
