# CLI Toolset design against platform contract v1

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../../team-start.md)
> and the [current usage guides](../../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

CLI Toolset Team. Research baseline: 2026-09-30 America/Toronto.
This complete revision follows the
[current mission](../missions.md), [platform-contract-v1.md](../platform-contract-v1.md)
and [CONTRIBUTING.md](../../../CONTRIBUTING.md), replacing earlier transport,
receipt and result proposals. It is documentation, not a runnable module.
Runtime source, project dependencies and model calls await phase authorization.

PM retains DDGS 9.16.0, HTTPX 0.28.1, Trafilatura 2.2.0 and pypdf 6.19.0.
The coordinated design selection is Yahoo primary, corrected Google fallback
(disabled until its integrated fidelity gate passes), and separately registered
scholar.crossref.search@1 / scholar.openalex.search@1. Historical Google/DDG
failures remain recorded; no new runtime or live probe is part of this revision.
Supported sources are static HTML, ordinary text/plain and unencrypted text PDFs.
Browser/OCR/authenticated browsing/paid search/document.find are outside v1.
See [research](../../research/free-search-fetch.md) for actual evidence and
failed selected-search availability/fidelity gates.

## 1. Ownership and recorded execution

After authorization, Toolset owns src/ebd/toolset/ and tests/toolset/: catalog,
validation, executor, workers, CLI parsing/formatting and process/resource checks.
Connections supplies binding/identity/scope/grants. Container owns the single
RecordedToolAction and lifecycle events; Storage owns publication/immutable
reads/publication events. PM owns shared types, composition and integration.

```text
host/agent -> Connections -> Container RecordedToolAction
           -> ToolExecutor -> fixed CLI worker -> prepared observation
                          -> scoped SnapshotStore commit/read
           <- execution observation -> acknowledged tool.outcome -> ToolResult
```

The [baseline](../baseline-acceptance.md) uses Engine and registered tools,
never direct DDGS/HTTP/parser/subprocess/alternate-store calls. Search is
discovery; citations require saved document.read slices. Toolset contains no
model session, answer generation, research strategy or scheduler.

1. Resolve pinned definition; validate closed arguments/grants and reserve
   shared-lineage attempt/limits. Rejected preflight has no process/attempt;
   Container records tool.rejected when possible.
2. Container freezes tool.intent, obtains committed EventReceipt and rechecks
   deadline/cancellation/grants before worker/network/Storage read. No receipt
   means no external work. Known nondispatch after intent gets tool.outcome
   with dispatched=false.
3. Executor rechecks live attempt lease, obtains authoritative read slice or
   retains assigned fetch operation ID, constructs fresh private request and
   launches only trusted fixed argv.
4. Concurrent pumps enforce all stream bounds. Executor validates response
   identity/phase/exit/caps/cleanup. Fetch validates proposal then calls scoped
   SnapshotStore.commit under still-valid normal authority.
5. Executor returns internal ToolExecutionResult. Container records observed
   execution/cleanup/commit facts and obtains terminal receipt before ToolResult.
   Incomplete recording stops future dispatch.

Executor is a trusted consumer of the recorded action path. Binding requires
the same reserved live attempt lease rechecked/activated after the gate. JSON context or saved receipt is
not authority. No alternate unrecorded host path, logger or snapshot database.

## 2. Catalog, interfaces and closed public inputs

```text
ToolCatalog.resolve(name, revision) -> Result[ToolDefinition]
async ToolExecutor.execute(definition, arguments, context, storage_plan)
    -> ToolExecutionResult
async ToolExecutor.close(deadline) -> CleanupReport
async RecordedToolAction.run(tool_request, binding, context) -> ToolResult
```

Resolution uses Ok(value)|Err(error). Execution returns domain outcome directly,
with no competing ok envelope. Expected failures are data; unexpected defects
remain exceptions after cleanup. Clean up and re-raise Python task cancellation;
explicit engine cancellation returns cancelled.

ToolDefinition required fields: schema_version,name,revision,description,
input_schema,output_schema,capabilities,limits,argv,config,storage_needs.
Name/revision identify immutable registry entries; both schemas are closed.
output_schema describes public tool payload within ToolResult, not worker
envelope. Trusted argv pins executable/module/arguments; no model-provided
shell/executable/cwd/env. Config pins safe search/extraction policy. Model sees
only names/descriptions/public schemas. Unknown names/revisions fail resolution.

Initial revision is 1 for all five registered tools. Reject unknown properties, duplicate keys, nonfinite
numbers, wrong types and oversized JSON. Boolean is not integer. String limits
apply to UTF-8 bytes and bounded characters. Bindings only narrow.

| Tool | Exact allowed public fields | Required binding |
| --- | --- | --- |
| web.search | query: nonblank string <=4096 UTF-8 bytes; max_results: integer 1..10, default 5 | network.search; Yahoo/conditionally enabled Google plan |
| scholar.crossref.search | query: nonblank string <=4096 UTF-8 bytes; max_results: integer 1..10, default 5 | network.search narrowed to fixed Crossref metadata endpoint, no Storage publication |
| scholar.openalex.search | query: nonblank string <=4096 UTF-8 bytes; max_results: integer 1..10, default 5 | network.search narrowed to fixed OpenAlex metadata endpoint, no Storage publication |
| web.fetch | url: absolute http/https <=8192 UTF-8 bytes, no userinfo; mode: optional literal static, default static | network.fetch; snapshot.commit in assigned scope |
| document.read | snapshot_ref: Storage typed store-qualified ref; range: exactly {kind:lines or pages,start,end_exclusive}; max_text_bytes: integer 1..65536, default 65536; continuation: null or bounded opaque cursor, default null | snapshot.read for exact object/range |

No public deadline/backend/root/operation ID/grant/key/slice/reserved controls.
Region/backend/filter settings belong to trusted config. Initial search exposes
no date/language/domain/safesearch filter. Unknown filters fail validation.
Literal site: syntax is a query, not verified domain enforcement. Future filters
require verified capability intersection across all fallbacks; DDG ignores
safesearch and cannot satisfy enforced safesearch. Never weaken silently.

## 3. Shared identity, errors and result records

schema_version=1 is sole wire/event compatibility major. Tool revision,
document_snapshot/1, document_index/1, extraction and normalization versions
are separate. Common allocators supply action per logical call, attempt before
each dispatch, new attempt for authorized execution retry. Identical delivery
retains frozen event/operation IDs/content. Worker request_id only correlates;
Container separately preserves provider-native call IDs.

These exact records elaborate common types for the shared package; optional
values are explicit null. No second receipt/finalization helper is introduced.

| Record | Required fields / meaning |
| --- | --- |
| ToolExecutionResult | schema_version,tool,invocation,status,result,error,observations,process,usage,persistence; internal, no lifecycle acknowledgment |
| ToolResult | Same facts plus recording,event_ids; Container finalizes |
| tool | {name,revision} |
| invocation | {run_id,root_run_id,correlation_id,action_id,attempt_id,context_kind}; attempt nullable for nondispatch; no invented standalone agent/provider ID |
| status | succeeded,failed,validation_failed,limit_exhausted,timed_out,cancelled; execution terminal independent of recording/commit |
| error | null or {code,message,details,observed_effect_state}; Storage/delivery errors also commit_state,retryable_delivery; bounded/sanitized |
| persistence | {required,operation_id,commit_state,receipt}; READY Storage receipt or null; not_applicable for all discovery tools/read |
| recording | {status,intent_receipt,outcome_receipt,error}; complete,incomplete,unavailable; receipts are EventReceipt |
| event_ids | {intent,outcome,rejected}; nullable as applicable |
| process | {dispatched,exit_code,termination_reason,stdin_bytes,stdout_bytes,stderr_bytes,stderr_truncated,cleanup}; actual observations/null |
| usage | {duration_ms,search_backend_attempts,http_request_count,http_response_count,decoded_body_bytes,text_utf8_bytes,monetary_cost}; unknown=null |

Ordinary succeeded/failed execution has exactly one result/error. Successful
observation retains result if later terminal recording fails; recording.error
describes that separate fault. Do not claim rollback of known successful effects.
Public success requires succeeded execution, complete recording and every
required READY receipt. succeeded with recording=incomplete is incomplete
delivery. Storage EventReceipt is exactly schema_version,store_id,event_id,
recorded_seq,recorded_at,duplicate. No RecordAck/caller durability flag.
An event cannot contain its own eventual receipt.

Storage SnapshotReceipt supplies assigned operation_id,snapshot_ref,manifest_ref,
raw_ref,text_ref,index_ref,component_digests,extraction_format_version,line_count,
page_count_or_null,event_receipt,duplicate. Typed references are opaque identity,
not paths/grants. Storage's definitions remain authoritative.

| Tool | Closed public payload |
| --- | --- |
| web.search | query,searched_at,backend_policy,backend_attempts,results; exact Yahoo/Google provider identity and disabled-gate fields in Section 6; discovery only |
| scholar.crossref.search | Closed crossref_result: provider/scholarly scope/query/time/discovery flag/total/results with original DOI/member/publisher/link identities; Section 14 |
| scholar.openalex.search | Closed openalex_result: provider/scholarly scope/query/time/discovery flag/total/results with work/DOI/publisher/landing/OA-location identities; Section 14 |
| fetch | snapshot_ref,extraction_version,normalization_version,line_count,page_count,provenance,preview; authoritative refs/counts and <=64 KiB preview |
| read | Exact canonical DocumentSlice; no transformed/additional fields |

Safe observations record backend/redirect/status/extraction/count/error facts.
No raw source text/stderr in ordinary lifecycle payloads. Store authorized
source components separately. Reject/redact credential URLs/headers; never env,
keys,cookies,auth,machine roots or unsanitized exceptions. Cost unknown absent
billing evidence, never invented zero.

## 4. Parent-held ToolStoragePlan

Nonserializable bound in-process object with required fields
tool,invocation,scope,operation,limits,snapshot_store,operation_store,lease,request.
Unused scope/clients null. Live clients/grants/lease are Connections-issued,
never deserialized. Plan matches definition/run/action/attempt and quotas.

| Tool | operation / frozen request / injection |
| --- | --- |
| web.search | none; no snapshot/scope access; inject Yahoo/conditionally enabled Google plan |
| scholar.crossref.search / scholar.openalex.search | none; null Storage clients/scope; inject fixed scholarly provider/request plan and parent-held quota reservation descriptor |
| fetch | snapshot.commit; assigned operation_id/scope; worker receives ID/limits only |
| read | snapshot.read; exact ref/range/budget/continuation; inject Storage slice after intent |

Worker cannot replace scope/object/range/operation. Parent rechecks revocation,
normal deadline/quotas before read/commit; Storage reauthorizes every lookup.
Denied/missing/corrupt/incomplete/invalid read fails before process with recorded
nondispatch after intent. No DB/root/grant/Storage credential/broker in worker.
Initial mediation requires no extra IPC service.

## 5. Private one-shot worker protocol

Exactly one strict UTF-8 JSON stdin object then EOF; one stdout object plus
optional whitespace/EOF. stderr diagnostics bounded. Reject BOM/invalid UTF-8,
duplicate keys/nonfinite values/depth>32/extra values/unknown fields/byte overflow.
Construct fresh controls; never merge model JSON over reserved fields.

```text
WorkerRequest = {
 schema_version:1,message_type:"worker_request",request_id,
 tool:{name,revision},invocation,arguments:<validated public object>,
 execution:{deadline_utc,limits},plan:<one closed variant>
}
search plan = {kind:"search",backend_order,fallback_on,max_backend_attempts,
               backend_settings,disabled_backends}
scholarly plan = <closed fixed-provider variant and exact mapping in Section 14>
fetch plan = {kind:"fetch",operation_id,representation:"content_decoded",
              extraction_config_ref,normalization_version}
read plan = {kind:"read",slice:<authoritative DocumentSlice>}
WorkerResponse = {
 schema_version:1,message_type:"worker_response",request_id,tool,invocation,
 phase:"prepared"|"failed",prepared:<payload|null>,error:<error|null>,
 observations:<bounded safe facts>,usage:<observed values/null>
}
```

All fields required; variants closed, identities exactly echoed. prepared has
payload/error=null; failed has prepared=null/error. Web search prepares discoveries;
scholarly tools prepare their exact provider-specific closed discovery payload;
read returns exact slice; fetch prepares {operation_id,proposal}. No newly minted fetch refs,
receipts or grants. Original/text/index are canonical base64 plus declared
decoded length/SHA-256; text/index strict UTF-8 after decoding. Private response
is never final model/host output.

| Exit and response | Decision |
| --- | --- |
| 0 + prepared | Eligible validation/commit only |
| 2 + failed validation/unsupported | validation_failed |
| 3 + failed transport/content | failed |
| 4 + failed limit | limit_exhausted |
| 5 + failed deadline | timed_out |
| 6 + failed cancellation | cancelled |
| Mismatch/missing/truncated/extra/invalid | WORKER_PROTOCOL_ERROR; no commit |
| Crash/other exit/OS termination | WORKER_CRASH unless parent observed cancel/timeout/limit first |

Parent-observed stop wins over later worker claim. No commit from cancelled,
timed-out/overflowing worker even with valid output prefix. EOF/root exit is
insufficient with live descendants/drains. Lost output cannot authorize refetch.
Malformed/unbound direct worker fails before external work; valid JSON is not
launcher authentication or same-user OS isolation.

## 6. Selected named search and complete URLs

PM selected Yahoo primary, with its DDGS-declared Bing relationship recorded
explicitly, and corrected Google as a bounded fallback. At most one named call
per backend, at most two in a worker. Google is disabled until integrated
raw-wrapper fidelity acceptance passes; currently only Yahoo is active.
An enabled profile never infers Google readiness from a configured name or the
four isolated correction cases. Trusted gate evidence pins adapter/config/tool
revisions. No public argument/worker flag can enable it.

No auto/merge/invalid-name fallback/page walk/hidden wrapper retry. DDG is only
an explicitly reviewed alternative configuration, replacing an allowed slot
under the same <=2-call bound; it is not a default or added third hidden attempt.
No enforced domain/date/language/safesearch/region promise for ignored settings.
Literal site: in query is syntax, not a verified filter. Yahoo's declared Bing
relationship is implementation metadata, not observed independent index proof.

Each actual named call consumes inherited deadline. Explicit fallback_on allows
no-results, backend/transport failure and invalid/unusable URLs; denial/cancel/
deadline/quota stops. Useful primary stops fallback. If Yahoo is unavailable
while Google is disabled, return SEARCH_UNAVAILABLE with its actual attempt
and the disabled reason; do not call an unapproved replacement.

Fallback is a backend observation, not another tool attempt. Relaunch requires
new attempt/intent. backend_attempts entries are exactly backend_attempt_index,
backend,declared_provider,outcome,elapsed_ms,returned_count,kept_count,error.
declared_provider is pinned DDGS metadata (Yahoo declares Bing; Google declares
Google). outcome is returned,unavailable or failed. No-results does not prove
blocking/rate limiting. DDGS internal HTTP count unknown unless measured.

The closed web.search result is query,searched_at,backend_policy,
backend_attempts,results. backend_policy is exactly configured_order,active_order,
disabled_backends; its two order arrays contain reviewed names with <=2 entries.
Each disabled entry is {backend,reason}, currently
{backend:"google",reason:"URL_FIDELITY_GATE_PENDING"}. Disabled backend consumes
no attempt index/count or request. Each candidate has rank,title,url,snippet,
source_date,backend,declared_provider,discovery_only=true,truncated_fields.
Unknown date null. Rank keeps backend order; source metadata is discovery only.

Validate absolute HTTP(S) URLs and keep path/query/percent encoding/fragment.
Dedupe cannot collapse different query targets. HTTP excludes fragment and
records actual normalized request/redirects alongside discovery URL.
truncated_fields is only title/snippet; URLs/identifiers are never truncated.
Result/actual encoded cap enforced before output.

Stock Google parsing loses wrapped queries/encoded targets. Required correction
parses raw outer q once, preserving destination query/escaping, before stock
postprocessing discards it. Never guess from damaged final href. Direct-link
success does not waive the failed stock gate. Yahoo query/escape/literal-plus
fidelity and repeated representative availability also remain unverified.
Historical Google/DDG 9/48 and 0/18 EBD observations are preserved, not relabeled
as evidence for this newly selected profile.

Separate scholar.crossref.search and scholar.openalex.search are specified in
Sections 14–16. They never silently merge into web.search or claim general web
coverage. Their metadata must lead to normal web.fetch/document.read for
source evidence. Package stack remains unchanged; selection is design only.


## 7. Same-response retrieval, decoding and provenance

HTTPX GET with TLS verification, no implicit env proxy/credential inheritance,
hidden retry or more than five explicit redirects. Check bound destination
policy each connection. Public mode rejects userinfo, credential-like query,
forbidden IP ranges. Actual transport must connect to validated resolved
address; resolve-then-unpinned-connect is not rebinding protection. No cross-origin
credentials. Count observable requests/responses; hidden requests unknown.

Original means content-decoded body, not compressed wire capture. Stream limits
before adding overflowing chunk; bound transfer bytes where observable and
decoded bytes separately. Content-Length early hint only. Hash retained bytes;
record representation/content-encoding/declared length. Text/index/preview all
derive from that one body, never a second GET.

| Media | Derivation / explicit failure |
| --- | --- |
| text/html or application/xhtml+xml | Pinned Trafilatura/options, extractor network disabled. Charset from consistent declaration/BOM/meta policy; record chosen encoding/detection. Bad decoding/challenge/login/JS-only/empty extraction fail; heuristics cannot prove every page is an article. |
| text/plain | Compatible UTF-8 BOM; UTF-16 BOM only matching declaration or no charset. Otherwise registered declared charset, else strict UTF-8. Unknown/conflicting charset or decode failure explicit UNSUPPORTED_ENCODING/DECODING_ERROR; no replacement/guessed Latin-1. Reject NUL/binary controls except TAB/LF/CR/FF. |
| application/pdf | Verify magic; pypdf from retained BytesIO, unencrypted, <=500 physical pages, elapsed/text/index caps. Empty pages retained; all-empty/scanned PDF_NO_TEXT with OCR_REQUIRED observation. Encrypted/malformed failure, no passwords/OCR. |

Canonical text UTF-8/no BOM; CRLF/lone CR=>LF. No implicit NFC/NFKC, text/plain
whitespace collapse/form-feed removal/final-LF trimming. HTML normalization pinned.
An unsolicited 206/Content-Range response is partial and fails, not a complete
snapshot. Type/magic disagreement, unsupported/binary/non-2xx/challenge/empty/extraction
failure cannot become successful article snapshot. Physical PDF locators do not
guarantee multi-column/table/equation/semantic fidelity.

Safe provenance: requested_url, optional discovery_url,final_url,redirects,
retrieved_at,http_status,media_type,content_encoding,representation,
declared_content_length,chosen_charset,charset_source,original/text/index
sizes/SHA-256, extraction identity/options/config ref,normalization version,
classification and optional search query/backend/rank. Allowlisted ETag/
Last-Modified only; no arbitrary headers/cookies/auth. Missing metadata null.
Serialized provenance <=64 KiB; excess explicit limit failure.

## 8. Storage proposal, publication and exact read

Storage document_snapshot/1 proposal includes original/text/index descriptors
and bytes, extraction identity/config/options,normalization version,physical
page map/count if available,classification,provenance. No paths/final refs.
Descriptors require byte_length/SHA-256. Parent verifies base64/actual lengths/
hashes/UTF-8/schema/index/versions/provenance/assigned ID/whole wire cap before
commit. Storage independently verifies structure/digests/limits/locations; no
source reparse/article guarantee.

document_index/1 contains ordered logical-line content spans and physical page
spans. Offsets zero-based/end-exclusive, UTF-8 boundaries. LF outside line
content spans; coverage accounts every byte. PDF joins normalized page strings
with one explicit LF between pages, outside page spans and accounted by
normalization/index policy. Empty physical pages retain ordinal/equal endpoints,
no invented line. Printed labels descriptive, physical numbers canonical.

```text
SnapshotStore.commit(context,operation_id,scope,proposal) -> Result[SnapshotReceipt]
SnapshotStore.read(context,snapshot_ref,range,max_text_bytes,continuation)
    -> Result[DocumentSlice]
OperationStore.status(context,operation_id) -> Result[OperationStatus]
```

READY receipt proves sealed verified components,published metadata/event.
Only receipt refs become public; refresh produces new immutable snapshot even
with equal bytes. Preview uses validated canonical proposal text. Reads use
saved Storage bytes/index; never network/new extractor.

DocumentSlice required fields match Storage: schema_version,snapshot_ref,
extraction_version,normalization_version,requested_range,returned_range,spans,
text,truncated,has_more_in_requested_range,has_more_in_document,next_position.
Spans identify absolute line/physical page where applicable and UTF-8 offsets.
Read worker echoes injected slice; parent requires equality of all text/fields.

Range exactly {kind:lines|pages,start,end_exclusive}, one-based/end-exclusive,
1<=start<=end_exclusive<=N+1 for selected unit. Never clamp. <=200 lines/10
physical pages and <=64 KiB text plus bounded overhead. Non-PDF pages unsupported.
Empty text zero lines; final LF no phantom: ""=>0,"a"=>1,"a\n"=>1,"\n"=>1,"a\n\n"=>2.

| Case | Exact behavior |
| --- | --- |
| Valid empty [k,k) | Empty text/spans, complete range, no cursor; more-document follows remaining units |
| Zero selected units | Only [1,1) |
| Empty physical page | Consume page/zero-byte span; progress by unit despite zero bytes |
| Budget splits line/page | UTF-8-boundary partial span, stable locator, truncation and advancing next_position |
| Next code point cannot fit | LIMIT_EXCEEDED plus minimum_next_codepoint_bytes 1..4; no zero-progress cursor |
| Continuation | Same immutable snapshot/extraction/normalization/original range, reauthorized; smaller positive budget if next code point fits |

Storage cursor opaque/integrity-protected, not grant. Returned range/spans
identify actual units/partial bytes. More requested content differs from more
document. Empty intermediate page cannot prevent reading later requested pages.

## 9. Uncertainty, cancellation and close

Identical delivery keeps IDs/frozen content; changed content conflicts. No
default worker/source/model replay. Lost commit reply uses same-ID status with
reauthorization. Momentary absence is not noncommit if admission/queue unknown.
Confirmed nonadmission/rollback/durable abort=>not_committed; READY=>committed;
unresolved admitted/queued/sealed=>unknown/pending, owner/resources retained.
Duplicate committed delivery never refetches.

| Failure | Required observation/action |
| --- | --- |
| Intent unavailable/denied preflight | No read/network/process; recording unavailable or rejection |
| Worker cancel/timeout/overflow/crash | Terminate tree, bounded drains/reap, safe observed effects; no commit |
| Cancel before commit admission | No new business write; not_committed only if admission known absent |
| Cancel after admission | Storage settles or remains unknown; commitment cannot be undone |
| Lost commit reply | Same operation status, no refetch/new ID |
| Lost outcome append | Preserve execution/receipt facts; same event ID/digest status/re-delivery, no success without ack |
| Unconfirmed cleanup | Incomplete; retain controlled resources, no public success |

Inherited UTC-to-monotonic deadline/ledger cover network/parsing/read/commit;
fallback never resets it. Selected finite defaults: work <=60s also <=ancestor/
binding limit, backend <=8s, HTTP connect/read <=8s/10s limited by remaining
whole time. Not measured SLAs.

Explicit engine cancellation returns cancelled after cleanup. Python task
cancellation shields only finite owned cleanup/record settlement then re-raises.
Separate trusted record_cleanup targets <=5s unless narrowed: owner-event
append,same-ID status,resource/lease cleanup only. No new model/tool/business
publication. Uninterruptible admitted Storage I/O may exceed grace; pending
close retains owner/root, never fabricated rollback.

Executor.close stops admissions/cancels/drains workers, verifies tree/pipes and
closes handles. Container finishes records, Connections releases leases, Storage
closes last. Borrowed binding never closes shared store. Detached live work is
not closed.

## 10. Bounded drains and real Windows descendants

Start concurrent stdin writer/stdout drain/stderr drain before exit wait;
incremental counters/bounded buffers. stdout or total stderr>64 KiB overflow
triggers limit termination; no infinitely discarded stream. Close stdin after
one request. Decode after byte caps, strict parse/schema. No unbounded
communicate/capture_output in production. Sanitize bounded diagnostic tail.

Windows gate: unnamed Job Object, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no
breakaway. CREATE_SUSPENDED/CREATE_NO_WINDOW worker, assign before resuming
primary thread. Setup/assignment failure terminates/reaps suspended child
before tool code. Inherit only child stdio, not Job/parent handles. Check nested
job compatibility, never enable breakaway to work around failure. Dedicated
Win32 spawn adapter avoids assigning already-running Popen escape race.

On stop: TerminateJobObject, reap root, verify zero active job processes, close
parent job handle, bounded EOF/drains, close process/thread/stream handles.
Root exit with descendant-held pipes still requires job cleanup. Taskkill/root
kill alone is not proof. These are design inferences from
[Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[assignment API](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
and [creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags),
checked 2026-09-30; no adapter/cleanup implemented/tested. Jobs contain ordinary
CreateProcess descendants; no hostile same-user service/privileged-launch sandbox.

## 11. Smaller profile and measurement gates

| Item | Maximum, narrowing only |
| --- | ---: |
| Content-decoded original | 8 MiB |
| Canonical UTF-8 text / index | 4 MiB / 1 MiB |
| Serialized provenance | 64 KiB |
| Worker stdin / fetch stdout | 1 MiB / 20 MiB |
| Web/scholarly search/read stdout / final public JSON | 512 KiB each |
| Scholarly metadata transfer / decoded body | 1 MiB each |
| Scholarly total request/parse time | <=30s and inherited deadline |
| stderr total / JSON depth | 64 KiB / 32 |
| Read/preview text | 64 KiB |
| Requested read units | 200 lines / 10 physical pages |
| PDF pages | 500 physical pages |
| Fetch concurrency | Measure one first, then at most two |

MiB=1048576/KiB=1024 bytes. Base64=4*ceil(n/3); 8/4/1 MiB combined
requires 18,175,324 bytes before metadata/framing. Check actual full encoded
envelopes/escaped strings before writing; individually fitting components can
fail total cap. Validate lengths before decode allocation, hash actual bytes,
bound depth/arrays/metadata.

Caps do not bound PDF/DOM/parser/object RAM,copies,buffers,latency. No research
peak RAM evidence. Future acceptance measures Windows parent and worker/job
peak private committed bytes/working set,baseline/delta,time,encoded bytes and:

- One HTML/plain-text/text PDF then <=2 simultaneous fetches.
- Max-fit, one byte over each cap, aggregate/escaped oversize, invalid base64/
  JSON, stdin/stderr floods.
- Compressed PDF expansion, malformed/huge text/empty pages, parsing cancellation,
  actual memory-limit failure.
- Crash before/after output, real sleeping descendant and descendant-held pipes,
  timeout/overflow/failed Job assignment, actual process removal.
- Cancel around Storage admission/lost commit/outcome reply, same-ID settlement
  with no second source GET.

Select/verify finite Job committed-memory ceiling from measured host/corpus
budget, not source cap; value pending measurement. Parser allocation may precede
text/page counters, so external memory ceiling/whole deadline are required.
Breach typed limit failure, no partial snapshot/success. Larger required sources
or unacceptable RAM need measured streaming/scope proposal before raising limits
or adding IPC/browser/OCR.

## 12. Standalone and compact conformance checklist

Proposed ebd tool <registered-name> --json takes one public argument object and
emits final ToolResult. PM composes bootstrap; Toolset parses/formats. Connections
opens single Storage/control owner, creates fresh standalone_tool scope/grants,
then same Container RecordedToolAction; no model/profile opens. Old snapshot
requires explicit grant; owned root=>STORAGE_BUSY, active Engine attachment
outside v1. Host exit zero only public success; worker zero only preparation.

| Common requirement | Conformance | Future proof |
| --- | --- | --- |
| Sole version/Result vs domain outcome | Sections 2–3 | shared types/schemas |
| IDs/live grants/shared ledger | Sections 1,3–4,9 | denial/revocation/retry |
| Intent before worker/network/read, runtime producer | Sections 1,12 | acknowledged real recorder |
| Prepared vs finalized receipts | Sections 3,5,8 | phase/exit/commit/outcome faults |
| Parent plan/no DB/broker/logger | Sections 4–5,8 | real clients/Storage |
| READY/unknown/no replay | Sections 8–9 | cancellation/lost reply/dedup |
| Immutable ranges/empty pages/cursors | Section 8 | reopen/code-point progress |
| Same-body HTML/plain/PDF | Sections 7–8 | stored hashes/classification |
| Web search/intact URLs | Section 6 | Yahoo repeated availability/URL fidelity; Google disabled until integrated gate |
| Scholarly provider/quota/metadata discovery | Sections 14–16 | real identity/relevance/one-request/errors/quota/source follow-through |
| Smaller caps/drains/deadlines/tree | Sections 9–11 | RAM/expansion/Windows cleanup |
| Same standalone helper/no model | Section 12 | real host/Container/Connections |
| Complete baseline consumption | Sections 1,8,12 | real model/cited slices/reopen by PM |

PM selected the five-tool discovery catalog without changing generic shared
execution/Storage/recording APIs. Historical failed search availability/fidelity,
new-profile unverified availability, unmeasured resource/cleanup and absent runtime integration prevent
runnable acceptance. Design/isolated fetches do not complete teammate or baseline
handoff.

## 13. Closed argument schema artifacts and bounded parser details

The following valid JSON Schema fragments specify the public argument objects.
The SnapshotRef reference denotes the shared Storage type in the common schema
package, not a network lookup or an authority grant. UTF-8 byte limits, URL
policy, grant checks, range ordering and selected-unit bounds are additional
semantic validation; JSON Schema character length alone cannot enforce them.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$defs": {
    "web_search": {
      "type": "object", "additionalProperties": false, "required": ["query"],
      "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 4096},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}
      }
    },
    "scholar_crossref_search": {"$ref": "#/$defs/web_search"},
    "scholar_openalex_search": {"$ref": "#/$defs/web_search"},
    "web_fetch": {
      "type": "object", "additionalProperties": false, "required": ["url"],
      "properties": {
        "url": {"type": "string", "minLength": 1, "maxLength": 8192},
        "mode": {"const": "static", "default": "static"}
      }
    },
    "document_range": {
      "type": "object", "additionalProperties": false,
      "required": ["kind", "start", "end_exclusive"],
      "properties": {
        "kind": {"enum": ["lines", "pages"]},
        "start": {"type": "integer", "minimum": 1},
        "end_exclusive": {"type": "integer", "minimum": 1}
      }
    },
    "document_read": {
      "type": "object", "additionalProperties": false,
      "required": ["snapshot_ref", "range"],
      "properties": {
        "snapshot_ref": {"$ref": "ebd-contract-v1#/$defs/SnapshotRef"},
        "range": {"$ref": "#/$defs/document_range"},
        "max_text_bytes": {"type": "integer", "minimum": 1, "maximum": 65536, "default": 65536},
        "continuation": {"type": ["string", "null"], "maxLength": 8192, "default": null}
      }
    }
  }
}
```

Every exact record/variant enumerated in Sections 3–5 also rejects unknown
properties and validates finite JSON, causal identity and bounds. Limits are
fixed allowlisted integer fields drawn from Section 11, never arbitrary worker
control names. Observation arrays cap at ten search results, two initial
backend attempts, one request per scholarly tool, five source-fetch redirect
hops and 500 physical pages; index bytes still
cap at 1 MiB. Safe details have <=8 KiB serialized JSON and messages <=1024
UTF-8 bytes. Unknown observations fail schema; backend-specific facts belong
only to explicitly declared schema fields. Process cleanup uses the common
CleanupReport type; it never equates root exit with whole-resource completion.

Registered worker argv is pinned by trusted registration, for example
[resolved_python,"-m","ebd.toolset.worker",tool_name,tool_revision]. This is an
illustration of future composition, not an installed command. All public
arguments travel through stdin, never command-string interpolation.

HTML charset policy is pinned as follows: compatible BOM, then HTTP charset,
then HTML meta declaration, then strict UTF-8; record all observations and
reject a conflicting BOM/declared encoding. Undeclared non-UTF-8 fails explicitly
rather than silent replacement. Extraction receives decoded text, with network
disabled. This may reject some legacy pages and must be evaluated on the
required corpus before broadening detection policy.

For plain text the declared charset is resolved through an allowlist of text
codecs (UTF-8, UTF-16/LE/BE when consistent with BOM, ASCII, Windows-1252 and
ISO-8859-1). Remove a compatible initial BOM before canonical encoding.
Unknown/ambiguous/conflicting encodings fail. Explicit declared Latin-1 is
different from guessing it after a failed UTF-8 decode. Decode strictly, then inspect Unicode text (UTF-16 raw NUL bytes are not binary evidence); retain
TAB/LF/CR/FF and reject other C0 controls, DEL and NUL. Empty/whitespace-only
text is unusable fetch content, even though empty snapshot range semantics are
defined for Storage.

Read responses may echo the authoritative existing SnapshotRef in the injected
slice. The prohibition in Section 5 concerns newly minted fetch references,
receipts or expanded authority. Storage-controlled cursors/refs are compared
against the injected slice without reinterpretation.

The Google parser correction must preserve properly outer-encoded multi-parameter
destinations with one decode, not double-decode destination %26/%2B. Reject
duplicate q values or ambiguous unescaped wrapper parameters; full destination
recovery is impossible once an upstream parser has discarded it. Four controlled
candidate cases pass, but live query-bearing wrapper integration and malformed
cases are pending runtime acceptance. Content/media unsupported errors use
failed/exit 3; invalid public mode/schema/filter uses validation_failed/exit 2.

## 14. Registered scholarly discovery: exact protocol and schemas

The PM-selected catalog adds scholar.crossref.search@1 and
scholar.openalex.search@1. Each uses the same ToolDefinition, ToolExecutor,
WorkerRequest/Response and Container RecordedToolAction as the other tools.
Their fixed provider is in trusted config; query and max_results are the only
public inputs. The closed argument schema is the same query/limit schema in
Section 13, bound separately to each tool. There is no public endpoint, API
key, account, sort, filter, page, automatic retry or fallback argument.

The network.search grant narrows to the exact configured metadata endpoint;
neither tool receives snapshot publication/read rights or a model session.
ToolStoragePlan operation=none, scope/snapshot_store/operation_store=null,
with frozen provider request policy in request and the same live attempt lease.
Container's committed intent precedes quota admission/worker/network; deadline,
revocation and local quota are rechecked immediately before actual dispatch.

```text
scholarly plan = {
 kind:"scholarly",provider:"crossref"|"openalex",
 endpoint_id:"crossref_works_public"|"openalex_works_anonymous",
 query_parameter:"query.bibliographic"|"search",
 count_parameter:"rows"|"per-page",
 request_method:"GET",max_http_requests:1,follow_redirects:false,
 max_response_transfer_bytes:1048576,max_response_decoded_bytes:1048576,
 max_response_json_depth:32,max_metadata_duration_ms:30000,
 max_encoded_request_url_bytes:16384|4094,
 quota_reservation_id:<parent-owned identifier>
}
```

This variant is closed. Numeric values above are enforcement ceilings; trusted
bindings may narrow them. Endpoint/provider/method/parameter constants never
change. Exact tool/provider/endpoint/parameter/cap mapping is
validated, not inferred from worker input:
Crossref maps to crossref_works_public,query.bibliographic,rows,16384;
OpenAlex maps to openalex_works_anonymous,search,per-page,4094.
The two literal endpoint IDs resolve to https://api.crossref.org/works and
https://api.openalex.org/works through pinned trusted config. No worker-selected
host/path or cross-provider fallback. Reservation ID is only a causal
descriptor; the live reservation/accounting stays in the parent.

Supply the validated original query unchanged, including quotes, case, spaces,
plus signs and Unicode. Encode it only for URL transport and verify round-trip
parameter equality. Do not trim, add an author/phrase/filter, change keywords,
split a long query or walk pages. Strategy chooses query wording. Reject an
overlong fully encoded URL locally with validation_failed before a request;
the smaller OpenAlex configured ceiling applies even when public query bytes
fit. max_results becomes rows/per-page exactly. Pinned request parameters are
only the query/count pair; no mailto/key/politeness identity is invented.

Exactly one anonymous GET per admitted tool attempt, with TLS, no proxy/env
credential inheritance, auth/key/cookie header, redirects or transport retry.
Redirect response fails explicitly; it is not a second metadata request.
HTTP timeout/stream/parse/projection all consume min(30s,remaining work deadline);
connect/read ceilings remain 8s/10s narrowed by that total. Count transfer and
content-decoded body before overflow, each <=1 MiB. Require JSON media and strict
UTF-8/finite unique-key JSON at depth<=32. Incomplete/malformed provider response
is failure; a well-formed genuine zero-result list is a prepared empty discovery,
not an outage or a claim of useful coverage.

Prepared payload is exactly crossref_result/openalex_result below, selected by
resolved tool identity. This is internal WorkerResponse.prepared, later exposed
inside acknowledged ToolResult.result. Worker cannot supply recording receipts,
Storage refs or grants. Metadata output stdout and final public envelope are
each <=512 KiB, with inherited stdin/stderr/deadline/tree rules unchanged.
No new lifecycle producer/logger or metadata database.

Schemas are closed at every output object. All fields are required; missing
upstream optional metadata becomes null or an empty list, never guessed.
Unknown upstream fields are not copied into the closed projection. Rank is
one-based order within that single returned page; never re-sort by credibility.
Crossref titles preserve the supplied title array; member_id preserves actual
Crossref member metadata, not an inferred publisher identifier. Date-part arrays keep
all supplied dates/precision; validate calendar ranges without inventing month/day.
OpenAlex work/DOI/source/host-organization/location IDs and OA URLs preserve
supplied strings, even when two locations identify the same target. Missing
locations remain empty/null. is_oa/license are provider metadata, not a guarantee
of accessible content or a new license for the linked paper.

Nullable URLs must be absolute HTTP(S), free of credential fields, and retain
query/escape/plus semantics; validate opaque identifier/provider prefixes where
documented. Schema lengths are characters; same numeric UTF-8-byte ceilings
apply separately. Native integer IDs must be exact JSON integers. Reject
overlong identifiers/URLs/titles/arrays instead of silently discarding identity.
Reject more result rows than max_results or any oversized projected envelope.
No abstracts/full-text content or purported verified quotes are projected.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$defs": {
    "identity_text": {
      "type": [
        "string",
        "null"
      ],
      "maxLength": 512
    },
    "short_text": {
      "type": [
        "string",
        "null"
      ],
      "maxLength": 1024
    },
    "url": {
      "type": [
        "string",
        "null"
      ],
      "maxLength": 8192
    },
    "integer_count": {
      "type": [
        "integer",
        "null"
      ],
      "minimum": 0,
      "maximum": 9007199254740991
    },
    "crossref_link": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "url",
        "content_type",
        "content_version",
        "intended_application"
      ],
      "properties": {
        "url": {
          "type": "string",
          "minLength": 1,
          "maxLength": 8192
        },
        "content_type": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 256
        },
        "content_version": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        },
        "intended_application": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        }
      }
    },
    "crossref_candidate": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "rank",
        "titles",
        "doi",
        "doi_url",
        "member_id",
        "publisher",
        "work_type",
        "published_date_parts",
        "links"
      ],
      "properties": {
        "rank": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10
        },
        "titles": {
          "type": "array",
          "maxItems": 10,
          "items": {
            "type": "string",
            "maxLength": 8192
          }
        },
        "doi": {
          "$ref": "#/$defs/identity_text"
        },
        "doi_url": {
          "$ref": "#/$defs/url"
        },
        "member_id": {
          "type": [
            "string",
            "integer",
            "null"
          ],
          "maxLength": 512,
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "publisher": {
          "$ref": "#/$defs/short_text"
        },
        "work_type": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        },
        "published_date_parts": {
          "anyOf": [
            {
              "type": "array",
              "minItems": 1,
              "maxItems": 8,
              "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 9999
                }
              }
            },
            {
              "type": "null"
            }
          ]
        },
        "links": {
          "type": "array",
          "maxItems": 20,
          "items": {
            "$ref": "#/$defs/crossref_link"
          }
        }
      }
    },
    "openalex_source": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "source_id",
        "display_name",
        "source_type",
        "host_organization_id",
        "host_organization_name",
        "is_oa"
      ],
      "properties": {
        "source_id": {
          "$ref": "#/$defs/identity_text"
        },
        "display_name": {
          "$ref": "#/$defs/short_text"
        },
        "source_type": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        },
        "host_organization_id": {
          "$ref": "#/$defs/identity_text"
        },
        "host_organization_name": {
          "$ref": "#/$defs/short_text"
        },
        "is_oa": {
          "type": [
            "boolean",
            "null"
          ]
        }
      }
    },
    "openalex_location": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "location_id",
        "landing_page_url",
        "pdf_url",
        "is_oa",
        "version",
        "license",
        "source"
      ],
      "properties": {
        "location_id": {
          "$ref": "#/$defs/identity_text"
        },
        "landing_page_url": {
          "$ref": "#/$defs/url"
        },
        "pdf_url": {
          "$ref": "#/$defs/url"
        },
        "is_oa": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "version": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        },
        "license": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        },
        "source": {
          "anyOf": [
            {
              "$ref": "#/$defs/openalex_source"
            },
            {
              "type": "null"
            }
          ]
        }
      }
    },
    "open_access": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "is_oa",
        "oa_status",
        "oa_url"
      ],
      "properties": {
        "is_oa": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "oa_status": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 128
        },
        "oa_url": {
          "$ref": "#/$defs/url"
        }
      }
    },
    "openalex_candidate": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "rank",
        "work_id",
        "title",
        "doi_url",
        "publication_year",
        "open_access",
        "primary_location",
        "best_oa_location",
        "locations"
      ],
      "properties": {
        "rank": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10
        },
        "work_id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "title": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 8192
        },
        "doi_url": {
          "$ref": "#/$defs/url"
        },
        "publication_year": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 1,
          "maximum": 9999
        },
        "open_access": {
          "anyOf": [
            {
              "$ref": "#/$defs/open_access"
            },
            {
              "type": "null"
            }
          ]
        },
        "primary_location": {
          "anyOf": [
            {
              "$ref": "#/$defs/openalex_location"
            },
            {
              "type": "null"
            }
          ]
        },
        "best_oa_location": {
          "anyOf": [
            {
              "$ref": "#/$defs/openalex_location"
            },
            {
              "type": "null"
            }
          ]
        },
        "locations": {
          "type": "array",
          "maxItems": 32,
          "items": {
            "$ref": "#/$defs/openalex_location"
          }
        }
      }
    },
    "crossref_result": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "provider",
        "scope",
        "query",
        "searched_at",
        "discovery_only",
        "provider_total_results",
        "results"
      ],
      "properties": {
        "provider": {
          "const": "crossref"
        },
        "scope": {
          "const": "scholarly_metadata"
        },
        "query": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4096
        },
        "searched_at": {
          "type": "string",
          "format": "date-time",
          "maxLength": 64
        },
        "discovery_only": {
          "const": true
        },
        "provider_total_results": {
          "$ref": "#/$defs/integer_count"
        },
        "results": {
          "type": "array",
          "maxItems": 10,
          "items": {
            "$ref": "#/$defs/crossref_candidate"
          }
        }
      }
    },
    "openalex_result": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "provider",
        "scope",
        "query",
        "searched_at",
        "discovery_only",
        "provider_total_results",
        "results"
      ],
      "properties": {
        "provider": {
          "const": "openalex"
        },
        "scope": {
          "const": "scholarly_metadata"
        },
        "query": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4096
        },
        "searched_at": {
          "type": "string",
          "format": "date-time",
          "maxLength": 64
        },
        "discovery_only": {
          "const": true
        },
        "provider_total_results": {
          "$ref": "#/$defs/integer_count"
        },
        "results": {
          "type": "array",
          "maxItems": 10,
          "items": {
            "$ref": "#/$defs/openalex_candidate"
          }
        }
      }
    },
    "scholar_error_details": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "provider",
        "http_status",
        "reason",
        "observed_requests",
        "observed_responses",
        "response_transfer_bytes",
        "response_decoded_bytes",
        "quota_source",
        "remaining_microusd",
        "reset_at",
        "retry_after_seconds"
      ],
      "properties": {
        "provider": {
          "enum": [
            "crossref",
            "openalex"
          ]
        },
        "http_status": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 100,
          "maximum": 599
        },
        "reason": {
          "enum": [
            "invalid_arguments",
            "local_quota_exhausted",
            "remote_quota_exhausted",
            "http_forbidden",
            "rate_limited",
            "auth_required",
            "unexpected_redirect",
            "http_error",
            "transport_unavailable",
            "invalid_provider_response",
            "response_limit",
            "deadline",
            "cancelled",
            "quota_policy_changed"
          ]
        },
        "observed_requests": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 1
        },
        "observed_responses": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 1
        },
        "response_transfer_bytes": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "response_decoded_bytes": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "quota_source": {
          "enum": [
            "local",
            "remote",
            "both",
            null
          ]
        },
        "remaining_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "reset_at": {
          "type": [
            "string",
            "null"
          ],
          "format": "date-time",
          "maxLength": 64
        },
        "retry_after_seconds": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 172800
        }
      }
    },
    "scholarly_attempt": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "provider",
        "endpoint_id",
        "http_request_count",
        "http_response_count",
        "http_status",
        "response_transfer_bytes",
        "response_decoded_bytes",
        "duration_ms"
      ],
      "properties": {
        "provider": {
          "enum": [
            "crossref",
            "openalex"
          ]
        },
        "endpoint_id": {
          "enum": [
            "crossref_works_public",
            "openalex_works_anonymous"
          ]
        },
        "http_request_count": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 1
        },
        "http_response_count": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 1
        },
        "http_status": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 100,
          "maximum": 599
        },
        "response_transfer_bytes": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "response_decoded_bytes": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "duration_ms": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        }
      }
    },
    "quota_observation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "owner_scope",
        "reservation_id",
        "local_utc_bucket",
        "reserved_microusd",
        "local_remaining_microusd",
        "provider_reported_remaining_microusd",
        "provider_reported_cost_microusd",
        "effective_min_interval_ms",
        "reset_at",
        "retry_after_seconds",
        "admission_blocked"
      ],
      "properties": {
        "owner_scope": {
          "const": "executor_local"
        },
        "reservation_id": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 256
        },
        "local_utc_bucket": {
          "type": [
            "string",
            "null"
          ],
          "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
        },
        "reserved_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "local_remaining_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "provider_reported_remaining_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "provider_reported_cost_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "effective_min_interval_ms": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "reset_at": {
          "type": [
            "string",
            "null"
          ],
          "format": "date-time",
          "maxLength": 64
        },
        "retry_after_seconds": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 172800
        },
        "admission_blocked": {
          "type": "boolean"
        }
      }
    },
    "remote_header_value": {
      "anyOf": [
        {
          "type": "null"
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "capture",
            "raw"
          ],
          "properties": {
            "capture": {
              "enum": [
                "single",
                "invalid"
              ]
            },
            "raw": {
              "type": [
                "string",
                "null"
              ],
              "maxLength": 128,
              "pattern": "^[ -~]*$"
            }
          },
          "oneOf": [
            {
              "properties": {
                "capture": {
                  "const": "single"
                },
                "raw": {
                  "type": "string",
                  "minLength": 1
                }
              }
            },
            {
              "properties": {
                "capture": {
                  "const": "invalid"
                },
                "raw": {
                  "type": "null"
                }
              }
            }
          ]
        }
      ]
    },
    "worker_provider_limits": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "crossref_rate_limit",
        "crossref_rate_interval",
        "crossref_concurrency_limit",
        "openalex_limit_usd",
        "openalex_remaining_usd",
        "openalex_cost_usd",
        "openalex_limit_credits",
        "openalex_remaining_credits",
        "openalex_cost_credits",
        "openalex_reset_seconds",
        "retry_after"
      ],
      "properties": {
        "crossref_rate_limit": {
          "$ref": "#/$defs/remote_header_value"
        },
        "crossref_rate_interval": {
          "$ref": "#/$defs/remote_header_value"
        },
        "crossref_concurrency_limit": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_limit_usd": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_remaining_usd": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_cost_usd": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_limit_credits": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_remaining_credits": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_cost_credits": {
          "$ref": "#/$defs/remote_header_value"
        },
        "openalex_reset_seconds": {
          "$ref": "#/$defs/remote_header_value"
        },
        "retry_after": {
          "$ref": "#/$defs/remote_header_value"
        }
      }
    },
    "provider_limit_observation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "rate_limit_requests",
        "rate_interval_ms",
        "concurrency_limit",
        "budget_limit_microusd",
        "remaining_microusd",
        "cost_microusd",
        "credit_limit",
        "remaining_credits",
        "cost_credits",
        "currency",
        "credit_unit",
        "reset_at",
        "retry_after_seconds",
        "missing_fields",
        "invalid_fields",
        "reset_after_seconds"
      ],
      "properties": {
        "rate_limit_requests": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "rate_interval_ms": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "concurrency_limit": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "budget_limit_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "remaining_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "cost_microusd": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "credit_limit": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "remaining_credits": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "cost_credits": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "currency": {
          "enum": [
            "USD",
            null
          ]
        },
        "credit_unit": {
          "enum": [
            "openalex_credit",
            null
          ]
        },
        "reset_at": {
          "type": [
            "string",
            "null"
          ],
          "format": "date-time",
          "maxLength": 64
        },
        "retry_after_seconds": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 172800
        },
        "missing_fields": {
          "type": "array",
          "maxItems": 11,
          "uniqueItems": true,
          "items": {
            "enum": [
              "crossref_rate_limit",
              "crossref_rate_interval",
              "crossref_concurrency_limit",
              "openalex_limit_usd",
              "openalex_remaining_usd",
              "openalex_cost_usd",
              "openalex_limit_credits",
              "openalex_remaining_credits",
              "openalex_cost_credits",
              "openalex_reset_seconds",
              "retry_after"
            ]
          }
        },
        "invalid_fields": {
          "type": "array",
          "maxItems": 11,
          "uniqueItems": true,
          "items": {
            "enum": [
              "crossref_rate_limit",
              "crossref_rate_interval",
              "crossref_concurrency_limit",
              "openalex_limit_usd",
              "openalex_remaining_usd",
              "openalex_cost_usd",
              "openalex_limit_credits",
              "openalex_remaining_credits",
              "openalex_cost_credits",
              "openalex_reset_seconds",
              "retry_after"
            ]
          }
        },
        "reset_after_seconds": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0,
          "maximum": 172800
        }
      }
    },
    "worker_scholarly_observations": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "scholarly_attempt",
        "provider_limits"
      ],
      "properties": {
        "scholarly_attempt": {
          "$ref": "#/$defs/scholarly_attempt"
        },
        "provider_limits": {
          "$ref": "#/$defs/worker_provider_limits"
        }
      }
    },
    "executor_scholarly_observations": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "scholarly_attempt",
        "quota",
        "provider_limits"
      ],
      "properties": {
        "scholarly_attempt": {
          "$ref": "#/$defs/scholarly_attempt"
        },
        "quota": {
          "$ref": "#/$defs/quota_observation"
        },
        "provider_limits": {
          "$ref": "#/$defs/provider_limit_observation"
        }
      }
    }
  }
}
```

