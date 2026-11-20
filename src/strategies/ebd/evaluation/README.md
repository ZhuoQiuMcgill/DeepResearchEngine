# EBD against the baseline: testing and evaluation record

This folder holds what was measured, how, and the data behind every number, for the final
report. It describes the EBD strategy as it stands on 2026-11-20 (the final
implementation). How the strategy works is in [../README.md](../README.md); how each test
came about, step by step, is in [../DESIGN.md](../DESIGN.md), sections 23 to 37.

## 1. The result in short

- **With the same number of researchers, on Claude Haiku 5.5, EBD is level with the
  baseline.** A blind judge does not tell the two sides' reports apart on ordinary
  questions, and both sides state a planted problem (a false fact in the question,
  sources that disagree, an answer that depends on who asks) in nearly every report.
- **EBD costs about the same and takes about half as long again.** Cost +5% on real
  queries and -15% on planted-problem questions; time +52% to +57% a run.
- **On a weaker model the two sides separate.** On OpenAI's older, smaller GPT-5 nano,
  EBD corrected a well-known false fact in 6 of 6 reports and the baseline in 4 of 6. Six
  questions: an indication, not a result.
- **Why they are level on Haiku 5.5:** both sides get the same researchers, who find the
  same things whatever the plan says; and the model already does unasked what EBD's rules
  demand (the baseline's planner corrected every well-known false fact from its own
  knowledge before any search). Section 4 has the evidence.

| Test | EBD version | Questions | Researchers | Result, EBD against baseline | EBD's cost and time |
|---|---|---|---|---|---|
| Development questions, 2026-11-18 | Earlier planner with five options | 5, known during development | Ceiling of 6; EBD used 69% more | Judge preferred EBD in 7 of 10 judgments; checklist 94% against 87% | +54%, 2.5 times |
| First test on new questions, 2026-11-18 | The same | 12 new: 6 real, 6 designed | Ceiling of 6; EBD used 58% more | Questions 3 to 7, 2 undecided; checklist 89% against 85% | +46%, 2.4 times |
| **Final test, 2026-11-19** | The one approach | 12 new real queries, 4 planted | Equal | Questions 4 to 5, 3 undecided; checklist 0.77 against 0.77; planted points in full 4 of 4 against 2 of 4 | +5%, +57% |
| Writer-input check, 2026-11-20 | Final writer input, on the saved notes | The 12 real queries | Same notes | Questions 3 to 2, 7 undecided; single judgments 11 to 11 | |
| **Planted-problem test, 2026-11-20** | Final code | 12 new planted | Equal allowance; EBD used 33 of 38 | Planted points in full 12 of 12 against 11 of 12 | -15%, +52% |
| Weaker model, 2026-11-20 | Final code, on GPT-5 nano | 6 with a well-known false fact | At most 3 each | Corrections in full 6 of 6 against 4 of 6 | -16%, +86% |
| Acceptance check, 2026-11-20 | Final code | The project's fixed EBD question | Up to 6 | 11 of 11 contract checks on Haiku 5.5 and on GPT-6 Luna | $0.19 and $0.04 a run |

"Questions 4 to 5, 3 undecided" means: the judge preferred EBD's report on 4 questions and
the baseline's on 5, in both orders of presentation; on 3 the two orders disagreed.

## 2. How the comparison was made

**The two sides.** The baseline strategy (`src/strategies/baseline/`, the platform's
reference module) and the EBD strategy (`src/strategies/ebd/`). Everything else is the
platform's and is shared: the researchers with the model's own web search, the writer,
the budget, the records. Both sides run on the same model within a comparison.

**Equal researchers.** Since the final test EBD gets the number of researchers the
baseline used on the same question (`matchResearchersTo` in the experiment spec). The two
tests of 2026-11-18 had a common ceiling of 6 instead, and EBD used more.

**Questions.**

- *Real queries:* drawn at random from the test split of the public Researchy Questions
  dataset with a fixed seed; the first 12 with a question and at least three
  sub-questions. Their checklist is the dataset's own list of sub-questions.
- *Planted-problem questions:* written before any run on them, each with the one thing a
  report must say. Three kinds: a false fact in the question, sources that give different
  figures, an answer that depends on who asks.
