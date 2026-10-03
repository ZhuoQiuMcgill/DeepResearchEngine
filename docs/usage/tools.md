# Registered CLI tools

The Toolset runs real, one-shot Python workers behind the Engine's recorded
action boundary. The registry contains five tool names. `web.search` has
revisions 1 and 2; the other names remain at revision 1.
Use the public `deepresearch tool` command or `Engine.run_tool`; the private worker
protocol requires an owner-issued execution plan and recorded attempt.

| Tool | Closed arguments | Result |
| --- | --- | --- |
| `web.search@1` | `query`, optional `max_results` | Original Yahoo profile, retained for existing callers |
| `web.search@2` | `query`, optional `max_results` | Yahoo then DuckDuckGo fallback, original destination wrappers and HTTP/parser diagnostics |
| `scholar.crossref.search` | `query`, optional `max_results` | Crossref bibliographic metadata and DOI/member/publisher identities |
| `scholar.openalex.search` | `query`, optional `max_results` | OpenAlex work/source/open-access location metadata |
| `web.fetch` | `url`, optional `mode: "static"` | Committed snapshot reference, extraction counts, provenance and bounded preview |
| `document.read` | `snapshot_ref`, `range`, optional `max_text_bytes`, `continuation` | Saved immutable text with ranges, byte spans and continuation |

Queries remain literal, must be nonblank and fit 4,096 UTF-8 bytes.
`max_results` defaults to 5 and accepts integers from 1 through 10. The encoded
provider URL must also fit its own cap: 16,384 bytes for Crossref and 4,094 bytes
for OpenAlex. The registry publishes JSON schemas, and its pure semantic
validator checks byte limits and range relationships before intent recording.

## Run tools

Use uv and Python 3.11+ from the project directory. These PowerShell examples
send strict JSON on stdin, which also avoids shell quoting problems with JSON
passed as a native argument. `--arguments` is available for callers that pass
an already correctly quoted JSON string. Every command prints one public JSON
result. Success requires both `status: "succeeded"` and
`recording.status: "complete"`; the CLI otherwise exits with code 2.

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
uv run --locked deepresearch --store local/demo-store tools

'{"query":"environment based design Yong Zeng","max_results":3}' |
  uv run --locked deepresearch --store local/demo-store tool web.search --revision 2

'{"query":"\"Environment based design\" \"Yong Zeng\"","max_results":3}' |
  uv run --locked deepresearch --store local/demo-store tool scholar.crossref.search

'{"query":"\"environment-based design\"","max_results":3}' |
  uv run --locked deepresearch --store local/demo-store --admit-openalex tool scholar.openalex.search
```

OpenAlex starts closed until the host explicitly admits its initial anonymous
budget. `--admit-openalex` performs that initial admission; existing persisted
quota state is retained. Reopening the same store does not replenish the local
budget or clear a provider block. Free search backends can return empty results,
HTTP challenges or rate limits.
Strategies can select another registered discovery tool in a new recorded
action after an eligible source failure.

## Search revision 2

Select it with `Engine.run_tool(ToolRef("web.search", 2), arguments)` or CLI
`--revision 2`. The CLI and an unqualified ToolRef retain revision 1.
`baseline@3` and `baseline@4` explicitly pin revision 2 through their MethodDefinitions; methods
without a tool pin retain revision 1.

The fixed plan names Yahoo followed by DuckDuckGo, with at most one named
backend attempt each. Each backend has eight seconds inside the shared worker
deadline and up to two explicit HTTPS redirects, at most three HTTP requests.
Redirects must stay on that backend's search host and preserve the literal query.
Yahoo's `/_bv/v.gif` wrapper is allowed only when its single embedded `orig`
points back to that search host with the same query; cookies remain inside the
one worker attempt.
HTTP errors, challenges, empty parsing or rejected destinations permit the next
named backend. A successful result stops backend fallback; there is no merge or
worker replay. Google remains disabled. Anonymous HTML search requires no key.

Result rows add `raw_url` alongside the decoded `url`. Yahoo and DuckDuckGo
wrappers are decoded once; destination query strings, literal plus signs and
percent escapes are preserved. Advertising URLs are rejected after unwrapping.
All result rows remain discoveries, not fetched evidence.

Each backend observation records HTTP request/response counts, final status,
received body bytes/SHA-256, explicit redirects, extracted candidates, rejected
URLs, ads, retained results and a failure reason. Reasons distinguish HTTP
errors, challenges, rate limits, no-result markers, missing parser matches,
rejected candidates, backend deadlines, transport errors and parser errors. Body size is checked
before parsing at 1 MiB; the HTTP client receives the body first, so the existing
worker memory ceiling and deadline also bound that stage. Raw response bodies
are not included in the public result.

Run the search-only live check without model or fetch calls:

```shell
uv run --locked python examples/live_search_check.py
```

It uses real workers, SQLite and saved artifacts, covers EBD definition and
foundational-paper discovery, and verifies topic decisions. Both diagnostic
cases retain the exact experiment question `What is EBD (Environment Based Design)?`;
their tool queries are separate probe inputs.
Each execution uses fresh identities; it does not replay completed runs.

Fetch a source, then read the exact saved snapshot in an explicitly selected
source run. This example reads the first nine lines, using a one-based,
end-exclusive interval. Keep the same store between commands.

```powershell
$fetch = ('{"url":"https://www.rfc-editor.org/rfc/rfc9110.txt"}' |
  uv run --locked deepresearch --store local/demo-store tool web.fetch) | ConvertFrom-Json
