"""Cleanup state has exact host-issued keys and the original lineage ledger."""
import pytest

from deepresearch.engine import Engine, EngineSettings
from deepresearch.engine.contracts import Err, StateMutation, Grant


@pytest.mark.asyncio
async def test_workflow_cleanup_writes_only_explicit_state_key(tmp_path):
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store"))).unwrap()
    session = (await engine.open_workflow_session(cleanup_state_keys=("failure-projection",))).unwrap()
    try:
        session.context.cancellation.set()
        cleanup = session.context.for_cleanup(5)
        before = cleanup.ledger.used.get("storage_writes", 0)
        receipt = (await session.binding.storage.state.commit(cleanup, "cleanup-test", [
            StateMutation(cleanup.scope, "failure-projection", "put", 0, {"status": "cancelled"})])).unwrap()
        assert receipt.mutation_versions[0]["new_version"] == 1
        assert cleanup.ledger is session.context.ledger
        assert cleanup.ledger.used["storage_writes"] == before + 1
        denied = await session.binding.storage.state.commit(cleanup, "other-key", [
            StateMutation(cleanup.scope, "unselected", "put", 0, {"value": 1})])
        assert isinstance(denied, Err) and denied.error.code == "ACCESS_DENIED"
        artifact = await session.binding.storage.artifacts.put(cleanup, "forbidden-publication", cleanup.scope, b"new effect")
        assert isinstance(artifact, Err) and artifact.error.code == "ACCESS_DENIED"
    finally:
        assert (await session.close()).complete
        assert (await engine.close()).complete


@pytest.mark.asyncio
async def test_ordinary_workflow_has_no_cleanup_business_state_grant(tmp_path):
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store"))).unwrap()
    session = (await engine.open_workflow_session()).unwrap()
    try:
        session.context.cancellation.set()
        cleanup = session.context.for_cleanup(5)
        cleanup.grants.grants.append(Grant("*", cleanup.scope))
        denied = await session.binding.storage.state.commit(cleanup, "unissued-cleanup", [
            StateMutation(cleanup.scope, "failure-projection", "put", 0, {})])
        assert isinstance(denied, Err) and denied.error.code == "ACCESS_DENIED"
    finally:
        await session.close()
        await engine.close()
