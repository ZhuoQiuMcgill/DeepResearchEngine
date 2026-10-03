# Research acceptance — 2026-10-02

## Baseline revision 5: complete source access and parallel distillation

The current method is `baseline@5`, pinning Planner 3, Distiller 1, Analyst 3,
Writer 5 and Reviewer 4. The reusable discovery, acquisition, retained reader,
quotation locator and bounded parallel mapper remain separate from the method's
round/quality policies. Every role uses the ordinary Runtime with no tools and a
262,144-token context allowance. See [the current usage and frontend contracts](usage/baseline-parallel.md).

The real unseeded run is **`run_44dee4613305486aaab70b78f7c53492`**:

| Check | Actual result |
| --- | --- |
| Full project regression | **1,118 passed in 225.97 seconds**; final methods/catalog/architecture regression after the coverage correction: **351 passed in 176.72 seconds** |
| Original input | Exactly `What is EBD (Environment Based Design)?`; no supplied queries or URLs |
| Execution / recording | `succeeded` / `complete`; no unsettled operations |
| Research budget | At most two rounds and 20 attempted URLs globally; this run stopped after one round at `evidence_sufficient`, with 10 attempted URLs, six snapshots and four retained fetch failures |
| Saved-source access | All six snapshots fully read and byte/hash checked: five complete PDFs (18, 28, 12, 9 and 10 pages) plus the 1,857-byte original lab landing page |
| Previous ten-page omission | QMS PDF now delivers all 18 pages / 52,133 bytes, including its tail; the 2002 theory PDF delivers all 28 pages / 79,708 bytes |
| Source distillation | Six validated source digests, 41 bound findings, seven model attempts including one quote-repair retry; **four concurrent Distillers observed in actual model intent/outcome intervals** |
| Coverage | `quality.status=sufficient`, `evidence_sufficient=true`, `report_accepted=true`, five distinct substantive documents, six fully read/distilled sources, no required gaps/reasons |
| Synthesis context | 284,109 UTF-8 bytes / 71,028 estimated tokens, within the 524,288-byte / 131,072-token evidence limits |
| Model usage | 11 paired calls; 304,923 input + 14,913 output = **319,836 observed tokens**, including retries; 22,528 cached input tokens |
| Report | English; 11,908 bytes; `sha256:6790600ef9ae0bb0bf4d8948f331d8d3f84071ed136446ff0f87e6f193ea470d`; first draft accepted and exported bytes identical to the saved Writer output |
| HTTP/SSE / restart | 611 replayed events; reconnect, idempotent request and byte-identical report after reopening passed |
| SQLite/provenance | **2,486 checks, zero failures**; integrity/FK checks pass, 627 events, 121 artifacts, six snapshots, four checkpoints, 31 paired tools and 11 paired models/invocations |
| Exact Agent access | Saved Distiller task JSON matches the actual invocation-input digest; every input segment and verified quote resolves to original snapshot bytes and a recorded read action |
| Packaging | Isolated final wheel loads Baseline revisions 1–5, all 25 new role-resource files and 256k limits; real model-free Workflow/Storage run succeeds |

The report was read after publication. It explains the definition, the three
activities, the axiomatic foundation, the Edmonton quality-manual case and the
2023 aircraft-pylon case. It distinguishes the brief landing page from article
full text, formal background papers from direct EBD descriptions, and a reported
single-case expert evaluation from independent replication. `sufficient` is a
coverage judgment for this definition question and these planned questions; it
does not claim an exhaustive literature review or independently replicated outcomes.

Controlled cases additionally verify complete line/PDF tails, partial byte caps,
known range promotion, digest reuse, alternate full text after 403/abstract/
bibliography results, DOI/hash deduplication, irrelevant-content exclusion and
isolated concurrent Agent inputs. Fabricated quotes/unknown IDs still fail before
synthesis. Whitespace and ASCII soft line hyphens locate only original saved
substrings; known segment-pointer corrections retain raw output and a separate
`validation_changes` record. Contradictory Analyst `sufficient=true` plus gaps or
read requests is conservatively downgraded, with raw and normalized analysis
references retained. Reviewer acceptance cannot override missing citations,
wrong coverage labels or non-English narrative.

