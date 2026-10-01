# Connections design proposal

Owner: Connections (`Connection Team`).
Date: 2026-09-30 (America/Toronto).
Revision: proposal 0.1, contract major 1 proposed.
Status: DRAFT for PM and module review. This is documentation, not an
implementation or an approved shared contract.

## 1. Recommended boundary

Connections resolves registered implementations into an immutable, constrained
binding for one run. It supplies configuration references, context propagation
and explicit call-and-result delegation. Container retains the real provider
adapters, context/model/tool loop, validation and runtime accounting; Toolset
retains command registration and process execution; Storage retains access
enforcement, durable state, artifacts and activity persistence.

Recommend launcher-mediated bounded Storage injection for the three initial
tools if PM/Toolset accepts the explicit snapshot/JSON caps in section 10.
Retain a capability-authenticated loopback broker for tools requiring dynamic
Storage operations or larger streaming transfers; compare CLI's private-pipe
candidate before settling the topology. Each is a transport to the existing
Storage interface. No model/tool backend, Python package layout or dependency is selected
here. PM must reconcile the proposal before user design approval.

## 2. Definitions, registration and compatibility

Propose these serializable definitions; immutable maps/sets are required in
memory, not merely a frozen outer object containing mutable dictionaries.

| Definition | Required fields |
| --- | --- |
| `DependencyDefinition` | `schema_major`, `kind` (`model`, `toolset`, `storage`), `name`, immutable `revision`, `implementation_id`, `implementation_revision`, supported contract majors, `config_ref`, advertised capabilities, ownership (`application_shared` or `session_owned`) |
| `RegisteredAgent` | Container-owned `AgentDefinition`, exact definition revision/digest, accepted contract major, named outbound invocation rules; no executable or secret supplied by an agent |
| `InvocationRule` | Exact caller/destination definition identities, delegable model/tool/storage capabilities, delegable downstream destinations, result-export grant, maximum child depth/duration/output, cycle rule |
| `ConfigReference` | Symbolic configuration identity/revision and allowed credential-key references; never credential values |

Implementation factories/objects are a separate trusted bootstrap registration,
owned by the corresponding module. A serialized definition cannot import an
arbitrary dotted Python name or supply arbitrary argv. Connections verifies
that a named implementation exists; it does not construct its HTTP protocol,
registered tool command or SQLite implementation.

Proposed public signatures (documentation only):

```text
ConnectionRegistry.register(definition, implementation_handle) -> RegistrationReceipt
ConnectionRegistry.register_agent(container_definition, invocation_rules) -> RegistrationReceipt
ConnectionRegistry.freeze() -> RegistrySnapshot
async ConnectionResolver.bind(agent_definition, context) -> Result[BoundSession, ConnectionError]
async ConnectionResolver.check_readiness(reference, mode, context) -> ReadinessReport
async AgentInvoker.invoke(destination_ref, typed_input, parent_context, options) -> InvocationOutcome
async ConnectionSession.close(mode="drain", grace_ms=5000) -> CloseReport
```

Registration/freeze are synchronous, local operations. Identical identity,
revision and content is idempotent; a changed definition under the same
identity/revision is `REGISTRATION_CONFLICT`. Duplicate trusted handles must
also agree. New revisions coexist. Freeze validates references, schema shapes,
cycle policy and interface majors against the bootstrap catalog, with no live
service calls. Required references must exist; registered optional provider
configurations may be explicitly unconfigured. A run pins a snapshot and exact
revisions, preventing mid-run replacement. New configuration requires a new
snapshot; existing sessions continue under their pinned version or are revoked
through explicit application policy.

First handoff: require exact supported major; permit additive optional fields
only when declared by that schema. Reject unknown permission/security fields,
unknown requested capabilities and unsupported major versions. Registry
snapshots are not a substitute for runtime grant revocation checks.

## 3. Binding contract and resolution

`BoundSession` contains a `BindingSet` and a lifecycle lease. It is an async
context manager. `BindingSet` contains:

| Field | Meaning |
| --- | --- |
| `descriptor` | Non-secret binding ID, contract major, registry/config/agent revisions and effective-grant digest |
| `model` | Container's provider factory/profile capability for the selected named configuration; Runtime opens its session using the restricted configuration accessor; no unguarded client exposed to strategy code |
| `tools` | Approved Toolset catalog view and constrained `ToolExecutor` facade |
| `storage` | Storage's own scoped handle, rechecking grants on every operation |
| `recorder` | Restricted owner/event-kind recorder lease from trusted host Storage bootstrap, distinct from agent data access |
| `invoker` | Connections facade exposing only exact allowed destination identities |
| `context_sources` | Explicit Storage/context references and read limits; Container assembles the context |
| `effective_permissions` | Non-secret granted capabilities and limitations, including delegation authority |
| `readiness` | Local-validation results and any separately obtained reachability evidence with timestamps |

The immutable descriptor is serializable. Live handles, secrets, tokens,
cancellation objects and resource leases are not. Descriptor digests exclude
secrets and transport tokens. Reopening a saved descriptor requires fresh
configuration/permission validation and leases; it cannot authorize access.

Resolution sequence:

1. Check pinned registry, Container definition validation, schema compatibility,
   deadline/cancellation and trusted execution authority.
2. Select only the agent's referenced provider, tools, scopes and context
   sources. An unused/unconfigured Qwen profile does not block API agents.
3. Compute effective permissions under section 5. Required capabilities denied
   or unavailable fail the entire binding; do not silently remove them.
   Optional capabilities may be absent only when explicitly optional in the
   definition, with an absence reason recorded.
4. Resolve required configuration keys through the central loader. Pass needed
   configuration to the implementation owner through a non-serializable secret
   accessor. Validate supported capabilities locally; do not substitute a model.
5. Acquire scoped module handles according to declared ownership. If any step
   fails, release only acquired session leases in reverse order. No model call,
   external tool execution or agent loop occurs during binding.
