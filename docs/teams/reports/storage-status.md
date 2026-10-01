# Storage team status

Date: 2026-09-30 (America/Toronto).
Phase: design/research only.
State: design proposal completed for PM/joint review; shared contracts and
implementation approval pending. Revision: `storage-design-r1`.
Chat: `Storage Team`, `01a0f546-8fc3-76f0-84fe-ffde8c2c89e5`, host `local`.

## Completed work and owned outputs

- Read AGENTS.md, team README, shared-platform, coordination, Storage spec,
  all three sibling specs, current decision-log updates, and CONTRIBUTING.md.
- Registered with the verified project PM chat and followed its transport
  coordination and temporary repository-baseline document hold.
- Saved `docs/teams/designs/storage-design.md`: proposed signatures/results,
  shared scope/authority ownership, SQLite schema/migrations, CAS revisions,
  idempotent durable receipts, hook/event ownership, artifact sealing/recovery,
  composite snapshot/checkpoint publication, stable locations/bounded reads,
  operation status, cleanup/shutdown, pagination and acceptance plan.
- Saved this report at `docs/teams/reports/storage-status.md`.
- Three independent read-only reviews covered durability/recovery, CLI access,
  and contract consistency; substantive findings were incorporated.

Only those two Storage-owned documents were edited. No source/dependency,
lockfile/configuration/ignore, installation, database or Git changes were made
by Storage. No credentials were read, and no model calls were made. The workspace
now has the PM-created private Git repository; PM is its only Git writer.

## Recommendation and proposed contracts

Use SQLite for state/revisions/events/receipts/publication metadata and generated
immutable files for bytes beneath a configured private local root. One process
owns the root, recovery and writer; bound runs/workers share that owner. A second
standalone owner fails `STORAGE_BUSY` before dispatch instead of creating a hidden
store. Multi-owner fencing/attachment are later extensions.

Recommend explicit rollback journal `DELETE` with `synchronous=EXTRA` as the
initial profile. Optional WAL requires a checked patched linked SQLite release
and `synchronous=FULL`; never silently change the requested profile. Official
SQLite docs identify the WAL-reset race/fixes. PM separately recorded the
existing interpreter's linked SQLite as 3.50.4; Storage did not run that check.
[SQLite WAL](https://sqlite.org/wal.html#walresetbug),
[SQLite synchronization profiles](https://sqlite.org/pragma.html#pragma_synchronous)

Recommend launcher-mediated batch handoff for the initial three tools, pending
joint agreement. Worker emits a bounded internal snapshot proposal; ToolExecutor
uses the scoped Storage client and returns final public success only after the
durable snapshot receipt. Saved reads are pre-resolved through Storage and only
the authorized bounded slice is injected. Worker receives no database/root,
general grant or model credential. The proposal also compares dedicated private
pipes and ephemeral loopback, and specifies a transport-independent
snapshot commit/read/status/error contract for either proxy alternative.

The recommendation minimizes initial Windows setup for fixed operations;
its cost is larger base64/JSON transfer and unmeasured peak memory. Interactive
worker reads/writes would need the scoped proxy. Windows extra pipes need a
concrete handle/ACL/lifecycle adapter; `pass_fds` is POSIX-only. Public stdout
stays one final JSON result. [Python subprocess](https://docs.python.org/3.11/library/subprocess.html)

Container remains the engine agent/model/tool intent/outcome owner; Connections
owns bindings and parent invocation records; Storage owns state/artifact/snapshot/
checkpoint publication events. Standalone launcher ownership is explicit and
exclusive unless PM chooses a shared Runtime lifecycle wrapper. Event append
deduplicates identical IDs/content and acknowledges only committed persistence.
Failed intent prevents dispatch; failed outcome stops further external work and
reports execution outcome separately from recording status. Unknown outcomes
remain incomplete and never authorize blind replay.

State CAS plus versions/revisions/event/operation receipt commits in one SQLite
transaction. Artifacts persist expected size/digest in SEALED before rename and
READY/event publication. Composite reservations/child IDs are durable before
upload, permitting deterministic recovery. Cancellation cannot report a known
abort unless a durable ABORTED disposition prevents later publication. Files
and database are explicitly separate boundaries.

## Verification actually performed

- Repository/spec reads and primary-source research, with direct URLs in the
  design. SQLite, Python 3.11 and Microsoft documentation support technical facts.
- Read-only design reviews; draft section inspection through `rg` before the
  final revision; successful file-edit tool acknowledgments for saved revisions.
- No persistence prototype, crash test, transport trial, installation, live
  provider/tool check or model execution. Acceptance cases are future plans.

Final saved-file shell QA was attempted after PM released the hold. It did not
run: the native execution helper returned `helper_unknown_error: setup refresh
had errors` before process creation. Do not treat the planned section/fence checks
as passing. PM can read/verify the frozen files through its working host execution
before staging. This helper issue also affected reviewer follow-up file reads;
review feedback was reconciled using visible text and acknowledged patches.

## Unverified limits and decisions requested

Unverified: linked SQLite metadata independently by Storage; all proposed SQL/API
behavior; Windows root-lock/containment/handle/rename/abrupt-power-loss guarantees;
transport cancellation/shutdown; resource/concurrency performance; final saved-file
shell QA. Local vLLM/Qwen live validation remains pending deployment. Provider
continuation semantics and actual API integration belong to later authorized
Container checks. No shared contract is described as agreed.

PM decisions needed:

1. One shared context/grant/event/reference definition; cleanup-only authority,
   exact five-second grace and its revocation/shutdown handling.
2. Initial CLI transport, internal-worker vs public envelope, caps/normalization/
   page-map/range semantics and explicit standalone lifecycle owner.
3. SQLite profile/version gate, root owner and path/durability acceptance policy.
4. Event naming/paired-boundary rules and RecordingFailure result with Container;
   parent invocation vs child run remains distinct.
5. Retention/backup/cursor signing, checkpoint resume claim, approved package and
   dependency layout; completed-design user approval before implementation.

The design assignment is ready for review; remaining shared decisions are normal
reconciliation dependencies, not a claim of implementation readiness. Frozen
handoff paths: `docs/teams/designs/storage-design.md` and this status file. Do not
edit the ready-to-commit revision until PM confirms the commit or coordinates a
new revision under CONTRIBUTING.md.
