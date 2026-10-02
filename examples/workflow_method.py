"""Compose a model-free example.echo Workflow over a real research service.

Run: uv run --locked python examples/workflow_method.py
Only the host entry point owns Engine; method/components use WorkflowContext.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from ebd.agent_catalog import AgentCatalog
from ebd.bootstrap import create_research_service
from ebd.engine import Engine, EngineSettings
from ebd.engine.contracts import canonical_json, digest_bytes
from ebd.workflows import (
    MethodDefinition, MethodRegistry, PlatformPort, ResearchRunRequest, WorkflowContext,
)


METHOD_ID = "example.echo"
METHOD_REVISION = 2  # This component example has different bytes from built-in @1.
DEFAULT_MESSAGE = "Hello from a model-free Workflow."


def build_registry() -> MethodRegistry:
    """Pin the tutorial's schema and source without changing built-in methods."""
    definition = MethodDefinition(
        METHOD_ID, METHOD_REVISION,
        "Model-free echo composed from selection, publication and checkpoint components.",
        input_schema={"type": "object", "additionalProperties": False,
            "properties": {"message": {"type": "string", "minLength": 1, "maxLength": 4096}},
            "required": ["message"]},
        parameters_schema={"type": "object", "additionalProperties": False, "properties": {}},
        agent_roles=(),
        resource_digests={"workflow_method.py": digest_bytes(Path(__file__).read_bytes())},
    )
    registry = MethodRegistry()
    registry.register(definition, ComposedEchoMethod())
    return registry


async def select_parts(context: WorkflowContext, message: str) -> tuple[list[str], str]:
    """A reusable deterministic component; selection Hooks can narrow/reorder IDs."""
    lines = message.splitlines() or [message]
    if len(lines) > 32:
        raise ValueError("Echo accepts at most 32 logical lines")
    candidates = {f"part-{index:03d}": line for index, line in enumerate(lines, 1)}
    async with context.node("echo.select", "context_selection", {"candidate_count": len(candidates)}):
        selected_ids = await context.select("echo.select", "context.select", list(candidates))
        if not selected_ids:
            raise ValueError("Echo needs at least one selected part")
        rendered = "\n".join(candidates[item_id] for item_id in selected_ids) + "\n"
    return selected_ids, rendered


async def publish_echo(context: WorkflowContext, rendered: str) -> dict[str, Any]:
    """Publication uses the run's bound PlatformPort and returns an opaque ref."""
    port: PlatformPort = context.port
    async with context.node("echo.publish", "publication", {"text_bytes": len(rendered.encode("utf-8"))}):
        return await port.publish(rendered.encode("utf-8"), "text/markdown", "echo.md")


async def checkpoint_result(context: WorkflowContext, report_ref: dict[str, Any],
                            selected_ids: list[str]) -> dict[str, Any]:
    async with context.node("echo.checkpoint", "checkpoint", {"selected_count": len(selected_ids)}):
        result = {"schema_version": 1, "method_id": METHOD_ID, "method_revision": METHOD_REVISION,
                  "selected_ids": selected_ids, "report_ref": report_ref}
        manifest_ref = await context.port.publish(canonical_json(result),
            "application/json", "research-result.json")
        await context.port.update(report_ref=report_ref, result_manifest_ref=manifest_ref)
        await context.checkpoint({"kind": "example.echo.result/1", "selected_ids": selected_ids,
                                  "report_ref": report_ref, "result_manifest_ref": manifest_ref})
    return {**result, "result_manifest_ref": manifest_ref}


class ComposedEchoMethod:
    """WorkflowRunner supplies the root node; components own their logical nodes."""

    async def run(self, context: WorkflowContext, task_input: dict[str, Any],
                  parameters: dict[str, Any]) -> dict[str, Any]:
        selected_ids, rendered = await select_parts(context, task_input["message"])
        report_ref = await publish_echo(context, rendered)
        return await checkpoint_result(context, report_ref, selected_ids)


def inspect_writer_spec() -> dict[str, Any]:
    """Loading/rendering/compiling resources is pure: no model or credentials."""
    spec = AgentCatalog().load("baseline.writer", 1)
    rendered = spec.render_task({"question": "What evidence was supplied?",
                                 "evidence": "Only this explicitly supplied example text."})
    definition = spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=())
    if spec.tool_requests or definition.allowed_tools:
        raise RuntimeError("baseline.writer@1 must request zero tools")
    return {"role_id": spec.role_id, "revision": spec.revision, "tool_requests": [],
            "spec_ref": spec.ref, "input_fields": sorted(spec.input_schema.get("properties", {})),
            "output_type": spec.output_schema.get("type"),
            "rendered_task_sha256": digest_bytes(rendered.encode("utf-8")),
            "compiled_tool_count": len(definition.allowed_tools)}


