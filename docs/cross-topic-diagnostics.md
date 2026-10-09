# Baseline 9 cross-topic diagnostics — 2026-10-03

Three exact user inputs were each run once through the real HTTP service,
Engine, model provider, discovery/fetch tools and SQLite. **Two runs failed;
one produced a report.** The purpose was to locate accuracy/coverage losses
outside the workflow's research strategy, not to tune that strategy until the
examples passed. No failed run was discarded or retried as a new research run.

## Fixed experiment

- `baseline@9`: Planner 4, Selector 3, Distiller 3, Analyst 5, Writer 6, Reviewer 5.
- `deepseek` / `deepseek-flash`, unchanged instructions and role schemas.
- At most two research rounds, 20 attempted fetch URLs globally, four draft/review
  attempts, 20 Distiller calls, four parallel workers. Every Agent retains its
  262,144-token context allowance. Synthesis evidence remains bounded by
  131,072 estimated tokens / 524,288 bytes.
- No supplied queries, URLs, travel dates or other task details. The original
  strings below are unchanged; generated search queries are separate data.
- Trials ran sequentially in fresh stores. Independent external fact checks
  were evaluation work and were never supplied to the baseline.
- `protocol.json` freezes 187 role/method/component files; the post-run hash
  comparison found no change. No production workflow, Engine or role was edited.

| Exact user input | Outcome | Fetch attempted / succeeded | Model calls | Provider tokens | Workflow elapsed |
| --- | --- | ---: | ---: | ---: | ---: |
| `compare meta quest 3 and apple vision pro` | Failed: unsupported follow-up page read | 14 / 7 | 9 | 77,117 | 77.903 s |
| `How do I flight from GuangZhou to Montreal?` | Failed: Selector wrapped JSON in Markdown | 10 / 5 | 10 | 78,643 | 61.987 s |
| `What food can help me sleep well?` | English report; host `sufficient`, fourth draft accepted | 10 / 6 | 18 | 521,440 | 120.356 s |

Elapsed time runs from acceptance to `workflow.finished`, excluding the driver's
subsequent HTTP/SSE/restart checks. Tokens are recorded provider usage, including
all drafts and reviews, not estimates or dollar costs. All 37 model attempts have
known usage. These are three observations, not an estimated general success rate.

## Confirmed findings and ownership

| Priority | Observed evidence | Non-strategy cause | Appropriate next change within the existing stages |
| --- | --- | --- | --- |
| P0 | Headsets Analyst requested pages 3–12 from a fully read HTML abstract. Storage returned `UNSUPPORTED_RANGE`; the run ended as `SOURCE_READ_FAILED`. | Instruction violation, incomplete source-capability handoff, insufficient pre-execution range validation and overly broad failure propagation. | Deliver allowed range kinds and actual bounds; validate against the snapshot before executing. Preserve the typed error and permit a bounded corrected decision or an explicit gap. |
| P0 | Flights round-two Selector returned a valid JSON object inside a `json` code fence. Runtime rejected the raw output with `strict_json`. | Output framing, despite an explicit no-fence instruction; native enforcement is disabled. | Use provider-supported structured output where available, or a narrowly defined, recorded envelope normalization / bounded format repair. Keep semantic and ID validation. |
| P1 | Headsets web search succeeded only 3/7 times; fetch succeeded 7/14. Flights fetch succeeded 5/10. | Search backend availability / extraction and source access, independent of research topology. | Address backend challenges and parser coverage using recorded failure types; improve acquisition alternatives for 403, empty static HTML and redirects. Do not equate a finished discovery node with successful search. |
| P1 | Flights recovery removed `total duration stops` from an actual query; a recovery variant dropped Montreal entirely. | Generic query preparation applies scholarly title heuristics and word truncation to travel searches. | Preserve query operators, both route endpoints and the retrieval purpose. Separate bibliographic-title recovery from general search preparation. |
| P1 | Sleep review 1 introduced an unsupported sample size of ten healthy adults; draft 2 adopted it; review 2 then required its removal. | Reviewer grounding failure: correction text can itself introduce new factual content. | Require evidence-bound review issues and recheck facts introduced by a correction. |
| P1 | Sleep draft 2 included the requested no-control-group limitation and fuller references; final draft 4 dropped them and was accepted. | Revision regression and incomplete feedback delivery. The next Writer receives only the previous review's issues; Reviewer receives no issue history. | Carry a persistent issue/status record in stage inputs and explicitly verify earlier material corrections. This does not require a different agent graph. |
| P2 | Sleep report lists many nutrients and mechanisms but omits practical caffeine/moderation guidance already in its supplied evidence. | Instruction priorities and evidence selection inside the model, not missing source access. | Match output requirements to advice/comparison/travel questions; retain material study qualifiers beside claims rather than only in general limitations. |
| P2 | Headset evidence mixes dated comparisons and product revisions; flight pages give contradictory direct-flight claims. Planner has no reference date in its task input. | Freshness, version and uncertainty metadata are not consistently made part of the role contract. | Supply an as-of date and available publication/retrieval dates; require version/market distinctions and explicit missing travel parameters. Do not invent dates or resolve commercial contradictions from memory. |

