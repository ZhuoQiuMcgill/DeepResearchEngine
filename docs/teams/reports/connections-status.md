# Connections team status

Date: 2026-09-30 (America/Toronto).
Phase: design and research; implementation is not authorized.
State: design assignment completed; DRAFT ready for PM reconciliation and commit.
Runtime implementation and shared-contract approval remain outstanding.

## Completed

- Read AGENTS.md, team README, shared-platform, coordination, Connections,
  and the sibling Container/CLI/Storage briefs and current PM decision log.
- Verified PM's exact chat and its human coordination authorization using
  the app thread reader. Registered with PM through the authorized channel.
- Verified this chat as `Connection Team`,
  `01a0f546-f888-7353-b103-72f3f930fc79`, host `local`.
- Assigned independent design reviews for child permissions/limits and
  Windows-compatible CLI scoped-storage transport.
- Consulted primary Python 3.11 and python-dotenv documentation for
  deadlines, cancellation, configuration parsing, and precedence.
- Reviewed the saved Container and Storage proposals, adopted Storage's
  snapshot operation names/end-exclusive ranges, and identified remaining
  shared-schema/event/retry differences for PM.
- Completed independent reviews of context/grants/shared accounting, recorder
  bootstrap, admission/terminal ownership, shutdown and all three CLI transports.
- Read root CONTRIBUTING.md and latest shared guidance. Honored PM's temporary
  document-write hold; resumed owned files after its baseline-ready notice.

## Owned outputs

- Proposal: `docs/teams/designs/connections-design.md` (completed DRAFT).
- Status: `docs/teams/reports/connections-status.md` (this file).

## Recommendations for PM

- Pin immutable binding descriptors; expose constrained module interfaces.
- Distinguish capability use from permission to delegate that capability.
- Child runs share runtime-owned lineage accounting and inherit narrower
  deadlines, cancellation and scopes; nesting must not reset budgets.
- Connections owns parent invocation intent/outcome; Container owns the
  corresponding child run and model/tool lifecycle records.
- For the initial `web.search`, `web.fetch` and `document.read`, prefer
  launcher-mediated bounded read injection/postprocess snapshot commit, if
  Toolset/Storage accept explicit caps. Successful worker extraction becomes
  canonical fetch success only after Storage returns its committed receipt.
- Initial injection limits proposed: 8 MiB original, 4 MiB normalized text,
  1 MiB index, 64 KiB provenance/read text, 20 MiB private fetch stdout,
  1 MiB stdin and 2 concurrent fetches. Actual memory feasibility is untested.
- Retain a scoped loopback broker for dynamic Storage operations or larger
  streamed transfers; private separate pipes remain viable with a complete
  Windows/standalone adapter. No transport/backend is approved by this team.
- Use trusted Storage recorder bootstrap, one-use runtime admission leases,
  control-plane-only bounded cleanup, per-owner revocation gates and resource
  leases that preserve sibling/shared services during child shutdown.
- Central configuration uses explicit `local/.env`, allowlisted process-env
  overrides and non-secret configuration references; selected bindings only.

## Verification and limitations

Document/coordination/primary-source review and saved-file QA were performed.
Both owned Markdown files were nonempty with paired fenced blocks; the design's
one JSON example parsed successfully. Independent reviews covered delegation
and three transport candidates. No runtime code,
dependency changes, installations, provider/tool/storage smoke tests or model
calls have occurred. `local/.env` was not opened or inspected. Git was absent at
initial startup; PM has since initialized the private shared repository. This
team made no Git mutations and follows PM-only staging/commit/branch ownership.
Normal native helper refresh failed during setup; read-only QA subsequently ran
successfully through reviewed host execution. Document checks are evidence of
saved-file structure, not implementation correctness.

No binding, credential, provider reachability, IPC interoperability or peak
memory/live integration is verified. No external dependency has been selected.
The local vLLM Qwen service remains pending deployment and live verification.

## Decisions requested from PM

1. Reconcile context/grants, child-scope creation, result export, shared lineage
   ledger, admission lease and nesting/concurrency defaults.
2. Select CLI transport with Storage/Toolset; settle private/public response
   schemas, injected-plan validity, Storage receipts/ranges, caps and standalone
   common tool-action helper. Compare the full three-candidate section.
3. Reconcile logical-action/attempt IDs versus Container's fresh action-per-retry
   proposal; `schema_major`/`schema_version`; binding/invocation/run event names;
   commit causal identity and standalone event producer. Parent invocation
   intent/outcome and child lifecycle remain distinct, with durable intent gates.
4. Approve configuration precedence, current-grant revocation semantics,
   control-plane recording/cleanup and resource drain/close policy.
5. Confirm shared contract/package/dependency ownership. Explicit user design
   approval and implementation authorization remain required.

## Blockers and handoff

No blocker to the completed design deliverable. The proposals await cross-team
reconciliation and PM decisions; current authorization ends at design/research.
The two owned paths are offered as a stable ready-to-commit revision. After the
completed report is sent, hold edits until PM confirms its commit or coordinates
the next revision. PM receives the exact paths, recommendation, checks,
limitations and requested decisions through the authorized chat channel.