- *Questions not used for development.* The strategy was tuned on five questions. Every
  test since 2026-11-18 used questions that nobody had read before the run. After a test
  its questions count as development data.

**Measures.**

1. *Blind pairs.* A judge model (Claude Opus 5.5, effort medium) gets the question, its
   checklist and the two reports as A and B, without knowing which side wrote which, and
   names the better one on four criteria and overall. Each pair is judged in both orders.
   A question counts for a side only when both orders name it.
2. *Checklist coverage.* The same judge scores each report against each checklist item: 1
   stated with a source, 0.5 stated without a source or in part, 0 missing.
3. *Planted point.* The same scoring, with the one planted point as the checklist.
4. *From the run records:* researchers, searches, cost, time, the strategy's own calls.
5. *The platform's citation check:* links in the report that the researchers never saw.

**Rules fixed before the runs.** For the final test: EBD is kept unless the baseline wins
10 or more of the decided questions, EBD states fewer planted points, or EBD costs more
than 15% above the baseline; it counts as better only at 10 or more wins. For the
planted-problem test: a difference counts as shown only if the two-sided sign test gives
p < 0.05 (six questions for EBD and none against). The tests ran in two stages, a small
one first as the live check of the code; between the stages only a defect of the program
could be fixed.

**The judge's two instructions, word for word.**

```text
You compare two research reports, A and B, that answer the same question. You do not know how they were produced. Judge only their text; you cannot open their links.

Criteria:
- coverage: which covers more of what the question needs (the checklist lists the main items);
- support: which states its claims more carefully: key facts, numbers and dates carry citations, nothing is asserted beyond its sources, and uncertainty is stated where it exists;
- conflicts: which better handles disagreements between sources and any false assumption in the question;
- usefulness: which answers the question more directly and is easier to act on, at a length that suits the question.

For each criterion answer "A", "B" or "tie"; use "tie" when the difference is small. Do not prefer a report for being longer. Then give an overall verdict ("A", "B" or "tie") and at most two sentences of reasons.

Reply with one JSON object and nothing else: {"coverage":"A","support":"B","conflicts":"tie","usefulness":"A","overall":"A","reason":"..."}
```

```text
You check a research report against a checklist of what a full answer contains. The checklist was written from the question before the report existed. Judge only the report's text; you cannot open its links.

For each item:
- score 1: the report states it and cites a source for it;
- score 0.5: the report states it without a citation, or covers it only in part;
- score 0: the report does not cover it.
- quote: up to 25 words copied exactly from the report that cover the item; an empty string for score 0.
- wrong: true if what the report says on this item looks factually wrong or contradicts itself; otherwise false.

Reply with one JSON object and nothing else: {"items":[{"n":1,"score":1,"quote":"...","wrong":false}, ...]}
```

## 3. The tests

### 3.1 Before the final test (2026-11-18)

EBD then made its first plan in three model calls and had five options switched on. It
was compared with the baseline under a common ceiling of 6 researchers, and it used more
of them.

| | Five development questions | Twelve new questions |
|---|---|---|
| Checklist coverage, EBD against baseline | 94% against 87% | 89% against 85% |
| Blind judgments, EBD : tie : baseline | 7 : 0 : 3 | 8 : 0 : 16 |
| Questions on which both orders agree | | EBD 3, baseline 7, undecided 2 |
| Researchers, cost and time against the baseline | +69%, +54%, 2.5 times | +58%, +46%, 2.4 times |

The lead on the development questions did not carry over to new ones. What the judge
named against EBD on the new questions was the same from question to question: a main part
of the answer missing that the baseline had, space spent beside the question, and a
report framed around a doubt about the question. This led to the one approach: the whole
plan in one call, every researcher of the first round sent to a main part of the answer,
and a later researcher sent only to a main part or to a claim of the question
(DESIGN.md, sections 24 and 28 to 30).

### 3.2 The final test (2026-11-19)

Baseline against the one approach with equal researchers (3.19 a run on both sides), 12
new real queries and 4 planted-problem questions, Haiku 5.5, one run for each cell, 32
runs, all ended ok. Table: `tables/final-test.txt`.

