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

### 2026-10-09: Platform, module and strategy plug-ins

Decision: the EBD team develops the whole EBD strategy module. The platform side provides the outer layers, the plug-in mechanism and baseline as the example module.

- **Plug-ins:** a strategy is `src/strategies/<name>/` default-exporting a `StrategyModule` (`name`, `description`, `contractVersion`, `create(options)`). Modules are loaded lazily by name, so a broken module affects only runs that select it. `_template/` is a minimal copy-and-edit start; it is type-checked and tested but never offered as a strategy.
- **Contract v1:**
  - `src/core/index.ts` is the only import surface, and `ctx.today` is shared by all components.
  - Strategy options come from the experiment spec.
  - Material must be researcher notes lines; the module records violations, and `check-strategy` fails on them.
- **Module and platform:**
  - `runResearchModule` takes injected strategy, profile and budget, and writes no files.
  - `runOne` and `runExperiment` handle strategy and model resolution, records, tracing and cost.
  - Experiment specs (`experiments/*.json`) choose tasks × strategies (with options and labels) × models × repeats × budget, and names are validated before any spend.
- **Verified live:** `check-strategy` passed all checks on baseline (Haiku, EBD question). `experiments/smoke.json` completed on both models.

### 2026-11-20: E9 (DeepSeek provider)

Question: can DeepSeek run both strategies with the same contracts and records as the other two providers? Probes are in `scripts/explore/e9-deepseek.ts` (single API calls) and `scripts/explore/e9-researcher.ts` (one researcher through the real adapter and prompt). Raw response bodies are in `local/explore-deepseek/`; the trimmed ones under `tests/fixtures/deepseek/` back the adapter tests.

- **Model: `deepseek-flash`** (DeepSeek-V4.1-Flash on the pricing page). Web tools worked on it on both the Anthropic-compatible Messages endpoint and Responses, as the Web Tools guide says. `deepseek-v4-pro`, used in the Anthropic page's example, was not probed.
- **Tools on the Messages endpoint.** It accepts `web_search_20250305`, `web_search_20260209`, `deepseek_web_search` and `deepseek_read_url`. `web_fetch_20250910` returns 422, so there is no page reading next to a capped search. `ChatAnthropic.bindTools` rejects the `deepseek_*` types, so the adapter sends tools as raw request fields.
- **Cap.** `max_uses` on `web_search_20250305`/`20260209` is enforced: further attempts get `max_uses_exceeded` (cap 2: 2 run, 2 rejected; cap 3: 3 run, 1 rejected). With `max_uses: 12`, every request stopped after 5 executed searches and rejected the 6th: a probe that asked for 10 searches, 4 probe researchers and all 19 researchers of the acceptance runs below. `deepseek_web_search` (deep thinking search with `open_page`) cannot be capped. It accepted `max_uses: 2` silently and made 5 tool calls; on Responses, `max_tool_calls: 3` came back as `null` and 10 calls ran.
- **Response contents.**
  - `web_search_20250305`: one `input.query` per `server_tool_use`. Each `web_search_tool_result` lists `title`, `url`, `page_age` and `snippet`. A rejected search is an array holding one `web_search_tool_result_error`; Anthropic sends an object instead.
  - With thinking on, the text had no structured citations; URLs are inline.
  - Deep search: `input.action` is `search` with up to 3 `queries`, or `open_page` with a `url`. Each page open returns a `web_fetch_tool_result` with URL and title, but no page text. `web_search_result_location` citations came back in 1 of 2 runs.
  - URLs carry DeepSeek result markers (`#1`, `#1#6#1`). The adapter removes them in sources, citations and notes.
- **Usage.**
  - `input_tokens` excludes cache hits. `cache_read_input_tokens` was 49–59% of researcher input in the acceptance runs, so the ledger now records cached input tokens and prices them at the profile's cache rate. Profiles without that rate (Haiku, Luna) are priced as before.
  - In `server_tool_use`, `web_search_requests` counts every search result block, rejected ones included. `web_fetch_requests` counts fetch blocks. `tool_search` counts executed queries that returned results. `tool_fetch` stayed 0 with page opens.
  - The adapter checks the blocks against these counters. They agreed in all 23 researcher runs (19 in acceptance, 4 in probes).
