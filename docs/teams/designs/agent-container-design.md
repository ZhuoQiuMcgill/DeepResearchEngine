# Agent Container design aligned to platform contract v1

Status: complete owned design for shared review; revision agent-container-v1-r3, October 1, 2026 (America/Toronto). Normative shared authority: [platform-contract-v1.md](../platform-contract-v1.md); assignment: [missions.md](../missions.md); contribution rules: [CONTRIBUTING.md](../../../CONTRIBUTING.md). This revision replaces the team's earlier competing interface proposals. It is documentation, not implemented functionality or authorization to build.

## 1. Ownership and conformance rules

Container owns Runtime, RecordedToolAction, agent/model schemas and validation, context assembly, limits, native provider protocols and continuation, and canonical agent/model/tool activity. Connections supplies composition, configuration, grants, identity service, lineage ledger, admission callers and resource leases. Toolset owns catalog, fixed-argv subprocesses, private workers, prepared-output validation and mediated Storage commit/read. Storage owns scoped persistence, publication/recovery and event receipts. Providers request tools; they never execute them. The runtime contains no EBD strategy, report planner or scheduler.

Current editable paths are this design and reports/agent-container-status.md only. After a directly authorized phase transition, the whole module assignment is src/ebd/agent/, src/ebd/providers/, tests/agent/ and tests/providers/. PM owns shared contracts, entry-point composition, integration, dependencies and Git. Use shared uv-managed Python 3.11.15, .python-version, pyproject.toml, uv.lock and uv run --locked. This team's implementation does not begin on a draft's acceptance alone.

All schemas below are closed records: every listed R field is required, O fields may be omitted only as stated, nullable fields use explicit null, and unknown execution/security fields fail. Defaulted definition fields are materialized before digesting/admission. Wire/event compatibility is integer schema_version=1; it is never a string or a second schema-major field. Definition, tool, extraction and native-codec revisions are independent. JSON is UTF-8, finite, unique-key, depth <=32 and byte-bounded. IDs are nonempty opaque strings issued by their specified owner; IDs/refs/serialized descriptors never grant authority. Digests use the PM-owned canonical-content codec and SHA-256; changing that codec is a contract decision, not independent per-module serialization.

Shared imported types: ExecutionMetadata/ExecutionContext, BindingSet, JsonValue/JsonSchema, NamedRef, ToolIdentity, scoped Storage refs/receipts, EngineError, EventReceipt, CleanupReport and lineage/resource protocols. This document defines their required use and owned schemas without creating a second type package. Local schemas use JSON Schema Draft 2020-12 with only approved bundled references; validation cannot perform network $ref retrieval. Native schema support is separately capability-checked; translating a required constraint into a weaker one is forbidden.

## 2. Exact AgentDefinition and nested schemas

| AgentDefinition field | Required type and rule |
| --- | --- |
| schema_version | R integer literal 1 |
| agent_id | R registered reusable agent identity; execution run IDs are separate |
| definition_revision | R nonempty immutable revision string |
| definition_digest | R lowercase SHA-256 of canonical materialized definition excluding this field; mismatches reject admission |
| instructions | R nonempty UTF-8 string, <=32 KiB; runtime research policy is appended in a control role, never derived from source text |
| input_schema | R valid local JsonSchema |
| output_contract | R OutputContract below |
| model_ref, profile_ref | R NamedRef {name, revision}; exact non-secret configured model and protocol profile references |
| model_settings | R closed profile-validated settings object, default {}; no arbitrary HTTP extra fields |
| required_capabilities | R unique list of declared capability keys, default []; unknown/unsupported cannot satisfy a requirement |
| allowed_tools | R ordered unique ToolAllowance list, default []; names/revisions must resolve through bound catalog |
| storage_requests | R unique requested scope/operation descriptors, default []; binder intersects grants, requests are not authority |
| delegation_requests | R named destination/rule references, default []; only bound AgentInvoker can invoke |
| context_policy | R ContextPolicy below |
| limits | R ExecutionLimits below; effective values can only narrow through bindings/lineage |
| error_policy | R ErrorPolicy below |
| metadata | R bounded application JsonObject, default {}, <=16 KiB; no core mission requirement or secrets |

NamedRef is exactly {name:string, revision:string}. ToolAllowance is {tool:ToolIdentity, argument_constraints:JsonSchema|null}; ToolIdentity is {name:string, revision:string}. Additional constraints narrow the registered input schema. They never introduce argv, an executable, scope selection, credentials or reserved worker control fields. Storage/delegation requests use Connections' shared descriptors; no free-form granting scope string is accepted.

| OutputContract field | Type/rule |
| --- | --- |
| mode | R text or json |
| media_type | R text/plain or text/markdown for text, application/json for json; explicit artifact media; default text/plain or application/json by mode |
| schema | R JsonSchema; text is validated as a JSON string, json as its parsed JsonValue |
| native_enforcement | R disabled, optional or required; default optional |
| max_bytes | R positive integer <= effective final-output cap; counts exact UTF-8 text bytes for text or canonical JSON bytes for json; retained raw final content is independently bounded |
| delivery | R inline_or_artifact or artifact; default inline_or_artifact; artifacts contain the same validated value |

Output success requires parsing when needed and complete local schema validation. Native JSON syntax or provider schema constraints do not replace validation, refusal/incompletion handling or byte bounds. Oversized output is an error, not unchecked success via a path. Permitted large values within max_bytes can be artifact-backed; a reference alone does not authorize a recipient to read it.

ContextPolicy is exactly {sources:ContextSource[], overflow:fail|drop_optional_groups, max_source_bytes:int, max_tool_context_bytes:int}. Defaults are sources=[], overflow=fail, max_source_bytes=262144, max_tool_context_bytes=65536. ContextSource is a tagged union with an explicit required boolean:

| kind | Closed body |
| --- | --- |
| state | scope_ref, key, version:positive integer or latest_at_start, required |
| artifact | artifact_ref, byte_range:{start,end_exclusive}, max_bytes, required |
| snapshot | snapshot_ref, range:shared lines/pages range, max_text_bytes, continuation:string|null, required |

The task input is always required, separate from sources. Resolve latest_at_start once and record the actual version; subsequent restoration reads that exact version. Definition order is context order. History is adapter-native continuation, not an alternative generic text-history store. Sources and their approved ranges must pass current grants, immutable-version/readiness and cumulative bounds. Snapshot ranges and continuation retain Storage's one-based, end-exclusive physical-page/line semantics and zero-based UTF-8 offsets. Empty units and long-unit cursors are not silently renumbered or clamped.

ErrorPolicy is exactly {recoverable_tool_errors:return_to_model|terminate, unauthorized_tool:terminate, invalid_arguments:terminate, max_model_retries:int, max_repairs:int}. Defaults are return_to_model, terminate, terminate, 0, 0. An explicit permitted retry remains subordinate to the same limits and effect/uncertainty rules. No policy authorizes retry after ambiguous external effect or missing outcome recording. Repair changes the request, so it creates a new logical model action linked to the validation failure.

These numeric defaults are proposed complete runtime defaults within v1's smaller resource envelope, not measured performance or provider maximums:

| ExecutionLimits field | Default and interpretation |
| --- | --- |
| max_run_seconds / max_model_seconds / max_tool_seconds | 120 / 45 / 30; positive finite; inherited absolute deadline wins |
| max_model_calls / max_tool_calls / max_tool_attempts | 8 / 12 / 12; model dispatch reservations include retries/repairs; emitted tool calls and actual worker attempts are separately counted |
| max_output_tokens_per_call / max_context_tokens | 4096 / 32768; profile-compatible request bound; context measurement quality remains explicit |
| max_task_input_bytes / max_model_request_bytes | 65536 / 1048576; measure actual UTF-8 rendered body, schemas and native history included |
| max_model_response_bytes / max_continuation_bytes | 1048576 / 1048576; whole native body and retained codec payload, not just visible text |
| max_final_output_bytes / max_public_result_bytes | 65536 / 524288; output value and whole result envelope respectively |
| max_cleanup_seconds / max_record_cleanup_seconds | 5 / 5; no new work during either grace; session shutdown may reduce them |
| token_budget | null by default; optional {max_total_tokens:int, enforcement:strict|advisory}; strict requires verified sufficient accounting/counting |

