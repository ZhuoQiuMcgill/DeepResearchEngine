# Live web baseline — 2026-10-12

Branch: `codex/langfuse-baseline`. The reference baseline strategy and question
were not edited. This run uses local Qwen inference and managed Tavily search/
extraction, not the offline corpus and not the Haiku/Luna web backends.

## Execution

- Question: `What is EBD (Environment Based Design)?`
- Run: `20261012-231549-baseline-local-web-b06a5d-78ba`
- Trace: `0fb6b3a08876c0f7d9005cbd7e1c765e`
- Native trace URL: http://localhost:3000/project/inse691-baseline/traces/0fb6b3a08876c0f7d9005cbd7e1c765e
- Profile: `local-web`; source mode: `tavily-web`.
- Terminal execution status: `ok`; duration 251124 ms.
- One research round; two successful research nodes. The strategy declined a
  follow-up round before finalize/write.
- Eleven search calls and five page-read attempts; one page-read attempt failed.
- Reported cumulative tokens: 98087 input, 10785 output over 13 generations.
- Langfuse v4 Observations API returned 65 observations, including all five
  graph stages, the completed root, model calls, and nested managed-tool spans.
- Native wrapper spans: 11 `web_search`, 5 `read_web_page`; SDK child spans
  represent those same operations and must not be counted as extra searches.
- Source URLs in the report: nine. The report and HTML artifact are saved under
  the ignored run directory. Exported HTML was checked against configured secret
  values: none were present. Its inline script parses; the loopback preview
  returns the live-web artifact and refuses non-artifact paths.

Local inference incurs no model API charge. Tavily charges/quota are not priced
by the ledger; `unpricedServices` explicitly includes Tavily. The zero numeric
estimate is not a statement that this entire run is free.

## Answer scope error

The graph completed, but the report is not an acceptable academic explanation
of Yong Zeng's Environment-Based Design. It conflates that methodology with
healthcare/architecture's Evidence-Based Design and claims the only relevant
usage is one 2023 paper. That conclusion is contradicted by primary material:

- [Yong Zeng's official research page](https://users.encs.concordia.ca/~zeng/research.html)
  describes Environment Based Design as a generic methodology for innovative
  product design, its three steps and ROM.
- [Concordia faculty profile](https://www.concordia.ca/faculty/yong-zeng.html)
  identifies Environment-Based Design as his design theory.
- [His 2011 EBD paper](https://users.encs.concordia.ca/~design/reference/EBD-Final.pdf)
  predates the supposedly sole 2023 usage.

The run record shows the retrieval drift: researcher 1 added healthcare,
architecture and evidence-based design qualifiers to its queries. Researcher 2
searched healthcare principles and hospital outcomes. Neither retained source
list contained a concordia.ca or ebdgo.org URL. A second assignment referred to
the field identified by the first researcher despite parallel scheduling and
no first-to-second result transfer. These observations locate plausible
contributors; they are not a causal experiment separating those contributors.

No corrected question or extra sources were injected into the run afterward.
The original report, decisions, searches and source lists remain unchanged.
A separate `review.json`/`ANSWER_NOTE.md` records the scope error, and the HTML
timeline shows a prominent answer warning. It proves the execution/tracing
integration works, not that a completed run produces a correct answer.

Code checks preceding this run: 37 tests passed, typecheck/build passed. The
scope-note exporter change also passes typecheck/build. Secrets and raw traces
remain in ignored machine-local files, not in Git.
