"""Research HTTP and SSE over real Storage; no model credentials are needed."""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.application import ResearchRunService
from deepresearch.bootstrap.application import create_research_service
from deepresearch.engine.connections import Engine, EngineSettings
from deepresearch.engine.contracts import EngineError
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.interfaces.http.research import install_research_routes, replay_position, stream_events, SourceReadView, MethodPage
from deepresearch.interfaces.http import create_app
from deepresearch.workflows import MethodDefinition, MethodRegistry, ResearchRunRequest, ResearchRunView


def settings(tmp_path):
    return EngineSettings(workspace=tmp_path, storage_root=tmp_path / "store")


async def terminal(service, run_id):
    for _ in range(300):
        view = await service.get_run(run_id)
        if not view.active:
            return view
        await asyncio.sleep(0.01)
    pytest.fail("Research execution did not settle")


@pytest.mark.asyncio
async def test_shared_http_contracts_report_replay_and_safe_failures(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    service = create_research_service(engine)
    app = create_app(engine=engine)
    app.state.research_service = service
    install_research_routes(app)
    def no_model(*args):
        pytest.fail("Echo method resolved credentials")
    monkeypatch.setattr(engine.profiles, "resolve", no_model)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            catalog = (await client.get("/api/v1/methods")).json()
            MethodPage.model_validate(catalog)
            methods = catalog["methods"]
            assert {method["method_id"] for method in methods} >= {"baseline", "example.echo"}
            data = {"client_request_id": "http-echo", "method_id": "example.echo", "input": {"message": "Saved report"}}
            started = await client.post("/api/v1/research-runs", json=data)
            assert started.status_code == 202, started.text
            view = ResearchRunView.model_validate(started.json())
            run_id = view.run_id
            done = await terminal(service, run_id)
            assert done.status == "succeeded" and done.terminal_event_receipt
            assert done.pins["method"]["method_id"] == "example.echo" and done.pins["roles"] == []
            duplicate = await client.post("/api/v1/research-runs", json=data)
            assert duplicate.status_code == 202 and duplicate.json()["run_id"] == run_id
            conflict = await client.post("/api/v1/research-runs", json={**data, "input": {"message": "Different"}})
            assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            malformed = await client.post("/api/v1/research-runs", json={**data, "api_key": "must-not-echo"})
            assert malformed.status_code == 422 and "must-not-echo" not in malformed.text
            unknown = await client.post("/api/v1/research-runs", json={**data, "client_request_id": "missing", "method_id": "absent"})
            assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "METHOD_NOT_FOUND"
            assert (await client.get("/api/v1/research-runs/missing")).status_code == 404
            assert (await client.get("/api/v1/research-runs?limit=101")).status_code == 422
            invalid_range = await client.post(f"/api/v1/research-runs/{run_id}/sources/unknown/read",
                json={"range": {"kind": "lines", "start": 1, "end_exclusive": 202}})
            assert invalid_range.status_code == 422
            assert (await client.get("/api/v1/research-runs")).json()["runs"][0]["run_id"] == run_id
            chunk = (await client.get(f"/api/v1/research-runs/{run_id}/report?max_bytes=5")).json()
            assert base64.b64decode(chunk["data"]) == b"Saved" and chunk["byte_length"] == 5 and chunk["next_offset"] == 5
            objects = await client.get(f"/api/v1/research-runs/{run_id}/objects?limit=100")
            assert objects.status_code == 200 and objects.json()["objects"]
            ref = done.report_ref.artifact_id
            saved = await client.get(f"/api/v1/research-runs/{run_id}/artifacts/{ref}?max_bytes=5")
            assert saved.status_code == 200 and base64.b64decode(saved.json()["data"]) == b"Saved"
            other = await client.post("/api/v1/research-runs", json={**data, "client_request_id": "another-run"})
            other_id = other.json()["run_id"]
            await terminal(service, other_id)
            denied = await client.get(f"/api/v1/research-runs/{other_id}/artifacts/{ref}")
            assert denied.status_code == 404
            events = (await service.events(run_id))["events"]
            streamed = await client.get(f"/api/v1/research-runs/{run_id}/events/stream?limit=2")
            assert streamed.status_code == 200 and streamed.headers["content-type"].startswith("text/event-stream")
            ids = [int(line[4:]) for line in streamed.text.splitlines() if line.startswith("id: ")]
            assert ids == sorted(set(ids))
            assert all(sequence in ids for sequence in [row["receipt"]["recorded_seq"] for row in events])
            for frame in streamed.text.strip().split("\n\n"):
                lines = frame.splitlines()
                row = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
                assert int(lines[0][4:]) == row["receipt"]["recorded_seq"]
            replay = await client.get(f"/api/v1/research-runs/{run_id}/events/stream",
                headers={"Last-Event-ID": str(ids[-2])})
            replay_ids = [int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")]
            assert replay_ids == [ids[-1]]
            bad_header = await client.get(f"/api/v1/research-runs/{run_id}/events/stream", headers={"Last-Event-ID": "private-text"})
            assert bad_header.status_code == 422 and "private-text" not in bad_header.text
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/api/v1/research-runs"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("ResearchRunRequest")
            assert "ResearchRunView" in schema["components"]["schemas"]
    finally:
        await service.close()
        await app.state.run_service.close()
        await engine.close()


class WaitingMethod:
    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def run(self, context, task_input, parameters):
        async with context.node("wait", "controlled_wait"):
            self.entered.set()
            await self.release.wait()
            ref = await context.port.publish(b"Finished", "text/markdown", "report.md")
            await context.port.update(report_ref=ref)
        return {"report_ref": ref}


def waiting_service(engine, method):
    registry = MethodRegistry()
    registry.register(MethodDefinition("waiting", 1, "Controlled lifetime", {"type": "object"}, {"type": "object"}), method)
    return ResearchRunService(engine, registry, AgentCatalog(), TokenMeter())


class SubscriptionRequest:
    disconnected = False

    async def is_disconnected(self):
        return self.disconnected


@pytest.mark.asyncio
async def test_sse_disconnect_only_closes_subscription_and_stream_failures_are_safe(tmp_path, monkeypatch):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = WaitingMethod()
    service = waiting_service(engine, method)
    subscription = SubscriptionRequest()
    try:
        run_id = (await service.start_run(ResearchRunRequest(client_request_id="stream", method_id="waiting", input={}))).run_id
        await method.entered.wait()
        stream = stream_events(service, subscription, run_id, 0, 100)
        first = await anext(stream)
        assert first.startswith(b"id: ")
        subscription.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        assert (await service.get_run(run_id)).active
        assert not service._runs[run_id].session.context.cancellation.is_set()
        subscription.disconnected = False
        native = service.events
        page = await native(run_id)
        async def broken(*args):
            raise RuntimeError("private provider/credential exception")
        monkeypatch.setattr(service, "events", broken)
        failed = b"".join([part async for part in stream_events(service, subscription, run_id, 0, 100, page)])
        assert b"event: error" in failed and b"private provider" not in failed
        assert b"RESEARCH_STREAM_DEFECT" in failed
        assert (await service.get_run(run_id)).active
        monkeypatch.setattr(service, "events", native)
        method.release.set()
        assert (await terminal(service, run_id)).status == "succeeded"
    finally:
        method.release.set()
        await service.close()
        await engine.close()


@pytest.mark.asyncio
async def test_http_cancellation_drains_committed_terminal_in_sse(tmp_path):
    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = WaitingMethod()
    service = waiting_service(engine, method)
    app = create_app(engine=engine)
    app.state.research_service = service
    install_research_routes(app)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            started = await client.post("/api/v1/research-runs", json={"client_request_id": "cancel", "method_id": "waiting", "input": {}})
            run_id = started.json()["run_id"]
            await method.entered.wait()
            cancelled = await client.post(f"/api/v1/research-runs/{run_id}/cancel")
            assert cancelled.status_code == 200 and cancelled.json()["cancellation_requested"]
            assert (await terminal(service, run_id)).status == "cancelled"
            streamed = await client.get(f"/api/v1/research-runs/{run_id}/events/stream?limit=1")
            assert "event: workflow.finished" in streamed.text
            assert '"status":"cancelled"' in streamed.text and '"status":"succeeded"' not in streamed.text
            assert (await client.delete(f"/api/v1/research-runs/{run_id}")).json()["status"] == "cancelled"
    finally:
        await service.close()
        await app.state.run_service.close()
        await engine.close()


@pytest.mark.parametrize("value", ["-1", "+1", " 1", "1.2", "٠", "9223372036854775808", "x" * 128])
def test_sse_sequence_selector_is_strict(value):
    with pytest.raises(EngineError):
        replay_position(0, value)


@pytest.mark.asyncio
async def test_source_continuation_over_http_and_reopened_storage(tmp_path):
    from deepresearch.engine.contracts import SnapshotProposal, canonical_json, digest_bytes, new_id
    from deepresearch.workflows import SourceRange

    engine = (await Engine.open(settings(tmp_path))).unwrap()
    method = WaitingMethod()
    service = waiting_service(engine, method)
    app = create_app(engine=engine)
    app.state.research_service = service
    install_research_routes(app)
    text = ("α🙂 bounded retained evidence " * 20).encode()
    try:
        run_id = (await service.start_run(ResearchRunRequest(client_request_id="source", method_id="waiting", input={}))).run_id
        await method.entered.wait()
        live = service._runs[run_id]
        index = {"schema_version": 1, "format": "document_index/1", "text_sha256": digest_bytes(text),
                 "lines": [{"line": 1, "start_byte": 0, "end_byte": len(text)}], "pages": None}
        receipt = (await live.session.binding.storage.snapshots.commit(live.session.context,
            new_id("source_"), live.session.context.scope,
            SnapshotProposal(text, text, canonical_json(index), {"url": "https://example.org/retained"}))).unwrap()
        await live.port.update(sources={"items": [{"item_id": "retained", "url": "https://example.org/retained",
            "status": "succeeded", "snapshot_ref": receipt.snapshot_ref.to_dict(), "source_run_id": run_id,
            "line_count": 1, "text_bytes": len(text), "recording_status": "complete", "persistence_state": "committed"}]})
        method.release.set()
        assert (await terminal(service, run_id)).status == "succeeded"
        body = {"range": {"kind": "lines", "start": 1, "end_exclusive": 2}, "max_text_bytes": 32}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            assert (await client.get(f"/api/v1/research-runs/{run_id}/sources")).json()["items"][0]["item_id"] == "retained"
            assert (await client.get(f"/api/v1/research-runs/{run_id}/context")).json() is None
            assert (await client.get(f"/api/v1/research-runs/{run_id}/result")).json()["report_ref"]["artifact_id"]
            assert not (await client.get(f"/api/v1/research-runs/{run_id}/usage")).json()["available"]
            first = await client.post(f"/api/v1/research-runs/{run_id}/sources/retained/read", json=body)
            assert first.status_code == 200, first.text
            chunk = first.json()
            SourceReadView.model_validate(chunk)
            assert chunk["truncated"] and chunk["continuation"] and len(chunk["text"].encode()) <= 32
            parts = [chunk["text"]]
            continuation = chunk["continuation"]
            first_cursor = continuation
            invalid = await client.post(f"/api/v1/research-runs/{run_id}/sources/retained/read",
                json={**body, "continuation": "x" * 8193})
            assert invalid.status_code == 422
            while continuation:
                response = await client.post(f"/api/v1/research-runs/{run_id}/sources/retained/read",
                    json={**body, "continuation": continuation})
                assert response.status_code == 200, response.text
                chunk = response.json()
                parts.append(chunk["text"])
                assert chunk["continuation"] != continuation
                continuation = chunk["continuation"]
            assert "".join(parts).encode() == text
    finally:
        method.release.set()
        await service.close()
        await app.state.run_service.close()
        await engine.close()
    reopened = (await Engine.open(settings(tmp_path))).unwrap()
    recovered = create_research_service(reopened)
    try:
        # Cursors are scoped to a live Storage session. Fresh reads still work
        # after reopen without restoring that session's old cursor authority.
        with pytest.raises(EngineError) as expired:
            await recovered.read_source(run_id, "retained", SourceRange(**body["range"]), 32, first_cursor)
        assert expired.value.code == "INVALID_CURSOR"
        restored = await recovered.read_source(run_id, "retained", SourceRange(**body["range"]), 65536)
        assert restored["text"].encode() == text
    finally:
        await recovered.close()
        await reopened.close()