Every effective definition supplies these fields after defaults. Execution limits intersect caller policy, binding limits, shared lineage quota and selected provider ceilings. V1 Toolset limits remain authoritative for private stdin/stdout, retained original/text/index/provenance, stderr and parser resources; Container does not override them upward. Child agents cannot regain quota by creating a fresh run.

Illustrative definition payload: reference/digest placeholders must be substituted from actual registration/computation. It is a schema example, not a configured agent or execution evidence.

```json
{
  "schema_version": 1,
  "agent_id": "<registered-agent-id>",
  "definition_revision": "<immutable-revision>",
  "definition_digest": "<computed-sha256>",
  "instructions": "Answer the supplied task using permitted source tools.",
  "input_schema": {"type": "object", "properties": {"task": {"type": "string", "minLength": 1}}, "required": ["task"], "additionalProperties": false},
  "output_contract": {"mode": "json", "media_type": "application/json", "schema": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": false}, "native_enforcement": "optional", "max_bytes": 65536, "delivery": "inline_or_artifact"},
  "model_ref": {"name": "<configured-model-name>", "revision": "<model-config-revision>"},
  "profile_ref": {"name": "<configured-profile-name>", "revision": "<profile-revision>"},
  "model_settings": {},
  "required_capabilities": ["function_tools"],
  "allowed_tools": [{"tool": {"name": "web.search", "revision": "<registered-tool-revision>"}, "argument_constraints": null}],
  "storage_requests": [],
  "delegation_requests": [],
  "context_policy": {"sources": [], "overflow": "fail", "max_source_bytes": 262144, "max_tool_context_bytes": 65536},
  "limits": {
    "max_run_seconds": 120, "max_model_seconds": 45, "max_tool_seconds": 30,
    "max_model_calls": 8, "max_tool_calls": 12, "max_tool_attempts": 12,
    "max_output_tokens_per_call": 4096, "max_context_tokens": 32768,
    "max_task_input_bytes": 65536, "max_model_request_bytes": 1048576,
    "max_model_response_bytes": 1048576, "max_continuation_bytes": 1048576,
    "max_final_output_bytes": 65536, "max_public_result_bytes": 524288,
    "max_cleanup_seconds": 5, "max_record_cleanup_seconds": 5, "token_budget": null
  },
  "error_policy": {"recoverable_tool_errors": "return_to_model", "unauthorized_tool": "terminate", "invalid_arguments": "terminate", "max_model_retries": 0, "max_repairs": 0},
  "metadata": {}
}
```

## 3. ModelRequest, ModelResponse, continuation and request audit

ModelRequest is a closed serializable record with these required fields. Connections' live context is passed separately and must agree with its execution metadata.

Required imported execution metadata fields are context_kind, run_id, root_run_id, correlation_id, agent_id, definition_ref, action_id, attempt_id, parent_run_id, parent_action_id, parent_attempt_id, deadline_at_utc, depth, ancestry, binding_ref, policy_ref and bounded metadata. Nullable agent/definition and parent/attempt fields follow v1's agent/standalone and nondispatch rules; live grants, ledger, cancellation and leases are separate.

| Field | Exact shape/constraint |
| --- | --- |
| schema_version | integer 1 |
| model_ref, profile_ref, definition_ref | pinned shared references; definition_ref includes agent_id/revision/digest |
| execution | shared metadata: context_kind=agent, run/root/correlation IDs, agent/definition refs, logical action_id and mandatory attempt_id, parent run/action/attempt IDs, deadline_at_utc, binding/policy refs, depth/ancestry and safe metadata |
| step_index | nonnegative integer; initial generation is 0; increases for new model turns, not identical delivery retries |
| input_items | ordered InputItem list; initial task/context or new correlated tool results/repair feedback, never duplicated full history plus continuation |
| tools | ordered unique ModelToolSchema list restricted to effective registered function tools |
| output_contract | materialized OutputContract |
| settings | closed settings accepted by the exact bound provider/profile; no unknown flags |
| limits | effective remaining byte/count/time/context/token snapshot; authoritative live ledger remains separate |
| continuation | null for the initial request, otherwise matching ContinuationEnvelope |

InputItem is a tagged union: instruction {kind, text, purpose:definition|platform_search_policy}; task {kind, value:JsonValue}; context {kind, text, source_ref, source_version, locator, required}; tool_result {kind, provider_call_id, tool:ToolIdentity, status:execution terminal, result:JsonValue|null, error:EngineError|null, result_refs}; repair {kind, validation_id, safe_errors}. A failed tool result has error and no success result; successful JSON null is distinguished by status. Context locators use authoritative Storage spans. Required fields are present for their tag; other tags' fields are rejected.

ModelToolSchema is {tool:ToolIdentity, provider_name:string, description:string, input_schema:JsonSchema, native_strict:bool}. The provider-name map is immutable and bijective within the binding. Proposed internal naming is t_ plus the first 32 hex characters of the canonical ToolIdentity digest; detect any collision before admission. Names fit the selected endpoint's documented grammar; schemas/descriptions communicate the registered tool identity. Never infer a canonical tool from untrusted prose. The adapter cannot expose hosted search, shell, MCP, file-search or other provider tools through this array.

| ModelResponse field | Exact shape/constraint |
| --- | --- |
| schema_version | R integer 1 |
| execution, step_index | R match the request's action/attempt/run/profile and step |
| completion | R final, tool_calls, incomplete, refused or failed |
| content | R ordered public ContentPart list: {kind:text,text} or {kind:json,value}; native reasoning is excluded |
| raw_visible_text | R string|null; exact ordered final/intermediate provider-visible content without added separators or normalization; required for a final candidate in the selected text/JSON profiles |
| tool_calls | R ordered ToolCall list, empty except a complete callable response |
| native_finish_reason | R string or null; an unknown reason becomes an explicit unsupported protocol failure |
| usage | R UsageReport or null |
| provider_request_id, provider_response_id, reported_model_id | R nullable safe strings; missing means unknown |
| continuation | R matching envelope or null if no supported continuation is returned/needed |
| request_audit | R RenderedRequestAudit or null only when rendering never completed |
| error | R EngineError|null; required non-null for failed/refused/incomplete with safe causal detail |

ToolCall is exactly {provider_call_id:string, index:nonnegative int, provider_name:string, tool:ToolIdentity|null, arguments_json:string, arguments:JsonObject|null, argument_error:EngineError|null}. Preserve original argument strings and provider IDs, including index/order. Reject missing/duplicate IDs, malformed JSON, unknown functions, insufficient capability and schema/policy violations before any member of a batch runs. A native named-tool finish reason of stop can still mean tool_calls; interpret actual complete calls and the reason together. Incomplete/truncated call data never dispatches. Public text beside calls is intermediate, not a final answer.

ProviderSession.generate returns this domain outcome for anticipated HTTP/protocol/refusal/incomplete failures, not a second Result wrapper. ProviderFactory.open is an infrastructure operation returning Result[ProviderSession]. Unexpected defects and caller Python cancellation retain exception semantics after bounded cleanup. Adapter translation preserves native turn pairing; it does not execute a function or switch a model. HTTP/SDK automatic external retries are disabled; a runtime-approved retry has a new attempt and counted intent.

UsageReport is {input_tokens:int|null, output_tokens:int|null, total_tokens:int|null, cached_input_tokens:int|null, reasoning_output_tokens:int|null, completeness:complete|partial|unknown, source:provider|verified_local|estimate, measurement_ref:string|null}. All counts are nonnegative and nullable when unavailable. Completeness concerns authoritative primary input/output/total accounting for that attempt; nullable cache/reasoning breakdowns remain explicit. They are subsets/diagnostics of provider totals, not additional totals to double-add. Failure/interrupt usage is retained when reported. UsageAggregate contains known_subtotals, completeness, unknown_attempt_ids and per_attempt_usage_refs; a missing dispatched attempt makes whole-run totals partial/unknown, never fabricated zero. A run with no dispatch can truthfully have zero dispatch counters.

