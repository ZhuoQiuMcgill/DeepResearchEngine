# Runnable platform acceptance

Development moved to the root chat and its in-chat subagents at the user's
direction. No former team chat was dispatched or messaged for implementation.
All modules share uv, Python 3.11+, one lockfile and root-only Git operations.

The four module implementations and public consumer examples are runnable.
The real EBD report is generated and verified. Both API providers passed real
tool conversations. GPT-6-Luna succeeded after the earlier recorded HTTP 429
`insufficient_quota` failures; the successful run uses the same local key
source and exact requested model. Qwen live verification remains pending the
local deployment, as agreed. No model substitution was used.

## Real report

Question: `What is EBD (Environment Based Design)`.

Run: `run_9837219d984f4ad8b9be32f96442c9b8`.
Model: requested `deepseek-flash` (DeepSeek V4.1 Flash).
Runtime: 9 model calls and 12 recorded tool calls; completed in about 41 seconds.
Three cited sources, four complete immutable read ranges: two research PDFs
and an explicitly qualified secondary source for acronym disambiguation.

Authoritative Store: ignored `local/ebd-baseline-store/`.
Review copies: `local/runs/run_9837219d984f4ad8b9be32f96442c9b8/`:

- `report.md`: exact saved model output.
- `citations.json`: source URLs, refs, component hashes, successful read
  identities, line/page ranges and retained slices.
- `request-audit.json`: requested/reported provider facts, safe settings,
  function-only tool mapping, instruction/search-policy and request digests.
- `trace.json`: committed binding, model/tool intent/outcome and publication
  events, terminal receipt and fresh host access records.
- `checkpoint.json`: standard `engine_checkpoint/1` envelope, with
  `baseline_terminal/1` payload and obtained terminal/result/source refs.
- `agent-result.json` and `acceptance.json`: final status and verification facts.

Report SHA-256:
`cf61a094e68a2eb355143b4e90a0af7d30c5432333b5a6d2a1de8cdd87f29052`.
Saved report, citation manifest, checkpoint and all cited slices were closed,
reopened under renewed host grants, and compared byte for byte. Verification
did not call a model or refetch a source.

Independent review supports the core definition, process/ROM, root-conflict
analysis, case details and evidence limitations against retained source reads.
The report has two minor editorial limitations: its opening frequency wording
is stronger than the evidence despite a later frequency disclaimer, and some
peripheral acronym expansions are uncited. The original model output is
preserved. No long copied source passages were found.

The system instruction prohibits internal/provider-hosted/implicit search;
only registered function tools are rendered. Audits prove this client-side
request policy. Provider internals are not independently observable.

Earlier runs are retained: one failed on a bounded PDF stderr stream; another
completed but failed substantive citation review. The source-failure policy
now allows a safely cleaned, fully recorded, known uncommitted read-only
failure to be returned to the model for a different source. Failed identical
requests are not automatically replayed. Global cancellation, unknown Storage
commit, missing recording and unconfirmed cleanup still stop work.

## Module evidence

Final combined verification: **144 tests passed in 10.59 seconds** on the
shared Windows/Python 3.11 environment. The source distribution and wheel
build successfully; the wheel includes the registered tool schemas and CLI.
The installed wheel's CLI opened real Storage and listed all five tools using
the locked project dependency environment, with the source tree excluded as
the package origin. A separately resolved offline dependency environment was
unavailable because its required registry wheels were not all cached.

| Requirement | Actual evidence and status |
| --- | --- |
| Shared environment | Locked uv runtime: Python 3.11.15; SQLite 3.50.4; HTTPX 0.28.1; DDGS 9.16.0; Trafilatura 2.2.0; pypdf 6.19.0 |
| Agent definition/runtime | Schema validation, live single-use admission, shared/local budget reservations, native model/tool pairing, exact output publication before terminal recording, typed failures/cancellation; real Storage fault tests |
| DeepSeek API | Real successful two-model-turn Crossref function conversation plus the complete report workflow; evidence in `local/provider-acceptance/deepseek-run_b449f6cee5e647d894d21f38324b5645/` |
| GPT-6-Luna Responses API | Real successful two-turn Responses conversation and one recorded Crossref tool call; both responses report `gpt-6-luna`. Native call ID, final artifact hash, complete cleanup and publication before terminal event verified. Evidence: `local/provider-acceptance/openai-run_b855c1961ef24553ba88f7bdd24de713/`. Earlier quota failures remain retained |
| Qwen/vLLM | Configurable pinned deployment-manifest connector and native protocol checks; live service unavailable on this machine |
| All five CLI tools | Real recorded Yahoo, Crossref, OpenAlex, fetch and document.read subprocess checks; HTML/plain/PDF retained evidence and standalone scoped reads |
| Search/quotas | Yahoo best effort; Google disabled pending fidelity gate. Distinct scholarly discovery schemas. OpenAlex anonymous reservation/settlement persisted through normal Storage state before/after dispatch and restored without reset |
| Process/resource behavior | Actual Windows suspended spawn into Job, descendant/pipe cleanup, flood/deadline/cancel/memory tests, and abnormal worker exit with inherited descendant pipes. Single worker peaks approximately 120 MiB HTML, 76 MiB PDF and 55 MiB OA PDF; two concurrent fetch checks passed. Byte caps and sampled measurements do not establish a universal RAM guarantee |
| Storage | Verified DELETE/EXTRA/FK baseline, single root owner, CAS/tombstones and multi-scope batches; artifacts/snapshots/checkpoints/events, immutable hashes, sealed recovery and automatic commit hooks |
| Async artifact source | Declared length/hash, authorization/dedup/quota before source consumption, owned bounded reads, verification and close before READY; identical redelivery does not consume a new source |
| Authority | Object/range/byte bounds enforced in low-level Storage as well as fresh access facades; references confer no authority, exact observer status cannot redeliver, current grants rechecked before release/publication |
| Connections/children | Recorded bindings, model-free standalone helper, public Python strategy session, allowed invocation edges, local+ancestor caps, cycle/depth limits, source scope selection, committed result export and revocation/cancellation checks |
| Handoff | Public usage documents and examples; source ownership remains separate. Root reviews, commits and publishes changes sequentially |

