# Connections design aligned with platform contract v1

Owner: Connection Team.
Date: 2026-10-01 (America/Toronto).
Revision: aligned design 1.0; wire/event compatibility `schema_version: 1`.
Status: complete design contribution for PM review; runtime implementation is
not authorized. This replaces the team's earlier competing contract proposals.

Authority: [platform-contract-v1.md](../platform-contract-v1.md),
[Connection mission](../missions.md), and
[CONTRIBUTING.md](../../../CONTRIBUTING.md). The common contract wins over any
older peer draft. This document defines Connections' composition behavior and
lists the remaining shared-protocol requests explicitly; it is not runnable code.
The [baseline acceptance design](../baseline-acceptance.md) additionally requires
fresh post-run access to exact Runtime-published output and terminal receipts.

## 1. Ownership and composition boundary

Connections is the host composition root: named registration/configuration,
trusted context/grant issuance, binding and leases, Engine consumer operations,
permitted child invocation and authorized result export. It consumes module-owned
factories/protocols. It does not implement provider HTTP, a model/tool loop,
subprocess launching, durable persistence, a scheduler or EBD strategy.

| Owner | Supplied capability | Connections' use |
| --- | --- | --- |
| Container | AgentDefinition validation, Runtime.admit/execute, provider factories, shared ledger, RecordedToolAction | Bind exact profiles; submit one admitted execution; consume validated terminal facts; use the common recorded tool helper |
| Toolset | Catalog, fixed command definitions, ToolExecutor, worker parsing/formatting and prepare/finalize adapters | Bind permitted catalog/executor and ToolStoragePlan; compose standalone without a model |
| Storage | Store-root ownership, scopes, state/artifacts/snapshots/checkpoints, recorder/status and recovery | Open through its factory; provision via its administrative boundary; supply narrowed handles; reconcile by existing IDs |
| PM | Shared executable types, package/host CLI glue, dependencies, integration and Git | Request exact missing protocols; leave shared files and Git writes to PM |

Current editable outputs are this file and `reports/connections-status.md`.
After a directly authorized phase transition, future ownership is
`src/ebd/connections/` and matching Connections tests. Shared uv/Python 3.11.15,
`.python-version`, `pyproject.toml` and `uv.lock` remain authoritative.

The initial CLI Storage bridge is bounded launcher-mediated read injection and
postprocess snapshot commit. No broker, extra pipe, worker database/root access
or alternate snapshot store is composed. Larger/dynamic transfers require a
measured scope decision; the old broker/pipe comparison is not an implementation
assignment. The selected search/fetch stack belongs to Toolset/PM, not Connections.

## 2. Public Engine contract and expected results

Exact public signatures follow v1; the parameter schemas below define the
consumer boundary. Signatures are interface-only documentation.

```text
async Engine.open(settings) -> Result[Engine]
Engine.register_agent(definition, invocation_rules) -> Result[RegisteredAgent]
async Engine.bind(agent_ref, context) -> Result[BoundSession]
async Engine.run_agent(agent_ref, task_input, options) -> AgentResult
async Engine.run_tool(tool_ref, arguments, options) -> ToolResult
async AgentInvoker.invoke(caller_context, destination, input, options) -> InvocationOutcome
async Engine.close(deadline) -> CleanupReport
```

PM accepted this additive host-access signature during the design mission:

```text
async Engine.open_run_access(run_ref: RunRef, request: RunAccessRequest,
                             options: RunAccessOptions) -> Result[RunAccessSession]
```

It supplies the trusted application context/scoped binding missing from
bind(context). Section 12 specifies its fresh authority, lifetime and baseline use.

| Input/type | Exact meaning |
| --- | --- |
| `EngineSettings` | Version, trusted workspace/config references, bootstrap policy reference, module-owned factory catalog, selected Storage settings and finite shutdown policy. Live factory/authority objects are host supplied; not imported from arbitrary agent strings. No credential values in serializable settings. |
| `AgentRef` / `ToolRef` | Registered identity plus exact revision, resolved before binding. A new revision is a new identity/version pair; no silent latest-version replacement during a run. |
| `RunOptions` | Optional stricter deadline/limits, registered grant-preset requests, bounded metadata and output preferences allowed by the definition. Requests attenuate trusted policy; they cannot supply authority, argv, endpoint, secret value or a model substitution. |
| `ToolRunOptions` | Same root bounds plus explicit registered grants for any saved snapshot. No AgentDefinition/model/profile requirement. |
| `InvocationOptions` | Stricter child timeout/limits/grant attenuation and permitted result-export selection. No arbitrary destination definition or automatic replay setting. |
| `RegisteredAgent` | Exact Container-owned validated definition reference/digest plus validated outgoing invocation rules; immutable registration receipt. |

`Engine.open` returns only after Storage startup/root ownership/recovery and a
control-recorder binding succeed. Registration is synchronous and local: invoke
Container's static definition validator, reject incompatible versions/unknown
security fields, and register trusted references without opening a model.
Identical identity/revision/content is idempotent; different content under the
same identity/revision is `REGISTRATION_CONFLICT`. Forward destination references
may be registered but must resolve before that agent binds or dispatches.

Each root run pins a registry/config snapshot and exact revisions. Trusted
registration can add a new revision for future roots; it cannot mutate an active
BindingSet. Per-operation revocation still applies to pinned snapshots.

`run_agent` owns root context creation, scope/binding and Runtime admission;
Container owns the actual run and AgentResult. Preflight failures return the
agreed AgentResult error shape with no claim that an agent started. `run_tool`
creates a standalone context and calls RecordedToolAction; it never starts an
agent or opens a provider. `bind` consumes a trusted context issued by the host
identity/authority service, not JSON supplied by strategy/model code.
It intersects that context's live authority; a result-access context cannot be
rebound into agent execution by falling back to Engine's broader host policy.

Expected failures use common `Ok(value) | Err(error)` where the signature names
Result; execution APIs return their common result types with structured errors.
Execution terminals are only `succeeded`, `failed`, `validation_failed`,
`limit_exhausted`, `timed_out`, `cancelled`. Rejection/admission/dispatch phases
are observations, not extra terminal statuses. Recording is separately
`complete`, `incomplete`, `unavailable`; external effect and commit state remain
separate. Unexpected defects retain exception semantics after bounded cleanup.
Python task cancellation is cleaned up and re-raised; explicit engine cancellation
returns the appropriate execution result. Request R1 below fixes remaining result
and admission-status wire shapes before executable shared types are frozen.

## 3. Configuration precedence and lazy named profiles

The central loader explicitly reads only workspace-relative `local/.env` during
authorized runtime bootstrap. No upward/nested dotenv discovery, file rewrite or
independent provider/worker loaders. This design did not inspect that file.
Parse allowlisted keys into a private mapping without modifying `os.environ`;
disable variable interpolation so resolution precedence is explicit.

Non-secret precedence, low to high: schema defaults; trusted explicitly selected
non-secret configuration; allowlisted `local/.env` keys; allowlisted process
keys captured at Engine.open; permitted trusted bootstrap non-secret overrides.
Credentials resolve by SecretRef: an explicitly present process key overrides
the same `local/.env` key; absent process key falls back to that exact file.
Present-but-empty/invalid is an error, not a fallback. Do not accept credential
values in checked-in config, agent definitions/input or command-line overrides.

Configuration references name allowed variables without presuming this machine's
existing variable names. A missing key error names the reference/key only.
Profile descriptors record identity/revision and source category, not secret
values or secret-derived hashes. Raw mappings, credential-bearing endpoints,
headers, stdin and unrestricted stderr never enter exceptions/events/checkpoints.

