# ResearchRun service

`ResearchRunService` owns complete method execution over one caller-owned Engine.
`MethodRegistry` pins the method revision and its agent roles; the shared request
and view models are `deepresearch.workflows.ResearchRunRequest` and `ResearchRunView`.
Bootstrap supplies `baseline@1`, formal `baseline@2` and model-free `example.echo@1`.
A workflow root has no agent identity, provider, model grant or credentials.
The formal baseline plans, acquires and selects saved evidence, analyzes gaps,
then writes and reviews a report. The Planner sees the question before acquisition;
all evidence-consuming roles receive only explicitly selected saved text.
See [Baseline usage](baseline.md) and [method design](../architecture/baseline.md).

## Python composition

```python
import asyncio
from deepresearch.bootstrap.application import create_research_service
from deepresearch.engine import Engine, EngineSettings
from deepresearch.workflows import ResearchRunRequest

async def main():
    engine = (await Engine.open(EngineSettings(storage_root="local/research-store"))).unwrap()
    service = create_research_service(engine)
    try:
        view = await service.start_run(ResearchRunRequest(
            client_request_id="first-echo", method_id="example.echo",
            input={"message": "A real Storage publication"},
        ))
        while view.active:
            await asyncio.sleep(0.1)
            view = await service.get_run(view.run_id)
        print(view.to_dict())
    finally:
        cleanup = await service.close()
        if cleanup.complete:
            await engine.close()
        else:
            raise RuntimeError("Research tasks still own resources")

asyncio.run(main())
```

Direct construction accepts
`ResearchRunService(engine, registry, agent_catalog, token_meter,
extension_registry=None, max_active_runs=8)`.
The registry contains trusted Python method implementations; HTTP cannot register
code, credentials, provider endpoints or execution grants.

| Service call | Result |
| --- | --- |
| `await start_run(ResearchRunRequest)` | `ResearchRunView`; accepted work is service-owned |
| `await get_run(run_id)` | Current validated projection and committed terminal facts |
| `await list_runs(cursor=None, limit=100)` | `{schema_version, runs, cursor}` |
| `await cancel_run(run_id)` | Current view; signals owned cancellation |
| `await events(run_id, after_seq=0, limit=100)` | Committed root and child events, `next_after_seq`, `has_more` |
| `await read_source(run_id, item_id, SourceRange, max_text_bytes=65536, continuation=None)` | Bounded retained document slice |
| `await read_report(run_id, start=0, max_bytes=65536)` | Base64 artifact chunk with `next_offset`, `eof` and chunk `byte_length` |
| `await read_context(run_id, start=0, max_bytes=65536)` | Selected context bytes using the same chunk contract |
| `await list_objects(run_id, cursor=None, limit=100)` | Bounded saved-object catalog |
| `await read_artifact(run_id, artifact_id, start=0, max_bytes=65536)` | Owned Workflow artifact; foreign run references are rejected |
| `await close(timeout_seconds=30)` | `CleanupReport`; never closes the caller's Engine |

Page limits are 1–100. Report and source reads are bounded at 65,536 bytes per
call; source ranges select at most 200 lines or 10 physical pages. Ranges are
one-based and end-exclusive. Report offsets are zero-based UTF-8 byte offsets;
a chunk may end within a Unicode code point, so concatenate bytes before decoding.
`byte_length` is the bytes in the report chunk, and `total_bytes` is the artifact
length. `next_offset` is the next request's `start`.

## HTTP

`install_research_routes(app)` mounts the following `/api/v1` routes and uses the
`app.state.research_service` supplied by the owning lifespan. The existing local
host/origin boundary, finite strict JSON parser and safe error handlers apply.
The HTTP request body is the same `ResearchRunRequest` used by Python consumers.

| Verb and path | Behavior |
| --- | --- |
| `GET /methods` | Pinned method catalog and schemas |
| `POST /research-runs` | Admit a method; returns 202 and a `ResearchRunView` |
| `GET /research-runs?cursor=...&limit=100` | Owned research catalog |
| `GET /research-runs/{run_id}` | Status, activity, nodes, sources, context, refs and usage |
| `POST /research-runs/{run_id}/cancel` | Signal cancellation |
| `DELETE /research-runs/{run_id}` | Alias for cancellation; retained records remain readable |
| `GET /research-runs/{run_id}/events?after_seq=0&limit=100` | Incremental committed history |
| `GET /research-runs/{run_id}/events/stream` | SSE history replay and progress |
| `GET /research-runs/{run_id}/sources` | `SourceManifest` |
| `POST /research-runs/{run_id}/sources/{item_id}/read` | Read a selected retained range |
| `GET /research-runs/{run_id}/context` | `ContextPlan` or null |
| `GET /research-runs/{run_id}/context/content` | Selected evidence bytes; chunk contract matches report |
| `GET /research-runs/{run_id}/objects` | Saved object descriptors and cursor |
| `GET /research-runs/{run_id}/artifacts/{artifact_id}` | Bounded saved discovery/manifests/context bytes |
| `GET /research-runs/{run_id}/result` | Validated view with report/result/checkpoint references |
| `GET /research-runs/{run_id}/usage` | Cumulative observed usage across all roles or null |
| `GET /research-runs/{run_id}/report?start=0&max_bytes=65536` | Explicit bounded report bytes |

