# EBD deep research: user guide

EBD is a deep research strategy built on Environment-Based Design. Given a question,
it works out what the question is about and what it takes for granted, turns every
unknown into a research goal, sends researchers after the goals, checks their findings
for disagreements and false assumptions, grows new goals from what it finds, and stops
when every necessary goal is settled. A writer then turns the findings into a cited
report.

This guide says how to run it and how to read what it produces. How it works and why
is in [DESIGN.md](DESIGN.md); the plug-in contract is in
[docs/strategy-modules.md](../../../docs/strategy-modules.md).

## Before the first run

- Node.js 22 and `npm install` at the repository root.
- A `.env` file at the repository root (copy `.env.example`) with the key of the model
  you use: `ANTHROPIC_API_KEY` for Claude Haiku 5.5 (profile `haiku`), `OPENAI_API_KEY`
  for GPT-6 Luna (profile `luna`). The `LANGFUSE_*` keys are optional; with them, every
  model call is also traced to the team's self-hosted Langfuse.
- Every run uses real models and real web searches. A run costs about $0.05–0.70 on
  Haiku.

## Run a question

```
npm run research -- --strategy ebd --model haiku --question "How do heat pumps work in cold climates?" --researchers 6
```

- The question is used exactly as typed.
- `--researchers` is the most researchers the run may send (default 10). Each
  researcher runs one brief with up to 12 web searches and page reads.
- `--options '{"conflicts": false}'` changes a setting (see below).
- `--task ebd` (or `headset`, `flight`, `sleep`) runs one of the fixed test questions.

The run writes its record to `local/runs/<run id>/`; the report is `report.md` there.
To run EBD with contract checks (a run plus the platform's checks of everything the
strategy returned), use
`npm run check-strategy -- --strategy ebd --model haiku --task ebd`. Its records go
to `local/checks/`.

## What happens in a run

| Step | Who | What it does |
|---|---|---|
| Plan | Request analyst (a model) | Reads the question; lists its objects, the claims it takes for granted, its time, place and purpose; writes the research goals, each with what a full answer must contain |
| Sort | Premise sorter (a model) | For each claim the question takes for granted: check it as a fact of its own (a date, a number, who did what, a particular event or its cause), or take it as given because it only restates what the question asks about. It never judges whether a claim is true (setting `premiseSort`) |
| Widen | Extension analyst (a model) | Lists the steps of the subject's life cycle that the question depends on and what each step involves, as assumptions; each step becomes a research goal of its own, and the findings confirm, correct or refute each assumed part (setting `extend`) |
| Order | Code | Ranks the goals: checks of the question's claims and definitions first, goals that other goals depend on before them; packs up to three goals into each researcher's brief. A check of a claim is asked inside a brief on a part of the answer and takes no researcher of its own |
| Research | Researchers (the platform) | Each searches the web and reads pages for its brief, and writes notes in which every finding carries its source |
| Check | Conflict checker (a model) | Compares the new findings with earlier ones and with the question's claims, also those taken as given; each real disagreement gets a goal to settle it, or is reported as unresolved |
| Judge | Round analyst (a model) | For each goal, which parts of a full answer the findings meet; a verdict on each claim of the question; new goals the findings call for |
| Decide | Code | Settles goals, retries partial ones (two attempts each), stops, or plans the next round |
| Write | Writer (the platform) | Writes the report from the researchers' notes, following EBD's outline and instructions: say plainly when a claim of the question is false, give both sides of an unresolved disagreement, say what could not be established |

## How a run ends

The stop is recorded in every decision of `events.jsonl` (`strategyState.stop`) and
shown in the viewer.

| Stop | Meaning |
|---|---|
| `complete` | Every necessary goal is settled (answered, given up on after its attempts, left as an unresolved disagreement, or dropped because a claim it relied on was false), every claim of the question has a verdict, and no disagreement on a necessary goal is open. One more round may then serve nice-to-have goals |
| `saturated` | A round made no progress on any necessary goal and found nothing new |
| `budget` | No researcher is left; the briefs EBD still wanted are recorded as unmet demand |
| `out_of_scope` | Nothing could be researched, for example a question about an attached file that was not provided; the report says so in one paragraph |
| `researcher_failures` | Every necessary goal is settled, but some ended only because their researchers failed (timeouts, provider errors); the report says what could not be researched |