Validate the selected Storage configuration at Engine.open. Register provider
profiles as named descriptors/factories and validate only the selected agent's
required profile at bind. Missing Qwen endpoint/model/parser/credential settings
fail only an agent selecting Qwen; standalone/API agents do not resolve them.
Do not select a different model if the requested one is unavailable. The fixed
OpenAI target remains Container's GPT-6-Luna Responses profile; DeepSeek and Qwen
configuration requirements are supplied by Container, including any selected
DeepSeek V4.1 Flash baseline profile. Connections does not guess service IDs or
implement request formatting.

Binding validates local profile/capability metadata, configuration presence and
interface compatibility. `supported`, `unsupported`, `unknown` feature evidence
is preserved; unknown cannot satisfy a required capability. Registration,
Engine.open and binding make no incidental network/model probes. A future explicit
live-check operation requires trusted authorization, a bounded context/cost and
owner-provided real evidence; it cannot be assumed from a successful local bind.
Local Qwen live verification remains pending deployment.

Only the implementation owner receives a restricted, nonserializable secret
accessor for its selected profile. Runtime uses ProviderFactory.open; Connections
never exposes a raw client to strategy code. Tool workers receive a controlled
allowlisted process environment and no model credentials. Rotation takes a new
bootstrap/config snapshot and owner-managed session replacement; it is not a
mid-run descriptor mutation. Python secret wrappers redact repr/diagnostics but
do not promise secure-memory zeroization. Any loader dependency needs PM approval.

## 4. Common ExecutionContext, authority and identities

Only integer `schema_version: 1` expresses wire/event compatibility. Definition,
tool, configuration, extraction and continuation codec revisions are independent.
Use strict finite JSON, unique keys, depth 32 and explicit UTF-8 byte limits.
Unknown execution/security fields fail validation rather than becoming grants.

| Persisted metadata | Required rule |
| --- | --- |
| `context_kind` | Exactly `agent` or `standalone_tool`; no invented system agent |
| `run_id`, `root_run_id`, `correlation_id` | Trusted Connections identity service; new child run ID, unchanged root/correlation across lineage |
| `agent_id`, `definition_ref` | Registered agent identity/revision for agent context; null for standalone |
| `action_id`, `attempt_id` | Action owner; logical operation plus fresh attempt for every dispatch reservation including the first; nondispatch preflight may omit attempt |
| `parent_run_id`, `parent_action_id`, `parent_attempt_id` | Null at root; child links to the exact caller invocation attempt |
| `deadline_at_utc` | Finite RFC 3339 UTC deadline established before binding/admission |
| `depth`, `ancestry` | Root depth zero and engine-owned ancestor identities; cannot be altered by worker/model input |
| `binding_ref`, `policy_ref`, lineage reference | Non-secret pinned descriptor/policy and accounting identities; references themselves confer no authority |
| `metadata` | Bounded application JSON; mission identifiers are optional data only |

Live context contains linked cancellation, a reconstructed monotonic deadline,
trusted effective grants/revocation authority, the Runtime shared lineage ledger
and resource leases. Live authority is binder issued, never restored from a saved
metadata object or an opaque artifact/snapshot reference. Persist no cancellation
objects, open resources, secret accessors or monotonic clock values.

Connections allocates run/root/correlation IDs. Each action owner allocates
logical action and first/next attempt before reservation. A changed request/new
model turn is a new action; an explicitly permitted retry retains action and
changes attempt. Event producers allocate event IDs once before append and reuse
them with frozen content for delivery retry. Native provider call IDs remain
independent and are never invented for standalone tools.

Storage commits reuse the supplied causal run/agent/action/attempt/parent/
correlation fields. The trusted caller allocates operation_id before mutation;
Storage allocates its publication event_id and receipt. No separate Connections
commit action exists. Distinct snapshot components may have subordinate operation
IDs; they do not become model/tool dispatch actions. A recorded digest is not
permission to execute an external action again.

Root/child run-root anchors are reserved through the shared identity preparation
boundary before binding, so preflight records have planned parent linkage.
Storage provisioning records linkage/scope facts, not an agent start. Container
alone emits `agent.started` and `agent.finished`; no additional accepted/start
lifecycle event is emitted for the same boundary.

On resume, revalidate definitions/grants/leases, restore trusted shared accounting,
reject expired/uncertain execution and rebuild a local monotonic timer from the
remaining UTC deadline capped by approved remaining duration. A restart never
renews the original allowance. Clock discontinuity or unresolved dispatched work
requires reconciliation, not a fresh ledger or a blind replay.

## 5. BindingSet, BoundSession and recorder bootstrap

`BoundSession = {binding: BindingSet, lease: ResourceLease}` is an async context
manager. Only its non-secret descriptor is serializable; the live set is restricted
to Runtime/Toolset/Connections consumers through the common protocols.

| Binding member | Meaning and ownership |
| --- | --- |
| `descriptor` | Binding ID/digest, schema version, registry/definition/config revisions and non-secret grant/limit references; deep immutable |
| `provider_factory/profile` | Container-owned selected provider capability and restricted configuration accessor; absent in standalone binding |
| `catalog/executor` | Toolset-owned allowed descriptor view and constrained executor; no arbitrary argv launcher |
| `storage` | Storage-owned scoped clients enforcing trusted grants on every operation |
| `recorder` | Owner/event-kind-restricted engine recorder; separate from agent business data grants |
| `invoker` | Connections allowed-destination facade for agent context; absent for standalone unless a future scope is approved |
| `identity_service`, `storage_plan_factory` | Trusted per-owner ID allocation and Connections plan binding for an actual tool attempt |
| `context_sources/limits` | Explicit allowed references/ranges and finite inherited limits; Container assembles context and owns accounting |

Registry definitions contain trusted module factory references, not arbitrary
import strings supplied by agents. The binder resolves selected references,
validates definition/schema/config/capabilities and computes attenuation before
acquiring module leases. It obtains only handles owned by those factories and
releases newly acquired leases in reverse order on failure.

Bootstrap avoids a circular requirement to bind Storage before recording bind:
Engine.open uses StorageSession.open(resolved_settings, trusted_issuer), obtains
the store-root lock and verified recovery/settings, then a restricted engine
control-recorder handle. An administrative host capability installs scope/run
facts; it is not a third ExecutionContext kind or an agent data grant. If this
startup fails, return its safe error, dispatch nothing and report recording
unavailable. No alternative file/logger is treated as durable engine history.
Connections passes the explicit DELETE/EXTRA baseline profile to Storage's
factory, which owns linked-runtime/settings validation and root locking. An
explicit opt-in WAL profile requires Storage's patched-runtime gate; binding
never silently switches journal modes. Hardware power-loss behavior is not
established by configuration presence or this design.

For a candidate run, provision its bounded run scope through StorageAdmin,
issue separate data and owner-recorder authorities, and create a binding action.
`binding.resolved` must return EventReceipt before the binding becomes usable;
`binding.failed` records a local rejection when Storage remains available.
Failure of either append is surfaced with its original event ID and recording
state; no recursive logging. Binding does not claim that Container accepted or
started a run. Bootstrap/provision/bound-handle factory details need the exact
Storage/PM protocol confirmation in R2.

Shared resources are application-owned with borrower leases. Session-owned
exclusive handles close with their last authorized borrower. Closing a child
BoundSession releases its lease; it cannot terminate a sibling's provider pool,
executor or store. Snapshot descriptors do not change these ownership rules.