The root selects the appropriate result definition by the resolved tool.
Both prepared and failed scholarly WorkerResponses require the same closed
worker_scholarly_observations: scholarly_attempt plus provider_limits. The
worker transports bounded remote header facts; the parent alone decodes and
validates them, then builds executor_scholarly_observations with a parsed
provider_limits projection and its own authoritative quota ledger. A worker
cannot supply that parent projection, local balances, reservations, grants or
admission decisions. Unknown HTTP request counts remain null when DNS/transport/
process loss prevents observation. The
same definition's output_schema points to that closed payload, never a worker
or final-result envelope. Bindings narrow limits and allowed tool names.

### Remote limit capture and parent decoding

provider_limits is mandatory on prepared and failed worker observations, even
for HTTP 200, malformed metadata, 403/429 and transport failure. Each of the
11 fields in worker_provider_limits is required and uses remote_header_value:
null means no applicable observed header; {capture:"single",raw:<string>}
means exactly one captured value; {capture:"invalid",raw:null} means capture
was rejected. Empty, duplicate (even equal), non-ASCII/control-bearing or
>128-byte values are rejected captures; never merge, truncate or log them.
A single value is 1..128 printable ASCII bytes, copied without interpretation.
The serialized worker_provider_limits object is <=8 KiB, within the unchanged
512 KiB observation/response envelope. No arbitrary header map or body text.

