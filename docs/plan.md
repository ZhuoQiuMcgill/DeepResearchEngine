# Implementation plan

Scope of this round: implement the shared skeleton and the baseline strategy,
run real tests, and fix problems that do not come from model capability or the
providers' built-in tools (instructions, orchestration, parsing, budget,
recording). The EBD strategy is out of scope; its interface is delivered.

## Explorations

These questions are answered with small real calls before the code that depends
on them is finalised. Results go into the log at the end of this file and into
[design.md](design.md).

| ID | Question | Decides |
| --- | --- | --- |
| E1 | Can LangChain.js pass the search caps (`max_uses` for Anthropic `web_search`/`web_fetch`, `max_tool_calls` for OpenAI) and keep queries, sources, citations and usage counts in the returned message? | Whether adapters use LangChain models or need the native SDK for the researcher call |
| E2 | Is one model call per researcher enough, or does the researcher need a loop (Anthropic `pause_turn`, empty answers after searching)? | Researcher shape |
| E3 | Which Anthropic web tool versions work on `claude-haiku-5-5` (dynamic filtering `web_search_20260209`/`20260318` vs basic `web_search_20250305`)? | Tool versions in the model profile |
| E4 | Does the fixed notes format come back reliably from both models while searching, and does `withStructuredOutput` work for the baseline's planning calls on both models? | Prompt wording, parsing strategy |
| E5 | Does self-hosted Langfuse run here and receive nested LangGraph traces? | Observability setup |
| E6 | What reasoning effort and search settings give usable researchers without excessive tokens on each model? | Default model profiles |

## Phases

| Phase | Work | Done when |
| --- | --- | --- |
| P0 | TypeScript project scaffold: npm, tsconfig, vitest, lint-free build | `npm run build` and `npm test` pass |
| P1 | Explorations E1–E4 with throwaway scripts in `scripts/explore/` | Each has a recorded answer |
| P2 | Contracts (zod), budget, notes parser, strategy interface and registry | Unit tests pass |
| P3 | Provider adapters and researcher | One live researcher run per provider produces a valid `ResearchResult` |
| P4 | Skeleton graph, writer, run records, CLI | One live end-to-end run per provider |
| P5 | Baseline strategy | Live runs of all four questions on both models |
| P6 | Langfuse self-hosting and tracing (E5) | Traces visible for a full run |
| P7 | Test rounds: run, read every report and record, classify each problem, fix the non-model ones, rerun | Two consecutive rounds without new non-model problems, or remaining problems documented |
| P8 | Docs and commit | design.md updated, test log written |

## Problem classification for P7

Every problem found in a run is recorded with one class:

- **Instruction**: a prompt asks for the wrong thing, is ambiguous, or misses a
  rule the model then breaks. Fix the prompt.
- **Orchestration**: wrong data flow, lost results, budget misuse, wrong
  stopping, bad truncation, missing failure handling. Fix the code.
- **Contract/parsing**: output that is fine but not parsed or passed on. Fix
  the parser or contract.
- **Model capability**: the model had what it needed and still reasoned or
  wrote poorly. Record it; do not fix.
- **Built-in tool**: search returned poor or no sources, a page could not be
  read. Record it; do not fix.

A fix must not be tuned to one question. Each fix is checked on all four
questions in the next round.

## Exploration and test log

Entries are added as work proceeds.

### 2026-10-09: E1–E4

Scripts are in `scripts/explore/`. Each conclusion comes from real calls.

