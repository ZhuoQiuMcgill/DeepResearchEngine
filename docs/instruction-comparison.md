# Instruction experiment: baselines 8 and 9 — 2026-10-03

This experiment changes all six instruction/task bundles while retaining baseline
7's executable role schemas, tool pins, scheduling, source delivery, validation
and budgets. The initial pass is revision 8. Revision 9 retains it and refines three roles
after observed failures; every intermediate bundle and historical store is preserved. [Usage and role formats](usage/baseline-instructions.md)
show the current interfaces.

## Intervention and controls

| Role | Old → new | Instruction change |
| --- | --- | --- |
| Planner | 3 → 4 | Concrete output instance, exact downstream question keys, focused scope and bounded queries |
| Selector | 1 → 2 → 3 | Exhaustive ID classification, metadata-supported relevance, distinct deferral/rejection reasons, history-aware access choices |
| Distiller | 1 → 2 → 3 | Output instance rather than schema, exact source/chunk/question/segment binding, verifiable short quotations and explicit repair checks |
| Analyst | 3 → 4 → 5 | Exact plan/source bindings, evidence-only synthesis, actionable core gaps and valid saved-range requests |
| Writer | 5 → 6 | Raw English Markdown, claim-level citation support, grounded references and concise coverage limitations |
| Reviewer | 4 → 5 | Concrete accept/revise instances and bounded corrections grounded in the supplied evidence |

A concrete pre-existing conflict was removed: Analyst 3 instructions required
`follow_up_reads`, while its task template demanded exactly five root fields and
omitted that field. Analyst 4 consistently requires all six root fields.

Every run uses exactly `What is EBD (Environment Based Design)?`, DeepSeek Flash,
no seed URLs, at most 20 total attempted URLs (failures count), two research rounds,
four parallel Distillers, 20 Distiller calls, four report/review pairs and a
262,144-token context per Agent. Evidence limits remain 131,072 estimated tokens
and 524,288 bytes. Early stopping remains possible. No native JSON enforcement,
new retries, forgiving parsing or different model was introduced.

Before the new live runs, `local/instruction-comparison-20261003/protocol.json`
fixed three sequential full-run attempts and a separate 12-call paired Distiller
replay: two exact historical task inputs, three repetitions per input for each
role revision, no retries. All outcomes are retained. Frozen inputs isolate the
role instruction/template change from live search variation; the full runs test
how all six new roles behave together.

The historical baseline 5 report uses older search tool revisions. The previous
successful baseline 7 report predates its final selection/provenance hardening;
the third baseline 7 attempt used that final code and failed in Distiller. These
are descriptive historical comparisons, not a controlled causal estimate of the
whole workflow. The paired replay is a more direct instruction comparison, still
with a small sample and nondeterministic model responses.

## Evidence locations

All generated requests, stores, raw failed outputs, reports and checks are under
`local/instruction-comparison-20261003/`. Historical stores referenced by the
[Selector comparison](selector-comparison.md) are read-only inputs to this audit.
The standard live driver exercises actual HTTP, SSE replay, saved artifacts,
request idempotency and restart/report identity on every successful trial.

## Follow-up refinement

The fixed revision 8 series completed with one report in three attempts. Trial 1
failed on an OCR quotation after its bounded repair. Trial 2 returned 30 candidate
IDs in both deferred and rejected. Trial 3 produced a report after two rounds and
20 fetch attempts, but treated absence of a single canonical definition sentence
and independent effectiveness validation as required gaps for a definition question.
This first instruction pass did not demonstrate an overall improvement.

A separately recorded follow-up protocol fixes two revision 9 full-run attempts
and six Distiller 3 calls on the same frozen input cases. It does not overwrite or
exclude revision 8. Selector 3 constructs a mutually exclusive partition before
serializing the lists; Distiller 3 prefers short exact quotations and removes
feedback-rejected findings rather than reconstructing OCR text; Analyst 5 ties
required gaps to the actual question and allows synthesis across supported passages.
There are still no executable schema, tool, quota, scheduling or validator changes.

The initial paired replay produced 3/6 nonempty fully valid outputs for Distiller 1
and 2/6 for Distiller 2. Both had 5/6 schema-valid outputs: old Distiller once
returned a JSON Schema; new Distiller once added unsupported `quote_note` fields.
Among parseable outputs, new Distiller retained question keys, but quotation errors
still prevented completion. This is evidence against claiming that longer, more
explicit instructions alone had already solved compliance.

## Full-run results (all attempts retained)

