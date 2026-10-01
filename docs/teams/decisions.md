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
| Shared contracts | Draft | Reconcile four team proposals before implementation. |
| Search/fetch backends | Research assigned | CLI team researches free, open-source candidates; PM selects after report. No backend chosen. |
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
