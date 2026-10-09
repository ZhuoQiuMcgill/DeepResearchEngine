"""HTML quotation adaptation preserves cells, values and archived offsets."""
import pytest

from deepresearch.workflows.components.quotations import locate_quote


TABLE = ('<table><tr><th colspan="2">Memory</th></tr>\n'
         '<tr><td>RAM</td><td>16 GB</td></tr>\n'
         '<tr><td>Storage</td><td>256 GB</td></tr>\n'
         '<tr><td>Availability</td><td>not available</td></tr></table>')


@pytest.mark.parametrize("space", [" ", "\t", "\r\n", " \n\t"])
@pytest.mark.parametrize("side", ["quote", "source"])
def test_cell_edge_formatting_returns_original_utf8_span(space, side):
    exact = '<td>RAM</td><td>16 GB</td>'
    formatted = f'<td>{space}RAM{space}</td><td>{space}16 GB{space}</td>'
    quote = formatted if side == "quote" else exact
    text = "😀préface\n" + TABLE.replace(exact, formatted if side == "source" else exact)
    expected = formatted if side == "source" else exact
    assert locate_quote(quote, text) is None
    actual = locate_quote(quote, text, html_cells=True)
    assert actual == expected
    offset = len(text[:text.index(actual)].encode())
    assert text.encode()[offset:offset + len(actual.encode())] == actual.encode()


def test_partial_cell_quote_and_markdown_link_projection_compose():
    source = '<table><tr><td>RAM</td><td>[16 GB](https://example.org/spec)</td></tr></table>'
    quote = 'RAM\t</td><td>16 GB\t</td>'
    assert locate_quote(quote, source, html_cells=True) is None
    assert locate_quote(quote, source, html_cells=True, markdown_links=True) == (
        'RAM</td><td>[16 GB](https://example.org/spec)</td>')


@pytest.mark.parametrize("quote", [
    '<td>RAM\t</td><td>160 GB</td>',  # changed number
    '<td>Availability\t</td><td>available</td>',  # lost negation
    '<td>Storage\t</td><td>16 GB</td>',  # wrong row association
    '<td>16 GB\t</td><td>RAM</td>',  # reversed columns
    '<th colspan="3">Memory\t</th>',  # changed relationship
    '<th>Memory\t</th>',  # omitted relationship
    '<td>RAM\t</td><td>16 GB</td><td>Storage</td><td>256 GB</td>',  # missing row
    '<td>ram\t</td><td>16 GB</td>',
    '<td>RAM\t</td><td>16GB</td>',
    '<td>RAM\t</td><td>16 GB\u00a0</td>',  # entity/layout semantics not admitted
    'RAM 16 GB Storage 256 GB',  # flattened structure
])
def test_cell_formatting_never_repairs_facts_or_relationships(quote):
    assert locate_quote(quote, TABLE, html_cells=True) is None


@pytest.mark.parametrize("wrapper", [
    '<pre>{}</pre>', '<code>{}</code>', '<textarea>{}</textarea>',
    '<!-- {} -->', '```html\n{}\n```', '~~~html\n{}\n~~~',
    '`{}`', '``{}``', '```html\n{}', '    {}', '\t{}',
])
def test_code_and_comments_remain_literal(wrapper):
    text = wrapper.format(TABLE)
    quote = '<td>RAM\t</td><td>16 GB</td>'
    assert locate_quote(quote, text, html_cells=True) is None
    assert locate_quote('<td>RAM</td><td>16 GB</td>', text, html_cells=True) is not None


def test_literal_code_before_real_table_cannot_supply_match():
    text = '```html\n' + TABLE + '\n```\n' + TABLE
    # Prefix selects the source region; adaptation must return only the second.
    quote = TABLE.replace('RAM</td>', 'RAM\t</td>')
    assert locate_quote(quote, text, html_cells=True) == TABLE
    from deepresearch.workflows.components.html_quotations import table_projections
    marked = TABLE.replace('RAM</td>', 'RAM\t</td>')
    projected = list(table_projections('```html\n' + marked + '\n```\n' + marked))
    assert len(projected) == 1 and projected[0][0] == TABLE.replace('</tr>\n<tr>', '</tr><tr>')
    assert projected[0][1][0] == len('```html\n' + marked + '\n```\n')


