"""Mixed inline formatting retains literal bodies and original source spans."""
import pytest

from deepresearch.workflows.components.markdown_quotations import markdown_projections
from deepresearch.workflows.components.quotations import PreparedQuoteSource, locate_quote


OPTIONS = dict(markdown_formatting=True, html_cells=True)


@pytest.mark.parametrize('suffix', [
    r' See [other\_label](https://example.test/other) later.',
    r' Earlier \*literal\* and escaped\_text remain.',
    r' See [other\_label](https://example.test/A_(B) "Title") later.',
])
@pytest.mark.parametrize('prefix', ['', r'Escaped\_prefix first. '])
def test_escaped_original_characters_do_not_disable_exact_inline_mappings(prefix, suffix):
    source = prefix + 'Leave control to [`Session.mode`](https://example.test/mode "Mode") now.' + suffix
    quote = 'Leave control to Session.mode now.'
    expected = 'Leave control to [`Session.mode`](https://example.test/mode "Mode") now.'
    assert locate_quote(quote, source, **OPTIONS) == expected
    for visible, positions in markdown_projections(source):
        assert visible == ''.join(source[i] for i in positions)
        assert positions == sorted(set(positions))
        assert '\\' in visible


def test_escaped_link_label_is_retained_without_decoding_its_body():
    source = r'Use [`mode`](https://example.test/mode) and [other\_label](https://example.test/other).'
    assert locate_quote(r'Use mode and other\_label.', source, **OPTIONS) == source
    assert locate_quote('Use mode and other_label.', source, **OPTIONS) is None
    assert locate_quote('Use mode and otherlabel.', source, **OPTIONS) is None


@pytest.mark.parametrize('quote', [
    'Use mode=True (or the older `legacy=None`) now.',
    'Use `mode=True` (or the older legacy=None) now.',
    'Use mode=True (or the older legacy=None) now.',
    'Use `mode=True` (or the older `legacy=None`) now.',
])
def test_mixed_retained_and_omitted_code_delimiters_compose(quote):
    source = 'Use `mode=True` (or the older `legacy=None`) now.'
    assert locate_quote(quote, source, **OPTIONS) == source


def test_query_code_and_source_code_use_one_policy_without_reinterpreting_bodies():
    source = 'Use [`mode=True`](https://example.test/mode "Mode") and `**literal**` now.'
    assert locate_quote('Use mode=True and `**literal**` now.', source, **OPTIONS) == source
    assert locate_quote('Use mode=True and literal now.', source, **OPTIONS) is None
    assert locate_quote('Use mode=True and `literal` now.', source, **OPTIONS) is None


def test_retained_query_destinations_and_titles_must_stay_exact():
    source = 'Use [records](https://example.test/a "Title") with `mode=True` and `None`.'
    quote = 'Use [records](https://example.test/a "Title") with mode=True and `None`.'
    assert locate_quote(quote, source, **OPTIONS) == source
    assert locate_quote(quote.replace('/a ', '/b '), source, **OPTIONS) is None
    assert locate_quote(quote.replace('"Title"', '"Changed"'), source, **OPTIONS) is None
    assert locate_quote(quote.replace('[records]', '[record]'), source, **OPTIONS) is None


def test_mixed_query_delimiters_can_retain_emphasis_without_altering_literal_stars():
    source = 'Use **mode** with `True` and `None`.'
    assert locate_quote('Use **mode** with True and `None`.', source, **OPTIONS) == source
    assert locate_quote('Use mode with True and `None`.', source, **OPTIONS) == source


@pytest.mark.parametrize('quote', [
    'Use mode=False (or the older `legacy=None`) now.',
    'Use mode=True (or the older `legacy=0`) now.',
    'Use Mode=True (or the older `legacy=None`) now.',
    'Use mode=True (or `legacy=None`) now.',
    'Use mode=True (or the older `legacy=None`) later.',
])
def test_mixed_delimiters_never_change_values_case_qualifiers_or_words(quote):
    source = 'Use `mode=True` (or the older `legacy=None`) now.'
    assert locate_quote(quote, source, **OPTIONS) is None


@pytest.mark.parametrize('source,quote', [
    ('`120` and `None`', '20 and `None`'),
    ('`not available` and `None`', 'available and `None`'),
    ('`unavailable` and `None`', '`available` and None'),
    ('120 and `None`', '`20` and None'),
    ('some_value and `None`', '`value` and None'),
])
def test_new_query_projection_cannot_match_partial_code_numbers_or_identifiers(source, quote):
    assert locate_quote(quote, source, **OPTIONS) is None