Cancellation regressions delay or lose the acknowledgement after a real SQLite
commit, including repeated cancellation and sibling failure. The same admitted
operation is settled under the projection lock before cancellation propagates;
live/DB versions, all usage references and terminal node/error facts remain
consistent. Unknown commitments never authorize a replacement CAS or execution.
Final line ranges now include the actual retained terminal LF; immutable line
indexes and line counts are unchanged.

Search remains bounded and records unavailable providers/challenges. A known,
fully settled read-only `SEARCH_UNAVAILABLE` can continue fallback/recovery and
retain earlier candidates. Whole-topic screening excludes the unrelated BSI
standards found in the first trial. Cited-title recovery preserves actual titles
and publisher/OA locations, rather than inventing URL templates.

Earlier development trials are retained unchanged under fresh identities: trial
1 exposed the event allowlist and cancelled CAS acknowledgement race; trial 2
exposed settled search failure classification; trial 3 exposed PDF soft word
wraps and segment-pointer errors; trial 4 exposed contradictory Analyst coverage.
The fixes were exercised in regression tests and trial 5 above. No earlier
requests, outputs, role bundles or baseline revisions were retroactively rewritten.

Ignored retained evidence:

```text
local/baseline-parallel-request.json, local/baseline-parallel-request-{2..5}.json
local/baseline-parallel-live-20261002-{1..5}/
local/baseline-parallel-live-20261002-5-evidence/
  acceptance.json, run.json, result.json, report.md
local/baseline-parallel-provenance-20261002-5/{audit,events}.json
local/parallel-baseline-final-tests.txt
local/parallel-baseline-final-method-checks.txt
local/parallel-baseline-wheel/
```

## Retained validation: exact experiment input and English report — Baseline revision 4

All current EBD experiment entry points preserve the exact user input:
**`What is EBD (Environment Based Design)?`**. The research question is not
expanded to request additional principles, process or comparisons. Queries
generated by Planner/Analyst and prepared by SearchPolicy remain separate,
recorded data. Earlier saved experiments with different input are historical
records and are not retroactively relabelled as identical-input trials.

At this validation, `examples/baseline-request.json` selected `baseline@4` with no supplied URLs or
queries. `examples/research.py`, the legacy baseline's new-run question and both
search diagnostic requests use the same sentence, including its question mark.
The live research experiment driver rejects a modified question or a method
revision without English report roles before opening the HTTP/Engine host.
Old legacy verification preserves its saved question, including the historical
variant without a question mark.

Writer 4 explicitly requires English report headings, prose, reasoning and
limitations regardless of question/source language. Reviewer 3 rejects reports
that switch language and returns English feedback. Baseline 4 also rejects CJK
narrative independently of the review verdict, retaining the rejected draft
and requesting a rewrite within the existing allowance. Original bibliographic
names may remain in References. The structural script check is not a complete
language classifier; the Reviewer checks English for other scripts. Revisions
1–3 and their Agent resources remain intact.

The real unseeded run is **`run_4eb377278aef4846a5125a33d584b84c`**:

