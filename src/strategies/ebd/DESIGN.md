# EBD strategy design: building EBD research behaviour on the LangGraph platform

Behaviour design (Haoxi Li). **Draft for team review.** Built so far: the request
analysis (section 5) and a v0 strategy in which `init` runs it and the research stops
after one round. The loop (sections 6–12) is not built yet.

- 2026-10-07: first draft, written for the Python platform's planned `ebd@1` method.
- 2026-10-14: retargeted to the TypeScript platform on main (`d24a40d`, strategy
  contract v1).
  - The method sections (6, 10 and 11: priority, new goals, done and stopping) carry
    over with small edits.
  - The platform sections are new.
  - Every platform fact was read from the code on main or checked with offline
    probes on 2026-10-14 (section 2.3).
- 2026-10-19: D-A decided. Rev 2 has no `client` route and no `needs_clarification`
  status (sections 5.2 and 18).
- 2026-10-19: moved from `docs/research/ebd-method-design.md` to
  `src/strategies/ebd/DESIGN.md`, inside the EBD team's path.
- 2026-10-19: client directives are routed to their readers (sections 7 and 12):
  - source preferences go to every brief;
  - the report format goes to the writer;
  - scope limits and other directives go to both.

## 1. Summary

- EBD is a strategy plug-in, `src/strategies/ebd/`, implementing `init`, `observe` and
  `finalize` of contract v1 (`docs/strategy-modules.md`).
  - The platform runs the researchers, the writer, the budget and the records for both
    arms.
  - EBD decides what to research, when to stop and what the writer sees.
- What EBD does in each step:
  - `init` runs the request analysis: the Lab 2 contract, ported.
  - `observe` reads the round's notes, checks conflicts, judges every served goal
    against its `done_when` and grows new goals.
  - Code ranks the goals, packs them into researcher briefs and applies the stop rules.
- The model still makes only narrow, categorical judgments; code turns them into
  priorities and stop decisions. That rule from the first draft is unchanged.
- The rewrite removes most of the old design's platform work:
  - no Distiller and no source selection: the provider tools search and read inside
    each researcher;
  - no 32-call cap;
  - no Writer 5/Reviewer 4 projection.
- It adds three constraints:
  - all search goes through briefs;
  - the writer's material must be researcher notes lines;
  - structured outputs behave differently on the two providers (section 5.3).

## 2. What changed on main and what it means for EBD

### 2.1 The new system

On 2026-10-08/09 the platform restarted.
- **Language and framework:** TypeScript on Node.js 22, LangGraph.js and LangChain.js.
- **Search:** each model API's built-in web search and fetch.
- **Models:** `gpt-6-luna` and `claude-haiku-5-5`.
- **The old Python platform:** archived on branch `archive/concept-experiments`, tag
  `concept-experiments-final`.

A run is: `plan` → parallel researchers → `observe` → … → `finalize` → `write`
(`src/graph/skeleton.ts`).