if ($fetch.status -ne 'succeeded' -or $fetch.recording.status -ne 'complete') {
  throw 'Fetch did not produce an acknowledged snapshot'
}
$readArgs = @{
  snapshot_ref = $fetch.result.snapshot_ref
  range = @{ kind = 'lines'; start = 1; end_exclusive = 10 }
  max_text_bytes = 65536
} | ConvertTo-Json -Depth 10 -Compress
$readArgs | uv run --locked deepresearch --store local/demo-store tool document.read `
  --source-run $fetch.invocation.run_id
```

Read ranges accept at most 200 lines or 10 physical PDF pages per request;
`max_text_bytes` defaults to and cannot exceed 65,536. PDF pages preserve their
physical numbering, including empty pages. A truncated read can end inside a
line or page. Pass the returned opaque `continuation` unchanged with the same
snapshot reference and original requested range. `next_position` separately
describes the next unit and absolute UTF-8 byte offset; it is not the token to
send back. `has_more_in_requested_range` and `has_more_in_document` distinguish
the remaining requested material from material elsewhere in the document.
Reading a snapshot performs no network request or extraction.

## Module boundary

`ToolCatalog.resolve(name, revision=1)` returns a `Result[ToolDefinition]`.
`definitions` and `list()` return copies of the immutable registered
definitions. `validate_arguments(definition, arguments)` raises a safe
`EngineError` on invalid semantic input and performs no I/O.

`ToolExecutor.execute(definition, arguments, context, plan)` is async and
returns the internal `ToolExecutionResult`. `plan` is the shared
`ToolStoragePlan`, bound to the live context, registered tool and single
`AttemptLease`. It must carry the Container's verified `tool.intent` receipt
before the executor admits network activity, a Storage read or a worker.
The executor checks the recorded lease and capabilities, consumes the attempt
once, and rejects reuse. The Container records the matching outcome and
constructs the public `ToolResult`; Toolset does not run a second event logger.
Both agent and standalone tool calls use this path.

Search plans have no snapshot clients or publication rights. Fetch workers
return a prepared proposal containing original/text/index bytes and bounded
provenance; the parent validates the proposal and commits through scoped
Storage. Only a matching READY receipt becomes public success. A lost commit
acknowledgment triggers a same-operation status lookup, never another fetch or
commit. An unresolved Storage outcome remains unknown. Read workers receive
only the already-authorized immutable `DocumentSlice` and must echo that
slice exactly. Workers receive no Storage roots, grants, live clients, model
API keys or authority to manufacture references.

Constructors accept these host controls:

```python
ToolCatalog()
ToolExecutor(catalog=None, *, openalex_admission=False, fetch_concurrency=1,
             memory_bytes=512 << 20, quota_checkpoint=None,
             quota_checkpoint_sink=None)
```

`export_quota_checkpoint()` returns trusted owner state. The optional sync or
async sink persists each scholarly reservation before dispatch and its
settlement afterward. Engine composition stores this state in real Storage
and restores it on open. Restored in-flight reservations stay blocked;
unconfirmed dispatch never earns a fabricated refund. `close(deadline=None)`
drains owned work and returns a `CleanupReport`.

## Discovery and retrieval policy

Revision 1 uses the pinned DDGS Yahoo engine directly for one first-page
search. Revision 2 uses the explicit Yahoo/DuckDuckGo plan described above.
Neither profile uses the DDGS aggregator or merges its engines. Both installed
engines declare Bing as their underlying provider. The corrected Google parser
passes controlled raw-HTML wrapper tests for escapes, literal plus and
query-bearing URLs, but Google remains disabled because its live fidelity gate
is pending. Results report active/disabled backends and actual attempts.
The tool does not rewrite queries, paginate or replay workers; Workflow query
preparation happens before the recorded tool call.