- **`stop_reason: "tool_use"`.** When the model kept searching after rejections, the server sometimes ended the turn with no notes. This happened to 6 of 11 researchers in the first acceptance runs (empty failures). Re-sending the reply as the last message returns 400. Adding a user turn that asks for the notes, with `tool_choice: "none"`, returned the notes. The adapter does this once and records it as a diagnostic.
- **Structured output.**
  - Baseline's `jsonSchema`: the Messages endpoint ignores `output_config.format` (Markdown reply, nothing parsed). Chat Completions rejects `json_schema` with 400. Responses honours `text.format` `json_schema` with reasoning on.
  - EBD's unforced submit tool works on both Messages and Responses.
- **Settings.** The Messages endpoint takes `output_config.effort` (`low`, `high`, `max`; `medium` maps to `high`) and treats `thinking: adaptive` as enabled. Thinking is on by default. `ChatOpenAI` drops `reasoning` for non-OpenAI model names, so the profile sends it in `modelKwargs`; the response echoed effort `high`.
- **First decision, superseded the same day (see "Deep search" below).**
  - Profile `deepseek`: the researcher used the Messages endpoint with `web_search_20250305` and `max_uses: 12` (enforced by the API; 5 in effect). Strategy roles and the writer use Responses. All calls run with thinking on at effort `high`.
  - `toolCallsPerResearcher` stays 12, as for the other profiles. This capped setup is now the documented alternative.
- **Pricing** (pricing page, read 2026-11-20): $0.15 per 1M input tokens on a cache miss, $0.003 on a cache hit, $0.6 per 1M output tokens, at off-peak rates. Peak hours (01:00–04:00 and 06:00–10:00 UTC on weekdays) cost twice as much; the estimate ignores them so cost follows tokens only. Server-side search and fetch are unbilled since 2026-11-18 (pricing page and Web Tools guide), so `perSearch` is 0.

Live acceptance of the capped setup (`check-strategy`, EBD question, 6 researchers, run records in `local/checks/`):

| Run | Checks | Researchers (ok/failed) | Searches | Cost | Time |
| --- | --- | --- | --- | --- | --- |
| baseline, before the continuation (`20261121-025819-baseline-deepseek-b06a5d-9531`) | all pass | 5 (2/3) | 25 | $0.055 | 285 s |
| EBD, before the continuation (`20261121-025819-ebd-deepseek-b06a5d-1c5b`) | all pass | 6 (3/3) | 30 | $0.102 | 532 s |
| baseline (`20261121-031335-baseline-deepseek-b06a5d-3aa5`) | required pass; 1 warning | 4 (4/0) | 20 | $0.072 | 163 s |
| EBD (`20261121-031336-ebd-deepseek-b06a5d-9912`) | all pass | 4 (4/0) | 20 | $0.101 | 401 s |

In each accepted run, one researcher needed the continuation. EBD's three structured calls were accepted on the first attempt. The baseline warning comes from the writer: it changed `environment-based_design` to `environment_based_design` in a designsociety.org URL.

