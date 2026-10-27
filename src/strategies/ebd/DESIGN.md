# EBD strategy design: building EBD research behaviour on the LangGraph platform

Behaviour design (Haoxi Li). **Draft for team review.** Built: the request analysis
(section 5) and the loop (sections 6–12), tested offline with a fake model through the
real skeleton and live on Haiku (section 16.1). The defaults of the open decisions in
section 18 are built in as options, pending the team's confirmation. A run viewer for
checking runs step by step is in `viewer/`.

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
- 2026-10-20: the loop is built (phases 1 and 3, section 16). Changes found while
  building and in the first live runs are marked "2026-10-20" in sections 5.4 and
  9–13.
- 2026-10-20: review of the flight runs (section 5.6). An environment object is
  defined through the steps of its lifecycle and what each step involves, a
  verification question no longer replaces a defining question, and the round analyst
  asks about steps the evidence reveals (section 10.2).
- 2026-10-21: review of the GPU rerun (section 16.1). Necessary request goals keep a
  first-try reserve of researchers (section 7); the writer gets a length rule and the
  planned contents of each section (section 12); questions cover the main cases of
  what the client did not state (sections 5.6 and 10.2); a settle goal checks a claim
  only when the disagreement decides it (section 9).
- 2026-10-26: review of the Lab 4 runs (section 16.1).
  - The round analyst gives a verdict on each claim a goal checks (section 10.1).
  - An `evidence_vs_assumption` conflict gets no settle goal when a goal served in the
    same round already checks its claim on the same findings (section 9).
  - A settle goal is completing unless it decides a claim or a goal waits for it
    (sections 9 and 11).
  - The writer gets a short note when the request is out of scope (section 12).
