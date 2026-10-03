# Run Baseline revision 3

`baseline@3` uses the same Planner -> acquisition/analysis -> Writer -> Reviewer
flow as [revision 2](baseline.md), with larger resource allowances. It pins
Planner 2, Analyst 2, Writer 3 and Reviewer 2. Earlier method and role revisions
remain available. Select `method_revision: 3`; the wire schema remains 1.
It also pins `web.search@2`; see [search profiles](tools.md#search-revision-2).

| Allowance | Default | Accepted values / scope |
| --- | --- | --- |
| Research rounds | 2 | 1–2; analysis can stop early when sufficient |
| Attempted source URLs | 20 | 1–20 across the entire run, including failed fetches |
| Queries | 2 | 1–4 per round; previously searched strings are deduplicated |
| Discovery results | 5 | 1–10 per discovery call |
| Draft/review pairs | 4 | 1–4; report revisions are separate from research rounds |
| Assembled evidence tokens | 131,072 | 512–196,608; excludes instructions, analysis and report |
| Assembled evidence bytes | 524,288 | 1,024–786,432 UTF-8 bytes |
| Saved-text scan bytes | 262,144 | 1,024–1,048,576 per source per round |
| Agent context | 262,144 | Each of the four roles; host/model limits can narrow it |
| Agent task input bytes | 1,048,576 | Structured and rendered task input |
| Agent model request bytes | 2,097,152 | Independent request byte bound |
| Agent output | 8,192 tokens | Per model call; final output still capped at 65,536 bytes |

## Search preparation and screening

The Workflow's pure SearchPolicy quotes explicit multiword subjects in
Agent-generated queries and reduces retrieval instructions to their cited title,
named author and year. Host-provided `queries` remain literal in the first round.
Queries containing internal retained-source IDs are recorded as skipped queries;
they are not sent to Internet search. This does not implement the separate
gap-driven reader.

`search_topic` optionally specifies the subject. Without it, simple definition
subjects and expanded parenthetical names are inferred from the question. The
policy requires subject terms in discovery titles/snippets before projecting
URLs; it is a lexical heuristic, not a semantic model. If all web rows are
rejected, the configured scholarly fallback still runs. Raw tool results remain
saved, with separate selection artifacts recording original/executed query,
subject, accepted/rejected ranks and reasons. `selection_ref` links those
decisions from each successful discovery entry in the result manifest.

For the supplied example, `Environment-Based Design` is inferred as the subject,
so Evidence-Based Dentistry and Evidence-Based Design do not satisfy it. An
explicit subject is useful for other question forms or domain vocabulary.

Evidence selection retains the existing relevance-window and equal-allocation
policy. Revision 3 permits up to 65,536 selected bytes per source instead of
16,384. Small-source unused allocations are still not redistributed. Larger
allowances do not themselves add model reranking, targeted gap-driven reads
or a stricter report completeness gate. Writer 3 explicitly distinguishes
source-document reference numbers from report citation IDs, duplicate copies
from independent evidence and author affiliations from origin claims.

Default evidence counts and complete provider-request preflight both estimate
`ceil(UTF-8 bytes / 4)`. The request audit records `estimator`, `text_bytes`,
`estimated_tokens` and `verified_tokenizer: false`. These estimates are not exact
provider counts. Evidence strict mode requires a registered model tokenizer;
provider usage is measured separately from actual responses.

The default Engine grant permits 32 model calls, 128 tool calls, 4,096 storage
writes, 2,048 storage reads/status reads, 64 MiB source bytes and 128 MiB storage
bytes/read bytes. The whole tree shares the grant and deadline; rounds do not
reset it. The request defaults to 600 seconds and accepts up to 1,800 seconds.
The supplied expanded request uses 1,800 seconds for its real research retry.

## Run and inspect

[examples/baseline-request.json](../../examples/baseline-request.json) now selects
revision 3, 20 attempted sources, two rounds, 128k evidence tokens and a 512 KiB
evidence byte cap. Use a fresh `client_request_id` for a new run; an identical
identity/request retrieves the earlier result instead of rerunning it.

```shell
uv run --locked python examples/live_research_check.py --request examples/baseline-request.json --store local/my-expanded-baseline --output local/my-expanded-baseline-evidence
```

The same request works through `deepresearch research` and
`POST /api/v1/research-runs`. Report, saved source/context, artifact, event/SSE and
usage retrieval retain the [existing interface](research-service.md).
Inspect `stop_reason`, every analysis's `sufficient`/gaps, source failures and
review output when assessing report quality; an accepted draft alone does not
establish complete research coverage.