## Settings

Set in `--options` or in an experiment spec's strategy entry. All have defaults.

| Setting | Default | What it changes |
|---|---|---|
| `init` | `"fixed"` | `"agent"` runs the request analyst as a tool-using agent instead of one call with a code check and one retry. `"environment"` replaces the steps Plan, Sort and Widen by one call (see "One-call plan" below), and in the first round sends every researcher to a main part of the answer, the necessary parts first; built on 2026-11-19, its prompt text approved the same day, off until the final test |
| `maxPerRound` | 4 | Researchers per round at most |
| `questionsPerBrief` | 3 | Goals packed into one brief |
| `spread` | true | Give researchers that would sit idle a goal of their own |
| `conflicts` | true | `false` turns the conflict checker off |
| `newGoals` | true | `false` keeps only the goals of the first plan |
| `maxNewGoalsPerRound`, `maxOpenGoals`, `maxDepth` | 4, 20, 2 | Limits on new goals: per round, open at once, and steps away from the question |
| `maxAttempts` | 2 | Attempts before a goal is given up on |
| `evidenceFloor` | 2 | Different websites needed before a claim, number or date counts as answered |
| `extraRound` | true | One more round for nice-to-have goals after `complete` |
| `premiseFirst` | true | Check the question's claims in the first round |
| `reserveFirstTries` | true | Keep researchers for necessary goals that have not had a first try |
| `extend` | true | Widens the first plan: after analysing the question's words, the analyst lists the steps of the subject's life cycle and what each involves, as assumptions, and each step gets its own research goal. Findings confirm, correct or refute each assumed part; none reaches the report as a fact. When a step depends on something the question does not state, such as who is asking, the analyst is told to cover the main cases (added on 2026-11-18). `false` keeps the plan built from the question's words only |
| `focusFollowUp` | false | `true` sends the researchers left after a round only to what the answer depends on. The conflict checker marks which disagreements are critical (the answer changes with the side that is right); only those get a goal to settle them, one per round and with one attempt. A goal is searched again only when most of it is unanswered or a claim of the question is undecided. A new goal is necessary only for a main part of the question, and details never share a researcher with it |
| `leanGuidance` | false | `true` tells the writer only what the notes do not show: how the question was read, the claims of the question that the evidence contradicts or leaves open, and at most three critical disagreements, each treated where it arises. No outline for a one-part question, no section for disagreements and no list of planned contents |
| `strictFollowUp` | false | `true`: after the first round a researcher goes only to a main part of the answer or to a claim of the question. A disagreement between sources is reported to the writer and not researched again, unless it decides a claim of the question; a detail gets no researcher after the first round; a planned main part that no researcher was asked about still gets one. Part of the one approach (DESIGN.md sections 29 and 30); texts approved on 2026-11-19, off until the final test |
| `mainPartsFirst` | true | Only with `focusFollowUp`: after the first round, the researchers go first to the necessary goals that ask for a part of the answer; a goal that settles a disagreement gets a researcher only when one is left, unless a part of the answer waits behind it. `false` gives the earlier order, in which the goal that settles a critical disagreement comes first. Decided on 2026-11-18; replayed on saved runs, not yet tested on new questions (DESIGN.md section 25) |
| `uncitedParts` | true | Only with `focusFollowUp`: the round analyst may ask for a main part of the answer that no finding mentions, as one of the two necessary new goals of a round, without citing a finding. `false` rejects every new goal that cites no evidence. Approved on 2026-11-19; in replays on 17 saved runs the analyst never used it (DESIGN.md section 26) |
| `premiseSort` | true | Before any search, one model call sorts the claims the question takes for granted. A specific fact (a date, a number, who did what, a particular event or its cause) is checked. A claim that only restates what the question asks about is taken as given: it gets no check and no line for the writer, and the conflict checker still reports findings that state it false. `false` checks every claim. Decided on 2026-11-19 (DESIGN.md section 27) |
| `premiseRides` | true | A check of a claim is asked in the brief of a main part in round 1, one check to a brief, so that it takes no researcher of its own. The check is still made in round 1. `false` gives every check its own researcher. Decided on 2026-11-19 (DESIGN.md sections 26 and 27) |
| `stepsFirst` | true | In round 1, when the plan has life-cycle steps: a planned question that the steps stand in for only rides along in a brief with room, and a researcher that would sit idle goes to a step that shares a brief before any other goal. `false` gives the earlier allocation (DESIGN.md section 27) |
| `partQuestions` | false | `true` asks a researcher one key question for each expected part of a life-cycle step, in place of one question for the whole step, so every part gets its own sourced answer. Each necessary goal gets a researcher before a group of nice-to-have goals does. Tested on 2026-11-18 on the five development questions and on new ones (DESIGN.md sections 21 and 24); the brief text awaits approval |
| `completeMap` | false | `true` makes the analyst write the life-cycle steps so that they hold the whole answer, starting with the step that answers the question most directly, and leave out steps the question does not depend on. The steps then replace the planned questions they cover, except a question that checks a claim. Tested on 2026-11-18 on plans of the five development questions and of 12 new ones, where the gain was about the same (DESIGN.md sections 22 and 24); the prompt text awaits approval |