| | Baseline | EBD |
|---|---|---|
| Questions the judge preferred, both orders agreeing (12 real queries) | 5 | 4 |
| Undecided | 3 | |
| ... on coverage | 4 | 3 |
| ... on support | 4 | 0 |
| ... on the handling of conflicts and false assumptions | 2 | 3 |
| ... on usefulness | 4 | 4 |
| Checklist coverage, mean score of 53 items | 0.77 | 0.77 |
| ... the 14 items that only ask what a term is | 0.57 | 0.50 |
| ... the other 39 items | 0.85 | 0.87 |
| Planted points stated in full (4 questions) | 2 | 4 |
| Cost of the 16 runs | $5.07 | $5.35 |
| Seconds a run | 122 | 192 |
| The strategy's own calls a run | 2.0 | 3.8 |
| Words a report | 1,904 | 1,750 |
| Links in the reports that the researchers never saw | 1 of 756 | 0 of 706 |

By the rules fixed beforehand EBD was kept, and it is not shown to be better (sign test on
the decided questions p = 1.0).

| | Real query | The judge preferred |
|---|---|---|
| s01 | how changes to funding have impacted the nhs | undecided |
| s02 | why income inequality is good for the economy | baseline |
| s03 | why do engineering students drop out | baseline |
| s04 | how did america change ww1 | EBD |
| s05 | why do people oppose affirmative action | undecided |
| s06 | how structured literacy instruction differs from typical literacy practices | EBD |
| s07 | how did darwin explain the differences in traits? | baseline |
| s08 | why are there no laws yet to protect people from sociopaths | baseline |
| s09 | how does economics play a role in african american culture | EBD |
| s10 | why is eugenics considered unethical | baseline |
| s11 | how did early american colonies contribute to the growth of capitalism? | EBD |
| s12 | why do people declare bankruptcy | undecided |

The four planted questions: the Chernobyl accident dated 1989, Fleming credited with
insulin, the height of Mount Everest, and a visa for the United Kingdom. Both sides stated
all four planted points; the baseline's two half marks were a correction without a source
and a thinner account of the older figures.

### 3.3 The writer-input check (2026-11-20)

After the final test, what EBD tells the platform's writer was changed (DESIGN.md, section
34): the researched main parts as a suggested outline, a contradicted claim corrected in a
sentence or two before the question is answered as asked, a line on the question's main
terms and a line on sources; no more restated question, assumed purpose, or line for a
claim the evidence leaves open. To see what this does by itself, the 12 EBD reports of the
final test were written again by the platform's writer from the saved notes with the new
input, and judged against the baseline's recorded reports. Tables:
`tables/writer-input-rewrites.txt`, `tables/writer-input-check.txt`.

| The 12 real queries | Recorded EBD reports | EBD reports with the final writer input |
|---|---|---|
| Questions, EBD : baseline : undecided | 4 : 5 : 3 | 3 : 2 : 7 |
| ... on coverage | 3 : 4 : 5 | 4 : 2 : 6 |
| ... on support | 0 : 4 : 8 | 1 : 1 : 10 |
| ... on conflicts | 3 : 2 : 7 | 0 : 1 : 11 |
| ... on usefulness | 4 : 4 : 4 | 3 : 6 : 3 |
| Single judgments of 24, EBD : baseline : tie | 11 : 13 : 0 | 11 : 11 : 2 |
| Words a report; scholarly or official sources cited | 1,913; 16.4 | 2,264; 20.7 (baseline 2,093; 20.4) |

