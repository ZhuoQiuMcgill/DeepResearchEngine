# Design: baseline and EBD research engine

Status: implemented for the baseline, 2026-10-09. Exploration results and test
rounds are logged in [plan.md](plan.md).

## 1. Purpose

The project compares two research orchestrators that differ in one thing: how
they decide what to research. The **baseline** decides like a plain deep
research coordinator. The **EBD** strategy decides with Environment-Based
Design: it analyses the question into objects, relations and environment
(ROM), and after each round it resolves conflicts between that model and the
evidence. Everything else (search, execution, budget, writing, recording) is
shared, so differences in outcome can be attributed to the strategy.

## 2. Architecture

Deep research is a module embedded in a platform. Strategies are plug-ins of
the module. The EBD team develops the EBD strategy module; everything around it
is shared and fixed.

```
┌ Platform (src/platform) ──────────────────────────────────────────────┐
│ experiment config: tasks × strategies (+options) × models × repeats   │
│ resolves strategy and model by name; records, tracing, cost, parallel │
│   ┌ Research module (src/module, src/graph, src/research, src/writer)┐ │
│   │ plan ─▶ research × N ─▶ observe ─▶ … ─▶ finalize ─▶ write        │ │
│   │ (parallel researchers with built-in web search; shared writer)   │ │
│   │   ┌ Strategy plug-in (src/strategies/<name>/) ──────────────────┐ │ │
│   │   │ init / observe / finalize — baseline (reference), ebd, …    │ │ │
│   │   └─────────────────────────────────────────────────────────────┘ │ │
│   └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

| Layer | Entry point | Responsibility | Owner |
| --- | --- | --- | --- |
| Platform | `runExperiment(spec)`, `runOne(spec)` | Choose and load strategy and model by name, run jobs, records, tracing, usage and cost | Zhuo |
| Research module | `runResearchModule(input)` | Skeleton graph, budget enforcement, stopping, researchers and provider adapters, writer, shared data-quality steps; no file or CLI access | Zhuo |
| Strategy plug-in | default-exported `StrategyModule` | Question analysis, briefs, processing results, stopping, material for the writer | Baseline: Zhuo. EBD: EBD team |

The module never inspects strategy state. A strategy never calls search, never
sees provider-specific data and never chooses the model. The developer guide for
strategy modules is [strategy-modules.md](strategy-modules.md).

## 3. Strategy contract (version 1)

`src/core/index.ts` is the only import surface for strategy code.

```ts
interface StrategyModule {        // default export of src/strategies/<name>/index.ts
  name: string                    // equals the directory name
  description: string
  contractVersion: string         // CONTRACT_VERSION, "1"
  create(options?: JsonValue): ResearchStrategy<any>   // options from the experiment config
}