| Method / trial | Outcome | Rounds | URL attempts / successful | Model calls | Observed total tokens | Elapsed seconds | Draft attempts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Historical baseline 5 sample | Report; sufficient | 1 | 10 / 6 | 11 | 319,836 | 83.50 | 1 |
| Baseline 7 trial 1 | Failed: Distiller output schema | — | 10 / 5 | 8 | ≥72,265 | 53.76 | — |
| Baseline 7 trial 2 | Report; sufficient | 1 | 10 / 4 | 11 | 203,482 | 79.59 | 1 |
| Baseline 7 trial 3 | Failed: Distiller validation | — | 10 / 4 | 7 | 56,125 | 47.38 | — |
| Baseline 8 trial 1 | Failed: quotation after repair | — | 15 / 7 | 14 | ≥186,148 | 92.60 | — |
| Baseline 8 trial 2 | Failed: duplicate Selector categories | — | 5 / 2 | 5 | 51,486 | 48.61 | — |
| Baseline 8 trial 3 | Report; partial | 2 | 20 / 8 | 18 | 431,750 | 164.74 | 1 |
| **Baseline 9 trial A** | **Report; sufficient** | **1** | **5 / 3** | **9** | **135,201** | **47.69** | **1** |
| **Baseline 9 trial B** | **Report; sufficient** | **2** | **20 / 5** | **17** | **381,598** | **142.22** | **2** |

Elapsed time is acceptance to recorded terminal; token counts are provider-observed
input plus output, not configured allowances or monetary cost. A ≥ value means an
interrupted sibling has unknown usage: its tokens are not counted as zero. A dash
means no final result/round manifest, not no research activity. Failed trial stores
retain their inputs, outputs, reads and terminal errors. Historical baseline 5 is
one successful reference sample, not a claimed 100% success rate for that version.

Revision 9 produced reports in 2/2 fixed attempts; revision 7 produced 1/3. Across
both instruction-development passes, 3/5 full attempts produced reports. These
small, changing-source samples do not establish a general reliability rate.
Revision 9's two-run mean is 258,399.5 tokens: **27.0% higher** than the historical
successful revision 7 sample, despite trial A being much cheaper. There is no
basis for claiming uniformly lower cost. Tool/model variability and different
amounts of acquired text remain substantial confounders.

## Frozen-input Distiller comparison

Both historical task objects, source/chunk/segment IDs, text and feedback were
replayed unchanged with the same model, schema, 256k context, output limit and no
repair/retry. Revisions render their own instruction and task templates. The first
12 calls interleaved Distiller 1 and 2; the follow-up ran six Distiller 3 calls on
the same cases after revision 9 was frozen. This last group was later in time,
not an additional randomized simultaneous control.

| Distiller | Calls | JSON/schema valid | Exact question/segment bindings among schema-valid outputs | Nonempty output passing production quotation/identity validation |
| --- | --- | --- | --- | --- |
| 1 — prior baseline | 6 | 5/6 | 4/5 | 3/6 |
| 2 — initial instructions | 6 | 5/6 | 5/5 | 2/6 |
| **3 — final refinement** | **6** | **6/6** | **6/6** | **4/6** |

Every final-revision replay returned nonempty findings and correct schema/keys.
Two still failed quotation matching. The production validator allows only its
existing whitespace/PDF soft-wrap normalization and unique-segment correction;
"valid" does not mean every raw quote was byte-identical before those checks,
and it does not score claim entailment. We did not relax validation or count an
empty digest as a successful nonempty extraction. This supports a narrow observed
format improvement, not a claim that prompts guarantee accurate quotation.

## Report quality, after reading the reports

| Dimension | Historical baseline 5 | Successful baseline 7 | Baseline 9 A | Baseline 9 B |
| --- | --- | --- | --- | --- |
| Answer and process | Definition, origin, detailed process, two cases | Similar answer; more process/case exposition | More concise definition/process and two cases | Definition/process, richer 2004 conceptual vocabulary and two cases |
| Primary theory actually read | 2002 theory plus both 1999 papers | Only 1999 Part I among those antecedents | Neither 2002 nor 2004 theory | **2004 environment-based problem formulation** |
| Fully read sources / text bytes | 6 / 251,025 | 4 / 130,917 | 3 / 92,931 | 5 / 144,286 |
| Body citation mentions / top-two share | 42 / 76.2% | 42 / 78.6% | 27 / 85.2% | 51 / 62.7% |
| Approximate words, including references | 1,564 | 1,658 | 1,128 | 1,443 |
| Independent replication established | No | No | No | No |

Trial A is a useful, shorter answer to the actual definition question. Trial B
adds an acquired primary source for product/environment, requirements and recursive
problem formulation. Its lower citation concentration reflects a third substantive
paper, not independent research groups. Both preserve the distinction between
reported case outcomes and independently established effectiveness. Neither is
an exhaustive review, and neither demonstrably surpasses baseline 5 in every
research-quality dimension.

