# Agent Container team specification

> **Historical design record.** The original text below describes the earlier
> design/review phase. Its phase holds, chat assignments and proposed API
> signatures are not current instructions. Implementation and live acceptance
> are complete within the documented platform scope; use [Team start](../team-start.md)
> and the [current usage guides](../usage/connections.md) to begin work.
> Do not contact former team chats based on this record.

Status: design assignment. Shared contracts remain **DRAFT** until reconciliation and approval under the shared platform specification. This assignment authorizes design work only.

## Start here

You are the leader of the Agent Container team. Read this specification, [Shared Platform](shared-platform.md), and [Coordination](coordination.md) before beginning work. Use the coordination document for the verified project-manager chat identity, authorized messaging, and reporting procedure; do not infer a destination from a chat title.

Your first deliverable is an interface and implementation design in `docs/teams/designs/agent-container-design.md`. Maintain your team report at `docs/teams/reports/agent-container-status.md` according to the coordination document. Neither file needs to exist before your design session starts.

Propose the interfaces, lifecycle, provider capabilities, and cross-team dependencies. Report unresolved decisions and reconcile them with the project manager. Do not implement source code, install packages, change dependencies, call models, or perform credential-dependent checks until implementation receives explicit approval.

## Purpose

Deliver a reusable container that executes a defined agent against a real configured model and permitted tools, validates its result, enforces execution limits, and produces recordable lifecycle events. Research strategy and orchestration must be able to use the container without editing its internals.

The eventual handoff uses working services and real CLI tools. Mock model replies or placeholder provider adapters are not platform deliverables. The local vLLM deployment is unavailable on this machine, so its live acceptance remains pending until an accessible deployment exists.

## Environment and configuration

