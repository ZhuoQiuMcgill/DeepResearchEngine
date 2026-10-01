# Free search, retrieval, HTML and PDF research

CLI Toolset team, 2026-09-30 (America/Toronto). **Research complete; PM has selected the initial design stack. Transport, shared schemas/limits and implementation remain pending approval.** Sources below were checked on this date. Package versions are the latest non-prerelease releases found, not a promise of stability. HTTPX still declares a Beta development classifier.

## PM selection and research recommendation

PM selected **DDGS 9.16.0 + HTTPX 0.28.1 + Trafilatura 2.2.0 + pypdf 6.19.0** for the initial design, matching this report's recommendation. The decision is recorded in [decisions.md](../teams/decisions.md) and the [team brief](../teams/cli-toolset.md); it does not authorize production dependencies or implementation. All four installed and executed on Windows x64 with CPython 3.11.15 in an isolated uv environment without required API keys, browsers or OCR. HTML/PDF retrieval and extraction worked on the small public corpus. Search is the weak point: **5 of 12 DDGS attempts across three queries/four modes** returned results; all four attempts for the niche technical query failed. These are repeated modes over three queries, not validated research-task coverage.

DDGS is a **replaceable, best-effort development backend**. PM's initial configuration is explicit **Google then DuckDuckGo**, with named backend outcomes, centrally bounded fallback, unsupported-filter rejection and visible outages. Avoid silent automatic merging and the zero-success Brave profile. Google and DuckDuckGo returned useful candidates in these trials; generic failures do not establish a specific rate-limit/blocking cause. Representative-task availability and URL-fidelity checks must pass before teammate acceptance or experiments; those gates have not passed. Initial source scope is static HTML and unencrypted text PDFs. Preserve content-decoded source bytes, encoding/representation metadata and hashes, deriving text from that same retained response.

**SearXNG + the same fetch/extraction/PDF stack** is an alternative for centralized administrative control if the group accepts maintaining a Linux service. Better reliability is unproven: it was not deployed locally, and a single public-instance JSON trial returned HTTP 429. This report does not recommend depending on an arbitrary free public instance. SearXNG's upstream search engines can still block requests.

Requests/readability-lxml are viable simpler synchronous alternatives; this corpus does not demonstrate a quality advantage over HTTPX/Trafilatura. PyMuPDF was much faster on the one PDF, but its AGPL/commercial licensing and native engine add a decision the initial text-only requirement does not need. These alternatives remain unselected. Browser retrieval remains outside the initial scope. The selected stack is a design target; project dependency installation remains unauthorized.

## Version, source and license evidence

