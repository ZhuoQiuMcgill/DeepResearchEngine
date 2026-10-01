# Connections team status: v1 alignment

Date: 2026-10-01 (America/Toronto).
Phase: design alignment; implementation/API phase remains unauthorized.
State: full owned design and limited PM corrections completed for review/commit.
Owner: Connection Team, chat `01a0f546-f888-7353-b103-72f3f930fc79`, local.

## Completed mission

- Read missions.md, platform-contract-v1.md, CONTRIBUTING.md, the Connections
  brief, relevant peer interface declarations and baseline-acceptance.md.
- Replaced the whole legacy proposal with the common v1 composition/identity/
  authority/result/recording vocabulary; no competing commit action or duplicate
  agent start. Initial Storage bridge is bounded preparation/read injection/commit.
- Defined all Engine consumer operations, lazy dotenv/named-profile behavior,
  immutable BindingSet/BoundSession leases, control-recorder bootstrap,
  scope provisioning, use/delegate attenuation, child export and shared budgets.
- Aligned Runtime.admit -> parent invocation intent -> Runtime.execute(single-use
  lease), common admission status/release, exact-ID uncertainty, revocation,
  bounded record_cleanup and ordered resource ownership/shutdown.
- Specified ToolStoragePlan and the common RecordedToolAction producer runtime
  for standalone_tool, with no model/provider initialization or extra logger.
- Supplied complete interface-only researcher-to-writer and explicit-grant
  standalone saved-read sequences; neither is live execution evidence.
- Resolved the post-run consumer gap with PM: accepted public signature
  Engine.open_run_access(run_ref, request, options) -> Result[RunAccessSession].
  Section 12 defines closed request/options/session fields, fresh host authority/
  action/deadline/I/O quotas, owner-restricted recorder and no execution capability.
- Added the complete baseline run -> exact Runtime-published report read -> normal
  manifest/terminal checkpoint publication -> close -> reopen/read/history flow.
  AgentResult/RunRef/terminal_state are authority free; no expired agent grant or
  record_cleanup business writes; checkpoint is terminal evidence, not resume.
- Aligned the baseline with the selected registered web.search,
  scholar.crossref.search, scholar.openalex.search, web.fetch and document.read
  catalog. All three search tools use the none Storage plan without worker
  Storage access/publication rights. Platform-only search and fetched/saved
  citation evidence remain required; Toolset owns the exact scholarly schemas.
- Added a compact v1 conformance checklist and seven exact cross-team DTO/factory
  requests, distinguishing accepted semantics from uninstantiated executable types.
- Applied PM's four limited review corrections: baseline run ID comes from
  AgentResult.execution.run_id; standalone binds storage_plan_factory before the
  helper allocates/validates actual IDs and constructs the attempt plan; worker
  envelopes reject malformed input but do not authenticate a same-user launcher;
  fresh host status uses explicitly granted read-only mode=observer authority.
  Observer grants pin target store/run, exact IDs and receipt visibility; Storage
  validates target origin. No prior actor/action/attempt is copied into host
  context, no prior event/mutation is redelivered, no ledger is released and no
  execution is replayed. Existing originator rules remain unchanged; fetch plans
  explicitly grant operation.status for their assigned operation_id to the owner.

## Stable owned outputs

- `docs/teams/designs/connections-design.md`: complete aligned design 1.0.
- `docs/teams/reports/connections-status.md`: this full mission status.

Current writes remain these two paths. Future authorized ownership is
`src/ebd/connections/` and matching tests. PM owns shared types/CLI glue,
manifest/lockfile, baseline/integration and all Git mutations.

## Conformance summary

| Requirement | Design section |
| --- | --- |
| Engine APIs, central config, lazy selected profile | 1-3 |
| Common schema/IDs/live authority, BindingSet and recorder bootstrap | 4-5 |
| Delegation/scope/export/shared ancestor limits | 6-7 |
| Canonical recording, unknown status, revocation and cleanup mode | 8 |
| Bounded tool plan after actual ID allocation; exact fetch status grant; worker envelope limits | 9, 11 |
| Complete root-to-child consumer sequence | 10 |
| Fresh host result access, exact-ID observer grants and baseline close/reopen | 12 |
| Ordered close and owner retention | 13 |
| Exact shared requests and actual evidence limits | 14-15 |

