# CLI Toolset design proposal

CLI Toolset team, 2026-09-30 (America/Toronto). **DRAFT for PM reconciliation. PM selected the initial backend stack; production implementation/dependency changes remain unauthorized.** Read with the [research report](../../research/free-search-fetch.md), [PM decision](../decisions.md), shared brief and the Storage/Connections proposals. Proposed shared schemas, transport and limits below remain drafts and must become one common contract.

Initial design stack: DDGS 9.16.0, HTTPX 0.28.1, Trafilatura 2.2.0 and pypdf 6.19.0. DDGS is replaceable/best-effort, configured explicitly Google then DuckDuckGo with named outcomes, bounded fallback, unsupported-filter rejection and visible outages. Five successful attempts across three queries/four modes do not validate research coverage. Representative-task availability and URL-fidelity checks are required before teammate acceptance/experiments and remain pending. Source scope is static HTML and unencrypted text PDFs, with same-response extraction from retained content-decoded bytes and explicit representation/encoding/hashes.

## 1. Scope and ownership

Provide three deterministic source tools, a registered catalog and a generic asynchronous ToolExecutor. External search/retrieval results can change; deterministic means bounded source operations without strategy or model interpretation, and repeatable reads of an immutable saved extraction. Search discovers; fetch retrieves/extracts and proposes a snapshot; read reads saved content. No claim evaluation, answers, goal ranking, scheduler, MCP server, browser or OCR in the initial scope.

| Owner | Responsibility |
| --- | --- |
| Container | Tool permission/admission, model call ID correlation, durable tool intent before work, terminal lifecycle event and recording failures; central retry decision |
| Toolset | Catalog/schemas, argv-only worker launch, deadlines/cancellation/cleanup, JSON and exit validation, retrieval/extraction/provenance, process-boundary Storage adapter |
| Connections | Trusted effective context, storage plan/grants, dependency/configuration binding, attenuation and resource leases; no process launching |
| Storage | Scoped snapshot commit/read, complete artifact bundle finalization/recovery, authoritative immutable refs/receipts, commit events and durable activity append |

Toolset consumes public Storage methods. It does not open SQLite, write engine artifact files, load `local/.env`, or emit duplicate tool lifecycle records. Local research scratch captures are outside the proposed production module.

## 2. Catalog and Python execution API

Proposed shared `ToolDefinition` fields:

| Field | Meaning |
| --- | --- |
| `name`, `revision`, `description` | Stable registered identity; revision identifies schemas, backend adapter/configuration and normalization policy |
| `schema_version` | Shared protocol compatibility version; major mismatch rejected before launch; initially propose integer `1` pending PM agreement |
| `input_schema`, `output_schema` | Closed JSON schemas with finite numbers, bounds, tagged unions and unknown-field rejection |
| `argv` | Trusted absolute interpreter/entry point plus fixed arguments, supplied by registration; no executable/command/shell fragments in agent arguments |
| `capabilities` | Backend-specific supported filters, source modes, media, physical PDF page mapping; does not claim filter correctness beyond evidence |
| `limits` | Input/output/diagnostic bytes, duration, redirects, document bytes/pages/text, concurrency and request budgets |
| `storage_requirements` | None for search; one approved snapshot commit for fetch; exact authorized snapshot read for read |
| `network_policy_ref`, `config_ref` | Reviewed non-secret policy/configuration identities; no embedded credentials or developer paths |

Catalog resolution returns immutable definitions. Duplicate conflicting revisions, unsupported protocol/schema or unconfigured dependencies fail at binding. The model sees schemas/descriptions/capabilities, not argv, Storage control fields, secrets or host paths. Toolset validates input again at execution even after Container admission.

Draft Python signatures (documentation only):

```text
ToolCatalog.resolve(name, revision) -> ToolDefinition | CatalogError
async ToolExecutor.execute(definition, arguments, context,
                           storage_plan=None) -> ToolExecutionResult
async ToolExecutor.close(deadline) -> CleanupReport
```

