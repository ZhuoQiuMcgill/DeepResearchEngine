"""Neutral format/binding fixtures; no route, vendor or model-specific rules."""
import pytest

from deepresearch.methods.baseline.stages import reporting as proposed

ID = "source-1"
URL = "https://example.org/study_(neutral)"
OTHER = "https://example.org/other"


def issues(entry, *, body="Claim [source-1].", urls=None, known=(ID,)):
    return proposed.citation_issues(body + "\n## References\n" + entry, known, strict=True,
                                   source_urls=urls if urls is not None else {ID: URL})


@pytest.mark.parametrize("entry", [
    f"- [{ID}]({URL})", f"[{ID}]({URL})", f"1. [{ID}]({URL})",
    f'[{ID}]({URL} "Optional title")', f"[{ID}]({URL} 'Optional title')",
    f"[{ID}]({URL} (Optional title))", f"[{ID}](<{URL}>)",
    f'[{ID}](<{URL}> "Title (neutral)")', f"[{ID}](  {URL}  )",
    f"[{ID}] {URL}", f"- [{ID}] Source — {URL}",
    f"[{ID}] [Title]({URL}).",
])
def test_valid_link_and_existing_standalone_forms(entry):
    assert issues(entry) == []


@pytest.mark.parametrize("url", [
    "https://example.org/neutral", "https://example.org/a_(b_(c))",
    "https://example.org/a,b;c.", "https://example.org/a%2Fb?q=a%20b&k=c#fragment",
    "https://example.org/café", "https://例子.org/path",
])
def test_exact_destinations(url):
    assert issues(f"[{ID}](<{url}>)", urls={ID: url}) == []


@pytest.mark.parametrize("entry", [
    f"![{ID}]({URL})", f"![Caption [{ID}]({URL})]({OTHER})",
    f"`[{ID}]({URL})`", f"``[{ID}]({URL})``",
    f"```markdown\n[{ID}]({URL})\n```", f"~~~\n[{ID}]({URL})\n~~~",
    f"    [{ID}]({URL})", f"\\[{ID}]({URL})", f"[source\\-1]({URL})",
    f"[source&#45;1]({URL})", f"[*{ID}*]({URL})", f"[`{ID}`]({URL})",
    f"[{ID} extra]({URL})", f"[[{ID}]]({URL})",
    f"[{ID}][source-2]({URL})", f"[{ID}] [source-2]({URL})",
    f"[{ID}]({URL}) [source-2]({OTHER})", f"[{ID}]({URL}) [{ID}] {URL}",
    f"[{ID}]({URL}", f"[{ID}]({URL} extra)", f"[{ID}]({URL} \"unclosed title)",
    f"[{ID}](https://example.org/unbalanced_(neutral)",
    f"[{ID}](https://wrong.example.org/study_(neutral)) {URL}",
    f'[{ID}]({OTHER} "{URL}")', f"[{ID}](<{OTHER}>) {URL}",
    f"[{ID}]({URL}) {OTHER}", f"[{ID}]({URL}) [Other]({OTHER})",
    f"[{ID}]({URL}) <{OTHER}>", f'[{ID}]({URL} "{OTHER}")',
    f"<code>[{ID}]({URL})</code>", f"<pre>[{ID}]({URL})</pre>",
    f"<span>[{ID}]({URL})</span>", f"<code>\n[{ID}]({URL})\n</code>",
    f"<div>\n[{ID}]({URL})\n</div>",
])
def test_fake_ambiguous_malformed_and_wrong_links_rejected(entry):
    assert issues(entry, known=(ID, "source-2"))


@pytest.mark.parametrize("entry", [
    f"`[{ID}] {URL}`", f"```\n[{ID}] {URL}\n```", f"\\[{ID}] {URL}",
    f"[{ID}] {OTHER}", f"[{ID}] {URL}\n[{ID}] {URL}",
    f"[{ID}]({URL})\n[{ID}]({URL})", f"[{ID}]({URL})\n[{ID}] {URL}",
    f"[unknown]({URL})", f"[{ID}]({URL})\n[uncited]({OTHER})",
])
def test_strict_count_unknown_uncited_and_legacy_binding_rejected(entry):
    assert issues(entry, known=(ID, "uncited"))


def test_one_valid_entry_for_each_cited_id():
    assert issues(f"[{ID}]({URL})\n[source-2] {OTHER}", known=(ID, "source-2"),
                  body="Claims [source-1] [source-2].", urls={ID: URL, "source-2": OTHER}) == []
    assert issues(f"[{ID}]({URL})", known=(ID, "source-2"),
                  body="Claims [source-1] [source-2].", urls={ID: URL, "source-2": OTHER})


@pytest.mark.parametrize("entry", [
    f"[{ID}]\n{URL}", f"[{ID}]  \n{URL}", f"[{ID}]\r\n{URL}",
    f"[{ID}]\n<{URL}>", f"- [{ID}]\n  {URL}", f"1. [{ID}]\n   {URL}",
    f"[{ID}] A source title\nand publication information.\n{URL}",
])
def test_same_entry_continuation_lines_bind_exact_url(entry):
    assert issues(entry) == []