ContinuationEnvelope is exactly:

| Required field | Rule |
| --- | --- |
| schema_version, codec_id, codec_revision | integer 1 plus explicit owned native codec identity/revision |
| provider_kind, protocol, model_ref, profile_ref, actual_model_id | bind to exact selected configuration/endpoint protocol, not merely a compatible API family |
| run_id, agent_id, definition_digest, binding_digest | execution/configuration binding; saved state conveys no authority |
| step_index, payload_digest | native turn position and canonical retained-payload digest |
| pending_calls | ordered {provider_call_id,tool,index} list; each receives exactly one matching result before the next generation |
| payload | tagged {kind:memory,native:JsonValue} or {kind:artifact,ref:ArtifactRef}; memory form is live-run owned, artifact requires restricted approved persistence |
| persistence | prohibited or restricted; codec/profile policy controls allowed publication/load |
| expires_at | nullable UTC time for any provider/state expiry; expiration cannot be silently bypassed |

Native payload is adapter-private, strict JSON with required provider-supplied message/items retained in order. It never includes headers, credentials, client objects, cancellation handles or arbitrary Python serialization. Persist only supplied protocol material needed for continuation; do not request private reasoning, synthesize it or publish it as research text. Ordinary lifecycle payloads contain safe refs/digests, not native reasoning. Codec load checks provider/protocol/model/profile/run/definition/binding/expiry, current grants and bounds. A decoder that cannot preserve a required native field rejects the profile rather than reconstructing from visible text.

OpenAI stateless Responses retains replayable native output items, function calls and supplied encrypted reasoning, with original call_id on function_call_output. DeepSeek Chat retains required assistant messages/tool calls and full supplied reasoning_content when tools are carried, including turns without a call. Qwen3 follows its selected chat template's history policy, which omits historical thinking; do not apply DeepSeek replay universally. Full source findings/config mappings are in section 9.

RenderedRequestAudit is exactly {schema_version:1, provider_kind, protocol, requested_model_id, model_ref, profile_ref, adapter_revision, safe_endpoint_id, instruction_digest, platform_search_policy:string, function_tools:[{tool,provider_name,input_schema_digest}], safe_settings:JsonObject, request_body_digest, provider_request_id:string|null, provider_response_id:string|null, reported_model_id:string|null}. It is <=16 KiB. platform_search_policy is the fixed rendered control instruction, not arbitrary task/source text. request_body_digest hashes the body actually sent without auth headers; it cannot prove inaccessible provider internals. The policy is: Do not use internal, provider-hosted or implicit web search. Research only through registered platform function tools; fetch and read source evidence before citing it.

The adapter privately freezes/validates its rendered body before I/O and retains its safe audit by action/attempt even if transport fails. This is an internal rendering phase of the same provider generation, not another common helper or dispatch. It returns the audit with ModelResponse; Runtime records it in model.outcome, with permitted audit refs under normal authority when needed. On cancellation, its bounded already-created audit can be embedded in the owner outcome through record_cleanup; no new business artifact write is authorized. Future acceptance checks the transport body's digest and actual tool/policy surface against this record. Only documented provider controls may be added to an exact profile; there is no invented enable-search/disable-search flag, and disabling thinking is not disabling search.

Illustrative correlated response/result delta; symbolic IDs/refs stand for actual bound/provider values. This is not evidence of a call.

```json
{
  "schema_version": 1,
  "model_response_fragment": {
    "completion": "tool_calls",
    "tool_calls": [{"provider_call_id": "<provider-call-id>", "index": 0, "provider_name": "<mapped-function-name>", "tool": {"name": "web.fetch", "revision": "<registered-revision>"}, "arguments_json": "{\"url\":\"<source-url>\"}", "arguments": {"url": "<source-url>"}, "argument_error": null}],
    "usage": null,
    "continuation_ref": "<restricted-native-state-ref>"
  },
  "next_input_item": {"kind": "tool_result", "provider_call_id": "<provider-call-id>", "tool": {"name": "web.fetch", "revision": "<registered-revision>"}, "status": "succeeded", "result": {"snapshot_ref": "<store-qualified-ready-snapshot-ref>"}, "error": null, "result_refs": []}
}
```

## 4. Exact AgentResult and output lifetime

Runtime.execute returns one AgentResult domain outcome; it is not wrapped in Result. AgentResult is a closed record:

| Required field | Type/rule |
| --- | --- |
| schema_version | integer 1 |
| execution, definition_ref, admission_id | root-run metadata, pinned definition and known admission identity |
| status | succeeded, failed, validation_failed, limit_exhausted, timed_out or cancelled |
| start_state | not_started, started or unknown, based on agent-start receipt; not inferred from a timeout |
| output_delivery | none, inline or artifact |
| output | JsonValue|null; inline permits valid JSON null, artifact/none uses null |
| output_ref, raw_output_ref | nullable store-qualified ArtifactRef; required for succeeded output; text may share one ref |
| output_metadata | nullable {mode,media_type,byte_length,sha256,raw_media_type,raw_byte_length,raw_sha256}; agrees with receipts |
| output_publications | ordered {role:raw|validated, operation_id, artifact_ref:null|ArtifactRef, receipt:null|ArtifactReceipt, commit_state:not_committed|committed|unknown} list; records each actually admitted automatic output write once, including known receipts or pending identity |
| validation | {state:passed|failed|not_run, schema_digest:string, errors:bounded safe list} |
| observed_output | FinalCandidate|null for retained known candidate/validation after failure; never represents public success |
| persistence_state | not_committed, committed, unknown or not_applicable; final-output publication state |
| error, recording_error | nullable EngineError; primary failure and independently causal durability failure |
| recording_status | complete, incomplete or unavailable |
| cleanup | CleanupReport, including unconfirmed resources without masking a primary error |
| usage, counters | UsageAggregate and actual/reserved model/tool/repair counts, source bytes, elapsed time |
| start_event_receipt, terminal_event_receipt | EventReceipt|null; terminal receipt exists only after agent.finished committed |
| unfinished_actions | bounded {action_id,attempt_id:null|string,event_id:null|string,operation_id:null|string,phase} list |
| terminal_state | TerminalStateDescriptor|null, authority-free; fields below |
| terminal_state_ref | ArtifactRef|null; optional normal preterminal-state publication, authority-free and never a resume handle |
| audit_refs | ordered finalized safe audit artifact refs; inline safe audits can instead be found in referenced outcomes |

FinalCandidate is {mode:text|json, raw_visible_text:string, parsed_value:JsonValue|null, validation_state:passed|failed|not_run, byte_length, sha256}. It is bounded by the final-output/public-result allowances. It preserves the provider-returned visible content string as UTF-8 without rewriting, trimming or newline normalization; it is not a claim to retain HTTP wire bytes. JSON raw candidate and canonical parsed value are distinct. No native reasoning appears in this object. If it cannot fit public output, set observed_output=null and retain safe metadata in bounded error details plus already-finalized permitted refs; never return an oversized envelope.

TerminalStateDescriptor is {schema_version:1, state:terminal, run_id,root_run_id,correlation_id,root_action_id,definition_ref,model_ref,profile_ref,binding_digest,task_input_ref:null|ArtifactRef,source_refs:Ref[],model_outcome_event_ids:ID[],tool_outcome_event_ids:ID[],continuation_ref:null|ArtifactRef,limits_snapshot,counters,usage,output_ref:null|ArtifactRef,raw_output_ref:null|ArtifactRef,persistence_state}. It contains no leases/grants/secret/client, no future terminal receipt and no admission authority. It can seed a host terminal checkpoint; it cannot resume a run. Optional safe runtime checkpoints require separately approved codec/grants and a proven safe boundary.

PM accepted this automatic publication and fresh-host-access split during the v1 alignment. Automatic final-output ordering is: complete model outcome and local output validation; under still-valid normal run grants commit raw final visible-content artifact and validated output artifact (reuse a ref when bytes are identical); settle receipts and owned provider cleanup; decide terminal execution facts; append agent.finished with output/preterminal-state refs; then construct AgentResult with the received terminal_event_receipt. Do not attempt to store a complete final AgentResult before its own receipt exists, or put that receipt into its own event. Runtime publication is mandatory for succeeded output, even if a bounded inline value is also returned.