`context` combines agreed serializable identity/deadline metadata with trusted live cancellation/authority handles. The executor borrows bound Storage through `storage_plan`; it does not close a shared store. Executor results contain finalized tool response, process facts, usage observations, causal IDs and any cleanup/commit uncertainty. Expected errors are typed. Caller-task cancellation must terminate/reap the worker, attempt bounded cleanup and surface details to the Container's terminal-recording path.

## 3. One-request, one-response CLI protocol

Use the single PM-approved common version/envelope. Proposed wire profile: stdin is one strict UTF-8 JSON object terminated by EOF; stdout is one strict UTF-8 JSON object plus optional trailing whitespace before process exit. No JSONL progress stream or extra Storage messages. stderr is bounded sanitized diagnostics. Reject duplicate keys, NaN/Infinity, invalid UTF-8, unknown fields, incompatible version and multiple objects. Commands never prompt.

Draft request example:

```json
{
  "schema_version": 1,
  "call_id": "opaque-model-call-id",
  "tool": {"name": "document.read", "revision": "draft-1"},
  "arguments": {
    "snapshot_ref": "opaque-store-qualified-snapshot-ref",
    "range": {"kind": "lines", "start": 1, "end_exclusive": 21},
    "max_text_bytes": 2048
  },
  "execution": {
    "run_id": "run-id",
    "agent_id": "agent-id",
    "action_id": "action-id",
    "attempt_id": "attempt-id",
    "parent_action_id": "parent-action-id",
    "correlation_id": "correlation-id",
    "deadline_at_utc": "2026-10-01T03:00:00Z",
    "storage_input": {"kind": "document_slice", "slice": "<trusted structured DocumentSlice>"}
  }
}
```

`execution` is a reserved launcher-injected field absent from agent input schemas. JSON IDs do not grant permissions. The illustrative string placeholder for `slice` is a structured object in an actual request. `call_id` links a provider conversation, while `action_id` and `attempt_id` identify execution; they must not be conflated. Optionality/allocation and any additional shared context fields follow PM's reconciled context, not a second Toolset definition.

Response shape proposed for the shared contract:

```text
{
  schema_version, call_id, ok,
  result?: <tool-specific typed result>,
  error?: {code, category, safe_message, retry_hint, details},
  observations: <bounded non-secret metadata>,
  storage_proposal?: <reserved fetch-only complete SnapshotProposal>
}
```

Exactly one of result/error is present. `ok=true` requires exit 0; `ok=false` requires nonzero exit. Protocol/schema/exit contradictions are executor `PROTOCOL_ERROR`, rather than trusting whichever channel appears successful. Launch/crash/kill can produce no JSON; the executor synthesizes a typed failure with process evidence. Proposed worker exit classes: 2 validation/unsupported, 3 transport/provider, 4 content limitation, 5 Storage/injected-binding problem, 6 deadline, 7 cancellation, 1 unexpected failure. Code/category remains authoritative; values require PM agreement. Unknown nonzero exits are process failures.

`storage_proposal` is internal transport data and never an agent-visible result. For fetch, worker exit 0 means retrieval/extraction completed and a valid complete proposal was emitted. **Outer web.fetch succeeds only after Storage returns a committed snapshot receipt.** The executor inserts Storage's reference into the final tool result, removes the private bundle and records process exit separately. A Storage error after worker success remains a failed outer tool with explicit process success and commit state.

## 4. Three tool schemas

All schemas reject arbitrary caller limit increases; effective limits are the intersection of registered, run, grant and remaining-deadline bounds. Agent input contains semantic arguments, not argv/provider secrets/scope grants. JSON Schema may use `$defs` for shared refs/ranges/errors; PM owns the canonical schema package.

### web.search

| Input | Exact proposed semantics |
| --- | --- |
| `query` required | Nonempty UTF-8 string, <=2,048 bytes; preserved verbatim in provenance |
| `limit` optional | Integer 1–10; default 5; cap result list after provider response |
| `page` optional | Integer 1–5; default 1; accepted only for backend with supported paging; not an immutable continuation cursor |
| `filters` optional | Closed object; supported subset of `domains`, `time_range`, `language`, `region`, `safesearch`; unknown/unsupported values fail explicitly |

