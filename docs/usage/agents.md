# Agent Container and real model connectors

`error_policy.finalize_on_limit` is an opt-in boolean (default false), also
exposed as `finalize_on_limit` during HTTP agent registration. It reserves
the last model call for a final answer and enters final mode when two or fewer
tool calls remain after research has begun. An oversized registered tool batch
is not dispatched: an `agent.finalizing` event records the declined call IDs,
and correlated not-executed results are returned to the model. Final mode uses
`tool_choice=none` and asks for explicit missing information. If the model still
requests tools, Runtime fails without dispatch. This does not bypass model,
tool, time, recording or authority limits, and a saved answer can be partial.

Local NInfer is also supported through an explicit `ninfer` provider. For
`ebd serve`, set `NINFER_BASE_URL` and `NINFER_MODEL` in ignored `local/.env`
or the process environment. The endpoint must be loopback. It uses Chat
Completions with registered function tools and native tool continuation,
separate from the vLLM deployment profile. Thinking is disabled using
`chat_template_kwargs.enable_thinking=false`. Output defaults to 4096 tokens
per call and temperature 0.2. Start/configure the model server independently.
Python hosts can supply the same ProviderConfig via EngineSettings.profiles.

A live local Qwen planning request and a fetch/read/report conversation
completed on October 1, 2026. The latter run was
`run_9bbe8e94205740a5b5c0a2c1a0951d0c`, with a committed report and token usage.
These small runs do not measure performance at full 256K context.

Use the platform through `ebd.connections.Engine`. `AgentDefinition` is a
serializable reusable definition. Connections supplies live bindings, scopes,
deadlines, grants and a shared lineage budget; definitions and saved references
do not supply authority. Runtime has no research strategy or EBD-specific logic.

```python
import asyncio
from ebd.connections import Engine, EngineSettings, RunOptions
from ebd.contracts import AgentDefinition, ToolRef

async def main():
    engine = (await Engine.open(EngineSettings())).unwrap()
    try:
        definition = AgentDefinition(
            agent_id="researcher",
            instructions=("Investigate the supplied question. Discover sources, "
                          "fetch and read them, then return a cited Markdown report."),
            model_ref="deepseek-flash",
            profile_ref="deepseek",
            allowed_tools=[ToolRef("web.search"), ToolRef("web.fetch"),
                           ToolRef("document.read")],
            limits={"max_run_seconds": 300, "max_model_seconds": 60,
                    "max_model_calls": 12, "max_tool_calls": 18,
                    "max_tool_attempts": 18},
        )
        registered = engine.register_agent(definition).unwrap()
        result = await engine.run_agent(
            registered, "Your research question", RunOptions(timeout_seconds=300)
        )
        print(result.status, result.recording_status, result.output_ref)
    finally:
        await engine.close()

asyncio.run(main())
```

`local/.env` supplies `DEEPSEEK_API_KEY` and `OPENAI_API_KEY`; process environment
overrides the file. These profiles resolve only when selected. Use
`model_ref="gpt-6-luna", profile_ref="openai"` for the real Responses connector.
Credentials remain live values and are excluded from serialized configuration,
request audits and connector representations. No mock model is configured by
the package. The usage example makes real API calls and consumes the selected
account's allowance.

The platform appends its fixed instruction prohibiting internal, provider-hosted
and implicit search. It exposes registered function tools only. The audit stores
the actual request body digest, safe profile settings, instruction policy,
function-name/schema digests and provider IDs. It does not claim independent
observation of inaccessible provider internals. Model requests use bounded HTTPX
reads, disabled transport retries, no redirects and nonstreaming responses.

## Definitions and validation

Definitions contain agent identity/revision, instructions, input/output schemas,
exact model/profile names, tools, context sources, limits, model settings and
error policy. Unknown provider settings and limits reject admission. Schema
validation is local Draft 2020-12; external schema references are rejected.
The registered revision is immutable, and input/output validation is performed
before a successful result can be returned.

The default output is Markdown text validated as a JSON string. For JSON use
`output_mode="json", output_media_type="application/json"` and the desired
`output_schema`. An `output_contract` may explicitly declare `mode`,
`media_type`, `schema`, `native_enforcement`, `max_bytes` and `delivery`.
Native schema enforcement never substitutes for local validation. Required
arbitrary native JSON enforcement is unavailable in the Chat profiles.

`context_sources` are explicit tagged `artifact`, `snapshot` or `state`
descriptors. Artifacts use UTF-8 byte ranges and bounded reader chunks;
snapshots retain authoritative line/page ranges and continuation;
state selects an exact revision or pins `latest_at_start` once. Bindings must
authorize every source read. These values are rendered as untrusted evidence.

Important defaults are 120 seconds per run, 45 per model request, 30 per tool,
8 model calls, 12 tools/attempts, 4096 output tokens per model call, 1 MiB
request/response/continuation, 64 KiB final output and 512 KiB public result.
Caller and lineage bounds can narrow these. Counts are consumed before dispatch;
children share the same ledger. Token usage missing from a dispatched attempt
remains unknown/partial. Strict token budgeting requires a verified tokenizer
profile and is rejected by these connectors. Automatic model retries/repairs
are disabled; nonzero requests are rejected rather than silently replayed.
`max_context_tokens` applies an advisory UTF-8 byte estimate to rendered context,
including schemas and native history. The request audit records this measurement
as unverified. It can reject a request conservatively and does not prove the
provider's exact token count. The independent request byte cap remains enforced.

