"""The offline auditor follows real Runtime/Storage references and detects tampering."""
from pathlib import Path
import runpy
import sqlite3

import pytest

from tests.methods.test_parallel_baseline import ALPHA, _configured, _json, _lines, _request, _settle
from tests.methods.test_selection_baseline import _decision
from tests.methods.test_systemic_baseline import valid_report


@pytest.mark.asyncio
@pytest.mark.parametrize("broken_role", ["baseline.selector", "baseline.distiller", "baseline.writer"])
async def test_store_audit_checks_repaired_inputs_and_immutable_bytes(tmp_path, monkeypatch, broken_role):
    def respond(role, value, ordinal):
        if role == broken_role and ordinal == 1:
            return '{"source_id":"one","source_id":"two"}'
        if role == "baseline.selector":
            return _decision(value)
        if role == "baseline.writer": return valid_report(value)
        return None
    async with _configured(tmp_path, monkeypatch, {ALPHA: _lines("SOURCE")}, respond=respond) as h:
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={"method_revision": 11})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        writer_nodes = [node for node in view.nodes if node.kind == "agent"
                        and node.detail.get("role_id") == "baseline.writer"]
        assert len(writer_nodes) == len(h.role_calls("writer"))
        for node, call in zip(writer_nodes, h.role_calls("writer")):
            assert await _json(h.service, view.run_id, node.detail["input_ref"]) == call["input"]
    auditor = runpy.run_path(str(Path(__file__).resolve().parents[2] / "examples/benchmarks/audit_research_store.py"))["audit"]
    store = tmp_path / "store"
    result = auditor(store)
    assert result["findings"] == [] and result["integrity"] == "ok"
    assert result["role_repairs"] == 1 and result["verified_findings"] > 0
    assert result["role_repair_events"] == (1 if broken_role == "baseline.selector" else 0)
    assert result["role_repair_inputs_unavailable"] == 0
    assert result["runs"][0]["citation_errors"] == [] and result["runs"][0]["literal_primary_queries"] == 1
    with sqlite3.connect((store / "store.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        key = db.execute("SELECT relative_key FROM artifacts WHERE object_id=?", (view.report_ref.artifact_id,)).fetchone()[0]
    path = store / key
    path.write_bytes(path.read_bytes() + b"\n")
    damaged = auditor(store)
    assert damaged["integrity"] == "ok"  # SQLite alone cannot check archived file bytes.
    assert {f["kind"] for f in damaged["findings"]} == {"artifact_hash"}
