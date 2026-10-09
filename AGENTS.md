# DeepResearch Engine

Course project (Concordia INSE 691): a deep research agent system that compares
an Environment-Based Design (EBD) orchestrator against a baseline orchestrator.

## Status

The project restarted on 2026-10-08. The earlier self-built platform (custom
search, fetch, extraction and runtime, up to `baseline@13`) was a concept
experiment. It is archived on branch `archive/concept-experiments`, tag
`concept-experiments-final`. Use it as a record of lessons and design rationale,
not as code to port. Its two main lessons:

- Self-hosted open-source search returned results too poor to support research.
- Building the implementation layer ourselves spent the schedule on tool
  fidelity instead of the EBD arm.

## Stack decisions

- Both arms, baseline and EBD, are LangGraph.js graphs. Use LangChain.js for model and
  tool integration and LangSmith for tracing, instead of custom infrastructure.
- Web search uses each model API's built-in search tool. Do not add
  self-hosted search, fetching or content extraction.
- Models: `gpt-6-luna` and `claude-haiku-5-5`. Each provider searches with its
  own backend, so compare baseline and EBD within the same model.

## Rules

- Preserve each experiment question verbatim. Do not expand, translate or
  rephrase it. The fixed EBD question is `What is EBD (Environment Based Design)?`.
  Agent-generated search queries are separate recorded data.
- Use TypeScript on Node.js 22 with npm. Python remains only for the
  proposal build scripts under `docs/proposal/`.
- Never expose values from `.env` in messages, documents, traces or
  command output.
- Only the root session edits the manifest/lockfile and performs Git writes.
- Handoffs must run real models and tools. Controlled fault tests do not
  replace live acceptance.
- Use GPT-6.1-sol for execution subagents with concrete steps and fixed goals.
  Use Astra (gpt-6-astra) for exploration subagents that investigate and reason.
  This model routing is the user's explicit preference.

## Layout

- `docs/background/`: course slides.
- `docs/proposal/`: proposal and design drafts.
- `research/`: survey of open-source deep research systems (LangChain Open Deep
  Research, GPT Researcher, Local Deep Research, MindSearch).
- `.env`: API keys at the repository root, ignored by Git.
- `local/`: machine-local run outputs, ignored by Git.