For Markdown/text, output_ref is the exact readable model-generated visible-content bytes. JSON output_ref is the canonical validated value and raw_output_ref preserves the original returned JSON text. Storage allocation/operation IDs and receipts are explicit; independent file writes are never a substitute. Source/citation manifest interpretation and a full application terminal checkpoint belong to the host baseline, not Runtime research logic.

After return, the host uses a fresh normal result-access/export binding from Connections, with explicit run/object read and publication grants. It may reuse/export the runtime output artifact and persist the citation manifest, finalized AgentResult and terminal checkpoint including actual terminal receipt. It does not revive the expired agent binding or use record_cleanup for business writes. Closing/reopening requires newly authorized read/checkpoint bindings; reference possession is not authority. The accepted Connections surface is async Engine.open_run_access(run_ref, request, options) -> Result[RunAccessSession]. The session exposes fresh scoped context, Storage/history, stable mutation identity allocation and a resource lease, with no provider/executor/invoker/admission. Preserve original context_kind/run/agent association, record the distinct host principal and purpose=result_access, and use a fresh binding/access action parented to the target root; do not reuse an old dispatch attempt. Reauthorize before existence/status disclosure and every operation. See Connections' owned RunRef/RunAccessRequest/RunAccessOptions schema.

Known output-publication failure with a durably recorded failure outcome yields failed (or timed_out/cancelled when that is the cause), observed_output retained, persistence_state=not_committed, and recording_status=complete if all required lifecycle records committed. Unknown admitted publication commitment is explicit unknown and incomplete pending reconciliation; lost outcome/terminal acknowledgment independently makes recording incomplete. A validated candidate alone never gives succeeded without required output receipts. A terminal append failure preserves the already-finalized execution status/output facts but returns incomplete recording. Host diagnostic publication can preserve observations through fresh authority; it cannot rewrite the original run as successful.

## 5. Admission, execution and child ordering

The v1 signatures are adopted without a competing caller-run or prepared-agent API:

```text
async Runtime.admit(definition, task_input, binding, context) -> Result[AdmissionLease]
async Runtime.execute(admission_lease) -> AgentResult
async Runtime.admission_status(context, admission_id) -> Result[AdmissionStatus]
async AdmissionLease.release() -> Result[ReleaseReceipt]
```

Admission performs local validation and bounded scoped context reads only. It validates the materialized definition/digest and task schema; exact provider/profile and capabilities; catalog schemas and immutable name map; grants, cancellation, ancestry/depth and limits; output-publication rights; source versions/ranges; and available shared-ledger reservation. It does not open a model network connection, spawn a worker, run a child, or infer authority from serialized context. A rejected admission returns Err with safe details and no agent start or external effect.

AdmissionLease has a live single-use handle and a separately serializable descriptor. The descriptor is exactly {schema_version:1, admission_id, run_id, root_run_id, correlation_id, root_action_id, definition_ref, binding_id, binding_digest, ledger_id, reservation_id, expires_at_utc}. Its live handle additionally owns the resolved immutable definition/input/context plan, cancellation/revocation linkage, monotonic expiry and reservation. Descriptors and old receipts are observations, not capabilities. Connections' trusted allocator provides run/lineage identity; Runtime allocates admission/root-action identity and links the parent's invocation action AND attempt when present.

AdmissionStatus is {schema_version:1, admission_id, state, start_event_receipt:null|EventReceipt, terminal_event_receipt:null|EventReceipt, terminal_status:null|ExecutionStatus, reservation_state, error:null|EngineError}. State is reserved, consumed, terminal, released, expired or unknown; consumed is v1's consumed/accepted state and does not alone prove committed agent.started. reservation_state records the shared ledger's known reserved/consumed/released/unknown observation. ReleaseReceipt is {schema_version:1, admission_id, state:released|expired, reservation_id, duplicate:bool}; only a known unconsumed reservation is releasable. The shared-contract codec/ledger enum spellings must be consolidated by PM before implementation.

Execute atomically verifies lease identity/expiry, current grants and available lineage resources, then consumes it once. Recheck cancellation/deadline before recording agent.started and before any external dispatch. Failed consume returns a not-started domain result; unknown consumption returns an unknown start/reservation observation, holds identity for reconciliation, and never creates another run. Append agent.started on the root action with attempt_id=null. Only its committed receipt permits opening/using the provider and reaching a model dispatch. A provider-open failure after a committed start becomes a recorded failed agent. A lost start acknowledgment is reconciled by exact event ID/digest; no receipt means no external call.

The live owner settles the reservation on every known terminal path. release is idempotent for the same known unconsumed reservation; it cannot release consumed, uncertain or already admitted work by guessing. admission_status reauthorizes its lookup and observes that owner/history; it does not consume, renew, resume, retry or reconstruct a lease after restart. History may prove committed start/terminal facts after owner loss. Missing history never proves that dispatch did not occur. Unresolved consumption or dispatch remains unknown with IDs and reservation/resource observations retained.

Connections' child path is fixed: narrow grants/deadline and allocate shared lineage identity; Runtime.admit child; Connections commits parent invocation.intent with its action/attempt and the admission descriptor; recheck caller state; Runtime.execute consumes child lease and records the child's lifecycle; Connections performs only authorized bounded result export, then records parent invocation.outcome including the export receipt or failure and the preserved child terminal facts, and awaits its committed receipt. Release the child only if known unconsumed. Lost consume/return acknowledgment is an observation/status-reconciliation case, never a second child. Container does not write Connections' invocation events or treat an export failure as proof that a successfully completed child failed.

The runtime loop is deterministic in ownership and record order:

1. Resolve the pinned initial context/input and start receipt. Open the bound provider session using its scoped resolved configuration; credentials remain in live configuration only.
2. Allocate a model action/mandatory attempt and reserve applicable counts/token allowance. Render and validate the exact request/audit. Commit model.intent with frozen request digest, safe audit/refs and limits; recheck live cancellation/deadline/grants; call generate once.
3. Bound/reassemble/validate the native response. Record model.outcome with dispatch/effect/completion, safe audit, nullable usage and continuation reference when authorized. Failed recording stops all further dispatch.
4. A complete tool-call batch is checked in full against unique native IDs, name map, schemas, grants and remaining aggregate limits before its first member executes. Default execution is sequential in provider order. For each member use the common RecordedToolAction below and feed its correlated result to the native next turn only after complete required recording.
5. Candidate text beside calls is intermediate. Final content is parsed and locally schema-validated. Invalid output terminates validation_failed by default; an explicitly bounded repair is a new model action with original validation observation linked and required native state preserved.
6. Publish final raw/validated output under normal grants, settle provider/resources and reservation, record agent.finished, and return the bounded AgentResult. The execution status, recording status, persistence and effect observations remain independent.

A recoverable tool failure may be fed back when the definition explicitly permits it and recording is complete. Unauthorized functions, invalid arguments, unknown effects, missing output/terminal receipts, exhausted limits, cancellation and deadline never cause an unbounded model repair or automatic worker replay. Default model retry/repair counts are zero. Any explicitly allowed retry needs a proven permissible effect state, same logical action/new attempt, new durable intent and remaining shared quota. Changed prompts, repairs or model turns use new actions.

## 6. One recorded tool action for agent and standalone execution

```text
async RecordedToolAction.run(tool_request, binding, context) -> ToolResult
ToolCatalog.resolve(name, revision) -> Result[ToolDefinition]
async ToolExecutor.execute(definition, arguments, context, storage_plan) -> ToolExecutionResult
async ToolExecutor.close(deadline) -> CleanupReport
```

Container owns RecordedToolAction and producer=runtime. Both Runtime's model loop and Connections' host/standalone runner call this exact implementation. Toolset's executor and worker do not emit the Container lifecycle hooks, and Connections does not create a parallel standalone logger. Standalone context_kind=standalone_tool has nullable agent/definition/provider call IDs; its root action is its actual tool action, with an actual tool attempt. Standalone never opens a provider.

