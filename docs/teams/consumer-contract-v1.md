# Orchestrator and console consumer contract v1

Stage 1/2 now adds whole-method execution through
[ResearchRun](../usage/research-service.md) alongside the individual-Agent API.
Methods use [WorkflowContext](../usage/workflows.md), FetchManifest,
SourceManifest and ContextPlan. Canonical implementations live under deepresearch.engine.*;
old imports remain compatible. Frontend lifecycle uses `/api/v1/research-runs`,
SSE/replay and bounded saved-source/context/artifact/report reads. The
[OpenAPI](../api/openapi.json) snapshot includes these additive v1 routes.

The four-module execution platform is the foundation. Python EBD strategies
own phase transitions, agent selection and domain-specific checkpoint formats.
The application RunService owns execution task handles and the console's HTTP
boundary. All persistence and token accounting continue through platform Storage.

New contributors start with [team setup](../team-start.md). Exact Python names
come from the public source and [usage guides](../usage/connections.md); exact
HTTP fields come from the generated [OpenAPI snapshot](../api/openapi.json)
or the running service's `/openapi.json`. The
[HTTP walkthrough](../usage/console-quickstart.md) covers registration through
saved report retrieval without requiring frontend code first.

## Orchestrator boundary

Use Engine registration, `open_agent_session`, public Runtime admission and
execution, and the bound invoker. Explicit `InvocationRule.allow_evidence`
and `InvocationOptions.evidence` let a strategy delegate exact immutable
object ranges/formats and state keys under existing caller authority. Rights
are read-only, revocable, deadline bounded and charged to the shared lineage.
No inferred permission follows from a reference. Read selectors and child
causal IDs are recorded in the parent invocation intent.
`Engine.bind_evidence` lets the trusted host import exact selected reads from
an owned completed Reader/standalone source run into the live parent binding;
a later Writer can then receive those selections through its explicit edge.
The recorded host binding precedes read authority and verifies actual scope.

Run phases and strategy resumability are application responsibilities. A saved
checkpoint is data; no API silently restarts an interrupted model or tool.
The Engine supports known-version state CAS and immutable artifact publication
for an application to define its own recovery protocol.

## Console boundary

Use the service's `/api/v1` DTOs and generated OpenAPI, not Engine internals.
The service accepts a run and returns its identity before terminal output.
HTTP request disconnection does not abandon owned execution. Cancellation
signals the Runtime, and terminal status, recording status and cleanup state
remain separate. The service owns one Engine/Store; clients never open SQLite.

Catalog and incremental event APIs use explicit bounded reads. Reopening
reconstructs saved terminals and exposes unfinished work as interrupted rather
than successful or resumable. Partial model usage is in model outcome events;
terminal usage contains the committed Runtime aggregate and per-attempt refs.
No count is invented when a provider did not report it.

The initial service runs locally with one owner and named model profiles.
Agent registrations are process-local configuration and must be registered
again at startup; existing runs/results remain durable. Multi-user identity,
distributed scheduling, pause/resume and token-by-token output streaming are
outside this v1 contract. Progress polling reads real committed activity.

See [Connections usage](../usage/connections.md) and
[service usage](../usage/service.md) for runnable consumer entry points.

## Team integration ownership

Platform maintainers own Engine, scoped evidence, Storage and the v1 run API.
Orchestrator authors own mission inputs, phase/state schemas, scheduling and
recovery decisions. Console authors own views and clients of the run API.
The existing service starts individual agents; there is no mission-launch
endpoint. A whole-mission console flow needs an application-level contract
agreed by the orchestrator and frontend teams, while run/event/report/usage
integration can proceed against v1 now.

Contributors propose shared-interface changes with affected consumers, exact
fields/signatures and verification to root. HTTP changes regenerate the
OpenAPI snapshot and update examples in the same handoff. Agent definition
revisions are immutable. Preserve integer schema major 1 for compatible
additions; breaking changes require explicit versioning.
