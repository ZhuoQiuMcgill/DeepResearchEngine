"""Validate saved role decisions and keep their provenance in the Workflow."""
from __future__ import annotations

from deepresearch.engine.contracts import EngineError, canonical_json, strict_json_loads
from deepresearch.workflows.components.agents import invoke_role


async def decision(context, role_id, task_input, contract, *, node_id, input_ref=None):
    raw, outcome = await invoke_role(context, role_id, task_input, node_id=node_id, input_ref=input_ref)
    async with context.node(node_id + ".validate", "decision_validation", {"role_id": role_id}):
        try:
            value = contract.model_validate(strict_json_loads(raw, 65536))
        except (ValueError, TypeError):
            raise EngineError("INVALID_ROLE_OUTPUT", "Saved role output violates the research decision contract",
                              {"role_id": role_id}) from None
    return value, outcome


async def retain(context, value, filename):
    return await context.port.publish(canonical_json(value), "application/json", filename)


def validate_findings(analysis, selected_ids, plan):
    known = set(selected_ids)
    for finding in analysis.findings:
        if (not finding.claim.strip() or not finding.question.strip()
                or not set(finding.source_ids) <= known
                or len(set(finding.source_ids)) != len(finding.source_ids)):
            raise EngineError("INVALID_EVIDENCE_REFERENCE", "Analysis may cite only selected retained sources")
        if finding.question not in plan.questions:
            raise EngineError("INVALID_ROLE_OUTPUT", "Analysis must answer a planned research question")
