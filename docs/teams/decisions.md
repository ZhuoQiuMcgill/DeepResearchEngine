# Platform decisions

PM owns this log. Team recommendations are proposals until resolved here
or by a later direct user instruction.

| Topic | Status | Decision / next step |
| --- | --- | --- |
| Environment | User decided | uv; Python 3.11+. |
| Tool boundary | User decided | CLI tools replace MCP. |
| Platform scope | User decided | Agent Container, CLI Toolset, Storage, Connections precede orchestration. |
| Provider targets | User decided | Real DeepSeek API, GPT-6-Luna API, local vLLM Qwen; local live testing pending deployment. |
| Current phase | User decided | Finish design; no runtime implementation yet. |
| First module priorities | User directed | Agent Container and CLI Toolset first; other module interfaces can be designed in parallel. |
| Shared contracts | Consolidated for review | `platform-contract-v1.md` resolves the four narrow reconciliation replies; runtime checks/phase authorization remain pending. |
| Search/fetch backends | PM selected for initial design | DDGS 9.16.0 best-effort search; HTTPX 0.28.1; Trafilatura 2.2.0; pypdf 6.19.0. Research-task search availability/URL fidelity remains a handoff gate. |
| Team chats | User opens | Leaders read specs, register, and report to this PM chat. |

Add dated entries with evidence paths, reasoning, affected contracts, and
remaining validation limits when PM resolves a proposal.

## 2026-09-30: Agent Container team registered

Verified chat `01a0f545-10ae-7b51-a754-3dc13e95a857`, host `local`,
title `Agent Container Team`, and its human startup prompt/workspace using
the app's thread reader. Its design and provider-capability research is in
progress; no implementation assignment has been issued.

Provider targets remain DeepSeek, `gpt-6-luna`, and vLLM/Qwen. The exact
DeepSeek model/thinking configuration and Qwen deployment profile remain
open pending the team's evidence and hosting requirements. They should be
explicit configuration/capability inputs, without blocking the common
interface proposal or silently substituting models.

Recording direction follows the existing shared brief: durable intent before
external dispatch; if intent persistence fails, do not dispatch. Outcome
persistence failure remains visible as a recording failure/incomplete
action and does not authorize automatic replay. Container and Storage
should propose the exact acknowledgment/error contracts.

## 2026-09-30: CLI Toolset team registered

Verified chat `01a0f545-ea04-71e3-965e-2c53d2d241d3`, host `local`,
title `CLI Toolset Team`, and its human startup prompt/workspace using the
app's thread reader. Search/fetch/PDF research and draft CLI contracts are
in progress. No backend is selected.

The team's scoped Storage proxy over private pipes is a candidate transport,
pending joint Storage/Connections review. The proposal must cover Windows
and standalone CLI use, protocol framing, bounded content transfer, failure
and cancellation, and the existing JSON stdin/stdout contract. IPC topology
is not frozen by this registration.

Storage snapshot publication should expose a complete original-content,
derived-text, and provenance bundle through a staging/finalization protocol.
SQLite metadata/event commits can be transactional; filesystem writes and
SQLite are separate durability boundaries. The design must explain recovery
and atomic visibility without claiming cross-filesystem/database atomicity.

## 2026-09-30: Storage team registered

Verified chat `01a0f546-8fc3-76f0-84fe-ffde8c2c89e5`, host `local`,
title `Storage Team`, and its human startup prompt/workspace through the
app's thread reader. Persistence/recording design is in progress.

Storage proposes an ephemeral loopback broker with short-lived scoped
capabilities delivered through stdin. CLI proposes a scoped private-pipe
proxy. Both are alternatives under review, not selected infrastructure.
Storage and CLI should compare the same criteria: Windows portability,
standalone launcher behavior, lifecycle/cancellation, bounded content
transfer, permission enforcement, failure/recovery, and setup complexity.
Connections will review binding and capability lifecycle after registration.
PM will reconcile the proposals without delaying web-tool research.

Container remains the canonical producer of top-level agent/model/tool
lifecycle events. Storage owns durable acknowledgment, event append
deduplication, scoped persistence, and artifact/state commit records.

## 2026-09-30: Connections team registered; transport review aligned

Verified chat `01a0f546-f888-7353-b103-72f3f930fc79`, host `local`,
title `Connection Team`, and its human startup prompt/workspace through the
app's thread reader. All four module teams are registered and designing.

Connections reviews common permission, binding, cancellation, and capability
lifecycle requirements across three candidate CLI storage transports:
private pipes, an ephemeral loopback broker, and launcher-mediated bounded
snapshot/read injection using the existing JSON stdin/stdout boundary.
Storage defines the operation/error/acknowledgment semantics; Toolset defines
executor/command behavior. None of these transports is selected yet.