def test_plain_fragment_requires_explicit_source_table_context():
    assert locate_quote('RAM\t</td>', 'RAM</td>', html_cells=True) is None
    # Unbounded source fragments stay literal because their context is unknown.
    assert locate_quote('RAM</td>', 'RAM\t</td>', html_cells=True) is None


def test_expanded_original_span_still_obeys_quote_bound():
    quote = '<td>RAM\t</td><td>16 GB</td>'
    text = '<table><tr><td>RAM' + ' ' * 2048 + '</td><td>16 GB</td></tr></table>'
    assert locate_quote(quote, text, html_cells=True) is None


@pytest.mark.parametrize("parent", ["div", "td", "th", "li", "dd"])
def test_optional_paragraph_end_preserves_parent_boundary_and_saved_span(parent):
    passage = f'<{parent}><p>515 g <span>with strap</span></p></{parent}>'
    text = ('<table><tr>' + passage + '</tr></table>' if parent in {'td', 'th'}
            else '<table><tr><td>' + passage + '</td></tr></table>')
    quote = passage.replace('</p>', '')
    assert locate_quote(quote, text, html_cells=True) == passage
    assert locate_quote(passage, text.replace('</p>', ''), html_cells=True) == quote
    assert locate_quote(quote.replace('515', '551'), text, html_cells=True) is None


@pytest.mark.parametrize("parent", ["a", "audio", "del", "ins", "map", "noscript", "video", "custom-item"])
def test_nonoptional_paragraph_end_is_never_discarded(parent):
    passage = f'<{parent}><p>515 g</p></{parent}>'
    text = '<table><tr><td>' + passage + '</td></tr></table>'
    assert locate_quote(passage.replace('</p>', ''), text, html_cells=True) is None


def test_paragraph_separation_and_inline_markup_are_not_flattened():
    text = '<table><tr><td><p>not</p><p>available</p></td></tr></table>'
    assert locate_quote('<p>not<p>available</td>', text, html_cells=True) is None
    assert locate_quote('not available', text, html_cells=True) is None
    text = '<table><tr><td><pre><p>not</p></div></pre></td></tr></table>'
    assert locate_quote('<p>not</div>', text, html_cells=True) is None


STRUCTURED_TABLE = ('<table id="specs"><thead><tr><th colspan="2">Feature</th></tr></thead>'
                    '<tbody><tr><th scope="row">Memory</th><td>16 GB</td><td></td></tr>'
                    '<tr><td>Availability</td><td>not available</td></tr></tbody>'
                    '<tfoot><tr><td>Price</td><td>256</td></tr></tfoot></table>')


@pytest.mark.parametrize("gap", [" ", "\t", "\r\n", "\f", " \r\n\t\f"])
@pytest.mark.parametrize("side", ["quote", "source"])
@pytest.mark.parametrize("boundary", [
    '<table id="specs">|<thead>', '<thead>|<tr>', '</th>|</tr>', '</tr>|</thead>',
    '</thead>|<tbody>', '<tbody>|<tr>', '<tr>|<th scope="row">', '</th>|<td>',
    '</td>|<td>', '</td>|</tr>', '</tr>|<tr>', '</tr>|</tbody>', '</tbody>|<tfoot>',
    '<tfoot>|<tr>', '</tr>|</tfoot>', '</tfoot>|</table>',
])
def test_structural_gap_variants_both_sides_preserve_original_span(gap, side, boundary):
    left, right = boundary.split('|')
    formatted = STRUCTURED_TABLE.replace(left + right, left + gap + right)
    source = formatted if side == "source" else STRUCTURED_TABLE
    quote = formatted if side == "quote" else STRUCTURED_TABLE
    text = "😀préface\n" + source
    assert locate_quote(quote, text) is None
    assert locate_quote(quote, text, html_cells=True) == source
    from deepresearch.workflows.components.quotations import PreparedQuoteSource
    prepared = PreparedQuoteSource(text, html_cells=True)
    assert prepared.locate_spans(quote) == [(len("😀préface\n"), len(text))]
    offset = len("😀préface\n".encode())
    assert text.encode()[offset:offset + len(source.encode())] == source.encode()


