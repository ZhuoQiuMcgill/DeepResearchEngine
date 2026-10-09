"""Generic conditions and source relationships, independent of benchmark topics."""
from __future__ import annotations

import pytest

from tests.toolset.test_html_fidelity import extract

PROSE = '<p>' + 'These measurements apply only under the explicitly documented conditions. ' * 12 + '</p>'


@pytest.mark.parametrize('tag', ['main', 'article', 'div'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_short_link_labels_cannot_delete_a_condition_or_nested_exception(tag, wrapped):
    condition = ('<p>Before proceeding, examine the <a href="range">range</a> and '
                 'its <a href="check">check</a>.</p><ul><li>Stop if the test fails.</li></ul>')
    if wrapped:
        condition = '<div>' + condition + '</div>'
    text = extract(PROSE + '<ol><li>' + condition + '</li></ol>'
                   '<p>Only then record the result.</p>', tag=tag, noise=True)
    assert 'Before proceeding, examine the [range](https://example.test/manual/range)' in text
    assert '[check](https://example.test/manual/check)' in text
    assert '\n   - Stop if the test fails.' in text
    assert text.index('Before proceeding') < text.index('Stop if the test fails.') < text.index('Only then')
    assert 'Member login' not in text


def test_merged_table_retains_row_and_column_spans():
    text = extract(PROSE + '<table><caption>Recorded measurements</caption>'
        '<tr><th rowspan="2">Condition</th><th colspan="2">Duration (min)</th></tr>'
        '<tr><th>Group A</th><th>Group B</th></tr>'
        '<tr><th rowspan="2">Cold</th><td>12</td><td>24</td></tr>'
        '<tr><td>±2</td><td>±3</td></tr></table>')
    from lxml import html
    table = html.fragment_fromstring(text, create_parent=True).find('.//table')
    assert table is not None
    assert table.xpath('.//th[@colspan="2"]/text()') == ['Duration (min)']
    assert table.xpath('.//th[@rowspan="2"]/text()') == ['Condition', 'Cold']
    assert table.xpath('.//tr[4]/td/text()') == ['±2', '±3']


def test_explicit_and_reversed_list_values_do_not_become_sequential_steps():
    text = extract(PROSE + '<ol start="5" reversed><li>Initial check.</li>'
                   '<li value="2">Special condition.</li><li>Final check.</li></ol>')
    from lxml import html
    sequence = html.fragment_fromstring(text, create_parent=True).find('.//ol')
    assert sequence is not None and 'reversed' in sequence.attrib and sequence.get('start') == '5'
    assert sequence.xpath('./li[@value="2"]/text()') == ['Special condition.']


def test_recovery_does_not_absorb_a_separate_article_or_hidden_conditions():
    condition = '<ol><li>Read <a href="x">X</a> and <a href="y">Y</a> before proceeding.</li></ol>'
    text = extract('<article>' + PROSE + condition + '<p hidden>Hidden condition.</p>'
                   '<p aria-hidden="true">Visible qualifier excluded only from accessibility APIs.</p></article>'
                   '<div><p>Unrelated recommendation. ' + 'Card summary. ' * 100 + '</p></div>')
    assert 'before proceeding.' in text
    assert 'Unrelated recommendation' not in text
    assert 'Hidden condition' not in text
    assert 'Visible qualifier excluded only from accessibility APIs.' in text


def test_preservation_guard_allows_restored_dates_but_not_changed_evidence():
    from lxml import etree, html
    from deepresearch.engine.toolset.html_structure import _retains_text
    primary = etree.fromstring(b'<body><list><item>Source A, , correct only above 40.</item></list></body>')
    assert _retains_text(primary, html.fromstring('<div><dl><dd>Source A, <time>2020</time>, correct only above 40.</dd></dl></div>'))
    for changed in ['Source A, 2020, correct only above 41.', 'Source A, 2020, correct above 40.',
                    'Source A, 2020, correct only below 40.']:
        assert not _retains_text(primary, html.fromstring('<div><p>'+changed+'</p></div>'))


def test_restored_image_link_has_one_destination_without_nested_repair_labels():
    text = extract(PROSE + '<p>Results: <a href="data.csv"><img src="plot.png" alt="Series"></a></p>'
                   '<ol><li>Read <a href="x">X</a> and <a href="y">Y</a> before proceeding.</li></ol>')
    assert '[![Series](https://example.test/manual/plot.png)](https://example.test/manual/data.csv)' in text
    assert text.count('https://example.test/manual/data.csv') == 1


def test_ambiguous_page_is_not_expanded_to_rescue_a_list():
    main = '<div><h1>Original observations</h1>'+PROSE
    main += '<ol><li>Read <a href="x">X</a> and <a href="y">Y</a> before proceeding.</li></ol>'
    main += '<p>Documented results. ' + 'Independent recorded observation. ' * 10 + '</p></div>'
    controls = '<ul>' + ''.join(f'<li><a href="currency-{i}">Currency {i}</a></li>' for i in range(100)) + '</ul>'
    cards = '<div><h2>Recommended</h2><p>Unrelated card. '+ 'A separate topic. '*20 + '</p></div>'
    from deepresearch.engine.toolset.article_extraction import extract_source
    from deepresearch.engine.toolset.common import LIMITS
    from tests.toolset.test_fetch_v2 import info
    markup = ('<html><body><div>'+controls+main+cards+'</div></body></html>').encode()
    result = extract_source(markup, info(markup), LIMITS)
    assert 'Currency 99' not in result['text'].decode()
    assert 'before proceeding.' in result['text'].decode()
    diagnostic = result['provenance']['html_extraction']['structure']
    assert diagnostic['unresolved'] and diagnostic['decision'] == 'partially_recovered'
    assert diagnostic['recovered_blocks'] == 1 and diagnostic['unresolved_blocks'] == 1


def test_nested_code_indentation_is_preserved_under_markdown_list_indentation():
    code = '\n     bytes=0-499\n'
    text = extract(PROSE + '<ol><li><p>Before proceeding, read <a href="x">X</a> and <a href="y">Y</a>.</p>'
                   '<pre>'+code+'</pre></li></ol>')
    assert 'Before proceeding' in text and 'bytes=0-499' in text
    assert '\n        bytes=0-499\n' in text  # five source spaces + three list spaces


def test_linked_code_keeps_both_indentation_and_source_destinations():
    text = extract(PROSE + '<pre>accept = <a href="terms.html#token">TOKEN</a>\n    next</pre>'
        '<ol><li>Read <a href="x">X</a> and <a href="y">Y</a> before proceeding.</li></ol>')
    from lxml import html
    code = html.fragment_fromstring(text, create_parent=True).find('.//pre')
    assert code is not None and code.text_content() == 'accept = TOKEN\n    next'
    assert code.xpath('.//a/@href') == ['https://example.test/manual/terms.html#token']


def test_literal_structure_excludes_comments_and_executable_attributes():
    text = extract(PROSE + '<table onclick="track()"><tr><th colspan="2">Observations</th></tr>'
        '<!-- Private rendering note. --><tr><td>12</td><td>24</td></tr></table>')
    assert '<table' in text and 'colspan="2"' in text
    assert 'Private rendering note.' not in text and 'onclick' not in text and 'track()' not in text


def test_structure_recovery_preserves_code_exponents_and_surrounding_qualifiers():
    code = 'if ready:\n    begin()\n    if failed:\n        rollback()\nfinish()'
    text = extract(PROSE + '<p>Only valid above 0 degrees, at 10<sup>−3</sup> mol L<sup>−1</sup>.</p>'
        '<pre><code>' + code + '</code></pre>'
        '<ol><li>Read <a href="x">X</a> and <a href="y">Y</a> before proceeding.</li></ol>')
    assert 'before proceeding.' in text
    assert 'Only valid above 0 degrees' in text
    assert '10<sup>−3</sup> mol L<sup>−1</sup>' in text
    assert '\n' + code + '\n' in text
    assert text.count('rollback()') == 1


def test_preformatted_highlighting_does_not_insert_blank_lines():
    from lxml import html
    from deepresearch.engine.toolset.html_structure import _render
    code='>>> statement()\n<div><span>result</span>\n</div>>>> next()'
    node=html.fromstring('<div><pre>'+code+'</pre></div>')
    emitted=[]
    text=_render(node,emitted)
    expected='>>> statement()\nresult\n>>> next()'
    assert '\n'+expected+'\n' in text and expected in emitted


def test_literal_structures_record_visible_code_even_when_spans_split_words():
    from lxml import html
    from deepresearch.engine.toolset.html_structure import _render
    emitted=[]
    text=_render(html.fromstring('<div><dl><dt>Constraint</dt><dd><code><span>WITHOUT</span> '
        '<span>ROWID</span></code></dd></dl></div>'),emitted)
    assert 'WITHOUT ROWID' in emitted
    assert html.fragment_fromstring(text,create_parent=True).find('.//code').text_content()=='WITHOUT ROWID'


def test_inline_code_source_line_break_does_not_block_unrelated_structure_recovery():
    from deepresearch.engine.toolset.article_extraction import extract_source
    from deepresearch.engine.toolset.common import LIMITS
    from tests.toolset.test_fetch_v2 import info
    markup=('<html><body><main>'+PROSE+'<p>Use <code>\nPoolType</code> for this documented setting.</p>'
        '<ul><li>Read <a href="x">X</a> and <a href="y">Y</a> before proceeding.</li></ul>'
        '</main></body></html>').encode()
    result=extract_source(markup,info(markup),LIMITS)
    assert 'PoolType' in result['text'].decode() and 'before proceeding.' in result['text'].decode()
    assert result['provenance']['html_extraction']['structure']['decision']=='recovered'


def test_code_table_keeps_line_numbers_separate_from_program_indentation():
    from lxml import html
    from deepresearch.engine.toolset.html_structure import _render
    body='<div><code><table><tr><td><pre>1\n2</pre></td><td><pre>if ready:\n    begin()</pre></td></tr></table></code></div>'
    emitted=[];text=_render(html.fromstring(body),emitted)
    table=html.fragment_fromstring(text,create_parent=True).find('.//table')
    assert table is not None
    assert [p.text_content() for p in table.findall('.//pre')]==['1\n2','if ready:\n    begin()']
    assert 'if ready:\n    begin()' in emitted


def test_literal_definition_keeps_email_citation_without_executable_destinations():
    from lxml import html
    from deepresearch.engine.toolset.html_structure import _render
    text=_render(html.fromstring('<div><dl><dt>Author</dt><dd><a href="mailto:author@example.test">Contact</a>'
        '<a href="javascript:alert(1)">Unsafe</a></dd></dl></div>'))
    assert 'mailto:author@example.test' in text
    assert 'javascript:' not in text


def test_linked_inline_code_preserves_destination_and_adjacent_prose():
    from lxml import html
    from deepresearch.engine.toolset.html_structure import _render
    code = '<code><a href="https://example.test/syntax">call()</a></code>'
    emitted = []
    text = _render(html.fromstring('<div><p>Use ' + code + ' only after validation.</p></div>'), emitted)
    assert 'Use <code>' in text and '</code> only after validation.' in text
    assert '<a href="https://example.test/syntax">call()</a>' in text
    assert 'call()' in emitted


def test_linked_inline_code_does_not_prevent_unrelated_table_recovery():
    from lxml import etree, html
    from deepresearch.engine.toolset.html_structure import recover_structure
    before = 'These original measurements apply only to the listed settings and exclude the external power supply.'
    scope = '<main><p>' + before + '</p><table><tr><th>Mass</th><td>123 g without supply</td></tr></table>'
    scope += '<p>See <code><a href="https://example.test/syntax">lookup()</a></code> for the original calculation.</p></main>'
    selected = '<body><p>' + before + '</p><table><row><cell>Mass</cell><cell/></row></table>'
    selected += '<p>See <code><ref target="https://example.test/syntax">lookup()</ref></code> for the original calculation.</p></body>'
    class Document:
        body = etree.fromstring(selected.encode())
    tree = html.fromstring('<html><body>' + scope + '</body></html>')
    primary = before + '\n| Mass | |\nSee `lookup()` (https://example.test/syntax) for the original calculation.'
    text, diagnostic = recover_structure(tree, Document(), primary)
    assert diagnostic['recovery_applied'] and not diagnostic['unresolved']
    assert '123 g without supply' in text
    assert '<code><a href="https://example.test/syntax">lookup()</a></code>' in text


def test_linked_inline_code_sanitizes_attributes_without_changing_literal_text():
    from lxml import html
    from deepresearch.engine.toolset.html_structure import _render
    text = _render(html.fromstring('<p>Read <code onclick="track()"><a href="javascript:track()">'
        '<span>call(</span><span>1)</span></a></code> before proceeding.</p>'))
    result = html.fragment_fromstring(text, create_parent=True).find('.//code')
    assert result.text_content() == 'call(1)'
    assert 'javascript:' not in text and 'onclick' not in text


@pytest.mark.parametrize('wrappers', [0,8])
@pytest.mark.parametrize('kind', ['table','ul'])
def test_anchored_structures_keep_order_and_do_not_expand_unrelated_branches(wrappers,kind):
    from lxml import etree,html
    from deepresearch.engine.toolset.html_selection import select_anchored_structure
    from deepresearch.engine.toolset.html_structure import _retains_text
    before='The documented measurements are valid only for the conditions listed immediately below.'
    after='These results exclude all observations outside the stated interval and sampling conditions.'
    block=('<table><tr><th>Interval</th><td>12–24</td></tr></table>' if kind=='table'
           else '<ul><li>Only valid from 12 through 24; exclude all other intervals.</li></ul>')
    scope=html.fromstring('<body><div><ul id="controls"><li>Unrelated control</li></ul><section><p>'+before+'</p>'
        +'<div>'*wrappers+block+'</div>'*wrappers+'<p>'+after+'</p></section>'
        '<div><p>A separate unselected recommendation with enough text to resemble an article paragraph.</p>'
        '<ul><li>Unrelated recommendation</li></ul></div></div></body>')
    original=etree.tostring(scope)
    document=etree.fromstring(('<body><p>'+before+'</p><p>'+after+'</p></body>').encode())
    blocks=scope.xpath('.//ul|.//table')
    projected,recovered=select_anchored_structure(scope,document,blocks)
    assert recovered==1 and _retains_text(document,projected)
    text=projected.text_content()
    assert text.index(before)<text.index('12')<text.index(after)
    assert 'Unrelated' not in text and 'separate unselected' not in text
    assert etree.tostring(scope)==original
