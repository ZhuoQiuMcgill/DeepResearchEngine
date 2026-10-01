# Storage and recording team specification

Status: **DRAFT — design work only.** The public contracts below require reconciliation with the other module designs and explicit user approval before implementation begins.

Read [shared-platform.md](shared-platform.md) for the common platform contract and [coordination.md](coordination.md) for session registration, reporting, messaging, and approval rules. This specification assigns the storage module; it does not authorize source edits, dependency changes, installations, or implementation.

## Objective

Provide durable, scoped storage and automatic execution recording for a real runnable agent platform. A teammate must be able to use the public storage interface without knowing SQLite tables or artifact file paths. Normal execution must generate its activity history automatically; strategy authors must not manually log every model call, tool invocation, or state change.

The eventual handoff must contain a working SQLite database and real filesystem artifacts, with documented setup, failure behavior, and inspection commands. Mock persistence, in-memory-only implementations, canned responses, and unimplemented interface methods do not satisfy that handoff.

## Ownership and module boundaries

The storage team owns:

- SQLite schema, migrations, transactions, concurrency handling, and lifecycle.
- Scoped JSON state, binary/text artifacts, opaque runtime checkpoints, and append-only activity history.
- The public persistence and query interfaces, authorization checks on storage operations, and persistence acknowledgments.
- Recovery from interrupted artifact creation and interrupted execution records.
- A usable method to inspect saved runs and their correlated actions.

Other modules own:

- Agent definitions, execution loops, checkpoint contents, model usage calculations, and run status decisions: the agent container/runtime team.
- Tool registration, command execution, process deadlines, and cancellation: the toolset team.
- Validated dependency bindings, permitted agent invocation, and execution-context propagation: the connections team.
- Research goals, evidence interpretation, strategy, orchestration, and mission-level scheduling: later application work.

Store domain state as caller-owned data. Do not introduce goal trees, EBD-specific tables, research-round decisions, or an orchestrator into this module. Do not create another model or tool execution loop.

## Proposed public contract

Names are proposals for cross-team reconciliation, not frozen APIs. Use the final common types from `shared-platform.md` once approved.

| Interface | Required behavior |
| --- | --- |
| `StateStore.get(context, scope, key)` | Read a permitted state value and return its version, or a typed missing result. |
| `StateStore.commit(context, mutations, activity)` | Apply validated state mutations and their associated activity record in one SQLite transaction. Support expected-version checks to prevent silent concurrent overwrites. |
| `ArtifactStore.put(context, scope, content, metadata)` | Persist real content and return an opaque artifact reference, size, media type, and content digest. |
| `ArtifactStore.open(context, artifact_ref)` | Return permitted artifact content through the interface, without exposing arbitrary filesystem access. |
| `CheckpointStore.save(context, checkpoint)` | Persist a versioned, serializable runtime checkpoint and related activity. |
| `CheckpointStore.load(context, checkpoint_ref)` | Return the permitted checkpoint and its schema/version metadata. |
| `ActivityRecorder.append(context, event)` | Append a validated event and acknowledge durable persistence. Repeated submission of the same event ID must not duplicate it. |
| `ActivityReader.query(context, filters, cursor, limit)` | Page through permitted run/action history in stable order. |
| `StorageSession.close()` | Flush/close owned storage resources safely and report failures. |

Define scope semantics explicitly: run scope and an explicitly granted shared scope are proposed core options. The research application may define mission-related scopes as application data; mission concepts are not mandatory engine types. Arbitrary caller-supplied scope strings must not create access grants. An opaque artifact reference also does not grant access by itself.

Before approval, specify exact return types and errors for missing objects, denied access, invalid data, version conflicts, unavailable storage, incomplete artifacts, and incompatible checkpoints. Document transaction boundaries and which methods are safe to retry.

## Common record fields

An activity envelope should include `event_id`, event type, schema version, timestamp, and recorded sequence. Proposed common identifiers are `run_id`, `agent_id`, `action_id`, `parent_action_id`, and `correlation_id`, as applicable to the event. An optional `parent_run_id` can link child runs; an optional `attempt_id` should be reconciled with retry semantics. Research-specific identifiers such as `mission_id` belong in optional application metadata, not mandatory core fields. Distinguish logical actions, actual retry attempts, and individual records.

Event payloads should reference large inputs/outputs through stored artifacts. Preserve enough information to connect agent inputs, context sources, model responses, tool results, state versions, and agent outputs. Secrets are excluded; store configuration references and approved redacted metadata, never credential values. A recorded digest is useful for integrity but is not a substitute for content needed to inspect a run.

SQLite assigns stable record order. Timestamps are descriptive and must not be the sole ordering mechanism. Record updates to state as new activity; activity rows themselves are append-only through the public API. Corrections are new events referencing earlier events. This is an application audit history, not a claim of cryptographic tamper-proof storage.

## Recording hooks and ownership

Recording is triggered at the owner of an action. Storage persists records; it does not infer agent behavior by watching files or database changes. The approved container, toolset, and connection paths must invoke the hooks automatically.

