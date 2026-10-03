# Search information acceptance — 2026-10-02

The new contracts are `web.search@3`, `scholar.crossref.search@2` and
`scholar.openalex.search@2`. `baseline@6` selects them with the same Agent roles,
research decisions and budgets as revision 5. Old revisions and saved experiments
remain intact. See the [tool contract](usage/tools.md#complete-discovery-information).

## Actual tool run

`run_29718262b9204f57a23e47b528081a34` used real workers and SQLite. Its original
question was exactly `What is EBD (Environment Based Design)?`. The diagnostic
made five bounded, separately recorded search calls with a requested maximum
of ten results each. It made no model calls or fetch calls. The host explicitly
admitted the new store's bounded anonymous OpenAlex allowance for this check;
normal host defaults were not changed.

| Tool / literal probe | Returned | With authors | With supplied abstract |
| --- | ---: | ---: | ---: |
| Web / original question | 7 | n/a | Search snippets |
| Web / `"Environment Based Design"` | 2 | n/a | Search snippets |
| Crossref / original question | 10 | 9 | 5 |
| Crossref / `"Environment-based formulation of design problem"` | 10 | 9 | 2 |
| OpenAlex / `"Environment Based Design"` | 10 | 10 | 9 |

All five calls succeeded with complete recording. Optional scholarly metadata
had no invalid/truncated fields in these actual responses. Every tool response
was published unchanged as a discovery artifact, read through the public
bounded artifact interface, and read byte-identically after closing/reopening
the Engine and service. The diagnostic distinguishes provider availability
from contract-check success and records failures explicitly when they occur.

The OpenAlex first page included the core 2011 paper
(`10.1115/detc2011-48263`), the 2015 methodology paper
(`10.3233/jid-2015-0004`) and the 2023 ICED paper
(`10.1017/pds.2023.168`). Crossref's focused query returned the 2004 foundational
paper (`10.3233/jid-2004-8404`) at rank **10**. A Workflow asking for only five
results would not receive that tenth candidate. The tool now makes this
first-page/count boundary explicit; topic filtering and the requested result
count remain Workflow decisions. Provider total counts are not relevant-paper counts.

The raw original-question web probe also returned evidence-based-design results.
These are retained as received, alongside the environment-based-design candidate;
the tool does not secretly reinterpret EBD or remove results by research policy.

Evidence is retained under ignored `local/search-information-live/`:
`evidence/acceptance.json`, `evidence/run.json`, `evidence/probe-0.json` through
`probe-4.json`, and the actual `store/store.sqlite3` and object files.
Reproduce into a fresh store with
`examples/live_search_information_check.py --admit-openalex` and explicit
`--store`/`--output` paths when preserving a previous check.

## Regression coverage

| Verification | Result |
| --- | --- |
| Full project regression | **1,141 passed in 245.09 seconds** |
| Final toolset regression after bounding inverted-index expansion and adding the binding check | **116 passed in 6.05 seconds** |
| Live searches | **5/5 succeeded**, with complete recording and byte-identical restart reads |
| Live SQLite | `integrity_check=ok`, zero foreign-key violations |
| Isolated wheel | Baseline revisions 1–6, enriched tool definitions and new resource files load; a real model-free Workflow/Storage run succeeds |

Controlled cases check metadata retention, exact query/URL preservation,
Unicode byte limits and truncation flags, missing-versus-zero values, invalid
optional metadata, malformed/sparse/overlapping abstract indexes, result-limit
omissions, original provider ranks, failure diagnostics, parent rejection of
inconsistent coverage, registered worker revisions and real Storage recording.
The parallel-method integration exercises both revisions 5 and 6 with the same
Agent roles, archived-source delivery, concurrency and report path.

These checks establish the returned information and its recorded accessibility.
They do not guarantee continuous availability of anonymous search providers,
topic relevance, exhaustive recall or access to every linked full text.