## 6. Use, delegation, scopes, result export and shared limits

An AgentDefinition requests capabilities; it issues none. Each grant specifies
resource/profile/tool, operations, scope/object selectors, expiry, finite quotas
and whether/how much further delegation is permitted. Use differs from delegate.
Root authority = definition requests intersect trusted bootstrap policy. Child
use/delegation authority = destination requests intersect caller's delegable
rights intersect exact invocation edge intersect current policy and stricter
caller options. Match resource and operation; narrow selectors and take the
minimum applicable constraints. Required denial fails before child dispatch;
explicitly optional capabilities can be omitted with a recorded reason.

Model-profile use must be delegable for that destination; registering a privileged
writer never enlarges a researcher's rights. Tool names/revisions and outbound
agent edges remain explicit. Callers cannot delegate another child's acquired
rights unless the original lineage allowed that onward delegation.

Run scopes are tagged `run(run_id)`; shared scopes are registered
`shared(scope_id)`. Connections issues trusted bounded grants; Storage validates
issuer/store/principal/context and enforces them. StorageAdmin.provision_run
materializes the new scope only with explicit root/child scope-creation authority.
Provisioning itself grants no data access. Ancestry, correlation, a scope string,
a saved reference or a continuation cursor does not grant parent/shared reads.
Authorize before existence disclosure. Root/child scope quotas charge the same
ancestor ledger; child creation cannot obtain unlimited new storage allowances.

Input is validated bounded JSON by value. An input artifact/snapshot reference
requires an explicit destination read grant on that object/range. Output by
value uses only the declared validated result channel. For artifact-backed child
output, the InvocationRule requires explicit export authority and a bounded
caller destination scope; otherwise do not expose an unreadable locator as success.

Default export copies only the finalized validated result through existing
ArtifactStore.open and ArtifactStore.put interfaces: use a narrowly authorized
export context with source-object read and destination-scope write; allocate a
stable export operation_id; verify bytes/digest/media and retain the committed
receipt. This is Connections' invocation/export step, not another persistence
implementation. It reuses the parent invocation action/attempt and Storage emits
its own artifact publication event. Do not export arbitrary child state,
checkpoints or provider continuation. Object-only grant export is an optional
future policy, not an implicit parent right.

Export is normal bounded business work inside the parent deadline. If cancelled,
revoked or expired before export admission, perform no new copy/write; preserve
the child's known terminal facts and return the parent failure/cancellation.
An admitted copy/put follows Storage commit uncertainty rules. Authorized output
can be preserved internally as an observation even when the parent outcome append
fails, but incomplete recording cannot be exposed as fully successful execution.

Runtime's shared ledger reserves every operation atomically against all applicable
ancestor caps plus child-local limits. Children receive the same ledger handle,
not copies of remaining counters. Every dispatched retry/repair/child consumes
limits; release only known unused reservations. Unknown usage stays unknown;
unresolved dispatch retains conservative reservation. Hard cost guarantees require
supported conservative bounds; Connections does not manufacture usage or budgets.
Finite definition/root policy provides model/tool attempt, byte/time and storage
limits. Proposed invocation defaults are depth 4, at most 16 descendant
admissions and 4 active descendants, with stable-agent cycle rejection. These
may narrow; trusted policy can explicitly approve a different finite profile.
No hidden mission scheduler or autonomous fan-out is added.
These are API boundaries for trusted modules/registered workers. Arbitrary
Python code or a same-user executable is not OS-sandboxed by scoped facades;
normal engine paths nevertheless must retain grants, limits and recording.

## 7. Admission, child invocation and canonical outcome

InvocationRule binds exact caller/destination revisions, delegable rights and
onward edges, scope creation, child-local bounds and result-export selection.
Connections uses Container's validators and admission gate rather than validating
outputs or constructing another agent loop.

1. Check caller's active binding, destination/input, required capabilities,
   cycle/depth, current delegation grants and cancellation/deadline. Allocate
   invocation action/attempt plus a candidate child run; retain root/correlation.
2. Derive child metadata: parent run/action/attempt, destination identity,
   depth/ancestry and minimum parent/options/destination deadline. Materialize
   only authorized child scope and bind selected child dependencies.
3. Call Runtime.admit(definition, input, binding, child_context). Runtime validates
   and reserves the shared lineage limits; it returns a single-use expiring
   AdmissionLease or a typed rejection. Admission performs no model/tool work.
4. Freeze parent `invocation.intent`, including candidate child and binding/
   grant/limit/input references. Append and obtain EventReceipt. If receipt is
   unavailable/unknown, do not execute; reconcile its exact event identity.
5. Recheck deadline/cancellation/grants and consume only through
   Runtime.execute(admission_lease). Runtime atomically verifies lease/binding/
   identity/ledger, consumes once, records `agent.started`, executes its existing
   loop and records `agent.finished`. Reuse of a consumed lease cannot start
   another child. No Connections agent lifecycle event is emitted.
6. Observe Runtime's validated AgentResult; perform only authorized bounded
   result export; record parent `invocation.outcome` with dispatched/effect/
   child terminal/export/receipt/recording observations. Await its receipt.
   Runtime has already published the exact final provider-visible UTF-8 candidate
   and validated output representation through normal Storage before cleanup and
   agent.finished. JSON raw candidate and canonical validated output remain
   distinct. AgentResult includes output/raw refs/digests, persistence observation,
   obtained terminal receipt and authority-free terminal_state descriptor/ref;
   it is not stored self-referentially before obtaining its own receipt.
7. Release leases only when runtime/commit/recording ownership is settled.
   Connections never implicitly retries a child, model or tool.

Known nondispatch after a committed intent produces an outcome with
`dispatched=false`; no fictional child terminal is emitted. Release the lease
only when Runtime confirms it unconsumed/nonadmitted. Unknown consumption keeps
its identity/accounting and blocks resubmission. Runtime must own status/release
semantics; a missing durable child event alone does not establish nonconsumption.
Use the now-agreed Runtime.admission_status(context, admission_id) and
AdmissionLease.release() boundaries. Status is reserved, consumed/accepted,
terminal, released, expired or unknown, with known receipts. The live owner is
authoritative; process-loss history establishes only known facts, not a new live
lease. R1 requests exact shared DTO/peer conformance, not a replacement API.

`InvocationOutcome` proposal, using the common vocabulary: schema version;
caller run/action/attempt; destination; nullable candidate child run; admission/
dispatch observation; canonical execution status and safe error; child terminal
status/event/result references where known; authorized output or exported
reference/operation receipt; unknown-aware usage; recording status; effect/
commit/cleanup observations. AgentResult observation fields are output_delivery,
output/output_ref/raw_output_ref with digest/size/media, persistence_state,
admitted operation IDs, terminal_event_receipt and terminal_state. Rejected preflight maps to the relevant failed,
validation_failed or limit_exhausted result and records a nondispatch rejection;
it is not a new `rejected` agent terminal. Child output/terminal facts remain
separate if export or parent recording fails. Exact serialization is R1.

Parent cancellation propagates to child and active dependencies; child-local
cancellation does not cancel parent/siblings. Container alone arbitrates child
completion/cancellation and final status. A parent task cancellation initiates
bounded cleanup/recording and re-raises CancelledError. A completed child whose
terminal append failed stays a known completed observation with incomplete
recording, rather than being reclassified by Connections. Local interruption
does not prove remote provider cancellation or absence of billing.

