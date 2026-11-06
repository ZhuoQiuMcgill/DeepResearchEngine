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
| Order | Code | Ranks the goals: checks of the question's claims and definitions first, goals that other goals depend on before them; packs up to three goals into each researcher's brief |
| Research | Researchers (the platform) | Each searches the web and reads pages for its brief, and writes notes in which every finding carries its source |
| Check | Conflict checker (a model) | Compares the new findings with earlier ones and with the question's claims; each real disagreement gets a goal to settle it, or is reported as unresolved |
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
| `init` | `"fixed"` | `"agent"` runs the request analyst as a tool-using agent instead of one call with a code check and one retry |
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
- The round analyst asks for dated, primary sources. When the web search cannot reach
  them, necessary goals end partly answered, and the report says what is not
  established.
- How many goals the plan makes for one question varies between runs, and so does the
  number of researchers used.
- Web results change over time and are not cached; the records keep every query and
  source.
- Questions are researched in English, from the open web: no paywalled content, no
  attached files.
