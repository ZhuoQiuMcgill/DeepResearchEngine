# Develop a Workflow method and optional Hooks

A Workflow is a reusable research method. Its `run(context, task_input,
parameters)` composes deterministic components, selects evidence and invokes
pinned Agent roles through `PlatformPort`. `WorkflowRunner` supplies the method
root node; `WorkflowContext.node(...)` supplies each logical component's lifecycle.
The application service owns admission, cancellation, durable terminal recording
and cleanup. Method and Hook implementations receive no Engine, Storage client,
provider, credentials or HTTP request.

## Run the examples without credentials

From the repository root, use the locked Python environment:

```shell
uv run --locked python examples/workflow_method.py
uv run --locked python examples/workflow_hooks.py
uv run --locked python examples/workflow_hooks.py --no-hooks
```

These scripts run `example.echo@2`, a model-free tutorial method made from
selection, publication and checkpoint components. The built-in `example.echo@1`
remains a separate pinned implementation. The tutorial uses revision 2 because
its component code and method manifest differ from revision 1.

All three commands use real Storage in isolated temporary directories. They
make no model, tool, discovery or network requests. No credential file needs to
be configured. Each command checks the committed Workflow terminal, successful
nodes, saved report bytes/hash, result manifest, checkpoint and absence of model
usage. It then closes the research service followed by the caller-owned Engine,
checking `complete`, `errors` and `unconfirmed_resources` for both. The default
Store is removed only after this closure. Incomplete execution, recording,
publication or cleanup raises an error rather than printing successful output.

Retain saved objects for inspection by selecting a Store:

```shell
uv run --locked python examples/workflow_method.py --store local/workflow-method-example
uv run --locked python examples/workflow_hooks.py --store local/workflow-hooks-example
```

A Store has one live owner. Repeated invocations use new `client_request_id`
values and append distinct runs; they do not resume an old execution. Returned
artifact/checkpoint references identify objects in that Store. Report text and
cleanup evidence are printed as JSON.

The method example prints `Hello from a model-free Workflow.`. The Hook example
starts from three named parts and uses a selection Hook to keep the last two in
reverse order, producing `Third candidate` followed by `Second candidate`.
`--no-hooks` runs the complete same method and keeps all three in original order.
Use `--message` to supply your own text and `--keep 1` to narrow the selection
further. The input schema bounds the message to 4,096 characters; the component
bounds it to 32 logical lines.

## Public imports and bootstrap ownership

New code uses the canonical execution-platform namespaces:

```python
from deepresearch.engine import Engine, EngineSettings
from deepresearch.engine.contracts import canonical_json, digest_bytes
from deepresearch.workflows import (
    MethodDefinition, MethodRegistry, PlatformPort,
    ResearchRunRequest, WorkflowContext, WorkflowRunner,
)
from deepresearch.bootstrap import create_research_service
from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDecision, HookEvent
from deepresearch.agent_catalog import AgentCatalog
```

The execution modules live under `deepresearch.engine.*`. Older import paths remain
compatibility entry points. Workflow/framework, Agent catalog, extensions,
application and bootstrap remain distinct packages.

Only the script's outer host bootstrap calls `Engine.open(...)` and closes it.
It passes that caller-owned Engine into
`create_research_service(engine, registry=..., extensions=...)`. Method components
use `context.port`; Hook handlers receive immutable events and, for selection,
current candidate IDs. The examples never call Engine execution/session APIs,
unscoped Storage operations or HTTP routes from method/Hook code.

`create_research_service(engine)` selects the built-in registry containing
`baseline@1`, `baseline@2` and `example.echo@1`. To run the tutorial, the examples pass the
registry returned by `build_registry()` in
[workflow_method.py](../../examples/workflow_method.py). They submit
`ResearchRunRequest(method_id="example.echo", method_revision=2, ...)` through
`service.start_run`, poll `service.get_run` until `active=False`, and inspect
saved report/events using the service's public methods. The service supplies
`WorkflowContext` and calls `WorkflowRunner`; a method does not create another
runner or duplicate the root node.

## Define a method and compose components

