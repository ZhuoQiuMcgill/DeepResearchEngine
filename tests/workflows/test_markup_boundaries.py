"""Presentation-only repairs keep table relationships and literal source spans."""
import pytest

from deepresearch.workflows.components.quotations import locate_quote


@pytest.mark.parametrize('tag', ['span', 'b', 'strong', 'i', 'em'])
def test_inline_presentation_within_one_cell_returns_original_bytes(tag):
    body = f'<span>12.5 kg <{tag}>per unit</{tag}></span>'
    text = '😀préface\n<table><tr><th>Mass</th><td>' + body + '</td></tr></table>'
    assert locate_quote('12.5 kg per unit', text) is None
    actual = locate_quote('12.5 kg per unit', text, html_cells=True)
    assert actual == f'12.5 kg <{tag}>per unit'
    start = len(text[:text.index(actual)].encode())
    assert text.encode()[start:start + len(actual.encode())] == actual.encode()


@pytest.mark.parametrize('markup', [
    '<sup>per unit</sup>', '<sub>per unit</sub>', '<del>per unit</del>',
    '<s>per unit</s>', '<ins>per unit</ins>',
    '<span hidden>per unit</span>', '<span style="display:none">per unit</span>',
    '<span aria-label="different">per unit</span>', '<span class="deleted">per unit</span>',
    '<div>per unit</div>', '<p>per unit</p>', '<a href="#note">per unit</a>',
    '<span>per unit</b>', '<span>per unit', '<!-- qualifier --><span>per unit</span>',
])
def test_inline_semantics_hidden_content_blocks_and_malformed_tags_stay_literal(markup):
    text = '<table><tr><td>12.5 kg ' + markup + '</td></tr></table>'
    assert locate_quote('12.5 kg per unit', text, html_cells=True) is None


def test_inline_code_presentation_can_be_omitted_but_its_literal_body_cannot_change():
    text = '<table><tr><td>12.5 kg <code>per unit</code></td></tr></table>'
    assert locate_quote('12.5 kg per unit', text, html_cells=True) == '12.5 kg <code>per unit'
    assert locate_quote('12.5 kg per units', text, html_cells=True) is None


@pytest.mark.parametrize('quote', [
    '125 kg per unit', '12.5 g per unit', '12.5 kg Per unit',
    '12.5 kg available', 'per unit 12.5 kg',
])
def test_inline_projection_never_repairs_claim_text(quote):
    text = '<table><tr><td>12.5 kg <span>per unit</span> not available</td></tr></table>'
    assert locate_quote(quote, text, html_cells=True) is None


def test_inline_projection_cannot_merge_cells_rows_or_nested_tables():
    for text in [
        '<table><tr><td>12.5 kg</td><td><span>per unit</span></td></tr></table>',
        '<table><tr><td>12.5 kg</td></tr><tr><td><span>per unit</span></td></tr></table>',
        '<table><tr><td>12.5 kg<table><tr><td><span>per unit</span></td></tr></table></td></tr></table>',
    ]:
        assert locate_quote('12.5 kg per unit', text, html_cells=True) is None


@pytest.mark.parametrize('wrapper', [
    '<pre>{}</pre>', '<code>{}</code>', '<textarea>{}</textarea>', '<!-- {} -->',
    '```html\n{}\n```', '~~~html\n{}\n~~~', '    {}', '`{}`',
])
def test_inline_tables_in_code_and_comments_are_not_adapted(wrapper):
    text = wrapper.format('<table><tr><td>12.5 kg <span>per unit</span></td></tr></table>')
    assert locate_quote('12.5 kg per unit', text, html_cells=True) is None


TABLE = '| Item | Result |\n| :--- | ---: |\n| A | 12.5 kg |\n| B | not available |\n'


@pytest.mark.parametrize('delimiter', ['| --- | --- |', '| :--- | ---: |', '|:---:|:---:|'])
def test_markdown_delimiter_is_presentation_while_rows_and_pipes_remain(delimiter):
    text = '😀préface\n\n' + TABLE.replace('| :--- | ---: |', delimiter)
    quote = 'Item | Result |\n| A | 12.5 kg'
    assert locate_quote(quote, text) is None
    exact = locate_quote(quote, text, markdown_formatting=True)
    assert exact == f'Item | Result |\n{delimiter}\n| A | 12.5 kg'
    start = len(text[:text.index(exact)].encode())
    assert text.encode()[start:start + len(exact.encode())] == exact.encode()


