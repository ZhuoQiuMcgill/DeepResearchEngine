# Agent Container team status

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../../team-start.md)
> and the [current usage guides](../../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

Owner: Agent Container Team. Revision: agent-container-v1-r3, October 1, 2026 (America/Toronto).
Status: complete owned design alignment for PM review; design/research phase only. Freeze these two owned paths after completed QA/handoff until PM confirms the commit or coordinates another revision.

## Completed deliverables

- [Whole Agent Container design](../designs/agent-container-design.md): replaces the earlier competing interfaces with platform contract v1 throughout, rather than appending a reconciliation note.
- This status records completion, actual checks, shared consolidation requests and the limits of the evidence.

The design defines closed AgentDefinition/input/output/context/error/limit schemas; exact ModelRequest/ModelResponse and native continuation/audit; AgentResult with raw/validated output refs/media/digests/operation observations and actual terminal receipt; single-use Runtime admission/status/release; committed intent before every model/tool dispatch; and one Container-owned RecordedToolAction for agent/standalone producer=runtime. It adopts integer schema_version=1, required dispatch attempts, parent invocation action AND attempt, six execution terminals, independent recording/commit/effect, EventReceipt and context-first Storage/status.

It covers bounded context/native history, batch preflight, counts/unknown usage/strict-budget gates, cancellation/task-cancellation distinction, finite cleanup/owner retention and no record_cleanup business writes. Provider profiles/configuration are mapped to primary official documentation: exact GPT-6-Luna Responses, requested DeepSeek V4.1 Flash/deepseek-flash Chat and explicit vLLM/Qwen manifest with native protocol differences. Future actual API/tool/storage/permission/resource/reopen acceptance is specified; no synthetic example is labeled execution evidence.

PM accepted Runtime automatic publication of exact final visible-content UTF-8 bytes and separately canonical validated JSON before cleanup/agent.finished. Runtime constructs the final AgentResult only after its terminal receipt. PM/Connections also accepted Engine.open_run_access -> RunAccessSession for fresh normal host result/source/history access and citation-manifest/checkpoint/export publication. This resolves the earlier missing post-run context; no expired agent grant, saved descriptor or cleanup capability supplies business authority.

Known publication failure with fully recorded failure can be recording_status=complete and persistence_state=not_committed. Unknown admitted commitment or lost outcome/terminal recording remains incomplete with observations/IDs retained. Later host preservation cannot retroactively mark failed execution successful.

## V1 conformance

| Area | Evidence in design |
| --- | --- |
| strict/versioned definitions and input/output validation | 1-2 |
| exact requests/responses/native codecs/tool IDs/nullable usage/audit | 3, 9 |
| AgentResult/output lifetime/normal publication/fresh host access | 4, 8, 10-11 |
| admission/accepted-start-terminal/unknown consumption | 5 |
| shared RecordedToolAction, standalone root and READY/public result | 6 |
| canonical IDs/producers/receipts/status and no uncertain replay | 5-7 |
| context/ranges/ledger/token uncertainty/cancellation/cleanup | 2-3, 7-8 |
| complete future module and full baseline acceptance gates | 10 |
| precise shared consolidation versus resolved decisions | 11 |

## Actual checks and evidence

Read the team routing documents/brief, CONTRIBUTING, missions, decisions, platform-contract-v1, baseline-acceptance and relevant peer status/host-access excerpts. Reviewed current official model/protocol documentation through browsing. The latest DeepSeek model catalog refresh returned a web Internal Error; its current thinking guide uses deepseek-flash and the shared v1 selects it. Replaced the stale OpenAI Responses reference URL after its 404 with the verified current Python API reference. Documentation capability evidence does not verify actual account/server capability.

Draft-buffer checks completed before saving: three JSON examples parse, each has integer schema_version=1; five opening/closing code-fence pairs. Examples use symbolic identifiers/digests and are illustrative shapes, not instantiated configurations or records.

Historical pre-correction r1 saved-file QA passed using Python 3.11.15 through uv --cache-dir .uv-cache run --locked --offline --no-sync python -: strict UTF-8 without BOM, LF/final newline/no trailing whitespace, paired fences (five pairs in design), finite unique-key JSON at depth <=32 (three examples), integer schema_version=1, example field/default checks, all relative local links, required v1 contract fields and absence of obsolete version/receipt/producer vocabulary. This is document/example validation, not implemented JSON Schema or runtime testing. The first content check required parent_attempt_id to be named explicitly; the design was corrected and the complete check reran successfully. Read-only git diff --check passed; owned-path git status/diff inspected. Ordinary sandbox process startup intermittently failed with helper_unknown_error; those document-only checks succeeded through approved host execution, with no sync/install or model/platform execution.

PM independently verified the r1 saved bytes/hashes and document checks. Its semantic review identified one peer ordering discrepancy: the r1 child sequence recorded invocation.outcome before export. The coordinated r2 revision now performs authorized bounded export first, then records the parent invocation.outcome containing the export receipt/failure while preserving the child's terminal facts, matching Connections section 7. Related future acceptance wording also follows this order. AgentResult run identity remains execution.run_id; no public fields or runtime were changed.

Historical pre-catalog r2 saved-file QA passed with the same locked/offline/no-sync Python 3.11.15 document checks listed above, plus assertions that authorized child export precedes parent invocation.outcome and that the outcome includes export receipt/failure with preserved child terminal facts. All three JSON examples and five design fence pairs pass; both files identify revision r2; local links/format/stale vocabulary/required contract checks and read-only git diff --check pass. The initial sandbox helper failed; approved document-only host execution completed the checks. These checks do not validate runtime behavior.

PM's independent saved-byte QA and full boundary review of frozen r2 passed. The coordinated r3 delta only aligns the baseline/catalog references with Yahoo primary/gated corrected-Google fallback and the two separate scholarly discovery tools. Prior child export/parent-outcome ordering and all reviewed authority/publication/continuation corrections are preserved. CLI owns the exact scholarly schemas; generic catalog, recording and Storage-plan interfaces are unchanged. No public fields, runtime or other modules were changed.

Coordinated r3 saved-file QA passed under the same locked/offline/no-sync Python 3.11.15 command: strict UTF-8/LF/no BOM/final newline/whitespace, all three finite unique-key/version1/depth-bounded JSON examples, five design fence pairs, local links and required/stale contract vocabulary. Added assertions verify all five selected tool names in both baseline references, removal of the obsolete three-tool restriction, saved citation-evidence requirement, r3 revision identifiers and preservation of export-before-parent-outcome semantics. Read-only git diff --check passed. The sandbox helper failed on the initial check; approved host execution completed document-only QA. Runtime, binding, Storage-plan interfaces and public fields were not changed or executed.

PM's earlier draft commit/QA at 4210b8c is historical and does not validate this replacement. PM announced baseline-acceptance design at 3d25c7c. PM is the only Git writer; this team performs no stage/commit/push. Private repository and shared environment are already initialized; there is no outstanding no-Git/no-project-environment blocker.

## Shared consolidation needed before implementation

1. PM pins one canonical JSON byte/digest codec for definition/event/request/write/continuation comparisons and tool-name mapping.
2. PM consolidates the owned exact schemas and peer ToolExecutionResult/ToolResult/ToolStoragePlan/refs/error/cleanup fields in one shared contract package, including DefinitionRef={agent_id,revision,digest}, output publication IDs/receipts and admission/ledger enum spellings.
3. Connections/Container finalize the shared live lineage reservation/consume/settle/release protocol and trusted factory wiring; uncertain consumption retains identity/reservation. No metadata can issue authority.
4. Connections/Storage/Toolset consolidate owner cleanup/supervision and event/operation status observations so admitted work can settle without losing root ownership.
5. Connections binds the same Container RecordedToolAction to tool catalog/executor/plan, recorder/Storage and ID/ledger handles for both paths; no duplicate lifecycle helper/logger.

These are exact common-package integration requests, not unresolved internal design work or reasons to stop the current mission. Output-publication behavior, host-access signature, DeepSeek baseline selection, resource caps, DELETE/EXTRA, receipt/status/ID and standalone producer decisions are resolved in v1.

## Phase and evidence limits

No runtime source/test/dependency/lockfile changes, installations, local/.env inspection, model API calls, CLI workers or real Storage execution occurred. Runtime implementation and live acceptance remain unperformed and await PM confirmation of a directly human-authorized phase transition. PM reported automatic approval review rejected that transition because the user's design-first instruction still applies; this design task does not retry it.

The future module belongs wholly to src/ebd/agent/, src/ebd/providers/, tests/agent/ and tests/providers/. PM owns shared types/integration/dependencies/Git. Use shared uv/Python 3.11.15 and locked project commands after authorization. Local vLLM Qwen live verification remains explicitly pending because it is not deployed on this machine; missing local deployment must not block API profiles.

The real DeepSeek baseline uses the selected five registered tools (web.search, scholar.crossref.search, scholar.openalex.search, web.fetch and document.read) under the platform-only search policy in [baseline-acceptance.md](../baseline-acceptance.md); citations still require fetched/saved source evidence. It must save a complete model-generated sourced Markdown report, citation manifest, request audit, paired durable trace and terminal checkpoint, then verify them through fresh authorized close/reopen access. The baseline does not replace GPT, child/standalone, permission/CAS, uncertainty, resource or cleanup gates. No report/trace/checkpoint/runtime has been generated yet.

## PM handoff

Ready-to-commit and frozen for PM review: docs/teams/designs/agent-container-design.md and docs/teams/reports/agent-container-status.md. Handoff reports the actual checks and limitations above. Keep these files stable until PM confirms the commit or coordinates another revision. PM stages/reviews/commits/pushes sequentially; the team does not modify shared or peer files.