## Reading a run

Build the run viewer and open `local/viewer/index.html` in a browser:

```
npx tsx src/strategies/ebd/viewer/build.ts
```

It shows every step: the plan, each researcher's brief and notes, each model call with
its exact input and reply, what the code decided, the goal table, the disagreements,
what the writer received and the report. With the `LANGFUSE_*` keys set, runs are also
traced to the team's self-hosted Langfuse, and the viewer adds each run's trace: a
timeline of the graph steps and model calls, the calls of each step with their latency
and tokens, a check that the trace matches the run record, and links into Langfuse.
[viewer/README.md](viewer/README.md) lists the pages and how to verify a run.

The files of a run record:

| File | Contents |
|---|---|
| `report.md` | The report |
| `question.txt`, `config.json` | The question as asked; the settings, model profile, date and the code version (commit) |
| `events.jsonl` | Every decision with its rationale and EBD's full state after the step: goals, findings, disagreements, verdicts, the model calls and what the code did |
| `results/<brief id>.md` | Each researcher's notes; the `.json` beside it has its queries, sources and usage |
| `synthesis.json` | What the writer received: the notes, the outline and the instructions |
| `summary.json` | Researchers used, searches, page reads, tokens, cost, time, citation checks |

IDs in the records: goals are `Q1`, `Q2`, …; the question's claims are `A1`, …;
disagreements are `C1`, …; a finding is `r2-b1-f3` (round 2, brief 1, finding 3) and a
gap the researcher reported is `r2-b1-g1`.

## Known limits

- Tested live on Claude Haiku 5.5 only. On 2026-11-05, 18 runs with contract checks
  all passed, covering the four test questions, a false-premise question and the
  `init`, `conflicts` and `newGoals` settings; runs in which every researcher failed
  ended as described above. A run in which only some researchers fail has not occurred
  live. GPT-6 Luna is checked offline only (`providers.test.ts`); run `check-strategy`
  with `--model luna` once an OpenAI key is available.
- The settings added after 2026-11-11 were developed on five questions. On 12 questions
  they were not developed on (2026-11-18, DESIGN.md section 24), EBD with those settings
  covered slightly more of the checklists than the baseline (89% against 85%) and used
  46% more money, and a blind judge preferred the baseline's report in 16 of 24
  judgments. On the five development questions the same judge had preferred EBD in 7 of
  10. Treat a result on the five questions as a result on those questions only.
