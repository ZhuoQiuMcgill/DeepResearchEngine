# Research acquisition and controlled context

Recorded on 2026-10-02 from the user's requirements. This preserves the acquisition
agreement. Stages 1 and 2 are now implemented; see the
[actual structure](project-structure.md), [Workflow guide](../usage/workflows.md)
and [acceptance](../research-acceptance.md) for executable interfaces and checks.

## Decision

A Workflow is a reusable research method. Baseline and EBD compose platform
capabilities and shared workflow components, with different Agent roles and
selection/context policies.

Discovery, retrieval, retention and model context are separate operations.
Agents may submit structured source requests. A model-free acquisition
component processes a selected URL manifest, retains sources, and returns
metadata/references. The orchestrator chooses which saved content enters each
Agent's context. Fetching must not implicitly deliver text or preview to a model.

Reuse existing Toolset, Storage and Connections. Add shared orchestration and
token measurement, rather than another HTTP fetcher, extractor or unmanaged
SQLite writer.

## Existing capabilities and verification boundary

The [tool guide](../usage/tools.md), [Connections guide](../usage/connections.md),
[Storage guide](../usage/storage.md) and
[platform acceptance](../platform-acceptance.md) document these capabilities:

| Capability | Existing behavior | Additional work |
| --- | --- | --- |
| `web.search` | Literal query, bounded discoveries, backend observations | Query planning, persisted discovery sets and candidate selection |
| `web.fetch` | One URL, static retrieval/extraction, committed snapshot, bounded preview | Manifest scheduling, item state and batch limits |
| SnapshotStore | Immutable original/text/index/manifest and provenance | Acquisition catalog projection and tokenizer-specific measurements |
| `document.read` | Authorized saved ranges, no network or new extraction | Context selection and explicit delivery |
| `Engine.run_tool` | Recorded tool execution without a model conversation | Reusable component owning batch lifecycle |
| Evidence binding | Scoped source access; references are not permission | Bind selected sources/ranges for each consumer |

The search field list below was audited against current
`src/deepresearch/engine/toolset/search.py` and `catalog.py`, and exercised through real
Workflow discovery. Raw results are retained as JSON artifacts, available through
bounded saved reads in the [Research API](../usage/research-service.md).

## Documented general-search payload

Input: `query`, optional `max_results` (default 5, integer 1 through 10).
Queries must be nonblank and fit 4,096 UTF-8 bytes. No public backend, domain,
date, language, pagination or sort arguments are documented.

The result payload contains:

- `query`, `searched_at`;
- `backend_policy`: `configured_order`, `active_order`, `disabled_backends`;
- `backend_attempts`: each attempt records `backend_attempt_index`, `backend`,
  `declared_provider`, `outcome`, `elapsed_ms`, `returned_count`, `kept_count`,
  `error`;
- `results`: each candidate has `rank`, `title`, `url`, `snippet`,
  `source_date`, `backend`, `declared_provider`, `discovery_only`,
  `truncated_fields`.

Unknown dates are null. `discovery_only` is true: titles/snippets are discovery
metadata, not retained or independently verified full text. Truncation is
identified for titles/snippets; URLs are not truncated.

Current usage/acceptance identifies DDGS Yahoo as active, with Bing as its
declared underlying provider. Google is disabled pending its fidelity gate.
There is no hidden engine merge, query rewriting, automatic pagination or
retry. The limit does not guarantee that many usable candidates. Literal
`site:` query syntax is not enforced domain filtering.

The payload is inside a recorded public tool result, not an unwrapped list.
Check successful execution and complete recording. Preserve run/action identity
to connect selected candidates to their discovery call. Crossref and OpenAlex
have distinct metadata schemas; neither represents fetched paper full text.

## Proposed contracts

Versioned shared workflow schemas are pinned by methods and referenced by
Agent output schemas. These names/fields are proposed, not existing public DTOs.

A **FetchManifest** is a bounded source list:

```json
{
  "schema_version": 1,
  "items": [
    {
      "item_id": "source-001",
      "url": "https://example.org/paper.pdf",
      "discovery_ref": null,
      "reason": "Read the original method description"
    }
  ]
}
```

