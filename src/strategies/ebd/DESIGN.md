# EBD strategy design: building EBD research behaviour on the LangGraph platform

Behaviour design (Haoxi Li). **Final (2026-11-20).** The strategy is one approach. It
passes the platform's acceptance check on Claude Haiku 5.5 and on GPT-6 Luna (sections 38
and 39.2).
With the same number of researchers it is level with the baseline, not better; every test
against the baseline is summarised in [evaluation/README.md](evaluation/README.md).

**How to read this document.** It is the record of how the design was reached, in the
order in which things happened. Early sections describe mechanisms that later sections
changed or removed, so start from the table.

| To learn | Read |
|---|---|
| What the final strategy does | Section 1, then the user guide ([README.md](README.md)) |
| The mechanisms that are in the code | Sections 6 to 12 (goals, briefs, reading results, conflicts, round analysis, stopping, the writer's input), as changed by sections 20 (critical conflicts and what is searched after a round), 21 (the key questions of a part), 28 (the plan in one call), 29 (after the first round, only a main part or a claim), 30 (the first round) and 34 (what the writer is told) |
| What was built and taken out again | Sections 5 (the request analysis in several calls), 19 and 22 (the problem extension), 27 (the premise sorter). Section 32 says what went and how it was shown that nothing else changed |
| The tests against the baseline | Sections 23 and 24 (2026-11-18), 31 (the final test), 33 (why the two sides are level), 35 (planted problems), 36 and 37 (weaker models). In one place: `evaluation/README.md` |
| Settings and files | Sections 13 and 15; section 39 for the two switches that were removed last |
| The state at the end, and what is open | Section 38 |

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
- 2026-11-05: the planned changes of the Lab 4 design review (Lab 5), and the system
  finalised for the comparison.
  - Parts of a goal met in earlier rounds are kept with their findings; later rounds
    judge only the missing parts (section 10.1).
  - A conflict whose claim a goal checks in the same round is settled only by a
    supported or contradicted verdict; otherwise it is handled like any other
    disagreement (section 9).
  - Ready goals are split over more briefs when researchers would otherwise sit idle
    (section 7).
  - Each round's results are read in brief order (section 8).
  - A round with a failed researcher is never saturated, and a goal ended only by
    failures is reported as a failure (sections 11 and 12).
  - Fixed: a settle goal judged "conflicting" waited on itself and left the goal
    waiting for it "conflicting" for good (section 9).
  - Decided: D-C, D-D, D-E, D-F and L-7 as built; the comparison spec with a ceiling
    of 6 and a matched-spend control (sections 14 and 18). Platform drafts for the
    owner's review: the code version in run records and the matched control (section 17).
  - The Python request-analyst bundle is removed from the tree (section 5.1).
- 2026-11-05, afternoon: fixes from live rounds 9 and 10 on Haiku (section 16.1), with the
  texts approved by the behaviour design lead.
  - The round analyst may propose a goal for a main part or step the findings only name
    (section 10.2).
  - A new goal attached to the answer object moves to the object of the goal that
    prompted it, and is rejected only when it restates a synthesis question
    (section 10.2).
  - Each disagreement gets at most two sentences in the report (section 12).
  - G1 (b), the request analysis rule for defining an object, no longer lets the
    checklist's environment-kind labels into a goal (section 5.6).
  - Splitting completing goals into their own briefs keeps a researcher for each
    necessary retry (section 7).
- 2026-11-05, evening: completeness. Live failure tests fixed how failed researchers are
  reported (sections 8, 11 and 12); EBD's model calls are tested offline through the
  OpenAI adapter; a user guide is in `README.md`.
- 2026-11-11: problem extension (section 19). After the request analysis, the analyst
  answers "what is the subject?" through its life cycle as a working assumption, each
  event becomes a search goal, and the findings confirm, correct or refute each assumed
  part. Option `extend`, on by default since its prompt text was accepted the same day.
- 2026-11-11, evening: critical conflicts, follow-up and writer input (section 20).
  The conflict checker marks the conflicts the answer depends on; only those are
  followed up, one per round, and only those reach the writer, at most three. A goal is
  searched again only when most of it is unanswered. Options `focusFollowUp` and
  `leanGuidance`, off by default until their prompt text is approved.
- 2026-11-18: part questions (section 21) and a complete map (section 22). A brief asks
  one key question per planned part of a life-cycle step, and each necessary goal gets a
  researcher before a brief of completing goals does; the extension analyst writes the
  events so that they carry the whole answer. Options `partQuestions` and `completeMap`,
  off by default until their text is approved. Checked with a same-day A/B of the briefs
  and with the extension step rerun on 100 saved analyses, then run end to end on the
  five development questions and judged against two baseline samples (section 23).
- 2026-11-18, evening: test on questions the strategy was not developed on (section 24).
  26 new questions, half of them real user queries drawn at random; the plan-level gains
  of `completeMap` and `partQuestions` carry over, the result against the baseline does
  not (blind judgments 8 for EBD and 16 for the baseline on 12 new questions, against 7
  and 3 on the five development questions). Two code changes to the fallback of the
  request analysis: a question whose only fault is its length is kept, and a run no
  longer ends when the analysis leaves nothing usable twice. Of the three changes proposed in
  section 23.3 none is built; one sentence for the extension prompt awaits approval.
- 2026-11-18, night: two decisions of the user applied (section 25). The sentence on the
  main cases is part of the accepted extension prompt. In a follow-up round with
  `focusFollowUp` the necessary goals that ask for content come before the goals that
  settle a disagreement (option `mainPartsFirst`, on by default). Replayed on the 17
  saved runs, the new order changes who gets a researcher in 1 of 23 plans: missing parts
  of the answer were rarely raised, which is now the first open point.
- 2026-11-19: two more decisions of the user applied, and a check of whether the changes
  since section 24 are worth a test (section 26). The round analyst may raise a necessary
  goal for a main part of the answer that no finding mentions (option `uncitedParts`, on
  by default with `focusFollowUp`), and one sentence of the pending conflict-checker
  section is corrected. Replayed with a fresh round analyst on the 17 saved runs, the new
  sentence was never used (0 of 34 replies cite nothing), and the missing parts the judge
  named are still not raised. From the records, the baseline's lead comes from earlier in
  the run: 10 of the 68 first-round researchers only checked a claim the question takes
  for granted, and parts the judge missed were thin in the notes. Verdict: the changes
  made since section 24 would not move the result, so no test was run. Built for the
  user's decision, off by default: a claim check shares a researcher in round 1 (option
  `premiseRides`).
- 2026-11-19, later: the premise check redone on the user's instruction (section 27).
  Before any search a small model call sorts the claims the question takes for granted:
  a specific fact is checked, a claim that only restates the question is taken as given
  (option `premiseSort`). A check shares a researcher with a main part (`premiseRides`,
  now on), and a planned question that the life-cycle steps stand in for only rides
  along (`stepsFirst`). The conflict checker still reports findings that contradict a
  claim taken as given, and the writer gets no line about one unless it was
  contradicted. All three options are on by default. Checked without search: the sorter
  sent every false premise to be checked, on saved analyses and on 16 new questions; in
  replayed first-round plans no researcher only checks a claim any more.
- 2026-11-19, evening: the user allowed a working process of our own as long as EBD's
  concept is kept, and accepted a change of the first step if it improves the approach.
  Built, off by default: the whole first plan in one call (`init: "environment"`, section
  28): the main parts of the answer with their key questions, the claims sorted, what the
  client did not state. Checked on plans without search (204 plans of three methods on 24
  questions): one call in place of three, a fifth of the input tokens, less than half the
  time, no fallback; but it asks about fewer checklist items than the present plan (85% to
  87% against 93% to 94%; baseline 89% to 91%) and about no more of the parts the reports
  lacked. Not switched on; a revision is proposed.
- 2026-11-19, night: the user approved the four wording changes; applied to the planning
  prompt and checked on 12 real queries from a second random draw, never used before
  (section 28.8). A plan now has 14.5 key questions against 11.8, and the share of
  checklist items asked is unchanged (69%; baseline 67%, present EBD 83%). The
  difference to the present EBD is the items that only ask what a term is (26% against
  89%); on all other items the four plans are within four points. False premises are
  still marked for a check in 16 of 16 plans. Both EBD modes stop on a question that
  names no referent, where the baseline plans a general answer. The mode stays off; a
  live run is the next step.
- 2026-11-19, late: the user asked that one EBD approach be left at the end, and approved
  the one proposed (section 29): the one-call plan, key questions asked one by one, a
  follow-up only for a main part of the answer or a claim of the question, lean writer
  input. Built, off by default: option `strictFollowUp` (a disagreement between sources is
  reported, not researched again; a detail gets no researcher after round 1), the
  sentence for a request that names no referent, and wording of the round prompts for a
  plan of key questions. One live run passed all contract checks ($0.58). Every text of
  the approach is on one page for approval, and the rules of the final test are fixed
  (section 29.6). The other planner and the option switches go once a test confirms it.
- 2026-11-19, last: the user approved every change and every text of the one approach
  ("approve all changes and texts"). Before the test, 69 saved plans were replayed with
  the baseline's number of researchers, which the test gives the approach (section 30).
  The first round kept researchers back for second tries: with 3 to 5 researchers a run
  used 2.7 to 3.2 of them, and 14% to 27% of the main parts were asked as one question.
  Changed in code: in the first round of a plan of key questions every researcher goes to
  a main part, the necessary parts first, and a planned part that no researcher was asked
  about is still served after the first round. The test is prepared in two stages, the
  four planted questions first as the live check of the program as tested, with its
  scoring scripts tried on saved runs. It waits for the user's go.
- 2026-11-19, night: the final test, on the user's go (section 31). The one approach
  against the baseline with the same number of researchers, on 12 sealed real queries and
  4 questions with a planted problem. By the rules fixed beforehand the approach is kept:
  the judge preferred it on 4 questions and the baseline on 5, with 3 not decided; it
  stated all four planted points in full, the baseline two in full and two in part; it
  cost 5% more. No difference is shown. It takes 57% longer a run, its claims are judged
  less carefully supported, and three of the baseline's five wins are questions on which
  the approach checked the question's own premise and built the report around the
  verdict. $13.21. The consolidation to one approach waits for the user's word.
- 2026-11-19, after the test: consolidated on the user's word, after one commit of the
  state before (`5b84010`). The one approach is the strategy (section 32): 13 options, the
  premise sorter, the problem extension and every wording and rule that was sent only
  with an option off are gone; the request analysis is no longer called. Replayed with no
  model call, the code makes the same decisions, goals, conflicts, log lines and writer
  input on the 16 runs of the test and on 414 runs of 69 saved plans, and the texts it
  sends are unchanged. 196 tests. Not run with searches since.
- 2026-11-19, after the consolidation: on the user's question why the approach is not
  better than the baseline (section 33). From the records: the two sides did the same
  research, the approach's follow-up loop had no researcher left in any run, its plans
  trade depth on the answer for breadth around it, and what it tells the writer made
  the reports shorter and less sourced. Three cheap trials, about $2.45, no judge and no
  change to the strategy: a different input to the writer (the clearest movement, in
  cheap screens only), a line that makes researchers read pages (not proposed), and
  reworded planner rules at plan level. Proposed texts and a staged plan wait for the
  user.
- 2026-11-20: the user approved the texts of section 33.6 and asked for the judge check
  (section 33.9). The Opus judge on the 12 rewritten reports against the baseline's
  recorded ones: 3 to 2 with 7 undecided (the test: 4 to 5 with 3), 11 to 11 in single
  judgments (11 to 13). Support is no longer lost and coverage rose; usefulness fell. No
  net gain: the writer's input does not make the approach preferred. $1.68. The texts
  are approved and not applied.
- 2026-11-20, later: on the user's word ("Commit consolidation first, then proceed with
  2 recommended steps") the consolidation was committed (`6fc5f1c`) and the approved
  texts were applied (section 34): the writer's outline and lines in `synthesis.ts`,
  two passages of the planning prompt. The line on sources goes in without "Cover each
  part of the outline.", as recommended after the judge check. Replayed with no model
  call, nothing else changes on 17 recorded runs, and the writer's input equals the
  judged one but for that sentence and a claim's label. 199 tests.
- 2026-11-20, last: the planted-problem test (section 35), questions and run approved by
  the user beforehand. 12 new questions (a false fact, sources that give different
  figures, an answer that depends on who asks), both sides with the same researchers,
  the Opus judge on the one planted point: stated in full 12 of 12 by the approach and
  11 of 12 by the baseline. No difference; the approach used 33 of 38 researchers and
  cost 15% less, and took half as long again. $7.43. First runs with searches of the
  code of sections 32 and 34: 12 of 12 ended ok.
- 2026-11-20, on the user's question whether a weaker model would separate the sides
  (section 36): a probe of the planning step, $0.40, no test. With Haiku 5.5 at medium or
  low effort neither side's plan takes a false or unknowable fact for granted (0 of 24
  each); with the previous Haiku the baseline's does in 3 of 12 plans and the approach's
  in none. A sign of where a difference could open, not a result.
- 2026-11-20, with the OpenAI key the user added (5 dollars on it; section 37): the
  planning probe on GPT-6 Luna (plans like Haiku 5.5, no gap) and on the older GPT-5 nano,
  and a side run with searches on GPT-5 nano, six questions with a well-known false fact:
  the approach stated the correction in 6 of 6 reports, the baseline in 4 of 6 (one in
  part, one not at all). The first setting in which the approach is ahead; six
  questions, an indication. On that model 11 of 24 of the approach's replies were
  rejected and redone and its round analysis was repaired by the code in 5 of 6 runs.
  At most $2.78. The platform's model file is unchanged.
- 2026-11-20, final: on the user's word to finalize (section 38). The platform's
  acceptance check passed on the committed code on Haiku 5.5 and, for the first time, on
  Luna (11 of 11 checks each). The user guide and the head and section 1 of this
  document describe the final strategy; `evaluation/` holds the record of every test
  against the baseline with its data. Nothing outside this folder was changed.
- 2026-11-20, after the finalization: the two switches `conflicts` and `newGoals` removed
  on the user's view that they should not stay (section 39). No test had compared a
  report with a switch off against one with it on. Replayed with each switch off, the
  28 test runs give the writer the same input without new goals (28 of 28); without the
  conflict checker the writer loses the lines on critical disagreements in 17 of 27
  runs, and a run would be about 40 s shorter. The platform's comparison spec loses the
  two arms that set them, in a commit for the platform owner's review. Two limits that
  stopped every new goal at 0 now start at 1. The acceptance check passed again on the
  committed code on Haiku 5.5 and on Luna (11 of 11 checks each).

## 1. Summary: the final design

- **What it is.** EBD is a strategy plug-in, `src/strategies/ebd/`, implementing `init`,
  `observe` and `finalize` of contract v1 (`docs/strategy-modules.md`). The platform runs
  the researchers, the writer, the budget and the records for both sides. EBD decides
  what to research, when to stop and what the writer is told.
- **What it keeps of Environment-Based Design.** EBD designs a product from its
  environment: first what surrounds the product and what that requires of it, then the
  conflicts, then solutions, and each solution changes the environment. Here the product
  is the answer to the client's question. Its environment has three sides: the client who
  will use the answer, the subject with everything around it that the answer depends on,
  and what the question itself takes for granted. The conflicts are disagreements between
  sources and between the evidence and the question's claims. The procedure is the
  team's own: on 2026-11-19 the lead decided that the strategy follows EBD's concept and
  not its procedure step by step (section 28.2).
- **`init`: the plan, in one model call** (the environment analyst, section 28). It writes
  the main parts a full answer needs, usually 3 or 4, each with 4 or 5 key questions and
  marked necessary or completing; the claims the question takes for granted, sorted into
  those to check (a specific fact that could be wrong) and those taken as given; what the
  answer depends on and the client did not state; and terms with several meanings. Code
  checks the reply and turns the plan into goals. In the first round every researcher
  goes to a main part, the necessary parts first (section 30), and the check of the
  claims is one key question in the brief of a main part.
- **`observe`: after each round.** Code maps the researchers' notes to goals and indexes
  every finding (section 8). The conflict checker, one model call, lists the disagreements
  and marks each critical or not (sections 9 and 20). The round analyst, one model call,
  says which key questions the findings answer, gives a verdict on each checked claim and
  proposes new goals (section 10). Code then settles goals, accepts at most two necessary
  new goals a round, and sends a later researcher only to a main part of the answer or to
  a claim of the question (section 29). The run stops when nothing of that kind is left,
  or when no researcher is left (section 11).
- **`finalize`: what the writer gets** (sections 12 and 34). The material is whole lines
  of the researchers' notes, grouped by goal. The researched main parts are the suggested
  outline. The guidance has a few lines: a claim of the question that the evidence
  contradicts, to be corrected in a sentence or two before the question is answered as
  asked; at most three critical disagreements; a line on the question's main terms and a
  line on sources.
- **Model and code.** The three model roles make narrow judgments in structured replies.
  Code checks every reply and asks again once when it fails, and code alone turns the
  judgments into priorities, briefs and stops. Every step records its model calls and its
  code actions, which the run viewer shows.
- **Settings** (section 13): limits and three rules for dividing researchers. No setting
  chooses another planner or turns the conflict checker or the new goals off (section
  39).
- **What was built and taken out.** The request analysis in several calls, the problem
  extension with its environment map, and the premise sorter made the first plan until
  2026-11-19. They took about three planning calls where one now does, for the same
  substance (section 28), and the follow-up they fed spent researchers on disagreements
  that decided nothing (section 24.5). The one-call plan and the fixed follow-up rules replaced them
  (sections 28 to 32).
- **Where it stands against the baseline.** With the same number of researchers on Claude
  Haiku 5.5 the two sides are level on ordinary questions and on questions with a planted
  problem, at about the same cost and half as much time again. On a weaker model the
  strategy's explicit checks begin to pay (sections 31, 33 and 35 to 37;
  `evaluation/README.md`).
- **Constraints from the platform**, unchanged since the first build: all search goes
  through briefs; the writer's material must be lines of the researchers' notes; and
  structured replies behave differently on the two providers (section 5.3).

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
| Conflict checker | A `ctx.model` call in `observe` |
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
- That path belonged to the deleted Python platform and was removed from the tree on
  2026-11-05. Recover it with `git show 43dc249:<path>`.
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
   Since 2026-11-18 the fallback of the request analysis keeps a question whose only
   fault is its length, and a second failure in one run gives a minimal plan instead of
   a throw (section 24.4).

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

Changed 2026-11-05 (live round 10): G1 (b) asked `done_when` to name, for each event, "the
kinds that matter". On the EBD question, whose subject is a theory of environment kinds,
the analysis copied the checklist's labels into a goal: "for each the environment kinds it
covers (natural, built, digital, economic, social)". The researcher wrote that the client
mentioned these categories, and the report told the client that "the client's digital,
economic and social categories do not appear in the framework". The labels reached the
analysis in 3 of 10 runs of the EBD question and the report once. G1 (b) now asks for what
to find in the object's own terms (the fees, documents and people involved at each step)
and says that the kind names are labels for the check, never to be listed in a question or
`done_when`. The worked examples already wrote `done_when` this way.

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
- **Spreading (`spread`, built 2026-11-05).** When packing leaves researchers idle this
  round, shared briefs are split: the lowest-ranked goal of the largest brief gets its
  own brief, one at a time, until every free researcher has a brief or every brief has
  one goal. Free researchers are `maxPerRound`, or the remaining budget less the
  first-try reserve if smaller. In the Lab 4 flight run, rounds 1 and 2 sent one
  researcher each, with every ready goal about the flight in one brief, although four
  could run (Lab 5 review, change 3). Two kinds of split, in this order (changed after
  live round 10):
  - a necessary goal leaves a brief that keeps another necessary goal, whenever a
    researcher is free;
  - any other split leaves a brief of completing goals only, and is made only while, after
    this round, one researcher stays for each necessary goal served in it, in case it
    needs a retry.

  In round 9 such completing splits helped: the flight run's premise check found the
  disagreement over nonstop flights, and the headset run's app-ecosystem goal covered a
  checklist item, with researchers to spare. In round 10 they took the last researchers:
  two necessary headset goals (intended use and audience; passthrough quality) got no
  retry, and the flight run's necessary goal on transit at Toronto was never served. The
  guard keeps every split of round 9 and blocks both of round 10.
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
- **Order (built 2026-11-05):** the round's results are sorted by brief ID before
  anything reads them, so the conflict checker and the round analyst see the findings
  in the same order whatever order the researchers finished in. Code decisions never
  depended on arrival order (Lab 5 review, change 4).
- **Failures:** a failed researcher counts as an attempt for each of its goals. The
  goal is re-queued, or exhausted after `maxAttempts`; it is not marked "not found",
  because nothing was searched. Since 2026-11-05 failed attempts are counted, and a goal
  whose attempts all failed is reported as a failure (section 12). Its claims keep no
  verdict, since nothing checked them: in the live failure test (section 16.1) the old
  "unsettled" made the writer say that the evidence does not establish that EBD exists.

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
records or settle goals are made. This is the H1 ablation. (The switch was removed on
2026-11-20, section 39: the conflict checker always runs.)

With `focusFollowUp` (section 20), only a critical conflict gets a settle goal: one per
round, necessary, with one attempt.

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
  - Changed 2026-11-05 (Lab 5 review, change 2): the conflict waits for that goal's
    verdict (`checkedBy`). A supported or contradicted verdict settles it, with that
    goal as its `settleGoal`, and the guidance points the writer to that goal's notes.
    An unsettled verdict, or none, leaves a real disagreement: it gets a settle goal
    within the limits, or is disputed. Before, the conflict was settled at once, so with
    an unsettled verdict the writer was told both that the claim is not established and
    that the notes show which side holds.
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

Fixed 2026-11-05: a settle goal judged "conflicting" is disputed, and so are its
conflict and the goal waiting for it. Before, it looked for an open conflict on its
objects, found its own, and waited on itself; the goal waiting for it stayed
"conflicting" and its claim never got a final verdict (Lab 4 flight run). As a safety
net, after every round a conflicting goal whose settle goal has settled settles too:
answered if the settle goal was answered, disputed otherwise (`releaseWaiting`).

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

With `focusFollowUp` (section 20), a partial goal is re-queued only when fewer than half
of its parts are met or a client claim it checks is undecided, and the evidence floor
applies to client claims only.

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

Built 2026-11-05 (Lab 5 review, change 1): met parts are kept.
- Each part judged met is stored with its findings and round (`metParts`). The message
  for a retried goal lists them under "Parts already met (kept from earlier rounds; do
  not judge them again)" and asks to judge only the missing parts; the outcome is
  judged on those parts alone.
- `partsMet` and `partsTotal` count the kept parts too. A "conflicting" judgment locks
  nothing, because its findings disagree.
- Before, every round judged every part again: in the Lab 4 EBD run, "each source's
  name, date and scope" was met in round 1 and judged unmet in round 2.

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
- it does not ask for the final answer. A goal attached to a product object (the answer
  the client asks for) is rejected when its text restates a synthesis question
  (near-identical, at least 0.45 of their content words shared, or at least 0.75 of its
  own content words in the synthesis question); otherwise it moves to the object of the
  goal whose evidence prompted it. Built 2026-10-26 as an outright rejection, as in the
  request analysis; changed 2026-11-05 after live round 9, in which the flight run lost
  its necessary transit and visa goals only because the question has no object for them
  but "How";
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

Built 2026-11-05 (live round 9): this also covers a main part or step that the findings
only name. When findings list an object's main parts or steps but none says what one of
them involves, the round analyst proposes a goal for it if a synthesis question needs it
explained, even when the part of a goal that asks for the list is met. The EBD question's
run named EBD's three activities but explained only environment analysis, and no goal was
proposed, so it failed the growth criterion (section 14), as Lab 4's T1 had.

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
| Researcher failures (built 2026-11-05) | As complete, but a necessary goal ended only because its researchers failed | `stop: true` | `strategy-stop`; the state records `researcher_failures`, so such a run never counts as complete |

- After **complete**, at most one more round serves completing goals, if
  `extraRound` is on and a researcher is left.
- The stop kind is also kept in the state (`stop.kind`, `stop.round`).
- Built 2026-10-20 (`goals.ts`):
  - a round in which a researcher failed is not "saturated", because its goals wait for
    a retry (2026-11-05, Lab 5 review, change 8; before, only a round in which every
    researcher failed);
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

**`guidance`:** plain sentences, with no claims of its own beyond the analysis. What
follows is the full guidance; `leanGuidance` (section 20.4) keeps only what the notes
do not show.
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
  For a disputed one, both sides with their sources, in at most two sentences (built
  2026-11-05: in live round 9, disagreements took 42% of the sleep report and 23% of the
  flight report; with a client length limit, one sentence, as before).
- **Off-target referents.** Exclude them, or distinguish the terms only where needed.
- **Defaults and evidence status.** The frame defaults, only where they change the
  answer, as the baseline does with its interpretation. Exhausted necessary goals, as
  evidence status: "no reliable source states …". Built 2026-10-20: a goal with some
  parts met is "only partly established", with its missing parts, so the writer still
  uses its notes (test round 1 told the writer that no source settled goals with 71
  findings). Built 2026-11-05: a necessary goal whose attempts all failed is not "no
  reliable source": "These questions could not be researched because of technical
  failures, not for lack of sources. Do not claim that no source exists; where relevant,
  say only that the report does not cover them." Internal evidence and conflict IDs are
  removed from the guidance.
- **No meta text.** Never open the report with the guidance, and never mention the
  research process.
- **Out of scope (built 2026-10-26).** The guidance is only: "Nothing was researched:
  <reason>. Write only the title and one paragraph of at most four sentences: why the
  question cannot be answered yet and what the client could provide. Add no other
  sections and no general advice." In the Lab 4 missing-file test, the writer's usual
  3–5 sections turned empty material into 334 words of generic advice.
- **Nothing researched (built 2026-11-05).** When every researcher of the run failed,
  the guidance is only: "Nothing could be researched: every researcher failed for
  technical reasons, so there is no evidence. Write only the title and one paragraph of
  at most four sentences: say that the research could not be carried out, so the
  question is not answered, and that it should be run again. Do not answer from general
  knowledge, and do not judge the question's premises." There is no outline. In the live
  failure test the usual plan gave 431 and 773 words with no evidence behind them.

## 13. Options and ablations

Strict zod options, all with defaults, chosen per experiment spec. Since the consolidation
of section 32 and the removal of the two ablation switches (section 39) these are limits
and three rules for dividing researchers (`premiseFirst`, `reserveFirstTries`,
`spread`); an option that is not listed is rejected.

| Option | Default | Use |
|---|---|---|
| `maxPerRound` | 4 | Briefs per round |
| `questionsPerBrief` | 3 | Goals packed into one brief |
| `maxNewGoalsPerRound` / `maxOpenGoals` / `maxDepth` | 4 / 20 / 2 | New-goal limits, each at least 1 (section 39) |
| `maxAttempts` | 2 | Attempts before a goal is exhausted |
| `evidenceFloor` | 2 | Independent hosts needed before a claim of the question counts as checked (section 20) |
| `premiseFirst` | true | L-7: a request's verification goal is served in round 1 even when the analysis made it wait for definition goals |
| `reserveFirstTries` | true | D-E: keep researchers for necessary request goals not yet served; briefs made only of goals added during the run use the rest (section 7) |
| `spread` | true | Give every researcher of a round a goal of its own where the goals allow it: in the first round every researcher goes to a main part of the answer, the necessary parts first (section 30); in a later round shared briefs are split when researchers would otherwise sit idle (section 7) |

Removed on 2026-11-19, with the section that describes what each one switched: `extraRound`, `init`, `extend`, `focusFollowUp`, `leanGuidance`, `partQuestions`, `completeMap`, `mainPartsFirst`, `uncitedParts`, `premiseRides`, `premiseSort`, `strictFollowUp`, `stepsFirst`. Section 32.1 says what the code does in place of each.

Example spec entry:

```json
{ "name": "ebd", "label": "ebd-three-a-round", "options": { "maxPerRound": 3 } }
```

Removed on 2026-11-20 (section 39): `conflicts` (the conflict checker on or off) and
`newGoals` (new goals from the evidence, or the first plan only).

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

Fairness (decided 2026-11-05; Lab 5 review, change 6):
- All arms run from one spec on one commit, `experiments/compare.json`, and every run
  record names its commit.
- Ceiling of 6 researchers for every arm. It is the baseline's largest plan and its
  per-round cap, which it never exceeded (Lab 4 questions: 3, 4, 3, 3).
- Matched-spend control `ebd-matched`: EBD with the researchers the baseline used on the
  same task, model and repeat, so a quality difference cannot come from search volume
  alone.
- Reported with quality: researchers, searches, page reads and strategy model calls
  (`docs/design.md` §8).
- Web results cannot be frozen, so the arms of one task run in the same session, with
  repeats, and each run records its queries and sources.
- Coverage is scored on checklists written before the runs
  (`experiments/checklists.md`). An item counts only if the report states it with a
  supporting citation, judged blind.
- Goal growth (H-9) passes when every main part the findings name has a goal and is
  explained in the report (Lab 5 review, change 5; criterion in the same file).

## 15. Module layout and tests

