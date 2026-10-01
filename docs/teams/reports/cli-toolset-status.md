# CLI Toolset team status

Date: 2026-09-30, America/Toronto. Phase: **design and research**.
Team chat: `CLI Toolset Team`, verified ID `01a0f545-ea04-71e3-965e-2c53d2d241d3`.
Current assignment: **complete; PM selection reflected in coordinated revision**. Initial stack selected; transport, shared schemas/limits and implementation remain pending approval. No runtime implementation has begun.

## Completed outputs

| Owned file | State |
| --- | --- |
| `D:\Projects\DeepResearchEngine\docs\research\free-search-fetch.md` | Completed source-grounded candidate/version/license comparison, actual trials, recommendation, limitations and PM decisions |
| `D:\Projects\DeepResearchEngine\docs\teams\designs\cli-toolset-design.md` | Completed draft three-tool schemas, catalog/ToolExecutor protocol, errors/limits/provenance, snapshot/range/recording ownership, three-way Storage transport and standalone design |
| `D:\Projects\DeepResearchEngine\docs\teams\reports\cli-toolset-status.md` | This handoff/status record |

Read team/shared/coordination specs, sibling Storage/Connections specs and saved proposals, PM decisions and CONTRIBUTING.md. Registered with the exact PM chat using verified human coordination authorization. Research was delivered to PM before the joint transport proposal was finished; final stable paths/evidence are delivered after saved-file QA.

## PM selection and proposed interfaces

PM selected DDGS 9.16.0 + HTTPX 0.28.1 + Trafilatura 2.2.0 + pypdf 6.19.0 for the initial design, recorded in [decisions.md](../decisions.md) and the team brief. DDGS is replaceable/best-effort with configurable explicit Google then DuckDuckGo, named backend outcomes, bounded fallback, unsupported-filter rejection and visible outages. Five successes in twelve attempts across three queries/four modes do not validate coverage; all four modes failed for the niche technical query. Representative-task availability and URL-fidelity gates must pass before teammate acceptance/experiments and remain pending. Static HTML and unencrypted text PDFs are the selected source scope; preserve content-decoded bytes, representation/encoding metadata and hashes with same-response extraction. No browsers/OCR or production dependency/source changes are authorized.

SearXNG remains an unselected alternative for administrative control; local deployment and better reliability are unproven, and a public JSON endpoint returned 429 on its only trial. PyMuPDF's observed speed on one PDF does not settle its AGPL/commercial licensing decision. Research observations/candidate comparisons are preserved; this coordinated revision records selection rather than running new trials.

Preferred **initial Storage transport proposal** is launcher-mediated bounded read injection and end-of-command complete snapshot proposal, aligned with current sibling proposals; no topology is selected. Original body <=8 MiB, text <=4 MiB, index <=1 MiB, provenance <=64 KiB and actual fetch JSON <=20 MiB are draft mediation caps. Read <=64 KiB/200 lines/10 pages with snapshot-bound continuation. Broker/private-channel alternatives are compared for streaming/dynamic use.

ToolExecutor owns argv-only process execution and its scoped Storage adapter. Connections binds the trusted operation plan. Storage owns complete-bundle staging/finalization, authorization, receipts and commit events. Container owns a single intent/outcome around the whole tool including parent read/commit. Worker exit 0 is not durable fetch success. Original content is content-decoded response bytes; text derives from that same retrieval. Reads never refetch and retain physical PDF-page/line/UTF-8 byte references.

Independent reviews checked source claims/counts and compared the design with sibling interfaces. Corrected continuation forwarding, empty logical lines versus empty physical PDF pages, and broker-token ownership (Storage issues/validates; Connections binds/leases; ToolExecutor delivers). Explicit trusted backend-attempt selection clarifies central retry ownership.

## Verification actually run

- Isolated uv research environment on Windows x64, CPython 3.11.15, uv 0.11.6; installed all exact seven comparison package versions and recorded the 33-package resolved closure.
- Twelve real DDGS public-query calls: five result lists and seven generic `No results found` errors. Domain hosts validated on the two successful domain-syntax calls. No claim that generic failures prove blocking/rate limits.
- Eight real public fetches using HTTPX/Requests, all successful; ten HTTP responses including redirects. Both clients preserved equal decoded-body SHA-256 for article/docs/PDF. Eight HTML extractions, four PDF extractions, twelve bounded saved-buffer slices. One 194-page text PDF; pypdf approximately 4.17 seconds versus PyMuPDF 0.20 seconds extraction, not a general benchmark.
- One bounded public SearXNG JSON request returned HTTP 429; stopped without bypass. No local SearXNG deployment trial.
- Actual research request/options/timestamp/latency/output/error records and original/extracted captures remain in ignored `D:\Projects\DeepResearchEngine\.uv-cache\cli-toolset-research\`. No mocked results or model calls.
- Primary-source license/dependency review; installed cssselect LICENSE resolved its BSD-3-Clause variant. Full native/wheel/container distribution audit remains pending.
- Saved research/design files read for review; dependency SHA-256 rechecks match the pre-research baseline. Read-only Git status identifies owned drafts after PM's repository initialization. No Git/index/branch mutation by this team.
- Final saved-file QA through the shared `uv run --locked --offline` environment checks strict UTF-8, balanced code fences, the JSON example, local report/design links and dependency hashes. Research scratch is confirmed ignored. The hash check's initial case-comparison error was corrected; underlying project files match baseline.

`pyproject.toml` SHA-256: `054F4CE51130E1BBD8072FA3B3FFA40D2A3C77397016BFD45735CDD41234D7FD`.
`uv.lock` SHA-256: `38CBB937D8DF92930FC872F65A57FB15FFD5E9F53CACFF7E7778C365B1FA7073`.

Normal sandbox network access and later its native helper failed; approved host commands completed the isolated trials and non-secret reads. No automatic approval rejection remained unresolved. Credentials were never read, copied or printed. Project dependency files, runtime source and other teams' files were not edited. PM's brief Git baseline write hold was observed; owned document work resumed after its ready notice. Root contribution/environment/Git rules apply going forward.

## Untested, blockers and decisions

No current blocker prevents review of this assignment. No production ToolExecutor, mediated adapter/broker/pipe, Storage integration, event path, process-tree cleanup, memory quota or standalone runner exists as this team's deliverable. Sustained search, paging/localization/date guarantees, JS rendering, complex/scanned/encrypted PDFs, OCR and adversarial content remain unverified. API smoke tests were not authorized/run; undeployed local vLLM Qwen live verification remains pending outside this assignment.

PM must reconcile supported filters/fallback accounting and one common schema/context/error model, choose transport/limits, agree acceptance-gate criteria and Windows deadline/memory/cleanup policy, assign shared schema/runner ownership and approve the later dependency/license closure. Initial stack, ordered named-backend policy and source preservation/scope are selected. User design approval precedes implementation.

Cross-document review questions to PM: ensure Storage commit events reuse the causal action/attempt plus separate operation ID rather than conflicting new action allocation; ensure zero-text range rules use the requested unit count and do not erase valid empty PDF physical pages; keep continuation in the mediated read path. CLI-owned wording is aligned; sibling changes belong to their owners/PM.

After final handoff, these three owned paths are **stable and ready for PM to review/stage/commit**. Team will keep them frozen until PM confirms that revision or coordinates a follow-up revision. PM remains the sole Git writer.
