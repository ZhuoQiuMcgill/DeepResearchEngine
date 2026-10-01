# Shared platform design brief

Status: DRAFT for team design review. This records the user's scope and
proposes boundaries; it does not freeze Python types or authorize runtime
implementation.

Research update: PM selected DDGS 9.16.0 (replaceable best-effort search),
HTTPX 0.28.1, Trafilatura 2.2.0, and pypdf 6.19.0 for the initial tool design.
Expanded research changed the discovery design to explicit Yahoo primary with
corrected Google as a gated fallback, plus separate Crossref/OpenAlex scholarly
tools. See `decisions.md`; representative availability and live URL fidelity
still need acceptance evidence.
The common interfaces are consolidated in `platform-contract-v1.md` for
review. Runtime implementation authorization remains outstanding.

## User requirements

- Build a usable basic engine so other group members can implement strategies.
- Four independent modules: Agent Container, CLI Toolset, Storage, Connections.
- Use uv and Python 3.11+; Python 3.11 is the shared development target.
- Hand off real, runnable functionality; no mock replies or placeholder-only modules.
- Support real DeepSeek API, GPT-6-Luna API, and local vLLM Qwen provider adapters.
- API credentials already exist in `local/.env`; keep their values private.
- The local Qwen service is not deployed here; do not claim live verification.
- Finish design before implementation.
- Research free, open-source web search and fetch tools in the CLI team; PM selects the combination after its report.

## Module boundaries

| Module | Owns | Consumes |
| --- | --- | --- |
| Agent Container | Agent definitions, context assembly, model/tool loop, real provider adapters, validation, execution limits, agent/model/tool lifecycle hooks | Bound providers, ToolExecutor, scoped storage and recorder, invocation bindings |
| CLI Toolset | Tool catalog and schemas, ToolExecutor subprocess execution, concrete CLI tools, deterministic retrieval/extraction | Execution context and scoped Storage access supplied through bindings |
| Storage | Durable state, artifacts/snapshots, checkpoints, scoped access, append-only activity persistence, transactions | Events emitted by action owners and writes through its interface |
| Connections | Validated bindings, central configuration/secret loading, permissions/context propagation, permitted agent invocation | Module interfaces and Agent Container execution entry point |

Internal modules use Python interfaces. Tools execute as registered CLI
processes. Connection bindings select implementations without duplicating
their execution logic. The core engine has no EBD goal-ranking, Finance,
Reader, Writer, or mission scheduling logic.

## Draft common contracts

Teams should propose fields, operations, failure semantics, and concrete
examples for these contracts. Names below are working names.

| Contract | Required meaning | Lead / reviewers |
| --- | --- | --- |
| AgentDefinition | Identity/version, instructions, input/output schemas, model reference, allowed tools, storage access, context policy, limits | Container / Connections |
| ModelRequest / ModelResponse | Conversation/input items, tool definitions/calls/results, completion state, usage, opaque provider continuation state | Container / Connections |
| ToolDefinition / ToolResult | Name, description, schemas, registered argv, limits, structured result/error and execution details | Toolset / Container, Storage |
| ExecutionContext | Run/agent/action/parent/correlation identifiers, deadline, cancellation, scoped permissions | Connections / all teams |
| ExecutionEvent | Event/action identity, event kind, status, timestamp, input/output references, duration/usage/error as applicable | Storage / action owners |
| Storage interface | Scoped state access, artifact commit/read, event append/query, checkpoints, transaction semantics | Storage / all teams |
| BindingSet / agent invocation | Resolve provider/tool/storage access and explicitly permitted child invocations | Connections / Container |

Represent unknown usage as unknown. Preserve provider continuation data
needed for actual tool conversations; a text-only common response is
insufficient. The exact Qwen model/server configuration is still to be
specified. Research-specific identifiers such as mission IDs belong in
application metadata, rather than being mandatory core-engine concepts.

Proposed common identifiers are `run_id`, `agent_id`, `action_id`,
`parent_action_id`, and `correlation_id`. Child-run linkage can use optional
`parent_run_id`; retry attempts may need an `attempt_id`. Reconcile exact
allocation, optionality, and event relationships before freezing the types.

## Tool execution and recording

Container decides whether a requested tool is allowed and records intent
before dispatch. Toolset's ToolExecutor executes fixed registered argument
arrays without a shell, exchanges one UTF-8 JSON request/result, handles
timeouts/cancellation/process cleanup, and interprets errors/exits. Container
records the result, failure, timeout, or cancellation afterward. Diagnostics
belong on stderr. Agents cannot supply arbitrary shell command strings.

One action owner emits each top-level activity; avoid duplicate recording
by Container, ToolExecutor, and CLI command. Container owns agent/model/tool
lifecycle hooks; Connections owns delegation/binding activities; Storage
owns state/artifact commit events. Storage persists these automatically.
Strategy authors should not need to manually log ordinary execution.

Persist state changes and their corresponding commit events in one Storage
transaction. Intent/outcome recording does not make remote side effects
atomic or guarantee exactly-once execution. Interrupted actions remain
identifiable as unfinished. The recorder must not recursively record its
own event appends.

## Cross-team design questions to resolve

1. Concrete request/result/error schemas, async/cancellation behavior, retry ownership, and version compatibility.
2. How a CLI process receives scoped artifact access through Storage's interface, including standalone invocation. Do not silently bypass Storage with a second snapshot store.
3. How child runs inherit and restrict context/permissions without hidden scheduling.
4. How provider-specific continuation is persisted and restored without leaking credentials.
5. What reliable snapshot locators and bounded document-read ranges look like.
6. Which free, open-source search/fetch combination meets the CLI research criteria.

PM reconciles the proposals in a shared contract revision. User approval of
the completed design precedes implementation assignments. If a later direct
user instruction authorizes implementation, report the change to PM and
follow that instruction.

## Eventual platform handoff

Each module needs documented runnable entry points, real integration
examples, meaningful checks, explicit errors, and known limitations. Shared
dependency/lockfile changes are coordinated by PM. A fake response is not
evidence that a live integration works. The undeployed local provider is
documented as pending live validation; the two configured API providers
must be validated when implementation and API smoke tests are authorized.