- 2026-10-26, evening: code fixes from the review of the reruns. None changes a prompt.
  - Moot rule (section 10.2): when the goal that checked a contradicted claim also
    confirmed another claim, only the dependents about a refuted object are moot. In
    the telescope run the goal on NASA's purposes was dropped although only the year
    was wrong, so the report never said why NASA launched the telescope.
  - A time frame taken only from a refuted date is left out of later briefs (section 7).
  - A bold line inside a findings list is a sub-heading, not a finding or part of one
    (section 8).
  - New goals (section 10.2): a goal on the question word (a product object) is
    rejected; same template and objects is a duplicate only when the texts also
    overlap; a goal that asks for a part a retried goal still misses is rejected; a
    new object enters the ROM only with an accepted goal.
  - A single value sent where a list is expected is made a list instead of costing a
    retry (section 5.3).
  - A multi-goal brief names an object found in the notes by its text (section 7).

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
- 2026-10-20, from Lab 3: every question stands alone. A search question's text and
  `done_when`, and a synthesis question's text, may not point to another question ("Q1",
  "the previous question", "the ones identified"). In the Lab 3 batch, 24 questions in
  15 of 81 analyses did. The places list also gained the countries Lab 3 flagged
  falsely (Philippines, Russia), and possessive acronym expansions ("the European
  Union's") count as known.
- 2026-10-20, from the review of the flight runs (section 5.6): an environment object
  that a verification question (T7) covers also needs a search question with a
  template from T1 to T6 (`object_only_verified`). That question may verify the claim
  as well.

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

### 5.6 Question templates and guidelines

Each question uses one template, which names the part of the request's object model it
asks about, and one guideline, which says what a sufficient answer contains (its
`done_when`). The full text is in `request/prompt.ts`, Step 5.

| Template | Used for | Question form | Guideline | Goal kind (section 6.3) |
|---|---|---|---|---|
| T1 | A noun with no modifier | What/Who is N? | G1 | define |
| T2 | A noun with an adjective | What is A N? | G1 | define |
| T3 | A noun that narrows another noun | What is A? What is A N? | G1 | define |
| T4 | A verb with its subject and object | What do you mean by V? How/Why/When/Where does N1 V N2? | G6, G5, G3, G4 | relate |
| T5 | A verb with an adverb | What do you mean by V A? Why/When/Where does N1 V A N2? | G6, G5, G3, G4 | relate |
| T6 | A verb missing its subject or object | What/Who V N? N1 V what? | G2 | define |
| T7 | A claim the request makes or presupposes | Is it true that N1 V N2? | G7 | verify |

Any question that verifies an assumption becomes a verify goal, whatever its template.

| Guideline | A sufficient answer contains |
|---|---|
| G1 What/Who is N | For the product, its purpose and coverage. For an environment object, the lifecycle events that matter for the client's purpose and, for each, the environment it involves: natural, built (physical and digital: documents, data, laws, software), economic (costs, prices, time), social (people, organisations). Otherwise, components and attributes. |
| G2 What/Who V N | The components and attributes of the missing participant |
| G3 When | A time or a triggering event |
| G4 Where | A place or a situation |
| G5 Why | The purpose or the cause |
| G6 What do you mean by V / How | The activities included in V-ing (the mechanism); for an activity someone carries out, its steps from start to finish, each with its environment as in G1. If a participant is the product, the question goes to synthesis. |
| G7 Verification | Whether the evidence supports, contradicts or does not settle the claim, each source's finding with its date and scope, and the disagreements |

Changed 2026-10-20, after a review of the four live flight runs ("How do I flight from
GuangZhou to Montreal?", section 16.1):
- Only run 1 asked what the connections and the arrival in Canada require; its report
  has a visa and transit section. The other three stopped at routes, airlines, times
  and booking, and their reports say nothing or almost nothing about entry rules.
- The loop could not add the topic later. A new goal must start from a line in the
  notes and serve a goal or a synthesis question of the plan (section 10.2). In run 2
  the notes mentioned clearing immigration on a self-transfer, but no goal or
  synthesis question needed it. In run 3 the synthesis question did, but no note
  mentioned it. Run 4 had neither.
- G1 (b) read "the events and dates in its existence", which suits an entity's history
  but not an activity. It now names the steps of an activity and ties the events to
  the client's purpose; G6 (a) gets the same for a verb.
- In run 4 the only search question about "flight" was the check that a flight exists
  (T7), which asks for no lifecycle at all. Step 5 now says that a verification
  question does not define its objects, and code enforces it (section 5.4).
- Worked example E2 defines the electric car through the steps of owning one (buying,
  charging, driving), because the examples' defining questions were attribute lists
  and the flight analyses wrote the same shape.
- The examples in the prompts avoid travel, so the prompts do not carry the answer to
  a test task.

Changed 2026-10-21: Step 5 adds that when the answer to a search question depends on
something the client did not state (who the client is, their budget, their dates), the
question and its `done_when` cover the main cases and name them, as Step 1's neutral
default requires. In the flight rerun the analysis disclosed the unstated nationality
only in its synthesis question, and the research then followed one nationality.

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
- **First-try reserve (`reserveFirstTries`, D-E; built 2026-10-21).** A necessary
  request goal that has never been served keeps a claim on the budget. The strategy
  holds one researcher for each brief such goals will need (goals about the same object
  share a brief), including goals still waiting for their dependencies. A brief made
  only of goals added during the run (settle goals, and goals grown from findings or
  gaps) is served only from researchers beyond that reserve; otherwise it waits, and
  its slot goes to the next ranked goals. Two kinds of brief are never held back: one
  that contains a request goal (first try or retry), and one that contains a settle
  goal a request goal is waiting for. Without that exception, the goals that depend on
  them could never become ready. A held-back goal packed into a brief that goes anyway
  still goes, since it costs nothing extra. If holding back would leave no brief at
  all, the reserve is released for that round rather than ending the run with
  researchers left. The rationale names what was held back ("Held back for first
  tries: Q8 (2 researcher(s) kept for Q3, Q4)"). In the GPU rerun of 2026-10-21 (section
  16.1), settle goals took the slots before the "use" and "cost" goals had a first try.
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
  - match a section to its goal by the `[Qn]` prefix, or by a bare `Qn` that opens the
    heading (live check X2, section 16.1: Haiku often writes `Q4: …` or drops the ID);
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
- **`source_vs_source` and `evidence_vs_assumption`:** create one settle goal with
  `settle_by` in its instructions, at level 1 while it is necessary (2026-10-26, below).
  If that fails, the conflict becomes `disputed`.
- **`off_target`:** the finding lines are excluded from the material and named in
  the guidance.
- **`time_dependent`:** settled at once with the condition ("as of …").

With `conflicts: false`, the round analyst still sees the evidence, but no conflict
records or settle goals are made. This is the H1 ablation.

Built 2026-10-20 (`rounds/conflicts.ts`):
- A settle goal checks a claim only when the conflict checker says the disagreement
  decides it (field `claim`; for `evidence_vs_assumption`, the assumption in side_b); a
  disagreement about a detail leaves the claim's verdict to the goals that check it.
  When a settle goal ends, it changes the verdict of the goal waiting for it only if it
  judged the claim itself. Changed 2026-10-21: settle goals had taken over the claim of
  the goal they settle, so in the first flight run settle goals about flight times
  carried verdicts on "a flight connects GuangZhou and Montreal".
- A conflict is about a fact (a value, a date, an event, whether something exists).
  Differing opinions of reviewers, small numeric differences and listings of different
  options are not conflicts (test round 2, section 16.1).
- A `source_vs_source` conflict whose two sides rest on the same host is rejected by
  code: two parts of one page are not two sources (test round 1).
- Settle goals obey the limits of new goals (section 10.2): `maxDepth`,
  `maxNewGoalsPerRound` (shared with proposals) and `maxOpenGoals`. Only an open or
  answered necessary goal gets one, a goal has at most one open settle goal, and a
  settle goal gets none of its own. Any other `source_vs_source` or
  `evidence_vs_assumption` conflict is recorded as disputed at once, and the writer
  presents both sides. Without these limits, test round 1 grew 15 settle goals from the
  evidence of earlier settle goals until the budget ran out.
- A goal judged "conflicting" whose conflict is disputed (it could get no settle goal)
  becomes disputed itself (test round 3).
- A finding that a goal asks for is not off_target. The first live run (the EBD
  question) marked as off_target the lines that listed other expansions of "EBD",
  which the goal had asked for. The prompt now says so, and section 12 keeps any
  off_target line that a goal cites as its own evidence.

Built 2026-10-26, after the Lab 4 runs (section 16.1):
- **No settle goal for a claim already being checked.** An `evidence_vs_assumption`
  conflict gets no settle goal when a goal served in the same round verifies its claim
  and the contradicting findings are that goal's own (`checkedThisRound`).
  - The round analyst judges that goal next, on those findings, so a settle goal would
    only repeat the check.
  - The conflict is settled, with that goal as its `settleGoal`, and the guidance points
    the writer to that goal's notes.
  - In the false-premise test (JWST "launched in 2018"), such a settle goal took 2 of 5
    researchers and a third round to re-prove a launch year that the verification goal
    had already contradicted.
  - A disagreement between sources keeps its settle goal, which gives the researcher
    both sides and what would settle them.
- **Settle goals are necessary only when they matter (`settlePriority`).** A settle goal
  is necessary while its disagreement decides a claim, or while a goal waits for it
  because the round analyst judged that goal "conflicting". Otherwise it is completing
  (level 4).
  - Code sets this after every round's judgments, so a later "conflicting" judgment
    makes the settle goal necessary again.
  - A completing settle goal is served after the necessary goals, from spare
    researchers, and its open conflict does not block "complete" (section 11). If it is
    never served, the writer presents both sides.
  - In the flight test, a settle goal on the fastest itinerary's duration decided no
    claim, and the analyst had judged its goal partial, not conflicting. It still ranked
    at level 1, took shares of two researchers and ended not found. Meanwhile the only
    necessary new goal, on transit visas, got a third of one researcher in the last
    round.

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

Built 2026-10-20 (`rounds/analyst.ts`):
- Code rejects:
  - a judgment whose met part cites no finding, or cites a gap line;
  - "answered" with unmet parts;
  - an answered goal with a claim that has no verdict (per claim since 2026-10-26).
- The floor applies to:
  - verification and settle goals;
  - `G3` (when) goals;
  - goals whose `done_when` asks for numbers, prices, dates or rates.
- A goal judged "conflicting" without a conflict record is treated as partial.
- "As of <run date>" or "the latest available evidence" is met by the most recent
  evidence the sources give; it does not require a capture date (test round 2: the
  analyst demanded capture dates and proposed goals that asked only for them).
- The trigger words for the floor no longer include "when", which matched ordinary
  prose in `done_when` (test round 1).
- The fallback after a failed retry repairs judgments instead of dropping them, as
  step 5 of section 5.3 says: evidence IDs that are not findings are dropped, a met
  part left without evidence becomes unmet, and the outcome is recomputed from the
  parts, never above what the analyst said.

Built 2026-10-26 (Lab 4 review): one verdict per claim.
- A goal that checks several claims gets a verdict on each (`verdicts`, by assumption
  ID). The claims of one goal are independent: one can hold while another does not.
- The fallback keeps the verdicts on the goal's own claims; an answered goal left
  without a verdict on one of its claims becomes partial.
- Before, one verdict per goal was copied to every claim it checked. So in the
  false-premise test "NASA launched the James Webb Space Telescope" was marked
  contradicted together with "in 2018".

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
- it does not duplicate an open or settled goal: near-identical text, or the same
  template and objects with overlapping text (built 2026-10-26: the same template and
  object alone rejected three different questions about one telescope);
- it does not ask for a part that a goal re-served this round still misses, since the
  retry asks for it (built 2026-10-26);
- it does not attach to a product object, the answer the client asks for (built
  2026-10-26, as in the request analysis);
- it is at most `maxDepth` derivation steps from the request (default 2);
- the quota allows it: `maxNewGoalsPerRound` (4) and `maxOpenGoals` (20).

New objects enter the ROM only with a verbatim quote from a finding line.

Built 2026-10-20 (section 5.6): a part or life-cycle event includes a step that the
findings reveal and no goal covers, for example a finding that a product must be
imported, which brings in import rules, duties and delivery time. The round analyst
asks what the step requires, kind by kind as in G1, and proposes it when the step
could change the answer to a synthesis question, even if that question does not name
the step. The finding that reveals the step is what prompted it, so the code rules
above are unchanged.

Built 2026-10-21: a new goal keeps the client's scope. The round analyst does not narrow
it to one case of something the client did not state (one region, one customer group,
one budget) because a finding describes that case; it asks for the main cases, or for
the case the request implies. In the flight rerun of 2026-10-20 the transit goals were
written for a Chinese passport holder because the first researcher had assumed one.

Updates also remove work, as EBD's recomposition does (Zeng 2015, p. 14): when an
assumption is contradicted, the goals that rely on it become moot. Built 2026-10-26: a
goal relies on it when it depends on a goal whose claims were all contradicted. When that
goal also confirmed a claim, only the dependents about a refuted object are moot: an
object of the contradicted claim's relations that no supported claim shares ("2018" in
"NASA launched the telescope in 2018", when "NASA launched the telescope" holds). Restating changes
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
- Built 2026-10-20 (`goals.ts`):
  - a round in which every researcher failed is not "saturated", because nothing was
    searched;
  - an assumption whose verification goals all became moot does not block
    "complete";
  - when no goal is ready, the run stops as saturated.
- Built 2026-10-26: an open conflict whose settle goal is completing (section 9) does
  not block "complete".

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
- `off_target` lines are removed, unless a goal cites them as its evidence
  (2026-10-20, section 9).
- Unmapped sections and results go last under "Further findings", so no on-topic
  evidence is dropped. The writer prompt says to use all notes.

**`outline`:** the synthesis questions in order, plus "Where the sources disagree"
when a conflict is disputed and the client sets no length limit. At most 5 items,
matching the writer's 3–5 sections.

**`guidance`:** plain sentences, with no claims of its own beyond the analysis.
- **Client directives.** The report format, scope limits and other directives, each
  with the client's own words. Source preferences have already reached the
  researchers (section 7).
- **Length limit (built 2026-10-21).** When a report-format directive mentions pages,
  paragraphs, sentences or a word count, or asks for something short, brief or
  concise: "The client limits the length ("<client's words>"). This comes before
  everything below: answer the question first, give each disagreement and each gap at
  most one sentence, and leave out detail the client did not ask for." Each disputed
  disagreement then reads "Give both sides in one sentence, with their sources", and
  the outline has no separate disagreement section. The GPU rerun's "one-page summary"
  ran to about 1,470 words while the guidance asked for both sides of seven
  disagreements.
- **Planned contents (built 2026-10-21).** "What each part of the report must
  contain, as planned": each synthesis question with its `done_when`. It carries the
  defaults the analysis asked the report to state, such as an unstated nationality;
  before, the writer saw only the synthesis questions' text.
- **Assumption verdicts.** A contradicted premise: "The question presupposes that
  <claim>. The evidence contradicts this; say so plainly early in the report." An
  unsettled one is stated as not established. This is the H1 lever.
- **Conflicts.** For a settled conflict, which side holds and why, from the notes of
  its settle goal or of the goal that checked its claim in the same round (section 9).
  For a disputed one, both sides with their sources.
- **Off-target referents.** Exclude them, or distinguish the terms only where needed.
- **Defaults and evidence status.** The frame defaults, only where they change the
  answer, as the baseline does with its interpretation. Exhausted necessary goals, as
  evidence status: "no reliable source states …". Built 2026-10-20: a goal with some
  parts met is "only partly established", with its missing parts, so the writer still
  uses its notes (test round 1 told the writer that no source settled goals with 71
  findings). Internal evidence and conflict IDs are removed from the guidance.
- **No meta text.** Never open the report with the guidance, and never mention the
  research process.
- **Out of scope (built 2026-10-26).** The guidance is only: "Nothing was researched:
  <reason>. Write only the title and one paragraph of at most four sentences: why the
  question cannot be answered yet and what the client could provide. Add no other
  sections and no general advice." In the Lab 4 missing-file test, the writer's usual
  3–5 sections turned empty material into 334 words of generic advice.

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
| `premiseFirst` | true | L-7: a request's verification goal is served in round 1 even when the analysis made it wait for definition goals |
| `reserveFirstTries` | true | D-E: keep researchers for necessary request goals not yet served; briefs made only of goals added during the run use the rest (section 7) |
| `init` | `"fixed"` | D-F: `"agent"` runs the request analyst as a tool-using agent |
| `rom` | `"concept"` | Not built. `"word"` would re-enable the rev 1.3 word-level ROM if the A/B test needs it |

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
  request/            prompt (instructions + examples as TS constants), schema, checks,
                      fixed and agent modes
  rounds/evidence.ts  mapping notes to goals and indexing evidence lines (section 8)
  rounds/conflicts.ts conflict checker: prompt, schema, checks, effects (section 9)
  rounds/analyst.ts   round analyst: judgments, evidence floor, proposals (section 10)
  goals.ts            readiness, levels, tie-breaks, reserve slot, moot, stop rules, tree metrics
  briefs.ts           packing goals into briefs
  synthesis.ts        material, outline, guidance
  viewer/             run viewer: static pages to check a run step by step (viewer/README.md)
  *.test.ts           unit tests and the fake-model skeleton test (strategy.test.ts)
  DESIGN.md           this document
```

Every step records its model calls (input, reply, check errors, tokens) and its code
actions in `state.step`, which is replaced at each step. The platform writes the state
into `events.jsonl` after every step, so each decision record shows its own work.

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
| 1 | Scaffold from `_template`; options, state, goals, briefs, stop rules, synthesis; fake-model skeleton test | no | Done 2026-10-20: `npm test` passes; the skeleton test passes the provenance check |
| 2 | Request analysis rev 2: prompt, schema, checks, helper, converted examples; offline tests on recorded replies | X1 | Both models produce valid analyses for the 4 tasks and the Lab 2 cases; A/B test (section 5.5) |
| 3 | `observe`: mapping and indexing, conflict checker, round analyst, update rules | X2, X3 | Built 2026-10-20 and tested offline; first live runs in section 16.1 |
| 4 | `check-strategy` on both models; test rounds as in `docs/plan.md` P7 (classify each problem; fix non-model ones; rerun all 4 tasks) | yes | Two rounds without new non-model problems |
| 5 | Experiments: baseline vs EBD vs ablations, both models, repeats, planted-conflict tasks as explicit questions in the spec | yes | Records ready for blind judging |

### 16.1 Live test rounds (2026-10-20)

`npm run check-strategy -- --strategy ebd --model haiku --task <task>`, which gives 6
researchers (experiments give 10). Every run passed every required check. Each round
fixed the problems the previous one showed. The problems are classified as in
`docs/plan.md` P7.

| Round | Task | Researchers | Stop | Cost (USD) | What the run showed |
|---|---|---|---|---|---|
| 1 | ebd | 1 | complete | 0.04 | Lines listing other expansions of "EBD", which the goal asked for, were marked off_target and left out of the material |
| 1 | headset | 6 | budget | 0.52 | Three settle goals for small price differences, one of them two parts of one article; a judgment lost in a fallback; the guidance said no source settled goals with 71 findings |
| 1 | flight | 6 | budget | 0.38 | Conflict cascade: 17 conflicts and 15 settle goals, down to depth 3 |
| 2 | headset | 6 | budget | 0.52 | Reviewers' opinions recorded as conflicts; the analyst demanded capture dates |
| 2 | flight | 3 | complete | 0.29 | As designed; internal IDs reached the guidance |
| 3 | headset | 2 | complete | 0.15 | As designed; the extra round served one completing goal |
| 3 | flight | 5 | budget | 0.50 | A settle goal got a settle goal of its own |
| 3 | ebd | 5 | complete | 0.28 | A settle goal for an exhausted goal; the request check rejected "Q1" in a question and the retry fixed it |
| 4 | flight | 3 | complete | 0.20 | As designed: one settle goal, answered; two later disagreements disputed; one extra round |
| 4 | ebd | 4 | complete | 0.33 | No new non-model problem; Haiku sent arrays as JSON text and left out `proposals`, which the retry or the repair absorbed |
| 5 | ebd | 3 | complete | 0.17 | After the review changes of section 5.6: analysis accepted on the first attempt; no regression |
| 5 | flight | 5 | complete | 0.48 | After the review changes: the plan asks for the trip's steps, entry documents included; the round analyst raised transit-visa goals for the connecting hubs it found; the report covers the Canadian visa, transit by hub and arrival. New: the research assumed a Chinese passport holder and the report does not say so; no premise was recorded |
| 5 | Lab 3 P3 (GPU comparison) | 6 | budget | 0.55 | Rerun of the 2026-10-19 v0 run, question unchanged. The "use" goal (Q3) never reached a researcher and the cost goal (Q4) got one in the last round: both waited for the flagship goal, which needed two rounds, and settle goals took 3 of the 4 slots left. The report is about 1,470 words although the client asked for one page. The writer cited one URL the research did not report (warning) |
| 6 | flight | 6 | budget | 0.53 | After the four changes of 2026-10-21: the steps question asks for the main entry cases (visa, eTA, visa-exempt) and the report states both kinds of traveller; the nonstop-flights dispute checked no claim. The steps question waited for the flights question and got its only try in round 3. One new goal (never served) was still written for a Chinese passport holder |
| 6 | Lab 3 P3 (GPU comparison) | 6 | budget | 0.48 | After the four changes: the length rule applied (11 one-sentence disagreements, no disagreement section in the outline, 848 words against 1,470); the dispute over whether AMD has a flagship checked A1, the benchmark disputes checked no claim; the reserve held back two settle goals in round 3. Cost and use still never reached a researcher: all three first tries waited for the flagship goal, which waited two rounds for its settle goal |
| 7 | Lab 4 T1–T4 (agent init; `local/lab4/rerun-1026`) | 3, 6, 6, 4 | complete, complete, budget, complete | 0.31–0.59 | After the four changes of 2026-10-26 morning: per-claim verdicts (A1 supported, A2 contradicted on the telescope), no settle goal for an already-checked claim, completing settle goals. Problems: the purposes goal was moot although only the year was wrong (the report never said why NASA launched it; the baseline's did); sub-headings indexed as findings; the duplicate rule rejected 8 of 20 proposals; disagreement sections took 25–40% of the reports |
| 8 | Lab 4 T1–T4 (agent init; `local/lab4/rerun-1027a`) | 2, 6, 6, 6 | complete, complete, budget, budget | 0.08–0.61 | After the evening code fixes: the purposes goal was kept and researched, and the report opens with the correct date and NASA's science purpose; new-goal checks rejected a goal on "How" and two re-asks. Open: when a settle goal ends disputed, the goal waiting for it stays "conflicting" (flight run), so its claim gets no final verdict; disagreement sections still 19–29% (writer change awaiting review) |

| Problem | Kind | Fix |
|---|---|---|
| Settle goals without limits; settle goals for settle goals and for exhausted goals | orchestration | `settleBlock` (section 9) |
| Conflicts over small differences, two parts of one page, opinions | instruction, plus a code rule for one host | Checker prompt; same-host rule (section 9) |
| Off-target lines that the goal asked for were left out | instruction and orchestration | Section 9; kept when cited (section 12) |
| `Q4: …` headings mapped by order | parsing | `headingGoals` (section 8) |
| The fallback dropped whole judgments | orchestration | Repair per part (section 10.1) |
| Floor triggered by "when" | orchestration | Trigger words (section 10.1) |
| Capture dates demanded | instruction | Currency rule (section 10.1) |
| Guidance wording and internal IDs | instruction | Section 12 |
| Schema slips (an array sent as JSON text, a missing field, an unknown enum value), gap lines cited as evidence | model | Caught by the checks and absorbed by the retry or the repair. After round 4, JSON text is decoded and a missing `proposals` counts as none, which saves those retries |
| The writer cited a URL the research did not report (round 1 flight, a warning) | writer (platform) | For the platform owner |

Live check X2 (headings): Haiku kept the goal ID in most sections but often wrote `Q4:`
instead of `[Q4]`, and sometimes dropped it. With the bare-ID rule, rounds 2–4 mapped
32 of 39 sections by ID, 5 by key-question order and 2 to their brief's only goal. All
7 others were in one-goal briefs, so no section went to the wrong goal. Briefs with
several goals still depend on the ID.

X3: both new calls work on live notes. Their tools are not strict, so Anthropic's
grammar limit does not apply.

Total cost of the four rounds: about $3.20. Phase 4 needs two rounds in a row
without a new non-model problem; round 4 is the first. The next round should cover all
four tasks and Luna (needs `OPENAI_API_KEY`).

Open after these rounds:
- Completing goals grown from findings use spare slots while a necessary goal is still
  open (section 6.3, level 4). With 6 researchers, the flight run in round 3 left a
  necessary settle goal unserved. A budget reserve for necessary goals is a candidate
  threshold (D-E).
- The analyst still asks for primary sources (an airline's own timetable) that the
  web search cannot reach, so some goals end exhausted at 4 of 5 parts. Whether that is
  strictness or correct caution is for the judged experiments to show.
- Round 5, flight: the client's nationality is not stated, but the first researcher
  wrote the entry rules for Chinese citizens and the new transit goals followed that
  finding. The synthesis question's `done_when` asked to state this default, but the
  writer receives only the synthesis questions' text (`buildOutline`), not their
  `done_when`, so the report presents one nationality's rules without saying so.
  Built 2026-10-21: planned contents in the guidance (section 12), main cases in search
  questions (section 5.6) and in new goals (section 10.2).
- Round 5, flight: the analysis recorded no assumption, where all four earlier flight
  analyses recorded "a flight connects GuangZhou and Montreal". One run; to watch.
- `plain()` leaves a comma where it removes an ID at the end of a parenthesis
  ("(snapshots are from mismatched dates,)"). Fixed 2026-10-26.
- Round 5, GPU comparison: a necessary request goal that has never been served can lose
  every remaining slot to settle goals, which are level 1 whatever their disagreement is
  about (here the ship date of a next-generation product and a consumer card's margin
  over its predecessor). A reserve of one researcher per unserved necessary request
  goal would have served Q3 and Q4 in round 3. This extends the reserve question above
  (D-E). Built 2026-10-21: the first-try reserve (section 7). The completing-goal case
  of round 3 above stays open.
- Round 5, GPU comparison: the client's "one-page summary" reached the writer as a
  report-format directive, but the guidance also asked it to present both sides of
  seven disagreements, and the report ran to about 1,470 words. Built 2026-10-21: the
  length rule (section 12).
- A settle goal takes over the claim of the goal it settles even when the disagreement
  is about a detail (flight times, airline lists), so its verdict badge refers to that
  claim. If such a goal ended without a verdict, the claim would count as unsettled
  overall. No run so far. Built 2026-10-21: the conflict checker names the claim a
  disagreement decides (section 9).
- Round 6: a goal waits until every goal it depends on is settled (section 6.2), and a
  defining goal often needs two rounds or a settle goal first. In the GPU rerun the
  performance, cost and use goals all waited for the flagship goal, which waited two
  rounds for the settle goal on whether AMD has a flagship; with 6 researchers, cost
  and use were never served, and the first-try reserve could only keep one researcher
  for them. In the flight rerun the steps question got its only try in the last round.
  Candidate fix, for review: a goal is ready once each goal it depends on has findings,
  and the first try of a necessary request goal ranks before retries and before settle
  goals that decide no claim.

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
| D-C | Goals per brief | Up to 3, grouped by object. **Built as the default** (`questionsPerBrief: 3`), pending confirmation |
| D-D | Conflict checker as its own call before the round analyst, or merged | Its own call, so H1 is attributable and ablatable. **Built this way**, pending confirmation |
| D-E | Thresholds | Defaults in section 13, tuned on development tasks only. **Built as the defaults**, pending confirmation. The first-try reserve (section 7) was approved on 2026-10-21 |
| D-F | Init mode: one call with a code retry (`fixed`), or the analyst as a tool-using agent (`agent`) | Lab 3 evidence (Haiku, 81 runs, 2026-10-19): equal final acceptance and case checks; agent costs 1.7–2× the input tokens. Default `fixed`; keep `agent` as an option (both are in `src/strategies/ebd/request/`). **Built this way**, pending confirmation |
| L-7 | When the premise check runs, if the analysis made it wait for definition goals | Round 1, so a refuted premise can make other goals moot early. **Built as the default** (`premiseFirst: true`), pending confirmation |
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
