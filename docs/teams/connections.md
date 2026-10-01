# Connections team specification

Status: **DRAFT — design work only.** Reconcile these proposed contracts with the other team designs, then obtain explicit user design approval before implementation begins.

Read [shared-platform.md](shared-platform.md) for common types and [coordination.md](coordination.md) for session registration, reports, messaging authorization, and approval rules. This specification assigns connections design work; it does not authorize installations, source edits, model calls, or dependency mutations.

## Objective

Let an agent connect to real model, toolset, and storage implementations through explicit validated bindings. Support permitted agent-to-agent invocation through the same execution platform. Teammates should define which dependencies an agent may use without constructing another execution loop or depending on provider-specific internals.

The eventual platform handoff must be runnable against real configured services and actual local modules. Dummy endpoints, canned model responses, mock tool results, and placeholder implementations do not satisfy it.

## Ownership and boundaries

Connections owns:

- Dependency registration and resolution into a validated binding set for an agent run.
- Validation of provider/tool/storage references and permissions before a binding becomes usable.
- Execution-context propagation: run/parent identities, tracing, deadlines, cancellation, and granted capabilities.
- Permitted invocation of another registered agent through the container/runtime's entry point.
- Central local configuration loading and credential-reference resolution, without leaking secret values.
- Lifecycle coordination for connections/resources according to explicit ownership rules.

Other modules own:

- Agent definitions, context assembly, model protocol translation, provider implementations, the model/tool loop, output validation, and run status: container/runtime.
- Tool discovery/registration, input/output schemas, actual process invocation, process cancellation, and structured process execution details: toolset. Container owns top-level tool intent/outcome hooks.
- Database/filesystem implementation, scoped access enforcement, persistence, checkpoints, and event querying: storage.
- Scheduling research work, deciding agent order, EBD strategy, mission orchestration, and mission-level policy: later application work.

Do not add a second model client, tool process launcher, scheduler, or agent execution loop. A connection resolves and constrains an existing capability; its implementation owner remains the relevant module team.

## Two kinds of connection

### Dependency binding

An agent definition refers to a named model configuration, a permitted tool set, permitted storage scopes, and context sources. Resolve these references into an immutable binding set for a run. Record non-secret binding identities/versions so a saved run can show what it used.

The current tool execution boundary is the project's CLI toolset: real registered commands, UTF-8 JSON on standard input/output, and execution without a shell. Connections must consume that public interface, not launch those commands itself. CLI tools have replaced MCP in the user's scope; do not add an MCP client/server to this assignment.

Resolve the container team's real DeepSeek API, GPT-6-Luna API, and local vLLM Qwen provider implementations by their configured names. Connections does not implement provider request formats. The local Qwen service is not deployed here; preserve that live-validation limitation in the eventual handoff until deployment is available.

### Agent invocation

Allow an authorized caller to invoke a registered destination agent with typed input and receive its validated result. This creates a child run and calls the existing runtime. The connection declares who may invoke whom; the invoking strategy/runtime decides when to invoke.

This is an explicit call-and-result interface. Do not add hidden broadcasts, an autonomous message bus, arbitrary peer discovery, or an orchestration language to the first platform handoff. Streaming execution events may be exposed through the runtime contract without becoming another scheduling system.

## Proposed public contract

Names and shapes are drafts to reconcile, not frozen API requirements.

| Interface | Required behavior |
| --- | --- |
| `ConnectionRegistry.register(definition)` | Register a named dependency definition owned by the appropriate module, rejecting conflicting identities. |
| `ConnectionResolver.bind(agent_definition, context)` | Validate referenced dependencies and permissions, then return the effective immutable binding set. |
| `BindingSet.model` | Reference the container/runtime's real model capability; provider details remain behind that module's interface. |
| `BindingSet.tools` | Expose only the effective registered tool permissions through the toolset interface. |
| `BindingSet.storage` | Expose storage operations with validated scopes/grants, preserving storage's own enforcement. |
| `AgentInvoker.invoke(destination, input, parent_context)` | Validate permission, create a child execution context, invoke the runtime, and return its typed outcome. |
| `ConnectionSession.close()` | Release only resources the session owns, coordinating shared resources and in-flight runs. |

Resolve exact registration-time versus run-time checks, sync/async signatures, result types, lifecycle rules, and typed errors before approval. Configuration presence alone must not be reported as a successful live connection. State whether readiness checks are local validation or actual provider/tool reachability checks and what they cost.

## Execution context and propagation

Use one shared context contract from `shared-platform.md`. Proposed identifiers are `run_id`, `agent_id`, `action_id`, `parent_action_id`, and `correlation_id`, together with a deadline, a cancellation signal, permission grants, and applicable execution-limit references. Reconcile optional `parent_run_id` for child linkage and optional `attempt_id` with actual retry semantics. Research-specific values such as `mission_id` belong in optional application metadata, not mandatory engine fields.

Distinguish serializable context metadata from live execution handles. Cancellation objects and open resources do not belong in stored JSON or checkpoints. If deadlines are persisted, use an explicit portable representation and rebuild local timers safely on resume.

Dependency calls preserve the caller's identity and effective permissions. A child invocation creates a new `run_id`, retains `correlation_id`, and preserves linkage through the originating `parent_action_id` and any approved `parent_run_id` field. Its deadline cannot exceed the parent deadline; parent cancellation propagates to the child and downstream tool/model execution according to each owner's documented cancellation semantics.

Effective child permissions are bounded by caller delegation authority and the destination agent's declared permissions. A destination declaration must not enlarge what the caller is allowed to delegate. Storage may support explicit shared-scope grants; retaining a correlation or application identifier does not itself grant data access.

