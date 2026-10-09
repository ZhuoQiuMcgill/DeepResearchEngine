# Candidate Selector experiment — 2026-10-02

Baseline 7 adds `baseline.selector@1` between discovery and fetch. It classifies
host-provided candidates into immediate selections, deferred alternatives and
rejections, with recorded reasons. The other five role bundles and the
20-attempt/two-round/256k-per-Agent limits are unchanged. See
[implementation and contracts](usage/baseline-selection.md).

## Finding

The Selector makes acquisition decisions explicit and auditable, but these
trials do **not** demonstrate better research quality. It can identify direct
EBD sources and reject acronym collisions, yet it still spends attempts on
inaccessible publisher locations and sometimes prefers uncertain background
papers over more useful foundations. The successful report remains supported
mainly by the same two EBD case papers as the earlier baseline.

All six observed Selector invocations across three runs produced accepted,
ID-bound decisions. Only one of those three workflows published a report; the
other two failed later in the unchanged Distiller. This is a small exploratory
sample, not an estimate of production reliability.

## Conditions and all attempted runs

Every request used exactly `What is EBD (Environment Based Design)?`, no supplied
queries/URLs, `deepseek` / `deepseek-flash`, two primary queries, four recovery
queries, five search results per call, at most 20 URL attempts, two rounds,
20 Distiller calls, concurrency four, and up to four draft/review pairs. Evidence
allowance was 131,072 estimated tokens / 524,288 bytes; archived reads were
bounded at 1,048,576 bytes per source. All roles retain 262,144 context tokens.
The default host call/descendant envelope increased from 32 to 40 to accommodate
the added role; both current comparison arms used that same envelope. Actual
call counts were far below either ceiling.

Historical v5 used web search 2 and scholarly search 1. Both v6 controls and v7
trials used web search 3 and scholarly search 2; OpenAlex admission remained
closed in the ordinary host profile. Fresh v6 controls were attempted to avoid
attributing search-contract improvements to selection. Each arm has independent
live searches and model outputs; no fixed seed, frozen search corpus or immutable
model deployment was established. Paired executions may also share upstream
account/IP quotas, so timing and availability are not independent controls.

| Trial | Run ID | Outcome |
| --- | --- | --- |
| Historical v5 | `run_44dee4613305486aaab70b78f7c53492` | Accepted report |
| v6 preflight | `run_d8783e6ada03400bab2fdcef58f005ff` | Interrupted: the existing settled-search exception omitted web search revision 3 |
| v6 control 2 | `run_4731973b9a7542a9b51fea3dfaa97fa6` | Failed: Distiller changed planned question strings, including during its bounded repair |
| v7 trial 1 | `run_d5c43f28d2cb45c7a17ac92574ea81ce` | Failed: Distiller returned a JSON Schema instead of a distillation instance |
| v6 control 3 | `run_ea6f702671a3451bbc608a547a1db202` | Failed: Distiller output validation |
| v7 trial 2 | `run_13fd092229044bfc9f6c707f633d495a` | Accepted report; successful-sample comparison below |
| v6 control 4 | `run_d69258627c7746b6ab381f927015e5c9` | Interrupted: Crossref rate limit |
| v7 trial 3 | `run_fe5cf063e34148f5ae0d837653127378` | Selector decisions passed; failed later on Distiller output validation |

The preflight search bug was corrected narrowly for revision 3, preserving all
cleanup, recording and no-persistence conditions. Both later arms use that fix.
After trial 2, code review also moved large selection bindings out of round
checkpoints into referenced artifacts, preserved requested-URL provenance across
rediscovery, and retained the earlier bounded query-recovery trigger when hits
are unrelated. Trial 3 exercised those fixes. The final-byte accounting correction
only includes JSON array punctuation in the candidate-input bound and has a
boundary regression test. The successful report predates these final hardening
changes; the last live final-code trial did not publish a report. No historic
request, store, report or failed run was overwritten.

The v6 controls produced no report, so there is no completed contemporaneous
v6/v7 report pair from which to infer a causal quality improvement. Failures
remain part of this experiment rather than being discarded as unsuccessful
retries. Distiller schema failures currently have no repair path, and a malformed
child can cancel other parallel children. Some cancelled calls have unknown
token usage; their recorded subtotals are lower bounds, not full costs.

## Successful samples, not an average across trials

