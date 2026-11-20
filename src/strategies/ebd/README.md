# EBD deep research: user guide

EBD is a deep research strategy built on Environment-Based Design. Given a question, it
first analyses the environment of the answer: who asks and for what, what the subject is
and what surrounds it, and what the question takes for granted. From that it plans the
main parts a full answer needs, sends one researcher to each part, checks the findings
for disagreements and for false claims in the question, and researches again only what
the answer still lacks. A writer then turns the findings into a cited report.

**Status: final for the comparison with the baseline (2026-11-20).** The strategy is one
approach, with no setting that switches to another planner or to other follow-up rules.
It passes the platform's acceptance check on Claude Haiku 5.5 and on GPT-6 Luna. With the
same number of researchers it is level with the baseline, not better; the results are
summarised [below](#how-it-compares-with-the-baseline).

## Where things are

| Read | For |
|---|---|
| This guide | How to run the strategy, what a run does, how to read its records |
| [evaluation/README.md](evaluation/README.md) | Every test against the baseline: method, results, limits, and the data behind them |
| [DESIGN.md](DESIGN.md) | Why the strategy is built this way, and the record of each change and test. Its section 1 describes the final design and says which later sections still apply |
| [viewer/README.md](viewer/README.md) | The run viewer: stepping through a run and checking each agent |
| [docs/strategy-modules.md](../../../docs/strategy-modules.md) | The platform's plug-in contract |

| File | Holds |
|---|---|
| `index.ts` | The strategy: `init` (the plan), `observe` (after each round), `finalize` (what the writer gets) |
| `environment.ts` | The environment analyst: its prompt, the checks on its reply, the plan turned into goals |
| `briefs.ts` | From goals to researcher briefs: who is sent where, with which key questions |
| `rounds/evidence.ts`, `rounds/conflicts.ts`, `rounds/analyst.ts` | Reading the researchers' notes; the conflict checker; the round analyst |
| `goals.ts`, `map.ts`, `state.ts`, `analysis.ts` | The goal table and stop rules; the plan's main parts during a run; the state kept between steps |
| `synthesis.ts` | The writer's input: material, suggested outline, guidance |
| `options.ts`, `llm.ts` | The settings; the one helper for model calls with a checked, structured reply |
| `*.test.ts`, `fixtures.ts` | The tests (no network) |
| `viewer/` | The run viewer |
| `evaluation/` | The evaluation record: questions, judge output, reports, tables |
| `request/` | The earlier request analysis. The strategy no longer calls it (see Known limits) |

## Before the first run

- Node.js 22 and `npm install` at the repository root.
- A `.env` file at the repository root (copy `.env.example`) with the key of the model
  you use: `ANTHROPIC_API_KEY` for Claude Haiku 5.5 (profile `haiku`), `OPENAI_API_KEY`
  for GPT-6 Luna (profile `luna`). The `LANGFUSE_*` keys are optional; with them, every
  model call is also traced to the self-hosted Langfuse.
- Every run uses real models and real web searches. A run costs about $0.08 to $0.55 on
  Haiku 5.5, most of it the search fee of the researchers (about $0.09 a researcher). The
  one run made on Luna so far cost $0.04.

## Run a question

```
npm run research -- --strategy ebd --model haiku --question "How do heat pumps work in cold climates?" --researchers 6
```

- The question is used exactly as typed.
- `--researchers` is the most researchers the run may send (default 10). Each
  researcher runs one brief with up to 12 web searches and page reads.
- `--options '{"maxPerRound": 3}'` changes a setting (see below).
- `--task ebd` (or `headset`, `flight`, `sleep`) runs one of the fixed test questions.

The run writes its record to `local/runs/<run id>/`; the report is `report.md` there.
To run EBD with contract checks (a run plus the platform's checks of everything the
strategy returned), use
`npm run check-strategy -- --strategy ebd --model haiku --task ebd`. Its records go
to `local/checks/`.

In an experiment spec, the strategy entry is `"ebd"` or
`{ "name": "ebd", "label": "ebd-matched", "matchResearchersTo": "baseline" }`, which gives
EBD the number of researchers the baseline used on the same question. Every comparison
since 2026-11-19 was run that way.

## What happens in a run

| Step | Who | What it does |
|---|---|---|
| Plan | Environment analyst (a model, one call) | Reads the question and analyses the environment of the answer. Writes the main parts a full answer needs, usually 3 or 4, each with 4 or 5 key questions; sorts the claims the question takes for granted into those to check (a date, a number, who did what, a particular event) and those taken as given because they only restate the question; notes what the answer depends on and the client did not state |
| First round | Code, then researchers (the platform) | Every researcher goes to a main part, the necessary parts first. With as many researchers as parts, each part has one to itself and its key questions are asked one by one. With fewer, parts share a researcher. The check of the question's claims is asked in the brief of a main part and takes no researcher of its own. Each researcher searches the web, reads pages and writes notes in which every finding carries its source |
| Check | Conflict checker (a model) | Compares the new findings with one another, with the question's claims and with what the key questions take for granted. Marks each disagreement critical or not: critical means the answer changes with the side that is right |
| Judge | Round analyst (a model) | For each main part, which key questions the findings answer; a verdict on each checked claim; and new goals: a main part of the answer that the findings leave out, or a detail |
| Decide | Code | After the first round a researcher goes only to a main part of the answer or to a claim of the question: a part that is mostly unanswered, a part the analyst found missing (at most two a round), or a disagreement that decides a claim. A disagreement between sources that decides no claim is not researched again; when it is critical the writer is told. A detail gets no researcher. The run stops when nothing of that kind is left, or when no researcher is left |
| Write | Writer (the platform) | Writes the report from the researchers' notes. EBD suggests the researched main parts as the outline and tells the writer only a few things: a claim of the question that the evidence contradicts (to be corrected in a sentence or two before the question is answered as asked), at most three critical disagreements, to say what the question's main terms mean, and to build first on the strongest sources |

The model makes narrow judgments (a plan, a list of disagreements, a verdict); code turns
them into who is sent where and when the run stops. Every reply of a model is checked by
code and asked again once when it fails the checks.

## How a run ends

The stop is recorded in every decision of `events.jsonl` (`strategyState.stop`) and
shown in the viewer.

| Stop | Meaning |
|---|---|
| `complete` | Every necessary goal is settled (answered, given up on after its attempts, left as an unresolved disagreement, or dropped because a claim it relied on was false), every checked claim of the question has a verdict, and no disagreement on a necessary goal is open |
| `saturated` | A round made no progress on any necessary goal and found nothing new, or nothing is left that a researcher may be sent to |
| `budget` | No researcher is left; the briefs EBD still wanted are recorded as unmet demand |
| `out_of_scope` | Nothing could be researched, for example a request for a poem, or a question about an attached file that was not provided; the report says so in one paragraph |
| `researcher_failures` | Every necessary goal is settled, but some ended only because their researchers failed (timeouts, provider errors); the report says what could not be researched |

## Settings

Set in `--options` or in an experiment spec's strategy entry. All have defaults. They
are limits and three rules for dividing researchers (`spread`, `premiseFirst`,
`reserveFirstTries`). No setting turns the conflict checker or the new goals off.

| Setting | Default | What it changes |
|---|---|---|
| `maxPerRound` | 4 | Researchers per round at most |
| `questionsPerBrief` | 3 | Goals packed into one brief in a round after the first |
| `spread` | true | Give every researcher of a round a goal of its own where the goals allow it. `false` packs the goals of the first round by the limit above |
| `maxNewGoalsPerRound`, `maxOpenGoals`, `maxDepth` | 4, 20, 2 | Limits on new goals: per round, open at once, and steps away from the question. Each is at least 1 |
| `maxAttempts` | 2 | Attempts before a goal is given up on |
| `evidenceFloor` | 2 | Different websites needed before a claim of the question counts as checked |
| `premiseFirst` | true | Check the question's claims in the first round |
| `reserveFirstTries` | true | In a later round, keep researchers for necessary planned goals that have not had a first try |

An unknown setting is rejected. That includes the settings that existed until
2026-11-19 and chose a planner or a follow-up rule (`init`, `extend`, `completeMap`,
`partQuestions`, `premiseSort`, `premiseRides`, `stepsFirst`, `focusFollowUp`,
`leanGuidance`, `mainPartsFirst`, `uncitedParts`, `strictFollowUp`, `extraRound`), and the
two that turned the conflict checker and new goals off until 2026-11-20 (`conflicts`,
`newGoals`; DESIGN.md, section 39). No experiment spec in the repository uses one of
them.

## Reading a run

Build the run viewer and open `local/viewer/index.html` in a browser:

```
npx tsx src/strategies/ebd/viewer/build.ts
```

It shows every step: the plan, each researcher's brief and notes, each model call with
its exact input and reply, what the code decided, the goal table, the disagreements,
what the writer received and the report. With the `LANGFUSE_*` keys set, runs are also
traced to the self-hosted Langfuse, and the viewer adds each run's trace: a timeline of
the graph steps and model calls, the calls of each step with their latency and tokens, a
check that the trace matches the run record, and links into Langfuse.
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

IDs in the records: goals are `Q1`, `Q2`, …; the question's claims are `A1`, …; the key
questions of the plan are `M1`, …; disagreements are `C1`, …; a finding is `r2-b1-f3`
(round 2, brief 1, finding 3) and a gap the researcher reported is `r2-b1-g1`.

What changed in the records with the final version, for tools that read them: the state
no longer has `map.replaced`, `map.questions` or `extraRoundServed`; the roles of the
strategy's model calls are `environment_analyst`, `conflict_checker` and `round_analyst`;
and `synthesis.json` now has an `outline` in most runs. Goals, disagreements, findings and
the question's claims are recorded as before.

## How it compares with the baseline

The full record is in [evaluation/README.md](evaluation/README.md). In short, with the
same number of researchers on both sides, on Claude Haiku 5.5:

| Test | Result, EBD against the baseline |
|---|---|
| Final test (2026-11-19): 12 new real queries, blind judge, both orders | The judge preferred EBD on 4 questions and the baseline on 5, with 3 undecided. Checklist coverage 0.77 against 0.77 |
| The same reports with the final writer input (2026-11-20) | 3 to 2, with 7 undecided |
| Planted-problem test (2026-11-20): 12 new questions with a false fact, sources that disagree, or an answer that depends on who asks | The planted point stated in full in 12 of 12 reports against 11 of 12 |
| Cost and time | 5% more on real queries and 15% less on the planted-problem questions; about half as long again a run |
| On a weaker model (GPT-5 nano, a side run of six questions with a false fact) | The correction stated in 6 of 6 reports against 4 of 6 |

EBD is level with the baseline on Haiku 5.5. Both sides get the same researchers, who
find the same things whatever the plan says, and this model already does unasked what
EBD's rules demand, such as correcting a well-known false fact. What EBD adds is on
record: the claims of the question with a verdict, the disagreements between sources and
the plan's parts, which the run viewer shows step by step.

## Known limits

- **Not shown to be better than the baseline.** Twelve questions with one run each and a
  model as the judge can only tell a large difference from chance. No fact and no citation
  was checked, and no person has rated the reports.
- **The follow-up rounds have hardly run.** With the baseline's number of researchers all
  of them go out in the first round, so the analysis after it could rarely send anyone:
  one follow-up round in EBD's 28 runs of the two tests.
- **Time.** EBD spends about 85 seconds a run in its own calls, about 40 of them in the
  conflict checker, which runs after every round and cannot be turned off. Some of its
  first replies fail the code checks and are asked again (9 of 16 runs of the final
  test).
- **Weaker models strain it.** On GPT-5 nano almost half of EBD's own replies failed the
  code checks and were asked again, and the round analysis had to be repaired by the code
  in 5 of 6 runs. The runs still ended ok.
- **Luna has an acceptance run only.** On the fixed EBD question Luna planned one main
  part and used one researcher. The comparison with the baseline on Luna has not been run.
- **Fewer researchers than main parts** (DESIGN.md, section 30). With one or two
  researchers a plan of four parts does not fit: the necessary parts and the check of the
  claims are asked, and some completing parts are not.
- **The plan lists a term with several meanings more often than its prompt asks for**, so
  the restated question still reaches the writer in most runs (DESIGN.md, section 34.1).
- **The writer's output limit is the platform's** (21,000 tokens). EBD's writer calls use
  more of it than the baseline's (17,800 at most in the planted-problem test); no report
  of the final code was cut off.
- When the plan is rejected twice, its valid parts are used. When nothing usable is left,
  the step is run again; if that happens twice in one run, the run plans the request
  itself as one question and records "minimal plan" under `init` in `events.jsonl`. This
  last case has not occurred live.
- How many main parts the plan has for one question varies between runs.
- Web results change over time and are not cached; the records keep every query and
  source.
- Questions are researched in English, from the open web: no paywalled content, no
  attached files.
- `request/` holds the request analysis that made the first plan until 2026-11-19. The
  strategy no longer calls it and nothing else in the repository uses it. It is kept
  because scripts of an earlier lab on the behaviour design lead's machine import it; it
  can be ignored.

## Changing the strategy

- Work only inside `src/strategies/ebd/`, and import platform types only from
  `src/core/index.ts` (the platform's rule for strategy modules).
- The texts sent to a model are approved by the behaviour design lead and pinned by a
  test (`approach.test.ts`, "the prompt texts"): a changed text fails the test until its
  new fingerprint is entered. Show the text, now and proposed, before changing it.
- Before a change of behaviour, replay recorded runs with no model call to see what it
  moves (`evaluation/scripts/golden.ts.txt` shows how), then run `npm test`,
  `npm run typecheck` and `npm run check-strategy -- --strategy ebd`.
- New test questions must not have been read before the run; the questions in
  `evaluation/questions/` are used and count as development data.
