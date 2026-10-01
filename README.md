# EBD DeepResearch Engine

A group-project execution platform for Environment-Based Design deep research.
The Python environment is configured; the four execution modules below are
still to be implemented.

## Environment

- Use uv for Python, virtual environments, dependency resolution, and execution.
- Support Python 3.11 and later, with Python 3.11 as the shared development version.
- Declare dependencies in `pyproject.toml` and keep the generated `uv.lock` in version control.
- Keep virtual environments, local Python installations, caches, and credentials out of version control.

From the project root:

```shell
uv sync --locked
uv run --locked python --version
```

Add a runtime dependency with `uv add PACKAGE`, or a development dependency
with `uv add --dev PACKAGE`. Commit the resulting changes to `pyproject.toml`
and `uv.lock` together. Run Python programs through `uv run --locked`.

The current environment has no third-party dependencies. Each execution module
will add the dependencies needed for its real implementation.

## Platform scope

1. Agent definition and runtime: define and execute agents against real models.
2. CLI toolset: discover registered tool definitions and execute real commands.
3. Storage and recording: persist state, artifacts, and automatic execution events.
4. Connections: bind agents to models, tools, storage, and permitted agent invocations.

## Team design work

All teams follow [CONTRIBUTING.md](CONTRIBUTING.md): one uv/lockfile
environment, assigned file ownership, GitHub account attribution through a
noreply identity, and PM-only staging/commits/pushes in the shared checkout.

The current phase is design and research. Team leaders start with
[the team spec index](docs/teams/README.md), the shared platform draft, and
their module spec. `AGENTS.md` routes a prompt such as "You are the leader
of CLI Toolset team, now read your spec" to the right documents.

The CLI Toolset team researches free, open-source search and fetch tools
and reports its comparison to the PM chat. PM selects the combination after
reviewing that evidence. Initial design selection: DDGS search, HTTPX
retrieval, Trafilatura HTML extraction, and pypdf text-PDF extraction. DDGS
is replaceable and best-effort; research-task availability remains unverified.
Shared contracts and runtime implementation are still pending.

## CLI tool contract

This is a draft design contract, subject to cross-team review.

- Register each tool's name, description, input/output schemas, command arguments, and execution limits.
- Accept one UTF-8 JSON request on standard input.
- Return one JSON response on standard output; write diagnostics to standard error.
- Exit with code zero for success and a nonzero code for failure, returning structured error details.
- Execute registered command arguments without a shell.
- Record each invocation's start and outcome, including timeout and cancellation, through the engine.

Tool processes form the external execution boundary. Agent, storage, and
connection modules communicate through Python interfaces.

## uv references

- [Working on projects](https://docs.astral.sh/uv/guides/projects/)
- [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