The new input removed the faults the judge had named (support was lost 0 to 4 and is now
level; no report argues with the question; the judge's reasons mention a definition in 14
of 24 judgments, mostly to EBD's credit) and cost directness. It did not make EBD preferred. The judged version had one
more sentence ("Cover each part of the outline."), which was left out of the code after
this result because the judge's recurring complaint was wandering into side parts; the
form without it was not judged apart.

### 3.4 The planted-problem test (2026-11-20)

The first run with searches of the final code. Twelve new questions, four of each kind,
both sides with the same allowance of researchers, 24 runs, all ended ok. Table:
`tables/planted-problem-test.txt`.

| | Baseline | EBD |
|---|---|---|
| Planted point stated in full | 11 of 12 | 12 of 12 |
| ... a false fact in the question | 4 of 4 | 4 of 4 |
| ... sources that give different figures | 4 of 4 | 4 of 4 |
| ... an answer that depends on who asks | 3 of 4 | 4 of 4 |
| Researchers used | 38 | 33 of the 38 allowed |
| Cost of the 12 runs | $3.63 | $3.10 |
| Seconds a run | 114 | 173 |
| Words a report | 1,616 | 1,729 |

By the rule fixed beforehand the result "points the same way" and is no difference in
substance: one question for EBD and none against (sign test p = 1.0), and on that one
(antibiotics) the two reports say much the same. With the four planted questions of the
final test: 16 of 16 against 13 of 16 (p = 0.25).

| | Question | The report must say |
|---|---|---|
| pp01 | How did the Wright brothers' first powered flight in 1908 change transportation? | The flight was on 17 December 1903 |
| pp02 | How did Galileo's invention of the telescope change astronomy? | Galileo did not invent the telescope (Netherlands, 1608) |
| pp03 | Why was Pompeii destroyed by the eruption of Mount Etna? | The volcano was Vesuvius |
| pp04 | Why did the space shuttle Challenger break apart during re-entry in 1986? | It broke apart shortly after launch |
| pp05 | How long is the Nile? | About 6,650 km, and why sources give different lengths |
| pp06 | How many countries are there in the world? | 193 members of the United Nations, and who is counted differently |
| pp07 | How many people died in the 1918 influenza pandemic? | A range of estimates, and why they differ |
| pp08 | How many people died in the bombing of Dresden in February 1945? | About 25,000, and where the much higher figures came from |
| pp09 | What is the legal drinking age? | It depends on the country; several covered |
| pp10 | How many days of paid annual leave am I entitled to? | It depends on the country; several covered |
| pp11 | When does the school year start? | It depends on the country; several covered |
| pp12 | Do I need a prescription to buy antibiotics? | It depends on the country; several covered |

### 3.5 Weaker models (2026-11-20)

**A probe of the planning step only** (no search, `tables/planning-probe-weaker-models.txt`).
Both sides planned six questions with a well-known false fact and six with a specific fact
that no model can know. A small model, not told the side, read how each plan treats the
fact: corrects it, asks a researcher to check it, or takes it for granted.

| Plans that take the fact for granted | Baseline | EBD |
|---|---|---|
| Claude Haiku 5.5, effort medium (as in every test) | 0 of 24 | 0 of 24 |
| Claude Haiku 5.5, effort low | 0 of 24 | 0 of 24 |
| OpenAI GPT-6 Luna | 0 of 12 | 0 of 12 |
| Claude Haiku 4.5 (the previous Haiku) | 3 of 12 | 0 of 12 |
| OpenAI GPT-5 nano (August 2025) | 0 of 12 | 2 of 12 |

Luna plans like Haiku 5.5. The two weaker models slip on opposite sides, and a single plan
varies a lot on them.

**A run with searches on GPT-5 nano** (`tables/weaker-model-run.txt`). The six questions of
the two earlier tests with a well-known false fact, both sides, at most three researchers
a run, 12 runs, all ended ok. The planted point was scored with the judge's coverage
instruction answered by Claude Haiku 5.5, and the two reports on which the sides differ
were read by hand.

| GPT-5 nano | Baseline | EBD |
|---|---|---|
| Correction stated in full | 4 of 6 | 6 of 6 |
| Stated in part; missing | 1; 1 | 0; 0 |
| The plan dealt with the false fact | 5 of 6 | 6 of 6 |
| Seconds a run | 175 | 326 |
| Cost a run, at most | $0.25 | $0.21 |
| EBD's own replies rejected by its code checks and asked again | | 11 of 24 |
| Runs in which the code had to repair the round analysis | | 5 of 6 |

On the Wright brothers question the baseline's planner did not notice the wrong year, its
researchers' notes did contain 1903, and its writer still wrote "The Wright brothers' 1908
powered flight demonstrated ...". EBD's plan marked the year for a check in every run, the
check came back contradicted, and the writer was told to correct it. EBD's heavier steps
strain on this model: almost half of its replies failed the code checks, and a run took
almost twice as long.

### 3.6 Acceptance checks of the final code (2026-11-20)

The platform's `npm run check-strategy` on the committed final code, with the project's
fixed question `What is EBD (Environment Based Design)?` and up to 6 researchers. Tables:
`tables/acceptance-check-haiku.txt`, `tables/acceptance-check-luna.txt`; the reports are
in `reports/acceptance-check/`.

| | Claude Haiku 5.5 | OpenAI GPT-6 Luna |
|---|---|---|
| Contract checks passed | 11 of 11 | 11 of 11 |
| Main parts planned; researchers used | 3; 3 of 6 | 1; 1 of 6 |
| Searches; page reads | 13; 2 | 3; 2 |
| Cost; seconds | $0.19; 129 | $0.04; 64 |
| Words of the report | 1,514 | 907 |

This was EBD's first run on Luna. Luna planned one main part and used one researcher on
this question. A comparison of the two sides on Luna has not been run.

### 3.7 What the conflict checker and the new goals change (replay, 2026-11-20)

Until 2026-11-20 two settings turned the conflict checker and the round analyst's new
goals off. Before they were removed (DESIGN.md, section 39), the 28 runs of EBD in the
final test and in the planted-problem test were replayed with each of them off: the
recorded replies and researcher results are fed back in, with no model call. No report was
written or judged for this. Table: `tables/switches-replay.txt`.

| | New goals off | Conflict checker off |
|---|---|---|
| Runs compared | 28 | 27 |
| Researchers sent to the same goals | 28 of 28 | 27 of 27 |
| The writer gets the same notes and outline | 28 of 28 | 27 of 27 |
| The writer gets the same guidance | 28 of 28 | 10 of 27 |
| The writer is told to correct a claim of the question | The same | The same: 10 runs, the same text |
| What is no longer there | 21 proposed goals, none of which had a researcher | The lines on critical disagreements in 17 runs (1 to 3 a run) and a line on evidence to keep apart in 1 run |

- With the baseline's number of researchers the new goals change no report: in 8 runs
  EBD asked for a researcher for one, and none was left.
- The conflict checker gives the writer the lines on where the sources disagree. It also
  sent the only researcher of the 28 runs that went out after the first round (the
  question on paid annual leave); that run cannot be replayed without it.
- In these 28 runs the conflict checker takes 40 of a run's 184 seconds and 3% of its
  cost. A run of the baseline takes 118 seconds.
- Whether a report is better with or without either part was not tested.

## 4. What the records explain

From the 12 real queries of the final test (`tables/final-test-what-the-records-show.txt`):

| A run, on average | Baseline | EBD |
|---|---|---|
| Researchers; searches; pages read | 3.42; 25.9; 1.0 | 3.42; 25.9; 0.9 |
| Cited findings in the notes; distinct links | 153; 120 | 152; 121 |
| Scholarly or official sources in the notes | 42 | 41 |
| Rounds of research after the first | 0 | 0 |
| Key questions that ask for part of the answer itself | 66% | 55% |

1. **The research is the same.** What a strategy writes into a brief changed neither how
   much the platform's researchers found nor from which kinds of sources.
2. **EBD's loop did not run.** With the baseline's number of researchers all of them go
   out in the first round. EBD's analysis after the round found 8 necessary things to
   research further in 6 of the 12 runs, and no researcher was left. The test compared two
   first plans and two inputs to the writer.
3. **The plans trade depth for breadth, and it comes out even.** EBD spreads its key
   questions over what surrounds the answer; the baseline keeps them on the answer. The
   breadth won EBD its four questions and cost depth on the five it lost.
4. **The model does unasked what EBD's rules demand.** On all four false-fact questions
   of the planted-problem test the baseline's planner had corrected the fact from its own
   knowledge in its first call. With a weaker model it does so less reliably (section 3.5).
5. **Published deep-research systems gain by searching and iterating more**, which a
   comparison at equal researchers switches off for both sides (DESIGN.md, section 33.2,
   with sources).

Also tried, with no gain: telling researchers to read pages (three times the page reads
at equal cost, fewer findings from fewer sources; DESIGN.md, section 33.4), and a planner
rule that gives the direct answer more room (a trade, not a gain; section 33.5).

## 5. Software tests

- **197 automated tests pass** (`npm test`, no network), 167 of them in this strategy's
  folder: the planning call and its checks (`environment.test.ts`, 17), briefs and key
  questions (`parts.test.ts`, 10), conflicts, round analysis, goals and stopping
  (`loop.test.ts`, 50), the follow-up rules and the writer's input (`focus.test.ts`, 33),
  whole runs through the platform's skeleton with a scripted model (`approach.test.ts`,
  20, and `strategy.test.ts`, 3), the OpenAI adapter (`providers.test.ts`, 3), the run
  viewer's trace reader (3), and the request analysis that is no longer called (28).