Header names are matched case-insensitively against this fixed allowlist, using
individual raw entries before any library comma-joining. The worker only
captures/sanitizes these transport facts; it does not parse quantities or make
quota decisions. Unit meanings below are pinned parent decoder rules.

| Worker field | Exact source header | Parent meaning |
| --- | --- | --- |
| crossref_rate_limit | x-rate-limit-limit | Requests per advertised interval |
| crossref_rate_interval | x-rate-limit-interval | Decimal seconds with literal s suffix |
| crossref_concurrency_limit | x-concurrency-limit | Concurrent requests |
| openalex_limit_usd | x-ratelimit-limit-usd | Reported USD-denominated budget ceiling |
| openalex_remaining_usd | x-ratelimit-remaining-usd | Reported USD-denominated remainder |
| openalex_cost_usd | x-ratelimit-cost-usd | Reported USD-denominated query consumption |
| openalex_limit_credits | x-ratelimit-limit | OpenAlex credit budget, not requests/s |
| openalex_remaining_credits | x-ratelimit-remaining | OpenAlex credit remainder |
| openalex_cost_credits | x-ratelimit-credits-used | OpenAlex credits used by this query |
| openalex_reset_seconds | x-ratelimit-reset | Pinned delta seconds until reported reset |
| retry_after | retry-after | Delta seconds or strict IMF-fixdate |

