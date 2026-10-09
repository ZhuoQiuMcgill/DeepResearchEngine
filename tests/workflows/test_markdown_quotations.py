"""CommonMark presentation differences never authorize factual edits."""
import pytest

from deepresearch.workflows.components.quotations import locate_quote


@pytest.mark.parametrize("quote,text,expected", [
    ("the storage jump costs $200 to $300 per tier", "The cost: the **storage jump costs $200 to $300 per tier**.",
     "the **storage jump costs $200 to $300 per tier"),
    ("a small bold result", "a *small* **bold** result", "a *small* **bold** result"),
    ("a small result", "a _small_ result", "a _small_ result"),
    ("A 1h B 2h C 3h", "Intro\n\n- A 1h\n- B 2h\n- C 3h\n", "A 1h\n- B 2h\n- C 3h"),
    ("A 1h B 2h", "* A 1h\n\n* B 2h", "A 1h\n\n* B 2h"),
    ("A 1h B 2h", "+ **A** 1h\n+ B 2h", "A** 1h\n+ B 2h"),
    ("route Vancouver 16h 34 Tokyo 16h 50", "- route **Vancouver** 16h 34\n- Tokyo 16h 50",
     "route **Vancouver** 16h 34\n- Tokyo 16h 50"),
    ("a `code **literal**` bold tail", "a `code **literal**` **bold** tail", "a `code **literal**` **bold** tail"),
])
def test_returns_literal_contiguous_source_span(quote, text, expected):
    assert locate_quote(quote, text) is None
    text = "😀préface\n\n" + text
    actual = locate_quote(quote, text, markdown_formatting=True)
    assert actual == expected and actual in text
    offset = len(text[:text.index(actual)].encode())
    assert text.encode()[offset:offset + len(actual.encode())] == actual.encode()


@pytest.mark.parametrize("quote,text", [
    ("costs 200 dollars", "costs **20** dollars"),
    ("is available", "is **not** available"),
    ("A 1h C 3h B 2h", "- A 1h\n- B 2h\n- C 3h"),
    ("A 1h C 3h", "- A 1h\n- B 2h\n- C 3h"),
    ("A 1h B 2h", "1. A 1h\n2. B 2h"),
    ("A 1h B 2h", "- A 1h\n  - B 2h"),
    ("A 1h B 2h", "- A 1h\n\nParagraph\n\n- B 2h"),
    ("A 1h B 2h", "> - A 1h\n> - B 2h"),
    ("A 1h B 2h", "```text\n- A 1h\n- B 2h\n```"),
    ("A 1h B 2h", "    - A 1h\n    - B 2h"),
    ("A 1h B 2h", "<pre>\n- A 1h\n- B 2h\n</pre>"),
    ("2 3", "2 * 3"),
    ("23", "2**3"),
    ("temperature 5 degrees", "temperature **-5** degrees"),
    ("a value tail", "a `**value**` tail"),
    ("a value tail", r"a \**value** tail"),
    ("A value and B", "**A value**\n\nand B"),
    ("Name Value A 2", "| Name | Value |\n| --- | --- |\n| A | 2 |"),
    ("safe text", "~~safe~~ text"),
])
def test_preserves_facts_hierarchy_code_math_and_block_boundaries(quote, text):
    assert locate_quote(quote, text, markdown_formatting=True) is None


def test_markdown_links_and_emphasis_can_compose_without_changing_destinations():
    source = "A **[source](https://example.org/x)** reports 2."
    assert locate_quote("A source reports 2.", source, markdown_formatting=True, markdown_links=True) == source
    assert locate_quote("A source reports 20.", source, markdown_formatting=True, markdown_links=True) is None


def test_source_span_stays_bounded_after_marker_restoration():
    source = '- ' + ('x' * 1022) + '\n- ' + ('y' * 1024)
    quote = ('x' * 1022) + ' ' + ('y' * 1024)
    assert len(quote) <= 2048
    assert locate_quote(quote, source, markdown_formatting=True) is None


