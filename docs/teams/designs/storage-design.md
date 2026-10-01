# Storage design proposal

Status: DRAFT for PM and joint interface review; design assignment completed,
implementation not authorized. Date: 2026-09-30 (America/Toronto).
Owner: Storage Team, chat `01a0f546-8fc3-76f0-84fe-ffde8c2c89e5`.
Revision: storage-design-r1, ready for PM review; frozen at contribution handoff.

This proposal follows the shared brief and all four team specifications.
It specifies persistence behavior; the shared Python types, package layout,
transport selection, dependency policy, and approval remain PM decisions.
Only Storage's design/status documents are changed. No credentials are read.

## 1. Recommended boundary

Use SQLite for scoped JSON state, mutation receipts, append-only events,
artifact publication metadata, immutable snapshots, and checkpoint metadata.
Use generated files beneath one configured local root for immutable bytes.
Consumers use bound Storage clients, never SQL or object paths. Connections
resolves non-secret settings and authority; Storage enforces every operation.

Storage does not execute models/tools, schedule research, interpret evidence,
infer run termination, or implement runtime resumption. A saved event is an
application audit record, not proof of exactly-once external execution or
cryptographic tamper resistance. Normal recording is automatic at the owning
module's hooks. Recorder reads/appends do not recursively create activity.

The first implementation can use the Python 3.11 standard library for the
persistence core (`sqlite3`, JSON, hashing, filesystem operations). Any schema
validator, async facade, transport adapter, or stronger Windows path/durability
support needs PM review before dependency changes. These are design choices,
not a claim that an implementation or installed runtime has been validated.

## 2. Shared types and scope authority

Connections leads `ExecutionContext`, `ScopeRef`, and immutable effective
`StorageGrant` definitions; PM places approved definitions in one shared
contract package. Storage leads receipts, references, event persistence,
snapshot manifests/ranges and errors. Other packages import these types.

| Type | Proposed exact meaning |
| --- | --- |
| `ScopeRef` | Tagged `run` plus `run_id`, or `shared` plus registered `scope_id`. No free-form scope grants. |
| `StorageGrant` | Trusted binding authority naming store instance, principal, scope selectors, operations, optional object selectors, expiry and resource limits. |
| `ExecutionContext` | `run_id`, nullable `agent_id`, `action_id`, nullable `attempt_id`, nullable `parent_action_id`, nullable `parent_run_id`, `correlation_id`, portable UTC deadline, live cancellation handle and nonserializable bound authority. Trusted persistence mode is `normal` or `record_cleanup`, with a separate cleanup binding when applicable. |
| `ArtifactRef` / `SnapshotRef` / `CheckpointRef` | Store-instance-qualified opaque IDs with a type/version tag. No path, credential, or grant. |
| `JsonValue` | Strict JSON: finite numbers, strings, booleans, null, arrays and objects with unique string keys; bounded depth/bytes. No pickle or live Python handles. |
| `Version` | Positive 64-bit integer per `(scope, key)`; zero means never created. Deletes retain a tombstone and increment the version. |
| `OperationId` | Stable caller-generated ID for one proposed write; retained across delivery retries with unchanged request bytes/meaning. |

Authority is installed by a trusted binder, not reconstructed from tool JSON.
Storage checks issuer/store identity, expiry, operation, scope, object selection,
deadline and cancellation. A caller cannot enlarge grants by changing context
IDs. Context metadata and authority must match the binding. New run scopes are
provisioned only by the trusted run/binding path, not by `put` or `get`.

Core operations are `state.read`, `state.commit`, `artifact.read`,
`artifact.put`, `snapshot.read`, `snapshot.commit`, `checkpoint.read`,
`checkpoint.save`, `operation.status`, `events.read`, and trusted `events.append`. Recovery,
migration and provisioning are administrative operations. CLI workers receive
only snapshot operations needed by their tool, never general event append or
state/database access.

A child has its own run scope. Parent linkage/correlation does not grant data
access. Reading a parent/shared scope requires an explicit attenuated grant;
child grants are bounded by the caller's delegation authority and destination
policy. Passing an artifact reference does not transfer read permission.
Grants are checked again on resume and on each history page. Revocation prevents
new operations; bytes already returned cannot be recalled.

Do authorization before disclosing object existence. An ungranted reference
returns `ACCESS_DENIED`; a granted but absent reference returns `NOT_FOUND`.
State keys and display filenames are data, never file paths. Initial limits
proposed for review: keys <=256 UTF-8 bytes, state values <=1 MiB, event JSON
<=64 KiB, checkpoint JSON <=4 MiB, metadata <=16 KiB, depth <=32. Binder limits
may reduce these. Oversized content uses artifacts instead of event payloads.

This is interface enforcement for trusted local components. Python and CLI
processes running as the same user are not isolated from that user's filesystem
by this API. Store directory permissions and registered trusted commands are
part of deployment; hostile executable sandboxing is a separate decision.

## 3. Proposed public API and results

All calls below are async and receive the shared trusted `ExecutionContext`.
SQLite work is serialized through an owned worker; no synchronous disk operation
blocks the model loop. SQLite connections remain on their owning thread.
Signatures are documentation, not runtime source or final package names.

Every operation returns `Result[T]`: exactly one of `Ok(value: T)` or
`Err(error: StorageError)`. Expected persistence failures are typed results.
Cancellation before admission returns `CANCELLED/not_committed`. For an admitted
write, a known abort requires a durably saved ABORTED disposition before returning
`not_committed`; recovery never promotes that disposition. Once sealed/final
publication is admitted, finish the owned commit if possible or return
pending/unknown, rather than assert rollback. Cancellation/deadline arriving
after commit cannot convert a durable write into a rolled-back result. A lost
reply or interruption during commit has `commit_state=unknown`; query/retry the
same ID to resolve it. No Storage method retries an external model/tool call.

