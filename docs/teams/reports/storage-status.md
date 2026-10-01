# Storage team status

Date: 2026-09-30 (America/Toronto).
Phase: active design alignment; runtime implementation not authorized.
Revision: `storage-design-r3-v1`, limited coordinated correction, ready for PM QA/commit.
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
| Exact status | ActivityRecorder.status exact event ID/digest and OperationStore.status, with field/state/phase invariants. Absent observation does not prove no queued write. |
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

Completed now:
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

R3 saved-byte QA/hash computation was attempted with the shared locked/offline
uv command; native helper_unknown_error/setup refresh again prevented process
creation. No r3 checks ran and no current hashes were obtained. The historical
r2 hashes are not hashes of this correction. Do not treat prepared-text checks
as proof of revised saved bytes. PM will rerun QA before staging exact paths.

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