- **The approved prompt texts are pinned**: a test fails when a text sent to a model
  changes (`approach.test.ts`).
- **Replays with recorded replies.** Before each change of the final stage, the recorded
  runs were replayed step by step with no model call, and every decision, goal, conflict
  and log line compared (`tables/writer-input-replay.txt`; DESIGN.md, sections 32.2 and
  34.2).
- **Live:** the acceptance checks of section 3.6, and 70 recorded runs in `runs.csv`, all
  ended ok. Earlier live rounds and the failure tests are in DESIGN.md, section 16.

## 6. Limits of this evaluation

- **Small samples.** Twelve questions with one run each can only tell a large difference
  from chance. The weaker-model run has six.
- **A model is the judge.** It prefers the report shown second (15 of 24 judgments in the
  final test, 17 of 22 in the writer-input check), which is why a question counts only
  when both orders agree. It cannot open links, so no fact and no citation was checked. No
  person has rated the reports.
- **One kind of real query.** The draws are questions on history and society that ask why
  or how; there is no product, travel or how-to request among them.
- **The planted problems are simple** and well known. Nothing was tested with a true fact
  that looks doubtful, so it is not measured whether EBD "corrects" what is right.
- **One model for the main comparison.** Everything in sections 3.1 to 3.4 is on Claude
  Haiku 5.5. Luna has an acceptance run only; GPT-5 nano is a side run outside the
  project's model list.