```
src/strategies/ebd/
  index.ts            StrategyModule default export; EbdStrategy (orchestration only)
  options.ts          OptionsSchema (strict zod)
  state.ts            EbdState and its parts (types, not interfaces: JsonValue)
  llm.ts              structured-call helper with validation and one feedback retry
  environment.ts      environment analysis in one call: prompt, schema, checks, and the
                      analysis, map and goals built from the plan (section 28)
  analysis.ts         the analysis as the strategy keeps it: the reading of the request, its
                      frame, objects, claims and questions; the plan of last resort
  map.ts              the plan's map during a run: key questions confirmed, corrected or
                      refuted, and each part's goal kept in step (sections 19 and 28)
  request/            the request analysis of Lab 2, which made the first plan until
                      2026-11-19; no longer called by the strategy (section 32.4)
  rounds/evidence.ts  mapping notes to goals and indexing evidence lines (section 8)
  rounds/conflicts.ts conflict checker: prompt, schema, checks, effects (section 9)
  rounds/analyst.ts   round analyst: judgments, evidence floor, proposals (section 10)
  goals.ts            readiness, levels, tie-breaks, reserve slot, moot, stop rules, tree metrics
  briefs.ts           packing goals into briefs
  synthesis.ts        material, outline, guidance
  viewer/             run viewer: static pages to check a run step by step (viewer/README.md);
                      traces.ts adds each run's Langfuse trace (LangChain callbacks, read back
                      through Langfuse's public API)
  *.test.ts           unit tests, the fake-model skeleton tests (strategy.test.ts,
                      approach.test.ts, environment.test.ts), and EBD's model calls through
                      the OpenAI adapter offline (providers.test.ts)
  fixtures.ts         test data: two worked analyses with goals that depend on one another
  evaluation/         the tests against the baseline: questions, the judge's output, reports,
                      tables and the scripts behind them (evaluation/README.md)
  README.md           user guide: running a question, settings, stops, reading a run
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
| 4 | `check-strategy` on both models; test rounds as in `docs/plan.md` P7 (classify each problem; fix non-model ones; rerun all 4 tasks) | yes | Two rounds without new non-model problems. **Haiku done 2026-11-05** (rounds 9–11): round 11 found no new non-model problem, and what remains is recorded in section 16.1. **Luna not run** (no OpenAI key) |
| 5 | Experiments: baseline vs EBD vs ablations, both models, repeats, planted-conflict tasks as explicit questions in the spec | yes | Records ready for blind judging. **Spec ready** (`experiments/compare.json`, checklists in `experiments/checklists.md`); waits for Luna, for `routed-review` on main (request P7) and for the planted-conflict tasks, which are not written yet |

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
| 9 | ebd, headset, flight, sleep (check-strategy, commit `3325ece`, `local/accept-1105`); matched pair on ebd | 1, 6, 5, 6; baseline 3 and ebd-matched 3 of 3 | complete ×4; matched: budget | 0.05–0.53; $1.65 in total | After the Lab 5 review changes. Every required check passed. The matched control gave EBD the 3 researchers the baseline used, and every record names its commit. Spreading served the ready goals in parallel in three runs; kept parts were used in three (headset Q2 ended 5/6 with five kept parts). Problems: the EBD run named EBD's three activities and explained one, and proposed no goal (growth criterion failed); the flight run lost its necessary transit and visa goals to the answer-object rule; disagreements took 42% of the sleep report; the writer mistyped one host (`xuebei` for `xuebao`), a platform warning |
| 10 | ebd ×2, headset, flight, sleep (check-strategy, commit `0b6087c`, `local/accept-1105/r10`) | 3, 3, 6, 6, 6 | complete, complete, budget, budget, complete | 0.16–0.68; $2.02 in total | After the round-9 fixes. Every required check passed. Growth on the EBD question: one run's notes explained all three activities; in the other the round analyst proposed a goal on what each activity involves, and the report explains each one with its inputs, outputs and tools. The headset run moved a necessary goal (intended use and audience) off the answer object instead of rejecting it. Each disagreement became one compact table row, but the sleep run had 14, still 40% of its report. Problems: the analysis copied its checklist of environment kinds into an EBD goal, and the report told the client that "the client's" categories were not in EBD (section 5.6); completing splits took the last researchers in the headset and flight runs (section 7); the analyst exhausted necessary goals for want of dated or primary sources (open, below) |
| 11 | ebd ×2, headset, flight, sleep, and the Lab 4 false-premise question "Why did NASA launch the James Webb Space Telescope in 2018?" (check-strategy, commit `f50de7f`, `local/accept-1105/r11`) | 4, 1, 5, 6, 6, 6 | complete, except flight: budget | 0.06–0.52; $2.01 in total | After the round-10 fixes. Every required check passed, no unknown URL, no new non-model problem. The false-premise run took the claim-check path: the conflict over the launch year waited for the verdict, the year was judged contradicted while "NASA launched it" held, the conflict settled on that goal with no settle goal, and the report opens with the correct date (25 December 2021). The sleep run took the other path: its premise check left "some food can help" unsettled, so that disagreement stayed open and was disputed; a settle goal whose sources still disagreed was disputed and released the goal waiting for it. The split guard kept researchers for necessary retries, and the flight run served its goal on clearing customs at Toronto. The checklist labels reached one EBD goal again, but there they matched the categories of the published eLCD adaptation, and the report presented both lists with sources |

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
| A main part the findings only named got no goal (round 9, ebd) | instruction | Round analyst prompt (section 10.2) |
| Necessary new goals rejected because they were attached to the answer object (round 9, flight) | orchestration | Moved to the prompting goal's object; rejected only when they restate a synthesis question (section 10.2) |
| Disagreements took 23–42% of reports (round 9, flight and sleep) | instruction | At most two sentences each (section 12) |
| New goals written for one nationality the client did not state (round 9, flight) | model | Recorded; the round analyst prompt already forbids it |
| The checklist's environment-kind labels copied into a goal and reported as the client's categories (round 10, ebd) | instruction | G1 (b) asks for the object's own terms and forbids the labels (section 5.6) |
| Completing goals split into their own briefs took researchers that necessary retries and a new necessary goal needed (round 10, headset and flight) | orchestration | Budget guard on the split (section 7) |
| Many disagreements on an evidence-heavy question: 14 table rows, 40% of the sleep report (round 10) | model and question | Recorded: each row follows the two-sentence rule, and several rows correct a source's error |
| The EBD question's plan varies from one goal (one researcher, round 11) to three (four researchers) | model | Recorded; the judged comparison shows whether it matters (the baseline used three researchers there) |

Open after round 11 (2026-11-05), recorded rather than fixed:
- The round analyst exhausts necessary goals for want of dated or primary sources the web
  search does not reach (round 11: the flight goal at 3 of 6 parts, the headset goal at 5
  of 11, the sleep goal at 1 of 4). Whether this is strictness or correct caution is for
  the judged comparison to show (open since round 3).
- Not run on Luna: there is no OpenAI key on this machine. EBD's model calls through
  the OpenAI adapter are tested offline (`providers.test.ts`).

Live failure tests (2026-11-05, `local/accept-1105/failures`): experiment specs with a
researcher time limit of 10 and 30 seconds, so that real researchers fail mid-search.
In both runs every researcher failed, and three faults showed: the question's claims
were marked unsettled, so the writer said the evidence does not establish that EBD
exists, or that the two headsets are real products; the run was recorded as complete;
and the writer still followed the section plan, writing 431 and 773 words with no
evidence. Fixed the same day: such claims keep no verdict, the stop is
`researcher_failures` (section 11), and the writer gets a short note with no outline
(section 12). Rerun on commit `b3a18d2`: the run stopped as `researcher_failures`, the
writer received only the short note, and the report was 57 words saying that the research
could not be carried out and should be run again. With a 60-second limit every
researcher finished, so a run in which only some researchers fail has not occurred live;
its rules are covered by unit tests.

Settings checked live on commit `63578c7` (check-strategy, every required check
passed): the tool-using request analyst on the EBD question ($0.20; it grew a goal on
what conflict identification and solution generation involve); no conflict checker on
the false-premise question ($0.31; the check of the question's claims alone made the
report open with the correct launch date); no new goals on the headset question
($0.41).

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
- **P5 (drafted 2026-11-05).** The code version in every run record: `config.json` and
  `summary.json` carry the commit, the branch and whether tracked files had uncommitted
  changes (`src/platform/version.ts`).
- **P6 (drafted 2026-11-05).** The matched-spend control: `matchResearchersTo` in a
  spec's strategy entry, `experiments/compare.json` and the coverage checklists
  (`experiments/checklists.md`).
- **P7.** Merge `routed-review` (with `baseline-router`) into main, so the comparison
  can include the stronger non-EBD arm. `behaviour-design` then merges main, and the two
  labels are added to `experiments/compare.json`.
- **P8 (writer).** The writer twice wrote `xuebei.sjtu.edu.cn` for the reported
  `xuebao.sjtu.edu.cn` (2026-11-05, two EBD-question runs), so the citation check flagged
  an unknown URL. The repair after writing completes only cut-off URLs; matching an
  unknown URL to the one known URL that differs from it by a letter or two would repair
  this kind of typo too.

## 18. Open decisions

| ID | Decision | Recommendation |
|---|---|---|
| D-A | Client route and `needs_clarification` in rev 2 | **Decided 2026-10-19: removed** (section 5.2) |
| D-B | Concept-level or word-level ROM | Concept-level plus the never-drop check; word level as an ablation only if needed |
| D-C | Goals per brief | **Decided 2026-11-05:** up to 3, grouped by object (`questionsPerBrief: 3`), split when researchers would sit idle (`spread`) |
| D-D | Conflict checker as its own call before the round analyst, or merged | **Decided 2026-11-05:** its own call, so H1 is attributable and ablatable |
| D-E | Thresholds | **Decided 2026-11-05:** the defaults in section 13, tuned on development tasks only, with the first-try reserve (approved 2026-10-21) |
| D-F | Init mode: one call with a code retry (`fixed`), or the analyst as a tool-using agent (`agent`) | **Decided 2026-11-05:** `fixed`. Lab 3 evidence (Haiku, 81 runs, 2026-10-19): equal final acceptance and case checks; agent costs 1.7–2× the input tokens. `agent` stays an option |
| L-7 | When the premise check runs, if the analysis made it wait for definition goals | **Decided 2026-11-05:** round 1 (`premiseFirst: true`), so a refuted premise can make other goals moot early |
| D3 | Budget matching between the arms | **Decided 2026-11-05:** one spec, ceiling 6, matched-spend control (section 14) |
| D2 (team) | The fixed EBD question has no planted conflicts, so H1 needs the planted-conflict tasks | Keep the four tasks for development; add the nine proposal tasks as explicit questions in experiment specs |
| D5 (team) | Calendar | If W1 is the week of 2026-09-21, scope freezes the week of 2026-10-26 |

## 19. Problem extension: the environment map (option `extend`, built 2026-11-11)

On by default since 2026-11-11, when the behaviour design lead accepted the prompt text
after the live checks of section 19.5. `extend: false` gives the plan built from the
request's words, for comparison.

### 19.1 Why

- **What the comparison showed.** In the five-question comparison of 2026-11-10
  (`local/arch-1110/`), the first EBD plan had 1 or 2 goals built from the request's
  words; round 1 made 43 searches against the baseline's 113; topics a full answer needs
  never reached the notes (for the headset question, how comfortable the headsets are;
  for the flight question, how to get from the airport to the city).
- **What EBD prescribes.** Questions asked from the request's own object model are only
  the first half, "design problem analysis". The second half, "design problem
  extension", answers the question about the main object through its life cycle and the
  environment of each event, adds the answer to the object model and asks again (Wang &
  Zeng 2009, Table 4, rules 3 to 6; Zeng 2020, Table 10 and pp. 58 to 60). In the
  papers' cases most questions come from the second half: 2 from the wording and 9 from
  the life cycle for the rivet tool (Wang & Zeng 2009, pp. 293 to 294).
- **What the module did.** Section 5.6 ported the answering guideline as the completion
  criterion (`done_when`) of one goal, so one researcher with 8 searches had to deliver
  the whole life cycle, and no answer went back into the plan.

### 19.2 The step

After the request analysis, `init` makes one more model call, the **extension analyst**
(`extension.ts`). The request analysis, its prompt and its checks are unchanged.

- **Input:** the analysis: restated request, frame, objects, client assumptions, the
  planned search questions with what each checks, and the synthesis questions.
- **Output:** the subject; the life-cycle events the client's question depends on
  (usually 3 or 4, at most 5), each marked necessary or completing; for each event 3 to
  6 **parts** (what the event involves, each with an environment kind: natural, built
  physical, built digital, economic, social), one self-contained search question, source
  hints and the synthesis questions it feeds; and the planned questions the events
  replace.
- **Only what the question needs.** An event is kept only if a full answer to the
  client's question needs it; a stage of the subject's life that the question does not
  concern is left out, however much could be found about it. EBD's criteria for
  environment analysis are meant "to avoid the under- or over- definition of a design
  problem" (Zeng 2020, p. 51), and the eLCD case keeps only the events "more relevant to
  the current design" (Yang et al. 2020). In the fourth live batch
  the plan for "Why did NASA launch the James Webb Space Telescope in 2018?" included
  the launch campaign, the deployment and the operations after commissioning, and the
  report spent most of its length on them.
- **What the analyst may use.** Its general knowledge, to name kinds of things only.
  Everything it writes is an assumption. The code check that keeps names out of the
  request analysis (`namesIn`) runs on every event, part and question, so a specific
  organisation, product or law that the request does not name is rejected. In the live
  runs it rejected, for example, the name of the departure airport and the orbit point
  of the telescope, which the analyst knew and the request does not say.
- **Checks and fallback.** One event, part or source hint too many is cut with a
  warning. After a second rejected reply, the fallback keeps the valid events and drops
  only the part an error points to; it needs two events, and then replaces no planned
  question. Without a usable reply the plan is the request analysis's own.
- **What code builds.** The **environment map** (`state.map`): the events and their
  parts, each part with an origin (assumed or found) and a status (assumed, confirmed,
  refuted, unfound). One search goal per event, with origin `assumed`; at most four are
  necessary.
- **Report points.** Every point that a synthesis question says the report must contain
  is a part of some event, also when a planned question asks for it. The loop can cancel
  a planned question or give up on it, while an event goal depends on nothing. In the
  third live batch the goal "Why did NASA launch the James Webb Space Telescope?" was
  again cancelled with the false launch year, no event asked for the mission's purpose
  because that planned goal did, and the report could give the purpose only in brief
  terms. With this rule the same question gets a necessary event for the programme's
  origins, with the scientific goals as a part.
- **Replaced questions.** The events may replace a planned question that asks for the
  subject as a whole, but only one that checks no client assumption. The replaced
  question is not deleted: it becomes a completing goal, and the goals that waited for it
  wait for the necessary event goals instead. It is still asked, in the request's own
  terms, in a brief it shares with event goals, and it neither holds up the stop nor
  claims a second attempt. The events are assumptions and may not carry all it asked: in
  the second live batch the events that replaced "What is the telescope ...?" covered
  its development, launch and deployment but not its purpose, the goal that asked why
  was cancelled with the false launch year (the open point of section 10.2), and the
  report could not say why the telescope was launched.
- **Briefs.** An event goal's brief lists the parts and says they are expectations, not
  facts: the researcher reports what the sources say, says so when a part does not
  apply, and adds other main points the sources treat as part of the step.

### 19.3 How the evidence overwrites the plan

The parts are the analyst's working answer, so they are never evidence, and a finding
decides each one (decision of 2026-11-11: the analyst's general knowledge may give the
first answers, provided evidence or a conflict can overwrite them).

| What the evidence shows | Effect |
|---|---|
| A finding covers the part | The round analyst marks it met; the part is **confirmed** with its findings |
| A finding states that the part does not exist or does not apply | The part is **refuted** and leaves the plan: it is not searched again and not reported as missing. If the findings say what holds instead, that enters the map as a **found** part |
| The same, in the findings of any goal of the round | The conflict checker records an `evidence_vs_plan` conflict, which is settled at once with the same effect. This reaches the parts of goals that were not served in the round |
| Every part of an event is refuted | The event's goal becomes moot |
| At least half of an event's parts are confirmed | The event counts as researched and its goal is answered. The parts no source reported become **unfound** and are not searched again; the round analyst may propose a goal for one the report needs, written with what the findings now show |
| Fewer than half are confirmed | The goal gets its second attempt, as other goals do |
| Sources disagree about a fact inside an event | The disagreement keeps its own conflict record and settle goal. It does not hold the event open, so the settle goal is completing unless it decides a client assumption |

- Silence never refutes: a part the sources do not mention is unfound, not refuted.
- A finding that only one item of a part does not apply, or that the part does not apply
  to one of several things the subject covers, confirms the part. In the second live
  batch the conflict checker removed "sales channels, retailer discounts and trade-in
  offers" from the headset plan because one headset has no trade-in; both prompts now
  say that such a finding is information about the part.
- The floor of two independent hosts (section 10.1) does not apply to event goals: they
  ask what a step involves, and their parts are assumptions, not checked facts.
- **The writer** never receives an assumption. The guidance names only the events that
  findings confirmed; unfound parts, refuted parts, moot event goals and
  `evidence_vs_plan` conflicts are left out. The events are named as material for
  answering the client's question, not as sections the report must have: an earlier
  wording ("give each one a place in the report") made the writer give every researched
  event a section.

### 19.4 What stays the same

- With `extend` off, no map exists, and the prompts and tool schemas sent to the
  conflict checker and the round analyst are the earlier ones, character for character
  (`analystSystem(false)`, `conflictSystem(false)`); the tests check this. So `extend:
  false` is the plan built from the request's words, for comparison. The loop tests of
  `strategy.test.ts` run with `extend: false`; the loop with a map is tested in
  `extension.test.ts` and `focus.test.ts`.
- With a map, first attempts come before second attempts within a level (section 6.3):
  the plan is widened before it is deepened, which is the width-first order of Zeng's
  questioning rules (Zeng 2020, section 4.2).
- Two checks are more lenient only when a map exists, because the map made the slips
  frequent and neither changes a judgment: a gap line that the round analyst cites as
  the reason a part is unmet, or next to the findings that meet a part, is dropped
  instead of rejected (such citations alone rejected 19 of 52 first replies in the live
  batches); and an empty field that the conflict checker leaves out counts as empty.

### 19.5 Live checks (2026-11-11)

Five batches of the five development questions (the four fixed questions and "Why did
NASA launch the James Webb Space Telescope in 2018?"), Haiku, ceiling of 6 researchers,
one run per question; records in `local/ebd-extend/`. The step changed between batches,
so they are a development record, not repeats. The comparison runs are those of
2026-11-10 (`local/arch-1110/`).

| Totals over the five questions | Baseline | EBD, `extend` off | EBD, `extend` on (last batch) |
|---|---|---|---|
| Researchers in round 1 | 17 | 8 | 20 |
| Searches in round 1 | 113 | 43 | 114 |
| Researchers used | 17 | 25 | 30 |
| Searches | 113 | 141 | 172 |
| Characters of notes given to the writer | 278,802 | 259,137 | 363,861 |
| Report words | 9,329 | 7,146 | 8,347 |
| Strategy model calls | 10 | 38 | 40 |
| Cost | $1.53 | $2.10 | $2.53 |

- **Round 1.** Searches in round 1 over the five batches: 108, 125, 121, 114, 114.
- **The extension analyst.** Its first reply was accepted in 21 of 25 runs. Three named
  something the request does not, all on the flight question, and were corrected at the
  second attempt. One gave an event seven parts and used the fallback, which then dropped
  that event; an extra part is now cut instead. Every run had a map.
- **The map against the evidence.** In the last batch 84 of 94 assumed parts were
  confirmed, 10 were unfound and none was refuted; every event goal was answered at its
  first attempt.
- **Overwrites.** Two in the full runs: one through the conflict checker, which was too
  broad and led to the rule about one item of a part, and one through the round analyst
  ("disagreements between sources about the definition of EBD", which the findings said
  do not exist). A controlled check with the real model
  (`local/ebd-extend/overwrite-check.ts`): a finding that a planned part does not exist
  removed it through either route, including a part of a goal that was not served in the
  round, and a finding that one item of a part does not apply left the part in place.
- **What the batches changed.** The coverage rule and the rule that a disagreement does
  not hold an event open (batch 1: retries for one unfound part took the last
  researchers, and two detail disagreements held two events of the telescope run);
  keeping a replaced question (batch 2); report points carried by events (batch 3); only
  the events the question needs, and the writer's wording (batch 4).

### 19.6 Open points

- **The fixed EBD question.** The extension prompt names the life cycle and the kinds
  of environment, so on "What is EBD (Environment Based Design)?" the assumed parts can
  echo them. They are still only assumptions that researchers check.
- **More findings bring more recorded disagreements.** Each one becomes a line of
  writer guidance (section 12), so the share of the report spent on disagreements grows
  with the plan. Section 20 limits this with `leanGuidance`.
- **New goals share their quota with settle goals** (`maxNewGoalsPerRound`), so a round
  with several disagreements leaves little room for goals about unfound parts. With
  `focusFollowUp` (section 20) at most one conflict without a client claim gets a
  settle goal in a round.
- **A cancelled goal can still take the question's main point with it** (section 10.2).
  The report-points rule is a prompt rule, and the analyst does not always follow it: in
  two of the five telescope runs the goal that asked why the telescope was launched was
  cancelled with the false launch year, and only an event could carry the purpose.
- **Topic-specific aspects.** The analyst names kinds of things from general knowledge
  and may not name an aspect that only someone who knows the topic expects, such as how
  well a headset shows the room around the wearer. The round analyst can still propose
  a goal for it once a finding names it.
- **Luna is untested** with the extension; all live checks ran on Haiku.

## 20. Critical conflicts, follow-up and writer input (options `focusFollowUp` and `leanGuidance`, built 2026-11-11)

Two changes to what happens after the first round. `focusFollowUp` decides where the
researchers left after a round go. `leanGuidance` decides what the writer is told
besides the notes. Their prompt text was approved on 2026-11-19 as part of the one
approach (section 29). Both stay off by default until the final test of section 29.6, and
with both off nothing sent to a model changes (section 20.5).

### 20.1 Why

**What the runs showed.** The batch of section 19.5 (environment map on), and the 90 EBD
runs recorded under `local/` up to that batch:

| Observation | Measured |
|---|---|
| Disagreements in the writer's guidance | 32 lines over five runs, up to 11 in one run: every recorded conflict got one |
| Report words under a heading about disagreement | 25% (2,096 of 8,347); in the baseline's reports, written from the notes alone, 9% |
| Outline of the run on "What food can help me sleep well?" | One heading, "Where the sources disagree": that request has no synthesis question |
| The report on EBD | Left out the Recursive Object Model, which 12 lines of the notes covered. The planned-contents line named "the evidence gathered for Q1", the notes of one goal out of seven |
| The ten researchers after round 1 | Served 10 goals to settle a disagreement (1 answered), 5 second attempts (2 answered) and 5 goals raised by findings or gaps |
| A necessary request goal, on how food affects sleep | Never served: it waited for a premise check that was sent out again for source dates |
| Second attempts at planned goals with at least half their parts met | 63 in the recorded runs; 11 ended answered; 0.4 parts gained on average |
| Second attempts at settle goals | 26; 1 settled its disagreement |
| Settle goals served | 115; 19 answered, 18 of them at the first attempt |

**What EBD prescribes.**
- **The critical conflict.** EBD does not resolve every conflict it identifies. "A
  critical conflict can be further determined based on the relations among the
  identified design conflicts" (Zeng 2015, p. 13), and solution generation is a loop:
  find the critical environment component, resolve the conflict associated with it,
  update the ROM, repeat (Zeng 2015, Table 6 and Fig. 12).
- **Focus.** EBD guides designers "to collect the necessary and sufficient information
  for a design task" and "to determine the focus at each stage of design" (Zeng 2015,
  p. 15).
- **Neither under- nor over-definition** (Zeng 2020, p. 51) and width first (Zeng 2020,
  section 4.2), as in section 19.

**What the module did.** Every disagreement between sources was treated alike: each got
a settle goal within the limits of section 9, and each got a line in the writer's
guidance. Every partial goal got a second attempt. The round analyst gave each new goal
a need without a definition of "necessary".

### 20.2 Critical conflicts

The conflict checker marks each conflict **critical** or not: a prompt section and one
schema field, `critical`, added when either option is on.

- **Critical:** the answer to the client's question depends on which side is right.
  With one side the report would conclude, recommend or instruct something different
  than with the other.
- **Not critical:** the report's answer is the same with either side: a value that
  differs without changing the conclusion, a date or a count in the background, who
  measured something, a figure for one market or one study.
- **Code overrides the mark upwards only.** A conflict with a client claim at stake
  (`evidence_vs_assumption`, or `source_vs_source` with a claim) is critical whatever
  the checker says. A mark left out counts as not critical, with a warning.
- **Records.** `Conflict.critical` is true, false, or null when the checker was not
  asked. The run viewer shows it.

With `focusFollowUp`:

| Rule | Before |
|---|---|
| Only a critical conflict gets a settle goal. The others are recorded as disputed at once | Every `source_vs_source` and `evidence_vs_assumption` conflict got one, within the limits |
| One critical conflict is settled per round: the first in the checker's list, which is asked to put the one the answer depends on most at the top. A conflict with a client claim at stake is handled first and is not counted | One settle goal per goal at a time, up to the quota of new goals |
| A settle goal is necessary, because its conflict is critical | Necessary only while it decided a claim or a goal waited for it |
| A settle goal gets one attempt. If it does not settle the disagreement, the conflict is disputed | Two attempts |
| A conflict holds a goal, so that the goal waits for the settle goal, only when it decides a claim the goal checks. A goal judged "conflicting" over any other disagreement is judged on its parts | Any open or disputed conflict about the goal held it |

### 20.3 What is searched after a round

**Code rules, with `focusFollowUp`:**
- **Second attempts.** A goal judged partial is searched again only when fewer than half
  of its parts are met. Otherwise it is settled as answered, and the parts still
  missing are logged and not searched again. The same share closes an event of the
  environment map (section 19.3).
- **Premise checks.** A goal that checks client claims is done when each claim has a
  verdict of supported or contradicted and its evidence comes from at least
  `evidenceFloor` independent hosts, whatever its other parts say. An unsettled claim,
  or too few hosts, still gets the second attempt.
- **The evidence floor** guards the client's claims only. For any other number or date
  a second source is a wish about the sources, and no researcher is spent on it.
- **New goals.** At most two new goals of a round are necessary; a further necessary
  proposal becomes completing. A proposal that cites a conflict is rejected: conflicts
  are followed up by their settle goals only.
- **Briefs after round 1.** The researchers go to the necessary goals first, one goal
  per researcher while researchers last. A brief of completing goals is added only for
  a researcher that no necessary goal can use, so a detail never shares the researcher
  sent for a main part. Since 2026-11-18 the goals that settle a disagreement are served
  after the necessary goals that ask for content, with the researchers left (section 25.2).
- **A replaced question** (section 19.2) is not served once the necessary event goals
  that replaced it have been researched.

**The round analyst's prompt section,** added only with the option:
- A part asks for content. A wish about the source is not a part and is not missing: a
  primary source in place of a secondary one, a full text read directly, a page date, a
  second confirmation.
- The verdict on a claim is the analyst's to give from the findings; no finding has to
  state it.
- Conflicts are followed up by code, not by proposals, and a conflict that decides none
  of a goal's claims is no reason to judge the goal "conflicting".
- **Need of a proposal.** Necessary: a main part of the client's question that the
  findings cover only in passing or not at all, so that a reader would call the report
  incomplete without it. Completing: anything that sharpens an answer the findings
  already give.
- Main parts come before details: the analyst compares the findings with what a full
  answer needs before it proposes any detail, and marks at most two proposals
  necessary.

The stop rules of section 11 are unchanged. A main part still uncovered is a necessary
goal, so the run is not complete while one is open.

### 20.4 Writer input with `leanGuidance`

The baseline hands its writer the notes and, at most, one sentence on how the question
was read. The lean guidance is close to that: it keeps what the notes do not show.

| Part of the writer input | Full (section 12) | Lean |
|---|---|---|
| Outline | The synthesis questions, plus "Where the sources disagree" when a conflict is disputed | The synthesis questions only when the request has several; never a section for disagreements |
| Reading of the question | – | "The question was read as: <the analysis's restated request>", only when the question cannot be taken at its word: a premise the evidence does not support, or a term with several meanings |
| Planned contents | Each synthesis question with what the plan said its part must contain | Left out |
| Parts of the subject covered (section 19) | The events with confirmed parts | Left out; the labels of the note sets show them |
| Premises | One line per premise, also when the evidence supports it | Only premises the evidence contradicts, leaves open or could not check. For one left open: "do not present it as established", in place of "state that it is not established" |
| Conflicts | One line per conflict | At most three critical conflicts, a client claim first, each "where it arises in the report, in at most three sentences, not in a section of its own". A conflict whose claim has a verdict is left to the premise line |
| Off-target referents, evidence outside the frame | One line each | The same |
| Defaults, client directives, length limit, goals whose researchers failed | As in section 12 | The same |
| Goals without any reliable source | Named | The same |
| Goals only partly established | Named with the analyst's list of what is missing | Left out: the notes show what was found, the researchers' gap lines show what was not, and the list is written for the next researcher (a source to look for, a conflict ID) |
| Goals cancelled with a contradicted premise | Named as not pursued | Left out: the premise line says what was contradicted |

Every other disagreement is left to the shared writer prompt, which already says to
report notes that disagree and never to pick a side silently. Records made without the
critical mark are read as before this section: a conflict counts as critical when its
settle goal is necessary.

**Rewrites from saved notes.** The five reports of section 19.5 were written again from
the same notes with the lean guidance, one writer call each and no search
(`local/ebd-focus/rewrite.ts`):
- Words under a heading about disagreement fell from 25% to 4%, and the report on EBD
  named the Recursive Object Model 7 times, against 0.
- **The reading line** came from three wordings tried on two questions. With no line
  about the question, the report on "Why did NASA launch the James Webb Space Telescope
  in 2018?" explained the date and left out the mission's purposes. With the synthesis
  question's text ("... explained in plain terms for a general reader?") the report on
  EBD left out the Recursive Object Model again. With the planned contents worded as a
  minimum, 38% of that report was about disagreements, because the plan says "notes any
  disagreement between sources". With the restated request, both reports covered both
  points.
- **Only where needed.** With the reading line on every question, the five reports
  were 16% shorter than without it (6,904 against 8,191 words, one rewrite of each), so
  the line is given only when a premise fails or a term is ambiguous.
- **Length follows the notes.** From the notes of three runs of the batch of section
  20.6, the writer produced reports of the same length with no guidance at all (1,211
  to 1,556 words) as with the lean guidance (1,298 to 1,628).

### 20.5 What stays the same

- With both options off, the prompts and tool schemas sent to the conflict checker and
  the round analyst are the earlier ones character for character, with and without an
  environment map. A snapshot taken before the work is compared by
  `local/ebd-focus/prompt-invariant.ts`, and the tests check it (`focus.test.ts`).
- The request analysis, the extension analyst, the researchers' briefs and the material
  given to the writer are unchanged by either option.
- The shared writer prompt belongs to the platform and is unchanged.

### 20.6 Live checks (2026-11-11)

Records in `local/ebd-focus/`. All on Haiku with a ceiling of 6 researchers.

- **Replays.** Round 1 of each run of section 19.5 was put through `observe` again with
  the real model: the saved plan and notes, the new conflict checker and round analyst,
  no search (`replay.ts`, four passes over the five runs). They showed, and the rules
  above then fixed: the analyst asking again for disagreements marked as details;
  every new goal marked necessary; a premise check sent out again with its claim
  already judged supported; two necessary goals sharing a researcher while a detail had
  one to itself; a goal with every part met waiting for a disagreement about one food.
- **One live run,** then **one live batch** of the five development questions, with
  `extend`, `focusFollowUp` and `leanGuidance` on.

| Totals over the five questions | `extend` only (section 19.5) | With both options |
|---|---|---|
| Researchers in round 1 | 20 | 19 |
| Searches in round 1 | 114 | 106 |
| Researchers used | 30 | 26 |
| Searches | 172 | 136 |
| Strategy model calls | 40 | 32 |
| Characters of notes given to the writer | 363,861 | 311,451 |
| Conflicts recorded | 32 | 40, of which 10 critical |
| Settle goals served | 9, of which 1 answered | 3, of which 2 answered |
| Other goals searched twice | 5 | 1 |
| Report words | 8,347 | 7,448 |
| Report words under a heading about disagreement | 25% | 5% |
| Cost | $2.53 | $1.97 |

- **The reports counted here** were written again from the batch's notes
  (`local/ebd-focus/b1-final/`), because three writer rules changed after the batch
  started: the reading line only where needed, at most three sentences for a critical
  conflict, and no line for cancelled goals. The batch's own reports had 7,336 words.
  Headings are counted by keyword, and one of the headings counted in the 5% is about
  EBD's own concept of conflict.
- **Changed after these reports.** The wording for a premise left open (section 20.4),
  checked with one rewrite of the report on EBD, and one clause of the round analyst's
  section, reworded to say that code settles one conflict per round.
- **What the live runs changed.**
  - One critical conflict settled per round: in the first live run two settle goals and
    a new goal shared one researcher, and none of the three was answered. In the batch,
    the settle goal on whether a nonstop flight exists settled its conflict, which no
    earlier run had done.
  - The writer line for a critical conflict asks for "the source the notes cite" (the
    writer had invented an address for a publisher that the notes cite without a link)
    and for at most three sentences (a disagreement about one battery figure had got a
    section of its own).
  - The reading line only where needed and no line for cancelled goals (section 20.4):
    in the batch that line named the question about NASA's reasons as not pursued,
    although an event goal had researched them.
  - The wording for a premise left open: the report on EBD had opened by doubting that
    EBD stands for Environment Based Design.
- **Checks.** With both options off, nothing sent to a model changed (snapshot). The
  run viewer shows the critical mark (`viewer-check.ts`). `npm run check-strategy`
  passed live with the final text: with the default options on the EBD question (a map,
  no critical mark asked), and with both options on for the flight question (outputs
  in `local/ebd-focus/check-default.out` and `check-focus.out`).

### 20.7 Open points

- **A run can end with researchers unspent.** When the plan is answered after round 1
  and the round analyst proposes no further main part, the run stops: two of the five
  runs of the batch used 4 of 6 researchers. Whether a main part is still thin then
  rests on one judgment of the round analyst, which varies: in the replays the same
  notes gave a goal on how the headsets track hands and eyes once as necessary and once
  as completing.
- **Which conflicts are critical varies** between runs of one question: 1 to 4 of the
  4 to 9 conflicts of the sleep question in the replays and live runs.
- **Report length follows the notes** (section 20.4): the reports are shorter than the
  baseline's (7,448 against 9,329 words) with either guidance.
- **A premise the question itself spells out** can still be left open by the round
  analyst ("EBD stands for Environment Based Design" in the batch), and the report then
  treats it with caution. Premise checks on obvious premises are on the deferred list of
  2026-11-10.
- **The cancel rule of section 10.2** again dropped the goal on NASA's reasons with the
  false launch year; an event goal carried the reasons.
- **The conflict checker's second reply,** after a rejected first one, can list fewer
  conflicts or none: the valid items of the first reply are not kept.
- **Luna is untested** with either option.

## 21. Part questions (option `partQuestions`, built 2026-11-18)

Off by default until the behaviour design lead approves the brief text. With the option
off, every brief is the earlier one (the tests check this).

### 21.1 Why

**What the runs showed.** The batch of section 20.6 against the baseline runs of
2026-11-10, per researcher:

| Per researcher | Baseline | EBD (section 20.6) |
|---|---|---|
| Key questions in the brief | 3.9 | 1.3 |
| Searches | 6.6 | 5.2 |
| Findings in the notes | 36 | 26 |
| Characters of notes | 16,400 | 11,800 |

- An EBD researcher with one key question made 4.5 searches on average; one with two or
  three made 7.1. The shared researcher prompt tells a researcher to stop when the key
  questions are answered.
- The baseline's planner gives each researcher 3 to 6 specific key questions. An EBD
  brief asked one compound question for a whole life-cycle step and listed the step's
  parts in the instructions.

**What EBD prescribes.** Every object of the environment that is not yet defined gets
its own question (Wang & Zeng 2009, Table 4; Zeng 2020, Table 10). The parts of an event
are such objects. Section 19 turned each event into a question; the parts stayed a list
inside one question.

### 21.2 The brief

For a goal of the environment map that is **asked by part**:

| Field | With `partQuestions` | Before |
|---|---|---|
| `keyQuestions` | One per planned part still open: `[Q5] <event name>: <part>`, for example `[Q5] Driving in the cold: cabin heating system and its energy use` | `[Q5] <the event's question>` |
| `objective` | The event's question (a brief with one goal), as before | The same |
| `instructions` | `For [Q5], the question is: <the event's question>` followed by `PART_QUESTIONS_INSTRUCTION` | `For [Q5], look for what the sources report on: <parts>.` followed by `PLANNED_PARTS_INSTRUCTION` |

