# Writing a strategy module

A strategy decides what to research and when to stop. The platform does
everything else. This guide is for anyone writing a strategy, such as EBD.
`src/strategies/baseline/` is the full worked example. `src/strategies/_template/`
is a minimal starting point to copy.

## What the platform does for you

```
experiment config ──▶ platform ──▶ research module ──▶ your strategy
(tasks, strategies,    records,      skeleton graph,     init / observe / finalize
 options, models,      tracing,      researchers with
 repeats, budget)      cost          web search, writer
```

| The platform owns | You own |
| --- | --- |
| Choosing the model and injecting it as `ctx.model` | Analysing the question |
| Running researchers in parallel with the provider's web search | Choosing what each researcher investigates (briefs) |
| Enforcing the researcher budget and the round safety cap | Processing results, finding conflicts, choosing the next briefs |
| The writer and the final report | Deciding when to stop |
| Run records, Langfuse traces, usage and cost | Selecting and organising material for the writer |

Switching strategies, models and options happens in the experiment config.
Your module never reads files, environment variables or CLI arguments.

## Quick start

1. Copy `src/strategies/_template/` to `src/strategies/ebd/`.
2. In `index.ts`, set the module's `name` (and the class's `name`) to `"ebd"`.
   The module name must equal the directory name.
3. Check the contract with one live run:
   `npm run check-strategy -- --strategy ebd --model haiku --task ebd`.
4. Run it like any strategy:
   `npm run research -- --strategy ebd --model luna --task headset`.

Work only inside `src/strategies/ebd/`, and import platform types only from
`src/core/index.ts`. You can add your own files, prompts and dependencies
there; ask the platform owner to add npm packages.

## The contract (version 1)

A module default-exports a `StrategyModule`:

```ts
const ebd: StrategyModule = {
  name: "ebd",                      // equals the directory name
  description: "…",
  contractVersion: CONTRACT_VERSION,
  create: (options) => new EbdStrategy(parseOptions(options)),
};
export default ebd;
```

`create` is called once per run. `options` is whatever the experiment config
gives for this strategy. Validate it with zod, as baseline does with
`OptionsSchema`.

The strategy implements three methods:

```ts
interface ResearchStrategy<S extends JsonValue> {
  init(input: { question: string }, ctx: StrategyContext): Promise<{ state: S; decision: Decision }>
  observe(state: S, results: ResearchResult[], ctx: StrategyContext): Promise<{ state: S; decision: Decision }>
  finalize(state: S, ctx: StrategyContext): Promise<SynthesisInput>
}
```

The platform calls `init` once, then `observe` after every round of
researchers, and finally `finalize`:

```
init ─▶ round 1 researchers ─▶ observe ─▶ round 2 researchers ─▶ observe ─▶ … ─▶ finalize ─▶ writer
```

### What you receive

| | Contents |
| --- | --- |
| `question` | The research question, verbatim. Never rewrite it for the writer. |
| `ctx.model` | The run's chat model (LangChain `BaseChatModel`). Use `withStructuredOutput(zodSchema, { method: "jsonSchema" })` for structured decisions. |
| `ctx.budget` | `researchersTotal`, `researchersUsed`, `researchersRemaining`, `toolCallsPerResearcher`. |
| `ctx.round` | The round the briefs you return now would start. |
| `ctx.today` | The run's date (YYYY-MM-DD). Use it instead of the system clock. |
| `results` | Every result of the round just finished, failures included. |

Each `ResearchResult` has:
- `brief`: your brief, with its `id`, `round` and `tag`.
- `status`: `ok` or `failed`, with `failure` when failed.
- `notes`: Markdown with one section per key question, each with Takeaway, Cited Findings, Inferences and Gaps. `parseNotes()` parses it.
- `sources`: URLs the search tool reported.
- `queries`, `usage`, `diagnostics`, `unlistedCitations`.

### What you return

A `Decision` is `{ briefs, stop, rationale }`.
- **Briefs** have `objective`, `keyQuestions` (at least one), and optionally `constraints`, `sourceHints`, `instructions`, `priority` and `tag`.
- **`instructions`** is your direct channel into the researcher's prompt, e.g. "look specifically for evidence that contradicts X".
- **`tag`** is returned on the result, so you can map results back to your own structures, e.g. a ROM node id.
- **`stop: true`** ends the research, and any briefs in the same decision are ignored. Returning no briefs also ends it.
- **`rationale`** is recorded and shown as the visible research process. Make it say what you decided and why.

