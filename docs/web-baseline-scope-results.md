# Source-first live web baseline — 2026-10-13

Branch: `codex/langfuse-baseline`; tested code revision: `b3ff07d`.
Main was not merged or modified. The baseline method changed; see
[the mechanism and its limits](baseline-concept-scope.md).

## Actual run

- Question, unchanged: `What is EBD (Environment Based Design)?`
- Run: `20261013-051328-baseline-local-web-b06a5d-2f12`
- Trace: `4f312b1bffc6b79c600539a12df68964`
- [Native Langfuse trace](http://localhost:3000/project/inse691-baseline/traces/4f312b1bffc6b79c600539a12df68964)
- Model: local `qwen38-local-256k`, Q4_K_M weights, Q4 KV, actual server slot
  capacity 262144 tokens. Thinking disabled; same local-web profile and tool budget.
- Retrieval: actual managed Tavily Search/Extract; no offline-corpus fallback.
- Execution: `ok`; 353341 ms (5 min 53 s), excluding model cold start.
- Two research rounds, three successful researchers, no failed researchers.
- Thirteen searches; ten provider page-read attempts, seven successful and
  three failed. A further read request was rejected locally because the URL
  came from prior-round context rather than that researcher's own search.
- Cumulative reported usage: 134996 input / 14844 output tokens, 17 generations.
  These totals are across calls, not a single context-window measurement.
- Export: 82 Langfuse observations. There are 13 outer search spans and 11 outer
  read spans, including the locally rejected read. Nested SDK spans must not be
  counted again. Provider page-read usage remains ten, not eleven.
- Fifteen report URLs; no unknown report URLs, unlisted researcher citations
  or output-truncation diagnostic. URL provenance does not establish claim accuracy.
- Local inference API estimate is zero; Tavily quota/credits remain unpriced.

The ignored local directory is
`local/langfuse-web-baseline-fixed/20261013-051328-baseline-local-web-b06a5d-2f12`.
It holds the original question, config, decisions, per-researcher notes/results,
synthesis, report, summary, exported observations and timeline HTML. The
loopback viewer at http://127.0.0.1:5182/ now serves this run. Configured secret
values are absent from both exported artifacts; the HTML script parses and
other server paths return 404.

## Scope outcome

The identity researcher's initial searches were:

1. `"Environment Based Design" EBD`
2. `"environment-based design" definition`
3. `Yong Zeng "environment-based design" methodology Concordia`
4. `"environment-based design" Zeng "three activities" environment analysis`

The first two queries did not assume a field. The later author-specific queries
followed actual search results; no author, preferred website, gold answer or
offline paper was injected into the assignment. The first-round notes identified
Zeng's engineering methodology and surfaced Design Society publications,
Concordia theses and the defining journal article. The planner then used those
notes to assign theoretical mechanics and engineering applications. Every
second-round assignment received the same prior-round notes explicitly.

The final report is titled **Defining Environment-Based Design as a
Transdisciplinary Methodology**. It identifies the subject as Yong Zeng's
Environment-Based Design, explains environment analysis, conflict identification
and solution generation, discusses ROM and recursive environment updates, and
describes engineering cases. It no longer claims Environment-Based Design is a
misnomer or replaces it with healthcare's Evidence-Based Design.

An independent post-run check of the
[official Concordia faculty profile](https://www.concordia.ca/faculty/yong-zeng.html)
supports that central identity: the profile says Zeng proposed Environment-Based
Design. That check happened after the run and was not fed into it.

## Comparison and remaining limits

| Observation | Earlier baseline | Revised baseline |
| --- | --- | --- |
| Field before source discovery | Healthcare/architecture assumptions | No field assumed in initial concept searches |
| Parallel dependency | One assignment required another's future answer | Source discovery completed before dependent assignments |
| Final subject | Evidence-Based Design substituted for the question | Environment-Based Design retained |
| Rounds / researchers | 1 / 2 | 2 / 3 |
| Runtime | 251124 ms | 353341 ms |
| Searches / provider reads | 11 / 5 | 13 / 10 |

This single rerun shows the observed scope failure did not recur. It does not
prove general reliability or isolate the causal contribution of scheduling
versus prompt changes. The earlier record is unchanged and remains documented
in `docs/web-demo-results.md`.

The defining 2015 article's full text and a ResearchGate page remained
unreadable. Some findings therefore rely on search excerpts or secondary
documents. The report acknowledges missing theoretical details and the lack of
an accessible head-to-head quantitative comparison. It also includes tangential
historical claims about the other EBD acronym; these have not undergone full
claim-by-claim scholarly review. Treat the report as a research draft whose
central subject is corrected, not as publication-ready prose.

Code checks: 40 controlled tests passed; typecheck and build passed. Controlled
tests assess scheduling, context delivery, scope preservation and stopping;
the above separate real-model/tool run assesses the resulting answer.

## Required live strategy check

`npm run check-strategy -- --strategy baseline --model local-web --task ebd
--researchers 10` also completed successfully, with all eleven interface checks
passing. Its separate run is `20261013-052311-baseline-local-web-b06a5d-a2b6`,
trace `9a662ebc4504aa196979cf6c2f166206`, under ignored `local/checks/`.
It ran two rounds/four researchers in 451164 ms, with thirteen searches and
thirteen provider page-read attempts. Its final report also retained Zeng's
Environment-Based Design rather than substituting the other acronym meaning.

All researchers completed and there were no provider-read failure diagnostics.
However, the three follow-up researchers collectively cited six URLs that
their own tools had not returned (URLs carried in prior notes). The system
recorded those per-researcher issues and marked 34 link occurrences in synthesis;
34 is not a count of unique sources. Report URLs were all present somewhere in
the run's research sources, so the interface check passed. This difference
between run-wide source provenance and individual-node source provenance
remains a limitation, not something hidden by the successful interface status.
The viewer continues to show the primary rerun above; no report was overwritten.
