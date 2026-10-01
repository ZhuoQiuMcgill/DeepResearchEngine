# Sustained team missions and PM responsibilities

Status: active design alignment; implementation phase pending authorization.
Read `platform-contract-v1.md`, `CONTRIBUTING.md`, your brief and your own
design. These missions let each leader finish a whole module independently.
PM coordinates boundaries and reviews evidence rather than writing all modules.

## Shared working rules

- Same checkout: `D:\Projects\DeepResearchEngine`; uv, Python 3.11.15,
  committed manifest/lockfile and `.python-version`.
- Current writes remain owned design/status paths in `CONTRIBUTING.md`.
  The source/test ownership in the common contract applies only after PM
  confirms the authorized phase transition. No runtime code or API calls now.
- PM alone changes shared types/dependencies and stages/commits/pushes.
  Never switch branches, overwrite another team or stage the whole checkout.
- Decide internal design details yourself within the agreed boundaries.
  Send exact cross-module contract changes to PM; do not wait for routine choices.
- Report milestones with saved paths, actual evidence and unresolved risks.
  Freeze a ready-to-commit revision until PM confirms it. Request a contract
  decision early if it blocks independent work; continue unrelated work.
- No mock replies at platform handoff. Isolated research tests remain evidence,
  not implemented module functionality. Never expose `local/.env` values.

## Agent Container Team

Owner: `Agent Container Team`. Current outputs:
`designs/agent-container-design.md`, `reports/agent-container-status.md`.
Future source ownership: `src/ebd/agent/`, `src/ebd/providers/` and their tests.

Current mission: finish the complete runtime/provider design against the
common contract. Replace competing version/status/receipt/ID proposals;
define exact AgentDefinition, input/output validation, context policy,
ModelRequest/Response, native continuation envelope and AgentResult schemas.
Document Runtime admission lease, accepted/start/terminal state transitions,
record-before-dispatch logic and one RecordedToolAction shared by engine and
standalone use. Give precise bounds and failure behavior for context assembly,
model/tool calls, validation repair, cancellation and cleanup. Map each required
provider capability and configuration key to official evidence, distinguishing
implemented design from unavailable live capability. Identify any irreducible
cross-module request rather than inventing another helper in a consumer.

After authorized implementation, this team owns the whole agent execution
loop and real DeepSeek, GPT-6-Luna Responses and configurable vLLM/Qwen
connectors. It must preserve native continuation and tool-call pairing,
validate and finalize outputs, enforce shared limits/grants and emit canonical
agent/model/tool hooks. API/internal search must be disabled for research;
rendered-request audits expose only safe model/profile/tool metadata. No EBD
strategy belongs in the runtime; adapters cannot execute tools. Local Qwen
live verification stays pending until deployment, without blocking API agents.

Definition of done: exact design aligned with common types and peer needs;
then runnable documented entry points, meaningful admission/recording/cancel/
continuation checks and real API tool conversations. Return module paths,
commands/results, safe audit evidence and explicit deployment limitations.

## CLI Toolset Team

Owner: `CLI Toolset Team`. Current outputs:
`designs/cli-toolset-design.md`, `reports/cli-toolset-status.md`,
`../research/free-search-fetch.md` and assigned ignored research scratch.
Future source ownership: `src/ebd/toolset/` and its tests.

Current mission: finish exact catalog, executor, private worker and public
result schemas under the selected DDGS/HTTPX/Trafilatura/pypdf design. Separate
prepared worker output from finalized public success. Define ToolStoragePlan,
fetch proposal/provenance/page map, read injection, exit/phase validation,
bounded pipe drain, timeout/cancellation and Windows descendant cleanup.
Align the smaller resource profile with Storage; specify measurement and
failure gates instead of claiming byte caps bound RAM. Complete representative
free-search availability/URL-fidelity research in isolated scratch with no
model keys, project dependency changes or runtime source. Do not claim reliable
search from the earlier five-of-twelve outcome. Record exact attempts/outages.

After authorized implementation, this team owns real registered `web.search`,
`web.fetch` and `document.read`, catalog/executor and CLI parsing/formatting.
Use explicit configurable named search backends and bounded fallbacks, with
outages surfaced. Retain original fetched representation and derive text from
the same body. Execute only fixed argv without a shell. Commit/read through
the supplied Storage plan; do not create a second store or lifecycle logger.
The host standalone composition uses the common recorded tool helper, with
no model initialization. Browser/OCR/paid services require a measured scope
proposal rather than silently adding dependencies.

