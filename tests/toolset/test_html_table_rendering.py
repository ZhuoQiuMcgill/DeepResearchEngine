"""Final rendered cells preserve source roles, values and row boundaries."""
from lxml import html
from markdown_it import MarkdownIt
import pytest

from tests.toolset.test_html_fidelity import extract
from tests.toolset.test_html_structure import PROSE


def cells(table):
    return [[(cell.tag, ''.join(''.join(cell.itertext()).split()))
             for cell in row if cell.tag in {'td', 'th'}]
            for row in table.iter('tr')]


@pytest.mark.parametrize('tag', ['main', 'article', 'div'])
@pytest.mark.parametrize('rows', [
    '<tr><td>Cold</td><td>12</td></tr><tr><td>Warm</td><td>24</td></tr>',
    '<tr><th>Cold</th><td>12</td></tr><tr><th>Warm</th><td>24</td></tr>',
    '<tr><th>Condition</th><th>Value</th></tr><tr><td>Cold</td></tr>'
    '<tr><td>Warm</td><td>24</td></tr>',
    '<tr><th>Condition</th><th>Value</th></tr><tr><th>Cold</th><td>12</td></tr>',
    '<tr><td><a href="first">A</a></td><td><code>12</code></td></tr>'
    '<tr><td>B</td><td>24</td></tr>',
])
def test_html_table_keeps_original_cell_roles_and_row_lengths(tag, rows):
    source = '<table>' + rows + '</table>'
    text = extract(PROSE + source, tag=tag, noise=True)
    rendered = html.fragment_fromstring(MarkdownIt('commonmark').enable('table').render(text), create_parent='div')
    assert [cells(table) for table in rendered.iter('table')] == [cells(html.fromstring(source))]
    assert 'Member login' not in text
    if 'href' in source:
        assert rendered.xpath('.//table//a/@href') == ['https://example.test/manual/first']
        assert rendered.xpath('.//table//code/text()') == ['12']


@pytest.mark.parametrize('value', ['A | B', '<code>A | B</code>',
    '<p>Only A.</p><p>Exclude B.</p>', 'A<br>B'])
def test_representable_header_table_keeps_cells_after_markdown_parsing(value):
    source = '<table><tr><th>Choice</th><th>Value</th></tr><tr><td>' + value + '</td><td>12</td></tr></table>'
    text = extract(PROSE + source)
    rendered = html.fragment_fromstring(MarkdownIt('commonmark').enable('table').render(text), create_parent='div')
    assert [cells(table) for table in rendered.iter('table')] == [cells(html.fromstring(source))]


def test_headerless_table_does_not_introduce_a_header_or_empty_cells():
    source = '<table><tr><td>12</td></tr><tr><td>24</td><td>Only after cooling.</td></tr></table>'
    text = extract(PROSE + source)
    rendered = html.fragment_fromstring(MarkdownIt('commonmark').enable('table').render(text), create_parent='div')
    assert len(rendered.findall('.//table')) == 1
    assert not rendered.findall('.//th')
    assert [len(row) for row in rendered.findall('.//tr')] == [1, 2]


def test_literal_table_stays_inside_the_selected_article_and_sanitizes_attributes():
    table = '<table onclick="track()"><tr><td>Only A</td><td>12</td></tr><tr><td>B</td><td>24</td></tr></table>'
    text = extract('<article>' + PROSE + table + '</article><aside><table><tr><td>Unrelated 99</td></tr></table></aside>')
    assert '<table>' in text and 'Only A' in text
    assert 'Unrelated 99' not in text and 'onclick' not in text