def test_prefix_determines_code_context_but_cannot_supply_quote_bytes():
    source = "- A 1h\n- B 2h\n```\n"
    assert locate_quote("A 1h B 2h", source, markdown_formatting=True, markdown_prefix="```text\n") is None
    source = "- A 1h\n- B 2h\n"
    assert locate_quote("A 1h B 2h", source, markdown_formatting=True, markdown_prefix="Intro\n\n") == "A 1h\n- B 2h"
    assert locate_quote("Intro A 1h", source, markdown_formatting=True, markdown_prefix="Intro\n\n") is None
    source = '<table><tr><td>RAM</td></tr></table>\n```'
    assert locate_quote('RAM\t</td>', source, html_cells=True, markdown_prefix="```html\n") is None


def test_recorded_prefix_requires_unbroken_consistent_utf8_reads():
    from deepresearch.workflows.components.markdown_quotations import recorded_prefix
    prefix = "😀 Intro\n\n"
    first = {"text": prefix, "start_byte": 0, "end_byte": len(prefix.encode())}
    target = {"text": "- A\n- B", "start_byte": first["end_byte"]}
    assert recorded_prefix([first], target) == prefix
    assert recorded_prefix([], target) is None
    assert recorded_prefix([{**first, "start_byte": 1}], target) is None
    assert recorded_prefix([{**first, "end_byte": 999}], target) is None
    assert recorded_prefix([first], {**target, "start_byte": 2}) is None  # inside a codepoint
    assert recorded_prefix([], {"start_byte": False}) is None
    start = {"text": "ABC", "start_byte": 0, "end_byte": 3}
    overlap = {"text": "CD", "start_byte": 2, "end_byte": 4}
    assert recorded_prefix([start, overlap], {"start_byte": 4}) == "ABCD"
    assert recorded_prefix([start, {**overlap, "text": "ZD"}], {"start_byte": 4}) is None


@pytest.mark.parametrize("prefix", [None, "\ud800", "x" * 2097153], ids=["type", "unicode", "size"])
def test_invalid_markup_context_is_bounded(prefix):
    assert locate_quote("a b", "a **b**", markdown_formatting=True, markdown_prefix=prefix) is None


EMPHASIZED_TABLE = '| **Item** | Result |\n| --- | --- |\n| **Control** | *12 kg* |\n| Sample | **not** available |\n'


@pytest.mark.parametrize('quote,expected', [
    ('Control | 12 kg', 'Control** | *12 kg'),
    ('Item | Result |\n| Control | 12 kg', 'Item** | Result |\n| --- | --- |\n| **Control** | *12 kg'),
    ('Item | Result |\n| --- | --- |\n| Control | 12 kg', 'Item** | Result |\n| --- | --- |\n| **Control** | *12 kg'),
    ('Sample | not available', 'Sample | **not** available'),
])
def test_cell_emphasis_restores_literal_quote_and_utf8_offsets(quote, expected):
    text = '😀préface\n\n' + EMPHASIZED_TABLE
    assert locate_quote(quote, text) is None
    actual = locate_quote(quote, text, markdown_formatting=True)
    assert actual == expected
    offset = len(text[:text.index(actual)].encode())
    assert text.encode()[offset:offset+len(actual.encode())] == actual.encode()


@pytest.mark.parametrize('quote', [
    'Control | 120 kg', 'control | 12 kg', 'Sample | available', 'Control 12 kg',
    'Item | Result |\n| Sample | not available', 'Control | not available',
    '12 kg | Control',
])
def test_emphasis_does_not_allow_changed_cells_deleted_rows_or_pipes(quote):
    assert locate_quote(quote, EMPHASIZED_TABLE, markdown_formatting=True) is None


@pytest.mark.parametrize('wrapper', ['```text\n{}\n```', '<pre>\n{}\n</pre>', '> {}', '    {}'])
def test_table_inside_literal_or_nested_context_is_not_adapted(wrapper):
    prefix = '> ' if wrapper == '> {}' else '    ' if wrapper == '    {}' else ''
    text = wrapper.format(EMPHASIZED_TABLE.replace('\n', '\n'+prefix))
    assert locate_quote('Control | 12 kg', text, markdown_formatting=True) is None


