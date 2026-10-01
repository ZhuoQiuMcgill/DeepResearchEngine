# Engine composition and data access

The Engine is the trusted host composition root. It opens real SQLite/file
Storage, registers fixed CLI tools, lazily resolves model credentials and
binds the independent Runtime. Strategy belongs in an application.

```python
import asyncio
from ebd.connections import Engine, EngineSettings, RunOptions
from ebd.contracts import AgentDefinition, ToolRef

async def main():
    engine = (await Engine.open(EngineSettings())).unwrap()
    async with engine:
        agent = engine.register_agent(AgentDefinition(
            "researcher", "Research the task using registered tools.",
            allowed_tools=[ToolRef("web.search"), ToolRef("web.fetch"),
                           ToolRef("document.read")],
        )).unwrap()
        result = await engine.run_agent(agent.ref, "Your research question",
                                        RunOptions(timeout_seconds=120))
        print(result.status, result.output_ref)

asyncio.run(main())
```

Named defaults are `deepseek`/`deepseek-flash` and
`openai`/`gpt-6-luna`. Key variable names are case insensitive in
`local/.env`; values stay in live provider bindings. vLLM needs an explicitly
registered `ebd.providers.ProviderConfig` with its deployment manifest; see
[agents.md](agents.md). Profiles pin model IDs and endpoints. Public run
options cannot substitute a provider or create authority.

`Engine.run_tool(ToolRef(...), arguments, RunOptions(...))` uses the same
Runtime recorded tool helper without opening a provider. Reading a snapshot
from an earlier standalone run requires `ToolRunOptions(source_run_ref=...,
read_objects=(SnapshotReadRequest(...),))`; the host verifies ownership of
that run and grants only the selected snapshot/range. A guessed reference
does not authorize access.

Register trusted `InvocationRule(destination=AgentRef(...), allowed_tools=...,
allow_export=True, limits=...)` edges with an agent. Its live binding exposes
`binding.invoker.invoke(caller_context, destination, input, RunOptions(...))`
at the Python boundary. Invocation is explicit; the Runtime does not add a
model-selected delegation tool or scheduler. Child budgets charge the same
lineage owner and also enforce local caps. Cycles, excessive depth,
undelegated tools, expired/cancelled authority and revoked export rights fail
before the affected work. Required artifact export uses scoped Store read/put
and commits before the parent invocation outcome. Child terminal facts remain
visible if parent export fails.

For a Python strategy that manages explicit calls, use
`await engine.open_agent_session(agent_ref, RunOptions(...))` to obtain a
recorded root binding without dispatch. In its async context manager, invoke
the allowed child through `session.binding.invoker` and `session.context`, or
call `engine.runtime.admit(session.definition, input, session.binding,
session.context)` and `engine.runtime.execute(admission)`. This uses the same
real modules and grants as `run_agent`; close the session when finished.

Completed Runtime bindings expire. Open a fresh data session:

```python
from ebd.connections import RunAccessRequest, ArtifactReadRequest
from ebd.contracts import RunRef

access = (await engine.open_run_access(
    RunRef(engine.storage.store_id, result.execution["run_id"]),
    RunAccessRequest(read_objects=(ArtifactReadRequest(result.output_ref),)),
)).unwrap()
async with access:
    reader = (await access.storage.artifacts.open(
        access.context, result.output_ref,
    )).unwrap()
    try:
        chunk = (await reader.read(access.context, 65536)).unwrap()
    finally:
        await reader.aclose(access.context)
```

Continue reading until `chunk.eof` for larger outputs. Access selectors bound
objects, ranges, byte limits, history filters and publication media/formats.
`PublicationRequest` explicitly permits citation manifests, terminal
checkpoints or review exports. Use `access.identity_service.allocate()` for
stable mutation IDs; identical delivery retains its identity. Created objects
become readable only when `read_created=True` was granted. Historical status
uses exact `EventStatusRequest`/`OperationStatusRequest` observer grants and
keeps a fresh host action. These sessions expose no model, executor, invoker
or admission and cannot restore execution budgets.

