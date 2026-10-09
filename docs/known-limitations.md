# Known limitations

Last assessed: **2026-10-04**.

This document records the remaining limitations after the final supervised-fetch
acceptance round. It covers `baseline@13`, pinned to `web.search@4` and
`web.fetch@3`. The baseline retains two research rounds, forty attempted URLs
across the whole run, and a 262,144-token allowance per Agent. Earlier method
revisions remain available; consumers must explicitly select revision 13.

The engineering objective is to eliminate losses caused by acquisition,
formatting, evidence delivery, recording and orchestration. Search depth and
model judgment are separate limitations. The follow-ups below are recommendations,
not completed fixes or an active implementation plan.

## Evidence and scope

The final batch ran each original question once with `deepseek-flash` and once
with `gpt-6-luna`, using fresh stores and unchanged question text:

- `compare meta quest 3 and apple vision pro`
- `How do I flight from GuangZhou to Montreal?`
- `What food can help me sleep well?`

| Question | GPT result | DeepSeek result |
| --- | --- | --- |
| Headsets | Published; `sufficient` | Unpublished draft; `REPORT_REVIEW_FAILED` |
| Flights | Published; `partial` | Stopped at the second Analyst call; `provider.transport` |
| Sleep | Published; `sufficient` | Published; `sufficient` |

Across these six runs, 80 URL attempts produced 64 snapshots and four published
reports. All six store audits passed, including artifact hashes, recorded read
segments and citation bindings. Independent checks also verified local role
inputs against provider request preparation.

These checks establish local consistency. They do not establish remote receipt,
model attention, extraction completeness or factual accuracy. Search results and
model paths differed between runs: this batch is not a controlled model ranking,
a failure-frequency estimate or a general website success rate.

## Engineering limitations

| ID | Limitation | Responsible component | Follow-up priority |
| --- | --- | --- | --- |
| L1 | Transport failures have incomplete diagnostics and limited recovery | Provider adapter and application orchestrator | First: characterize outcomes before widening recovery |
| L2 | Failed-run quality can describe an earlier checkpoint | Application/API and method quality assessment | First: expose assessment freshness |
| L3 | Dynamic content can remain unavailable after successful static fallback | Fetch supervision, renderer and extraction | Conditional on workload impact |
| L4 | Complex document relationships and graphics are not fully extracted | HTML/PDF extraction | Conditional on required source types |
| L5 | Strict quotation validation excludes some unsupported formatting | Shared quotation validation | Retain examples; make only verified, general fixes |

### L1. Transport diagnostics and recovery

The DeepSeek flight run retained all 18 fetched sources, then encountered a
`ReadError` after 16.429 seconds during the second Analyst call. Local recording
and cleanup completed, but remote completion and usage remained unknown. The
failure did not retain provider request/response IDs, HTTP status or received-byte
progress. No model output was available for validation.

The adapter catches transport errors around the response lifecycle, so the saved
record cannot distinguish a failure before headers, an interrupted body read or
a failure while reading an error response. Missing IDs and an empty visible-text
record do not prove that no bytes arrived or that the provider did no work.
Network/proxy interruption and provider-side closure remain possible causes.
There is no established context-overflow diagnosis.

The orchestrator already retries eligible, fully recorded transient HTTP and
explicit native service failures with bounded waiting. It does not replay an
unknown remote outcome. Consequently, useful completed research can remain
archived while the overall run fails. Recovery during an active run also does
not provide automatic workflow resume after a service/process restart.

