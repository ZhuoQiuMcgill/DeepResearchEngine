# Orchestrator and console consumer contract v1

The four-module execution platform is the foundation. Python EBD strategies
own phase transitions, agent selection and domain-specific checkpoint formats.
The application RunService owns execution task handles and the console's HTTP
boundary. All persistence and token accounting continue through platform Storage.

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