These fixes are recommendations, **not changes made in this experiment**. Source
budgets, early stopping, the number of research rounds and the decision to use a
Planner/Selector/Distiller/Analyst/Writer/Reviewer remain separate strategy choices.

## 1. Headsets: a bad read request prevented use of evidence already acquired

Run: `run_3b7877ba90084b50a22d5b64856d946f`.

The first Analyst correctly noticed conflicting specifications/prices in dated
commercial articles and requested an official source. Round two actually fetched
and completely read `https://www.apple.com/ca/apple-vision-pro/specs/` (5,619 bytes).
Thus the failure was not simply an inability to find Apple's specifications.

The Analyst also requested this range from `r1.recovery.source-009`:

```json
{"kind":"pages","start":3,"end_exclusive":13}
```

That source was a Springer chapter landing page/abstract, archived as HTML, with
7,418 bytes and 147 indexed lines, no physical page map, and `complete=true`.
The chapter's bibliographic pagination was mistaken for accessible snapshot pages.
The Analyst instruction already forbids inventing page counts. Its delivered
evidence showed a complete line read; however, no explicit machine-readable list
of supported range kinds and bounds was supplied. The host validated the source
ID but not the requested range against the snapshot.

Storage correctly refused the request. `_fulfill_reads` then converted that
specific error into a fatal generic `SOURCE_READ_FAILED`. This happened after
the new round-two acquisitions but before their distillation/analysis. Seven
archives were fully read; only four had reached distillation and synthesis.
There is **no final headset report** to evaluate.