Full commands:

```shell
uv --cache-dir .uv-cache run --locked --offline pytest -q
uv --cache-dir .uv-cache run --locked --offline python examples/live_provider_check.py
uv --cache-dir .uv-cache run --locked --offline python -m ebd.baseline --store local/ebd-baseline-store
uv --cache-dir .uv-cache run --locked --offline python -m ebd.baseline --store local/ebd-baseline-store --verify-run run_9837219d984f4ad8b9be32f96442c9b8
```

The combined live-provider command reports failure honestly when either
provider fails, while completing and saving independent results for both.
The verification-only command retains the model output and reconciles its
actual citations; it never resumes an expired agent or conceals durability
failure through regeneration.

Current implementation deliberately supports the verified DELETE Storage
profile; WAL is rejected. No hardware power-loss, hostile same-user isolation,
interactive browser/OCR or unavailable deployment claim is made. Strict token
budgeting and nonzero automatic retry/repair requests fail closed unless a
verified supported profile is implemented; byte limits and bounded execution
are enforced. Research applications can build further strategy on these APIs.

## Final completion audit

The original criteria in `docs/teams/baseline-acceptance.md` remain intact.
Root and in-chat module owners inspected current source, actual SQLite/file
objects and retained live records. The following requirements are proven for
the current Windows profile; this classification does not extend the explicit
deployment and extraction limitations above.

| Baseline requirement or artifact | Classification and authoritative evidence |
| --- | --- |
| Open Engine, register a bounded agent, bind all four modules | Proven: `src/ebd/baseline.py` uses public Connections/contracts; the saved run records its definition, bindings and limits |
| Finite genuine discovery, fetch and saved reads | Proven: 12 paired tool intents/outcomes, three cited snapshots and four exact complete read ranges; failed source attempts remain visible |
| Exact question and actual DeepSeek V4.1 Flash | Proven: run metadata contains the exact question; all nine model outcomes request and report `deepseek-flash` |
| Provider/internal search disabled by the permitted instruction method | Proven at the client boundary: the saved instruction digest equals the committed instructions plus platform policy; requests expose only the five registered functions. Provider internals are not observable |
| Complete report produced by the model | Proven: the unique final model outcome hash equals the 12,687-byte report artifact and export; no manual replacement |
| Save output before cleanup/terminal recording | Proven: artifact publication sequence 181 precedes terminal sequence 182; complete recording/cleanup and no unfinished actions |
| Citation manifest | Proven: all citations resolve to actual URLs, snapshot/component hashes and successful reads; retained slices reconstruct exactly and support the core claims |
| Request audit and execution trace | Proven: nine model and twelve tool intent/outcome pairs preserve ordering and native call identities; exported events match SQLite |
| Terminal checkpoint and post-run authority | Proven: standard saved checkpoint identifies the question, plan, run, definition, result, manifest and source refs; fresh exact observer authority confirms the obtained terminal receipt |
| Close/reopen without regeneration or refetch | Proven: the report, manifest, checkpoint and every cited slice compare byte for byte under renewed host grants; verification dispatches no model or fetch |
| Full platform beyond the flat baseline | Proven by the module evidence above and 144 tests, including real Windows crash/descendant cleanup, scoped child/budget/export checks and actual live conversations for both API providers |
| Qwen implementation and live-deployment exception | Configurable connector and native protocol checks proven; live verification explicitly deferred because the service is not deployed here, as the user specified |

The independent reviews found no remaining required implementation work for
this profile. Earlier failed runs and quota checks are retained alongside the
successful evidence rather than overwritten or reported as successes.
