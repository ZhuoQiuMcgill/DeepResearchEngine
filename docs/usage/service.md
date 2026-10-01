# Local run service

For setup and a complete registration/start/poll/download sequence, use the
[console walkthrough](console-quickstart.md). Frontend tooling can consume the
[generated OpenAPI snapshot](../api/openapi.json) without running a backend;
the live server publishes the corresponding schema at `/openapi.json`.

The service supplies asynchronous run control and durable inspection over the
real Engine. One process owns one Storage root. A frontend talks to this process;
it does not open SQLite or another Engine for that same store. Research strategy
remains a Python application built on public Engine interfaces.

```powershell
uv --cache-dir .uv-cache run --locked --offline ebd serve --help
uv --cache-dir .uv-cache run --locked --offline ebd --store local/store serve --port 8765 --origin http://localhost:5173
```

The CLI starts one Uvicorn worker on loopback. See its help for store, port and
explicit CORS origin options. Open `/docs` for the generated OpenAPI interface
and `/openapi.json` for its machine-readable schema. The default permits direct
local clients and browsers on the service's own approved origin; additional
browser origins must be explicitly trusted. Remote clients,
untrusted Host headers and unlisted browser origins are rejected. This is a
trusted local development service, without multiuser authentication or remote
deployment support. Do not bind it to a public network or add wildcard origins.

The application factory can also be embedded:

```python
from ebd.connections import EngineSettings
from ebd.service import create_app

app = create_app(
    EngineSettings(storage_root="local/store"),
    trusted_origins=("http://localhost:5173",),
)
```

Its lifespan opens and closes one Engine and drains its RunService first.
`create_app(engine=already_open_engine)` injects an existing owner and leaves
that Engine open after service shutdown. `app.state.run_service` exposes the
service in this mode immediately, including for HTTPX ASGITransport tests that
do not run ASGI lifespan automatically. The caller closes the service before
closing its injected Engine. Shutdown reports unsettled work rather than
abandoning admitted operations or closing their Storage.

## HTTP interface

Requests and responses use `schema_version: 1`. Requests reject unknown fields,
duplicate JSON keys, nonfinite numbers, oversized bodies and invalid schemas.
The maximum body is 256 KiB, JSON response 512 KiB, page 100 entries, and artifact
chunk 64 KiB. Large reports are immutable artifacts retrieved in bounded chunks.

| Method and path | Meaning |
| --- | --- |
| `GET /api/v1/health` | Readiness, store identity, owned active count |
| `GET /api/v1/agents` | Registered agent definitions/revisions/rules |
| `POST /api/v1/agents` | Register a typed agent using a preconfigured named profile |
| `GET /api/v1/profiles` | Safe named profile/model/provider metadata |
| `GET /api/v1/tools` | Tool schemas and limits, without argv/config/credentials |
| `POST /api/v1/runs` | Validate/admit a run and return its handle with HTTP 202 |
| `GET /api/v1/runs?cursor=...&limit=...` | Owned run catalog; optional agent/root filters |
| `GET /api/v1/runs/{id}` or `/status` | Execution, activity and recording state |
| `POST /api/v1/runs/{id}/cancel` | Signal cooperative cancellation; terminal cancellation is idempotent |
| `GET /api/v1/runs/{id}/result` | Durable terminal output refs, validation, persistence, errors and receipts |
| `GET /api/v1/runs/{id}/usage` | Committed Runtime aggregate; missing counts remain unknown |
| `GET /api/v1/runs/{id}/events?after_seq=0&limit=100` | Incremental committed events and next sequence |
| `GET /api/v1/runs/{id}/objects` | Bounded immutable object catalog |
| `GET /api/v1/runs/{id}/artifacts/{artifact_id}?start=0&max_bytes=65536` | Owned artifact byte chunk encoded as base64 |
| `GET /api/v1/runs/{id}/state/{key}?version=...` | Current or exact historical application state |

Example registration and start bodies:

```json
{"schema_version":1,"agent_id":"researcher","instructions":"Research the supplied task using registered tools and saved sources.","profile_ref":"deepseek","model_ref":"deepseek-flash","allowed_tools":[{"name":"web.search","revision":1},{"name":"web.fetch","revision":1},{"name":"document.read","revision":1}]}
```

```json
{"schema_version":1,"agent_id":"researcher","revision":1,"input":"What is EBD (Environment Based Design)","timeout_seconds":600,"limits":{"model_calls":16,"tool_calls":32}}
```

Registration allows input/output schemas and bounded limits. Invocation rules
select explicitly registered destinations and tool/model/export bounds. HTTP
requests cannot register keys, provider endpoints, arbitrary provider settings,
context grants or shared-evidence authority. Those belong to trusted Python
configuration and workflow composition. Tool/schema revisions are pinned;
changing content under an existing agent revision conflicts.

