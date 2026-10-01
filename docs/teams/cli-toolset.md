# CLI Toolset team specification

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../team-start.md)
> and the [current usage guides](../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

Status: design and research phase. Shared contracts are **DRAFT**.
Design date: 2026-09-30.

## PM research decision, 2026-09-30

PM selected DDGS 9.16.0 for replaceable best-effort search, HTTPX 0.28.1
retrieval, Trafilatura 2.2.0 HTML extraction, and pypdf 6.19.0 text PDFs.
See [decisions.md](decisions.md) for evidence, named-engine policy, and the
research-task search availability/URL-fidelity gate. This does not authorize
implementation or project dependency changes. Reconcile schemas/transport next.

After the expanded report, PM selected explicit Yahoo primary, corrected Google
as a disabled-until-fidelity-passes fallback, and separate
`scholar.crossref.search` / `scholar.openalex.search` tools. The old Google/DDG
default failed all 18 EBD calls. This revised selection still needs real
availability/fidelity acceptance; anonymous metadata access is bounded, with
no paid escalation or requirement for new credentials. The complete owned
design defines exact schemas under `platform-contract-v1.md`.

## Start here

You are the leader of the **CLI Toolset team**. Read this specification,
[shared-platform.md](shared-platform.md), and [coordination.md](coordination.md)
before starting. The project manager (PM) coordinates the other teams and
resolves shared interface decisions. Follow the coordination document for
reporting, cross-chat communication authorization, and exact destination IDs;
do not infer or invent those IDs.

The project is designing a runnable platform that teammates can use to develop
research strategies. The environment uses **uv and Python 3.11+**, with Python
3.11 as the shared development version. Windows compatibility matters because
the current project workspace is on Windows. Internal modules communicate
through Python interfaces. Agent-facing external tools use a JSON CLI protocol;
this team is not building an MCP server.

The first assignment is **research and interface design**, not implementation.
Do not select the final backend, install project dependencies, change the
lockfile, or build the production toolset before the PM/user agrees to the
design and backend choice. A future teammate handoff must execute real tools;
mock replies do not satisfy that handoff.

## First assignment: free, open-source search and fetch research

Investigate free, open-source combinations that provide real web search,
webpage retrieval, content extraction, and text-based PDF extraction. Start
with DDGS as one candidate, verify its current package/repository identity, and
compare credible alternatives. Do not assume the old package name or an old
tutorial describes its current behavior.

Search and fetch are separate decisions. Evaluate complete combinations, not
just search packages. Candidate families to investigate include:

- Search libraries such as DDGS and self-hosted metasearch such as SearXNG.
- Ordinary HTTP retrieval plus an open-source main-content extractor, including
  candidates such as HTTPX/Requests and Trafilatura/readability-based extractors.
- PDF text extraction libraries, including candidates such as pypdf or
  PyMuPDF, with their exact licensing and extraction limitations verified.
- Browser-based retrieval, such as Playwright, only as a comparison outside
  the proposal's initial browser-automation scope. Document its setup burden
  and whether unsupported JavaScript pages matter; do not add it to the initial
  toolset without a scope decision from PM/user.

These names are a research starting list, not approved dependencies. Add or
remove candidates based on current primary evidence.

For each viable combination, establish:

| Dimension | Required evidence |
| --- | --- |
| Functionality | Real search results, redirects, HTML extraction, text PDF handling, and bounded document reading |
| Licensing | Exact licenses of the proposed package versions and relevant components; identify distribution or source-sharing implications for the project |
| Monetary requirements | Paid API requirement, free-tier limits, credentials, required subscriptions, and whether useful operation is possible without payment |
| Operating requirements | CPU/memory, network traffic, hosting, browser installation, external services, maintenance, and known backend rate limits |
| Environment | Python 3.11 support, uv compatibility, Windows support, exact dependency versions, native binaries, and transitive requirements that affect setup |
| Reliability | Documented failure modes, blocking/rate limiting, result instability, pagination, localization, and fallback behavior |
| Provenance | Search provider/query/rank, original and final URL, retrieval time, original response preservation, content hash, and extraction version |
| Content consistency | Whether original content and cleaned text can be obtained from the same HTTP response rather than fetching the source twice |
| PDFs | Page references, extraction quality, size limits, encrypted/scanned PDFs, OCR requirements, and explicitly unsupported cases |
| Team setup | Reproducible setup burden and whether each teammate can run the combination locally |

Distinguish **open-source software**, **no paid API requirement**, and **no
operational expense**. They are separate claims. A search client can be free
while its upstream sources impose limits; a self-hosted service requires
resources and maintenance.

Use official repositories, release metadata, license files, and project/vendor
documentation as primary sources. Record exact versions, relevant release or
publication dates when available, and the date each source was checked. Do not
present a secondary article or an assumed permissive license as verification.

### Live research trials

Where feasible, run small real trials using public queries and public sources.
Keep trial work isolated from production dependencies and do not change
`pyproject.toml` or `uv.lock`. Any trial setup must remain within the design and
research authorization described in the coordination document. If dependencies,
network access, or suitable runtime components are unavailable, report the
candidate as untested instead of substituting mock results.

Use the same trial cases across combinations where feasible: a general query,
a niche technical query, a domain-filtered query where supported, an ordinary
article, a documentation page, a text PDF, and a JavaScript page if rendering is
being evaluated. Confirm filter behavior rather than silently assuming it.

Record actual requests, timestamps, environment and versions, latency,
structured outcomes, and encountered failures. State the number of trials and
their limits; a handful of successful requests does not establish sustained
reliability. Separate observed behavior, documented behavior, and untested
claims in the report. Do not run model calls, consume model API keys, bypass
access restrictions, or upload project credentials as part of this research.

### Research deliverable

Save the research report to
[docs/research/free-search-fetch.md](../research/free-search-fetch.md). Include:

1. Candidate/version/source table and license findings.
2. Comparable feature, cost, environment, and reliability results.
3. Trial cases and results, clearly identifying anything untested.
4. At least one coherent search + HTTP/extraction + PDF combination, if the
   evidence supports one, and its remaining limitations.
5. A recommendation with reasons and alternatives **for PM selection**.
6. Open questions that affect interfaces or setup.

Do not turn the recommendation into a final backend choice. Save team status
to [reports/cli-toolset-status.md](reports/cli-toolset-status.md) and report to
the PM according to [coordination.md](coordination.md).

## Proposed agent-facing tools

The selected design has five registered tools. The complete owned design supplies
closed schemas under the common contract; the table summarizes their purposes.

| Tool | Purpose | Proposed input semantics | Proposed output semantics |
| --- | --- | --- | --- |
| `web.search` | General source discovery | Query and result limit; trusted named backend plan | Ranked discovery candidates with query/time/backend identity and bounded fallback observations |
| `scholar.crossref.search` | Bibliographic discovery | Query and result limit; fixed Crossref provider | Closed metadata candidates preserving DOI/publisher/landing identities; discovery only |
| `scholar.openalex.search` | Scholarly and OA-location discovery | Query and result limit; fixed OpenAlex provider | Closed work/DOI/location metadata with access observations; discovery only |
| `web.fetch` | Retrieve a source and create a document snapshot | URL and static mode; trusted bounds | READY snapshot reference, provenance, immutable counts and bounded preview |
| `document.read` | Read a bounded range from an existing snapshot | Snapshot reference, exact line/page range, UTF-8 byte budget and continuation | Authoritative DocumentSlice with stable locations and advancing continuation |

An optional `document.find` can locate literal or explicitly defined pattern
matches within an existing snapshot. It should return bounded locations and
snippets suitable for subsequent `document.read` calls. Decide whether it is
needed during contract review; it is not a reason to delay the three basic
tools.

Search output is discovery material. A search snippet is not a verified quote
from a fetched document. Preserve that distinction in names and schemas.
Tools do not write LLM answers, assess credibility, select research goals,
extract research claims, or decide how the strategy should proceed.

Fetch must identify inaccessible, blocked, timed-out, invalid, oversized, or
unsupported content explicitly. It must not return a login page, bot challenge,
or empty extraction as a successful research article. JavaScript rendering and
OCR are outside the initial requirement unless the scope is explicitly changed.

## CLI protocol and execution boundary

Use the envelope, error model, identifiers, and schema-version rules agreed in
[shared-platform.md](shared-platform.md). Do not introduce competing versions
inside this team spec. Propose concrete schemas as part of design review.

- Each registered command accepts one UTF-8 JSON request on stdin.
- It emits one JSON response on stdout. Progress and diagnostics go to stderr.
- Success uses exit code zero. Failure uses a nonzero exit code and a
  structured error when the process remains capable of producing one.
- Commands must not prompt interactively or mix human-formatted output with
  the JSON response.
- The caller executes registered argument vectors without a shell. Command
  names, paths, and accepted inputs are governed by the public tool definition.
- Every tool definition includes identity, description, input/output schemas,
  command invocation, supported capabilities, and limits.
- Unknown filters or retrieval modes must produce an explicit unsupported or
  validation error rather than silently changing the request.
- Bound result counts, response bytes, redirects, document processing, output
  size, and execution duration. Define how those bounds interact with the
  caller's deadline and cancellation in the shared contracts.
- Errors distinguish input errors, transport/provider failures, content
  limitations, timeout, and cancellation. Agree retry responsibility centrally;
  nested retries must not hide extra requests, cost, or elapsed time.

The proposed ownership is that this team supplies a generic **ToolExecutor**
alongside the commands/catalog. ToolExecutor launches registered argument
vectors without a shell, enforces deadlines and cancellation, cleans up
processes, and parses JSON results, exits, and errors. Connections binds that
executor to the Agent Container. The Container decides which tool to invoke,
checks permissions, and surrounds ToolExecutor with automatic lifecycle
recording. This assignment remains draft pending shared-contract review.

## Storage, provenance, and recording boundaries

**Storage owns durable snapshots and artifacts.** The Toolset uses the public
Storage interface and the connections assigned to it. Do not introduce a
separate durable document database or encode database-specific access in the
tool contract. Agree the fetch-to-storage handoff with the Storage and
Connections teams while the shared contracts are draft.

A CLI subprocess cannot automatically receive an in-process Python object.
Design how it obtains scoped Storage access with those teams: configuration
serialization, initialization/injection, or a suitable transport must be
explicit. Do not replace the agreed interface with raw filesystem writes or
direct database access because the process boundary is inconvenient.

Preserve the original response content and derive normalized text from the
same retrieval. Stable references belong to a particular immutable snapshot
and extraction version. A refreshed URL creates a distinguishable snapshot;
subsequent reads of an older snapshot must not silently refetch a changed page.
For PDFs, preserve page mapping when the selected extraction supports it.

**The Agent Container owns automatic tool lifecycle recording.** It records
dispatch/start, outcome, timeout, and cancellation around the CLI invocation.
The Toolset returns sufficient observation metadata for those events, including
provider request IDs where available, duration/usage details, cache origin, and
snapshot references. It must not persist a second copy of the same lifecycle
events. Storage owns recording its own artifact/state commits under the agreed
event contract.

Record actual usage units such as request counts, bytes, and rendering time
where available. Report monetary cost only when supported by billing evidence
or a clearly identified estimate. Do not invent a zero cost for an upstream
service simply because the client package is free.

## Design review and later runnable handoff

The research/design phase is ready for PM review when the report is saved,
unsupported claims are identified, proposed schemas and ownership questions
are documented, and the Container/Storage/Connections integration points are
clear. PM agreement on backend and contracts precedes implementation.

After implementation is authorized, the eventual handoff must demonstrate real
search, real HTML and text-PDF retrieval, reading a saved snapshot, structured
failures, bounded output, and automatic runtime records against real persistent
storage. Include uv-based setup and execution instructions. A mock server,
hardcoded result, or merely proposed command is not a runnable handoff.
