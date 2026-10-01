# Storage design aligned to platform contract v1

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../../team-start.md)
> and the [current usage guides](../../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

Status: complete owned design alignment for PM review; runtime implementation
is not authorized. Date: 2026-09-30 (America/Toronto).
Revision: `storage-design-r4-v1` (coordinated read-only observer authority).
Owner: Storage Team, chat `01a0f546-8fc3-76f0-84fe-ffde8c2c89e5`.

[platform-contract-v1.md](../platform-contract-v1.md) is the authority for shared
types, identity, receipts, producer ownership, mediation and resource limits.
This document supplies compatible persistence details. It supersedes r1's
alternative standalone producer, larger transfer limits and cleanup-write
proposal. PM owns shared types, dependencies and Git; current edits are only
this design and `docs/teams/reports/storage-status.md`. Future ownership is
`src/ebd/storage/` and matching tests after the authorized phase transition.

## 1. Boundary and shared vocabulary

SQLite stores scoped state and immutable revisions, operation receipts,
append-only activities, artifact publication metadata, snapshots and
checkpoints. Generated immutable files below one configured private local root
store bytes. Consumers use scoped protocols, not SQL or filesystem paths.
Connections is the composition root and issues live authority; Storage
validates it on operations and before publication. The configured root and
resolved non-secret settings come from Connections.

Storage owns one root lock, one serialized SQLite worker, migration/recovery
and its resources. It does not run models/tools, infer external outcomes,
schedule research, select goals or decide checkpoint resumption. References
identify objects and never grant access. Files and SQLite have separate
durability boundaries. Activity is application history, not cryptographic
tamper proof or a guarantee of exactly-once external execution.

Shared types are supplied by PM's common contract package, with Connections
owning allocation/binding and Storage supplying persistence schemas. There
are no duplicate context/grant definitions in module packages.

| Shared concept | Storage interpretation |
| --- | --- |
| `schema_version` | Integer 1, the sole wire/event compatibility major. Unknown majors/security fields are rejected. |
| Context metadata | `context_kind: agent|standalone_tool`, run/root/correlation IDs, nullable agent/definition ref, action/attempt, parent run/action/attempt, UTC deadline, depth/ancestry, binding/policy refs and bounded metadata. |
| Live context | Cancellation, reconstructed monotonic deadline, effective grants/revocation handle, shared lineage ledger and resource leases. No live handle is saved in JSON. |
| `ScopeRef` | Tagged `run{run_id}` or registered `shared{scope_id}`. Arbitrary strings cannot create authority. |
| Effective grant | Trusted store/principal/scope/operation/object selectors, lifetime/revocation and resource limits. JSON and saved descriptors cannot issue or restore it. |
| Typed reference | Store-qualified opaque artifact/snapshot/checkpoint ID plus type/format tag; no raw path or capability. |
| JSON | Finite numbers, unique string keys, strict UTF-8, depth <=32 and byte limits. No pickle or live Python objects. |
| State version | Positive signed 64-bit revision per scope/key; zero means never created. Tombstones retain monotonically increasing revisions. |

Definition/tool/extraction/continuation codec revisions and database schema
versions remain independent of the shared compatibility major.

Authorization precedes disclosure and deduplication. For originator delivery,
validate current issuer/store,
principal/context identity, scope/object selectors, operation, revocation/expiry,
deadline, valid lease and receipt visibility. Then inspect the same event/operation
ID and compare frozen origin/content. Return its existing committed receipt or
identical pending status without a fresh write reservation or consuming source
bytes. Only NEW admission checks remaining business-write quota, fresh-use
reservations, queue allowance and CAS. Exhausted write quota alone cannot deny
authorized receipt reconciliation; current receipt/status/read visibility and
finite delivery bounds still apply. No permission is revived and changed origin
cannot replay. Caller metadata cannot enlarge its bound grant.
Direct scope/operation denial returns `ACCESS_DENIED`. Opaque lookups are
constrained to granted visibility and do not expose another scope's data,
metadata, hashes or sequence; no-visible-object results are `NOT_FOUND`.
A guessed ref, correlation ID, parent linkage or application mission ID
conveys no authority. Histories require their own read grant.

Granted operation labels are state.read/state.commit, artifact.read/artifact.put,
snapshot.read/snapshot.commit, checkpoint.read/checkpoint.save, events.append,
events.status/events.read and operation.status. Historical state uses state.read
with its version selector. Exact status uses two closed trusted grant modes:
`originator` and `observer`; unknown modes are rejected, and request JSON cannot
select or change a mode. Originator authority retains the existing frozen
producer/caller and run/action/attempt restrictions, with separately authorized
delivery/write rights. Observer authority permits only `events.status` and/or
`operation.status` for its exact targets. Neither mode implies arbitrary history.
Provisioning/migration/recovery are trusted administrative rights, never worker
grants.

Connections' binder may install `mode=observer` on a fresh normal host access
binding. It checks the current host principal, policy, deadline, lease,
revocation/expiry and finite status/read limits. The grant selects the exact
target store, run and event IDs or operation IDs, permitted frozen target origin
(principal, producer/caller, scope and run/action/attempt, including literal
nulls where applicable), and receipt visibility. Caller identity remains the
fresh host principal/action; it never becomes the stored origin. Selectors are
trusted binding constraints, not extra status API arguments, wildcard run
access or authority derived from a digest.

Observer mode grants no append, delivery retry, new write, execution replay,
ledger/admission release or scope expansion. Worker bindings receive no observer
grants. RunRef, AgentResult, saved binding descriptors, IDs/digests and returned
refs do not issue one automatically. Separate authorized object/history or
publication grants, if present on a host session, remain separate: observing a
receipt cannot enlarge them.

Child scopes require explicit creation authority, and child output must be
exported into a parent-readable scope or explicitly granted. Parent linkage
does not make child data readable. New grants on resume are issued by
Connections; cached authority is never restored from a checkpoint.

This is an interface boundary for trusted registered components, not an
OS sandbox against a hostile executable running as the same local user.
Store directory ACLs and verified containment belong to deployment acceptance.

## 2. Canonical identity, immutable requests and receipts

| Identity | Allocation and invariant |
| --- | --- |
| `run_id`, `root_run_id`, `correlation_id` | Connections' trusted identity service, preserving lineage. |
| `action_id` | Action owner, one logical model generation/tool call/parent invocation. Changed input or a new model turn is a new action. |
| `attempt_id` | Action owner before every dispatch reservation, including the first. Actual authorized retry keeps action and changes attempt. |
| `event_id` | Producer before append; frozen event delivery retries keep it. |
| `operation_id` | Trusted caller before a Storage mutation; identical delivery/status reconciliation keeps it. |
| Provider native IDs | Provider-owned request/call IDs, retained separately for conversation pairing. |

Storage publication events retain causal run/action/attempt and parent IDs.
They have their own operation/event identities; no competing commit action is
allocated. Compound child operation IDs derive from parent operation plus role,
so retries cannot duplicate constituent artifacts. Storage allocates publication
event IDs before the commit and persists them with the reservation.

Default external retries are disabled. A fresh execution attempt needs an
explicit owner decision and fresh attempt/intent within inherited limits.
A delivery retry is neither a new attempt nor permission to repeat a fetch,
model call or child invocation.

Canonical successful event receipt has exactly these shared fields:

```text
EventReceipt = {
  schema_version: 1,
  store_id,
  event_id,
  recorded_seq,
  recorded_at,
  duplicate
}
```

`Ok(EventReceipt)` means committed under the verified active durability
profile. There is no separate RecordAck, caller durability flag or redundant
record ID. Sequence is store-wide, ascending with possible gaps; timestamps
describe time and never determine order. An event cannot contain its own
eventual receipt.

Digests serialize as sha256:<64 lowercase hex digits>; sizes and byte positions
are nonnegative integers. IDs remain the shared opaque identity types, not paths.

A write receipt contains `schema_version, store_id, operation_id,`
`event_receipt, duplicate` plus its operation-specific result. The original
refs/versions/sequence/time remain unchanged on delivery replay;
`duplicate` is delivery metadata. Success implies committed publication,
not external-effect atomicity or hardware immunity.

Request fingerprint version 1 uses deterministic compact UTF-8 JSON with
sorted keys, strict finite values and unique keys. Numeric type/representation
is frozen by the shared serializer. It includes method, trusted origin
(principal/producer, scope and run/action/attempt), input metadata and expected
content digests/lengths. It excludes delivery timestamps, live handles,
server-assigned sequence and returned duplicate flags. Streams are identified
by a required declared length/SHA-256 descriptor, then verified against bytes.
Different base64 spellings are not different content after validated decoding.
All producers use the one PM-owned canonicalizer.

Originator delivery deduplication is by store/event ID or store/operation ID.
Reauthorize current
identity/visibility first, compare frozen canonical content/origin, then return
an existing committed receipt before fresh write quota/reservation, queue-admission
or expected-version checks. Identical pending delivery returns OPERATION_PENDING
with the original ID/phase (or that status through the status API), not a new
reservation. Only a new ID proceeds to fresh admission; the root owner's atomic
ID claim prevents concurrent identical submissions reserving twice. Different
content/origin is IDEMPOTENCY_CONFLICT. Never overwrite/REPLACE a history or
receipt row. Reconciliation consumes no source stream or additional write quota;
independent finite delivery/status/read limits and current authority still apply.
A fresh host observer does not submit the stored origin/content as its own;
section 4 defines its read-only status authorization separately.

## 3. Async context-first APIs and exact results

All execution operations below are async, scoped and context-first, using
`Result[T] = Ok(value) | Err(error)`. Expected errors use results. Unexpected
defects retain exception semantics after bounded cleanup. Python task
cancellation cleans up and re-raises; explicit engine cancellation returns
an error result. Disk work stays on the owned worker, not the model event loop.

The session factory and terminal close are lifecycle operations: close keeps
the exact v1 `close(deadline)` signature rather than inventing a context argument.

| Signature | Result |
| --- | --- |
| `StateStore.get(context, scope, key)` | `Result[StateLookup]` |
| `StateStore.get_version(context, scope, key, version)` | `Result[StateLookup]` |
| `StateStore.commit(context, operation_id, mutations, activity)` | `Result[StateCommitReceipt]` |
| `ArtifactStore.put(context, operation_id, scope, content, metadata)` | `Result[ArtifactReceipt]` |
| `ArtifactStore.open(context, artifact_ref, byte_range, max_bytes)` | `Result[ArtifactRead]` |
| `SnapshotStore.commit(context, operation_id, scope, proposal)` | `Result[SnapshotReceipt]` |
| `SnapshotStore.read(context, snapshot_ref, range, max_text_bytes, continuation)` | `Result[DocumentSlice]`; continuation is explicit null on first call |
| `CheckpointStore.save(context, operation_id, scope, checkpoint)` | `Result[CheckpointReceipt]` |
| `CheckpointStore.load(context, checkpoint_ref, accepted_formats)` | `Result[CheckpointEnvelope]` |
| `ActivityRecorder.append(context, event)` | `Result[EventReceipt]` |
| `ActivityRecorder.status(context, event_id, expected_event_digest)` | `Result[EventStatus]` |
| `ActivityReader.query(context, filters, cursor, limit)` | `Result[ActivityPage]` |
| `OperationStore.status(context, operation_id)` | `Result[OperationStatus]` |
| `StorageSession.close(deadline)` | `Result[CloseReceipt]` |

Trusted bootstrap factory `StorageSession.open(resolved_settings, authority)`
returns `Result[StorageSession]` after obtaining the root lock, verifying
schema/runtime/settings and completing recovery. Connections supplies the
administrative authority and grants; Storage never issues them. Administrative
`provision_run(admin_context, run_descriptor)` returns a registered scope,
not permission to use it. Shared scope registration is similarly explicit.
These factory/provisioning paths are not worker/agent capabilities.

| Result/value | Required shape and behavior |
| --- | --- |
| `StateLookup` | `Present(value, version, commit_event_id)` or `Missing(version)`. Latest missing version is 0 or retained tombstone version. Historical tombstone is Missing at that exact revision; absent revision is NOT_FOUND. |
| `StateMutation` | `{scope,key,kind:put|delete,expected_version,value?}`. Duplicate keys in a batch invalid. |
| `StateCommitReceipt` | Common write fields plus ordered `mutation_versions[{scope,key,old_version,new_version}]`. Revisions remain readable under grants. |
| `ArtifactContent` | Immutable expected byte length/SHA-256 and an async byte source. Unknown descriptors are rejected; no unreviewed streaming RPC is added. |
| `ArtifactMetadata` | Valid media type plus optional display filename/bounded JSON. Filename is data, not a path. |
| `ArtifactReceipt` | Common write fields plus `artifact_ref,scope,byte_length,sha256,media_type`. |
| `SnapshotReceipt` | Common write fields plus `snapshot_ref,manifest_ref,original_ref,text_ref,index_ref,component_digests,extraction_version,line_count,physical_page_count_or_null`. |
| `CheckpointReceipt` | Common write fields plus `checkpoint_ref,payload_ref,byte_length,sha256,envelope_format_version`. |
| `ByteRange` | `{start,end_exclusive}`, zero-based, `0 <= start <= end <= byte_length`; no clamping. |
| `CloseReceipt` | `{schema_version:1,store_id,closed:true,completed_operation_ids,interrupted_operation_ids}`. An unresolved writer returns an error instead of closed=true. |

`ArtifactRead.read(context, max_bytes)` returns `Result[ByteChunk]`,
`ByteChunk={bytes,eof,next_absolute_offset}`; `aclose(context)` returns
`Result[Unit]` and is idempotent. The handle is bound to the original authority,
range and cumulative allowance. Every chunk checks current context/grants,
deadline/cancellation and total remaining budget. Verify size/digest before
releasing content. Midstream fault/denial stops further bytes; consumers need
successful EOF to regard the selected read as complete. Already delivered
prefixes cannot be recalled. Streaming holds no SQLite transaction.

CAS uses expected version 0 only for never-created keys. Put/delete advances
the version, with delete retaining a tombstone. Deleting a never-seen/already
deleted key is INVALID_DATA. Recreate expects the tombstone's actual version,
preventing ABA. Version exhaustion is LIMIT_EXCEEDED, never wraparound.
Conflict rolls back the entire batch, with current versions disclosed only
where permitted. There is no unconditional overwrite available to agents.

State value cap is 1 MiB; batch is <=100 mutations and <=4 MiB. Keys are
<=256 UTF-8 bytes. Event JSON is <=64 KiB; checkpoint JSON <=4 MiB;
ordinary metadata <=16 KiB. Bindings may reduce these module-local defaults.
Activity annotations supply safe cause/references/application metadata;
Storage controls producer, mutation identities/versions and mandatory event.
One-database multi-scope batch requires all write grants; its event visibility
requires access to all affected scopes. Cross-database/file/state atomic
batches are outside v1.

## 4. Exact event/operation status and error semantics

The existing `ActivityRecorder.status(context, event_id, expected_event_digest)`
and `OperationStore.status(context, operation_id)` signatures serve both modes;
neither accepts a caller-issued observer flag or origin override. Event status
is exact-ID/digest lookup, not history search. Expected digest is the shared
canonical producer-event digest, excluding Storage sequence/time/receipt; it
verifies target content and never grants authority.

Authorization order:

1. Validate the live caller's issuer/store, principal/context binding, policy,
   mode, permitted status method, deadline, lease, expiry/revocation and finite
   status/read allowances. Intersect exact target IDs/run/scope and receipt
   visibility before any existence or status disclosure. Exhausted
   business-write quota alone does not deny this observation; no new write
   quota/reservation/CAS is evaluated or consumed.
2. For `originator`, retain the original producer/caller and run/action/attempt
   checks. An authorized same-ID request with changed canonical content/origin
   remains IDEMPOTENCY_CONFLICT. This revision changes no originator delivery,
   fresh-write admission or idempotency rules.
3. For `observer`, use a non-disclosing scoped lookup of the stored or admitted
   target origin and match it to the binder's exact selector. Compare the
   target's frozen origin, not the fresh host's action/attempt. A target origin
   outside that selector or insufficient receipt visibility is ACCESS_DENIED,
   with no existence, foreign payload, hash, sequence or phase disclosure.
   Authorization failures precede any absent/unknown answer.
4. Only after authority/origin/receipt visibility is satisfied, compare the
   expected event digest. A mismatch on an authorized target returns
   IDEMPOTENCY_CONFLICT without returning target content. Operation status has
   no caller digest argument and returns only its permitted frozen operation
   observation.

Authorized observation returns the same original receipt or bounded
pending/aborted/interrupted/absent/unknown disposition below. It does not append
an event, retry delivery, consume source bytes, publish an object, release
execution/admission accounting or confer access to refs carried in the receipt.
Status/read quotas remain finite and current authority is checked on every
call, including reopened access. No background write is admitted by polling.

```text
EventStatus = {
  schema_version: 1, store_id, event_id,
  state: committed | pending | absent | unknown,
  observed_seq,
  receipt: EventReceipt | null,
  pending_phase: queued | appending | null
}
OperationStatus = {
  schema_version: 1, store_id, operation_id,
  state: committed | pending | aborted | interrupted | absent | unknown,
  commit_state: committed | not_committed | unknown,
  observed_seq,
  receipt: StateCommitReceipt | ArtifactReceipt | SnapshotReceipt
           | CheckpointReceipt | null,
  phase, safe_disposition
}
```

Status invariants: committed requires a receipt and no pending phase. Event
pending requires queued/appending and no receipt; absent/unknown have neither.
Operation phase is queued|reserved|writing|sealed|publishing|ready|aborted|
interrupted or null. Committed has ready/committed/receipt; pending uses one of
the first five phases with unknown/no receipt; aborted/interrupted uses its
matching phase and not_committed/no receipt; absent/unknown uses null phase
and unknown/no receipt. safe_disposition is null or a bounded failure code/message,
not arbitrary exception text. observed_seq is a nonnegative integer or null.

Committed includes the original receipt. Pending includes phase and no receipt;
it is unknown commitment until settled. Aborted/interrupted with a confirmed
nonpublication disposition is not_committed. Absent means not visible at the
observation, with unknown commitment: it does not prove no queued request exists.
Unknown has no receipt and unknown commitment. observed_seq is the permitted
store observation watermark, not a count of another run's history. If that
watermark is outside the caller's visibility, return null. Unavailable database
returns Err with unknown commitment rather than invent a successful lookup.

The root owner maintains an admitted-ID map, including queued writes. Admission
registers ID/content/origin before enqueue; status serializes against the worker
and combines committed rows with those reservations. A duplicate pending request
returns OPERATION_PENDING instead of starting another writer. After process
death volatile queue entries may disappear; recovered absence still does not
establish an external outcome. Idempotent same-ID delivery resolves persistence
without dispatching external work.

`StorageError` follows the common envelope:
`{code,message,details,effect_state,commit_state,retryable_delivery,`
`operation_id?,event_id?,action_id?,attempt_id?}`.
Details are bounded and sanitized: no secrets, authentication headers,
credential URLs, unfiltered stderr or internal absolute paths. effect_state
reports the observed Storage effect; it is separate from a model/tool's effect.

| Code | Exact persistence consequence |
| --- | --- |
| ACCESS_DENIED | Invalid/expired/revoked authority, mode/scope/operation denial, observer target-origin mismatch or insufficient receipt visibility; no existence disclosure or write admission. |
| NOT_FOUND | No visible authorized object/revision; ordinary latest-state absence uses Missing. |
| INVALID_DATA / INCOMPATIBLE_SCHEMA | Invalid strict JSON/type/reference/version; no silent conversion. |
| LIMIT_EXCEEDED | Byte/depth/key/unit/version cap; minimum next UTF-8 codepoint size may be included. |
| VERSION_CONFLICT | Batch rollback confirmed; caller rereads and chooses a new logical mutation/new operation ID. |
| IDEMPOTENCY_CONFLICT | Authorized originator same-ID changed content/origin, or authorized exact-event status digest mismatch; no overwrite, duplicate publication or foreign payload. |
| OPERATION_PENDING | Existing owned admitted write; status/same-ID reconciliation only. |
| INCOMPLETE_ARTIFACT | Non-READY artifact/snapshot/checkpoint; no partial content. |
| INTEGRITY_ERROR | Missing/altered READY bytes or invalid containment; fail read and preserve history. |
| UNSUPPORTED_RANGE / INVALID_CURSOR | Missing page map or invalid/bound-to-other-content continuation; never synthesize/clamp. |
| INCOMPATIBLE_CHECKPOINT | Envelope outside accepted formats; Runtime handles semantic adapter incompatibility. |
| STORAGE_BUSY / STORAGE_UNAVAILABLE | Bounded queue/lock, disk/full/permissions/I/O failure; commitment truthfully classified. |
| CANCELLED / DEADLINE_EXCEEDED | No new admission; admitted writes may still be pending or committed. |
| SESSION_CLOSED | Owner stopped admissions; borrowed lease close does not close a shared store. |

Known not_committed requires confirmed nonadmission, rollback, or durable ABORTED
state preventing later publication. Once admitted/sealed, cancellation does
not establish rollback. A committed write remains committed despite cancellation.
A lost reply is unknown until same-ID status/receipt reconciliation. Storage
never refetches/reinvokes or automatically retries execution. A successful
receipt can coexist with failed tool outcome recording.

## 5. Schema, migrations, worker and durability profile

Logical schema 1 uses these tables. SQLite columns have explicit NOT NULL,
CHECK and foreign-key constraints; values use bound parameters.

| Table | Keys/required contents and constraints |
| --- | --- |
| store_metadata | One store UUID, database schema/canonicalizer version and explicitly configured durability profile. |
| schema_migrations | Unique version, checksum and application time; checksum/version agrees with user_version. |
| scopes / run_links | Registered tagged scope; run/root/agent/definition/correlation and parent run/action/attempt facts supplied by Connections. |
| state_heads | PK(scope,key), latest version/revision, tombstone and commit event link. |
| state_revisions | Unique(scope,key,version), immutable JSON/tombstone and commit event; retain values for exact historical reads. |
| operations | Unique operation ID, method/origin/fingerprint, causal context, preallocated child/object/event IDs, reservation phase, sealed descriptor, completed receipt or abort disposition. |
| artifacts | Opaque ID, scope, operation, generated relative key, RESERVED/SEALED/READY/ABORTED/INTERRUPTED phase, digest/length/media metadata, availability and event link. |
| snapshots | Immutable ID/scope/format and original/text/index/manifest refs; public only when full bundle READY and publication event/receipt committed. |
| checkpoints | Immutable ID/scope/envelope/runtime codec refs and READY payload ref/publication event. |
| events / event_scopes | AUTOINCREMENT recorded_seq, unique event_id, schema/producer/event digest and envelope, causal IDs/kind/status, visibility scopes. Append/query only through API. |
| action_attempts | Derived lifecycle intent/outcome links; canonical attempt/boundary uniqueness, no independent run-status decision. |

Indexes include run+sequence, action/attempt+sequence, correlation+sequence,
scope+sequence and pending phase. Dispatch uniqueness requires non-null attempt
IDs: one model/tool/invocation intent and outcome per actual attempt. Agent
start/finish are unique on their run-root action. Publication uniqueness is
operation+event kind, so multiple artifact children share causal attempt safely.
Corrections are new events referencing old records, never REPLACE.

One exclusive process-lifetime root lock precedes schema access/recovery.
Second owner receives STORAGE_BUSY; no hidden second store or attachment.
All SQLite writes/checkpoints are executed serially on the owning worker/
connection. Short reads are scheduled there initially; no connection crosses
thread ownership. Root/worker/leases remain owned until admitted operations
settle. This topology is deliberately simple, rather than relying on contention
or lease age to prove another producer died.

For atomic state/event/receipt writes: validate current identity/authority and
receipt visibility; reconcile the same ID/content/origin before any fresh quota
reservation or new-write queue admission. For NEW admission, atomically claim ID,
check/reserve remaining write quota/fresh-use/queue allowance; BEGIN IMMEDIATE;
recheck receipt before CAS; verify all expected versions; insert event/revisions/
heads/receipt; COMMIT; then acknowledge. Any statement failure rolls back the
whole transaction. Statement-level ABORT alone is insufficient. Busy COMMIT
retains its active transaction within the same total budget, then resolve
commit/rollback rather than detach it. No external wait or file streaming occurs
inside a SQLite transaction. Default queue+busy budget is min(5 seconds,
remaining context deadline); internal retries do not reset it.
[SQLite transaction rules](https://sqlite.org/lang_transaction.html),
[conflict handling](https://sqlite.org/lang_conflict.html)

Database schema, wire major and payload codec revisions are independent.
Reject unknown newer database schemas/altered migration checksums. Administrative
migration stops admissions, settles writers, verifies a database+object backup,
applies explicit transaction-controlled statements and records version/checksum.
No migration during an action. JSON/schema validation has no provider network
effects. Retention/GC is deferred; preserve receipts/revisions for retained data.

Baseline is explicit DELETE journal, synchronous EXTRA and foreign_keys ON on
the shared uv/Python3.11.15 environment. Open queries returned journal mode,
synchronous=3, foreign_keys=1, linked SQLite version and root/schema identity.
Failure to establish a requested setting is a typed startup failure. PM recorded
linked SQLite3.50.4; that is metadata evidence, not Storage behavior verification.
EXTRA adds rollback-journal directory synchronization. Device/VFS truthfulness
still matters. [SQLite synchronous settings](https://sqlite.org/pragma.html#pragma_synchronous)

Optional explicit WAL uses FULL (2), foreign_keys ON, local same-host storage
and a patched linked-library gate: >=3.51.3, or documented patched 3.50.x>=3.50.7
or 3.44.x>=3.44.6. Do not accept arbitrary intermediate older releases merely
because they exceed 3.44.6. Verify returned settings and trusted runtime evidence.
Unsuitable requested WAL is rejected, never silently downgraded. Profile
conversion is an explicit quiescent administrative operation with backup.
No interpreter upgrade, package install or database profile change occurs now.
[SQLite WAL safety notice](https://sqlite.org/wal.html#walresetbug)

Python3.11 uses isolation_level=None and explicit transaction statements.
Map sqlite_errorcode/sqlite_errorname, keep connections on their worker and
avoid executescript inside a pending transaction because it can commit it.
[Python3.11 SQLite](https://docs.python.org/3.11/library/sqlite3.html)

Backup uses a quiescent publication barrier, SQLite backup API and manifest of
referenced immutable files, verified on restore. Never copy only a live main
database and discard WAL. A normal close need not force a truncation checkpoint
to make a prior committed receipt true.

## 6. Filesystem publication, composite recovery and containment

Storage generates all staging/final names beneath the resolved configured root.
Agent filenames are metadata. Reject traversal, alternate stream/device syntax,
symlink/junction/reparse escape and invalid opened-file containment. Stage and
objects are on the same local volume. An unexpected final destination is a
conflict, not permission to overwrite. Deployment acceptance must verify
Windows opened-handle containment/ACL and lock behavior; normalization alone
does not prove protection against hostile path replacement.

| Phase | Persisted fact / public visibility |
| --- | --- |
| RESERVED | Operation/origin/fingerprint, object/event IDs, expected descriptor and owner reserved in SQLite; unreadable. |
| Writing | Exclusive generated stage; bounded chunks, hash/length, file flush+fsync; no open database transaction. |
| SEALED | SQLite stores verified completed digest/length after complete file sync/close; unreadable. An unsealed file hash does not prove a complete stream. |
| Final file | Same-volume rename to generated final key; verify size/digest/containment and supported metadata sync. File alone is not publication. |
| READY | One SQLite transaction publishes READY metadata, authoritative publication event and original operation receipt. Acknowledge afterward. |
| ABORTED | Durable nonpublication disposition; recovery never promotes it. |
| INTERRUPTED | Missing/unsealed/invalid incomplete operation; no readable partial content or reconstructed external fetch. |

Python documents flushing buffers before fsync and same-filesystem rename
requirements. These primitives do not establish verified Windows directory
power-loss survival or a joint file/database atomic transaction.
[Python filesystem APIs](https://docs.python.org/3.11/library/os.html)

Snapshot/checkpoint reservation persists the complete validated immutable parent
descriptor, preallocated publication ID/event and child operation IDs BEFORE
staging. Children derive from parent ID+component role. Snapshot roles are
original/text/index/manifest; checkpoint role is payload. Retry/status uses
the same reservation; ready children are reused rather than duplicated.
Children have their own artifact publication events. Parent visibility requires
all exact children READY/verified, then one transaction commits parent row,
its publication event and receipt. Children orphaned by an interrupted/aborted
parent remain recorded and are not silently claimed rolled back.

Recovery acquires the root lock before serving requests. It is exact admitted
Storage completion under trusted recovery authority supplied by the host,
not reconstitution of saved user grants. It preserves causal metadata and
uses the preallocated IDs. Never reclaim an active owner's file based on age,
PID or expired lease alone. No second owner can race publication.

| Recovered condition | Result |
| --- | --- |
| Unsealed/missing incomplete stage | INTERRUPTED, quarantine; do not hash partial bytes and publish. |
| SEALED + valid stage | Verify stored seal, rename, then READY/event/receipt once. |
| SEALED + valid final | Verify seal, finish READY/event/receipt once. |
| Complete sealed parent + all READY children | Publish original snapshot/checkpoint identity once, unless durably ABORTED or administratively prohibited. |
| Incomplete parent | Mark INTERRUPTED, preserve recorded children; no indefinite pending reservation. |
| ABORTED | Keep nonpublication; cleanup/quarantine only. |
| READY + healthy bytes | Preserve receipt; no second publication event. |
| READY + missing/mismatched bytes | Availability fault, fail reads with INTEGRITY_ERROR and append an origin-linked storage diagnostic; never rewrite committed history. |
| Unindexed generated file | Quarantine as an administrative health diagnostic; do not invent an agent run/context to record it. |

Recovery never creates a model/tool outcome or changes an incomplete external
action to failed. Already admitted publication can settle after a caller loses
its response; same-ID status returns the original result. Any current policy
prohibiting unfinished publication yields a durable abort rather than revived
business authority.

## 7. Snapshots, exact ranges and smaller bounded mediation

The v1 path is launcher-mediated access. ToolExecutor holds Connections'
ToolStoragePlan bound to tool/revision, run/action/attempt, exact operation,
scope/object/range and quotas. Worker has no Storage client, root, authority,
finalized ref or publication receipt. Read is authorized and prepared through
SnapshotStore before worker dispatch; fetch worker emits prepared payload.
The executor validates and commits that payload. Container's one shared
RecordedToolAction owns intent/outcome for both agent and standalone use.
No broker/private-pipe implementation or independent snapshot database is added.

Private WorkerResponse uses phase prepared|failed. Exit 0 means prepared.
Search prepares discoveries; read serializes the exact injected DocumentSlice;
fetch prepares a complete proposal with the assigned operation ID. A public
fetch success requires READY snapshot receipt AND complete tool lifecycle
recording. Failed post-worker Storage commit stays a failed tool observation;
lost commit reply reconciles the same operation, never refetches.

SnapshotProposal format document_snapshot/1 has immutable component descriptors/
bytes (original, canonical text, index), extraction name/version/options/
normalization, physical page count/map where available, content classification
and safe provenance. Original is the HTTP client's content-decoded retained
body, with content-encoding/representation metadata, not a claimed wire capture.
Extraction and original come from the same response. Toolset owns classification
of blocked/login/unsupported/empty extraction; Storage verifies structure/hash/
limits/locations. Empty-data range semantics do not turn unusable fetch into
public success.

Stored manifest links original/text/index digests, size and typed refs; requested/
final sanitized URL, redirects/time/status/media/encoding, safe headers/search
provenance and extraction versions. Never cookies/authentication or arbitrary
header dumps. Refresh creates another immutable snapshot; read never refetches
or re-extracts with a different library.

Index format document_index/1 contains line spans (content byte start/end),
physical-page spans and optional printed labels. Spans identify exact stored
UTF-8 boundaries; LF delimiters and any declared inter-page separators have
explicit normalization ownership. Page entries are one-based in physical order,
including zero-length empty-page spans. Storage validates counts, monotonic
bounds, delimiter/coverage rules and manifest/index digest agreement. It does
not parse the PDF again or claim semantic extraction fidelity.

Canonical text is UTF-8 without BOM, LF line endings, no implicit Unicode
normalization. Empty text has zero logical lines. Final LF adds no phantom
line: ""=>0, "a"=>1, "a\n"=>1, "\n"=>1, "a\n\n"=>2. PDF unit count is physical
page count including empty pages, independent of the logical line count.
Unavailable page map returns UNSUPPORTED_RANGE.

DocumentRange is exactly one tagged object:
`{kind:lines|pages,start,end_exclusive}`. For selected unit count N,
`1 <= start <= end_exclusive <= N+1`. Empty ranges are allowed at any valid
boundary; N=0 permits only [1,1). No clamping/mixing units. Counts exceeding
200 lines/10 pages are LIMIT_EXCEEDED; callers choose the next bounded range.

DocumentSlice required fields:
`schema_version, snapshot_ref, extraction_version, normalization_version,`
`requested_range, returned_range, spans, text, truncated,`
`has_more_in_requested_range, has_more_in_document, next_position`.
Each span has physical page/line where applicable and zero-based absolute
UTF-8 byte start/end; no invented line on a textless page.

| Case | Exact result |
| --- | --- |
| Empty range [k,k) | Equal requested/returned range, text "", spans [], truncated=false, next_position=null, within-range=false; more-document=(k<=N). |
| Zero lines | Only lines[1,1) valid; no phantom unit. |
| Empty physical PDF page p | pages[p,p+1) consumes a real page; text "", zero-length page span, complete range and no fictitious line. |
| Nonempty slice fits | Complete requested range, next_position=null, truncated=false; more-document=(end_exclusive<=N). |
| Budget truncates line/page | Return UTF-8-boundary spans with an advancing next_position; remaining requested units/bytes are explicit. |
| Next codepoint does not fit | LIMIT_EXCEEDED with minimum_next_codepoint_bytes (1..4); no zero-progress cursor. |
| Missing page map/invalid bounds | UNSUPPORTED_RANGE/INVALID_DATA; no synthesized map or silently changed range. |

Continuation is integrity-protected and binds store/snapshot/extraction/
normalization, original requested range, byte/unit position and authority
selector. On the next call supply the same range and continuation; reauthorize.
A smaller still-positive budget is allowed if the next codepoint fits.
Process empty units by advancing unit position even if text byte length is zero.
Keep page/unit and byte progress distinguishable. Cursor is not a grant.

| v1 resource target | Maximum |
| --- | ---: |
| Decoded original | 8 MiB |
| Canonical UTF-8 text | 4 MiB |
| Index | 1 MiB |
| Serialized provenance | 64 KiB |
| Worker stdin / fetch stdout | 1 MiB / 20 MiB |
| Final public JSON / stderr | 512 KiB / 64 KiB |
| JSON depth | 32 |
| Read text / units | 64 KiB / 200 lines or 10 physical pages |

Storage enforces decoded component/index/provenance caps and aggregate scoped
storage quotas. Toolset additionally enforces actual serialized whole envelopes
and pipe drains. Base64 components require 4*ceil(n/3) bytes, about 17.34 MiB
at the combined original/text/index maxima before metadata/framing; JSON
escaping must also be checked. An oversized whole proposal is rejected even
when each component fits. No cap is permission to increase a narrower grant.
Generic artifact maximum is 8 MiB unless an explicitly approved owner profile
narrows it; generated manifest fits <=256 KiB. No worker-selected profile override.

Byte caps do not bound peak RAM, PDF decompression/parser allocations, objects,
copies or latency. Measure one fetch first, then at most two concurrent fetches;
these are future enforcement/measurement gates, not observed performance.
Larger/interactive streaming requires a measured scope decision by PM/user.

## 8. Automatic hooks, dispatch gate and cancellation

ExecutionEvent uses schema_version 1, event ID/kind, trusted producer, causal
context, occurred_at, status and bounded safe payload/references with optional
duration/usage/error. Dispatch context contains attempt; nondispatch preflight
may omit it. Unknown usage remains unknown, never fabricated zero. Stored
sequence/time are server fields. Producer authority restricts kinds.

| Action/event | Canonical producer / required fact |
| --- | --- |
| agent.started / agent.finished | Runtime; definition/binding/input, run start and terminal result/recording facts. No duplicate run.accepted. |
| model.intent / model.outcome | Runtime; frozen request/limits/profile and observed response/error/continuation/usage. |
| tool.intent / tool.outcome | Runtime's RecordedToolAction; validated args/limits and executor/process/commit observation. |
| tool.rejected | Runtime; no execution attempt/process, known nondispatch. |
| context/validation/limit/cancel observations | Runtime; safe source/version/count/decision metadata, not new agent terminal statuses. |
| binding.resolved / binding.failed | Connections; safe binding identity or local validation failure. |
| invocation.intent / invocation.outcome | Connections; parent call/attempt and child linkage/result; child Runtime still owns its lifecycle. |
| state.committed | Storage; mutation old/new revisions and operation, in the state transaction. |
| artifact.committed / snapshot.committed / checkpoint.saved | Storage; complete refs/digests/size/format and operation, within publication metadata transaction. |
| Origin-linked recovery/availability diagnostics | Storage; exact already-admitted operation disposition, never invented model/tool outcome. |

Context kinds are agent/standalone_tool. Standalone producer is runtime through
the same Container-owned RecordedToolAction; no standalone_driver alternative.
Connections bootstraps grants and scope; CLI parsing/executor/worker never adds
a lifecycle logger or opens a model. Storage appends/reads/metadata maintenance
do not recursively create records; business publication emits its one explicit
commit event. History/UI polling is not execution activity.

Before dispatch: freeze intent, append, obtain committed EventReceipt, then
recheck cancellation/deadline/grants. No receipt means no model/tool/child
dispatch. Known nondispatch after a committed intent records an outcome with
dispatched=false. After dispatch preserve observed effect separately from
recording and commit states; outcome acknowledgment precedes public success.
Failure stops further dispatch and reports incomplete/unavailable recording.

record_cleanup is a separate trusted bounded context for owner-event append,
exact status reconciliation and lease/handle cleanup. It authorizes NO new
business writes, output artifact/snapshot/checkpoint/state admission or
model/tool calls. A completed output not yet admitted when cancellation occurs
cannot be published by cleanup; preserve known refs and bounded safe observation
or mark missing output/recording incomplete. Already admitted Storage tasks
settle under their original reservations; this is not new cleanup admission.

Connections issues cleanup authority/window and Runtime owns activation and
terminal hooks, preserving causal IDs. Explicit revocation of that cleanup
authority still denies use. Storage does not clear cancellation on ordinary
contexts or invent a grant extension. Cleanup expiry can leave terminal history
incomplete; a pending writer still retains root/resources. No Storage method
replays an external effect to reconstruct missing output.

A fresh host observer uses normal current authority rather than an expired
owner context or record_cleanup. Its read-only observation does not activate
cleanup, settle/release an uncertain execution ledger or admission, close a
writer's lease/root, reclassify a recorded outcome or authorize another dispatch.
Already admitted work remains with its original owner/resources until the
ordinary settlement rules are satisfied.

## 9. Pagination, checkpoints and ordered close

ActivityFilters supports authorized run/action/attempt/correlation IDs,
kind/status, scope and descriptive time filters. Initial page captures a
committed high-water sequence under a short read snapshot. Query ascending
last_seq < seq <= high_water_seq with keyset pagination, not OFFSET.
Page <=500 events/1 MiB; no read transaction survives between pages.
Cursor integrity binds store/schema/filter/principal/grant selector, last/high
sequence and a 24-hour expiry. Reauthorize each page; changed grants invalidate
it. Return only complete permitted visibility sets; no foreign total count or
payload. New events require a new query. Cursor keys are generated by the owner,
stored privately in nonserializable resources; restart invalidates old cursors,
avoiding a new checked-in secret/config loader.

CheckpointEnvelope is immutable strict JSON with envelope/payload schema,
runtime/definition/binding refs, run identity and last fully recorded position,
transcript/artifact/state-version refs, provider/model/adapter codec continuation,
portable deadline and remaining/shared budget descriptors. Large content lives
in its READY payload artifact. No credentials, connections, locks, live
cancellation/grants/leases or monotonic readings.

Storage checks accepted envelope formats, sizes/digests/references and grants;
Runtime checks adapter/provider/model semantics, safe position and exclusive
resume claim. Fresh Connections binding/grants and rebuilt timers are required.
Unknown external attempt outcomes cannot be replayed from a checkpoint.
Runtime may use a scoped CAS state claim but Storage does not schedule resumption.
Migration emits a new checkpoint/ref/event rather than changing old bytes.

Shutdown order:
1. Connections stops new execution admission and cancels/drains borrowers.
2. Runtime/Connections terminal hooks use their bounded recorder cleanup.
3. Storage settles admitted operations; callers reconcile same-ID uncertainty.
4. Release borrowed leases and close Storage/recorder last.

StorageSession.close stops its own new admissions. If all writes/readers settle,
close owned worker/resources and release root lock. Borrowed binding close only
releases that lease. If an OS sync/commit outlasts the deadline, return an error
with pending IDs/unknown commitment and retain draining session/worker/root.
Never report closed=true or let another owner enter while a write remains active.
A hard real-time filesystem guarantee is not claimed.

## 10. Acceptance plan, conformance and actual evidence

After explicit implementation authorization, real Storage/source tests belong
to src/ebd/storage/ and matching tests. Use shared uv/Python3.11.15/locked
dependencies; PM alone changes manifests/shared types/Git. No runnable module,
database, installation or model calls have been produced in this phase.

| Meaningful future case | Evidence required |
| --- | --- |
| Open/profile/migration | Report actual linked version and returned DELETE/EXTRA/FK/schema settings; reject unsuitable explicit WAL and unknown schema without silent switch. |
| Close/reopen | Real state/revisions/artifacts/snapshots/checkpoints/events/receipts retain bytes/digests/identity/order. |
| CAS/tombstone | Concurrent expected-version writes have one winner; injected event/receipt failure rolls back entire batch; recreation cannot reuse version 0. |
| Scope isolation | Other run/child/standalone cannot read/write guessed refs without explicit grant; status/query cannot expose foreign payload/metadata. |
| Delivery dedup/conflict | Concurrent same ID/content/origin returns original receipt; changed data/origin conflicts, including replay after later state revision. |
| Exhausted-quota lost reply | A real state write with expected_version=0 commits and consumes the final write quota; lose its reply. Identical same-ID/content/origin retry with current receipt visibility returns the original receipt/version/sequence despite the now-nonzero head, without another write reservation, quota charge or CAS. Changed content conflicts; revoked authority denies reconciliation. |
| Exact status/uncertainty | Lose append/write reply at known boundaries; lookup/retry same ID only, distinguish pending/absent/unknown and never redispatch external work. |
| Fresh host observer | Commit an event and operation under an original run/action/attempt, let that owner deadline expire, then issue a fresh host binding with exact observer selectors and receipt visibility. Both existing status APIs return the permitted original receipt; queued targets expose only bounded pending/unknown observations. Caller principal/action stays fresh and stored origin stays unchanged. Exhausted original business-write quota does not deny a status call within current status/read limits. |
| Observer delivery denial | With only that observer grant, try append, same-ID write/delivery retry, a new write and a different target ID/run. Each fails authorization before admission, reservation, source consumption or foreign existence disclosure. Observation cannot redispatch execution, release an uncertain ledger/admission or widen object/history access. Workers/RunRef/result refs cannot acquire observer authority automatically. |
| Observer origin/visibility/digest | Wrong frozen origin selector or missing visibility for any receipt field denies without existence/phase/hash/sequence leakage. On an authorized target, a changed expected event digest conflicts. Expired/revoked observer authority, exceeded status/read limits and unknown mode fail before disclosure. Unchanged originator lost-reply/quota/CAS vectors still pass. |
| Artifact interruption | Kill at reservation, stream, seal, rename, READY and receipt boundaries; unsealed remains unreadable, sealed recovers once, ABORTED never promotes. |
| Composite recovery | Parent+child IDs stable; complete sealed parent publishes once, incomplete becomes interrupted with recorded orphans. |
| Integrity/containment | Missing/changed READY bytes and traversal/junction/reparse invalid containment fail closed. Verify Windows lock and root exclusivity. |
| Range vectors | Zero lines, trailing LF, empty physical pages, EOF empty ranges, long codepoint/line/page continuation, wrong/expired cursor and missing page map. |
| Pagination/checkpoint | Concurrent appends do not shift a fixed-watermark query; grant revocation denies next page; incompatible/unsafe checkpoint rejected. |
| Cancel/close | Before admission known nondispatch; after admission commitment retained/unknown until settled. Cleanup cannot admit new business writes; unresolved writer retains root. |
| Real integration/resources | Actual CLI snapshot/read and runtime lifecycle; one canonical producer/no recursion; max-fit escaped envelopes, oversized PDF expansion and measured parent/worker RAM. |

Compact v1 conformance checklist:
- [x] Common async context-first Result operations and lifecycle close exception.
- [x] Logical action/fresh dispatch attempt and stable event/operation delivery IDs.
- [x] Exact six-field EventReceipt; successful return means committed.
- [x] ActivityRecorder.status exact-ID/digest and OperationStore.status.
- [x] Closed originator/observer modes, exact target-origin selectors, fresh host identity and read-only status/receipt visibility before disclosure.
- [x] Same-content/origin receipt reconciliation precedes fresh quota/reservation/CAS; tombstones, rollback and pending/unknown remain explicit.
- [x] Single-root/owned-worker DELETE/EXTRA, settings checks and opt-in patched WAL.
- [x] Sealed READY publication, deterministic composite recovery and owned close.
- [x] V1 mediated Worker phase, Container-only standalone recording and smaller caps.
- [x] Unit-specific empty line/page ranges and advancing UTF-8 continuation.
- [x] Cleanup limited to owner events/status/lease cleanup; no new business writes.
- [x] Future real fault/integration/measurement checks distinguished from evidence.

These checkboxes assert document alignment, not implementation/test success.
Current irreducible interface blockers: none for this design revision. Remaining
phase prerequisites are PM's shared executable types/composition/dependencies
and explicit authorized transition. New consumer/schema discrepancies must be
reported to PM rather than fixed in another team's module.

The [baseline acceptance design](../baseline-acceptance.md) requires saved full
report bytes, citation manifest with immutable slice locations, rendered-request
audit, terminal checkpoint and trace, followed by close/reopen without refetch.
Storage's planned audit covers these plus CAS/scopes, exact-ID uncertainty,
interruption and root ownership; the flat baseline does not replace those gates.

Actual evidence: entry/mission/v1/contribution/baseline acceptance and owned/sibling design reads;
prior official SQLite/Python/Microsoft source research and PM's r1 saved-file
UTF-8/fence/five-JSON QA confirmation at commit 4210b8c. PM's pre-correction r2
saved-byte QA passed; its historical hashes and resolved ordering finding are
recorded in storage-status.md. PM subsequently verified the final r3 saved bytes
and committed them at c061b29. This limited r4 observer design preserves that
quota/dedup/commit ordering; its own saved-byte QA is recorded in the status.
No runtime profile setting,
fault/recovery, performance, provider or power-loss behavior is claimed tested.
Local vLLM/Qwen live verification remains pending deployment. The private
repository and contributions are coordinated by PM; this revision is frozen
when handed off until PM confirms a commit or new coordinated revision.