Only Crossref's three fields plus retry_after apply to Crossref; only OpenAlex's
seven fields plus retry_after apply to OpenAlex. Inapplicable fields must be
null. A supplied cross-provider fact, local balance/reservation/grant/admission
field, unknown key or invalid capture shape is WORKER_PROTOCOL_ERROR. Rejection
does not refund known/uncertain dispatch or erase parent-observed effects.
Header syntax that is malformed within a valid capture is remote evidence to
classify, not a reason to replace an actual 403/429 with a different HTTP fact.

The parent validates identity, schema, capture shape and byte limits, including
every raw byte in 0x20..0x7E, before parsing on either worker phase.
It trims only outer ASCII spaces, then uses
these bounded decoders; it never evaluates text, accepts NaN/Infinity, uses
binary floats or guesses a different unit/epoch:

- Counts are unsigned base-10 integers (0 or a nonzero leading digit followed
  by digits), <=2^53-1. A known zero remains zero. Negative/exponent/comma values
  are invalid. A positive Crossref interval uses decimal seconds with <=3
  fractional digits and literal s, converted exactly to integer milliseconds.
  Zero interval is invalid; interval >172800s is invalid, not clamped down.
- USD quantities use the same unsigned decimal grammar with <=6 fractional
  digits, converted exactly to integer microUSD <=2^53-1. Credits stay separate
  integer units; no credit-to-USD conversion or request-rate inference. Parent
  currency=USD / credit_unit=openalex_credit only labels valid mapped facts;
  these are reported quota units, never verified monetary billing.