| Signature | Successful result and semantics |
| --- | --- |
| `StateStore.get(context, scope: ScopeRef, key: str) -> Result[StateLookup]` | `Present(value, version, last_commit_ref)` or `Missing(version=0 or tombstone_version)`. Missing is a typed ordinary lookup result. |
| `StateStore.get_version(context, scope: ScopeRef, key: str, version: Version) -> Result[StateLookup]` | Read an immutable permitted revision/tombstone for exact context restoration. Absent authorized revision is `NOT_FOUND`; latest value is never substituted. |
| `StateStore.commit(context, operation_id: OperationId, mutations: tuple[StateMutation, ...], activity: ActivityAnnotation) -> Result[StateCommitReceipt]` | One SQLite transaction changes all keys, records generated `state.committed`, and stores the operation receipt; returns mutation versions, event receipt and operation ID. |
| `ArtifactStore.put(context, operation_id: OperationId, scope: ScopeRef, content: ArtifactContent, metadata: ArtifactMetadata) -> Result[ArtifactReceipt]` | `ArtifactContent` supplies expected byte length/SHA-256 and an async byte source. Stream within granted limits, verify declared content, acknowledge only READY bytes plus committed event. Receipt includes ref, size, SHA-256, media type and event receipt. |
| `ArtifactStore.open(context, artifact_ref: ArtifactRef, byte_range: ByteRange, max_bytes: int) -> Result[ArtifactRead]` | Bounded async read handle with actual half-open byte range, size/digest/media metadata. Handle enforces its total allowance and must be closed. No raw path. |
| `SnapshotStore.commit(context, operation_id: OperationId, scope: ScopeRef, proposal: SnapshotProposal) -> Result[SnapshotReceipt]` | Stage raw/text/index/manifest as immutable objects, then atomically publish snapshot metadata and `snapshot.committed` in SQLite. Return ready snapshot/associated artifact refs and event receipt. |
| `SnapshotStore.read(context, snapshot_ref: SnapshotRef, range: DocumentRange, max_text_bytes: int, continuation: str or null = null) -> Result[DocumentSlice]` | Read immutable saved extraction; no network/refetch. Continuation resumes within the same snapshot/range. Return exact locators/ranges, bounded UTF-8 text and continuation information. |
| `CheckpointStore.save(context, operation_id: OperationId, scope: ScopeRef, checkpoint: CheckpointEnvelope) -> Result[CheckpointReceipt]` | Publish immutable versioned checkpoint and its event. No mutable current-checkpoint pointer unless caller explicitly CAS-writes one through StateStore. |
| `CheckpointStore.load(context, checkpoint_ref: CheckpointRef, accepted_formats: tuple[FormatVersion, ...]) -> Result[CheckpointEnvelope]` | Enforce permission/readiness/digest and compatibility; return original envelope without executing or interpreting it. |
| `ActivityRecorder.append(context, event: ExecutionEvent) -> Result[EventReceipt]` | Validate producer, identity, references, event version and deduplication; acknowledge after SQLite commit. |
| `ActivityReader.query(context, filters: ActivityFilters, cursor: str or null, limit: int) -> Result[ActivityPage]` | Stable sequence pagination of permitted records, with high-water mark and next cursor. |
| `OperationStore.status(context, operation_id: OperationId) -> Result[OperationStatus]` | Reauthorize original scope/operation/origin; return pending phase, committed original receipt, interrupted disposition or unknown availability. No external action status is inferred. |
| `StorageSession.close(deadline: UTCInstant) -> Result[CloseReceipt]` | Stop new calls, finish admitted commits within deadline, close owned readers/writer and report incomplete operations. Closing a borrowed binding does not close the shared store. |

Shutdown order: Connections stops new executions, owners cancel/drain operations
and finish terminal recording grace, then request Storage close. Storage close
rejects later new admissions; it must not run ahead of required terminal hooks.
Lock/queue/admission budgets are bounded, but OS disk synchronization can outlast
a deadline. If a writer is still inside an uninterruptible commit, return a typed
pending-close failure and retain owner/lock/resources until it resolves; do not
detach the write and release the root to another owner. No hard real-time disk
latency guarantee is made.

`StateMutation` is `{scope, key, kind: put|delete, expected_version, value?}`.
`expected_version` is required; zero only creates a never-seen key. Duplicate
keys within a batch are invalid. Delete of a never-seen/already deleted key is
`INVALID_DATA`; recreation must expect the retained tombstone version. A batch
is bounded to 100 mutations/4 MiB. A conflict rolls back the whole batch and
returns current versions only for keys the caller may read. No force-write
escape hatch is exposed to agents.

`ActivityAnnotation` contains safe cause/reference/optional application metadata;
the caller cannot choose another producer or omit the commit event. Storage
generates authoritative versions/digests/reference fields. Referenced objects
must belong to this store, be ready and be permitted. A state batch can span
granted scopes in this database; its event visibility requires event access
to every involved scope. Cross-database/file/state atomic batches are excluded.

`EventReceipt = {event_id, recorded_seq, recorded_at, duplicate}`.
`StateCommitReceipt = {operation_id, mutation_versions, event_receipt, duplicate}`.
Artifact/snapshot/checkpoint receipts also include their operation ID and
publication receipt. `recorded_seq` is a store-wide monotonic integer with
possible gaps, not a count or timestamp. `recorded_at` is Storage's UTC time;
producer `occurred_at` remains descriptive.

Remaining result schemas are proposed as follows:

| Value | Required fields |
| --- | --- |
| `ArtifactReceipt` | `operation_id, artifact_ref, scope, byte_length, sha256, media_type, event_receipt, duplicate`. Safe metadata remains queryable through the authorized read handle. |
| `SnapshotReceipt` | `operation_id, snapshot_ref, manifest_ref, raw_ref, text_ref, index_ref, component_digests, extraction_format_version, line_count, page_count_or_null, event_receipt, duplicate`. |
| `CheckpointReceipt` | `operation_id, checkpoint_ref, payload_ref, sha256, byte_length, envelope_format_version, event_receipt, duplicate`. |
| `OperationStatus` | `operation_id, state: pending|committed|aborted|interrupted, phase, commit_state, original_receipt_or_null, safe_disposition_or_null`. Unavailable status returns an error with unknown commitment. |
| `ByteRange` | Zero-based `{start, end_exclusive}` within stored byte length; empty range allowed, never silently clamp invalid offsets. |
| `ArtifactMetadata` | Required registered/syntactically valid `media_type`; optional display filename and bounded strict-JSON application metadata. Content descriptor supplies required SHA-256/length. |
| `CloseReceipt` | `closed:true, completed_operation_ids, interrupted_operation_ids`; pending uninterruptible close returns typed error with owner still held. |

`ArtifactRead.read(max_bytes: int) -> Result[ByteChunk]` and
`ArtifactRead.close() -> Result[Unit]` are async; close is idempotent.
`ByteChunk={bytes,eof,next_absolute_offset}` with positive requested read size
and aggregate allowance <=the originally opened byte range/budget. Each read
checks deadline/cancellation and current authorization; denied/expired/error
handles stop and must be closed. Verify stored length/digest before releasing
content and detect mid-stream I/O/truncation faults; already delivered prefixes
cannot be recalled. Such failure is a partial failed read, never a successfully
verified complete artifact. Consumers require successful EOF for completion.
Handle ownership does not keep a database transaction open while streaming.

Trusted administrative API, unavailable to agent/worker bindings:
`StorageSession.open(settings: ResolvedStorageSettings, issuer: TrustedIssuer)
-> Result[StorageSession]` obtains the root lock, validates schema/runtime and
recovers before admission. `StorageAdmin.provision_run(admin_context,
descriptor: RunDescriptor) -> Result[ScopeRef]` registers the run/parent facts
and run scope with stable identity; it does not grant callers access by itself.
Shared scopes are explicitly provisioned/registered through that administrative
boundary. Connections installs bounded grants independently.

## 4. Error and retry contract

`StorageError = {code, safe_message, operation_id?, event_id?, action_id?,
attempt_id?, retryable_delivery: bool, commit_state: not_committed|committed|
unknown|not_applicable, details}`. Details are bounded/sanitized and never
contain credentials, authentication headers, unfiltered stderr or internal
absolute paths. Transport errors preserve causal IDs without raw exception text.