@pytest.mark.parametrize("quote", [
    '<td>❌</td><td>✅</td></tr>', '<td>❌</td>\t<td>✅</td>\f</tr>',
    '❌</td><td>✅</td></tr>', '</td><td>✅</td></tr>',
])
def test_fragment_can_match_with_original_structural_gaps(quote):
    source = '<table><tbody><tr><td>Feature</td><td>❌</td>\n<td>✅</td>\n</tr></tbody></table>'
    actual = locate_quote(quote, source, html_cells=True)
    expected = ('<td>❌</td>\n<td>✅</td>\n</tr>' if quote.startswith('<td>') else
                '❌</td>\n<td>✅</td>\n</tr>' if quote.startswith('❌') else
                '</td>\n<td>✅</td>\n</tr>')
    assert actual == expected


@pytest.mark.parametrize("wrapper", [
    '<pre>{}</pre>', '<code>{}</code>', '<textarea>{}</textarea>', '<script>{}</script>',
    '<style>{}</style>', '<math>{}</math>', '<svg>{}</svg>', '<template>{}</template>',
    '<noscript>{}</noscript>', '<div hidden>{}</div>', '<div style="display:none">{}</div>',
    '<div aria-hidden="true">{}</div>', '<!-- {} -->', '`{}`', '``{}``',
    '```html\n{}\n```', '~~~html\n{}\n~~~', '```html\n{}', '    {}', '\t{}', '\\{}',
])
@pytest.mark.parametrize("side", ["quote", "source"])
def test_structural_gaps_never_adapt_literal_or_opaque_context(wrapper, side):
    compact = '<table><tr><td>A</td><td>B</td></tr></table>'
    spaced = compact.replace('</td></tr>', '</td>\n</tr>')
    query = spaced if side == "quote" else compact
    source = wrapper.format(compact if side == "quote" else spaced)
    assert locate_quote(query, source, html_cells=True, markdown_formatting=True) is None
    exact = compact if side == "quote" else spaced
    assert locate_quote(exact, source, html_cells=True) == exact


@pytest.mark.parametrize("table", [
    '<table><tr><td>A</td><td>B</td></tr>',  # incomplete table
    '<tr><td>A</td><td>B</td></tr>',  # unbounded fragment
    '<table><td>A</td><td>B</td></table>',  # missing row
    '<table><tr><td>A</th><td>B</td></tr></table>',  # mismatched end
    '<table><tr><td><td>A</td></td><td>B</td></tr></table>',  # nested cells
    '<table><tr><td><table><tr><td>A</td><td>B</td></tr></table></td></tr></table>',
    '<table><tr><td><strong>A</td><td>B</td></tr></table>',  # malformed inline child
    '<table><tr><td>A</td garbage><td>B</td></tr></table>',
    '<table><tr><td hidden>A</td><td>B</td></tr></table>',
    '<table><tr><td><math>x</math>A</td><td>B</td></tr></table>',
    '<table><tr><td><code>x</code>A</td><td>B</td></tr></table>',
    '<table><tr><td>A</td><!-- note --><td>B</td></tr></table>',
    '<table><tr>outside<td>A</td><td>B</td></tr></table>',
])
@pytest.mark.parametrize("side", ["quote", "source"])
def test_structural_gaps_require_complete_valid_source_table(table, side):
    spaced = table.replace('<td>B', '\n<td>B')
    source = spaced if side == "source" else table
    query = table if side == "source" else spaced
    assert locate_quote(query, source, html_cells=True) is None
    assert locate_quote('<td>B</td>\n</tr>', table, html_cells=True) is None


@pytest.mark.parametrize("mutation", [
    lambda s: s.replace('<td></td>', ''),
    lambda s: s.replace('<td>16 GB</td><td></td>', '<td></td><td>16 GB</td>'),
    lambda s: s.replace('<td>16 GB</td>', '<td>160 GB</td>'),
    lambda s: s.replace('not available', 'available'),
    lambda s: s.replace('colspan="2"', 'colspan="3"'),
    lambda s: s.replace('<th scope="row">Memory</th>', '<td>Memory</td>'),
    lambda s: s.replace('</tr></tbody><tfoot><tr>', ''),
    lambda s: s.replace('</td></tr><tr><td>', '</td><td>'),
])
def test_structural_gaps_never_repair_empty_cells_values_or_order(mutation):
    source = STRUCTURED_TABLE.replace('</td></tr>', '</td>\n</tr>')
    assert locate_quote(mutation(STRUCTURED_TABLE), source, html_cells=True) is None