| Action boundary | Hook owner | Required record |
| --- | --- | --- |
| Agent run accepted/started | Container/runtime | Definition version, input references, run identity, parent identity, selected binding references. |
| Context assembled | Container/runtime | Permitted source references and versions, context-size metadata, and selected input artifacts. |
| Model request about to dispatch | Container/runtime | Durable intent with request metadata and permitted input references. |
| Model request finishes/fails/times out/is cancelled | Container/runtime | Outcome, response references, usage, duration, and structured error/status. |
| Tool invocation about to dispatch | Container/runtime, before calling ToolExecutor | Durable intent with tool identity, validated input references, and effective limits. |
| Tool process finishes/fails/times out/is cancelled | Container/runtime, using ToolExecutor's structured details | Structured result/error, output references, exit/status information, and duration. |
| Child-agent invocation requested/resolved | Connections, coordinated with runtime | Parent-child relationship, destination agent, input/result references, and outcome. |
| State mutation committed | Storage transaction API | Mutation identities/versions and activity in the same transaction. |
| Artifact made available | Artifact store | Reference, digest, size, ownership/scope, and successful finalization. |
| Checkpoint saved | Runtime requests; storage commits | Checkpoint reference/version and related execution position. |
| Agent output emitted/run terminated | Container/runtime | Validated result, terminal status, usage totals, or failure/cancellation details. |

Reconcile event names and owner assignments with the other teams. There must be one canonical producer for each event, so connections and runtime do not both emit competing terminal records. ToolExecutor and the CLI command return structured execution details; neither duplicates the container's top-level tool lifecycle records.

The recorder must **not record its own `append` calls**, metadata reads, or internal database writes. Artifact persistence and state commits emit their explicitly defined business events without recursively recording the recorder's work. UI polling and history inspection do not generate execution activity by default.

## Durability and failure rules

1. Persist action intent before dispatching an external model/tool operation. If intent cannot be persisted, do not dispatch the operation.
2. Persist the outcome after the operation returns or terminates. If this fails, surface a recording failure with the action identity; do not silently report a fully recorded success.
3. An intent without a terminal outcome remains an incomplete action. It may mean execution never began, is still running, or completed before recording failed. Recovery must not automatically label it as failed or replay it.
4. The action owner records each actual retry attempt. Event deduplication only prevents duplicate records; it does not make external operations exactly once.
5. State mutations and their activity record commit or roll back together within SQLite. Expected-version mismatches produce a typed conflict, not an overwrite.
6. Filesystem artifacts and SQLite are separate durability boundaries. Design a staging/finalization process with recovery so only complete verified artifacts become readable. Do not claim an ordinary file write and database commit are one atomic transaction.
7. Define bounded behavior for lock contention and unavailable disk space. A long-running action must not hold a SQLite transaction open while waiting for a model or tool.

## Artifacts, checkpoints, and local configuration

The database/artifact root comes from the shared local configuration. Configuration policy and secret resolution belong to connections; storage accepts already resolved non-secret storage settings. Do not hard-code developer-specific absolute paths.

Validate artifact paths against the configured root, including traversal and links that could escape it. Agent-supplied filenames are metadata, not arbitrary write targets. Artifact IDs/references should be independent of storage paths.

Checkpoints store opaque versioned runtime state, not live Python handles, open model connections, cancellation objects, or secret values. The runtime defines how a checkpoint resumes. A checkpoint is not sufficient to guarantee safe replay of external side effects.

Keep local databases, generated artifacts, and credentials out of version control according to the shared repository policy. The approved implementation may add the relevant ignore entries; do not change them during this design stage.

## Required joint design: CLI access to storage

CLI tools need to persist source snapshots and read bounded ranges of previously saved content through this module's scoped interface. Storage, toolset, and connections must jointly propose how a separate process receives capability-limited storage access, including standalone CLI use. In-process Python bindings alone do not solve this process boundary.

Specify request/response serialization, capability lifetime, allowed scopes/operations, configuration transport, reliable snapshot locators, bounded read ranges, and failure/recording ownership. Do not send an unrestricted database/artifact-root path as a substitute for scoped access, create an independent snapshot store, or allow standalone commands to silently bypass the storage interface with raw file writes. Propose a concrete workable transport for PM reconciliation; this draft does not prescribe an unreviewed service architecture.

## Design deliverables and coordination

First inspect the shared documents and sibling team specifications. Produce the design proposal at `docs/teams/designs/storage-design.md` and report progress/questions at `docs/teams/reports/storage-status.md` using the coordination format. Those files are not required to exist before the storage team's session begins.

The design proposal must settle schema/versioning, scope grants, exact method signatures, event names, transaction boundaries, artifact finalization/recovery, snapshot locators, bounded content reads, and query pagination. Resolve the CLI scoped-storage transport jointly with toolset and connections. Coordinate the hook matrix with container, toolset, and connections before treating it as an agreed contract. Resolve scope/context type ownership in `shared-platform.md` rather than duplicating definitions across packages.

Use `uv` and Python 3.11+ for the eventual implementation. Dependencies, package paths, and implementation file ownership are decided through the approved shared design. During this stage, perform design/documentation work only; do not install packages, alter dependencies, edit runtime source, call models, or begin implementation until explicitly approved.

## Eventual handoff acceptance

After approval and implementation, demonstrate with real SQLite/filesystem persistence that:

- A real agent run records model calls, real tool process invocations, output, and terminal status without strategy code manually logging them.
- Closing and reopening storage preserves state, artifacts, checkpoints, and the correlated execution history.
- Separate runs obey scoped access; a denied request cannot read another run's state or artifact without a grant.
- Concurrent expected-version writes detect conflicts, and state plus associated event never commit separately.
- A failed intent write prevents dispatch; interrupted outcome recording leaves a visible incomplete action rather than triggering an unsafe automatic replay.
- Interrupted artifact creation recovers without exposing partial content; normal artifact reads return the verified saved content.
- CLI retrieval stores snapshots and reads bounded document ranges through approved scoped storage access, including the documented standalone invocation path.
- Recorder activity does not recursively generate more records.

Provide reproducible `uv run --locked ...` commands, real setup requirements, and readable inspection output. Acceptance details should exercise actual module behavior, including failures, without replacing the handoff with mock replies.
