# Workflow Stage 1/2 acceptance — 2026-10-02

The selected delivery target is a team-ready modular foundation plus one complete
research baseline. EBD strategy and frontend application implementation are not
required for these stages. Source, schemas, executable examples and acceptance
checks below establish the usable development boundary.

| Stage | Delivered result | Entry points |
| --- | --- | --- |
| 1 — shared foundation | Actual engine/framework/method/application/interface separation; immutable method registry, versioned Agent resources, shared manifests/context/run DTOs, optional Hooks, real minimal method, import boundary tests | [Architecture](architecture/project-structure.md), [team setup](team-start.md), [method guide](usage/workflows.md), [Agent catalog](usage/agent-catalog.md) |
| 2 — complete baseline | Recorded search -> selected URL manifest -> model-free fetch and archive -> source measurements -> chosen saved bytes -> tool-free Writer -> report; ResearchRun HTTP/CLI, SSE/replay, cancel, durable identity and bounded saved reads | [Research API](usage/research-service.md), [request](../examples/baseline-request.json), [live check](../examples/live_research_check.py), [OpenAPI](api/openapi.json) |

## Namespace migration verification — 2026-10-02

The canonical package is now `deepresearch`, its distribution is
`deepresearch-engine`, and its CLI is `deepresearch`. Eight implementation
blocks moved to `src/deepresearch/`. Seven former flat directories and their
two script entrypoints were removed; all old imports are concentrated in
`src/ebd/__init__.py`. EBD is reserved for a future research method. See the
[actual tree and import migration map](architecture/project-structure.md).

Post-migration checks ran on the same uv-managed Windows Python 3.11.15:

| Check | Actual result |
| --- | --- |
| Full test suite | **676 passed in 39.52 seconds**; includes exact visible directory constraints, canonical repository consumers, legacy module identity/resources/reload and CLI/worker entrypoints |
| Team examples | Workflow, Hooks enabled and Hooks disabled all succeeded with real Storage and complete cleanup |
| Built wheel | `deepresearch_engine-0.1.0-py3-none-any.whl`; role/method/tool resources, both CLI entrypoints and only one `ebd` compatibility source file verified |
| Isolated wheel execution | Real model-free Workflow and recorded `document.read` worker succeeded using unpacked wheel code, with complete cleanup |
| HTTP contract | Regenerated OpenAPI still has 30 paths; only the service title changed to `DeepResearch execution service` |
| Real HTTP/SSE and restart | `run_367eae37a8d044739d7db575e32a7df7` succeeded/complete; 27 events; replay, idempotency and byte-identical report after server restart passed |
| Previous real baseline | New CLI read `run_ef88fac329fa41e1953489c7a2e2af60` from its existing Store; report remains 8,962 bytes with the original SHA-256 below |

The migration made no new model calls. The prior real DeepSeek baseline remains
the model acceptance evidence; its retained report was compared byte-for-byte
with the migrated CLI output. Wire v1 and saved Store formats remain unchanged.
Historical acceptance sections below retain the commands and results from their
original runs.

## Automated checks

Environment: Windows, uv-managed Python 3.11.15, committed dependency lockfile.

```shell
uv --cache-dir .uv-cache run --locked --offline pytest -q
```

Pre-migration result: **639 passed in 34.79 seconds**. Checks cover the existing
platform, Workflow session/tool/child authority, strict shared contracts,
Agent resource validation/compilation, model-labelled token measurement,
extension error/timeout/cleanup, source continuation/UTF-8 byte selection,
method idempotency/recovery/cancellation, HTTP/SSE and import boundaries.
Controlled provider/tool fault tests use the real Engine/SQLite/recorder;
they are distinct from live research acceptance below. A truncated Writer
response fails explicitly while retaining its observed token usage.

The three team examples ran successfully with real Storage and no model calls:

```shell
uv run --locked python examples/workflow_method.py
uv run --locked python examples/workflow_hooks.py
uv run --locked python examples/workflow_hooks.py --no-hooks
```

