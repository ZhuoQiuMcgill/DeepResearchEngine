# Baseline revision 13 source and role contracts

Select `method_id: "baseline", method_revision: 13`, or use
[the standard request](../../examples/baseline-request.json). The HTTP request
schema and default revision 1 remain unchanged. Revision 12 permits forty attempted URLs across two rounds, with a 262,144-token allowance per Agent.
Execution success, evidence sufficiency and report acceptance remain separate.
After a run fails, `quality` can remain the last completed assessment while
`sources` includes later completed acquisition. It is not a fresh recount of
every source in a failed run. Use the source manifest for acquisition totals;
phase 34 records an actual round-two transport failure with 18 retained sources
and a round-one quality checkpoint covering 10. Explicit assessment freshness
metadata and resumable failed runs remain limitations.
Revision 11 retains its twenty-URL schema. Revision 12 keeps its predecessor's
role pins and defaults except the fetch ceiling; `max_distillation_calls` still
defaults to 20, and can be requested up to 40 subject to host model/descendant
grants. Host defaults remain 40 total model calls/descendants, which also cover
planning, selection, analysis and report review. Increasing fetch capacity does
not grant additional model calls or force the method to spend every URL slot.
The host's default shared tool allowance is 512 dispatches: saved-document reads
consume it as well as search/fetch. It remains finite and independently
configurable through `EngineSettings.limits`; it does not change the method's
forty attempted-URL ceiling. The former 128-dispatch default exhausted during
ordinary scans of long reference documents, even after removing bridge calls.
See [cross-scenario diagnostics](../scenario-systemic-diagnostics.md).