The selected initial backend order is configurable explicit Google then DuckDuckGo, governed by binding policy rather than arbitrary agent argv. Use named outcomes; avoid DDGS automatic merging and the zero-success Brave profile. A request with filters runs only on backends supporting them; unsupported filters are rejected and fallback never silently relaxes them. Initial supported domain request can be a strict **post-discovery hostname constraint** with optional `site:` query augmentation: label `application=postfilter`, retain original provider query and validate every returned host. Specify whether subdomains are permitted. Filtering can return fewer results/partial status; it cannot guarantee the search provider exhaustively found that domain's content. The live trial verified query syntax only for two successful calls. Precise date or language filtering remains unverified and should stay disabled until reviewed/validated. A relative engine time filter is not a verified publication-date range.

Container governs the bounded Google-to-DuckDuckGo fallback and conveys each authorized named attempt in a trusted `execution.search_plan` drawn from the bound allowlist/configuration, with shared inherited request/deadline budgets and recorded outcomes. Agent arguments cannot supply that field or arbitrary engine/configuration names. No hidden DDGS/executor/Connections fallback or retry is permitted. Exact request/attempt limits remain draft; exhaustion or all-provider failure is an explicit outage.

Output `SearchResults`:

```text
{kind:"search_results", query, executed_queries, searched_at_utc,
 results:[{rank, title, url, search_snippet, source_date?,
           source_date_basis?, provider, backend, backend_rank?}],
 backend_outcomes:[{backend, status, elapsed_ms, request_count?, error?}],
 filters_applied:[{name, value, application, support_basis}],
 partial, truncated, next_page_possible, warnings}
```

Unknown dates/request counts are null/absent with explicit unknown semantics. DDGS automatic results do not expose reliable per-result engine identity: do not invent it. Prefer individually selected active backends, recording the package version and aggregate rank separately from backend rank. SearXNG engine positions/contributors can map to additional provider observations. Stock DDGS CLI output does not satisfy this protocol; a future registered wrapper would use its Python API.

No-result success is allowed only when the backend can establish a genuine empty result; DDGS `No results found` is an ambiguous provider failure under observed behavior. Distinguish partial backend successes from all-provider failure. Bound provider requests; no hidden executor/Connections retries. Container owns a new attempt/fallback decision and records it. Searching again does not reproduce a frozen rank list.

### web.fetch

| Input | Exact proposed semantics |
| --- | --- |
| `url` required | Absolute public `http`/`https` URL <=8 KiB, no userinfo or credential-bearing URL parameters; preserve useful query strings |
| `mode` optional | Literal `http`, default; unknown/browser mode rejected as unsupported |
| `preview_bytes` optional | 0–4,096 UTF-8 bytes, default 2,048 |
| `search_provenance_ref` optional | Permitted discovery reference; advisory linkage, not verified content or authority |

Connections supplies network policy. Validate original target, resolved destination and every redirect. Initial public-web policy rejects local/file/other schemes, loopback/private/link-local targets and DNS/redirect changes into prohibited ranges; apply deployment rules to avoid internal-network fetches. These checks do not claim an OS network sandbox or immunity to DNS rebinding. The Storage control channel, if later chosen, is distinct and cannot be selected as a web target. Keep TLS verification; no challenge/login bypass.

Fetch once using a streaming client; enforce Content-Length where available and actual encoded/decoded/elapsed budgets. Preserve the content-decoded source-body representation and available encoding headers. Extraction runs on that retained body. Dispatch media after status and type/signature checks: static HTML and unencrypted text PDF initially; explicit unsupported status for other media, including plain-text retrieval until separately authorized. Reject clear login/bot challenges, empty/no-usable-text output and unsupported content rather than calling them successful articles. Detection is heuristic and cannot guarantee recognizing every challenge; emit confidence/reason/limitations and retain that risk.

Output `FetchedSnapshot` after Storage finalization:

```text
{kind:"document_snapshot", snapshot_ref, snapshot_format,
 requested_url, final_url, redirects, retrieved_at_utc,
 response:{status, media_type, source_encoding, content_encoding,
           representation, safe_headers},
 original:{artifact_ref, sha256, bytes},
 extraction:{name, version, options_ref, normalization_version,
             text_artifact_ref, sha256, bytes, line_count,
             physical_page_count?, page_map_available, limitations},
 preview:{text, returned_spans, truncated}, publication_receipt}
```

