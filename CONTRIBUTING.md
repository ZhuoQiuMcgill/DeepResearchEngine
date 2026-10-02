# Shared environment and contribution rules

The current root chat and its in-chat subagents work in this checkout.
Cross-session development coordination ended at the user's direction.
Read `AGENTS.md`, `docs/team-start.md`, the relevant current usage guide and
these rules before edits. Historical designs preserve rationale; they do not
impose a new design-only phase or authorize messaging former team chats.

## Environment

- Use uv and Python 3.11+. The initial shared development interpreter is Python 3.11.15.
- Use the committed `pyproject.toml`, `.python-version`, and `uv.lock`.
- Follow `.gitattributes` for consistent text line endings across Windows and other hosts.
- Run project commands through `uv run --locked`; synchronize with `uv sync --locked`.
- Do not use globally installed Python or independently modify project dependencies.
- Send dependency/version requests to root. Root updates the manifest and lockfile together.
- Keep research trials in ignored scratch environments. Trial dependencies do not become platform dependencies automatically.
- Keep `local/.env`, machine configuration, generated databases/artifacts, environments, and caches out of Git. Only placeholder examples may be checked in.

The workspace already has a uv-managed interpreter and cache. If the default
uv locations are inaccessible in the sandbox, use these existing locations:

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.uv-python'
uv --cache-dir .uv-cache sync --locked --offline
uv --cache-dir .uv-cache run --locked --offline python --version
```

Offline synchronization requires cached dependencies. Report missing packages
to root; do not silently change versions. The current implementation supports
the verified SQLite DELETE profile and rejects WAL; see platform acceptance.

## GitHub identity

- The repository belongs to the signed-in GitHub account `ZhuoQiuMcgill` and is private.
- Authenticate GitHub operations through that account's existing GitHub CLI login; never copy or print its credentials.
- Commits use that account's GitHub noreply identity. Do not use a personal email or switch to a team-specific/bot author.
- Git requires an author email field; the account-linked noreply address provides attribution without exposing a personal email.
- PM sets repository-local Git identity. Teams must not override it or change global Git/auth settings.

## One shared checkout, one Git writer

Root is the only writer that stages, commits, pulls, merges, changes branches,
or pushes in this shared checkout. Teams edit only their assigned files and
report exact paths and validation evidence. PM stages completed paths,
checks the diff, commits, and pushes sequentially.

Teams must not run `git add`, `commit`, `push`, `pull`, `checkout`, `switch`,
`merge`, `rebase`, `reset`, `clean`, `stash`, or change Git configuration.
Read-only `git status`, `diff`, and `log` are allowed. Do not revert another
team's edits or stage the entire checkout.

The shared branch is `main`. Subagents work in exclusive paths and root
integrates sequentially. Do not switch branches underneath another writer.

## File ownership

| Owner | Editable paths in the current phase |
| --- | --- |
| Agent/runtime subagent | `src/ebd/engine/agent/`, `src/ebd/engine/providers/`, `tests/agent/`, `tests/providers/`, `docs/usage/agents.md` |
| Toolset subagent | `src/ebd/engine/toolset/`, `tests/toolset/`, `docs/usage/tools.md` |
| Storage subagent | `src/ebd/engine/storage/`, `tests/storage/`, `docs/usage/storage.md` |
| Root | Shared contracts, Connections, RunService/HTTP API, package/CLI composition, examples, baseline, integration tests, environment, project docs and Git |

New method/catalog/extension/application paths are assigned explicitly before
parallel work. Follow [implemented architecture](docs/architecture/project-structure.md).
Flat imports remain compatibility entry points, not implementation locations.
Keep methods over WorkflowContext/components and concrete composition in bootstrap.

Cross-module interface changes go to root with the affected consumers and a
concrete proposed contract. Read current source/DTOs and usage guides before
editing. Root may refine exclusive path assignments through in-chat
collaboration. Application/frontend contributors agree their owned paths with
root before parallel edits to this shared checkout.

For an HTTP contract change, regenerate `docs/api/openapi.json` with
`uv run --locked python examples/export_openapi.py`, review the schema diff,
update the service guide/examples and run the relevant service checks. Python
contract changes include matching usage examples and affected consumer checks.
Breaking wire changes require a new schema major; do not silently reinterpret
v1 fields. See `docs/teams/consumer-contract-v1.md` for consumer boundaries.

## Completed contribution handoff

Notify PM with owned paths, completed versus draft status, checks actually
run, limitations, and requested decisions. For a ready-to-commit version,
pause edits to those paths until PM confirms the commit, or coordinate the
next revision. Unfinished team documents remain uncommitted until handed off.

PM verifies staged files and ignores before publishing. Preserve other teams'
uncommitted work; avoid force pushes, destructive cleanup, and blanket staging.
File ownership and serialized Git operations prevent overlapping changes in
this shared workspace.