## 8. Recording, uncertainty and revocation

| Operation | Canonical producer / identity |
| --- | --- |
| Binding resolved/failed | Connections binding action; nondispatch attempt may be null |
| Invocation intent/outcome/rejection | Connections parent invocation action/attempt; child linkage in payload/context |
| Agent/model/tool/validation/limit/cancel lifecycle | Container runtime; child run-root parents to exact invocation attempt |
| Artifact/state/snapshot/checkpoint publication | Storage; original causal context plus operation ID and own event ID |
| Standalone tool lifecycle | Same RecordedToolAction, producer runtime, context_kind standalone_tool; no model/agent/native-call ID |

EventReceipt is exactly v1: schema_version, store_id, event_id, recorded_seq,
recorded_at, duplicate. Successful return is the verified Storage commit;
Connections adds no alternate acknowledgement type, durability flag or sequence. Append a
frozen intent and obtain its receipt before external/read/worker activity.
Outcome recording and cleanup precede public success. Recorder append/query does
not recursively record itself; Storage publication and enclosing tool lifecycle
are different events, not duplicate tool outcomes.

After uncertain append, ActivityRecorder.status(context, event_id,
expected_event_digest) reauthorizes and reconciles the same frozen event. After
uncertain write, OperationStore.status(context, operation_id) reconciles the same
mutation/receipt. Do not change timestamps/content/event IDs for delivery retry.
These originator status/delivery rules retain the original producer and causal
identity under current authority. Fresh host observation of prior IDs instead
uses the read-only mode=observer grant in section 12; it cannot redeliver them.
An absent status observation does not prove no queued operation; require confirmed
nonadmission/rollback/durable abort before claiming not_committed. Pending/sealed
work remains unknown until its owner resolves. No status query fetches the URL,
resubmits a model request or launches a child.

`record_cleanup` is a separately bounded trusted mode preserving original
context kind/IDs with an owner-restricted recorder/status/lease-cleanup binding.
Use a fresh local cleanup token/deadline, initially at most 5 seconds and no later
than the enclosing shutdown allowance. It permits owner-event append, existing
operation/admission status reconciliation and lease cleanup only; no new model,
tool, scope/result export or business write. An expired work token must not
prevent this terminal audit attempt. Audit rights are separate from revoked
business grants; their narrow lifetime cannot revive execution authority.

Revocation authority is checked by Connections before bind/invocation admission,
Container before each model/agent admission, ToolExecutor before worker launch,
and Storage at each operation/publication gate. After acknowledged revocation,
new admissions fail. Already admitted remote calls/commits may finish; request
linked cancellation without a rollback guarantee. Previously returned bytes
cannot be recalled. Revocation and pinned immutable definitions are compatible:
the descriptor selects what may be used, while live authority decides whether
that operation remains allowed now.

## 9. ToolStoragePlan and standalone no-model composition

The trusted plan is a live capability, not authority reconstructed from worker
JSON. Connections creates it for an actual context/attempt via the bound plan
factory; RecordedToolAction supplies the owner-allocated tool action/attempt.
Its descriptor pins tool/revision, store/context/attempt, operation kind, exact
scope/object/range/continuation, finite limits, expiry and assigned mutation
operation_id. Public arguments cannot set reserved plan/authority/receipt fields.
The constructor-to-helper protocol is request R3; no Storage read occurs merely
to prepare the descriptor before tool intent.

| Plan kind | Allowed behavior |
| --- | --- |
| `none` for web.search, scholar.crossref.search and scholar.openalex.search | Bound search configuration/limits; no worker Storage access or publication rights |
| `snapshot_commit` for web.fetch | One complete validated SnapshotProposal committed into the exact prebound scope under the assigned operation ID |
| `read_injection` for document.read | Exact authorized SnapshotStore.read reference/range/byte cap/continuation; inject only the returned immutable DocumentSlice |

The snapshot_commit plan builder explicitly grants operation.status for its
assigned operation_id to the current owner under originator rules, matching
store/run/producer/action/attempt and receipt visibility. This permits exact-ID
reconciliation after an uncertain commit without a refetch or new operation ID.
It does not grant arbitrary status/history access. The worker receives neither
this live status authority nor Storage publication authority.

RecordedToolAction owns validation, reservation, intent/outcome and public
ToolResult. ToolExecutor owns prepare -> worker -> finalization observations,
process cleanup and ToolExecutionResult. Storage owns authorization, byte/index/
manifest validation, READY publication/receipt and recovery. Connections supplies
plans/leases, never performs worker parsing or snapshot persistence.

Fetch worker `phase=prepared` and exit zero establishes complete process output,
not publication. Executor validates the one private response and commits via
SnapshotStore.commit; the helper exposes success only after a READY complete
receipt and complete lifecycle recording. Worker-provided final snapshot refs,
receipts or scope changes are protocol errors. Public model context receives
bounded preview/reference/results, never the private raw bundle.

For read, the intent receipt precedes SnapshotStore.read and worker dispatch.
Forward any supplied continuation unchanged; Storage checks its immutable
snapshot/extraction/original range and current grants. Use tagged one-based,
end-exclusive lines/pages; preserve physical empty PDF pages, zero-line text and
zero-based UTF-8 offsets. Valid boundaries are 1 <= start <= end_exclusive <= N+1;
N=0 allows only [1,1). Never clamp or repeat a truncated first fragment. Toolset
validates the worker returned exactly the authoritative slice/locations; it cannot
invent data from another ref or expand a read. A cursor carries no authority.

Initial mediation profile is exactly v1: original 8 MiB; text 4 MiB; index 1 MiB;
provenance 64 KiB; stdin 1 MiB; fetch stdout 20 MiB; public JSON 512 KiB; stderr
64 KiB; JSON depth 32; read text 64 KiB and 200 lines/10 physical pages. Measure
one fetch before at most two concurrent fetches. All limits may narrow. Actual
wire escaping/base64 and decoded aggregate bounds both apply. Bytes/JSON depth
do not bound PDF expansion or peak RAM; Toolset must measure parent/worker memory,
max-fit/oversize content and Windows descendant cleanup before handoff. No
streaming service is silently composed if a required source fails those gates.

The standalone host CLI entry-point glue is PM owned; Toolset owns argument/worker
parsing. It calls Engine.open/settings and Engine.run_tool, which uses the same
Container RecordedToolAction. No independent standalone lifecycle logger or
producer is added. No provider is opened or selected; agent/native provider IDs
remain null. Engine may register static factories without initializing models.
Standalone obtains a fresh run scope and explicit configured grants for older
snapshots. If the store root is already owned, Engine.open returns STORAGE_BUSY;
attachment to an active engine or fallback store is outside this initial design.
Internal workers are unsupported direct entry points and reject missing or
malformed envelopes. Workers do not load dotenv or discover a database root;
parent-held bindings enforce Storage read/publication authority. A valid-looking
envelope does not authenticate its launcher or prevent forged direct invocation
by a trusted same-user command. This interface adds no launcher authentication
or OS isolation subsystem.

## 10. Complete interface-only sequence: researcher to child writer

This is a proposed consumer/runtime sequence, not execution evidence. Agent
names/profile aliases below are illustrative registrations, not verified local
service configuration. The example begins at v1's explicit Python invoker
boundary when strategy/Runtime elects to delegate; it adds no Connections scheduler.