Receipt/reference fields originate from Storage. A URL refresh creates a distinct immutable snapshot even for equal body hashes; an older reference never silently refetches. Metadata captures unknown encoding/usage as unknown. Reject oversized documents instead of truncating an original and labeling the snapshot complete. A scanned PDF with no usable text is a content limitation, and pages with no text remain represented in an otherwise supported PDF map. Reject encryption initially; adding passwords/crypto or OCR is a scope change.

### document.read

| Input | Exact proposed semantics |
| --- | --- |
| `snapshot_ref` required | Opaque store-qualified typed reference, no filesystem path/URL; possession does not grant access |
| `range` required | Exactly `lines{start,end_exclusive}` or `pages{start,end_exclusive}`; one-based start, end-exclusive |
| `max_text_bytes` optional | 1–65,536 bytes, default 8,192; text-only budget separate from response-envelope cap |
| `continuation` optional | Snapshot/range/version-bound position for continuing a partial long line/page; never a grant |

Align with Storage's `DocumentRange`/`DocumentSlice`: no more than 200 lines or 10 pages per call. Validate against the selected unit's available count; zero logical lines permit only the empty line range `[1,1)`. An empty physical PDF page remains a valid page when its stored physical page count includes it. No clamping invalid ranges or inventing page mapping. PDF pages are physical one-based pages; printed page labels are additional metadata. Initial chunk ranges and `document.find` are deferred, avoiding incompatible locator systems.

Output is the authoritative bounded `DocumentSlice`: snapshot/extraction versions, requested/returned range, ordered text spans with line/page and absolute zero-based UTF-8 byte offsets, `has_more_in_requested_range`, `has_more_in_document`, `truncated`, and `next_position`. Favor complete lines; if a single line/page exceeds the budget, return a valid UTF-8 partial span with a continuation that makes progress. Reads require no network and never re-extract with a changed library.

Canonical text: UTF-8 without BOM, LF line endings, no implicit Unicode normalization; final LF creates no phantom last line, empty text has zero lines. Toolset freezes normalized text and index; Storage verifies offsets/counts/coverage. Page map preserves empty pages and labels. Locators include immutable snapshot identity and extraction/normalization revision; changing extraction creates a new revision/reference.

## 5. Snapshot access across the process boundary

Storage/Connections proposals were reviewed while drafting this section. The preferred initial candidate is now **launcher-mediated bounded injection**, rather than the initial private-pipe question. This agrees with their current initial-tool recommendation, conditional on joint caps and PM selection. The worker's Storage authority is a trusted parent-held scoped interface and a one-attempt operation plan; no self-authorizing serialized grant is accepted.

| Option | Windows/standalone and framing | Transfer, failures and tradeoff |
| --- | --- | --- |
| Bounded launcher mediation: preferred initial candidate | One JSON stdin/stdout; no added socket/token/channel. Same approved runner inside/outside a model loop | Known read is injected; fetch returns one bounded proposal. More JSON/base64 memory copies and smaller maximum documents; no dynamic worker Storage operations |
| Ephemeral loopback broker | Ordinary Windows/Unix sockets; trusted runner creates a per-action capability; one tool stdin/stdout plus separate bounded HTTP RPC | Streaming chunks reduce whole-bundle buffering; requires listener/auth/parser/client, revocation and request accounting. Suitable if larger/dynamic operations become required |
| Private inherited/named pipe proxy | Needs separate Windows handle/ACL/inheritance and POSIX adapters plus standalone launcher; cannot multiplex Storage messages on tool stdout | Private channel and streaming; extra framing/lifecycle complexity. Raw bytes plus strict JSON required; avoid pickle object receive |

