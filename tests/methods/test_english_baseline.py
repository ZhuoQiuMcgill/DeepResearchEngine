"""English publication remains enforced when the model reviewer misses Chinese."""
import base64
import json

import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.bootstrap import create_method_registry
from deepresearch.methods.baseline.stages.reporting import english_report_issues
from tests.methods.test_baseline import ACCEPT, PLAN, REPORT, analysis, close, configured, request, settle

CHINESE_REPORT = "# 研究结论\n\n现有证据支持这个发现 [requested-001]。\n\n## 局限\n只读过选定文本。\n"


def test_english_roles_are_new_exact_pins_and_keep_expanded_budgets():
    definition, method = create_method_registry().resolve("baseline", 4)
    assert definition.agent_roles == (("baseline.planner", 2), ("baseline.analyst", 2),
        ("baseline.writer", 4), ("baseline.reviewer", 3))
    assert definition.tool_revisions == {"web.search": 2}
    assert method.defaults["max_sources"] == 20 and method.defaults["max_rounds"] == 2
    assert method.defaults["context_tokens"] == 131072
    catalog = AgentCatalog()
    for role, old, new in (("baseline.writer", 3, 4), ("baseline.reviewer", 2, 3)):
        before, after = catalog.load(role, old), catalog.load(role, new)
        assert before.ref != after.ref
        assert "Write your final output in English." in after.instructions
        assert "Respond in the language appropriate" in before.instructions
        compiled = after.compile_definition(profile_ref="controlled", model_ref="deepseek-flash")
        assert compiled.limits["max_context_tokens"] == 262144


def test_language_check_allows_original_names_only_in_references():
    assert english_report_issues(CHINESE_REPORT)
    assert english_report_issues("# Findings\n\n这里有中文正文。 [source-1]\n")
    assert not english_report_issues(REPORT + "\n## References\n[source-1] 中文来源标题.\n")


@pytest.mark.asyncio
async def test_chinese_draft_is_retained_then_rewritten_even_if_reviewer_accepts(tmp_path, monkeypatch):
    engine, service, _, calls, _, _ = await configured(tmp_path, monkeypatch,
        [PLAN, analysis(), CHINESE_REPORT, ACCEPT, REPORT, ACCEPT])
    try:
        view = await settle(service, (await service.start_run(request(max_report_attempts=2).model_copy(
            update={"method_revision": 4}))).run_id)
        assert view.status == "succeeded", view.error
        part = await service.read_artifact(view.run_id, view.result_manifest_ref.artifact_id)
        result = json.loads(base64.b64decode(part["data"]))
        assert [draft["accepted"] for draft in result["drafts"]] == [False, True]
        assert result["drafts"][0]["structural_issues"]
        part = await service.read_artifact(view.run_id, result["drafts"][0]["draft_ref"]["artifact_id"])
        assert base64.b64decode(part["data"]).decode("utf-8") == CHINESE_REPORT
        part = await service.read_report(view.run_id)
        assert base64.b64decode(part["data"]).decode("utf-8") == REPORT
        assert len(calls) == 6
        assert "Write all report headings and narrative in English" in calls[4]["messages"][1]["content"]
    finally:
        await close(engine, service)


@pytest.mark.asyncio
async def test_chinese_only_draft_exhausts_review_budget_without_final_report(tmp_path, monkeypatch):
    engine, service, _, calls, _, _ = await configured(tmp_path, monkeypatch,
        [PLAN, analysis(), CHINESE_REPORT, ACCEPT])
    try:
        view = await settle(service, (await service.start_run(request(max_report_attempts=1).model_copy(
            update={"method_revision": 4}))).run_id)
        assert view.status == "failed" and view.error["code"] == "REPORT_REVIEW_FAILED"
        assert view.report_ref is None and len(calls) == 4
    finally:
        await close(engine, service)