@pytest.mark.parametrize('source', [
    '```text\nUse `mode=True` and `legacy=None`.\n```',
    '    Use `mode=True` and `legacy=None`.',
    '> Use `mode=True` and `legacy=None`.',
    'Use `mode=True`\n\nand `legacy=None`.',
    '| A | B |\n| --- | --- |\n| `mode=True` | `legacy=None` |',
    '<table><tr><td>`mode=True`</td><td>`legacy=None`</td></tr></table>',
])
def test_mixed_query_projection_does_not_join_blocks_cells_or_code_contexts(source):
    assert locate_quote('Use mode=True and `legacy=None`.', source, **OPTIONS) is None
    assert locate_quote('mode=True legacy=None', source, **OPTIONS) is None


def test_new_query_projection_requires_html_provenance_and_known_context():
    source = 'Use `mode=True` and `legacy=None` now.'
    quote = 'Use mode=True and `legacy=None` now.'
    assert locate_quote(quote, source, markdown_formatting=True) is None
    assert locate_quote(quote, source, html_cells=True) is None
    assert locate_quote(quote, source, **OPTIONS, markdown_prefix=None) is None
    assert locate_quote(quote, source, **OPTIONS, markdown_prefix='```text\n') is None


def test_original_utf8_range_and_current_read_boundaries_survive_mixed_formatting():
    paragraph = 'Use `café=True` and `legacy=None` now.'
    source = '😀préface\n\n' + paragraph
    quote = 'Use café=True and `legacy=None` now.'
    prepared = PreparedQuoteSource(source, **OPTIONS)
    assert prepared.locate(quote) == paragraph
    assert prepared.locate_spans(quote) == [(len('😀préface\n\n'), len(source))]
    a, b = prepared.locate_spans(quote)[0]
    left, right = len(source[:a].encode()), len(source[:b].encode())
    assert source.encode()[left:right] == paragraph.encode()
    split = source.index(' and ')
    assert locate_quote(quote, source[split:], **OPTIONS, markdown_prefix=source[:split]) is None


def test_previously_exact_match_keeps_priority_and_all_locations_remain_visible():
    quote = 'Use mode=True and `legacy=None` now.'
    mixed = 'Use `mode=True` and `legacy=None` now.'
    source = mixed + '\n\n' + quote
    prepared = PreparedQuoteSource(source, **OPTIONS)
    assert prepared.locate(quote) == quote
    assert prepared.locate_spans(quote) == [(0, len(mixed)), (len(mixed) + 2, len(source))]


def test_format_policy_count_is_bounded_and_original_span_cap_remains():
    source = ' '.join(['Use `mode=True` and `legacy=None`.'] * 100)
    assert len(list(markdown_projections(source))) == 1
    long_link = 'Use [`mode=True`](https://example.test/' + 'x' * 2050 + ') and `legacy=None` now.'
    assert locate_quote('Use mode=True and `legacy=None` now.', long_link, **OPTIONS) is None


def test_mixed_views_use_four_shared_policies_regardless_of_span_count():
    for count in (1, 100):
        source = ' '.join(['Use **mode** with [`True`](https://example.test/a) and `None`.'] * count)
        mixed = []
        projections = list(markdown_projections(source, mixed_views=mixed))
        assert len(projections) <= 16
        assert len(mixed) == 4
        assert len({tuple(positions) for _, positions, _ in mixed}) == 4
        for visible, positions, bodies in mixed:
            assert visible == ''.join(source[i] for i in positions)
            assert positions == sorted(set(positions))
            assert len(bodies) == count * 2


@pytest.mark.parametrize('literal', ['<td>2</td>', 'https://example.test/A_(B)', r'A\*B', '&amp;'])
def test_code_bodies_with_html_urls_escapes_and_entities_remain_literal(literal):
    source = f'Use `{literal}` and `None` now.'
    assert locate_quote(f'Use `{literal}` and None now.', source, **OPTIONS) == source
    changed = literal.replace('2', '20').replace('A', 'a').replace('&amp;', '&')
    if changed != literal:
        assert locate_quote(f'Use `{changed}` and None now.', source, **OPTIONS) is None