The final scope refinement avoids the initial revision 8 report's misleading
required gap that no *single canonical sentence* combines all elements of the
definition. A supported synthesis can answer the question without such a sentence.
However, report acceptance still does not prove sentence-level attribution. In
trial B's opening sentence, `[r1.source-001]` supports the attribution/brief
identification, while the added claim about requirements and the design driver
needs the fuller primary passages cited elsewhere. This is a concrete residual
citation-support concern; stored reports were not manually corrected or replaced.

Trial B also needed a second draft because the deterministic citation checker
interpreted editorial square-bracket word endings `[ing]`, `[ly]` and `[ied]` as
unknown source IDs. Both model Reviewer decisions were accept; the host caught
this format ambiguity. The final draft passes the existing checker. That extra
Writer/Reviewer pair used real tokens; it is not evidence of better model review.

## Remaining bottlenecks

- **Exact quotation and claim support:** formatting improved in the frozen sample,
  but 2/6 final Distiller outputs still fail quotation matching; Writer/Reviewer
  can also miss a citation whose source only supports part of a compound claim.
- **Source selection and accessibility:** trial B attempted 20 URLs for five
  successful acquisitions. Publisher blocks, redirects, unsupported response
  formats and an image-only PDF remain visible failures. More precise prompts
  do not create access to unavailable full text or supply OCR. Existing source
  delivery and archive integrity passed their checks.
- **Variable acquisition and stopping:** trial A finishes with the core papers in
  round 1; trial B reaches them in round 2 after less useful/failed locations.
  Instructions improve scope decisions but do not fix source ordering or cost.
- **Coverage is method-local:** `sufficient` means the bounded workflow's required
  answer is supported; it is separate from accepted report status and independent
  replication. All dominant sources still belong to one research lineage.

## Verification and retained evidence

- Full regression at revision 8: **1,270 passed**; new role-contract tests:
  **12 passed**. After revision 9 registration/resources: **58 targeted tests
  passed**, including all role schemas/limits/examples, both new method pins and
  real Runtime/SQLite selection integration. The complete suite was not rerun
  after the final instruction-only refinement.
- Isolated built-wheel check loads all method revisions 1–9, the six final role
  bundles (30 resource files), their 256k limits, tool pins and a real model-free
  Storage run. The wheel check passed.
- Read-only integrity/event/artifact/usage checks cover all five new live stores:
  **10,666 checks, zero failures**, including failed trials. All operations/models
  are settled; unknown provider usage remains explicitly unknown.
- Full provenance checks for the three successful new reports: revision 8 trial 3
  **4,263**, revision 9 A **1,693**, revision 9 B **3,621** checks, all zero failures.
  They bind actual source reads, segments/quotations, role invocation inputs,
  selected fetches, model usage, output/export bytes and final report artifacts.
- Real HTTP/SSE replay, request idempotency and reopened byte-identical reports
  passed for all three successful new runs. Both replay Engine stores closed
  completely; their individual failures remain recorded.
- All 90 pre-existing role-resource files and all 30 frozen revision 8 role files
  retain their captured hashes. No history, old role bundle or failed run was
  rewritten to make the comparison look successful.

Local evidence (ignored, never includes credentials in Git):

```text
local/instruction-comparison-20261003/
  protocol.json, follow-up-protocol.json
  request-1.json ... request-5.json
  store-1/ ... store-5/             real SQLite, immutable outputs and failures
  evidence-3/report.md             baseline 8, partial report
  evidence-4/report.md             baseline 9 A, concise report
  evidence-5/report.md             baseline 9 B, theory-enriched report
  replay-store/, replay-results.json
  refined-replay-store/, refined-replay-results.json
  comparison.json, *-metrics.json, storage-audit.json
  audit-3/, audit-4/, audit-5/      full provenance checks
  full-tests.txt, role-tests-final.txt, refinement-tests.txt
  wheel-final/, wheel-final-verification.txt
```

Exact run identities:

| Trial | Method | Run ID |
| --- | --- | --- |
| 1 | 8 | `run_d2ccb3e79c484210b7c52cda7c3e2006` |
| 2 | 8 | `run_386e9691d1754aed94eba9c60085e457` |
| 3 | 8 | `run_9c85042ae205453a94900e2eabc67392` |
| A / 4 | 9 | `run_94617ed40421404bb58b201ec5bb1744` |
| B / 5 | 9 | `run_0392b1f933c849ea844a43dc4a4029e7` |