Recorded for the capped setup, not fixed:
- Model behaviour: researchers make no page reads with the capped tool. Notes are long (23–44k characters, 9–16k output tokens). Most researchers cite one URL the tools never reported.
- The prompt and `BudgetView` state 12 tool calls while DeepSeek runs at most 5 searches. The model then attempts further searches, which are rejected; those rejections trigger the `tool_use` stops above.
**Deep search (2026-11-20, the profile's mode).** DeepSeek becomes a separate test target, analysed apart from Haiku and Luna. Its researchers use `deepseek_web_search` with no hard per-researcher cap. Run length is bounded by `maxRounds` in the experiment spec and by `researchersTotal`. `toolCallsPerResearcher` stays 12 as the soft budget the shared prompt states, and every result records that the cap is not enforced. The capped `web_search_20250305` setup above is the documented alternative.

- **Replies that only announce the research.** In the first deep-search runs, 5 of 11 researchers returned one sentence ("I'll start by searching ...") with no thinking and no tool call, and were recorded as `ok` with about 100 characters of notes. Sending the same request again rarely helped: on two replayed briefs, 2 of 18 tries searched, with thinking `enabled`, `adaptive` or omitted, an extra system line, or on the Responses endpoint. Effort `max` searched, but its thinking alone used the whole output limit. Adding a user turn, "Go ahead with your research now.", started the research in 3 of 6 tries on the harder brief. The adapter now sends that turn up to 8 times on the same conversation. A reply that neither used a tool nor wrote notes in the shared format never becomes notes; if the model never starts, the researcher fails as `empty`.
- **Error bodies with HTTP 200.** One probe got `{"type":"error","error":{"type":"api_error","message":"The model failed to generate a complete response. Please retry."}}` after 16 tool calls, with usage. The adapter retries it once and counts its tokens. Correction, 2026-11-21: the body has no `content`, so `ChatAnthropic` threw "Cannot read properties of undefined (reading 'length')" in `anthropicResponseToChatMessages` before the adapter saw it. That failed 6 of 57 researchers in the ResearchRubrics DeepSeek experiment, and their usage was lost. The adapter's fetch now adds an empty `content` to such a body. A test drives the real `ChatAnthropic` path with the recorded body.
- **`stop_reason: "tool_use"` after deep search.** A follow-up turn after deep search had about 100 input tokens, whether sent through LangChain, which drops `web_fetch_tool_result` blocks, or raw with every block. The model wrote notes from memory, with wrong facts and DOI-style URLs that no tool had returned. So after deep search the adapter only records such a stop and does not continue. No accepted run had one.
- **Page actions on the open page.** `open_page` or `find_in_page` with `url: ""` acts on the page already open. A result without an error now counts as a page read with no new source.

Live acceptance in deep-search mode (`check-strategy`, EBD question, 6 researchers):

| Run | Checks | Researchers (ok/failed) | Searches / page reads | Tool calls per researcher (min/median/max) | Cost | Time | Longest researcher |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline, before the follow-up turn (`20261121-034659-baseline-deepseek-b06a5d-e950`) | all pass | 6 (6/0, 3 of them announcements) | 16 / 37 | 0 / 8.5 / 19 | $0.061 | 300 s | 108 s |
| EBD, before the follow-up turn (`20261121-034659-ebd-deepseek-b06a5d-60da`) | required pass; 1 warning | 5 (5/0, 2 of them announcements) | 20 / 44 | 0 / 16 / 26 | $0.104 | 487 s | 118 s |
| baseline (`20261121-041042-baseline-deepseek-b06a5d-8b2e`) | all pass | 3 (3/0) | 16 / 62 | 20 / 25 / 33 | $0.069 | 178 s | 106 s |
| EBD (`20261121-041042-ebd-deepseek-b06a5d-9d27`) | required pass; 1 warning | 6 (6/0) | 40 / 98 | 17 / 23.5 / 28 | $0.183 | 795 s | 105 s |

In the accepted runs, 8 of 9 researchers first only announced the research. They started after 1, 2 and 4 follow-up turns (baseline) and 1, 1, 3, 1 and 3 (EBD); that run allowed at most 4 turns, raised to 8 afterwards. No `tool_use` stop, error body or counter mismatch occurred. Each warning is a writer URL error, e.g. `verification.asmedigitalcollection.asmedigitalcollection.asme.org`. The researcher timeout of `check-strategy` is 8 minutes; the longest researcher took 118 s.

Recorded, not fixed:
- Tool calls per researcher (17–33) exceed the soft budget of 12.
- Deep-search notes cite many links that no tool reported. They are mostly site roots (`https://dl.acm.org/`) or cut paths (`https://scholar.google.com.au/citations?user=`): 35 and 51 per accepted run, and 58 and 86 links marked "(unverified link)" in the writer's material. The capped setup had 6 and 1. The text carried no structured citations.
- EBD's strategy calls dominate the run time (8 calls, 107k output tokens in the accepted EBD run).