- OpenAlex reset is an unsigned delta in 0..172800 seconds, preserved as
  reset_after_seconds. The parent derives a conservative reset_at from its
  trusted receipt UTC plus that delta, with no worker clock authority. It does
  not treat this header as an epoch, replenish the local UTC bucket, or replay.
  A provider format change is invalid evidence pending reviewed decoder change.
- Retry-After is unsigned integer seconds in 0..172800 or strict English
  IMF-fixdate with matching weekday and literal GMT. The parent validates the
  calendar and computes a nonnegative ceiling delay from trusted receipt UTC;
  a past valid date gives zero. A larger/overflowing delay is invalid, never
  reduced to the cap. Waiting uses the parent's monotonic clock/deadline.

The parent emits only the closed provider_limit_observation projection: parsed
remote rate/interval/concurrency, USD and credit limit/remaining/cost, explicit
units, reset delta/derived time and Retry-After, plus ordered missing_fields and
invalid_fields. Only applicable unobserved fields enter missing_fields; rejected
captures or invalid syntax/range enter invalid_fields. Arrays are disjoint in
the schema field order. Their corresponding parsed values are null. A valid
zero is neither missing nor invalid. Partial valid facts survive other invalid
fields; no raw header values enter the public observation/error/diagnostic path.

executor_scholarly_observations requires scholarly_attempt, this parsed
provider_limits and the existing parent-owned quota. quota's provider_reported
remaining/cost fields reflect this attempt's validated USD facts, or null when
missing/invalid; never relabel an older remote observation as current. The local
ledger/effective pace/block can retain prior restrictions independently.
Preflight without a worker uses null remote values and marks applicable fields missing. If output is lost
or a process cannot report, facts remain unknown; never invent a response or
header. For a valid failed response, retain the actual HTTP status, counts,
bytes and duration alongside these observations. Header capture should precede
body parsing so a parse/size failure can retain known HTTP and limit facts.
No changes to error terminals, payloads, Storage rights or lifecycle ownership.

