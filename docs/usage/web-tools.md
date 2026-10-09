# Open-source web tools

Select `web.search@4` and `web.fetch@3`, or request **`baseline@13`** to use
both. Baseline 13 retains revision 12's six Agent roles, instructions, schemas,
two-round policy and 40-URL maximum. It changes only the fetch tool pin.
Earlier methods and tool revisions remain available as comparison controls.

## Install and start

From the repository root, with Python 3.11+, uv and a running Docker daemon:

```shell
uv sync --locked
uv run --locked playwright install chromium --only-shell
uv run --locked python examples/manage_web_tools.py start
```

The launcher creates an ignored local SearXNG configuration and random service
secret, then starts the image pinned in `deploy/web-tools/compose.yaml`.
It binds **127.0.0.1:18888**, keeps only Yahoo and DuckDuckGo and enables JSON.
It does not expose the service to the network or start it automatically on reboot.

```shell
uv run --locked python examples/manage_web_tools.py status
uv run --locked python examples/manage_web_tools.py stop
```

Run the launcher in the environment that owns your Docker daemon. On the
verified development machine Docker runs in WSL, while the project's Python
environment is Windows-native. The launcher uses only the standard library,
so `python3 examples/manage_web_tools.py start` in WSL starts the same service;
project tests and benchmarks still use Windows-native uv. No second project
virtual environment is needed. The Windows Docker Desktop named pipe was not
available during this check.

Missing service/browser installation is a recorded tool failure. Fetch does
not install a browser during a research run. Static acquisition can still
succeed without Chromium.

## Contracts and composition

| Capability | Selected implementation | Contract |
| --- | --- | --- |
| Search | Self-hosted SearXNG 2026.10.2-19ffbcd30; Yahoo + DuckDuckGo | Literal query, up to 10 ranked results, complete available snippet, exact service-returned URL, contributing engines and partial failures |
| Primary HTTP | curl_cffi 0.16.3 | Public HTTP(S), browser-compatible transport, cookie-preserving redirects, bounded body and deadline |
| Alternate HTTP | Existing HTTPX 0.28.1 | One static fallback for an empty/challenge response; useful where the primary transport is treated differently |
| Dynamic HTML | Playwright 1.63.0, bundled Chromium | Bounded rendering after static extraction fails or a thin scripted body is detected; all requests pass through guarded curl transport |
| Generic HTML extraction | Trafilatura 2.2.0 + Markdownify 1.2.3 | Selected Markdown with bounded DOM recovery; HTML fragments preserve relationships that Markdown cannot express |
| Scholarly HTML | Existing labelled article sections | Preserve metadata/abstract boundaries |
| Text PDF | PyMuPDF 1.28.2 with pypdf 6.19.0 page checks and PDFium spacing corroboration through pypdfium2 5.13.0 | Physical pages, original bytes, bounded extraction diagnostics |
| Storage/access | Existing snapshot commit + document.read | Immutable original, text and index; hashes, line ranges, continuation and token measurement |

Generic HTML extraction identity `trafilatura_markdown/17` retains revision 9's normalization of
transparent custom inline components to spans in the parsed working tree. This
keeps linked text and following conditions in source order through the library.
It preserves attributes and original archived bytes, excludes structural/literal
components, and does not change Agent instructions. See the
[extraction boundaries](baseline-reliability.md) and phase 17 of the
[systemic diagnostics](../scenario-systemic-diagnostics.md) for the paired live
failure and checks. Revision 10 also restores structures within a strongly
covered authored section, counts intact projected subtrees, and measures prose
overlap after the final Markdown render (`dom-prose-overlap/2`, preserving the
intermediate counts). Phase 18 records verification. Extraction diagnostics remain
heuristic rather than proof of semantic completeness.

Revision 11 additionally explains flattened tokens with complete original DOM
text slots in one block. It permits re-rendering original fields when the library
deleted intervening slots and joined numbers or words. Source order, block/code
boundaries and bounded work remain enforced; quotation validation is unchanged.
Phase 19 records archived replay, live acquisition and paired distillation checks.

Revision 12 can also project omitted original paragraphs and local headings
inside one explicit article/main. It checks final text, destinations, code and
already matched paragraphs before replacing the library output. Unmarked page
scope and independent nested articles cannot authorize this recovery; unrelated
unselected link cards stay excluded. Optional `prose_render_recovery_*` fields
record attempts and application. See phase 20 for the original-paragraph replay.