A `MethodDefinition` pins a method ID, positive integer revision, input and
parameter JSON schemas, exact `(role_id, revision)` Agent role pairs and resource
digests. Register it with an object implementing:

```python
class MyMethod:
    async def run(self, context: WorkflowContext, task_input: dict, parameters: dict):
        selected_ids, rendered = await select_parts(context, task_input["message"])
        report_ref = await publish_echo(context, rendered)
        return await checkpoint_result(context, report_ref, selected_ids)
```

These three functions are executable components in the method example. They
use stable node IDs `echo.select`, `echo.publish` and `echo.checkpoint`. A node ID
can execute only once within a run; loops must include a stable item/iteration
identity. The runner's root node ID is `method`, so components choose other IDs.

A component places bounded metadata in its node and performs host operations
through `PlatformPort`:

```python
async def publish_echo(context: WorkflowContext, rendered: str):
    port: PlatformPort = context.port
    async with context.node("echo.publish", "publication", {
        "text_bytes": len(rendered.encode("utf-8")),
    }):
        return await port.publish(rendered.encode("utf-8"), "text/markdown", "echo.md")
```

`context.node` records started/completed/failed lifecycle facts and invokes
optional observation Hooks. Exceptions propagate to the service. `port.assert_active`
checks the existing run's lifetime; components should use async operations and
cooperate with cancellation. `port.update` accepts allowed result/progress
fields and validates published references. It cannot change run identity,
terminal status or execution authority.

For a full research method, compose the shared components in
`deepresearch.workflows.components`:

| Component | Work through the existing context/port |
| --- | --- |
| `discovery.discover` | Record explicit discovery-tool results and project URL candidates. |
| `acquisition.acquire` | Execute a selected `FetchManifest` and retain READY source snapshots. |
| `context_selection.assemble_context` | Read saved sources, select bounded text and record target-model token measurements. |
| `agents.invoke_role` | Invoke a pinned role in a node, require a committed output, then explicitly read its saved artifact. |

The shipped `baseline@1` composes those components, invokes its pinned Writer
and publishes the result. The tutorial's deterministic echo components show the
same composition boundary without discovery/network or model consumption.
The [formal baseline](../architecture/baseline.md) adds planning, bounded research
rounds and draft/review stages. Loops pass `node_prefix="rN."` to discovery and
context selection; acquisition receives `previous=` to retain earlier source facts.
`recipient_role=` names the intended evidence consumer in its ContextPlan.
Return successful publications through `report_ref` and
`result_manifest_ref`, and use `context.checkpoint(...)` for versioned application
data. A checkpoint does not automatically resume execution. The application
service writes `workflow.finished`; a method does not invent a separate terminal.

## Pin Agent task, schema and spec resources

`baseline@1` pins the catalog role `baseline.writer@1`. This is the zero-tool
Writer: its `definition.json` declares `tool_requests: []`, and the compiled
AgentDefinition has zero allowed tools. The Workflow acquires/reads sources,
then sends the Writer already selected evidence. Tool-free does not mean
model-free: invoking this Writer makes a provider request and needs the chosen
profile's credentials. Neither tutorial example invokes it.

An Agent role revision contains these packaged resources:

| Resource | Role |
| --- | --- |
| `definition.json` | Role/revision, requested tools, execution limits and output contract. |
| `instructions.md` | Agent instructions. |
| `task.md` | Validated task template with named top-level placeholders. |
| `input.schema.json` | Structured data accepted before task rendering. |
| `output.schema.json` | Agent output contract. |

The method example performs this preparation against the actual packaged bundle:

```python
spec = AgentCatalog().load("baseline.writer", 1)
rendered = spec.render_task({"question": "What evidence was supplied?", "evidence": "Supplied text."})
definition = spec.compile_definition(
    profile_ref="deepseek", model_ref="deepseek-flash", tools=(),
)
assert spec.tool_requests == ()
assert definition.allowed_tools == []
```

Loading, rendering and compiling are pure operations; they grant no authority,
resolve no credentials and dispatch no model. `spec.ref` includes exact role and
revision plus hashes of all five resources. The output includes these pins and
a digest of the rendered task. Structured role input remains separate from the
rendered string accepted by the execution Runtime.