ToolRequest is {schema_version:1, tool:ToolIdentity, arguments:JsonObject, provider_call_id:string|null, model_action_id:string|null, model_attempt_id:string|null}. Agent requests require matching originating model action/attempt/call IDs; standalone requires all three null. The trusted helper derives this tool's own action/attempt metadata from the supplied context and identity service; preflight has no attempt, and the helper allocates the first attempt only for dispatch admission. Context supplies live authority independently. Public arguments cannot specify process argv, executable/root, grants, worker control envelope, operation ID or injected Storage plan. Resolve a pinned registered ToolDefinition; intersection of its limits, definition allowance and live policy determines the actual request.

RecordedToolAction owns preflight and the public lifecycle boundary:

1. Validate public input, exact tool/version, closed schema and additional narrowing, allowed-tool membership (agent), grants, deadlines, ledger and registered capabilities. Rejection records tool.rejected with attempt_id=null, dispatched=false and safe causal error. It starts no process, creates no dispatch reservation, and never pretends to have a worker outcome.
2. For an admitted dispatch allocate the attempt before reserving limits. Freeze the trusted execution/Storage/search plan, allocate any mutation operation IDs, and append tool.intent under the tool action/attempt. Get EventReceipt, then recheck cancellation/deadline/revocation. An intent followed by known nondispatch receives tool.outcome with dispatched=false; it is not another tool.rejected.
3. Pass the scoped live context and immutable plan to ToolExecutor. Toolset mediates approved read injection or fetch publication. Every network request, worker start and tool-related Storage read follows this recorded intent. A malformed internal control envelope is rejected, but valid-looking JSON is not authentication or a claim of same-user OS isolation.
4. Validate ToolExecutionResult and bound its safe result/error, process observations, cleanup, refs, commit/effect states and receipts. A prepared fetch bundle/exit zero does not count as public success. Only a complete Storage READY snapshot receipt supports a fetched snapshot result; required read result must match the injected authoritative slice.
5. Append tool.outcome using the same action/attempt and observed facts. Complete execution, required persistence and committed outcome are all required before exposing public succeeded. If append/status reconciliation fails, return incomplete/unavailable recording and known observations/receipts; terminate further external dispatch. Public ToolResult is failed with a recording error when its required hook failed, while its internal execution/effect/commit observations remain known; an AgentResult terminal-append failure separately preserves the execution terminal as specified in section 4. Do not hide a committed snapshot or remote effect because the hook failed.

ToolExecutionResult is an imported Toolset-owned internal observation, never mislabeled ToolResult. Public ToolResult is the shared closed record containing schema_version=1; execution/tool identity; provider_call_id nullable; six-way execution status; result/error; dispatched/effect observations; safe worker phase/process/duration/usage/cleanup; persistence_state, operation IDs and receipt/refs; recording_status/error; and intent/outcome/rejection event IDs/receipts. Exact public shared field spellings are PM-owned; Container contributes the hook/receipt/identity invariants instead of forking Toolset's schema. Successful JSON null is determined by status, not truthiness.

One worker launch is one tool attempt. An allowed named search fallback or fetch redirect is a bounded worker observation with backend_attempt_index, backend and outcome, within the immutable pre-dispatch plan. It does not allocate another attempt or hook pair. DDGS internal HTTP counts remain unknown unless instrumented. Worker relaunch is a new attempt and durable intent; neither fallback permission nor a delivery retry authorizes it.

The initial mediation design is bounded launcher injection for document.read and prepared bundle publication for web.fetch, with no persistent broker. The executor calls scoped Storage; workers have no database/root access or finalized publication authority. Search discoveries alone never become citation evidence. Runtime feeds bounded results into native history, retaining source refs and exact locator/continuation; strategy chooses subsequent fetch/read actions.

## 7. Canonical records, errors and reconciliation

Identity rules apply throughout the document: Connections allocates run/root/correlation; the owning runtime allocates logical model/tool/root actions and each dispatch attempt; the event producer allocates event_id before append; the trusted mutation caller allocates operation_id before admission. Storage publication events reuse the causal action/attempt and their operation ID. Provider-native request/response/call IDs are preserved separately. Identical delivery freezes all IDs/content; external execution retry changes attempt and consumes quota; changed request changes action. Agent bookkeeping root events have no attempt. Child roots carry parent invocation action AND attempt.

Runtime emits agent.started/finished, model.intent/outcome, tool.intent/outcome/rejected and bounded validation/limit/cancel observations. Connections alone emits binding.resolved/failed and invocation records; Storage alone emits its transactional publications. No duplicate start marker is emitted. Rejection/intent/observation markers are not additional execution terminal enums.

ExecutionEvent is the shared envelope: schema_version=1, event_id, kind, producer, causal ExecutionMetadata, producer timestamp, bounded safe payload/refs, and appropriate status/duration/usage/error. The frozen event never includes its own future receipt. Safe payloads contain identities, schema/request digests, audit, native ID pairings, observed states, bounded errors and authorized references. No credentials, env values, headers, unsanitized HTTP/stderr bodies or native reasoning. References carry store identity and need read authorization.

EventReceipt is exactly {schema_version:1, store_id:string, event_id:string, recorded_seq:positive integer, recorded_at:UTC timestamp, duplicate:bool}. A successful append means committed under the startup-verified Storage profile. Sequence, not producer clocks, orders committed records. Container has no alternate acknowledgment type or caller-controlled durability switch.

Illustrative append receipt; an event refers to preceding receipts when needed, not to this receipt before append:

```json
{
  "schema_version": 1,
  "store_id": "<verified-store-id>",
  "event_id": "<frozen-event-id>",
  "recorded_seq": 12,
  "recorded_at": "2026-10-01T00:00:00Z",
  "duplicate": false
}
```

Result[T] is Ok(value)|Err(EngineError) for infrastructure. ModelResponse, AgentResult, ToolExecutionResult, ToolResult and InvocationOutcome directly represent anticipated domain failures. EngineError carries shared code, sanitized message, bounded safe details and observed effect state. Storage/delivery errors additionally carry commit_state=not_committed|committed|unknown|not_applicable and retryable_delivery. retryable_delivery applies to the identical event/write, never a fresh model/tool/invocation. Unexpected defects remain exceptions after cleanup; Python task cancellation is re-raised as specified below.

Use context-first ActivityRecorder.append(context, event) and ActivityRecorder.status(context, event_id, expected_event_digest). On an ambiguous append, retain the frozen event and query/re-deliver only the identical event under currently authorized owner-event access. Returned receipt must match store/event and digest. OperationStore.status(context, operation_id) similarly reconciles an admitted Storage mutation; compare its authorized observed identity/content and receipt to the caller's frozen expected request. A lookup reauthorizes and never grants read/business rights. Exact status variants import Storage's shared schemas.

A missing record at one moment is not proof that a queued/admitted write will never commit. not_committed requires proven nonadmission, rollback or durable abort. Pending/unknown operations keep their IDs, live owner and resources until settled or explicitly reported unresolved. Cancellation after admission does not roll back by assertion. Reusing an ID with changed bytes/origin is a conflict; allocating a new ID to hide uncertainty is prohibited.

Without a committed intent receipt there is no dispatch. If cancellation/revocation happens after intent but before dispatch, record an outcome with dispatched=false. If a response/effect is known but outcome recording fails, preserve it, stop further dispatch, reconcile only recording and return incomplete. A failed terminal append preserves the earlier execution status and artifact receipts. AgentResult's execution terminal and recording_status are not collapsed into one enum.

record_cleanup is separately issued, finite, owner-bound access for event append, status reconciliation and lease cleanup. It cannot authorize a new model/tool call, publication of raw/final output, audit artifact, snapshot, citation manifest, checkpoint or other business mutation. If a normal write was already admitted, its owner may settle/report it without treating that as a new write. Storage must remain available through these settlements and terminal recording. No accepted operation is silently discarded to make shutdown appear clean.

## 8. Context, accounting, cancellation and cleanup

