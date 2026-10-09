"""Record-local recovery cannot borrow common fields from another record."""
from lxml import etree, html
import pytest

from deepresearch.engine.toolset.html_records import RecordMatcher
from deepresearch.engine.toolset.html_selection import select_anchored_structure
from deepresearch.engine.toolset.html_structure import _render, _retains_text


def fixtures(*, tag='div', omitted='12 min'):
    rows = [[name, 'Recorded warehouse temperature', '18 degrees', omitted, 'Closed measurement interval',
             'M', 'T', 'W', 'T', 'F', 'S', 'S'] for name in ('Record-A', 'Record-B')]
    block = html.fromstring('<ol>' + ''.join('<' + tag + '>' + ''.join(
        '<span>' + field + '</span>' for field in row) + '</' + tag + '>' for row in rows) + '</ol>')
    units = [field for row in rows for field in [*row[:3], row[4], ''.join(row[5:])]]
    document = etree.fromstring(('<body>' + ''.join('<p>' + field + '</p>' for field in units) + '</body>').encode())
    return block, document


@pytest.mark.parametrize('tag', ['li', 'div'])
def test_whole_record_fields_authorize_missing_field_recovery_without_new_records(tag):
    block, document = fixtures(tag=tag)
    original = etree.tostring(block)
    assert RecordMatcher(document).retains_records(block)
    scope = html.fromstring('<div><ul><li>Unrelated option</li></ul>' + etree.tostring(block, encoding='unicode') + '</div>')
    result, recovered = select_anchored_structure(scope, document, scope.xpath('.//ol|.//ul'))
    assert recovered == 1 and _retains_text(document, result)
    assert result.text_content().count('12 min') == 2
    assert 'Unrelated' not in result.text_content()
    assert etree.tostring(block) == original


@pytest.mark.parametrize('change', ['number', 'case', 'order', 'substring', 'negation', 'missing_record', 'reversed_records'])
def test_changed_fields_or_unselected_records_cannot_authorize_recovery(change):
    block, document = fixtures()
    if change == 'number':
        document[2].text = '19 degrees'
    elif change == 'case':
        document[1].text = 'recorded warehouse temperature'
    elif change == 'order':
        document[1].text, document[2].text = document[2].text, document[1].text
    elif change == 'substring':
        document[0].text += '000'
    elif change == 'negation':
        document[1].text = 'Not ' + document[1].text
    elif change == 'missing_record':
        for node in list(document)[5:]:
            document.remove(node)
    else:
        for node in list(document)[:5]:
            document.append(node)
    assert not RecordMatcher(document).retains_records(block)


def test_repeated_anchor_and_fields_elsewhere_cannot_supply_local_coverage():
    block, document = fixtures()
    document.append(etree.fromstring(b'<p>Record-A</p>'))
    assert not RecordMatcher(document).retains_records(block)
    block, document = fixtures()
    # Keep A's anchor but move all its remaining fields after B. The shared
    # phrases still occur on the page; A cannot borrow them from B's window.
    for node in list(document)[1:5]:
        document.append(node)
    assert not RecordMatcher(document).retains_records(block)


def test_large_unselected_field_and_record_prefix_do_not_establish_coverage():
    block, document = fixtures(omitted='An extensive unselected record field. ' * 20)
    assert not RecordMatcher(document).retains_records(block)
    block, document = fixtures()
    document[3].text = 'Closed'
    assert not RecordMatcher(document).retains_records(block)


@pytest.mark.parametrize('mutation', ['one_record', 'mixed_records', 'container_text', 'record_tail', 'no_list'])
def test_ambiguous_record_shapes_are_not_inferred(mutation):
    block, document = fixtures()
    if mutation == 'one_record':
        block.remove(block[-1])
    elif mutation == 'mixed_records':
        block[-1].tag = 'li'
    elif mutation == 'container_text':
        block.text = 'Unselected context'
    elif mutation == 'record_tail':
        block[0].tail = 'Unselected qualifier'
    else:
        block.tag = 'div'
    assert not RecordMatcher(document).retains_records(block)


@pytest.mark.parametrize('limit,value', [('MAX_RECORDS', 1), ('MAX_SLOTS', 2), ('MAX_CHARS', 20),
    ('MAX_UNITS', 2), ('MAX_DOCUMENT_CHARS', 20), ('MAX_STATES', 1), ('MAX_WORK', 1)])
def test_limits_fail_conservatively(monkeypatch, limit, value):
    from deepresearch.engine.toolset import html_records
    block, document = fixtures()
    monkeypatch.setattr(html_records, limit, value)
    assert not RecordMatcher(document).retains_records(block)


def test_work_budget_is_shared_by_blocks_and_not_reset_between_matches(monkeypatch):
    from deepresearch.engine.toolset import html_records
    block, document = fixtures()
    monkeypatch.setattr(html_records, 'MAX_WORK', 10000)
    matcher = RecordMatcher(document)
    assert matcher.retains_records(block)
    assert not all(matcher.retains_records(block) for _ in range(100))
    assert not matcher.retains_records(block)
    assert RecordMatcher(document).retains_records(block)


@pytest.mark.parametrize('tag', ['ol', 'ul'])
def test_non_li_record_groups_and_nested_lists_survive_rendering(tag):
    source = html.fromstring('<div><' + tag + '><div><span>Record-A</span><ul><li>18 degrees</li>'
        '<li>12 min</li></ul></div><div onclick="track()"><span>Record-B</span>'
        '<ul><li>24 degrees</li><li><a href="https://example.test/conditions">3 min</a></li></ul>'
        '<!-- hidden note --></div></' + tag + '></div>')
    text = _render(source)
    parsed = html.fragment_fromstring(text, create_parent=True)
    records = parsed.xpath('./' + tag + '/div')
    assert len(records) == 2
    assert records[0].xpath('./ul/li/text()') == ['18 degrees', '12 min']
    assert records[1].xpath('./ul/li[1]/text()') == ['24 degrees']
    assert records[1].xpath('./ul/li/a/@href') == ['https://example.test/conditions']
    assert 'onclick' not in text and 'hidden note' not in text
