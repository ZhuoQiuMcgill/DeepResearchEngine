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
```

The tests use actual SQLite and files for close/reopen, CAS/tombstones,
lost committed replies with final quota, immutable integrity, scoped denial,
observer status, Unicode/empty physical pages, fixed history watermarks,
composite/seal/rename/publication interruptions and cancellation/root ownership.
The result-access tests use actual Connections and Storage without invoking a
model. These controlled checks complement the separate live baseline evidence.
