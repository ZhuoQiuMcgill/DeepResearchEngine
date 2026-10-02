# Start building with the team

Research methods are runnable Workflows over a shared execution engine. The
baseline discovers candidates, submits a URL manifest to model-free acquisition,
retains immutable sources, selects saved evidence and invokes a tool-free Writer.
Frontend clients launch the whole method through ResearchRun.

## Choose your interface

| Contributor | Owns | Public interface and first check |
| --- | --- | --- |
| Method / EBD author | `src/ebd/methods/<method>/` | [Workflow guide](usage/workflows.md), `MethodDefinition`, `WorkflowContext`, shared components; run [method example](../examples/workflow_method.py). |
| Agent role author | `src/ebd/agent_catalog/resources/<role>/<revision>/` | [Catalog guide](usage/agent-catalog.md); definition, instructions, task template and input/output schemas. Pin revisions in your method. |
| Frontend author | Your UI and client state | [Research API](usage/research-service.md), [OpenAPI](api/openapi.json); start, subscribe/replay, read sources/context/report/usage. |
| Extension author | Your extension package | [Hook guide](usage/extensions.md), [Hook example](../examples/workflow_hooks.py); register observers or selection decisions. |
| Platform maintainer | `src/ebd/engine/` | [Connections](usage/connections.md), [Storage](usage/storage.md), [Tools](usage/tools.md), [Runtime](usage/agents.md). |

[Architecture](architecture/project-structure.md) defines actual directory and
dependency boundaries. [Stage 1/2 acceptance](research-acceptance.md) records
tests and real execution evidence. Old team designs are historical rationale;
current source, usage guides and OpenAPI define executable signatures.

## Set up and run without credentials

From the repository root:

```shell
uv sync --locked
uv run --locked pytest -q
uv run --locked ebd methods
uv run --locked python examples/workflow_method.py
uv run --locked python examples/workflow_hooks.py
uv run --locked python examples/live_research_check.py
```

The examples run real Workflows with SQLite/artifacts and no model calls.
Python 3.11+ is required. Each developer uses a separate ignored Storage
directory; only one Engine process owns a store. HTTP and application services
share that Engine. Do not open another Engine over a running backend's directory.

## Run the new baseline

Copy `.env.example` to ignored `local/.env` only if that file does not already
exist. Fill the selected profile's credential; the default is
`deepseek` / `deepseek-flash`. Environment values override the file.
The browser selects a profile and never receives credentials or endpoints.

```shell
uv run --locked ebd --store local/my-baseline research < examples/baseline-request.json
uv run --locked ebd --store local/my-baseline research --show RUN_ID
uv run --locked ebd --store local/my-baseline research --sources RUN_ID
uv run --locked ebd --store local/my-baseline research --report RUN_ID --output local/report.md
```

In PowerShell:

```powershell
Get-Content -Raw examples/baseline-request.json | uv run --locked ebd --store local/my-baseline research
```

Use a new `client_request_id` for each new intent. The same identity and body
returns the original run across restart; a changed body is a conflict.
Source URLs are optional. The example also performs real web discovery.
Failed sources remain explicit; a report needs at least one usable saved source.

The old `ebd baseline` command preserves legacy single-Agent acceptance.
New method work uses `ebd research` and `methods/baseline`.

## Start frontend work

```shell
uv run --locked ebd --store local/my-console serve --port 8000 --origin http://localhost:5173
```

Open `http://127.0.0.1:8000/docs`. Start with `GET /api/v1/methods`, then
`POST /api/v1/research-runs` using
`{"client_request_id":"first-ui-run","method_id":"example.echo","input":{"message":"Hello team"}}`.
This first integration needs no model key. ResearchRun executes whole methods;
the existing `/agents` and `/runs` execute individual Agents, including explicit
output formats and schemas.

Wait for `active=false`, then check `status`, `recording_status` and report
reference. SSE reads committed events and resumes from `Last-Event-ID`; it does
not stream model tokens. HTTP disconnection leaves owned execution running.
Cancel is a request; continue reading until execution settles.

## Shared development rules

- Agree exclusive source/test paths before parallel edits. Root owns shared
  contracts, integration, environment and Git. See [CONTRIBUTING](../CONTRIBUTING.md).
- Change method or Agent assets using a new revision. Runs retain exact asset
  hashes, model/profile, tools and method definition.
- Methods use `WorkflowContext` and its abstract host port. Bootstrap registers
  concrete methods. Engine code never imports research strategies or HTTP.
- Search snippets/fetch previews do not enter Writer context. SourceManifest
  carries references and measurements; ContextPlan records chosen saved bytes.
- Default token measurements are estimates. Strict budgeting requires a
  registered tokenizer for the target model. Provider usage is separate.
- Reopened results remain readable. Interrupted runs do not automatically resume.
  Checkpoints preserve facts, not permission to repeat external effects.
- Regenerate HTTP schemas with `uv run --locked python examples/export_openapi.py`.

Static HTML/text and text-PDF acquisition are supported. Search and public source
access can fail externally; failures stay recorded. Google discovery and live
local Qwen verification retain their previous gates.