- **Equal researchers** is one way to be fair. EBD's follow-up rounds cannot run under it
  unless EBD divides its researchers differently; that was not tested.
- **No part of EBD was measured by itself.** No report was made without the conflict
  checker or without the new goals and judged against one made with them; section 3.7
  has only what a replay shows.
- **Cheap screens can mislead.** A screen that put Haiku in the judge's place had the
  rewritten reports preferred in 33 of 43 judgments; the Opus judge had them level.

## 7. Cost of the tests

| | Spend |
|---|---|
| Final test (32 runs and the judge) | $13.21 |
| Analysis after it, with the writer-input check | $4.13 |
| Planted-problem test (24 runs and the judge), with its plan check | $7.60 |
| Weaker models: planning probes and the run on GPT-5 nano | $0.43 and at most $2.78 on the OpenAI key |
| Acceptance checks | $0.19 and $0.04 |

A run costs about $0.28 to $0.36 on Haiku 5.5, most of it the search fee of $0.01 a search.

## 8. What is in this folder

| Path | Contents |
|---|---|
| `runs.csv` | One line for each of the 70 runs: test, question, side, model, researchers, searches, tokens, cost, time, length of the report, code version |
| `questions/` | The question sets with their checklists or planted points |
| `judgments/` | The judge's output for every call: verdicts, reasons, scores, quotes |
| `reports/` | The 70 reports, by test, named `<question>-<side>.md`, and the 12 reports written again for the writer-input check |
| `tables/` | The tables the scripts printed, as text |
| `scripts/` | The scripts that made the specs, ran the judge and printed the tables. TypeScript files are kept as `.ts.txt`: they ran from `local/ebd-heldout/` on the behaviour design lead's machine, and are here for the record |

Names: `final-test` uses the label `ebd-one` for EBD in its judgments; `p01` to `p04` and
`pp01` to `pp12` are planted-problem questions, `s01` to `s12` the real queries. In
`runs.csv` the code version of the final test reads "d906c5d + uncommitted changes": that
state was committed afterwards as `5b84010`. The planted-problem test and the run on GPT-5
nano ran on the state committed as `bd19ea8`.

The full run records (every decision, every researcher's notes, every model call) are too
large for the repository (29 MB). They are on the behaviour design lead's machine under
`local/ebd-heldout/`, with a browsable copy built by the run viewer
([../viewer/README.md](../viewer/README.md)), and nearly every run since 2026-11-19 is
traced, call by call, in the self-hosted Langfuse on that machine.