interface ResearchStrategy<S extends JsonValue = JsonValue> {
  readonly name: string
  init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<S>>
  observe(state: S, results: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<S>>
  finalize(state: S, ctx: StrategyContext): Promise<SynthesisInput>
}

type StrategyStep<S> = { state: S; decision: Decision }
type Decision = { briefs: ResearchBriefInput[]; stop: boolean; rationale: string }
type StrategyContext = {
  model: BaseChatModel // the arm's model, injected by the module
  budget: BudgetView   // researcher budget, read-only
  round: number        // 1-based round that the returned briefs would start
  runId: string
  today: string        // run date shared by all components
}
```

Rules for every implementation:

1. `S` must survive `JSON.parse(JSON.stringify(state))` unchanged. The module
   stores it after every step, and it appears in run records and traces.
2. All model calls use `ctx.model`; strategies make no searches of their own.
   A strategy may create its own prompts, chains or LangGraph subgraphs
   internally.
3. `observe` receives every result of the round, including failures.
4. The question is passed verbatim. A strategy may write its own search
   objectives, but it never rewrites `question` for the writer.
5. Briefs beyond the remaining budget are dropped by priority, highest first,
   and the drop is recorded. Invalid briefs are dropped and recorded.
6. Material passed to the writer is researcher notes: selected, reordered or
   excerpted by whole lines, optionally under the strategy's own headings. The
   strategy's analysis goes into `outline` or `guidance`, never into material.
   The module records violations as diagnostics, and `check-strategy` fails on
   them. This keeps the evidence the same kind for both arms.
7. A step that throws is attempted up to 3 times; then the run fails.

Contract changes within version 1 only add fields. The loader rejects a module
whose `contractVersion` has a different major version.

## 4. Data contracts

The contracts are zod schemas in `src/core/contracts.ts`, and the TypeScript
types are inferred from them. Fields are added over time, but existing fields
are not changed.

| Type | Fields |
| --- | --- |
| `ResearchBriefInput` | `objective`, `keyQuestions[]`, `constraints[]`, `sourceHints[]`, optional `instructions`, optional `priority` (higher first), optional `tag` (opaque label the strategy can use, e.g. a ROM object id) |
| `ResearchBrief` | `ResearchBriefInput` plus `id` and `round`, both assigned by the skeleton |
| `ResearchResult` | `brief`, `status` (`ok` or `failed`), optional `failure` `{ kind, message }`, `notes` (Markdown in the fixed notes format), `sources[]` `{ url, title?, cited }` (only URLs the provider's tools reported), `queries[]`, `usage` `{ inputTokens, outputTokens, searches, pageReads }`, `model`, `durationMs`, `unlistedCitations[]` (URLs cited in the notes that the tools never reported), `diagnostics[]` (non-fatal problems such as tool errors or truncated output) |
| `BudgetView` | `researchersTotal`, `researchersUsed`, `researchersRemaining`, `toolCallsPerResearcher` |
| `SynthesisInput` | `material[]` `{ label, notes }` in the order the writer should consider, optional `outline[]` (section guidance), optional `guidance` (extra writer instructions, e.g. conflicts to address) |

### Researcher notes format

Every researcher writes the same Markdown structure, adopted from Claude Code's
deep-research skill. One section per key question:

```markdown
## <key question>
### Takeaway
### Cited Findings      - <claim> — [Publisher or title](URL)
### Inferences
### Gaps
```

The skeleton parses these sections leniently into `takeaways` and `gaps` for
strategies that want them (`parseNotes`). A note that does not parse is still
passed through as text.

## 5. Skeleton

LangGraph state: question, round, strategy state, pending briefs, results
(append reducer), decisions log (append reducer), synthesis input, report,
stop reason.

Nodes: `plan` (calls `init`), `research` (one per brief through `Send`),
`observe` (calls `observe` once all briefs of the round are back), `finalize`,
`write`.

Stop conditions, checked after every decision:

1. The researcher budget is exhausted.
2. The strategy returned `stop: true`.
3. The strategy returned no briefs.
4. A safety cap on rounds (`maxRounds`, default 8) is reached. This is an
   engineering guard against loops, not an experimental variable.

## 6. Researcher

A researcher receives one brief and works with the provider's built-in web
tools under a per-researcher tool-call cap. Its prompt is shared and has one
slot, `{instructions}`, filled from `brief.instructions`. That slot is the only
way a strategy changes researcher behaviour.

| | Anthropic (`claude-haiku-5-5`) | OpenAI (`gpt-6-luna`) |
| --- | --- | --- |
| Tools | `web_search_20250305` and `web_fetch_20250910` server tools (direct calls; the dynamic-filtering versions made Haiku's generated code send malformed searches) | `web_search` (search, open_page, find_in_page) |
| Cap | `max_uses` per tool | `max_tool_calls` per response |
| Recorded | queries, result URLs, citations, `server_tool_use` counts | queries, sources, `url_citation` annotations |

A provider adapter turns each response into a `ResearchResult`. Provider errors
become `status: "failed"` with a failure kind (`provider`, `timeout`, `empty`)
rather than disappearing. One model call per researcher is enough on both
providers. The Anthropic adapter continues `pause_turn` up to three times.

## 7. Writer

One shared writer turns `SynthesisInput` into the report. It receives the
verbatim question, the material in strategy order, the optional outline and
guidance, and nothing else. Its prompt is adapted from the deep-research skill's
report writer: a bottom-line opening paragraph, 3–5 sections with descriptive
headings, inline `([Source](URL))` citations, a short conclusion, no claim
without a source in the material, and English output. After writing, the
skeleton applies two shared data-quality steps for every strategy. Before writing,
links in the material whose page the provider's tools never reported are
marked "(unverified link)". After writing, a cited URL that is a prefix of
exactly one known URL is completed, which repairs URLs the writer cut short.
It also runs two diagnostics, recorded in the run summary, neither of which
rejects a report. The first lists cited URLs that appear in no result's sources
or notes, compared without query strings. The second, a heuristic binding
check, reports cited sentences whose numbers do not appear in a notes line
citing the same URL. It also flags rounding and unit conversion, so it is used
only to compare runs.

## 8. Budget

| Layer | Limit | Enforced by |
| --- | --- | --- |
| Researcher | tool-call cap (`max_uses` / `max_tool_calls`) | provider API |
| Run | total researchers (`researchersTotal`) | skeleton |
| Concurrency | parallel researchers at once | skeleton (engineering only) |

Both arms get the same search budget. Tokens and cost are not capped. They are
recorded per run and per role as outcome metrics, so the strategy's own
overhead is visible. A budget is a ceiling: reports compare quality together
with the researchers and searches actually used.

## 9. Baseline strategy

The reference implementation follows the deep-research skill's coordinator:

- `init`: one structured call decomposes the question into non-overlapping
  subtopics that together cover it, 1–6 researchers by complexity (default 3),
  each with objective, key questions, constraints and source hints. No user
  clarification step, because experiments have no user in the loop.
- `init` also returns the interpretation the report should state: the chosen
  meaning of ambiguous terms and any scope bounds. It adds no assumptions about
  the asker.
- `observe`: after round 1, one structured call reads the full notes and the
  observed problems (tool errors, truncation) and launches extra researchers
  only for critical gaps or contradictions on key points. After round 2 it
  always stops. This matches the skill's single optional extra round.
- `finalize`: all successful notes in brief order, with the interpretation as
  `guidance` and no outline.

## 10. Observability and records

- **Langfuse** (self-hosted, Docker) receives traces for every graph node and
  model call through `@langfuse/langchain`. Tracing is enabled when the
  `LANGFUSE_*` variables are set and is optional for local runs. The
  OpenTelemetry SDK starts once per process; runs only flush. Langfuse v4
  stores events only, so read data through `/api/public/v2/observations`.
  Setup is in `deploy/langfuse/README.md`.
- **Run records** are written to `local/runs/<runId>/` (single runs) or
  `local/experiments/<name>-<time>/runs/<runId>/` (experiments): the resolved config, the
  question, every decision with its rationale, each result (notes and JSON),
  the synthesis input, the report and a summary with usage and timings. They
  are the input for analysis and later blind judging.

## 11. Configuration

Everything that varies between runs is chosen by name in an experiment spec
(`experiments/*.json`, schema in `src/platform/experiment.ts`):
- tasks (ids from `src/config/tasks.ts`, or explicit verbatim questions);
- strategies (directory names, or `{ name, options, label }` for ablation variants);
- model profiles (`src/config/models.ts`: provider, model id, effort, output limit, tool versions and caps, prices);
- repeats, the researcher budget, the round safety cap, concurrency and parallel runs.

Names are validated before any run starts. Each run's `config.json` records
the resolved spec, model profile and date, so every run is reproducible from
its record.

## 12. Evaluation (outline)

Judging starts blind: report files are renamed to hashes, and reports are
stripped of formatting and anything identifying the arm or model before the
judges see them. The task set, rubric and repetition count are designed after
the full pipeline works. Current test questions, used verbatim:

- `What is EBD (Environment Based Design)?`
- `compare meta quest 3 and apple vision pro`
- `How do I flight from GuangZhou to Montreal?`
- `What food can help me sleep well?`