Context assembly is bounded and grant-checked before use. Canonicalize/validate task input; resolve definition-ordered source refs and latest_at_start versions once; read only authorized immutable slices; preserve source identity, actual spans, extraction revision/hash and advancing continuation. Treat source text and tool output as untrusted data roles, never system instructions or authority. Task/instructions/required sources and an outstanding native assistant-call/result group cannot be removed to make a request fit.

Measure the actual rendered UTF-8 request, including function schemas, native reasoning/encrypted items and tool results. Bound source bytes, request/response bytes, continuation, JSON depth, read units and context/token estimates separately. overflow=fail rejects a request that cannot fit; drop_optional_groups can omit complete optional context groups in definition order with recorded omission/ref/range, before their inclusion in a native transcript. It cannot arbitrarily delete native conversation items, half a tool exchange or required evidence. No implicit summary, alternate model, reretrieval or permission expansion is a fallback. A future compaction profile requires explicit compatible codec/capabilities and recorded transformed content.

Model calls, emitted tool calls, worker attempts, repairs, context bytes and elapsed time consume their effective shared-lineage limits at their documented reservation/observation boundaries. Reserve before dispatch and account known usage once by action/attempt. Identical record delivery consumes no new external execution count; actual retries and children do. Usage has nullable unknown fields, known subtotal and missing-attempt list. Unknown usage is not zero. Strict token budgets need a verified sufficient input/output upper-bound method for that exact profile, including native/tool/schema overhead and reasoning; unsupported strict enforcement fails admission. Advisory budgets retain uncertainty and use hard byte/count/deadline/output-token limits. Provider ceilings are capability constraints, not default runtime allowances.

The v1 Toolset envelope is adopted: decoded original 8 MiB, text 4 MiB, index 1 MiB, provenance 64 KiB, stdin 1 MiB, fetch stdout 20 MiB, public JSON 512 KiB, stderr 64 KiB, depth 32, read text 64 KiB and at most 200 lines/10 physical pages. Bindings may reduce these. Check encoded JSON/base64/escaping totals, not just component payloads. Measure one fetch and then at most two concurrent fetches; these limits do not prove parent/worker/PDF-parser peak RAM. Container propagates limits and refuses an oversize observation rather than bypassing Toolset caps with an unregistered executable or broker.

Use UTC deadline metadata for audit and a live monotonic deadline for enforcement. The inherited parent deadline, definition limit and per-call limit take the earliest expiry. Recheck cancellation, revocation, ledger and deadline at admission/consume, every intent acknowledgment, external dispatch and normal publication. Cancellation propagates downward through the shared context. Stop new dispatch first; distinguish work that never dispatched, known returned/effected work, and uncertain remote processing.

Explicit engine cancellation returns cancelled after finite cleanup/recording. Python task cancellation runs bounded cleanup/owner reconciliation under shielded ownership and then re-raises CancelledError; it is not swallowed to fabricate an AgentResult. An expired execution returns timed_out, except that already-known completed execution/commit facts remain reported. Local HTTP disconnect/timeout does not prove remote inference was cancelled or unbilled. Preserve safe provider IDs and unknown usage/effect. Do not retry an uncertain remote call.

ProviderSession.aclose returns CleanupReport; Toolset owns actual process-tree termination, child reaping and pipe draining; Runtime settles its provider tasks/admission reservation and borrowed leases. CleanupReport imports the shared bounded fields for attempted/confirmed/unconfirmed resources and errors. A secondary cleanup failure does not replace the primary error or remove known observations. No new dispatch is allowed during cleanup. A resource owner/supervisor retains admitted operations that outlive caller cancellation; a five-second grace does not magically abandon or close them. The result reports unresolved work and IDs.

record_cleanup has the narrower authority defined in section 7. Ordinary output/audit/checkpoint business writes must have been authorized/admitted before expiry/cancellation or use fresh host access later. Terminal records can contain bounded already-observed safe facts; they cannot trigger a new audit artifact write. If business publication cannot proceed, return failure/observations and independently record the terminal outcome. Host later preservation remains diagnostic when the original execution failed.

Connections stops admission, cancels/drains admitted runs and invocations, lets outcome/terminal and Storage operations settle, releases module leases, then closes Storage last. A borrowed provider/executor/store handle is not independently closed as the shared owner. Container gives Connections unresolved resource/operation facts; it does not assert clean shutdown while ownership is uncertain.

Safe checkpoints are authority-free observations. Terminal checkpoints are host-authored under fresh normal grants and contain actual final receipts and refs. Any future resumable provider checkpoint must pin exact run/definition/model/profile/binding/codec/tool map, retain necessary native continuation under restricted rights, and occur at a proven complete exchange boundary with no pending external dispatch/write/outcome. Loading it must reacquire authority and validate compatibility. V1 does not promise process-loss resumption, automatic replay, saved-lease reconstruction, or checkpoint-based revival of a cancelled run.

Storage baseline remains single-root ownership, serialized bounded SQLite worker, DELETE journal, synchronous EXTRA, foreign keys and verified startup settings. Optional WAL needs Storage's patched-runtime gate; there is no silent fallback. Complete READY receipts and exact-ID status/delivery reconciliation are required. This design makes no hardware power-loss guarantee and does not replace Storage's recovery protocol.

## 9. Provider profiles, configuration and official evidence

ProviderFactory.capabilities(profile) is a local, versioned declaration, not an incidental probe. ProviderCapabilities is {schema_version:1, provider, protocol, profile_ref, adapter_revision, model_id, function_tools, tool_choice_modes, native_json_mode, native_json_schema, schema_subset_ref, reasoning_modes, streaming, usage_fields, stateless_native_continuation, checkpoint_codec_ref, cancellation_semantics, context_token_ceiling, output_token_ceiling, evidence_refs}. All fields are required. Identity/ref fields are strings/shared NamedRefs; function_tools/native_json_mode/native_json_schema/streaming/stateless_native_continuation use Capability={state:supported|unsupported|conditional|unknown, conditions:bounded string[], evidence_refs:Ref[]}. tool_choice_modes is a unique auto/none/required/named list; reasoning_modes and usage_fields are explicit bounded string lists; schema_subset_ref/checkpoint_codec_ref are nullable NamedRefs; context_token_ceiling/output_token_ceiling are nullable positive integers; cancellation_semantics is local_only or confirmed_remote with evidence; evidence_refs is a bounded Ref list. Unknown deployment facts remain unknown. A required conditional feature must be established by exact resolved configuration and later live acceptance, not optimism. ProviderFactory.open returns Result[ProviderSession]; generate returns ModelResponse; aclose returns CleanupReport.

The exact initial profiles are OpenAI Responses with gpt-6-luna; DeepSeek Chat Completions with the requested V4.1 Flash API ID deepseek-flash; and configurable local vLLM/Qwen Chat Completions. They have separate renderers/native codecs. Neither "OpenAI-compatible" nor a common client library proves interchangeable conversation, structured-output, reasoning or cancellation behavior.

| Capability | OpenAI GPT-6-Luna Responses | DeepSeek V4.1 Flash Chat | Local vLLM/Qwen |
| --- | --- | --- | --- |
| Registered function calls | documented; retain native output items/call_id | documented; assistant tool_calls and matching tool_call_id | conditional on pinned model/template/tool parser/server |
| Native reasoning continuation | Responses native items; restricted encrypted items when required | full preceding reasoning_content when tools parameter is present | pinned template/protocol; Qwen3 example omits thinking from subsequent public history |
| Native output enforcement | Structured Outputs supported subset | json_object syntax mode; strict tool arguments are a separate beta profile | structured outputs backend/version/model dependent |
| Local output validation | always required | always required | always required |
| Usage/cancellation | actual nullable usage; local disconnect not remote proof | actual nullable usage/cache/reasoning; same uncertainty | unknown until deployed/version-tested |
| Platform-only research tools | fixed instruction plus function-only payload/audit | same, with thinking controlled independently | same, with manifest/tool parser validation |
| Evidence status | official documentation; no live call in this design | official documentation; account availability/live call pending | connector/manifest design only; no deployment here |