`PART_QUESTIONS_INSTRUCTION` says what `PLANNED_PARTS_INSTRUCTION` says, worded for parts
that are key questions: the parts are expectations, not facts; the researcher reports
what the sources say about each, says so under the key question when a part does not
apply, and puts any other main point under the key question it is closest to.

- **At most six key questions in a brief** (`MAX_PART_QUESTIONS`): the most the
  baseline's planner gave one researcher, and the most parts an event may have. Goals
  are taken in rank order and asked by part while the brief stays within six; every
  other goal keeps its one question.
- **Necessary goals first.** In a brief with a necessary goal, only necessary goals are
  asked by part. A completing goal that shares the brief keeps one question, and it
  waits for a later round when it keeps the necessary goal from being asked by part
  (`fitBrief`).
- **Second attempts** ask only the parts still open.
- **Goals without planned parts** (request goals, premise checks, settle goals and goals
  raised by findings) keep their brief.
- **Reading the notes** (section 8). A notes section maps to its goal by the ID in its
  heading, as before. A section without an ID maps to the goal of the key question at
  its position when the notes have one section per key question.

### 21.3 A researcher for each necessary goal

`pack` groups goals by object, and every event goal carries the same objects, so three
events can share a brief while a completing goal on another object opens a brief of its
own. In 9 of the 44 plans recorded up to 2026-11-18, two necessary life-cycle steps
shared a researcher in round 1 while a brief of completing goals had one to itself.

With `partQuestions`, `spread` frees a researcher in that case: the smallest brief made
of completing goals only gives up its researcher, and its goals move to another brief of
completing goals, or else to the brief that asks the fewest key questions. Recomputed on
the 44 plans without a model call (`local/ebd-parts/alloc.ts`): 0 plans with the flaw,
and plans in which two necessary goals share a researcher fall from 14 to 7 (those have
more necessary goals than researchers in a round).

### 21.4 What stays the same

- The request analysis, the extension analyst, the conflict checker, the round analyst
  and the writer input are unchanged. The round analyst judges the planned parts from
  the same evidence lines.
- The researcher prompt belongs to the platform and is unchanged; the option changes
  only the fields of the brief.

### 21.5 Live check (2026-11-18)

A same-day A/B on identical plans (`local/ebd-parts/ab.ts`): the plan of each question
was made once, and round 1 was researched twice, with the earlier briefs and with
`partQuestions`. A brief that is the same in both arms was researched once and shared.
Three questions (the fixed EBD question, the headset comparison, the sleep question),
Haiku, 12 researchers in each arm, 21 researcher runs in all.

| Per researcher, the 9 briefs that differ | Earlier briefs | Part questions |
|---|---|---|
| Key questions | 1.4 | 4.7 |
| Searches | 6.1 | 6.4 |
| Page reads | 0.8 | 0.9 |
| Sections in the notes | 1.4 | 4.1 |
| Findings | 27.7 | 37.1 |
| Cited pages | 25.9 | 30.3 |
| Characters of notes | 13,500 | 17,000 |
| Cost | $0.08 | $0.09 |

| Round 1 of the three questions | Earlier briefs | Part questions |
|---|---|---|
| Findings | 329 | 414 |
| Findings on the necessary life-cycle steps | 124 | 219 |
| Planned parts confirmed by the round analyst | 42 of 50 | 49 of 50 |
| Conflicts recorded | 18 | 18 |
| New goals, settle goals included | 3 | 3 |
| Characters of notes given to the writer | 164,000 | 195,400 |
| Report words (written from round 1 alone) | 4,508 | 4,657 |
| Pages cited in the reports | 110 | 118 |

- **More findings, hardly more searches.** The researchers searched about as often and
  reported a third more findings, one section per part.
- **The effort moves to the necessary steps.** In the headset plan of that day the two
  necessary steps "Buying" and "Hardware" shared a researcher while a replaced overview
  question had one to itself (49 findings); with the option each step had a researcher
  (34 and 47 findings, against 31 for both).
- **Fewer follow-up goals for gaps.** With the earlier briefs the headset run raised two
  necessary goals for parts round 1 had missed (the app library, where one headset is
  sold); with part questions round 1 confirmed all 19 parts and the run was complete.
- **The reports did not grow.** The writer produced reports of the same length from the
  larger notes. Whether they are better was not judged.
- **Checks.** Every conflict-checker and round-analyst reply in the part arm was accepted
  at the first attempt. The notes sections mapped by ID or by key-question order; in one
  brief with a single goal, six sections without IDs mapped to that goal.

### 21.6 Open points

- **One run per brief.** The A/B has 9 pairs of briefs on 3 questions. On the fixed EBD
  question two of three researchers wrote one section with sub-headings instead of one
  per key question, and reported no more findings than before.
- **The report.** More findings did not make a longer report. No judge compared the two
  arms' reports.
- **Goals without parts** still go out as one compound question. A premise check that
  also asks for the subject's definition is such a goal (section 22).
- **Run end to end** only together with `completeMap`, `focusFollowUp` and
  `leanGuidance` (section 23). Luna is untested.

## 22. A complete map (option `completeMap`, built 2026-11-18)

A variant of the extension analyst's prompt (section 19.2). Off by default until the
behaviour design lead approves the text; with the option off the prompt is the one
accepted on 2026-11-11, character for character (the tests check this).

### 22.1 Why

**What the plans showed.** The plans of the recorded runs and dry runs with an
environment map (44, of which 8 to 10 for each of the five development questions):

| Observation | Measured |
|---|---|
| The fixed EBD question: an event for what the method consists of | In 5 of 10 plans; in the others one planned question carried it |
| The sleep question: an event for the foods that help | In 3 of 9 plans |
| The sleep question: an event for products sold for sleep, their prices or where to get them | In 5 of 9 plans |
| The flight question, plan of 2026-11-18 | No event for travel documents or for booking; events for on-time rates and for the weather on arrival |
| The sleep run of 2026-11-11 | The two planned questions with the core of the answer shared one researcher (25 findings); a planned question on how sleep is measured had a researcher to itself (30 findings) |

- **The cause.** Step 5 of the prompt tells the analyst not to write an event that
  repeats a planned question. The core of the answer then stays in a planned question,
  which goes to one researcher as one compound question, while the events around it are
  researched part by part.
- **The writer** is told to use every set of notes, so a goal on a side topic takes
  space in the report (the judge of 2026-11-11 named melatonin products and sleep
  measures in the sleep report).

**What EBD prescribes.** The answer to "what is the subject?" through its life cycle
is the environment system of the problem, and it must hold the necessary components
(Zeng 2020, p. 51). The questions asked from the request's wording are the first half;
in the papers' cases most questions come from the life cycle (Wang & Zeng 2009,
pp. 293 to 294).

### 22.2 The change

Three passages of the prompt are reworded (`RELEVANCE_NOW`, `PLANNED_NOW` and
`EXAMPLE_NOW` in `extension.ts`, each with its proposed text), and the worked example
replaces both of its planned questions.

- **The most direct event.** One event answers the client's question most directly; it
  must be there, and it is necessary.
- **Relevance.** Any other event is kept only if what happens in it could change the
  answer, or if it is a step the client must take to do what they ask. A question about
  what a thing does needs neither where it is sold nor what it costs.
- **The events carry the answer on their own.** Every main part of a full answer is an
  event or a part of one, also when a planned question asks for it.
- **Defining questions.** A planned question that only asks what a word of the request
  means, or how something is measured, becomes one part of the event that depends on
  it, not an event of its own.
- **Replaced questions.** The events replace every planned question that checks no
  client assumption and whose sufficient answer they carry in full. A planned question
  that checks a client assumption always stays, for its verdict.

The code is unchanged: a replaced question becomes a completing goal, and the goals
that waited for it wait for the necessary event goals (section 19.2).

### 22.3 Check without search (2026-11-18)

The extension step was run again on the request analysis of every recorded run of the
five development questions (100 analyses), with both prompts on the same day
(`local/ebd-parts/plans.ts`). A small model call (Haiku) then listed, for each item of
the question's coverage checklist (`experiments/checklists.md`), the plan elements that
ask for it. It judges the plan, not a report.

| 100 plans with each prompt | Accepted prompt | Variant |
|---|---|---|
| Checklist items asked by some goal of the plan | 83% | 84% |
| Checklist items asked by an event or one of its parts | 72% | 82% |
| Checklist items asked by a necessary goal | 71% | 66% |
| Events with no checklist item | 0.34 per plan | 0.14 per plan |
| Planned questions replaced | 0.56 per plan | 0.90 per plan |
| Necessary planned questions left | 1.16 per plan | 0.88 per plan |

| The same, each question weighted equally | Accepted prompt | Variant |
|---|---|---|
| Checklist items asked by an event: share of items | 75% | 86% |
| Agreement between the plans of one question on those items | 84% | 93% |
| Items asked by an event in some plans and not in others (20% to 80% of the plans), of 41 | 14 | 5 |

- **The events now carry what the plan asks.** Nearly every item that the plan asks for
  is asked by an event, so it is researched part by part (section 21), and the plans of
  one question agree more on which items those are.
- **Side events.** On the sleep question an event about products, prices or places of
  sale appeared in 5 of 12 plans with the accepted prompt and in none with the variant.
  On the flight question the events outside the checklist fell from 5 to 1 in 21 plans.
- **Necessary planned questions.** With the variant every planned question that is left
  necessary checks a client assumption (with the accepted prompt 1.3 per sleep plan and
  0.6 per telescope plan checked none).
- **Fewer items under a necessary goal.** What a replaced question carried now sits in
  events, and the analyst marks some of them completing.
- **The defining-questions sentence** was added after a first scoring of the variant
  (83% of the items asked by an event), because 4 of 12 sleep plans had made an event of
  how sleep is measured. With the final wording, scored above: 2 of 12, by keyword.
- **The scoring varies** by a point or two between two passes over the same plans.

### 22.4 Open points

- **Aspects only the topic's sources name** are in no plan with either prompt: how EBD
  identifies conflicts, its theoretical basis and its life-cycle view (missed by 81% to
  100% of the plans), and dietary patterns for the sleep question (83% to 100%). The
  analyst may not name them (section 19.2), so they can come only from findings: a
  researcher's "other main points", or a goal the round analyst proposes.
- **A premise check that also asks for the subject** stays necessary and overlaps the
  event that now carries the subject. It costs one researcher of round 1.
- **Necessary and completing marks** vary between plans of one question.
- **One reply in 300** sent its events as malformed JSON text twice, and that plan had
  no map.
- **Run with search** only together with the other options (section 23); Luna is
  untested.

### 22.5 Plans from the request alone (idea of 2026-11-18, tested on plans only)

**The idea** (behaviour design lead, 2026-11-18): decompose the request into its
concepts first, the product at the centre and the environment around it, and let the
researchers work on those; the wording of the request should not be taken apart first,
because that limits what the model associates with the question.

**Where the module stands.** The request analysis does not work word by word: since
revision 2 its objects are phrases (4 for the sleep question, 2 for the fixed EBD
question; section 5.5). But it still plans from the wording: one question for each
phrase that needs one and one for each presupposed claim, by the templates of section
5.6. The decomposition into a centre and its environment is the second step
(section 19), and `completeMap` makes its events the plan.

**The test.** The extension analyst was given the bare request: no objects from the
wording, no assumption and no planned question (`plans.ts direct`, 12 plans for each of
the five questions with each wording of the prompt, no search). Scored as in section
22.3, each question weighted equally:

| | Analysis of the wording, then extension | | The request alone | |
|---|---|---|---|---|
| Extension prompt | Accepted | Variant | Accepted | Variant |
| Checklist items asked by some goal | 87% | 88% | 85% | 88% |
| Agreement between plans on those items | 95% | 95% | 91% | 95% |
| Checklist items asked by an event | 75% | 86% | 85% | 88% |
| Items asked by an event in some plans only, of 41 | 14 | 5 | 8 | 4 |
| Model tokens for the plan, in and out | 22,500 and 7,400 | 23,000 and 7,100 | 4,900 and 2,300 | 4,800 and 2,100 |
| Seconds | about 30 | about 30 | about 10 | about 10 |

- **As complete and as stable** as the two-step plan with the variant, for a third of
  the output tokens and a third of the time. On the fixed EBD question all 12 plans
  made with the accepted wording had the same four events (origin, what it consists
  of, application, assessment).
- **What the plans lost** is what the analysis of the wording supplies:
  - the check of a presupposed claim. Other meanings of the acronym "EBD" were asked
    for in 0% to 8% of the plans, against 75% to 81%;
  - the client's unstated details. Naming the nationality and dates as assumptions
    was asked for in 0% to 8% of the flight plans, against 62% to 67%;
  - the question's own "why". 2 of 12 telescope plans with each wording had no event
    for the mission's purpose, against none.
- **Model knowledge in the plan.** Several telescope plans named events such as "Delays
  from 2018 to launch": the analyst used what it knows about the subject, which the
  request analysis never does.

Not decided and not built. The test covers the plan only: no premise list was produced,
and no search or report used these plans.

## 23. End-to-end check with every option (2026-11-18)

The five development questions with `extend`, `completeMap`, `partQuestions`,
`focusFollowUp` and `leanGuidance`, one run each, Haiku, ceiling of 6 researchers; and
the baseline on the same day. Records in `local/ebd-parts/` (`ebd-parts-one-*`,
`ebd-parts-batch-*`, `baseline-1118-*`). The options are still off by default: their
text awaits approval.

### 23.1 The runs

| Totals over the five questions | Baseline, 11-10 | Baseline, 11-18 | EBD, 11-11 (section 20.6) | EBD, 11-18 |
|---|---|---|---|---|
| Researchers used | 17 | 16 | 26 | 27 |
| Researchers in round 1 | 17 | 16 | 19 | 20 |
| Searches | 113 | 112 | 136 | 159 |
| Findings in the notes | 617 | 639 | 677 | 866 |
| Characters of notes | 278,800 | 276,000 | 311,500 | 396,900 |
| Report words | 9,329 | 8,201 | 7,336 | 7,686 |
| Pages cited in the reports | 246 | 216 | 182 | 223 |
| Strategy model calls | 10 | 10 | 32 | 36 |
| Seconds | 563 | 563 | 1,190 | 1,391 |
| Cost | $1.53 | $1.52 | $1.97 | $2.34 |

- Every run ended with status ok and no recorded problem. On the sleep question each
  necessary step had its own researcher, 15 of 15 planned parts of the necessary steps
  were confirmed in round 1, and round 2 served one critical conflict and one goal
  raised by a gap (how much of the trial doses ordinary foods supply).
- The run on the fixed EBD question was complete after round 1 with 4 of 6 researchers,
  as on 11-11.
- `npm run check-strategy` passed live with the five options on the headset question
  (all 11 required checks; `local/ebd-parts/check-parts.out`).

### 23.2 The judge pass

The informal judge of the earlier passes (Claude Opus 5.5, the prompts and checklists of
`local/arch-1110/judge/`), one pass of 30 calls (`local/ebd-parts/judge.ts`, 310,600
input tokens): checklist coverage of the new EBD reports and of the new baseline
reports, and each new EBD report against each of the two baseline samples in both
orders, blind.

| Checklist coverage, 41 items | Score |
|---|---|
| Baseline, 11-10 (scored on 11-10) | 36.5 (89%) |
| Baseline, 11-18 | 35.5 (87%) |
| EBD, 11-10 | 32.5 (79%) |
| EBD, 11-11 (section 20.6) | 36.5 (89%) |
| EBD, 11-18 | 38.5 (94%) |

| Blind pairs, overall verdict | EBD | Tie | Baseline |
|---|---|---|---|
| EBD 11-11 against the baseline reports of 11-10 (10 judgments) | 2 | 0 | 8 |
| EBD 11-18 against the same baseline reports (10 judgments) | 5 | 1 | 4 |
| EBD 11-18 against the baseline reports of 11-18 (10 judgments) | 7 | 0 | 3 |

| EBD 11-18, the 20 judgments by criterion | EBD | Tie | Baseline |
|---|---|---|---|
| Coverage | 7 | 5 | 8 |
| Support | 8 | 7 | 5 |
| Handling of disagreements and false premises | 7 | 10 | 3 |
| Usefulness | 12 | 2 | 6 |
| Overall | 12 | 1 | 7 |

| EBD 11-18 by question, four judgments each | EBD | Tie | Baseline |
|---|---|---|---|
| The fixed EBD question | 2 | 0 | 2 |
| Headset comparison | 3 | 0 | 1 |
| Flight | 1 | 0 | 3 |
| Sleep | 3 | 1 | 0 |
| Telescope (false premise) | 3 | 0 | 1 |

**How far this goes.**
- One run of each question and one judge. Of the 10 pairs of a question with a baseline
  sample, the two orders agreed in 4: three for EBD, one for the baseline.
- The judge preferred the report shown second in 14 of the 20 judgments (5 of 10 in the
  pass of 11-11), so a single order says little.
- The questions are the ones the options were developed on.
- EBD used 69% more researchers, 54% more money and 2.5 times the time of the baseline.
  The judge does not see cost.

**What the judge named.**
- For EBD: every checklist item of the sleep question, with cautions and the point at
  which to see a clinician; the mission's purpose and the launch operator in the
  telescope report; careful handling of the disputed prices, battery figures and
  trial results; no wrong statement against two in the baseline reports of 11-18.
- Against EBD, the flight report: it assumed a Chinese passport without naming other
  travellers, said that every route enters Canada at one of two airports against its
  own list of routes, and spent space on a cargo airport and airline reviews.
- Against EBD, the fixed EBD question: a shorter report (1,113 words) without the
  life-cycle view and the two types of conflict, which the baseline report of 11-10
  had; the baseline report of 11-18 explained the procedure and the acronym's other
  meanings in more detail.
- Against EBD, the headset report in one order: no processors, little on availability.

### 23.3 Open points

- **One nationality.** The flight plan asked for "a traveller from China", and both
  follow-up goals asked about Chinese passport holders. The extension prompt has no
  rule to cover the main cases of what the client did not state, which the request
  analysis and the round analyst have. Counted on the saved flight plans, an event names
  one nationality in 9 of 21 with the accepted prompt and in 13 of 21 with the variant.
- **Researchers unspent on a short answer.** The run on the fixed EBD question stopped
  complete with 4 of 6 researchers and gave the shortest report.
- **Follow-up on a side step.** In the headset run a completing step about support and
  warranty was searched again in the extra round, and a necessary goal raised from its
  notes took the last researcher (one such goal in the ten recorded runs with
  `focusFollowUp`).
- **A place name read as ambiguous.** The request analysis of the flight run asked
  which Montreal is meant, and the report mentioned another airport.
- **Cost.** No run with the baseline's number of researchers was made.
- **The evaluation** needs repeated runs and questions that were not used for
  development before it can show a difference.
- Section 24 tests the options, and the first three points above, on questions that
  were not used for development.

## 24. Test on questions the strategy was not developed on (2026-11-18)

The options of sections 20 to 22 were developed on five questions and judged on the
same five (section 23). This section tests them on questions that were never used:
whether what the options gained carries over, and whether a rule written after one
question's failure holds for other requests. Records, scripts and results are in
`local/ebd-heldout/`. No option changed its default.

### 24.1 The questions

| Set | Questions | Where they come from | Checklist |
|---|---|---|---|
| Real | 14 search-engine queries of real users | A random draw with a fixed seed (20261118) from the test split of the public dataset Researchy Questions (Rosset et al. 2024), so nobody chose them | The dataset's own top-level sub-questions for each query (written by GPT-4 for the dataset's authors), 3 to 7 items |
| Designed | 12 questions, one for each kind of request that the five questions and the draw lack | Written for this test | Written from the question alone before any run, 3 to 8 items |
| Probes | 5 questions of the flight question's pattern (the answer depends on who the client is, and a place is named) | Written for the main-cases rule (section 24.6) | None |

The designed kinds: a procedure with details not stated (registering a trademark), a
quantity (people without electricity), an abbreviation with several meanings and no
gloss ("SLA"), a false premise of another kind (a prize awarded for the wrong work), a
true premise with a date, a request with directives on format and sources, one simple
fact, how a technology works, a decision that depends on place, time and the person, the
sleep question's wording with another subject (exercises for back pain), a person, and
a technical choice between two options.

Each set was split by position before any run, not by content:

- **Check questions** (6 real, 6 designed): used first, and only at plan level, without
  search. A problem found here may lead to a change.
- **Sealed questions** (6 real, 6 designed): not looked at until everything else was
  frozen, then run once end to end, with the configuration of section 23 unchanged.
- Two real queries are reserves. A larger draw with the same seed starts with the same
  14 queries, so draws 15 onward give the next sealed set.

The sealed questions: six real queries ("does population control lead to better child
quality? evidence from china's one-child policy enforcement", "how did industrial
revolution affect people", "why was slavery important", "why disability inclusion
matters", "how did the internet spread to other areas", "how can social science solve
social problems") and six designed ones (the quantity, the false premise, the
directives, the technology, the back-pain question and the technical choice). The full
list with the checklists is `local/ebd-heldout/questions.json`.

### 24.2 The prompt texts, checked for traces of the five questions

- No prompt names a development question, its subject or a name from it. The worked
  examples use other subjects (car prices and tariffs, an electric car, a vaccine, a
  licence).
- Four passages were written after a failure on one development question:
  1. the example in the `completeMap` wording that a question about what a thing does
     needs neither where it is sold nor what it costs (sleep question);
  2. in the follow-up section of the round analyst, "a price or a place of sale that the
     client did not ask about" as an example of a detail (sleep question);
  3. in the same section, the sentence on a name or an abbreviation (fixed EBD question);
  4. in the conflict checker's section on critical conflicts, the four cases after "This
     covers", which match the kinds of the four fixed questions.
- Passage 1 was tested by removing it (section 24.3): the result on the five questions
  does not depend on it. Passages 2 to 4 are worded as general rules and cannot be tested
  without search; the sealed runs give what there is on them (section 24.5).
- The allow-list of the name check in the request analysis (`GENERIC` in
  `request/checks.ts`: units and abbreviations of computer hardware) is a list grown from
  the questions of Lab 3. It is older than these options and is treated in section 24.3.

### 24.3 Plans on the check questions (no search)

The method of section 22.3: six request analyses of each check question (72), the
extension step with the accepted prompt and with the `completeMap` wording on each, and
a small model call that says which plan elements ask for which checklist item. The five
development questions were scored again the same evening with the same script (their 100
saved analyses). The scorer is itself a model call: scoring the same plans twice moved
the averages by 1 to 2 points.

