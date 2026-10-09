"""Visible inline formats remain anchored to their original structural block."""
import pytest

from deepresearch.workflows.components.quotations import locate_quote

OPTIONS = dict(markdown_links=True, html_cells=True, markdown_formatting=True)


@pytest.mark.parametrize('tag', ['p', 'td', 'th', 'dt', 'dd', 'li'])
def test_inline_code_links_emphasis_and_empty_anchors_preserve_exact_original_span(tag):
    body = 'Use <span id="index-1"></span><a href="https://example.test/entry" title="Entry">'
    body += '<code><span>value</span></code></a> only if <strong>ready</strong>.'
    source = '<' + tag + '>' + body + '</' + tag + '>'
    assert locate_quote('Use value only if ready.', source, **OPTIONS) == body
    for changed in ['Use value if ready.', 'Use Value only if ready.', 'Use value only if not ready.']:
        assert locate_quote(changed, source, **OPTIONS) is None


def test_nested_paragraph_is_independent_of_other_paragraphs_and_cell():
    source = '<table><tr><td><div><p>100 <span>items only</span></p>'
    source += '<p>Separate condition.</p></div></td><td>Group B</td></tr></table>'
    assert locate_quote('100 items only', source, **OPTIONS) == '100 <span>items only'
    assert locate_quote('100 items only Separate condition.', source, **OPTIONS) is None
    assert locate_quote('Separate condition. Group B', source, **OPTIONS) is None


def test_table_inline_projection_retains_row_cell_spans_and_attributes():
    source = '<table><tr><th>Label</th><td colspan="2">8 <a href="https://example.test/u">GB</a> total</td></tr></table>'
    quote = 'Label</th><td colspan="2">8 GB total'
    assert locate_quote(quote, source, **OPTIONS) == 'Label</th><td colspan="2">8 <a href="https://example.test/u">GB</a> total'
    for changed in ['Label 8 GB total', quote.replace('colspan="2"', 'colspan="1"'), quote.replace('8 GB', '16 GB')]:
        assert locate_quote(changed, source, **OPTIONS) is None


def test_highlighted_code_preserves_literal_strings_operators_and_comments():
    source = '<pre><code>conn <span>=</span> open(<span>"test.db"</span>)\n# use \'with\' here</code></pre>'
    assert locate_quote('conn = open("test.db")', source, **OPTIONS) == 'conn <span>=</span> open(<span>"test.db"</span>)'
    assert locate_quote("# use 'with' here", source, **OPTIONS) == "# use 'with' here"
    for changed in ['conn == open("test.db")', 'conn = open("other.db")', '# use `with` here']:
        assert locate_quote(changed, source, **OPTIONS) is None


@pytest.mark.parametrize('source', [
    '<p>Alpha <span hidden>Beta</span> Gamma</p>',
    '<p>Alpha <span style="display:none">Beta</span> Gamma</p>',
    '<p>Alpha <span class="unknown">Beta</span> Gamma</p>',
    '<p hidden>Alpha <span>Beta</span> Gamma</p>',
    '<div style="display:none"><p>Alpha <span>Beta</span> Gamma</p></div>',
    '<p>Alpha <del>Beta</del> Gamma</p>',
    '<p>Alpha <sup>Beta</sup> Gamma</p>',
    '<p>Alpha <span>Beta</b> Gamma</p>',
    '<p>Alpha <span>Beta</span> Gamma',
    '<p>Alpha <!-- uncertain --> <span>Beta</span> Gamma</p>',
    '<p>Alpha <span>Beta</span><br> Gamma</p>',
    '<script><p>Alpha <span>Beta</span> Gamma</p></script>',
    '<p>Alpha <a href="javascript:run()">Beta</a> Gamma</p>',
    '<p>Alpha <span id="a" id="b">Beta</span> Gamma</p>',
])
def test_unsupported_or_malformed_html_remains_literal(source):
    assert locate_quote('Alpha Beta Gamma', source, **OPTIONS) is None


