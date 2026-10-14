# DeepResearch Engine

A deep research agent system for Concordia INSE 691. It compares an
Environment-Based Design (EBD) orchestrator with a baseline orchestrator on the
same models and the same search tools.

- Language: TypeScript on Node.js 22, managed with npm.
- Framework: LangGraph.js for both arms, LangChain.js integrations, self-hosted Langfuse tracing.
- Search: each model API's built-in web search tool.
- Models: `gpt-6-luna` and `claude-haiku-5-5`.

The project restarted on 2026-10-08. The earlier concept experiments are on
branch `archive/concept-experiments` (tag `concept-experiments-final`).

## Usage

```bash
npm install
npm run research -- --strategy baseline --model haiku --task ebd   # one run
npm run research -- --model luna --question "..."                  # any question, verbatim
npm run experiment -- experiments/baseline-all.json                # tasks × strategies × models × repeats
npm run experiment -- experiments/smoke.json --dry-run             # list the runs only
npm run check-strategy -- --strategy baseline                      # contract check for a strategy module
npm test                                                           # unit tests, no network
```

Strategies, their options, models, repeats and budgets are chosen in the
experiment spec. Each run writes a record: config, decisions, every
researcher's notes and sources, the writer input, the report and a summary
with usage and cost. `npx tsx scripts/analyze-runs.ts <run dirs>` compares
report diagnostics across runs.

- [docs/design.md](docs/design.md): architecture and the strategy contract.
- [docs/strategy-modules.md](docs/strategy-modules.md): how to write a strategy
  module such as EBD; start from `src/strategies/_template/`.
- [docs/plan.md](docs/plan.md): exploration results and test rounds.

## Layout

- `src/platform/`: experiments, single runs, strategy loading, run records.
- `src/module/`, `src/graph/`, `src/research/`, `src/writer/`: the research
  module (skeleton graph, researchers with provider adapters, writer).
- `src/core/`: contracts and the strategy interface; `src/core/index.ts` is the
  import surface for strategy modules.
- `src/strategies/<name>/`: strategy plug-ins. `baseline/` is the reference,
  `_template/` a minimal copy-and-edit start.
- `src/config/`: model profiles and test questions. `experiments/`: experiment specs.
- `deploy/langfuse/`: self-hosted Langfuse.
- `docs/background/`: course slides.
- `docs/proposal/`: proposal and design drafts.
- `research/`: survey of open-source deep research systems.

Copy `.env.example` to `.env` at the repository root and fill in the keys.
Git ignores `.env`; never commit it.