| Check | Actual result |
| --- | --- |
| Full tests | **857 passed in 106.33 seconds** |
| Final architecture checks | 127 passed after the legacy verifier was updated to retain its saved question |
| Role pins | Planner 2, Analyst 2, Writer 4, Reviewer 3; existing 262,144 context limits and 20-source/two-round capacities |
| Original saved request | Exact `What is EBD (Environment Based Design)?`, `method_revision: 4`, `source_urls: []` |
| Execution / recording | `succeeded` / `complete` |
| Research | Two rounds, seven attempted URLs, three saved snapshots; `round_limit`, both analyses `sufficient=false` |
| Report language / provenance | English headings and prose read after publication; exported bytes exactly equal the raw Writer 4 model output, with no translation or replacement |
| Review | First draft accepted, no structural or model review issues |
| Report | 11,546 bytes; `sha256:e8ed4efd203dbd505b303ed1dc0095137aff19639c5fafe3500cf50c72a12cb0` |
| Real model usage | Five calls; 43,352 input + 5,598 output = 48,950 observed tokens |
| HTTP/SSE and restart | 376 replayed events; reconnect, idempotency and byte-identical report after reopening passed |
| Storage/provenance | 1,261 checks, zero failures; 386 events, 22 paired tool calls, five paired models, 54 artifacts, three snapshots and five checkpoints; no unsettled operations |
| Wrong-language controlled cases | Real Runtime/SQLite/read worker retains a Chinese draft even when Reviewer says accept, then publishes its English rewrite; a Chinese-only draft exhausts the cap and leaves no final report |
| Search diagnostics | Two real model-free EBD cases retain the same original question; definition `run_01020d6a5d084324b4e659d8985d0d5d` and foundation `run_0c3eafad3de64652a211181d8b135673`, five candidates each |
| Packaging | Isolated wheel loads all four Baseline versions, Writer 4 / Reviewer 3 and their 256k limits; a model-free Workflow completes with real Storage |

The English report covers the requested definition and clearly marks remaining
evidence gaps. Its substantive evidence is concentrated in the QMS case study,
a short Scribd description and a bibliography excerpt; it is not a claim of
complete literature coverage or a comparison with the differently worded prior
experiment on identical input. No extra user-requested subquestions were added.

Ignored retained evidence:

```text
local/baseline-exact-english-request.json
local/baseline-exact-english-live-20261002/
local/baseline-exact-english-live-20261002-evidence/
  acceptance.json, run.json, result.json, facts.json, report.md
local/baseline-exact-english-provenance-20261002/{audit,events}.json
local/exact-question-search-20261002/{store,evidence}/
```

## Search revision 2 and unseeded Baseline acceptance

`baseline@3` now pins `web.search@2`. The worker explicitly attempts Yahoo then
DuckDuckGo, with an eight-second allowance per backend, at most two same-host
query-preserving redirects and three HTTP requests each. Yahoo's verification
redirect is observable. Destination wrappers decode once, ads are excluded
after decoding, and HTTP/parser/rejection counts distinguish backend failures.
Google remains disabled; the implementation uses the locked existing
dependencies and requires no search API key.