For an actual Writer component, pin `agent_roles=(("baseline.writer", 1),)` in
its method definition and call
`await context.port.invoke_agent("baseline.writer", {"question": question,
"evidence": selected_text})`. The application adapter validates/renders the
pinned task, mediates the existing child edge and returns execution, recording,
publication and usage facts. Check successful status, complete recording and an
acknowledged `output_ref` before publishing a research result. Change revisions
when resource bytes or contracts change; do not silently substitute a role,
profile or model. See [Agent catalog](agent-catalog.md).

`invoke_agent` returns execution metadata and an exported `output_ref`; it does
not inject the role's text into another Agent. Read it explicitly with
`await context.port.read_artifact(output_ref, max_bytes=65536)` or compose
`agents.invoke_role`. Artifact access is limited to the current Workflow scope,
with a positive byte cap of at most 262,144. The shared helper uses 65,536 bytes
and closes the stream on success or failure. The application accumulates role
usage under the original shared budget; the method should not replace it with
one child's usage.

## Register bounded observation and selection Hooks

Hooks are optional host configuration. The runnable
[workflow_hooks.py](../../examples/workflow_hooks.py) builds an `ExtensionRegistry`
and passes it as `extensions=` to `create_research_service`. Its handlers are
async callables registered with exact `ExtensionSpec` records. Extension
`spec.revision` is a **string** such as `"v1"`; method/Agent revisions are integers.

```python
observer_spec = ExtensionSpec(
    extension_id="example.lifecycle", revision="v1",
    points=("node.before", "node.after", "node.failed"),
    mode="observe", timeout_seconds=0.5,
    config={"max_observations": 16},
)
registry.register(observer_spec, LifecycleObserver(observer_spec))
```

Node observation payloads contain exactly `kind`, `status` and `detail_sha256`.
`run_id`, `node_id` and `point` are HookEvent envelope fields. Node detail,
source text, queries and prompts are not exposed in these payloads; the observer
must not assume they are available. `HookEvent.payload` and `ExtensionSpec.config`
are immutable bounded metadata snapshots. Configure a handler explicitly from
its frozen spec; changing config requires a new pinned registration. The
registry has one exact revision per extension ID, and a dispatcher snapshots
registrations for the run.

A control Hook can select a subset of current candidate IDs and reorder them:

```python
async def keep_last(event: HookEvent, candidate_ids: tuple[str, ...]) -> HookDecision:
    return HookDecision(keep_ids=tuple(reversed(candidate_ids))[:2])
```

Register it with `mode="control"`, `points=("context.select",)` and a string
revision. The method opts into that point with
`await context.select("echo.select", "context.select", candidate_ids)`.
The shipped research components also expose `discovery.select` and
`context.select`. The dispatcher validates decisions against the current list;
a later Hook can narrow/reorder the remaining IDs but cannot restore an ID
removed by an earlier Hook. Invented IDs and duplicates fail validation.
Handlers cannot return replacement text, URLs, Agent definitions, credentials,
budgets or executable actions.

Dispatch order follows extension ID order. Observation failures are recorded
and isolated from the method when recording succeeds. A failed, timed-out or
invalid control decision fails selection. Mandatory recording failures still
propagate. The example checks committed `workflow.hook.observed` and
`workflow.hook.decision` receipts and requires no `workflow.hook.failed` events.
Default success exercises `node.before`/`node.after`; `node.failed` is registered
for actual component errors, without injecting a failing run into the default
example. The no-Hook run verifies the method remains complete on its own.
See [Extensions](extensions.md) for exact bounds and error semantics.

## Hand off a new method

Keep method policy in its components and schemas, optional behavior in explicitly
registered Hooks, and service/Engine ownership in bootstrap. Pin resource hashes,
keep node details and Hook facts bounded, inspect execution and recording
separately, and require real published evidence before downstream use. Run the
same method with extensions enabled and disabled. For a model-free check, use
`example.echo`; for research acceptance, use actual providers/tools and retain
scope-qualified sources, result/checkpoint refs and complete cleanup evidence.
