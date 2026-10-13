# Baseline concept scope revision — 2026-10-13

This is a change to the baseline method on `codex/langfuse-baseline`, not an EBD
strategy change. The earlier live run and its scope-error note remain intact.
The fixed question remains `What is EBD (Environment Based Design)?`.

## Mechanism

English definition questions (`what is/are`, `define`, `definition of`) and
questions with an explicit capitalized acronym expansion receive one
source-discovery assignment before any planner decomposition. That assignment
asks for the exact concept's original definition, origin and field without
preselecting a domain. It contains no topic-specific answer, author or URL.

After the identity assignment returns, the planner receives the actual notes
and failures. Its parallel assignments each receive those same prior-round
notes plus the verbatim question and scope constraints. They do not depend on
other same-round researchers' future output. Each researcher must obtain its
own cited sources through the real tools; forwarded notes are orientation, not
new tool provenance.

The later source-relay revision adds a structured registry of actual prior-round
tool sources, allowing explicit inherited support and page access while retaining
origin and access state. Text-only URLs still do not establish provenance. See
`docs/source-relay-and-read-recovery.md` and `docs/web-baseline-source-results.md`.

Other questions retain initial parallel decomposition plus an optional gap
round. Follow-up briefs also receive prior notes. Both paths retain the
two-round limit and existing researcher/tool budgets. If no budget remains,
the strategy stops and the writer must explain any unsupported scope.

Shared research and writing instructions preserve supplied acronym expansions
and prohibit replacing a subject with a more popular meaning. A limited lookup
supports uncertainty about what was found, not a claim that a concept does not
exist. Explicit question wording takes precedence over a planner's provisional
interpretation.

## Limits and comparison

This scheduling change prevents decomposition before discovery and supplies
the missing dependency data. It does not guarantee that a model interprets
every page correctly. The heuristic currently covers English definition
questions and explicit acronym expansions; it is not a universal ambiguity
detector. Identity discovery consumes the first round, leaving no third round
for gaps in subsequent work. Forwarded notes can contain source errors or
untrusted text, so researchers are instructed to treat them as data.

The new run is a revised-baseline demonstration. It must not be pooled with the
earlier baseline or used as a controlled causal comparison: prompts and
scheduling both changed, and search/model responses can vary. Future baseline
versus EBD experiments must lock and disclose the method revision first.

Controlled tests exercise source-first scheduling, prior-note delivery to
parallel assignments, verbatim scope preservation, the two-round limit and
zero-budget stopping. Actual local Qwen + Tavily runs remain required to
assess the output; passing execution checks is not a claim of answer accuracy.