| Metric | Historical v5 | v7 trial 2 |
| --- | ---: | ---: |
| Research rounds completed | 1 | 1 |
| URL attempts / successful fetches | 10 / 6 | 10 / 4 |
| Substantive documents | 5 | 3 |
| Completely read saved sources | 6 | 4 |
| Saved text read, UTF-8 bytes | 251,025 | 130,917 |
| Model calls | 11 | 11 |
| Selector calls | 0 | 2 |
| Distiller calls, including repair | 7 | 5 |
| Provider input tokens | 304,923 | 190,380 |
| Provider output tokens | 14,913 | 13,102 |
| Total known tokens; complete in these two runs | 319,836 | 203,482 |
| Acceptance to terminal, seconds | 83.50 | 79.59 |
| Body citations to the two dominant papers | 32 / 42 (76.2%) | 33 / 42 (78.6%) |
| Report accepted / host coverage | Yes / sufficient | Yes / sufficient |

The 36.4% token reduction accompanies a 47.8% reduction in saved text read and
fewer substantive documents. It is not evidence that the Selector achieves
the same coverage more efficiently. Its two calls themselves used 21,232 tokens
and about 8.77 seconds of summed model intent-to-outcome intervals. Elapsed
workflow time includes tools and overlapping Distillers and is sensitive to
live availability and caching; the small observed difference is not a benchmark.

Trial 2's first selection received 30 candidates: five selected, 15 deferred,
ten rejected. It prioritized the 2011 quality-management PDF, the ASME EBD
overview, the 2023 Cambridge paper, the services paper and the Concordia landing
page. Recovery received 19 candidates: five selected, seven deferred, seven
rejected. No candidate cards or fields were omitted/truncated in these decisions.
Both batches attempted only exact URLs bound to valid Selector IDs.

Six fetch attempts failed in the successful v7 run. The sources actually read
were the 2011 quality-management paper, 2023 aircraft-pylon paper, brief Concordia
landing page and 1999 Part I background theory. The 2002 axiomatic paper and 1999
Part II, both read in the historical run, were absent. Some alternative publisher
locations consumed attempts without producing additional evidence.

## Report inspection

Both full reports were read. The new report gives a useful definition, the three
EBD activities, ROM/questioning, root-conflict handling, and the two documented
cases. It explicitly distinguishes the 1999 paper from a direct EBD description,
and states that the cases come from the method's own research group rather than
independent replication. It contains more procedural and case detail in places,
but still relies on the same two papers for most claims. It does not establish
broader validation, recover the inaccessible primary overview publications or
improve source diversity. The host's `sufficient` label concerns its bounded
definition-question criteria, not exhaustive literature coverage.

The next demonstrated reliability issue is downstream structured output:
Distillers sometimes paraphrase question strings that must match exactly, or
return schema text rather than instances. A separately evaluated change could
use stable question IDs and bounded schema repair. Those changes were deliberately
kept out of this candidate-selection experiment.

## Evidence and verification

All local evidence is under ignored `local/selector-comparison-20261002/`:

- `comparison.json` and `*-metrics.json`: all eight runs including the historical
  sample, role usage, actual sources, choices, timing and terminal states.
- `selector-evidence-2/report.md`, `run.json`, `acceptance.json`: the successful
  English report and HTTP acceptance exports.
- `selector-audit-2/audit.json`: 2,151 checks, zero failures; SQLite integrity/FK
  checks pass, 592 events, 109 artifacts, four snapshots, no unsettled operations.
- `selector-store-3/`: final-code run, including two accepted Selector decisions
  and the subsequent Distiller failure.
- Separate `control-store*` and `selector-store*` directories preserve every
  run. Original requests and log files remain alongside them.

The successful run passed loopback HTTP/SSE replay, idempotent requests and
byte-identical report access after restart. Saved Selector inputs match actual
invocation digests; decisions bind to delivered IDs, Hook selections are subsets,
and actual Fetch manifests obey those selections and batch budgets. Saved source
reads and quotations were independently checked against snapshot bytes.

Automated checks cover role contracts/Runtime compatibility, rejection of invalid
IDs and oversized selections before fetching, global attempt budgets, cross-round
history, Hook restrictions, explicit inventory bounds, requested provenance and
large-checkpoint regressions. Verification results:

| Check | Result |
| --- | --- |
| Full project suite | 1,268 passed in 381.99 seconds; `local/selector-full-tests.txt` |
| Final selection/retrieval regression after the last boundary changes | 137 passed in 88.66 seconds; `local/selector-final-regression.txt` |
| Wheel build and isolated verification | Revisions 1–7, all 30 current role-resource files, 256k contexts, exact search pins and a real model-free Workflow/Storage run passed |
| Diff whitespace validation | `git diff --check` passed |

The wheel is under `local/selector-wheel/`; its build and verification logs are
`local/selector-wheel-build.txt` and `local/selector-wheel-verification.txt`.