- **E1 (LangChain.js passes caps and keeps metadata): yes on both.**
  - Anthropic server tools pass through `bindTools` as raw definitions, including `max_uses`. The `AIMessage` keeps `server_tool_use`, `web_search_tool_result` (URL and title per result) and text citations. `response_metadata.usage.server_tool_use` carries `web_search_requests` and `web_fetch_requests`.
  - OpenAI's `max_tool_calls` goes through `modelKwargs` and is enforced. With a cap of 2, the third call (an `open_page`) stayed in `searching` and was not run, and the model still answered. `additional_kwargs.tool_outputs` holds the `web_search_call` items: each carries `action.queries` (several queries per call) and `action.sources` (with `include: ["web_search_call.action.sources"]`). Text blocks carry `url_citation` annotations whose URLs end in `?utm_source=openai`, so adapters strip that parameter.
  - Native SDKs are not needed.
- **E2 (researcher shape): one model call per researcher is enough on both.** Both providers run the search loop server-side. Anthropic can return `stop_reason: "pause_turn"`, which LangChain does not continue, so the adapter re-sends the conversation a bounded number of times.
- **E3 (Anthropic tool versions on Haiku 5.5): both work.** `web_search_20260209` with dynamic filtering runs: the search goes through code execution, and results are still listed in `web_search_tool_result`, but the text came back without structured citations and URLs were written inline. Basic `web_search_20250305` returned two structured citations. The Models API reports web search and code execution supported for `claude-haiku-5-5`. The default profile uses the dynamic-filtering versions, with the version kept as a profile setting.
- **Budget asymmetry.** One OpenAI `web_search_call` can carry several queries, while one Anthropic `web_search` use is one query. Caps are therefore comparable within a model, not across models.
- **E4 (structured output): works on both models** with the default, `jsonSchema` and `functionCalling` methods for a planning schema. The baseline uses `jsonSchema`.

### 2026-10-09: E5 (Langfuse)

- **Self-hosted Langfuse v4.55.0 runs here** (Docker, 6 containers, health 200) and receives LangGraph spans and generations through `@langfuse/langchain` + `@langfuse/otel`.
- v4 runs in `events_only` mode, so `/api/public/traces` and `/sessions` are unavailable. `/api/public/v2/observations` works for checks.
- **Bug found and fixed:** the OpenTelemetry SDK is process-global. Starting and shutting it down per run lost every span of concurrent runs: only 5 of 8 traces arrived, with no Luna run among them. Now the SDK starts once per process, each run only flushes, and the CLIs shut it down at exit.

### 2026-10-09: Round 1 (baseline v0, 4 questions × 2 models)

All 8 runs completed with no researcher failures, and no run used the follow-up round. Problems were found by reading every decision, note and report: by hand, plus two independent review agents.

| Problem | Class | Fix |
| --- | --- | --- |
| Planner committed to guessed meanings when unsure. For EBD on Haiku, 2 of 3 researchers went to game art or climate design. On Haiku it also assumed facts about the asker (a Chinese passport for the flight question). Cause: our "choose the most plausible interpretation" rule. | Instruction | Planner keeps the question's wording, adds no assumptions about the asker, and does not guess an unknown term's field; it makes establishing the meaning part of the assignments. |
| Haiku with dynamic-filtering web tools: generated code called `web_search` with `{"params":{...}}`, giving `invalid_tool_input`. One sleep researcher lost 5 of 8 searches. | Configuration (orchestration) | Haiku profile uses the direct `web_search_20250305` / `web_fetch_20250910`. |
| A researcher's notes were cut at `max_tokens` (16k, thinking included). | Configuration | Haiku 21k (non-streaming SDK limit), Luna 32k. |
| URLs containing parentheses were cut at `(`, which corrupted source matching. | Parsing | Balanced-parenthesis URL extraction, with tests. |
| All 4 Haiku reports narrated a research process in the first person ("I found no ..."). | Instruction | Writer rule; researchers write notes impersonally. |
| "Cited URL not reported by provider" flags were all false positives: the same page appeared with a different query string. The flagged URLs were also mixed into `sources`. | Contract/parsing | Page-level comparison ignores the query string. Unlisted citations go to a separate `unlistedCitations` field. |
| Conflicts between researchers (price, OS release status, battery, weight) were silently resolved by the writer. Whole note topics were dropped. Claims were sometimes cited to the wrong source. | Instruction | Writer rules: surface disagreements with both sources; use every researcher's key findings; keep each claim with its own URL; cite numbers in the same sentence. |
| Overlapping briefs (a separate "recent changes" brief duplicated others) produced the conflicts above. | Instruction | Planner rule: every fact belongs to exactly one assignment; cross-cutting bounds go into constraints. |
| The gap check saw only takeaways and gaps, not findings, conflicts or tool errors. | Orchestration | Gap check receives the full notes plus observed problems, and contradiction on a key point counts as critical. |
| The coordinator's interpretation never reached the writer. | Contract | Planner outputs `interpretation`; baseline `finalize` passes it as `guidance`. |
| Citation check only tested that a URL exists somewhere in the notes. | Orchestration | Added a heuristic binding diagnostic: numbers in a cited report sentence should appear in a notes line citing the same URL. It is noisy (unit conversion and rounding are flagged), so it is used only to compare rounds. |

