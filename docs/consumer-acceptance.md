# Orchestrator and console interface acceptance

This records acceptance before the namespace migration. Original `ebd`
commands remain historical evidence; new code uses `deepresearch`. See the
[structure and migration map](architecture/project-structure.md) and
[post-migration verification](research-acceptance.md).

Verified on 2026-10-01 with uv, Python 3.11.15, the committed lockfile and
the actual Windows platform. Development used this root chat and its in-chat
subagents. The interfaces are described in
[consumer contract v1](teams/consumer-contract-v1.md),
[Connections usage](usage/connections.md) and [service usage](usage/service.md).

## Implemented boundary

- Read-only evidence bindings select saved snapshot ranges, artifact byte
  ranges, checkpoint formats and state keys. The trusted host can bind an
  owned completed source run into a live parent; an explicit invocation edge
  can delegate those narrowed reads to a later Writer. Reference-only reads,
  source writes, foreign scopes, expanded bounds and revoked rights are denied.
- The local service owns Engine admission/execution and exposes typed OpenAPI
  DTOs for run start/list/status/cancel, catalogs, progress events, terminal
  results, token usage, state and bounded artifact reads. HTTP disconnection
  does not abandon admitted work. Finite shutdown retains unresolved owners.
- Cancelled/expired owned admissions can record a durable `not_started`
  terminal without provider dispatch. Known standalone tool outcomes and
  rejections reconstruct their actual canonical status after reopening.
- Catalog cursors preserve watermarks. Incremental polling uses bounded SQL
  sequence intervals and scoped permissions. Root lineage polling captures
  its watermark before child discovery, preventing concurrent-child gaps.

## Actual verification

```powershell
uv --cache-dir .uv-cache run --locked --offline pytest -q
uv --cache-dir .uv-cache build --wheel --out-dir local/builds
uv --cache-dir .uv-cache run --locked --offline python examples/live_service_check.py
uv --cache-dir .uv-cache run --locked --offline python -m ebd.baseline --store local/ebd-baseline-store --verify-run run_9837219d984f4ad8b9be32f96442c9b8
```

The complete suite passed **228 tests in 22.73 seconds**. The wheel built
successfully. Tests cover actual SQLite/file persistence, CLI workers,
permission/ownership denial, state CAS, cancellation races, admission expiry,
shutdown during blocked admission, typed HTTP schemas, source-selector mutation
races, close/reopen and the indexed event query plan. Controlled provider fault
tests complement the following live evidence; they do not substitute for it.

The real DeepSeek acceptance saved authoritative Store data and review copies
under ignored
`local/service-acceptance/acceptance-09d54981c0e54556bdcc669e326d9b8f/`:

| Actual run | Proof |
| --- | --- |
| `run_31468989eab6446eb341529185ab2241` | Actual DeepSeek child used registered `document.read` on a parent-owned READY supplied-source snapshot; exact saved range/hash and evidence marker checked. Two received responses reported 1,924 input and 213 output tokens, total 2,137. |
| `run_56649536a4bc414f9fed392fbc6dabec` | Real Uvicorn loopback TCP/FastAPI run performed a genuine Crossref CLI conversation. HTTP status/events/result/artifact/usage and report bytes checked. Two received responses reported 1,189 input and 147 output tokens, total 1,336. |
| `run_14493191594d423598656ee3df260b38` | Actual HTTP cancellation retained a complete cancelled terminal, no output and one interrupted model attempt. No response usage was received; the counts remain unknown. |
| `run_cc2075d050954a29b4b58237f85dc607` | A fresh parent used `Engine.bind_evidence` on the previous owned source run, then a real DeepSeek Writer read that saved snapshot through `document.read`. Binding receipt preceded invocation, and report/usage survived close/reopen. |

`acceptance.json`, `source-binding-acceptance.json`, the saved reports and
traces record exact receipts, native/normalized usage, per-attempt references
and byte-identical reopen verification. The source used for delegation was
explicitly supplied acceptance text, with honest provenance; the console's
Crossref discovery was an actual external tool request. The source-binding
check used an ignored local driver over public APIs and did not reopen or
reuse expired execution authority.

The previous full EBD baseline report also reopened unchanged, with its three
citation sources and report digest
`cf61a094e68a2eb355143b4e90a0af7d30c5432333b5a6d2a1de8cdd87f29052`.
That verification made no model request and refetched no source.

## Consumer scope

The local v1 service starts individual registered agent runs. EBD strategy
authors own multi-round mission state, scheduling and recovery policy; the
engine's Python sessions/invoker/state/evidence APIs support that work. A
strategy-only parent session has no fabricated agent terminal. The console
reads real recorded runs and application state; this release does not claim
to provide an EBD mission scheduler or a workflow-launch endpoint.

Agent registrations are process-local configuration and are registered again
at startup. Saved runs, artifacts and usage are durable. Checkpoints do not
automatically resume execution. The service is local and single-owner;
remote/multiuser deployment and token-by-token model streaming are outside
this contract. Qwen live verification remains pending local vLLM deployment.

## Teammate onboarding verification

The current handoff starts at [Team start](team-start.md), with a complete
[console walkthrough](usage/console-quickstart.md) and generated
[OpenAPI contract](api/openapi.json). Historical design records are explicitly
marked; current ownership and interface precedence are in AGENTS/CONTRIBUTING.

On 2026-10-01, the four client-side PowerShell blocks from that walkthrough
were executed against a real Uvicorn loopback service, using an isolated store
and an allocated port. Only the base URL's port was changed. Registration,
start, status/event polling, usage retrieval and artifact download succeeded.

- Run: `run_cbc64327205648d2b8f15059d18f4b7b`.
- Actual DeepSeek profile: two received responses and one successful Crossref
  tool outcome. This was a bibliographic lookup, not a full-text research claim.
- Terminal execution `succeeded`, recording `complete`, persistence `committed`.
- Downloaded report: 1,174 bytes. Report bytes/hash and token aggregate matched
  after graceful shutdown and service reopen through the public HTTP routes.
- Reported usage: 1,353 input and 357 output tokens, 1,710 total; two persisted
  per-attempt usage references, complete accounting.
- Local evidence: `local/team-onboarding-check/acceptance.json`; the downloaded
  report is under `local/client-reports/<run_id>.md`. These are ignored runtime
  files; teammates reproduce the walkthrough with their own credentials.

The generated OpenAPI snapshot matches `create_app().openapi()` and all internal
schema references resolve (14 path entries). All 169 links checked in the
onboarding/document cleanup resolved. `git diff --check` passed. The unchanged
runtime suite was independently rerun during the handoff audit: 228 tests passed
in 23.29 seconds. No runtime implementation or dependency versions changed for
this documentation handoff.