| Measure, accepted prompt → `completeMap` wording | Five development questions (100 plans each) | Twelve new questions (72 plans each) |
|---|---|---|
| Checklist items asked by a life-cycle step | 76% → 86% | 82% → 90% |
| The same, difference on the same analyses, with a 95% interval | +9.6 points (6.2 to 13.0) | +7.7 points (2.8 to 13.0) |
| Agreement between plans of one question | 85% → 93% | 85% → 93% |
| Items asked in 20% to 80% of the plans | 14 → 6 of 41 | 13 → 7 of 61 |
| Items asked by any goal of the plan | 88% → 88% | 95% → 94% |
| Items asked in round 1 (ceiling of 6) | 86% → 88% | 92% → 92% |
| Events that match no checklist item, per plan | 0.33 → 0.13 | 0.56 → 0.24 |

- **The gain of the wording carries over.** More of the answer is asked by a life-cycle
  step, and the plans of one question agree more, by about as much on the new questions
  as on the five. The gain is larger on the real queries (75% → 88%) than on the designed
  questions (90% → 92%), whose plans were already close to their checklists.
- **The example written for the sleep question is not what carries the result.** Without
  it, the five development questions score the same (86% and 87% by step; difference 0.0
  points, interval −2.4 to +2.8), the sleep question included. On the new questions the
  text with the example scores 3 points higher, within the noise (interval −6.9 to +0.3).
  The text stays as built.
- **Without the stricter relevance rule** (the direct-answer sentence added to the
  accepted rule) the plans have more events and more of them off the list, and score 1.6
  to 2.4 points lower on both sets. The rule stays.
- **Part questions and the allocation rule hold.** Over all 569 round-1 briefs of the
  144 plans, no brief asks more than 6 key questions, and every necessary goal that is
  ready has a researcher in round 1.

What the new questions showed that the five did not:

- **The first reply of the extension analyst is rejected twice as often**: 25% to 28% of
  the plans against 12% to 16% on the five questions, and 3 of 72 plans per wording fell
  back to their valid events (none of 100 on the five). Nearly every rejection is the
  rule against names that the request does not contain.
- **That rule meets two different things on new questions.** On questions about history
  and people the analyst writes names it knows (a county, a college, co-workers), which
  the rule is there to stop. And the check takes capitalised common words for names:
  "X-ray" (19 times), "IT", "Celsius", "Fahrenheit", "Black". The second kind is a defect
  of the check. Adding the words found to its allow-list would repeat how that list was
  made; the check needs a rule that does not depend on a word list. Open.
- **A request analysis can leave nothing usable.** In 1 of 102 analyses of new questions
  both replies were rejected for a text over the 400-character limit, the only search
  question was dropped, and `init` threw. The skeleton then runs the whole step again, up
  to three times (section 5.3), so a run ends without a report only when every attempt
  fails. 9 of the 102 fell back to a reduced plan, 6 of them for the same length limit.
  Changed in section 24.4.
- **One simple fact gets a full plan.** The boiling-point question gets 2 to 3 events and
  4 researchers in round 1. The plan is sound and larger than the question needs.

### 24.4 Changes made after the check questions (code only, no prompt text)

Both concern the fallback of the request analysis (section 5.3, step 5) and apply with
any options.

- **A question whose only fault is its length is kept.** After the last failed attempt
  the fallback dropped every question an error pointed to. A question whose only error is
  a text or done_when over the limit is now kept with that text cut at the limit, after
  its last full sentence or its last whole word (`salvage`, `cutAt` in
  `request/checks.ts`). A question with any other error is dropped as before.
- **A run no longer ends for want of a usable analysis.** The first time an analysis
  leaves nothing usable, `init` throws as before and the skeleton runs the step again.
  When it happens a second time in the same run, `init` plans the request itself as one
  search question and one synthesis question (`minimalAnalysis`): no model of the
  request, no check of its assumptions. The record says so (`init.stopReason` is
  "minimal plan", and a line under `problems`), and the problem extension builds its
  events on it as on any analysis.
- Tests: `request/checks.test.ts` (three) and `strategy.test.ts` (one).
- Live: 31 further analyses with the changed code, none failed; 6 fell back, 5 of them
  with a length fault, and in four of these a question that would have been dropped was
  kept with its text cut. The minimal plan has not occurred live; only its test
  exercises it.
- `npm run check-strategy` passed live with the changed code and the five options on the
  sleep question (all 11 required checks; `local/ebd-heldout/check-after-fallback.out`).

### 24.5 The sealed questions, end to end

The configuration of section 23 (`extend`, `completeMap`, `partQuestions`,
`focusFollowUp`, `leanGuidance`; the code as it stood before section 24.4), the baseline,
and on the six real queries also EBD with its default options. One run per cell, Haiku,
ceiling of 6 researchers, the same evening. All 30 runs ended with status ok.

| Totals | Baseline (12 questions) | EBD, five options (12) | EBD, default options (6 real) | EBD, five options (the same 6) |
|---|---|---|---|---|
| Researchers used | 43 | 68 | 36 | 35 |
| Searches | 310 | 407 | 243 | 233 |
| Findings in the notes | not counted | 2,458 | 1,305 | 1,435 |
| Findings per researcher | not counted | 36.1 | 36.2 | 41.0 |
| Report words | 21,772 | 18,704 | 10,949 | 9,735 |
| Seconds | 1,530 | 3,627 | 2,093 | 1,992 |
| Cost | $4.31 | $6.29 | $3.52 | $3.44 |

- EBD with the five options ended 6 runs complete and 6 at the ceiling. No run stopped
  early with researchers to spare: 4 researchers once, 5 twice, 6 nine times.
- Recorded problems in 5 of its 12 runs, none of which ended a run: one request analysis
  and one extension fell back, one conflict check fell back, and in two runs some note
  sections carried no goal ID and were assigned to every goal of their brief.
- The false premise was contradicted and corrected in the first sentence of the report,
  by the baseline too. The directives were recognised (a table; sources from 2023), and
  both reports have tables. On the quantity question the one conflict marked critical was
  the disagreement over the figure asked for, so the mark does not depend on the four
  cases the prompt lists (section 24.2, passage 4).

**The judge pass.** The judge and the two instructions of section 23.2, one pass of 54
calls (`local/ebd-heldout/judge.ts`; 477,800 input and 35,700 output tokens): checklist
coverage of all 30 reports, and each EBD report with the five options against the
baseline report of its question in both orders, blind.

| Checklist coverage | Baseline | EBD, five options | EBD, default options |
|---|---|---|---|
| Six real queries (25 items) | 18.0 (72%) | 20.5 (82%) | 21.0 (84%) |
| Six designed questions (36 items) | 34.0 (94%) | 34.0 (94%) | not run |
| All twelve (61 items) | 52.0 (85%) | 54.5 (89%) | |
| Statements the judge marked wrong | 2 | 5 | 1 (six questions) |

| Blind pairs, EBD with the five options against the baseline | EBD | Tie | Baseline |
|---|---|---|---|
| Overall, six real queries (12 judgments) | 4 | 0 | 8 |
| Overall, six designed questions (12 judgments) | 4 | 0 | 8 |
| Overall, all twelve (24 judgments) | 8 | 0 | 16 |
| Questions on which both orders agree (12) | 3 | 2 undecided | 7 |
| Coverage | 7 | 2 | 15 |
| Support | 2 | 16 | 6 |
| Handling of disagreements and false premises | 7 | 13 | 4 |
| Usefulness | 6 | 2 | 16 |

| The same configuration on the two kinds of question | Five development questions (section 23) | Twelve new questions |
|---|---|---|
| Checklist coverage, EBD against the baseline of the same day | 94% against 87% | 89% against 85% |
| Blind judgments against the baseline of the same day, EBD : tie : baseline | 7 : 0 : 3 | 8 : 0 : 16 |
| Statements marked wrong, EBD against baseline | 0 against 2 | 5 against 2 |
| Researchers, cost and time against the baseline | +69%, +54%, 2.5 times | +58%, +46%, 2.4 times |

- **The result against the baseline did not carry over.** On the development questions
  the judge preferred the EBD report in 7 of 10 judgments; on the new questions in 8 of
  24. EBD won both orders on 3 questions (how the internet spread, how HTTPS works, the
  database choice) and the baseline on 7.
- **The five options did not change the checklist coverage on the new questions**: 82%
  with them and 84% without, on the six real queries. With them a researcher wrote 13%
  more findings (41.0 against 36.2); on the development questions the same-plan
  comparison of section 21.5 gave 34% more. The reports were 11% shorter.
- **What the judge named against EBD** is the same from question to question:
  - a main part of the answer is missing that the baseline covers: politics, protest and
    culture for the industrial revolution; how slavery ended and what it left; how to do
    the exercises and what to avoid; the outlook for electricity access; the lecture
    behind the belief about the prize;
  - space spent beside the question: health studies in the electricity report, tests of
    relativity in the prize report;
  - the report framed around a doubt: the back-pain report leads with whether exercise
    helps at all, the social-science report with rejecting the question's premise.
- **Where the follow-up researchers went.** Of the 20 researchers sent after round 1, 9
  served a goal to settle a critical disagreement and 9 a new goal from the findings. Of
  the 9 settle goals, 3 were answered and 6 ended with nothing settled; 23 of the 31
  critical disagreements stayed disputed. In the industrial-revolution run the two
  follow-up researchers went to a dispute over one living-standard index and to other
  countries, while the goal for the political and cultural effects was raised as
  completing and never served.

**How far this goes.**
- One run of each question and one judge. The two orders agreed on 10 of the 12
  questions, 7 to 3; that count alone could arise by chance (two-sided p = 0.34). The
  judge preferred the report shown second in 14 of 24 judgments.
- The checklists of the real queries are coarse (3 to 7 broad items), and those of the
  designed questions were written by the person who ran the test, before the runs.
- The real queries are of one kind (questions on history and society that ask why or
  how); the draw contains no product, travel or how-to request.
- The test does not show that the baseline is better. It shows that the advantage
  measured on the five development questions is not found on new ones.
- The sealed questions have now been read and are development questions from here on.

### 24.6 The three changes proposed in section 23.3, against the new questions

Each was proposed after one run of one development question. None was built at the time
of the test; the first was approved afterwards (section 25.1).

| Proposed change | What the new questions show | Decision |
|---|---|---|
| A rule in the extension prompt to cover the main cases of what the client did not state | A plan settles on one nationality in 5 of 50 plans without the rule (3 of 21 saved flight analyses, 2 of 29 analyses of five new questions of the same pattern) and in 2 of 50 with it. Too few to tell the two apart. On the 72 analyses of the check questions the rule changes no measure | One sentence, consistent with the rule the request analyst and the round analyst already have. Approved by the user on 2026-11-18 and added to the accepted prompt (section 25.1) |
| Spend the researchers left when a run is complete early | Did not recur: no sealed run stopped with fewer than 4 researchers, and 6 of 12 reached the ceiling with goals still open | Not built |
| Never mark a goal necessary when it was raised from a completing step | 2 of the 11 necessary goals raised in the sealed runs came from a completing step: one a detail (how a connection is closed), one a main part of the answer (the role of enslaved labour). A fixed rule would have been wrong for one of the two | Not built |

The count of 9 to 13 of 21 flight plans in section 23.3 was a count of plans that name
a nationality anywhere. A model call that reads each plan and reports only a plan that
asks for one nationality and no other gives 3 of 21.

The sentence for the main-cases rule, at the end of step 4 of the extension prompt
(tested as the wording "m" in `local/ebd-heldout/plans.ts`; approved and added on
2026-11-18, section 25.1): "When
what an event involves depends on something the client did not state (who the client is,
where they come from, their budget, their dates), the question and the parts cover the
main cases and name them; never settle on one case that the request does not state."

### 24.7 Open points

- **Follow-up priority.** Under a ceiling of 6, nearly half of the follow-up researchers
  go to settling a disagreement, and two thirds of those settle nothing, while main parts
  of the answer stay unserved. Whether a missing main part should come before a critical
  disagreement is a design decision: section 20 gives the critical conflict the first
  place, following EBD. Decided on 2026-11-18: the missing main part comes first
  (section 25.2). The replay of section 25.3 shows that the order was rarely what decided.
- **Breadth of the plan.** The life-cycle steps follow the question's own scope; the
  baseline's planner spreads over the topic, and the judge counted that as coverage.
- **A claim read from a modal verb.** "Exercises can help" and "social science can
  solve" became claims to check, and their verdict shaped the report's first sentence.
- **The name check** (section 24.3) and the rejection rate of the first replies.
- **Size of the plan for a simple question.**
- **The next test** needs a new sealed set (draws 15 onward), more than one run per
  question, and the default configuration judged in pairs as well.

## 25. Two decisions of 2026-11-18: the main cases, and the order of the follow-up

After section 24 the user decided two of its open points: the sentence on the main cases
goes into the extension prompt, and a missing main part of the answer comes before
settling a disagreement. Both are in the code. Neither has been tested on reports of new
questions yet (section 25.5).

### 25.1 The main-cases sentence in the extension prompt

The last sentence of step 4, as shown to the user and approved: "When what an event
involves depends on something the client did not state (who the client is, where they
come from, their budget, their dates), the question and the parts cover the main cases
and name them; never settle on one case that the request does not state."

- It is part of the accepted prompt (`EXTENSION_SYSTEM`), so it applies with the default
  options and with `completeMap`.
- Checked without search on a larger sample than in section 24.6: 60 analyses of the
  five probe questions and the 21 saved analyses of the flight question, each planned
  with and without the sentence. A model call reads each plan and reports a plan that
  asks for one nationality and no other; its count on the same plans moved by one or two
  between passes.

| Plans that settle on one nationality the request does not state | Without the sentence | With the sentence |
|---|---|---|
| Accepted prompt | 5 of 81 | 7 of 81 |
| `completeMap` wording | 12 of 81 | 4 of 81 |

- **The failure belongs mostly to the `completeMap` wording**, whose events carry the
  answer and are therefore written more specifically. There the sentence brings it down
  to the level of the accepted prompt. On the accepted prompt it makes no measurable
  difference.
- **No side effect on the check questions.** With the accepted prompt, on the 72
  analyses of section 24.3: items asked by any goal +0.1 points, by a life-cycle step
  −1.4 (interval −7.6 to +4.9), in round 1 +1.5.
- The figures of section 24.6 (5 of 50 and 2 of 50) were the first 29 probe analyses and
  the flight analyses with the `completeMap` wording.

### 25.2 The order of a follow-up round (option `mainPartsFirst`)

**The decision.** A missing main part of the answer comes before settling a
disagreement. Section 20 had given the goal that settles a critical conflict the first
place: it is a necessary goal of level 1, ranked with the premise checks and before the
goals that ask for content.

**The rule,** with `focusFollowUp`, in every round after the first:

1. The researchers go first to the necessary goals that ask for content: planned goals
   not yet asked, goals asked again under the rules of section 20.3, and the new goals
   the round analyst marked necessary. One goal to a researcher while researchers last,
   as before.
2. The goals that settle a disagreement are served with the researchers that are left,
   one settle goal to a researcher.
3. Briefs of completing goals come last, as before.

- **One exception.** A settle goal that a part of the answer waits behind stays in the
  first pass. This is the case when a goal judged "conflicting" waits for its outcome
  and a necessary goal that is still open depends on that goal (verify before
  explaining, section 6.2). Serving the settle goal is then the only way to that part.
  A premise check does not wait for the goal it depends on (`premiseFirst`), so it is
  not counted as held up.
- **What stays.** Which conflicts get a settle goal (critical ones, one per round), that
  the goal is necessary, so the run is not complete while it is open, its single
  attempt, and what the writer is told about a critical conflict that was not settled:
  both sides, where it arises. No prompt text changes. Without `focusFollowUp` nothing
  changes: there a settle goal is necessary only while it decides a claim or a goal
  waits for it (section 9).
- **Records.** The rationale of the decision names the settle goals that wait and why.
- **Code.** `plan` in `index.ts`, `gatesAnswer` in `goals.ts`, option `mainPartsFirst`
  (default true; false gives the order of section 20). Six tests in `focus.test.ts`.

### 25.3 The new order replayed on the saved runs (no model call)

`local/ebd-heldout/replay-order.ts` recomputes every plan of a follow-up round from the
recorded state of the 17 saved runs with the five options (the 12 sealed questions of
section 24 and the five development questions of section 23): 23 plans, 27 researchers.

- **The replay computes what the runs computed.** With the order of section 20 the
  recomputed plan equals the recorded one in all 23 plans.
- **The new order changes who gets a researcher in 1 of the 23 plans.** In the run on
  the one-child-policy question two settle goals wait, and their researcher goes to a
  new necessary goal (the long-run outcomes of the children born under the policy). In
  6 other plans only the order of the same briefs changes.
- **In the 9 other plans in which a settle goal had a researcher, no other necessary
  goal was left without one.** Briefs that settle a disagreement: 11 of the 27 follow-up
  researchers before, 9 with the new order.

What the follow-up had to choose from after round 1, with 2 researchers left in each of
the 17 runs (`local/ebd-heldout/supply.py`):

| After round 1, over the 17 runs | Count |
|---|---|
| New necessary goals for a part of the answer | 10: none in 8 runs, one in 8 runs, two in 1 run |
| New completing goals | 10 |
| Goals to settle a disagreement | 11 |
| Researchers left | 34 |
| Researchers sent | 26 |

- **The order was not what kept missing parts from being researched.** In 16 of the 17
  runs the round analyst raised at most one missing part. The settle goal then took the
  second researcher, which nothing else asked for, and 8 of the 34 researchers were not
  sent at all.
- **Why few missing parts are raised,** as far as the rules show:
  - A proposal must cite a finding or a gap that mentions the part (section 10.2), and
    one that cites nothing is rejected. A part of the answer that no researcher was asked
    about, and that no source happened to mention, cannot be raised.
  - The analyst marked as completing a part that the judge of section 24.5 then missed
    in the report: the political and cultural effects in the industrial-revolution run.
- Section 24.7 called the follow-up order the first open point. On this evidence the
  first open point is the raising of missing parts; the order only decides between goals
  that have been raised.

### 25.4 Live checks

- `npm run check-strategy` passed live after both changes: with the default options on
  the fixed EBD question, whose extension prompt now carries the sentence, and with the
  five options on the flight question (all 11 required checks each;
  `local/ebd-heldout/check-decisions-default.out` and `check-decisions-five.out`).
- In the flight run the step for travel documents asked "for the main nationalities and
  for connections in third countries". After round 1 the two researchers left went to a
  new necessary goal first and then to the goal that settles the one critical conflict
  followed up; the record says the settle goal took a researcher "that no missing part
  of the answer can use this round". It settled its conflict, and the run ended complete.
- One run of one question: it shows that both changes work in a real run, not what they
  do to the report.

### 25.5 Open points

- **Raising the missing parts.** Proposed to the user, not built: the round analyst may
  propose a necessary goal for a main part of the answer that no finding mentions,
  within the two necessary goals of a round, and code accepts it without a citation.
  It changes the rule that every new goal grows from evidence, and it needs prompt text.
  Approved and built on 2026-11-19 (section 26.1); the replay of section 26.2 shows the
  analyst does not use it.
- **One sentence of the pending conflict-checker section** says of the critical
  conflicts that "one of them is settled in each round". With the new order one of them
  is followed up in a round only when a researcher is left. To be corrected when that
  section is approved. Corrected on 2026-11-19 (section 26.1).
- **Neither decision has been tested on reports.** The replay shows what the order does
  to the plans of saved runs, most of them runs the decision was drawn from. A test on
  new questions needs a new sealed set (section 24.1) and a judge pass.

## 26. Before the next test: would the changes so far move the result? (2026-11-19)

The user approved two more changes and asked that, before any test, the changes be shown
to be worth one, because the API budget is short. This section records the two changes,
what replays of the saved runs show about them, where the baseline's lead of section 24.5
comes from, and one further change built for decision. No search and no judge pass was
run. Scripts and outputs are in `local/ebd-heldout/`.

**Verdict.** The changes made since section 24 (sections 25 and 26.1) would not change
the result of section 24.5. A test now would spend its budget to measure the same thing
again.

### 26.1 Two changes approved on 2026-11-19

**A main part of the answer that no finding mentions** (option `uncitedParts`, on by
default, effective only with `focusFollowUp`).

- Prompt, one sentence of the pending follow-up section of the round analyst
  (`MAIN_PARTS_UNCITED` in `rounds/analyst.ts`), as shown to the user and approved: "For
  each main part that the findings mention only in passing or not at all, propose a
  necessary goal before you propose any detail. Cite the finding or gap that mentions it;
  when nothing mentions it, cite nothing." The earlier sentence (`MAIN_PARTS_CITED`) is
  sent with the option off.
- Code, in `acceptProposals`: a proposal that cites no existing evidence is accepted when
  it is marked necessary and fewer than two new goals of the round are necessary. It is
  never made a completing goal: a detail still has to grow from a finding. Every other
  check of section 10.2 applies (it serves a necessary goal or a synthesis question, it
  repeats no goal, the limits). The new goal is one step from the request, its origin is
  recorded as `uncovered`, a term it introduces is not added to the objects, and a goal
  attached to the answer the client asks for moves to an object of the goal it serves.
- 8 tests in `focus.test.ts`. The run viewer shows the origin.

**The sentence on critical conflicts** in the pending conflict-checker section. Before:
"one of them is settled in each round." Now: "at most one of them is followed up in each
round." The log line of the same rule was reworded to match.

### 26.2 The step after round 1 replayed with a fresh round analyst

`replay-observe.ts` runs `observe` again from the recorded state before round 1's results
and the recorded researcher results of the 17 saved runs with the five options (the 12
sealed questions of section 24 and the five development questions).

- **The replay is exact.** With the recorded replies of the conflict checker and the
  round analyst and the options of the runs, all 17 steps give the recorded goals and
  briefs, and the round analyst's input is the recorded input character for character.
- Then the round analyst was called afresh, twice with each wording of the sentence, on
  the same input: 68 calls, about $0.51. Both wordings use the follow-up order of
  section 25.

| Over 34 replayed steps with each wording | Earlier sentence | Approved sentence |
|---|---|---|
| New necessary goals for a part of the answer | 23 | 26 |
| of them citing nothing | 0 | 0 |
| Steps with none, one, two such goals | 16, 13, 5 | 14, 14, 6 |
| New completing goals | 14 | 11 |
| Researchers of round 2 sent to a new necessary goal | 23 | 26 |
| to a goal that settles a disagreement | 19 | 21 |

- **The permission is never used.** No reply cites nothing. The analyst always finds a
  finding to cite, so the citation was not what kept missing parts from being raised;
  section 25.3 guessed that it was.
- **The two wordings cannot be told apart** (23 and 26 over 34 steps; two calls with one
  wording differ as much).
- **What the analyst calls a missing main part is not what the judge missed.** For the
  seven questions on which the judge preferred the baseline in both orders, in the four
  fresh calls each:

| Question | The judge missed | What the round analyst raised |
|---|---|---|
| Industrial revolution | Politics, protest and culture | That part as a completing goal in 4 of 4; "outside Britain" as the necessary one in 4 of 4 |
| Slavery | How slavery ended and what it left | Other slave systems (the Islamic world, the Indian Ocean) as necessary in 4 of 4; the ending never |
| People without electricity | The outlook, investment needs | Nothing in 4 of 4 |
| Einstein's prize | The Nobel lecture behind the belief | One goal on the prize's statutes in 1 of 4; the lecture never |
| Back-pain exercises | How to do them, what to avoid | One named method in 2 of 4, guidelines in 1; neither part |
| Nuclear and solar | Land per unit of energy, costs on one basis | Two necessary goals in 3 of 4, with either wording: land per unit of energy each time, cost on one basis once. The recorded run raised none |
| One-child policy | Care in what is concluded | One goal in 1 of 4 |

- The same sentence in the prompt names "one more market, region, case or group of
  users" as a completing goal. The analyst marked other regions or other systems
  necessary in two of these questions.

### 26.3 Where the baseline's lead comes from, in the records

Read from the saved runs and the judge's results of section 24.5, with no model call
(`digest.py`, `innotes.py`, `plansvs.py`, `round1.py`). The line counts are keyword
counts and only show the size of a difference.

- **It is not checklist coverage.** Item by item, the EBD report scored higher than the
  baseline's on 11 checklist items and lower on 6. The judge still preferred the
  baseline in 16 of 24 judgments, and on usefulness in 16.
- **Parts the judge missed were thin in EBD's notes, or in the notes and little used.**

| Question | Part | Lines in EBD's notes, then report | In the baseline's notes, then report |
|---|---|---|---|
| Industrial revolution | Politics and movements | 2, 1 | 44, 7 |
| Slavery | How it ended | 31, 3 | 28, 7 |
| Slavery | What it left | 4, 2 | 20, 5 |
| People without electricity | Outlook to 2030 | 10, 2 | 16, 4 |
| Einstein's prize | The Nobel lecture | 5, 0 | 14, 1 |
| Back-pain exercises | What to avoid | 8, 1 | 34, 4 |
| Back-pain exercises | Flare-ups and warning signs | 9, 1 | 24, 7 |
| Nuclear and solar | Capacity factor | 6, 1 | 32, 4 |

- **EBD's notes are longer than the baseline's on six of the seven questions** (for
  example 17,200 against 9,700 words on slavery), and on five of those six its report is
  the shorter one. What the researchers were asked decides what the notes hold.