@pytest.mark.parametrize('line,quote,accepted', [
    ('**Control** | *12 kg*', 'Control | 12 kg', True),
    ('| **Control** | *12 kg* |', 'Control | 12 kg', True),
    ('| **Control** |', 'Control |', False),  # parser pads a synthetic cell
    ('| **Control** | *12 kg* | omitted |', 'Control | 12 kg', False),
    ('| **Control** | `*12 kg*` |', 'Control | *12 kg*', True),  # exact code body
    ('| **Control** | `*12 kg*` |', 'Control | 12 kg', False),  # literal stars
    ('| **Control | 12 kg** |', '| Control | 12 kg |', False),  # emphasis crosses cells
    ('| **Control** | A \\| B |', r'Control | A \| B', True),
    ('| **Control** | A \\| B |', 'Control | A | B', False),
    ('| **Control** | 12\\* kg |', r'Control | 12\* kg', True),
])
def test_physical_cells_must_map_without_parser_normalization(line, quote, accepted):
    text = '| Item | Result |\n| --- | --- |\n' + line
    actual = locate_quote(quote, text, markdown_formatting=True)
    assert (actual is not None) is accepted
    if actual is not None:
        assert actual in text


def test_table_emphasis_respects_recorded_prefix_and_span_cap():
    row = '| **Control** | *12 kg* |\n'
    header = '| Item | Result |\n| --- | --- |\n'
    assert locate_quote('Control | 12 kg', row, markdown_formatting=True, markdown_prefix=header) == 'Control** | *12 kg'
    assert locate_quote('Control | 12 kg', row, markdown_formatting=True, markdown_prefix='```\n'+header) is None
    assert locate_quote('Item | Result |\n| Control | 12 kg', row, markdown_formatting=True, markdown_prefix=header) is None
    text = EMPHASIZED_TABLE.replace('---', '-'*2050)
    assert locate_quote('Item | Result |\n| Control | 12 kg', text, markdown_formatting=True) is None


def test_real_parser_edge_case_keeps_exact_quotes_without_breaking_validation():
    text = '> ' + EMPHASIZED_TABLE.replace('\n', '\n> ')
    assert locate_quote('**Control** | *12 kg*', text, markdown_formatting=True) == '**Control** | *12 kg*'
    assert locate_quote('Control | 12 kg', text, markdown_formatting=True) is None


@pytest.mark.parametrize('exception', [IndexError, RecursionError])
def test_optional_parser_failure_keeps_literal_matching(monkeypatch, exception):
    from deepresearch.workflows.components import markdown_quotations
    def broken(*args, **kwargs):
        raise exception('controlled parser failure')
    monkeypatch.setattr(markdown_quotations.MarkdownIt, 'parse', broken)
    assert locate_quote('literal 12', 'literal 12 and **bold**', markdown_formatting=True) == 'literal 12'
    assert locate_quote('and bold', 'literal 12 and **bold**', markdown_formatting=True) is None


def test_softbreak_spaces_cannot_disable_exact_emphasis_mapping_in_a_paragraph():
    # A legacy extractor may emit pipe-separated prose without a GFM header.
    # Preserve those literal pipes/rows, without inventing table semantics.
    text = '| **Name** | Result | \n| **Control** | 12 | \n| Sample | **not** available |'
    assert locate_quote('Control | 12', text, markdown_formatting=True) == 'Control** | 12'
    assert locate_quote('Control 12', text, markdown_formatting=True) is None
    assert locate_quote('Name | Result |\n| Sample | not available', text, markdown_formatting=True) is None
    assert locate_quote('Sample | available', text, markdown_formatting=True) is None
    assert locate_quote('Name | Result |\n| Control | 12', text, markdown_formatting=True) == 'Name** | Result | \n| **Control** | 12'


@pytest.mark.parametrize('source,quote', [
    ('Use `value` now.', 'Use value now.'),
    ('Use ``call(`value`)`` now.', 'Use call(`value`) now.'),
    ('Use ```call(``value``)``` now.', 'Use call(``value``) now.'),
    ('Use `**literal**` and **bold** now.', 'Use **literal** and bold now.'),
    ('Use `A &amp; B` now.', 'Use A &amp; B now.'),
    (r'Use `A\*B` now.', r'Use A\*B now.'),
    ('Use ` café(2, -5) ` now.', 'Use ` café(2, -5) ` now.'),
    ('Use `café(2, -5)` now.', 'Use café(2, -5) now.'),
])
def test_inline_code_omits_only_delimiters_with_literal_body_and_utf8_mapping(source, quote):
    text = '😀préface\n\n' + source
    actual = locate_quote(quote, text, markdown_formatting=True)
    assert actual == source
    offset = len(text[:text.index(actual)].encode())
    assert text.encode()[offset:offset + len(actual.encode())] == actual.encode()


