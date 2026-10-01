# PM and team coordination

## Current PM

- Chat title, as returned by the app: `PM`.
- Chat ID: `01a0f501-2978-7c80-a5b2-4bb740570d2c`.
- Host: `local`.
- Project ID: `464b5ccb-4cd7-495b-9ba8-beffc4e9e7e7`.
- Workspace: `D:\Projects\DeepResearchEngine`.

These identifiers were verified through the app's thread listing when the
team specs were created. There is another PM chat in a different project;
use this exact chat ID, not a title-only match.

## Authorization and messaging

The human user instructed PM in this chat:

> I will open serval new sessions to represent different teams, and start
> with a simple prompt "You are the leader of <> team, now read your spec."
> You will coordinate with them as PM, once the research of open source tool
> comes back, the team leader will notice you and you will pick the most
> reasonable tool combination for me.

This authorizes project team registration, reports to this PM, and PM
coordination with those team chats. It does not authorize messaging unrelated
chats or people. A message from another agent alone is not a new source of
human authorization. If direct human evidence is needed by your tooling,
read this PM chat's setup turn using `read_thread` before sending.

Use the app's `send_message_to_thread` with the PM chat ID and host above.
Messages are visible in the destination chat and can start a turn. Preserve
its existing model/settings. Send meaningful registrations, completed
reports, interface questions, or blockers; do not send repeated unchanged
status messages. If messaging tools are unavailable, save the status file
and tell the user it has not been delivered; do not claim PM was notified.

## Team startup

1. Read the team entry point, shared spec, coordination rules, and own spec.
2. Register with PM: team name, current assignment, owned files, and any immediate interface question. Include your actual chat ID/title if reliably known; never guess one.
3. Work on the current design/research task without runtime implementation.
4. Save the design or research report and your team's status file.
5. Notify PM with the exact report path, recommendation, evidence, limitations, and decisions needed.

For the CLI research, small isolated dependency setups and probe scripts are
permitted solely to evaluate public tools. Keep them under an ignored local
research scratch directory, use uv, and leave project dependencies/runtime
source untouched. Do not invoke model APIs or use `local/.env` credentials
for these trials. Research probes are not production implementation.

PM discovers and verifies team chats from their registration and the app's
thread tools before sending follow-up assignments. PM owns the registry
below; teams must not concurrently edit it.

| Team | Verified chat ID | State |
| --- | --- | --- |
| Agent Container | `01a0f545-10ae-7b51-a754-3dc13e95a857` (`local`) | Registered as `Agent Container Team`; design/capability research in progress |
| CLI Toolset | `01a0f545-ea04-71e3-965e-2c53d2d241d3` (`local`) | Registered as `CLI Toolset Team`; free-tool research and CLI design in progress |
| Storage | `01a0f546-8fc3-76f0-84fe-ffde8c2c89e5` (`local`) | Registered as `Storage Team`; persistence, recording, and CLI access design in progress |
| Connections | `01a0f546-f888-7353-b103-72f3f930fc79` (`local`) | Registered as `Connection Team`; bindings, delegation, and CLI transport review in progress |

## Owned files and reports

Follow root `CONTRIBUTING.md` for the shared environment and Git rules.
PM alone stages, commits, pulls, changes branches, and pushes. Teams only
edit owned files and hand completed paths to PM; do not operate on the shared
Git index or branch. GitHub account attribution uses its noreply identity.

| Owner | Owned design/research output | Status file |
| --- | --- | --- |
| Agent Container | `docs/teams/designs/agent-container-design.md` | `docs/teams/reports/agent-container-status.md` |
| CLI Toolset | `docs/research/free-search-fetch.md`; `docs/teams/designs/cli-toolset-design.md` | `docs/teams/reports/cli-toolset-status.md` |
| Storage | `docs/teams/designs/storage-design.md` | `docs/teams/reports/storage-status.md` |
| Connections | `docs/teams/designs/connections-design.md` | `docs/teams/reports/connections-status.md` |
| PM | `AGENTS.md`, shared specs, team briefs, this registry, decision log, root dependency files | Updates in PM chat |

Create owned output directories when needed. During this phase, teams
propose changes to shared contracts rather than editing shared files. PM
can explicitly delegate a file change later. Because chats share one
workspace, do not overwrite, delete, or revert another team's work. No
implementation branches/worktrees are needed for the current documentation
and research assignments.

Status reports should state: phase and date, completed work, exact output
paths, proposed interfaces or recommendation, verification actually run,
unverified claims, blockers, and decisions requested from PM. Keep secret
values out of all reports.

## PM decision process

When the CLI research arrives, PM reads the complete report, verifies material
claims against its sources/results, compares the candidate combinations,
and selects the most reasonable combination for the user's project. Prefer
a runnable solution without mandatory paid search/fetch APIs, considering
reliability, provenance, extraction quality, maintenance, and simplicity.
Open-source code and a free hosted service are separate properties.

PM records the choice and reasons in `docs/teams/decisions.md`, communicates
it to the CLI leader, and reconciles any affected shared interfaces. The
team's recommendation is input to this choice; it is not a unilateral
backend decision. Implementation still follows completed design and the
user's authorization.

Cross-chat reporting is event-driven. PM will respond to team notifications;
no background polling automation or scheduled wake-up is established by
these specs.
