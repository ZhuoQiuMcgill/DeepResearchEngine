"""Custom inline wrappers must not delete linked conditions or reorder text."""
from copy import deepcopy

import pytest
from lxml import html

from deepresearch.engine.toolset.article_extraction import _normalize_inline_components
from tests.toolset.test_html_fidelity import extract


@pytest.mark.parametrize("wrapper", ["reference-source", "lab-evidence", "x-citation"])
@pytest.mark.parametrize("block", ["p", "li", "td", "dd"])
def test_inline_component_preserves_qualifiers_links_and_order(wrapper, block):
    passage = (f'<{block}>The <{wrapper}><a href="trial">measured result</a></{wrapper}>'
               f' was 12, not 24. A <{wrapper}><a href="limits">separate check</a></{wrapper}>'
               f' found no improvement below 0 degrees.</{block}>')
    if block == "li":
        passage = '<ul>' + passage + '</ul>'
    elif block == "td":
        passage = '<table><tr><th>Observed condition</th></tr><tr>' + passage + '</tr></table>'
    elif block == "dd":
        passage = '<dl><dt>Observed condition</dt>' + passage + '</dl>'
    padding = '<p>' + 'Independent observations apply only to the documented configuration. ' * 12 + '</p>'
    text = extract(padding + passage)
    assert 'was 12, not 24.' in text
    assert 'found no improvement below 0 degrees.' in text
    assert 'https://example.test/manual/trial' in text
    assert 'https://example.test/manual/limits' in text
    assert text.index('measured result') < text.index('was 12') < text.index('separate check')


def test_nested_inline_components_keep_original_text_and_attributes():
    tree = html.fromstring('<p>Before <x-outer class="note"><x-inner title="source">'
        '<a href="/trial">trial</a></x-inner> excludes 24 cases.</x-outer> After.</p>')
    original = deepcopy(tree)
    _normalize_inline_components(tree)
    assert tree.text_content() == original.text_content()
    assert tree.xpath('.//span[@class="note"]/span[@title="source"]/a/@href') == ['/trial']
    assert 'x-inner' in html.tostring(original, encoding='unicode')


@pytest.mark.parametrize("markup", [
    '<p><x-panel><table><tr><td>12</td></tr></table></x-panel></p>',
    '<p><x-field role="button">Submit</x-field></p>',
    '<p><code><x-label>literal markup</x-label></code></p>',
    '<div><x-block>Outside a prose block</x-block></div>',
])
def test_structural_semantic_and_literal_components_are_not_reinterpreted(markup):
    tree = html.fromstring(markup)
    before = html.tostring(tree)
    _normalize_inline_components(tree)
    assert html.tostring(tree) == before


def test_hidden_custom_component_and_article_boundary_remain_excluded():
    passage = '<p>' + 'The published observation has a limited scope. ' * 12 + (
        '<x-reference><a href="trial">original trial</a></x-reference> found no benefit. '
        '<x-hidden hidden>WITHHELD DRAFT 999</x-hidden></p>')
    related = '<aside><p>UNRELATED CLAIM 888</p></aside>'
    text = extract('<article>' + passage + '</article>' + related)
    assert 'found no benefit.' in text
    assert 'WITHHELD DRAFT' not in text and 'UNRELATED CLAIM' not in text