Start a complete baseline with a configured named profile:

```json
{
  "schema_version": 1,
  "client_request_id": "ebd-question-001",
  "method_id": "baseline",
  "method_revision": 2,
  "input": {"question": "What is Environment Based Design?"},
  "parameters": {"max_sources": 3},
  "profile_ref": "deepseek",
  "model_ref": "deepseek-flash",
  "timeout_seconds": 600.0
}
```

For execution without model credentials or network, choose `example.echo` with
`input: {"message": "Hello"}`. It publishes artifacts and a checkpoint through
real Storage. It is a separate integration method, not a simulated baseline.
All methods validate the chosen profile/model against `engine.list_profiles()`;
validating configured names does not resolve credentials.
The request's method revision still defaults to 1 for compatibility. Select
revision 2 explicitly for the formal Baseline; method revisions and wire v1 are
independent.

A saved source read has this body:

```json
{
  "range": {"kind": "lines", "start": 1, "end_exclusive": 21},
  "max_text_bytes": 16384,
  "continuation": null
}
```

If the slice has `has_more_in_requested_range`, send its opaque `continuation`
with the same source, range and allowance. The cursor is at most 8,192 characters
and carries no authority: each read obtains fresh, bounded result access to that
run's committed snapshot. Continuations belong to the live Storage session;
after reopen, begin a fresh selected-range read. Sources and reports remain
readable after reopen.
Sources, context and result metadata do not automatically return source/report
text. Token measurements distinguish verified counts from named estimates;
`usage` retains the cumulative observed provider aggregate and its completeness,
including available consumption from failed roles. Unknown counts remain null.

## Admission, terminal recording and recovery

The service persists `research.run/1` with CAS versions, a full canonical request
fingerprint, selected profile/model and method/agent resource pins. It publishes
the full canonical request as `research-request.json`, links it from the
`research-method.json` manifest and the accepted event, and preserves method-created manifests and checkpoints in the
workflow scope. A provisioned descriptor also retains the bounded request
identity, so even an uncertain first state acknowledgement cannot silently start
a replacement execution.

The same `client_request_id` and full request return the original run. Changing
any request field under that identity raises `IDEMPOTENCY_CONFLICT` (409). An
initial bounded scan covers at most 32 pages of 100 owned run descriptors. If the
scan is exhausted, admission fails closed rather than assuming an identity is
unused. Restart can reconcile an existing identity without its method being
registered again; it never dispatches, resumes or replenishes that run's budget.

Only a committed `workflow.finished` receipt and its acknowledged projection can
confirm success. The service also requires a Storage completion attestation
published after the live workflow session closes successfully. This final bounded
host review export supplies no tools, provider or execution authority. Missing
terminal recording, unknown outcomes or failed cleanup cannot reopen as success.
A saved run without complete terminal evidence is `interrupted`. Checkpoints are
data and `automatic_resume` is always false.

Cancellation sets `cancellation_requested` and records a committed request;
the response remains active until method/tool/Agent execution settles.
Failure facts use bounded cleanup recording;
`port.update(cleanup=True, **fields)` requests the same ledger/lease and a bounded
cleanup context. The application requests the exact `research.run/1` cleanup
key grant. Storage uses `state.cleanup` with the original ledger, allowing no
unselected key, model/tool action or artifact publication.
Cleanup projection updates may only change existing nodes and sources and may
not invent successful publications. Ordinary methods cannot change application
status or identity. `close` stops admissions, signals cancellation and drains
admission/execution tasks. It closes the retained Hook dispatcher before the
workflow session and merges their cleanup reports. Unconfirmed Hook handlers
prevent success and keep their dispatcher reachable. A deadline returns incomplete cleanup and keeps owned
work reachable; callers should retain Engine ownership until it settles.

## SSE replay

Every SSE frame's `id` is its committed Storage `recorded_seq`; `event` is the
recorded event kind, and `data` contains that event and its receipt. The stream
includes every child role's events and drains committed history when execution ends.
Use `after_seq` or the browser's `Last-Event-ID` to reconnect; when both are
present, replay starts after their maximum. Positions must be nonnegative signed
64-bit integers. Drain paginated polling using `has_more` and `next_after_seq`.

HTTP disconnect closes only the subscriber. It does not cancel admission or
method execution. Streams buffer at most one bounded event page and poll
committed Storage rather than synthesizing progress. An error after headers are
sent produces an `event: error` frame with a safe error envelope and closes the
subscription; it does not manufacture a success terminal or cancel the run.
Optional extensions record bounded metadata and decisions through the same
workflow recorder. A complete method runs with no extensions installed.

The application and HTTP tests use real Engine/Storage, controlled provider and
fetch boundaries, and real retained-document reads. They verify contracts,
idempotency, reopen, cancellation, uncertain recording, cleanup failures,
selected evidence delivery and SSE replay/disconnection. Controlled tests do not
establish live external provider/search acceptance.