1. Trusted host supplies EngineSettings with Storage/control authority, exact
   Container/Toolset/Storage factories and named profile `research_api`.
   Engine.open opens/recover-verifies real Storage, then control recorder. It
   registers researcher and writer definitions via Engine.register_agent.
   Researcher requests search/fetch/read, its private run scope and invocation of
   writer. Writer requests only the delegated model profile, document.read on
   selected source refs, its own bounded run scope and validated report output.
   Both require explicit rights; registration makes no network request.
2. Host calls Engine.run_agent(researcher_ref, typed_question, root_options).
   Connections allocates root run/correlation, trusted grants/shared ledger and
   finite deadline, provisions the root scope, binds selected dependencies and
   durably records binding.resolved. Runtime.admit validates/reserves, then
   Runtime.execute consumes once and records agent.started before real model work.
3. Researcher's Container loop uses its registered tools through
   RecordedToolAction. Toolset fetches real sources and commits complete snapshots
   through plans; Runtime receives only final ToolResult and immutable source refs.
   These are future real effects, not manually supplied result fixtures.
4. When the caller strategy/Runtime selects writing, it calls the bound
   AgentInvoker.invoke(researcher_context, writer_ref, typed_writer_input,
   stricter_options). Input contains selected saved refs/notes by value. The
   edge permits writer model use, object-specific snapshot reads, isolated child
   scope creation and result-only export into the researcher scope; no web.fetch,
   researcher state read or onward agent invocation is delegated.
5. Connections allocates parent invocation action/attempt and new writer run,
   retaining root/correlation and parent run/action/attempt linkage. It narrows
   deadline/grants/limits, provisions/binds writer, obtains Runtime admission,
   persists parent invocation.intent and rechecks authority before execute.
6. Runtime records writer agent.started and runs the same real provider/tool loop.
   document.read uses exact delegated SnapshotStore slices; limits charge the
   shared ancestor ledger. Runtime validates writer output, publishes any result
   artifact through Storage and returns AgentResult with agent.finished receipt
   or truthful recording/commit uncertainty. Connections does not validate the
   output a second time or emit a competing child terminal.
7. Connections exports only the validated report artifact: scoped open child
   result, scoped put in researcher result scope using the stable export operation
   ID, and committed receipt. It records parent invocation.outcome with child
   terminal/export facts, returns authorized output to the caller, then releases
   settled child leases. Researcher continues/finishes in its existing Runtime.
8. Engine.close stops admission, drains/cancels and records as below, then closes
   owned resources. Stored parent/child/tool/publication IDs remain inspectable.

Denial, exhausted root budget or missing writer profile fails before its external
work. After committed parent intent, known nondispatch records dispatched=false.
Cancelled/revoked export does not undo a completed child; uncertain admission or
commit stops replay and is looked up under existing identities. R5 asks Container
how its strategy/model dispatch selects this agreed invoker boundary; this design
neither invents an agent.invoke CLI nor claims that routing already exists.

## 11. Complete interface-only sequence: standalone saved read

1. Trusted operator supplies the existing store-qualified SnapshotRef and a
   configured read grant for its exact scope/object, plus lines [10,31),
   max_text_bytes <=64 KiB and optional immutable continuation. The argument
   reference/range requests access; only the live configured grant supplies it.
2. Host CLI calls Engine.open using non-secret Storage settings and bootstrap
   policy/factories. Storage acquires the root and validates/recover-verifies it;
   if already owned, return STORAGE_BUSY without attaching or creating another
   store. Open control recorder. Do not resolve a model credential or call
   ProviderFactory.open; no AgentDefinition is required.
3. Engine.run_tool(document.read_ref, arguments, tool_options) creates
   context_kind=standalone_tool with null agent/definition/native-call IDs, new
   run/root/correlation and finite deadline/ledger. Provision fresh run scope;
   bind only allowed catalog/executor, data/read authority and owner-recorder
   leases plus storage_plan_factory. Persist binding.resolved; no attempt-specific
   read_injection plan or Storage read exists yet.
4. RecordedToolAction allocates the actual logical action/first attempt, validates
   context/arguments and reserves their limits, then calls the bound factory.for_attempt to
   construct the read_injection plan for that validated action/attempt. Freeze
   tool.intent and obtain EventReceipt. Recheck gates. Only then ToolExecutor
   calls SnapshotStore.read with the original continuation
   and exact grant/reference/range/byte cap. Unauthorized/missing/range errors
   return a typed observation with no worker launch/content disclosure.
5. ToolExecutor injects the authoritative DocumentSlice in the single private
   UTF-8 WorkerRequest, starts only registered argv and enforces bounded pipes,
   timeout/cancellation and process-tree cleanup. Worker returns one prepared
   response matching the injected snapshot/extraction/range/text and advancing
   continuation. No raw store paths, credentials or worker-minted grants.
6. Executor returns ToolExecutionResult; the common helper completes cleanup and
   appends tool.outcome, producer runtime/context_kind standalone_tool. Public
   ToolResult is successful only with valid slice/worker observation and complete
   recording. The CLI prints that public result once; no extra runner logger,
   model response or fictional agent events are produced.
7. Engine.close releases the standalone leases and owned store last. A later
   read opens the same Store again with an explicit grant; its old snapshot and
   line/page references remain immutable. No network refetch is implied by read.

Cancellation after a successful read preserves that observation but cannot
claim a fully recorded success if terminal append fails. Task cancellation cleans
up/re-raises; explicit cancellation returns the canonical result. A guessed old
SnapshotRef or resumed cursor never creates a grant.

## 12. Fresh host/result access and complete baseline lifetime

PM accepted Engine.open_run_access as a normal host/application binding with
current explicit policy, a new deadline/quota and an owned lease. It does not
reactivate a finished agent, retain its expired capability, or authorize business
writes through record_cleanup. This resolves how application consumers obtain
the trusted context required by scoped Storage after Engine.run_agent returns.

```text
async Engine.open_run_access(run_ref: RunRef, request: RunAccessRequest,
                             options: RunAccessOptions) -> Result[RunAccessSession]
RunAccessSession.context -> ExecutionContext
RunAccessSession.storage -> ScopedStorage
RunAccessSession.history -> ActivityReader
RunAccessSession.identity_service -> ScopedIdentityService
async RunAccessSession.close(deadline) -> CleanupReport
```

| Type/field | Exact proposed semantics |
| --- | --- |
| `RunRef` | schema_version, store_id, run_id. Authority-free target identifier; Store resolves verified run/root/agent/definition association under current host policy. An arbitrary run ID never authorizes lookup. |
| `RunAccessRequest.read_objects` | Exact store-qualified report/raw/validated output, checkpoint/audit artifact refs and saved source SnapshotRefs, each with permitted range/max bytes as applicable. Empty by default. No implicit child/private continuation access. |
| `RunAccessRequest.history` | Optional bounded run/action/kind filters and explicit events.read request; only currently permitted visibility scopes. No global history enumeration. |
| `RunAccessRequest.publications` | Requested artifact.put/checkpoint.save operations into explicit already provisioned target scopes, purpose/media/format selectors and byte/count limits. Baseline presets allow citation manifest, terminal checkpoint and saved-output review copy. Requests grant nothing by themselves. |
| `RunAccessRequest.status_operations` | Exact existing event/operation identities to observe under a trusted read-only mode=observer grant. Current host policy pins target store/run, allowed IDs and receipt visibility; Storage validates target origin before disclosure. The request supplies selectors, never authority or original producer identity. |
| `RunAccessOptions` | Required finite timeout/deadline capped by current host policy; optional lower aggregate/read/write/op quotas; selected registered host grant preset; bounded application metadata. No credential, arbitrary authority or execution-resume flag. |
| `RunAccessSession.context` | Fresh binder-issued normal Storage context associated with the verified target run. New access/binding action ID parents to target run-root; no old model/tool/invocation attempt is reused. Nondispatch attempt is null. |
| `RunAccessSession.storage/history` | Only approved scoped Storage data/status/history capabilities. Prior-ID status uses read-only facades for the existing ActivityRecorder.status/OperationStore.status APIs, bound to mode=observer. Never raw database/root access or prior-producer append/delivery. Written objects become readable only under an explicitly granted created-output selector or subsequent fresh grant. |
| `RunAccessSession.identity_service` | May allocate stable mutation operation IDs for this authorized session. Cannot create agent admissions, execution attempts or grants. |
| `RunAccessSession.lease` | Engine-owned live access lease pinning store/config/current authority, deadline and I/O quotas. Async context-manager close is idempotent; admitted writes follow Storage settlement/cleanup rules. |

