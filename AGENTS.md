# EBD DeepResearch implementation entry point

The user ended cross-session development coordination. Development now happens
in the current root chat and its in-chat subagents. Do not contact or dispatch
work to the former module-team chats. Their reviewed documents remain design
references, not active work assignments.

The runnable platform and real EBD baseline are delivered. Current handoff
work makes the platform usable by teammates through clear documented public
interfaces, runnable examples and verified integration. Strategy and console
development consume those interfaces; their completion is not a prerequisite
for platform handoff.

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
| Agent/runtime subagent | `src/ebd/agent/`, `src/ebd/providers/`, `tests/agent/`, `tests/providers/`, `docs/usage/agents.md` |
| Toolset subagent | `src/ebd/toolset/`, `tests/toolset/`, `docs/usage/tools.md` |
| Storage subagent | `src/ebd/storage/`, `tests/storage/`, `docs/usage/storage.md` |
| Root | Shared contracts, Connections, RunService/HTTP API, package/CLI composition, examples, baseline, integration tests, environment, project docs and Git |

Use uv and Python 3.11+. Only root edits the manifest/lockfile and performs Git
writes. Subagents must not stage, commit, push, change branches or overwrite
another owner's files. Request shared-interface changes through in-chat
collaboration and continue independent work. Send only coordination needs and
completed handoffs; no routine acknowledgments or check-ins.

Handoffs must run real models/tools/storage. Controlled fault tests do not
replace live acceptance. Never expose values from `local/.env` in messages,
documents, traces or command output. Local vLLM Qwen is not deployed here;
implement its configurable connector and retain explicitly pending live tests.
