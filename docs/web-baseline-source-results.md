# Live baseline with source relay — 2026-10-13

Branch: `codex/langfuse-baseline`; research revision `b0656c0`. Main was neither
merged nor changed. See [the mechanism](source-relay-and-read-recovery.md).
All previous reports and traces are preserved in their original directories.

## Run and outcome

- Exact question: `What is EBD (Environment Based Design)?`
- Command: `npm run check-strategy -- --strategy baseline --model local-web --task ebd --researchers 10`
- Run: `20261013-060908-baseline-local-web-b06a5d-0051`
- [Native Langfuse trace](http://localhost:3000/project/inse691-baseline/traces/54ea6f638d1c4e8a74fba15aecfee42a)
- Local Qwen, 262144-token server slot, Q4_K_M weights/Q4 KV; actual Tavily web
  search and advanced extraction. No offline-corpus fallback or answer injection.
- Execution `ok`; 523110 ms (8 min 43 s); two rounds, four successful researchers.
- Eight searches, 23 provider page-read attempts: 22 returned usable text, one failed.
- Zero unlisted citations in all four researcher results; zero unknown report URLs.
- Three follow-up nodes cited respectively six, seven and nine inherited source
  entries, retaining `originBriefId: r1-b1`. These are per-node counts, not unique
  sources or fresh reads. New detailed page reads remain separate tool operations.
- Synthesis contains 62 source registry entries with origins/access states;
  the registry also appears in the recorded writer input. There is no false
  cross-node source annotation diagnostic.
- All eleven required strategy interface checks passed. Forty-five controlled
  tests, typecheck and build passed.
- Cumulative reported tokens: 217220 input, 21759 output, over 19 generations.
  This is aggregate usage, not one context-window measurement or a speed benchmark.
- Local API inference estimate is zero; Tavily search/extraction costs remain unpriced.

The final report, **Defining Environment-Based Design as a Methodology**, retains
Zeng's engineering methodology, explains its activities and knowledge methods,
and identifies limits of accessible source material. It does not replace the
question's subject with Evidence-Based Design.

## Remaining inaccessible page

The ACM abstract endpoint for the 2004 formulation paper could not be read:
`https://dl.acm.org/doi/abs/10.5555/1275831.1275835`.
The tool returned a structured `unavailable` response with the query suggestion
`Environment-Based Formulation Of Design Problem author manuscript full text`.
The URL was not replayed. It was the researcher's last allowed read; no hidden
recovery search was made afterward. A Concordia PDF copy had already been found
and read earlier, so the notes distinguish that available support from the
inaccessible ACM page. The failed endpoint remains `readState: failed`, and the
diagnostic remains in the summary. This is graceful handling, not a claim that
an external site's access problem has been eliminated.

The report also acknowledges missing portions of formal mathematical content
and unavailable full journal text. An extract operation returning text is not
proof that it contains the entire paper. Two numeric claim/source-line binding
flags remain: an inferred decade and a publication-year attribution. These
are recorded separately from URL provenance and have not been silently cleared.
The report remains a research draft rather than publication-ready prose.

## Timeline delivery

The ignored run directory is
`local/checks/20261013-060908-baseline-local-web-b06a5d-0051`.
It holds per-node results, decisions, synthesis, report, summary and exported
observations/HTML. The loopback viewer at http://127.0.0.1:5182/ serves this run.

There are exactly 100 observations: eight outer search spans and 23 outer read
spans, along with SDK children, model calls and graph stages. SDK children are
not additional provider operations. The old exporter incorrectly rejected an
exactly-full terminal page when `meta.cursor` was absent. The
[official V2 pagination contract](https://langfuse.com/docs/api-and-data-platform/features/observations-api)
uses cursor absence as the end condition. The export now follows it; a separate
request with limit 1000 returned the same 100 observations and empty cursor
metadata, including completed root/write records.

Configured secret values are absent from both artifacts. The inline script
parses, the loopback viewer serves the new run, and other server paths return 404.
Original historical results were not rewritten or imported into this run.

This run demonstrates registered cross-node source relay and honest read-failure
handling on this question. Changes in search/model responses and task allocation
mean it is not a controlled causal comparison or a general reliability claim.