Definition of done: aligned schemas and complete evidence/measurement plan;
then real search/HTML/text-PDF/reopen/read, immutable locators, max-fit/oversize
protocol checks, measured parent/worker RAM, actual cleanup and uncertainty
without refetch. Report reproducible commands, exact results and search
limitations. Tool output cannot become public fetch success before Storage
publication and lifecycle acknowledgment.

## Storage Team

Owner: `Storage Team`. Current outputs:
`designs/storage-design.md`, `reports/storage-status.md`.
Future source ownership: `src/ebd/storage/` and its tests.

Current mission: finish the async scoped persistence contract, SQLite schema
and filesystem recovery protocol aligned with v1 IDs/receipts. Replace WAL/
competing caps/ack proposals with explicit DELETE/EXTRA baseline and optional
patched-WAL gate. Specify exact event-status and operation-status lookup,
idempotency content/origin comparison, CAS/tombstones, admitted commit states,
READY snapshot publication, interrupted recovery and close ownership. Align
DocumentSlice line/page/UTF-8 continuation/empty-unit semantics with Toolset.
Provide concrete hook/transaction tables, migration/settings checks and fault
acceptance cases; keep identity allocation and authority issuance in their owners.

After authorized implementation, this team owns real state, append-only
activities, artifacts, snapshots and checkpoint persistence; scoped handles,
single-root ownership, transactions and recovery. Acknowledgment follows a
verified commit and complete bytes. Persist publication events automatically,
without duplicate model/tool lifecycle records or recursive append logging.
Reconcile uncertain commitment by the same IDs; never invoke external work.
Keep the root and resources owned while admitted writes remain unresolved.

Definition of done: coherent exact APIs and failure tables; then verified
runtime/settings, durable close/reopen, CAS/permission isolation, immutable
artifacts/snapshots, identical-ID/different-content conflicts and meaningful
interruption/uncertain-commit tests. Return reproducible fault evidence and
state clearly what durability is verified versus hardware dependent.

## Connection Team

Owner: `Connection Team`. Current outputs:
`designs/connections-design.md`, `reports/connections-status.md`.
Future source ownership: `src/ebd/connections/` and its tests.

Current mission: finish complete composition/binding and invocation design.
Align common context/identity, immutable descriptors, live authority/leases,
central dotenv precedence, lazy named provider selection, BindingSet,
single-use runtime admission, parent invocation events and child export.
Define public Engine operations that strategy authors consume, standalone
bootstrap without a model and the trusted ToolStoragePlan. Remove competing
commit action IDs, duplicate loops and alternate runtime lifecycle names.
Specify downward cancellation, shared lineage limits, use/delegate distinctions,
revocation, scope provisioning, uncertain admission and ordered shutdown.
Provide two complete interface-only example sequences: root researcher to
child writer; standalone saved-document read with an explicit scope grant.

After authorized implementation, this team owns actual registry/config loading,
Engine composition, module factories/leases, contexts/permissions and child
invocation. It calls Container's loop and Storage's persistence, and supplies
Toolset's plans; it never recreates those operations. Missing Qwen config
affects only its selected agents. No incidental network probe in registration
or binding; explicit live checks are bounded and recorded. No hidden scheduler.

Definition of done: exact executable-consumer API design; then real module
bindings, environment/config errors, root/child/standalone composition,
attenuation/export/lineage limits, revocation and cancellation/close evidence.
Report path ownership and any contract defect before editing shared files.

## PM

PM owns the one shared contract and schema vocabulary, contract-change
decisions, environment/dependency lockfile, coordination and Git. Module
leaders own module internals and their verification. PM reviews completed
contributions, integrates them and resolves boundary defects with their owners.

After phase authorization, PM supplies shared executable types/protocols and
package entry-point glue, coordinates parallel source ownership, and builds
the simple baseline using only the platform APIs. PM runs final real acceptance
for the requested EBD question/model with API/internal search disabled,
audits the generated report against recorded fetched snapshots and traces,
and reports what actually passed. An existing research draft is not that report.
PM does not complete the goal until the platform and real baseline report exist.

Current next handoff from each leader: update the whole owned design/status
to v1, include a compact conformance checklist and exact blocking discrepancies,
and notify PM once the saved revision is complete. A short proposal message
alone is not the module deliverable. Continue autonomously within ownership
until the current design mission is complete; runtime work waits for the
explicit phase-transition notice.