Recorded but not fixed:
- Model capability: few page reads, so reports rest on snippets. Section count sometimes 6. Command-style headings. An occasional finding without a URL under Cited Findings. A language slip in one planner objective.
- Built-in tools: ResearchGate and similar pages not accessible to `web_fetch`; `url_not_in_prior_context` when Haiku tried to fetch a URL from memory.
- Baseline design: briefs that depend on each other run in parallel (flight transit rules before the hubs are known). This is a property of the baseline being compared, not a defect to fix in it.

Round 2 ran with the planner, tool-version, token-limit, URL and first-person fixes. The planner no longer guessed EBD's field or the asker's passport. Haiku first-person mentions fell from 18 to 6 across its 4 reports.

### 2026-10-09: Round 3 (all round-1 fixes)

All 8 runs completed. Langfuse received all 8 traces, with generations from both providers.

| Measure (8 reports) | Round 1 | Round 2 | Round 3 |
| --- | --- | --- | --- |
| First-person narration (matches) | 18 | 6 | 0 |
| Cited sentences with numbers checked | 67 | 159 | 113 |
| ...whose numbers are absent from the notes line citing that URL* | 4 | 19 | 10 |
| Cited URLs absent from all notes | 0 | 3 | 2 |

\* All rounds are recomputed with the final heuristic, which compares whole notes lines. Most remaining flags are rounding or unit conversion. The writer now cites numbers far more often (67 to 113–159 checked sentences), while the flagged share stays around 6–12%. The fixes made citations more checkable; the heuristic shows no measurable change in misattribution.

Both unknown URLs are model output errors that the diagnostic caught. Haiku wrote a truncated `https://www.jstage.jst.go.jp'`. Luna shortened a Concordia repository PDF link to its parent record.

No run used the follow-up round. The gap rationales consider conflicts and weak spots, and judge them non-critical for these four questions, which matches the baseline's "only if absolutely necessary" rule.

**E7 (follow-up round triggers when needed): yes, on both models.** `scripts/explore/e7-gap-check.ts` replays a saved run with the hardware researcher marked as a provider failure. Both models launched exactly one targeted follow-up brief and explained the missing subtopic.

An independent review of the 8 round-3 runs found that most round-1 fixes held: disagreements were surfaced with both sources, every researcher's findings were used, and 30 spot-checked numbers matched their notes and URLs, with two misattributions. Remaining problems and round-4 fixes:

| Problem | Class | Fix |
| --- | --- | --- |
| `interpretation` was filled in every run and mixed instructions into the reading; 5 of 8 reports opened with meta lines copied from the guidance | Contract/instruction | Filled only for genuinely ambiguous questions, as one plain sentence. Writer mentions it only where it changes the answer, never as the opening. |
| Coordinator narrowed questions with default populations ("adults", "generally healthy", "mainland China") or widened them ("Quest 3 family", other EBD expansions although the question spells it out) | Instruction | Rule: neither narrow nor widen what the question names; a spelled-out term means what it says. |
| Gaps written as process ("did not open full texts") were copied into reports as narration | Instruction | Gaps state the status of the evidence. The writer rewrites any process statement and avoids I/we/searched/retrieved. |
| Citations to pages the tools never reported reached 4 reports | Orchestration | The skeleton marks such links "(unverified link)" in the writer's material, for every strategy. The writer may not rest a key claim on them alone. |
| Writer cut URLs short (`https://www.jstage.jst.go.jp'`, a Concordia PDF shortened to its record page) | Orchestration | After writing, an unknown URL that is a prefix of exactly one known URL is completed. Repairs are recorded in the diagnostics. |
| Every link labelled "Source" | Instruction | Links are labelled with the publisher or page title. |

Recorded, not fixed: Luna places citations at paragraph ends and stops early, using 3 searches for EBD and none for fares in the flight question. Haiku still writes some first-person notes and rarely opens pages. One Haiku note cited a likely fabricated ResearchGate URL; the unverified-link marking now applies to such cases.

### 2026-10-09: Round 4 and stopping point

All 8 runs completed (`20261009-0647*` to `-0650*`).

| Measure (8 reports) | Round 3 | Round 4 |
| --- | --- | --- |
| First-person narration | 0 | 0 |
| Cited URLs absent from all notes | 2 | 0 |
| Cited sentences with numbers checked / flagged | 113 / 10 | 144 / 11 |
| Reports opening with meta text about the reading | 5 | 0 |
| Links marked unverified in the writer's material | – | 10 (2 Luna runs) |

Every report now opens with the answer. Haiku left `interpretation` empty for all four clear questions. Luna still filled it, but the writer no longer leads with it. Haiku's sleep briefs still say "focus on adults", which is a residual narrowing despite the rule. The flight briefs cover Chinese citizens in depth and summarise other passports, which follows the "common cases" rule.

**Stopping here.** The remaining problems are model behaviour or tool limits, not pipeline defects:
- Luna places citations at paragraph ends, stops researching early (EBD: 1 researcher, 3 searches), and fills `interpretation` when it is not needed.
- Haiku rarely opens full pages, still writes some notes in the first person, and keeps some default-population constraints.
- Built-in tools cannot open ResearchGate or ACM pages, and OpenAI does not report every page behind a citation.
- The baseline never needed its follow-up round on these four questions. E7 shows that it triggers when an essential subtopic is missing.

Further fixes should come from a new class of failure on new tasks, not more patching of these four questions.

Spend: 33 live runs plus explorations. The provider dashboards show $5.57 for Anthropic (tokens $1.38, web search $4.19) and $2.70 for OpenAI on 2026-10-09, about $8.3 in total. The run summaries had estimated $12.94: they applied Haiku's long-prompt tier to the cumulative input of server-side search loops, which the bill did not. The estimator now uses base rates, and recomputing from the records reproduces both bills ($1.37 + $4.17 and $0.42 + $2.25).

Claude costs more because of the search billing unit. Anthropic bills each query: 419 queries, 417 billed searches. OpenAI bills each `web_search_call`, which averaged 3.9 queries: 867 queries, 225 billed calls. Token prices are equal. Haiku's 3.4× larger input (full search results in context) adds only about $1. Per run, Haiku cost about $0.33 and Luna about $0.17.

### 2026-10-09: E8 (explicit Haiku effort)

The Haiku profile now sets `effort: "medium"`, sent as `output_config.effort` through `ChatAnthropic`'s `outputConfig`. Before this, all Haiku runs relied on the provider default, which was also `medium` with adaptive thinking. Luna's `reasoning.effort: "medium"` was already explicit. `scripts/explore/e8-effort.ts` captured the outgoing requests:
- plain, structured-output (merged with `format`) and web-tool researcher calls all carried `effort: "medium"`;
- the API accepted all three.