The host supplies batch identity, authority, concurrency, deadlines and resource
limits. Agent output cannot supply grants or override those controls. Validate
the manifest before dispatch; preserve query strings/source identity in dedup.

A **SourceManifest** records each item's discovery identity, requested/final URL,
execution status, recording/persistence status, source run, snapshot reference,
media/extraction facts, text size/hash, available ranges, token measurements
and safe errors. Return bounded metadata/references; omit text and preview from
the Agent-facing manifest. Reuse snapshot facts/receipts rather than maintaining
a divergent document store.

SQLite owns the catalog, operations and workflow state. Retained bodies remain
in Storage-managed immutable artifacts. The requirement is durable, queryable
retention; it does not require every body in a SQLite text column.

A **ContextPlan** selects snapshot references, exact ranges, recipient role,
rendering format and target token budget. A model-free reader/context assembler
materializes the selected content. Retain source/range/hash identities alongside
the actual delivered content for citations and replay.

Current `document.read` ranges are one-based and end-exclusive: at most 200 lines
or 10 physical PDF pages, and 65,536 text bytes per request. Follow its opaque
continuation with the original range when necessary. Renew explicit source
access when acquisition/analysis use different runs.

In a strictly controlled-context method, analysis/writer Agents have no direct
`web.fetch` grant. Giving an Agent `document.read` still lets returned text enter
its conversation; restrict it to host-selected ranges or deliver selected text
as explicit input. Saving a fetch before returning it to the same Agent does
not implement context separation.

## Token measurement

Measure retained text outside model conversations. A measurement names text
hash/range, target model, tokenizer identity/revision, rendering revision,
count and whether it is verified or estimated. Cache by that complete identity.
An unsupported tokenizer means labelled estimate or unknown, not exact count.

Full-document tokens help planning. Selected rendered evidence tokens describe
the intended context contribution. Total request size also includes system/task
instructions, tools, wrappers, history and reserved output. Counts of separately
tokenized fragments need not sum to the count of the assembled input. Recount
the actual assembled input when a verified model profile permits it. Provider
usage after a call remains separate from prospective content measurements.
Measurement alone does not establish strict token-budget enforcement.

## Reusable component and lifecycle

```text
query plan -> search -> persisted discovery -> selection -> FetchManifest
  -> model-free acquisition -> snapshots -> SourceManifest
  -> token measurement -> ContextPlan -> selected saved reads -> Agent input
```

Acquisition owns validation, bounded scheduling, conservative deduplication,
explicit cache freshness, item states, failure policy, cancellation and
checkpoints. Retain successful items when others fail. Unknown dispatch/commit
outcomes require reconciliation, not silent refetching. Item calls obey shared
batch/workflow limits; creating standalone runs must not reset those limits.

Implemented placement within the modular structure:

```text
workflows/contracts.py               # manifests and ContextPlan
workflows/components/discovery.py    # preserve provider discovery schema
workflows/components/acquisition.py  # reusable model-free batch execution
workflows/context.py                # abstract host port and node lifecycle
workflows/components/context_selection.py # saved read / selection / delivery
engine/providers/tokenization/      # model/tokenizer-specific measurement
methods/baseline/                    # baseline selection/context policy
methods/ebd/                         # future EBD selection/context policy
application/                        # shared lifecycle/query facade for HTTP/CLI
```

The current layout implements the selected two stages. Methods compose components and supply
policy. HTTP/CLI use the same application service. Frontend source queries
expose item state, snapshot metadata, token measurements and authorized
previews without accessing SQLite directly.

## Hooks

Search, candidate selection, per-URL acquisition, snapshot publication,
measurement, context selection and context delivery expose stable node
lifecycle Hooks. Node points are `node.before`, `node.after`, `node.failed`;
selection points are `discovery.select` and `context.select`.
Observers receive bounded immutable facts/references. Control extensions return
validated decisions before execution intent freezes, within current authority
and resource/context budgets.

Mandatory retention, recording and context policy belong to base components.
Optional extensions observe progress or customize permitted choices. A complete
method runs without optional extensions. Committed events support frontend
live progress/replay. SSE is implemented at
`/api/v1/research-runs/{run_id}/events/stream`, with committed sequence IDs and
`Last-Event-ID` replay.