@pytest.mark.parametrize('wrapper', ['    {}', '```html\n{}\n```', '~~~html\n{}\n~~~'])
def test_html_appearing_inside_markdown_code_cannot_be_interpreted(wrapper):
    body = '<p>Alpha <span>Beta</span> Gamma</p>'
    assert locate_quote('Alpha Beta Gamma', wrapper.format(body), **OPTIONS) is None
    assert locate_quote(body, wrapper.format(body), **OPTIONS) == body


def test_recorded_prefix_keeps_a_fragment_inside_its_literal_code_block():
    body = '<p>Alpha <span>Beta</span> Gamma</p>\n```'
    assert locate_quote('Alpha Beta Gamma', body, markdown_prefix='```html\n', **OPTIONS) is None


def test_entities_are_not_decoded_and_source_opt_in_is_required():
    source = '<p>Alpha <span>&amp;</span> Beta</p>'
    assert locate_quote('Alpha & Beta', source, **OPTIONS) is None
    assert locate_quote('Alpha &amp; Beta', source, **OPTIONS) == 'Alpha <span>&amp;</span> Beta'
    assert locate_quote('Alpha &amp; Beta', source, html_cells=False, markdown_formatting=True) is None


def test_excessive_nesting_disables_optional_projection_but_not_exact_match():
    source = '<div>' * 130 + '<p>Alpha <span>Beta</span> Gamma</p>' + '</div>' * 130
    assert locate_quote('Alpha Beta Gamma', source, **OPTIONS) is None
    assert locate_quote('Alpha <span>Beta</span> Gamma', source, **OPTIONS) is not None


@pytest.mark.parametrize('sibling', ['<br>Later', '<sup>2</sup>', '<span hidden>Later</span>', '<p>Later</p>'])
def test_unsupported_sibling_stays_literal_without_disabling_an_independent_link(sibling):
    source = '<table><tr><th>Label</th><td>8 <a href="https://example.test/u">GB</a> total' + sibling + '</td></tr></table>'
    quote = 'Label</th><td>8 GB total'
    assert locate_quote(quote, source, **OPTIONS) == 'Label</th><td>8 <a href="https://example.test/u">GB</a> total'
    assert locate_quote('8 GB total Later', source, **OPTIONS) is None
    assert locate_quote('8 GB total2', source, **OPTIONS) is None


@pytest.mark.parametrize('wrapper', ['`{}`', '``{}``', '```\n{}\n```', '    {}'])
def test_code_delimiter_projection_is_never_reinterpreted_as_html(wrapper):
    body = '<table><tr><td>12.5 kg <span>per unit</span></td></tr></table>'
    assert locate_quote('12.5 kg per unit', wrapper.format(body), **OPTIONS) is None
    assert locate_quote(body, wrapper.format(body), **OPTIONS) == body


@pytest.mark.parametrize('br', ['<br>', '<br/>', '<br />'])
@pytest.mark.parametrize('tag', ['p', 'td', 'li'])
def test_nested_break_keeps_boundary_but_allows_independent_inline_quote(br, tag):
    body = f'Intro{br}Read <a href="https://example.test/method">the method</a> carefully.'
    source = f'<{tag}><span>{body}</span></{tag}>'
    assert locate_quote('Read the method carefully.', source, **OPTIONS) == (
        'Read <a href="https://example.test/method">the method</a> carefully.')
    assert locate_quote('IntroRead the method carefully.', source, **OPTIONS) is None
    assert locate_quote('Intro Read the method carefully.', source, **OPTIONS) is None
    assert locate_quote('Read the method carelessly.', source, **OPTIONS) is None


@pytest.mark.parametrize('wrapper', [
    '<span hidden>{}</span>', '<span style="display:none">{}</span>',
    '<code>{}</code>', '<span class="unknown">{}</span>',
])
def test_nested_break_does_not_relax_unsupported_wrappers(wrapper):
    source = '<p>' + wrapper.format('Intro<br/>Read <em>the method</em> carefully.') + '</p>'
    # Inline <code> bodies can omit presentation, as before, but never a break.
    query = 'Intro Read the method carefully.' if wrapper.startswith('<code>') else 'Read the method carefully.'
    assert locate_quote(query, source, **OPTIONS) is None