Closed interface-only DTO shapes (unknown fields/roles fail; common reference,
range/format/filter types retain their v1 definitions):

```text
RunRef = {schema_version: 1, store_id: StoreId, run_id: RunId}
RunAccessRequest = {
  schema_version: 1,
  read_objects: tuple[ArtifactReadRequest | SnapshotReadRequest | CheckpointReadRequest],
  history: HistoryReadRequest | null,
  publications: tuple[PublicationRequest],
  status_operations: tuple[EventStatusRequest | OperationStatusRequest]
}
ArtifactReadRequest = {kind: artifact, ref: ArtifactRef, range: ByteRange, max_bytes: int}
SnapshotReadRequest = {kind: snapshot, ref: SnapshotRef, range: DocumentRange,
                       max_text_bytes: int, continuation: str | null}
CheckpointReadRequest = {kind: checkpoint, ref: CheckpointRef,
                         accepted_formats: tuple[FormatVersion], max_bytes: int}
HistoryReadRequest = {filters: ActivityFilters, max_pages: int,
                     max_events: int, max_total_bytes: int}
PublicationRequest = {
  operation: artifact.put | checkpoint.save, scope: ScopeRef,
  purpose: citation_manifest | terminal_checkpoint | review_export,
  allowed_media_types: tuple[str], allowed_formats: tuple[FormatVersion],
  max_object_bytes: int, max_total_bytes: int, max_operations: int,
  read_created: bool
}
EventStatusRequest = {kind: event, event_id: EventId, expected_event_digest: Digest}
OperationStatusRequest = {kind: operation, operation_id: OperationId}
RunAccessOptions = {
  schema_version: 1, grant_preset_ref: PolicyRef,
  deadline_at_utc: UTCInstant | null, timeout_ms: int | null,
  max_total_read_bytes: int, max_total_write_bytes: int,
  max_operations: int, max_active_operations: int, metadata: JsonObject
}
```

The target RunRef applies to every status selector. Event/operation IDs and the
expected event digest are authority-free; the request cannot select an actor,
action, attempt or grant mode. The binder installs immutable mode=observer
status grants from current host policy, pinning target store/run, the exact
allowed event/operation IDs and permitted receipt visibility. No omitted selector
means all IDs. Storage validates the stored target origin against that grant;
it does not substitute the requesting host's new causal IDs for the original
producer identity or disclose a foreign origin/payload on a mismatch.

Exactly one deadline/timeout is supplied and finite/positive where applicable;
UTC deadline must be future. Quotas are nonnegative (zero means no operation in
that category), active-operation limit is positive, and all requested constraints
intersect the current preset. A baseline checkpoint allows only its registered
terminal format; review/citation artifacts permit explicit media types.
read_created is requested authority, not a receipt side effect. Newly written
refs are returned but only a granted created-output selector or new explicit
read grant makes them readable. No request enables state mutation, event append,
model/tool execution, native continuation export or scope creation.

Request lists have an initial local cap of 64 selectors per category and the
aggregate request has 64 KiB/depth-32 bounds; trusted settings may choose other
finite caps before binding. Omitted fields use empty tuples/null/empty metadata,
never all objects/scopes. Returned session stores an immutable effective access
descriptor with access_session_id, target RunRef, host principal/policy revision,
purpose, new binding action, expiry, effective quota/selector summary and the
read-only observer status bounds (target store/run, exact IDs, receipt visibility).
This descriptor is inspectable but not authority. Returned context/handles/lease are
live and nonserializable. A scoped client checks the selected read range, format,
purpose and quota at each use; client arguments cannot expand the admitted plan.
R2/R7 specify the module-owned facade/constraint enforcement handshake, including
the agreed observer grant and Storage target-origin validation.

Every selector/operation is intersected with the host bootstrap policy and current
revocation state. Reauthorize before object existence/status disclosure, at each
operation and on reopen. RunRef, AgentResult, terminal_state, digest and binding
descriptor contain no capability. A returned ref cannot add a permission.
Configured policy may authorize own-run result/source/history access; the fact
that a report was returned is not that policy. Source/shared scopes need their
own current grant, and guessed refs fail without disclosure.
The proposed StorageAdmin.describe_run(admin_context, run_ref) administrative
metadata read supplies verified context-kind/owner/root/agent/definition facts;
the Engine must restrict the lookup to its already authorized target/principal
predicate before any existence-sensitive reply. It cannot expose its bootstrap
administrative capability through the resulting session. This factory/read
handshake is included in R2.

Preserve the verified target's context_kind, agent/definition and run/root/
correlation association for Storage history. Issue a fresh live grant to the
host principal with purpose=result_access; binding.resolved records actor/purpose,
target root and new access deadline/quota. This is a host access action linked to
the completed run, not a new agent dispatch or an extended agent work deadline.
No new application/system ExecutionContext kind is required. The original agent
deadline/terminal facts remain unchanged; post-run publication records explicitly
identify the new host binding rather than pretending the agent performed them.

Observer status uses ActivityRecorder.status(context, event_id,
expected_event_digest) or OperationStore.status(context, operation_id) with this
fresh host context and its bound observer grant. It may return authorized original
receipts or pending/unknown facts. Never copy original actor/action/attempt IDs
into the host context, append as that producer, redeliver its event/mutation,
release its execution ledger/admission or replay execution. Observation does not
authorize a write. A new publication by this session has its own host-origin
operation ID and normal grant; its current owner retains the unchanged originator
status/identical-delivery rules for that publication.

Session I/O quotas are new bounded host-publication limits, not replenishment of
the finished Runtime execution ledger. No provider factory/profile, ToolExecutor,
Invoker or Runtime admission capability is returned. A session cannot start/resume
an agent or execute a tool. Current host authority is installed by Engine.open's
trusted policy; public request/options only attenuate it. If the target's terminal
status is unknown, result access can inspect explicitly authorized evidence but
cannot infer success, release uncertain execution accounting or resume work.

Allocate and persist binding.resolved for this fresh access action before returning
the session. If that append is unknown, preserve its original ID and reconcile;
do not hand out a usable new session. Reads do not need a fictional tool lifecycle.
Storage generates artifact/checkpoint publication records within normal commits,
reusing the access action and their own operation IDs. An internal recorder facade
is Connections-owner/event-kind restricted; the application cannot append
agent/model/tool lifecycle as producer runtime. History is read-only.

