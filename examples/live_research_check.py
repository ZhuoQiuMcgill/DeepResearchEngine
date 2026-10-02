"""Verify real loopback HTTP, SSE replay, idempotency and restart reads.

Default: a model-free method on real Storage. --request makes exactly the
configured method's real network/model calls; credentials stay server-side.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket

import httpx
import uvicorn

from ebd.engine import EngineSettings
from ebd.engine.contracts import digest_bytes
from ebd.interfaces.http import create_app


@asynccontextmanager
async def server(settings):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    address = "http://127.0.0.1:" + str(sock.getsockname()[1])
    app = create_app(settings)
    host = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", log_level="error", access_log=False))
    task = asyncio.create_task(host.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if host.started:
                break
            if task.done():
                await task
                raise RuntimeError("HTTP server did not start")
            await asyncio.sleep(.01)
        else:
            raise RuntimeError("HTTP server startup timed out")
        yield address
    finally:
        host.should_exit = True
        await asyncio.wait_for(task, timeout=35)
        sock.close()
        for field in ("cleanup", "research_cleanup", "engine_cleanup"):
            cleanup = getattr(app.state, field, None)
            assert cleanup is not None and cleanup["complete"], f"{field} was incomplete"


async def report(client, run_id):
    parts, offset = [], 0
    while True:
        response = await client.get(f"/api/v1/research-runs/{run_id}/report",
                                    params={"start": offset, "max_bytes": 4096})
        response.raise_for_status()
        chunk = response.json()
        data = base64.b64decode(chunk["data"], validate=True)
        assert chunk["byte_length"] == len(data)
        parts.append(data)
        assert chunk["next_offset"] == offset + len(data)
        offset = chunk["next_offset"]
        if chunk["eof"]:
            content = b"".join(parts)
            assert len(content) == chunk["total_bytes"] and digest_bytes(content) == chunk["sha256"]
            return content
        assert data, "Report chunk made no progress"


async def replay(client, run_id):
    events, position = [], 0
    while True:
        response = await client.get(f"/api/v1/research-runs/{run_id}/events",
                                    params={"after_seq": position, "limit": 7})
        response.raise_for_status()
        page = response.json()
        events += page["events"]
        position = page["next_after_seq"]
        if not page["has_more"]:
            return events


async def check(args):
    settings = EngineSettings(workspace=Path.cwd(), storage_root=args.store)
    request = json.loads(args.request.read_text(encoding="utf-8")) if args.request else {
        "client_request_id": "echo-http-example-1", "method_id": "example.echo",
        "input": {"message": "Shared workflow interfaces are ready."}}
    async with server(settings) as address:
        async with httpx.AsyncClient(base_url=address, timeout=40, trust_env=False) as client:
            methods = await client.get("/api/v1/methods")
            methods.raise_for_status()
            assert request["method_id"] in {item["method_id"] for item in methods.json()["methods"]}
            start = await client.post("/api/v1/research-runs", json=request)
            assert start.status_code == 202, start.text
            run_id = start.json()["run_id"]
            for _ in range(int(request.get("timeout_seconds", 600) * 5) + 200):
                response = await client.get(f"/api/v1/research-runs/{run_id}")
                response.raise_for_status()
                view = response.json()
                if not view["active"]:
                    break
                await asyncio.sleep(.2)
            else:
                raise RuntimeError("Research run did not settle")
            assert view["status"] == "succeeded" and view["recording_status"] == "complete", view.get("error")
            content = await report(client, run_id)
            events = await replay(client, run_id)
            kinds = [row["event"]["kind"] for row in events]
            assert kinds.count("workflow.finished") == 1
            async with client.stream("GET", f"/api/v1/research-runs/{run_id}/events/stream") as stream:
                stream.raise_for_status()
                sse = (await stream.aread()).decode()
            sequences = [int(line[4:]) for line in sse.splitlines() if line.startswith("id: ")]
            assert sequences == [row["receipt"]["recorded_seq"] for row in events]
            last = sequences[-1]
            resumed = await client.get(f"/api/v1/research-runs/{run_id}/events/stream",
                                        headers={"Last-Event-ID": str(last)})
            resumed.raise_for_status()
            assert not resumed.content
            again = await client.post("/api/v1/research-runs", json=request)
            assert again.status_code == 202 and again.json()["run_id"] == run_id
            if request["method_id"] == "baseline":
                assert "model.intent" in kinds and kinds.index("workflow.context.selected") < kinds.index("model.intent")
                assert sum(source["status"] == "succeeded" for source in view["sources"]["items"]) >= 1
                model_intents = [row["event"]["payload"] for row in events if row["event"]["kind"] == "model.intent"]
                # No model receives a registered discovery/fetch/read function.
                assert all(not intent["request_audit"]["function_tools"] for intent in model_intents)
    async with server(settings) as address:
        async with httpx.AsyncClient(base_url=address, timeout=40, trust_env=False) as client:
            restored = await client.post("/api/v1/research-runs", json=request)
            assert restored.status_code == 202 and restored.json()["run_id"] == run_id
            assert restored.json()["status"] == "succeeded" and not restored.json()["active"]
            assert await report(client, run_id) == content
            restored_events = await replay(client, run_id)
            restored_by_id = {r["receipt"]["event_id"]: r for r in restored_events}
            assert all(restored_by_id[r["receipt"]["event_id"]] == r for r in events)
            # Fresh report access records another binding. It never dispatches
            # the research method/model or changes any committed earlier fact.
            assert sum(r["event"]["kind"] == "workflow.finished" for r in restored_events) == 1
            assert sum(r["event"]["kind"] == "model.intent" for r in restored_events) == kinds.count("model.intent")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_bytes(content)
    (out / "run.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"schema_version": 1, "run_id": run_id, "method_id": view["method_id"],
        "status": view["status"], "recording_status": view["recording_status"], "events": len(events),
        "report_bytes": len(content), "report_sha256": digest_bytes(content),
        "http_sse_replay": True, "idempotency": True, "restart_report_identical": True}
    (out / "acceptance.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default="local/research-http-check")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", default="local/research-http-check-evidence")
    asyncio.run(check(parser.parse_args()))


if __name__ == "__main__":
    main()