## 15. Provider admission, free quotas and explicit failures

Provider limits are parent-held within each owned executor and shared by all
its bound runs. They do not control unrelated executors/hosts or the entire
upstream IP/account quota. Binding/executor metadata includes that local
ownership boundary. Workers cannot reset counters or acquire credentials.
No paid tier, automatic key/account creation or quota escalation is allowed.

| Provider | Request and local admission policy | Remote evidence/policy |
| --- | --- | --- |
| Crossref | One public list GET, one in flight across this executor; wait >=1s after previous request settles before next dispatch | Honor response-header rate/interval/concurrency only when they narrow; default never exceeds one list call/s |
| OpenAlex | One anonymous keyword GET; one owned request in flight, >=1s between settled requests; reserve 1000 integer microUSD from local <=100000 per UTC day plus narrower lineage limits | Current anonymous free allowance 0.10 USD/day; reported keyword valuation 0.001 USD/call; observed remote remaining/reset/cost may narrow admission |

Crossref pacing permit is held through worker/HTTP settlement and cleanup, so
delayed process startup cannot bunch requests after an earlier launch-time
permit. OpenAlex also uses a conservative local serial >=1s dispatch interval; this
does not claim that provider-wide traffic is controlled. A slower valid rate header lengthens the next interval; a faster header
never relaxes the 1/s default. Serial execution remains even if a header offers
more concurrency. Budget waiting consumes deadline and can end with known
nondispatch outcome; bounded pending admission prevents an unbounded queue.

