# Run viewer

Static HTML pages that let you step through a research run and check what each
agent did. It works for any strategy's run records. EBD runs get the full view.

```
npx tsx src/strategies/ebd/viewer/build.ts                  # every run under local/runs, local/checks, local/experiments
npx tsx src/strategies/ebd/viewer/build.ts local/checks/<runId>   # one run, or any folder of runs
```

The pages are written to `local/viewer/`. Open `local/viewer/index.html` in a
browser. The pages are self-contained and need no network. Rebuild them after
new runs.

## What each page shows

| Step | Content |
|---|---|
| Overview | Things to check (failed researchers, invalid or dropped briefs, rejected model calls, fallbacks, sections without `[Qn]` headings, unknown citations), the stop kind and its reason, each assumption's verdict and the goals that checked it, the goal tree with the tree metrics, and the conflicts |
| Init: plan | The request analyst's call (input, reply, check errors), the request analysis (frame, ROM, questions), the goal table, and the first briefs with their full instructions |
| Researchers round N | Each researcher's brief, queries, the sources the tools reported (cited or not), its diagnostics, how its sections were mapped to goals, and its notes with an evidence ID on every finding and gap |
| Observe round N | The conflict checker's and round analyst's calls, with the exact input, the reply and any errors the code checks found; what the code did (goals settled or requeued, the evidence floor, proposals accepted or rejected, moot goals, the stop check); the goal table with its changes since the last step; conflicts; the next briefs |
| Writer input | The outline, the guidance and the material the writer received, with the platform's provenance diagnostics |
| Report | The final report |

Click an evidence ID such as `r2-b1-f3` to see its line, its goals and its hosts,
and jump to it in the researcher's notes. Use the ← and → keys to step through
the run.

## How to verify a run

1. Start at **Things to check**.
2. For each answered goal, open its evidence IDs and confirm that the lines state
   what the parts of `done when` ask for.
3. For each conflict, read both sides.
4. For each contradicted assumption, confirm that the guidance tells the writer
   to say so, and that the report does.
5. Compare the stop reason with the goal table: "complete" needs every necessary
   goal settled.

This is a development tool. The strategy never imports it, and the viewer only
reads the run records the platform writes.