@pytest.mark.parametrize('suffix', [
    '(https://example.test/a "A title")',
    "(http://example.test/a 'A title')",
    '(https://example.test/a (A title))',
    '(https://example.test/A_(B))',
    '(https://example.test/A_(B_(C)) "A (nested) title")',
    '( <https://example.test/A_(B)> "A title" )',
    '(https://example.test/a "")',
    '(https://example.test/a\n "A title"\n)',
    '(https://example.test/a "A\n title")',
])
@pytest.mark.parametrize('legacy_links', [False, True])
def test_inline_http_links_map_complete_valid_title_and_destination(suffix, legacy_links):
    source = 'Use [Alpha]' + suffix + ', then continue.'
    text = '😀préface\n\n' + source
    assert locate_quote('Use Alpha, then continue.', text,
                        markdown_formatting=True, markdown_links=legacy_links) == source
    assert locate_quote('Use Alpha then continue.', text,
                        markdown_formatting=True, markdown_links=legacy_links) is None


@pytest.mark.parametrize('quote', [
    'Use Alpha and run(2), then `None` stays.',
    'Use Alpha and `run(2)`, then `None` stays.',
    'Use **Alpha** and run(2), then None stays.',
    'Use Alpha and run(2), then None stays.',
])
def test_links_emphasis_and_code_preserve_partly_retained_formatting(quote):
    source = ('Use [**Alpha**](https://example.test/A_(B) "Title") and '
              '[`run(2)`](https://example.test/api "API"), then `None` stays.')
    assert locate_quote(quote, source, markdown_formatting=True) == source


@pytest.mark.parametrize('source,quote', [
    ('Use **bold** and `value` now.', 'Use **bold** and value now.'),
    ('Use **bold** and `value` now.', 'Use bold and `value` now.'),
    ('Use [Alpha](https://example.test/a "Title") and `value` now.',
     'Use [Alpha](https://example.test/a "Title") and value now.'),
    ('Use [Alpha](https://example.test/a "Title") and `value` now.',
     'Use Alpha and `value` now.'),
])
def test_preexisting_and_new_inline_policies_remain_independent(source, quote):
    assert locate_quote(quote, source, markdown_formatting=True) == source


@pytest.mark.parametrize('source,quote', [
    ('Use `run(2, -5)` now.', 'Use run(20, -5) now.'),
    ('Use `run(2, -5)` now.', 'Use Run(2, -5) now.'),
    ('Use `run(2, -5)` now.', 'Use run(2 -5) now.'),
    ('Use `run(2, -5)` now.', 'Use run(2, 5) now.'),
    ('Use ``call(`value`)`` now.', 'Use call(value) now.'),
    ('Use ``value`` now.', 'Use `value` now.'),
    ('Use `**literal**` now.', 'Use literal now.'),
    ('Use `A &amp; B` now.', 'Use A & B now.'),
    (r'Use `A\*B` now.', 'Use A*B now.'),
    ('Use ` value ` now.', 'Use value now.'),
    ('Use `line\nbreak` now.', 'Use line break now.'),
    ('Use ``value` now.', 'Use value now.'),
    ('Use `value`` now.', 'Use value now.'),
    (r'Use \`value\` now.', 'Use value now.'),
    ('Use [A &amp; B](https://example.test/a "Title") now.', 'Use A & B now.'),
    (r'Use [A\*B](https://example.test/a "Title") now.', 'Use A*B now.'),
    (r'Use \[Alpha](https://example.test/a "Title") now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a "unclosed) now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a"Title with spaces") now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a (nested (title))) now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a "Title" extra) now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/A_(B) now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/A_(B))) now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a "Title") now.', 'Use alpha now.'),
    ('Use [Alpha](https://example.test/a "Title") now.', 'Use Title now.'),
    (r'Use [Alpha](https://example.test/A_\(B\) "Title") now.', 'Use Alpha now.'),
    (r'Use [Alpha](https://example.test/a "A\"title") now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a "A &amp; B") now.', 'Use Alpha now.'),
    ('Use [Alpha](https://example.test/a?x=1&amp;y=2 "Title") now.', 'Use Alpha now.'),
    ('Use [Alpha](/relative "Title") now.', 'Use Alpha now.'),
    ('Use [Alpha](mailto:a@example.test "Title") now.', 'Use Alpha now.'),
    ('Use ![Alpha](https://example.test/a "Title") now.', 'Use Alpha now.'),
    ('Use [Alpha][ref] now.\n\n[ref]: https://example.test/a "Title"', 'Use Alpha now.'),
    ('Use <https://example.test/A_(B)> now.', 'Use https://example.test/A_(B) now.'),
    ('Use <span>Alpha</span> and `value` now.', 'Use Alpha and value now.'),
    ('Use `first` now.\n\nUse `second` later.', 'Use first now. Use second later.'),
    ("```text\n# use 'value' now\n```", '# use `value` now'),
])
def test_code_link_delimiter_escape_title_and_boundary_changes_stay_rejected(source, quote):
    assert locate_quote(quote, source, markdown_formatting=True) is None