Raw database/artifact-root paths and a second durable snapshot database are rejected. The comparison is design reasoning, not a verified transport implementation. [Python subprocess/Windows handles](https://docs.python.org/3.11/library/subprocess.html#popen-constructor), [Windows asyncio](https://docs.python.org/3.11/library/asyncio-platforms.html#windows), [connection serialization](https://docs.python.org/3.11/library/multiprocessing.html#listeners-and-clients).

### Preferred flow using existing Storage methods

1. Container checks permission and durably records tool intent. Connections supplies an immutable `ToolStoragePlan` bound to tool revision, run/action/attempt, exact scope/object/range, operation, limits and deadline. ToolExecutor cannot expand it.
2. Search requires no worker Storage access. Its bounded result can be recorded by Container through its existing recorder/artifact path.
3. For read, Toolset's parent adapter calls `SnapshotStore.read(context, snapshot_ref, range, max_text_bytes, continuation=None)` under the plan, forwarding a supplied continuation unchanged, aligned with Storage's current proposed signature. Storage validates its snapshot/range/extraction-version/position binding rather than granting access through the cursor. The parent then injects only that authoritative `DocumentSlice` in `execution.storage_input`. The worker verifies matching arguments/plan/slice/continuation and serializes the bounded result; a differing reference/range/returned payload is a protocol failure. Omitting a supplied position must not repeat a long line/page's first fragment. The private input is not captured as an unrestricted model argument.
4. For fetch, the parent allocates a stable Storage `operation_id` and injects the matching plan identity. The registered worker fetches once, derives text/index/provenance and returns a complete `storage_proposal`: original bytes base64, canonical text, index/page map, sanitized metadata, digest/length seals and assigned operation correlation. No store path, scope choice or fake receipt comes from the worker.
5. The parent validates envelope/bounds/identity/content seals/UTF-8/index coverage and content-result classification, then passes the proposal through `SnapshotStore.commit(context, operation_id, bound_scope, proposal)`. **Storage stages/seals all original/text/index/manifest objects, then publishes ready metadata and its snapshot commit event in a SQLite transaction.** Ordinary filesystem writes plus SQLite are not jointly atomic; Storage's recovery handles orphaned/incomplete files. No snapshot is visible until the complete bundle is finalized.
6. Only a committed Storage receipt makes the outer tool successful. Container records one terminal result with finalized refs, bounded preview, usage/process metadata, and persistence status. Toolset does not duplicate either lifecycle or Storage commit events.

The tool action spans parent reads/commit and the subprocess, rather than terminating at worker exit. If intent persistence fails, no read/fetch/launch occurs. A structured outcome-persistence failure after work must reach the Container; successful snapshot publication does not imply its tool outcome was durably recorded.

Worker death/nonzero exit/incomplete/invalid/oversized output causes failure with no new snapshot. Cancellation/deadline before commit admission prevents new publication even when bytes are complete. Once commit is admitted, Storage determines committed/not-committed/unknown; cancellation cannot undo a durable commit. Lost finalization replies use Storage's same `operation_id`/status or idempotent same-proposal delivery to reconcile, never blindly refetch the URL. Parent death before commit can lose an unpersisted proposal; parent death during staging uses Storage recovery. Interrupted tool intent remains incomplete. `commit_state` and receipt are kept in the outcome when known.

Proposed mediation bounds aligned with Connections:

| Bound | Initial review value |
| --- | --- |
| Original decoded content | 8 MiB |
| Normalized text / index / provenance | 4 MiB / 1 MiB / 64 KiB |
| Worker stdin / fetch stdout | 1 MiB / 20 MiB actual encoded JSON bytes |
| Ordinary worker/final tool response | 512 KiB wire JSON; read text <=64 KiB; fetch preview <=4 KiB |
| stderr | 64 KiB, sanitized and with explicit truncation marker |
| JSON depth | 32 |
| Active fetches | At most 2 per executor and lower inherited budget |

Use direct UTF-8 Unicode output/minimal necessary escaping. Binary base64 expansion, JSON escaping, metadata and envelope overhead count toward the actual wire cap. Component maxima do not guarantee fit; emit explicit `BUNDLE_LIMIT` if the complete JSON exceeds 20 MiB. Do not truncate the bundle. The 2.86 MB / 0.46 MB text / 194-page trial PDF fits; this is useful initial coverage, not support for arbitrary research PDFs. Memory copies/peak RAM remain unmeasured and must be validated before accepting caps. A later larger-document requirement can favor a broker or separate pipe without changing agent tool contracts.

### Alternative streaming proxy profile

If selected instead, Storage issues/maintains and validates an expiring per-action capability token/session; Connections requests the narrowed authority and owns its binding/lease, while ToolExecutor delivers it with the same plan. Inject only endpoint/channel descriptor and capability in reserved stdin. Never place it in argv, URLs, logs, model fields or activity. A loopback broker binds only `127.0.0.1` on an ephemeral port, fixed routes, no redirects/environment proxies and strict byte/frame limits; it forwards only to canonical scoped Storage. A private pipe uses separate length-prefixed JSON/bytes with bounded reads, platform-specific launch/ACL handling and explicit EOF/lifecycle. Neither exposes arbitrary SQL, state, artifact enumeration or event append.

Logical streaming operations map to Storage: begin staging; append a component chunk with exact offset/hash; finalize complete original/text/index/provenance seals; abort; status by stable operation ID; bounded snapshot read. Exact duplicate delivery is idempotent; overlaps/gaps/changed content conflict. Frame/chunk/total/request-count quotas are enforced server-side per plan. The teams' alternative chunk/total defaults differ and require PM reconciliation; do not introduce a second frozen profile here.

On process death, cancellation, deadline, session close or revocation, deny new requests, close the channel and abort unfinished staging through Storage, preserving commits already completed/admitted. Ambiguous commit replies are resolved through stable operation IDs. No transport-retry policy may replay an external web request. This is scoped API enforcement for trusted registered local workers, not a hostile-process OS sandbox.

### Standalone CLI

An approved trusted **tool runner** is the public standalone entry point: load centrally bound non-secret policy, establish a real run/action/context and fresh run-scope Storage access, record intent using Container's common tool-action helper, invoke ToolExecutor, record outcome, close only owned resources, emit one final JSON. No model loop is needed. Reading an earlier snapshot requires an explicitly configured permitted shared/run scope; the reference itself grants nothing. If another owner holds the configured store, surface `STORAGE_BUSY`, never create a hidden alternative store.

Direct internal fetch/read worker launch without the matching injected plan/slice fails explicitly before network work. The worker does not discover credentials/store roots or fall back to direct files. Proposed future invocation is `uv run --locked <approved-tool-runner> ...`; **this command is not implemented**. PM selects names/package ownership after approval.

## 6. Execution, limits, errors and observability

ToolExecutor launches fixed registered argv with `shell=False`, controlled working directory and allowlisted minimal environment; never forward all parent credentials. Keep stdin/stdout/stderr separate and drain output concurrently with incremental byte caps; unbounded `communicate()` buffering is unsuitable. Bind Windows processes to an owned cleanup mechanism/process tree (Job Object candidate); do not rely on POSIX signal/process-group assumptions. Proposed graceful stop <=250 ms then force termination/reap within a bounded two-second cleanup allowance. Cleanup allowance performs no new retrieval/extraction/commit; record descendants that could not be confirmed terminated. Windows process-tree behavior requires implementation-stage verification. [Python subprocess](https://docs.python.org/3.11/library/subprocess.html), [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

Effective deadline is the earliest parent UTC deadline, registered timeout and inherited remaining limit; derive a local monotonic timer. Check cancellation/expired budget before admission and again before launch/commit. Worker HTTP connect/read timeouts cannot extend it. Initial proposals: search <=20 seconds, fetch including extraction/commit <=45 seconds, read <=5 seconds, redirects <=5, PDF physical pages <=500, explicit decoded content/normalized-text caps above. Bound encoded transport bytes separately before decompression; no claim byte/page limits alone bound RAM. Use isolated process memory quotas where feasible; failure to configure a required quota must be explicit. Actual quota mechanism/threshold is a PM implementation decision.

Retry ownership: executor launches once, HTTP transport retry setting is disabled initially, Connections never retries. DDGS has internal concurrent behavior and imperfect request accounting; expose that limitation until instrumentation/wrapper bounds are implemented. Container may authorize an additional backend/attempt within shared request/deadline limits, with a new attempt ID and retained failures. Storage delivery reconciliation uses the same operation ID and is distinct from network retrieval retry.

| Error category / examples | Semantics |
| --- | --- |
| input: VALIDATION_ERROR, UNSUPPORTED_FILTER/MODE/RANGE, UNKNOWN_TOOL | No unsupported work; caller can correct arguments |
| authority: ACCESS_DENIED, INVALID_BINDING | No unauthorized execution; refs/IDs alone do not grant access |
| provider/transport: SEARCH_UNAVAILABLE, HTTP_ERROR, TLS_ERROR, RATE_LIMITED when evidenced | Preserve known HTTP/retry-after details; generic DDGS empty error does not prove rate limiting |
| content: BLOCKED_CONTENT, EMPTY_EXTRACTION, ENCRYPTED_PDF, NO_TEXT_LAYER, UNSUPPORTED_MEDIA, CONTENT_LIMIT | No successful article/snapshot claim; surface available safe observations |
| process/protocol: LAUNCH_FAILED, WORKER_CRASH, PROTOCOL_ERROR, OUTPUT_LIMIT | Capture exit/signal/cleanup facts without raw secret-bearing dumps |
| persistence: STORAGE_UNAVAILABLE/BUSY, BUNDLE_LIMIT, COMMIT_UNKNOWN | Preserve operation ID/known receipt/commit state; no blind external replay |
| control: DEADLINE_EXCEEDED, CANCELLED, MEMORY_LIMIT | Stop work and cleanup; preserve any prior durable commit |

An error includes bounded safe message/details, category, retry hint (`never`, `caller_decision`, `delivery_reconcile`) and causal IDs. Retry hints are guidance, not auto-retry authorization. A fatal process cannot be required to produce JSON; executor observations supply the outcome.

Observations include backend/config/library versions, requested/effective limits, queue/process/retrieval/extraction/commit duration where measured, timestamps, cache origin (`none` initially), HTTP request/redirect counts when known, decoded/encoded bytes separately, output text bytes, optional provider request IDs, and finalized refs. Unknown request count/cost/usage is unknown; no invented zero monetary bill. Redact credential-bearing URLs/headers, token/config secrets and raw exception text before stdout/stderr/event propagation. Fetch source content may itself contain sensitive material; follow scoped retention/context policy rather than treating extraction as sanitization.

## 7. Readiness and acceptance after approval

Current verification consists of primary-source research, real isolated Windows public search/HTML/PDF trials, sibling proposal review and document review. No ToolExecutor, transport, snapshot API or lifecycle integration has been built or tested. Root dependency files remain unchanged. Local vLLM Qwen is undeployed and live verification remains pending outside Toolset research.

After PM reconciles shared design/contracts and the user authorizes implementation, the selected-stack handoff must demonstrate:

1. Reproducible uv/Python 3.11 setup using PM's selected lock, actual registered tool entry points and JSON protocol.
2. Real search with accurate named-backend/filter provenance, bounded Google-to-DuckDuckGo fallback and structured outage handling; no fixed results. Pass an agreed representative research-task availability and URL-fidelity corpus, including niche/domain tasks and URL query parameters, before teammate acceptance or experiments. These gates remain unverified.
3. Real same-response static-HTML/unencrypted-text-PDF retrieval, retained content-decoded bytes with encoding/representation/hashes, complete durable snapshot and bounded preview.
4. A new process reads the saved immutable snapshot with stable lines/pages, truncation/long-line continuation and no network; scopes denied explicitly.
5. Invalid protocol/argv exposure, cancellation/deadlines/output bounds/process-tree cleanup/memory pressure, content limitations and partial/ambiguous Storage publication handled meaningfully.
6. Real SQLite/filesystem records show one Container intent/outcome and Storage snapshot commit receipt/event; interrupted intent remains inspectable, recorder recursion absent, standalone uses the same path.
7. Synthetic secret/capability redaction checks and selected wheel/license inventory; no use of real credentials as test fixtures.

Remaining PM decisions: reconcile common envelope/types/errors and supported filters/fallback accounting; approve mediation or streaming transport and concrete caps; agree acceptance-gate criteria, timeout/request/memory policy and Windows cleanup mechanism; assign runner/shared schema ownership and any later dependency changes. The stack, content-decoded preservation and initial static-HTML/unencrypted-text-PDF/no-browser/no-OCR scope are selected. Shared decisions remain draft, and implementation awaits user authorization.