- Use uv and Python 3.11 or later; Python 3.11 is the shared development version.
- Follow the repository's `pyproject.toml`, `uv.lock`, and environment instructions. Coordinate dependency changes after implementation is approved.
- Both API credentials are held in `local/.env`. Do not read or print their values during design. Propose configuration references and required variable names without assuming existing names or changing that file.
- Keep credential values out of agent definitions, model envelopes, logs, persisted events, errors, and documentation. Endpoint authentication is injected through the agreed configuration boundary.
- Target OpenAI model ID: `gpt-6-luna`, documented on the [official model page](https://developers.openai.com/api/docs/models/gpt-6-luna). Verify its supported endpoint and tool-calling capabilities during design, along with the selected DeepSeek and deployed Qwen model IDs. Account/deployment access remains unverified. Do not silently select another model.
- Resolve only the provider selected by an execution. An unavailable local backend must not prevent API-based agents from running.

## Ownership

The Agent Container team owns:

1. The agent definition schema and validation.
2. Context assembly and the model/tool execution loop.
3. Provider adapters for DeepSeek API, GPT-6-Luna API (`gpt-6-luna`), and local vLLM serving Qwen.
4. Model message and tool-call translation, provider continuation handling, response normalization, and capability reporting.
5. Output validation, execution limits, cancellation handling, and container/model/tool lifecycle hooks.

Other teams own these boundaries:

| Team | Owns | Container consumes |
|---|---|---|
| CLI Toolset | Tool registration, schemas, subprocess execution, process cleanup, and structured tool outcomes | Permitted tool descriptors and `ToolExecutor` interface |
| Storage and Recording | Durable state/artifacts, checkpoints, scopes, event persistence, and storage mutation hooks | Scoped reads/writes and event recording interface |
| Connections | Configuration resolution, binding to provider factories/tools/storage, permission scopes, execution identity propagation, and permitted agent invocation | A validated binding and execution context |

Provider adapters belong to this team. The Connections team binds configured providers and resolves configuration references; it does not implement provider HTTP protocols. The container calls the bound `ToolExecutor`; it does not launch tool subprocesses itself. The container validates tool permissions and records each tool action's start and outcome exactly once around that invocation. Delegation routes through Connections when configured rather than creating an independent agent registry inside the container.

## Agent definition design

Propose a serializable, versioned definition with these concepts. Field names and concrete types are DRAFT until agreed with the other teams.

| Concept | Required meaning |
|---|---|
| Identity and definition version | Distinguish the reusable definition from each execution and identify the definition used in a recorded run |
| Instructions | Agent role and operating instructions, independent of research strategy |
| Input/output contracts | Schemas, validation rules, and the supported result forms |
| Model reference | A reference resolved by Connections; no embedded credential values |
| Permitted tools | Explicit tool identities and any invocation restrictions |
| Context policy | How task input, history, scoped stored context, and tool results enter the model request |
| Storage and delegation references | Requested capabilities resolved into permitted access by Connections |
| Execution limits | Model/tool-call limits, deadlines, output size, context allowance, and any optional usage budget |

The definition must not embed EBD goals, research rounds, report logic, or baseline strategy. Those are application inputs and orchestration decisions.

## Public interfaces to propose

Specify the complete inputs, outputs, error behavior, resource lifecycle, and asynchronous behavior of these operations. The names below describe design concepts, not approved Python signatures.

| Boundary | Contract to specify |
|---|---|
| Execute an agent | Definition, typed task input, resolved binding, execution context, and terminal agent result |
| Request model generation | Ordered messages, permitted tool schemas, requested output form, model settings, execution limits, and provider continuation |
| Receive a model response | Content, tool calls with correlation IDs, termination reason, optional usage, and provider continuation |
| Invoke a tool | Resolved tool identity, validated arguments, execution context, structured result/error, and cancellation |
| Read/write stored context | Scoped references, versions where relevant, artifact limits, and durable results |
| Emit lifecycle activity | Agreed event envelope, parent/action correlation, payload references, and recording failure behavior |

Keep provider usage fields optional where unavailable. Missing or unsupported accounting is unknown, never fabricated as zero. Define how partial usage and provider failures appear in the terminal result.

Use the shared execution identity fields `run_id`, `agent_id`, `action_id`, `parent_action_id`, and `correlation_id`. An application `mission_id`, if needed, belongs in optional metadata. Specify identity propagation and allocation with Connections without inventing concrete IDs or embedding EBD-specific fields in the common contracts.

### Preserve provider continuation

A plain text reply plus tool names is insufficient for the model envelope. Preserve the provider-supplied continuation information needed for subsequent turns, including opaque reasoning/tool state, ordering, tool-call correlation, and other required native message fields.

Propose an explicit provider-owned continuation envelope or equivalent mechanism. It must:

- Round-trip required fields without flattening or reconstructing them from text.
- Bind continuation to its provider/model and applicable execution so it is not replayed against another provider.
- Permit safe persistence and reload when continuation is supported and approved.
- Keep native provider details out of strategy code while retaining them inside the adapter boundary.
- Avoid requesting or exposing private internal reasoning. Retain only continuation material actually supplied by the provider and needed by its protocol.

Show how a response containing tool calls is followed by the matching tool results and the next model request. Account for providers that impose additional message-pairing or continuation rules. Do not claim that every endpoint accepts one universal message representation unchanged.

## Execution lifecycle

Describe a bounded lifecycle with the following responsibilities:

1. Validate task input, definition, resolved bindings, and required provider capabilities before paid or external work.
2. Assemble the permitted initial context and establish the execution identity, deadline, and accounting state.
3. Record the start of a model action, invoke the selected real provider, and record its outcome.
4. Interpret termination and tool requests through the provider adapter. Validate tool identity, permissions, arguments, and limits before invocation.
5. Record each tool action's start, invoke its bound `ToolExecutor`, and record its structured outcome exactly once. Preserve each result's correlation and ordering, and pass results into provider continuation. ToolExecutor owns process timeout/cancellation/cleanup and JSON/exit parsing.
6. Repeat only within the agreed bounds. When several tools are requested, specify ordering and the conditions under which concurrency is safe.
7. Validate the final output against the declared contract and return a structured terminal result with status, output references, usage, and execution identity.
8. Release provider resources and propagate cancellation through active operations.

Specify when tool/model errors are returned to the model, when execution terminates, and whether validation repair is allowed. Every repair or retry consumes the applicable limits and remains visible in events. Do not silently retry a tool with potential side effects after an ambiguous outcome.

The runtime must distinguish successful completion, execution failure, validation failure, limit exhaustion, timeout, and cancellation. Reconcile the exact status and error taxonomy with shared contracts.

## Context, capabilities, and limits

Propose context accounting and truncation behavior that preserves instructions, required message pairs, tool-call results, and provider continuation. Exact token counts must not be claimed when the selected provider/tokenizer cannot supply them. Large tool output should use the agreed artifact/reference mechanism and an explicit context policy rather than uncontrolled prompt growth.

Prepare a capability matrix grounded in official documentation for each configured endpoint/model. Include tool calling, supported output validation mechanisms, continuation requirements, usage reporting, context limits, streaming if proposed, and cancellation limitations. Mark facts that require a deployed endpoint or account check as unverified.

Capabilities belong to the configured provider/model combination. If an agent requires an unavailable feature, fail binding or preflight with an actionable error; do not drop the requirement or silently switch providers.

Propose a minimal mandatory feature set for the first handoff and label optional features. Include bounded model/tool calls, deadlines, tool/output size limits, and context allowance. Distinguish locally enforced limits from remote cancellation, which may leave a request running or billable after the local wait stops.

## Recording responsibilities

The container originates lifecycle activity for agent execution, model actions, tool invocations, output validation, retry/repair attempts, limits, and cancellation. It owns the automatic tool start/outcome events around `ToolExecutor`, exactly once per action. CLI Toolset returns a structured execution outcome and diagnostic references; it does not independently persist duplicate tool lifecycle events. Connections originates binding/delegation activity; Storage owns persistence and storage commit activity. Correlate these events without duplicating another module's authoritative operation event.

Agree on event names and payloads with Storage. At minimum, the record must support these semantic boundaries:

- Agent start and terminal outcome.
- Model action start and completion/failure/timeout/cancellation outcome.
- Tool action start and completion/failure/timeout/cancellation outcome around its `ToolExecutor` invocation.
- Validation or repair attempt and its outcome.
- Limit or cancellation decision affecting execution.

Include definition version, execution/action correlation, ordered timestamps, model configuration references, safe input/output references, duration, usage when available, and structured error information. Avoid storing credentials or authentication headers. Define recording failure behavior with Storage, including whether external work may start before its start event is durably acknowledged and how interrupted actions are represented.

## Required design deliverables

Submit a design containing:

1. Proposed public contracts with example payloads containing no secrets or invented service identifiers.
2. Agent execution state transitions and a model/tool sequence diagram.
3. Provider adapter responsibilities and the continuation-preserving envelope.
4. Verified provider capability findings with direct official source links, plus unresolved endpoint/model mappings.
5. Context, permissions, limits, errors, cancellation, and recording decisions.
6. Cross-team contract requests and assumptions that require reconciliation.
7. An implementation work breakdown and proposed dependency changes, without making those changes.
8. A verification plan that clearly separates currently available live checks from local vLLM checks pending deployment.

## Eventual implementation acceptance

These checks apply after implementation approval, configured access, and authorization for bounded model use. They are not permission to run calls during this design assignment.

- Define and execute an agent without changing container internals.
- Demonstrate bounded real model requests against DeepSeek and the verified GPT endpoint/model; record which endpoints/models were actually checked.
- Complete a real permitted CLI tool invocation within a model/tool cycle, preserve continuation, and validate final output.
- Persist correlated execution and model events through the agreed Storage interface, with no credential exposure.
- Verify meaningful failures: unauthorized tools, invalid input/output, limits, timeouts, cancellation, and unavailable capabilities.
- Run API agents while local vLLM is unconfigured or unreachable.
- Provide the real configurable vLLM/Qwen connector and document its endpoint requirements. Mark live integration **pending deployment** until tested against an accessible server; do not report it as verified.
- Publish setup and example execution instructions using uv and Python 3.11+, with the validation evidence and remaining limitations.

The design phase ends with a reconciled proposal and status report. Implementation begins only after the project manager communicates the approved contracts and explicit implementation authorization under the coordination procedure.
