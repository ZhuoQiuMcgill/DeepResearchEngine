# Storage

Storage runs a real SQLite connection and immutable file store on one owned
worker thread. Connections opens `StorageSession`, provisions runs, and passes
the scoped facades into runtime/tool/result-access bindings. Callers receive
typed `Ok(value)` or `Err(EngineError)` results; references carry identity only.

```python
from ebd.connections import Engine, EngineSettings

engine = (await Engine.open(EngineSettings(storage_root="local/store"))).unwrap()
# Engine.run_agent, Engine.run_tool and Engine.open_run_access provide contexts
# with current grants. Use the binding's context and its Storage facade.
await engine.close()
```

The lower-level owner factory is
`await StorageSession.open({"root": path, "profile": "delete"})`.
The factory is a host bootstrap surface, not a registered worker tool. Trusted
Connections alone provisions a scope through
`provision_run(admin_context, run_descriptor)`; ordinary grants do not create
scopes. `describe_run` requires `run.describe` before returning a descriptor.
Explicit shared scopes use `provision_scope(admin_context, shared_scope, descriptor)`.
Multi-scope batches require all key grants; their history/receipt visibility
requires all affected scope grants.

| Facade | Context-first operations |
| --- | --- |
| `state` | `get(context, scope, key)`, `get_version(context, scope, key, version)`, `commit(context, operation_id, mutations, activity=None)` |
| `artifacts` | `put(context, operation_id, scope, content, metadata=None)`, `open(context, ref, byte_range=None, max_bytes=8388608)` |
| `snapshots` | `commit(context, operation_id, scope, proposal)`, `read(context, ref, range, max_text_bytes=65536, continuation=None)` |
| `checkpoints` | `save(context, operation_id, scope, envelope)`, `load(context, ref, accepted_formats=("engine_checkpoint/1",))` |
| `recorder` | `append(context, event)`, `status(context, event_id, expected_event_digest=None)` |
| `activity` | `query(context, filters=None, cursor=None, limit=100)` |
| `operations` | `status(context, operation_id)` |

The owner also exposes discovery and metadata inspection for the Connections
run service:

| Operation | Authority and result |
| --- | --- |
| `list_runs(context, filters=None, cursor=None, limit=100)` | `runs.list` selecting `context.principal`; returns `{runs, cursor, schema_version}` |
| `list_objects(context, scope, cursor=None, limit=100)` | `objects.list` on the exact scope, whose persisted `owner_principal` must match the context; returns `{objects, cursor, schema_version}` |
| `describe_object(context, ref)` | Matching `artifact.read`, `snapshot.read` or `checkpoint.read` for the actual stored scope/ref; returns public metadata without reading content |
| `latest_run_event(context, run_id, kind="agent.finished")` | Target-scope `events.read`; returns the latest visible `{event, receipt}` or `None` |
| `history_watermark(context)` | Context-scope `events.read`; returns the committed store-wide sequence clock without event contents |
| `activity.poll(context, filters=None, after_seq=0, limit=100, through_seq=None)` | Explicit scoped `events.read`; returns `{events, next_after_seq, has_more, high_water_seq, schema_version}` |

Run discovery filters are closed: `root_run_id`, `parent_run_id`, `agent_id`
and `context_kind`. IDs must be bounded strings; `parent_run_id` and `agent_id`
also accept null to select records without those fields. Only runs owned by
the caller's current principal are returned; the platform's internal quota
run is excluded. Saved arbitrary caller metadata is omitted. Run registration
order and a fixed registration watermark keep cursor page membership stable.

Object discovery includes ordinary artifacts, READY snapshot/checkpoint
components and their parent objects. Descriptors carry `kind`, typed `ref`,
tagged `scope`, `byte_length`, `sha256`, `media_type` and `schema_version`.
Snapshot descriptors additionally carry extraction/normalization versions,
line count and nullable physical page count; their byte/hash/media fields
describe the saved derived text. Checkpoint descriptors carry format and run
identity; their byte/hash/media fields describe the saved envelope. Internal
paths, raw publication descriptors, origins and arbitrary metadata are omitted.
Discovery grants confer no content read right. Description still requires an
object read grant, including exact scope/selector and media/format constraints.
Listing a shared scope requires its provisioning descriptor to name the
owning principal explicitly. No owner is inferred from scope references.

Catalog limits are 1..500 records and at most 1 MiB encoded JSON. Opaque
cursors bind store, principal, selected grant, filters/scope and watermark;
new publications cannot enter an existing page sequence, including artifacts
reserved before the initial page but committed later. Cursors expire and do
not survive owner close/reopen. Start a fresh authorized catalog query after
reopen. Metadata reads consume normal shared read/count quotas.