| EBD can | EBD cannot |
|---|---|
| Call `ctx.model` as often as it needs, with structured output; strategy calls are not capped, only recorded as cost under the role `strategy` | Search, fetch, or create models |
| Choose every brief: `objective`, `keyQuestions`, `constraints`, `sourceHints`, `instructions` (the researcher prompt's only free slot), `priority`, `tag` | Change the researcher prompt outside `instructions`, or its tool cap (Haiku 8 searches + 4 fetches, Luna 12 tool calls) |
| Stop whenever its own rules say so | Change the writer, or rewrite the question for it |
| Order, select and excerpt whole notes lines under its own `#` headings | Add its own claims to the material: analysis goes to `outline` and `guidance` |
| Keep any JSON state; the platform records it after every step | Read files, environment variables or CLI arguments; prompts live in TypeScript |
| Take options from the experiment spec (ablations) | Import platform code other than `src/core/index.ts` |

The platform also guarantees four things:
- A failed researcher arrives as a result with `status: "failed"`.
- Invalid briefs are dropped and recorded.
- Briefs beyond the remaining budget are dropped lowest `priority` first.
- A step that throws is attempted up to 3 times. After 8 rounds the run stops
  (`maxRounds`).

### 2.2 Earlier team decisions this settles

| Decision | Status now |
|---|---|
| D1 reuse/fairness boundary | Settled by the platform: everything except `init`/`observe`/`finalize` is shared |
| D3 budgets and call caps | The budget is `researchersTotal` per run (experiment default 10, `check-strategy` 6), the same for both arms and a ceiling, not a target. No model-call cap; tokens and cost are recorded per role. |
| D4 who writes `methods/ebd` | The EBD team writes `src/strategies/ebd/` (AGENTS.md ownership table) |
| D2 tasks, D5 calendar | Still open (section 18) |

### 2.3 Platform behaviour checked on 2026-10-14

Offline probes (no network) in the git-ignored `local/explore/`:

| Check | Result | Design consequence |
|---|---|---|
| Structured output, Anthropic (LangChain jsonSchema → Anthropic SDK `transformJSONSchema`) | `enum`, `minLength`/`maxLength` and `maxItems` are moved into the description, not enforced. The reply is checked with zod on our side, and a violation throws "Failed to parse". | Re-validate and retry with feedback ourselves (section 5.3). |
| Structured output, OpenAI (Responses API) | Sent with `strict: true`, including `enum`, `minLength`/`maxLength`, `minItems`/`maxItems`. No client-side check: replies that broke an enum or a length limit came back as "parsed OK". A zod `.optional()` field is sent but not listed as required, which strict mode rejects. | Never use `.optional()`; always re-validate with zod. |
| `includeRaw: true` | On a parse failure it returns `parsed: null` plus the raw message. | A feedback retry can show the model its own reply. |
| Budget stop | Briefs returned with `stop: false` at zero budget give stop reason `budget-exhausted`, and the unmet demand is recorded as `dropped`, highest priority first. | EBD never says `stop: true` because of budget (H3, section 11). |
| Goal IDs in key questions | `[Q3] …` key questions came back as `## [Q3] …` section headings and parsed into `NotesSection.question`. Tested with a fake researcher; must be confirmed live (X2). | Results map back to goals by ID. |
| Regrouped material | Own `#` headings plus excerpted whole lines: 0 unmatched lines in `materialProvenance`. | EBD can group notes by goal. |
| Request analysis schema on Haiku, live (Lab 3, 2026-10-19) | Rejected with "The compiled grammar is too large", both as `jsonSchema` structured output and as a strict tool. | The analysis comes back through an unforced `submit_analysis` tool call and code validates it (section 5.3). Only small schemas can be strict. Test the conflict checker and round analyst schemas for the same limit (X3). |
| Forced tool use on Haiku, live (Lab 3) | `withStructuredOutput` with `functionCalling` forces `tool_choice`. The API accepts it with `effort` set, but Haiku does not think: about 1.7k output tokens per analysis, against about 5k unforced. | Use unforced tool calls, so Haiku keeps its adaptive thinking. |
| Tool list across turns on Haiku, live (Lab 3) | Thinking blocks are bound to the tool list. Changing any tool between turns (even `max_uses`) gives 400 "The tools list differs from the one this block was created with". | A multi-turn loop binds its tools once; a cap cannot shrink per turn. |

Provider documentation:
- Anthropic structured outputs support `enum`, `const`, `anyOf` and `$ref`/`$defs`.
  They do not support `minLength`/`maxLength` or `minItems` above 1.
- Anthropic limits a request to 24 optional parameters and 16 parameters with union
  types (nullable fields count). A larger schema can return "Schema is too complex for
  compilation".
- OpenAI strict mode lists `pattern`, `format`, number bounds and
  `minItems`/`maxItems`, but not `minLength`/`maxLength`.
- So the schemas sent to the APIs carry types, enums and required fields only, with
  few nullable fields. All lengths and counts are checked in code. Live check X1
  confirms this on both models.

## 3. The proposal's company on this platform

| Position (proposal) | Where it lives now |
|---|---|
| Front desk | The task text, passed verbatim |
| Analyst | The EBD strategy: request analysis in `init`; round analysis, goal ranking and stopping in `observe`; the report plan in `finalize` |
| Analyst's assistant | Not needed. There is no candidate pool, because researchers choose their pages inside their tool cap. H-4 (candidate value) no longer applies. |
| Searchers and Readers | Platform researchers: one model call per brief with the provider's search and fetch; notes with one section per key question |
| Finance | Platform budget (`researchersTotal`, priority drop), plus EBD code that allocates goals to briefs |
| Conflict checker | A `ctx.model` call in `observe` (option `conflicts`) |
| Writer | The shared writer; EBD supplies `material`, `outline` and `guidance` |
| Records | Run records (`events.jsonl` holds EBD's state after every step) and Langfuse traces |

## 4. The loop

```
init      request analysis ─▶ task model + goal table ─▶ rank ─▶ pack briefs
observe   map notes to goals ─▶ index evidence lines ─▶ conflict check ─▶ round analysis
          ─▶ update goals ─▶ stop rules ─▶ rank ─▶ pack briefs   (repeat per round)
finalize  material grouped by goal ─▶ outline from synthesis questions ─▶ guidance
```

1. **`init`**
   - One structured call analyses the request (section 5).
   - Code validates it, builds the task model (ROM, frame, assumptions) and the goal
     table, ranks the ready goals (section 6) and packs them into briefs (section 7).
   - The decision's `rationale` states the ROM's central objects, the assumptions to
     verify and why these goals go first.
2. **`observe`**, once per round:
   - Code maps each result's sections to goals and indexes every evidence line
     (section 8).
   - The conflict checker compares the new evidence with other evidence, the
     assumptions and the frame (section 9).
   - The round analyst judges each served goal and proposes new or moot goals
     (section 10).
   - Code accepts or rejects the proposals, updates statuses, applies the stop rules
     (section 11), and ranks and packs the next briefs.
   - The `rationale` says what settled, which conflicts appeared, which goals were
     added and what is served next and why.
3. **`finalize`**: code projects the task model into the writer's input (section 12).

Model calls per run: 1–2 for the request analysis, plus 2 per observed round. That is
about 7–10 strategy calls for 3–4 rounds, all recorded under the role `strategy`.

### 4.1 Worked example: the fixed question

`What is EBD (Environment Based Design)?` This is an illustration of the mechanism,
not expected output.

**Round 1.**
- The ROM has the question word as the product and one central environment object.
  "EBD" and "Environment Based Design" are one concept, because the request spells
  out the expansion.
- One goal defines the concept with G1 (its life cycle and environment). One
  verification goal checks the presupposition that a design method of that name
  exists and is abbreviated EBD.
- Both concern one object, so they share one brief. The constraints carry the
  question's own expansion, so the researcher does not drift to other expansions of
  the acronym (baseline test round 1 drifted to game art and climate design).

**Round 2.**
- Suppose the notes report that the method consists of several named activities and
  a modelling formalism.
- The round analyst proposes one define goal per part. Each cites the finding line
  that names the part, and each attaches to the EBD object at depth 1.
- The conflict checker marks findings about another "EBD" expansion as `off_target`.
  Those lines stay out of the material, and the guidance tells the writer to
  distinguish the terms only where needed.

**Round 3.** Relation goals become ready, for example how the activities connect, if
a synthesis question depends on them. Unanswered parts are re-served once.

**Stop.** The run stops when it is complete or saturated. The tree records which
branch came from which finding, which is the growth that H3 and H-9 measure.

## 5. Request analysis (round 0)

### 5.1 Starting point

`ebd.request_analyst` rev 1.3 (Lab 2) is the source.
- Instructions, four worked examples and the output schema were committed in
  `43dc249` under
  `src/deepresearch/agent_catalog/resources/ebd.request_analyst/1/`.
- That path belongs to the deleted Python platform. Recover it with
  `git show 43dc249:<path>`.
- The lab sources and test runs stay in the git-ignored `labs/lab2/`.
- `platform_check.py` and `build_bundle.py` import the deleted platform, and
  `run_tests.py` and `build_submission.py` import `platform_check`. Run them from a
  worktree at `88eb994` if they are needed again. `validate.py` has no platform
  imports and is the reference for the TypeScript checks.

Steps 1–7 carry over: gate, frame, ROM, assumptions, templates T1–T7, guidelines
G1–G7, routes, need, ordering rules and final check.

### 5.2 Changes for revision 2

| Change | Reason |
|---|---|
| Delete the inline JSON Schema and the bare-JSON output rules | The provider's structured output carries the schema |
| Remove the `client` route and the `needs_clarification` status (D-A) | Experiments have no client in the loop, and the baseline has no clarification step either. A missing purpose, time or place becomes a disclosed default. Two unrelated meanings become a level-1 disambiguation goal that runs first, with the readings listed in its constraints. Missing material becomes a disclosed limitation in the guidance; if nothing can be researched without it, the scope gate returns `out_of_scope`. Decided 2026-10-19. |
| Keep the scope gate | An `out_of_scope` request returns no briefs, so the writer states that nothing was researched. None of the four tasks triggers it. |
| Concept-level ROM objects (D-B) | Word-level objects crowd the 30-object limit and produce trivial questions (first draft, section 8.2). See section 5.5. |
| Add `source_hints` (at most 3 generic source kinds) to search questions | The baseline planner gives researchers source hints, so EBD briefs should carry them too. The rule against naming organisations not in the request stays. |
| "Searchers" become "researchers"; keep "Writer" | Matches the platform |
| API schema: types, enums and required fields only | Section 2.3. Lengths and counts move into the instructions and the code checks. Fewer than 16 nullable fields; prefer `[]` or `""` over `null` where the meaning allows. |

The four worked examples (E1 tariffs, E2 cold-winter EV, E3 missing message, E4 poem)
are converted to the new schema: no client questions, concept-level objects. They
keep their teaching roles.

### 5.3 One structured-call helper for all three roles

The helper in `llm.ts` works in five steps:
1. Call `ctx.model.withStructuredOutput(apiSchema, { method: "jsonSchema", includeRaw: true })`.
   - Revised 2026-10-19 for the request analysis (Lab 3, section 2.3): its schema is
     too large for Haiku's strict grammar.
   - The call instead binds one unforced `submit_analysis` tool, and step 2
     validates the tool's arguments.
   - This is implemented in `src/strategies/ebd/request/fixed.ts`, with an agent
     mode in `agent.ts`.
2. Parse the raw text and validate it with the strict zod schema (lengths, counts,
   enums).
3. Apply the role's rule checks (section 5.4).
4. On any error, retry once. The retry sends the previous reply and the numbered error
   list, as in Lab 2: correct exactly the listed errors and change nothing else.
5. If the retry also fails, apply the role's fallback:
   - request analysis: drop items with broken references, and continue if at least one
     search goal survives;
   - conflict checker: keep only valid conflicts;
   - round analyst: keep valid parts and treat unjudged goals as `partial`.

   Throw only when nothing usable remains; the skeleton then retries the whole step.

Problems are recorded in the state, so they appear in `events.jsonl`.

### 5.4 Code checks for the request analysis (port of `labs/lab2/validate.py`)

- IDs are unique and in order; every reference (objects, relations, assumptions,
  `depends_on`) exists.
- Every quote is a verbatim substring of the question.
- No search question lists a product object.
- `depends_on` points to earlier questions of an allowed route: search questions
  depend on search questions, and a necessary search question only on necessary ones.
- Every `needs_question` object is covered, and every assumption is verified by a
  search question.
- At least one search question and one synthesis question.
- Names not in the request are errors, with the narrowed exemptions of rev 1.3:
  calendar words, places, units, common abbreviations, forms of request words, and
  spelled-out acronyms.
- Length limits: question and `done_when` 400 characters; meaning, claim, quote and
  directive 300; at most 30 objects, 20 questions and 10 objects per question.
- New for rev 2: every never-drop span is covered (section 5.5).

### 5.5 Decomposition without spaCy

spaCy (the first draft's grammar pass) is Python and is no longer an option. Proposal
for v1:
- A concept-level prompt.
- A deterministic **never-drop check** in TypeScript using a small lexicon and
  patterns: negation; quantifiers and restrictors ("only", "all", "most", "at
  least"); comparatives and superlatives; modality; numbers, dates, times; capitalised
  names; and acronym–expansion pairs `X (Y)`.
- Every such span must be covered by some object or relation. A miss goes back to the
  model in the feedback retry.
- No dependency is added.
- A JS parser (`compromise` or `wink-nlp`, for noun chunks) needs the platform owner
  to add a package. Ask for it only if the A/B test below shows unstable concept sets.

A/B test, as in the first draft:
- A: concept-level prompt only;
- B: concept-level prompt plus the never-drop check.
- Optionally C: rev 1.3 word level, run with the `rom` option.

Run it on the four tasks and the Lab 2 cases, three repetitions on both models.
Compare:
- first-attempt pass rate;
- never-drop coverage;
- object and question counts;
- concept-set stability across repetitions (Jaccard);
- output tokens.

## 6. Goals and priority

The goal table holds one row per search goal:
- Request-derived goals keep the analysis question ID (`Q1`, …). New goals take the
  next free `Q` number; `G1`–`G7` already name guidelines.
- **Fields:** text, `object_ids`, template, guideline, need, `depends_on`, `verifies`,
  `done_when`, `source_hints`.
- **Origin:** `request`, or the finding, gap or conflict that prompted the goal.
- **Tracking:** depth, status, attempts, created round, last served round, missing
  parts, and the supporting evidence line IDs.

Synthesis questions are kept separately; they become the outline (section 12).

### 6.1 What EBD provides

The papers give ordering rules, not a formula. Wang & Zeng (2009, p. 297): "A more
robust algorithm for determining the sequence of asking questions is under
development." No paper gives weights, an information-value measure or a numeric
threshold. The order below is built from the rules the papers state; everything
numeric is this project's addition.

### 6.2 Ready

A goal can be served only when the goals it depends on are settled: answered,
exhausted, disputed or moot.
- "Before an object can be further defined, the objects constraining them should be
  refined" (Wang & Zeng 2009, Table 2).
- Central objects "will be questioned last" (Zeng 2020, p. 56).
- Questions that ask for the answer itself are not searched; they go to the writer as
  synthesis questions ("skip the question and leave for solution generation", Zeng
  2020, Table 10).

### 6.3 Order

Code derives a kind from the template and origin:
- **verify:** T7, or `verifies` is not empty;
- **settle:** created for a conflict;
- **define:** T1, T2, T3, T6;
- **relate:** T4, T5.

| Level | Goals | Basis |
|---|---|---|
| 1 | Necessary goals that verify a client assumption or settle a conflict | EBD runs "until no more undesired conflicts exist" (Zeng 2015, p. 8). A refuted premise can make other goals moot, so checking it early saves budget (value of information, Howard 1966). |
| 2 | Necessary goals that define an object: what it is, its parts, its life cycle | The environment is "the first thing to be looked at" (Zeng 2020, p. 45); the question rules are width-first (Zeng 2020, §4.2). |
| 3 | Necessary goals about relations: when, where, why, how | Their participants are defined first; central objects come last (Zeng 2020, p. 56). |
| 4 | Completing goals, in the same internal order | Collect what is "necessary", then what is "definable at a given design stage" (Zeng 2020, p. 51). |

Ties within a level, in order:
1. **Reach:** the goal that more unsettled necessary goals and synthesis questions
   depend on, directly or through other goals. This follows the eLCD idea that
   dependency paths mark the major concerns (Yang et al. 2020, p. 18).
2. **Most undefined constraints** on its objects: "An object with the most undefined
   constraints should be considered first" (Wang & Zeng 2009, Table 2).
3. **Fewer derivation steps** from the request (drift control).
4. **Fewer attempts, then older.**

One slot per round goes to the necessary goal that has waited longest, if it is not
already selected. This stops early findings from starving a branch (the exploration
reserve of tree-search agents such as LATS).

Not adopted in v1: Wang & Zeng's requirement pyramid (Table 4). It is a candidate
tie-breaker for a later revision.

### 6.4 Why code computes the priority

- Model-assigned scores cluster on one value and are overconfident (G-Eval; Xiong et
  al. 2024).
- Yes/no and categorical judgments agree better across models (CheckEval).
- Smaller judges rank more reliably than they score (Thakur et al. 2024).
- Luna and Haiku are the small, cheap tiers of their families.
- A computed order is reproducible, and the decision `rationale` can show why each
  goal ranked where it did.

## 7. From goals to researcher briefs

Each brief costs one researcher out of `researchersTotal`. Ranking works on goals;
packing turns the top goals into briefs.

- **Packing (D-C).** Walk the ranked ready goals in order and group them by their
  primary object, at most `questionsPerBrief` goals per brief (default 3) and at most
  `maxPerRound` briefs per round (default 4, the platform's concurrency). With 12
  tool calls per researcher, three goals get about four calls each.
- **`objective`:** the goal's text for a one-goal brief. Otherwise "Answer the key
  questions below about <object>".
- **`keyQuestions`:** `[Q7] <goal text>`. A re-served partial goal appends "Still
  missing: <parts>". The ID maps the notes section back to its goal (section 8).
- **`constraints`:**
  - the frame's time frame and place, with basis;
  - the reading the question fixes, for example the spelled-out expansion of an
    acronym;
  - disclosed defaults;
  - the client's source preferences, scope limits and other directives, each with
    the client's own words. Report-format directives go to the writer instead
    (section 12).
- **`sourceHints`:** the goal's `source_hints`. Verification and settle goals add
  "primary records; at least two independent publishers".
- **`instructions`**, the only slot EBD controls in the researcher prompt:
  - for each goal: "For [Q7], a sufficient answer contains: <done_when>";
  - for verification goals (G7): "State whether the evidence supports, contradicts or
    does not settle the claim '<claim>'. Look specifically for evidence that
    contradicts it. Give each source's finding with its date and scope; report
    disagreements, do not resolve them";
  - for settle goals: the two sides with their sources, and what would settle the
    disagreement;
  - from round 2: at most 3 verbatim takeaways from earlier notes on the same object,
    marked as orientation only ("re-find and cite sources yourself").
- **`priority`:** `100 − 10 × level − position`, so that the platform's drop order
  matches EBD's order if a decision ever exceeds the budget.
- **`tag`:** the goal IDs, for example `Q7,Q8`.

## 8. Reading results

- **Mapping:**
  - parse each `ok` result with `parseNotes`;
  - match a section to its goal by the `[Qn]` prefix;
  - otherwise by key-question order;
  - otherwise attach it to all goals of the brief.
- **Evidence lines:** every Cited Findings bullet and every Gaps bullet gets an ID
  from the platform's brief ID: `r2-b1-f3` (finding) and `r2-b1-g1` (gap). The checker
  and the round analyst cite these IDs, never paraphrases, and code resolves them to
  the exact lines. This replaces the old Distiller's claim IDs and avoids
  quote-mismatch errors.
- **Independence:** two findings are independent when their cited URLs have
  different hosts. Strategy code may import only `src/core/index.ts`, which does not
  export `extractUrls`/`pageKey` (request P1). Until that is added, a local Markdown
  link extractor is used.
- **Failures:** a failed researcher counts as an attempt for each of its goals. The
  goal is re-queued, or exhausted after `maxAttempts`; it is not marked "not found",
  because nothing was searched.

## 9. Conflicts

The conflict checker runs before the round analyst (D-D), as the proposal's Analyst
inputs list conflicts.

It sees:
- the question, the frame and the open assumptions;
- this round's indexed findings;
- earlier findings on the same objects;
- the open conflicts.

It outputs conflict records:

| Type | Side A | Side B | Example |
|---|---|---|---|
| `source_vs_source` | finding | finding | Two sources give different dates for one event |
| `evidence_vs_assumption` | finding | assumption | The question presupposes a ban the sources do not report |
| `evidence_vs_frame` | finding | frame field (time, place, scope) | Evidence older than the time frame presented as current |
| `off_target` | finding | object | The finding is about a different referent with the same name |
| `time_dependent` | finding | finding | Both values hold at different times |

Each record also carries `about` (a goal or object), a one-sentence statement and
`settle_by` (what evidence would settle it). This follows EBD's definition of a
conflict as "two competing objects and one resource object" (Zeng 2015, p. 13).

The code rule decided in design v0.1 stays: a conflict without valid evidence on both
sides is not recorded.

Effects:
- **`source_vs_source` and `evidence_vs_assumption`:** create one level-1 settle goal
  with `settle_by` in its instructions. If that fails, the conflict becomes
  `disputed`.
- **`off_target`:** the finding lines are excluded from the material and named in
  the guidance.
- **`time_dependent`:** settled at once with the condition ("as of …").

With `conflicts: false`, the round analyst still sees the evidence, but no conflict
records or settle goals are made. This is the H1 ablation.

## 10. Round analysis: done, new goals, moot

### 10.1 When a goal is done

- The round analyst splits the goal's `done_when` into parts and marks each part yes
  or no, citing evidence line IDs.
- Code checks the IDs and applies an evidence floor: verification goals, numbers and
  dates need findings from at least `evidenceFloor` independent hosts (default 2).
- An answer that fails the floor is `partial`.

| Outcome | Next step |
|---|---|
| answered | settled |
| partial | re-queued with the missing parts; attempts + 1 |
| not found | one retry with a new angle; then exhausted (settled) |
| conflicting | conflict record; one settle goal; if that fails, disputed (settled) |
| moot | its premise was refuted (settled) |

Sufficiency judged per question against the retrieved text works (Joren et al. 2025:
93% accuracy for a strong model). The citation check and the evidence floor guard
against weaker models.

### 10.2 New goals

Wang & Zeng (2009, Step 4) analyse each answer "as new ROM diagrams" merged into the
original, and ask questions about it in turn. Answers "do not need to be given for all
the questions in one iteration" (Yang et al. 2020, p. 10).

| What the evidence shows | New goal | Level |
|---|---|---|
| A term a necessary goal needs (e.g. which GPUs are the current flagships) | Define it; dependent goals are restated with the names | 2 |
| A part or life-cycle event of an object | Define it | 2 or 4, by need |
| A relation left unverified or contested | Verify it | 1, or 4 if completing |
| A conflict | One goal to settle it, with a condition such as "as of 2026" | 1 |
| A partial answer | The same goal re-queued with the missing part | unchanged |

Code accepts a proposal only if all of these hold:
- it cites the finding, gap or conflict that prompted it;
- it attaches to an existing object, and leads to a necessary goal or a synthesis
  question;
- it does not duplicate an open or settled goal (same objects and template, or
  near-identical text);
- it is at most `maxDepth` derivation steps from the request (default 2);
- the quota allows it: `maxNewGoalsPerRound` (4) and `maxOpenGoals` (20).

New objects enter the ROM only with a verbatim quote from a finding line.

Updates also remove work, as EBD's recomposition does (Zeng 2015, p. 14): when an
assumption is contradicted, the goals that rely on it become moot. Restating changes
goals only; the question itself stays verbatim (AGENTS.md).

STORM (Shao et al. 2024) found that questions drawn from retrieved answers reach far
more distinct sources than questions written up front.

## 11. Stopping

Code checks after every round; the first rule that applies ends the research.

| Stop | Condition | Decision returned | Platform `stopReason` |
|---|---|---|---|
| Complete | Every necessary goal is settled; every assumption has a verdict (supported, contradicted or unsettled, with sources); no conflict on a necessary goal is open | `stop: true` | `strategy-stop` |
| Saturated | The round settled or advanced no necessary goal, and produced no new conflict or necessary goal | `stop: true` | `strategy-stop` |
| Budget | `researchersRemaining` is 0 | The briefs EBD still wants, with `stop: false` | `budget-exhausted`, with the unmet demand recorded as `dropped` |
| Safety cap | 8 rounds | – | `max-rounds` |

- After **complete**, at most one more round serves completing goals, if
  `extraRound` is on and a researcher is left.
- The stop kind is also kept in the state (`stop.kind`, `stop.round`).

Basis:
- **Complete** is EBD's own end. It runs "until no more undesired conflicts exist"
  (Zeng 2015, p. 8) and "until no more generic questions can be asked" (Wang & Zeng
  2009, p. 288). Every object is "either questioned or self-evident" (Zeng 2020,
  Table 7).
- **Saturated** is a project addition, because the EBD papers are silent on
  diminishing returns. It follows the marginal value theorem (Charnov 1976) and
  saturation stopping in qualitative research (Francis et al. 2010; Guest, Namey &
  Chen 2020).
- The model is never asked whether the research is sufficient overall:
  - prompted stopping performs about like a fixed iteration cap (Stop-RAG, Park et
    al. 2025);
  - Anthropic reports that its research agents kept searching after they already had
    enough (Hadfield et al. 2025).

## 12. Writer input (`finalize`)

**`material`:**
- One item per goal, ordered by the synthesis question it feeds, then by goal order.
  A goal that feeds several synthesis questions appears once.
- Each item has `label` = the goal text, and `notes` = an own heading plus the whole
  lines of the goal's sections (Takeaway, Cited Findings, Inferences, Gaps).
- `off_target` lines are removed.
- Unmapped sections and results go last under "Further findings", so no on-topic
  evidence is dropped. The writer prompt says to use all notes.

**`outline`:** the synthesis questions in order, plus "Where the sources disagree"
when a conflict is disputed. At most 5 items, matching the writer's 3–5 sections.

**`guidance`:** plain sentences, with no claims of its own beyond the analysis.
- **Client directives.** The report format, scope limits and other directives, each
  with the client's own words. Source preferences have already reached the
  researchers (section 7).
- **Assumption verdicts.** A contradicted premise: "The question presupposes that
  <claim>. The evidence contradicts this; say so plainly early in the report." An
  unsettled one is stated as not established. This is the H1 lever.
- **Conflicts.** For a settled conflict, which side holds and why. For a disputed one,
  both sides with their sources.
- **Off-target referents.** Exclude them, or distinguish the terms only where needed.
- **Defaults and evidence status.** The frame defaults, only where they change the
  answer, as the baseline does with its interpretation. Exhausted necessary goals, as
  evidence status: "no reliable source states …".
- **No meta text.** Never open the report with the guidance, and never mention the
  research process.

## 13. Options and ablations

Strict zod options, all with defaults, chosen per experiment spec:

| Option | Default | Use |
|---|---|---|
| `maxPerRound` | 4 | Briefs per round |
| `questionsPerBrief` | 3 | Goals packed into one brief |
| `conflicts` | true | Conflict checker on or off (H1 ablation) |
| `newGoals` | true | Grow goals from evidence; off = static EBD plan (tree-growth ablation) |
| `maxNewGoalsPerRound` / `maxOpenGoals` / `maxDepth` | 4 / 20 / 2 | New-goal limits |
| `maxAttempts` | 2 | Attempts before a goal is exhausted |
| `evidenceFloor` | 2 | Independent hosts for verification goals, numbers and dates |
| `extraRound` | true | One round of completing goals after "complete" |
| `rom` | `"concept"` | `"word"` re-enables the rev 1.3 word-level ROM, if the A/B test needs it |

Example spec entry:

```json
{ "name": "ebd", "label": "ebd-no-conflicts", "options": { "conflicts": false } }
```

## 14. Records and metrics

Every decision in `events.jsonl` carries EBD's state:
- ROM, goal table, conflicts and assumption verdicts;
- the round each item was created and settled;
- the stop kind.

This makes the hypotheses measurable from the records.

| Hypothesis or item | Measured from |
|---|---|
| H1 contradictions and false assumptions | Conflicts recorded, settled and disputed; assumptions contradicted; whether the report states them (judged) |
| H2 coverage and citation accuracy | Blind judging; the platform's citation diagnostics |
| H3 own stopping condition | `state.stop.kind` and `stopReason` (but see request P2); searches per cited source |
| H4 larger gain on the smaller model | Same metrics per model profile. The proposal's local model now depends on the local-Qwen work on `codex/langfuse-baseline`. |
| H-9 tree metrics | Goals created per round, depth, origin type, outcomes |

Fairness:
- Both arms get the same `researchersTotal`, and it is a ceiling. The baseline usually
  uses about 3 researchers, and EBD will usually use more.
- `docs/design.md` §8 already says to compare quality together with the researchers
  and searches used.
- A matched-usage comparison (EBD at the baseline's mean usage) would separate the
  strategy's choices from sheer search volume.

## 15. Module layout and tests

```
src/strategies/ebd/
  index.ts            StrategyModule default export; EbdStrategy (orchestration only)
  options.ts          OptionsSchema (strict zod)
  state.ts            EbdState and its parts (types, not interfaces: JsonValue)
  llm.ts              structured-call helper with validation and one feedback retry
  request/            prompt (instructions + examples as TS constants), schema, checks
  rounds/             evidence mapping and indexing, conflict checker, round analyst
  goals.ts            readiness, levels, tie-breaks, reserve slot, acceptance, stop rules
  briefs.ts           packing goals into briefs
  synthesis.ts        material, outline, guidance
  *.test.ts           unit tests (vitest picks them up from src/)
  DESIGN.md           this document
```

- **Pure code is unit-tested:** goal ranking, packing, stop rules, evidence mapping,
  projection and the request checks.
- **Skeleton test without network:** the full strategy runs through the real skeleton
  with a fake researcher, as `tests/template.test.ts` does, and a fake `ctx.model`
  whose `withStructuredOutput().invoke()` returns recorded replies.
- **Contract checks:** `npm run check-strategy -- --strategy ebd` on both models before
  any experiment.

## 16. Build plan

| Phase | Work | Needs API keys | Done when |
|---|---|---|---|
| 0 | Merge main into `behaviour-design`; offline probes (section 2.3) | no | Done 2026-10-14: typecheck and 29 tests pass |
| 1 | Scaffold from `_template`; options, state, goals, briefs, stop rules, synthesis; fake-model skeleton test | no | `npm test` passes; the module loads; the skeleton test passes the provenance check |
| 2 | Request analysis rev 2: prompt, schema, checks, helper, converted examples; offline tests on recorded replies | X1 | Both models produce valid analyses for the 4 tasks and the Lab 2 cases; A/B test (section 5.5) |
| 3 | `observe`: mapping and indexing, conflict checker, round analyst, update rules | X2, X3 | Researchers keep `[Qn]` headings (X2); both calls work on replayed notes (X3) |
| 4 | `check-strategy` on both models; test rounds as in `docs/plan.md` P7 (classify each problem; fix non-model ones; rerun all 4 tasks) | yes | Two rounds without new non-model problems |
| 5 | Experiments: baseline vs EBD vs ablations, both models, repeats, planted-conflict tasks as explicit questions in the spec | yes | Records ready for blind judging |

The live explorations:
- **X1:** the request schema through `withStructuredOutput` on both models: Luna
  strict-mode acceptance, Haiku enum adherence, Anthropic schema complexity.
- **X2:** heading fidelity of researchers given `[Qn]` key questions.
- **X3:** the conflict checker and round analyst on recorded baseline notes, like
  main's E7 replay.

No `.env` exists on this machine yet. Copy `.env.example` to `.env` and fill
`OPENAI_API_KEY` and `ANTHROPIC_API_KEY` before phase 2.

## 17. Requests to the platform owner

- **P1.** Export `extractUrls` and `pageKey` from `src/core/index.ts` (an addition
  within v1). EBD needs host independence and URL matching. The platform's extractor
  already handles URLs with parentheses, a round-1 bug.
- **P2.** An optional `Decision.stopKind`, copied into the decision record and the run
  summary.
  - Today the baseline's fixed two-round cap and its "no critical gaps" judgment are
    both recorded as `strategy-stop`.
  - So H3 would count a fixed cap as the baseline's "own condition".
  - Suggested values: `complete`, `saturated`, `judged-sufficient`, `round-cap`.
- **P3 (optional).** `ctx.maxRounds` in `StrategyContext`, so a strategy can plan
  within the safety cap.
- **P4.** `codex/langfuse-baseline` (not on main) changes shared parts:
  - the baseline gets an identity-first round for definition questions;
  - researchers get an `inheritedSources` registry;
  - the writer gets a numeric publication gate.
  
  If it lands, EBD's later rounds benefit from inherited sources, and the baseline
  becomes stronger on the EBD question. Agree on the version before the test rounds.

## 18. Open decisions

| ID | Decision | Recommendation |
|---|---|---|
| D-A | Client route and `needs_clarification` in rev 2 | **Decided 2026-10-19: removed** (section 5.2) |
| D-B | Concept-level or word-level ROM | Concept-level plus the never-drop check; word level as an ablation only if needed |
| D-C | Goals per brief | Up to 3, grouped by object |
| D-D | Conflict checker as its own call before the round analyst, or merged | Its own call, so H1 is attributable and ablatable |
| D-E | Thresholds | Defaults in section 13, tuned on development tasks only |
| D-F | Init mode: one call with a code retry (`fixed`), or the analyst as a tool-using agent (`agent`) | Lab 3 evidence (Haiku, 81 runs, 2026-10-19): equal final acceptance and case checks; agent costs 1.7–2× the input tokens. Default `fixed`; keep `agent` as an option (both are in `src/strategies/ebd/request/`) |
| D2 (team) | The fixed EBD question has no planted conflicts, so H1 needs the planted-conflict tasks | Keep the four tasks for development; add the nine proposal tasks as explicit questions in experiment specs |
| D5 (team) | Calendar | If W1 is the week of 2026-09-21, scope freezes the week of 2026-10-26 |

## References

EBD papers (`docs/background/ebd-papers/`):

- Wang, M., & Zeng, Y. (2009). Asking the right questions to elicit product
  requirements. *International Journal of Computer Integrated Manufacturing*, 22(4),
  283–298.
- Yang et al. (2020). Environment-based life cycle decomposition (eLCD).
- Zeng, Y. (2015). Environment-Based Design (EBD): A methodology for
  transdisciplinary design+. *Journal of Integrated Design and Process Science*,
  19(1), 5–24.
- Zeng, Y. (2020). Environment: The first thing to look at in conceptual design.

Research loops and stopping:

- Charnov, E. L. (1976). Optimal foraging, the marginal value theorem. *Theoretical
  Population Biology*, 9, 129–136.
- Francis, J. J., et al. (2010). What is an adequate sample size? *Psychology &
  Health*, 25, 1229–1245.
- Guest, G., Namey, E., & Chen, M. (2020). A simple method to assess and report
  thematic saturation. *PLOS ONE*, 15, e0232076.
- Hadfield, J., et al. (2025). How we built our multi-agent research system.
  Anthropic Engineering.
- Howard, R. A. (1966). Information value theory. *IEEE Transactions on Systems
  Science and Cybernetics*, 2(1), 22–26.
- Joren, H., et al. (2025). Sufficient context: A new lens on retrieval augmented
  generation systems. ICLR. arXiv:2411.06037.
- Park et al. (2025). Stop-RAG: Value-based retrieval control for iterative RAG.
  arXiv:2510.14337.
- Shao, Y., et al. (2024). Assisting in writing Wikipedia-like articles from scratch
  with large language models (STORM). NAACL. arXiv:2402.14207.
- Zhou, A., et al. (2024). Language agent tree search (LATS). ICML.

Model judgments:

- Lee et al. (2025). CheckEval. EMNLP.
- Liu, Y., et al. (2023). G-Eval. EMNLP.
- Thakur et al. (2024). Judging the judges. arXiv:2406.12624.
- Xiong, M., et al. (2024). Can LLMs express their uncertainty? ICLR.

Provider documentation (structured outputs, read 2026-10-14):

- Anthropic. Structured outputs: JSON Schema limitations and schema complexity limits.
  https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- OpenAI. Structured Outputs guide. https://developers.openai.com/api/docs/guides/structured-outputs
