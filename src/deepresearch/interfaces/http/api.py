"""Local HTTP composition. One lifespan owns one Engine and its run service."""
from __future__ import annotations

from contextlib import asynccontextmanager
import ipaddress

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from deepresearch.engine.connections import (
    AgentRef, Engine, EngineSettings, InvocationRule, RunOptions,
)
from deepresearch.engine.contracts import (
    AgentDefinition, EngineError, ToolRef, canonical_json, strict_json_loads,
    to_json_value,
)
from deepresearch.application.agent_contracts import (
    ErrorView, RegisterAgentRequest, RunView, StartRunRequest, HealthView,
    AgentCatalogView, RegisteredAgentView, ProfileCatalogView, ToolCatalogView,
    RunPageView, ResultView, UsageView, EventPageView, ObjectPageView,
    ArtifactChunkView, StateView,
)
from deepresearch.application.agent_runs import MAX_RESPONSE_BYTES, RunService
from deepresearch.bootstrap import create_research_service


MAX_BODY_BYTES = 262144


def error_status(error):
    code = error.code
    if code in {"NOT_FOUND", "AGENT_NOT_FOUND", "RUN_NOT_FOUND"}:
        return 404
    if code in {"ACCESS_DENIED", "ORIGIN_DENIED", "REMOTE_ACCESS_DENIED"}:
        return 403
    if code in {"SERVICE_BUSY", "STORAGE_BUSY", "REGISTRATION_CONFLICT", "VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT"}:
        return 409
    if code in {"LIMIT_EXCEEDED", "REQUEST_TOO_LARGE"}:
        return 413
    if code in {"CREDENTIAL_MISSING", "PROFILE_NOT_FOUND", "SESSION_CLOSED"}:
        return 503
    if code in {"INVALID_DATA", "INVALID_RANGE", "INVALID_CURSOR", "PROFILE_MISMATCH"} or "validation" in code:
        return 422
    return 500


def error_response(error):
    # Owners supply safe error messages/details; no exception repr or request
    # body is included, even when validation input contains a credential.
    return JSONResponse({"schema_version": 1, "error": error.to_dict()}, status_code=error_status(error))


def response(value, status_code=200):
    value = to_json_value(value)
    try:
        canonical_json(value, MAX_RESPONSE_BYTES)
    except ValueError:
        raise EngineError("LIMIT_EXCEEDED", "Encoded response exceeds the public JSON bound") from None
    return JSONResponse(value, status_code=status_code)


