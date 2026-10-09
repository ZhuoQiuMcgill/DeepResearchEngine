# Web-tool selection comparison — 2026-10-03

The selected free open-source stack is **SearXNG + curl_cffi + HTTPX fallback +
Playwright Chromium + Trafilatura/pypdf**. It is registered as `web.search@4`
and `web.fetch@2`, and pinned by `baseline@10`. The baseline keeps revision 9's
Agent instructions, schemas and research policy. See [setup and contracts](usage/web-tools.md).

## Controlled test

The immutable fixture in [web-tools.json](../examples/benchmarks/web-tools.json)
preserves the user's exact input, including spelling and capitalization:

1. `compare meta quest 3 and apple vision pro`
2. `How do I flight from GuangZhou to Montreal?`
3. `What food can help me sleep well?`

Search receives each question literally, requesting ten results. Fetch receives
all 34 exact URLs attempted in the previous cross-topic workflow trials: 14
headsets, 10 flights, 10 sleep. No failed URL is omitted, no URL is added to make
the score better, and query-parameter order is preserved. These are 34 distinct
literal URLs, not necessarily 34 distinct documents; three publisher URLs, for
example, lead to the same abstract.

[benchmark_web_tools.py](../examples/benchmark_web_tools.py) runs real recorded
Engine subprocesses and SQLite Storage. It checks all archived component hashes
and reconstructs the complete text through `document.read`. There are **zero
model calls**. This separates source acquisition from Agent selection,
instructions, reasoning and report quality.

## Results

| Case | Old search 3 results | New search 4 results | Old fetch 1 archives | New fetch 2 archives |
| --- | ---: | ---: | ---: | ---: |
| Headset comparison | Failed | 10 | 7/14 | 11/14 |
| Guangzhou → Montreal | 10 | 10 | 5/10 | 9/10 |
| Foods and sleep | 5 | 7 | 7/10 | 8/10 |
| Total | 2/3 questions succeeded | 3/3 questions succeeded | **19/34** | **28/34** |

All 28 new successful archives were completely read back, with matching
original/text/index hashes and complete durable tool recording. Nine previously
failed URLs succeeded; no old successful URL regressed. The selected search
results retained their literal queries, destination links and nonempty snippets.
This is an observed live comparison, not a statistical availability guarantee:
search engines can change results or present a CAPTCHA between calls.

“Archive succeeded” is deliberately narrower than “good evidence.” The old
19 includes a Verywell page with only **15 bytes** (`Skip to content`) and a
Sleep Foundation page whose selected body was a mattress promotion. Counting
HTTP 200 or successful storage alone would hide these extraction failures.

Manual source inspection found these concrete improvements:

| Source | Old retained material | New retained material |
| --- | --- | --- |
| VRcompare comparison/specification pages | Empty HTML shell | Rendered specification tables; product names retained in table columns |
| Verywell food/sleep article | 15-byte navigation label | About 14 KB of article content |
| Sleep Foundation nutrition page | Mattress promotion and reference list | Nutrition/sleep article sections and references |
| FlightRoutes | HTTP failure | Route and connecting-flight page text |
| EVA Air route page | HTTP failure | Route page with explicit “no matching fares” state; not a confirmed itinerary |
| Springer PDF-shaped URL | Redirect failure | Public HTML abstract/metadata, explicitly not a full PDF |
| PMC review article | Available through HTTPX | Still available: curl cookie challenge rejected, HTTPX recovers the same 93,624-byte text |

The final extractor uses Trafilatura's image-alt-text option because dropping
image-bearing containers also dropped product names from comparison table
headers. This stores source-provided alt text and URLs; it does not download
images or infer their contents. Generic pages retain Markdown headings, tables
and links. Scholarly pages keep labelled abstract/metadata/reference boundaries.

The main remaining failures are six fixed URLs: a Sage SSO redirect chain, ACM,
SSRN, two ScienceDirect pages returning 403, and Booking's JavaScript-dependent
page. These failures remain explicit and produce no fabricated evidence.
Dynamic capture blocks non-GET requests and does not solve interactive access
challenges; some sites therefore remain unavailable.

## Why these tools

| Candidate | Observed selection evidence |
| --- | --- |
| Existing direct DDGS adapters | Kept as search revisions 1–3. Literal-topic probes encountered missing results, challenges and parser/backend limitations. |
| Direct Bing / Bing RSS | The three-question probe included dictionary, unrelated product and restaurant results. Not enabled simply to increase result counts. This observation is specific to this trial. |
| Google, Brave, Mojeek, Startpage | Direct/service probes returned denied, rate-limited or empty responses in this environment. Not selected for the published profile. |
| Self-hosted SearXNG, Yahoo + DuckDuckGo | Complete relevant-topic result lists with engine attribution and explicit partial failures; native aggregation and parsers avoid maintaining a second custom search scraper. |
| curl_cffi | Recovered several route and health sites that rejected the original HTTP transport. Kept its browser-compatible TLS and cookie-preserving session behind existing bounds. |
| HTTPX | Retained as an alternate because replacing it everywhere lost the previously available PMC article. |
| Playwright bundled Chromium | Recovered real VR comparison tables from app shells. The Engine owns the worker and all browser descendants. |
| Trafilatura | Direct generic-page extraction recovered content removed by the handwritten DOM pruning rules; pypdf remains the PDF extractor. |
| Crawl4AI / Scrapling | Considered as open-source frameworks, but not benchmarked end-to-end here. The Engine already owns concurrency, archival, cancellation and source access, so the selected lower-level libraries fit without adding another orchestration layer. No performance superiority over those frameworks is claimed. |

The search software is open source; Yahoo/DuckDuckGo's indexes are not. This
configuration uses their free public endpoints and requires no paid API key.
Upstream rate limits and source restrictions remain external dependencies.

## Evidence and checks

Reproducible driver commands are in [web-tools usage](usage/web-tools.md).
Local evidence is retained under `local/web-tools-selection-20261003/`:

- `control/report.json`: fresh search 3/fetch 1 control.
- `release/report.json`: final search 4/fetch 2 comparison with identical fixture.
- Per-URL `original.bin`, `text.txt`, `index.json`, `read-*.json` and verification
  records: exact stored and read material.
- `comparison.json`, `database-integrity.json`, `release-tests.log`,
  `final-tests.log`, `method-control-test.log`: measurements and checks.
- Earlier `candidate/`, `final/`, `acceptance/` and targeted rechecks: retained
  intermediate results, including the cookie-page false positive that was fixed.

Tool/extraction/protocol, example and architecture checks passed (339 tests).
Additional affected workflow/application/connection checks passed (167 tests,
overlapping some tool tests). A separate method-control check proves that
baseline 10 retains baseline 9's role pins and input/parameter schemas.
Actual Chromium tests verify driver/browser/renderer termination on cancellation
and deadline, with zero active processes in the owning Windows Job. Live stores
pass SQLite integrity and foreign-key checks; successful source reads are
byte-for-byte verified, not inferred from log messages.

This comparison does not claim three new end-to-end research reports or improved
report factual accuracy. It establishes better source access and extraction,
while keeping workflow/Agent variables fixed. Source dates, product generations,
travel dates, reverse routes, abstracts versus full text, commercial bias and
medical evidence strength still require correct selection and interpretation.