OpenAlex anonymous admission defaults to closed. A trusted application may
set `EngineSettings(openalex_admission=True)` for its initial local budget.
The Engine persists reservations and settlement through normal Storage state
before/after dispatch and restores them on reopening. Unknown in-flight spend
stays blocked; reopening never supplies fresh credit. Provider headers may
further narrow the local limits. Search availability remains best effort.

These module capabilities constrain normal platform paths. Arbitrary Python
or same-user executables are not an operating-system sandbox.

## Shared evidence for child agents

An invocation edge opts into read-only evidence delegation with
`InvocationRule(..., allow_evidence=True)`. A Python strategy selects exact
objects and keys at each invocation. The Engine verifies the object's actual
scope and attenuates the caller's live authority before child admission.

```python
from ebd.connections import EvidenceBinding, InvocationOptions, SnapshotReadRequest

outcome = await session.binding.invoker.invoke(
    session.context, reader_ref, task,
    InvocationOptions(timeout_seconds=90, evidence=EvidenceBinding(
        read_objects=(SnapshotReadRequest(
            snapshot_ref, {"kind": "lines", "start": 1, "end_exclusive": 20},
            max_text_bytes=8192,
        ),),
    )),
)
```

The Reader can use its registered `document.read` tool against that saved
range. A snapshot/artifact/checkpoint reference in task data alone grants
no access. `ArtifactReadRequest` pins a byte range and cumulative allowance;
`CheckpointReadRequest` pins accepted formats and a byte allowance.
`StateReadRequest(scope, key, max_bytes)` grants read access to one selected
key, including retained historical versions. It grants no state writes or
key enumeration. Copy a value into an immutable artifact if a child must
receive a fixed version only. No parent continuation token is transferred.

At most 64 selectors fit in a bounded 64 KiB binding. Object read bounds
must narrow the caller's grants. Child deadlines and shared lineage budgets
still apply; parent grant revocation also revokes the delegated binding.
Onward delegation requires both `allow_onward` and another explicit evidence
edge. The parent invocation intent records the selected evidence manifest.

To send a Reader's retained source to a later Writer, the trusted orchestrator
first binds selected source authority to its live parent session:

```python
evidence = EvidenceBinding(read_objects=(source_selector,))
receipt = (await engine.bind_evidence(
    parent_session, reader_outcome.child_run, evidence,
)).unwrap()
writer_outcome = await parent_session.binding.invoker.invoke(
    parent_session.context, writer_ref, writing_task,
    InvocationOptions(evidence=evidence),
)
```

`bind_evidence` verifies the selected same-owner source run, the actual object's
scope and the exact live target binding. It records `binding.evidence` before
installing only selected read rights. Failed or unknown recording grants no
access. The source session may have finished; the host issues fresh authority
under the parent deadline. This also permits explicit source import from an
owned standalone fetch run. It grants no source writes, history or execution
budget. Browser requests cannot manufacture these bindings.

## Host discovery and incremental progress

The public host APIs are `list_agents()`, `list_profiles()`,
`list_runs(filters, cursor, limit)`, `describe_run(RunRef)`,
`list_run_objects(RunRef, cursor, limit)`, `read_run_state(RunRef, key, version)`,
and `query_run_events(RunRef, after_seq, limit, include_descendants)`.
The asynchronous methods return the common `Ok`/`Err` envelope. Every request
uses fresh bounded host authority and validates the run's owner. Model
credentials and endpoints are absent from the profile catalog. Registration
is a live Engine catalog; applications register definitions at startup or
through the service, including after reopening.

Run and object catalog cursors preserve an immutable watermark; start a
fresh query to discover later entries. Event polling instead returns
`next_after_seq`, `has_more` and `high_water_seq`. Reuse `next_after_seq` on
the next request to read later committed events. Sequence numbers belong to
the Store clock and need not be consecutive for a selected run. Root lineage
polling captures a watermark before enumerating authorized child scopes, so
a child created concurrently cannot be skipped. A child cannot request its
siblings through the root selector. Terminal reconstruction requires the
saved `agent.finished` event; absent terminal recording remains incomplete.

For browser applications use the [run service](service.md). It owns real
execution tasks and exposes versioned HTTP DTOs; a browser receives no
ExecutionContext, GrantSet or database handle. Checkpoint storage does not
implement execution pause/resume or automatic restart.
