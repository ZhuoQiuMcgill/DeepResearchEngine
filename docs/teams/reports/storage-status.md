# Storage team status

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../../team-start.md)
> and the [current usage guides](../../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

Date: 2026-09-30 (America/Toronto).
Phase: active design alignment; runtime implementation not authorized.
Revision: `storage-design-r4-v1`, limited observer-authority correction, ready for PM QA/commit.
Owner: Storage Team, `01a0f546-8fc3-76f0-84fe-ffde8c2c89e5`, host local.

## Completed mission and exact owned paths

- Entire design revised against platform-contract-v1.md and the Storage mission
  in missions.md; CONTRIBUTING.md and baseline-acceptance.md were read.
- `docs/teams/designs/storage-design.md`: complete async APIs, exact six-field
  EventReceipt, canonical IDs/dedup, event/operation status schemas, CAS/tombstones,
  owned SQLite worker/DELETE-EXTRA settings, sealed/composite recovery, smaller
  mediated snapshot profile, exact empty-unit/UTF-8 range semantics, automatic
  hooks, checkpoint/history/close, conformance checklist and meaningful fault plan.
- `docs/teams/reports/storage-status.md`: this handoff and evidence record.

Only these two owned Markdown files were edited. No runtime/source/test,
installation, environment, credential, project dependency/shared-file or Git
changes were made by Storage. No model/API calls. The same uv/Python3.11.15/
lockfile environment remains the required future runtime.

## V1 alignment and completed decisions

| Requirement | Design disposition |
| --- | --- |
| Async context-first Result APIs | All 14 v1 operations retained; terminal close follows the exact lifecycle close(deadline) exception. Unexpected defects and Python task cancellation preserve common exception behavior. |
| Canonical identity | Logical action, fresh attempt before each dispatch, immutable event and preallocated operation IDs. Storage commits retain causal action/attempt; no extra commit action. |
| EventReceipt | Exactly schema_version/store_id/event_id/recorded_seq/recorded_at/duplicate. Ok means committed; no competing receipt or durability flag. |
| Exact status | Existing ActivityRecorder.status exact event ID/digest and OperationStore.status retain their schemas. Closed originator/observer modes separate original caller reconciliation from fresh host observation; exact target origin and full receipt visibility are checked before disclosure. Absent observation does not prove no queued write. |
| CAS/delivery | Current authorization/receipt visibility, then same-ID frozen content/origin reconciliation before any fresh write quota/reservation/queue/CAS. Exhausted write quota alone cannot deny an authorized existing receipt. New admissions alone reserve quota; tombstones and conflict semantics remain. |
| SQLite/root | Single root owner/owned worker, verified DELETE/EXTRA/FK settings, bounded transactions and explicit patched-WAL gate; no silent profile or interpreter switch. |
| Files/composites | Persisted seal and deterministic parent/child reservation IDs; READY/event/receipt metadata commits only after complete bytes. Incomplete and durable abort recovery are distinct. |
| Cancellation/shutdown | Known noncommit requires confirmed rollback/nonadmission/durable abort; admitted uncertainty retains owner/resources. Cleanup admits no new business writes. |
| CLI/standalone | Selected v1 bounded launcher mediation; Worker prepared phase is not public success. Runtime's shared RecordedToolAction is sole producer in standalone_tool context; no alternate driver logger. |
| Caps | Original8MiB/text4MiB/index1MiB/provenance64KiB/stdin1MiB/fetchstdout20MiB/public512KiB/stderr64KiB/depth32/read64KiB and 200 lines/10 pages. Encoded bundle checked separately; not RAM guarantees. |
| Empty/range units | Unit-specific counts, [1,1) for zero units, physical empty pages preserved, EOF empty ranges, explicit continuation input and minimum-next-codepoint error without zero progress. |
| Checkpoint/history | Immutable accepted-format storage, Runtime semantic resume ownership, fresh grants/timers, fixed-watermark pagination and scoped cursors. |
| Full baseline audit | Report/citation/request-audit/checkpoint/trace reads after close/reopen without refetch; broader fault/CAS/scope/resource gates remain required. |

These are design conformance claims, not implemented functionality or passed
module acceptance. Future owned implementation is `src/ebd/storage/` plus
matching tests after PM confirms the authorized phase transition.

## Actual checks and verification limits

Earlier completed design checks (r2):
- Reads of current mission/v1/contribution/baseline acceptance and existing owned
  designs/status; successful full saved-file update acknowledgments.
- Nine checks executed on the final prepared text held in session memory:
  all 14 APIs, exact EventReceipt fields, absence of competing receipt definition,
  paired fences, LF/final newline, smaller caps, no cleanup business-write
  admission, common standalone producer and baseline-audit reference. All passed.
- Base64 size arithmetic: combined maximum 8/4/1MiB components require
  18,175,324 encoded bytes before metadata/framing. Whole-envelope limits still
  apply; no runtime/memory enforcement was tested.

For r2, independent saved-byte shell QA was attempted using the shared
`uv --cache-dir .uv-cache run --locked --offline python` path. It did not start:
native execution helper returned `helper_unknown_error: setup refresh had errors`
before process creation. PM subsequently completed saved-byte QA through shared
locked/offline uv/Python3.11.15: UTF-8/no BOM/LF/final LF/paired fences/local links
passed; there were zero JSON blocks. These results apply to PRE-CORRECTION r2:

- Design SHA-256: e6aba65257f61277aad0053cfeae9d60d75b619679e1577717fbec9cf53b40e9.
- Status SHA-256: c1bc64c3158455511c0a5e1d4cc669e0e4fd8c88de0f44871a21b7fb68a400ee.

PM's semantic review found one material ordering conflict: the general admission
paragraph checked quota before deduplication. The coordinated r3 correction now
validates current identity/scope/operation/revocation/expiry/deadline/lease and
receipt visibility first, compares same-ID frozen origin/content, then returns
the existing receipt or identical pending disposition with no fresh reservation,
source consumption or write-quota charge. Fresh quota/use/queue/CAS checks apply
only to new admission. Current authority and finite delivery/status/read bounds
still apply; changed origin conflicts and revoked authority remains denied.

Added a meaningful future acceptance vector: a committed write exhausts its
quota, its reply is lost, and identical retry returns the original receipt even
though expected_version=0 would now conflict if CAS ran. It reserves/charges no
new write quota; changed-content and revoked-authority controls remain explicit.
This is a test plan, not an executed persistence test.

Storage's r3 saved-byte QA attempt failed before process creation due to the
native helper_unknown_error/setup refresh. PM then ran saved-byte QA through
locked/offline uv: UTF-8/no BOM/LF/final LF/paired fences/local links passed and
accepted/committed r3 at c061b29. Its frozen pre-r4 hashes were:

- Design SHA-256: 1645a48802d2e02eaf4587d12a686c7b663eda61b9ea6763eb2a0bd97b67bb51.
- Status SHA-256: 9e4d78c8872b44dabffc8075ac5a48b338ee35a0d2b6163015c5c3689ccb0cda.

These historical hashes do not identify r4. Current r4 saved-byte QA is recorded
below; prepared-text checks are not proof of saved bytes.

## Limited r4 observer alignment

PM selected the explicit read-only observer grant for fresh-host result access
because originating-only status authority conflicted with Connections'
Engine.open_run_access design. Both existing status API signatures and result
schemas are retained. No irreducible interface conflict remains.

- Closed trusted modes are originator and observer; caller arguments/descriptors
  cannot select a mode or impersonate the stored origin.
- Binder installs observer mode on the current host principal/action binding,
  under current policy/expiry/revocation/deadline/lease and finite status/read
  limits. Exact store/run/event or operation selectors, frozen target origin and
  full receipt visibility are required before existence/status disclosure.
- Event digest verifies an authorized target's content; mismatches conflict.
  A wrong target-origin selector or insufficient receipt visibility denies
  without existence/phase/hash/sequence leakage.
- Observer permits no append, delivery retry, new write, execution replay,
  ledger/admission release, scope expansion or automatic worker/RunRef/result
  grant. Receipt refs add no object/history permissions.
- Original originator behavior and reviewed r3 quota/dedup/commit ordering are
  preserved. Exhausted business-write quota alone cannot deny authorized
  observation within finite current status/read limits.

Added future acceptance cases for a fresh host observing old committed/pending
targets, observer-only delivery/write denial and origin/receipt-visibility/
digest/revocation/limit controls. They are meaningful planned cases; no runtime
persistence, grant enforcement or execution accounting test was run.

R4 prepared-text review passed 13 checks: closed modes, exact target selectors,
fresh caller identity, authorization-before-disclosure, event digest role,
read-only restrictions, no worker/automatic grants, preserved r3 quota ordering,
the three meaningful observer cases, all 14 APIs, exact EventReceipt fields,
paired fences and LF/final LF. These were session-memory checks, not saved-byte
or runtime evidence.

R4 saved-byte QA/hash computation was attempted through shared locked/offline
uv. The native execution helper failed with helper_unknown_error/setup refresh
before process creation, so no saved-byte checks ran and no final r4 hashes
were obtained. Successful patch acknowledgments confirm the two owned edits;
they do not substitute for byte-level QA. PM must verify final saved bytes and
compute their hashes before staging. The r2/r3 hashes above remain historical.

Historical evidence: PM confirmed r1 UTF-8/fence/JSON saved-file QA and pushed
the module drafts at 4210b8c. Prior official SQLite/Python/Microsoft research
supports the cited technical premises. PM recorded Python3.11.15 with linked
SQLite3.50.4; Storage did not independently query it. Those facts do not prove
r2 runtime behavior or Windows hardware power-loss durability.

Not run: SQLite initialization/profile/migration, real persistence/reopen,
CAS/scope tests, interruption/uncertain-commit recovery, Windows containment/
root-lock/close, actual CLI/provider integration or memory measurement.
These are explicitly planned module/acceptance gates, not replaced with mocks.
Local vLLM/Qwen live verification remains pending deployment.

## Blockers and handoff

Irreducible common-interface blockers for this design revision: none.
Routine internals are settled in the owned design; no competing shared API
has been introduced. New integration defects go to PM with affected consumers.

Remaining phase prerequisites: PM's shared executable types/composition/
dependency decisions and explicit authorized implementation transition.
PM reported automatic approval review rejected the earlier runtime transition
under the user's design-first instruction. Storage stayed within the current
authorized document mission and did not retry runtime startup.

The completed revision is frozen for PM: exact ready paths are
`docs/teams/designs/storage-design.md` and
`docs/teams/reports/storage-status.md`. PM is the sole Git writer. Resume edits
only after its commit confirmation or a coordinated revision request.