async def wait_terminal(service, run_id: str):
    async with asyncio.timeout(40):
        while True:
            view = await service.get_run(run_id)
            if not view.active:
                return view
            await asyncio.sleep(0.02)


async def committed_events(service, run_id: str) -> list[dict[str, Any]]:
    rows, after_seq = [], 0
    for _ in range(32):
        page = await service.events(run_id, after_seq=after_seq, limit=100)
        rows.extend(page["events"])
        next_seq = page["next_after_seq"]
        if not page["has_more"]:
            return rows
        if next_seq <= after_seq:
            raise RuntimeError("Committed event cursor made no progress")
        after_seq = next_seq
    raise RuntimeError("Example event history exceeds its inspection bound")


async def run_echo(service, message: str) -> dict[str, Any]:
    """Use the application API; never inspect private tasks or Storage clients."""
    accepted = await service.start_run(ResearchRunRequest(
        client_request_id="example-" + uuid4().hex,
        method_id=METHOD_ID, method_revision=METHOD_REVISION,
        input={"message": message}, timeout_seconds=30,
    ))
    done = await wait_terminal(service, accepted.run_id)
    if (done.active or done.status != "succeeded" or done.recording_status != "complete"
            or not done.terminal_event_receipt or not done.report_ref
            or not done.result_manifest_ref or not done.checkpoint_ref):
        raise RuntimeError("Workflow did not finish with complete recording and publications: "
                           + json.dumps(done.to_dict(), ensure_ascii=False))
    if done.pins.get("roles") != []:
        raise RuntimeError("The model-free example must pin no Agent roles")
    rows = await committed_events(service, done.run_id)
    kinds = [row["event"]["kind"] for row in rows]
    if any(kind.startswith(("model.", "tool.", "invocation.")) for kind in kinds):
        raise RuntimeError("The echo example unexpectedly used a model, tool or child")
    if "workflow.finished" not in kinds or any(node.status != "succeeded" for node in done.nodes):
        raise RuntimeError("Committed workflow/node completion is missing")
    report = await service.read_report(done.run_id, max_bytes=65536)
    data = base64.b64decode(report["data"], validate=True)
    if not report["eof"] or digest_bytes(data) != report["sha256"]:
        raise RuntimeError("Saved report was truncated or its digest did not match")
    usage = await service.get_usage(done.run_id)
    if usage["available"]:
        raise RuntimeError("A model-free run unexpectedly reported model usage")
    return {"run_id": done.run_id, "method_id": done.method_id,
            "method_revision": done.method_revision, "status": done.status,
            "recording_status": done.recording_status, "model_calls": 0,
            "report": data.decode("utf-8"), "report_ref": done.report_ref.to_dict(),
            "result_manifest_ref": done.result_manifest_ref.to_dict(),
            "checkpoint_ref": done.checkpoint_ref,
            "node_ids": [node.node_id for node in done.nodes],
            "terminal_event_receipt": done.terminal_event_receipt, "events": rows}


async def close_host(service, engine) -> dict[str, Any]:
    """Close both owners, even when one fails; require every cleanup field."""
    reports, failures = {}, []
    for label, owner in (("research_service", service), ("engine", engine)):
        try:
            report = await owner.close()
            reports[label] = report.to_dict()
            if not report.complete or report.errors or report.unconfirmed_resources:
                failures.append(label)
        except Exception as error:
            reports[label] = {"complete": False, "error_type": type(error).__name__}
            failures.append(label)
    if failures:
        raise RuntimeError("Incomplete cleanup: " + json.dumps(reports, ensure_ascii=False))
    return reports


async def run_example(store: Path, message: str) -> dict[str, Any]:
    # This outermost bootstrap owns the Engine. Components above receive only a port.
    engine = (await Engine.open(EngineSettings(storage_root=store))).unwrap()
    service = None
    try:
        service = create_research_service(engine, registry=build_registry())
        result = await run_echo(service, message)
        result.pop("events")
        result["writer_spec_preparation_only"] = inspect_writer_spec()
    finally:
        if service is None:
            cleanup = await engine.close()
            if not cleanup.complete or cleanup.errors or cleanup.unconfirmed_resources:
                raise RuntimeError("Engine cleanup is incomplete")
        else:
            cleanup = await close_host(service, engine)
    return {**result, "cleanup": cleanup}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, help="Retain a real Store; default uses an isolated temporary Store")
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    args = parser.parse_args()
    if args.store is None:
        with tempfile.TemporaryDirectory(prefix="ebd-workflow-method-") as directory:
            result = asyncio.run(run_example(Path(directory), args.message))
    else:
        result = asyncio.run(run_example(args.store, args.message))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
