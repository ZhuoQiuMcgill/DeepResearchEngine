# EBD deep research: user guide

EBD is a deep research strategy built on Environment-Based Design. Given a question, it
first analyses the environment of the answer: who asks and for what, what the subject is
and what surrounds it, and what the question takes for granted. From that it plans the
main parts a full answer needs, sends one researcher to each part, checks the findings
for disagreements and for false claims in the question, and researches again only what
the answer still lacks. A writer then turns the findings into a cited report.

This guide says how to run it and how to read what it produces. How it works and why
is in [DESIGN.md](DESIGN.md); the plug-in contract is in
[docs/strategy-modules.md](../../../docs/strategy-modules.md).

Since 2026-11-19 the strategy is one approach, with no setting that switches to another
planner or to other follow-up rules (DESIGN.md section 32). The request analysis, the
premise sorter and the problem extension that made the first plan before are no longer
part of it.

## Before the first run

- Node.js 22 and `npm install` at the repository root.
- A `.env` file at the repository root (copy `.env.example`) with the key of the model
  you use: `ANTHROPIC_API_KEY` for Claude Haiku 5.5 (profile `haiku`), `OPENAI_API_KEY`
  for GPT-6 Luna (profile `luna`). The `LANGFUSE_*` keys are optional; with them, every
  model call is also traced to the team's self-hosted Langfuse.
- Every run uses real models and real web searches. A run costs about $0.08 to $0.60 on
  Haiku, almost all of it the researchers (about $0.09 each).

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
| Plan | Environment analyst (a model, one call) | Reads the question and analyses the environment of the answer. Writes the main parts a full answer needs, usually 3 or 4, each with 4 or 5 key questions; sorts the claims the question takes for granted into those to check (a date, a number, who did what, a particular event) and those taken as given because they only restate the question; notes what the answer depends on and the client did not state |
| First round | Code, then researchers (the platform) | Every researcher goes to a main part, the necessary parts first. With as many researchers as parts, each part has one to itself and its key questions are asked one by one. With fewer, parts share a researcher. The check of the question's claims is asked in the brief of a main part and takes no researcher of its own. Each researcher searches the web, reads pages and writes notes in which every finding carries its source |
| Check | Conflict checker (a model) | Compares the new findings with one another, with the question's claims and with what the key questions take for granted. Marks each disagreement critical or not: critical means the answer changes with the side that is right |
| Judge | Round analyst (a model) | For each main part, which key questions the findings answer; a verdict on each checked claim; and new goals: a main part of the answer that the findings leave out, or a detail |
| Decide | Code | After the first round a researcher goes only to a main part of the answer or to a claim of the question: a part that is mostly unanswered, a part the analyst found missing (at most two a round), or a disagreement that decides a claim. A disagreement between sources that decides no claim is not researched again; when it is critical the writer is told. A detail gets no researcher. The run stops when nothing of that kind is left, or when no researcher is left |
| Write | Writer (the platform) | Writes the report from the researchers' notes. EBD tells it only what the notes do not show: a claim of the question that the evidence contradicts or leaves open, at most three critical disagreements, and what the plan assumed because the client did not state it |

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

Set in `--options` or in an experiment spec's strategy entry. All have defaults. The
first two are the switches the platform's comparison experiment uses; the others are
limits.

| Setting | Default | What it changes |
|---|---|---|
| `conflicts` | true | `false` turns the conflict checker off |
| `newGoals` | true | `false` keeps only the goals of the first plan |
| `maxPerRound` | 4 | Researchers per round at most |
| `questionsPerBrief` | 3 | Goals packed into one brief in a round after the first |
| `spread` | true | Give every researcher of a round a goal of its own where the goals allow it. `false` packs the goals of the first round by the limit above |
| `maxNewGoalsPerRound`, `maxOpenGoals`, `maxDepth` | 4, 20, 2 | Limits on new goals: per round, open at once, and steps away from the question |
| `maxAttempts` | 2 | Attempts before a goal is given up on |
| `evidenceFloor` | 2 | Different websites needed before a claim of the question counts as checked |
| `premiseFirst` | true | Check the question's claims in the first round |
| `reserveFirstTries` | true | In a later round, keep researchers for necessary planned goals that have not had a first try |

An unknown setting is rejected. That includes the settings that existed until
2026-11-19 and chose a planner or a follow-up rule (`init`, `extend`, `completeMap`,
`partQuestions`, `premiseSort`, `premiseRides`, `stepsFirst`, `focusFollowUp`,
`leanGuidance`, `mainPartsFirst`, `uncitedParts`, `strictFollowUp`, `extraRound`).

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

IDs in the records: goals are `Q1`, `Q2`, …; the question's claims are `A1`, …; the key
questions of the plan are `M1`, …; disagreements are `C1`, …; a finding is `r2-b1-f3`
(round 2, brief 1, finding 3) and a gap the researcher reported is `r2-b1-g1`.

## Known limits

- **Compared with the baseline once** (2026-11-19, DESIGN.md section 31): with the same
  number of researchers, on 12 new real queries and 4 questions with a planted problem,
  rules fixed beforehand. A blind judge preferred EBD on 4 questions and the baseline on
  5, with 3 undecided. EBD stated all four planted points in full; the baseline stated two
  in full and two in part. EBD cost 5% more and took 57% longer a run. By the rules it
  was kept; it is not shown to be better. Twelve questions, one run each and a model as
  the judge can only tell a large difference from chance.
- **The question's own premise.** In that test EBD lost three questions of the form "why
  is X good" or "why are there no laws against X". It checked the opinion the question
  starts from, the evidence contradicted it or left it open, and the report was framed
  by that verdict, where the baseline gave a fuller answer. The sort of such claims has
  not been changed since.
- **Support.** The judge found the baseline's claims more carefully stated and cited on 4
  of the 12 questions, and EBD's on none.
- **Time.** EBD spends about 86 seconds a run in its own three kinds of calls. In 9 of
  16 runs the conflict checker's first reply was rejected by the code checks and asked
  again.
- **Fewer researchers than main parts** (DESIGN.md section 30). With one or two
  researchers a plan of four parts does not fit: the necessary parts and the check of
  the claims are asked, and some completing parts are not.
- **The follow-up rules have hardly run with searches.** In all 16 runs of the test the
  first round used every researcher, so no follow-up round took place. One earlier live
  run had one.
- **The code as it stands has not run with searches.** The strategy was consolidated to
  this one approach after the test. Replayed on the 16 runs of the test, it makes the
  same decisions, goals, conflicts and writer input, and the texts it sends are
  unchanged; a live `check-strategy` run is still to be made.
- Tested live on Claude Haiku 5.5 only. GPT-6 Luna is checked offline only
  (`providers.test.ts`); run `check-strategy` with `--model luna` once an OpenAI key is
  available.
- When the plan is rejected twice, its valid parts are used. When nothing usable is left,
  the step is run again; if that happens twice in one run, the run plans the request
  itself as one question and records "minimal plan" under `init` in `events.jsonl`. This
  last case has not occurred live.
- How many main parts the plan has for one question varies between runs.
- Web results change over time and are not cached; the records keep every query and
  source.
- Questions are researched in English, from the open web: no paywalled content, no
  attached files.
- The results of the earlier planner (the five development questions, the 12 questions of
  2026-11-18) are in DESIGN.md sections 20 to 27. They do not describe this code.
- `request/` holds the request analysis that made the first plan until 2026-11-19. The
  strategy no longer calls it. It is still in the folder because scripts of Lab 3 on
  the behaviour design lead's machine import it; whether it moves there or goes is the
  lead's decision.
