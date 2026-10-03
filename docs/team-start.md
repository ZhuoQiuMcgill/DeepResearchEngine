# Start building with the team

Research methods are Workflows over one shared execution engine. The expanded
`baseline@3` uses Planner 2, bounded search/fetch/context rounds with Analyst 2,
then Writer 3 and Reviewer 2 with deterministic citation-label checks. It answers
arbitrary topics; only a reviewed, accepted draft becomes the final report.
All four roles are tool-free and use the common Runtime.

Read [Expanded Baseline usage](usage/baseline-expanded.md), [Baseline architecture](architecture/baseline.md)
and [project structure](architecture/project-structure.md). Root records actual
checks in [research acceptance](research-acceptance.md); historical team designs
do not override current source or contracts.

## Choose your interface

| Contributor | Owns | Public interface and first check |
| --- | --- | --- |
| Method / EBD author | `src/deepresearch/methods/<method>/` | [Workflow guide](usage/workflows.md), `MethodDefinition`, `WorkflowContext` and shared components; [method example](../examples/workflow_method.py) |
| Agent role author | `src/deepresearch/agent_catalog/resources/<role>/<revision>/` | [Catalog guide](usage/agent-catalog.md); definition, instructions, task template, input/output schemas |
| Frontend author | UI and client state | [ResearchRun API](usage/research-service.md), [OpenAPI](api/openapi.json); start, replay, read sources/context/report/artifacts/usage |
| Extension author | Extension package | [Hook guide](usage/extensions.md), [Hook example](../examples/workflow_hooks.py); lifecycle observers and selection decisions |
| Platform maintainer | `src/deepresearch/engine/` | [Connections](usage/connections.md), [Storage](usage/storage.md), [tools](usage/tools.md), [Runtime](usage/agents.md) |

Canonical imports use `deepresearch.*`. The `ebd` namespace and executable are
deprecated compatibility bridges. Methods do not construct an Engine, Storage,
provider or HTTP client. `WorkflowContext` nodes compose shared components using
`PlatformPort`; the application implements that port. Bootstrap registers methods.

## Set up and run without credentials

From the repository root, with Python 3.11+:

```shell
uv sync --locked
uv run --locked pytest -q
uv run --locked deepresearch methods
uv run --locked python examples/workflow_method.py
uv run --locked python examples/workflow_hooks.py
uv run --locked python examples/live_research_check.py
```

The examples use real Storage and model-free `example.echo`, so they need no
model credentials. The HTTP check exercises loopback HTTP/SSE and reopened saved
results. Each developer uses a separate ignored store; one Engine process owns
a store. Do not open a second Engine over an active backend's directory.

## Select Baseline revision 3 explicitly

Bootstrap registers `baseline@1`, `baseline@2`, `baseline@3` and `example.echo@1`.
`ResearchRunRequest.method_revision` still defaults to **1**. New consumers must
send revision 3 for expanded budgets; wire `schema_version: 1` stays unchanged. V1's code and schemas
remain under `methods/baseline/v1/`, with `baseline.writer@1` retained.
`deepresearch baseline` is the older single-Agent CLI, separate from these methods.

Revision 3 pins `web.search@2` for recorded Yahoo/DuckDuckGo fallback and uses
Workflow-owned query preparation/topic screening. Standalone callers select
`deepresearch tool web.search --revision 2`; unqualified tool calls retain revision 1.
Run `uv run --locked python examples/live_search_check.py` for the model-free
live search check. Its store and evidence are generated under ignored `local/`.

Copy [.env.example](../.env.example) to ignored `local/.env` only if that file does
not already exist, then configure the selected provider. The default named pair
is `deepseek` / `deepseek-flash`; environment values override the file. The browser
selects names and never receives credentials or endpoints.

Use the explicit v3 request in the [expanded usage guide](usage/baseline-expanded.md). To run a
request file in a POSIX shell:

```shell
uv run --locked deepresearch --store local/my-baseline-v2 research < examples/baseline-request.json
```

In PowerShell:

```powershell
Get-Content -Raw examples/baseline-request.json | uv run --locked deepresearch --store local/my-baseline-v2 research
```