| Code | Meaning / caller response |
| --- | --- |
| `ACCESS_DENIED` | Grant absent, expired, wrong scope/object/op or forged context. No existence disclosure or automatic escalation. |
| `NOT_FOUND` | Authorized artifact/snapshot/checkpoint absent. `get` instead returns `Missing`. |
| `INVALID_DATA` / `LIMIT_EXCEEDED` / `UNSUPPORTED_RANGE` | Bad JSON, schema/reference/range or resource limit; page mapping absent uses `UNSUPPORTED_RANGE`. No partial public mutation. |
| `VERSION_CONFLICT` | CAS mismatch; caller rereads and decides a new operation, never blind overwrite. |
| `IDEMPOTENCY_CONFLICT` | Existing event/operation ID with different canonical content, origin or target; no overwrite. |
| `INCOMPLETE_ARTIFACT` | Reserved/staged/sealed object is not published. No partial bytes. |
| `INTEGRITY_ERROR` | Ready object's size/digest/path verification failed; stop read and flag repair. |
| `INCOMPATIBLE_SCHEMA` / `INCOMPATIBLE_CHECKPOINT` | Unsupported storage/wire/event/checkpoint format; no silent conversion. |
| `STORAGE_BUSY` / `OPERATION_PENDING` | Bounded lock/queue wait exhausted, or the same admitted write is pending; query status or retry delivery with the same stable ID. |
| `STORAGE_UNAVAILABLE` | Disk-full, permissions, disconnected volume or I/O failure; preserve commit uncertainty. |
| `DEADLINE_EXCEEDED` / `CANCELLED` | No new work after limit; admitted commit may still finish. |
| `INVALID_CURSOR` / `SESSION_CLOSED` | Invalid/expired cursor or closed owner. |

Writes deduplicate by `(store_id, operation_id)` and submitted events by
`event_id`. Compare canonical validated request content, principal, scopes and
execution identities; Storage computes the fingerprint. JSON canonicalization
has a versioned deterministic UTF-8 serializer (sorted keys, no nonfinite
numbers, no duplicate keys); hashing alone does not define semantic equality.
Content descriptors (expected digest/length) are part of the request fingerprint.
Committed delivery retries do not consume a supplied stream; caller must repeat
the same descriptor. New supplied bytes with a false unchanged descriptor are
not a new upload. For unknown-length streams use an internal staged upload and
finish with declared digest/length; seal verification precedes publication.
Operation lookup precedes re-reading/re-uploading committed content and CAS.

An identical committed submission returns the original refs/versions/sequence,
with `duplicate=true`. A pending write returns `OPERATION_PENDING` with its
phase/operation ID; `OperationStore.status` returns the complete typed status.
The original owner must finish, cancel or be recovered before another producer
can supply bytes. A reused ID cannot become a fresh fetch/model dispatch.
Idempotency records persist for the retained lifetime of their committed data.
Automatic pruning/GC is outside the first handoff.

Reads are safely repeatable against immutable content. `append` and committed
writes are safe delivery retries with the same ID; changing data after conflict
requires a new ID. Timeout alone never proves a write failed. Error `retryable`
means safe Storage delivery, not permission to replay the external action.

## 5. SQLite schema, versions and concurrency

One database contains these logical tables; column names/layout remain draft.

| Table | Keys and essential columns / invariant |
| --- | --- |
| `store_metadata`, `schema_migrations` | Store UUID, schema integer, canonicalization version; migration version/checksum/applied time. |
| `scopes`, `run_links` | Tagged scope identity; trusted run/agent/parent/correlation registration. Facts come from Connections, not Storage run-status decisions. |
| `state_entries` | PK `(scope_id, key)`, JSON or tombstone, current version, last commit event. |
| `state_revisions` | Immutable `(scope_id, key, version)` revisions/tombstones and commit event; permits precise historical state inspection. |
| `operations` | Unique operation ID, origin/request digest, reservation owner, phase, sealed content metadata, result/receipt. |
| `artifacts` | Unique opaque ID, scope, generated relative object key, phase, SHA-256, size, media type, safe metadata, commit event. |
| `snapshots` | Unique snapshot ID, scope, ready manifest/raw/text/index refs, extraction format/version, publication event. |
| `checkpoints` | Unique checkpoint ID, scope, payload artifact ref, runtime/adapter/format versions, publication event. |
| `events`, `event_scopes` | `recorded_seq INTEGER PRIMARY KEY AUTOINCREMENT`; unique event ID, canonical envelope/hash, trusted producer, action/attempt IDs, visibility scopes. Public API exposes insert/query only. |
| `action_attempts` | Derived intent/outcome sequence links; uniqueness for one canonical intent and one terminal outcome per action/attempt. Absence of outcome is incomplete. |

Indexes support `(run_id, recorded_seq)`, `(action_id, attempt_id,
recorded_seq)`, `(correlation_id, recorded_seq)`, `(scope_id, recorded_seq)` and
pending operation phase. Foreign keys prevent dangling committed refs. Tables
for goals, missions, scheduling and evidence judgments are deliberately absent.
Application metadata is caller-owned JSON.

Three independent version axes: database schema integer; shared wire/event
schema major version; per-checkpoint/extraction format version. Bootstrap is
schema 1. Run migrations under exclusive administrative admission after a
verified backup; use explicit transaction-controlled statements and record
checksum/version together. Reject newer unknown schemas and altered migration
checksums. No opportunistic schema change during an agent action. Checkpoint
migrations belong to Runtime, producing a new checkpoint/event, not mutation
of the old bytes. Additive shared fields require agreement; unknown major
versions fail explicitly.

Proposed baseline settings: local disk, foreign keys on every connection,
rollback journal `DELETE` plus `synchronous=EXTRA`; optional WAL plus
`synchronous=FULL` only on a verified patched linked SQLite version;
bounded writer queue and short `BEGIN IMMEDIATE` write transactions. Use one
process-lifetime storage-root owner with an exclusive local lock. It owns
migrations/recovery, writer and checkpoints; a second owner of this root returns
`STORAGE_BUSY`. Multiple bound runs/workers share that owner. Standalone launchers
use sequential root ownership, or an explicitly separate configured store; no
automatic second owner or independent snapshot directory. Multi-owner fencing
and authenticated attachment to an existing owner are deferred. Readers take
short snapshots, never remain open during model/tool waits. Busy waiting has
one total cap: min(5 seconds, remaining caller deadline), including queue wait;
internal retries never reset that budget.