- The changes made after that test (the order of the follow-up, new goals without a
  citation, the sentence on the main cases) were replayed on the saved runs on
  2026-11-19 and would not have changed its result: the parts the judge missed were
  thin in the notes of the first round, where 10 of 68 researchers only checked a claim
  the question takes for granted (DESIGN.md section 26). They have not been tested on
  new questions.
- **The one approach** (DESIGN.md section 29; chosen on 2026-11-19, not on by default).
  Settings `{ "init": "environment", "focusFollowUp": true, "leanGuidance": true,
  "strictFollowUp": true }`: the one-call plan, a follow-up only for a main part of the
  answer or a claim of the question, and writer input limited to what the notes do not
  show. It passed one live contract check. Its changes and prompt texts were approved
  on 2026-11-19 (`local/ebd-heldout/one-approach-prompts.md`).
- **Final test of the one approach** (2026-11-19, DESIGN.md section 31): against the
  baseline with the same number of researchers, on 12 new real queries and 4 questions
  with a planted problem; rules fixed beforehand. A blind judge preferred it on 4
  questions and the baseline on 5, with 3 undecided. It stated all four planted points in
  full; the baseline stated two in full and two in part. It cost 5% more and took 57%
  longer a run. By the rules it is kept; it is not shown to be better. Its claims were
  judged less carefully supported (4 questions to 0 for the baseline), and it lost three
  questions on which it checked the question's own premise ("why is X good", "why are
  there no laws") and framed the report by the verdict. The other planner and the option
  switches are to be removed on the behaviour design lead's word.
- **Fewer researchers than main parts** (DESIGN.md section 30). With the one-call plan,
  every researcher of the first round goes to a main part of the answer and none is kept
  for a second try. With as many researchers as parts each part has one to itself. With
  fewer, the necessary parts come first and the completing parts share what is left, or
  are asked as one question in a brief with room. With one or two researchers a plan of
  four parts does not fit, and some completing parts are not asked. Replayed on 69 saved
  plans, and run with searches in the 16 runs of the final test, where the approach used
  every researcher it was allowed in the first round. So no run had a follow-up round,
  and of the follow-up rules of `strictFollowUp` only the first (a disagreement between
  sources is reported, not researched again) has run with searches in a follow-up round,
  once, in the live check.
- **One-call plan** (`init: "environment"`, built on 2026-11-19, off by default, prompt
  text approved on 2026-11-19; DESIGN.md section 28). One model call replaces the steps Plan, Sort
  and Widen: it writes the main parts of the answer, each with its key questions, sorts
  the claims the question takes for granted, and notes what the client did not state. It
  may name what it knows as examples to look for; the researchers are told that these are
  expectations. Checked on plans only, without search, last on 12 new real queries after
  four wording changes: it needs one call where the present plan needs about three and
  less than half the time. It asks for what the present plan and the baseline's plan ask
  for, except the items that only ask what a term of the question is (26% against 89% for
  the present plan and 30% for the baseline). It has run end to end once, in the live
  check of the one approach.
- The premise check was redone on 2026-11-19 (`premiseSort`, `premiseRides`,
  `stepsFirst`, DESIGN.md section 27). Checked without search: the sorter sent every
  false premise to be checked, on saved analyses and on 16 new questions, and in replayed
  first-round plans no researcher only checks a claim. What it does to the reports has
  not been tested.
- When the request analysis is rejected twice, a question whose only fault is its length
  is kept with its text cut. When nothing usable is left, the step is run again; if that
  happens twice in one run, the run plans the request itself as one question and records
  "minimal plan" under `init` in `events.jsonl`. This last case has not occurred live.
- The round analyst asks for dated, primary sources. When the web search cannot reach
  them, necessary goals end partly answered, and the report says what is not
  established.
- How many goals the plan makes for one question varies between runs, and so does the
  number of researchers used.
- Web results change over time and are not cached; the records keep every query and
  source.
- Questions are researched in English, from the open web: no paywalled content, no
  attached files.
