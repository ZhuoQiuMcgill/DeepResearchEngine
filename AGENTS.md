# DeepResearch Engine implementation entry point

The user ended cross-session development coordination. Development now happens
in the current root chat and its in-chat subagents. Do not contact or dispatch
work to the former module-team chats. Their reviewed documents remain design
references, not active work assignments.

The platform and formal `baseline@2` Workflow are delivered. Methods, Agent
specifications, optional Hooks, application ownership and HTTP/CLI are separate
modules. Current source, docs/team-start.md and
docs/architecture/project-structure.md define the development boundaries;
docs/research-acceptance.md records actual checks. EBD strategy and console work
consume those interfaces and are outside this baseline delivery.
The formal method composes planning, bounded acquisition/analysis rounds and
draft/review stages. Pin method revision 2 explicitly; revision 1 is retained
for existing consumers. See docs/architecture/baseline.md and docs/usage/baseline.md.

Read `CONTRIBUTING.md`, `docs/team-start.md`,
`docs/teams/consumer-contract-v1.md`, `docs/teams/platform-contract-v1.md`
and the relevant current guide under `docs/usage/`. Acceptance evidence is in
`docs/platform-acceptance.md` and `docs/consumer-acceptance.md`.
Module designs under `docs/teams/designs/` are historical rationale; their old
phase holds and proposed signatures do not override executable contracts.
Root assigns exclusive source/test paths to subagents and owns shared
contracts, integration, dependencies and Git.

| Owner | Paths |
| --- | --- |
| Agent/runtime subagent | `src/deepresearch/engine/agent/`, `src/deepresearch/engine/providers/`, `tests/agent/`, `tests/providers/`, `docs/usage/agents.md` |
| Toolset subagent | `src/deepresearch/engine/toolset/`, `tests/toolset/`, `docs/usage/tools.md` |
| Storage subagent | `src/deepresearch/engine/storage/`, `tests/storage/`, `docs/usage/storage.md` |
| Root | Engine contracts/Connections, research contracts, application/interfaces/bootstrap, examples, integration, environment, docs and Git; explicitly assign methods/catalog/extensions before parallel edits |

The deprecated ebd namespace is isolated in src/ebd/__init__.py. New code uses
canonical deepresearch.* imports. Methods use WorkflowContext and its port; only
bootstrap registers concrete methods. Architecture tests enforce these boundaries.
Pytest uses committed importlib mode; shared helpers use tests.<module> imports.

Use uv and Python 3.11+. Only root edits the manifest/lockfile and performs Git
writes. Subagents must not stage, commit, push, change branches or overwrite
another owner's files. Request shared-interface changes through in-chat
collaboration and continue independent work. Send only coordination needs and
completed handoffs; no routine acknowledgments or check-ins.

Handoffs must run real models/tools/storage. Controlled fault tests do not
replace live acceptance. Never expose values from `local/.env` in messages,
documents, traces or command output. Local vLLM Qwen is not deployed here;
implement its configurable connector and retain explicitly pending live tests.