ResolvedProviderConfig is a live closed profile selection {provider, protocol, model_id, model_ref, profile_ref, adapter_revision, endpoint, credential_handle, request_settings, continuation_policy, deployment_manifest_ref:null|NamedRef}. The serializable descriptor substitutes safe endpoint identity for connection data and omits credential_handle. Connections resolves central configuration and environment precedence; Container validates only selected settings. Model IDs/config refs never silently change, fallback models are absent, and missing Qwen settings do not block API profiles.

| Key or setting | Mapping, evidence and design rule |
| --- | --- |
| provider / protocol / model_id | explicit renderer/endpoint and exact requested model. GPT-6-Luna documents Responses function tools; Chat tool calling requires reasoning none, so Responses is the selected profile. Its documented ceilings are 1,050,000 context/128,000 output tokens; smaller runtime limits apply. [OpenAI model](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| endpoint / credential_handle | named safe endpoint plus Connections-issued live secret; OpenAI/DeepSeek authentication follows their API references; Qwen endpoint/auth is explicit manifest policy. No secret in definition/request/audit, and endpoint network/proxy policy is trusted configuration. [Responses reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create), [DeepSeek Chat reference](https://api-docs.deepseek.com/api/create-chat-completion/) |
| OpenAI request_settings.reasoning_effort | none/low/medium/high/xhigh/max map to reasoning.effort; medium is documented default. Unknown/ineffective sampling settings reject against the selected profile. [OpenAI model](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| OpenAI request_settings.max_output_tokens / stream | map to documented Responses fields; default nonstreaming. No hidden client retries/background mode. Streaming, if explicitly enabled, assembles one bounded terminal response without dispatching partial calls. [Responses reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create) |
| OpenAI continuation_policy | stateless store=false; preserve all required prior native output items and original call_id for function_call_output; request reasoning.encrypted_content when needed for restricted stateless continuation. Do not convert items to plain assistant text or rely on a server response ID alone. [Reasoning](https://developers.openai.com/api/docs/guides/reasoning), [Function calling](https://developers.openai.com/api/docs/guides/function-calling) |
| OpenAI native output | explicit supported JSON-schema subset/strict configuration; unsupported required schemas reject before dispatch, optional mode falls back only to stated local validation. Refusal/incomplete remain domain outcomes. [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) |
| DeepSeek model_id | v1 selects deepseek-flash for V4.1 Flash. Actual selected account/model evidence must be verified during authorized acceptance; no substitution. Current catalog was researched earlier; the final attempted catalog refresh returned a web Internal Error, while current thinking examples also use this ID. [Model catalog](https://api-docs.deepseek.com/quick_start/pricing/), [Thinking guide](https://api-docs.deepseek.com/guides/thinking_mode/) |
| DeepSeek thinking / reasoning_effort | documented thinking type enabled/disabled and effort low/high/max; materialize the selected mode. Thinking requests ignore sampling controls such as temperature, so reject ineffective settings rather than pretend they work. Thinking plus required/named tool choice is constrained; profile validation rejects incompatible combinations. With tools, round-trip all previous reasoning_content, including turns without calls. [Thinking guide](https://api-docs.deepseek.com/guides/thinking_mode/), [Chat reference](https://api-docs.deepseek.com/api/create-chat-completion/) |
| DeepSeek max_tokens / response_format / stream | documented Chat fields; max_tokens narrows selected limits. json_object supplies syntax, not arbitrary local schema validation. Strict tool mode uses beta-specific URL/schema rules and is not enabled implicitly. Reassemble tool deltas by native index/ID. [JSON mode](https://api-docs.deepseek.com/guides/json_mode/), [Tool calls](https://api-docs.deepseek.com/guides/tool_calls/), [Chat reference](https://api-docs.deepseek.com/api/create-chat-completion/) |
| DeepSeek optional Responses | a distinct future profile/codec; do not reuse OpenAI encrypted/store/background settings or assume endpoint compatibility. Initial baseline remains Chat. [DeepSeek Responses guide](https://api-docs.deepseek.com/guides/responses_api/) |
| Qwen deployment_manifest_ref | exact served model/alias, repo/revision, tokenizer/revision, template digest, vLLM version/image, tool/reasoning parser, thinking mode, structured-output backend, generation configuration and hardware/limits. Qwen's Qwen3-8B example uses auto tool choice, hermes and deepseek_r1; other model/version combinations need their own evidence. [Qwen function calling](https://qwen.readthedocs.io/en/stable/framework/function_call.html), [Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B) |
| vLLM request settings | max_tokens/tool_choice and supported sampling/structured-output fields are declared by the pinned server. Named tool output can have finish_reason=stop, so inspect actual calls. Do not send obsolete guided_json keys on modern versions or invent universal Qwen flags. [Compatible server](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/), [Tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/), [Versioned structured outputs](https://docs.vllm.ai/en/v0.22.1/features/structured_outputs/) |
| tools / search policy | only mapped registered function schemas; fixed platform-only system instruction and rendered audit. These are client-enforceable controls. No undocumented search flag or claim that inaccessible provider internals were independently observed. [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling), [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/), [vLLM tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/) |
| continuation persistence / cancellation | adapter-local codec with restricted artifact rights or memory-only policy; bounded local cleanup and honest unknown remote status. Continuation payloads are not public reasoning reports; no profile promises remote rollback on client disconnect. |

VllmDeploymentManifest is exactly {schema_version:1, manifest_ref:NamedRef, endpoint_id, served_model_id, model_repository, model_revision, tokenizer_repository, tokenizer_revision, chat_template_sha256, vllm_version, server_image_digest, tool_call_parser, reasoning_parser:null|string, thinking_mode, enable_auto_tool_choice:bool, structured_output_backend:null|string, generation_config_digest, max_model_len, max_output_tokens, server_limits, hardware_description, evidence_refs}. It contains no executable server command that the Windows client starts implicitly, secret or invented deployed value. "Qwen" without this manifest is insufficient for capability admission. The model card/template determines whether thinking is retained or omitted; a DeepSeek rule is not copied into Qwen.

Official documentation supports these mappings; it does not prove deployment, credentials, live account model availability, full schema compatibility or real cleanup. Evidence is dated September 30, 2026 and must be rechecked against the pinned profiles during authorized implementation/live acceptance. The current Windows environment is a client; Container does not install a local vLLM server or add its GPU packages to the shared project.

## 10. Future module work and acceptance evidence

After PM confirms a directly human-authorized phase transition, implement the owned paths only: agent schemas/validation and context/admission/loop/RecordedToolAction/accounting under src/ebd/agent/; exact profile renderers/parsers/native codecs under src/ebd/providers/; meaningful checks under tests/agent/ and tests/providers/. PM supplies the one shared executable contract package and dependency lockfile. Connections supplies real bindings/invocation; Toolset real registered processes; Storage real persistence. Do not fill missing modules with mock replies at handoff.

Consumer entry points are the v1 signatures above, through Engine for applications and the bound Runtime for Connections. Document actual uv run --locked commands, configured profiles/tool revisions, required grants, schemas, errors, outputs and cleanup once runnable. This design does not claim nonexistent CLI commands, source files, test results, model-generated report paths or deployment. Tests that substitute a transport to exercise malformed data can prove a specific parser/fault condition; they cannot prove real model/tool/storage integration.

| Future verification | Required observation |
| --- | --- |
| Definition/admission | unique-key/finite/depth/byte and schema failures, forbidden settings/capabilities/grants, pinned versions, no network/worker before accepted start, duplicate/expired/released/unknown consumption, shared reservation retention |
| Model native turns | real GPT-6-Luna Responses and real deepseek-flash at least tool call -> actual platform tool -> correlated result -> final candidate; safe actual request/profile audit and exact native continuation/call ID evidence |
| Qwen connector | configurable complete manifest, compatibility/failure/codec checks; actual local live result pending until deployment, with no guessed parser/template/server claims |
| RecordedToolAction | agent and standalone use the same helper/producer, root/attempt semantics, durable intent before worker/network/Storage read; prepare/exit zero cannot bypass READY commit or outcome receipt |
| Validation and limits | valid/invalid final JSON/text, native refusal/incomplete, whole tool-batch preflight, bounded repair/explicit retry accounting, unknown usage/strict-budget rejection, rendered/escaped max-fit and oversize boundaries |
| Cancellation/cleanup | before/after intent, during remote response/worker/read/commit and after successful effect; explicit cancelled result versus re-raised task cancellation; actual provider/task/process/pipe/lease settlement, unconfirmed resources honest |
| Storage/recording uncertainty | lost intent/outcome/terminal acknowledgments and admitted publication replies; same ID/content status/delivery, committed/pending/absent distinction, no duplicate external dispatch, complete recording on known recorded publication failure |
| Output/host lifetime | hash/length/media of exact text candidate, JSON raw versus canonical validated artifact, completed terminal receipt without self-reference, fresh RunAccessSession after completion and close/reopen; expired grants and guessed refs denied |
| Root/child/standalone | shared ancestor limits, parent invocation action+attempt linkage, narrow grants/deadline, authorized export before parent invocation.outcome with its receipt/failure and preserved child terminal, standalone no provider, no authority from saved checkpoints |
| Resource profile | Toolset's encoded bytes/parser expansion/peak RAM and actual Windows descendant cleanup evidence; no claim that numeric caps alone prove memory or shutdown |

The simple PM baseline asks exactly "What is EBD (Environment Based Design)" through one flat deepseek-flash agent with the selected five registered tools (web.search, scholar.crossref.search, scholar.openalex.search, web.fetch and document.read) and the fixed platform-only search policy, as specified in [baseline-acceptance.md](../baseline-acceptance.md). The general discovery profile is Yahoo primary with corrected Google as a gated fallback; scholarly discovery keeps its separate registered definitions. Runtime handles normal execution and exact final publication; the host handles research instructions/citation manifest/full terminal checkpoint and quality review. Actual final report must be a readable Markdown artifact, derived from the real final model text, with report hash equal to reopened bytes. Each citation must map to saved fetched/read evidence, snapshot/extraction identity/hash and exact ranges; General or scholarly discovery metadata alone is insufficient citation evidence.

Use Engine.open_run_access after return for the report, audit/source/history reads and normal citation-manifest/checkpoint publication. Close all admitted work/leases before Engine.close; reopen Engine and obtain new access under current policy to verify saved report/checkpoint/sources. Include actual terminal receipts and uncertainties in the checkpoint. Do not claim the baseline alone proves GPT/Qwen, child/standalone, permission/CAS, resource, uncertainty or cleanup gates; [baseline-acceptance.md](../baseline-acceptance.md) lists the full platform audit.

## 11. Cross-module consolidation requests and resolved decisions

All behavior choices above are complete design proposals under v1, not authority to implement. No unresolved question prevents finishing the owned design. The following exact shared protocol/schema consolidation is needed before runnable integration; PM owns the shared package and coordinates its consumers.

| Request | Exact need and affected consumers |
| --- | --- |
| C1 Canonical byte codec | One pinned canonical finite-JSON encoder/digest domain for definitions, tool name map, request/event/mutation/continuation comparisons; define allowed numeric forms/key ordering/string handling. Storage/Connections/Container must use identical bytes. Do not independently select competing serializers. Definition excludes its own digest; audit body digest excludes credentials. |
| C2 Common closed records | PM lifts owned AgentDefinition/ModelRequest/ModelResponse/AgentResult/Admission schemas and accepted output_publications/raw/ref/media/terminal fields, and consolidates the common ToolRequest plus peer-owned ToolExecutionResult/ToolResult/ToolStoragePlan/refs/error/cleanup schemas once. Confirm DefinitionRef={agent_id,revision,digest} and shared field/enumeration spellings. This is type consolidation, not another behavior alternative. |
| C3 Lineage/binder wiring | Connections creates/issues/binds the trusted lineage ledger and narrowed grant/revocation/resource handles; Container owns runtime accounting/admission behavior. Consolidate live ledger reservation/consume/settle/release/snapshot protocols and ownership across child and standalone factories; unknown consumption cannot release/recreate permits. Schema-only metadata must never issue authority. |
| C4 Owner cleanup settlement | Connections/Storage/Toolset provide bounded owner reports and supervisors for admitted operations surviving cancellation. Runtime needs exact event-status receipts and the narrow record_cleanup capability while Store remains alive; no business writes through that capability. Unresolved operations retain IDs/ownership. |
| C5 Shared tool helper constructor | Connections binds exactly one Container RecordedToolAction to catalog/executor, Storage/recorder, IDs/ledger and plan factory; same instance/protocol for agent/standalone with producer=runtime. Toolset retains the private launcher/commit boundary. Confirm the shared public ToolResult's required receipt/error fields, not a second logger/helper. |

PM accepted Runtime's automatic raw/validated final publication and AgentResult lifetime fields; v1 now includes them. PM/Connections accepted Engine.open_run_access -> RunAccessSession, resolving the earlier missing post-run application context. It exposes only scoped data/history/status/publication and a lease, with new normal host bounds and explicit current rights; no old execution authority, provider/executor/invoker/admission. These are resolved design decisions, not open API-selection questions.

The requested baseline profile is resolved to DeepSeek V4.1 Flash/deepseek-flash. Account availability remains a future live check, not permission to choose a different model. The shared caps, DELETE/EXTRA baseline, attempt IDs, six terminals, direct execution outcomes, EventReceipt, context-first Storage/status and standalone producer are all adopted. Optional provider features/native schema subsets and local Qwen manifest are explicit configuration/evidence gates; routine internal implementation choices need no extra user decision.

Runtime/live API work remains outside current authorization. PM reported that automatic approval review rejected the phase transition because of the human design-first instruction. This mission finishes the concrete reviewable design; it does not retry that transition or perform model calls.

## 12. V1 conformance and actual verification

| V1 requirement | Owned conformance location |
| --- | --- |
| ownership, shared uv/Python, integer version, strict bounded JSON | 1-2 |
| exact AgentDefinition/input/output and closed settings | 2 |
| ModelRequest/Response, native IDs/content/usage/continuation/audit | 3, 9 |
| six execution terminals and independent recording/commit/effect | 4, 6-7 |
| exact final raw/validated bytes, normal publication, terminal receipt, fresh host access | 4, 8, 10-11 |
| single-use admission, accepted/start/terminal observations, uncertain consume | 5 |
| required attempt before dispatch; parent action+attempt; frozen delivery IDs | 5-7 |
| committed intent before model/tool/read/network; outcome/rejection and terminal ownership | 5-7 |
| one RecordedToolAction; ToolExecutionResult versus public result/READY; runtime standalone producer | 6 |
| exact EventReceipt and context-first status; no uncertain replay | 7 |
| context/range/version/readiness; whole native exchange; limits/token uncertainty | 2-3, 8 |
| finite cancellation/cleanup; task cancellation re-raised; no cleanup business writes | 7-8 |
| exact GPT/DeepSeek profiles, Qwen manifest, official settings and platform-only search audit | 3, 9 |
| full future real-provider/tool/storage/permission/resource/reopen acceptance | 10 |
| exact common-package consolidation and design/live boundary | 11 |

Actually performed: read README/shared platform/coordination/Agent Container brief, CONTRIBUTING, missions, decisions, v1 and PM baseline acceptance; reviewed peer reconciliation/host-access/status excerpts; completed the whole owned document replacement; researched/rechecked cited primary provider documentation. The final browser refresh of DeepSeek's catalog returned an Internal Error; current thinking documentation still identifies deepseek-flash, while v1 selects that model. The outdated OpenAI Responses reference URL returned 404 and was replaced with its verified current Python API reference.

Saved-file QA results are recorded in [agent-container-status.md](../reports/agent-container-status.md). Only checks actually completed there are evidence. Earlier PM commit/QA of the draft at 4210b8c is historical and does not validate this replacement. Shared baseline acceptance was announced by PM at 3d25c7c; this team has not staged/committed/pushed anything.

No runtime source/dependencies/lockfile changes, package installation, local/.env inspection, model API call, CLI worker or actual Storage run occurred in this design mission. All provider/account, recorded dispatch, persistence/reopen, process/RAM, permission, cancellation and integration checks in section 10 remain future/unperformed. Local vLLM/Qwen live verification is explicitly pending because no deployment exists on this machine. A schema example or saved design is not a platform handoff.
