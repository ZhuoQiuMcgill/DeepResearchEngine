# Numeric source binding revision — 2026-10-14

Branch: `codex/langfuse-baseline`; main and the EBD strategy remain unchanged.
The original fixed question and historical run artifacts remain unchanged.

## Diagnosis

The previous two cited-sentence flags had different causes. The ACM publication
year 2011 appeared explicitly in the notes' matching citation label, but the
checker removed labels before extracting numbers. That caused a false alarm.
The `mid-2000s` expression came from an uncited inference line; the cited
findings established exact 2004/2007 dates, not that approximate claim. It
should not be accepted simply because it shares a decade with source dates.

## Changes

- Bibliography-label years can support a matching report reference such as
  `2011 paper`, using the same URL. They cannot support quantities such as
  `2011 participants`. Arbitrary label numbers and digits in URLs/DOIs remain
  excluded. This is a narrow reference-date rule, not broader claim support.
- Checked numerical units without citations are now flagged too; a revision
  cannot escape the check by removing the source but retaining the number.
- Multi-sentence quotations stay with their trailing citation. Separate
  uncited sentences cannot borrow a later unrelated sentence's source.
- Writer instructions retain exact source-backed dates and distinguish paper
  publication years from method origin. They prohibit turning dated papers
  into unsupported approximate decades or coinage dates.
- If the generated report has flagged numerical/date units, the writer can
  make exactly one extra model call with the same original notes and source
  registry. It returns structured edits for indexed full statements, supplied
  with exact source-specific candidate notes. Both draft and edits are real
  traced generations; the extra usage is recorded normally.
- Each replacement must have zero numeric-support issues and only registered
  source URLs before it is accepted. Unsupported candidates are not published:
  their original statement units are omitted, with original text and action
  retained in the summary's edit audit. All unflagged prose is preserved. The
  final report is checked again; any remaining issues are retained. No extra
  research or hidden retrieval is introduced.
- This strict source gate followed a real-model test where whole-report revision
  repeated four unsupported statements. That intermediate run is preserved;
  its successful execution was not counted as passing the numeric criterion.

## Limits

These checks compare numerical statements with cited notes and bibliographic
metadata. Matching a number does not prove the surrounding semantic claim,
units, population, causality, or the original page's accuracy. Single-digit
values remain outside the existing heuristic's coverage. Version-1 output
contracts and all historical summary files are preserved.

53 controlled tests passed, including reference-year false alarms, incorrect
years, misused label/URL digits, unsupported decades, missing citations,
quotation/abbreviation boundaries, bounded revision, citation-dropping attempts and invented
replacement URLs. Modern bibliography-label years (1900–2099) are recognized.
Typecheck/build also passed. A separate actual local-Qwen/Tavily baseline run
assesses the final output and required strategy interface checks.

The live result and separately recorded source-backed abbreviation restoration
are documented in `docs/numeric-baseline-results.md`. Original model output is
retained; finalization never silently overwrites historical run records.
