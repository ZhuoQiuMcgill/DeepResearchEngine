"""Recover authored prose without importing unrelated page branches."""
from lxml import html
import pytest

from deepresearch.engine.toolset.html_recovery import finalize_diagnostic, recover_rendered_prose

KEPT = 'Recorded measurements retain their original source, sample identifier and stated observation time. ' * 4
MISSING = 'These observations apply only above the stated threshold, exclude invalid samples and do not establish a general effect. ' * 8
OTHER = 'The alternate measurement uses a different preparation method and must not be pooled with the first group. ' * 8


def fixture(tag='main', extra=''):
    body = f'<{tag}><h1>Original observations</h1><p>{KEPT}</p><div><h2>Limitations</h2><p>{MISSING}</p></div><p>{OTHER}</p>{extra}</{tag}>'
    tree = html.document_fromstring('<html><body>'+body+'<aside><p>Unrelated recommendation. '+OTHER+'</p></aside></body></html>')
    diagnostic = {'method': 'dom-prose-overlap/1', 'semantic_verification': False,
        'eligible_blocks': 3, 'eligible_characters': 1, 'primary_matched_blocks': 1,
        'primary_matched_characters': len(KEPT), 'matched_blocks': 1,
        'matched_characters': len(KEPT), 'recovery_attempted': True,
        'recovery_applied': False, 'substantial_omission': True}
    return tree, finalize_diagnostic(tree, KEPT, diagnostic)


@pytest.mark.parametrize('tag', ['main', 'article'])
def test_original_paragraphs_and_headings_return_with_final_diagnostics(tag):
    tree, before = fixture(tag)
    original = html.tostring(tree)
    text, flags = recover_rendered_prose(tree, KEPT, before)
    assert MISSING.strip() in text and OTHER.strip() in text and KEPT.strip() in text
    assert '## Limitations' in text and 'Unrelated recommendation' not in text
    after = finalize_diagnostic(tree, text, flags)
    assert after['matched_blocks'] == 3 and not after['substantial_omission']
    assert after['intermediate_matched_blocks'] == before['intermediate_matched_blocks'] == 1
    assert flags['prose_render_recovery_applied'] and html.tostring(tree) == original


def test_unselected_nested_article_and_link_cards_are_not_imported():
    # Multiple nested articles make main the outer visible scope. They remain
    # independent documents; a selected paragraph cannot authorize their prose.
    extra = '<article><p>Separate article A. '+OTHER+'</p></article><article><p>Separate article B. '+OTHER+'</p></article>'
    extra += '<div><a href="https://example.test/other">Unrelated link card</a></div>'
    tree, before = fixture(extra=extra)
    text, flags = recover_rendered_prose(tree, KEPT, before)
    assert flags['prose_render_recovery_applied']
    assert MISSING.strip() in text and 'Separate article' not in text and 'Unrelated link card' not in text


def test_unmarked_body_and_ambiguous_multiple_mains_do_not_authorize_expansion():
    tree, before = fixture('div')
    assert recover_rendered_prose(tree, KEPT, before)[0] == KEPT
    tree, before = fixture()
    tree.find('body').append(html.fromstring('<main><p>Second document.</p></main>'))
    assert recover_rendered_prose(tree, KEPT, before)[0] == KEPT


def test_missing_prior_text_never_trades_for_a_longer_document():
    tree, before = fixture()
    text = KEPT + '\n\nAnother retained condition not present in this source scope.'
    candidate, flags = recover_rendered_prose(tree, text, before)
    assert candidate == text and not flags['prose_render_recovery_applied']


@pytest.mark.parametrize('broken', ['text', 'destination', 'code'])
def test_final_renderer_must_preserve_existing_text_destinations_and_code(monkeypatch, broken):
    from deepresearch.engine.toolset import html_structure
    extra = '<p>Read <a href="https://example.test/original">the source</a> before using <code>literal * value</code>.</p>'
    primary = KEPT+'\n\nRead [the source](https://example.test/original) before using `literal * value`.'
    tree, before = fixture(extra=extra)
    original = html_structure._render
    def render(scope, **kwargs):
        value = original(scope, **kwargs)
        if broken == 'text':return value.replace('Recorded measurements', 'Changed measurements')
        if broken == 'destination':return value.replace('https://example.test/original', 'https://example.test/changed')
        return value.replace('`literal * value`', 'literal * value')
    monkeypatch.setattr(html_structure, '_render', render)
    candidate, flags = recover_rendered_prose(tree, primary, before)
    assert candidate == primary and not flags['prose_render_recovery_applied']


def test_fetch_pipeline_applies_final_recovery_before_index_and_size_check(monkeypatch):
    from deepresearch.engine.toolset import article_extraction
    from deepresearch.engine.toolset.common import LIMITS, ToolFault
    from tests.toolset.test_fetch_v2 import info
    tree, before = fixture()
    raw = html.tostring(tree)
    before['structure'] = {'method': 'dom-structure-check/1', 'semantic_verification': False,
        'checked_blocks': 0, 'damaged_blocks': 0, 'recovery_applied': False,
        'unresolved': False, 'decision': 'no_damage_detected'}
    monkeypatch.setattr(article_extraction, '_structured_markdown', lambda *args: (KEPT, before))
    result = article_extraction.extract_source(raw, info(raw), LIMITS)
    assert result['original'] == raw and MISSING.strip().encode() in result['text']
    assert not result['provenance']['html_extraction']['substantial_omission']
    with pytest.raises(ToolFault, match='exceeds limit'):
        article_extraction.extract_source(raw, info(raw), {**LIMITS, 'text_bytes': len(KEPT.encode())+1})
