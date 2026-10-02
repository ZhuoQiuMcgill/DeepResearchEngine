# Research acceptance — 2026-10-02

## Formal Baseline revision 2

`baseline@2` is implemented as a reusable method: Planner -> bounded recorded
search/fetch/read rounds -> Analyst -> Writer -> Reviewer -> accepted report.
It pins four versioned, tool-free role bundles, uses shared Workflow components,
retains the original request and intermediate decisions, and exposes the existing
ResearchRun HTTP/CLI interfaces. `baseline@1` remains registered; new consumers
select method revision 2 explicitly. See [design](architecture/baseline.md) and
[usage](usage/baseline.md).

Current checks used the locked uv-managed Windows Python 3.11.15 environment.
No dependency was added or lockfile changed.

| Check | Actual result |
| --- | --- |
| Full test suite | **824 passed in 74.22 seconds** |
| Formal method integration | Actual Runtime, recorder, SQLite and saved-read worker; controlled boundaries verify two research rounds, rejected draft/revision, seven recorded model calls, all stop reasons, missing evidence, invalid references, cancellation and restart |
| Optional Hooks | Formal Baseline completes both with an empty registry and with lifecycle observation plus discovery/context subset controls; every completed node is observable |
| Role request capacity | Actual provider preflight accepts bounded evidence plus plan/analysis/draft with declared role capacity; JSON schema and required-field failures remain strict |
| Failure diagnosis | Complete final outputs failing schema/strict JSON retain only scoped raw bytes; no valid output/export; tests verify restart, write/acknowledgement/unknown-commit failures and shared budgets |
| Durable request and terminal | Original request and execution pins readable after restart; long node histories retain full saved nodes and a bounded terminal summary |
| Team examples | Method example, Hooks enabled and Hooks disabled succeeded with real Storage and complete cleanup |
| Built wheel | `deepresearch_engine-0.1.0-py3-none-any.whl` contains 30 role resource files, both Baseline method schemas/implementations and shared stages |
| Isolated wheel execution | All four formal role specs and all registered method definitions load; real model-free Workflow and recorded `document.read` worker succeed from wheel code, with complete cleanup |
| HTTP contract | Regenerated OpenAPI remains unchanged at 30 paths; wire v1 is preserved |
| Historical report compatibility | Current CLI still reads the earlier real `baseline@1` report, 8,962 bytes, byte-identical to its retained original |

The final **real** Baseline v2 run is
**`run_075321cf8b9347bd84958b3c7afe1588`**. It used configured DeepSeek
`deepseek-flash`, actual web search, actual public-source fetching and retained
document reads. It did not use scripted model responses.

| Observation | Recorded fact |
| --- | --- |
| Execution / recording | `succeeded` / `complete`, committed terminal and settled completion attestation |
| Roles | Four actual invocations: Planner, Analyst, Writer 2, Reviewer; native requests all have `function_tools=[]` |
| Research | One round; four attempted unique URLs, three succeeded (two primary PDFs and a short secondary description), one explicitly failed |
| Stopping / review | `source_limit`; evidence gaps retained; first draft accepted with no structural/review issues |
| Supplied context | 16,711 UTF-8 bytes; 7,488 selected bytes from each PDF and 571 bytes from the secondary description; partial PDF selection is explicit |
| Context measurement | 4,178 **estimated** tokens, `utf8-byte-size/4`, selected model `deepseek-flash`, budget 6,000 |
| Actual provider usage | 20,898 input + 3,756 output = 24,654 tokens across four recorded attempts; 1,024 cached input tokens; reasoning count remains unknown |
| Report | 8,976 bytes; `sha256:1e3b04dfff3ca67fd3a60dc419b3317bde650e95508ab2c2eb7c0e7ff66fd212` |
| Live interfaces | 244 replayed events, 28 completed nodes; HTTP/SSE sequence replay, reconnect and identical-request idempotency passed |
| Restart / CLI | Second HTTP host returns byte-identical report with no additional model dispatch; separate CLI export is byte-identical; original request and result remain readable |

This actual run reached its source allowance with one research round and no draft
revision. The multi-round and revision paths were separately verified by controlled
integration tests over real Runtime/Storage. Acceptance establishes execution and
publication behavior, not exhaustive evidence coverage or external factual truth.
The report states its remaining evidence limitations.

Retained local evidence is ignored:

```text
local/baseline-formal-live-20261002-verified/           SQLite and immutable objects
local/baseline-formal-live-20261002-verified-evidence/
  acceptance.json                                   live HTTP/replay/restart facts
  run.json                                          validated final view and usage
  result.json                                       rounds, stop reason and drafts
  report.md                                         accepted report
  report-from-cli.md                                byte-identical CLI export
```

Reproduce the formal method with a fresh store and your configured credentials:

```shell
uv run --locked python examples/live_research_check.py --request examples/baseline-request.json --store local/my-formal-baseline --output local/my-formal-baseline-evidence
```

Role resources explicitly declare full-request capacity rather than relying on
the Runtime's smaller default. The shared recording allowance is 1,024 writes;
all nodes/roles still share the existing lineage limits and cancellation. The
method never resets those budgets or automatically resumes/refetches uncertain
work. The built wheel was also verified offline with no model calls.

## Earlier Stage 1/2 acceptance

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

Historical real `baseline@1` run: **`run_ef88fac329fa41e1953489c7a2e2af60`**.

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

The current example request selects formal revision 2. Reproduce the current
method with your own credentials and dedicated store:

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