def test_multiline_entries_keep_their_own_destinations():
    options = dict(known=(ID, "source-2"), body="Claims [source-1] [source-2].",
                   urls={ID: URL, "source-2": OTHER})
    assert issues(f"[{ID}]\n{URL}\n[source-2]\n{OTHER}", **options) == []
    assert issues(f"[{ID}]\n{OTHER}\n[source-2]\n{URL}", **options)
    assert issues(f"[{ID}]\n[source-2]\n{OTHER}", **options)


@pytest.mark.parametrize("entry", [
    f"[{ID}]\n\n{URL}", f"[{ID}]\n\n```\n{URL}\n```",
    f"[{ID}]\n\n    {URL}", f"- [{ID}]\n- {URL}",
    f"[{ID}]\n# {URL}", f"[{ID}]\n<div>{URL}</div>",
    f"[{ID}]\n{OTHER}", f"[{ID}]\n{URL}\n{OTHER}",
    f"[{ID}]({URL})\n{OTHER}", f"[{ID}]\n{URL}\n[{ID}]\n{URL}",
])
def test_continuations_cannot_cross_blocks_or_hide_wrong_urls(entry):
    assert issues(entry)


def test_destination_binding_uses_its_own_id():
    assert issues(f"[{ID}]({OTHER})\n[source-2]({URL})", known=(ID, "source-2"),
                  body="Claims [source-1] [source-2].", urls={ID: URL, "source-2": OTHER})


def test_exact_allowed_alternatives_and_empty_destination():
    assert issues(f"[{ID}]({OTHER})", urls={ID: {URL, OTHER}}) == []
    assert issues(f"[{ID}]() {URL}")
    assert issues(f"[{ID}]({URL})", urls={ID: set()})


@pytest.mark.parametrize("different", [
    "https://example.org/study_%28neutral%29", "https://example.org/study_(neutral)/",
    "https://example.org/STUDY_(neutral)", "http://example.org/study_(neutral)",
    "https://EXAMPLE.org/study_(neutral)", "https://example.org:443/study_(neutral)",
])
def test_no_url_guessing_or_decoding(different):
    assert issues(f"[{ID}](<{different}>) {URL}")


def test_raw_url_guard_remains_conservative_for_encoded_syntax():
    assert issues(f"[{ID}](https://example.org/study_\\(neutral\\))")
    url = "https://example.org/a?q=1&k=2"
    assert issues(f"[{ID}](<{url.replace('&', '&amp;')}>)", urls={ID: url})
    encoded = "https://example.org/a%2Fb"
    assert issues(f"[{ID}](https://example.org/a/b)", urls={ID: encoded})


@pytest.mark.parametrize("body", ["Claim.", f"Claim [{ID}]({URL}).", f"![{ID}]({URL})"])
def test_body_still_requires_standalone_citation(body):
    assert issues(f"[{ID}]({URL})", body=body)


@pytest.mark.parametrize("report, expected", [
    ('', ['The report is empty.', 'Cite at least one supplied source ID using [source-id].']),
    ('Claim.', ['Cite at least one supplied source ID using [source-id].']),
    ('Claim [source-1].', []),
    ('Claim [unknown].', ['Cite at least one supplied source ID using [source-id].', 'Remove citations to unknown source IDs: unknown']),
    ('Claim [source-1](https://example.org/study_(neutral)).', ['Cite at least one supplied source ID using [source-id].']),
    ('Claim [source-1].\n## References\n[source-1](https://example.org/other)', []),
    ('Claim [source-1].\n## References\n![source-1](https://example.org/study_(neutral))', []),
    ('Claim [source-1].\n## References\n[source-1] https://example.org/study_(neutral)\n[source-1] https://example.org/study_(neutral)', []),
    ('Claim [source-1].\n## References\n[uncited](https://example.org/other)', []),
])
def test_nonstrict_outputs_unchanged(report, expected):
    assert proposed.citation_issues(report, [ID], source_urls={ID: URL}) == expected


@pytest.mark.parametrize("report", [
    f"Claim [{ID}].", f"Claim [{ID}].\n## References\n[{ID}]({URL})\n## References\n",
])
def test_heading_rule_unchanged(report):
    assert proposed.citation_issues(report, [ID], strict=True, source_urls={ID: URL})


@pytest.mark.parametrize("error", [IndexError, RecursionError])
def test_optional_parser_failure_requests_structural_repair(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error("controlled parser failure")
    monkeypatch.setattr(proposed.MarkdownIt, "parse", fail)
    result = issues(f"[{ID}]({URL})")
    assert len(result) == 1 and "References Markdown could not be parsed" in result[0]
    assert not any("missing" in item for item in result)


def test_unrelated_programming_errors_are_not_hidden(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("controlled unrelated error")
    monkeypatch.setattr(proposed.MarkdownIt, "parse", fail)
    with pytest.raises(ValueError, match="unrelated error"):
        issues(f"[{ID}]({URL})")