@pytest.mark.parametrize('wrapper', ['```text\n{}\n```', '~~~text\n{}\n~~~', '    {}', '> {}'])
def test_new_inline_adaptations_do_not_enter_literal_or_nested_blocks(wrapper):
    content = 'Use [`run(2)`](https://example.test/A_(B) "API") and `None` now.'
    source = wrapper.format(content)
    assert locate_quote('Use run(2) and None now.', source, markdown_formatting=True) is None
    assert locate_quote(content, source, markdown_formatting=True) == content


@pytest.mark.parametrize('quote,accepted', [
    ('Alpha 12 Beta 3', True),
    ('Beta 3 Alpha 12', False),
    ('Alpha 120 Beta 3', False),
    ('Alpha Beta 3', False),
])
def test_flat_list_keeps_code_body_and_link_label_order(quote, accepted):
    source = '- [**Alpha**](https://example.test/A_(B) "Title") `12`\n- `Beta` 3'
    actual = locate_quote(quote, source, markdown_formatting=True)
    assert (actual is not None) is accepted
    if actual is not None:
        assert actual in source


@pytest.mark.parametrize('source', [
    '1. [`Alpha`](https://example.test/A_(B) "Title") 12\n2. `Beta` 3',
    '- [`Alpha`](https://example.test/A_(B) "Title") 12\n  - `Beta` 3',
])
def test_new_inline_policies_cannot_flatten_ordered_or_nested_lists(source):
    assert locate_quote('Alpha 12 Beta 3', source, markdown_formatting=True) is None


@pytest.mark.parametrize('quote,accepted', [
    ('Item | Value |\n| Alpha | run(2)', True),
    ('Item | Value |\n| --- | --- |\n| Alpha | run(2)', True),
    ('Alpha | run(2)', True),
    ('Alpha run(2)', False),
    ('run(2) | Alpha', False),
    ('Alpha | run(20)', False),
    ('Item | Value |\n| Beta | None', False),
    ('Alpha | run(2) | Beta | None', False),
])
def test_linked_code_table_cells_preserve_rows_pipes_and_values(quote, accepted):
    source = ('| Item | Value |\n| --- | --- |\n'
              '| [**Alpha**](https://example.test/A_(B) "Title") | `run(2)` |\n'
              '| Beta | `None` |')
    actual = locate_quote(quote, source, markdown_formatting=True)
    assert (actual is not None) is accepted
    if actual is not None:
        assert actual in source


def test_new_inline_projection_restores_span_cap_and_recorded_read_boundaries():
    source = 'Use [`value`](https://example.test/' + 'x' * 2050 + ' "Title") now.'
    assert locate_quote('Use value now.', source, markdown_formatting=True) is None
    source = 'Use [`value`](https://example.test/A_(B) "Title") now.'
    split = source.index(' now.')
    assert locate_quote('value now.', source[split:], markdown_formatting=True,
                        markdown_prefix=source[:split]) is None
    assert locate_quote('value now.', source, markdown_formatting=True,
                        markdown_prefix='```text\n') is None
    split = source.index('value')
    assert locate_quote('value now.', source[split:], markdown_formatting=True,
                        markdown_prefix=source[:split]) == source[split:]


def test_new_inline_maps_are_monotone_exact_and_projection_count_is_constant():
    from deepresearch.workflows.components.markdown_quotations import markdown_projections
    source = 'Use **Alpha** and [`run(2)`](https://example.test/A_(B) "Title"), then `None`.'
    projections = list(markdown_projections(source))
    assert 0 < len(projections) <= 16
    for visible, positions in projections:
        assert positions == sorted(set(positions))
        assert all(0 <= i < len(source) for i in positions)
        assert visible == ''.join(source[i] for i in positions)