Scholarly workers each make one bounded anonymous request to the fixed provider
endpoint. Results are closed metadata projections, with no abstract or paper
full text. Crossref pacing starts at no more than one request per second per
owned executor and can narrow using response headers. OpenAlex reserves
1,000 micro-USD per keyword request within a local ceiling of 100,000 micro-USD
per UTC day; recognized cost/remaining/reset headers can only narrow admission.
A 429 latches a block. Missing and malformed observations stay distinct,
known zero stays zero, and unknown reset time cannot permit automatic replay.
Credits and USD remain separate units. Local accounting does not control other
hosts' traffic or assert the provider's complete remaining allowance.

`web.fetch` uses HTTPX with TLS verification, no environment proxy and no
automatic retry. It admits public HTTP(S) destinations, rejects credential
URLs and non-global resolved addresses, connects to a validated pinned address
with the original Host/SNI, and revalidates each of at most five redirects.
The retained original is the content-decoded response body. Original, derived
UTF-8 text and index come from that single body; component hashes use
`sha256:<64 lowercase hex digits>`. Provenance includes requested/final URLs,
redirects, HTTP counts/status, transfer/decoded sizes, charset policy, parser
version and extraction warnings. URL normalization is observable; fragments
are excluded from the HTTP request.

HTML uses Trafilatura article extraction and strict bounded charset selection.
Plain text uses explicit BOM/header/default encoding rules and normalizes
line endings while preserving tabs and form feeds. PDFs use pypdf with the
physical page index retained. Encrypted PDFs, images requiring OCR, blank
extractions, challenges, inaccessible pages and unsupported representations
fail explicitly. There is no browser, login, OCR or challenge bypass. PDF
warnings are counted in bounded provenance rather than flooding stderr.
Article extraction and PDF reading order are heuristic: saved text is
reproducible evidence of the chosen extraction, not a guarantee of complete
page content, layout, mathematical notation or font fidelity.

## Limits and process ownership

| Boundary | Cap |
| --- | --- |
| Strict UTF-8 JSON stdin | 1 MiB, depth 32, no duplicate keys/BOM/nonfinite numbers |
| Encoded fetch-worker stdout | 20 MiB |
| Encoded other-worker stdout / internal public payload | 512 KiB |
| Drained stderr | 64 KiB total |
| Retained original / derived text / index | 8 MiB / 4 MiB / 1 MiB |
| Provenance / preview | 64 KiB / 64 KiB |
| Scholarly response | 1 MiB raw and decoded |
| PDF physical pages | 500 |
| Worker work budget | 60 seconds, shortened by the inherited deadline; metadata at most 30 seconds |
| Windows worker Job committed memory | 512 MiB by default |

Actual encoded byte size is checked after JSON/base64 escaping, including the
combined proposal, rather than inferred from individual component sizes.
The maximum 8/4/1 MiB component vector fits the fetch transport at 18,186,735
bytes; excess aggregate/escaped responses fail before prepared success.

On Windows, workers are created suspended, assigned to a kill-on-close Job
Object with the configured committed-memory ceiling, then resumed. Assignment
failure kills and reaps the suspended process. Only designated pipe handles
are inherited. Timeout, cancellation, stdout/stderr overflow and Job memory
limits terminate the entire Job, reap the root, confirm no active descendants
and drain/close owned streams. Actual sleeping-child and memory-limit tests
verify this behavior. Unconfirmed cleanup is reported, never silently marked
complete. POSIX uses a process-group cleanup path; that path is implemented
but has not had live platform acceptance on this Windows machine.

Byte limits do not establish RAM limits. Worker Job peak committed memory and
parent memory have separate scopes; parsers may allocate much more memory than
the retained text. Host fetch concurrency defaults to one. The explicit
concurrency-two acceptance below followed successful single-fetch measurement.

## Verification evidence

Owned deterministic checks completed on 2026-10-01: **47 passed in 3.57s**.
They include real child-process ownership, Unicode continuations through real
Storage and recorded read workers, closed protocols, exact encoded caps,
physical empty PDF pages, compressed/encrypted/blank PDF cases, quota state,
and controlled lost-ack recovery without replay. Controlled provider or
Storage faults are test vectors, separate from live acceptance.

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.uv-python'
uv --cache-dir .uv-cache run --locked --offline pytest -q tests/toolset
```

`tests/toolset/live_acceptance.py` is an opt-in real Engine/worker/Storage
exercise. It admits a new bounded anonymous OpenAlex budget, performs public
search and metadata calls, follows a real OpenAlex paper location, saves
HTML/plain/PDF sources and reads the saved documents. It writes ignored local
evidence, not fixture replies. These completed runs are retained here:

- All five registered tools succeeded with complete recording and cleanup:
  `local/toolset-acceptance/acceptance_86f4785276d7486697d423a73f69f994/evidence.json`.
- Single-fetch measurements followed by two simultaneous successful HTML/PDF
  fetches: `local/toolset-acceptance/acceptance_38869d620939485183f7d74a26b81aeb/evidence.json`.
  Yahoo was unavailable in this later run; the recorded failure is retained.

Both directories retain their real Storage databases and snapshot components.
The first run's source inventory is:

| Requested source | Retained body bytes | Text bytes | Physical pages | Peak Job committed bytes |
| --- | ---: | ---: | ---: | ---: |
| `https://www.rfc-editor.org/rfc/rfc9110.txt` | 502,941 | 502,938 | n/a | 45,105,152 |
| `https://www.rfc-editor.org/rfc/rfc9110.html` | 1,187,554 | 5,243 | n/a | 120,262,656 |
| `https://www.rfc-editor.org/rfc/rfc9110.pdf` | 2,858,365 | 467,051 | 194 | 75,960,320 |
| Cambridge paper DOI `10.1017/S0890060425000083`, OpenAlex-discovered PDF | 1,437,542 | 97,429 | 18 | 55,455,744 |