OpenAlex local quota allows at most 100 such keyword dispatch reservations per
UTC day absent tighter policy; this is a conservative executor ceiling, not
assurance the remote anonymous budget remains. Use exact integer microUSD for
local accounting, not binary-float subtraction. Bind the reservation to the
tool action/attempt. After dispatch or uncertain dispatch, retain consumption
pessimistically even when no reply arrives; refund only confirmed nondispatch.
No retry/new worker is granted by a remaining balance. A new UTC date changes
the local bucket without replaying old actions or replenishing a lineage ledger.
Process restart must not claim a fresh full remote allowance; retain a trusted
owner quota checkpoint or mark remote remainder unknown and fail closed pending
explicit host admission policy. This is quota metadata, not a second source store
or worker-owned persistence.

Parent-decoded provider_limits facts from either worker phase describe the
remote observation. A valid positive Crossref rate/interval pair narrows the
minimum interval to at least ceil(rate_interval_ms/rate_limit_requests), with
the existing >=1s/settlement rule retained. Zero request or concurrency allowance
blocks admission; positive concurrency never increases the serial ceiling.
Retry-After also delays a later explicit action, including after HTTP 200.
A missing/invalid component cannot produce a faster interval or remove an
existing delay/block. Only the parent updates its authoritative quota projection.

Remote remaining below one query blocks subsequent local admission; exhausted
local ledger returns SCHOLAR_QUOTA_EXHAUSTED before network. Valid USD budget
limits/remainders only narrow the configured/local/lineage ceilings. Credit
counts are separate: known zero blocks, and a valid remaining/cost pair can
narrow admission, but credits never become USD or requests/s by inference.
The effective query reservation never falls below the configured 1000 microUSD.
If observed USD consumption is higher, charge only the excess above the existing
reservation exactly once to that action/attempt, narrow/stop future work and
surface the policy discrepancy; do not double-charge or refund on a lower cost.
Provider balances never overwrite local_remaining_microusd or create new grants.

