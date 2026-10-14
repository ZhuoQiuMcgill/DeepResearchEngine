# Numeric source support — live baseline, 2026-10-14

Branch: `codex/langfuse-baseline`. Main was not merged or modified; all original
questions, research notes, reports and summaries remain in their run directories.
See [the mechanism](numeric-source-binding.md).

## Delivered run

- Verbatim question: `What is EBD (Environment Based Design)?`
- Run: `20261014-064755-baseline-local-web-b06a5d-5d4e`
- Research/writer revision: `4d7d9a6`, followed by the abbreviation-boundary
  correction and source-backed report finalization described below.
- [Native Langfuse trace](http://localhost:3000/project/inse691-baseline/traces/6c6733fc324d74d519ee128f5769cef9)
- Actual local Qwen inference plus Tavily search/advanced extraction, no offline
  fallback or gold-answer injection.
- Two rounds; four successful researchers; execution duration 990064 ms
  (16 min 30 s), excluding cold starts and later editorial finalization.
- Sixteen searches and fifteen provider reads; fourteen reads returned usable
  content, one remained unavailable. The source gap is retained.
- Twenty-four checked numerical report units; **zero residual source-binding
  flags**, no unknown report URLs, no unlisted researcher citations.
- The draft had eleven flags. Eight indexed units received source-linked
  replacements; the initial gate omitted three units. Finalization restored
  one supported abbreviation fragment, leaving **two audited omissions**.
- All twelve live strategy checks passed, including the newly required numeric
  source-support check. Fifty-three controlled tests, typecheck/build passed.
- Cumulative reported usage: 343104 input / 24298 output tokens over 23 model
  generations. The writer made two calls: draft and structured statement edits.
  Aggregate usage exceeding 262144 is not a single context-window measurement.
- Export: 107 observations across two V2 API pages. SDK child spans are not
  additional searches/reads. The local viewer at http://127.0.0.1:5182/ shows
  the finalized report and expandable before/after statement records.

Local model API cost is zero; Tavily credits remain unpriced. Source matching
does not establish every semantic claim's accuracy. Because this output gate
enforces support or omission, zero residual flags is an output-policy property,
not independent proof that the model became universally more accurate. Output
coverage, omission counts and original statements must accompany that metric.

The report retains Zeng's Environment-Based Design, its three activities,
axiomatic foundations and ROM, with inline sources and accessibility limits.
It no longer carries the unsupported approximate-decade statement. Paper
publication dates in bibliography labels are recognized as reference metadata,
without allowing label/DOI digits to support numerical quantities.

## Finalization and immutable originals

Manual review found a formatting fault: `J.` in a parenthesized journal name
was split as a sentence ending. The strict gate consequently omitted a
source-backed prefix and left an orphaned journal reference. The parser now
preserves parentheses, bracketed citations and common scholarly abbreviations.
A regression test covers that exact class of boundary.

`scripts/recheck-omitted-units.ts` recovered the original prefix from the real
recorded draft, using a unique surviving context anchor. It restored it only
after the resulting complete report had zero numeric flags and no unknown
source URLs against the same original research results. No facts, sources,
model calls or searches were added during this deterministic finalization.

The original `report.md`, `summary.json`, model generations and gate audit stay
unchanged. The delivered text is saved separately as `report-final.md`;
`review.json` records the restoration and final binding check. The exported
payload records which report file it displays. The two other omitted units
were an uncited date-heavy definition summary and unnecessary conference
reference/citation-count details. Original text remains available in the audit.

Configured secret values are absent from both exported artifacts. The HTML
script parses; the loopback server serves the finalized report and other paths
return 404. The report remains a research draft, not publication-ready prose.

## Preserved intermediate attempts and local settings

| Run suffix | Outcome | Trace |
| --- | --- | --- |
| `060024…faf2` | CUDA `unknown error` terminated the local server; no report | `32e2b8b4994c0518b7f350386d077087` |
| `061736…0c4f` | Full network execution completed; whole-report revision still left four numeric flags, so the required check failed | `ee85683238e0a54b0bf351bb57ebb4c9` |
| `064755…5d4e` | Source-ledger statement edits passed all required checks, followed by audited abbreviation restoration | `6c6733fc324d74d519ee128f5769cef9` |

The failure's exact hardware/driver cause is not established. Subsequent runs
used conservative local settings: graph concurrency 1, physical batch 128,
logical batch 512, prompt RAM cache 0, context checkpoints 0, 6144 MiB fit
margin per device, and `GGML_CUDA_DISABLE_GRAPHS=1` (supported by the installed
llama.cpp source). The model retained Q4_K_M weights, Q4 KV, one slot and actual
262144-token context. No other GPU programs were stopped. Launch-script values
remain optional environment overrides rather than global driver changes.

The successful run was invoked with:

```powershell
npm run check-strategy -- --strategy baseline --model local-web --task ebd --researchers 10 --concurrency 1
```

Runtime/task allocation changed between attempts; this is not a controlled
causal benchmark. Intermediate failures were not hidden or counted as success.
