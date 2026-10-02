# Model-free Workflow sessions

Canonical imports are `ebd.engine.connections` and `ebd.engine.contracts`;
older paths below remain compatibility imports. A trusted host may pass
`cleanup_state_keys=("application.failure-state",)` to `open_workflow_session`.
Only those exact same-run keys receive `state.cleanup`; default sessions have
no cleanup state grant. This permits bounded failure-projection CAS with the
original ledger after cancellation and no new artifact/model/tool effects.

A trusted Python Workflow owns its scheduling, nodes and Hooks. Engine supplies a
bounded run over the existing Toolset, Storage, recording and child invoker.
The root has `context_kind="workflow"` from provisioning onward,
`BoundSession.definition=None`, no AgentDefinition, provider configuration,
provider factory, credential resolution or `model.generate` grant.

The public APIs are:

```python
await engine.open_workflow_session(
    *, tools: tuple[ToolRef, ...] = (),
    invocation_rules: tuple[InvocationRule, ...] = (),
    options: RunOptions | None = None,
) -> Result[BoundSession]

await engine.run_workflow_tool(
    session: BoundSession, tool_ref: ToolRef, arguments: JsonObject,
) -> ToolResult

await engine.emit_workflow_event(
    session: BoundSession, kind: str, payload: JsonObject, *, cleanup: bool = False,
) -> Result[EventReceipt]
```

`Result` is the existing `Ok`/`Err` envelope. Tools and edges must be typed tuples;
options must be a plain `RunOptions` record. Defaults select no tools or child
edges. Policy/options are copied before binding; caller mutation cannot widen a
session. Public `WorkflowPolicy` records the selected ToolRefs and InvocationRules
in `binding.resolved`; it supplies the invoker's workflow tool policy. Creating a
policy record alone grants no authority.

## Open, execute and finish

```python
from ebd.connections import Engine, EngineSettings, RunOptions
from ebd.contracts import ToolRef

engine = (await Engine.open(EngineSettings(storage_root="local/workflow-store"))).unwrap()
try:
    async with (await engine.open_workflow_session(
        tools=(ToolRef("web.fetch"), ToolRef("document.read")),
        invocation_rules=(),
        options=RunOptions(timeout_seconds=60, limits={"tool_calls": 2}),
    )).unwrap() as session:
        (await engine.emit_workflow_event(session, "workflow.accepted", {
            "workflow_id": "fetch-and-read", "revision": 1,
        })).unwrap()
        fetched = await engine.run_workflow_tool(session, ToolRef("web.fetch"), {
            "url": "https://example.org/",
        })
        status = fetched.status
        if fetched.status == "succeeded" and fetched.recording.get("status") == "complete":
            read = await engine.run_workflow_tool(session, ToolRef("document.read"), {
                "snapshot_ref": fetched.result["snapshot_ref"],
                "range": {"kind": "lines", "start": 1, "end_exclusive": 3},
            })
            status = read.status
        (await engine.emit_workflow_event(session, "workflow.finished", {
            "status": status,
        }, cleanup=True)).unwrap()
finally:
    await engine.close()
```

Every tool call uses the canonical `RecordedToolAction`: committed `tool.intent`
precedes worker execution, followed by `tool.outcome` or a recorded rejection.
Calls have distinct action/attempt IDs and no provider/model call identities.
They share the Workflow's existing run, scope, ledger, deadline, cancellation
signal and leases. Calling again does not reset allowances. Exact ToolRef
selection includes the revision; unselected tools cannot dispatch.

Only this Engine's issued live Workflow session is accepted. Copied, foreign,
closed, expired, cancelled or revoked sessions cannot start tool work or append
ordinary Workflow events. Scoped Storage is available through `session.binding.storage`
with `session.context`; references do not confer rights to other runs. Selected
tool capabilities grant only the needed search/fetch network operations.

## Child Agent edges

Register child AgentDefinitions, then select exact registered destinations:

```python
from ebd.connections import InvocationRule

# writer is a RegisteredAgent returned by engine.register_agent(...).
# Its requested tools must be contained in both the Workflow selection and edge.
session = (await engine.open_workflow_session(
    tools=(ToolRef("document.read"),),
    invocation_rules=(InvocationRule(
        writer.ref, allowed_tools=("document.read",),
        allow_model=True, allow_evidence=True, allow_export=True,
    ),),
    options=RunOptions(timeout_seconds=120, limits={"model_calls": 4, "tool_calls": 4}),
)).unwrap()
try:
    outcome = await session.binding.invoker.invoke(
        session.context, writer.ref, "Write from the selected evidence.",
        # Optional InvocationOptions(evidence=EvidenceBinding(...)) supplies exact reads.
    )
finally:
    await session.close()
```

Edge validation precedes Workflow provisioning. Unknown destinations, duplicate
selections, expanded tool requests, invalid timeouts and limits fail closed.
Invocation rechecks tool selection, live rights, depth, descendant allowances
and explicit model/export/evidence/onward permissions. A child uses its real
AgentDefinition/provider binding and the existing Runtime/invoker, with both
parent causal IDs and the shared lineage ledger. The Workflow itself receives
no model grant and no fabricated Agent terminal. Workflow roots add no fictitious
Agent ID to ancestry. Child allowances can only narrow the root's remaining budget.

Snapshots retained in the Workflow scope require explicit `EvidenceBinding` read
selectors plus `InvocationRule.allow_evidence=True` before a child can read them.
For previously saved sources, the existing `Engine.bind_evidence` host selection
also accepts a live Workflow session. See [Connections](connections.md) for
bounded read selectors and artifact result export.

## Bounded Workflow facts and cleanup

`WORKFLOW_EVENTS` exports this exact allowlist:

- `workflow.accepted`
- `workflow.node.started`, `workflow.node.completed`, `workflow.node.failed`
- `workflow.hook.observed`, `workflow.hook.decision`, `workflow.hook.failed`
- `workflow.context.selected`, `workflow.source.ready`, `workflow.measurement`
- `workflow.finished`

The producer is `workflow`. Each call creates one event ID and preserves its
canonical digest for lost-acknowledgement status reconciliation. A committed
receipt is returned only for the acknowledged event or its exact committed
status. Unknown/uncommitted status remains an error; Engine does not append a
replacement event or repeat execution. A new API call is a new fact, so callers
must not automatically retry an unknown commit result as a new event.

Payloads must be JSON objects, finite and at most 32 levels deep. Their canonical
UTF-8 encoding is capped at `WORKFLOW_EVENT_MAX_BYTES` (16,384 bytes); the full
event also obeys Storage's 64 KiB envelope cap. Payloads are detached before
append. Put large evidence in scoped Storage and record its reference/digest.
Events use the same `storage_writes`, `status_reads` and read-byte ledger as the
run; no recording budget is replenished.

`cleanup=True` permits only the exported `WORKFLOW_CLEANUP_EVENTS`:
`workflow.node.completed`, `workflow.node.failed`, `workflow.hook.failed`,
`workflow.finished`. It allows completion/failure facts after cancellation or
deadline expiry through a five-second recording context with the same ledger,
grants and active lease. It cannot start work, restore revoked/closed authority
or authorize business operations. Engine shutdown permits this recording while
it drains active work and Storage remains open.

The Workflow runner validates its own lifecycle/status payloads and emits
`workflow.finished` before closing the session. Closing only releases authority;
it does not infer success or manufacture a terminal. `Engine.describe_run(RunRef)`
selects `workflow.finished` for Workflow runs, including after Engine close/reopen.
An absent terminal stays absent; reopening grants inspection authority without
resuming execution or restoring old sessions.

Storage must accept `workflow` in its context validation and run-catalog filters;
the Toolset worker must accept it in its private invocation envelope. These
shared contract changes are owned by the parent integration, outside the
Connections implementation paths.
