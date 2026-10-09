"""Selected graphic labels survive without inventing graphical meaning."""
from jsonschema import validate
from lxml import html
from markdown_it import MarkdownIt
import pytest

from deepresearch.engine.toolset.article_extraction import extract_source
from deepresearch.engine.toolset.common import LIMITS, digest
from deepresearch.engine.toolset.html_graphics import project_selected_graphics, diagnostic_schema
from deepresearch.engine.toolset.html_recovery import diagnostic_schema as html_schema
from tests.toolset.test_fetch_v2 import info
from tests.toolset.test_html_structure import PROSE

PATH = '<path d="M1 1 L9 9 M9 1 L1 9"/>'


def extract(value, *, container='main', header=True, outside=''):
    head = '<tr><th>Condition</th><th>Observation</th></tr>' if header else ''
    raw = ('<html><body><' + container + '>' + PROSE + '<table>' + head +
           '<tr><td>Condition A</td><td>' + value + '</td></tr></table></' + container + '>' +
           outside + '</body></html>').encode()
    result = extract_source(raw, info(raw), LIMITS)
    assert result['original'] == raw
    assert result['provenance']['original_sha256'] == digest(raw)
    assert result['provenance']['text_sha256'] == digest(result['text'])
    validate(result['provenance']['html_extraction'], html_schema())
    rendered = html.fragment_fromstring(MarkdownIt('commonmark').enable('table').render(
        result['text'].decode()), create_parent='div')
    return result, rendered


@pytest.mark.parametrize('header', [True, False])
@pytest.mark.parametrize('container', ['main', 'article', 'div'])
@pytest.mark.parametrize('svg, expected, origin', [
    ('<svg aria-label="Not recorded">' + PATH + '</svg>', 'Not recorded', 'aria-label'),
    ('<svg><title>Not observed</title>' + PATH + '</svg>', 'Not observed', 'svg-title'),
    ('<svg title="Check manually">' + PATH + '</svg>', 'Check manually', 'title-attribute'),
    ('<svg><desc>Measurement unavailable</desc>' + PATH + '</svg>', 'Measurement unavailable', 'svg-desc'),
])
def test_explicit_label_is_authored_text_in_the_original_cell(svg, expected, origin, container, header):
    result, rendered = extract('Before ' + svg + ' after', container=container, header=header)
    assert [n.text_content() for n in rendered.xpath('.//tr[last()]/td')] == ['Condition A', 'Before ' + expected + ' after']
    assert not rendered.xpath('.//svg|.//path')
    assert 'data-deepresearch' not in result['text'].decode()
    graphic = result['provenance']['html_extraction']['graphics']
    assert graphic['selection_bound'] and graphic['coverage_complete']
    assert graphic['selected_svg_count'] == graphic['labelled_svg_count'] == 1
    assert graphic['unresolved_svg_count'] == 0
    assert graphic['entries'][0]['label_origins'] == [origin]