Revision 13 additionally recovers omitted fields within an already selected list
of records. Every record needs its own unique whole-field anchor and at least
80% ordered whole-slot coverage inside its own selected window. Record order,
text/slot/state/work bounds and all prior preservation checks still apply;
common fields elsewhere cannot authorize recovery. Lists containing direct
children other than `li` remain sanitized HTML so nested record groups survive.
This can increase stored text size and token use. It does not enlarge read,
context or fetch grants. See phase 21 for archived and live validation.

Revision 14 preserves linked inline code as inline sanitized HTML. Markdown code
spans cannot carry hyperlinks; dropping that destination previously caused the
whole structure-recovery candidate to be rejected, even when the damaged table
was elsewhere. Both literal code and original destinations now survive, with
the same preservation guard. See phase 22 for the archived infobox case.

Revision 15 preserves headerless, mixed-header, row-header and ragged tables as
sanitized HTML. Markdown cannot express their original cell roles and row lengths;
an intact intermediate extraction tree was insufficient to verify its final
rendering. No headers or empty cells are invented. Representable rectangular
header tables retain Markdown. See phase 24 for rendered-DOM comparisons.

Revision 16 retains explicit inline SVG labels within selected table cells as
inert text. Supported origins are `aria-label`, a bounded unique local
`aria-labelledby`, direct SVG title/description and tooltip title. Conflicting,
hidden, presentational, oversized or unsupported graphics remain unresolved;
path geometry and CSS/symbol names never become a guessed yes/no value. The
optional `html_extraction.graphics` records coverage separately from prose and
table shape. This is not image understanding: unlabelled values still cannot be
read from text. See phase 27 and the reliability guide for exact bounds.

Revision 17 preserves explicit inline `application/ld+json` scripts in a separate,
labelled publisher-declared supplement. It retains whole records, relationships,
numeric spellings and conflicting declarations; it does not execute scripts,
resolve contexts or equate metadata with visible text. The optional
`provenance.structured_data` exposes counts, omission reasons and readable UTF-8
ranges/hashes. Values are available through `document.read`, not source metadata.
Existing body bytes and diagnostics remain unchanged, and metadata cannot make a
JavaScript shell, abstract or short body pass a stronger body-content check.
Scholarly HTML retains its classification with `+inline-jsonld/1` provenance.
See phase 33 and the reliability guide for bounds and actual model delivery.

