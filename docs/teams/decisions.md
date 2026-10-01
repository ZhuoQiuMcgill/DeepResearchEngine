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