Each artifact/checkpoint publication uses a stable session-issued operation_id,
the current normal context/deadline and Storage's commit receipts. No write is
started after session expiry/cancellation/revocation. Already admitted work may
settle; bounded record_cleanup may reconcile/record it but cannot publish a new
manifest/checkpoint. A cancelled result session cannot roll back an already
committed report copy. Keep borrowed Storage ownership until unsettled operations
are resolved or retained by the supervisor. Closing this session does not close
the Engine store while other borrowers remain.

The terminal checkpoint is an application checkpoint format, e.g.
baseline_terminal/1, containing exact task/run/definition/config/flat-plan/source/
report refs, the final AgentResult status/recording/persistence observations and
its obtained agent.finished receipt plus authority-free terminal_state descriptor
or ref. It is saved after AgentResult returns. It neither embeds its own eventual
CheckpointReceipt nor grants resume. Native provider continuation/checkpoints
require their own separate restricted permissions; a baseline output grant does
not include them. CheckpointStore.load only retrieves data; Runtime owns any
future separately authorized resume decision.

Complete interface-only baseline sequence (future real workflow, not a report):

1. Engine.open uses shared factories and verified Storage/control recorder; host
   policy grants the baseline root profile and later exact result/source/history
   reads plus manifest/checkpoint publication. Register one flat research agent
   for the exact question What is EBD (Environment Based Design), named actual
   deepseek-flash profile, only the registered web.search, scholar.crossref.search,
   scholar.openalex.search, web.fetch and document.read tools, plus the platform-only
   search instruction/audit. This sequence does not schedule children.
2. Engine.run_agent returns a real AgentResult after Container's actual model/tool
   loop. Runtime must already have published exact provider-visible UTF-8 report
   bytes and validated output via normal scoped Storage before cleanup and
   agent.finished. Retain report/raw/validated refs/digests, request-audit/source
   refs, persistence observation, obtained terminal receipt and terminal_state.
   Do not publish a self-referential complete AgentResult before that receipt.
3. Call Engine.open_run_access with RunRef built from the obtained
   terminal_event_receipt.store_id and AgentResult.execution.run_id, exact
   requested objects/history/publications and new bounded host access options.
   The original agent BoundSession may already be closed or expired. The call
   checks current host authority independently; it never revives that binding.
   Request known prior event/operation IDs explicitly when receipt observation is
   required; current host policy creates exact-ID read-only observer grants.
4. Through access.storage and access.context, ArtifactStore.open the exact saved
   report/raw output and SnapshotStore.read the citation ranges under explicit
   grants. Preserve/verify their digests/UTF-8 bytes; do not replace them with text
   from an unrelated model buffer or live refetch. The application checks citation
   mappings against saved slices and publishes the citation manifest with
   ArtifactStore.put using a fresh stable operation ID and committed receipt.
5. Save the bounded terminal baseline checkpoint with CheckpointStore.save under
   normal access authority, after all its referenced objects/AgentResult receipt
   are available. Publication events are automatic. Record the returned manifest/
   checkpoint refs/receipts externally in the acceptance record; the checkpoint
   cannot contain its own not-yet-obtained receipt. Any failed/unknown publication
   leaves acceptance incomplete. Its current owner reconciles the same operation
   ID under originator rules; a later fresh host may only observe that ID under
   an explicit observer grant and cannot redeliver the earlier mutation.
6. An optional review-file export reads the persisted bytes through the granted
   artifact handle; the application/PM may write an authorized ignored review
   copy. That file is not an alternate store or replacement report. Close the
   access session, settle writes/receipts, then Engine.close in owner order.
7. Reopen Engine using the same verified store_id/root and freshly authorized
   host policy. No model registration/open/call is needed for these reads. Call
   open_run_access again requesting the exact report/manifest/checkpoint/source
   refs, bounded history and exact known event/operation status selectors as
   needed. Old session objects/grants/cursors and producer identities are not
   restored. Fresh observer grants pin receipt visibility and the target run.
8. Read identical report bytes/digests, CheckpointStore.load the accepted terminal
   format, and read the same cited immutable slices. ActivityReader.query starts
   a freshly authorized paginated history query; do not assume an old grant-bound
   cursor remains valid. Use the existing status APIs with the new host context
   and observer grants to inspect original receipts/pending facts; Storage checks
   target origin. Do not append/redeliver as the earlier producer or release its
   ledger. Check all receipts/status/recording and saved request
   audits. A changed/missing object, unknown commit, wrong model, unrecorded outcome
   or unsupported citation is failure/incomplete evidence, not permission to
   regenerate a report or refetch sources to conceal the durability fault.

Container's raw/validated result artifact schema, trusted actor/authority matching,
RunAccessRequest/session serialization and scoped facade factories remain R2/R4/R7
shared-type details. PM has accepted the public signature and lifetime/ownership
decision plus exact-ID read-only observer authority; these requests specify the
remaining concrete handshake, not a new authorization to implement. The flat
baseline does not replace child/standalone,
GPT-6-Luna, revocation, uncertainty or resource/shutdown module acceptance gates.

## 13. Resource shutdown and failure contract

Engine states are opening -> open -> closing -> closed, with cleanup_incomplete
reported if a live owner cannot settle. Engine.close(deadline) is idempotent and
stops new root/child admissions immediately. Default drain waits for already
accepted runs under original bounds and the supplied close deadline; they may
finish model/tool attempts during grace, but cannot admit a new child subtree.
A run needing another child receives SESSION_CLOSING. Deadline/grace expiration
signals cancellation; it is not authority for new business work.

Order: stop admission; request drain/cancellation through Runtime; let ToolExecutor
finish/reap processes and Storage settle admitted mutations; record known parent/
terminal outcomes through bounded record_cleanup; release per-attempt and
child/binding leases; close module-owned providers/executor after borrowers
settle; close Storage/control recorder last. The initial profile has no broker
resource. An unresolved admitted write/admission keeps its owner/root lock and
supervisor reference; do not close the store underneath it or advertise root reuse.
CleanupReport lists unresolved IDs/resources, primary/secondary failures and
observed remote/commit uncertainty. Process exit remains a trusted host decision,
not proof that a remote model stopped or that a filesystem/SQLite write rolled back.

| Failure | Required Connections behavior |
| --- | --- |
| Unknown reference/conflicting revision/incompatible schema | Safe typed error before binding/dispatch; no fallback dependency |
| Missing/invalid selected config | Name reference/key, never value; unused profile remains deferred |
| Denied use/delegation/scope/export | Fail required request; do not fabricate optional grants or expose child private output |
| Limit/cycle/deadline/cancellation | Narrow/reject through Runtime/owner gates; inherited ledger remains authoritative |
| Intent receipt missing/unknown | No new dispatch; exact frozen event/status reconciliation |
| Admission consumption unknown | Keep lease/run identity and reservation; owner lookup, no second execute |
| Commit reply lost/pending | Same operation/status lookup; no refetch/replay; preserve committed/unknown state |
| Outcome/terminal append fails | Incomplete recording with known facts; stop further dispatch; bounded cleanup only |
| Cleanup/close fails | Preserve primary outcome plus secondary safe error; retain unresolved owner/leases |
| Reused worker scope/receipt/plan mismatch | Protocol error; no public success or unrestricted Storage path |

Error envelope uses common code, sanitized message/details and observed effect;
Storage/delivery errors preserve commit_state/retryable_delivery. Advice to
retry delivery is not permission to execute. No Connections model/tool/agent
retry policy exists. Event/mutation delivery can retry identical frozen IDs/
content only under the owner contract and within a finite reconciliation allowance.

