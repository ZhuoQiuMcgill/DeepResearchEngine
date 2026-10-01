from __future__ import annotations

import asyncio
import dataclasses

from ebd.agent import RecordedToolAction
from ebd.connections.engine import ToolPlanFactory
from ebd.contracts import (AttemptLease, BindingSet, EngineError, Err, ExecutionContext,
    Grant, GrantSet, Ok, ScopeRef, SnapshotProposal, ToolRef, ToolRequest,
    ToolStoragePlan, deadline_after)
from ebd.storage import StorageSession
from ebd.toolset import ToolCatalog, ToolExecutor
from ebd.toolset.common import encode, strict_json
from ebd.toolset.process import ProcessOutcome
from ebd.toolset.retrieval import extract, pack_component


async def setup(path):
    store = (await StorageSession.open({"root": path})).unwrap()
    scope = ScopeRef("run", "tool-test")
    context = ExecutionContext("tool-test", "tool-test", "corr", "root", principal="test", context_kind="standalone_tool",
        store_id=store.store_id, scope=scope, deadline=deadline_after(60), grants=GrantSet([Grant("*")], "test"))
    (await store.provision_run(context, {"run_id": context.run_id, "root_run_id": context.root_run_id, "owner_principal": "test"})).unwrap()
    catalog, executor = ToolCatalog(), ToolExecutor()
    binding = BindingSet(catalog, executor, store.recorder, store.artifacts, store.snapshots, ToolPlanFactory(store, scope), storage=store)
    return store, context, binding


def test_real_storage_recording_and_exact_worker_read(tmp_path):
    async def check():
        store, context, binding = await setup(tmp_path / "store")
        proposal = SnapshotProposal(**extract("中abc\nsecond\n".encode(), {"content_type": "text/plain"}))
        receipt = (await store.snapshots.commit(context, "seed", context.scope, proposal)).unwrap()
        first = await RecordedToolAction().run(ToolRequest(ToolRef("document.read"), {"snapshot_ref": receipt.snapshot_ref.to_dict(),
            "range": {"kind": "lines", "start": 1, "end_exclusive": 3}, "max_text_bytes": 4}), binding, context.for_action("read-first", root_action_id="read-first"))
        assert first.status == "succeeded" and first.recording["status"] == "complete"
        assert first.result["text"] == "中a" and first.result["continuation"]
        second = await RecordedToolAction().run(ToolRequest(ToolRef("document.read"), {"snapshot_ref": receipt.snapshot_ref.to_dict(),
            "range": {"kind": "lines", "start": 1, "end_exclusive": 3}, "continuation": first.result["continuation"]}), binding, context.for_action("read-next", root_action_id="read-next"))
        assert second.status == "succeeded"
        assert first.result["text"] + second.result["text"] == "中abc\nsecond"
        events = (await store.activity.query(context, {"run_id": context.run_id}, limit=100)).unwrap().events
        tools = [event for event in events if event["event"]["kind"].startswith("tool.")]
        assert [event["event"]["kind"] for event in tools] == ["tool.intent", "tool.outcome", "tool.intent", "tool.outcome"]
        assert all(result.process["cleanup"]["complete"] for result in (first, second))
        await binding.executor.close(); await store.close()
    asyncio.run(check())


def test_unrecorded_attempt_and_reused_attempt_never_spawn(tmp_path):
    async def check():
        store, context, binding = await setup(tmp_path / "store")
        attempt = context.for_action("tool", "attempt")
        definition = binding.catalog.resolve("web.search").unwrap()
        plan = ToolStoragePlan(definition.ref, attempt, lease=AttemptLease(attempt))
        outcome = await binding.executor.execute(definition, {"query": "x"}, attempt, plan)
        assert outcome.error.code == "ACCESS_DENIED" and not outcome.process["dispatched"]
        assert not binding.executor.runner._active
        await binding.executor.close(); await store.close()
    asyncio.run(check())


def test_lost_commit_ack_uses_real_status_no_second_worker_or_source(tmp_path):
    # The controlled worker supplies a retained fixture; publication/status and
    # lifecycle are real. Live network/worker acceptance is a separate script.
    async def check():
        store, context, binding = await setup(tmp_path / "store")
        proposal = extract(b"retained same body\n", {"content_type": "text/plain", "requested_url": "https://example.com/", "final_url": "https://example.com/", "redirects": [], "retrieved_at": "2026-10-01T00:00:00Z", "http_status": 200, "content_encoding": None, "declared_content_length": None, "http_request_count": 1, "http_response_count": 1, "response_transfer_bytes": 19, "response_decoded_bytes": 19, "etag": None, "last_modified": None})
        calls = {"worker": 0, "commit": 0}
        class FixtureWorker:
            memory_bytes = 512 << 20
            async def run(self, argv, payload, **kwargs):
                calls["worker"] += 1
                request = strict_json(payload, 1 << 20)
                prepared = {"operation_id": request["plan"]["operation_id"], "proposal": {**proposal,
                    **{key: pack_component(proposal[key]) for key in ("original", "text", "index")}}}
                response = {key: request[key] for key in ("schema_version", "request_id", "tool", "invocation")}
                response.update(message_type="worker_response", phase="prepared", prepared=prepared, error=None,
                    observations={"http_status": 200, "redirects": [], "final_url": "https://example.com/", "extraction_version": proposal["extraction_version"]}, usage={"http_request_count": 1})
                output = encode(response)
                return ProcessOutcome(exit_code=0, stdout=output, stdin_bytes=len(payload), stdout_bytes=len(output), cleanup_complete=True)
            async def close(self, deadline=None): return {"complete": True}
        class LostReply:
            async def commit(self, *args):
                calls["commit"] += 1
                (await store.snapshots.commit(*args)).unwrap()
                return Err(EngineError("STORAGE_UNAVAILABLE", "controlled lost acknowledgment", commit_state="unknown", retryable_delivery=True))
        class Factory(ToolPlanFactory):
            def for_attempt(self, *args):
                result = super().for_attempt(*args)
                result.value.snapshot_store = LostReply()
                return result
        binding.executor.runner = FixtureWorker()
        binding.storage_plan_factory = Factory(store, context.scope)
        result = await RecordedToolAction().run(ToolRequest(ToolRef("web.fetch"), {"url": "https://example.com/"}), binding, context)
        assert result.status == "succeeded" and result.recording["status"] == "complete"
        assert result.persistence["commit_state"] == "committed"
        assert calls == {"worker": 1, "commit": 1}
        await binding.executor.close(); await store.close()
    asyncio.run(check())