Connections proposes a separate parent invocation action with intent/outcome
events linked to Container's child-run events. This matches the draft action
ownership direction; exact event names, lineage limits, and error contracts
still require reconciliation. Do not duplicate the child's run lifecycle.

Storage reported a potential SQLite WAL runtime-version requirement from
official docs. PM is independently verifying it before recording a gate;
the Python version alone is not evidence of the linked SQLite version.

## 2026-09-30: Shared contribution policy and SQLite evidence

The user requested a private GitHub repository under the existing
`ZhuoQiuMcgill` account and account-based attribution without a personal
email. GitHub API verified account ID `81338304`. Repository-local commits
use its GitHub noreply identity; existing CLI authentication handles remote
operations. `CONTRIBUTING.md` defines the common uv/lockfile environment,
assigned paths, and PM-only sequential Git operations in the shared checkout.

The existing workspace interpreter reports Python 3.11.15 and linked SQLite
3.50.4 (read-only metadata check). [Official SQLite WAL documentation](https://sqlite.org/wal.html#walreset)
confirms the reset race affecting multiple connections during overlapping
writes/checkpoints. The fix is in 3.51.3+, with documented 3.44.6/3.50.7
backports. Storage must propose a patched-runtime check before enabling
concurrent WAL, or explicitly justify a topology outside those trigger
conditions. No runtime upgrade, database change, or bug reproduction was
performed during design.

## 2026-09-30: Private repository initialized

Created `ZhuoQiuMcgill/DeepResearchEngine` as a private repository using the
existing authenticated GitHub CLI account. The shared branch is `main`;
initial local baseline is `7dafa7b`. Author/committer use the account-linked
noreply identity. `local/.env`, local configuration, caches/environments, and
downloaded package metadata were excluded. Active team outputs were left
outside the baseline. `.gitattributes` standardizes text line endings.

All four leaders received the contribution rules and a temporary document
write hold while PM publishes the baseline. Their read-only research can
continue; PM releases owned edits after verifying the remote and push.

## 2026-09-30: Free search/fetch combination selected

PM reviewed the complete research, saved public-source trials, primary
package metadata, and an independent review. Initial design targets:

| Operation | Component |
| --- | --- |
| Discovery | DDGS 9.16.0, replaceable best-effort development backend |
| HTTP retrieval/provenance | HTTPX 0.28.1 |
| HTML extraction | Trafilatura 2.2.0 |
| Text PDF extraction | pypdf 6.19.0 |
| Saved content reads | Storage immutable snapshot interface |

The stack ran on Windows/Python 3.11 in isolated real trials without required
API keys or a separate service. Eight retrievals succeeded across four
sources, including one 194-page PDF. This proves basic operation, not
arbitrary-site coverage, extraction fidelity, or memory enforcement.

Search returned results in five of twelve attempts across three queries/four
modes; every mode failed for the technical query. Reliable research coverage
is unproven. Use configurable explicit Google then DuckDuckGo initially,
record named backend outcomes, bound fallback, reject unsupported filters,
and expose outages. Avoid silent auto-merging and the zero-success Brave
profile. Representative-task availability and URL-fidelity checks must
precede teammate acceptance/experiments; those gates have not passed.

Preserve content-decoded original response bytes with representation/encoding
metadata, hashes, and extractor versions/options; derive text from the same
retained body. This does not claim wire-byte retention. Initial scope covers
static HTML, ordinary plain text and unencrypted text PDFs, without browsers
or OCR. Plain-text decoding/normalization uses the same retained HTTP body;
no additional fetch service or dependency is needed. PM explicitly aligned
this media choice with the common acceptance gate during mission review.

Local SearXNG was untested and one public request returned 429: greater
administrative control is supported, better reliability is not. The corpus
shows no necessary Requests/readability advantage. PyMuPDF's speed on one
PDF does not require its additional license/runtime decision for this scope.
Inventory the selected dependency/wheel notices before distribution; the
closure is not established as entirely permissive.

Evidence: `docs/research/free-search-fetch.md`,
[DDGS](https://pypi.org/project/ddgs/9.16.0/),
[HTTPX](https://pypi.org/project/httpx/0.28.1/),
[Trafilatura](https://pypi.org/project/trafilatura/2.2.0/), and
[pypdf](https://pypi.org/project/pypdf/6.19.0/) metadata.
This is a design selection. No production dependencies or source changed;
Storage transport, shared types/limits, and provider profiles remain drafts.

## 2026-09-30: Common interfaces and sustained team missions

All four leaders delivered narrow reconciliation replies. PM consolidated
their choices in `platform-contract-v1.md`: integer schema version, logical
actions/dispatch attempts/event/write identities, one Container-owned recorded
tool helper, distinct prepared/public results, launcher-mediated scoped snapshot
commit/read, async Storage receipts/status reconciliation, single-use admission,
bounded authority/leases and explicit DELETE/EXTRA baseline. An independent
boundary review clarified domain versus infrastructure outcomes, admission
lookup, root-action causality and the worker trust boundary.

The smaller initial mediation profile is a target pending actual encoded-byte,
parser-expansion, process-cleanup and peak-memory measurement. It does not claim
RAM enforcement or reliable search. Named backend fallbacks are bounded
observations inside one worker attempt; worker relaunch requires a new attempt.

The user directed PM to give teams sustained missions and explicit expectations.
`missions.md` assigns complete owned-design alignment now and whole-module
implementation/verification after authorization. PM owns shared contracts,
dependency integration, baseline acceptance and Git. All four leaders received
these missions through their verified chats, with exclusive paths and handoff
rules. The phase remains design: automatic approval review rejected starting
runtime/changing the phase due to the earlier design-first instruction. PM
has requested explicit phase-transition authorization against this concrete
design rather than retrying the rejected implementation.

## 2026-09-30: Result publication and post-run access

PM accepted Container's design choice to publish exact final provider-visible
UTF-8 content and validated representation before cleanup/agent.finished.
JSON retains raw candidate and canonical validated bytes separately; the final
AgentResult is constructed only after its terminal receipt, avoiding a
self-referential persisted result. Known failed publication and complete
recording are independent; uncertain publication or failed lifecycle append
remains explicit incomplete, without converting observations into success.

Fresh normal host/result-access authority owns post-run citation-manifest,
terminal-checkpoint and export operations. It cannot revive expired agent
grants or use record_cleanup for business publication. Connections owns the
exact public access surface and close/reopen consumer sequence. This is
interface agreement; the platform goal remains blocked pending the human
implementation/API phase confirmation after automatic approval review.

Connections proposed, and PM accepted for the shared design,
`Engine.open_run_access(run_ref, request, options) -> Result[RunAccessSession]`.
It binds fresh host-authorized Storage/history and publication access with
finite bounds/leases and no provider/executor/invoker/admission authority.
Binding audit distinguishes host principal/result_access purpose from the
verified target run/agent and links a new access action to that root. Reopen
reauthorizes; run IDs and saved results cannot revive old grants or budgets.

## 2026-09-30: Storage aligned design accepted

Storage handed off frozen `storage-design-r3-v1` in its two owned design/status
paths. PM read the complete saved design and independently reviewed identity,
receipts, publication/recovery, ranges and cancellation. One quota/dedup order
issue was corrected by the owner: current authorization and receipt visibility
precede exact-ID/content reconciliation; fresh-write quota/reservations/queue/CAS
apply only to new admission. The lost-acknowledgment/exhausted-quota case is an
explicit future acceptance vector, without consuming another write allowance.

Independent saved-byte QA passed using the shared locked/offline uv-managed
Python 3.11.15: strict UTF-8, no BOM, LF/final newline, paired fences and all
relative Markdown links. These files contain zero JSON-language examples.
Verified frozen hashes: design
`1645a48802d2e02eaf4587d12a686c7b663eda61b9ea6763eb2a0bd97b67bb51`,
status `9e4d78c8872b44dabffc8075ac5a48b338ee35a0d2b6163015c5c3689ccb0cda`.
The shared contract contains the same ordering rule. Design acceptance and
file integrity do not prove runnable Storage or its future fault tests.
Runtime implementation/API phase authorization remains pending after automatic
approval review; the platform goal remains blocked on that transition.

## 2026-09-30: Full handoff boundary reconciliation

Independent full-document review found four Connections/Container mismatches:
child export ordering, the nested AgentResult run ID, standalone plan construction
before actual action/attempt IDs, and an overstatement of direct-worker launcher
authentication. Owners received limited revisions; the shared contract now fixes
export before parent outcome, `execution.run_id`, plan factory then actual-ID
`for_attempt` before intent, and parent-held authority with no OS sandbox claim.

PM selected an explicit read-only observer status grant for fresh result access.
Existing ActivityRecorder.status/OperationStore.status stay the public APIs;
trusted binding pins exact store/run/event or operation selectors and permitted
receipt facts. Storage validates the original target origin while the requester
keeps its fresh host principal/action. This grants no producer impersonation,
append/delivery retry, business write, external replay, admission/ledger release
or broader scope. Current authorization, expiry/revocation/deadline and finite
read/status quotas still apply; business-write exhaustion alone cannot deny
authorized observation. Originator delivery/idempotency semantics remain intact.
Connections and Storage received the same limited revision, including positive
observer lookup and negative delivery acceptance cases. These are design
decisions only; runtime/API implementation remains blocked pending confirmation.

## 2026-10-01: Corrected full module handoffs accepted as designs

Container r3, Connections' full corrected design and Storage r4 are frozen.
Independent cross-module review found no remaining material inconsistency in
observer authority, quota-safe reconciliation, plan ordering, result run ID,
export ordering or worker trust boundaries. PM saved-byte QA passed strict
UTF-8/no BOM/LF/final newline, paired fences, local links and applicable JSON
examples. Connections/Container hashes matched the owners; PM computed Storage's
because its native helper failed before process creation.
The final catalog-reference delta updates Container/Connections to the five-tool
selection without changing their reviewed fields or authority/ordering rules.

| Frozen path | SHA-256 |
| --- | --- |
| designs/agent-container-design.md | e8fc9f8677251cc0bd2d35c6ab2d5d52d2e600873a3ccca2eca4dedf2b59c9b3 |
| reports/agent-container-status.md | 06d8ec55fcd86b9d0c396e85cdc4a61bb177125dc65719ddfe29141c366d3afe |
| designs/connections-design.md | 86bebaf6ef9801ef375ac98ea2f24ad68609c8dd2bc325adf09874ebf0b1cd2a |
| reports/connections-status.md | b2618be6705e10df91e1e7a37a76155285f9fe5cfbd75257e42379ae2f51047f |
| designs/storage-design.md | 5e360221f2689f8d036803f51c9b003ab66a2d95258ac05d77f6ad2db3a82e10 |
| reports/storage-status.md | 0acc216ec4128a9118433efdb390898e8658743ee11d3a5cdf35294b138afbb5 |

Paths are relative to docs/teams/. These checks establish design/file integrity,
not runnable modules, grant enforcement, durability or provider verification.
Each owner retains its complete implementation and verification mission after
phase confirmation; PM retains shared integration, baseline acceptance and Git.

## 2026-10-01: Expanded discovery selection

PM read the complete expanded CLI report, checked all three frozen document
hashes and both ignored evidence hashes, and obtained an independent full design,
evidence-summary and primary-doc review. Google/DDG returned 9/48 sets and failed
all 18 EBD searches. Yahoo returned 3/4 in one smaller pass; Crossref/OpenAlex
each returned three metadata responses, with explicit relevance/access limits.
These results justify changing the design candidate, not a reliability claim.

Retain DDGS 9.16.0, HTTPX 0.28.1, Trafilatura 2.2.0 and pypdf 6.19.0. General
web.search uses explicit Yahoo primary with its declared Bing relationship and
corrected Google as a bounded fallback, one call each per worker attempt. Google
stays disabled until its integrated URL-fidelity gate passes. Controlled parser
correction 4/4 does not establish live query coverage or availability. DDG is an
optional reviewed profile, without hidden auto/merge or unsupported filters.

Register separate scholar.crossref.search and scholar.openalex.search tools,
each with closed query/result-limit inputs, fixed provider, bounded anonymous
metadata response and no automatic paging/retry/query rewriting. Their closed
discovery-only schemas preserve DOI/work/publisher/landing/OA-location identities.
Relevant metadata is not verified source content; normal fetch/read still gates
citations. No mandatory paid API, new account/key or paid quota escalation is
selected. This does not claim zero operating cost or open-source search indexes.

Current primary docs confirm Crossref public access and list-query limit 1/s;
pace locally and honor narrower response headers. OpenAlex currently permits
casual keyless queries with 0.10 USD/day free allowance and 0.001 USD/keyword query.
Surface exhaustion/429; local bounds do not control unrelated callers or promise
remaining account/IP allowance. Source access/rights are separate from metadata.
Sources: [Crossref access](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/),
[Crossref July limits](https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137),
[OpenAlex authentication](https://help.openalex.org/api/authentication/),
[OpenAlex budgets](https://help.openalex.org/access/example-costs/).

CLI owns the coordinated schema/research/status revision and subsequent entire
module verification: repeated availability, Yahoo/Google URL fidelity, metadata
identity/relevance/quota behavior, real source follow-through and existing
recording/Storage/process/resource gates. Existing raw observations stay intact.
PM owns shared catalog-policy/baseline/brief alignment. This is design-only;
runtime/API phase remains blocked by the earlier automatic review rejection.