The generic Workflow SearchPolicy prepares Agent-generated queries, screens
explicit topic terms in titles/snippets and retains separate decisions beside
the original tool result. Irrelevant web rows do not suppress configured
scholarly fallback. Queries referencing retained source IDs are recorded as
skipped, rather than sent to Internet search. Explicit host queries remain
literal. These are query/metadata heuristics, not semantic reranking or a
gap-driven archive reader. Methods expose optional tool pins through the
frontend MethodView and the regenerated OpenAPI, still 30 paths and wire v1.
See [tool guide](usage/tools.md#search-revision-2),
[Workflow guide](usage/workflows.md) and
[expanded Baseline guide](usage/baseline-expanded.md).

The model-free [live search check](../examples/live_search_check.py) passed
three real worker/SQLite cases; each returned five selected candidates:

| Case | Actual run / observation |
| --- | --- |
| EBD definition | `run_d6c39087902c4adba192116e70a7d059`; Yahoo 307 → 307 → 200, with related EBD results |
| Foundational paper | `run_53dcca8d59574cf797302f3e9f0af594`; Yahoo parsed zero, DuckDuckGo returned the 2004 paper with DOI `10.3233/JID-2004-8404` |
| RAG survey | `run_764869b943834298a8622bddfc65ebbe`; Yahoo returned related survey results |

An earlier passing search check observed DuckDuckGo HTTP 202 and successful
Crossref fallback. It remains separately retained. These checks made no model
or fetch calls and do not claim that every discovered URL is accessible.

The actual two-round Baseline retry is
**`run_0511ae447d064db69d5b935feaca2c1b`**, using configured DeepSeek
`deepseek-flash`, **no supplied source URLs**, 20 attempted-source capacity and
the existing 256k role limits. No scripted model response was used.

| Observation | Recorded fact |
| --- | --- |
| Final full test suite | **850 passed in 97.24 seconds**; includes exact tool pins, source-ID query rejection, irrelevant-result fallback, redirect/query fidelity and transport/parser failure classification |
| Execution / recording | `succeeded` / `complete` |
| Discovery | Four real `web.search@2` calls, all returned usable metadata; two exercised DuckDuckGo fallback after Yahoo parser misses |
| Topic decisions | One of 18 returned rows excluded; 17 selected rows deduplicate to 15 fetched URLs |
| Acquisition | Six successful snapshots, nine recorded HTTP 403 failures |
| Useful papers | QMS case study, ICED23 creativity paper, 2011 EBD paper and 2025 TRIZ/EBD paper discovered and archived without seeded URLs; TRIZ HTML/PDF are copies of the same paper |
| Other source | A 571-byte Scribd description, explicitly qualified as a short secondary source |
| Context | 233,455 UTF-8 bytes / 58,364 estimated tokens; selected ranges remain partial |
| Model usage | Five calls; 181,723 input + 6,132 output = 187,855 observed tokens, including 4,608 cached input tokens |
| Stop / review | Two rounds, `round_limit`, both analyses `sufficient=false`; first draft accepted with no structural or review issues |
| Report | 12,860 bytes; `sha256:78ffd8b850473731c33607ca593a1222ce337f0a776c800d3cf306b4548ef101` |
| HTTP/SSE and restart | 475 replayed events, reconnect/idempotency and byte-identical report after reopening passed |
| Independent provenance audit | 1,634 checks, zero failures; 490 events, 32 paired tools, five paired models, 63 artifacts, six snapshots and five checkpoints; no unsettled operations |
| Packaging | Built wheel loads both search revisions, the shared policy, all Baseline versions and role resources; isolated real Storage Workflow succeeded |
| Public CLI | `deepresearch tool web.search --revision 2` returned three real candidates with `succeeded` / `complete`; four HTTP requests recorded |

The report was read. It covers the definition, environment principles, ROM,
conflict identification, recursive solution generation, applications and
qualified TRIZ comparisons. Compared with the earlier seeded run, search now
acquires relevant additional primary text itself. It still lacks independent
origin-history verification and exhaustive procedure/comparison coverage.
Accepted publication does not imply sufficient research or complete source
coverage; publisher 403s and targeted archive reads remain separate limits.

The preceding unseeded run, `run_46f4e2eb40de4a99a405fd8517b0518c`, had already
archived relevant papers, including an accessible copy of the 2004 foundation.
It failed when the second Analyst produced a claim over the existing
2,048-character limit. Its failed status, raw output and absent report remain
retained; an independent audit passed 1,365 checks. The retry used a new client
identity and store, without relaxing role validation or replaying that run.

Ignored retained evidence:

```text
local/search-fix-live-20261002-verified/{store,evidence}/
local/search-fix-live-20261002-final/{store,evidence}/
local/baseline-search-fixed-live-20261002/                 failed Analyst run
local/baseline-search-fixed-live-20261002-retry2/
local/baseline-search-fixed-live-20261002-retry2-evidence/
  acceptance.json, run.json, result.json, report.md, analysis-1.json, analysis-2.json
local/baseline-search-fixed-provenance-20261002/{audit,events}.json
local/baseline-search-fixed-provenance-20261002-failed/{audit,events}.json
local/search-fixed-wheel/
```

## Expanded Baseline revision 3

The expanded method retains revisions 1 and 2 and their role resource bundles.
`baseline@3` pins Planner 2, Analyst 2, Writer 3 and Reviewer 2. Its whole-run
source allowance is 20 attempted unique URLs, including failures; research is
capped at two rounds. Default evidence capacity is 131,072 estimated tokens /
524,288 UTF-8 bytes, with 262,144 context tokens declared by each Agent. Draft
and review capacity is four pairs, independent of the research-round cap.
See [expanded usage](usage/baseline-expanded.md).

The first expanded run, `run_2845fc55999a4dde9804b424cd57432c`, completed two
research rounds and attempted 18 URLs (six successful), supplying 28,749
estimated evidence tokens. It did **not** publish a report: the first draft
reproduced source-internal reference numbers as unknown report citations, and
the second draft required material review changes. Its two drafts and failure
remain retained. Writer 3 now explicitly distinguishes document reference
numbers, duplicate copies, affiliations and case-specific claims; the bounded
draft/review allowance was expanded to four pairs for the following run.

The successful real retry is **`run_60bf6f4962cc44e28c22989fad4aba1e`**, using
configured DeepSeek `deepseek-flash`, actual discovery/fetch and saved reads.

| Observation | Recorded fact |
| --- | --- |
| Final full test suite | **830 passed in 92.22 seconds** |
| Execution / recording | `succeeded` / `complete` |
| Research | Two rounds; 14 attempted URLs, five successful and nine recorded failures |
| Stop / analysis | `round_limit`; both analyses retain `sufficient=false` and explicit gaps |
| Report review | First draft accepted; no structural or model review issues |
| Evidence | 87,698 bytes / 21,925 estimated tokens; PDFs supply 30,010 and 38,941 bytes, rather than the earlier 7,488-byte prefixes |
| Agent requests | Five model calls; all audited context limits are 262,144 and function tool lists are empty |
| Largest full input estimate | 28,197 tokens; this run does not claim to have filled a 256k model window |
| Actual provider usage | 86,976 input + 5,374 output = 92,350 tokens; 4,224 cached input tokens; reasoning count unknown |
| Report | 12,710 bytes; `sha256:4cbd206532e285ccf4d243d1744bda69e397d836dc2b5be330f45362561b3ccc` |
| Live interfaces | 470 replayed events; HTTP/SSE replay, reconnect, idempotency and byte-identical report after restart |
| CLI report retrieval | 12,710 bytes, byte-identical to the HTTP-exported report |
| Quota integration | Real Runtime/SQLite/read-worker test attempts exactly 20 distinct URLs across two rounds, counts one failed fetch, delivers 19 source IDs, and stops at the whole-run source cap |
| Packaging | Isolated wheel loads 20 new role resource files, all three Baseline versions and the new schemas; model-free Workflow executes with real Storage and complete cleanup |

Evidence counts and full-request preflight now use `ceil(UTF-8 bytes / 4)` and
label the estimator, byte count and unverified status. They are separate from
actual provider observations. Independent task/request byte limits and the
root's shared call/storage/deadline bounds remain enforced. OpenAPI keeps 30
paths and schema major 1; ContextPlan's accepted byte maximum expands to 1 MiB.

The final report was read after publication. It substantially improves process
coverage: ROM, environment decomposition, conflict identification and recursive
solution generation are explained from retained primary text. It remains a
limited synthesis centered on two primary publications. Irrelevant/acronym
collision sources and inaccessible URLs persist; origin history, broad empirical
comparison and some planned questions remain unresolved. Review acceptance is
not an exhaustive research-quality or factual-truth guarantee.

Local retained evidence (ignored):

```text
local/baseline-expanded-live-20261002/                  first failed retry store
local/baseline-expanded-live-20261002-evidence/          failed view and drafts
local/baseline-expanded-live-20261002-retry2/            successful retry store
local/baseline-expanded-live-20261002-retry2-evidence/
  acceptance.json, run.json, result.json, facts.json
  report.md, analysis-1.json, analysis-2.json, review-1.json
```

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