The next bounded step is to preserve safe transport phase, status, provider IDs,
received-byte counts and categorical causes through the adapter and role
boundary, then test recovery decisions with fault injection. Any broader recovery
must retain attempt identity, original budgets and explicit handling of uncertain
remote work. One observed event does not establish a frequent bottleneck.
See [orchestrator recovery](usage/research-service.md#orchestrator-recovery-during-execution).

### L2. Quality assessment freshness

In that failed flight run, the source manifest contained 18 successful sources,
while `quality` still reflected the first-round checkpoint covering 10. The
second-round Analyst failed before a new assessment was completed. This is a
stale assessment, not evidence of lost sources or a ten-source acquisition cap.

The quality response lacks an explicit assessment round/as-of marker. A frontend
can therefore mistake earlier quality counters for current acquisition totals.
Until freshness is exposed, use the source manifest for acquisition totals and
treat failed-run quality as the last completed assessment. New sources should
not be labelled assessed or sufficient merely because fetching succeeded.
See [baseline reliability](usage/baseline-reliability.md).

### L3. Dynamic-page completeness and renderer limits

A real Meta fetch exceeded the renderer's 512 MiB worker limit. Supervision
correctly retained a validated static capture: 107 body bytes plus a 4,310-byte
JSON-LD supplement. Successful archival and complete readback of those bytes do
not establish completeness of the dynamic page.

Static acquisition and optional rendering share a 60-second work deadline,
40 HTTP requests and 32 MiB of decoded network traffic per logical fetch.
Rendering has at most 30 seconds and only the remaining grants. The automatic
thin-page trigger is heuristic and can both miss needed rendering and render
an already complete short page.

A rendered replacement must preserve the static body, declared dates and whole
retained JSON-LD records, while adding content. Useful renderings can be rejected
when extraction drops a heading or changes the preserved representation. Static
and rendered captures are not merged. After some worker terminations, total
network usage remains `null`; separately recorded known counts are lower bounds.

An independently budgeted renderer profile is worth evaluating if dynamic sources
regularly limit real tasks. A larger limit alone would not establish completeness.
See [supervised fetch revision 3](usage/web-tools.md#supervised-fetch-revision-3).

### L4. Complex HTML, graphics and PDF fidelity

Both models encountered five unresolved structure blocks in a Flightconnections
source; GPT encountered five more in a Trip.com source. These diagnostics indicate
possible missing relationships or conditions. They are not counts of independently
proven semantic omissions.

Remaining format boundaries include some lists and tables, unlabelled SVG
geometry, PDF formula glyphs and layout relationships. SVG label support covers
a narrow table-cell subset; it does not interpret geometry as facts. Retaining
opaque PDF glyph names does not decode their mathematical meaning. The text-PDF
path also does not establish coverage for image-only documents.

Archived JSON-LD records are explicitly publisher-declared supplements. They do
not establish visible-page completeness, current availability or relationships
outside the retained records. Bounded extraction may omit additional records,
with diagnostics recording those limits.

Specialized visual or document reading is justified when required evidence
frequently depends on these representations. Preserve original evidence and
warnings rather than inventing missing text or relationships.

### L5. Quotation formatting boundaries

Strict validation excluded four of 370 processed findings in the final batch.
One changed the source wording from `stopovers` to `layover duration` and was
correctly rejected. The other three involved unsupported representation cases:
spacing between adjacent HTML spans, a mixture of retained and removed Markdown
links, and a space added beside a link that had no source-space separator.

These cases can lose usable evidence even when acquisition and reads succeed.
They should not all be classified as model reasoning failures. Conversely,
accepting arbitrary whitespace or fuzzy wording would weaken source bindings.

Retain these examples as regression candidates. Extend matching only where
equivalence can be demonstrated while preserving words, values, qualifiers,
link destinations, table relationships and literal code. Topic-specific Agent
instruction changes would not address the underlying representation boundary.

## External, workflow and model boundaries

### L6. External access and discovery coverage

The final batch still encountered HTTP errors, redirect limits, pages requiring
rendering, unsupported content and empty extraction. Academic discovery also
encountered backend admission/quota restrictions. Free open-source clients do
not make external indexes unlimited or guarantee access to publisher sites.

Search results are a bounded candidate set, not a measure of web-wide recall.
Existing fallbacks and explicit partial-coverage reporting remain necessary.
Access restrictions are external constraints; correct recording of a failed URL
does not make its content available.

### L7. Baseline coverage, model judgment and publication

Two research rounds can leave shallow or narrow coverage. Forty URL attempts
include failures and do not guarantee forty distilled sources. Distillation
defaults to 20 calls, with a configurable ceiling of 40 subject to shared host
grants; the default 40 model-call/descendant grants also cover the other roles
and recovery. Fetch capacity is not additional model capacity.

The 262,144-token Agent allowance is a configured limit, not proof of a provider's
effective context capacity, exact tokenizer accounting or successful use of all
delivered evidence. Ambiguous questions and model query choices can also leave
product generations, travel assumptions, primary sources or original studies
underexplored.

The DeepSeek headset draft failed publication after four report attempts. Its
body cited a source absent from References and its account of chunk/read coverage
remained wrong. Inspection confirmed these problems in the draft itself; the
parser had not silently removed a valid reference entry. A working review gate
can therefore leave a run without a final report.

Publication, verified quotations and `quality=sufficient` are separate checks;
none certifies factual truth or comprehensive coverage. Workflow depth and model
judgment remain accepted baseline limits for this engineering round. They do
not justify overfitting instructions to the three benchmark questions.

## Recommended stopping point and follow-up

The strongest case for another bounded engineering pass is **L1 transport
observability/recovery classification and L2 quality freshness**. Establish their
behavior with targeted failure tests before another online comparison. Broader
renderer or visual-document work should depend on measured workload impact.
Unbounded website enumeration and isolated format patches have diminishing
returns without evidence that those cases materially affect intended tasks.

The detailed acceptance record is phase 34 of
[cross-scenario diagnostics](scenario-systemic-diagnostics.md). Supporting raw
evidence is machine-local under the ignored
`local/fidelity-cycle-20261004/render-supervision/` directory, including
`final-evaluation.json`, `final-matrix/`, `dispatch-verification.json` and
`transport-review/`. Those artifacts are not included in a normal repository
checkout. This document records the completed round; it does not start further
experiments.