| Component | Exact version / release date | License | Environment / primary source |
| --- | --- | --- | --- |
| DDGS | 9.16.0 / 2026-08-26 | MIT | Python >=3.10; universal wheel. Canonical package `ddgs`, repository `deedy5/ddgs`. [PyPI](https://pypi.org/project/ddgs/9.16.0/), [tagged metadata](https://github.com/deedy5/ddgs/blob/v9.16.0/pyproject.toml). |
| SearXNG | Git commit `a9d99003344ac3879ec45c56c661283482a92a39`, 2026-09-30T05:39:34Z; docs identity `2026.9.30+a9d990033` | AGPL-3.0-or-later | No numbered GitHub release selected. Python >=3.10; service installation is separate from our uv client. [Pinned source](https://github.com/searxng/searxng/tree/a9d99003344ac3879ec45c56c661283482a92a39), [license](https://github.com/searxng/searxng/blob/a9d99003344ac3879ec45c56c661283482a92a39/LICENSE). |
| HTTPX | 0.28.1 / 2024-12-06 | BSD-3-Clause | Python >=3.8; sync/async; universal wheel. [PyPI](https://pypi.org/project/httpx/0.28.1/), [source](https://github.com/encode/httpx/tree/0.28.1). |
| Requests | 2.34.2 / 2026-05-14 | Apache-2.0 | Python >=3.10; synchronous; universal wheel. [PyPI](https://pypi.org/project/requests/2.34.2/), [source](https://github.com/psf/requests/tree/v2.34.2). |
| Trafilatura | 2.2.0 / 2026-07-31 | Apache-2.0 | Python >=3.10; native lxml dependency. Releases before 1.8 had GPLv3+ licensing. [PyPI](https://pypi.org/project/trafilatura/2.2.0/), [tagged metadata](https://github.com/adbar/trafilatura/blob/v2.2.0/pyproject.toml). |
| readability-lxml | 0.9 / 2026-08-27 | Apache-2.0 | Python >=3.8.2,<3.15; native lxml dependency. [PyPI](https://pypi.org/project/readability-lxml/0.9/), [exact dependencies](https://pypi.org/pypi/readability-lxml/0.9/json). |
| pypdf | 6.19.0 / 2026-09-16 | BSD-3-Clause | Python >=3.9; pure Python, no mandatory runtime dependencies on 3.11. [PyPI](https://pypi.org/project/pypdf/6.19.0/), [tagged metadata](https://github.com/py-pdf/pypdf/blob/6.19.0/pyproject.toml). |
| PyMuPDF | 1.28.2 / 2026-08-06 | AGPLv3 or Artifex commercial license | Python >=3.10; native MuPDF; Windows x64 abi3 wheel approximately 19.8 MB. [PyPI](https://pypi.org/project/pymupdf/1.28.2/), [license documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright). |
| ddgr, comparison only | 2.2 / 2023-12-29 | GPLv3 | Python >=3.8; JSON CLI, same DDG upstream exposure; not installed. [PyPI](https://pypi.org/project/ddgr/2.2/), [official repository](https://github.com/jarun/ddgr). |
| Playwright Python, out of initial scope | 1.63.0 / 2026-09-15 | Apache-2.0 for Python package; browser/component licenses are separate | Python >=3.10 per current package metadata; Windows wheels. [PyPI](https://pypi.org/project/playwright/1.63.0/), [installation](https://playwright.dev/python/docs/intro). |

The former [duckduckgo-search package](https://pypi.org/project/duckduckgo-search/) redirects users to `ddgs`. Old tutorials are not evidence for this release. These clients/services are open-source software; the upstream search indexes and websites are separate services.

### Resolved dependencies and distribution implications

The research environment installed all comparison packages together. Its **33-package closure is broader than any proposed production combination**. Exact resolved versions and installed distribution metadata are preserved in `environment.json` and `freeze.txt` under the ignored scratch path below. Top-level pins alone do not freeze dependencies.

| Resolved packages | Declared license evidence from installed metadata / primary distribution |
| --- | --- |
| anyio 4.15.1; charset-normalizer 3.5.2; h11 0.16.0; primp 2.0.1; pytz 2026.4; six 1.17.0; tzlocal 5.4.4; urllib3 2.8.0 | MIT |
| babel 2.18.0; click 8.5.0; dateparser 1.4.3; httpcore 1.0.9; httpx 0.28.1; idna 3.20; lxml 6.1.3; lxml_html_clean 0.4.5; pypdf 6.19.0 | BSD-3-Clause |
| courlan 1.4.0; htmldate 1.10.0; readability-lxml 0.9; requests 2.34.2; trafilatura 2.2.0; tzdata 2026.4 | Apache-2.0 declared for packages; data/native notices can be additional |
| jusText 3.0.2 | BSD-2-Clause |
| cssselect 1.3.0 | BSD-3-Clause, verified from the installed wheel's LICENSE (metadata abbreviates it to BSD) |
| python-dateutil 2.9.0.post0 | Dual BSD/Apache; preserve component notices |
| typing_extensions 4.16.0 | PSF-2.0 |
| regex 2026.9.29 | Apache-2.0 AND CNRI-Python |
| certifi 2026.7.22 | MPL-2.0 |
| chardet 5.2.0 | LGPLv2+ |
| tld 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later |
| ddgs 9.16.0 | MIT |
| pymupdf 1.28.2 | AGPLv3/commercial |

Important verified details:

- DDGS requires Click, primp and lxml. primp 2.0.1 has a Windows `cp310-abi3` wheel; lxml 6.1.3 has a CPython 3.11 Windows x64 wheel. Neither needed a compiler in the actual install. [DDGS requirements](https://github.com/deedy5/ddgs/blob/v9.16.0/pyproject.toml), [primp files](https://pypi.org/project/primp/2.0.1/#files), [lxml files](https://pypi.org/project/lxml/6.1.3/#files).
- HTTPX requires certifi, httpcore, AnyIO and idna. Requests adds urllib3 and charset-normalizer. HTTP/2, SOCKS and optional compression extras were not installed. [HTTPX requirements](https://github.com/encode/httpx/blob/0.28.1/pyproject.toml), [Requests requirements](https://github.com/psf/requests/blob/v2.34.2/pyproject.toml).
- Trafilatura's closure includes Courlan/htmldate/jusText/lxml and date-related packages. Courlan introduces tld's reciprocal license options. [Tagged Trafilatura requirements](https://github.com/adbar/trafilatura/blob/v2.2.0/pyproject.toml), [Courlan 1.4.0 metadata](https://pypi.org/pypi/courlan/1.4.0/json), [tld 0.13.2](https://pypi.org/project/tld/0.13.2/).
- readability-lxml 0.9 pins `chardet>=5.2,<6`, so current chardet 7 licensing does not describe the installed 5.2.0 dependency. [Exact requirements](https://pypi.org/pypi/readability-lxml/0.9/json), [chardet 5.2.0](https://pypi.org/project/chardet/5.2.0/).
- lxml's official binary license inventory includes zlib, **iconv under LGPL-2.1**, and libxml2/libxslt/libexslt under MIT, plus other notices. Thus the DDGS/HTML binary closure is not entirely permissive even though the top-level packages are MIT/Apache/BSD. [Tagged lxml LICENSES.txt](https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/LICENSES.txt).

License implications for PM: retain applicable copyright/license/NOTICE texts when distributing packages; reciprocal components require their applicable source/notice provisions. certifi's MPL applies to covered files, tld permits a license choice, and chardet/iconv bring LGPL terms. AGPL SearXNG/PyMuPDF requires explicit review of distribution, modification and network-use obligations before integration; running a separately deployed search service and embedding a PDF library are different integration choices. A complete audit of each distributed wheel, bundled native libraries/data and the eventual selected lockfile has **not** been performed. Do not promise that these dependencies impose no source-sharing obligations. Primary license files and package metadata above establish the identified issues, not a blanket legal conclusion.

## Comparable combinations

| Combination | Functionality and monetary requirements | Local/setup burden | Reliability and limits | Trial evidence |
| --- | --- | --- | --- | --- |
| A: DDGS + HTTPX + Trafilatura + pypdf | Search, static HTML, text PDF; no required subscription/API key | uv + Windows wheels; no browser/service; CPU for extraction | Search scraping can fail; main-content heuristics; no JS/OCR | Installed and all parts exercised; 5/12 DDGS calls successful across all search modes; HTML/PDF successful on tiny corpus |
| B: SearXNG + HTTPX + Trafilatura + pypdf | Search via configurable engine service, same retrieval/extraction; selected engines can operate without paid APIs | Separate Linux service, network/hosting/maintenance; Windows via supported Linux/container route; uv client alone insufficient | JSON must be enabled; engines may be rate-limited; public hosts may block | No local deployment; one public request returned 429 |
| C: DDGS + Requests + readability-lxml + pypdf | Same initial scope; no paid API/key required | uv, native lxml; synchronous HTTP; additional LGPL chardet | No default HTTP timeout unless wrapper supplies it; cleaned HTML needs text conversion | Requests/readability/pypdf exercised on same URLs; search evidence shared with A |
| D: DDGS + HTTPX + Trafilatura + PyMuPDF | Same text scope plus richer PDF APIs; AGPL route can avoid license purchase if its obligations are accepted | Larger native wheel; licensing decision; process isolation | No automatic OCR; heuristic reading order; unsupported concurrent multithread use | Real PDF extraction was much faster on one sample; fidelity/complex-layout corpus untested |
| E: ddgr + HTTPX + Trafilatura + pypdf | JSON DDG CLI; no mandatory paid API | Simpler search client but GPL decision and single upstream | No independent resilience against DDG blocking | Documented only; untested |
| F: either search stack + Playwright + extractor + PDF library | Can render some JS pages | uv package **plus browser downloads**, service/runtime resources and browser maintenance | Rendering does not defeat login/access controls or guarantee useful content | Documented only; deliberately not installed or rendered |

"No paid API requirement" is supported for the candidate configurations, not "zero expense." Network, CPU, storage, electricity, hosting and maintenance remain. Actual monetary billing was not measured; cost is **unknown**, not invented as zero. Search clients do not come with a guaranteed requests/day quota. SearXNG engines may include optional keyed/commercial sources; enable a reviewed no-key set for this requirement.

### Search contracts and reliability findings

DDGS 9.16.0 advertises ten text engines, but the released registry disables Bing and Yandex text engines. Its active set is DuckDuckGo, Brave, Google, Mojeek, Startpage, Yahoo, Wikipedia and Grokipedia. Entirely invalid/disabled backend names fall back to automatic search, making backend validation essential. Its automatic mode prioritizes Wikipedia/Grokipedia, shuffles other engine order, merges/deduplicates/ranks results, and does not preserve reliable per-result upstream identity in its public result schema. A wrapper should execute named engines separately when provenance matters. [Registry](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/__init__.py), [Bing](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/bing.py), [Yandex](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/yandex.py), [aggregator](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/ddgs.py).

The generic text API uses `region`, SafeSearch, `timelimit`, `max_results`, `page` and backend; there is no independent general language or start/end-date field. Adapter support differs: DDG ignores SafeSearch, Mojeek ignores time, Yahoo ignores region/SafeSearch, and Wikipedia/Grokipedia ignore page/time/SafeSearch. Google derives language/country from region, while Brave ignores the language component. A generic accepted field is not evidence it was applied. [Released README](https://github.com/deedy5/ddgs/blob/v9.16.0/README.md), [DDG](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/duckduckgo.py), [Google](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/google.py), [Brave](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/brave.py), [Mojeek](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/mojeek.py), [Yahoo](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/yahoo.py), [Wikipedia](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/wikipedia.py), [Grokipedia](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/grokipedia.py).

One requested page is sent to each selected engine; `max_results` does not iterate further pages automatically. Rankings, localization and source availability change; snippets and date-like strings are discovery material. The Google adapter can strip destination query strings when unwrapping result links, so URL fidelity also needs a regression corpus. These behaviors are documented in released source; pagination/localization/date guarantees were not live-tested. DDGS's stock CLI is human-formatted; JSON file output is available, but our one-JSON stdin/stdout protocol needs a Python-API wrapper. [Aggregator](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/ddgs.py), [Google URL handling](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/engines/google.py), [CLI](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/cli.py).

Public issues report HTTP 403, weak rate-limit error mapping and mixed-engine failure behavior. Those are historical reports, not diagnoses of our failures. Released code can map non-200/empty results to a generic exception. Access remains subject to upstream policies; do not bypass challenges or restrictions. [Issue 480](https://github.com/deedy5/ddgs/issues/480), [issue 478](https://github.com/deedy5/ddgs/issues/478), [issue 427](https://github.com/deedy5/ddgs/issues/427), [base handling](https://github.com/deedy5/ddgs/blob/v9.16.0/ddgs/base.py), [Google terms](https://policies.google.com/terms?hl=en-US), [DuckDuckGo terms](https://duckduckgo.com/terms).

SearXNG provides GET/POST search, query, categories/engines, `pageno`, `language`, SafeSearch and time-range fields. JSON/CSV/RSS must be enabled in server configuration; unsupported output formats can return 403. Filters still depend on engine support. Its limiter is configurable and uses Valkey; reverse proxy/header/network configuration affects operation. This is an operating requirement, not an independent search index or an upstream-limit exemption. [Search API](https://docs.searxng.org/dev/search_api.html), [search settings](https://docs.searxng.org/admin/settings/settings_search.html), [limiter](https://docs.searxng.org/admin/searx.limiter.html), [installation](https://docs.searxng.org/admin/installation.html).

The pinned SearXNG server requirements include native `curl_cffi==0.16.3` (MIT), `lxml==6.1.3` (BSD plus bundled notices), `granian[pname]==2.8.3` (BSD-3-Clause), and `valkey==6.1.1` Python client (MIT). Its Compose template includes a separate `valkey:9-alpine` server (Valkey 9 BSD-3-Clause). These are documented dependencies, not a locally resolved/deployed service. Mutable container/base tags require image digests and a full native/container inventory for a reproducible distribution. No image was pulled. [Pinned requirements](https://github.com/searxng/searxng/blob/a9d99003344ac3879ec45c56c661283482a92a39/requirements.txt), [server requirements](https://github.com/searxng/searxng/blob/a9d99003344ac3879ec45c56c661283482a92a39/requirements-server.txt), [Compose](https://github.com/searxng/searxng/blob/a9d99003344ac3879ec45c56c661283482a92a39/container/docker-compose.yml), [Valkey license](https://github.com/valkey-io/valkey/blob/9.0.0/COPYING).

Windows service deployment is documented through Linux/container routes rather than an established native Windows server setup. Docker Desktop's documented 8 GB host RAM prerequisite is a host requirement, not measured SearXNG RAM; education/personal use can meet its free-use terms. CPU/RAM/traffic and Docker/WSL readiness were not tested. [Docker Windows setup and terms](https://docs.docker.com/desktop/setup/install/windows-install/), [SearXNG Docker installation](https://docs.searxng.org/admin/installation-docker.html).

### Retrieval, provenance and extraction

HTTPX/Requests provide streaming response bodies, response/status headers and redirect history. HTTPX defaults to disabled redirects and five-second network-inactivity timeouts; Requests follows redirects and has no default timeout. Neither timeout is an overall job deadline. The wrapper must add a process deadline, explicit redirect limit, streaming limits, status/media validation, verified TLS and no nested retries. HTTPX transport retries cover connect failures/timeouts rather than arbitrary read/HTTP errors. [HTTPX streaming](https://www.python-httpx.org/quickstart/#streaming-responses), [timeouts](https://www.python-httpx.org/advanced/timeouts/), [transport](https://www.python-httpx.org/advanced/transports/), [Requests behavior](https://requests.readthedocs.io/en/latest/user/quickstart/).

Both HTML extractors can work on **the same retained response body**; a second source fetch is unnecessary. Trafilatura directly produces text with configurable comments/tables/metadata and fallbacks, and can return `None`. readability produces cleaned article HTML; the trial then converted it to text with lxml. Neither guarantees semantic reading order, correct code/table preservation or a complete article. readability output is not a general-purpose HTML sanitizer. [Trafilatura core API](https://trafilatura.readthedocs.io/en/latest/corefunctions.html), [troubleshooting](https://trafilatura.readthedocs.io/en/latest/troubleshooting.html), [readability usage/security](https://pypi.org/project/readability-lxml/0.9/).

The trial retains **content-decoded original response bytes**, not packet-level wire bytes. The article still arrived gzip-encoded despite `Accept-Encoding: identity`; the client decoded it before hashing/extraction. Preserve the representation label and Content-Encoding. Exact compressed-body retention would instead require raw streaming and separately bounded decoding. Record requested/final URL, redirect chain, retrieval UTC, HTTP status/media/encoding, body size/digest, extractor/library versions/options, derived-text digest and immutable snapshot reference. Sanitized headers only; omit credentials/cookies. Search query/engine/backend rank/time belongs with discovery results, not an invented verified quotation.

### PDF findings and exclusions

pypdf and PyMuPDF preserve physical pages through page-oriented APIs. Use public one-based physical page numbers plus optional printed labels; those labels are not interchangeable with physical page indexes. Retain a per-page text map in each immutable extraction revision. [pypdf PdfReader](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html), [PyMuPDF text recipes](https://pymupdf.readthedocs.io/en/latest/recipes-text.html).

pypdf is not OCR. Scans can produce empty text; existing OCR layers can be read without verifying their accuracy. Complex positioning and tables can be wrong. Encrypted/AES PDFs need explicit password policy and an optional crypto dependency; no passwords/crypto extras were used here. A small compressed file can have huge expanded page streams; upstream documents a roughly 300 MB uncompressed stream requiring 10 GB RAM. Byte/page limits alone do not enforce memory limits. [Extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html), [encryption](https://pypdf.readthedocs.io/en/stable/user/encryption-decryption.html), [robustness](https://pypdf.readthedocs.io/en/stable/user/robustness.html).

PyMuPDF offers blocks/words/bounding boxes and a sorting heuristic, which still cannot guarantee semantic reading order. OCR requires separately installed Tesseract/language data; it is not automatic. Concurrent multithreaded PyMuPDF use is unsupported; use isolated processes. [OCR](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html), [multiprocessing](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html).

Initial contract: text-bearing, unencrypted PDFs only; explicitly classify encrypted, scanned/no-text, malformed, oversized and processing-limited documents. OCR, JS rendering, authentication and bypass of site restrictions are outside the initial toolset. Playwright needs separately downloaded version-matched browsers and browser dependencies; resources/network traffic depend heavily on pages and assets. Windows package availability does not establish an installed browser or a working rendered fetch. [Playwright browsers](https://playwright.dev/python/docs/browsers), [system requirements](https://playwright.dev/python/docs/intro). No browser or JS trial was performed.

## Live trial method and results

Observed host: Windows x64, CPython **3.11.15**, uv **0.11.6**. System `python` was 3.12.7; it was not used for these probes. Environment/script/output live only under the ignored research scratch directory:

`D:\Projects\DeepResearchEngine\.uv-cache\cli-toolset-research\`

Files: `probe.py`, `environment.json`, `freeze.txt`, `results.jsonl`, `results-auto.jsonl`, and `responses/` with fetched bytes and extracted text. This disposable research capture is not an engine snapshot store or a Storage implementation. No `local/.env` read, model call, credential use, runtime module edit or project dependency update occurred.

Reproduction of the initial trial (creates only a separate research environment):

```powershell
uv --cache-dir .uv-cache/cli-toolset-research/cache venv --python .uv-python/cpython-3.11.15-windows-x86_64-none/python.exe .uv-cache/cli-toolset-research/.venv
uv --cache-dir .uv-cache/cli-toolset-research/cache pip install --python .uv-cache/cli-toolset-research/.venv/Scripts/python.exe ddgs==9.16.0 httpx==0.28.1 requests==2.34.2 trafilatura==2.2.0 readability-lxml==0.9 pypdf==6.19.0 pymupdf==1.28.2
.uv-cache/cli-toolset-research/.venv/Scripts/python.exe .uv-cache/cli-toolset-research/probe.py
# Three supplementary calls, each saved separately:
.uv-cache/cli-toolset-research/.venv/Scripts/python.exe .uv-cache/cli-toolset-research/probe.py search auto 0
.uv-cache/cli-toolset-research/.venv/Scripts/python.exe .uv-cache/cli-toolset-research/probe.py search auto 1
.uv-cache/cli-toolset-research/.venv/Scripts/python.exe .uv-cache/cli-toolset-research/probe.py search auto 2
```

Another teammate can use their installed Python 3.11 path. `freeze.txt` can pin the complete comparison closure with `uv pip install --requirement`; it records versions, not an audited hash-locked artifact set. A later PM-approved project lock must be generated for the selected stack. [uv locking](https://docs.astral.sh/uv/concepts/projects/sync/).

The initial sandbox installation could not open network sockets (Windows error 10013); the authorized public dependency/probe commands then succeeded through the approval mechanism. This was an environment limitation, not a library failure. No access challenge was bypassed.

Every worker records request/query/options, UTC start/end, elapsed time and structured result/error. Search timeout 8 seconds; fetch timeout 12 seconds, max redirects 5, decompressed response-body limit 8 MiB; primary worker overall deadline 45 seconds. Search calls were sequential with a two-second gap. HTTP clients had environment proxy/credential inheritance disabled for the retrieval probes. HTTPS certificate verification remained enabled. No retries were added by the probe. DDGS's internal concurrency/HTTP count was not instrumented and is recorded as **unknown**.

Timestamps span **2026-10-01 02:26:21–02:27:21 UTC**, which is **2026-09-30 22:26:21–22:27:21 Toronto**. Durations below include Python imports and worker operations, not parent process startup. These are one-shot measurements, not sustained benchmarks.

### Search: identical three cases, four modes

Options: `max_results=5`, `page=1`, `region=us-en`, `safesearch=moderate`; no date filter. Public queries were exactly:

1. General: `renewable energy storage`
2. Niche technical: `Python asyncio TaskGroup cancellation`
3. Domain syntax: `site:docs.python.org asyncio TaskGroup`

| Mode | General | Niche technical | Domain syntax |
| --- | --- | --- | --- |
| DDGS duckduckgo | 5 results, 0.884 s | DDGSException: No results found, 0.295 s | Same error, 0.284 s |
| DDGS brave | Same error, 0.271 s | Same error, 0.269 s | Same error, 0.266 s |
| DDGS google | 5 results, 0.628 s | Same error, 0.639 s | 5 results, 0.530 s; all five hosts `docs.python.org` |
| DDGS auto (supplement) | 5 merged results, 0.946 s | Same error, 2.908 s | 5 results, 1.254 s; all five hosts `docs.python.org` |

Five successful calls, seven generic errors. Successful general calls included Wikipedia and other source candidates; successful domain calls included Python documentation URLs. The technical failures' cause was not identifiable from these exceptions. The query syntax passed a host check in the two successful domain calls; this does not verify a dedicated domain API, all domains/subdomains, date precision, or localization. No source snippet was promoted to a fetched quote. Auto per-result engine attribution and actual HTTP usage remain unknown.

Supplementary hosted SearXNG trial: official [instance inventory](https://searx.space/) listed `https://anonsearch.win/` with the pinned version above. One GET to `/search?q=renewable%20energy%20storage&format=json&pageno=1&language=en-US&categories=general` at **2026-10-01T02:27:49.924Z** returned **HTTP 429, text/html, 17 bytes, 204 ms**. Explicit research user agent, 15-second timeout, 1 MiB response buffer. The probe stopped; niche/domain cases were not run. This only establishes that this public endpoint denied that request. It does not measure a local SearXNG deployment, and no instance was installed or reconfigured.

### Retrieval and extraction: same four sources for both HTTP clients

| Case / exact source | HTTPX: status, body bytes, elapsed | Requests: status, body bytes, elapsed |
| --- | --- | --- |
| [Python.org article](https://www.python.org/success-stories/building-robust-codebases-with-pythons-type-annotations/) | 200; 57,151; 0.967 s | 200; 57,151; 0.697 s |
| [HTTPX QuickStart documentation](https://www.python-httpx.org/quickstart/) | 200; 79,175; 0.758 s | 200; 79,175; 0.621 s |
| [RFC 9110 text PDF](https://www.rfc-editor.org/rfc/rfc9110.pdf) | 200; 2,858,365; 5.675 s | 200; 2,858,365; 4.900 s |
| [httpbin one redirect](https://httpbin.org/redirect/1) | 302 then 200 at `/get`; 308; 0.568 s | 302 then 200 at `/get`; 308; 0.521 s |

Eight successful retrieval operations, ten HTTP responses including redirects. For article/docs/PDF, both clients returned identical body hashes. Redirect JSON is a transport fixture, not an extracted research article. There were four HTML retrievals, eight HTML extractions, two retrievals of one PDF and four PDF extractions.

| Extractor / content | Output / local checks | Extraction duration (HTTPX body / Requests body) |
| --- | --- | --- |
| Trafilatura / article | 6,329 characters, 85 lines; title token and code function marker retained | 0.026 / 0.027 s |
| readability+lxml / article | 6,507 characters, 125 lines; same markers retained | 0.013 / 0.013 s |
| Trafilatura / docs | 13,689 characters, 317 lines; title token and HTTP call marker retained | 0.048 / 0.057 s |
| readability+lxml / docs | 13,787 characters, 439 lines; same markers retained | 0.021 / 0.021 s |
| pypdf / RFC 9110 | 194 physical pages; 461,677 characters; no empty pages; first-page title found | 4.194 / 4.169 s; CPU 4.172 / 4.125 s |
| PyMuPDF / RFC 9110 | 194 physical pages; 465,214 characters; no empty pages; first-page title found | 0.206 / 0.200 s; CPU 0.203 / 0.203 s |

Output length/markers prove nonempty extraction and limited content retention, not exact fidelity, semantic ordering or a quality winner. No complex-table/multicolumn corpus was assessed. The PDF speed difference applies to this one document/interpreter only. Peak RAM was not measured, no low-memory claim is supported, and actual process memory enforcement remains a design/handoff check.

Bounded-read probe: select lines 1–20 of normalized HTML, or first-page lines 1–20 for PDF; emit at most **2,048 UTF-8 bytes**, cutting at a valid character boundary. Article slices hit the cap and reported truncation; docs slices returned 905 bytes (Trafilatura) / 376 (readability); PDF slices returned 715 (pypdf) / 711 (PyMuPDF). All reported more content. These twelve slice observations used the saved extraction buffers, never refetched. They are research checks only: Storage authorization, immutable locator APIs and production resume-cursor semantics are not implemented.

Body integrity evidence:

| Content-decoded source | SHA-256 (both clients) |
| --- | --- |
| Article | `db48c39b89c71be90bb57fb3a0b3feaad45e5cc26aeabf36a0560b28716934b9` |
| Documentation | `3387d642a52ab4efb614bb79dd8b4f217dd30ebc6c3e37aede64ed60407f033d` |
| PDF | `60b30efa1048900833d1758440247fe8ac85a3134f2327388dcb24e07d814c89` |

### Explicitly untested

Sustained search availability/rate limits, paging stability, date/language/region correctness, backend fallback recovery under load, public-host privacy/maintenance guarantees, local SearXNG, ddgr, Playwright/JS pages, encrypted/scanned/malformed PDFs, OCR, arbitrary encodings, bot/login detection, error-status retrieval, adversarial compressed inputs, memory quotas, cancelled process trees and persistent Storage integration were not verified. There were no mock results, model calls or provider API tests; the undeployed local vLLM Qwen verification remains pending outside this assignment.

## Remaining decisions and acceptance gates

1. Define and pass representative research-task availability and URL-fidelity checks for the selected Google-then-DuckDuckGo profile before teammate handoff or experiments. Include niche/domain tasks and URLs with query parameters; criteria remain to be agreed. Existing trials do not satisfy the gate.
2. Reconcile explicit per-engine provenance, bounded fallback accounting and the supported filter subset. Reject unsupported filters; label post-discovery hostname filtering without claiming an upstream guarantee.
3. Reconcile byte/decompression bounds and safe metadata for PM's selected content-decoded original-body preservation; exact wire capture is not claimed.
4. Determine limits/process memory policy within the selected static-HTML and unencrypted-text-PDF scope; browsers/OCR remain excluded.
5. Reconcile scoped Storage access, complete snapshot-bundle finalization, immutable locators and lifecycle recording using the separate [CLI design](../teams/designs/cli-toolset-design.md). Search/fetch selection does not depend on choosing its transport now.
6. Audit the selected resolved dependency/wheel license closure before teammate distribution; PM owns dependency/lockfile changes after approval.

Project dependency integrity baseline, rechecked at delivery: `pyproject.toml` SHA-256 `054F4CE51130E1BBD8072FA3B3FFA40D2A3C77397016BFD45735CDD41234D7FD`; `uv.lock` SHA-256 `38CBB937D8DF92930FC872F65A57FB15FFD5E9F53CACFF7E7778C365B1FA7073`. The workspace did not resolve as a Git repository at trial startup. PM subsequently initialized the private repository during this assignment; read-only Git status now identifies the team's owned drafts. Hashes verify the dependency files remained intact. CONTRIBUTING.md was read; this team performs no Git/index/branch mutations.
