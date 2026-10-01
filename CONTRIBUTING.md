# Shared environment and contribution rules

All four module teams work in the same checkout. Read `AGENTS.md`, your team
spec, and these rules before changing files.

## Environment

- Use uv and Python 3.11+. The initial shared development interpreter is Python 3.11.15.
- Use the committed `pyproject.toml`, `.python-version`, and `uv.lock`.
- Follow `.gitattributes` for consistent text line endings across Windows and other hosts.
- Run project commands through `uv run --locked`; synchronize with `uv sync --locked`.
- Do not use globally installed Python or independently modify project dependencies.
- Send dependency/version requests to PM. PM updates the manifest and lockfile together; teams synchronize after that commit.
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
to PM; do not silently change versions. SQLite runtime requirements for WAL
are recorded in the design decision log; Python version support alone does
not establish a suitable SQLite build.

## GitHub identity

- The repository belongs to the signed-in GitHub account `ZhuoQiuMcgill` and is private.
- Authenticate GitHub operations through that account's existing GitHub CLI login; never copy or print its credentials.
- Commits use that account's GitHub noreply identity. Do not use a personal email or switch to a team-specific/bot author.
- Git requires an author email field; the account-linked noreply address provides attribution without exposing a personal email.
- PM sets repository-local Git identity. Teams must not override it or change global Git/auth settings.

## One shared checkout, one Git writer

PM is the only session that stages, commits, pulls, merges, changes branches,
or pushes in this shared checkout. Teams edit only their assigned files and
report exact paths and validation evidence. PM stages completed paths,
checks the diff, commits, and pushes sequentially.

Teams must not run `git add`, `commit`, `push`, `pull`, `checkout`, `switch`,
`merge`, `rebase`, `reset`, `clean`, `stash`, or change Git configuration.
Read-only `git status`, `diff`, and `log` are allowed. Do not revert another
team's edits or stage the entire checkout.

The shared branch is `main` during design. If implementation later benefits
from separate branches/worktrees, PM first assigns isolated checkouts and an
integration sequence. Do not switch branches underneath another session.

## File ownership

| Owner | Editable paths in the current phase |
| --- | --- |
| Agent Container | `docs/teams/designs/agent-container-design.md`; `docs/teams/reports/agent-container-status.md` |
| CLI Toolset | `docs/research/free-search-fetch.md`; `docs/teams/designs/cli-toolset-design.md`; `docs/teams/reports/cli-toolset-status.md`; ignored CLI research scratch |
| Storage | `docs/teams/designs/storage-design.md`; `docs/teams/reports/storage-status.md` |
| Connections | `docs/teams/designs/connections-design.md`; `docs/teams/reports/connections-status.md` |
| PM | Shared specs, briefs, registry, decision log, root instructions/environment/dependencies, Git operations |

Cross-team changes go to PM as proposals. Read the latest shared documents
before drafting against an interface; do not overwrite them with stale copies.
Implementation paths will be assigned before implementation begins. Current
work remains design/research.

## Completed contribution handoff

Notify PM with owned paths, completed versus draft status, checks actually
run, limitations, and requested decisions. For a ready-to-commit version,
pause edits to those paths until PM confirms the commit, or coordinate the
next revision. Unfinished team documents remain uncommitted until handed off.

PM verifies staged files and ignores before publishing. Preserve other teams'
uncommitted work; avoid force pushes, destructive cleanup, and blanket staging.
File ownership and serialized Git operations prevent overlapping changes in
this shared workspace.