## 14. Conformance checklist and exact cross-team requests

| Common v1 requirement | Aligned location |
| --- | --- |
| Engine public signatures; module-owned composition | 1-2 |
| Sole schema_version, action/attempt/event/operation identities | 4, 8 |
| Canonical terminals/recording/commit/effect split | 2, 7-8, 13 |
| Explicit dotenv precedence, lazy selected profile, no incidental probe | 3 |
| Trusted metadata versus live authority | 4-6 |
| BindingSet/BoundSession leases and independent control recorder | 5 |
| Runtime.admit -> parent intent -> single-use execute | 7, 10 |
| agent.started/finished only; distinct parent invocation events | 4, 7-8 |
| Attenuation, child scope/export, common ancestor ledger | 6-7 |
| Revocation, uncertain admission/commit and record_cleanup | 7-8, 12-13 |
| Bounded ToolStoragePlan after actual ID allocation; exact fetch operation.status grant; prepared versus public success | 9, 11 |
| Runtime producer for standalone; no provider initialization; worker envelope does not authenticate launcher | 9, 11 |
| Fresh host result access; read-only exact-ID observer grants/target-origin checks; normal publication and close/reopen | 12 |
| Ordered shutdown; Storage retained for unsettled work | 13 |
| Root researcher -> child writer / explicit-grant saved read | 10-11 |
| Actual evidence separated from future acceptance | 15 |

The full design is aligned; the following precise executable-protocol details
still need PM/affected-owner confirmation. These are not permission to edit peers.

| Request | Owner / proposed minimum contract | Effect if absent |
| --- | --- | --- |
| R1 Admission/result DTO conformance | Container + PM: instantiate the agreed Runtime.admission_status(context, admission_id) -> Result[AdmissionStatus] and AdmissionLease.release() -> Result[ReleaseReceipt], bound lease IDs/expiry and observed states/known receipts; provide AgentResult preflight and InvocationOutcome serialization under the six common terminals | No safe automatic release/re-execute after ambiguous consumption; preserve unknown. Process loss never recreates admission authority; agree DTOs before source integration. |
| R2 Bootstrap/scope/scoped-handle factories | Storage + PM: confirm StorageSession.open(settings, issuer), StorageAdmin.provision_run(admin_context, RunDescriptor) -> Result[ScopeRef], StorageAdmin.describe_run(admin_context, RunRef) -> Result[RunDescriptor], owner-recorder and scoped-client factory accepting binder authority; define principal-filtered target lookup, purpose/object/range/quota enforcement, root lock/scope idempotency and orphan candidate-scope handling. Instantiate the agreed exact-ID mode=observer status grant with target store/run, allowed IDs, receipt visibility and Storage target-origin validation through the existing status APIs | Observer authority is read-only and does not impersonate the original producer or permit redelivery/ledger release; originator rules stay unchanged. No circular unrecorded bind, alternate persistence or scope-string authority; bootstrap fails closed. |
| R3 Plan/helper bridge | Container + Toolset + PM: publish bound storage_plan_factory.for_attempt(tool_ref, validated_arguments, ExecutionContext) -> Result[ToolStoragePlan] consumed by RecordedToolAction/ToolExecutor after helper allocation/validation of actual causal IDs; use none/snapshot_commit/read_injection, matching IDs and limits. snapshot_commit grants operation.status for its exact assigned operation_id to the current originator with receipt visibility | Do not construct an attempt plan before IDs, read Storage before intent, reimplement helper or let workers author grants/receipts. Status reconciliation never refetches. |
| R4 Result-reference DTO conformance | Container + Storage + PM: instantiate agreed output_delivery/output/output_ref/raw_output_ref, digest/size/media, persistence_state, terminal_event_receipt and authority-free terminal_state types; normal child-result open -> put copy under exact export authority/operation ID | Lifetime/publication decision is resolved. Export only validated output; separate raw/validated JSON; no native continuation or fabricated caller-readable locator. Existing Storage methods suffice for copy. |
| R5 Delegation selection boundary | Container + PM: specify the typed strategy/Runtime delegation request that calls bound AgentInvoker.invoke(caller_context, destination, input, options), including model-schema mapping if model-selected delegation is required | The interface-only call-and-result example is valid at the Python boundary; do not invent an agent.invoke CLI, hidden scheduler or claim model routing is implemented. |
| R6 Owner drain/cleanup leases | Container + Toolset + Storage + PM: publish finite cleanup/close reports and lease transfer semantics for admitted operations surviving caller cancellation | Keep supervisor/root ownership and report unresolved work rather than abandoning it or closing shared resources early. |
| R7 Accepted post-run access DTOs | PM + Storage + Container: instantiate the common Engine.open_run_access signature and exact section 12 DTOs/scoped field views, target-to-host actor binding and normal publication constraints. Enforce the agreed read-only mode=observer grant for requested prior IDs through existing status APIs: current host policy pins target store/run, exact IDs and receipt visibility; Storage validates target origin. Confirm this authority handshake with R2 | Signature/lifetime/ownership and observer authority are resolved. Fresh host context never copies original actor/action/attempt, appends/redelivers as that producer, releases its ledger or replays execution. No expired-grant reuse or record_cleanup business publication; new host action/deadline/authority required on use/reopen. |

Use the authoritative v1 target values/ownership while peers update their own
legacy signatures. Request changes centrally before constructing executable
shared types. No current user decision is needed for routine internal choices.
If representative required documents fail the bounded profile, PM should present
measured document-size/PDF-memory evidence and the explicit larger-transfer scope
tradeoff before adding IPC. Numeric bytes are acceptance targets, not RAM claims.

## 15. Actual verification, implementation plan and limits

Performed in this mission: read missions/common v1/contribution guidance and
peer interface excerpts, reconcile the entire owned design/status, and saved-file
QA described in the status report. Earlier primary-source design research covered
Python 3.11 deadlines/cancellation/IPC and python-dotenv loading. This revision
relies on the local common contract; it does not revalidate live package/service
behavior. No runtime source, tests or dependency/lockfile changes; no Git writes,
credential-file inspection, installations, provider calls or worker/storage trials.
Normal native Windows helper refresh fails; authorized read-only host inspection
has succeeded. Any unavailable check must be reported rather than inferred.

After explicit phase-transition authorization, implement Connections registry/
config, trusted context/grants and leases, Engine composition, plan binding and
child invocation by consuming PM's shared types and real peer modules. Next
consumer docs must contain actual uv run --locked entry points with configured
services/Storage and reproducible failure/cleanup evidence. Do not add another
loop, subprocess executor, database, scheduler or dummy provider to fill a gap.

Meaningful future checks: lazy profile/config errors without fallback; denied
bindings and owner-recorder kinds; real root/child/standalone composition;
concurrent ancestor-limit enforcement; scope creation/input read/result export
isolation; grant revocation at dispatch/publication gates; duplicate/expired/
unknown admission; exact-ID append/write uncertainty; cancellation before/after
commit and failed outcome recording; borrowed resource survival and ordered
close/root ownership. Toolset's max-fit/oversize/PDF expansion/peak-memory and
Windows process-tree checks are prerequisites to accepting the inline caps.

Provider verification belongs to later authorized Container integration using
real DeepSeek/GPT-6-Luna, with research internal/provider search disabled and safe
request/tool audits. Qwen config/adapter may be designed without deployment; local
Qwen live acceptance stays explicitly pending. A saved design, synthetic schema
example or unimplemented contract is not real integration evidence.