6. Append `binding.resolved` and await durable acknowledgment before returning
   a usable session. On failure append `binding.failed` where recording is
   available, containing references and sanitized reasons. Recording failure
   fails binding closed; report it separately if the failure event cannot be
   persisted. There is no recursive attempt to record recorder failures.

Bootstrap prerequisite: the trusted host first opens its configured Storage
instance and obtains a restricted control-plane recorder through Storage's
interface. This uses central configuration and module-owned startup, outside
agent binding; it is not an alternate persistence path. A recorder lease is
passed to the resolver so a provider/tool/scope binding failure can be logged
without depending on the failed capability. Storage registers candidate run
linkage for preflight events without claiming Container accepted that run.
If Storage itself cannot start or its required configuration is missing, return
the safe bootstrap error; no durable record is possible and no agent dispatch
is allowed. The system recorder is never exposed as an agent's broader grant.

Terminal recording and cleanup use an engine-only control context with a fresh
bounded cleanup deadline, referencing the original execution/action metadata.
It authorizes only the owner's event append, operation-status reconciliation
and lease/staging cleanup, not new model/tool calls or business data writes.
This avoids trying to append an outcome through an already cancelled/expired
execution handle. Storage must validate this distinction and event ownership.

Binding is an API boundary guarantee for normal engine calls. Trusted Python
plugins in the same process can access their process environment/files; this
does not establish an OS sandbox. All standard strategy paths use Container,
ToolExecutor, Connections and Storage hooks, rather than raw adapter handles.

## 4. Execution context and identifier allocation

Propose one shared type, defined centrally by PM rather than duplicated by each
module. Split persisted metadata from live execution controls.

| Persisted `ContextMetadata` | Rule |
| --- | --- |
| `schema_major`, `run_id`, `agent_id`, `agent_revision` | Required for agent execution; opaque IDs allocated by trusted engine services, not model arguments |
| `root_run_id`, `correlation_id` | Required; unchanged across the invocation lineage |
| `context_kind` | `agent`, `standalone_tool` or `system`; `agent_id`/revision may be null only for the latter two |
| `action_id`, `parent_action_id` | Action-scoped context; `action_id` required on dispatch/events, nullable before the run-root action is allocated; parent null only at the lineage root |
| `parent_run_id` | Null for a root run; caller run ID for a child |
| `attempt_id` | Null without an execution attempt; fresh ID per actual provider/tool retry under one logical action |
| `deadline_at_utc` | RFC 3339 UTC instant, required before binding/admission; finite root allowance comes from trusted bootstrap policy |
| `depth`, `ancestor_agents` | Root depth 0; exact ancestor definition identities, engine controlled |
| `permission_ref`, `limit_lineage_ref` | Durable policy/accounting references and versions, not authority derived from arbitrary strings |
| `application_metadata` | Optional bounded JSON, e.g. mission identifiers; never grants access |

`ExecutionControl` holds linked cancellation signals, the local monotonic
deadline, runtime accounting handle, live scoped permissions/leases and local
task handles. Never put it in stored JSON/checkpoints.

Connections allocates root/child run IDs through a shared ID service; the action
owner allocates its logical action ID and event IDs. Container allocates each
run-root/model/tool action; Connections allocates binding and parent invocation
actions; Storage allocates commit action/event identities under its agreed API.
The child run-root action has `parent_action_id = invocation_action_id` from
the caller run. Actions within the child parent to its run-root or originating
model action as agreed with Container. Child dependency calls retain the child
run/agent identity, correlation and narrowed grants. A transport PID is merely
execution detail, never an authorization principal.

Container's preparation/identity service reserves the run-root action anchor
before binding; Connections preflight actions can reference this anchor without
claiming the run was accepted. Storage permits this planned linkage for binding
events. A rejected preflight remains a rejected candidate, not an executed run.