Revision 13 changes only the `web.fetch` pin from 2 to 3. Agent bundles, input
schemas, rounds, attempted-URL ceiling and context allowances are identical to
revision 12. The parent may retain validated static content after a separately
supervised optional renderer fails. `source_descriptor.fetch_supervision` and
bounded Distiller feedback expose selection, failure and unknown network usage.
This status is metadata, not source evidence or a claim of content completeness.
See [fetch supervision](web-tools.md#supervised-fetch-revision-3).

| Stage | Role pin | Input and result |
| --- | --- | --- |
| Plan | Planner 5 | Original question, query allowance and research time → questions, literal queries and outline |
| Select | Selector 4 | Discovery cards, acquisition history and remaining budget → exhaustive, exclusive candidate classifications |
| Distill | Distiller 4 | Identified archived chunks and plan → findings with verified original quotations, or an explicit quarantined chunk |
| Analyze | Analyst 6 | Source metadata, digests and verified text → findings, gaps and supported follow-up reads/queries |
| Write | Writer 7 | The same eligible evidence, analysis and quality → English report with source-ID citations and References |
| Review | Reviewer 6 | Draft and supplied evidence → accept/revise; deterministic checks also gate publication |

Every role receives the same persisted `research_context.as_of` in UTC.
`repair` is empty on the first attempt and contains the previous output, attempt
number and host errors during a repair. These are data, not new instructions or
authority. New role bundles retain the output schemas of their predecessors. Selector records
link the actual accepted invocation input (including repair and research time);
`initial_input_ref` separately retains the original candidate payload. Planner
query-count violations use the same bounded repair before any search is dispatched.
Finding validation returns bounded `validation_errors` with exact field paths,
unknown/duplicate source IDs and the delivered `allowed_source_ids` and
`allowed_questions`. This lets the existing repair act on a concrete violation;
the host never guesses a replacement citation or expands its evidence authority.

Writer nodes in revisions 11–13 also retain their complete structured input,
including research time and any repair feedback, in `detail.input_ref` before
invocation. This reference matches the actual rendered task and follows the
same run-scoped artifact access rules as other roles. Old node records are not
rewritten to manufacture missing references. The offline store auditor counts
logical Agent nodes carrying an explicit repair input; API restarts inside one
node are separate. `role_repair_events` retains the narrower generic event count,
and `role_repair_inputs_unavailable` exposes incomplete historical coverage.

The method executes original model queries literally. Bounded recovery variants
remain separately recorded queries under the existing recovery allowance. Search
metadata, including title and available bibliography, remains labelled discovery
data when carried alongside the archive; it cannot substitute for source text.

`source_descriptor` declares original/final URLs, media type, classification,
line/page bounds, supported ranges, capture failures and retrieval time. Null
metadata is unknown. Retrieval time and Last-Modified do not establish publication
time, price validity or source accuracy. Explicit HTML head/meta publication and
modification declarations survive as `document_dates`, with their original field
names/values, conflicting assertions, a declared-not-verified label and bounded
omission counts. Related-article `<time>` values are not publication metadata;
JSON-LD/PDF date discovery is not guaranteed. PDF source descriptors additionally
expose the optional `pdf_extraction` diagnostic from web.fetch revision 2: native
and fallback page counts, disagreement reasons and unresolved control glyphs.
This is a tool-level extraction improvement, not a change to the baseline role
instructions or research policy; fallback pages may still contain merged words.
Extraction /9 can recover ordinary word spacing on a fully aligned page while
retaining explicitly font/operand-bound undecoded glyph names. Its optional
`opaque_glyph_alignment.retained_glyph_names` count indicates unresolved symbols,
not successful decoding. The model still receives the unchanged glyph names in
the original text; literal quotation validation does not establish formula meaning.
`read_retained_range` and full scans use
the same lifecycle and DocumentSlice validation. Range manifests record partial
completion explicitly and keep byte offsets, SHA-256 and action IDs.

Settled `web.fetch@2`/`@3` failures carry `details.failure_scope: "fetch"`.
Resource limits additionally identify resource URL/type, limit scope/kind and cap
where known. Classified, recorded, noncommitted local limits/timeouts and network
failures can be isolated after complete cleanup. A GET with no HTTP reply may retain
`observed_effect_state: unknown` while its local snapshot state is known
`not_committed`; it is recorded as a failed source and not automatically retried.
This does not make the whole store commit unknown. Global/unclassified limits,
cancellation, unknown execution/commitment and incomplete recording/cleanup stop execution. Chromium
may retain usable DOM after a resource-scoped auxiliary failure; failures remain
in provenance and evidence warnings. Missing dynamic content is not declared complete.

Roles with a `repair` input contract can receive the durably recorded raw text of
a failed output validation as a **diagnostic artifact**, never a valid Agent
output. Ordinary decisions have at most two attempts. Distillation also has at
most two attempts, counted against the unchanged shared distillation allowance.
Persistent content/format failures quarantine that chunk; they do not cancel
independent document workers. The same chunk/content hash is not retried again
in later acquisition batches. Infrastructure failures still propagate.

Transient model HTTP failures first pass through the application's
[orchestrator recovery policy](research-service.md#orchestrator-recovery-during-execution).
By default, recorded rate limits and selected temporary server errors permit
three replacements of the same role/input with shared provider cooldown.
Independent workers keep their results. Unrecoverable or exhausted failures
still propagate. These infrastructure replacements count toward the real host
model/descendant grants, but do not increment the method's logical distillation
counter. A format repair remains another logical distillation call. Neither path
refills the shared grants, and all real attempts remain visible in usage/events.

Quotation comparison can map simple inline HTTP Markdown links to their visible
labels, retaining character offsets into the immutable original. Every accepted
quote is replaced by the actual original contiguous substring and subsequently
gets original byte offsets/hashes. Unsupported markup stays literal; no fuzzy
fact matching is allowed. Unmatched quotations are excluded with recorded
adjustments and an extraction limitation; already verified findings are retained
without another model rewrite. Unknown identities still require repair or quarantine.

Complete, explicitly nested HTML tables permit HTML ASCII whitespace between
validated cell/row/section boundaries to differ. Every relationship tag, cell,
attribute and value stays exact; vertical tabs, entity gaps, literal code and
unsupported/malformed tables grant no new equivalence. An attribute-free `br`
inside inline presentation remains literal while independent links on either
side can still be quoted. It never becomes permission to join across that break.

With the same admitted HTML provenance and recorded Markdown context, U+2011
nonbreaking hyphens and ASCII hyphens can compare inside fully included lowercase
word compounds or one-to-three-digit integer/word compounds in prose paragraphs
and flat unordered-list paragraphs. This deliberately narrow subset excludes code,
URLs, raw HTML, numeric ranges and ambiguous notation. It is not global Unicode
normalization or a semantic classifier of lowercase identifiers. Existing matches
retain priority; returned quotations still contain the original hyphen and byte
offsets. Phase 31 records exact-input replay and archive-to-Analyst tests.

Analyst requests beyond known source capabilities are recorded as invalid read
adjustments and explicit gaps, without dispatching impossible reads. This keeps
an otherwise useful partial analysis and does not claim that the missing pages
were fetched or read. Inconsistent finding/source bindings still require repair.

Publication requires body and References source-ID sets to match, unique reference
entries, and each reference URL to match that source's original or resolved URL.
References may use `[source-id] URL` or `[source-id](URL)` with a plain exact ID;
body citations remain standalone `[source-id]`. Parsed Markdown links retain
destination binding, including balanced parentheses and optional titles. Images,
code, escaped or ambiguous labels cannot manufacture entries. Raw HTML References
paragraphs and reference aliases remain unsupported. Parser IndexError or
RecursionError produces repair feedback rather than terminating the method.
An ID and URL may occupy continuation lines of the same Markdown paragraph or
list item. The next source label or block ends that entry; URLs are never borrowed
from another entry, paragraph, heading or code block. Additional wrong URLs still
fail the binding check. Historical reports and failed run states are unchanged.
These checks cannot be overridden by Reviewer acceptance. Writer repairs receive
the previous draft as well as feedback. Semantic support still needs model review
and retained-source inspection; the mechanical gate does not certify truth.

For frontend and Hook consumers, existing source/node/quality views remain valid.
New recorded event kinds are `workflow.role.repair`, `workflow.evidence.quarantined`
and `workflow.source.range_partial`; large diagnostic bodies remain in artifacts.
Read those references through the existing bounded artifact API. Failure events,
invalid raw output and excluded findings remain visible in history.

See [the original audit](../systemic-error-audit.md) for failure evidence and
[the repair/test record](../systemic-repair-results.md) for measured outcomes.

## Cross-scenario boundary corrections

Subject inference only recognizes an explicit definition or a matching adjacent
acronym expansion. Capacities, dates and arbitrary quoted comparison criteria
do not replace the research subject. Original questions remain unchanged.

A completely recorded and cleaned-up scholarly HTTP 429 with no Storage commit
can disable that provider for the current retrieval call while other sources
continue. The original terminal and generic effect uncertainty remain recorded;
the executor retains its blocked quota. No retry or quota escalation is added.
Unknown commit/execution, cancellation and global limits still stop execution.

Generic HTML extraction resolves anchor hrefs against the final document URL
and an applicable explicit base href before the library converts them to
Markdown. The original bytes remain immutable. Extraction revision
`trafilatura_markdown/12+trafilatura/2.2.0+markdownify/1.2.3` keeps normal library comment cleanup;
revision 2 was withdrawn during verification after an HTML-comment regression.
Historical snapshots keep their own extraction identity and bytes.

Revision 4 additionally restores short-document structure when the alternative
extraction retains every previously selected text block, ignoring whitespace and
explicit navigation. It preserves code indentation, ordered lists, table columns,
exponents, image URLs and image-only link destinations. Image links are restored
after body selection to avoid changing the extractor's content-density decisions.
Revision 5 adds conservative long-document recovery. It measures overlap with
substantive DOM paragraphs within a sole article/main landmark (otherwise the
body), excluding explicit navigation and hidden elements. Substantial omissions
trigger a second pass with a neutral content wrapper and layout attributes removed
in a copy. A candidate must improve measured coverage and preserve previous text
blocks, source destinations and code. This prevents a subsection called `content`
from hiding the rest of a manual, without treating unrelated recommendations as
missing article text. It makes no domain-specific or question-specific decisions.

The optional closed `provenance.html_extraction` diagnostic records primary/final
overlap counts, recovery attempts and substantial unmatched prose. Its
`semantic_verification` is always false: overlap is a heuristic, not proof of
complete capture or correct semantics. Remaining substantial omissions appear in
source metadata and synthesis warnings. Old snapshots and non-HTML formats may
omit this field. The original/text/index bytes, extraction identity and read
offsets remain independently verifiable.

Revision 6 separates content selection from structure conversion. A sole
article/main is selected before library extraction. If lists, tables or code
lose their source structure, a bounded DOM candidate is rendered with
Markdownify 1.2.3. The smallest source container retaining the already selected
prose is preferred; an ambiguous unmarked scope with substantial extra content
is not expanded merely to recover one list. Existing text tokens must survive
in order inside source blocks; original dates/conditions may be inserted, but
numbers, punctuation, negation and case cannot be replaced. This guard does not
change the exact quotation-matching rules.

Revision 7 adds a source-order DOM projection for ambiguous page boundaries,
implemented separately in `engine/toolset/html_selection.py`. An omitted
list/table/code block can be restored beside a retained paragraph in the same
local container. The container must have strong retained-prose coverage; unrelated
article/card subtrees cannot serve as its paragraph anchor. The projection keeps
previously selected source text and must pass the same text/link/code preservation
checks. It does not expand the entire page to recover one block. Optional
`structure.recovered_blocks` and `structure.unresolved_blocks` distinguish partial
recovery; `partially_recovered` still carries an unresolved warning.

Highlighted preformatted code uses original text, avoiding blank lines inserted by
converting nested highlighting divs. Code inside definition lists and tables is
tracked from the retained HTML; code tables keep their cell and indentation
relationships. Literal source links may retain mailto/tel destinations while
executable destinations remain excluded. Revision 8 additionally tracks the source
text of rendered inline code. A formatting newline before an inline identifier
cannot reject otherwise complete structure recovery; block indentation remains
preserved. Those extraction revisions do not change role prompts.

Revision 9 prepares custom inline HTML components before extraction. A custom
element inside an explicit prose block, with only ordinary phrasing descendants
and no declared semantic role, becomes a span in the working tree. Attributes,
text, links and tails stay in place; nested transparent components are processed
from the inside out. This prevents the library from moving links past their
qualifiers or discarding the text after them. Block components, code and explicit
article/hidden boundaries remain unchanged. No domain, question, source wording,
role instruction or historical snapshot is rewritten.

Revision 10 recovers omitted structures inside an authored `section` whose own
prose has at least two retained paragraphs and strong coverage. Nested sections
cannot borrow outer anchors. Local heading-only branches retain the block's
context; separate cards do not contribute headings. Structural recovery counts
are checked against the actual pruned subtree, including intact structures
retained through their children.

Prose diagnostic `dom-prose-overlap/2` measures the final delivered Markdown,
including its tables and literal HTML, rather than the pre-render extractor tree.
`matched_blocks` and `matched_characters` now describe that final check;
`intermediate_matched_*` preserve the pre-structure counts, and
`verification_stage` is `rendered_markdown`. Primary counts and recovery-attempt
flags remain available. This both clears stale warnings after successful recovery
and exposes final renderer differences. Historical `/1` descriptors remain valid.
Presentation markers can still affect literal overlap; this heuristic is not a
semantic loss count and does not relax quotation validation.

Revision 11 adds a bounded DOM text-slot explanation after the existing token
preservation guard fails. An extracted unit must be a concatenation of complete
original slots in source order, within one paragraph, heading, item, cell or leaf
div. Whole omitted slots can be restored; partial slots, changed values/case,
reordered text and borrowing across other records or literal code are rejected
by this fallback. It has a shared two-million-unit work allowance per guard,
65,536-character selected-unit limit, 2,048-slot block limit and 512-state match
limit. Exceeding a limit cannot establish retention. It does not add word breaks
by guessing characters, and does not change the separate quotation matcher.
Original snapshots stay immutable. Explicit authored scope can still include
UI or marketing content; successful structural recovery is not a relevance score.

Revision 12 also checks substantial prose omissions after final rendering. With
one explicit article/main, it projects the missing original paragraphs and local
headings around delivered content. Prior text, source destinations, literal code
and matched paragraphs must survive the final render, and coverage must strictly
increase. Unmarked body scope, multiple mains and independent nested articles
do not authorize new prose. Optional `prose_render_recovery_attempted` and
`prose_render_recovery_applied` flags distinguish this pass; primary and
intermediate counts remain unchanged. Source bytes stay immutable and recovered
output still respects the existing text/index/process limits.

Hardened distillation separately admits a bounded HTML quotation adapter for
sources whose recorded media type is `text/html` or `application/xhtml+xml`. Inside a complete, code-free
archived table it tolerates ASCII whitespace at `td`/`th` content edges and an
optional `</p>` immediately before `</div>`, `</td>`, `</th>`, `</li>` or `</dd>`.
The latter follows [HTML paragraph closure](https://html.spec.whatwg.org/multipage/grouping-content.html#the-p-element).
Cell/row tags, row/column span attributes, numbers, words, punctuation and order
remain literal. A separate plain-text comparison may omit balanced,
attribute-free `span`, `b`, `strong`, `i` and `em` tags within one complete cell.
It never joins different cells or rows. Unsupported children, comments, malformed
tags, attributes, `sub`/`sup`, edit marks and code keep the whole cell literal.
Code, tables that remain incomplete after adding recorded preceding reads, and
other media types receive no HTML adaptation. No approximate text matching occurs.
The returned quote is always a contiguous original archived substring within the
existing 2048-character bound, with original offsets/digests. Normalizations and
excluded findings remain recorded in the validation artifact. Historical raw
outputs and snapshots are never rewritten.

The same HTML-source boundary supports a CommonMark quotation adapter using
`markdown-it-py`. It tolerates parsed emphasis delimiters and the bullet markers
of one flat unordered list, retaining every item's text and order. For a parsed
Markdown table it can omit the delimiter line and exactly source-mapped cell
emphasis, retaining all header/data rows and literal pipes. Parser-normalized
cells, synthetic padded cells and ragged rows do not authorize cell adaptation.
Paragraph soft-break whitespace remains in the original position map, including
legacy pipe-separated paragraphs without a GFM separator. Ordered or nested
lists, blockquotes and code remain literal. Unsupported inline
syntax falls back to exact matching; words, values and punctuation are unchanged.
An IndexError or recursion failure in this optional Markdown parser disables its
format projection while exact matching remains available. It does not authorize
approximating the quote or rewriting model output.
Both adapters require known document-start context: a read beginning at byte zero,
or a contiguous, overlap-checked UTF-8 prefix assembled from already recorded
reads (at most 2 MiB). Missing ranges disable adaptation rather than mistaking a
fragment of a code block for prose. Prefix bytes establish context only; the
returned quote must come entirely from the current read. No fetch or additional
Agent input is introduced. Legacy distillation keeps its explicit strict defaults.

`PreparedQuoteSource` prepares each used source segment once within a distillation
validation call. Repeated findings reuse its parsed projections and packed
original-character indexes; model outputs and match results are not cached.
Instances are local to that call and source, with the same input, context and
returned-span limits as `locate_quote`. This reduces repeated parsing of long
recorded prefixes without altering which original substring is returned.

Hardened distillation can verify a quote across adjacent reads in the **same
actual Agent input chunk**. It checks original offsets, UTF-8 lengths, hashes
and read actions before constructing bounded boundary windows. Missing ranges,
overlaps and multiple matching cross-read locations do not grant a match.
Additional source-access text cannot extend the Agent's quoted evidence. The
legacy strict validator keeps this behavior disabled.

The Distiller 4 output schema remains unchanged. The host retains the original
contiguous quote, anchors `segment_id` to its first part, and adds optional
`quote_bindings` to the validated record. Each entry identifies a retained
`finding_index`, the complete `quote_sha256`, and ordered `parts`; each part has
its original `segment_id`, `start_byte`, `end_byte`, `text_sha256` and
`read_action_id`. These are host bindings, not fields the Agent invents. Filtering
an unrelated invalid finding recomputes the indices. Historical artifacts remain
immutable. Evidence delivery includes all associated segment IDs in the digest.
When the synthesis allowance requires quote-only delivery, each part becomes
its own ContextSelection with the original read action and requested range.
There is no synthetic action covering multiple reads. Store auditing verifies
the binding against both the actual Agent input and the archived source bytes.

Soft word-wrap comparison accepts the seven Latin presentation ligatures as
letters alongside ASCII. It preserves the actual glyph: `dan-` followed by a
newline and `ceﬂoor` can match `danceﬂoor`, but cannot match `dancefloor`. Case,
inline hyphens, numeric/identifier boundaries and the 2048-character original
span limit remain unchanged. This is not Unicode compatibility normalization.

Hardened distillation can additionally compare a PDF body quote across a known
physical page boundary using `pdf_extraction.layout` annotations from the saved
source. Supported metadata is `repeated-page-margins/2` and `/3`; older snapshots without
it keep literal comparison. The withdrawn `/1` layout metadata remains readable
as diagnostic data but cannot authorize omission during quotation comparison.

The tool reconstructs complete visual rows before classifying their position
and font size, requires repetition on at least three pages, and allows varying
digits only for a consistent page counter. A small bold word embedded in a
normal body row and a short rotated chart label are not standalone margins.
Revision 3 allows a repeated family to cover a page dominated by table, caption
or reference fonts: at least three other pages must independently confirm that
complete margin row. The normalized text, edge position, font size and consistent
page-counter sequence must still match. Weak candidates cannot establish a
family or displace independently confirmed margins from the candidate budget.
Each uniquely aligned margin retains its page, original byte range, SHA-256,
kind and repetition count. Layout metadata binds to the whole archived text
hash and physical page breaks; source text is never deleted or reordered.

Comparison may omit only complete marked spans present in the supplied read
window, and the match must cross a recorded page boundary. The returned quote
still contains the full contiguous original text, including intervening margins,
within the existing 2048-character limit. Cross-read bindings and compressed
ContextSelection retain those bytes and original read actions. No extra source
text enters the Agent's input. Analyst metadata carries layout counts rather
than the full offset table.

Layout discovery is bounded to 32768-byte pages, sixteen candidate rows per
page and at most 32 KiB (or half the provenance allowance) of annotations.
Skipped pages, omitted candidates and omitted accepted spans are explicit.
Unconfirmed structure stays literal; these heuristics do not guarantee that all
headers, footers, watermarks or other page layouts are identified correctly.

Nested lists retain their hierarchy. Row/column spans, explicit/reversed list
numbering, definition lists and hyperlinks within preformatted code use a
sanitized HTML fragment when Markdown cannot express the relationship. Ordinary
text stays Markdown. Code checks distinguish source indentation from the extra
indentation required to nest a Markdown code block inside a list. Existing image
anchors are not wrapped a second time. Original bytes remain immutable.

`aria-hidden` alone is not a visual-content exclusion rule: it can hide visibly
rendered content from accessibility APIs. See the
[WAI-ARIA definition](https://www.w3.org/TR/wai-aria-1.2/#aria-hidden).
The selected scope still excludes HTML `hidden` content and explicit navigation.
Static HTML extraction does not claim to reproduce all computed CSS visibility.

The optional closed `html_extraction.structure` records checked/different blocks,
whether a recovery was adopted, its decision and `unresolved`. These are heuristic
structure differences, not a count of false facts or proof that all omitted
content is relevant. Rejected candidates retain the existing archive and an
explicit synthesis warning; `semantic_verification` remains false.

HTML extraction /16 additionally preserves declared inline SVG labels within
already selected table cells. Selection happens before label insertion, using
the existing text/link/code guards. Labels render as escaped, inert text inside
the original cells; no geometry, class, symbol ID or topic knowledge supplies a
value. `aria-labelledby` references must resolve within that selected table and
be unique in a bounded scan of the original document, including excluded IDs;
missing, removed hidden, out-of-scope, recursive and oversized references are
unresolved. Direct SVG title, description and tooltip metadata remain distinct
origins in provenance. Descriptions are not decoded graphical values.

The optional `html_extraction.graphics` (`selected-svg-labels/1`) distinguishes
selection-bound coverage from unassessed candidates. Work is limited to 20,000
selected DOM nodes and 128 SVGs, with a separate 20,000-node ID uniqueness check;
at most 32 diagnostic entries, four ID references
and 256 characters per metadata value are retained. Entry truncation is separate
from audit coverage. Entries identify paths within the selected rendering DOM and
hash parsed SVG subtrees, not original byte ranges. Existing original/text hashes
still bind the snapshot. Whole-document counts reach source descriptors and
revision 11/12 Distiller feedback, including repair attempts; detailed paths and
unread labels are not copied into Agent metadata. Authored recovered text enters
the usual bounded archive reads and quotation checks. No synthetic uncertainty
marker is inserted into quoteable text.

Unlabelled SVGs, conflicting declarations, hidden/presentational graphics and
graphics outside the supported inline-table subset remain explicit limitations.
Coverage counts are not claims that those graphics were semantically understood
or that every icon affects an answer. Scholarly HTML retains its separate
extraction path. No model, role revision, workflow depth or budget changes are
part of this extraction fix.

Full archived scans now use overlapping full line windows, just as PDF scans use
overlapping page windows. Original byte spans verify and remove the duplicate unit;
there is no separate two-line bridge call. The 200-line/10-page request limits,
UTF-8 boundaries, scan byte limits and shared tool-call grant remain enforced.

### Record lists in HTML extraction /13

A partially selected list may recover original omitted fields only when each
record has a unique whole-field anchor, source-order agreement and at least 80%
whole-slot coverage within that record's own selected window. All records must
qualify. Repeated page-wide values, partial field matches or unselected records
do not supply scope. Counts, bytes, alignment states and shared work are bounded.
The existing text, destination and code preservation guards remain in force.
Lists whose direct children are not all `li` retain sanitized source HTML instead
of flattening their nested lists. Original grouping and values survive; markup
can increase archive bytes and context costs. Standard bounded reads and host
budgets still apply. This is a tool extraction change, not a role or baseline
revision. See phase 21 of the systemic diagnostics for measured evidence.

### Source-mapped inline quote formatting

For admitted HTML-derived Markdown with known document-start context, paired
curly/straight double quotation delimiters can also match within exactly mapped
top-level paragraphs. Both endpoints must occur in the query. Parsed code,
destinations/titles, raw HTML, other block types, escapes/entities and ambiguous
formula/prime notation remain literal. Words, values, case, URLs and other
punctuation stay exact. A successful comparison returns the original archived
substring and offsets, not normalized replacement text. Phase 28 records the
single recovered finding and the still-rejected modified tracking URL.

For HTML-derived reads with verified document context, inline-code delimiters and
supported HTTP(S) Markdown link markup can be omitted for comparison. Original
code contents, values, punctuation and case remain exact. Link syntax is checked
with the pinned CommonMark parser; entities and escaped characters remain literal.
Exact escaped-punctuation accounting can coexist with independent link/code
mappings in the same paragraph; it does not decode or delete those characters.
At most sixteen independent formatting policies distinguish emphasis, link
markup, standalone code delimiters and code delimiters within labels. Identical
position maps are deduplicated. Multiline flat list items retain their original
markers and indentation; ordered/nested lists are not flattened.

For mapped top-level HTML-derived prose, a query may itself retain some inline
code delimiters while omitting others. One query parse and at most four shared
source policies compose that case. Entire literal code bodies and explicit query
link destinations/titles remain exact; code interiors cannot create a partial
number/identifier match. Existing matches retain priority. Phase 32 records the
fixed archived-input comparison, not a new complete workflow run.

Explicit balanced HTML prose/cell blocks can project supported inline code,
presentation and link markup. Highlighted preformatted code keeps every literal
body character. Separate paragraphs/cells/list items never become one plain-text
sequence; a table-wide view keeps relationship tags. Unknown attributes, hidden
content, entities and malformed structures remain conservative. Saved quotes are
still contiguous original substrings with original offsets and hashes, bounded
by the actual delivered read and the 2048-character span cap. These formatting
projections do not judge whether a claim follows from its quotation.

### Publisher-declared structured data

HTML extraction /17 appends explicit inline JSON-LD as fenced, labelled records
after the unchanged extracted text. It preserves script order, graph membership,
references, unknown fields, currencies, qualifiers, string escapes and numeric
lexemes. Only line endings are normalized. It neither expands JSON-LD nor fetches
remote contexts; valid JSON syntax does not prove schema meaning or factual truth.
Arbitrary hydration JavaScript, scripts with src, and scripts inside template or
noscript are excluded. Script MIME matching is exact after case/outer whitespace
normalization. MIME parameters and XHTML CDATA wrappers are not heuristically
repaired; CDATA wrappers currently produce an invalid-json omission.

Bounds are 32 candidate scripts, 64 KiB per script, 128 KiB for the complete
supplement including framing, and a maximum validation-tree depth of 64 counting
the root and scalar values. Duplicate keys, non-JSON NaN/Infinity, invalid roots
and syntax are omitted as whole scripts. Text/index budget exhaustion omits whole
records without evicting existing text. If provenance cannot fit, the extractor
first retains an explicit omission summary; at an exact existing-provenance cap,
it falls back to unchanged text/provenance fields with a generic positive parser
warning. An absent structured_data field therefore makes no coverage claim.

The optional structured_data diagnostic records origin, counts, omission reasons,
base_text_bytes and per-script original UTF-8 intervals/hashes within the extracted
archive. Body preservation checks run before the supplement, and content hints
exclude its bytes. Source descriptors carry no script values. Actual document.read
segments provide them; Distiller feedback gives separate bounded coverage and
script-range metadata, retained through role repair. Synthesis labels each
delivered excerpt's body/supplement/mixed origin outside its quoted bytes, including
when the context budget selects just a quotation. Labels cannot establish an
unread entity, currency, variant or qualification. Claim support and metadata
freshness still require judgment. Phase 33 documents corpus and live boundaries.