The Cambridge requested URL, all four component hashes, extraction identities,
receipts and snapshot references are recorded in that evidence. Its PDF had
108 counted parser warnings. Trafilatura retained only its selected article
text from the RFC HTML; HTML acceptance therefore establishes retrieval and
saved extraction, not whole-document content coverage. Source bodies can
change between requests, so use each run's actual hashes.

For concurrency two, the parent private-byte baseline was 41,316,352, the
sampled peak was 59,064,320 across 379 samples, and the final observation was
43,036,672. The two worker Job peaks were 119,668,736 and 74,952,704 bytes.
These observations cover these particular sources and sampling intervals;
they establish neither a general parent RAM bound nor an extraction-fidelity
corpus. The actual Windows memory-denial test verifies typed failure and
descendant cleanup, not an exact maximum reported peak under Windows accounting.

## Installed license inventory and source boundaries

The inventory below was read from the installed wheel metadata on 2026-10-01
for the non-extra dependency closure of DDGS, HTTPX, Trafilatura, pypdf and
jsonschema. It is reproducible environment evidence rather than a complete
distribution audit. Root owns `uv.lock` and dependency changes. Exact metadata
and license files remain under `.venv/Lib/site-packages/*dist-info/`.

| Direct package | Installed version | Declared license |
| --- | --- | --- |
| ddgs | 9.16.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| trafilatura | 2.2.0 | Apache-2.0 |
| pypdf | 6.19.0 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |

| Transitive packages and installed versions | Declared license |
| --- | --- |
| anyio 4.15.1; attrs 26.1.0; charset-normalizer 3.5.2; h11 0.16.0 | MIT |
| jsonschema-specifications 2025.9.1; referencing 0.37.0; rpds-py 2026.6.3 | MIT |
| primp 2.0.1; pytz 2026.4; six 1.17.0; tzlocal 5.4.4; urllib3 2.8.0 | MIT |
| babel 2.18.0; click 8.5.0; dateparser 1.4.3; httpcore 1.0.9; idna 3.20 | BSD-3-Clause |
| jusText 3.0.2 | BSD-2-Clause |
| courlan 1.4.0; htmldate 1.10.0; tzdata 2026.4 | Apache-2.0 |
| python-dateutil 2.9.0.post0 | BSD / Apache dual license; inspect its LICENSE |
| typing_extensions 4.16.0 | PSF-2.0 |
| regex 2026.9.29 | Apache-2.0 AND CNRI-Python |
| certifi 2026.7.22 | MPL-2.0 |
| tld 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later |
| lxml 6.1.3 | BSD-3-Clause plus component and bundled binary notices |

All listed distributions except the installed primp wheel exposed a
dist-info license/notice file; primp declared MIT in metadata but no matching
license file was found there. lxml's installed `LICENSES.txt` identifies
bundled zlib, iconv under LGPL-2.1, libxml2/libxslt/libexslt under MIT, and
additional component notices. Thus the closure cannot be described as entirely
permissive. Before distributing wheels or an executable bundle, preserve and
review the exact applicable license, copyright, NOTICE and source provisions,
including native/data components and the primp notice gap. The full eventual
distribution has not been audited. The existing
[research inventory](../research/free-search-fetch.md#version-source-and-license-evidence)
links the reviewed primary package/license sources.

Package licensing does not establish permission to redistribute provider
responses or fetched papers. Search results are discoveries. Crossref and
OpenAlex responses are metadata; the reviewed OpenAlex CC0 metadata statement
does not relicense linked papers. The tools retain actual requested/final source
URLs and provenance, fetch publicly accessible bodies without authentication
or restriction bypass, and leave source reuse rights attached to each source.
No claim of unrestricted paper redistribution, stable anonymous service
availability or complete legal clearance follows from a successful HTTP 200.
