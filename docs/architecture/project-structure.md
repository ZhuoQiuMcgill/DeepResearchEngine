# Project structure and dependency rules

This is the implemented Stage 1/2 structure. A Workflow is a research method,
with Python control flow for branching/loops and shared components for discovery,
acquisition and context selection. It is not a disposable CLI script.

```text
src/ebd/
  engine/
    contracts/             execution values, grants, receipts, budgets
    connections/           Engine, Workflow sessions, invocation and access
    agent/                 the common Agent container/runtime
    providers/             native model connectors
      tokenization/        model-specific measurement and estimate policy
    toolset/               fixed-argv search/fetch/read workers
    storage/               SQLite state, immutable objects, event history
  agent_catalog/
    catalog.py             role resolution, validation and compilation
    resources/<role>/<revision>/
      definition.json      tool requests, limits, output contract
      instructions.md      role instructions
      task.md              structured-input rendering template
      input.schema.json
      output.schema.json
  workflows/
    contracts.py           FetchManifest, SourceManifest, ContextPlan, Run DTOs
    registry.py            immutable MethodDefinition and registry
    context.py             abstract PlatformPort and node lifecycle
    runner.py              execute registered methods
    components/
      discovery.py         provider projection and discovery archives
      acquisition.py       URL manifest -> acknowledged immutable snapshots
      context_selection.py saved-source reads -> selected bounded evidence
  methods/
    baseline/              Baseline Workflow and versioned schemas
    example_echo/          real minimal method with no network/model
  extensions/              optional Hook contracts, registry and dispatcher
  application/
    research_runs.py       admission, idempotency, task ownership, inspection
    platform.py            Engine adapter implementing PlatformPort
    agent_runs.py          individual-Agent run service
    agent_contracts.py     individual-Agent application DTOs
  interfaces/
    http/                  FastAPI composition, ResearchRun routes and SSE
    cli/                   commands and legacy baseline compatibility
  bootstrap/               method/catalog/service composition
tests/                     modules, application, HTTP, architecture boundaries
examples/                  runnable consumers, never implementation dependencies
docs/                      setup, interfaces, decisions and acceptance
```

Old Python paths (`ebd.connections`, `ebd.agent`, `ebd.providers`, etc.) are
thin compatibility imports. Canonical implementations live under `engine`;
there are no copied runtimes. Old submodules resolve to the same implementation
module objects. New code uses canonical paths. The old single-Agent baseline
lives under the CLI compatibility boundary.

## Dependency direction

| Layer | Allowed dependency | Responsibility excluded |
| --- | --- | --- |
| Engine contracts | Standard library / validation support | Research policy, prompts, transport |
| Engine modules | Engine contracts and composed engine modules | Workflows, concrete methods, application, HTTP |
| Agent catalog | Engine definitions and validation | Method execution or HTTP task ownership |
| Extensions | Execution errors and immutable metadata | Session handles, credentials or unscoped Storage |
| Workflow framework | Engine values, token measurement, extensions | Concrete methods, Engine construction, direct workers/database access |
| Concrete methods | Workflow framework/components and shared values | HTTP, provider construction, direct SQLite/network calls |
| Application | Engine, Workflow contracts, catalogs, extensions | Hard-coded Baseline/EBD imports |
| Interfaces | Application contracts/services and bootstrap | Research algorithm decisions |
| Bootstrap | All composition inputs | Research algorithm itself |

`tests/architecture/test_layers.py` enforces these import boundaries. Add EBD
as `methods/ebd` with its own schemas, pinned roles and method revision;
register it in bootstrap without changing the Engine or frontend lifecycle.
EBD itself is outside the selected two delivery stages.

## Run contracts

| Contract | Producer -> consumer | Meaning |
| --- | --- | --- |
| MethodDefinition | Method -> registry/application/UI | Input/parameter schemas, method/Agent revisions and asset digests |
| FetchManifest | Orchestrator -> acquisition | Stable IDs and literal HTTP(S) URLs, no source body |
| SourceManifest | Acquisition -> orchestrator/UI | Per-item outcomes, snapshot, provenance, recording/publication and model-labelled measurements |
| ContextPlan | Orchestrator -> Writer/UI | Chosen snapshot/range/bytes, text hash/read action, context artifact and measurement |
| AgentSpec | Catalog -> common Runtime | Instructions, template, input/output schemas, tool requests and host-constrained limits |
| ResearchRunRequest/View | Frontend/CLI -> application | Intent ID, method/model pins, nodes, sources, context, report, terminal facts and usage |
| HookEvent/Decision | Node/selection -> extension | Immutable metadata; validated subset/reordering at selection points |

Acquisition is sequential (concurrency one), deduplicating exact URLs within a
manifest. New runs fetch fresh sources. Cross-run reuse and parallel acquisition
can be separate component policies; neither is silently assumed. A source is
usable only after acknowledged publication and recording. Unknown effects stop
execution without automatic refetch.

Token estimates name `utf8-byte-size/4`; they are not exact tokenizer counts or
hard model token guarantees. Selected and assembled bytes have separate hashed
measurements. Strict mode needs a host-registered exact-model tokenizer. The
evidence budget covers assembled evidence; Runtime separately bounds the full
rendered model request. Actual usage comes from provider outcomes.

## Hooks and frontend events

Every method node emits committed started/completed/failed events and exposes
`node.before`, `node.after`, `node.failed`. Optional observers receive kind,
status and the detail digest; node events retain full bounded details. Discovery
results and selected text remain artifacts. `discovery.select` and
`context.select` controls may remove/reorder known IDs. They cannot add URLs,
increase budgets, create grants or mutate frozen requests.

The complete baseline runs with an empty extension registry. Observer failures
and timeouts are recorded; invalid controls stop execution. Host callbacks must
cooperate with cancellation. Dispatcher cleanup is bounded and reports retained
resources if a callback does not settle. Python callbacks are trusted host code,
not a sandbox for arbitrary executable mods.

HTTP progress uses committed events via polling/SSE with sequence IDs and replay.
Report/source reads use saved-object access, not another fetch. Successful status
requires saved projection, acknowledged terminal, settled cleanup and completion
attestation. Restart exposes missing/inconsistent completion as interrupted.
These stages do not implement automatic resume, multi-user hosting, distributed
scheduling or token-by-token response streaming.