## Cross-team requests to PM

R1 (Container/PM): instantiate the agreed AdmissionLease/release and
Runtime.admission_status DTOs, preflight AgentResult and InvocationOutcome fields.
After process loss, unknown consumption remains unknown; no live lease is rebuilt.

R2 (Storage/PM): finalize asynchronous Storage startup/provision/describe_run,
principal-filtered run association lookup, owner-recorder/scoped-handle factories
and purpose/object/range/quota constraint enforcement. Instantiate the agreed
read-only mode=observer grant for existing status APIs, pinning target store/run,
exact event/operation IDs and receipt visibility with Storage target-origin
validation. Observer authority cannot impersonate/redeliver as the originator
or release its ledger. No circular unrecorded bind.

R3 (Container/Toolset/PM): shared storage_plan_factory.for_attempt constructor
consumed by RecordedToolAction and ToolExecutor, matching owner-allocated attempt
IDs allocated/validated before plan construction, reference/range/continuation,
operation IDs and inline limits. snapshot_commit explicitly grants operation.status
for its assigned operation_id to the current originator with receipt visibility.

R4 (Container/Storage/PM): instantiate agreed output_delivery/output/raw artifact/
digest/persistence/terminal receipt/terminal_state types and child result-copy
eligibility. Publication/lifetime semantics are resolved; raw and validated JSON
remain separate. No native continuation export is implied.

R5 (Container/PM): typed strategy/Runtime delegation-selection request to the
bound Python AgentInvoker, including model schema mapping if model-driven selection
is required. No invented agent.invoke CLI or hidden scheduler.

R6 (all action owners/PM): exact finite cleanup/close reports and supervisor/lease
ownership for admitted mutations/execution surviving caller cancellation.

R7 (PM/Storage/Container): shared executable forms of the accepted open_run_access
surface and section 12 DTOs, target-to-host actor binding and normal publication
constraints. Enforce the agreed exact-ID read-only mode=observer status authority
from R2 using fresh host context, current policy and target-origin checks; no
original actor/action/attempt copying, append/redelivery, ledger release or replay.
Signature/authority/lifetime and observer semantics are agreed; executable forms
remain pending. Current owner originator status/delivery rules are unchanged.

These requests are precise integration inputs, not a blocker to delivering the
complete design or permission to edit peer/shared files. Semantic decisions that
PM has already resolved are not reopened. Any source-phase blocker must be reported
before guessing an incompatible protocol.

## Verification actually performed and limits

Read and reviewed authoritative local design/mission/acceptance files; checked
saved UTF-8/LF text, nonempty content, paired fences, sequential section headings,
local Markdown link targets, common signatures and removal of legacy vocabulary.
Reviewed all four corrections across request/session fields, plan construction,
baseline/reopen sequence, conformance and R2/R3/R7 authority agreements.
Read-only Git diff/whitespace checks cover only these owned paths. Evidence is
saved-document integrity/conformance, not runtime correctness or API feasibility.
The final QA summary/hashes are supplied in the PM handoff rather than embedded
as self-changing document hashes.

Native Windows sandbox helper refresh failed again. Reviewed host execution
successfully performed authorized read-only file inspection/QA. No files outside
owned paths were changed; no Git writes, source/tests, dependency/lockfile changes,
installations, `.env` inspection, model/API calls, workers or live Storage trials.
Earlier independent design reviews/primary Python/dotenv research remain design
inputs; no new subagents or live provider/package verification were used here.

Unverified: actual module factories/binding/admission behavior; scoped permissions,
output export, concurrent lineage accounting, status durability, revocation,
cancellation/close/root ownership, IPC/worker cleanup, PDF expansion/peak memory,
provider/account access and complete baseline persistence/audit. Qwen live
verification is explicitly pending deployment. No report/checkpoint/baseline run
has been generated by this Connections mission.

## Phase boundary and handoff

PM reports that automatic approval review rejected runtime implementation under
the earlier design-first instruction. A directly authorized phase transition is
still required before source/dependency/model work. The present design assignment
is complete; this team has not retried that blocked implementation action.

After saved-file QA and notification, freeze both ready-to-commit files until PM
confirms the commit or coordinates another revision. Continue ordinary internal
implementation choices only after that authorized phase transition, through the
shared uv/Python 3.11.15 environment and locked dependencies.