- **A researcher of round 1 often only checks a claim the question takes for granted.**
  In the 17 runs, 10 of the 68 first-round researchers served nothing else. Seven of the
  ten confirmed the claim ("Slavery was important", "The industrial revolution affected
  people", "Some people in the world do not have access to electricity"), two left a
  claim undecided ("Exercises can help with lower back pain"), and one found the claim
  false: the telescope question, which was written with a false premise. Of all 17 claims
  checked, 11 were supported, 3 undecided and 3 contradicted, the 3 on the two questions
  written with a false premise.
- **The check and a life-cycle step then ask the same thing.** For the back-pain
  question one researcher asked whether exercise helps and a second asked for the
  evidence of benefit; the step on safety was a completing goal that shared a researcher
  with the step on mechanisms. The baseline sent its three researchers to the exercises
  and how they are done, the evidence, and safety and what to avoid.
- **A part can be missing from the plan altogether**: politics and protest for the
  industrial revolution, where the baseline's plan had two of four briefs on it.
- **The writer was told to build on side disputes.** For the slavery question the two
  conflicts marked critical were about farm labour in Athens and the kingdom of Kongo,
  and both went to the writer as points "the answer depends on". The judge called both
  tangents.

### 26.4 The writer's input rewritten on the saved notes

Tested because it costs a cent a report: `rewrite.ts` writes the 12 sealed reports again
from their saved states with the platform's writer (48 writer calls, about $0.35).

| Variant | What the writer is told |
|---|---|
| `rec` | The recorded input, written again: the control |
| `none` | The notes alone, as the baseline hands them over |
| `quiet` | The recorded input without the line for an undecided premise and without the lines for critical conflicts |
| `parts` | `quiet`, plus the researched life-cycle steps as the suggested outline |

- **The writer differs from run to run by more than the variants differ.** The same
  input written again gave 22,500 words over the 12 reports; the saved reports have
  18,700, the baseline's 21,800. In the back-pain report the lines on how the exercises
  are done went from 0 to 3 with the same input.
- **No variant brings in what the notes lack.** Politics in the industrial-revolution
  report: 1 line in every variant, against 7 in the baseline's. The Nobel lecture: 0 in
  every variant. The first section of the back-pain report is on how far exercise helps
  at all in every variant, also with no guidance: the notes carry that weight.
- **`quiet` and `parts` help where the notes hold the part.** Slavery, how it ended: 2
  lines in the control, 8 and 6 in these two, with a section of its own; Athens and
  Kongo: 4 lines in the saved report, 1 and 2. With `quiet` the title of the
  social-science report no longer denies the question's premise.

**A cheap screen, and its limits.** `screen.ts` puts the judge's pair instruction, word
for word, to Claude Haiku: three times per pair and order on the saved reports, twice on
the rewrites (about $0.10 a pass).

- Against the Opus judge on the same 24 pairs of saved reports: the same overall verdict
  in 52 of 72 judgments, and the same side on 8 of the 10 questions the Opus judge
  decided in both orders.
- It favours EBD more than the Opus judge does: 38 of 72 judgments for EBD against 8 of
  24. On "handling of disagreements" it gives EBD 38, tie 24, baseline 10; the Opus
  judge gave 7, 13, 4.
- On the rewrites (48 judgments each; EBD, tie, baseline): control 29, 3, 16; `quiet`
  22, 3, 23; `parts` 32, 1, 15; `none` 23, 2, 23. The industrial-revolution and
  back-pain reports stay with the baseline in all four, and the Einstein report never
  goes to EBD.
- The screen rewards the handling of disputes, which is what `quiet` removes, so it
  cannot decide for or against `quiet`. It is good enough to say that no variant of the
  writer's input turns the questions lost on missing material.

No change to the writer's input is proposed on this evidence.

### 26.5 A claim check shares a researcher (option `premiseRides`, built, not decided)

**The rule.** In round 1 a goal that only checks a claim of the question is asked in a
brief that asks for content, as one more key question at the head of the brief, and
takes no researcher of its own.

- The check is still made in round 1, so a false premise is still found before the
  follow-up (`premiseFirst`, section 6.2).
- It joins a brief that holds a necessary goal and no other check: the brief about its
  own object first, then the brief that asks the fewest key questions.
- It never joins a brief in which it would keep a life-cycle step from being asked part
  by part, or that would then ask more than six key questions (section 21).
- When a check fits nowhere, for example when the question has more claims to check than
  the round has briefs that ask for content, the round is planned as before.
- After round 1 nothing changes. No prompt text changes.
- Code: `isClaimCheck` and `shareChecks` in `briefs.ts`, `plan` in `index.ts`. 5 tests.
  Off by default: it changes what section 6.2 gives a premise check, which is the user's
  decision. Decided on 2026-11-19 and on by default since (section 27).

**Replayed on the 17 saved first-round plans** (`replay-round1.ts`, no model call; with
the option off the replay gives the recorded briefs in all 17):

| Over the 17 first-round plans | Now | With the option |
|---|---|---|
| Plans that change | | 14 |
| Researchers in round 1 | 68 | 67 |
| Researchers that only check a claim | 10 | 0 |
| Key questions asked | 288 | 330 |
| Goals asked part by part | 49 | 60 |
| Most key questions in one brief | 6 | 6 |

- For the slavery question the step on how slavery ended is asked in round 1; before, it
  waited for round 2.
- **Open:** in 3 of the 14 changed plans the researcher that becomes free goes to a
  planned overview question with one key question, while two completing steps still
  share a researcher (the back-pain plan: safety and mechanisms). Sending it to the step
  instead needs a further rule in `spread`. Done in section 27.4 (option `stepsFirst`).
- **Not known:** what it does to the reports. That needs searches.

### 26.6 What a test needs first

- **Not addressed by anything built:** a main part missing from the plan (26.3), and
  what the round analyst takes for a main part (26.2).
- **A staged order, cheapest first,** each step only if the one before it shows a
  difference:
  1. The user decides `premiseRides`.
  2. A check with searches on six questions already read: four the baseline won for a
     missing part (back pain, slavery, industrial revolution, electricity) and two EBD
     won (the internet, the database choice), so that a gain is not only the effect of
     picking the worst cases. About $3 of Haiku calls and 12 pair judgments, about
     110,000 input tokens of Opus.
  3. The sealed test of section 24.7 on new questions: about $11 of Haiku calls for 12
     questions in both arms, and 240,000 to 450,000 input tokens of Opus.
- The live contract check (`npm run check-strategy`) has not been run on the changes of
  this section. The approved sentence went to the live model 34 times through `observe`
  in the replay; the path for a goal that cites nothing has run in unit tests only.

### 26.7 Spend

About $1.30 of Haiku calls (round analyst replays $0.51, rewrites about $0.35, screen
passes $0.45), no search and no Opus call.

## 27. The premise check: sort, share, overrule (2026-11-19)

After section 26.3 the user asked how else a premise could be checked, what other deep
research systems do, and then gave the instruction: "Apply the recommend premise check
solution". This section records what was applied. Records and scripts are in
`local/ebd-heldout/` (`sort.ts`, `replay-round1.ts`, `replay-conflicts.ts`).

**The problem.** Section 6.2 checks every claim the question takes for granted in
round 1, with a researcher of its own. In the 17 saved runs that took 10 of the 68
first-round researchers; 7 of the 10 confirmed a claim that restates the question, and
where the check came back undecided the report opened with a doubt (section 26.3). A
strategy may not search (docs/strategy-modules.md, rule 2), so a claim cannot be settled
before round 1, and deciding it from the model's memory would be a guess.

**The solution, in four parts.** Which claims need a check is decided before any
search; a check that remains shares a researcher; the evidence can still overrule a
claim that was not checked; and the writer hears about a claim only when it matters.

### 27.1 The premise sort (option `premiseSort`, on by default)

One model call after the request analysis and before the extension (`premises.ts`,
role `premise_sorter`, tool `submit_premise_sort`). The request-analysis prompt of
Lab 2 is not changed.

- **Input:** the question and the claims the analysis listed (A1, A2, ...). Nothing else.
- **Output:** for each claim `check` or `given`, with a reason of at most 15 words.
- **It never says whether a claim is true.** The prompt says so, and tells the sorter
  to judge from the wording, "never from what you believe to be true".
- **check**, in the prompt's words: "the claim states a specific fact that the question
  treats as settled and that could simply be wrong", such as a particular event, a date,
  a number, who did something, the cause of a particular event, a place, or a property
  of a named thing.
- **given**: "the claim only restates, in general terms, what the question itself asks
  about: that its subject exists, matters, has effects, can help, can work or can be
  done", or the question's own words spell it out.
- **When in doubt: check.** A claim that joins a general part and a specific fact is
  check too.
- **Fail-safe.** Without a usable reply every claim is checked, as before, and the run
  records it under problems. No call is made when the analysis lists no claim.
- The full prompt is `PREMISE_SYSTEM` in `premises.ts`. Its five examples use subjects
  that are in no test question.

**What a claim taken as given changes in the plan** (`applyGiven`, after the extension):

- The planned question that checked it loses the claim. When it checks nothing any
  more, it is no longer a check: its brief carries no instruction to verify, the round
  analyst is asked for no verdict, and the evidence floor of section 10.1 does not apply.
- With necessary life-cycle steps in the plan, that question is treated like a question
  the steps replace (section 19.2): a completing goal, and what waited for it waits for
  the steps instead. Without them it stays a necessary question for content, and what
  waited for it no longer waits, since nothing is verified first.
- The run is complete without a verdict on the claim (section 11 needs a verdict only
  while a goal that verifies the claim is open).
- When another claim is contradicted, a claim taken as given protects its objects like
  a supported one (`refutedObjects`, section 10.2).
- The decision's rationale names the claims taken as given, and the run viewer shows
  the sorter's reason beside each.

### 27.2 A check that remains shares a researcher (option `premiseRides`, now on)

The rule of section 26.5, unchanged: in round 1 a goal that only checks a claim is asked
at the head of a brief that asks for content, one check to a brief, and the round is
planned as before when a check fits nowhere.

### 27.3 Where the first round's researchers go (option `stepsFirst`, on by default)

Two rules, so that the researcher a check gives up goes to a part of the answer. They
apply in round 1 when the plan has life-cycle steps.

- **A planned question that the steps stand in for only rides along.** That is a
  question the steps replaced (section 19.2) or one that stopped being a check
  (27.1). The briefs are made without it; it then joins a brief that has room for one
  more key question, or waits (`shareRiders`). Before, such a question could take a
  researcher to itself with one key question.
- **A researcher that would sit idle goes to a step first.** When a brief holds two or
  more steps, one of them gets the free researcher, so that each is asked part by part
  (`spread`). Otherwise the rule of section 7 applies as before.

### 27.4 The evidence can overrule a claim taken as given

- The conflict checker still sees every claim. A claim taken as given is marked
  "(taken as given)", and one section is added to the checker's prompt only when a run
  has such a claim (`CONFLICT_GIVEN_SECTION` in `rounds/conflicts.ts`):

  > Assumptions taken as given:
  > Under <assumptions>, a claim marked (taken as given) only restates, in general
  > terms, what the question asks about. The team did not check it as a fact of its own.
  > For such a claim, report an evidence_vs_assumption conflict only when findings state
  > that it is false as a whole (for example, the question asks why a food causes an
  > illness, and the sources report that it causes none). Findings that limit or qualify
  > it (it holds for some cases, groups or conditions and not for others, or its size is
  > disputed) are part of the answer and no conflict with the assumption. A disagreement
  > between sources about how far it holds is a source_vs_source conflict with an empty
  > claim.

- A conflict of evidence against a claim is critical as before (section 20.2). Its
  settle goal verifies the claim, and that goal's verdict is the claim's verdict.

### 27.5 What the writer is told about a claim

| The claim | Its verdict | The writer is told |
|---|---|---|
| Checked | Contradicted | "The evidence contradicts this; say so plainly early in the report." (unchanged) |
| Checked | Undecided, or never checked | Not to present it as established (unchanged) |
| Checked | Supported | Nothing with `leanGuidance`; one line otherwise (unchanged) |
| Taken as given | None | Nothing |
| Taken as given | Contradicted by a goal that settled a conflict about it | To say so plainly early in the report |
| Taken as given | Anything else from such a goal | Nothing about the claim; the conflict keeps its own line |

- The recommendation put to the user said "say nothing about one that was skipped or
  undecided". The line for a checked claim that stays undecided was kept: for a specific
  fact that no source confirms, the warning protects the reader. The three undecided
  claims of section 26.3 were general ones; the sorter takes two of them as given (27.6).

### 27.6 Checks without search

**The sorter on every saved request analysis that has claims** (`sort.ts saved`; 156
analyses, 184 claims, about $0.04): 121 claims taken as given, 63 to be checked, no
unusable reply and no second attempt.

| Question (saved analyses) | Claim, in one of its wordings | Verdicts |
|---|---|---|
| Telescope, written with a false date (15) | "The launch ... took place in 2018"; "NASA launched ..." | check in all 29 |
| Einstein's prize, false attribution (1) | "... was awarded for the theory of relativity" | check |
| Swiss women's vote (6) | "Switzerland did not give women the right to vote ... before 1971" | check in all 10 |
| Sleep and food (13) | "Some food can help the client sleep well" | given in all 13 |
| The EBD question (29) | "EBD stands for Environment Based Design" | given in 27, check in 2 that add "a design method" |
| Back-pain exercises (1) | "Exercises can help with lower back pain" | given |
| Social science (1) | "Social science can solve social problems" | given |
| One-child policy (1) | "Population control led to better child quality" | check: read as a cause stated as fact, although the question asks whether |

**The sorter on 16 new questions** (`sort.ts new`), written for this test before the
sorter ran on them and used for nothing else: one request analysis each, then the sorter
twice. The prompt was not changed afterwards.

| Kind of question | Questions | Result |
|---|---|---|
| A false premise: a wrong actor, inventor, date, number, property or cause | 8 | Every claim that holds the false element is check, in both sorts of all 8 |
| A general premise ("Why does sleep matter for learning?") | 6 | given in both sorts of all 6 |
| A true specific fact ("Why did the Titanic sink in 1912?") | 2 | check |

- In "How did Thomas Edison's invention of the telephone change communication?" the
  sorter split the two claims: "Thomas Edison invented the telephone" is check, "The
  invention of the telephone changed communication" is given.

**First-round plans replayed** (`replay-round1.ts`, no model call in the replay; with
the three options off it gives the recorded briefs in all 23 plans):

| Over the first-round plans | 17 plans, five options: before | after | 6 plans, default options: before | after |
|---|---|---|---|---|
| Claims of the question, and those taken as given | 17 | 10 given | 6 | 4 given |
| Researchers in round 1 | 68 | 65 | 24 | 24 |
| Researchers that only check a claim | 10 | 0 | 6 | 0 |
| Key questions asked | 288 | 340 | 39 | 38 |
| Briefs with exactly one life-cycle step | 44 | 61 | 7 | 15 |
| Steps that share a brief with another step | 22 | 6 | 16 | 11 |
| Steps not asked in round 1 | 1 | 0 | 3 | 0 |
| Researchers on one planned completing question alone | 2 | 0 | 0 | 0 |

- The back-pain plan: before, one researcher checked whether exercise helps and the
  steps on safety and on mechanisms shared one. After, each of the four steps (exercise
  types, evidence of benefit, mechanisms, safety) has a researcher.
- With the default options every one of the six plans had a researcher that only
  checked a claim.

**The conflict checker replayed** on the 10 saved runs with a claim taken as given
(`replay-conflicts.ts`; `observe` run again with a fresh checker and the recorded round
analyst, twice per arm, about $0.37):

| Checker replies | As recorded (10) | Fresh, no mark (20) | Fresh, claims marked (20) |
|---|---|---|---|
| With a conflict of evidence against a claim taken as given | 2 | 4 | 1 |
| With a disagreement between sources tied to such a claim | 0 | 2 | 0 |
| Conflicts in all | 72 | 116 | 111 |

- The conflicts against "exercise can help" and "social science can solve" are gone
  with the mark (0 of 4 replies; without it 3 of 4). The one left is a page that says no
  flight exists on the route, which states the claim false as a whole.
- **The safety net holds.** For the two questions written with a false premise every
  claim was marked as given against the sorter's verdict. The checker still reported
  the findings against the false claim in 4 of 4 replies.

### 27.7 Live check

`npm run check-strategy` passed live with the default options, which now include the
three options of this section: all 11 required checks, 6 researchers, 2 rounds, $0.50
(`local/ebd-heldout/check-premises-default.out`). The question is one of the 16 new
ones and has a false premise: "How did Thomas Edison's invention of the telephone change
communication?"

- **The sort.** "Thomas Edison invented the telephone" was sent to be checked, and "The
  invention of the telephone changed communication" was taken as given. One call, 1,419
  input tokens, 1.4 seconds.
- **Round 1** used three researchers. The check was asked in a brief together with a
  question for content, and the round analyst judged the claim contradicted in that
  round.
- **The writer** was told about the contradicted claim and nothing about the other one.
  The report opens: "The telephone did not come from Thomas Edison. Alexander Graham
  Bell received the key U.S. patent on March 7, 1876", and then answers how the
  telephone changed communication.
- One run of one question. It shows the parts working together in a real run, not what
  they do to the reports against the baseline.

**Code and tests.** `premises.ts` (the sorter, `recordSort`, `applyGiven`);
`shareChecks`, `shareRiders` and `spread` in `briefs.ts`; `init` and `plan` in
`index.ts`; `CONFLICT_GIVEN_SECTION` and the mark in `rounds/conflicts.ts`;
`buildGuidance` in `synthesis.ts`; `refutedObjects` in `goals.ts`. 15 tests in
`premises.test.ts`, 5 in `focus.test.ts`; 207 tests pass.

### 27.8 Open points

- **Not tested on reports.** Everything above is about plans and about what the checker
  and the sorter say. Whether the reports get better needs searches and a judge
  (section 26.6).
- **The correction rule approved on 2026-11-16 is still not built**: when a premise is
  contradicted, the questions that rely on it should be corrected, not dropped. It needs
  prompt text for the round analyst.
- **The sorter sorts what the request analysis lists.** A presupposition the analysis
  does not list is not sorted; it was not checked before either.
- **A claim that is the question itself.** "Population control led to better child
  quality" was listed as a claim of a question that asks whether, and sorted as check.
  One case; the prompt was not tuned on it.
- **Without life-cycle steps** (`extend` off, or no usable extension) a question that
  stopped being a check keeps a researcher as a question for content.
- **`stepsFirst` also changes plans of questions without claims**: a replaced overview
  question no longer takes a researcher to itself.

### 27.9 Spend

About $1.00 of Haiku calls: the sorter on saved analyses $0.04 and on the new questions
with their request analyses about $0.05, the conflict checker replays $0.37, and the
one live run with searches $0.50. No Opus call.

## 28. Environment analysis in one call (option `init: "environment"`, built 2026-11-19, off)

On 2026-11-19 the behaviour design lead set the frame: "we just need to follow the overall
concept of EBD for this approach, and we can develop optimal working process by our own",
and then: "Proceed with the next step, I accept the architecture update if it improves the
EBD approach." The next step was a first plan made in one call, checked on plans without
search. This section records what was built and what the check showed. The mode is off by
default: its prompt text is not approved, and the check does not show an improvement in
what the plan asks for (section 28.5).

### 28.1 Why

Read from the 24 saved runs of the sealed questions (section 24.5), no model call
(`local/ebd-heldout/yield.py`); EBD with the five options against the baseline:

| Over the 12 questions | Baseline | EBD |
|---|---|---|
| Strategy calls a run | 2.0 | 7.6 |
| Output tokens of the strategy's own calls | 36,400 | 422,600 |
| Seconds, of which first-round research | 1,530, 811 | 3,627, 814 |
| Words of notes, then words of reports | 101,900, 21,800 | 140,600, 18,700 |
| Citations in the reports for each researcher | 16.0 | 8.3 |
| Runs with a follow-up round | 1 | 11 |

- Report length does not follow the notes: over the 24 runs the correlation of note words
  with report words is -0.02, and every report has 1,185 to 2,155 words.
- The researchers sent to settle a disagreement were 13% of EBD's researchers and supplied
  6% of the citations in its reports. A follow-up researcher on a new part supplied as much
  as a first-round one (9.6 against 9.4 citations).
- Of EBD's extra 2,097 seconds, 446 were follow-up research and about 1,650 its own model
  calls. Three of those calls come before the first search.
- The baseline's planning call names what the model knows as examples to look for (41% to
  45% of its key questions carry one); the extension analyst may not name anything
  (section 19.2), and its name check rejected a quarter of the first replies on new
  questions (section 24.3).

### 28.2 The concept kept, the procedure changed

EBD's procedure asks questions from the wording of the request (the request analysis),
then widens them through the life cycle of the subject (section 19). This mode keeps the
concept and drops that order of steps:

- **The product is the answer.** Its environment has three sides: the client, who will
  use it; the subject, with everything around it that the answer depends on; and what the
  question takes for granted.
- **One call analyses that environment and writes the plan**: the main parts of a full
  answer, each with an objective and 4 or 5 key questions (3 to 5 in the first wording). The parts are found by looking
  from each side: the question itself, the subject over time, what surrounds the subject
  (natural, built, economic, social), the client's side, and where sources are likely to
  disagree.
- **The analyst may use what it knows**, and may name specific things as examples to look
  for. Everything it writes is an assumption that the evidence overrides, as decided on
  2026-11-11 (section 19.3): researchers are told so, a finding confirms or refutes each
  key question, and nothing the analyst writes reaches the writer.
- **Conflicts still drive what follows.** The claims of the question are sorted as in
  section 27, in the same call; the conflict checker, the round analyst, the stop rules
  and the writer input are unchanged.

### 28.3 The call

`environment.ts`: the prompt `PLAN_SYSTEM`, the reply schema, the checks, the fallback.

| The reply holds | Used for |
|---|---|
| Status, restated request, subject | Out-of-scope stop; the writer's reading line |
| Purpose, time frame, place, each with its basis | Brief constraints, as before |
| Directives, with the client's words | Researchers and writer, as before |
| What the client did not state, with the main cases | A constraint line in every brief |
| An abbreviation or ambiguous term, with its meanings | Brief constraint, or the writer's reading line |
| The claims the question takes for granted, each marked check or given | One check question for the claims marked check; the others are taken as given (section 27) |
| 1 to 5 main parts: name, necessary or completing, objective, key questions, source hints | One goal and one map event for each part; the key questions are its parts |

- **Checks.** A list that is too long is cut with a warning. A part listed twice, an
  objective or key question that refers to another one, or fewer than two key questions
  is an error, and the call is retried once with the errors. The fallback keeps the parts
  no error points to; a key question whose only fault is its length is cut.
- **No name check.** Names are allowed here; the checks of the request analysis do not
  apply.
- **No usable plan.** As in the other modes (section 24.4): the first time, `init`
  throws and the skeleton runs the step again; the second time the plan is the request
  itself as one question.

### 28.4 What code builds from the plan

- **An analysis** (`analysisFromPlan`) with one object for the subject, one for each
  abbreviation or ambiguous term, no relations, the claims as assumptions, and at most
  two questions: the check of the claims marked check, and the client's question as the
  synthesis question.
- **The environment map**: each main part is an event and its key questions are the
  event's parts, so the round analyst confirms or refutes each key question and the rules
  of section 19.3 apply unchanged. `map.questions` marks such a map.
- **Goals**: one for each part (at most four necessary, at least one), and the check.
  No goal waits for the check, so a contradicted claim cancels nothing.
- **Briefs**: a part's key questions are asked as written, one by one, whatever
  `partQuestions` says; the researcher is told that they and the examples they name are
  expectations (`PLAN_QUESTIONS_INSTRUCTION`). The check leads a brief that asks for
  content (`premiseRides`).
- `extend`, `completeMap` and `premiseSort` have nothing to do in this mode. Everything
  after `init` is the code of the other modes. The prompts of the conflict checker and the
  round analyst still say "life-cycle step" for a part.
- Code: `environment.ts`; `init` in `index.ts`; `briefFor` in `briefs.ts`; two optional
  state fields (`map.questions`, `plan`). 17 tests in `environment.test.ts`, one of them
  a whole run through the skeleton with fake researchers; 224 tests pass.

### 28.5 Plan-level check (no search)

`local/ebd-heldout/oneplan.ts`: the first-round plan of each method, several times for each
of the 24 questions of section 24 (12 sealed, 12 check; all read before, so development
data), and a small model call that says which checklist items the plan asks a researcher
about. The scorer sees objectives and key questions without the strategy's marks.

| | Baseline | EBD, five options, today's code | New one-call plan |
|---|---|---|---|
| Plans | 72 | 60 (36 rebuilt from saved replies) | 72 |
| Checklist items asked in round 1, sealed / check questions | 91% / 89% | 93% / 94% | 85% / 87% |
| The 8 main parts that the sealed reports lacked (section 26.3): asked | 23 of 24 | 11 of 16 | 16 of 24 |
| Researchers in round 1 | 3.5 | 3.8 | 3.4 |
| Key questions for each researcher, and their length | 4.5, 21 words | 5.4, 17 words | 3.7, 27 words |
| Key questions that name an example | 41% | 7% to 12% | 30% to 41% |
| Researchers that only check a claim | 0 | 0 | 0 |
| Planning: calls, seconds | 1.0, 12 to 14 | 2.7 to 3.4, about 40 | 1.0 to 1.1, 17 |
| Planning: input and output tokens | 1,700 and 2,500 | 29,100 and 9,300 | 5,900 and 3,600 |
| Plans with a fallback or a recorded problem | 0 | 5 | 0 |

- **The new plan is cheaper and faster, and it does not ask for more.** It needs one call
  where the present plan needs about three, a fifth of the input tokens and less than half
  the time, and none of its 72 plans fell back. It asks about fewer checklist items than
  the present plan (85% and 87% against 93% and 94%), and no more of the eight parts the
  reports lacked (16 of 24 against 11 of 16). The baseline's plan asks about nearly all of
  those (23 of 24).
- **Why it asks for less.** (1) Fewer key questions for each researcher: 3.7 against 4.5
  and 5.4. (2) Half of the items it asks about in fewer than half its plans are
  definitions ("What is slavery?"), which the prompt tells it not to make a part of; the
  baseline's plans leave out most of these too. (3) Parts about where things are heading
  or what is done about them are missing: the outlook for electricity access in 0 of 3
  plans, interventions against juvenile crime in 0 of 3. (4) The prompt is worded to keep
  parts out ("keep a part only if the answer would be wrong or incomplete without it"),
  where the baseline's says that the subtopics together must cover everything.