The start handle contains `run_id`, `run_ref`, `agent_ref`, `accepted_at`,
`status="accepted"`, `active=true`, and `recording_status="pending"`. Admission
validation occurs before acceptance/model dispatch. A disconnected HTTP client
does not stop an accepted run. Binding/admission/publication tasks are strongly
owned too; shutdown's finite deadline includes admission lock acquisition and
unfinished accepted-state commits. An incomplete close retains those tasks and
Engine ownership; retry close after the owned write settles. HTTP cancellation sets the live context Event;
it does not call Python `Task.cancel()` or manufacture a terminal result.

Poll status until `active=false`, then inspect execution status and recording
separately. `succeeded` without complete recording/persistence is not successful
delivery. `/result` returns `available=false` when no durable `agent.finished`
record exists. It returns immutable report refs when one does; read those bytes
through `/artifacts`, not an unrelated in-memory model response.

Event polling returns `{schema_version, events, next_after_seq, has_more}`. Each
row contains the actual persisted `event` and `receipt`. Save `next_after_seq`
and request the following page. Set `include_descendants=true` to inspect the
owned root lineage. Deduplicate by store/event ID; acknowledgement retries
are not additional API responses. A byte-bound page returns a prefix and its
actual final sequence so omitted events remain available. Live per-attempt
token observations appear in `model.outcome`; terminal `/usage` preserves the
Runtime's known subtotals/completeness/unknown attempt IDs. Cache and reasoning
counts are subsets, not additional totals.

Artifact chunks return `{encoding:"base64", data, start, next_offset, eof,
byte_length, media_type, sha256, artifact_ref}`. Decode each chunk, advance to
`next_offset`, and stop at `eof`. The service verifies run ownership through
Engine catalog/access grants; a guessed artifact reference cannot grant access.

Service restart reconstructs a known terminal from durable `agent.finished`
and its receipt. Without that terminal, an old run is `interrupted`; saved state
never automatically replays a model/tool call. Active tasks and authority are
process-local. Agent definitions must be registered again after restart.
Checkpoints remain application data, without automatic execution resume.

Cataloged standalone tools use their actual committed `tool.outcome` or
`tool.rejected` as the terminal. Their result exposes the recorded
`result_descriptor`, `persistence`, `process`, `observations` and error; it does
not invent model output or token usage. A durable preflight rejection is shown
with Runtime's canonical failure status, with no worker dispatch. Saved tool results remain inspectable
after reopen even though these tools were launched through the CLI/Python API.

Every route declares a named OpenAPI response schema, including nested immutable
refs, receipts, event pages, nullable token counters, object descriptors and
artifact chunks. Responses permit additive v1 fields; application state and
event payloads remain arbitrary JSON. This supports generated frontend clients
without exposing Storage, configuration or live authority. State key paths may
contain slashes; versions are positive retained revisions.

Errors use `{schema_version:1,error:{code,message,details,...}}`. Common HTTP
codes are 403 for denied authority/origin, 404 for unknown objects/runs/agents,
409 for busy/conflicting identity, 413 for bounds, 422 for invalid input, and
503 for unavailable configuration/service. Validation errors include only
field locations/types, never echoed request bodies or credentials.

## Python interface

```python
from ebd.connections import AgentRef, RunOptions
from ebd.service import RunService

service = RunService(engine)
handle = await service.start_run(AgentRef("researcher", 1), question,
                               RunOptions(timeout_seconds=600))
view = await service.get_run(handle["run_id"])
page = await service.events(handle["run_id"], after_seq=0, limit=100)
result = await service.get_result(handle["run_id"])
usage = await service.get_usage(handle["run_id"])
await service.cancel_run(handle["run_id"])
cleanup = await service.close(timeout_seconds=30)
# Close the Engine only after cleanup.complete.
```

Start performs public `open_agent_session` and Runtime admission; one strongly
owned background task consumes the lease through Runtime execution. Runtime
owns ordinary model/tool lifecycle records and output publication. Service
acceptance state uses normal scoped CAS Storage, without a second database,
fake provider or duplicate execution logger. The service owns no research
scheduler or EBD ranking algorithm.

Controlled HTTP/native-provider-boundary tests exercise the actual Runtime,
SQLite/files, terminal records, incremental polling, bounded report retrieval,
close/reopen, cooperative cancellation and request/ownership boundaries:

```powershell
uv --cache-dir .uv-cache run --locked --offline pytest tests/service -q
```

These fault/contract tests complement live model/tool acceptance. They do not
claim that a controlled provider response proves an external API integration.
Local vLLM Qwen live verification remains pending deployment.

Actual DeepSeek, CLI and Uvicorn TCP acceptance is runnable with:

```powershell
uv --cache-dir .uv-cache run --locked --offline python examples/live_service_check.py
```

This bounded check makes real API calls. It retains supplied-source provenance
explicitly, performs a real Crossref request, cancels a real console run and
verifies reports/token usage after close/reopen. See the
[saved consumer acceptance](../consumer-acceptance.md) for actual results.