@pytest.mark.parametrize('attrs, reason', [
    ('', 'no_explicit_label'),
    ('data-icon="check" alt="Yes"', 'no_explicit_label'),
    ('aria-hidden="true" aria-label="Yes"', 'author_hidden'),
    ('role="presentation" aria-label="Yes"', 'author_presentational'),
    ('aria-labelledby="absent" aria-label="Yes"', 'missing_ambiguous_or_outside_reference'),
])
def test_unlabelled_or_ineligible_geometry_stays_unknown(attrs, reason):
    result, rendered = extract('<svg ' + attrs + '>' + PATH + '</svg>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == ''
    assert result['provenance']['parser_warning_count'] >= 1
    graphic = result['provenance']['html_extraction']['graphics']
    assert graphic['unresolved_svg_count'] == 1 and graphic['labelled_svg_count'] == 0
    assert graphic['entries'][0]['reason'] == reason
    assert not any(word in result['text'].decode() for word in ('Yes', 'meaning unresolved', 'SVG graphic'))


def test_same_geometry_different_declared_labels_keeps_both_and_no_boolean_translation():
    result, rendered = extract('<svg aria-label="check">' + PATH + '</svg> / <svg aria-label="Not observed">' + PATH + '</svg>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == 'check / Not observed'
    assert result['provenance']['html_extraction']['graphics']['labelled_svg_count'] == 2


def test_label_is_escaped_literal_text_not_new_markup_or_a_link():
    result, rendered = extract('<svg aria-label="&lt;script&gt;literal&lt;/script&gt; | [x](javascript:bad)">' + PATH + '</svg>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == '<script>literal</script> | [x](javascript:bad)'
    assert not rendered.xpath('.//script|.//a')


@pytest.mark.parametrize('value, reason', [
    ('<svg aria-label="Observed"><title>Not observed</title>' + PATH + '</svg>', 'conflicting_source_labels'),
    ('<svg aria-label="' + 'x'*257 + '">' + PATH + '</svg>', 'invalid_or_oversize_label'),
    ('<svg aria-label="Observed"><text>Not observed</text></svg>', 'outside_inline_nontext_subset'),
    ('<svg aria-labelledby="dup"/><span id="dup">One</span><span id="dup">Two</span>', 'missing_ambiguous_or_outside_reference'),
    ('<svg aria-labelledby="bad"/><span id="bad"><a href="/elsewhere">Observed</a></span>', 'unsupported_label_subtree'),
    ('<svg aria-label="Observed">Unclassified words' + PATH + '</svg>', 'unclassified_svg_text'),
])
def test_conflicting_unsupported_and_oversize_labels_do_not_become_values(value, reason):
    result, rendered = extract(value)
    diagnostic = result['provenance']['html_extraction']['graphics']
    assert diagnostic['labelled_svg_count'] == 0
    assert diagnostic['entries'][0]['reason'] == reason


def test_local_id_reference_is_bounded_and_keeps_original_duplicate_text():
    result, rendered = extract('<span id="name">Not recorded</span> / <svg aria-labelledby="name">' + PATH + '</svg>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == 'Not recorded / Not recorded'
    assert result['provenance']['html_extraction']['graphics']['entries'][0]['label_origins'] == ['aria-labelledby']
    _, rendered = extract('<svg aria-label="Observed"><title>Observed</title><desc>Observed</desc>' + PATH + '</svg>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == 'Observed Observed'
    _, rendered = extract('<svg aria-label="Observed"><desc>Under the recorded conditions.</desc><title>Observed</title>' + PATH + '</svg>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == 'Under the recorded conditions. Observed'


def test_svg_links_are_outside_the_passive_label_projection_subset():
    result, _ = extract('<svg aria-label="Observed"><a href="https://example.test/original">' + PATH + '</a></svg>')
    assert result['provenance']['html_extraction']['graphics']['entries'][0]['reason'] == 'outside_inline_nontext_subset'


def test_long_selected_dom_path_is_unknown_rather_than_a_false_truncated_locator():
    tree = html.fromstring('<table><tr><td>' + '<div>'*100 + '<svg aria-label="Observed"/>' + '</div>'*100 + '</td></tr></table>')
    _, diagnostic = project_selected_graphics(tree)
    assert diagnostic['entries'][0]['selected_dom_path'] is None
    validate(diagnostic, diagnostic_schema())


def test_ancestor_hidden_status_is_not_undone_by_child_false():
    result, rendered = extract('<span aria-hidden="true"><svg aria-hidden="false" aria-label="Observed">' + PATH + '</svg></span>')
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == ''
    assert result['provenance']['html_extraction']['graphics']['author_hidden_svg_count'] == 1


def test_external_and_unselected_labels_are_not_imported_or_audited_as_selected():
    outside = '<nav><svg aria-label="NAVIGATION"/></nav><aside><span id="outside">UNSELECTED</span><svg/></aside>'
    result, _ = extract('<svg aria-labelledby="outside"/>', outside=outside)
    assert 'NAVIGATION' not in result['text'].decode() and 'UNSELECTED' not in result['text'].decode()
    assert result['provenance']['html_extraction']['graphics']['selected_svg_count'] == 1


@pytest.mark.parametrize('outside', [
    '<aside><span id="name">Unselected</span></aside>',
    '<span id="name" hidden>Hidden</span>',
    '<nav><span id="name">Navigation</span></nav>',
])
def test_document_wide_duplicate_id_cannot_be_mistaken_for_a_unique_local_label(outside):
    result, rendered = extract('<span id="name">Selected</span> / <svg aria-labelledby="name"/>', outside=outside)
    assert rendered.xpath('.//tr[last()]/td')[1].text_content() == 'Selected / '
    assert result['provenance']['html_extraction']['graphics']['labelled_svg_count'] == 0
    assert result['provenance']['html_extraction']['graphics']['entries'][0]['reason'] == 'missing_ambiguous_or_outside_reference'


def test_document_id_scan_overflow_cannot_authorize_a_label_reference():
    tree = html.document_fromstring('<html><body><table><tr><td><span id="name">Selected</span><svg aria-labelledby="name"/></td></tr></table>' + '<span/>'*20001 + '</body></html>')
    _, diagnostic = project_selected_graphics(tree.find('.//table'), source_tree=tree)
    assert diagnostic['labelled_svg_count'] == 0
    assert diagnostic['entries'][0]['reason'] == 'unverified_document_id_uniqueness'


def test_projection_has_work_and_metadata_bounds_and_does_not_mutate_input():
    for count in [33, 129]:
        tree = html.fromstring('<table><tr><td>' + ('<svg aria-label="Observed">'+PATH+'</svg>')*count + '</td></tr></table>')
        saved = html.tostring(tree)
        projected, diagnostic = project_selected_graphics(tree)
        assert html.tostring(tree) == saved
        assert len(diagnostic['entries']) <= 32 and diagnostic['entries_truncated']
        assert diagnostic['coverage_complete'] is (count <= 128)
        validate(diagnostic, diagnostic_schema())
    crowded = html.fromstring('<table><tr><td><svg/>' + '<span/>'*20001 + '</td></tr></table>')
    projected, diagnostic = project_selected_graphics(crowded)
    assert projected is crowded and not diagnostic['coverage_complete']


def test_unbound_non_table_graphic_is_not_claimed_as_selected_evidence():
    raw = ('<html><body><main>' + PROSE + '<p><svg aria-label="Outside subset">' + PATH + '</svg></p></main></body></html>').encode()
    result = extract_source(raw, info(raw), LIMITS)
    diagnostic = result['provenance']['html_extraction']['graphics']
    assert not diagnostic['selection_bound'] and not diagnostic['coverage_complete']
    assert diagnostic['selected_svg_count'] == 0 and diagnostic['unassessed_candidate_count'] == 1