`SynthesisInput` is `{ material, outline?, guidance? }`.
- **`material`** is a list of `{ label, notes }`.
- **`outline`** suggests report sections.
- **`guidance`** gives extra writer instructions.

### Rules

1. **State is plain JSON.** It must survive `JSON.parse(JSON.stringify(state))` unchanged. The platform stores it after every step, so it appears in run records. Declare it with `type`, not `interface`, or TypeScript rejects it as `JsonValue`.
2. **Use only `ctx.model`.** Do not create models and do not call search tools. All web research goes through briefs, so both strategies spend the same kind of budget.
3. **Material is researcher notes only.** Select, reorder or excerpt whole lines of `results[].notes`, and group them under your own `#` headings if useful. Never rewrite them or add your own claims to material. Your analysis (conflicts, structure, emphasis) goes into `outline` and `guidance`. The platform checks this and records any violation; `check-strategy` fails on it.
4. **Plan within the budget.** If you return more briefs than `ctx.budget.researchersRemaining`, the lowest `priority` briefs are dropped and the drop is recorded.
5. **Never rewrite the question** for the writer. The writer always receives the original question.

### Platform behaviour you can rely on

- Invalid briefs (for example no key questions) are dropped and recorded in the decision log. `check-strategy` fails on them.
- If `init`, `observe` or `finalize` throws, the step is attempted up to 3 times in total; then the run fails with the error in `error.txt`.
- A researcher failure never throws. It arrives in `results` with `status: "failed"`.
- After 8 rounds the run stops regardless (`maxRounds`, a safety cap).
- Links in your material whose page the search tools never reported are marked `(unverified link)` before the writer sees them.
- Each researcher works under a fixed tool-call cap that you cannot change.
- Contract changes within version 1 only add fields. Ask the platform owner for anything the contract lacks; do not change files outside your directory.

## Running and testing

| Command | Use |
| --- | --- |
| `npm run check-strategy -- --strategy ebd [--model haiku] [--task ebd] [--options '{…}']` | One live run plus contract checks; non-zero exit on failure |
| `npm run research -- --strategy ebd --model luna --task sleep` | One run; `--question "…"` for any question, verbatim |
| `npm run experiment -- experiments/<spec>.json` | Full experiments (see below); `--dry-run` lists the runs |
| `npm test` | Unit tests, no network |

There is no offline mode: every run uses real models and real searches. A run
costs roughly $0.20–0.50 on Haiku and $0.03–0.40 on Luna. Single runs write to
`local/runs/<runId>/`, checks to `local/checks/`, and experiments to
`local/experiments/<name>-<time>/`. Each run record has:

| File | Contents |
| --- | --- |
| `config.json` | Everything that defines the run, including strategy options and model settings |
| `events.jsonl` | Every decision (rationale, accepted, dropped and invalid briefs, your state after the step) and every researcher result summary |
| `results/<briefId>.md` / `.json` | Each researcher's notes and full result |
| `synthesis.json` | What the writer received, with platform diagnostics |
| `report.md`, `summary.json` | The report; usage, cost, timings and diagnostics |

If the `LANGFUSE_*` variables are set, every model call is also traced to Langfuse.

## Experiments and ablations

Every combination of tasks, strategies, models and repeats is one run. Use
labels to compare configurations of the same strategy:

```json
{
  "name": "ebd-vs-baseline",
  "tasks": ["ebd", "headset", "flight", "sleep"],
  "strategies": [
    "baseline",
    { "name": "ebd", "label": "ebd" },
    { "name": "ebd", "label": "ebd-no-conflicts", "options": { "conflicts": false } }
  ],
  "models": ["haiku", "luna"],
  "repeats": 3,
  "budget": { "researchersTotal": 10 }
}
```

## Reading the baseline

`src/strategies/baseline/` shows every part of a real module:
- the options schema;
- structured planning and gap-check calls through `ctx.model` with LangChain prompt templates (`prompts.ts`);
- JSON state;
- using `ctx.budget` to size rounds;
- handling failed results;
- passing its interpretation of the question as `guidance`.