The Hook example changes a recorded subset/order; disabling extensions keeps
the same method runnable. The final wheel was built offline with all role,
method and tool schema resources. A separate process loaded its unpacked package,
validated canonical/legacy Engine identity and ran a real model-free Workflow.
No test or packaging dependency was added.

OpenAPI was regenerated from the real application: **30 paths**, including
named method, source-read, event, usage, report and ResearchRun request/view DTOs.

## Live HTTP and baseline

The executable live check runs Uvicorn on an actual ephemeral loopback port,
uses HTTPX requests/SSE, closes the entire service/Engine, then starts a second
server on the saved store and repeats the same client request. It verifies
byte-identical report retrieval and no additional model execution. Saved reads
can append access-binding audit events; prior committed facts remain unchanged.

Model-free HTTP run: `run_692c5db21a5a4d06861f670345e784f5`.
Status/recording: succeeded/complete. Report: 38 bytes. HTTP/SSE, event replay,
request idempotency and restart report identity passed.

Final real Baseline run: **`run_ef88fac329fa41e1953489c7a2e2af60`**.

| Observation | Recorded fact |
| --- | --- |
| Execution / recording | `succeeded` / `complete`; acknowledged terminal and settled completion attestation |
| Discovery | Real `web.search` using the exact query in the example request |
| Acquisition | Two real public PDFs retained; one discovered source failed explicitly |
| First snapshot | `snapshot_4000050fa2c35847afc9474063678165`, 18 pages, 52,133 UTF-8 text bytes |
| Second snapshot | `snapshot_a70dd16ec7d85bb3b0ba14bf0d8445bc`, 10 pages, 38,941 UTF-8 text bytes |
| Supplied context | 23,796 bytes; source prefixes have exact `[0,11488)` byte spans and explicit partial-selection flags |
| Context measurement | 5,949 **estimated** tokens, `deepseek-flash`, `utf8-byte-size/4`, budget 6,000 |
| Writer | One actual model invocation; recorded native request `function_tools=[]`; selected context recorded before model intent |
| Actual provider usage | 5,648 input + 1,721 output = 7,369 tokens; reasoning count unknown |
| Report | 8,962 bytes, `sha256:9363c308dff9517ea5246f416064bcd46a4a3cea79bd95b60a436b16d6e4599d` |
| Live interfaces | 126 replayed events; SSE IDs match committed sequences; reconnect, identical request and restart report verification passed |

This run used the two supplied primary-paper URLs plus actual discovery. Failed
sources were not evidence. Estimates did not replace observed provider usage.
The report was generated by the shared Agent Runtime, not a scripted response.

Retained evidence is ignored local data:

```text
local/research-http-release-baseline-v2/          SQLite and immutable objects
local/research-http-release-baseline-v2-evidence/
  acceptance.json                              HTTP/replay/restart summary
  run.json                                     validated final run view
  report.md                                    saved report bytes
```

Reproduce with your own credentials and dedicated store:

```shell
uv run --locked python examples/live_research_check.py --request examples/baseline-request.json --store local/my-baseline-acceptance --output local/my-baseline-evidence
```

A clone contains the reproducible code and request, not credentials or generated
evidence. Repeating an identity in the same store reuses that run, including
failures; use a new client identity for a new intent. No automatic restart or
refetch occurs for interrupted/unknown work.

## Practical boundary

The default acquisition component fetches sequentially and deduplicates exact
URLs within the manifest; it performs fresh retrieval for a new run. It supports
static HTML/text and text-PDF sources. Search availability/access restrictions
remain external failures. A strict token budget needs a host-registered tokenizer
for the target model; the shipped DeepSeek measurements are labelled estimates.
The evidence budget covers selected evidence, with a separate Runtime request
limit. Frontend hosting is local with one owning Engine/Store. EBD methodology,
the UI itself, distributed scheduling and automatic resume remain future work.
