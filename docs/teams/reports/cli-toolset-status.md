# CLI Toolset Team status

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../../team-start.md)
> and the [current usage guides](../../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

Research observations: 2026-09-30 America/Toronto.
Complete PM-selected coordinated v1 design revision, ready
for PM review/commit. These three owned documents are frozen after handoff until
PM confirms commit or coordinates a revision. Runtime implementation is absent
and awaits the authorized design-phase transition.

## Stable deliverables

- [Full CLI design](../designs/cli-toolset-design.md): replaces competing older
  proposals with common v1 catalog/domain results, private prepared/failed
  worker protocol, parent ToolStoragePlan, acknowledged final results,
  same-response HTML/plain-text/PDF extraction, scoped READY commit and exact
  immutable read injection/ranges/cursors.
- [Expanded research](../../research/free-search-fetch.md): exact versions and
  license closure findings, prior comparative corpus, terminal separated
  named-engine study, controlled URL failures/correction candidate,
  plain-text probe and bounded Yahoo/Crossref/OpenAlex alternatives.
- This status: conformance, actual evidence, blockers and reproducibility.
  Only these owned files and ignored CLI scratch were edited. No source,
  shared specs, model/credential use, project manifests or Git mutations.

## Actual terminal research evidence

| Study | Observed outcome | Practical limit |
| --- | --- | --- |
| Earlier DDGS baseline | 5/12 returned across three cases/four modes | Earlier exploratory comparison, not representative acceptance |
| Historical Google/DDG selection | 9/48 calls returned; Google 6/24, DDG 3/24; all 18 EBD calls failed | Three 120s-separated runs in one host/time window; selected availability gate failed |
| Live URL audit | 53 Google raw wrappers preserved; no query-bearing destination among them; 43 result rows/28 distinct URLs | Live query fidelity missing; rank-one-only fetch coverage |
| Stock Google controlled parser | 1/3 exact expected targets; wrapped query lost and encoded target invalid | Fidelity gate failed; controlled method calls distinct from live searches |
| Raw-wrapper correction candidate | 4/4 exact controlled targets including nested destination escapes | Feasibility only; no implemented/live corrected adapter |
| Historical selected rank-one fetch | 9 fetches/9 responses, eight HTML 200 text, one 403 | Text presence and retained hashes, not full semantic fidelity |
| text/plain RFC9110 | 200, 502,941 original bytes; BOM removal/LF policy gives 502,938 text bytes, 10,785 lines; [1,201) 7,014 bytes | One strict UTF-8 same-body case; no Storage API proof |
| Other named DDGS | Yahoo 3/4 returned incl EBD broad; Mojeek 0/4, Startpage 0/4 | One pass, not uptime or proven independent indexes |
| Anonymous metadata | Crossref/OpenAlex each 3/3 HTTP200, five results each; Crossref EBD title matches 4/5 broad,1/5 niche; OpenAlex 0/5 broad,5/5 quoted niche | Scholarly scope/relevance differs; 200 alone is not usefulness |
| Alternative source follow-through | Four chains/five responses: two403, institutional HTML200,18-page OA PDF200 | Metadata discovery does not guarantee full text |
| Integrity | 13 expanded source bodies/10 nonempty extraction texts verified; separate plain-text hashes verified | Ignored captures only; not READY Storage/reopen |

Expanded total: 60 DDGS calls,12 returned result sets; six metadata requests,
14 source HTTP responses plus one plain-text response. DDGS internal HTTP
counts are unknown. All data is actual public research, no model/mock replies.
Windows text-mode LF expansion in research text captures was corrected offline
only after restored bytes matched the original computed hashes; original
bodies/outcomes were unchanged.

## Evidence paths and commands

All ignored paths below are relative to D:/Projects/DeepResearchEngine:

| Evidence | Path / SHA-256 |
| --- | --- |
| Selected run manifest | .uv-cache/cli-toolset-research/named-study-20260930/manifest.json |
| Exact selected inputs/outcomes/raw-link audits | .uv-cache/cli-toolset-research/named-study-20260930/evidence.jsonl; f6e0de7190a6f276f6036c1ace0e5d0dfd4114c069a0e8b8915d43dde919bd25 |
| Selected summary | .uv-cache/cli-toolset-research/named-study-20260930/summary.json |
| Plain-text metadata/original/text | .uv-cache/cli-toolset-research/plain-text-20260930/evidence.json, rfc9110.body, rfc9110.txt |
| Alternative exact queries/results/fixtures/fetches | .uv-cache/cli-toolset-research/alternatives-20260930/evidence.jsonl; fc4a4ec1e853a476319d5ac1a03bb590c6358193cd281ff72ffd3ae33cf687bf |
| Alternative API JSON responses/integrity summary | .uv-cache/cli-toolset-research/alternatives-20260930/*.json |
| All expanded source bodies/text | .uv-cache/cli-toolset-research/named-study-20260930/responses/ |
| Research scripts | .uv-cache/cli-toolset-research/named_study.py,plain_text_probe.py,alternative_study.py,alternative_followthrough.py,summarize_study.py,audit_evidence.py |

Actual calls use the existing uv-provisioned isolated interpreter:

```powershell
& '.\.uv-cache\cli-toolset-research\.venv\Scripts\python.exe' '.\.uv-cache\cli-toolset-research\named_study.py'
& '.\.uv-cache\cli-toolset-research\.venv\Scripts\python.exe' '.\.uv-cache\cli-toolset-research\alternative_study.py'
& '.\.uv-cache\cli-toolset-research\.venv\Scripts\python.exe' '.\.uv-cache\cli-toolset-research\alternative_followthrough.py'
& '.\.uv-cache\cli-toolset-research\.venv\Scripts\python.exe' '.\.uv-cache\cli-toolset-research\plain_text_probe.py'
```

Scripts append evidence; preserve output folders before rerun. Exact fixed
queries/options, UTC timings, package versions and per-outcome counts are in
the report/manifest. Offline summaries/integrity checks make no network calls.
Scratch environments never became project dependencies.

## Compact v1 conformance checklist

| Requirement | Complete design / present evidence | Not yet verified |
| --- | --- | --- |
| Catalog/domain results/version/IDs | resolve returns Result; execute returns ToolExecutionResult; final ToolResult by Container; sole schema_version1; exact record fields/closed argument schemas | shared types and runnable implementation |
| Private preparation vs success | prepared/failed worker, exact identity/exit mapping, no minted refs/receipts | subprocess schema/fault checks |
| Storage mediation | parent-held live plan; fetch validation/READY receipt; read authoritative slice injection | real grant/commit/read/reopen |
| Recording/uncertainty | intent before network/read/worker; same Container helper for standalone; outcome ack; same-ID status, no refetch | actual durable hooks/lost ack/cancel around admission |
| Immutable reads | one-based/end-exclusive, zero-unit/empty-page rules, UTF-8 partial spans and advancing continuation | real saved range/cursor/grant tests |
| Source scope | HTML/plain/text-PDF; strict charset/BOM/LF provenance from retained body | binary/conflicting charset/challenge/complex-PDF corpus |
| Smaller resources | 8/4/1MiB raw/text/index,20MiB fetch stdout,512KiB public,64KiB stderr/read,depth32 | encoded/escape max-fit/PDF expansion/peak RAM |
| Process cleanup | suspended Windows spawn into non-breakaway Job Object; bounded parallel drains/deadline/cleanup | actual root+descendant termination/reaping/handle checks |
| Web discovery | selected Yahoo/disabled-Google policy, explicit Bing declaration, <=2 named calls | Yahoo repeated cases/query/escape/plus; Google integrated gate and separate availability |
| Scholarly discovery | separate scholar.crossref.search@1 / scholar.openalex.search@1, closed payload/observation/error schemas, one anonymous request, local provider limits | identity/relevance/one-request/caps/403/429/quota/restart/source follow-through |
| Standalone/baseline | same recorded helper,no model; fresh scoped authority; public Engine consumption | complete real host and model-generated cited report |

Byte caps are enforcement targets, not RAM guarantees. One fetch must be measured
before <=2 concurrent; finite Job memory ceiling selection awaits real parent/
worker/job peaks and host budget. Real platform handoff cannot use mock execution.

## Selected coordinated profile and remaining gates

PM selected the revised design after verifying the prior frozen files/evidence
and obtaining an independent review. Package versions are unchanged.
The current five-tool catalog is:

| Definition, revision 1 | Selected bounded behavior |
| --- | --- |
| web.search | Yahoo primary with declared Bing relationship; corrected Google fallback disabled until integrated raw-wrapper fidelity passes; <=one call each, no auto/merge |
| scholar.crossref.search | Closed literal query/max_results; fixed Crossref endpoint, one anonymous metadata request, executor-local serial <=1/s with header narrowing |
| scholar.openalex.search | Closed literal query/max_results; fixed OpenAlex endpoint, one anonymous keyword request, local serial pacing and <=0.10 USD/day free allowance at 0.001 USD/query with remote narrowing |
| web.fetch | Same retained response for static HTML/plain/text PDF, parent READY snapshot publication |
| document.read | Exact authorized immutable Storage slice injection/echo |

DDG is optional reviewed configuration, not the default or hidden third attempt.
Scholarly payload/observation/error schemas are closed, provider-specific and
discovery-only. They retain DOI/work/member/publisher/landing/OA-location
identities and do not claim general web coverage, verified quotes or guaranteed
full-text access. Source evidence still requires real fetch and saved read.
No query rewriting, automatic pages/retry, paid escalation or key acquisition.

The exact private scholarly plan, endpoint/parameter mapping, 1 MiB transfer/
decoded body, <=30s total work and <=512 KiB public envelope are in the full
design. Both scholarly tools use the existing generic ToolExecutionResult/
ToolStoragePlan and Container recording path; no Storage publication grants or
model session. Both worker phases supply bounded remote header captures; only
the parent parses them and supplies authoritative quota observations.

Crossref pace and OpenAlex quota are shared across bindings of this owned
executor, not global provider/account controls. Remote observations can narrow;
429/exhaustion stops work without replay. Unknown dispatch consumes its reserved
local quota; restart must retain trusted accounting or fail closed under explicit
host admission policy. Old source captures and all failed gates are unchanged.
No new live probes/API/model calls or evidence files were created in this revision.

Still unverified:

- Repeated Yahoo representative/EBD availability and raw URL query/escape/plus
  fidelity. A single 3/4 pass is not uptime evidence.
- Integrated controlled/live corrected-Google raw-wrapper fidelity before
  enabling it, plus separate representative availability. Isolated 4/4 parsing
  remains feasibility only; historical stock Google failures remain failed.
- Registered scholarly provider identity, literal query/quote/Unicode/plus
  transport, exact projection, relevance/empty/null/oversize/malformed/error
  behavior and one-request/no-retry/no-page semantics.
- Crossref pacing/header narrowing/cancelled admission; OpenAlex remote/local
  limits, 403/429/exhaustion, uncertain dispatch/day/reset/restart accounting and
  no paid/key escalation. The future HTTP200-narrowing/failure-malformed/
  worker-local-forgery protocol vector remains unexecuted. Source follow-through
  must preserve blocked full text.
- Existing real subprocess/recording/Storage READY/reopen/read, cancellation
  around admitted commit/lost ack, max-fit/escape/PDF expansion/RAM and actual
  Windows root/descendant/drain cleanup, standalone integration and full baseline.
- Distribution license audit. Local Qwen live verification remains pending
  because no local service exists here; no model calls were made.

No additional generic helper/Storage API change requested; PM aligns the new
catalog in shared specs. Sustained implementation/verification stays with CLI
Toolset after direct human phase confirmation. This revision completes only
the coordinated design assignment, not runnable acceptance.


## Resolved final PM review finding

PM identified one success-path protocol gap: the closed worker observations
could carry HTTP facts but not the remote limits/costs needed for parent
admission after HTTP200. The limited correction adds required provider_limits
to both prepared and failed scholarly observations. Its 11 fixed allowlisted
header captures are nullable, bounded to 128 printable ASCII bytes each and
8 KiB together; duplicates/unsafe capture and malformed parsing remain distinct
from missing evidence and known zero. The parent alone validates/parses facts,
projects closed remote rate/interval/concurrency and USD/credit units/remaining/
cost/reset/Retry-After, narrows admission, and updates its authoritative ledger.
Workers cannot supply that parsed projection, local quota/reservation/grant/
admission state or parent-decoded quota values through Error.details.

Section15 now consumes that transport on both phases while preserving actual
HTTP failures and pessimistic dispatch accounting. A future vector covers
Crossref HTTP200 slowing/Retry-After, OpenAlex HTTP200 known-zero/higher-cost,
429/403 missing/malformed headers, and worker local-authority forgery. None of
these protocol branches was executed here. The shared SnapshotRef reference
remains a declared design reference, not runtime-resolved. No new generic
helper/Storage API, probe/scratch/evidence, source/dependency/shared/Git work.
All other reviewed policy, schema, result, range and resource semantics remain.

The prior frozen document hashes are historical, superseded only by this
coordinated correction; final current hashes go to PM after saved-byte QA:

| Historical owned file | Prior SHA-256 |
| --- | --- |
| CLI design | a1e785f372724153575df87f76a2d5f48e35ba50004ffd01300dd00288de6a59 |
| Research | d97dd5ad536eaa8ca9c402172dba1b21e806bad3eaee3867b65e7d9935101e0f |
| Status | a3c6d949bda47b7b2845cdfdf462d16cc8ff2077ceaabfd8b6d2ea5fc8804596 |

## Document verification and phase boundary

Owned documents use strict UTF-8 without BOM and LF. Parsed JSON schema fragments,
balanced fences and local links are checked by docqa.py. The two saved fragments
also pass read-only closed-object/required-field/internal-reference checks;
runtime schema/type/semantic validation, shared SnapshotRef resolution and the
new acceptance vector are not performed. Owned git diff --check
and dependency-hash checks are run for handoff. These verify documents, not
production/runtime acceptance. Exact final file hashes are supplied to PM
outside this status to avoid self-referential hashes.

pyproject.toml baseline: 054F4CE51130E1BBD8072FA3B3FFA40D2A3C77397016BFD45735CDD41234D7FD.
uv.lock baseline: 38CBB937D8DF92930FC872F65A57FB15FFD5E9F53CACFF7E7778C365B1FA7073.
PM is the sole Git/dependency writer. Automatic approval review rejected the
runtime phase transition under the earlier human design-first instruction;
this completed design/research remains within authorization.
