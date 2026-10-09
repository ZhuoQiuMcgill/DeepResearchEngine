"""Final fidelity diagnostics must describe delivered text, not an earlier tree."""
from copy import deepcopy

import pytest
from lxml import etree, html

from deepresearch.engine.toolset.html_recovery import finalize_diagnostic, diagnostic_schema
from deepresearch.engine.toolset.html_selection import select_anchored_structure, _intact


def _diagnostic(covered=False):
    return {'method': 'dom-prose-overlap/1', 'semantic_verification': False,
        'eligible_blocks': 2, 'eligible_characters': 2400,
        'primary_matched_blocks': 2 if covered else 0, 'primary_matched_characters': 2400 if covered else 0,
        'matched_blocks': 2 if covered else 0, 'matched_characters': 2400 if covered else 0,
        'recovery_attempted': not covered, 'recovery_applied': False, 'substantial_omission': not covered}


def _paragraphs():
    return ['Observation A: ' + 'Use only the recorded conditions and exclude unmeasured intervals. ' * 20,
            'Observation B: ' + 'No improvement was observed below 12 units or above 24 units. ' * 20]


def test_final_restoration_clears_stale_warning_and_retains_intermediate_counts():
    from jsonschema import validate
    a, b = _paragraphs()
    tree = html.document_fromstring('<html><body><article><p>' + a + '</p><p>' + b + '</p></article></body></html>')
    before = _diagnostic()
    after = finalize_diagnostic(tree, a + '\n\n' + b, before)
    assert after['matched_blocks'] == 2 and not after['substantial_omission']
    assert after['intermediate_matched_blocks'] == 0 and after['primary_matched_blocks'] == 0
    assert before == _diagnostic()
    validate(after, diagnostic_schema())
    validate(before, diagnostic_schema())  # Saved /1 descriptors remain accepted.


def test_final_renderer_loss_is_detected_even_when_intermediate_tree_was_complete():
    a, b = _paragraphs()
    tree = html.document_fromstring('<html><body><p>' + a + '</p><p>' + b + '</p></body></html>')
    after = finalize_diagnostic(tree, 'Observation A.\n\nObservation B.', _diagnostic(True))
    assert after['intermediate_matched_blocks'] == 2
    assert after['matched_blocks'] == 0 and after['substantial_omission']


def test_rendered_comparison_handles_inline_markup_tables_literal_html_and_code():
    a = 'Use the documented condition and the linked observation before drawing a conclusion about the measured result.'
    markup = ('<article><p>Use the <a href="https://example.test">documented condition</a> and the '
        'linked observation before drawing a conclusion about the measured result.</p>'
        '<table><tr><td><p>' + a + '</p></td></tr></table>'
        '<dl><dd><p>Recorded literal: ' + a + '</p></dd></dl>'
        '<p>Code text: &lt;p&gt;' + a + '&lt;/p&gt;</p></article>')
    tree = html.document_fromstring('<html><body>' + markup + '</body></html>')
    text = ('Use the [documented condition](https://example.test) and the linked observation before '
        'drawing a conclusion about the measured result.\n\n| Data |\n| --- |\n| ' + a + ' |\n\n'
        '<dl><dd><p>Recorded literal: ' + a + '</p></dd></dl>\n\n'
        'Code text: `<p>' + a + '</p>`')
    after = finalize_diagnostic(tree, text, _diagnostic())
    assert after['matched_blocks'] == 3


def test_source_boundaries_and_case_are_not_relaxed_for_overlap():
    a, b = _paragraphs()
    tree = html.document_fromstring('<html><body><article><p>' + a + '</p><p>' + b + '</p>'
        '<p hidden>Hidden: ' + a + '</p></article><aside><p>Unrelated: ' + b + '</p></aside></body></html>')
    after = finalize_diagnostic(tree, (a + '\n\n' + b).lower(), _diagnostic())
    assert after['eligible_blocks'] == 2 and after['matched_blocks'] == 0


def test_structure_count_includes_subtrees_retained_through_child_text():
    a = 'The first complete paragraph must retain its original list item and ordered relationship.'
    b = 'The second complete paragraph also retains its original independent relationship.'
    scope = html.fromstring('<div><ul><li><p>' + a + '</p></li></ul><ol start="3"><li><p>' + b + '</p></li></ol></div>')
    doc = etree.fromstring(('<body><p>' + a + '</p><p>' + b + '</p></body>').encode())
    projected, count = select_anchored_structure(scope, doc, scope.xpath('./ul|./ol'))
    assert count == 2 and projected is not None
    assert projected.find('ol').get('start') == '3'


@pytest.mark.parametrize('root', ['div', 'section'])
def test_retained_section_prose_can_anchor_a_nested_list_and_its_headings(root):
    a, b = _paragraphs()
    section = ('<section><h2>Recorded scope</h2><div><p>' + a + '</p><p>' + b + '</p></div>'
        '<div><div><h3>Exceptions</h3></div><div><ul><li>Exclude intervals below 12.</li></ul></div></div>'
        '<div><h3>Separate resources</h3><div><a href="/elsewhere">Unselected card text</a></div></div></section>')
    scope = html.fromstring(section if root == 'section' else '<div>' + section + '</div>')
    original = html.tostring(scope)
    doc = etree.fromstring(('<body><p>' + a + '</p><p>' + b + '</p></body>').encode())
    projected, count = select_anchored_structure(scope, doc, scope.xpath('.//ul'))
    assert count == 1
    text = projected.text_content()
    assert text.index('Recorded scope') < text.index(a) < text.index('Exceptions') < text.index('Exclude intervals below 12.')
    assert 'Separate resources' not in text and 'Unselected card text' not in text
    assert html.tostring(scope) == original


@pytest.mark.parametrize('nested', [True, False])
def test_unselected_or_weak_section_cannot_borrow_remote_prose(nested):
    a, b = _paragraphs()
    intro = '<div><p>' + a + '</p><p>' + b + '</p></div>'
    missing = '<p>' + 'Independent omitted observations. ' * 200 + '</p>'
    block = '<ul><li>UNSELECTED CLAIM</li></ul>'
    scope = html.fromstring('<div><section>' + intro +
        ('<section>' + block + '</section>' if nested else missing + block) + '</section></div>')
    doc = etree.fromstring(('<body><p>' + a + '</p><p>' + b + '</p></body>').encode())
    projected, count = select_anchored_structure(scope, doc, scope.xpath('.//ul'))
    assert count == 0 and projected is None


def test_partial_subtree_does_not_count_as_fully_retained():
    original = html.fromstring('<ul><li>Only above 12.</li><li>Not below 0.</li></ul>')
    changed = deepcopy(original)
    changed.remove(changed[1])
    assert not _intact(original, changed)
    for markup in ['<ul><li>Only above 24.</li><li>Not below 0.</li></ul>',
                   '<ol><li>Only above 12.</li><li>Not below 0.</li></ol>']:
        assert not _intact(original, html.fromstring(markup))
    assert not _intact(html.fromstring('<pre>if ready:\n    go()</pre>'), html.fromstring('<pre>if ready: go()</pre>'))
