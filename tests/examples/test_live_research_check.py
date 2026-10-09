"""HTTP acceptance must preserve evidence and recognize repaired logical roles."""
import argparse
from pathlib import Path
import runpy

import pytest


def example():
    return runpy.run_path(str(Path(__file__).resolve().parents[2] / "examples/live_research_check.py"))


def event(node, kind="workflow.node.completed", status="succeeded"):
    return {"event": {"kind": kind, "payload": {"node_id": node, "status": status}}}


@pytest.mark.parametrize("role", ["plan.research", "r1.analyze.evidence", "report.1.review"])
@pytest.mark.parametrize("attempt", [2, 3, 10])
def test_successful_repaired_role_counts_without_its_failed_first_attempt(role, attempt):
    nodes = {"plan.research", "r1.analyze.evidence", "report.1.review", "publish.result"}
    rows = [event(n) for n in nodes - {role}]
    rows += [event(role, "workflow.node.failed", "failed"), event(f"{role}.repair-{attempt}")]
    assert f"{role}.repair-{attempt}" in example()["completed_baseline_nodes"](rows)


@pytest.mark.parametrize("suffix", [".validate", ".repair-1", ".repair-02", ".repair-2.validate", ".repair-2x", ".other"])
def test_validation_or_unrelated_node_cannot_replace_a_role(suffix):
    rows = [event(n) for n in ("plan.research", "r1.analyze.evidence", "publish.result")]
    with pytest.raises(AssertionError, match="report.1.review"):
        example()["completed_baseline_nodes"](rows + [event("report.1.review" + suffix)])


def test_failure_does_not_count_and_publication_requires_its_exact_node():
    check = example()["completed_baseline_nodes"]
    rows = [event(n) for n in ("plan.research", "r1.analyze.evidence", "report.1.review")]
    with pytest.raises(AssertionError, match="publication"):
        check(rows + [event("publish.result.repair-2")])
    rows[-1] = event("report.1.review.repair-2", status="failed")
    with pytest.raises(AssertionError, match="report.1.review"):
        check(rows + [event("publish.result")])


@pytest.mark.asyncio
async def test_later_acceptance_failure_retains_real_http_report_and_events(tmp_path, monkeypatch):
    module = example()
    original = module["replay"]
    async def duplicate_terminal(client, run_id):
        rows = await original(client, run_id)
        return rows + [next(row for row in rows if row["event"]["kind"] == "workflow.finished")]
    monkeypatch.setitem(module["check"].__globals__, "replay", duplicate_terminal)
    output = tmp_path / "evidence"
    args = argparse.Namespace(store=tmp_path / "store", request=None, output=output,
                              expected_question=module["EBD_EXPERIMENT_QUESTION"])
    with pytest.raises(AssertionError):
        await module["check"](args)
    assert b"Shared workflow interfaces are ready." in (output / "report.md").read_bytes()
    assert (output / "events.json").exists() and (output / "run.json").exists()
    assert not (output / "acceptance.json").exists()
