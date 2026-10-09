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
npm run research -- --model haiku --task ebd          # one test question
npm run research -- --model luna --question "..."     # any question, verbatim
npm run batch -- --models haiku,luna --parallel 3     # all test questions
npm test                                              # unit tests, no network
```

Options: `--strategy` (default `baseline`), `--researchers` (run budget,
default 10), `--concurrency`, `--max-rounds`. Each run writes a record to
`local/runs/<runId>/`: config, decisions, every researcher's notes and sources,
the writer input, the report and a summary with usage and cost estimates.
`npx tsx scripts/analyze-runs.ts local/runs/<runId> ...` compares report
diagnostics across runs.

See [docs/design.md](docs/design.md) for the architecture and the strategy
interface that the EBD strategy implements, and [docs/plan.md](docs/plan.md)
for exploration results and test rounds.

## Layout

- `src/core/`: contracts, the strategy interface, budget, notes and URL helpers.
- `src/graph/`: the shared LangGraph skeleton.
- `src/research/`, `src/writer/`: shared researcher (provider adapters) and writer.
- `src/strategies/`: strategy registry; `baseline/` is the reference strategy.
- `src/config/`: model profiles, run defaults and test questions.
- `deploy/langfuse/`: self-hosted Langfuse.
- `docs/background/`: course slides.
- `docs/proposal/`: proposal and design drafts.
- `research/`: survey of open-source deep research systems.

Copy `.env.example` to `.env` at the repository root and fill in the keys.
Git ignores `.env`; never commit it.