def create_app(settings: EngineSettings | None = None, *, engine: Engine | None = None,
               trusted_origins: tuple[str, ...] = (),
               trusted_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver"),
               max_active_runs: int = 8, close_timeout_seconds: float = 30):
    """Create a loopback-only app. Injected Engines remain caller-owned.

    Only explicit trusted browser origins are allowed. An HTTP caller can
    select named profiles but cannot register credentials/endpoints/settings
    or construct evidence grants. Trusted Python workflow authors use Engine.
    """
    if not 0 < close_timeout_seconds <= 60:
        raise ValueError("close timeout must be between zero and 60 seconds")
    if any(origin == "*" or not origin.startswith(("http://", "https://")) for origin in trusted_origins):
        raise ValueError("CORS requires explicit HTTP(S) origins")
    if "*" in trusted_hosts:
        raise ValueError("Trusted hosts must be explicit")
    injected = engine is not None

    @asynccontextmanager
    async def lifespan(app):
        if app.state.run_service is None:
            opened = (await Engine.open(settings or EngineSettings())).unwrap()
            app.state.run_service = RunService(opened, max_active_runs=max_active_runs)
        if app.state.research_service is None:
            app.state.research_service = create_research_service(app.state.run_service.engine,
                max_active_runs=max_active_runs)
        try:
            yield
        finally:
            service = app.state.run_service
            research_cleanup = await app.state.research_service.close(timeout_seconds=close_timeout_seconds)
            app.state.research_cleanup = research_cleanup.to_dict()
            cleanup = await service.close(timeout_seconds=close_timeout_seconds)
            app.state.cleanup = cleanup.to_dict()
            if cleanup.complete and research_cleanup.complete and not injected:
                engine_cleanup = await service.engine.close()
                app.state.engine_cleanup = engine_cleanup.to_dict()
                if not engine_cleanup.complete:
                    raise RuntimeError("Engine shutdown has unsettled resources; ownership is retained")
            elif not cleanup.complete or not research_cleanup.complete:
                # Keep strong ownership and Storage alive for admitted work.
                raise RuntimeError("Service shutdown has unsettled execution; Engine remains owned")

    app = FastAPI(title="DeepResearch execution service", version="1.0.0", lifespan=lifespan,
        responses={code: {"model": ErrorView} for code in (403, 404, 409, 413, 422, 500, 503)},
        description="Local run control and durable research records; schema_version=1.")
    app.state.run_service = RunService(engine, max_active_runs=max_active_runs) if injected else None
    app.state.research_service = create_research_service(engine, max_active_runs=max_active_runs) if injected else None
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(trusted_hosts))
    if trusted_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(trusted_origins),
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Last-Event-ID"],
            allow_credentials=False)

    @app.middleware("http")
    async def local_boundary(request, call_next):
        client = request.client
        host = client.host if client else None
        try:
            local = host is not None and ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host in {"localhost", "testclient"}
        if not local:
            return error_response(EngineError("REMOTE_ACCESS_DENIED", "This service accepts loopback clients only"))
        origin = request.headers.get("origin")
        # Same-origin OpenAPI/browser requests need no CORS grant. Verify the
        # Host against the explicit host allowlist before using it in this
        # comparison; an arbitrary reflected Host cannot authorize an origin.
        same_origin = f"{request.url.scheme}://{request.url.netloc}"
        approved_same_origin = request.url.hostname in trusted_hosts and origin == same_origin
        if origin and origin not in trusted_origins and not approved_same_origin:
            return error_response(EngineError("ORIGIN_DENIED", "Browser origin is not trusted"))
        if request.method in {"POST", "PUT", "PATCH"}:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_BODY_BYTES:
                    return error_response(EngineError("REQUEST_TOO_LARGE", "Request body exceeds 256 KiB"))
            if raw:
                if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                    return error_response(EngineError("INVALID_DATA", "Use application/json for request bodies"))
                try:
                    strict_json_loads(bytes(raw), MAX_BODY_BYTES)
                except (ValueError, UnicodeError):
                    return error_response(EngineError("INVALID_DATA", "Request must contain strict finite JSON with unique keys"))
            # Starlette's cached request wrapper replays this bounded body to
            # the route parser after stream validation.
            request._body = bytes(raw)
        try:
            return await call_next(request)
        except (ValueError, TypeError):
            return error_response(EngineError("INVALID_DATA", "Request or response exceeds the supported JSON contract"))
        except Exception as exc:
            return error_response(EngineError("SERVICE_DEFECT", "Service request encountered an unexpected defect",
                {"exception_type": type(exc).__name__}))

    def service(request):
        if request.app.state.run_service is None:
            raise EngineError("SESSION_CLOSED", "Service lifespan has not opened the Engine")
        return request.app.state.run_service

    @app.exception_handler(EngineError)
    async def engine_error_handler(request, exc):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        issues = [{"location": list(issue["loc"]), "type": issue["type"]} for issue in exc.errors()[:32]]
        return error_response(EngineError("INVALID_DATA", "Request schema validation failed", {"issues": issues}))

    @app.get("/api/v1/health", response_model=HealthView)
    async def health(request: Request):
        current = service(request)
        return response({"schema_version": 1, "ready": current.accepting,
            "store_id": current.engine.storage.store_id, "active_runs": current.active_count,
            "single_owner": True, "automatic_resume": False})

    @app.get("/api/v1/agents", response_model=AgentCatalogView)
    async def agents(request: Request):
        return response({"schema_version": 1, "agents": service(request).engine.list_agents()})

    @app.post("/api/v1/agents", status_code=201, response_model=RegisteredAgentView)
    async def register_agent(request: Request, data: RegisterAgentRequest):
        current = service(request)
        canonical_json(data.model_dump(), 131072)
        # Definition settings/context authority are host-owned. Only the pinned
        # model of a preconfigured, safe named profile may be selected here.
        profiles = current.engine.list_profiles()
        if not any(p.get("profile_ref", p.get("profile_name")) == data.profile_ref
                   and p.get("model_id", p.get("model_ref")) == data.model_ref for p in profiles):
            raise EngineError("PROFILE_MISMATCH", "Select a preconfigured profile and its pinned model")
        definition = AgentDefinition(data.agent_id, data.instructions, data.model_ref, data.profile_ref,
            allowed_tools=[ToolRef(t.name, t.revision) for t in data.allowed_tools],
            input_schema=data.input_schema, output_schema=data.output_schema,
            output_mode=data.output_mode, output_media_type=data.output_media_type,
            limits=data.limits, revision=data.revision,
            error_policy={"finalize_on_limit": data.finalize_on_limit})
        rules = tuple(InvocationRule(destination=AgentRef(r.agent_id, r.revision),
            allowed_tools=tuple(r.allowed_tools), allow_model=r.allow_model,
            allow_export=r.allow_export, allow_onward=r.allow_onward,
            max_depth=r.max_depth, timeout_seconds=r.timeout_seconds, limits=r.limits)
            for r in data.invocation_rules)
        registered = current.engine.register_agent(definition, rules).unwrap()
        return response({"schema_version": 1, "agent_ref": registered.ref.to_dict(),
            "definition_ref": registered.definition_ref}, 201)

    @app.get("/api/v1/profiles", response_model=ProfileCatalogView)
    async def profiles(request: Request):
        return response({"schema_version": 1, "profiles": service(request).engine.list_profiles()})

    @app.get("/api/v1/tools", response_model=ToolCatalogView)
    async def tools(request: Request):
        safe = ("name", "revision", "description", "input_schema", "output_schema", "capabilities", "limits", "schema_version")
        catalog = [{key: getattr(tool, key) for key in safe} for tool in service(request).engine.catalog.definitions]
        return response({"schema_version": 1, "tools": catalog})

    @app.post("/api/v1/runs", status_code=202, response_model=RunView)
    async def start_run(request: Request, data: StartRunRequest):
        current = service(request)
        handle = await current.start_run(AgentRef(data.agent_id, data.revision), data.input,
            RunOptions(data.timeout_seconds, data.limits, data.metadata))
        return response(handle, 202)

    @app.get("/api/v1/runs", response_model=RunPageView)
    async def runs(request: Request, cursor: str | None = Query(default=None, max_length=8192),
                   limit: int = Query(default=100, ge=1, le=100),
                   agent_id: str | None = Query(default=None, max_length=128),
                   root_run_id: str | None = Query(default=None, max_length=256)):
        filters = {key: value for key, value in {"agent_id": agent_id, "root_run_id": root_run_id}.items() if value is not None}
        return response(await service(request).list_runs(filters, cursor, limit))

    @app.get("/api/v1/runs/{run_id}", response_model=RunView)
    @app.get("/api/v1/runs/{run_id}/status", response_model=RunView)
    async def run_status(request: Request, run_id: str):
        return response(await service(request).get_run(run_id))

    @app.post("/api/v1/runs/{run_id}/cancel", response_model=RunView)
    async def run_cancel(request: Request, run_id: str):
        return response(await service(request).cancel_run(run_id))

    @app.get("/api/v1/runs/{run_id}/result", response_model=ResultView)
    async def run_result(request: Request, run_id: str):
        return response(await service(request).get_result(run_id))

    @app.get("/api/v1/runs/{run_id}/usage", response_model=UsageView)
    async def run_usage(request: Request, run_id: str):
        return response(await service(request).get_usage(run_id))

    @app.get("/api/v1/runs/{run_id}/events", response_model=EventPageView)
    async def run_events(request: Request, run_id: str,
                         after_seq: int = Query(default=0, ge=0),
                         limit: int = Query(default=100, ge=1, le=100),
                         include_descendants: bool = False):
        return response(await service(request).events(run_id, after_seq, limit, include_descendants))

    @app.get("/api/v1/runs/{run_id}/objects", response_model=ObjectPageView)
    async def run_objects(request: Request, run_id: str,
                          cursor: str | None = Query(default=None, max_length=8192),
                          limit: int = Query(default=100, ge=1, le=100)):
        return response(await service(request).objects(run_id, cursor, limit))

    @app.get("/api/v1/runs/{run_id}/artifacts/{artifact_id}", response_model=ArtifactChunkView)
    async def run_artifact(request: Request, run_id: str, artifact_id: str,
                           start: int = Query(default=0, ge=0),
                           max_bytes: int = Query(default=65536, ge=1, le=65536)):
        return response(await service(request).read_artifact(run_id, artifact_id, start=start, max_bytes=max_bytes))

    @app.get("/api/v1/runs/{run_id}/state/{key:path}", response_model=StateView)
    async def run_state(request: Request, run_id: str, key: str,
                        version: int | None = Query(default=None, ge=1)):
        return response(await service(request).read_state(run_id, key, version))

    from deepresearch.interfaces.http.research import install_research_routes
    install_research_routes(app)
    return app