Design an explicit policy for nesting/cycles so permitted agent invocation cannot recurse without a bound. The runtime owns enforcement of run limits; connections validates allowed destinations and propagates the applicable limit context. A child run must not reset applicable inherited execution limits. Research mission budgets and scheduling remain application responsibilities.

## Recording responsibility

Use the storage team's append-only recorder through agreed action-owner hooks. Connections must record binding resolution failures and agent invocation relationships when they are meaningful execution activity. The container/runtime is the canonical producer of agent, model, and top-level tool lifecycle events. ToolExecutor returns structured execution details for the container to record.

An agent invocation intent must be durably recorded before dispatching the child. Resolve whether the runtime's run-accepted event also satisfies this intent requirement or whether a distinct parent invocation event is needed. Agree one producer and correlation rule; do not duplicate the same event in two modules.

After the child terminates, record the parent invocation outcome. A missing outcome remains visible as incomplete, and does not authorize a blind retry. Capture configuration identities and sanitized diagnostics; never serialize credential values, authorization headers, or credential-bearing URLs into events.

All normal engine actions must pass through the approved runtime/toolset/storage interfaces. Connections must not expose an unrestricted escape hatch that lets an agent call a provider or tool without permissions, limits, and recording. This is an API boundary guarantee; it does not claim Python code in the same process is an operating-system sandbox.

## Local configuration and credentials

Centralize local configuration policy for model endpoints, registered tool configurations, storage roots, and credential references. Prefer named references in agent definitions so secret values do not appear in reusable agent specifications or stored execution data.

The user has chosen the existing `local/.env` as the local credential/configuration source. Specify its precedence relative to process environment and non-secret configuration; do not independently create competing root and nested configuration loaders or rewrite the existing secret file. Include a checked-in example with placeholder variable names after approval, never populated credentials.

Resolve secrets only when needed by their implementation owner and keep secret values out of representations, exception messages, subprocess diagnostics, run reports, and checkpoints. Do not print or inspect existing secret values during design work. The model implementation receives the configuration it needs; connections must not duplicate provider request formatting or authentication logic.

Missing or invalid required configuration produces an actionable typed error naming the configuration key/reference, not its value. Optional connections may remain unbound only when the agent definition does not require them. Fail before starting work when a required binding is unavailable.

## Required joint design: CLI scoped-storage capability

The CLI tools' separate processes need capability-limited access to Storage for snapshot persistence and bounded reads. Connections, storage, and toolset must jointly design the transport/serialization for this access, including standalone CLI invocation. Merely resolving a Python object in the parent process does not make it usable in a child process.

Propose the capability representation, permitted operation/scope set, lifetime, configuration delivery, and process identity correlation. Configuration transport must avoid leaking credentials or granting unrestricted filesystem/database access. Storage retains authorization and commit-event ownership. ToolExecutor retains process launching. Connections supplies the approved binding/capability; it does not invent a second snapshot store or permit raw file writes that bypass Storage.

## Failure and lifecycle rules

- Distinguish unknown dependency, invalid binding, denied invocation, incompatible contracts, unavailable dependency, deadline exceeded, cancellation, and child execution failure.
- Preserve causal identifiers and structured downstream errors while removing sensitive details.
- Do not add retries at multiple layers. Model retry policy belongs to its runtime/provider owner; reconcile tool retry ownership with container/toolset. Connections does not silently replay either.
- Define whether a registry/session owns each resource or borrows it. Closing one agent binding must not unexpectedly terminate another agent's shared dependency.
- Define shutdown behavior for in-flight child runs. Completion/cancellation/failure must resolve through the runtime rather than abandoning unresolved calls.
- Reachability can change after initial validation. Return real execution failures through the typed interface instead of assuming a previously bound dependency remains healthy.

## Design deliverables and coordination

Write the design proposal to `docs/teams/designs/connections-design.md` and progress/questions to `docs/teams/reports/connections-status.md` using `coordination.md`. These files do not need to exist before the team's session begins.

The proposal must settle exact binding definitions, registration/resolution APIs, effective-permission rules, child context propagation, invocation result/error behavior, cancellation/deadline semantics, recording ownership, configuration precedence, and resource lifecycle. Propose the CLI scoped-storage transport jointly with storage/toolset. Coordinate with container/toolset first; storage may design in parallel, with common types reconciled centrally.

Use `uv` and Python 3.11+ for the eventual implementation. Package layout and dependencies must follow the approved shared design. During this stage, do not install dependencies, edit runtime source, mutate project dependencies, call models, or implement the contracts until explicitly approved.

## Eventual handoff acceptance

After design approval and implementation, supply reproducible `uv run --locked ...` commands that demonstrate:

- A defined agent binds to a real model, actual registered CLI tools, and persistent storage using named configuration references.
- Invalid/missing bindings and denied tool/agent destinations fail with useful structured errors before the prohibited action executes.
- Agent A invokes permitted agent B through the runtime; B receives typed input, a child run identity, bounded permissions, and returns a validated result.
- Parent/child and downstream actions are correlated in the durable activity history without duplicate event production.
- Parent deadlines/cancellation propagate through the documented execution path; nested invocation cannot evade inherited limits.
- Storage scopes remain enforced through both direct dependency use and delegated child invocation.
- CLI processes receive scoped storage capability through the approved transport, including the documented standalone path; tools do not receive unrestricted store access.
- Shared resource shutdown does not unexpectedly break another agent's active binding.
- Saved definitions, events, errors, and reports contain configuration references rather than credentials.

Demonstrations must use real implementations. Keep them small and explain actual credentials/services/setup requirements; do not replace external work with mock replies for the teammate handoff.
