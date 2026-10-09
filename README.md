# DeepResearch Engine

A deep research agent system for Concordia INSE 691. It compares an
Environment-Based Design (EBD) orchestrator with a baseline orchestrator on the
same models and the same search tools.

- Language: TypeScript on Node.js 22, managed with npm.
- Framework: LangGraph.js for both arms, LangChain.js integrations, LangSmith tracing.
- Search: each model API's built-in web search tool.
- Models: `gpt-6-luna` and `claude-haiku-5-5`.

The project restarted on 2026-10-08. The earlier concept experiments are on
branch `archive/concept-experiments` (tag `concept-experiments-final`).

## Layout

- `docs/background/`: course slides.
- `docs/proposal/`: proposal and design drafts.
- `research/`: survey of open-source deep research systems.

Copy `.env.example` to `.env` at the repository root and fill in the keys.
Git ignores `.env`; never commit it.