A separate correctness spot check found that the first Analyst preserved PC
Guide's claims of Quest 3 having 12 GB RAM and Vision Pro having 64 GB storage.
Those are source-quality problems, not evidence of corrupted reading: Meta's
[device comparison](https://developers.meta.com/vr/essentials/compare-devices/)
lists 8 GB RAM for Quest 3, and Apple's
[specifications](https://www.apple.com/apple-vision-pro/specs/) list 256 GB,
512 GB and 1 TB storage. The Analyst attributed the commercial table and flagged
hardware uncertainty; it had not produced a final reconciled comparison.

Code: `methods/baseline/parallel_workflow.py` (`analyze.bindings`, `_fulfill_reads`),
`stages/evidence_delivery.py` (`_block`), and Analyst 5 instructions.
Evidence: `headsets-diagnostics/r1.validated-analysis.json`, the source-009 access
record, round-two access records, and the paired failed `document.read` events.

## 2. Flights: the immediate failure was framing, with additional retrieval drift

Run: `run_46c95cc0979f4585823e914ed3f7171b`.

Five retained sources were completely read and distilled. The Analyst correctly
distinguished modeled nonstop flight-time estimates from actual connecting
itineraries, and noticed contradictory nonstop claims in commercial route pages.
It did not establish a verified current itinerary. No travel dates had been
provided, and the run did not reach a final answer.

The round-two Selector's 5,151-byte raw output began with a Markdown code fence.
The model completed normally; output was not cut off by token/byte limits. Runtime
retained the raw result and correctly rejected it as strict JSON. Offline removal
of **only the outer fence** passed both the production schema and candidate
partition/budget validator: all 37 delivered IDs were accounted for, with three
selections. This isolates the immediate termination to framing. It does not prove
the selected sources were substantively good, and the edited output was never
fed into the run.

Recorded query transformation:

```text
Analyst: "C$655 Cheap Flights from Guangzhou (CAN) to Montreal Pierre Elliott Trudeau (YUL)" total duration stops
Executed: "C$655 Cheap Flights from Guangzhou (CAN) to Montreal Pierre Elliott Trudeau (YUL)"
Recovery executed: c 655 cheap flights guangzhou
```

The original over-specific quoted commercial title is an instruction/relevance
issue; removal of the retrieval purpose and destination is a separate host
transformation. The resulting candidate set contained irrelevant Trudeau
biography/history records and broad Guangzhou-departure pages. The failed Selector
recognized many irrelevant records but still selected a generic academic flight
connection modeling paper. Syntax validity alone is not source-quality assurance.

A separate offline probe also confirms that `site:apple.com Apple Vision Pro
specifications` becomes `site apple com vision pro specifications`. This query
operator defect was **not** exercised by an actual live query in these trials.
A suspected product-name deletion was disproved: `"Meta Quest" "Apple Vision Pro"
comparison` loses quoting but retains the product words. The probe record preserves
both results so code-reading suspicions are not reported as observed failures.

Code: `workflows/components/retrieval.py::_prepare`, Selector 3 format contract,
Runtime output validation. Evidence: `flights-diagnostics/failed-selector-raw.json`,
`r2.selection-input.json`, `r2.retrieval.query.0.json`, and `probes.json`.

## 3. Sleep: successful transport and valid citations did not prevent semantic loss

Run: `run_06fa9fcddf834b89a00ed85c80132d2d`.
Report: [retained English output](../local/cross-topic-diagnostics-20261003/sleep-evidence/report.md).

Six sources were fully read (159,702 archived bytes), including the complete
retained text of the 2021 review *Sleep and Diet: Mounting Evidence of a Cyclical
Relationship*. The assembled evidence was 181,213 bytes and fit without dropping
source text. All six sources were also delivered in full to the Writer context.
Four substantive sources supported the host's `sufficient` judgment. The report
names plausible foods, distinguishes some mechanisms from evidence and includes
uncertainty. That is useful, but the quality flag overstates what the review gate
can guarantee.

Observed revision sequence:

1. Review 1 requested important study limitations, but also introduced an
   unsupported `n=10 healthy young adults` description of a cherry-juice trial.
2. Draft 2 copied that number. Review 2 identified it as absent from the supplied
   passage and required removal. The archived review describes participants aged
   18–40 but gives no sample size for that study in the relevant passage.
3. Review 1 also requested a specific no-control-group qualification for the
   initial kiwifruit study and fuller bibliographic references. Draft 2 incorporated
   these changes. Drafts 3 and 4 lost them; review 4 nevertheless accepted.
4. All four deterministic citation/English/coverage-label checks passed. The
   repeated drafts were driven by Reviewer issues, not a broken citation parser.

The no-control-group sentence exists in the archived review, Distiller input and
selected evidence. The final report's kiwifruit bullet still states the observed
improvement without that local design qualification. A general limitations section
does not repair the missing qualifier on that claim. This is not an archive or
context-window problem.

The report also spends considerable space on biochemistry and nutrient tables
while omitting practical caffeine timing, moderate snacks and usable snack examples
from its own Cleveland Clinic source. Those details were present in selected
evidence. They are relevant to an everyday advice answer, as also reflected in
[Cleveland Clinic's guidance](https://health.clevelandclinic.org/foods-that-help-you-sleep)
and [NHLBI's sleep guidance](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits).
This is a task-alignment/coverage issue, not a claim that every food answer needs
an exhaustive medical checklist. Secondary descriptions of trials were not checked
against every original clinical study; no clinical efficacy score is claimed.

Writer plus Reviewer consumed **395,537 of 521,440 tokens (75.9%)**. Later drafts
improved some wording while undoing earlier corrections. More calls alone therefore
did not ensure monotonic improvement.

Code: `stages/reporting.py::write_and_review` overwrites feedback each iteration;
the Reviewer task contains the current report but no earlier issue ledger.
Evidence: `sleep-diagnostics/report.{1,2,3,4}.{write,review}.output.*`,
`r1.selected-context.txt`, `r1.validated-analysis.json` and the saved review text.

## Search, acquisition and delivery accounting

| Layer | Headsets | Flights | Sleep | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `web.search` succeeded / calls | 3 / 7 | 4 / 5 | 2 / 2 | Failed calls retain backend observations; success does not imply relevant results. |
| Fetch succeeded / attempted | 7 / 14 | 5 / 10 | 6 / 10 | 18 successful archives from 34 attempts; rejected/blocked/empty sources are not silently counted as evidence. |
| Fully read archives | 7 | 5 | 6 | All successful archives were read completely. Full archive text is not necessarily a publication's full text. |
| Validated Distiller records | 4 | 5 | 6 | Headsets terminated before processing its three newly acquired round-two archives. |
| Bound Distiller findings | 34 | 34 | 35 | All 15 invoked Distillers succeeded on their first attempt; no observed quotation/key repair in these runs. |
| Sources in last synthesis context | 4 | 5 | 6 | Every selected source's archived byte range was fully delivered. |

Headsets recorded four DuckDuckGo HTTP challenges and four Yahoo
`parser_no_matches` attempts, alongside one `all_candidates_rejected` attempt.
These observations establish availability loss; they do not alone prove whether
each Yahoo response was a challenge page, changed markup or an empty result page.
Fetch failures across the three runs were ten HTTP failures, four empty static
HTML extractions and two redirect failures. Five OpenAlex admissions were denied
with `SCHOLAR_QUOTA_EXHAUSTED`; that code does not identify whether the underlying
allowance was local or provider-observed. Crossref remained available, but often
returned off-topic records for consumer/travel queries.

One complete 924-byte flight calculator was labeled `abstract` by the short-text
hint. The implementation uses a 2,048-byte cutoff regardless of page purpose.
This is a classification weakness worth separating from article completeness;
it did not cause the observed termination or substantive-source shortfall here.

## Verification, scope and retained artifacts

- All three stores: SQLite integrity and foreign-key checks passed; no pending
  operations, orphaned model attempts or missing usage records. The shared
  storage audit performed 5,598 checks with zero failures.
- Source/read/context/provenance audits: 2,215 headsets, 1,941 flights, 2,944 sleep
  checks; zero remaining failures. These overlap storage checks and are not
  independent trial counts or factual correctness scores.
- Another 85 offline delivery checks bound actual Distiller/Analyst invocation
  input digests to saved tasks and verified exact source-byte delivery; all passed.
- The reused audit initially reconstructed long line spans without newline
  delimiters. That produced audit-only mismatches, corrected by respecting the
  recorded reader's range semantics. Snapshot/event bytes were not changed.
- Sleep passed real HTTP/SSE replay, idempotency and byte-identical report access
  after restarting Engine. The failed runs export terminal views and events, not
  a report or a success acceptance file.
- The test driver now accepts `--expected-question` while preserving the default
  exact EBD guard. Explicit/default mismatch guards and failed-run exports passed;
  a separate model-free echo passed HTTP/SSE/restart checks. No full regression
  rerun was needed for an unchanged production baseline.

Example, after creating a request JSON with the exact headsets input and the fixed
settings above (use a fresh store and client request ID for a new trial):

```bash
uv run --locked python examples/live_research_check.py \
  --request local/headsets-request.json \
  --expected-question 'compare meta quest 3 and apple vision pro' \
  --store local/headsets-new-trial --output local/headsets-new-evidence
```

Actual execution used Windows-native `uv.exe --cache-dir .uv-cache run --locked
--offline`; `--offline` prevents dependency downloads, not the requested model and
research tool traffic.

All raw evidence is ignored under `local/cross-topic-diagnostics-20261003/`:

```text
protocol.json, summary.json, context-coverage.json
{headsets,flights,sleep}-request.json
{headsets,flights,sleep}-store/store.sqlite3 and objects/
{headsets,flights,sleep}-evidence/
{headsets,flights,sleep}-diagnostics/
{headsets,flights,sleep}-audit/audit.json
{headsets,flights,sleep}-metrics.json
storage-audit.json, delivery-probe.json, probes.json, harness-checks.json
metrics.py, storage_audit.py, audit.py, export_diagnostics.py,
summarize.py, delivery_probe.py, probes.py, check_harness.py
```

Historical EBD experiments remain unchanged. This experiment changes only the
live-check driver and diagnostic documentation. It does not mark baseline 9 as
generally reliable, repair the identified defects, or claim that citation/hash
validation establishes semantic accuracy.