Every `model.outcome` contains normalized per-attempt token usage in Storage,
including failed, refused, incomplete, malformed-content and cancelled attempts.
Missing or invalid counts are null; reported zero stays zero. Input/output/total
are preserved as reported, without inferring a missing total. Cache hits,
reasoning tokens and DeepSeek's reported cache misses (`uncached_input_tokens`)
are nullable subsets and never added to the primary totals. A bounded numeric
`provider_usage` projection retains known native detail fields and records invalid
fields or conflicting aliases; arbitrary provider text is excluded.
When a response supplies both input/prompt or output/completion aliases,
normalized input/output fields take precedence. Conflicting native values remain
in the projection with an explicit conflict marker; no value is reconciled by
inventing a new count.

Run `usage.known_subtotals` sums each observed counter independently and leaves a
counter null until reported. `per_attempt_usage_refs` contains
`store_id`, `event_id`, `action_id` and `attempt_id` for acknowledged outcome
records, so consumers can retrieve the actual per-response facts. Missing primary
counts or an unacknowledged outcome make the aggregate partial/unknown. Received
counts remain visible in a failed AgentResult even if recording fails; execution
halts before another dispatch and never claims that those facts were committed.

## Runtime, recording and output lifetime

The module exposes `Runtime.admit(definition,input,binding,context)` followed by
`Runtime.execute(lease)`. Admission has a real shared model reservation, a
single-use live lease and finite expiry. `lease.release()` is idempotent for
known unconsumed reservations. `admission_status` is observational; a serialized
descriptor cannot execute, renew or recover a run. Connections normally owns
this lower-level surface.
Runtime admits at most 32 live or uncertain leases and retains at most 128
observational admission records by default. Expiry releases only known
unconsumed reservations. Evicted terminal records return observational
`unknown`; durable lifecycle history remains in Storage. Trusted construction
can narrow these capacities.

Runtime commits `agent.started`, then a separate `model.intent` before each
provider dispatch. It freezes the actual rendered request and audit first,
waits for the intent receipt, and rechecks current model authority. A whole
native tool batch is validated before its first tool executes. The common
`RecordedToolAction` records tool intent before Storage read or worker launch,
then records bounded outcome descriptors and publication receipts. Agents and
standalone tools use this same helper implementation.

DeepSeek preserves assistant `reasoning_content` and original call IDs in native
Chat continuation. OpenAI preserves complete Responses output items, including
encrypted reasoning, and returns function results using the original `call_id`.
These private histories never become public reasoning reports. Each pending
call must receive one matching ordered result before the next model request.
Malformed/truncated/duplicate native calls execute no tools.

Runtime publishes exact final provider-visible UTF-8 bytes through scoped
Storage before `agent.finished`. It preserves whitespace/newlines. JSON keeps
the raw visible JSON artifact and a separate canonical validated value; identical
representations share one ref. The terminal event contains output refs and
preterminal observations. Its eventual receipt is added to `AgentResult` only
after append. The host then opens a fresh `Engine.open_run_access` session to
read/export output and save a final checkpoint; expired execution authority is
never revived. See the root baseline documentation for that host workflow.

Execution status, recording completeness and publication commitment are
independent. Lost acknowledgements reconcile the same event/operation ID;
unknown remote effects never trigger a replay. Known publication failure may
be completely recorded while execution fails. An unknown publication or missing
outcome receipt remains incomplete. Engine cancellation returns a cancelled
result after bounded cleanup; Python task cancellation records cleanup and is
re-raised. A response completed before caller cancellation retains its actual
usage and response metadata in the cancelled outcome. Its tools and final output
are not dispatched or published. Recording cleanup does no business publication
or external dispatch.

An owned reserved admission cancelled or expired before execution records
`agent.finished` with `start_state="not_started"`, zero dispatch counters and
unknown nullable token usage. It emits no `agent.started` and releases its
reservation. A closed lease or revoked recording grant remains unavailable;
cleanup does not restore that authority.

The default `recoverable_tool_errors=return_to_model` permits a different source
URL or discovery query after a fully recorded read-only source failure, including
a per-worker stream/memory cap, provider quota or source outage. Cleanup must be
confirmed, publication known uncommitted/not applicable and parent/lineage bounds
still active. The failed request cannot be replayed. Global quotas, cancellation,
expired parent deadlines, unsafe protocols, authority failure and uncertain
Storage commitments terminate the run. This policy leaves the worker caps intact.

## Local vLLM Qwen

Register a trusted `ebd.providers.ProviderConfig(provider="vllm", ...)` through
`EngineSettings.profiles` with its exact model alias, HTTP endpoint and explicit
`deployment_manifest`. The manifest declares version, endpoint/model identity,
model/tokenizer revisions, template hash, vLLM version/image, tool and reasoning
parser, thinking mode, structured-output backend, generation-config hash,
server/model/output bounds, hardware and evidence references. Auto tool choice
and its declared parser must be enabled. The client does not install or start a
GPU service or guess a Qwen template. Historical thinking follows the Qwen
profile rather than copying DeepSeek's continuation rule.
The selected endpoint must match the manifest, hash fields are validated, and
each request intersects the manifest's output/context ceilings. These local
checks validate declared configuration; they do not attest the remote server.

Local vLLM Qwen is not deployed on this machine. Its connector/configuration
and controlled protocol checks can run; live deployment verification remains
pending and is not inferred from either API provider's success.

## Verification

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.uv-python'
uv --cache-dir .uv-cache run --locked --offline python -m pytest tests/agent tests/providers -q
```

Owned tests use real SQLite/file Storage for lifecycle, exact-byte publication,
reopen, admission reservations and cancellation. Controlled HTTP transports
exercise native pairing, failures and no-retry behavior. They are fault/protocol
tests, not live model acceptance. Root performs the actual DeepSeek/GPT tool
conversations and the real sourced EBD baseline through Engine, and records
their evidence separately.