Progress polling accepts the existing history filters plus `root_run_id`;
lineage matching does not grant access to child scopes. Every affected event
scope must be authorized, including multi-scope state publication events.
`after_seq` is a nonnegative recorded sequence, and `next_after_seq` advances
only through returned events. Poll again after that position to receive future
committed events. `high_water_seq` is the current committed store sequence
clock, capped by `through_seq` when supplied. Unlike a history cursor, the numeric position can be retained
across reopen, but a fresh live history grant is still required. Pages are
bounded to 1 MiB and 500 events; oversized records fail without advancing past
them. No polling/terminal lookup operation restores execution authority or
replays a model/tool call. Connections captures `history_watermark` before
discovering owned descendants, issues their exact scope grants, then polls
with `through_seq` set to that watermark. Runs producing events below that
clock were already registered when the clock was captured; later registrations
and records are deferred to the next poll. This prevents a newly registered
child from being omitted while a later parent event advances the position.
The sequence is a store-wide ordering clock, not an indication of other
principals' event contents or execution status.
Incremental polls use the SQLite sequence index over the requested interval,
apply exact scoped selectors and closed filters in SQL, and fetch at most one
extra record to establish `has_more`. Old, ungranted and filtered records are
not decoded into Python events on every request. Fixed-watermark history
queries retain their visible-record watermark behavior.

Use `ArtifactContent` for immutable byte length/SHA-256 declaration,
`ArtifactMetadata` for media type/display data, and `StateMutation` for CAS.
`ArtifactContent(data=bytes)` or
`ArtifactContent(source=source, byte_length=n, sha256=declared_digest)` supplies
exactly one representation. An async source implements `read(max_bytes)` and
`aclose()`. Authorization, identical-ID receipt/pending reconciliation and
fresh quota reservation happen before Storage consumes or owns that source.
Rejected/reconciled submissions leave the caller source untouched. A newly
admitted writer owns it, reads bounded chunks, verifies actual length/digest
and closes it before READY. Incomplete source cleanup retains the root until
close can settle it. Borrower cancellation cannot detach this owned writer.
All wire digests are `sha256:` followed by lowercase hexadecimal. Artifact read
returns a handle with `await read(context, max_bytes)` producing `ByteChunk`;
only a successful EOF establishes the complete selected read. Close the handle
through `await aclose(context)`. This bounded release accepts its original
authority and remains idempotent; it does not grant new reads.

Put/delete advances a retained state revision. Expected version zero means a
key has never existed; deletion leaves a tombstone, so recreation uses its
actual tombstone revision. A conflict or failure rolls back the entire batch,
publication event and receipt. Historical revisions remain immutable.

Reuse an event/operation ID only for delivery of the identical frozen request
and originating principal/run/action/attempt. Current authority is checked
before receipt disclosure. An existing receipt is reconciled before fresh
write quota, source handling or CAS; an exhausted write allowance cannot deny
an otherwise authorized identical receipt. Changed content/origin conflicts.
Pending or uncertain writes are observed through status, never used to replay
a model call, fetch or other external effect.

Fresh host observer grants select exact event/operation IDs and the permitted
stored origin. They allow the same status APIs to return original receipts
without replacing the fresh host identity. They do not authorize delivery,
writes, history, access to receipt refs or execution reservation release.
`record_cleanup` permits only owner event append/status and lease cleanup;
it cannot admit artifact, state, snapshot or checkpoint writes.

Per-response model token usage is recorded by the agent runtime in the existing
`model.outcome` activity. Storage commits that activity and its receipt; there
is no separate token-usage writer or additional dispatch. The event's
`context.action_id` and `context.attempt_id` identify the model attempt, and its
`payload.request_audit` retains the safe provider response identity. The
`payload.usage` fields are `input_tokens`, `output_tokens`, `total_tokens`,
`cached_input_tokens`, `uncached_input_tokens` and `reasoning_output_tokens`, plus `completeness`,
`source` and `measurement_ref`. Counts are nonnegative integers or null.
Missing counts stay unknown; a real zero stays zero. Cache and reasoning
counts are subsets, so consumers must not add them to the primary totals.
Uncached input is retained only when the provider explicitly reports cache
misses; it is never computed by subtracting cached input. The companion
`payload.provider_usage` preserves bounded allowlisted provider fields and
capture/invalid-field facts rather than raw response bodies or diagnostics.

Retrieve committed usage through a fresh read-only result-access lease:

```python
from ebd.connections import RunAccessRequest, RunAccessOptions, HistoryReadRequest
from ebd.contracts import RunRef

request = RunAccessRequest(history=HistoryReadRequest(max_pages=20, max_events=1000))
access = (await engine.open_run_access(
    RunRef(engine.storage.store_id, saved_run_id), request, RunAccessOptions()
)).unwrap()
async with access:
    cursor = None
    while True:
        page = (await access.history.query(access.context, None, cursor, 100)).unwrap()
        for row in page.events:
            if row["event"]["kind"] == "model.outcome":
                response_usage = row["event"]["payload"]["usage"]
                # Persist/export row["receipt"]["event_id"] with response_usage.
        cursor = page.cursor
        if cursor is None:
            break
```

This access requires current host authority over the selected run; a saved run
reference does not revive execution. The terminal `agent.finished` payload and
`AgentResult.usage` contain known subtotals, completeness, unknown attempt IDs
and refs to the committed per-attempt usage activities. A subtotal stays null
until that counter has a real observation. Reconciliation and repeated history
reads reuse the original event identity: consumers deduplicate by store/event
ID rather than counting an acknowledgement or pagination repeat as another
API response. Earlier persisted records lacking normalized usage remain
historical unknowns, not evidence of zero consumption.

`SnapshotProposal` carries retained original/text/index bytes, provenance,
media type and extraction/normalization versions. The strict
`document_index/1` index contains its text digest, LF-excluding logical line
spans and optional physical page spans. Physical empty pages remain real units;
the one LF between pages is outside their spans. No parser is rerun on reads.
Ranges have `kind`, `start`, `end_exclusive` and use one-based half-open units.
Empty text has zero lines; a final LF adds no phantom line. Reads never clamp.
`DocumentSlice.continuation` is an opaque integrity-protected token;
`next_position` describes advancing unit/absolute byte position. Continue with
the same immutable ref and original range, current grants and a positive byte
budget. A codepoint that cannot fit returns its required byte count.

Bound grant selectors enforce byte/document ranges, per-read/publication caps,
media and checkpoint formats inside the low-level Store too. They cannot be
expanded by calling a raw facade with a result-access context. Actual state,
artifact, slice, checkpoint, status and history read bytes consume the shared
`storage_read_bytes` ledger. Every artifact chunk checks current selectors and
remaining lineage quota; opening another handle cannot reset those limits.

Caps are 8 MiB original/artifact, 4 MiB text, 1 MiB index, 64 KiB provenance,
256 KiB manifest and 64 KiB returned text with at most 200 lines/10 pages.
These byte limits do not promise a peak-memory bound. Checkpoints use the
strict `engine_checkpoint/1` envelope with run identity, schema versions and
JSON payload. Provider/runtime semantics and safe resume positions belong to
the runtime; a saved checkpoint never recreates live authority.

The active durability profile verifies DELETE journal, synchronous EXTRA and
foreign keys on startup. Database schema/checksum/profile disagreement is
rejected. WAL and automatic migrations are not enabled. Files are synced,
sealed and renamed before READY metadata, publication event and receipt commit.
Composite child IDs and receipts are stable: sealed children can recover while
an incomplete parent remains interrupted. A complete sealed parent publishes
once. ABORTED/interrupted operations are never promoted. Reads reject missing,
changed or non-READY bytes and generated-path reparse/symlink escapes.

Files and SQLite have separate durability boundaries. Windows directory power
loss synchronization and hostile same-user path replacement are deployment
limits; SQLite/file primitives do not establish joint atomicity or an OS
sandbox. The profile exposes the actual linked SQLite version and directory
sync support. One Windows process-lifetime root lock prevents a second owner.

`await session.close(deadline)` stops admissions and drains owned writers. A
deadline error leaves the worker/root held until admitted operations settle;
call close again to finish draining. Python task cancellation is re-raised and
does not detach or cancel an admitted publisher. Reopen completes eligible
sealed publications or records interrupted nonpublication, preserving IDs.
Continuation/history tokens are private to an owner session and expire; after
reopen begin a fresh authorized read/query.

Real persistence and controlled fault checks:

```powershell
uv --cache-dir .uv-cache run --locked --offline pytest tests/storage -q
uv --cache-dir .uv-cache run --locked --offline pytest tests/integration/test_result_access.py -q
uv --cache-dir .uv-cache run --locked --offline pytest tests/integration/test_token_usage.py -q
```

The tests use actual SQLite and files for close/reopen, CAS/tombstones,
lost committed replies with final quota, immutable integrity, scoped denial,
observer status, Unicode/empty physical pages, fixed history watermarks,
composite/seal/rename/publication interruptions and cancellation/root ownership.
The result-access tests use actual Connections and Storage without invoking a
model. Token-usage integration uses controlled native provider HTTP responses,
the actual registered document.read subprocess, real Storage, paginated fresh
history and close/reopen. It checks complete/partial/missing/zero counts and
committed acknowledgement loss without external API calls. These controlled
checks complement the separate live baseline evidence.