def test_multiline_flat_item_can_omit_inline_syntax_without_flattening_items():
    source = ('- `value` stays open,\n'
              '  while [`run(2)`](https://example.test/A_(B) "Title") keeps `None`.\n'
              '- `other` stays closed.')
    assert locate_quote('value stays open', source, markdown_formatting=True) == 'value` stays open'
    quote = 'value stays open, while run(2) keeps None.'
    assert locate_quote(quote, source, markdown_formatting=True) == source[3:source.index('\n-')]
    assert locate_quote(quote + ' other stays closed.', source, markdown_formatting=True) is None
    assert locate_quote('run(20) keeps None.', source, markdown_formatting=True) is None


@pytest.mark.parametrize('source', [
    '- `value` stays open,\n  while `None` stays.\n  - `nested` follows.',
    '1. `value` stays open,\n   while `None` stays.',
    '- `value` stays open,\n\n  Additional paragraph with `None`.',
])
def test_multiline_item_projection_excludes_nested_ordered_and_multiple_blocks(source):
    assert locate_quote('value stays open, while None stays.', source, markdown_formatting=True) is None


def test_unsupported_markup_elsewhere_in_an_inline_block_keeps_it_literal():
    source = 'Earlier <sup hidden>1</sup>, use [`value`](https://example.test/a "Title") now.'
    assert locate_quote('use value now.', source, markdown_formatting=True) is None
    assert locate_quote('use [`value`](https://example.test/a "Title") now.', source,
                        markdown_formatting=True) == source[source.index('use '):]


@pytest.mark.parametrize('tag', ['sup', 'sub'])
def test_preserved_annotation_does_not_disable_later_link_formatting(tag):
    source = f'Earlier <{tag}>1</{tag}>, use [`value`](https://example.test/a "Title") now.'
    assert locate_quote('use value now.', source, markdown_formatting=True) == source[source.index('use '):]
    assert locate_quote('Earlier 1, use value now.', source, markdown_formatting=True) is None
    assert locate_quote('Earlier 2, use value now.', source, markdown_formatting=True) is None
    broken = source.replace(f'</{tag}>', '</span>')
    assert locate_quote('use value now.', broken, markdown_formatting=True) is None


@pytest.mark.parametrize('source,expected', [
    ('Use value now.', 0),
    ('Use `value` now.', 1),
    ('Use **value** now.', 1),
    ('Use [value](https://example.test/A_(B) "Title") now.', 1),
    ('Use [`value`](https://example.test/A_(B) "Title") now.', 3),
    ('- Alpha\n- Beta', 1),
    ('- `Alpha`\n- `Beta`', 2),
    ('- **Alpha**\n- `Beta`', 4),
    ('- `Alpha` stays,\n  while Beta waits.', 1),
    ('| Item | Value |\n| --- | --- |\n| Alpha | 2 |', 1),
    ('| Item | Value |\n| --- | --- |\n| Alpha | `2` |', 3),
    ('| Item | Value |\n| --- | --- |\n| **Alpha** | `2` |', 7),
])
def test_absent_inline_groups_do_not_duplicate_source_position_maps(source, expected):
    from deepresearch.workflows.components.markdown_quotations import markdown_projections
    projections = list(markdown_projections(source))
    maps = [tuple(positions) for _, positions in projections]
    assert len(maps) == len(set(maps)) == expected
    for visible, positions in projections:
        assert visible == ''.join(source[i] for i in positions)


def test_repeated_code_spans_do_not_multiply_group_policy_maps_with_prefix():
    from deepresearch.workflows.components.markdown_quotations import markdown_projections
    prefix = '# Context\n\n```text\nLiteral `code` and **stars**.\n```\n\n'
    for count in (1, 100):
        text = ' '.join(['Use `value` now.'] * count)
        projections = list(markdown_projections(prefix + text))
        assert len(projections) == 1
        visible, positions = projections[0]
        assert visible == ' '.join(['Use value now.'] * count)
        assert all(i >= len(prefix) for i in positions)
        assert visible == ''.join((prefix + text)[i] for i in positions)
