# Start building on the EBD platform

The handoff target is a platform teammates can use independently. The four
modules, Python composition API and local HTTP run API are implemented and
verified. You can start strategy and console work against these interfaces.
The team's EBD strategy and UI are consumers of this platform.

## Choose your entry point

| Your work | Start here | Interface you own/use | First integration milestone |
| --- | --- | --- | --- |
| EBD orchestrator / strategy | [Connections guide](usage/connections.md), [research example](../examples/research.py) | Use public `Engine`, sessions, invocation rules, evidence bindings and scoped Storage. Own research phases and decisions. | Register and run an agent, inspect its result, then compose explicit child calls. |
| Frontend console | [HTTP walkthrough](usage/console-quickstart.md), [service reference](usage/service.md) | Use `/api/v1` and the [OpenAPI snapshot](api/openapi.json). Own UI and client state. | Register/start a run; show events, terminal status, report and token usage. |
| Agent / prompt author | [Agent guide](usage/agents.md) | `AgentDefinition`, named model profiles, pinned tools, schemas and limits. | Produce one validated output through `Engine.run_agent`. |
| Platform maintainer | [CONTRIBUTING](../CONTRIBUTING.md), [AGENTS](../AGENTS.md) | Maintain assigned modules, contracts and focused tests. | Reproduce the relevant acceptance checks before changing a consumer contract. |

Orchestrator authors also need [Storage](usage/storage.md) for state/CAS and
checkpoints, and [Tools](usage/tools.md) for discovery, fetch and saved reads.
The joint boundary is [consumer contract v1](teams/consumer-contract-v1.md).

## Set up your checkout

Run from the repository root. Install uv, then use its locked project environment:

```powershell
uv sync --locked
uv run --locked python --version
uv run --locked pytest -q
uv run --locked ebd --store local/my-tool-store tools
```

