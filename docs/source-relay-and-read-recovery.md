# Source relay and read recovery — 2026-10-13

Branch: `codex/langfuse-baseline`; no changes to the EBD strategy or main.
This revises shared retrieval/provenance handling used by the baseline demo.
It does not change the fixed experiment question, model, context window,
researcher allowance or two-round baseline limit.

## Source relay

The graph now supplies researchers with a structured source registry from
completed successful earlier rounds. Registry entries originate in actual tool
records, not URLs parsed from notes or generated assignments. Each inherited
source retains `originBriefId` and, for local web tools, `readState` (`snippet`,
`read`, `truncated` or `failed`). Same-round future results are never included.

Local web tools allow reading those registered public URLs without an artificial
repeat search. Source merging recognizes their provenance and retains the
origin; inherited eligibility does not imply that the receiving node read the
full page. Prompts distinguish source support passed in notes from fresh page
reads. The writer receives the graph-supplied registry separately from findings
so snippet-only support and read failures remain visible.

Synthesis no longer marks a real tool-backed source everywhere merely because
one researcher listed it as unknown. Truly unsupported links remain marked.
Report citation checks now require a recorded source: a URL in free-text notes
alone cannot establish provenance. Additive optional fields preserve version 1
contracts and old run readability; raw historical results are unchanged.

## Read recovery

Tavily Extract now uses `advanced` rather than `basic`, through the existing
official LangChain integration. Tavily documents advanced extraction as the
more thorough option; it does not promise access to every site. See the
[official Extract reference](https://docs.tavily.com/documentation/api-reference/endpoint/extract).
API credits for search/extraction remain unpriced in the run ledger.

An extract result must contain nonempty text for the requested public page to
count as usable. Empty, unrelated or error responses, including thrown request
errors, return a structured unavailable result rather than aborting the whole
researcher or fabricating content. The source is marked `failed` and the failure
remains in diagnostics.

The response includes a bounded query suggestion derived from the searched
page's title, targeting an author manuscript or accessible original copy.
Researchers are told to use that query and read a different returned source,
or record the missing information if their allowance is exhausted. There is no
hidden retry, extra extraction or off-ledger search inside a tool call.
Repeated failed URLs are skipped, including failures carried from prior nodes;
the skipped tool invocation consumes the model's allowance but is not counted
as a provider read. No local-corpus fallback or paywall bypass is added.

## Checks and limits

Controlled tests cover trusted inherited versus invented URLs, source origin
relay, avoiding cross-node annotation contamination, failure/exception recovery,
read accounting, and rejecting empty or unrelated extract content. Forty-five
tests, typecheck and build pass. A separate live `check-strategy` baseline run
assesses the actual outcome and all required interface checks.

An eligible URL establishes provenance, not the correctness of each claim.
Transferred notes can still contain interpretive mistakes, inaccessible sites
can still fail, and excerpts can still be incomplete. These states must remain
visible rather than being converted into a clean-looking success record.
