"""Research routes using the same strict DTOs as Python Workflow consumers."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from fastapi import Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field

from ebd.engine.contracts import EngineError, canonical_json
from ebd.application.agent_contracts import ObjectPageView, UsageAggregate, EventReceiptView, RecordedEventView
from ebd.workflows.contracts import Contract, ContextPlan, ResearchRunRequest, ResearchRunView, SourceManifest, SourceRange, SnapshotReference


class ResearchRunPage(Contract):
    runs: list[ResearchRunView]
    cursor: str | None = None


class RolePin(Contract):
    role_id: str
    revision: int = Field(ge=1)


class MethodView(Contract):
    method_id: str
    revision: int = Field(ge=1)
    description: str
    input_schema: dict[str, Any]
    parameters_schema: dict[str, Any]
    agent_roles: list[RolePin]
    resource_digests: dict[str, str]
    sha256: str


class MethodPage(Contract):
    methods: list[MethodView]


class SourceReadRequest(Contract):
    range: SourceRange
    max_text_bytes: int = Field(default=65536, ge=1, le=65536)
    continuation: str | None = Field(default=None, max_length=8192)


class SourceSpan(Contract):
    line: int | None
    page: int | None
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)


class SourceReadView(Contract):
    run_id: str
    item_id: str
    snapshot_ref: SnapshotReference
    extraction_version: str
    normalization_version: str
    requested_range: SourceRange
    returned_range: SourceRange
    text: str
    byte_length: int = Field(ge=0)
    truncated: bool
    has_more_in_requested_range: bool
    has_more_in_document: bool
    next_position: dict[str, int] | None
    continuation: str | None
    spans: list[SourceSpan]


class ResearchEventPage(Contract):
    events: list[RecordedEventView]
    next_after_seq: int
    has_more: bool
    high_water_seq: int


class ReportChunk(Contract):
    run_id: str
    artifact_ref: dict[str, Any]
    encoding: Literal["base64"]
    data: str
    start: int
    next_offset: int
    eof: bool
    byte_length: int
    total_bytes: int
    media_type: str
    sha256: str


class ResearchUsageView(Contract):
    run_id: str
    status: str
    active: bool
    available: bool
    usage: UsageAggregate | None
    terminal_event_receipt: EventReceiptView | None


def _service(request):
    service = getattr(request.app.state, "research_service", None)
    if service is None:
        raise EngineError("SESSION_CLOSED", "Research service lifespan has not opened")
    return service


def replay_position(after_seq, last_event_id):
    """An SSE reconnect cannot move behind either explicitly selected position."""
    if last_event_id is None:
        return after_seq
    if not last_event_id.isascii() or not last_event_id.isdecimal() or len(last_event_id) > 19:
        raise EngineError("INVALID_DATA", "Last-Event-ID must be a committed event sequence")
    value = int(last_event_id)
    if value > 2**63 - 1:
        raise EngineError("INVALID_DATA", "Last-Event-ID exceeds the sequence bound")
    return max(after_seq, value)


async def stream_events(service, request, run_id, after_seq, limit, initial_page=None):
    """Subscription owns only its polling. Work outlives disconnects and replay.

    Poll twice around observing inactivity to drain events committed during the
    final status read. Every SSE id comes from a committed Storage receipt.
    """
    page = initial_page
    heartbeat_at = time.monotonic()
    try:
        while not await request.is_disconnected():
            if page is None:
                page = await service.events(run_id, after_seq, limit)
            for row in page["events"]:
                if await request.is_disconnected():
                    return
                sequence = row["receipt"]["recorded_seq"]
                if type(sequence) is not int or sequence <= after_seq:
                    raise EngineError("INVALID_DATA", "Committed event replay did not advance")
                kind = row["event"]["kind"]
                if not isinstance(kind, str) or any(char in kind for char in "\r\n"):
                    raise EngineError("INVALID_DATA", "Committed event kind is invalid")
                yield f"id: {sequence}\nevent: {kind}\ndata: ".encode() + canonical_json(row) + b"\n\n"
                after_seq = sequence
            more = page["has_more"]
            page = None
            if more:
                continue
            view = await service.get_run(run_id)
            if not view.active:
                page = await service.events(run_id, after_seq, limit)
                if not page["events"] and not page["has_more"]:
                    return
                continue
            if time.monotonic() - heartbeat_at >= 15:
                yield b": keep-alive\n\n"
                heartbeat_at = time.monotonic()
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # HTTP headers may already be sent. End with a transport error, never a
        # synthetic success/terminal fact or an arbitrary exception message.
        error = exc if isinstance(exc, EngineError) else EngineError(
            "RESEARCH_STREAM_DEFECT", "Research event subscription failed",
            {"exception_type": type(exc).__name__})
        yield b"event: error\ndata: " + canonical_json({"schema_version": 1,
            "error": error.to_dict()}) + b"\n\n"


def install_research_routes(app):
    # Resolve existing response helpers only when composition installs routes;
    # importing this module never imports create_app or starts another lifespan.
    from ebd.interfaces.http.api import response

    if getattr(app.state, "research_routes_installed", False):
        return app
    app.state.research_routes_installed = True

    async def replied(awaitable, status_code=200):
        try:
            value = await awaitable
            return response(value.to_dict() if isinstance(value, Contract) else value, status_code)
        except EngineError as error:
            if error.code == "METHOD_NOT_FOUND":
                return JSONResponse({"schema_version": 1, "error": error.to_dict()}, status_code=404)
            raise

    @app.get("/api/v1/methods", response_model=MethodPage)
    async def methods(request: Request):
        return response(_service(request).list_methods())

    @app.post("/api/v1/research-runs", response_model=ResearchRunView, status_code=202)
    async def start_run(request: Request, data: ResearchRunRequest):
        return await replied(_service(request).start_run(data), 202)

    @app.get("/api/v1/research-runs", response_model=ResearchRunPage)
    async def list_runs(request: Request, cursor: str | None = Query(default=None, max_length=8192),
                        limit: int = Query(default=100, ge=1, le=100)):
        return await replied(_service(request).list_runs(cursor, limit))

    @app.get("/api/v1/research-runs/{run_id}", response_model=ResearchRunView)
    @app.get("/api/v1/research-runs/{run_id}/status", response_model=ResearchRunView)
    async def get_run(request: Request, run_id: str):
        return await replied(_service(request).get_run(run_id))

    @app.post("/api/v1/research-runs/{run_id}/cancel", response_model=ResearchRunView)
    @app.delete("/api/v1/research-runs/{run_id}", response_model=ResearchRunView)
    async def cancel_run(request: Request, run_id: str):
        return await replied(_service(request).cancel_run(run_id))

    @app.get("/api/v1/research-runs/{run_id}/events", response_model=ResearchEventPage)
    async def events(request: Request, run_id: str, after_seq: int = Query(default=0, ge=0, le=2**63 - 1),
                     limit: int = Query(default=100, ge=1, le=100)):
        return await replied(_service(request).events(run_id, after_seq, limit))

    @app.get("/api/v1/research-runs/{run_id}/events/stream")
    async def subscription(request: Request, run_id: str,
                           after_seq: int = Query(default=0, ge=0, le=2**63 - 1),
                           limit: int = Query(default=100, ge=1, le=100)):
        current = _service(request)
        position = replay_position(after_seq, request.headers.get("last-event-id"))
        # Fail before sending 200 when ownership/history/replay is invalid.
        initial = await current.events(run_id, position, limit)
        return StreamingResponse(stream_events(current, request, run_id, position, limit, initial),
            media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/research-runs/{run_id}/sources", response_model=SourceManifest)
    async def sources(request: Request, run_id: str):
        return await replied(_service(request).get_sources(run_id))

    @app.get("/api/v1/research-runs/{run_id}/context", response_model=ContextPlan | None)
    async def context(request: Request, run_id: str):
        return await replied(_service(request).get_context(run_id))

    @app.get("/api/v1/research-runs/{run_id}/result", response_model=ResearchRunView)
    async def result(request: Request, run_id: str):
        return await replied(_service(request).get_result(run_id))

    @app.get("/api/v1/research-runs/{run_id}/usage", response_model=ResearchUsageView)
    async def usage(request: Request, run_id: str):
        return await replied(_service(request).get_usage(run_id))

    @app.get("/api/v1/research-runs/{run_id}/objects", response_model=ObjectPageView)
    async def objects(request: Request, run_id: str, cursor: str | None = Query(default=None, max_length=8192),
                      limit: int = Query(default=100, ge=1, le=100)):
        return await replied(_service(request).list_objects(run_id, cursor, limit))

    @app.get("/api/v1/research-runs/{run_id}/artifacts/{artifact_id}", response_model=ReportChunk)
    async def artifact(request: Request, run_id: str, artifact_id: str, start: int = Query(default=0, ge=0),
                       max_bytes: int = Query(default=65536, ge=1, le=65536)):
        return await replied(_service(request).read_artifact(run_id, artifact_id, start, max_bytes))

    @app.get("/api/v1/research-runs/{run_id}/context/content", response_model=ReportChunk)
    async def selected_context(request: Request, run_id: str, start: int = Query(default=0, ge=0),
                               max_bytes: int = Query(default=65536, ge=1, le=65536)):
        return await replied(_service(request).read_context(run_id, start, max_bytes))

    @app.post("/api/v1/research-runs/{run_id}/sources/{item_id}/read", response_model=SourceReadView)
    async def read_source(request: Request, run_id: str, item_id: str, data: SourceReadRequest):
        return await replied(_service(request).read_source(run_id, item_id, data.range, data.max_text_bytes, data.continuation))

    @app.get("/api/v1/research-runs/{run_id}/report", response_model=ReportChunk)
    async def report(request: Request, run_id: str, start: int = Query(default=0, ge=0),
                     max_bytes: int = Query(default=65536, ge=1, le=65536)):
        return await replied(_service(request).read_report(run_id, start, max_bytes))

    return app