Implementation must explicitly roll back the whole batch on any statement
failure; statement-level ABORT does not undo earlier successful statements.
Handle a busy COMMIT while retaining its active transaction within the same
budget, then resolve rollback/commit state. Never use `INSERT OR REPLACE` for
audit/deduplication rows or blanket IGNORE for validation. Lifecycle uniqueness
keys use non-null attempt IDs for dispatch families. [SQLite transaction rules](https://sqlite.org/lang_transaction.html),
[SQLite conflict handling](https://sqlite.org/lang_conflict.html)

For the Python 3.11 target, propose `isolation_level=None` with explicit
transaction statements, parameter-bound SQL values, and mapping
`sqlite_errorcode`/`sqlite_errorname`. Do not use `executescript` inside a pending
transaction because it can implicitly commit it. Report linked
`sqlite3.sqlite_version_info` at startup. [Python 3.11 sqlite3](https://docs.python.org/3.11/library/sqlite3.html)

SQLite documents one WAL writer, same-host shared-memory requirements,
checkpoint starvation by long readers, and a WAL-reset race fixed in 3.51.3
(2026-03-13), with backports 3.44.6 and 3.50.7. Verify the linked library rather
than infer it from Python's version. If not patched, fail explicitly requested WAL startup with an
actionable error; do not silently switch profiles. WAL FULL synchronizes commits;
NORMAL can lose acknowledged commits
after power loss. These are documented behavior, not measured local guarantees.
[SQLite WAL documentation](https://sqlite.org/wal.html)

The baseline recommendation avoids a required runtime upgrade while keeping
concurrent WAL disabled. PM recorded the existing uv interpreter's linked SQLite
as 3.50.4 in `docs/teams/decisions.md`; Storage did not run that metadata check.
SQLite documents EXTRA's additional rollback-journal directory synchronization;
actual device/OS durability and returned settings still require implementation
verification. Baseline readers can block writes, so keep queries/transactions
short and retain the bounded busy policy. [SQLite synchronous profiles](https://sqlite.org/pragma.html#pragma_synchronous)

Backup/restore must cover database state and referenced immutable objects under
a quiescent publication barrier or consistent backup protocol; never copy only
the main live database and discard WAL. Initial administration can stop writers,
finish recovery, back up via the SQLite backup API, then copy referenced objects
and verify a manifest. `close` need not force a blocking truncation checkpoint
to claim a committed event persisted. Health checks report queue/busy/disk/format
errors without overwriting history.

## 6. Event envelope, ownership and automatic hooks

Submitted `ExecutionEvent` fields:

```text
schema_version: 1
event_id, kind, occurred_at (UTC RFC3339), run_id, correlation_id, action_id
agent_id: nullable only for explicit standalone/system contexts
attempt_id: required for model/tool/invocation intent and outcome; otherwise nullable
parent_action_id, parent_run_id: nullable for roots; populated for child linkage
producer: runtime | connections | storage | standalone_driver
status: intent | succeeded | failed | timed_out | cancelled | rejected | observed
input_refs, output_refs: ordered typed references
payload: bounded kind-specific JSON
application_metadata: optional caller-owned JSON
```

Storage adds sequence/recording time; caller cannot supply them. Producer is
bound trusted authority, not a worker-selected string. A logical `action_id`
survives retries; each actual dispatch gets a fresh `attempt_id`. `event_id`
identifies a record, not an action. The root run action owns run start/finish;
`agent.started` is its accepted/start intent boundary and `agent.finished` is
its terminal outcome.
Storage commit events reuse causal action/attempt identities, while `operation_id`
distinguishes the storage write. Event time never determines order.

| Canonical proposed event kind | Producer / payload |
| --- | --- |
| `agent.started`, `agent.finished` | Runtime: definition/version, bindings, input/output refs; final runtime status and known/unknown usage. |
| `context.assembled` | Runtime: ordered source refs/state versions, selected input artifacts, size/count estimation method. |
| `model.intent`, `model.outcome` | Runtime: model config/adapter/request refs and effective limits; response/continuation refs, elapsed monotonic duration, usage/error and outcome. |
| `tool.intent`, `tool.outcome` | Runtime around ToolExecutor: tool/schema/version, permitted input, limits; structured exit/status/diagnostic/output refs. |
| `validation.outcome`, `repair.intent`, `repair.outcome` | Runtime: output schema/rule and bounded sanitized error/repair references. Any model repair also records its distinct model attempt. |
| `execution.limit_reached`, `execution.cancel_requested` | Runtime: decision/reason and affected action; cancellation request alone is not a terminal outcome. |
| `binding.resolved`, `binding.rejected` | Connections: non-secret binding identity/version and effective permission references or safe failure. |
| `invocation.intent`, `invocation.outcome` | Connections: parent action/attempt, preallocated child run ID, destination definition, permitted input/result refs and outcome. |
| `state.committed` | Storage in state transaction: operation ID, keys, old/new versions, revision references. |
| `artifact.committed`, `snapshot.committed`, `checkpoint.saved` | Storage at publication transaction: immutable refs/digests/format/size; no content copy into event JSON. |
| `storage.recovery_observed`, `artifact.unavailable` | Storage: recovered/interrupted/integrity disposition; never invent external action termination. |
| `event.correction` | Original authorized owner: target event and correction reason/data; prior event stays immutable. |

Connections' invocation intent is the parent dispatch boundary; the child's
`agent.started` is a separate child execution fact. Runtime owns child terminal
status; Connections records the parent call's observation. These are distinct
records, with no competing producer for either. A child result must be published
into a scope the parent can read or explicitly granted; linkage alone is not
enough. Standalone trusted launcher records `tool.intent/outcome` as
`standalone_driver`, with a real new run ID and null agent ID, when no Container
owns the call. Worker and ToolExecutor do not independently duplicate records.

Intent/outcome references and payload rules are validated by kind. Intent and
terminal outcome uniqueness is `(run_id, action_id, attempt_id, family, phase)`.
This lifecycle uniqueness applies to model/tool/invocation/repair families;
agent start/finish have their own run-action boundary uniqueness. A
`validation.outcome` has a unique validation ID and requires no missing
`validation.intent`; observations/binding/storage events have kind-specific keys.
Storage publication uniqueness instead includes operation ID and event kind,
so several artifacts within one tool attempt remain distinct.
Dispatch/repair outcome requires its committed intent; agent finish requires
agent start. Corrections do not replace a terminal
row or silently change a run-status projection. Outcome payload has duration,
structured error/status and usage fields when known; missing usage is null plus
availability metadata, never zero by assumption.

Before external dispatch, the owner must receive a committed intent receipt.
If that fails, do not dispatch. After return, publish permitted outputs, then
append the outcome. If publication/outcome fails, owner returns a structured
`RecordingFailure` carrying action/attempt, known execution outcome if any,
available refs, failed storage operation and commit uncertainty. This failure
cannot become fully recorded success. Owner may retry *recording* with the same
event ID; it must not replay the tool/model merely to reconstruct an outcome.
After an unrecorded outcome, stop further external dispatch until recording is
resolved or the run terminates with the recording failure.

Cancellation/deadline does not itself suppress the terminal recording hook.
Connections supplies a preauthorized cleanup grant for one run/action/attempt;
the owner activates it against a committed intent receipt. The trusted cleanup
context retains causal IDs and sets `persistence_mode=record_cleanup` plus its
separate grant/deadline. Proposed deadline is min(activation UTC time + 5 seconds,
original action deadline + 5 seconds, session shutdown deadline). Grant expiry
is independently set for that cleanup window; explicit revocation still denies
access. Workers cannot create/activate/extend it. Normal execution cancellation
is ignored only for those cleanup Storage operations; the cleanup token has its
own cancellation/shutdown signal.

Allowed cleanup writes are output/diagnostic artifact publication within the
original attempt's byte/count caps (including an output produced just before
cancellation but not yet admitted to `put`), same-ID terminal event append and
operation status resolution. They cannot change arbitrary state, create a new
attempt, checkpoint/resume, commit a newly dispatched fetch or call models/tools.
Storage validates the bound token/intent/scope/IDs/effective persistence deadline;
it does not secretly clear ordinary cancelled contexts. Lifecycle-only run
termination cleanup uses its committed agent start receipt. This shared-context
extension needs joint approval. Exhaustion returns recording failure/incomplete
history and leaves admitted write commitment explicitly pending/unknown.

An intent without outcome is `incomplete` as a history projection: it can mean
no dispatch, running, or returned with failed/lost recording. Recovery does not
label it failed or automatically resume/retry. A pending event cannot log its
own logging error if persistence is unavailable; return it to the caller and
record a later authorized diagnostic/correction once storage is available.

## 7. Artifact publication and interrupted-write recovery

Artifact IDs/object names are generated by Storage. Display filenames remain
metadata. Configured root is resolved once by trusted configuration and checked
on every open/create against traversal, symlinks and Windows reparse/junction
escapes. Reject alternate streams/device/path syntax in any accepted path
component; workers never supply components. Stage and object directories must
be on the same local volume. Root is owned/private to trusted deployment;
ordinary path resolution alone is not proof against hostile same-user path races.
The implementation must verify opened handles/real paths or use platform support,
and fail closed if that containment check cannot be guaranteed.

Publication phases are internal and not readable:

1. Reserve `operation_id` and opaque object ID in a short SQLite transaction:
   `RESERVED`, owner token, scope and request fingerprint. No public commit event.
2. Stream to an exclusive generated staging file with bounded size/deadline,
   SHA-256 and byte count. Flush userspace buffers, then `fsync` the file.
3. Commit `SEALED` with the final expected digest/length in SQLite. An unsealed
   file's hash is insufficient to establish completeness: partial bytes hash too.
4. Move the sealed closed file to its generated final name on the same volume.
   Verify destination/size/digest. Flush directory metadata when a supported,
   tested platform primitive exists. No overwrite of another artifact.
5. One SQLite transaction sets READY, inserts the canonical `artifact.committed`
   event and saves its receipt. Deterministic event ID derives from the storage
   operation/phase. Acknowledge only after this transaction commits.

Python documents buffer flush before file `fsync`; `os.replace` can fail across
filesystems. The protocol uses same-volume rename for visibility and a separate
SQLite publication transaction. Windows directory-entry survival after abrupt
power loss is unverified here; do not claim that file plus database is one
atomic/durable unit. Reads recheck publication and integrity, and surface missing
or damaged acknowledged files. [Python filesystem documentation](https://docs.python.org/3.11/library/os.html)

Recovery runs at startup after obtaining the exclusive process-lifetime root
owner lock and before serving writes. No other owner can still finalize a stage.
Do not use age, PID or elapsed lease alone to declare a live writer dead. Active
uploads in the current owner are not reclaimed by maintenance. Staging files
hold no database transaction while streaming. A Windows nonblocking file lock
is a possible adapter and must be verified on the actual filesystem; multi-owner
epochs/fencing are deferred. [Python Windows locking](https://docs.python.org/3.11/library/msvcrt.html#msvcrt.locking)

| Interrupted state | Recovery |
| --- | --- |
| RESERVED / unsealed stage | Mark interrupted/quarantine; never infer complete content or publish. Re-delivery can report the operation; a new upload needs explicit caller decision/new operation. |
| SEALED + complete stage | Verify against persisted seal, finalize rename then READY/event transaction. |
| SEALED + complete final file | Verify against seal; finish READY/event transaction once. Lost acknowledgment retry returns original receipt. |
| SEALED + missing/mismatched bytes | Mark interrupted/integrity failure; no public readable artifact. |
| READY + valid final file | Preserve ready object; no extra commit event. |
| READY + missing/mismatched file | Mark availability fault and append `artifact.unavailable`; return `INTEGRITY_ERROR`, preserve original history. |
| Unindexed generated file | Quarantine for inspection; bounded administrative cleanup only under recovery lock. |

Snapshot commit first persists its parent reservation, complete validated
proposal descriptor/component digests and preallocated snapshot/manifest IDs.
Child artifact operation IDs derive deterministically from parent operation ID
plus component role (`raw`, `text`, `index`, `manifest`); existing ready children
are reused on delivery/recovery, never duplicated. Checkpoint save uses the same
parent/child scheme with role `payload`. Unknown streams cannot seal the parent
descriptor until expected component lengths/digests are fixed and validated.

Snapshot commit uploads raw response bytes, canonical text and location index
through this protocol, then publishes an immutable manifest and snapshot row.
The final snapshot row plus `snapshot.committed` plus operation receipt commit
together. Individual constituent artifact events can exist without a published
snapshot; they do not make it readable as a document. No snapshot is successful
until every referenced object is READY and verified. Artifacts left by a failed
snapshot are retained as orphans for explicit administrative retention review.
No silent rollback claim is made for already durable constituent files.
Root recovery finishes a composite only if its persisted parent descriptor is
sealed, all exact child refs are ready/verified and it was not durably ABORTED.
It commits the preallocated snapshot/checkpoint row, canonical publication event
and original operation receipt once. Otherwise mark parent interrupted and keep
children as recorded orphans; the operation cannot remain pending indefinitely.
No missing component is reconstructed through external retrieval. A lost reply
after parent commit resolves through `OperationStore.status`/same-ID retry.

## 8. Snapshot provenance and bounded document reads

`SnapshotProposal` includes exactly one retrieval's raw bytes and derived
normalized UTF-8 text, extraction identity/version/config reference, location
index and sanitized provenance. Toolset owns extraction and semantic detection
of login/challenge/empty/unsupported pages; Storage validates structure, hashes,
limits and references, not article correctness. Refreshed retrievals get new
snapshot IDs even if bytes match; no refetch on reads and no URL-key overwrite.

Manifest format `document_snapshot/1` includes:

- Snapshot ID/scope, raw/text/index artifact refs and digests/sizes.
- Requested/final URL (credential-bearing URLs rejected or sanitized before
  persistence), retrieval UTC time, status/media/encoding, selected safe response
  headers. Never cookies, authorization or unrestricted header dumps.
- Search provenance reference if applicable; snippets remain discovery metadata.
- Extractor name/version/options reference, normalization version, detected
  content limitations, line count and optional PDF page map.
- Raw content meaning: bytes delivered after HTTP content decoding by the selected
  client, plus available `Content-Encoding` metadata; not a fabricated exact
  TLS/wire capture. Raw and extraction must come from that same retrieval.

Canonical text is UTF-8 without BOM; line endings are LF. Define logical lines
by splitting canonical text on LF; a final LF does not create a phantom last
line. Empty text has zero lines. No implicit Unicode normalization is added.
Index stores UTF-8 byte offsets and ends for each line, with LF delimiters
outside line bodies. Toolset freezes normalization/extraction before publication;
Storage verifies monotonic offsets, UTF-8 boundaries, counts and coverage.
For PDF, page numbering is one-based physical page order; preserve empty pages
and page labels separately. Missing page mapping yields `UNSUPPORTED_RANGE`,
never invented page references.

`DocumentRange` is tagged `lines{start, end_exclusive}` or
`pages{start, end_exclusive}`. Starts are one-based and end-exclusive; valid
nonempty ranges stay inside the snapshot's available counts plus one. Empty
documents permit `{start:1,end_exclusive:1}` only. No mixing line/page units.
Initial read budget is positive and <=64 KiB text, further reduced by grants.
Requests exceeding 200 lines or 10 pages are `LIMIT_EXCEEDED`; callers request
the next bounded range or use continuation within an oversized bounded range.
Byte counts always count UTF-8, not Python characters.

`DocumentSlice` contains snapshot/extraction versions, requested and actually
returned ranges, ordered spans with absolute line/page and zero-based byte
offsets, text, `has_more_in_requested_range`, `has_more_in_document`,
`truncated`, and `next_position`. Prefer complete lines. If one line/page is
larger than the budget, return a UTF-8-boundary partial span and an opaque next
position for its byte offset; never loop forever on an oversized first line.
Byte budget constrains text plus a separate bounded response-envelope overhead.
Continuation position is snapshot/range/grant/format-bound, not authority;
submit it through the next read's `continuation` parameter with the same range.
The new output budget may be reduced within the grant without changing position.
Default line citations remain stable; partial spans carry byte ranges explicitly.

Reliable human locators are descriptive `snapshot-ref + line N` or physical
`page N + line/byte span`. Programmatic locators always carry the immutable
snapshot ID/extraction version and range units. Optional `document.find` and
chunks require a later contract; they do not change saved line/page references.

## 9. CLI access: transport-independent scoped contract

Storage/Toolset/Connections must agree one adapter. The worker never receives a
database filename, artifact root, model credential, unrestricted grant, or a
second durable snapshot store. This design separates operations from transport.

Allowed worker operations for the initial tools are `snapshot.commit` for fetch
and `snapshot.read` for document.read. `web.search` needs no storage capability
unless its bounded output is persisted by the trusted action owner. The trusted
launcher binds store/scope/run/action/attempt and granted object selectors.
Worker-visible capability cannot select another run/scope or append events.

Request/response logical envelope (both pipes and broker use strict UTF-8 JSON;
batch handoff maps the same fields to a trusted call):

```text
request = {schema_version:1, request_id, operation, operation_id?, body}
response = {schema_version:1, request_id, ok,
            result?: SnapshotReceipt|DocumentSlice|OperationStatus,
            error?: StorageError}
```

Transport/session binding supplies authority and causal context; worker values
cannot replace them. Unknown versions/fields/operations fail validation. Write
`operation_id` is derived/assigned by the trusted launcher for that action; a
worker's delivery retry uses the same assigned ID. `request_id` only correlates
messages and does not replace persistent idempotency.

For an interactive proxy, `snapshot.commit` is a bounded upload protocol:
`snapshot.begin` -> `upload.append{upload_id,offset,base64_bytes}` ->
`snapshot.finish{upload_id,provenance,extraction,index,component_seals}`. An
upload ID selects only its granted reservation; exact offset/chunk hash verifies
delivery repeats, rejects overlaps/gaps, and never grants arbitrary file access.
The final receipt is the sole publication acknowledgment. `operation.status`
resolves a lost acknowledgment but cannot infer external fetch success.
Uploads are staged inside Storage, not as worker-chosen file paths. Proposed
frame cap 1 MiB, decoded chunk cap 256 KiB, total raw/text caps 16 MiB/4 MiB,
index <=4 MiB, one active upload per tool attempt; all policy configurable
downward. Disconnect/cancellation revokes new requests and leaves admitted
commit resolution/recovery to Storage.

The three candidate transports and Storage recommendation are below for joint
review. Public CLI stdout remains exactly one final JSON tool result;
diagnostics remain stderr. Storage traffic may never share stdout as unframed
extra JSON messages. The platform-owned standalone launcher is part of every
option: it constructs an authorized standalone run/context, records intent,
uses the same ToolExecutor and Storage, records outcome, then prints one result.
If the configured root has another owner, return `STORAGE_BUSY` before dispatch;
do not create a new hidden store to make the command appear successful.
The public launcher requires valid bindings. An internal worker rejects ordinary
public requests without its explicit worker envelope; that envelope alone is
not Storage authority and cannot grant persistence or additional reads.
Default standalone access is a fresh run scope; reading a saved snapshot needs
an explicit authorized configured scope, never inferred from a supplied ref.

### Transport comparison and Storage recommendation

Recommend launcher-mediated batch handoff for the initial three tools, subject
to PM/CLI/Connections agreement. The worker returns a bounded fetch proposal;
ToolExecutor commits it through the bound Storage interface before returning
public success. For reads, the parent supplies only a bounded authorized slice.
This solves the process boundary through explicit serialization/mediation,
rather than pretending a Python object exists in the subprocess. It supports
the currently fixed operations; an interactive worker needing additional reads
would require the scoped proxy alternative. No transport is selected here.

| Dimension | Launcher batch handoff | Dedicated private pipes | Ephemeral loopback broker |
| --- | --- | --- | --- |
| Windows portability | Standard redirected stdin/stdout/stderr; no extra handle adapter. | Anonymous extra pipes need Windows handle inheritance; named pipes need a separate endpoint/security adapter. | Literal loopback TCP works across target platforms; choose framed JSON or separately reviewed HTTP. |
| Standalone | Trusted launcher owns the same root/session and ToolExecutor; no separate store. | Same launcher creates per-attempt channels and owns proxy lifetime. | Same launcher starts/binds broker and revokes it on shutdown. |
| Lifecycle/cancellation | One worker result; launcher owns postprocess commit resolution and cleanup. | Pump request/response plus stdout/stderr concurrently; close endpoints/abort pending frame on cancellation. | Bound listener/connections/request queues/timeouts; revoke token and close listener. |
| Transfer bounds | Larger final worker JSON and base64 copies; explicit per-stream and decoded caps. | Chunk frames and backpressure; never multiplex extra messages onto public stdout. | Same chunk protocol; additional socket/backpressure handling. |
| Authority | Parent-held bound grant, tool operation slot and requested ref/range; no bearer token. | Channel possession plus parent-bound grant; worker cannot select another scope. | Per-attempt token maps to parent-bound grant; authentication on every request. |
| Failures/recovery | Exit zero means proposal only; durable receipt required for success; loss resolves by operation ID. | Broken/truncated/oversized frames close capability; incomplete upload remains staged. | Disconnect/auth/request failures are explicit; no automatic external retry. |
| Setup complexity | Smallest initial integration; increased memory/wire overhead. | Native handle/ACL/lifecycle validation; supports interactive storage calls. | Listener/authentication/endpoint administration; supports non-Python clients. |

Internal envelope is distinguished from the final shared ToolResult:
`worker_request{schema_version:1,message_type,request_id,tool,input,context,
handoff}` and `worker_result{schema_version:1,message_type,request_id,tool,
status,snapshot_proposal?|read_observation?,observations,error?}`. Public input
cannot supply reserved `context`/`handoff` fields. ToolExecutor builds a fresh
request; it never merges agent JSON over trusted fields. Context contains safe
identifiers/deadline only; authority remains in the parent. Registered worker
stdout is internal protocol data, not a final user/model-visible ToolResult.

For fetch, proposal components are `raw_base64`, `text_utf8_base64`,
`index_utf8_base64`, declared component digests/lengths, extraction and safe
provenance. The parent validates request/tool IDs, exit/status, encoded/decoded
caps, strict UTF-8 and schema before `SnapshotStore.commit`. Storage computes
actual hashes and validates locations. ToolExecutor returns final snapshot ref,
digest/provenance/preview only after Storage's publication receipt. Storage
failure is a failed tool result with commit state; it is never converted into
fetch success because the network process exited zero. Intermediate raw stdout
must not be sent to the model or appended verbatim to ordinary diagnostics.

For read, ToolExecutor calls `SnapshotStore.read` with the public requested ref,
range/budget/continuation, then injects only that canonical slice into the worker.
It validates worker output against the supplied text/locators and preserves
Storage's canonical references. The worker cannot ask for more data in batch
mode. A forged internal envelope can transform only caller-supplied bytes; it
does not obtain the parent's bound Storage client.

Initial batch caps: raw 16 MiB, normalized UTF-8 4 MiB, index 4 MiB, other
metadata 256 KiB, internal stdout 64 MiB, internal stdin 1 MiB, stderr 64 KiB,
final ToolResult 512 KiB, read/preview text 64 KiB. Base64 of each binary component
uses `4*ceil(n/3)` bytes (combined component maxima about 32 MiB); encoded caps
are checked before decoding. The 64 MiB wire cap is not a peak-RAM guarantee:
buffers/parsed strings/extractors and copies add memory. Later acceptance must
measure memory/concurrency before raising these defaults. ToolExecutor pumps
all streams with byte counters and terminates on overflow; collecting everything
before checking a cap is insufficient. Python documents memory buffering in
`communicate` and the extra Windows handle-inheritance requirements for private
channels. [Python subprocess documentation](https://docs.python.org/3.11/library/subprocess.html)

If PM selects private pipes, use separate length-prefixed UTF-8 JSON channels,
one in-flight request initially, 1 MiB max frame and 256 KiB decoded upload
chunks. Truncated/oversized frames invalidate the channel. POSIX `pass_fds` does
not provide a Windows adapter; Windows requires an explicit inherited
`handle_list`, careful inheritable-handle closure and controlled process creation.
Alternatively Python's `AF_PIPE` listener can use authenticated byte messages;
use `send_bytes/recv_bytes(maxlength)`, never `recv`/pickle on worker input.
[Python multiprocessing connections](https://docs.python.org/3.11/library/multiprocessing.html)

A named-pipe design must supply a restricted user/logon ACL and reject remote
clients. Default named-pipe ACLs are insufficient for the proposed privacy;
Python's documented Listener interface does not expose every native setting.
[Microsoft named-pipe access controls](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights),
[Microsoft CreateNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea)

If PM selects loopback, bind literal `127.0.0.1` on an OS-assigned port, with a
fresh 256-bit token per attempt mapping to one attenuated grant/context. Deliver
endpoint/token only in trusted worker stdin, never argv/URLs/environment or
recorded tool inputs. Reject remote/non-authenticated/unknown-version requests;
bound connections, body/frame size, decoded bytes, upload count and lifetime.
Token expires at attempt completion/cancellation/deadline with cleanup only for
admitted commits. No worker delegation/refresh or persistent general service.

For every option, ToolExecutor passes an allowlisted environment with required
runtime variables (including Windows SystemRoot), not unrelated model secrets.
Storage retains publication/recovery/event ownership; ToolExecutor retains
process launching and transport pumping; Connections supplies grants/lifetime;
Container retains engine intent/outcome. Standalone ownership is the explicit
driver mode in section 6, or a shared Runtime-owned wrapper if PM chooses that
alternative. Exactly one owner emits the lifecycle, never both.

## 10. History pagination and checkpoint resumption

`ActivityFilters` accepts run IDs, action/attempt, correlation, kinds/status,
scope selector and optional descriptive time filters. Each selector is checked
against `events.read` grants. Return only records whose entire visibility set
is permitted. Event references do not permit underlying artifact reads. No
global total count or unrelated records leak through unauthorized filters.

First page captures `high_water_seq=max(committed sequence)` under one short
read transaction. Query ascending `last_seq < seq <= high_water_seq` with keyset
pagination; no OFFSET. Opaque integrity-protected cursor binds store/version,
filter digest, principal/grant fingerprint, last sequence, high-water sequence
and expiry (proposed 24 hours). Permission checks happen on every page;
permission/grant changes invalidate the cursor. Page max 500 events/1 MiB; no
live read transaction is held between pages. New events require a fresh query;
tailing explicitly starts after the last sequence. Cursor is not an access token.

`CheckpointEnvelope` contains format name/major/minor, runtime version,
definition/binding version refs, run identity, last fully recorded position,
ordered transcript and permitted input/output/state-version refs, opaque
provider continuation with provider/model/adapter format binding, and portable
deadline/limit/accounting state. No credentials, live resource handles, locks,
monotonic clock readings or cancellation objects. Large payload lives in an
artifact. Storage verifies JSON/envelope/reference integrity and size; Runtime
checks definition/adapter semantics and whether resumption is safe.

Storage load revalidates current grants, source refs and envelope format against
`accepted_formats`; those versions do not claim adapter compatibility. Runtime
checks adapter/provider/model continuation binding and semantic compatibility,
then rebinds credentials/resources and rebuilds local
timers from the remaining portable deadline. Expired deadline or unknown
external outcome stops automatic resume. Opaque provider data is retained only
if actually supplied/needed by that adapter, under the same confidential scope;
it is not a request for hidden reasoning. A checkpoint is never evidence that
an external side effect can safely be replayed. Runtime must claim exclusive
resumption of a run if resume is promised in the first handoff; a CAS state
record can support the claim, but Storage does not schedule or decide resume.

## 11. Proposed implementation stages and acceptance evidence

After user design approval and PM implementation assignment:

1. Shared approved schemas/errors/grants and bound client enforcement; store
   initialization/version gate and migration/inspection administration.
2. SQLite state CAS/revisions/operation receipts and append/query history.
3. Sealed filesystem artifacts, interruption recovery and snapshot publication.
4. Checkpoint persistence and selected CLI adapter/standalone launcher integration.
5. Container/Connections hooks, readable inspection, setup/uv commands and real
   integration/failure verification. PM owns dependencies and ignore policy.

| Meaningful acceptance case | Required evidence |
| --- | --- |
| Durable reopen | Real state/artifact/snapshot/checkpoint/event persists across close/reopen; saved bytes/digests and versions match. |
| Scope enforcement | A separate run cannot read guessed refs/keys/history; explicit grant permits only selected scope/operations. Child linkage grants nothing. |
| CAS + atomic audit | Concurrent expected-version writers yield one winner; event insertion failure rolls back state/revisions/receipt; tombstone prevents ABA. |
| Delivery retry | Same event/operation returns original receipt; different payload/origin under same ID is rejected. Lost ack does not duplicate bytes/events. |
| Dispatch gate | Failed real intent persistence prevents model/tool dispatch; failed outcome recording exposes incomplete action without replay. |
| Artifact interruption | Kill writer at reserve/write/seal/rename/publish boundaries; no unsealed/partial readable content; sealed complete writes recover with one event. |
| Integrity/path | Missing/altered READY bytes fail read; traversal/junction/reparse escape rejected; live upload not reclaimed by another session. |
| CLI/standalone | Real fetch preserves one-response raw+text, durable ref precedes success; another process performs bounded saved reads, including long line/page continuation. |
| Pagination | New appends cannot duplicate/skip fixed-high-water pages; unauthorized events/changed grants/cursor tampering fail. |
| Checkpoint compatibility | Unsupported adapter/format/expired grants/deadline fail; continuation round-trips without credentials or live handles. |
| Recording ownership | One canonical intent/outcome per actual attempt; storage commit events are distinct; inspection/appends generate no recursive records. |
| Contention/shutdown | Busy/full-disk/cancellation/lost reply return bounded typed failures; admitted commit is resolved rather than asserted rolled back. |

These checks are a plan, not executed tests. Final handoff must supply real
`uv run --locked ...` entry points after package names/commands are approved.
Do not substitute mock tool/model/persistence outputs. Configured API provider
checks belong to the later authorized Container integration; local vLLM/Qwen
live verification remains pending deployment on another accessible host.

## 12. Decisions requested from PM

1. Approve one shared context/grant/reference/event version and type owner;
   nullable agent identity only for explicit standalone/system contexts.
2. Reconcile one CLI transport and wire/resource limits with CLI/Connections;
   preserve the trusted standalone launcher and Storage commit ownership.
3. Confirm proposed event names, distinct parent invocation vs child lifecycle,
   strict intent acknowledgment and `RecordingFailure` shape with Container.
4. Confirm SQLite linked-version/WAL gate, local-root protection/durability
   profile, scope provisioning/recovery ownership and administration policy.
5. Confirm snapshot normalization/range/page mapping and the cap/unsupported
   behavior with Toolset; no claimed extraction semantics until agreed.
6. Choose retention/backup/cursor-key handling and package/dependency layout
   before implementation. Obtain the user's completed-design approval.

No proposal here has been represented as a jointly agreed shared contract.

## 13. Concrete contract examples and evidence

The following are illustrative design traces, not execution evidence. IDs are
placeholders and no external service identifiers or credentials are assumed.

1. A new run-scope `notes` key returns `Missing(version=0)`. Commit operation A
   with expected version 0 creates revision 1 plus one `state.committed` event.
   A concurrent expected-0 writer gets `VERSION_CONFLICT`. Re-delivering A returns
   its original version/event receipt, even if operation B later made revision 2.
   Delete expecting 2 creates tombstone 3; recreate expecting 0 conflicts,
   while recreate expecting 3 creates revision 4. `get_version(...,1)` still
   returns the original permitted content.
2. A fetch tool attempt has a committed `tool.intent` before its real subprocess
   starts. Worker returns original response bytes and extracted text as an
   intermediate proposal. Storage seals raw/text/index/manifest children and
   publishes the snapshot with its event/receipt. ToolExecutor returns that
   immutable ref; Container appends `tool.outcome`. If outcome append is lost,
   the history remains incomplete despite a committed snapshot. Inspecting its
   operation receipt does not authorize another fetch.
3. `read(snapshot_ref, lines{start:41,end_exclusive:61}, 65536)` asks for 20 lines
   from one saved extraction. A partial long line returns `next_position`;
   the next call passes the same range and that continuation. Unauthorized run
   receives `ACCESS_DENIED` without learning whether the ref exists. An updated
   URL produces another snapshot and leaves these locators unchanged.
4. An upload interrupted before SEALED is not published. If interrupted after
   durable seal and rename, startup verifies the persisted expected size/hash
   and commits READY once. If cancellation already durably marked ABORTED,
   recovery never publishes it. A lost acknowledgment is resolved by operation
   status; no remote side effect is reconstructed from a checkpoint.

Evidence checked on 2026-09-30:

| Primary evidence | What it establishes / limit |
| --- | --- |
| [SQLite WAL](https://sqlite.org/wal.html#walresetbug) | Current documented WAL race/version fixes and concurrency constraints; no local reproduction. Page reports update 2026-08-25. |
| [SQLite transactions](https://sqlite.org/lang_transaction.html), [conflicts](https://sqlite.org/lang_conflict.html), [pragmas](https://sqlite.org/pragma.html) | Transaction/error and synchronization semantics; proposed application behavior still unimplemented. |
| [Python 3.11 sqlite3](https://docs.python.org/3.11/library/sqlite3.html) | Target API/thread/explicit transaction behavior; no Storage runtime check. |
| [Python filesystem](https://docs.python.org/3.11/library/os.html), [Windows locks](https://docs.python.org/3.11/library/msvcrt.html) | Available sync/rename/locking primitives; Windows power-loss/containment/lock behavior untested here. |
| [Python subprocess](https://docs.python.org/3.11/library/subprocess.html), [connections](https://docs.python.org/3.11/library/multiprocessing.html) | Standard pipe/handle/message facilities; no transport implementation or trial. |
| [Microsoft pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights), [CreateNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea) | Native private/remote-client controls a pipe design must address; no Windows adapter verified. |
| Repository entry/shared/coordination/all sibling specs and CONTRIBUTING.md | Authorized design scope, ownership, shared environment and PM-only Git writer. |

Three independent read-only reviews covered durability/recovery, CLI transport,
and events/grants/API consistency. Their actionable findings are incorporated:
sealed completeness, composite parent/child recovery, cancellation commitment,
historical reads, continuation input, operation status, lifecycle uniqueness,
cleanup-only authority and shutdown order. Verification is source/spec review
and document consistency inspection only. No production code, dependency,
installation, database, credential or model/provider changes/trials were made.