Python 3.11+ is required; the recorded acceptance environment is Windows with
Python 3.11.15. The test suite and catalog command require no model credentials
or paid model calls. Run the suite on another OS before claiming that deployment
is verified. The existing workspace's offline cache commands are in
[CONTRIBUTING](../CONTRIBUTING.md#environment); a fresh checkout uses normal sync.

For real model runs, create your own ignored credential file without replacing
an existing one:

```powershell
New-Item -ItemType Directory -Force local | Out-Null
if (-not (Test-Path -LiteralPath local/.env)) {
    Copy-Item -LiteralPath .env.example -Destination local/.env
}
```

Fill `DEEPSEEK_API_KEY` for the default `deepseek` / `deepseek-flash` profile,
or `OPENAI_API_KEY` for `openai` / `gpt-6-luna`. Process environment values
override the file. The backend reads credentials; the browser never needs
them. A profile listed by the API is configured metadata, not proof that its
credential or account quota works. Starting a model run uses that account.

Each developer uses a separate Storage directory. Only one Engine process may
own a directory at a time. In one application, a strategy and RunService share
the same live Engine; do not open a second Engine over its database.

## First Python run

```powershell
uv run --locked python examples/research.py
```

This example makes real model and tool calls. It is a small consumer of the
public API, not an implementation dependency for your strategy. Copy its
registration/run pattern into your application and choose a dedicated
`EngineSettings(storage_root="local/my-strategy-store")` for it. Check
`status`, `recording_status`, `persistence_state` and `output_ref` separately.
Use fresh `Engine.open_run_access` grants to read saved output after completion.

For multiple roles, register all child definitions before the parent, explicitly
register `InvocationRule` edges, open a parent session and invoke children through
its bound invoker. Invocation is controlled by your Python strategy; registering
a child does not add a delegation tool to the model. The
[Connections guide](usage/connections.md#shared-evidence-for-child-agents)
shows how to bind a completed Reader's saved evidence and delegate it to a Writer.
References alone do not transfer read permission. A strategy-only parent session
has no fabricated model execution or agent terminal; record your mission state
through the application Storage contract.

## First console integration

```powershell
uv run --locked ebd --store local/my-console-store serve --port 8000 --origin http://localhost:5173
```

Leave this process running. Open `http://127.0.0.1:8000/docs` for interactive
requests; follow the [complete HTTP walkthrough](usage/console-quickstart.md)
in a second terminal. Catalogs, health, agent registration and OpenAPI work
without a model key. Model execution needs the selected key.

The backend permits the exact supplied browser origin. If your frontend uses
`http://127.0.0.1:5173`, pass that origin instead, or add a second `--origin`.
Use one Uvicorn worker. The v1 service accepts local clients only.

The checked-in [OpenAPI JSON](api/openapi.json) is available before a backend
or credential is configured. It is generated from the actual FastAPI routes
and DTOs, so frontend developers can import it into their client tooling.
Regenerate after an API change:

```powershell
uv run --locked python examples/export_openapi.py
```

This command opens no Engine, reads no credentials and makes no network calls.
The running service's `/openapi.json` is the authority for that server version.

## Integration rules to agree before parallel work

| Boundary | Existing contract |
| --- | --- |
| Python imports | Public exports from `ebd.connections`, `ebd.contracts`, `ebd.service`; scoped Storage through bindings. Avoid private backend/worker implementation imports. |
| HTTP compatibility | `/api/v1`, `schema_version: 1`, strict request fields, additive response fields. Use named OpenAPI types. |
| Definition changes | Keep an agent revision immutable; use a new revision for changed instructions, schemas or tools. Register definitions again after service restart. |
| Execution completion | Wait for `active=false`; separately inspect execution, recording, publication and cleanup. An accepted handle or a cancellation request is not a terminal result. |
| Progress | Poll committed events with `next_after_seq`; drain `has_more`. This is activity polling, not token streaming. |
| Tokens | Display `null` as unknown and retain completeness. Cache/reasoning counts are subsets, not extra totals. |
| Recovery | Reopened results are readable. An old run with no durable terminal is interrupted; checkpoints are data, not automatic execution resume. |
| Shared evidence | Host-issued bounded read selectors plus explicit child edges; sending a snapshot ID as task text is insufficient. |

The existing HTTP API launches individual registered agent runs. If the console
will launch a whole EBD mission, the application team must define its mission
request/status/state contract with the frontend team. There is no existing
`/missions` or workflow-launch route to assume. This does not block building
agent execution, report, usage and event views against today's API. Keep mission
strategy in the application layer; request shared contract changes through root.

## What is authoritative

1. Current public source/DTOs and generated OpenAPI define exact executable
   field names and signatures. The usage guides explain how to call them.
2. [Consumer contract](teams/consumer-contract-v1.md) and
   [platform contract](teams/platform-contract-v1.md) explain boundaries and invariants.
3. [Platform acceptance](platform-acceptance.md) and
   [consumer acceptance](consumer-acceptance.md) identify actual live evidence.
4. Documents marked **Historical design record** preserve earlier reasoning.
   Their old phase holds, chat assignments and pseudocode are not current setup
   instructions or authority to contact former team chats.

Report source/document discrepancies to root with the exact symbol/route, a
minimal reproduction and affected consumers. Root coordinates shared contracts,
dependencies and Git; contributors edit their assigned paths. Use
[CONTRIBUTING](../CONTRIBUTING.md) for handoffs.

## Verification available to teammates

The current suite has 228 passing tests. The original EBD baseline, both API
providers, scoped evidence sharing and real loopback HTTP runs have retained
live acceptance evidence. Generated reports, stores and keys are ignored local
data and do not arrive with a Git clone. Reproduce live evidence using the
commands in the acceptance documents when needed; they make real API calls.
Qwen live acceptance awaits deployment. Static HTML/text/text-PDF retrieval is
supported; Google discovery remains gated, and search availability is external.