Persist an absolute UTC deadline and checkpoint accounting version. On resume,
restore the ledger, revalidate grants, reject expired deadlines, and rebuild a
monotonic timer from remaining wall-clock duration capped by approved remaining
duration. Never persist/reuse a monotonic clock reading between processes.
Clock discontinuities on restart require conservative rejection or an explicit
resume decision; they must not silently renew the original allowance. Within a
live session, timing uses the event loop's monotonic clock. [Python event-loop
documentation](https://docs.python.org/3.11/library/asyncio-eventloop.html#asyncio.loop.time)

## 5. Permissions, delegation, result access and limits

Capabilities distinguish `use` from `delegate`; access does not imply authority
to pass it on. Definition permissions are requests, not grants. The trusted
bootstrap authority supplies root grants, policy revision and creation rights.

Root effective capabilities = definition requests intersect bootstrap grants
intersect application policy. Child effective capabilities = destination
requests intersect caller's delegable grants intersect the exact invocation
rule intersect current application policy and any stricter invocation options.
Intersection means matching resource and operation, narrower constraints and
the minimum applicable quotas; a wildcard never expands a concrete grant.

Use a shared revocation authority checked by Container before each model
attempt, ToolExecutor before each launch, Connections at binding/invocation
admission and Storage on each operation/before publication. After revocation
acknowledgment, newly admitted operations are denied. Already admitted remote
calls/commits may complete; linked cancellation is best effort without rollback
claims. A pinned snapshot cannot reinstate revoked grants. Previously returned
bytes cannot be recalled.

For each capability specify resource identity, permitted operations, scope,
read/write/output maxima and whether/how much further delegation is permitted.
Child-selected model configurations must be delegable as well as registered.
Child outbound agent destinations are similarly narrowed; the destination's
own invocation rules cannot replenish them. Optional caller options may narrow
grants/limits but cannot replace the engine's authority object.

Storage grants are exact Storage-issued scope handles with operations such as
`state.read`, `state.commit`, `snapshot.commit`, `snapshot.read`,
`checkpoint.read` and `checkpoint.save`, matching Storage's draft operation
names. Correlation IDs, scope strings and artifact locators
are not grants. A fresh child run scope requires explicit
`create_child_scope` authority with inherited storage quotas: Storage
materializes that scope and gives the child only approved operations. Without
that right, an agent requiring its own writable scope fails admission. Existing
shared scopes require explicit delegated grants; no automatic parent-store
visibility is implied by ancestry.

By default, invocation input is bounded typed JSON copied by value. Input
artifact references require explicit child read grants. A validated output
returned by value is the allowed result channel. Output artifacts require an
explicit result-export rule: Storage either grants the caller read access to
that specific finalized result or copies it into an authorized caller-readable
scope through its interface. A returned locator alone never opens the child's
other state/artifacts. Failed export produces a structured invocation failure
while preserving the child's actual terminal status.

Runtime owns a shared lineage ledger for model/tool/child admission counts,
concurrency, usage reservations and byte/storage quotas. All inherited ancestor
caps and the child's own caps apply simultaneously. Each action atomically
reserves applicable budget in this ledger before dispatch, then settles actual
known consumption. Children receive the same live ledger reference plus a
local restriction, not copied remaining counters. Counts already dispatched
are not refunded on failure; cancellation releases only unconsumed reservations.
Unknown token/cost usage remains unknown, retaining conservative reservation
until policy reconciliation, never recorded as zero. A hard monetary cap
requires a defensible provider-side/reservation bound; otherwise reject that
unsupported guarantee. Mission planning/budget allocation is application work.

Recommend first-handoff nesting defaults: maximum depth 4, maximum 16 accepted
descendant calls per root, maximum 4 active descendant runs, and no invocation
of a definition identity already in the ancestry chain. These are proposed
bounded defaults configurable downward by agents, subject to PM approval.
Runtime enforces counters/depth; Connections validates destinations/ancestry
and carries restrictions. Definition revision changes do not evade a cycle
check on stable agent identity. No hidden scheduling or automatic broadcasts.

Example (symbolic design data): caller can delegate `document.read` and
read-only scope `shared:sources`, destination requests these plus `web.fetch`
and unrelated scope `shared:finance`. The latter required capabilities cause
binding failure before child dispatch. If explicitly optional, the child binds
without them, with recorded reasons. Its new run ID does not increase the
parent's remaining model/tool limits.

## 6. Invocation result, admission and cancellation

`InvocationOptions` can request stricter timeout/output/permission bounds and
an existing invocation identity for status lookup; it cannot request silent
replay. Caller allocates a fresh invocation action for each new call.

`InvocationOutcome` fields: contract major, caller run/action IDs,
`child_run_id` (nullable before admission), destination definition reference,
`status` (`rejected`, `succeeded`, `failed`, `timed_out`, `cancelled`),
validated output or accessible output reference, optional child terminal event
reference, sanitized structured error, usage including unknown values,
`recording_status` (`durable`, `incomplete`) and cleanup status. The child's
terminal status remains separately preserved if export or parent recording
fails. Success requires validated child output, authorized export and durable
parent outcome acknowledgment.

Proposed execution sequence:

1. Validate caller session, destination rule and destination input schema. Check
   ancestry, cancellation, deadline and delegable grants before external work.
2. Allocate candidate child identity/context; child deadline is the earliest of
   parent deadline, requested timeout and destination limit. Bind only its
   selected dependencies. Input/grant/binding rejection records a Connections
   rejection/failure when Storage is available; no child execution starts.
3. Container's admission operation validates the bound input/context and
   atomically reserves the child-count/concurrency budget, returning a short
   live admission lease. This is preparation of the existing runtime, not a
   second execution loop. PM must agree `Runtime.admit(...)` and
   `Runtime.execute(admission)` or an equivalent atomic gate inside its public
   entry point. Release an unconsumed lease on all pre-dispatch failures.
   The lease is consumed once and atomically by runtime execution; concurrent
   reuse is denied. Expiration/shutdown before consumption releases reservations.
   A lost execute acknowledgment preserves the reserved identity and uncertain
   accounting until runtime reconciliation, rather than releasing possibly used
   budget or issuing another child. Rejected admission never emits a child
   accepted/terminal lifecycle.
   Runtime rechecks lease expiry, current grants, context/binding/ledger identity,
   cancellation, deadline and admission state on consumption. Reserve concurrency
   during preparation; settle accepted-child count only at actual acceptance.
   Container durably records its accepted/start boundary before child external work.
4. Connections appends parent `invocation.intent`, with the reserved child ID,
   destination, input reference, grant/limit/binding descriptors, and waits for
   durable acknowledgment. If append fails, release admission and do not call
   the runtime. Recheck cancellation/deadline immediately before dispatch.
   If this check fails after a durable intent, append a known parent outcome with
   `child_started=false`; do not leave a known non-dispatch looking ambiguous.
   If that outcome append fails, retain `recording_status=incomplete`.
5. Execute through Container. It emits child `run.accepted`/terminal events and
   all child model/tool actions. Connections awaits the validated result,
   applies result export, appends parent `invocation.outcome`, then returns.
6. Release child binding/admission leases after terminal handling; preserve
   incomplete recording/cleanup diagnostics. Do not retry the child implicitly.

Parent cancellation links to child and downstream operations; child-local
cancellation does not cancel its parent/siblings. Cancellation of the awaiting
Python task requests runtime cancellation and bounded cleanup; after handling
recording/cleanup it re-raises `CancelledError`, rather than pretending an
ordinary successful result. Explicit cancellation through the engine's signal
returns `cancelled` when the caller remains alive. Deadline expiration returns
`timed_out`. If child terminal completion was already durably established,
preserve it; otherwise Container decides the cancellation/completion race at
its authoritative terminal-state boundary and returns that result. Connections
does not independently recategorize the child's terminal status. Record remote
completion uncertainty.

Runtime/provider owns interruption of model requests; stopping the local wait
does not prove remote cancellation or absence of charges. ToolExecutor owns
terminating/reaping CLI processes and any registered descendant-process policy.
Storage governs whether a commit crossed its finalization point: cancellation
cannot roll back an already published artifact/state change. Cleanup uses a
separate bounded control-plane allowance; it never authorizes new model/tool
work after an execution deadline.

Python 3.11 supplies `TaskGroup` and `timeout_at`; cancellation must be handled
with cleanup and propagated, and awaiting cancellation can exceed the nominal
timeout. An `asyncio` task is not forcefully terminable arbitrary Python code.
The implementation needs explicit bounded module cleanup semantics in addition
to a timer. [Python task/cancellation documentation](https://docs.python.org/3.11/library/asyncio-task.html)

## 7. Error and retry contract

Expected connection/configuration/admission failures are typed results, not
unstructured provider exceptions. `ConnectionError` contains `code`, `phase`,
safe message, dependency/key reference, run/action/child IDs where allocated,
optional safe downstream error and `retry_advice` (`never`, `after_fix`,
`after_reconcile`). No advice automatically triggers a replay.

| Code | Meaning / behavior |
| --- | --- |
| `UNKNOWN_DEPENDENCY`, `UNKNOWN_AGENT` | Missing pinned registration; fail before dispatch |
| `INVALID_BINDING`, `INVALID_INPUT` | Invalid definition/config/schema; name the reference/field |
| `CONFIG_MISSING`, `CONFIG_INVALID` | Required key absent/empty/malformed; never include its value |
| `REGISTRATION_CONFLICT`, `INCOMPATIBLE_CONTRACT` | Conflicting revision or unsupported protocol/capability |
| `PERMISSION_DENIED`, `INVOCATION_DENIED` | Use/delegation/scope/destination denied; no prohibited action |
| `CYCLE_DENIED`, `LIMIT_EXCEEDED` | Ancestry, depth or shared admission/accounting denied |
| `DEPENDENCY_UNAVAILABLE`, `SESSION_CLOSED` | Resource absent, revoked, inaccessible or closing |
| `DEADLINE_EXCEEDED`, `CANCELLED` | Execution gate terminates under the propagated context |
| `CHILD_EXECUTION_FAILED`, `CHILD_OUTPUT_INVALID` | Runtime's validated child failure, preserving child reference |
| `RESULT_EXPORT_DENIED` | Child output artifact cannot be made readable under its export grant |
| `RECORDING_FAILED`, `CLEANUP_FAILED` | Action may have happened; surface incomplete state and reconcile |
| `CAPABILITY_INVALID`, `CAPABILITY_EXPIRED`, `PROTOCOL_INVALID` | Scoped CLI transport/grant violation |

Connections performs no model, tool or agent retries. Container/provider owns
visible model retries; Container/Toolset must agree actual tool-attempt policy.
Event append may resubmit the same event ID through Storage's deduplication
contract. Changing event IDs is a new record, not safe retry deduplication.
Storage transport write retries are limited to the exact same request/content
under the operation's documented idempotency contract. An unknown child outcome
is queried/reconciled by ID, never replayed because its waiter disappeared.

Raw exceptions, request headers, stdin envelopes, provider configuration objects
and stderr are not embedded in messages/events. Use allowlisted fields and
module error translation. Secret-value redaction is additional protection, not
the only protection against arbitrary diagnostic leaks. Programming defects
surface to the trusted host with safe diagnostics; they are not classified as
retryable provider failures.

## 8. Event ownership and recording failure

Event names below are proposed for Storage/Container reconciliation. Event
timestamps are UTC; Storage's committed sequence defines record order.

| Semantic event | Sole producer | Correlation |
| --- | --- | --- |
| `binding.resolved`, `binding.failed` | Connections | Binding action, candidate/root run, non-secret descriptors |
| `invocation.rejected` | Connections | Caller invocation action; no dispatched child |
| `invocation.intent`, `invocation.outcome` | Connections | Caller action and reserved child run ID; outcome references child terminal |
| `run.accepted`, run terminal, model/tool lifecycle | Container | Child run-root action parents to caller invocation action |
| State/artifact/checkpoint commit events | Storage | Authorized originating action and separate commit identity |

The distinct parent invocation intent is mandatory in this proposal. Container's
child `run.accepted` does not replace it: the parent authorization/dispatch must
be durably identifiable before the child starts. Parent invocation outcome and
child run terminal describe different operations; Connections cannot emit or
overwrite the child's terminal event.

Intent acknowledgment failure prevents dispatch. Outcome acknowledgment failure
returns `RECORDING_FAILED` with the known child outcome/reference and
`recording_status=incomplete`. Do not report fully recorded success. Host crash
after intent leaves a visibly unfinished invocation; recovery checks the child
identity and Storage history before any application-directed decision. It does
not infer whether the child ran from an absent event alone. Recorder unavailable
before an execution context exists returns a bootstrap error to the host;
durable recording cannot be claimed.

Context/config descriptors, safe input/output references, grants' non-secret
identities and child IDs may be recorded. Credential values, capability tokens,
authorization headers and credential-bearing URLs must never be recorded.
Storage append operations and internal transport reads do not recursively
generate activity. Snapshot finalization records a Storage commit event;
Container records the enclosing tool action once.

## 9. Central configuration and readiness

The central loader is the only engine loader. It explicitly reads the existing
workspace-relative `local/.env` when implementation is authorized; it performs
no upward/root/nested `.env` search and never rewrites that file. No existing
secret variable names or values were inspected for this design.

Proposed non-secret precedence, low to high:

1. Schema defaults.
2. Explicit bootstrap-selected checked-in non-secret TOML configuration (path
   selected by PM; no new file created during this assignment).
3. Allowlisted non-secret keys from `local/.env`.
4. Allowlisted process-environment keys present at bootstrap.
5. Explicit trusted bootstrap overrides for documented non-secret settings.

Credentials resolve by an allowlisted `SecretRef`: an explicitly present
process environment key overrides the same key in `local/.env`. Absent process
key falls back to that exact file. An empty/present invalid key fails rather
than falling through to another value. Credentials are forbidden in checked-in
config, agent input/definitions and command-line overrides. No arbitrary
environment key is forwarded to a provider/tool. Grant policy cannot be
expanded by agent options or unreviewed environment strings.

Parse `.env` into a private mapping without changing global `os.environ`, with
variable interpolation disabled for deterministic explicit precedence. Validate
missing, empty, null and malformed values separately. A candidate library,
`python-dotenv`, documents `dotenv_values` without environment mutation and an
`interpolate` parameter. This is a dependency proposal only. [python-dotenv
documentation](https://bbc2.github.io/python-dotenv/), [API reference](https://bbc2.github.io/python-dotenv/reference/)
Python 3.11 has a standard TOML reader, so non-secret TOML parsing need not add
a separate reader dependency. [Python tomllib](https://docs.python.org/3.11/library/tomllib.html)

The implementation owner resolves its secret accessor immediately before use
and owns authentication/provider request formatting. Scoped accessors cannot
enumerate other credentials. Secret wrappers must have redacted representations;
tracebacks/diagnostics cannot dump locals. Python cannot guarantee all copies
are zeroized; claim bounded exposure, not secure-memory erasure. Credentials
rotate by fresh bootstrap/config snapshot and explicit provider session policy.

Provider profiles use references for the specified DeepSeek API, GPT-6-Luna API
and local vLLM/Qwen targets. Exact DeepSeek settings and Qwen server/model/parser
requirements remain Container's research inputs. Do not inspect credentials or
call any model to verify profiles during design. API access and the local Qwen
deployment are unverified; Qwen live acceptance remains pending deployment.

Readiness reports distinguish:

| State/mode | Evidence and cost |
| --- | --- |
| `local_valid` | Catalog/contracts/required configuration present; no remote request or claim that the connection works |
| `unconfigured` | Named optional profile lacks required settings; required selected binding fails |
| `live_unchecked` | Local validation exists but reachability/account permissions have not been tested |
| `live_verified`, `live_failed` | Explicit timestamped owner-supplied real check and its scope; neither guarantees future health |

Binding defaults to local validation only. `check_readiness(..., mode="live")`
requires trusted application authorization and an explicit deadline/cost cap;
it delegates to the implementation owner. TCP/HTTP reachability does not prove
model/tool correctness. A model smoke request may be billable; never run it as
a side effect of registration. All actual execution failures remain typed even
after a previous successful readiness check.

## 10. Joint proposal: three CLI scoped-storage transports

### Initial-tool candidate: launcher-mediated bounded injection

For `web.search`, `web.fetch` and `document.read`, recommend this smaller
first-handoff candidate, conditional on joint acceptance of strict content caps.
It needs no additional listener, HTTP library, secret bearer or inherited
channel. The capability is a trusted launcher-owned scoped Storage handle plus
a per-attempt approved operation plan; no serialized grant can authorize itself.

Connections binds an immutable `ToolStoragePlan` to the registered tool
revision, run/action/attempt, Storage instance, allowed operation, approved
scope/object/range, quotas and deadline. Scope selectors are engine supplied;
the worker's JSON cannot change them. The plan is valid for one attempt only
and cannot enumerate data, widen ranges, create peers or reset quotas.
Toolset owns the plan's process-boundary adapter and calls Storage's exact
`SnapshotStore.commit/read` methods; Storage owns validation and receipts.
Container's common tool-action helper owns lifecycle recording around both
parent-side Storage work and the worker. Connections neither launches the tool
nor finalizes snapshots itself.

| Tool | Injected input and returned output | Storage authority |
| --- | --- | --- |
| `web.search` | Ordinary bounded arguments/results | No worker Storage operation needed |
| `document.read` | After durable tool intent, launcher calls scoped `SnapshotStore.read` with the validated reference/range, injects the bounded authoritative `DocumentSlice` in reserved stdin, and runs the deterministic registered worker | Exactly that snapshot/range; worker cannot ask for more or change snapshot identity |
| `web.fetch` | Launcher allocates stable commit operation ID; worker retrieves once and returns one bounded JSON response containing a private `SnapshotProposal` (original bytes, normalized text, index, provenance) plus preview/status; launcher validates and commits through Storage | Exactly one approved `snapshot.commit` into the prebound scope; no worker-selected store/path/scope |

Reserved fields: stdin `execution.storage_input` for an authoritative read slice
or fetch plan identity; stdout `storage_proposal` for fetch only. They are
outside model-visible tool argument/result schemas. No secrets, raw roots or
provider configuration are injected. Toolset validates a single response,
byte/digest/index/provenance bounds, declared operation/plan correlation and
canonical Storage format before commit. It derives the final agent-visible
`ToolResult` from the receipt, not from a worker's invented snapshot reference.
An untrusted/fake receipt supplied on stdout is rejected.

Fetch's exit code 0 means retrieval/extraction completed and a complete proposal
was emitted. It does not establish durable snapshot publication. The outer
ToolExecutor/runner returns successful `web.fetch` only after
`SnapshotStore.commit` returns a committed `SnapshotReceipt`. Snapshot-ref
fields in that final result come from Storage. The private response bundle is
never inserted into the model context or ordinary diagnostics; Container
records finalized refs, a bounded preview and receipt. An explicit range/read
result is bounded and may enter model context under the existing context policy.

Proposed injection profile: original bytes <=8 MiB; normalized text <=4 MiB;
location index <=1 MiB; provenance <=64 KiB; read text <=64 KiB and <=200 lines
or 10 pages; stdin <=1 MiB; fetch stdout <=20 MiB; stderr <=64 KiB. Binary
content uses base64 in the one JSON result. Serializer uses UTF-8 with ordinary
Unicode emitted directly and minimal escaping; the actual wire cap still
applies even when component caps pass. Lower root/tool/grant limits always win.
Oversized/unsupported documents fail explicitly before publication, rather than
truncating an original into a purported complete snapshot. PM/Toolset must
confirm these useful-but-smaller document limits against the research cases.

ToolExecutor drains stdout/stderr concurrently while enforcing wire-byte caps;
it terminates/reaps a producer that exceeds its allowance. Do not use unbounded
`communicate()` buffering for this adapter. Base64/JSON can create several
in-memory copies; cap concurrent fetches at 2 for this profile and validate
actual peak memory during the later Windows trial before accepting these caps.
The wire bound is a design constraint, not a proved process memory ceiling.
Python documents that `communicate()` buffers data in memory and that waiting
without draining output pipes may deadlock; the asyncio reader buffer `limit`
does not cap the total captured result. [Python subprocess buffering](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen.communicate),
[asyncio subprocess documentation](https://docs.python.org/3.11/library/asyncio-subprocess.html)

Worker death, nonzero exit, partial/invalid JSON or cancellation before parent
commit produces a typed tool failure and no snapshot publication. Complete bytes
received before cancellation do not authorize a new commit after the action's
deadline/cancellation gate. If commit was already admitted, Storage determines
its actual committed/unknown state and recovery; cancellation cannot undo it.
An admitted commit with lost acknowledgment is reconciled by the same stable
operation ID, never by refetching the URL. Parent death during Storage staging
uses Storage's existing seal/finalization recovery. Successful fetch data lost
before commit remains unpersisted; the interrupted tool action stays visible.

Standalone uses exactly the same trusted launcher/ToolExecutor/Storage adapter
and fresh scoped context. Direct internal worker invocation without the matching
injected plan/slice fails before work; no loader fallback or alternate store.
This is suitable only when Storage reads are known before launch and writes
are one bounded end-of-command bundle. It cannot satisfy arbitrary dynamic
Storage RPC or stream very large snapshots. Those requirements favor the broker
or private separate channel. No transport has been selected or trialed.

### Dynamic-operation candidate: scoped loopback broker

For dynamic operations, propose a session-owned Storage broker on `127.0.0.1` at an
OS-assigned port, with a private bounded HTTP/JSON protocol and per-tool opaque
bearer capability. The trusted engine starts it in-process; no persistent
public server, peer discovery or global reusable administrative token is needed.
Storage owns broker request validation, authorization and its normal commit
methods. Connections obtains a narrowed capability from Storage; ToolExecutor
alone launches the registered CLI and delivers its bootstrap envelope.

### Capability, delivery and correlation

Storage maintains a live server-side record: token digest, non-secret grant ID,
contract major, allowed operation/resource scopes, current authority revision,
run/agent/action/attempt IDs, expiration and local monotonic deadline,
process-launch lease, quotas, revocation state and owned upload IDs. Propose a
cryptographically random 256-bit token, opaque rather than a client-editable
signed claim. The broker authorizes from this server record, never from a scope
string or PID supplied by the CLI. The wire carries only token and grant ID,
endpoint and bounded context metadata, not store paths or model credentials.

Mint one token for a single tool attempt. Expiry is the earliest of run
deadline, tool timeout or 300 seconds proposed maximum lease. Long tools need
an explicitly larger approved limit; the CLI cannot self-renew. Revoke on exit,
cancellation, deadline, cancel-phase session shutdown or policy revocation.
Drain-mode close stops new independent issuance but leaves admitted attempt tokens valid
until exit/their own deadline or grace expiry; then revoke and cancel. A token is not
persisted, returned in ToolResult or copied to a child agent. Check validity at
each request and immediately before finalization. ToolExecutor reports the
actual PID after launch, before delivering stdin; record it as correlation only.
Loopback HTTP cannot prove which process possesses a bearer token.

ToolExecutor adds a reserved engine-only `execution` field to the single UTF-8
JSON stdin request. Container/model arguments cannot populate this field.
`arguments` remains the agent-facing schema; the executor validates then adds
context/storage bootstrap data. The command consumes the envelope and still
emits exactly one JSON result on stdout. Diagnostics go to stderr but may never
echo the envelope/token. Persist the redacted logical request, never the actual
transport envelope. Do not put the token in argv, URL query, environment or a
temporary file. Toolset must redact captured output with an allowlisted result
schema and token-aware sanitation before storage/model exposure. A compliant
registered tool is trusted to handle its short-lived token; this is not an OS
isolation guarantee against malicious installed code.

Illustrative redacted envelope (the token placeholder is not a usable secret):

```json
{
  "schema_major": 1,
  "arguments": {"snapshot_ref": "<opaque snapshot reference>", "range": {"kind": "lines", "start": 1, "end_exclusive": 41}},
  "execution": {
    "run_id": "<allocated run ID>",
    "action_id": "<allocated tool action ID>",
    "deadline_at_utc": "<UTC deadline>",
    "storage": {
      "transport": "loopback-http-v1",
      "endpoint": "<engine-supplied literal loopback endpoint>",
      "grant_id": "<non-secret grant ID>",
      "token": "<redacted ephemeral token>"
    }
  }
}
```

The dedicated client disables proxies/environment proxy discovery and
redirects; accepts only the supplied literal IPv4 loopback endpoint and exact
service path. Broker validates Host, rejects browser Origin/CORS requests,
does not enable cookie authentication or access logs containing authorization,
and exposes only fixed methods. Bind no wildcard/network address. Do not use
the general web-fetch client for this control channel.

### Proposed wire protocol and bounded content

Every request has protocol major, `request_id`, grant ID and operation body;
authentication is in the authorization header, never in URL/logged bodies.
Broker obtains action/context/grants from the token record. Any echoed context
must match that record. Response contains matching request ID, typed data/error
and any commit receipt. First handoff serializes one request per CLI capability
at a time; each request is independently bounded and interruptible.

| Fixed operation | Permission and semantics |
| --- | --- |
| `snapshot.begin` | `snapshot.commit`; approved scope/media metadata and declared size/parts; returns opaque staging ID |
| `snapshot.chunk` | Same grant/owned staging ID; part name, sequence, content digest and base64 chunk; duplicate identical sequence is idempotent, changed content conflicts |
| `snapshot.finalize` | Same grant; complete original/derived-text/provenance bundle, digests and lengths; Storage publishes once with its commit event and returns immutable snapshot reference |
| `snapshot.status` | Own authorized creation/read; resolve an ambiguous finalization using its stable operation ID, no new snapshot publication |
| `snapshot.abort` | Own staging only; idempotent cleanup; cannot delete finalized snapshots |
| `snapshot.read` | `snapshot.read`; opaque authorized snapshot reference, explicit normalized line or PDF page range and byte limit |

Do not expose unrestricted `state.commit`, event append/query, checkpoints,
filesystem paths, arbitrary SQL or all-artifact enumeration to a retrieval CLI.
Extra tools require separately declared operations and joint review.

Proposed initial bounds: 64 KiB decoded chunks; 128 KiB total HTTP JSON body;
64 KiB maximum returned UTF-8 read bytes; 25 MiB original content; 8 MiB
derived text; 256 KiB provenance; 1 active upload per tool capability; 1,024
requests per capability. All bounds intersect lower tool/run/grant limits and
consume ledger quotas. Base64 expansion is included in the HTTP body bound;
broker checks declared and actual lengths before decoding/writing. Read ranges
are tagged 1-based, end-exclusive `lines/pages{start,end_exclusive}`, following
Storage's draft; require a valid stored count/mapping. Storage defines normalized line semantics and authoritative
locators/digests. The response reports actual range, next location/truncation
and extraction version, without silently refetching live content.

HTTP bodies use explicit lengths; reject unbounded/chunked bodies in v1 and
unsupported major/operations. Requests have bounded connect/read durations no
longer than the remaining execution deadline. Uploads are Storage-owned staging
data through its API. Only complete verified bundles are published; metadata and
commit events are one SQLite transaction, while filesystem durability/recovery
is Storage's separate staging/finalization protocol. The CLI never writes raw
durable snapshot files or opens the database.

No automatic replay of ambiguous writes. Exact duplicate chunk/finalize request
IDs/content return the existing receipt under Storage's idempotency contract;
new content with an existing ID conflicts. If a finalize response disappears,
query status while the capability is valid; after revocation the trusted host
reconciles by operation ID through Storage. Cancellation revokes new admission,
aborts incomplete uploads after bounded in-flight work, and reports any commit
that had already passed finalization. Broker crash/expiry is a typed transport
failure. Storage's recovery owns orphan staging cleanup; no second store.

### Standalone path and comparison

Standalone means outside a model loop, using an approved tool runner. That
runner is trusted bootstrap glue: loads non-secret configuration/policy via
Connections, creates a real run/action context and scoped Storage session,
records intent through Container's common tool-action helper, launches through
ToolExecutor, records outcome and closes its broker/leases. It does not construct
an agent/model loop or choose arbitrary commands. A raw registered command
requiring Storage fails `CAPABILITY_INVALID` before retrieval if no valid
engine-issued envelope is supplied; it must not discover a store root or open
`local/.env` on its own. PM must approve runner name/layout after reconciliation.
Proposed future command shape is `uv run --locked <approved-tool-runner> ...`;
there is no runnable entry point in this design phase.

| Candidate | Benefit | Cost / first-handoff concern |
| --- | --- | --- |
| Launcher-mediated injection (recommended for the three initial tools, conditional on caps) | Existing stdin/stdout only, no bearer/listener/channel dependency; parent Storage checks exact input/read/commit; standalone uses identical adapter | One bounded whole snapshot bundle plus JSON/base64 copies; no dynamic worker reads/writes; successful worker extraction is not yet a durable tool result |
| Loopback broker (dynamic/streaming alternative) | Separate storage traffic preserves the one-request/one-result stdin/stdout protocol; ordinary sockets support Windows; chunk limits and standalone runner use the same transport | Listener/authentication/parser/client policy to maintain; bearer possession is authority, no OS peer attestation; loopback must remain excluded from web retrieval controls |
| Private named pipe / inherited separate channel | Private channel can reduce network exposure; Windows named pipes offer OS ACL/identity controls | Requires explicit Windows/POSIX channel adapters, launch/inheritance/framing and standalone bootstrap; stdin/stdout cannot also carry multiplexed Storage RPC without revising the tool protocol |
| Raw database/root paths | Simple bootstrap | Reject: unrestricted store exposure and access/recording bypass |

Windows subprocess handle inheritance differs from POSIX-only `pass_fds`, and
Windows asyncio pipe/subprocess support has specific event-loop constraints.
This supports a portability argument, not a live feasibility claim. A named
pipe remains a viable alternative if the CLI team supplies a complete separate
channel design. For named-pipe candidates using `multiprocessing.connection`,
use bounded `send_bytes/recv_bytes` with strict JSON, not object `send/recv`
that deserializes pickle. [Python subprocess](https://docs.python.org/3.11/library/subprocess.html#popen-constructor),
[Windows asyncio support](https://docs.python.org/3.11/library/asyncio-platforms.html#windows),
[Python connection API](https://docs.python.org/3.11/library/multiprocessing.html#listeners-and-clients)
PM, Storage and Toolset must agree the topology and protocol; no
code or interoperability trial has been run.

## 11. Resource lifecycle and shutdown

Registry definitions own no live resources. Trusted bootstrap owns shared
provider pools, ToolExecutor and Storage session/broker as explicitly registered.
Each BoundSession owns leases/scoped facades; exclusive resources belong to
that session. Closing a child binding releases its lease without closing a
shared provider pool/store/broker used by siblings. Connections never kills
tools directly or closes another module's borrowed handle.

Propose session states `open -> closing -> closed`, with failure details in a
CloseReport. Close is idempotent and forbids new independent bindings/invocations
immediately. `drain` allows already accepted runtime runs to finish existing
work under their inherited bounds; model/tool attempts and capability issuance
inside those runs remain allowed during grace. New child-run admissions are
denied after closing begins, so a run requiring another child returns a typed
closing/admission failure. This drains accepted work rather than admitting new
subtrees. `drain` waits for owned in-flight calls under existing
deadlines up to 5 seconds default grace; then requests runtime cancellation.
`cancel` requests cancellation immediately. A bounded 2-second cleanup allowance
follows grace; values require PM/module agreement and must not authorize new
execution. Runtime resolves child results; ToolExecutor terminates/reaps
processes; Storage finishes or reports commits; Connections records outstanding
invocation outcomes before releasing their recorder leases where possible.

CloseReport lists completed/cancelled actions, failed outcome persistence,
unconfirmed remote completion and resources still cleaning up. Resources with
live borrowers are not forcibly closed: keep the host shutdown supervisor's
reference until owners confirm release; report `cleanup_incomplete` and no new
work. Process exit is a final host decision, not a claim that remote effects
were stopped. Only the application owner closes shared resources after borrowers
finish: stop admission; drain/cancel runtime work; let Storage settle admitted
commits and ToolExecutor finish/reap processes; persist available parent outcomes;
release attempt and child/session leases; close broker/provider/tool resources
after remaining borrowers finish; close Storage/recorder last. Keep a draining
broker alive for active uploads/status queries until its owning attempts settle.

## 12. Verification plan and PM decisions

Current verification is document/primary-source review, independent design
reviews and saved-document structure/JSON-example checks, not executable platform
proof. No credentials inspected, runtime code installed, runtime source/dependency
changed or providers/tools invoked. Read the new root CONTRIBUTING.md and latest
shared guidance after PM's private repository baseline. Eventual implementation
uses the shared uv/Python 3.11.15 interpreter and locked manifest, with
dependencies/layout approved centrally; Python 3.11+ remains the support target.

| After approval: meaningful check | Required evidence |
| --- | --- |
| Bind a real API agent to configured model, actual CLI and durable Storage | Local validation distinguished from a real bounded execution and its receipts; pending authorized API smoke calls |
| Unknown/missing/denied required references | No model/tool/child dispatch and actionable typed errors |
| Permitted A invokes real B | Distinct child/run action linkage, typed validated output, single parent invocation and child terminal records |
| Concurrent siblings at inherited limits | Atomic shared ledger denies overspend; no budget reset with depth/revision changes |
| Scope/delegation/export denial | Parent/sibling references do not grant reads; child result artifact needs explicit export |
| Cancellation/deadline/shutdown | Local interruption/cleanup observed; remote completion uncertainty retained; siblings' shared handles survive child close |
| Selected CLI adapter plus standalone runner | Actual fetch snapshot bundle and bounded read; same Storage implementation; mismatched plans/grants denied; broker tokens tested only if that topology is approved |
| Interrupted/ambiguous finalization or recording | Complete artifacts only; status reconciliation; no duplicate publication or blind replay |
| Redaction/secret boundary | Dedicated synthetic secret/token leakage checks and inspected saved errors/events/diagnostics; no populated credentials in fixtures |
| vLLM Qwen | Connector contract/local validation only until deployment; live acceptance explicitly pending |

PM decisions requested:

1. Adopt/reconcile shared context metadata/control split, identity allocation,
   use-versus-delegate permissions, child scope creation and result export.
2. Agree Runtime admission/execution gate, shared lineage ledger and proposed
   bounded nesting/concurrency defaults; reconcile accounting checkpoint resume.
3. Settle distinct Connections invocation intent/outcome and Container child-run
   events with Storage's durable acknowledgment/error contract.
4. Choose bounded injection, loopback broker or fully specified private channel
   with CLI/Storage; agree reserved/private versus public reply schemas, inline
   or chunk quotas, finalization/status semantics and
   common standalone tool-action helper.
5. Approve fixed `local/.env` plus allowlisted process-env precedence, future
   non-secret config path/example placeholders and selected-profile readiness.
6. Reconcile current sibling differences: Container proposes fresh action IDs
   per retry; Storage proposes logical action plus mandatory attempt IDs. This
   proposal uses logical action/optional attempt IDs and requests one PM decision
   before freezing event uniqueness. Also reconcile `schema_major` versus sibling
   `schema_version`, `agent.started` versus `run.accepted`, exact grant/commit
   identity fields, and standalone producer (`runtime` helper versus trusted
   `standalone_driver`). No alias is assumed accepted.
7. Agree resource lease/close semantics, shared type/module layout and any
   dependencies before implementation. User design approval and explicit
   implementation authorization remain outstanding.

## 13. Sources, assumptions and limitations

Primary sources checked on 2026-09-30; technical claims are documentation findings,
not local execution observations. Permission rules, protocol bounds and lifecycle
choices above are Connections proposals. Sibling design reconciliation is pending
while the teams prepare their owned reports.

- Python 3.11 task/cancellation and monotonic event-loop documentation, cited
  above, support local timer/cleanup design. They do not guarantee remote abort.
- python-dotenv documentation/reference and Python tomllib, cited above,
  support explicit non-mutating configuration loading; no library installed.
- Python subprocess, Windows asyncio and connection APIs, cited in section 10,
  verify pipe portability, buffering and serialization concerns. Python's secure
  token generator is appropriate for a broker alternative; no token minted in
  this design. [Python secrets](https://docs.python.org/3.11/library/secrets.html)
- If HTTP transport is approved, `aiohttp` is a candidate implementation because
  its documented runner/site lifecycle supports explicit loopback binding and
  application request limits. It needs separately approved/pinned dependencies
  and explicit aggregate-byte accounting. [aiohttp server reference](https://docs.aiohttp.org/en/stable/web_reference.html#running-applications)
  Do not select `http.server` for the production broker: its own documentation
  limits its security checks. [Python HTTP server documentation](https://docs.python.org/3.11/library/http.server.html)
- Reviewed sibling `agent-container-design.md` and `storage-design.md` as they
  became available; adopted Storage's snapshot operations/end-exclusive ranges
  and Container's ownership of terminal status. Conducted independent reviews
  of context/accounting/shutdown and all three transport candidates. Cross-team
  agreements, feasibility, peak memory and interoperable code remain unverified.

At initial startup, before PM initialization, Git status reported no repository.
PM subsequently initialized the private repository and released its temporary
document-write hold. This historical observation is not the current repository
state. PM is the sole Git writer; this team performs direct document QA and hands
off stable owned paths without staging/committing. Native sandbox helpers later
failed refreshing; read-only saved-file QA ran successfully through the reviewed
host execution path. Only this Connections proposal and status are owned outputs.
No shared spec/decision/dependency files were
edited. No endpoint readiness, real interoperability, account access or API
credential correctness is verified. Local Qwen live testing is pending deployment.