Check `method_revision` in the file and choose a fresh `client_request_id` for each
new intent. The same full request and identity returns the original run across
restart; a different body conflicts. Research input accepts any topic, with
optional explicit queries and source URL candidates. Planning/search still run
with supplied URLs. The method archives discovery/referrals, retains successful
partial acquisition and records failed sources explicitly.

Use the emitted run ID for inspection after the command settles:

```shell
uv run --locked deepresearch --store local/my-baseline-v2 research --show RUN_ID
uv run --locked deepresearch --store local/my-baseline-v2 research --sources RUN_ID
uv run --locked deepresearch --store local/my-baseline-v2 research --report RUN_ID --output local/report.md
```

The source budget counts attempted unique URLs, including failures, across all
rounds. Stops are `evidence_sufficient`, `source_limit`, `no_new_queries` or
`round_limit`. Inspect analysis gaps, selected ranges and review artifacts; none
of those stop reasons establishes external factual truth. Reports cite only
selected-source `[source-id]` labels. Review combines model judgment and structure
checks and can accept a properly qualified, limited answer.

## Start frontend work

```shell
uv run --locked deepresearch --store local/my-console serve --port 8000 --origin http://localhost:5173
```

Open `http://127.0.0.1:8000/docs`. Read `GET /api/v1/methods`, then send
`POST /api/v1/research-runs` with this credential-free first request:

```json
{"schema_version":1,"client_request_id":"first-ui-run","method_id":"example.echo","method_revision":1,"input":{"message":"Hello team"}}
```

ResearchRun executes whole methods. The existing `/agents` and `/runs` execute
individual Agents; their DTOs live in `application/agent_contracts.py`.

Wait for `active=false`, then inspect `status`, `recording_status`, terminal
receipt and report reference. Successful completion also requires settled cleanup
and the persisted completion attestation. SSE reads committed events and resumes
from `Last-Event-ID`; it does not stream model tokens. HTTP disconnect leaves
execution running. Cancel is a request; continue reading until work settles.

A large `workflow.finished` payload can omit `nodes` and retain `node_count` plus
`nodes_sha256` within the 16 KiB event bound. Read the full node list from the
persisted view or node events. Read sources, selected context, reports and generic
artifacts through bounded API access; those reads do not rerun acquisition.

## Shared development rules

- Agree exclusive paths before parallel edits. Root owns shared contracts,
  integration, dependencies, acceptance and Git; see [CONTRIBUTING](../CONTRIBUTING.md).
- Change method/role assets through a new revision. Each standard role bundle
  has five resources; `baseline@2` pins Planner 1, Analyst 1, Writer 2, Reviewer 1.
- Keep generic components in `workflows/components/`, method decisions in
  `methods/`, Agent assets in `agent_catalog/` and concrete ports/task ownership
  in `application/`. Only bootstrap knows concrete method registrations.
- Retain input, plan, discovery archives, selected evidence, analyses, drafts,
  reviews and result/checkpoints. Full canonical input is in `research-request.json`,
  referenced by the method manifest and `workflow.accepted`. Rejected drafts and
  raw Runtime validation failures are diagnostic facts, not accepted reports;
  validation failure leaves `output_ref` null and produces no valid export.
- Default shared `storage_writes=4096` accommodates formal-flow recording.
  Host budgets may be narrower. Nodes, rounds and children share the same tree
  budget; no method increases grants or resets allowances. All maximum method
  parameters are not guaranteed to fit simultaneously.
- Default token measurements are estimates; unknown counts remain null. Strict
  evidence measurement needs a registered tokenizer. Provider usage accumulates
  observed attempts across every role/round/draft and retains incompleteness.
- Hooks observe lifecycle metadata and may subset/reorder selection IDs. A complete
  method runs with an empty extension registry; Hooks cannot add authority.
- Errors, cancellation and unknown effects stop execution. Reopened results remain
  readable, with `automatic_resume=false`; checkpoints cannot authorize refetch
  or repeated model calls.
- Root regenerates HTTP schemas with `uv run --locked python examples/export_openapi.py`
  when shared contracts change.

Static HTML/text and text-PDF acquisition are supported. Search/source access and
provider availability can fail; diagnostics stay recorded. Prompt instructions,
label checks and model review do not guarantee semantic correctness or protection
against every malicious source instruction.