These are free open-source software components. The public Yahoo/DuckDuckGo
search services and their indexes are **not** open-source indexes; they require
no paid API key in this configuration. Rate limits and availability still apply.
SearXNG's license is [AGPL-3.0](https://github.com/searxng/searxng/blob/master/LICENSE),
curl_cffi uses [MIT](https://github.com/lexiforest/curl_cffi/blob/main/LICENSE), and
Playwright and Trafilatura use
[Apache-2.0](https://github.com/microsoft/playwright/blob/main/LICENSE) /
[Apache-2.0](https://github.com/adbar/trafilatura/blob/master/LICENSE).
Markdownify uses [MIT](https://github.com/matthewwithanm/python-markdownify/blob/develop/LICENSE).
PyMuPDF's open-source distribution uses
[AGPL-3.0](https://pymupdf.readthedocs.io/en/latest/about.html).
The independent spacing reader uses the open-source
[pypdfium2/PDFium components](https://github.com/pypdfium2-team/pypdfium2#licensing).

Search arguments remain `query` and optional `max_results` (1–10, default 5).
`raw_url` is exactly the URL SearXNG returned, not a claim that the original
search-engine HTML wrapper was retained. `provider_rank` is SearXNG's native
aggregate rank; `engines` identifies contributing engines. Snippets are bounded
at 16 KiB and titles at 4 KiB with truncation markers. Missing dates stay null.
Coverage describes eligible results on the first page, not global recall.
`http_request_count` measures Engine-to-SearXNG requests;
`upstream_http_request_count=null` explicitly leaves server-to-engine traffic
unknown. The service endpoint is trusted host configuration through
`EngineSettings(searxng_url=...)` or global CLI `--searxng-url`.

Scholarly discovery revision 2 isolates malformed optional locations. A bad
Crossref supplemental link is omitted while its work/DOI metadata and valid
links remain available. Nullable DOI/OpenAlex location URLs become null when
invalid; `bibliography.invalid_fields` records their projected field paths
(for example `links[0].url` or `primary_location.pdf_url`). Link indices identify
the original provider projection before filtering. Destinations are never split,
guessed or repaired, and valid URLs retain their exact bytes. This uses the
existing closed revision-2 schema; revision 1 remains strict.

An unusable whole scholarly response is recorded as `SCHOLAR_PROTOCOL_ERROR`,
not a malformed user argument or transport failure. The orchestrator isolates
that backend only when its HTTP 200 response, worker exit, recording and cleanup
are all settled and no snapshot publication was required. Existing candidates
remain available and subsequent backends may run. This does not repeat the bad
request or bypass shared budgets; unknown outcomes and incomplete cleanup still
stop execution.

Fetch arguments remain `url`, with optional `mode`. Revisions 2–3 default to
`auto`; `static` disables Chromium while permitting the alternate static
transport. Revision 1 still defaults to and only accepts `static`.
Each URL is one recorded fetch operation regardless of internal adapter
attempts. `fetch_attempts` records their outcomes and actual HTTP counts.
Baseline revision 12's 40-URL budget includes failed URLs across both rounds.

## Supervised fetch revision 3

The parent owns static acquisition and optional rendering as distinct worker
phases. Before dispatch, `tool.intent.dispatch_policy` authorizes both under
one logical fetch attempt and snapshot operation. A phase is never replayed.
At most one validated original/text/index capture is published; captures are
not merged. `web.fetch@2` retains its prior one-worker behavior and integer
network counter schema. Unqualified tool calls still resolve revision 1.

In `auto` mode, rendering can follow a settled empty/shell/challenge result or
a successful but thin scripted HTML body: 1–2048 body bytes, 64 KiB–8 MiB raw,
an external executable script, at least half the markup occupied by scripts,
and at most 8192 bytes of non-script visible DOM text. JSON-LD supplements do
not enlarge the body for this decision. This heuristic can miss dynamic content
or render an already complete short page. It does not prove completeness.

Both phases share 60 seconds of work, 40 HTTP requests, 32 MiB decoded network
bytes, 20 MiB stdout and 64 KiB stderr. Queuing consumes the work deadline.
Rendering starts only with time, network, stream and provenance reserves and
has at most 30 seconds, leaving cleanup/publication time. The renderer gets
the residual network and stream grants; each worker's Windows Job remains
512 MiB. Revision 3 permits scripts up to 8 MiB within the aggregate budget;
other resource caps and revision 2's 2 MiB script cap remain unchanged. Network
byte limits are abort thresholds: an observed crossing chunk remains counted.

When a valid static capture exists, a rendered replacement must preserve its
literal ordered body blocks, declared document dates and every retained JSON-LD record, retain the same final
URL, report no failed resources, and add authored body content. Changed values,
missing headings or extraction-format changes can therefore reject an otherwise
useful rendered capture. The safe result is the static archive plus an explicit
selection diagnostic; no synthetic union or guessed facts are inserted.

A confirmed renderer memory/deadline/stream termination, failure to start, or
classified settled fetch failure can retain that static capture while the
parent remains active. Cancellation, unconfirmed cleanup, malformed worker
responses, changed identities and destination-policy faults remain fatal.
Without a valid static capture, renderer failure remains a failed URL.

`provenance.fetch_supervision` records the trigger, decision, selected stage,
renderer allowance/outcome and network accounting. If renderer traffic is
unknown after termination, aggregate counters are **null**, never zero or the
static count disguised as a total. `known_*` fields are explicit lower bounds;
there is no further network dispatch after that uncertainty. Very tight
provenance capacity can skip optional rendering and retain the diagnostic only
in durable tool observations. `process.stages` retains real request/response
digests, cleanup, usage and exit/termination details for both workers. Ordinary
process fields refer to the selected worker; aggregate peaks are maxima, not
sums. Snapshot `source_bytes` charges the selected original once, independently
of total network traffic. Source descriptors and bounded Distiller feedback
expose these limitations, while source values remain accessible by archived reads.

Phase 34 of the [systemic diagnostics](../scenario-systemic-diagnostics.md)
records actual tests and known limits. A successful static fallback is not a
claim that all dynamically displayed content was obtained.

For text PDFs, revision 2 records extraction version
`pdf_text/9+pymupdf/1.28.2+pypdf/6.19.0+pypdfium2/5.13.0`. Strict pypdf admission still rejects
encrypted, invalid, over-limit and textless documents. PyMuPDF then supplies
each physical page in creator order (`sort=False`). A streaming comparison
requires the same non-whitespace characters in the same order, preserves
existing word/line boundaries and indentation, and rejects splits within
numeric tokens. Single undecoded control glyph replacements are counted
separately; replacement characters, private-use and invisible glyphs cannot
count as successful decoding. If a whole native page fails these checks, a
second streaming pass may recover individual word gaps and decoded glyphs.
That pass still requires complete character alignment, with the explicitly
bound opaque-glyph exception below. It may
insert native ASCII spaces between alphanumerics. Other inserted spaces and
removal of a single old ASCII space between letters require agreement with
PDFium at the same character boundary. Both readers' complete ordered character
streams must align; only seven Latin presentation ligatures expand for comparison,
never in output. A secondary C0/C1 placeholder may align with one primary glyph,
but neither neighboring boundary can authorize an edit. It never supplies an
output glyph. A later character/order disagreement discards the entire alignment.
Continuous digits and recognized numeric token interiors (decimal, exponent,
date, version and base-prefixed forms), old line breaks, tabs, indentation and trailing
whitespace are protected. The independent reader opens lazily, closes its native
handles explicitly and serializes PDFium calls; fetch still uses isolated workers.
Its failure retains the previous word-gap recovery behavior and is diagnosed.
Comma-separated lists and joined bibliographic fields are not automatically
classified as one number. Ambiguous numeric formatting is not semantically parsed.

When PDFium observes a space missing from PyMuPDF, a bounded character-position
check may confirm it. This check requires complete page character alignment and
positive gaps between letters on the same horizontal baseline, font and size.
Three independently observed word gaps on that line can also calibrate one missed
gap of the same physical size (tolerance 0.2% of font size). At a font transition,
only a space independently observed by PDFium can be restored, and its positive
gap must match that same line's calibration in the preceding font. Both glyphs
must be letters at the same size and baseline. This handles separate ligature
fonts without guessing font-family relationships or inferring an unobserved
cross-font gap. Other sizes, baselines and orientations remain literal. The raw character dictionary
excludes images and is requested only for pages at most 32768 UTF-8 text bytes.
Failure leaves the independently corroborated text boundaries available; it cannot
authorize an unconfirmed geometric correction.
An extra ASCII space beside a word-internal ASCII hyphen can also be removed
when both independent readers agree and the same-font/baseline glyph coordinates
confirm a tight boundary. Numeric forms, identifiers, other dash characters,
real gaps and unresolved geometry remain literal. This changes only spacing;
it does not rewrite the word or hyphen. `geometry_joins` counts confirmed
boundaries, including ones that already had correct spacing, not removed spaces.
Native failure or unresolved disagreement retains the entire legacy page.
No OCR, inferred words, reordering or topic-specific correction is applied.

An optional bounded operand trace in `pdf_glyphs.py` isolates undecoded glyph
names that would otherwise block all page recovery. It uses the pinned pypdf
encoding adapter, actual text operand bytes and declared font differences;
literal text resembling a glyph name never qualifies. Every source character
must align, and each opaque name must map to one native control glyph in the
same font, verified against the complete native character dictionary. The
original name and both adjacent gaps remain untouched. Only the other aligned
text can receive existing spacing recovery. A partial match, wrong font,
ordinary character disagreement or missing geometry gives no such permission.
The trace is restricted to 32768-byte pages, 128 font maps, 131072 operations,
64 graphics-state levels and 32 nested forms. It does not modify PDF resources.

Optional `provenance.pdf_extraction`, method `page-text-preservation/8`, records
native/recovered/fallback/changed page counts, recovery/fallback reasons,
inserted/removed spaces, decoded/unresolved control glyph counts and native warnings.
`spacing_corroboration` records attempted/aligned pages, secondary opaque glyphs,
and reader/count/page/size/content failures; aligned pages plus failures equals
attempted pages. Its counts describe comparison evidence, not semantic accuracy.
Geometry page/confirmed-boundary counts and bounded geometry failure reasons
are recorded separately; confirmed boundaries can include spaces already present
in the old text and are not an additional count of output insertions.
The first three page counts sum to the physical page count; changed pages may
overlap native/recovered pages. The schema also accepts historical method
`page-text-preservation/1` through `/7` diagnostics with their original closed fields.
Its `semantic_verification=false` is intentional: agreement cannot establish
correct layout or complete extraction. Fallback may retain merged words, and
unconfirmed spacing remains unchanged. PDFium disagreement cannot weaken the
original page, character or byte-limit checks.
Unresolved-control counts cover C0/C1 glyphs, not all possible font errors.
`opaque_glyph_alignment` separately records attempted/aligned pages, retained
undecoded glyph names and size/unavailable/alignment failures. Retained names
are not decoded symbols, and this count does not imply that text changed.
These diagnostics remain visible in source descriptors supplied to consumers.
The diagnostic also appears in Workflow source descriptors. Original PDF bytes,
physical blank pages, UTF-8 byte indexes, immutable archive reads and quotas
retain their existing contracts. Revision 1 still uses its original pypdf path;
historical snapshots are never re-extracted in place.

For ordinary HTTP, the archived `original` is decoded response bytes and
`representation="content_decoded"`. For browser capture it is the UTF-8 DOM
used for extraction and **`representation="rendered_dom"`**. Browser metadata
records capture time, DOM bytes, relayed/blocked requests and failed resources.
Response transfer/decoded-byte fields describe the final main HTTP response;
DOM bytes and aggregate network usage are separate. No API claims a rendered
DOM is an untouched HTTP response or that an HTML abstract is a full PDF.

The worker retains its 60-second bound and 512-MiB Windows Job ceiling. Browser
capture shares a maximum of 40 HTTP requests and 32 MiB decoded traffic with
earlier attempts; each browser resource is capped at 2 MiB, and the stored
original/text caps remain 8/4 MiB. Images, fonts, media, WebSockets, service
workers and non-GET requests are blocked. Login/CAPTCHA/denial pages are not
published as evidence. This intentionally leaves some interactive sites
unavailable. Browser settlement is bounded, not a claim every app finished
loading. Windows tracks and terminates the complete worker/browser process tree.

`auto` currently renders after failed static extraction; a successful but thin
static page does not automatically trigger enrichment. A script-heavy purchase
page reproduced this limit in both model runs. Raising the script cap alone is
not a verified fix: an isolated 8-MiB-script probe exceeded the real 512-MiB Job
ceiling, while a 2-MiB control returned only the original thin text. The decoded
traffic budget is not a browser memory bound. Optional rendering needs static
result retention outside the renderer's termination boundary before enabling
such an enhancement. That redesign remains pending; current successful fetches
must not be interpreted as proof that all dynamically loaded facts were captured.
The Meta example also contained the declared Canadian price in static JSON-LD;
revision 17 now preserves that data without rendering. Phase 33 corrects the
earlier raw-absence diagnosis. This does not resolve the independent renderer
failure-domain limitation for content available only after JavaScript execution.
See phase 30 of [scenario diagnostics](../scenario-systemic-diagnostics.md).

The Engine commits extracted text before returning a snapshot reference.
Acquisition populates the source manifest and token estimates; orchestrator
context selection and `document.read` control what Agents receive. No browser
or fetch operation runs inside an Agent's model context.

## Use and compare

```shell
uv run --locked deepresearch --store local/search-demo tool web.search --revision 4 --arguments '{"query":"compare meta quest 3 and apple vision pro","max_results":10}'
uv run --locked deepresearch --store local/fetch-demo tool web.fetch --revision 2 --arguments '{"url":"https://vr-compare.com/compare?h1=0q3goALzg&h2=8aL1JxO3T"}'
```

Shell JSON quoting varies; stdin works in every supported CLI. New method
consumers send `method_revision: 10`; `examples/baseline-request.json` shows a
complete request. The HTTP source/context/artifact APIs are unchanged.

The fixed test corpus is `examples/benchmarks/web-tools.json`. It contains the
three exact user questions and all 34 prior attempted URLs, including failures.
The driver uses real Engine workers, SQLite and public archive/read APIs, with
**zero model calls** and no query rewriting:

```shell
uv run --locked python examples/benchmark_web_tools.py --search-revision 3 --fetch-revision 1 --store local/control-store --output local/control
uv run --locked python examples/benchmark_web_tools.py --search-revision 4 --fetch-revision 2 --store local/candidate-store --output local/candidate
```

Use fresh output directories to preserve evidence. Every successful fetch is
checked against all three archived component hashes and fully read back through
`document.read`. `ready_for_human_review` establishes transport/archive integrity;
it deliberately does **not** assert relevance, truth, completeness or report
quality. Read [the measured comparison](../web-tools-comparison.md) for results
and remaining limitations.