Missing and malformed evidence are distinct unknowns, not invented zero. Retain
prior restrictive bounds and pessimistic dispatch consumption; invalid/missing
facts cannot enlarge a balance, relax pacing, clear a block or supply billing.
Local and remote observed resets are distinct. Receipt of 429 stops this action
and latches a local provider block even when all limit/reset headers are absent
or malformed. Retry-After/reset can bound a later explicit action's earliest
admission, but no automatic execution follows a timer or a local/remote reset.
Unknown reset requires explicit host reconciliation. 403 does not automatically
establish quota, paywall or authentication cause. Preserve the actual HTTP facts
on either failure while projecting any valid, missing and invalid limit facts.

Error.details uses a closed scholarly safe record:
provider,http_status,reason,observed_requests,observed_responses,
response_transfer_bytes,response_decoded_bytes,quota_source,
remaining_microusd,reset_at,retry_after_seconds; unavailable values null.
reason is an allowlisted classification, never response-body/traceback text.
Worker Error.details quota_source, remaining_microusd, reset_at and
retry_after_seconds must be null: workers cannot supply parent-decoded quota
or delay facts through the error path either. The parent fills final safe error
details from its parsed remote observation and authoritative ledger, retaining
the actual HTTP status/classification. A nonnull worker value in those fields
is a protocol violation, not admission evidence.
observed_effect_state retains actual dispatch/response observation; error
delivery never authorizes source/metadata replay. The inherited error code/
message/byte limits and execution terminals remain the common v1 contract.

| Observation | Error / terminal / worker exit |
| --- | --- |
| Unknown public field, blank query or encoded URL over cap | INVALID_ARGUMENT / validation_failed / 2; no request |
| Local free quota exhausted or remote observed remainder insufficient | SCHOLAR_QUOTA_EXHAUSTED / limit_exhausted / 4; no new request |
| HTTP 403 | SCHOLAR_HTTP_FORBIDDEN / failed / 3, http_status=403 |
| HTTP 429 or explicit provider quota denial | SCHOLAR_RATE_LIMITED or SCHOLAR_QUOTA_EXHAUSTED / limit_exhausted / 4, actual http_status preserved |
| HTTP 401 | SCHOLAR_AUTH_UNSUPPORTED / failed / 3; no key acquisition |
| Unexpected 3xx or other error HTTP | SCHOLAR_UNEXPECTED_REDIRECT or SCHOLAR_HTTP_ERROR / failed / 3; status retained |
| DNS/TLS/connect/read transport failure or unavailable service | SCHOLAR_UNAVAILABLE / failed / 3; request/effect counts unknown where needed |
| Malformed/non-JSON/UTF-8/schema/identity mismatch | SCHOLAR_PROTOCOL_ERROR / failed / 3; no successful metadata |
| Transfer/decoded/depth/result-array/public-envelope cap exceeded | SCHOLAR_RESPONSE_LIMIT / limit_exhausted / 4; no partial success |
| Work deadline/cancel | DEADLINE_EXCEEDED or CANCELLED / timed_out or cancelled / 5 or 6 |

The parent can return the corresponding preflight/nondispatch ToolExecutionResult
without worker when local admission fails after intent. Python task cancellation
still cleans up and re-raises; explicit engine cancellation returns an outcome.
For failed work prepared=null/error populated; for a valid result error=null.
A keyword cost/credit observation belongs to bounded observations, not a claimed
monetary bill: common usage.monetary_cost stays unknown absent billing evidence.
Metadata has persistence.required=false,operation_id=null,
commit_state=not_applicable,receipt=null. Public discovery success still needs
complete intent/outcome recording and cleanup.

Quota restart/checkpoint authority is a trusted executor/host concern. Existing
scoped Storage may persist the owner's quota metadata through a separately
authorized host context; scholarly worker/tool bindings gain no publication
rights. If no such admission owner exists, fail closed across restart rather
than claim provider/account accounting. No new shared Storage API is requested.

Primary access/rate/cost sources and immutable anonymous observations remain in
the [research report](../../research/free-search-fetch.md). Three 200 responses in one run
support casual access only, not sustained reliability or general-web
coverage. Service/linked-paper licenses are distinct from client package license.

## 16. Revised discovery acceptance gates

These checks are future real implementation/verification work, not performed
by this design revision. Keep all historical failed observations intact.

1. Repeat representative general/technical/domain and all EBD cases across
   separated runs/hosts for Yahoo; record exact successful/unavailable counts.
   Test Yahoo raw redirect extraction with query ampersands, literal plus,
   encoded plus/%26, percent-encoded paths and distinct query targets.
   Compare raw expected destination, returned URL and actual request; no hidden
   merge/fallback or declaration of sustained uptime from one pass.
2. Corrected Google stays disabled until integrated controlled and live
   query-bearing wrapper tests pass with raw-to-result-to-fetch fidelity,
   malformed/duplicate/ambiguous wrapper rejection and one decode only. Gate
   artifact pins adapter/definition/config version. Availability is a separate
   repeated gate; parser success does not prove it. A disabled backend is
   reported without an attempted-call count or request.
3. Register the two scholar@1 schemas and verify immutable provider/endpoint/
   tool identity, unknown field/filter/key denial and literal query/quoted
   phrase/Unicode/plus transport equality. One network request, no redirects/
   pages/retry/cross-provider substitution. Validate exact count/rank/null/date/
   DOI/work/publisher/OA projection and oversized/malformed/empty cases.
4. Verify Crossref serial >=1s pacing, header narrowing and cancellation while
   waiting; OpenAlex local/remote exhaustion, 429 stop, uncertain dispatch
   accounting, midnight/restart ownership and no paid/key escalation. Demonstrate
   local counters do not claim provider-wide authority. Validate actual error
   status/caps/cleanup with the same recorded helper and real Storage events.
   Run the provider-limit protocol vector below on both prepared and failed
   observations; validate the parent's closed projection and error enrichment.
5. Measure metadata relevance separately from HTTP availability, including the
   known unrelated OpenAlex unquoted broad result. Fetch returned accessible
   publisher/institutional/OA targets and read their saved immutable slices.
   Preserve 403 or other full-text failure; metadata/abstract/snippet never
   substitutes for source evidence or a sourced final report.
6. All existing v1 encoded/PDF-memory/Windows descendant/Storage uncertainty/
   standalone/baseline gates remain. Five registered tools share that executor
   and recording path; no mock or direct API baseline bypass is a deliverable.

### Provider-limit protocol acceptance vector (future)

This is one required vector family for the eventual real worker/parent protocol;
it has not been executed here and is not research evidence or runnable acceptance.
Use the registered recorded helper and real lifecycle/storage wiring. Controlled
HTTP facts below exercise fault handling; the separate live provider/source gates
above still apply. All unspecified applicable headers are missing (null capture),
inapplicable fields are null, and identities/HTTP counts remain the actual ones.

| Branch and supplied remote facts | Required parent result/admission behavior |
| --- | --- |
| Crossref HTTP 200 with valid metadata, rate=1, interval=3s, concurrency=1, Retry-After=5 | Worker prepared observations include the same closed limit capture as failure. Parent projects 1/3000ms/1 and 5 seconds, retains >=1s/serial baseline, and delays later explicit dispatch >=3s after settlement and until the 5s Retry-After boundary. Current discovery can succeed after recording/cleanup; no automatic follow-up. |
| OpenAlex HTTP 200 with valid metadata, remaining-usd=0, cost-usd=0.002, remaining credits=0, used credits=20, reset=60 | Parent projects known zero, 2000 microUSD, USD/openalex_credit and reset delta 60; this is not missing/invalid/billing. Charge the reserved 1000 plus 1000 excess once. Complete the current discovery, block further admission, and never refill the local ledger or replay at remote reset. |
| Failed HTTP 429 with remaining-usd=0, malformed single Retry-After=bogus, missing cost/reset; repeat as 403 with duplicate cost header rejected capture | Actual 429/403 status, request/response count=1 and known sizes remain alongside parsed observations. Zero stays zero; malformed fields enter invalid_fields and absent fields missing_fields, their quantities null. 429 latches a block with unknown cooldown; no fabricated retry time/cost. 403 retains its failure classification and any valid narrowing facts. |
| Either phase includes worker observations.quota/local_remaining_microusd, a provider_limits reservation/grant/admission field, or nonnull worker Error.details quota_source/remaining_microusd/reset_at/retry_after_seconds | Parent rejects the local-authority forgery before accepting payload/public output. WORKER_PROTOCOL_ERROR; no success, new grant, refund or overwritten local ledger. Keep known/uncertain dispatch consumption and parent-observed effects; no replay. |

Also check exact closed projected keys, single/invalid capture shape, unobserved
null versus valid raw 0, cross-provider fields, bounded ASCII/duplicates/8 KiB,
integer/decimal/date overflow, and rejection of a worker-supplied parsed parent
projection. These are protocol/semantic tests pending implementation, not passed
by JSON parsing or the prior anonymous HTTP 200 samples.
