"""Bounded actual DeepSeek evidence delegation and loopback HTTP acceptance.

Run explicitly through uv. This makes real billed API calls and one genuine
scholarly-tool request. It retains supplied-source provenance honestly, owns
one Engine at a time, and verifies stored facts after closing and reopening.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import asynccontextmanager
from pathlib import Path
import socket
import time
import uuid

import httpx
import uvicorn

from ebd.baseline import history, read_artifact
from ebd.connections import (
    ArtifactReadRequest, Engine, EngineSettings, EvidenceBinding, HistoryReadRequest,
    InvocationOptions, InvocationRule, RunAccessOptions, RunAccessRequest,
    RunOptions, SnapshotReadRequest,
)
from ebd.contracts import (
    AgentDefinition, RunRef, SnapshotProposal, ToolRef, canonical_json, digest_bytes,
)
from ebd.service import create_app


COUNTERS = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens",
            "uncached_input_tokens", "reasoning_output_tokens")
TERMINAL = {"succeeded", "failed", "validation_failed", "limit_exhausted", "timed_out", "cancelled", "interrupted"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


@asynccontextmanager
async def loopback_server(engine):
    """Exercise real TCP HTTP and FastAPI lifespan, without a subprocess."""
    app = create_app(engine=engine, close_timeout_seconds=30)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    sock.setblocking(False)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
        log_level="error", access_log=False, lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]), name="live-console-http")
    try:
        expires = time.monotonic() + 10
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Loopback HTTP server exited before startup")
            require(time.monotonic() < expires, "Loopback HTTP server startup exceeded its bound")
            await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=15,
                                     transport=httpx.AsyncHTTPTransport(retries=0)) as client:
            yield client
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 35)
            cleanup = getattr(app.state, "cleanup", {})
            require(cleanup.get("complete") is True, "HTTP lifespan did not settle its execution tasks")
        finally:
            sock.close()


async def request_json(client, method, path, *, expected=200, **kwargs):
    response = await client.request(method, path, **kwargs)
    if response.status_code != expected:
        # HTTP service errors are sanitized. Report only the code, never a
        # raw body, provider diagnostic or request input.
        try:
            code = response.json().get("error", {}).get("code", "HTTP_ERROR")
        except ValueError:
            code = "HTTP_ERROR"
        raise RuntimeError(f"Service request failed with HTTP {response.status_code}: {code}")
    return response.json()


async def poll_terminal(client, run_id, timeout=190):
    expires = time.monotonic() + timeout
    while time.monotonic() < expires:
        status = await request_json(client, "GET", f"/api/v1/runs/{run_id}/status")
        if status["status"] in TERMINAL and not status["active"]:
            return status
        await asyncio.sleep(0.1)
    raise RuntimeError("HTTP run did not settle within the acceptance deadline")


async def events(client, run_id, *, include_descendants=False):
    rows, position = [], 0
    for _ in range(32):
        page = await request_json(client, "GET", f"/api/v1/runs/{run_id}/events",
            params={"after_seq": position, "limit": 25, "include_descendants": include_descendants})
        rows.extend(page["events"])
        require(len(canonical_json(rows)) <= 8388608, "Acceptance history exceeds its byte bound")
        if not page["has_more"]:
            return rows
        require(page["next_after_seq"] > position, "Incremental history did not advance")
        position = page["next_after_seq"]
    raise RuntimeError("Acceptance history exceeds its page bound")


async def artifact(client, run_id, ref):
    parts, position = [], 0
    for _ in range(8):
        chunk = await request_json(client, "GET", f"/api/v1/runs/{run_id}/artifacts/{ref['artifact_id']}",
                                   params={"start": position, "max_bytes": 65536})
        require(chunk["encoding"] == "base64" and chunk["start"] == position, "Artifact range response mismatch")
        data = base64.b64decode(chunk["data"], validate=True)
        require(chunk["next_offset"] == position + len(data), "Artifact byte offset mismatch")
        parts.append(data)
        position = chunk["next_offset"]
        if chunk["eof"]:
            return b"".join(parts)
        require(data, "Artifact reader made no progress")
    raise RuntimeError("Report artifact exceeds its acceptance byte bound")


def usage_observations(rows, aggregate, *, require_complete=False):
    outcomes = [row for row in rows if row["event"]["kind"] == "model.outcome"]
    observations = []
    for row in outcomes:
        event, payload = row["event"], row["event"]["payload"]
        usage = payload.get("usage")
        require(isinstance(usage, dict) and all(key in usage for key in COUNTERS), "Missing explicit per-attempt token usage")
        require(all(value is None or type(value) is int and value >= 0 for key in COUNTERS for value in (usage[key],)),
                "Invalid token count in stored outcome")
        if require_complete:
            require(usage["completeness"] == "complete" and usage["source"] == "provider", "Successful response usage is incomplete")
            require(payload["request_audit"]["reported_model_id"] == "deepseek-flash", "Actual provider model differs from the selected model")
        observations.append({"event_id": event["event_id"], "action_id": event["context"]["action_id"],
            "attempt_id": event["context"]["attempt_id"], "usage": usage,
            "provider_usage": payload.get("provider_usage"), "request_audit": payload.get("request_audit")})
    refs = [{"store_id": row["receipt"]["store_id"], "event_id": row["event"]["event_id"],
             "action_id": row["event"]["context"]["action_id"], "attempt_id": row["event"]["context"]["attempt_id"]}
            for row in outcomes]
    require(aggregate["per_attempt_usage_refs"] == refs, "Terminal usage references differ from committed outcomes")
    for key in COUNTERS:
        values = [row["event"]["payload"]["usage"][key] for row in outcomes if row["event"]["payload"]["usage"][key] is not None]
        require(aggregate["known_subtotals"][key] == (sum(values) if values else None), "Terminal subtotal differs from observed counts")
    return observations


async def saved_child(engine, run_ref, output_ref):
    access = (await engine.open_run_access(run_ref, RunAccessRequest(
        read_objects=(ArtifactReadRequest(output_ref, max_bytes=65536),), history=HistoryReadRequest()),
        RunAccessOptions())).unwrap()
    async with access:
        return await read_artifact(access, output_ref, 65536), await history(access)


async def supplied_evidence_delegation(engine, target):
    marker = "evidence-" + uuid.uuid4().hex
    source = ("Live acceptance supplied source.\nEvidence marker: " + marker +
              "\nThis source proves selected evidence access only; it is not external research.").encode()
    parent = None
    child = engine.register_agent(AgentDefinition("live-evidence-reader-" + marker,
        "You must call the registered document.read exactly once using the supplied snapshot_ref, range and max_text_bytes. "
        "After the real saved read, return its Evidence marker in one short sentence. Do not invent text or use internal search.",
        allowed_tools=[ToolRef("document.read")],
        limits={"max_run_seconds": 180, "max_model_seconds": 75, "max_model_calls": 3,
                "max_tool_calls": 2, "max_output_tokens_per_call": 256})).unwrap()
    parent_agent = engine.register_agent(AgentDefinition("live-evidence-strategy-" + marker,
        "Trusted Python strategy coordinates a child reader and consumes its saved result.", allowed_tools=[ToolRef("document.read")]),
        (InvocationRule(child.ref, allowed_tools=("document.read",), allow_evidence=True,
                        limits={"model_calls": 3, "tool_calls": 2}, timeout_seconds=180),)).unwrap()
    parent = (await engine.open_agent_session(parent_agent, RunOptions(timeout_seconds=240,
        limits={"model_calls": 3, "tool_calls": 2, "descendants": 1}))).unwrap()
    try:
        index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(source),
                 "lines": [], "pages": None}
        position = 0
        for number, line in enumerate(source.split(b"\n"), 1):
            end = position + len(line)
            index["lines"].append({"line": number, "start_byte": position, "end_byte": end})
            position = end + 1
        committed = (await parent.binding.snapshots.commit(parent.context, "supplied-source-" + marker, parent.context.scope,
            SnapshotProposal(source, source, canonical_json(index), {"source_kind": "supplied",
                "source_name": "live evidence acceptance", "network_fetch": False,
                "purpose": "Verify bounded parent-to-child read authority, not an EBD source claim"}))).unwrap()
        selector = SnapshotReadRequest(committed.snapshot_ref, {"kind": "lines", "start": 1, "end_exclusive": 4}, 4096)
        outcome = await parent.binding.invoker.invoke(parent.context, child.ref, canonical_json({
            "snapshot_ref": selector.ref, "range": selector.range, "max_text_bytes": selector.max_text_bytes,
        }).decode(), InvocationOptions(timeout_seconds=180, evidence=EvidenceBinding(read_objects=(selector,))))
        (target / "delegation-outcome.json").write_bytes(canonical_json(outcome))
        require(outcome.status == "succeeded" and outcome.recording_status == "complete", "Actual child evidence invocation failed")
        require(outcome.child_result.counters["tool_calls"] >= 1, "Child did not use the registered saved-read tool")
        report, rows = await saved_child(engine, outcome.child_run, outcome.child_result.output_ref)
        require(marker.encode() in report, "Child report does not establish the actual supplied evidence read")
        successful = [row for row in rows if row["event"]["kind"] == "tool.outcome"
                      and row["event"]["payload"].get("status") == "succeeded"]
        require(any(row["event"]["payload"]["tool"]["name"] == "document.read"
                    and row["event"]["payload"]["result_descriptor"].get("snapshot_ref") == selector.ref.to_dict()
                    and row["event"]["payload"]["result_descriptor"].get("returned_range") == selector.range
                    and row["event"]["payload"]["result_descriptor"].get("text_sha256") == digest_bytes(source) for row in successful),
                "Child read lacks the exact retained source/range/digest proof")
        observations = usage_observations(rows, outcome.child_result.usage, require_complete=True)
        # The parent is a trusted host strategy, not another model runtime. It
        # stores its consumption decision after the child's durable outcome.
        consumption = {"source_kind": "supplied", "parent_kind": "host_strategy", "child_run": outcome.child_run,
            "child_terminal_receipt": outcome.child_result.terminal_event_receipt, "source_selector": selector,
            "report_sha256": digest_bytes(report), "evidence_marker_observed": True}
        consumed = (await parent.binding.artifacts.put(parent.context, "parent-consumption-" + marker,
            parent.context.scope, canonical_json(consumption), {"media_type": "application/json",
            "metadata": {"purpose": "strategy_child_result_consumption"}})).unwrap()
        require(outcome.outcome_receipt.recorded_seq < consumed.event_receipt.recorded_seq, "Parent consumption was not ordered after child outcome")
        (target / "child-report.md").write_bytes(report)
        (target / "child-trace.json").write_bytes(canonical_json(rows))
        return {"parent_run_ref": RunRef(engine.storage.store_id, parent.context.run_id).to_dict(),
            "child_run_ref": outcome.child_run.to_dict(), "child_result": outcome.child_result.to_dict(),
            "source_receipt": committed.to_dict(), "selector": selector, "source_bytes": source,
            "report_bytes": report, "usage_observations": observations, "consumption_receipt": consumed.to_dict()}
    finally:
        if parent is not None:
            await parent.close()


async def console_conversation(client, target):
    health = await request_json(client, "GET", "/api/v1/health")
    require(health["ready"] and health["single_owner"], "HTTP console is not ready")
    agent_id = "live-console-" + uuid.uuid4().hex
    registration = {"schema_version": 1, "agent_id": agent_id,
        "instructions": "Call registered scholar.crossref.search exactly once with query 'Environment Based Design' and max_results 1. "
            "Then return one short sentence identifying the real returned title or describing an actual tool error. Use no internal/provider search.",
        "profile_ref": "deepseek", "model_ref": "deepseek-flash", "allowed_tools": [{"name": "scholar.crossref.search", "revision": 1}],
        "limits": {"max_run_seconds": 180, "max_model_seconds": 75, "max_model_calls": 3,
                   "max_tool_calls": 2, "max_output_tokens_per_call": 256}}
    await request_json(client, "POST", "/api/v1/agents", expected=201, json=registration)
    handle = await request_json(client, "POST", "/api/v1/runs", expected=202, json={
        "schema_version": 1, "agent_id": agent_id, "input": "Check the real console tool integration.", "timeout_seconds": 180})
    run_id = handle["run_id"]
    status = await poll_terminal(client, run_id)
    result = await request_json(client, "GET", f"/api/v1/runs/{run_id}/result")
    rows = await events(client, run_id)
    (target / "console-result.json").write_bytes(canonical_json(result))
    (target / "console-trace.json").write_bytes(canonical_json(rows))
    require(status["status"] == "succeeded" and result["recording_status"] == "complete", "Real HTTP model conversation failed")
    require(any(row["event"]["kind"] == "tool.outcome" and row["event"]["payload"].get("status") == "succeeded"
                and row["event"]["payload"]["tool"]["name"] == "scholar.crossref.search" for row in rows), "Real scholarly-tool request did not succeed")
    usage = await request_json(client, "GET", f"/api/v1/runs/{run_id}/usage")
    require(usage["usage"] == result["usage"], "HTTP usage differs from the saved terminal aggregate")
    observations = usage_observations(rows, result["usage"], require_complete=True)
    report = await artifact(client, run_id, result["output_ref"])
    (target / "console-report.md").write_bytes(report)
    return {"run_id": run_id, "result": result, "report_bytes": report, "usage_observations": observations}


async def console_cancellation(client, target):
    agent_id = "live-cancel-" + uuid.uuid4().hex
    await request_json(client, "POST", "/api/v1/agents", expected=201, json={"schema_version": 1,
        "agent_id": agent_id, "instructions": "Write a detailed explanation of design research. Use no external or internal tools/search.",
        "profile_ref": "deepseek", "model_ref": "deepseek-flash", "allowed_tools": [],
        "limits": {"max_run_seconds": 90, "max_model_seconds": 60, "max_model_calls": 1, "max_output_tokens_per_call": 2048}})
    handle = await request_json(client, "POST", "/api/v1/runs", expected=202, json={
        "schema_version": 1, "agent_id": agent_id, "input": "Explain with several detailed examples.", "timeout_seconds": 90})
    run_id = handle["run_id"]
    await request_json(client, "POST", f"/api/v1/runs/{run_id}/cancel")
    status = await poll_terminal(client, run_id, timeout=20)
    result = await request_json(client, "GET", f"/api/v1/runs/{run_id}/result")
    rows = await events(client, run_id)
    (target / "cancel-result.json").write_bytes(canonical_json(result))
    (target / "cancel-trace.json").write_bytes(canonical_json(rows))
    require(status["status"] == "cancelled" and result["recording_status"] == "complete", "HTTP cancellation did not retain a complete cancelled terminal")
    require(result["output_ref"] is None, "Cancelled console run published an output")
    observations = usage_observations(rows, result["usage"])
    return {"run_id": run_id, "result": result, "usage_observations": observations}


async def main(workspace, storage_root=None):
    settings = EngineSettings(workspace=workspace, storage_root=storage_root or workspace / "local" / "service-acceptance")
    target = Path(settings.storage_root) / ("acceptance-" + uuid.uuid4().hex)
    target.mkdir(parents=True, exist_ok=True)
    engine = (await Engine.open(settings)).unwrap()
    try:
        delegation = await supplied_evidence_delegation(engine, target)
        async with loopback_server(engine) as client:
            console = await console_conversation(client, target)
            cancelled = await console_cancellation(client, target)
            family = await events(client, delegation["parent_run_ref"]["run_id"], include_descendants=True)
            require(any(row["event"]["kind"] == "invocation.intent" and row["event"]["payload"].get("evidence") for row in family), "HTTP lineage has no evidence delegation intent")
            require(any(row["event"]["kind"] == "agent.finished" and row["event"]["context"]["run_id"] == delegation["child_run_ref"]["run_id"] for row in family), "HTTP lineage omits the child's durable terminal")
            (target / "lineage-trace.json").write_bytes(canonical_json(family))
    finally:
        require((await engine.close()).complete, "Engine cleanup failed before reopen")

    reopened = (await Engine.open(settings)).unwrap()
    try:
        async with loopback_server(reopened) as client:
            restored = []
            child = {"run_id": delegation["child_run_ref"]["run_id"], "result": delegation["child_result"],
                     "report_bytes": delegation["report_bytes"], "usage_observations": delegation["usage_observations"]}
            for label, expected in (("child", child), ("console", console), ("cancel", cancelled)):
                run_id = expected["run_id"]
                result = await request_json(client, "GET", f"/api/v1/runs/{run_id}/result")
                require(result["automatic_resume"] is False and result["active"] is False, "Reopened service resurrected execution")
                for key in ("status", "recording_status", "output_ref", "usage", "terminal_event_receipt"):
                    require(result[key] == expected["result"][key], "Stored result changed after restart: " + key)
                rows = await events(client, run_id)
                observed = usage_observations(rows, result["usage"], require_complete=label != "cancel")
                require(observed == expected["usage_observations"], "Native/normalized usage observations changed after reopen")
                if "report_bytes" in expected:
                    require(await artifact(client, run_id, result["output_ref"]) == expected["report_bytes"], "Stored report bytes changed after restart")
                restored.append({"kind": label, "run_id": run_id, "status": result["status"],
                    "usage": result["usage"], "terminal_event_receipt": result["terminal_event_receipt"]})
        selector = delegation["selector"]
        parent_ref = RunRef(**delegation["parent_run_ref"])
        access = (await reopened.open_run_access(parent_ref,
            RunAccessRequest(read_objects=(selector,)), RunAccessOptions())).unwrap()
        async with access:
            source = (await access.storage.snapshots.read(access.context, selector.ref, selector.range, selector.max_text_bytes)).unwrap()
            require(source.text.encode() == delegation["source_bytes"], "Supplied immutable evidence changed after reopen")
        proof = {"schema_version": 1, "status": "passed", "actual_provider": "deepseek", "actual_model": "deepseek-flash",
            "http_transport": "real_uvicorn_loopback_tcp", "parent_kind": "trusted_python_strategy", "source_kind": "supplied",
            "parent_run_ref": delegation["parent_run_ref"], "child_run_ref": delegation["child_run_ref"],
            "source_receipt": delegation["source_receipt"], "parent_consumption_receipt": delegation["consumption_receipt"],
            "child_report_sha256": digest_bytes(delegation["report_bytes"]), "console_report_sha256": digest_bytes(console["report_bytes"]),
            "close_reopen_identical": True, "runs": restored}
        (target / "acceptance.json").write_bytes(canonical_json(proof))
        print(canonical_json({"status": "passed", "evidence": str(target), "actual_provider": "deepseek",
                              "run_ids": [row["run_id"] for row in restored]}).decode(), flush=True)
    finally:
        require((await reopened.close()).complete, "Reopened Engine cleanup failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--storage-root", type=Path)
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(main(args.workspace, args.storage_root), 600))
