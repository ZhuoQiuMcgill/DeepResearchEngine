# EBD DeepResearch team entry point

The user is organizing separate chats as module teams, with the existing PM
chat coordinating their work. If asked "You are the leader of <team> team,
now read your spec", use the routing table below. Do not ask the user to
repeat the project background.

Read these first:

Read `CONTRIBUTING.md` for the shared environment, GitHub identity, file
ownership, and PM-only Git operations. Teams must not stage, commit, push,
pull, switch branches, or change Git configuration in the shared checkout.

1. `docs/teams/README.md`
2. `docs/teams/shared-platform.md`
3. `docs/teams/coordination.md`
4. `docs/teams/platform-contract-v1.md`
5. `docs/teams/missions.md`
6. Your team's spec below.

| Team name / aliases | Team spec |
| --- | --- |
| Agent Container / Agent Runtime / Agent | `docs/teams/agent-container.md` |
| CLI Toolset / CLI Tool Set / Toolset / Tools | `docs/teams/cli-toolset.md` |
| Storage / Records | `docs/teams/storage.md` |
| Connections / Connection / Connection Interface | `docs/teams/connections.md` |
| PM / Project Manager | `docs/teams/coordination.md` |

Current phase: design and tool research. The user explicitly said not to rush
implementation before the design is finished. Reading a spec authorizes its
current design/research assignment, not implementation of its future module.
The shared interfaces are drafts. Complete the current assignment and send
its report to PM using the coordination instructions.

Keep changes within your team's owned documents. PM owns this file, shared
specs, the decision log, and project dependency files. Do not modify another
team's files; propose cross-team changes to PM. Never expose values from
`local/.env` in messages, documents, traces, or command output.

The development environment is uv and Python 3.11+. Eventual platform
handoffs must execute real models/tools/storage; mock replies are not a
deliverable. The local vLLM Qwen service is not deployed on this machine,
so its live verification must remain explicitly pending.