- **The claims.** Sorted from the wording as in section 27: both claims of the false
  premise question on Einstein's prize are checked in 3 of 3 plans, and so are the dated
  facts of the other questions; the general restatements ("Slavery was important",
  "Exercises can help with lower back pain") are taken as given. Four general claims were
  marked check in some plans ("The internet spread from its place of origin to other
  areas"), which the separate sorter did not do on its test questions. The 16 questions
  written for the sorter (section 27.6) have not been run through this mode.
- **A correction.** Before this check the user was told that the first plan of EBD asked
  about none of those eight parts. That was a keyword count on the saved plans of the
  sealed runs. With the scorer used here those saved plans ask about 3 of 8, and fresh
  plans with today's code about 11 of 16: the changes of section 27 and the difference
  between one plan and the next account for much of that gap. The baseline's saved plans
  ask about 8 of 8.
- **What this check cannot show.** Plan-level checklist coverage did not decide the
  sealed test: the present plan scores highest on it, and its reports lost (section
  24.5). Nothing here was searched or written.

### 28.6 Verdict and open points

- **Not switched on.** The condition was that the change improves the approach. It lowers
  the cost and time of planning; it does not improve what the plan asks for.
- **One revision is indicated** (made and checked later the same day, section 28.8): 4 or 5 key questions for each part; the
  parts together must cover everything a full answer needs, stated as a requirement; the
  subject over time includes where it stands, where it is heading and what is done about
  it; `not_stated` only where it changes the answer. It needs the user's approval of the
  wording and a new check, on questions not used for it.
- **Not run end to end.** No live run and no `npm run check-strategy` in this mode.
- **The round prompts** name a part of the answer a "life-cycle step".
- **The steps after the plan** (one review call instead of two, follow-up only when it
  changes the answer, the writer's outline) are not built.

### 28.7 Spend

About $0.63 of Haiku calls against the $0.50 named beforehand: planning calls $0.45 (the
live plans of the present EBD cost $0.18 of that), scoring calls $0.17. No search, no Opus
call.

### 28.8 The wording revised and checked on new questions (2026-11-19, later)

The user approved the four changes of section 28.6 ("proceed with proposed change and
recheck"). They are in `PLAN_SYSTEM`; the first wording is kept in `oneplan.ts`
(`REWORDED`), which runs either wording through the strategy's own call.

| Passage | First wording | Revised |
|---|---|---|
| Key questions | "3 to 5 key questions that split the objective." | "4 or 5 key questions that split the objective; 3 only for a narrow part." |
| Completeness | "List the parts that together carry a full answer: [...] Look at the answer's environment from each side below, and keep a part only if the answer would be wrong or incomplete without it:" | "List the parts that together cover everything a full answer needs, so that the client does not have to ask again for a main point: [...] The parts do not overlap. Look at the answer's environment from each side below:" |
| The subject over time | "[...] how it is used or done, what follows from it;" | "[...] how it is used or done, how it changed or ended, where it stands now and where it is heading, and what is being done about it;" |
| What the client did not state | | Added: "List a point only when the answer changes with it; most questions have none or one." |

The worked example was brought in line with the first change: its two parts of three key
questions got a fourth ("When did sales of digital cameras overtake sales of film cameras,
worldwide and for Eastman Kodak Company?" and "Which warning signs of a technology change
do advisers tell small family businesses to watch for, and what do they recommend doing
first?").

**New questions.** 12 real queries from a second random draw of the same dataset with
another seed (`sample2.py`, seed 20261120; `fresh-questions.json`). The rows that the first
seed gives in its first 60 draws were left out without being fetched, so the sealed set of
the next end-to-end test (draws 15 onward of seed 20261118) is still unread. Three plans
for each question with the first wording, the revised wording and the baseline, one with
the present EBD; the scorer of section 28.5.

| On the 12 new questions | Baseline | EBD, five options | One call, first wording | One call, revised |
|---|---|---|---|---|
| Key questions in a plan | 16.3 | 17.6 | 11.8 | 14.5 |
| Key questions for each part | | | 3.5 | 4.2 |
| Points listed as not stated by the client, a plan | | | 2.4 | 1.7 |
| Checklist items asked in round 1, each question weighted equally | 69% | 75% | 62% | 62% |
| The same on the 11 questions that every method planned, by item (46 items) | 67% | 83% | 69% | 69% |
| Of those: the 9 items that only ask what a term of the question is | 30% | 89% | 33% | 26% |
| Of those: the 37 other items | 77% | 81% | 77% | 79% |
| Planning: calls, seconds, tokens in and out | 1.0, 14, 1,700 and 2,700 | 3.2, 39, 29,300 and 9,200 | 1.0, 16, 5,800 and 3,300 | 1.1, 16, 6,200 and 3,500 |
| Plans with a fallback or a recorded problem | 0 | 1 of 12 | 0 | 0 |

An item "only asks what a term is" by a rule (`oneplan_items.py`): it starts with What or
Who is, are, was or were, and what follows up to the first "and" is one to five words of the
question ("What was apartheid?", "What is Hanna Andersson?"). On the 24 earlier questions
the same split gives, for the other items: baseline 94%, present EBD 92% to 93%, one call
with the first wording 90% to 92%; and for the 11 definition items: 60%, 100%, 55%.

- **The revised wording does what it was written for, and the checklist score does not
  move.** A plan has 14.5 key questions against 11.8, and 1.7 points the client did not
  state against 2.4. The share of checklist items asked is the same, and on the items other
  than definitions 79% against 77%: with three plans for each question that difference
  cannot be told from chance.
- **What separates the plans is definitions.** On every other item the four are within four
  points on the new questions (77% to 81%) and on the earlier ones (90% to 94%). The present
  EBD plan asks what each term of the question is, through the defining questions of the
  request analysis; the one-call plan and the baseline's plan do so for about a third of
  such items. Whether a report is better for having them cannot be read from a plan: the
  checklists count them, and the baseline's reports won the sealed test without them.
- **A question that does not say what it refers to.** For "what caused so many casualties
  in the earthquake" both EBD modes stop as out of scope (the request names no earthquake),
  in every plan; the baseline plans to identify the likely events and answer in general.
  This is the rule of the request analysis (section 5), carried into the new prompt. One of
  the 12 new questions is of this kind, none of the first 14.
- **The claims** (the 16 questions of section 27.6, two plans each, revised wording): the
  claim that holds the false premise is marked check in 16 of 16 plans (the script counts
  15: one plan words it "can be seen" where the script looks for "visible"), the true dated
  fact in 4 of 4, and every claim of the six general questions is taken as given in 12 of
  12. Some plans add a second claim that only repeats the first ("There is a reason why
  humans use only 10% of their brains"), also marked check; it joins the same check
  question.

- **The parts the sealed reports lacked, with the revised wording** (measured afterwards
  for the user's question about the gap; 36 plans on the 12 sealed questions, $0.13). These
  questions are development data, and two of the four changes were written after reading
  their plans, so the number is favourable to the revised wording.

  | The 8 main parts of section 26.3, asked in the first plan | Asked |
  |---|---|
  | Saved plans of the sealed runs (code of 2026-11-18) | 3 of 8 |
  | Present EBD, five options, today's code | 11 of 16 |
  | One call, first wording | 16 of 24 |
  | One call, revised wording | 20 of 24 |
  | Baseline, fresh plans | 23 of 24 |

  The revised plan has 3.8 researchers and 16.0 key questions on these questions and asks
  about 86% of the checklist items (first wording 85%).
- **What the follow-up researchers of the sealed runs were sent for** (from the records, no
  model call): of 20, 9 went to settle a disagreement. Six of those disagreements were
  between sources only and three decided a claim of the question; six of the nine ended
  with nothing settled. The follow-up rules are unchanged since.

**Verdict.** At plan level the one-call plan now asks for what the baseline's plan and the
present EBD plan ask for, apart from definitions, with one call in place of about three, 16
seconds in place of 39, a fifth of the input tokens, and no fallback in 176 plans (8 needed the one retry). It is
not shown to ask for more. Whether its reports are better can only be shown with searches.

**Open, for the user:** the definitions (left out as written; one key question could ask
for them); the question that names no referent (stop, or plan for the likely cases as the
baseline does); a live run in this mode (`npm run check-strategy`), which nothing above
replaces.

**Spend of the recheck.** About $0.47 of Haiku calls: planning calls on the new questions
$0.31, on the premise questions $0.08, scoring $0.08. No search, no Opus call.

## 29. The one approach (2026-11-19, night)

The behaviour design lead on the end state: "by the end of this improving tuning process of
the EBD deep search approach, we only left 1 optimal EBD approach". The approach below was
put to the lead and approved the same evening ("recommended approach and plan approved"),
with the steps to take before a test: every prompt text of the approach on one page for
approval, the follow-up rule built, one live run, and the rules of the test fixed
beforehand. This section records those steps. The lead approved all of it the same night
("approve all changes and texts"). Nothing here is on by default: that waits for the test.

### 29.1 What it is

Settings: `{ "init": "environment", "focusFollowUp": true, "leanGuidance": true,
"strictFollowUp": true }`; every other option at its default.

| Step | Who | What | Section |
|---|---|---|---|
| Plan | Environment analyst, one call | The main parts of the answer, each with 4 or 5 key questions; the claims of the question sorted into checked and taken as given; what the client did not state | 28 |
| Round 1 | Researchers | One researcher for each main part, its key questions asked one by one; the check of the claims rides in one of those briefs. With fewer researchers than parts the necessary parts come first | 21, 26.5, 28.4, 30 |
| After each round | Conflict checker, then round analyst | Conflicts among the findings and with the claims; each key question judged; new goals proposed | 9, 10, 20 |
| Follow-up | Code | A researcher goes only to a main part of the answer or to a claim of the question | 29.2 |
| Report | The platform's writer | The notes, and a line only for what the notes do not show: a contradicted or undecided claim, at most three critical disagreements | 20.4 |

- **The texts were approved on 2026-11-19** ("approve all changes and texts"), as they
  stand on one page generated from the code: `local/ebd-heldout/one-approach-prompts.md`
  (`prompt-page.ts`). That covers the texts written for this approach (the planning
  prompt, what a researcher is told about key questions, the question that checks the
  claims, the two sections on key questions, the two reworded sentences on conflicts) and
  the texts pending since 2026-11-11 and 2026-11-18 (the section on critical conflicts,
  the follow-up section of the round analyst, the writer's lean lines). A test pins them
  (`approach.test.ts`, "the prompt texts of the one approach"): it fails when one of
  these texts changes, so that a later change is shown to the lead and approved first.
- **What goes when a test confirms the approach:** the request analysis in both modes
  (`request/`), the premise sorter, the problem extension, and the options that switch
  between them and their rules (`init`, `extend`, `completeMap`, `partQuestions`,
  `premiseSort`, `premiseRides`, `stepsFirst`, `focusFollowUp`, `leanGuidance`,
  `mainPartsFirst`, `uncitedParts`, `strictFollowUp`). Until then they stay, so that nothing
  in use changes. `conflicts` and `newGoals` are used by the platform's experiment file for
  its ablation runs and are to be kept; to confirm with the platform owner.

### 29.2 After the first round: only a main part or a claim (option `strictFollowUp`)

Two rules, in code only:

1. **A disagreement between sources is reported, not researched again.** A conflict gets a
   goal of its own only when it decides a claim of the question (an `evidence_vs_assumption`
   conflict, or a disagreement between sources that the checker ties to a claim). Any other
   disagreement is recorded as disputed at once; when it is critical the writer gets its
   line (section 20.4). `applyConflicts` in `rounds/conflicts.ts`.
2. **A detail gets no researcher after the first round.** With `focusFollowUp`, a follow-up
   round serves necessary goals only; a completing goal is never served in it, there is no
   extra round of completing goals once the run is complete, and when no necessary goal and
   no claim is left the run stops. `plan` in `index.ts`.

Replayed with no model call (`replay-disputes.ts`, `replay-live.ts`): the step after round 1
from the recorded state, with the recorded replies.

| The follow-up round after round 1 | Today's rules | With the rule |
|---|---|---|
| 17 saved runs with the five options: researchers | 26 | 15 |
| ... of them sent to settle a disagreement | 9 | 2 |
| ... runs that stop after round 1 | 2 | 5 |
| ... plans that change | | 10 |
| The live run of section 29.5: researchers | 2 (a missing main part, a detail) | 1 (the missing main part) |

Two sentences of the pending prompt texts say what code does with a conflict; with the
option they are sent in a wording that fits the rule (`CRITICAL_REPORTED` in
`rounds/conflicts.ts`, `CONFLICTS_REPORTED` in `rounds/analyst.ts`). 9 tests in
`approach.test.ts`, two of them whole runs through the skeleton; 233 tests pass.

### 29.3 A request that names no referent

For "what caused so many casualties in the earthquake" both EBD modes stopped as out of
scope, and the baseline planned a general answer (section 28.8). Approved sentence, added
to step 1 of the planning prompt: "A request that points at something without naming it
("the earthquake", "the new law") is not out of scope when research can still serve the
client: list it under not_stated, and plan for the most likely cases and name them."

Checked on plans (`referent.ts`, 11 plans, $0.02): that question and two others of the kind
("why did the bridge collapse", "how much does the surgery cost") are planned for the likely
cases in 7 of 7 plans; a request for a poem and "Are the mortgage rates from my earlier
message still current?" still stop, in 4 of 4.

### 29.4 Wording for a plan of key questions

The sections that the conflict checker and the round analyst get about the plan were
written for life-cycle steps with short parts (section 19). For a plan made in one call
they are sent in terms of key questions: `CONFLICT_QUESTIONS_SECTION` and
`ANALYST_QUESTIONS_SECTION`, and the two messages label the items "Key questions of the
main part". A key question is met when findings answer it, also with a no; it is refuted
only when what it takes for granted did not happen or does not exist. New text, on the page
of section 29.1. The other modes get the standing sections unchanged (tests).

### 29.5 Live check (one run, with searches)

`npm run check-strategy` with the settings of section 29.1, without rule 2 of section 29.2,
which was built after this run. Question: "How did Thomas Edison's invention of the
telephone change communication?", the question of the live check of section 27.7, so the
two runs can be set side by side. Record: `local/checks/20261119-222907-ebd-haiku-45abc8-e46b`.

| | Default options (section 27.7) | The one approach |
|---|---|---|
| Required contract checks passed | 11 of 11 | 11 of 11 |
| Planning | 3 calls, 38 s | 1 call, 11 s |
| Round 1 | 3 researchers, 5 key questions | 4 researchers, 15 key questions |
| Researchers, rounds, searches | 6, 2, 37 | 6, 2, 43 |
| Strategy calls, and their output tokens | 7, 33,300 | 6, 23,800 |
| Seconds | 274 | 243 |
| Cost | $0.50 | $0.58 |
| Report: words, pages cited | 1,497, 42 | 2,163, 69 |
| Recorded problems | none | none |

- **The plan.** Four main parts with 14 key questions: who invented the telephone, changes
  in everyday communication, Edison's own telephone work, and disputed and limited effects.
  "Thomas Edison invented the telephone" was marked check; "The telephone changed
  communication" was taken as given.
- **Round 1.** Four researchers; the check led the brief on who invented the telephone.
  Every key question was judged answered, and the claim was contradicted in this round.
  The report opens "Edison did not invent the telephone."
- **Disagreements.** Five between sources, none critical, none researched again.
- **Follow-up.** The round analyst raised a necessary goal (the state of telephone
  communication as of 2026) and a completing one (news gathering). Both got a researcher.
  The first found none of what it asked for and wanted a second try when the researchers
  ran out; the second is the case rule 2 was then written for.
- **One reply rejected.** The first reply of the conflict checker named the same source on
  both sides of two conflicts and was sent back; that cost 33 seconds.
- One run of one question; it shows that the approach runs, not how good it is.

### 29.6 The final test: rules fixed before any run

Written on 2026-11-19, before the sealed questions are drawn, and approved by the lead
the same night. `final_spec.py` makes the question files and the experiment specs; its
second stage reads the sealed questions and must not be run before the test.

- **Two stages.** Stage 1 (`final_spec.py planted`): the 4 planted questions, both arms.
  They are not sealed, so stage 1 is also the live check of the program as tested: rule 2
  of section 29.2 and the first-round rule of section 30 were built after the live run of
  section 29.5. Between the stages only a defect of the program may be fixed (a failed
  run, a contract problem, a rule that does not act as specified), and the approach's runs
  of stage 1 are then made again; the reports of stage 1 are not read for quality before
  stage 2 has run. `final_check.py` reads the records of stage 1 and lists every
  departure from the rules of sections 29.2 and 30 without reading a report; tried on the
  live run of section 29.5 it reports that run's one known departure, the detail that got
  a researcher before rule 2 existed. Stage 2 (`final_spec.py sealed`) reads the 12
  sealed questions, and both arms run on them.

- **Arms.** The baseline, and the one approach with the number of researchers the baseline
  used on the same question (`matchResearchersTo`), so that both spend the same research.
  One run for each cell, Haiku, the same day.
- **Questions.** 12 real queries: draws 15 onward of seed 20261118, unread until the test.
  And 4 questions with a planted problem, each with the one thing a report must say:

| Question | The report must say |
|---|---|
| Why did the Chernobyl nuclear accident happen in 1989? | That the accident happened in 1986, not in 1989 |
| How did Alexander Fleming's discovery of insulin change the treatment of diabetes? | That Fleming did not discover insulin, and that Banting (with Best, at Toronto, 1921 to 1922) did |
| How tall is Mount Everest? | 8,848.86 m as announced by Nepal and China in 2020, and that at least one earlier figure differs, and why |
| Do I need a visa to visit the United Kingdom for a week? | That the answer depends on nationality, covering visitors who need a visa and visitors who need only an electronic travel authorisation |

- **Measures.** (1) Blind pairs by the Opus judge in both orders on the 12 real queries; a
  question counts for an arm only when both orders name it. (2) The planted problems: the
  judge's checklist instruction on the one planted point; the point counts as said at
  score 1 (stated with a source), and a score of 0.5 (stated without a source, or in
  part) is reported apart. (3) Cost, time and strategy calls from the records. (4) The
  platform's citation check. (5) Checklist items covered by the report, with the items that
  only ask what a term is counted apart (section 28.8).
- **Scoring scripts.** `judge-final.ts`: the judge of 2026-11-18 (Opus 5.5, effort medium)
  with its two instructions word for word; the script stops if they differ, saves each
  result when it arrives and asks again only for what is missing. `final_stats.py` prints
  the five measures and applies the rules below. Both were tried without cost on the saved
  runs of 2026-11-18, where `final_stats.py` gives that test in these terms: approach 3,
  baseline 7, not decided 2, cost +46% with 5.7 researchers a run against 3.6.
- **What counts.** The approach is kept if, on the pairs, the baseline does not win 10 or
  more of the questions decided; it says at least as many of the four planted points as the
  baseline; and it costs no more than 15% above the baseline. It is shown to be better only
  if it wins 10 or more of the questions decided.
- **What the test can show.** With 12 questions only a split of 10 to 2 or wider can be
  told from chance (audit of the judge of 2026-11-19, `local/ebd-heldout/judgecheck.py`), so the likely outcome is
  "no difference shown", which the first criterion counts as kept.
- **Cost.** About $9 to $11 of Haiku calls. For the judge about 500,000 input and 40,000
  output tokens of Opus, about $2.80 at $4 and $20 per million tokens: the pass of
  2026-11-18 used 477,783 and 35,696 tokens for 54 calls, and this one has 56. The first
  version of this line said 300,000 input tokens, which was too low. About $12 to $14 in
  all.

### 29.7 Open points

- **What the round analyst calls a missing main part.** In the live run it was a side topic
  that the search could not serve. With equal researcher numbers the follow-up rarely gets
  a researcher, so the test will say little about it.
- **Rule 2 of section 29.2 has still not run with searches.** In all 16 runs of the test
  the approach used every researcher it was allowed in the first round, so no follow-up
  round took place (section 31.4). The first-round rule of section 30 acted as specified
  in all 16.
- **`not_stated`** still lists the client's purpose in some plans, which changes nothing.
- **The consolidation of section 29.1 waits for the test.**

### 29.8 Spend

About $0.73 of Haiku calls: the live run $0.58, plans for the check of section 28.8 on the
sealed questions $0.13, the check of section 29.3 $0.02. No Opus call.

## 30. The first round with the baseline's number of researchers (2026-11-19, after the approval)

The final test gives the approach the researchers the baseline used on the same question
(section 29.6): 3 to 5 on the 12 runs of 2026-11-18, 3.6 on average. Every check of the
one-call plan so far ran with 6. This section records what a replay with fewer researchers
showed, and the rule that was changed for it. Code only; no text sent to a model changes.

### 30.1 The replay

`local/ebd-heldout/matched-round1.ts`, no model call and no search. The 72 saved one-call
plans of the revised wording (section 28.8; 24 questions, 3 plans stopped as out of scope)
are replayed by their shape: the main parts with their need and number of key questions,
and the claims with their verdicts. Each runs as a whole run in the skeleton with 1 to 6
researchers; the researchers answer every key question, the conflict checker finds
nothing, and the round analyst judges every key question answered and proposes nothing. A
plan has 3.72 main parts (2.10 necessary, 1.62 completing) and 15.5 key questions; 28 of
the 69 have a claim to check.

| Researchers | Used a run, before and after | Main parts asked key question by key question | Main parts asked as one question | Plans with a part never researched |
|---|---|---|---|---|
| 3 | 2.71, 2.99 | 73%, 81% | 68, 48 | 2 (with a researcher unused), 0 |
| 4 | 2.94, 3.72 | 79%, 100% | 54, 0 | 0, 0 |
| 5 | 3.19, 3.72 | 86%, 100% | 37, 0 | 0, 0 |
| 6 | 3.72, 3.72 | 100%, 100% | 0, 0 | 0, 0 |

- **Before.** With 3 to 5 researchers a run sent 2.7 to 3.2 of them in the first round, and
  14% to 27% of the main parts were asked as one question while a researcher was kept
  back. With nothing to follow up, that researcher was never used. In 2 plans with 3
  researchers a planned part was left for a later round and then, by rule 2 of section
  29.2, never asked, with a researcher free.
- **The cause.** `spread` (section 7) takes a completing goal out of a shared brief only
  while one researcher stays for a second try of each necessary goal served in the round.
  Second tries are rare: in the 12 runs on new questions of 2026-11-18, 2 of 44 necessary
  planned goals got one, and one of the two was answered by it.
- **With 6 researchers nothing changes**, which is why the live run of section 29.5 and
  the plan checks did not show it.

### 30.2 The rule

1. **In the first round of a plan of key questions, every researcher of the round goes to
   a main part of the answer, and none is kept for a second try** (`partsFirst` in
   `briefs.ts`, used by `plan` in `index.ts`):
   - as many researchers as parts, or more: each part has a researcher to itself, and
     the researchers left over wait for the follow-up of section 29.2;
   - fewer researchers than parts, more than necessary parts: each necessary part has a
     researcher to itself, and the completing parts share the researchers left;
   - no more researchers than necessary parts: the necessary parts share the
     researchers, and a completing part is asked as one question in a brief that has
     room for one more key question, and not at all when none has.
   The check of the claims leads the brief of a necessary part, as before; when no brief
   has room it leads the brief that asks the fewest key questions all the same.
2. **After the first round, a main part of the plan that no researcher was asked about is
   not a detail**: with `strictFollowUp` it is still served while researchers last
   (`isUnaskedPart` in `state.ts`). With rule 1 this can only happen when a round has
   fewer researchers than the plan has parts and no brief has room.

The other planners keep their first round: every earlier test passes unchanged. In the
replay of section 29.2 on the 17 saved runs the totals are the same, and one follow-up
brief holds one more goal, a planned step that had not been asked.

### 30.3 What remains

- **With 1 or 2 researchers a full plan does not fit.** With 1, the necessary parts and
  the check are asked and 69 of the 112 completing parts are not; with 2, 3 are not. This
  is the case of a question that the baseline's planner takes for a single fact and the
  plan gives 3 or 4 parts.
- **Run with searches in the final test** (section 31): in all 16 runs the first round
  was as specified. Measured cost with equal researchers: 5% above the baseline (2% on
  the 12 real queries, 22% on the 4 planted questions), against the estimate below.
- **Expected cost with equal researchers, from the records.** A researcher costs $0.097
  in the baseline's runs and $0.085 to $0.092 in EBD's; the strategy's own calls cost
  $0.004 a run for the baseline and $0.012 to $0.032 for EBD. With the same number of
  researchers the approach should cost between about 9% less and 3% more than the
  baseline, inside the 15% of the rule of section 29.6.

8 tests in `approach.test.ts` (19 there, 243 in all). No spend.

## 31. The final test: the one approach against the baseline (2026-11-19, night)

Run on the user's go, by the rules of section 29.6, with the code of sections 29 and 30.
Records: `local/ebd-heldout/final-planted-20261120-022344` and
`final-sealed-20261120-023629` (the stamps are in UTC), `judge-final-results.json`,
`final-stats.out`. Every run can be stepped through in the run viewer
(`local/viewer/index.html`, 32 runs); 31 have a Langfuse trace, because the tracing
service was started during stage 1 (the first baseline run has none, two have a part).

### 31.1 Result by the rules

| Rule fixed beforehand | Result | |
|---|---|---|
| The baseline does not win 10 or more of the questions decided | baseline 5, approach 4, not decided 3 | met |
| The approach says at least as many planted points as the baseline | 4 of 4 against 2 of 4 in full | met |
| The approach costs no more than 15% above the baseline | $5.35 against $5.07, 5% more | met |
| Shown to be better: 10 or more wins | 4 wins | not shown |

**The approach is kept. No difference between the two is shown** (exact sign test on the
9 questions decided: p = 1.0). All 32 runs ended ok, and the judge's 56 calls all
returned a usable reply.

### 31.2 The measures

| | Baseline | The one approach |
|---|---|---|
| Blind pairs, 12 real queries, both orders: overall | 5 | 4 (3 not decided) |
| ... coverage | 4 | 3 (5 not decided) |
| ... support (how carefully claims are stated and cited) | 4 | 0 (8 not decided) |
| ... conflicts (disagreements and false assumptions) | 2 | 3 (7 not decided) |
| ... usefulness | 4 | 4 (4 not decided) |
| Planted points, of 4: in full, in part | 2, 2 | 4, 0 |
| Researchers a run | 3.19 | 3.19 |
| Cost a run, 16 runs | $0.317 | $0.334 |
| Seconds a run | 122 | 192 |
| The strategy's own calls a run | 2.0 | 3.8 |
| Report, words | 1,904 | 1,750 |
| Cited statements not bound to a source (platform check) | 29 of 487 | 34 of 450 |
| Checklist items of the real queries covered, of 53 | 47 | 47 |
| ... mean score: items that only ask what a term is, other items | 0.57, 0.85 | 0.50, 0.87 |
| ... items flagged as wrong by the judge | 2 | 0 |

- **Planted points.** Both arms stated all four. The judge gave the baseline half marks
  on two: its Chernobyl report opens "The Chernobyl accident occurred on 26 April 1986,
  not 1989." with no citation on that sentence, and its Everest report explains the older
  figure in one sentence marked as an inference, where the approach lists the earlier
  surveys in a table. Both reports on the two false premises open with the correction.
- **The judge's quotes.** Each of its 102 quotes is in the report it was taken from.
- **The two orders** named opposite reports on 3 of the 12 questions.

### 31.3 Question by question

The claims are those the plan marked for a check; "given" claims are left out.

| Question | Claim checked, verdict | Outcome | The judge's reason, in short |
|---|---|---|---|
| how changes to funding have impacted the nhs | funding changed; it had an impact: both supported | not decided | The orders disagree |
| why income inequality is good for the economy | "Income inequality is good for the economy": contradicted | baseline | A fuller account of the case for inequality and of the evidence against it |
| why do engineering students drop out | none | baseline | More ground: gateway courses, differences between groups, how the rate is defined |
| how did america change ww1 | the United States changed the war: supported | approach | Only it covers the effects at home: the draft, the Espionage and Sedition Acts, women's work |
| why do people oppose affirmative action | none | not decided | The orders disagree |
| how structured literacy instruction differs from typical literacy practices | "typical practices are what most classrooms use": contradicted | approach | Says what typical practice is today, with survey evidence, and questions that it is still the majority |
| how did darwin explain the differences in traits? | Darwin offered an explanation: supported | baseline | More focused on Darwin's own account; the approach answers "an odd yes/no framing" and drifts into modern figures |
| why are there no laws yet to protect people from sociopaths | "There are no laws yet": contradicted | baseline | Covers more: definition, prevalence, legal mechanisms. The approach is shorter and built around the false premise (usefulness went to it in both orders) |
| how does economics play a role in african american culture | none | approach | Ties economics to more cultural forms |
| why is eugenics considered unethical | "considered unethical by most people, scholars and institutions today": unsettled | baseline | The approach "spends much of its length attacking a premise the question never states" |
| how did early american colonies contribute to the growth of capitalism? | none | approach | The baseline's report is cut off in mid-sentence and has no conclusion |
| why do people declare bankruptcy | none | not decided | The orders disagree |

### 31.4 What the records show

- **Checking the question's own premise cost the approach.** The plan marked a claim for
  a check in 7 of the 12 real queries. In 6 of the 7 the claim is the question's own
  premise, not a fact of its own such as a date or a name: in three it only restates the
  question (the NHS, the war, Darwin), and in three it is the opinion the question starts
  from (inequality, the laws, eugenics). On those last three the evidence contradicted the
  claim or left it open, the writer was told so, and the report was framed by that
  verdict: the inequality report is titled "Evidence Contradicts the Claim That
  Inequality Boosts Growth", the report on the laws opens "The question's premise is not
  supported", and the eugenics report has a section on "the disputed premise" and ends on
  it. The judge preferred the baseline on all three; the baseline's reports on the first
  two correct the premise as well, inside a fuller answer. In the eugenics plan the claim
  says more than the question does ("by most people, scholars and institutions today"). The seventh (literacy) is a claim the question does not make either; there the
  judge counted the correction for the approach. The plan checks before the test had
  measured the sort only on questions written for it (section 28.8), not on real queries
  of the form "why is X considered Y".
- **Where the approach won**, its plan had a main part that the baseline's left out (the
  effects at home, what typical practice is today, more cultural forms). The fourth win
  is against a report that the platform's writer cut off at its output limit (21,000
  tokens; "writer: report output truncated" in the record). Without it the count is 3 to 5.
- **Time.** The approach spent 86 seconds a run in its own calls. 12 of its 60 replies
  were rejected by the code checks and asked again: 9 of the 16 first replies of the
  conflict checker (the same source on both sides of a conflict, or a statement longer
  than one sentence), 2 plans and 1 round analysis.
- **The rules of sections 29.2 and 30.** `final_check.py` on the 16 runs of the approach:
  no departure. It used every researcher it was allowed in the first round in every run
  (3.19 a run, as the baseline), each necessary part asked key question by key question
  and the check riding in a brief. So no run had a follow-up round, and rule 2 of section
  29.2 was not exercised. Of the 93 conflicts recorded, 29 were marked critical; the 19 of
  them that decide no claim got no goal and were left to the writer (who is told about
  three a run at most), and the 10 that decide a claim were tied to its check. One
  problem was recorded: in one run a researcher wrote sections without a goal ID, which
  were mapped to every goal of its brief.
- **Cost.** 2% above the baseline on the 12 real queries and 22% on the 4 planted
  questions, where its researchers searched more (64 searches against 57) and its own
  calls weigh more in a small run.

### 31.5 What the test does and does not show

- It shows that with the same number of researchers and 5% more money, the approach's
  reports are not told apart from the baseline's by this judge on 12 real queries, and
  that it states a planted problem at least as fully.
- It does not show that the approach is better. On real queries the one criterion with a
  clear split is support, 4 to 0 for the baseline.
- The limits of section 29.6 hold: 12 questions, one run for each cell, a model as the
  judge, no fact checked and no human reading. The test of 2026-11-18 had other
  questions, so the two can only be set side by side roughly: then 3 to 7 with 58% more
  researchers and 46% more cost, now 4 to 5 with the same researchers and 5% more cost.

### 31.6 Open after the test

- **The consolidation of section 29.1** was made after one commit of the state before
  (section 32).
- **Not changed, for a later decision** (each needs new questions to confirm, and the
  sealed set is used): the sort of the question's own premise on "why is X Y" questions,
  and the wording of a checked claim, which must not say more than the question; the
  conflict checker's first replies, rejected in 9 of 16 runs; the writer's output limit,
  which is the platform's.

### 31.7 Spend

Haiku $10.42 (baseline $5.07, approach $5.35) and the Opus judge $2.79 (558,112 input and
27,956 output tokens): $13.21, against the $12 to $14 named.

## 32. Consolidation: the one approach is the strategy (2026-11-19)

On the lead's word after the final test ("Commit, then consolidate"). The state before is
commit `5b84010`. This section says what was removed, what the code does instead, and how
it was checked that the approach itself did not change.

### 32.1 What went, and what the code does in its place

| Option removed | The code now always | Section |
|---|---|---|
| `init` | Makes the first plan with the environment analysis in one call | 28 |
| `extend`, `completeMap` | Has no problem extension: the plan's main parts are its map | 19, 22, 28 |
| `premiseSort` | Takes the sort of the claims from the plan; there is no premise sorter | 27, 28 |
| `partQuestions` | Asks a main part by its key questions, at most six key questions a brief | 21 |
| `premiseRides` | Asks the check of the claims in the brief of a main part | 26, 27 |
| `stepsFirst` | Sends a researcher that would sit idle to a main part first | 27, 30 |
| `focusFollowUp` | Follows up only what the answer depends on: a goal mostly unanswered, an undecided claim, at most two necessary new goals a round | 20 |
| `mainPartsFirst` | Serves the necessary goals for content before a goal that settles a disagreement | 25 |
| `uncitedParts` | Lets the round analyst raise a main part that no finding mentions | 26 |
| `strictFollowUp` | Sends a later researcher only to a main part or a claim: a disagreement that decides no claim is reported, a detail is not researched | 29 |
| `leanGuidance` | Tells the writer only what the notes do not show | 20 |
| `extraRound` | Has no round of details after a complete run; the option had no effect any more | 11, 29 |

- **Modules removed:** the problem extension (`extension.ts`) and the premise sorter
  (`premises.ts`) with their prompts, and in the kept modules every wording and rule that
  was used only with an option off: the sections on life-cycle steps of both round
  prompts, the earlier end of the section on critical conflicts, the sentence that asked
  for a citation, the full guidance for the writer, the brief for a life-cycle step.
- **Modules added:** `analysis.ts` holds the structure of the analysis, which the request
  analysis defined and the rest of the strategy reads, and the plan of last resort;
  `map.ts` holds the map helpers that the extension module held. Nothing in them is new.
- **State:** `extraRoundServed`, and `replaced` and `questions` of the map, are gone. The
  run viewer reads records with and without them, and names the goals of the plan "main
  part" in runs of this approach and "life-cycle event" in earlier records.
- **Kept:** `conflicts` and `newGoals`, which the platform's comparison experiment sets
  (`experiments/compare.json`), and the limits (section 13).

### 32.2 The approach did not change

Checked with no model call, before and after, by the same scripts (`local/ebd-heldout/`):

| Check | Result |
|---|---|
| `golden.ts`: the 16 runs of the final test and the live run of section 29.5 replayed step by step, with the recorded replies and the recorded researcher results. Compared: every brief, stop and rationale; the goals, conflicts, map and problems after every step; every log line; the checks and a fingerprint of the input of every model call; the writer's material, outline and guidance | The two files are identical |
| The same replay against the records: for the 16 runs of the test, the decisions and the writer's guidance of the record | Equal in 16 of 16 |
| `matched-round1.ts`: the 69 saved plans as whole runs with 1 to 6 researchers (414 runs), every allocation listed | The two outputs are identical |
| The test that pins the approved texts: the planner's prompt, the whole prompts of the conflict checker and the round analyst, the fixed words of a brief, the writer's lines | The same fingerprints |
| `prompt-page.ts`: the page of texts generated again | Each of its 17 text blocks is on the approved page word for word |

### 32.3 Tests

196 tests in 20 files pass (243 in 22 before). The tests of the extension and of the premise
sorter went with their modules, and so did every test of an option switched off. The tests
of the follow-up rules, of the key questions of a brief and of whole runs were rewritten for
the one approach: `focus.test.ts` (32), `parts.test.ts` (9), `strategy.test.ts` (5, whole
runs through the skeleton with the plan in one call, the two ablation switches among them).
`fixtures.ts` holds the two worked analyses those tests build their states from.

### 32.4 What is left

- **The request analysis (`request/`).** The strategy no longer calls it, and nothing in
  the repository imports it. It is still in the folder because scripts of Lab 3 on the
  lead's machine, which are not in the repository, import it. Whether it moves to those
  scripts or goes is the lead's decision.
- **No run with searches since.** The replays show the same decisions on recorded runs; a
  live `check-strategy` run of this code has not been made.
- **The scripts of the tuning period** in `local/ebd-heldout/` that replay the earlier
  planner or set a removed option (`plans.ts`, `oneplan.ts`, `replay-*.ts`, `referent.ts`)
  run at commit `5b84010`, not on this code. `golden.ts`, `matched-round1.ts`,
  `prompt-page.ts`, `judge-final.ts`, `final_stats.py` and `final_check.py` run on it.
- **What the test showed** (sections 31.4 and 31.6) is unchanged by the consolidation: the
  sort of the question's own premise, the conflict checker's rejected replies, and the
  follow-up rules that have hardly run with searches.

## 33. Why the approach is not better than the baseline, and what could make it so (2026-11-19, after the test)

On the lead's question: "Why the EBD strategy is still not better than the baseline? What
could we try to further improve it? Do research and try to exploit the deep search
strategy". This section reads the records of the final test again (33.1), sets them beside
what published deep-research systems rely on (33.2), reports three cheap trials (33.3 to
33.5), and lists what is proposed, with the texts (33.6) and a staged plan (33.7). Section
33.9 has the result of the plan's second step, the judge of the test on rewritten reports.
**Nothing in the strategy was changed.** Every trial ran from scripts in
`local/ebd-heldout/`. The lead approved the texts on 2026-11-20; section 34 applies them.

### 33.1 What the records show

The 12 real queries of the final test, means a run (`why.py` and its follow-up counts, no
model call):

| | Baseline | Approach |
|---|---|---|
| Researchers | 3.42 | 3.42 |
| Searches | 25.9 | 25.9 |
| Pages read (a researcher may read 4) | 1.0 | 0.9 |
| Cited findings in the notes | 153 | 152 |
| Findings that give a number; a year | 70%; 48% | 70%; 46% |
| Distinct links in the notes; of them scholarly or official sites | 120; 42 | 121; 41 |
| Words of notes handed to the writer | 9,232 | 9,259 |
| Guidance to the writer, in words; outline | 25; none | 190; none |
| Report: words | 2,093 | 1,913 |
| Report: distinct links; of them scholarly or official sites | 53; 20.4 | 49; 16.4 |
| Rounds of research after the first | 0 | 0 |
| The strategy's own calls | 2.0 | 3.75 |

1. **The research is the same.** Both sides get the same number of researchers, and a
   researcher is the platform's: its prompt, its 8 searches and 4 page reads. What a
   strategy writes into a brief differed (the approach's instructions have 145 words, the
   baseline's none; the baseline's source hints name a source in 74% of cases, the
   approach's in 13%), and it changed neither how much the researchers found nor from
   which kinds of sources.
2. **The approach's own loop did not run.** The experiment gives the approach the number
   of researchers the baseline used, and the rule of section 30 sends all of them in the
   first round. In all 12 runs none was left. After the first round the approach still
   spent 74 seconds a run (conflict checker 44, round analyst 30) and found 8 necessary
   things to research further in 6 of the 12 runs, and 6 details; nobody could be sent.
   So the test compared two first-round plans and two inputs to the writer. Looking for
   conflicts and following them up, which is the part of EBD that the baseline has no
   counterpart for, was paid for and could not act.
3. **The plans trade depth for breadth, and the trade comes out even.** A small model
   labelled every key question by what it asks for, without knowing who wrote it (section
   33.5). Of the baseline's key questions 66% ask for part of the answer itself; of the
   approach's, in the plans of the test, 55%. The approach puts 39% on what surrounds the
   answer (earlier and later history, debates, proposals, what the client can do), the
   baseline 27%. The approach is less direct on the questions it won (by 15 points) as
   much as on those it lost (by 10), so directness does not tell wins from losses. The
   judge's reasons show both sides of the trade. The four questions the approach won, it
   won with a part around the answer that the baseline lacked (the effects at home, how
   common typical practice is, more cultural forms, the effect on the wider world). On the
   five it lost, the baseline went deeper into the answer itself: it "sets out the
   pro-inequality case more fully", covers "group differences, gateway courses and rate
   definitions in more depth", is "more focused on Darwin's own account, citing more
   primary sources", "defines the construct clinically, shows prevalence and risk
   evidence". On the Darwin question the baseline's three researchers took the causes of
   variation, selection, and heredity; the approach's took Darwin's account, the check
   with the objections to it, and what genetics says today. With the same 15 key
   questions, more breadth is less depth.
4. **The check of the question's own claim.** A claim was checked in 7 of the 12 queries.
   There the approach won 2, lost 4, with 1 undecided; on the 5 without a check it won 2
   and lost 1, with 2 undecided. Where the verdict fell on the very thing the question
   asks to have explained, the writer was told "The evidence contradicts this; say so
   plainly early in the report" (inequality, the laws) or "do not present it as
   established" (eugenics), and the report argued with the question: "mostly argues
   against the premise, treats the positive case more thinly"; "spends much of its length
   attacking a premise the question never states". The baseline had no check, found the
   same evidence and wrote "supports it only in narrow conditions" inside a full answer.
   Where the checked claim was a side assumption (literacy: that typical practice is what
   most classrooms use), the correction counted for the approach. On the four planted
   questions the approach stated every planted point in full and the baseline two of
   four; the baseline stated the other two as well, less fully.
5. **The writer got the same notes and wrote less from them.** The approach's reports are
   9% shorter and cite 4 fewer scholarly or official sources, of the same 41 or 42 that
   the notes hold. Support is the one criterion with a clear split in the test, 0 to 4.
   Section 33.3 shows that what the approach tells the writer is part of the cause.
6. **Definitions are left out by both sides.** Of the 21 checklist items that a side did
   not cover in full, 11 ask what a main term of the question means ("What is
   bankruptcy?"). On those 14 items the judge gave the baseline 0.57 and the approach
   0.50, against 0.85 and 0.87 on the other 39. The judge's reasons name a missing or thin
   definition on 4 of the 12 questions.
7. **An internal label reached a report.** The eugenics report says "does not treat A1 as
   established". The conflict checker had written "assumption A1" into a statement, and
   the code that cleans the writer's guidance removes the labels of findings and conflicts
   but not those of claims.
8. **The size of the test.** 4 to 5 with 3 undecided on 12 questions is no difference; a
   gain of one or two questions could not be seen (section 31.5).

### 33.2 What published deep-research systems rely on

Read on 2026-11-19 (list at the end of this document).

| What the systems rely on | Source | Here |
|---|---|---|
| Spending more on search, reading and iteration. "Token usage by itself explains 80% of the variance" of results on a browsing benchmark; multi-agent systems "work mainly because they help spend enough tokens" | Anthropic | Equal by the rule of the comparison: same researchers, same researcher. The largest lever is switched off for both sides |
| A loop of search, read and reason, with a queue of open questions, until the answer is found or the budget is used | Jina, "DeepSearch" | Inside a researcher (8 searches). Between researchers only in the approach, and there it had no researcher left (33.1, point 2) |
| A draft or outline made first, revised as evidence comes in, and used to aim the next searches, in up to 20 steps | TTD-DR; WebWeaver | Neither side sends the writer an outline. Tried on the writer's side (33.3) |
| Briefs with an objective, an output format, guidance on sources and tools, and boundaries | Anthropic | Both sides. The baseline names sources more often, with no measured effect on the findings |
| Reading pages in full, not search snippets | Jina; survey in `research/` | 0.3 pages a researcher. Tried (33.4) |
| A final report written in one pass from all findings works better than sections written apart | LangChain Open Deep Research | The platform's writer does this; a strategy cannot change it |
| Reports judged on comprehensiveness, depth, instruction-following and readability, and on whether citations support their sentences | DeepResearch Bench | The judge of section 31 reads the text only; no citation is opened |
| Agents fail less at understanding the task than at integrating evidence, verifying it and re-planning | FINDER and DEFT | The approach's extra work goes into understanding the request, where models seldom fail; integration is the platform's writer; its verification (conflicts) is the one criterion it led, 3 to 2 |

What this says about the result: published gains come from more search and more
iteration, not from a better first plan at equal spend. At equal spend the approach can
gain in three places only: how the researchers are divided over the question, what is done
with a part of them after the first round, and what the writer is told.

### 33.3 Trial 1: what the writer is told

Each report of the 12 real queries was written again by the platform's writer from the
saved notes, with a different outline and guidance (`rewrite-final.ts`; no search, no
strategy call; `rewrite_stats.py`). Means of 12 reports:

| Writer's input | Words | Distinct links | Scholarly or official |
|---|---|---|---|
| Baseline, as recorded | 2,093 | 53.2 | 20.4 |
| Baseline, written again (how much the writer varies by itself) | 2,099 | 53.9 | 20.0 |
| Approach, as recorded | 1,913 | 49.3 | 16.4 |
| Approach, written again with the recorded guidance (the control) | 1,801 | 44.2 | 15.8 |
| Approach, notes only, no guidance | 1,947 | 48.0 | 16.7 |
| Approach, outline of the plan's parts and a reduced guidance | 1,925 | 49.8 | 18.0 |
| The same, with a line on sources and coverage | 2,073 | 51.0 | 19.1 |
| The same, with one more line on the question's main terms | 2,264 | 56.8 | 20.7 |

The reduced guidance leaves out the reading of the question unless the plan lists a term
with several meanings (it does in 9 of these 12 runs, see 34.1), the assumed purpose, time
frame and place, and the line for a claim the evidence leaves open; a contradicted claim
is to be corrected in one or two sentences before the question is answered as asked; the
lines for critical disagreements stay. The outline is the names of the plan's main parts
that were researched. The texts are in 33.6.

- Against the control, the row with the line on sources adds 272 words (standard error
  56), 6.8 distinct links (2.0) and 3.2 scholarly or official sources (1.0). Taking the
  guidance away adds 146 words (77).
- With the reduced guidance the eugenics report opens "Eugenics is considered unethical
  mainly because ...", with no argument about the premise and no internal label.
- One of the 12 reports of the seventh row was cut off at the writer's output limit, as
  one of the baseline's was in the test; none of the last row was. The limit is the
  platform's.

Two cheap screens by Haiku, with the judge's own instructions word for word. Pairs
(`screen-final.ts`): each variant against the baseline's recorded reports, both orders,
two samples, 48 judgments a row; the share of the decided judgments that prefer the
approach.

| Approach's reports | Overall | Coverage | Support | Conflicts | Usefulness |
|---|---|---|---|---|---|
| As recorded | 68% | 58% | 56% | 58% | 78% |
| The control | 55% | 49% | 46% | 54% | 74% |
| Outline and reduced guidance | 56% | 46% | 50% | 59% | 65% |
| ... with the line on sources and coverage | 57% | 48% | 83% | 75% | 39% |
| ... and the line on the main terms | 77% | 77% | 76% | 77% | 61% |

Checklist coverage (`cover-screen.ts`; mean score of an item, 0 to 1). On the recorded
reports Haiku gives the Opus judge's score on 88 of 106 items.

| Reports | All 53 items | 14 definition items | 39 other items | Opus judge, all |
|---|---|---|---|---|
| Baseline, as recorded | 0.75 | 0.61 | 0.81 | 0.77 |
| Approach, as recorded | 0.72 | 0.50 | 0.79 | 0.77 |
| Approach, outline, reduced guidance, line on sources | 0.75 | 0.54 | 0.83 | not judged |
| ... and the line on the main terms | 0.82 | 0.71 | 0.86 | not judged |

**Reading.** From the same notes, the last input gives reports that cite as many scholarly
or official sources as the baseline's (20.7 against 20.4), cover more of the checklist in
the cheap check (0.82 against 0.75), and are preferred in 33 of the 43 decided judgments of
the pair screen, against 24 of 44 for the control. The limits are plain: one rewrite of
each report; Haiku as the reader, which is lenient to the approach (the Opus judge decided
4 to 5 on the first row) and may favour a longer report although told not to (2,264 words
against 2,093); the first two rows differ by the writer's own variation alone; and the 12
questions are development data. The lines on sources and on terms are advice any strategy
could give the writer; they are not EBD's analysis. **It is a reason for the paid check of
33.7, not a result.** The paid check was made on 2026-11-20 (33.9): the Opus judge has
these reports level with the baseline's, so the preference in Haiku's pair screen did not
hold.

### 33.4 Trial 2: telling researchers to read pages

Three briefs recorded in the test were run again by the platform's researcher, with
searches, once as recorded and once with one more line of instructions that asks to open
the pages behind the most important figures before writing (`deepread.ts`).

| | As recorded | With the line |
|---|---|---|
| Searches; pages read (3 researchers) | 24; 2 | 20; 6 |
| Cited findings; of them with a year | 124; 48% | 98; 73% |
| Distinct links; of them scholarly or official | 96; 48 | 70; 39 |
| Cost | $0.33 | $0.29 |

The researchers read three times as many pages at no more cost (one of the three read
none either way: the pages could not be opened), and wrote fewer findings from fewer
sources, more of them dated. Three briefs, one run each. A judge that reads only the
report would see fewer sources, not better-read ones. **Not proposed** until facts are
checked by a person or a tool.

### 33.5 Trial 3: the planner's rules, at plan level

Passages of the planning prompt were reworded (33.6, B) and passed to the strategy's
planning call from a script; the accepted prompt is untouched. Plans were made twice for
each question with each wording, and the strategy's own code turned each into the briefs
of three researchers (`plancheck.ts`, `plancheck_stats.py`; no search). The recorded
columns are the briefs both sides sent in the test.

| 12 real queries | Baseline, recorded | Approach, recorded | Present wording | All four passages | Claims and definition only |
|---|---|---|---|---|---|
| Key questions that ask for part of the answer itself | 66% | 55% | 56% | 61% | 54% |
| ... that check a claim | 4% | 4% | 9% | 5% | 5% |
| ... that ask about what surrounds the answer | 27% | 39% | 33% | 30% | 38% |
| Plans with a question on a definition | 5 of 12 | 3 of 12 | 5 of 24 | 8 of 24 | 7 of 24 |
| Checklist items the plan asks a researcher about | 79% | 83% | 75% | 82% | 81% |
| Plans that check a claim | no such step | 7 of 12 | 14 of 24 | 10 of 24 | 12 of 24 |
| Key questions sent | 15.8 | 15.3 | 14.0 | 14.1 | 14.2 |

On 18 questions written with a false specific fact, a true one or none (the 16 of section
27.6 and two earlier ones) and the two planted questions with a false fact, the three
wordings do the same: the false fact is checked in 24 of 24 plans and nothing is checked
in 12 of 12 plans of a general question.

What each passage did:

- **A claim says no more than the wording.** In the four plans of the two reworded
  variants the eugenics claim reads "Eugenics is considered unethical", with nothing
  added; in one of the two plans of the present wording it reads "by ethicists and other
  authorities".
- **"How one thing changed another" takes only that for granted.** Fewer plans check a
  claim (10 and 12 of 24 against 14): "the United States changed the war in some way" and
  "funding changed the NHS" are taken as given.
- **The direct answer gets the most room.** 4.4 points more direct key questions
  (standard error 3.3). Small, and by point 3 of 33.1 a trade and not a gain: the parts
  around the answer are what won the approach its four questions.
- **One key question asks for the main terms' definitions.** Not followed: a definition
  question in 7 or 8 of 24 plans against 5. The prompt's own example has none and says so.

**These are measures of plans, not of reports.**

### 33.6 Proposed, not applied

**A. What the writer is told** (`synthesis.ts`). Tested as the last row of the tables of 33.3.

| | Now | Proposed |
|---|---|---|
| Outline | None | The names of the plan's main parts that were researched, the necessary ones first, at most five |
| Reading of the question | "The question was read as: ..." whenever a claim is not supported or a term has several meanings | Only when a term has several meanings |
| A claim the evidence contradicts | "The question presupposes: "..." The evidence contradicts this; say so plainly early in the report." | "The question takes for granted: "..." The evidence in the notes contradicts this. Say so in the opening paragraph, in one or two sentences with the source. Then answer the question the client asked as fully as the notes allow: the correction is not the subject of the report." |
| A claim the evidence leaves open | "The question presupposes: "..." The evidence neither confirms nor contradicts this; do not present it as established." | No line |
| What the client did not state | "The client did not state these; they were assumed. Mention them only where they change the answer:" with purpose, time frame and place | No block |
| New line on terms | None | "Early in the report, say what the question's main terms mean and how they are defined or measured, in a sentence or two each, with the source the notes give." |
| New line on sources | None | "Cover each part of the outline. In each part, build first on the strongest sources in the notes: official statistics, peer-reviewed studies and primary documents before commentary. Give each figure with its year and what it measures, and say where the evidence is thin or disputed." |
| A claim's label in a conflict statement ("assumption A1") | Reaches the writer | Replaced by the claim's words (code, no text) |

**B. The planner's rules** (`environment.ts`). Tested at plan level only (33.5).

| | Now | Proposed | Stand |
|---|---|---|---|
| A claim's wording | "List each claim that the wording treats as settled, as a full sentence, and give it a verdict ..." | "List each claim that the wording treats as settled, as a full sentence that says no more than the wording does ("is considered" does not become "is considered by most people"), and give it a verdict ..." | Proposed: it did what it should, at no cost |
| Taken as given | "A question that asks whether, which, what or how much takes at most a possibility for granted: given." | The same, followed by: "A question that asks how one thing affected, changed or contributed to another takes for granted only that it did so in some way: given." | Proposed: fewer checks of a claim that only restates the question |
| The direct answer | "the question itself: the part that answers it most directly comes first;" | "the question itself: the direct answer comes first and gets the most room. Split it into its main kinds (the kinds of reasons or causes, the steps of an explanation, the fields of an effect, the sides of a comparison) and give each kind a part of its own: at least two of the first three parts answer the question itself;" with "The other sides get a part of their own only where the answer depends on them; otherwise a side is one key question inside a part that answers the question." | Not proposed now: a trade between depth and breadth |
| Definitions | "... a definition that the answer needs is one key question of the part that needs it." | "But a reader must be told what the question is about: one key question of the first part asks what the question's main terms mean and how they are defined or measured." | Did not work as wording. Would need the plan to name the main terms and the code to add the question |

**C. Decisions without a text.**

- **The analysis after the first round when no researcher is left.** Today it costs 74
  seconds a run and can only add lines for the writer. Either a researcher is kept for it
  (below), or the round analyst's call is skipped when nobody can be sent and only the
  conflict checker runs, for the writer's lines on critical disagreements.
- **Dividing the same researchers as two and one.** The plans have about two necessary
  parts. The first round could research those, and the last researcher could go where the
  evidence of the first round points: a necessary gap, a claim, or else the best
  completing part. This is the loop of search, read and reason between researchers, at
  equal spend, and the one way the approach's own analysis can act under the rule of the
  comparison. It is untested, and the follow-ups raised in the test were of mixed worth
  (two of the eight led further from the question), so it comes after A.
- **The rule of the comparison.** With equal researchers the loop can run only if the
  approach divides them differently. A comparison at an equal ceiling, with cost reported
  beside quality, is the other form; the experiment file is the platform owner's, and
  equal researchers was the lead's decision of 2026-11-05.
- **Not proposed:** the line that tells researchers to read pages (33.4); naming sources
  in the hints, which the baseline does more and which changed nothing measurable.

### 33.7 A staged plan

| Step | What | Cost |
|---|---|---|
| 1 | The lead decides on the texts of A and on the first two rows of B. **Done 2026-11-20: approved** | none |
| 2 | The Opus judge, both orders, on the 12 rewritten reports of the last row of 33.3 against the baseline's recorded reports: does the writer's input alone move the judge that decided the test? With the control judged too, the writer's own variation is taken out. **Done 2026-11-20 without the control (33.9): no net gain** | $1.60, or $3.20 with the control; $1.68 spent |
| 3 | A and the two rows of B applied; one live run of the platform's strategy check; then four of the old questions with searches, approach only (two it lost, two it won), judged against the baseline's saved reports. Catches a regression before the larger spend; cannot show a gain | about $0.40 and $1.90 |
| 4 | Confirming test as in section 31: 12 newly drawn real queries and the 4 planted questions, both sides, the same rules | about $13 |

The 12 queries of the final test are development data now. A gain on them does not count
as a result.

### 33.8 Spend

The trials: about $2.45 of Haiku, no judge: 72 rewritten reports about $0.66 (from the
writer's recorded cost a call), five pair screens $0.45 and the coverage screen $0.06, six
researcher runs with searches $0.62, 207 planning calls $0.51 and their labels and
scores $0.13. Step 2: $1.68 of the Opus judge. About $4.13 in all.

### 33.9 Step 2: the judge of the test on the rewritten reports (2026-11-20)

The lead approved the texts of 33.6 and asked for step 2 ("approve the texts and run step
2"). Approval is step 1 of 33.7; applying the texts is step 3 and has not been started.

**The run.** `judge-rewrite.ts defs`: the judge of the final test (Claude Opus 5.5, effort
medium) with its pair instruction word for word, on the 12 reports of the last row of 33.3
against the baseline's recorded reports, both orders, blind, 24 calls, none failed. The
calls are traced in the local Langfuse (tags `judge`, `rewrite`, `defs`); the verdicts
with their reasons are in `judge-rewrite-defs.json` and `judge-rewrite-defs.out`
(`judge_rewrite_stats.py`). $1.68 (375,698 input and 8,799 output tokens), against $1.60
named. The rule for reading the result was written into the script before the run.

| | Recorded reports (the test) | Rewritten reports |
|---|---|---|
| Questions decided, both orders agreeing: approach, baseline, not decided | 4, 5, 3 | 3, 2, 7 |
| ... on coverage | 3, 4, 5 | 4, 2, 6 |
| ... on support | 0, 4, 8 | 1, 1, 10 |
| ... on conflicts | 3, 2, 7 | 0, 1, 11 |
| ... on usefulness | 4, 4, 4 | 3, 6, 3 |
| Single judgments of 24, overall: approach, baseline, tie | 11, 13, 0 | 11, 11, 2 |
| ... coverage | 10, 10, 4 | 12, 7, 5 |
| ... support | 2, 13, 9 | 3, 8, 13 |
| ... conflicts | 7, 9, 8 | 9, 6, 9 |
| ... usefulness | 10, 11, 3 | 7, 13, 4 |
| The report shown second is preferred | 15 of 24 | 17 of 22 decided |
| Questions on which the two orders disagree | 3 of 12 | 7 of 12 |

**By the rule fixed beforehand** the result reads "worth the confirming test": the approach
has more decided questions than the baseline (3 to 2) and does not lose support on more
questions than it wins it (1 to 1). The rule was set too low for what it has to bear: the
margin is one question (sign test p = 1.0), and in single judgments the two sides are
level, 11 to 11, where they stood at 11 to 13.

**What moved.**

- The baseline's decided wins fell from 5 to 2: inequality, dropout, the laws and eugenics
  became undecided, Darwin stayed, and affirmative action is new. The approach's fell from
  4 to 3: the war and the colonies stayed, bankruptcy is new, and literacy and African
  American culture became undecided.
- **Support:** the gap of the test (0 to 4) is gone in decided questions and smaller in
  single judgments (3 to 8, from 2 to 13).
- **Coverage** rose. The reasons mention a definition in 14 of the 24 judgments, most
  often to the approach's credit ("defines income inequality and its measures", "defines
  key terms", "defines eugenics explicitly").
- **Usefulness** fell. In about ten of the 24 reasons the baseline is called more focused
  or more direct, or the approach's report is said to wander: "spends much of its length
  on implementation details that wander from the question", a "long federal-policy section
  drifts from the question".
- The eugenics report is no longer faulted for arguing with the question, and one order
  credits it with handling "the question's presumption". No internal label is in any of
  the 12 reports. The Darwin report is faulted as before for what was researched (modern
  mutation rates, nothing on sexual selection): the writer cannot repair a plan.

**The order.** The judge preferred the report shown second in 17 of the 22 decided
judgments, and the two orders disagree on 7 of 12 questions. The closer the two reports
are, the more questions the position decides.

**The cheap screens.** Haiku's pair screen had these reports preferred in 33 of 43 decided
judgments; the Opus judge has them level. Haiku's coverage check pointed the right way
(coverage rose). So Haiku's pair screen is no guide to this judge's overall verdict, and
its row in 33.3 promised a gain that is not there.

**Reading.** What the writer is told changes where the two sides differ, not how often the
approach is preferred. The texts remove the approach's known faults (support, the argument
with the question, missing definitions) and cost directness. They do not make the approach
better than the baseline by this judge. A confirming test of these texts alone would most
likely show the two sides level again.

**Open after step 2.**

- **The texts.** Applied on 2026-11-20 without that sentence (section 34). When this was
  written they were approved and not applied. The judge's one recurring complaint
  about the rewritten reports is wandering into side parts, which the first sentence of
  the new line on sources asks for ("Cover each part of the outline."). Whether the texts
  go in as approved or without that sentence is the lead's decision; neither form has been
  judged apart from the other.
- **Where a difference could still come from.** Not from the first plan or the writer's
  input at equal research. Left are the approach's own loop at equal spend (33.6, C), and
  the kind of question the approach's check was built for: a false fact, sources that
  disagree, an answer that depends on who asks. The test had four of those (stated in full
  4 of 4 against 2 of 4); a larger set would show whether that difference is real.

## 34. The texts of section 33.6 applied (2026-11-20)

On the lead's words: "approve the texts and run step 2", and after the result of that step
(33.9) "Commit consolidation first, then proceed with 2 recommended steps". The
consolidation is commit `6fc5f1c`. The first recommended step was to apply the texts with
one sentence removed; this section records it. The second is the test of section 35.

### 34.1 What changed

| | Where | On the 17 recorded runs, replayed |
|---|---|---|
| **Outline:** the names of the plan's main parts that the notes cover, the necessary ones first, at most five; one part alone is no outline | `buildOutline` | 16 runs get an outline; none did |
| **Reading of the question:** only when the plan lists a term with several meanings | `buildGuidance` | In 12 runs, from 14 |
| **A claim the evidence contradicts:** "The question takes for granted:", the claim, and "The evidence in the notes contradicts this. Say so in the opening paragraph, in one or two sentences with the source. Then answer the question the client asked as fully as the notes allow: the correction is not the subject of the report." | `TAKEN_FOR_GRANTED`, `CONTRADICTED_LINE` | 6 runs, in place of "say so plainly early in the report" |
| **A claim the evidence leaves open:** no line | | 1 run loses "do not present it as established" |
| **Assumed purpose, time frame and place:** no block | | Gone from all 17 |
| **New line on terms:** "Early in the report, say what the question's main terms mean and how they are defined or measured, in a sentence or two each, with the source the notes give." | `TERMS_LINE` | In all 17 |
| **New line on sources:** "Build first on the strongest sources in the notes: official statistics, peer-reviewed studies and primary documents before commentary. Give each figure with its year and what it measures, and say where the evidence is thin or disputed." | `SOURCES_LINE` | In all 17 |
| **A claim's label in a conflict statement:** the label and the words that introduce it ("assumption A1", "the client's assumption A2") become "the question's claim" | `withoutClaimLabels` | 1 run; 10 mentions in the 590 conflicts of 80 saved runs |
| **Planner, a claim's wording:** "... as a full sentence that says no more than the wording does ("is considered" does not become "is considered by most people"), ..." | `PLAN_SYSTEM`, step 3 | Plans come from the record in a replay |
| **Planner, taken as given:** "A question that asks how one thing affected, changed or contributed to another takes for granted only that it did so in some way: given." | `PLAN_SYSTEM`, step 3 | |

- **The sentence left out.** The line on sources was approved with "Cover each part of
  the outline." in front. The judge then faulted the rewritten reports for wandering into
  side parts (33.9), and the lead took the recommendation to leave the sentence out. The
  form without it has not been judged.
- **The reading of the question stays in most runs.** The plan lists a term with several
  meanings in 12 of the 16 runs of the test ("NHS", "America", "drop out", "eugenics",
  "capitalism"), where the planning prompt asks for one only for "an abbreviation, or a
  word with several unrelated meanings". So this change removes the line in 2 runs, not in
  most, and the judged reports of 33.9 were written with the line in 9 of 12. Section 33.3
  said the reading was left out; that was true of the rule, not of most runs. Left as it
  is: the planner's listing of terms is a matter of its own.
- **Not changed:** the line for a checked claim that got no verdict, the lines for
  critical disagreements, and the notes handed to the writer.
- **"The question's claim"** are three fixed words that the code now writes in place of a
  label. The saved statements go on to say what the claim is ("... says most people
  consider eugenics unethical"), so the claim's own words are not repeated.

### 34.2 What the checks show

With no model call (`golden.ts`, `texts_check.py`):

| Check | Result |
|---|---|
| The 16 runs of the final test and the live-check run, replayed before and after: every brief, stop, rationale, goal, conflict, map entry, log line and call check | Equal in 17 of 17 |
| The notes handed to the writer | Equal in 17 of 17 |
| The writer's outline and guidance, against the input the judged reports of 33.9 were written from | Equal in 12 of 12, but for the sentence left out and the claim's label |

The planner's two passages, with the prompt exactly as applied (`plancheck.ts plan
applied`, 68 plans, $0.17): the false fact is checked in 24 of 24 plans, the true one in 4
of 4, nothing in 12 of 12 plans of a general question; on the 12 real queries a claim is
checked in 12 of 24 plans (14 before), and the plans keep their size (3.75 parts, 13.9 key
questions with three researchers). The eugenics claim reads "Eugenics is considered
unethical." in both plans.

### 34.3 Tests

199 tests in 20 files pass (196 before). New: the outline from the researched parts
(`parts.test.ts`), a claim named in words and never by its label (`focus.test.ts`), and
the three lines that are no longer sent (`approach.test.ts`). The test that pins the
approved texts has the planner's new mark and the writer's new lines; the marks of the
conflict checker, the round analyst and the briefs are unchanged.

### 34.4 What this does and does not do

- By the judge of the test (33.9) these texts do not make the approach preferred. They
  remove faults that the judge named: the lost criterion of support, the report that
  argued with the question, the missing definitions, the label in a report.
- The first run with searches of this code, and of the consolidated code, is the test of
  section 35.

## 35. The planted-problem test (2026-11-20)

The second recommended step of 33.9, on the lead's word ("proceed with 2 recommended
steps"); the lead approved the 12 questions and the run before it started. On ordinary
questions the two sides are level (sections 31 and 33.9). This test asks whether the
approach is better where its checks were built to matter: a false fact in the question,
sources that give different figures, an answer that depends on who asks. The final test had
four such questions (stated in full 4 of 4 against 2 of 4).

### 35.1 The test, fixed before the runs

**Questions** (`planted_spec.py`, `planted2-questions.json`): twelve, four of each kind,
written on 2026-11-20 before any run on them. None of them and none of their subjects was
used in the development of the strategy or in an earlier test. Each has the one thing a
report must say.

| | Question | The report must say |
|---|---|---|
| 1 | How did the Wright brothers' first powered flight in 1908 change transportation? | The flight was on 17 December 1903, not in 1908 |
| 2 | How did Galileo's invention of the telescope change astronomy? | Galileo did not invent the telescope: it appeared in the Netherlands in 1608, and he built his own in 1609 |
| 3 | Why was Pompeii destroyed by the eruption of Mount Etna? | The volcano was Mount Vesuvius (AD 79), not Mount Etna |
| 4 | Why did the space shuttle Challenger break apart during re-entry in 1986? | It broke apart shortly after launch, not during re-entry |
| 5 | How long is the Nile? | About 6,650 km, and that sources give different lengths (6,853 km) because of where the river is taken to start and how it is measured |
| 6 | How many countries are there in the world? | The number depends on who is counted: 193 members of the United Nations, and at least one case counted differently |
| 7 | How many people died in the 1918 influenza pandemic? | A range of estimates and not one number (17 to 50 million, some up to 100 million), and why they differ |
| 8 | How many people died in the bombing of Dresden in February 1945? | About 25,000 (the historians' commission of 2010), and that much higher figures were long claimed, and where they came from |
| 9 | What is the legal drinking age? | It depends on the country; several countries with different ages; not one country alone |
| 10 | How many days of paid annual leave am I entitled to? | It depends on the country; several with different rules; not one country alone |
| 11 | When does the school year start? | It depends on the country; starts that differ; not one country alone |
| 12 | Do I need a prescription to buy antibiotics? | It depends on the country: required in some, sold without one in many others; not one country alone |

The full wording of each point is in the questions file; the judge gets that wording.

**Sides.** The baseline, and the strategy as it stands (the one approach with the texts of
section 34), with the number of researchers the baseline used on the same question. One
run for each cell, Haiku, the same day, traced in Langfuse.

**Scoring.** The judge of the final test (Claude Opus 5.5, effort medium) with its coverage
instruction word for word (`judge-final.ts`), each report against its one planted point: 1
stated with a source, 0.5 stated without a source or in part, 0 missing.

**How the result is read.** A question counts for a side when that side has 1 and the other
has less. "Shown": the two-sided sign test on those questions gives p < 0.05, which needs at
least six for the approach and none for the baseline (or eight to one). "Points the same
way": more for the approach, short of that. "No difference": as many or fewer.

**Stages.** Questions 1, 5 and 9 run first (stage a) and are the first run with searches of
the code of sections 32 and 34. Between the stages only a defect of the program may be
fixed; the reports of stage a are not read for quality before stage b has run.

**Cost named beforehand:** about $6 to $7 (24 runs about $5.30, the judge about $1).

**What the test cannot show.** It has no question with a true fact that looks doubtful, so
it does not measure whether the approach "corrects" what is right. Twelve questions show
only a large difference. The planted points are simple; both sides stated all four in the
final test, and differed in how fully.

### 35.2 Result

Stage a: 6 runs ended ok, the check of the run records (`final_check.py`) found no fault,
and stage b followed unchanged. All 24 runs ended ok. Records: `planted2-a-20261120-062842`
and `planted2-b-20261120-064014` in `local/ebd-heldout/`, the judge's scores in
`judge-planted2.json` (`planted2_stats.py`), the runs with their traces in
`local/viewer/index.html`.

| | Baseline | Approach |
|---|---|---|
| Planted point stated in full (score 1) | 11 of 12 | 12 of 12 |
| Stated in part (0.5); missing (0) | 1; 0 | 0; 0 |
| In full, a false fact in the question | 4 of 4 | 4 of 4 |
| In full, sources that give different figures | 4 of 4 | 4 of 4 |
| In full, an answer that depends on who asks | 3 of 4 | 4 of 4 |
| Researchers used | 38 | 33 of the 38 allowed |
| Searches; pages read | 267; 24 | 216; 17 |
| Cost of the 12 runs | $3.63 | $3.10 |
| Seconds a run | 114 | 173 |
| Words a report | 1,616 | 1,729 |
| The strategy's own calls a run | 2.0 | 3.58 |

**By the rule fixed beforehand: "points the same way", and in substance no difference.**
One question counts for the approach and none for the baseline (sign test p = 1.0). That
one is the question on antibiotics, where the judge gave the baseline's report a half mark.
Read side by side, the two reports say much the same: both open with "yes" for nearly every
country covered, and both report sales without a prescription; the baseline's names 15
countries and files those sales under weak enforcement. With the four planted questions of
the final test the count is 16 of 16 against 13 of 16, three questions for the approach and
none against (p = 0.25).

### 35.3 What the records show

- **The approach's own steps found every planted problem, and so did the baseline's
  reports without such steps.** The plan marked the false fact for a check in 4 of 4
  questions and the check came back contradicted in all four. On the drinking age the plan
  put down "One legal drinking age applies throughout the place the question concerns" and
  the evidence contradicted it. All four questions that depend on who asks have what the
  client did not state listed in the plan. The conflict checker recorded 65 disagreements
  in the 12 runs, 19 of them critical. The baseline has none of this: its researchers
  found the true date, the range of figures and the differences between countries, and the
  platform's writer, whose own rules ask for both sources when notes disagree, wrote them
  down. The approach makes explicit what the baseline does without saying so, and the
  reports come out the same on the planted point.
- **Fewer researchers.** The approach stopped as complete with researchers left in 3 runs
  (the drinking age 3 of 5, Galileo 3 of 4, the school year 2 of 4), which is why it cost
  15% less here. On the four questions that depend on who asks, the baseline's reports name
  more countries (11 to 16 of a list of 17, against 6 to 13).
- **A follow-up round ran for the first time in a test:** on annual leave, where a claim
  left open got the one researcher left. Two runs stopped for lack of researchers with
  something necessary still open.
- **The program.** 5 of the approach's 43 replies were rejected by the code checks and
  asked again. In 2 runs a researcher wrote sections without a goal label, and the code
  mapped them to every goal of the brief; this is the recorded problem of section 31.4,
  not a defect, and nothing was changed between the stages.
- **The writer's input of section 34 in live runs:** an outline in 11 of 12 runs, the
  block for a contradicted claim in 5, the reading line in 4, and no report cut off. The
  writer's calls use more output tokens than the baseline's (11,200 against 8,900 on
  average, 17,800 at most, of the platform's limit of 21,000).

### 35.4 Reading

- The second place where a difference was looked for shows none. With this model and the
  platform's researchers, a plain plan and the platform's writer already state a planted
  problem of this kind, so twelve simple planted points cannot tell the sides apart. The
  4 of 4 against 2 of 4 of the final test was two half marks on four questions.
- Three results now stand side by side, all with the same researchers on both sides: on
  ordinary questions the sides are level (section 31, and section 33.9 with the new
  writer's input), and on planted problems they are level (this section). The approach
  costs 5% more on the real queries and 15% less here, and takes about half as long again.
- What the approach has that the baseline has not is on record, not in the judged report:
  the claims of the question with a verdict, the disagreements between sources, the plan's
  parts and what was left open. A judge of reports does not measure that; a person who has
  to check a run does (the run viewer).
- Not tested: a question with a true fact that looks doubtful, harder planted problems,
  and the quality of these 24 reports as a whole (no pair was judged).

### 35.5 Spend

Haiku $6.73 (I had named $5.30; the baseline used 3.2 researchers a question here, 2.5 on
the four of the final test) and the Opus judge $0.70 (145,857 input and 6,059 output
tokens): $7.43, against "about $6 to $7" named. The plan check of section 34.2 was $0.17.
Since the final test: $11.73.

## 36. Would a weaker model separate the two sides? A probe of the planning step (2026-11-20)

On the lead's question: "If we use other weaker model, will EBD and baseline show
difference?". No test was run; this section holds what the records of section 35 say and a
probe of the planning step alone (`weaker-probe.ts`, 120 plans and 120 small reads, $0.40,
no search).

### 36.1 Why the sides are level with this model

In the test of section 35, on all four questions with a false fact, the baseline's planner
had corrected the fact from its own knowledge in its first call, before any search: "the
first powered flight was on 17 December 1903 at Kitty Hawk", "Galileo did not invent the
telescope", "Vesuvius, not Mount Etna", "about 73 seconds after liftoff ... not during
re-entry". The baseline has no rule that asks for this. The approach has one: a specific
fact in the question is marked for a check from the wording alone, whatever the model
believes (section 28). With Claude Haiku 5.5 the model does by itself what the approach's
rule demands, so the rule changes nothing.

### 36.2 The probe

Both sides' own planning calls were made with three settings of the model, on 6 questions
of the two tests whose false fact is well known and on 6 questions written for the probe
with a specific fact that no model can know to be true or false (a small town, firm or
study; they were not researched). A small call, which does not know the side, then read
how each plan treats the fact: corrects it itself, asks a researcher to check it, or takes
it for granted.

| Plans that take the fact for granted | Baseline | Approach |
|---|---|---|
| Haiku 5.5, effort medium, as in every test (24 plans a side) | 0 | 0 |
| Haiku 5.5, effort low (24 plans a side) | 0 | 0 |
| Haiku 4.5, the previous Haiku, no thinking (12 plans a side) | 3 | 0 |

- **Less effort on the same model changes nothing.** The baseline's planner still corrected
  the well-known false fact in 11 of 12 plans and asked for a check in the twelfth, and it
  asked for a check of every fact it could not know.
- **With the previous Haiku the baseline's planner lets a fact through in 3 of 12 plans.**
  On Challenger it wrote the assignment "Establish the immediate physical cause of the
  structural failure and re-entry breakup sequence", and on two of the facts it could not
  know (a ferry line, an airline) it went straight to the reasons. The approach's plan
  marked the fact for a check in 12 of 12 plans, as its rule says.
- **The approach's planning call still works on the previous Haiku:** every plan passed
  the code checks, with 1.33 calls a plan on the six known questions (1.08 with Haiku
  5.5) and no plan of last resort.

### 36.3 What this says and does not say

- A weaker model is where a difference can open, and it would open on questions with
  something wrong in them, at the planning step. The approach's checks are a rule; the
  baseline's are the model's habit, which a weaker model has less of.
- It is a probe of plans, one plan a cell for the previous Haiku. Three of twelve against
  none is not a result (Fisher's exact test, p = 0.22). A researcher sent after "the
  re-entry breakup" may still find that there was none, and the writer may still correct
  it; with Haiku 5.5 they did. On ordinary questions nothing here suggests a difference.
- Further down, a model too weak for the approach's own calls would break the approach
  first (its plan is one large structured reply). The previous Haiku is not that weak.

### 36.4 What a test would take

- **The model.** Claude Haiku 4.5 is the only weaker Claude model still served. It has no
  effort setting and a context of 200,000 tokens, so it needs a profile of its own in the
  platform's model file, which is the platform owner's; the project's models are Haiku 5.5
  and Luna (`AGENTS.md`). Luna has not been run here (no key).
- **The cost.** Its tokens cost ten times those of Haiku 5.5 ($1 and $5 a million against
  $0.10 and $0.50); the search fee is the same, and it is most of a run's cost today
  (483 searches made $4.83 of the $6.73 of section 35). A run would cost about $0.80
  against $0.28: about $20 for the 12 planted questions on both sides, or about $13 for 8
  questions with a false or unknowable fact, the kind on which the probe saw the gap.
- **The likely outcome,** from the probe: an edge for the approach on such questions that
  twelve questions would not prove.

## 37. A weaker model: the planning probe on OpenAI models and a side run on GPT-5 nano (2026-11-20)

The lead added an OpenAI key with 5 dollars on it and asked: "Can we get an idea of how
baseline and EBD perform differently in other weaker models?" Done with at most $2.78 of
the 5 dollars. It is a side run: the project's models stay Haiku 5.5 and Luna
(`AGENTS.md`), and the platform's model file was not changed; the profile for GPT-5 nano is
added to the running process by `local/ebd-heldout/nano-run.ts`.

**Models and prices** (OpenAI's pricing and model pages, read 2026-11-20). GPT-5 nano:
August 2025, knowledge to May 2024, deprecated and still served, $0.05 and $0.40 a million
tokens, with web search in the Responses API. GPT-6 Luna: the project's second model, $0.10
and $0.50. Web search costs $0.01 a call on both, as with Anthropic.

### 37.1 The planning probe on five model settings

The probe of section 36, with two OpenAI models added (`weaker-probe.ts`,
`weaker_probe_stats.py`; $0.08 of OpenAI). Six questions with a well-known false fact and
six with a fact no model can know; one or two plans a cell; a small call reads how the plan
treats the fact.

| Plans that take the fact for granted | Baseline | Approach |
|---|---|---|
| Claude Haiku 5.5, effort medium (as tested) | 0 of 24 | 0 of 24 |
| Claude Haiku 5.5, effort low | 0 of 24 | 0 of 24 |
| OpenAI GPT-6 Luna | 0 of 12 | 0 of 12 |
| Claude Haiku 4.5 | 3 of 12 | 0 of 12 |
| OpenAI GPT-5 nano | 0 of 12 | 2 of 12 |

- **Luna plans like Haiku 5.5:** the baseline's planner corrected all six well-known false
  facts itself and asked for a check of all six it could not know. Nothing here suggests a
  difference between the sides on the project's second model.
- **The two weaker models fail on opposite sides.** With Haiku 4.5 the baseline's plan lets
  a fact through. With GPT-5 nano the approach's plan does: it marked the claim for a check
  in 3 of 6 plans on the known facts, because the model does not follow the long rule of
  the planning prompt, while the same model still corrected the fact in the baseline's
  short notes. One plan a cell; the run below, with one more plan for each question, came
  out the other way for the approach (6 of 6 marked), which shows how much a single plan
  varies on this model.

### 37.2 The side run on GPT-5 nano

The six questions of the two earlier tests whose planted fact is false and well known, both
sides, at most three researchers a run, one run a cell (`nano_spec.py`, folders
`nano-a-20261120-160959` and `nano-b-20261120-162011`, `nano_stats.py`). The planted point
was scored with the judge's coverage instruction answered by Haiku (`planted-screen.ts`),
and the two reports on which the sides differ were read by hand. With Haiku 5.5 both sides
had stated all six (sections 31 and 35).

| GPT-5 nano, six questions | Baseline | Approach |
|---|---|---|
| Planted point stated in full | 4 | 6 |
| Stated in part; missing | 1; 1 | 0; 0 |
| The plan dealt with the false fact | 5 of 6 (corrected in the planner's notes) | 6 of 6 (marked for a check; contradicted in all six) |
| Runs that ended ok | 6 of 6 | 6 of 6 |
| Seconds a run | 175 | 326 |
| Cost a run, at most | $0.25 | $0.21 |
| Words a report; links; links not in the notes | 1,396; 37; 2 | 1,374; 39; 5 |
| The strategy's replies rejected by the code checks | none recorded | 11 of 24 |
| Runs in which the round analysis had to be repaired by the code | | 5 of 6 |

- **Where the sides differ.** On the Wright brothers the baseline's planner did not notice
  the wrong year, and its report opens "The Wright brothers' 1908 powered flight
  demonstrated that controllable, practical flight was feasible"; 1903 appears once, in
  passing. Its researchers' notes do give 1903; the writer followed the question. The
  approach's report opens "The Wright brothers' first powered flight is best supported by
  credible sources placing the event on December 17, 1903". On Galileo the baseline's
  report says only that its focus is "not on the instrument's original invention by
  others"; the approach's gives the patent application of 1608.
- **Why.** The approach's check is a rule and its writer's line is an instruction: the plan
  marked the fact in every run, the check came back contradicted, and the weaker writer
  did what the line said. The baseline depends on the planner noticing and on the writer
  acting unasked, and this model does both less reliably than Haiku 5.5.
- **The approach's own steps strain on this model.** 11 of its 24 replies were rejected by
  the code checks and asked again (2 of 20 on these questions with Haiku 5.5). In 5 of 6
  runs the round analysis cited evidence labels that do not exist and the code fell back
  to its repaired judgments. The conflict checker found 1.3 disagreements a run, against 6
  to 7 with Haiku 5.5. The verdicts on the claims were still right in all six. A run took
  almost twice the baseline's time.
- **Both sides write weaker reports on this model:** fewer words and links than with Haiku
  5.5 (1,400 and 37 against 1,700 and 62 for the baseline), links that are not in the
  notes (2 and 5 in six reports, none with Haiku 5.5), and most researchers hit the cap of
  8 tool calls.

### 37.3 Reading

- This is the first setting in which the approach shows the advantage it was built for:
  with a weaker model, a false fact in the question is corrected in 6 of 6 reports against
  4 of 6. It fits the explanation of section 36: Haiku 5.5 does by itself what the
  approach's rule demands, and a weaker model does not.
- It is an indication. Six questions, one run each, one kind of problem, a cheap scorer:
  two questions for the approach and none against (sign test p = 0.5).
- The advantage comes from the approach's simplest steps (mark the fact, check it, tell the
  writer). Its heavier steps (the round analysis, the conflict check) are the ones that
  break on a weak model, and they are held up by the code's repairs.
- First runs with searches of the approach on the OpenAI adapter: 6 of 6 ended ok. Luna
  itself has not been run; the platform's `check-strategy` run with `--model luna` is
  still to be made.

### 37.4 Spend

OpenAI: the probe $0.08, and the 12 runs at most $2.70 (tokens $0.35; 235 web search calls
if every search and page open is billed, $2.35; the platform's ledger, which counts
searches only, says $1.82). At most $2.78 of the 5 dollars. Anthropic: about $0.03 for the
reader of the plans and the scorer.

## 38. The final state (2026-11-20)

On the lead's word to finalize the work on EBD's search behaviour, bring the documents in
line with the final implementation, record the tests, and leave the repository ready for
the rest of the team.

### 38.1 What is final

- **The code** of sections 32 and 34: the one approach, with the writer's input and the
  two planner passages approved on 2026-11-20. After that only comments and two test
  titles were brought in line with it. 199 tests pass and the project's type check is
  clean (197 tests since section 39, which took out the two tests of the switches).
- **Acceptance.** The platform's `npm run check-strategy` on the committed code, with the
  project's fixed question and up to 6 researchers:

| | Claude Haiku 5.5 | OpenAI GPT-6 Luna |
|---|---|---|
| Contract checks passed | 11 of 11 | 11 of 11 |
| Main parts planned; researchers used | 3; 3 of 6 | 1; 1 of 6 |
| Stop | complete after the first round | complete after the first round |
| Cost; seconds; words of the report | $0.19; 129; 1,514 | $0.04; 64; 907 |

  It was the strategy's first run on Luna. Luna planned one main part for the fixed
  question, and one researcher answered it.
- **The documents.** The user guide (`README.md`) describes the final strategy, its
  records and its limits. `evaluation/README.md` holds every test against the baseline
  with its method, results and limits, and the folder holds the data: the questions, the
  judge's output, the 70 reports of the last three tests, the printed tables and the
  scripts. This document keeps the full record; its head says which sections still apply.

### 38.2 For the rest of the team

- **Nothing outside `src/strategies/ebd/` was changed** up to this point: against the main
  branch as merged on 2026-11-06, every difference is inside this folder. The one
  exception came after it, with section 39: two platform files, in a commit of their
  own for the platform owner's review.
- **The experiment specs.** The settings that chose a planner or a follow-up rule are
  gone and are rejected when given (section 13). So are, since section 39, `conflicts`
  and `newGoals`, which `experiments/compare.json` set in two of its arms; those two arms
  are taken out of the spec in a commit for the platform owner's review.
- **Run records.** Goals, disagreements, findings, the question's claims with their
  verdicts and the writer's input are recorded as before, so a tool that reads them keeps
  working. Gone from the state: `map.replaced`, `map.questions` and `extraRoundServed`.
  The roles of the strategy's model calls are `environment_analyst`, `conflict_checker`
  and `round_analyst`. `synthesis.json` now has an outline in most runs.
- **`request/`** is not called by the strategy and nothing else in the repository uses
  it. It is kept because scripts of an earlier lab on the lead's machine import it.
- **To run it:** the user guide. **To change it:** the last section of the user guide;
  the texts sent to a model are approved by the lead and pinned by a test.

### 38.3 What is open

- **The comparison on Luna** has not been run; Luna has acceptance runs only.
- **EBD's own loop at equal spend.** With the baseline's number of researchers all of
  them go out in the first round, so finding conflicts and following them up has hardly
  run in a test. Sending two researchers first and the third where the evidence points
  would let it act; it is untested (section 33.6).
- **The evaluation.** No person has rated the reports and no fact was checked; twelve
  questions show only a large difference (`evaluation/README.md`, section 6).
- **Smaller matters:** the conflict checker's first replies that fail the code checks;
  the planner listing a term with several meanings more often than its prompt asks for
  (section 34.1); the writer's output limit, which is the platform's.
- **For the platform owner:** the change of `experiments/compare.json` and of the example
  in the module guide that goes with the removal of the two switches (section 39).

## 39. The two switches removed (2026-11-20)

The lead: "I do not think we should keep the switches. Is there any case the output is
better while conflict checker and newgoals are turned off?" Until now `conflicts: false`
turned the conflict checker off and `newGoals: false` kept only the goals of the first
plan. They were made so that what each part contributes could be measured by a run
without it (the conflict checker is a call of its own for that reason, decision D-D of
section 18), and they stayed at the consolidation (section 32) because the comparison
spec `experiments/compare.json` has an arm for each.

### 39.1 What the records say

- **No test compared a report made with a switch off against one made with it on.** Of
  the 169 runs of the strategy recorded on the lead's machine, two had a switch off: one
  live run for each switch on 2026-11-05, with the planner of that time, and no record of
  a comparison. No run of the comparison spec's two arms is on record there.
- **A replay with each switch off**, with no model call: the 28 runs of the strategy in
  the final test and in the planted-problem test, replayed by `golden.ts` on commit
  `a4e5cb2`, the last with the switches, and compared by `switch_check.py`. A replay
  feeds a run's recorded replies and researcher results back in, so it says what the
  strategy would have done as long as the same researchers are sent. Neither switch
  touches the first round, and only one of the 28 runs had a researcher after it. Table:
  `evaluation/tables/switches-replay.txt`.

| | New goals off | Conflict checker off |
|---|---|---|
| Runs compared | 28 | 27 |
| Researchers sent to the same goals | 28 of 28 | 27 of 27 |
| The writer gets the same notes and outline | 28 of 28 | 27 of 27 |
| The writer gets the same guidance | 28 of 28 | 10 of 27 |
| The writer is told to correct a claim of the question | The same | The same: 10 runs, the same text |
| What is no longer there | 21 goals proposed by the round analyst, in 15 runs; 10 of them necessary, in 8 runs; none had a researcher | The lines on critical disagreements in 17 runs (28 lines, 1 to 3 a run); the line on evidence to keep apart in 1 run; the record of 153 disagreements, 45 of them critical; 5 goals made to settle one, none of which had a researcher |
| Runs whose end is recorded as "researchers ran out" | 3 instead of 10 | 9 instead of 10 |

- **New goals change no report at the baseline's number of researchers.** In 8 runs the
  strategy asked for a researcher for a proposed goal, and none was left. What the switch
  changes there is the record: it shows what the run would have researched next.
- **The conflict checker gives the writer the lines on disagreements, and it sent the
  only later researcher of the 28 runs.** On the question about paid annual leave, the
  one researcher left after the first round went to settle a disagreement between a
  claim of the question and the findings. The claim stayed unsettled, and both sides'
  reports state the planted point in full. That run cannot be replayed without the
  checker.
- **The conflict checker is the longest of the strategy's own steps.** In the 28 runs it
  takes 40 s of a run's 184 s (22%) and $0.008 of $0.302 (3%); 13 of its 42 replies
  failed the code checks and were asked again. The round analyst takes 24 s and the plan
  17 s. A run of the baseline takes 118 s. So a run without the checker would be about
  40 s shorter.
- **The judge.** On the handling of conflicts and false assumptions the two sides are
  level. In the final test the approach led on 3 questions to 2 with 7 undecided, and
  trailed in single judgments, 7 to 9. With the final writer input it stands at 0 to 1
  with 11 undecided, and leads in single judgments, 9 to 6 (section 33.9). The criterion
  also covers the correction of a false claim, which does not depend on the checker.
- **So:** the records hold no case in which a report is better with a switch off, and
  none in which it is better with it on, because that was never tested. With new goals
  off the writer's input is the same. With the conflict checker off a run is shorter and
  the writer is told less about where the sources disagree.

### 39.2 What changed

- **The strategy.** `conflicts` and `newGoals` are gone from `options.ts` and are rejected
  like any unknown setting. The conflict checker runs after every round with findings, and
  the round analyst's proposals are always considered. The two whole-run tests of the
  switches went, and the test of rejected settings covers the two. 197 tests pass.
- **Two limits no longer take 0.** `maxNewGoalsPerRound: 0` and `maxDepth: 0` stopped
  every new goal, the goals that settle a disagreement included, so they were a second
  way to switch new goals off. Their smallest value is now 1. No test and no spec set
  them to 0. The three rules for dividing researchers (`premiseFirst`,
  `reserveFirstTries`, `spread`) stay as settings: they turn no part off.
- **Nothing changes for a run that did not set them.** The 28 runs replayed before and
  after the removal give the same file, byte for byte.
- **Acceptance after the removal.** The platform's `npm run check-strategy` on the
  committed code (`46fa444`), with the project's fixed question and up to 6 researchers,
  passed 11 of 11 contract checks on both models. Both runs ended complete after the
  first round.

| | Claude Haiku 5.5 | OpenAI GPT-6 Luna |
|---|---|---|
| Contract checks passed | 11 of 11 | 11 of 11 |
| Main parts planned; researchers used | 3; 3 of 6 | 2; 2 of 6 |
| Searches; page reads | 17; 1 | 8; 3 |
| Cost; seconds; words of the report | $0.23; 105; 1,199 | $0.10; 91; 1,108 |

  These runs replace those of section 38.1 in `evaluation/`. $0.33 against about $0.23
  named: Haiku made four more searches than in its earlier run, and Luna planned two main
  parts where its first run had one.
- **The platform's files, for the platform owner's review** (a commit of their own, as
  for the comparison spec itself on 2026-11-05): `experiments/compare.json` loses its two
  arms `ebd-no-conflicts` and `ebd-static`, which would now be rejected, and has 72 runs
  instead of 120; the example entry in `docs/strategy-modules.md` sets a limit instead of
  `conflicts`.
- **What is given up.** A run with a part switched off was the way to measure what that
  part contributes to a report, and the comparison spec planned it (section 16, step 5).
  After the removal it can only be made on commit `a4e5cb2` or earlier, and every run
  pays for the conflict checker. For the comparison at equal researchers the replay of
  39.1 stands in its place as far as the writer's input goes; it does not say whether
  the reports are better.

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

Deep-research systems and their evaluation (read 2026-11-19, section 33.2):

- Anthropic (2025). How we built our multi-agent research system.
  https://www.anthropic.com/engineering/multi-agent-research-system
- Jina AI (2025). A practical guide to implementing DeepSearch/DeepResearch.
  https://jina.ai/news/a-practical-guide-to-implementing-deepsearch-deepresearch/
- Deep Researcher with Test-Time Diffusion (TTD-DR). arXiv:2507.16075.
- WebWeaver: structuring web-scale evidence with dynamic outlines. arXiv:2509.13312.
- DeepResearch Bench: a benchmark for deep research agents. arXiv:2506.11763.
- FINDER and DEFT: a benchmark and a failure taxonomy of deep research agents.
  arXiv:2512.01948.
- LangChain (2025). Open Deep Research. https://blog.langchain.com/open-deep-research

Model judgments:

- Lee et al. (2025). CheckEval. EMNLP.
- Liu, Y., et al. (2023). G-Eval. EMNLP.
- Thakur et al. (2024). Judging the judges. arXiv:2406.12624.
- Xiong, M., et al. (2024). Can LLMs express their uncertainty? ICLR.

Provider documentation (structured outputs, read 2026-10-14):

- Anthropic. Structured outputs: JSON Schema limitations and schema complexity limits.
  https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- OpenAI. Structured Outputs guide. https://developers.openai.com/api/docs/guides/structured-outputs
