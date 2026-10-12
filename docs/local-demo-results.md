# Local baseline demonstration — 2026-10-12

Based on upstream `d24a40d`, on the separate `codex/langfuse-baseline` branch.
The archived custom Python platform and prior UI branch were not ported or
modified. The cloud baseline strategy remains unchanged.

## Completed run

- Question, verbatim: `What is EBD (Environment Based Design)?`
- Run: `20261012-202641-baseline-local-b06a5d-1f94`
- Trace: `056773c94aac639f10fd28beec10736c`
- Source mode: local corpus of eight readable downloaded EBD papers.
- Model: local Qwen via llama.cpp Chat Completions; Q4_K_M weights, Q4 KV;
  262144-token window and one slot confirmed through the running server.
- Strategy: baseline; researcher allowance 10, used 4 across two rounds.
- Result: 4 successful researchers, 0 failed; report produced in 360076 ms.
- Tool operations: 28 offline searches and 4 document reads, not web searches.
- Reported cumulative usage: 274650 input tokens and 14714 output tokens over
  24 model calls. These are cumulative counts, not one context-window input.
- Langfuse 4.57.0: 80 ingested observations, 24 generations and 32 tool spans;
  no ERROR observations. Plan, research, observe, finalize, write and completed
  root are present under one trace, with parent/child relationships.
- Report: 9859 UTF-8 bytes, six source URLs; runtime diagnostics only note the
  offline source mode. No output-limit diagnostic in this final run.
- API charge estimate: zero for local inference; hardware/electricity excluded.

The graph and individual operations were checked through actual model requests,
the running Langfuse v4 Observations API and the saved run records. The exported
waterfall script parses, its HTTP preview returns the HTML, and generated secret
values were checked absent from the exported artifact. Native UI authentication
is left to the user using their machine-local generated login.

The model initially interpreted EBD through healthcare/building design. Its
research notes and final report distinguish that interpretation from Yong Zeng's
engineering methodology using the available papers. This makes the demo useful
for examining how a plan changes after source retrieval; it does not establish
the accuracy of every statement in the report or a scientific advantage over
the project's other model/strategy arms. Several catalog records have only the
lab's publication index as their source URL; citation precision is limited there.

## Retained development attempts

The first full run (`20261012-201622-baseline-local-b06a5d-2cd3`) completed but
had one failed researcher and a truncated writer output. It is not the final
demo. A subsequent development run was interrupted before completion.
These records remain under ignored `local/` directories. The final-only native
tool configuration, explicit thinking-disable request and local output-limit
diagnostics were applied before the final run above.

## Code checks

34 tests pass; TypeScript typecheck and production build pass. Controlled tests
cover loopback-only configuration, bounded parallel tool batches, correlated
declined results, token/tool counting and local writer truncation. They support,
but do not replace, the actual run documented above.

The setup secrets, corpus, full observations and generated HTML/report are
machine-local ignored files. They are not included in this branch's Git commits.
See [run instructions](local-langfuse-demo.md).
