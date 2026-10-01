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