@pytest.mark.parametrize("body,query", [
    ('<strong>not</strong> <em>available</em>', '<strong>not</strong><em>available</em>'),
    ('<strong>16</strong> GB', '<strong>16</strong>GB'),
    ('<a href="https://example.test/a b">X</a>', '<a href="https://example.test/ab">X</a>'),
    ('&amp;', '&'), ('&#32;', ''), ('&nbsp;', ''),
])
def test_cell_text_gaps_attributes_and_entities_stay_literal(body, query):
    source = f'<table><tr><td>{body}</td><td>tail</td>\n</tr></table>'
    quote = f'<td>{query}</td><td>tail</td></tr>'
    assert locate_quote(quote, source, html_cells=True) is None


@pytest.mark.parametrize("gap", ['\v', '\u00a0', '\u2003', '&nbsp;', '&#10;'])
@pytest.mark.parametrize("side", ['quote', 'source'])
def test_only_ascii_structural_whitespace_may_disappear(gap, side):
    compact = '<table><tr><td>A</td><td>B</td></tr></table>'
    spaced = compact.replace('</td></tr>', '</td>' + gap + '</tr>')
    assert locate_quote(compact if side == 'source' else spaced,
                        spaced if side == 'source' else compact, html_cells=True) is None


def test_structural_gap_context_and_offsets_use_recorded_prefix_only():
    from deepresearch.workflows.components.quotations import PreparedQuoteSource
    prefix = '😀préface\n<table><tbody><tr>'
    text = '<td>Label</td><td>16 GB</td>\n</tr></tbody></table>'
    quote = '<td>Label</td><td>16 GB</td></tr>'
    exact = '<td>Label</td><td>16 GB</td>\n</tr>'
    assert locate_quote(quote, text, html_cells=True) is None
    prepared = PreparedQuoteSource(text, html_cells=True, markdown_prefix=prefix)
    assert prepared.locate(quote) == exact
    assert prepared.locate_spans(quote) == [(0, len(exact))]
    assert prepared.locate('<tr>' + quote) is None  # prefix cannot supply quotation bytes
    assert locate_quote(quote, text, html_cells=True, markdown_prefix='```html\n' + prefix) is None


def test_structural_gap_expansion_obeys_returned_span_bound():
    quote = '<td>A</td><td>B</td></tr>'
    source = '<table><tr><td>A</td><td>B</td>' + '\n' * 2048 + '</tr></table>'
    assert locate_quote(quote, source, html_cells=True) is None


def test_attribute_html_literal_is_never_parsed_as_structural_boundary():
    source = '<table><tr><td title="</td> </tr>">A</td><td>B</td>\n</tr></table>'
    quote = '<td title="</td></tr>">A</td><td>B</td></tr>'
    assert locate_quote(quote, source, html_cells=True) is None
    literal = '<td title="</td> </tr>">A</td><td>B</td>\n</tr>'
    assert locate_quote(quote.replace('title="</td></tr>"', 'title="</td> </tr>"'),
                        source, html_cells=True) == literal


@pytest.mark.parametrize("invalid", [
    '<table/>', '<table><tr><td>A</tr></table>',
    '<table><tr><td><table><tr><td>A</td></tr></table></td></tr></table>',
])
def test_invalid_table_does_not_poison_later_independent_table(invalid):
    from deepresearch.workflows.components.html_quotations import table_projections
    table = '<table><tr><td>A</td><td>B</td>\n</tr></table>'
    text = invalid + '\n' + table
    views = list(table_projections(text))
    assert len(views) == 1
    assert views[0][1][0] == len(invalid) + 1
    assert ''.join(text[i] for i in views[0][1]) == table.replace('</td>\n</tr>', '</td></tr>')
