"""Validate saved role decisions and keep their provenance in the Workflow."""
from __future__ import annotations

from deepresearch.engine.contracts import EngineError, canonical_json, strict_json_loads
from deepresearch.workflows.components.agents import invoke_role
from pydantic import ValidationError


async def decision(context, role_id, task_input, contract, *, node_id, input_ref=None,
                   validator=None, max_attempts=None):
    defaults = getattr(context, "agent_input_defaults", {})
    max_attempts = max_attempts or (2 if "repair" in defaults else 1)
    current = {**defaults, **task_input}
    for attempt in range(1, max_attempts + 1):
        node = node_id if attempt == 1 else f"{node_id}.repair-{attempt}"
        # The retained input must match the full data actually rendered by Runtime.
        current_ref = await retain(context, current, node + ".input.json") if defaults or attempt > 1 else input_ref
        raw, outcome = None, None
        try:
            raw, outcome = await invoke_role(context, role_id, current, node_id=node, input_ref=current_ref)
            async with context.node(node + ".validate", "decision_validation", {"role_id": role_id}):
                try:
                    value = contract.model_validate(strict_json_loads(raw, 65536))
                except (ValueError, TypeError) as error:
                    errors = ([{"path": list(item["loc"]), "type": item["type"], "message": item["msg"][:1024]}
                        for item in error.errors(include_input=False, include_context=False)[:12]]
                        if isinstance(error, ValidationError) else [{"path": [], "message": str(error)[:1024]}])
                    raise EngineError("INVALID_ROLE_OUTPUT", "Saved role output violates the research decision contract",
                        {"role_id": role_id, "validation_errors": errors, "output_ref": outcome["output_ref"]}) from None
                if validator is not None:
                    validator(value)
        except EngineError as error:
            if error.code not in {"INVALID_ROLE_OUTPUT", "INVALID_SELECTION", "INVALID_EVIDENCE_REFERENCE", "INVALID_SOURCE_RANGE"}:
                raise
            if outcome is not None:
                error.details.setdefault("output_ref", outcome["output_ref"])
            if attempt == max_attempts:
                raise
            output_ref = error.details.get("output_ref")
            if output_ref is None:
                # A diagnostic reference is required; do not mask the original
                # failure or fabricate a successful invocation outcome.
                raise
            if raw is None:
                raw = await context.port.read_artifact(output_ref, max_bytes=65536)
            repair = {"attempt": attempt + 1, "previous_output": raw.decode("utf-8", errors="replace"),
                      "errors": [error.to_dict()]}
            current = {**current, "repair": repair}
            await context.port.emit("workflow.role.repair", {"role_id": role_id,
                "attempt": attempt + 1, "error_code": error.code, "output_ref": output_ref})
            continue
        return value, {**outcome, "input_ref": current_ref}


def validate_plan(plan, max_queries):
    if len(plan.queries) > max_queries:
        raise EngineError("INVALID_ROLE_OUTPUT", "Planner exceeded the selected query budget",
                          {"max_queries": max_queries, "actual_queries": len(plan.queries)})


async def retain(context, value, filename):
    return await context.port.publish(canonical_json(value), "application/json", filename)


def validate_findings(analysis, selected_ids, plan):
    known = set(selected_ids)
    binding_errors, question_errors = [], []
    for index, finding in enumerate(analysis.findings):
        path = ["findings", index]
        for field in ("claim", "question"):
            if not getattr(finding, field).strip():
                binding_errors.append({"path": path + [field], "type": "blank_text"})
        unknown = sorted(set(finding.source_ids) - known)
        if unknown:
            binding_errors.append({"path": path + ["source_ids"], "type": "unknown_source_ids",
                                   "unknown_source_ids": unknown})
        duplicates = sorted({item for item in finding.source_ids if finding.source_ids.count(item) > 1})
        if duplicates:
            binding_errors.append({"path": path + ["source_ids"], "type": "duplicate_source_ids",
                                   "duplicate_source_ids": duplicates})
        if finding.question not in plan.questions:
            question_errors.append({"path": path + ["question"], "type": "unplanned_question",
                                    "question": finding.question})
    if binding_errors or question_errors:
        # Repair must know the exact invalid field and permitted identities.
        # Never infer a replacement from a similar-looking source ID.
        details = {"validation_errors": (binding_errors + question_errors)[:12],
                   "allowed_source_ids": list(dict.fromkeys(selected_ids)), "allowed_questions": list(plan.questions)}
        if binding_errors:
            raise EngineError("INVALID_EVIDENCE_REFERENCE", "Analysis may cite only selected retained sources", details)
        raise EngineError("INVALID_ROLE_OUTPUT", "Analysis must answer a planned research question", details)


def validate_analysis(analysis, selected_ids, plan, sources):
    """Keep supported analysis while recording impossible optional read requests."""
    from deepresearch.workflows.components.source_access import validate_source_range
    validate_findings(analysis, selected_ids, plan)
    by_id = {source.item_id: source for source in sources.items if source.item_id in selected_ids}
    valid = []
    for request in analysis.follow_up_reads:
        try:
            if request.source_id not in by_id:
                raise EngineError("INVALID_EVIDENCE_REFERENCE", "Read source is not in delivered source IDs")
            validate_source_range(by_id[request.source_id], request.range)
        except EngineError as error:
            analysis._read_adjustments.append({"kind": "invalid_read_request", "request": request.model_dump(),
                                               "error": error.to_dict()})
        else:
            valid.append(request)
    if analysis._read_adjustments:
        analysis.follow_up_reads = valid
        analysis.sufficient = False
        analysis.gaps = analysis.gaps[:7] + ["Some requested source ranges are unavailable in the retained snapshots; those requests were not executed."]
