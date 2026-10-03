"""Bounded draft/review policy and deterministic citation checks."""
from __future__ import annotations

import re

from deepresearch.engine.contracts import EngineError
from deepresearch.workflows.components.agents import invoke_role
from ..contracts import ReportReview
from .roles import decision, retain


def citation_issues(report, source_ids):
    # Citation labels are fixed source IDs supplied in the evidence blocks.
    labels = re.findall(r"(?<!!)\[([A-Za-z0-9_.-]+)\](?!\()", report)
    known = set(source_ids)
    cited = [label for label in labels if label in known]
    unknown = [label for label in labels if label not in known]
    issues = []
    if not report.strip():
        issues.append("The report is empty.")
    if not cited:
        issues.append("Cite at least one supplied source ID using [source-id].")
    if unknown:
        issues.append("Remove citations to unknown source IDs: " + ", ".join(dict.fromkeys(unknown))[:800])
    # URLs in a references section are checked by the role reviewer against the
    # supplied evidence. Label membership is a structural check, not proof of truth.
    return issues


async def write_and_review(context, question, plan, analysis, evidence, context_plan, *, max_attempts, revision=2):
    feedback, drafts = [], []
    source_ids = [selection.item_id for selection in context_plan.selections]
    for attempt in range(1, max_attempts + 1):
        prefix = f"report.{attempt}"
        raw, writer = await invoke_role(context, "baseline.writer", {
            "question": question, "plan": plan.to_dict(), "analysis": analysis.to_dict(),
            "evidence": evidence, "feedback": feedback,
        }, node_id=prefix + ".write")
        try:
            report = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise EngineError("INVALID_ROLE_OUTPUT", "Writer report is not UTF-8") from None
        structural = citation_issues(report, source_ids)
        if revision >= 4:
            structural.extend(english_report_issues(report))
        review, reviewer = await decision(context, "baseline.reviewer", {
            "question": question, "plan": plan.to_dict(), "analysis": analysis.to_dict(),
            "evidence": evidence, "report": report,
        }, ReportReview, node_id=prefix + ".review")
        feedback = list(dict.fromkeys(structural + review.issues))[:8]
        accepted = not feedback and review.verdict == "accept"
        record = {"attempt": attempt, "draft_ref": writer["output_ref"], "review_ref": reviewer["output_ref"],
                  "structural_issues": structural, "accepted": accepted}
        drafts.append(record)
        async with context.node(prefix + ".validation", "report_validation", {"accepted": accepted}):
            await retain(context, record, prefix + ".validation.json")
            await context.checkpoint({"kind": f"baseline-review/{revision}", "attempt": attempt, "drafts": drafts})
        if accepted:
            return writer["output_ref"], drafts
    raise EngineError("REPORT_REVIEW_FAILED", "Report did not pass bounded review and citation checks",
                      {"issues": feedback, "attempts": max_attempts})


def english_report_issues(report):
    """Reject CJK narrative independently of the model review verdict.

    Bibliographic names remain verbatim in References. This script check catches
    Chinese/Japanese/Korean prose; the Reviewer checks English for other scripts.
    """
    body = re.split(r"^#{1,6}\s+References\s*\r?$", report, maxsplit=1, flags=re.M | re.I)[0]
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\U00020000-\U0002fa1f]", body):
        return ["Write all report headings and narrative in English. Translate non-English prose; retain original bibliographic names only in References."]
    return []