@pytest.mark.parametrize('quote', [
    'Item Result A 12.5 kg',
    'Item | Result |\n| A | 125 kg',
    'Item | Result |\n| B | 12.5 kg',
    'Item | Result |\n| B | not available',  # omitted intervening A row
    'Result | Item |\n| 12.5 kg | A',
    'A | 12.5 kg |\n| B | available',
])
def test_markdown_delimiter_adaptation_preserves_data_rows_order_and_negation(quote):
    assert locate_quote(quote, TABLE, markdown_formatting=True) is None


@pytest.mark.parametrize('wrapper', ['```text\n{}\n```', '~~~\n{}\n~~~', '<pre>\n{}\n</pre>', '    {}'])
def test_markdown_table_code_is_literal(wrapper):
    text = wrapper.format(TABLE.replace('\n', '\n    ') if wrapper == '    {}' else TABLE)
    assert locate_quote('Item | Result |\n| A | 12.5 kg', text, markdown_formatting=True) is None


def test_table_projection_prefix_and_expanded_span_limits():
    quote = 'Item | Result |\n| A | 12.5 kg'
    assert locate_quote(quote, TABLE, markdown_formatting=True, markdown_prefix='```text\n') is None
    split = TABLE.index('| A')
    assert locate_quote(quote, TABLE[split:], markdown_formatting=True, markdown_prefix=TABLE[:split]) is None
    # The comparison can omit a long separator, but the archived quote cannot exceed 2048.
    text = TABLE.replace(':---', '-' * 2050)
    assert locate_quote(quote, text, markdown_formatting=True) is None
    text = '<table><tr><td>12.5 kg <span>' + ' ' * 2050 + 'per unit</span></td></tr></table>'
    assert locate_quote('12.5 kg per unit', text, html_cells=True) is None


def test_prepared_source_parses_once_without_caching_quote_results(monkeypatch):
    from deepresearch.workflows.components import quotations
    calls = []
    original = quotations.markdown_projections
    def tracked(text):
        calls.append(text)
        yield from original(text)
    monkeypatch.setattr(quotations, 'markdown_projections', tracked)
    source = quotations.PreparedQuoteSource('A **20 mg**. B **3 kg**.', markdown_formatting=True)
    assert source.locate('A 20 mg') == 'A **20 mg'
    assert len(calls) == 1
    assert source.locate('B 3 kg') == 'B **3 kg'
    assert source.locate('A 200 mg') is None
    assert source.locate('B 3 kg') == 'B **3 kg'
    assert len(calls) == 1
    other = quotations.PreparedQuoteSource('A **200 mg**.', markdown_formatting=True)
    assert other.locate('A 20 mg') is None
    assert other.locate('A 200 mg') == 'A **200 mg'
    assert source.locate('A 200 mg') is None


@pytest.mark.parametrize('text,prefix', [
    (None, ''), ('\ud800', ''), ('x' * 65537, ''), ('😀' * 20000, ''),
    ('A **20 mg**', None), ('A **20 mg**', '\ud800'), ('A **20 mg**', 'x' * 2097153),
], ids=['invalid-type', 'invalid-unicode', 'character-cap', 'utf8-cap',
        'prefix-type', 'prefix-unicode', 'prefix-cap'])
def test_prepared_source_invalid_context_never_parses(text, prefix, monkeypatch):
    from deepresearch.workflows.components import quotations
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid source/context must not be parsed')
    monkeypatch.setattr(quotations, 'markdown_projections', forbidden)
    source = quotations.PreparedQuoteSource(text, markdown_formatting=True, markdown_prefix=prefix)
    assert source.locate('A 20 mg') is None


def test_prepared_source_keeps_prefix_read_boundary_and_quote_bounds():
    from deepresearch.workflows.components.quotations import PreparedQuoteSource
    literal = PreparedQuoteSource('- A 20\n- B 30\n```', markdown_formatting=True, markdown_prefix='```text\n')
    assert literal.locate('A 20 B 30') is None
    assert literal.locate('- A 20') == '- A 20'
    partial = PreparedQuoteSource('| A | 12.5 kg |\n', markdown_formatting=True,
        markdown_prefix='| Item | Result |\n| --- | --- |\n')
    assert partial.locate('Item | Result |\n| A | 12.5 kg') is None
    assert partial.locate('A | 12.5 kg') == 'A | 12.5 kg'
    for quote in [None, '', '\ud800', 'x' * 2049]:
        assert partial.locate(quote) is None
