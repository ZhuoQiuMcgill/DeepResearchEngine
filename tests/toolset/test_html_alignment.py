"""Whole DOM slots explain deletion/concatenation without guessing characters."""
from lxml import etree, html
import pytest

from deepresearch.engine.toolset.html_alignment import DOMSlotMatcher
from deepresearch.engine.toolset.html_structure import _retains_text, recover_structure


@pytest.mark.parametrize("tag", ["li", "td", "dd", "p", "div"])
def test_original_fields_explain_merged_tokens_and_restore_omitted_slots(tag):
    source = html.fromstring(f'<{tag}><span>Range: 12–24</span><span>12</span>'
                            f'<span>24</span><span>3 samples</span></{tag}>')
    before = etree.tostring(source)
    primary = etree.fromstring(b'<body><p>Range: 12\xe2\x80\x93243 samples</p></body>')
    assert DOMSlotMatcher(source).retains('Range: 12–243 samples')
    assert _retains_text(primary, source)
    assert etree.tostring(source) == before


@pytest.mark.parametrize("text", ["Range: 12–253 samples", "range: 12–243 samples",
                                  "Range: 12–243 sample", "3 samplesRange: 12–24",
                                  "Range: 12–243 not samples"])
def test_changed_numbers_case_negation_order_and_partial_slots_cannot_match(text):
    source = html.fromstring('<p><span>Range: 12–24</span><span>omitted</span><span>3 samples</span></p>')
    assert not DOMSlotMatcher(source).retains(text)


@pytest.mark.parametrize("body", [
    '<p>Alpha</p><p>Beta</p>',
    '<ul><li>Alpha</li><li>Beta</li></ul>',
    '<ul><li>Alpha<ul><li>Beta</li></ul></li></ul>',
    '<table><tr><td>Alpha</td><td>Beta</td></tr></table>',
    '<div>Alpha<div>Beta</div></div>',
    '<pre><span>Alpha</span><i>deleted</i><span>Beta</span></pre>',
    '<code><p><span>Alpha</span><i>deleted</i><span>Beta</span></p></code>',
])
def test_no_borrowing_from_separate_blocks_or_literal_code(body):
    assert not DOMSlotMatcher(html.fromstring('<main>'+body+'</main>')).retains('AlphaBeta')


def test_div_with_inline_slots_preserves_original_link_and_following_condition():
    source = html.fromstring('<main><div>Click the <b>control</b> to select dates. '
        'Then <b>apply</b> only if valid.</div><ul><li>Range: <span>12–24</span>'
        '<span>12</span><span>24</span><span>3 samples</span></li></ul></main>')
    primary = etree.fromstring(b'<body><p>Click the Then </p><list><item>Range: 12\xe2\x80\x93243 samples</item></list></body>')
    # Whole slots cannot explain a partial sentence atom, even if its words occur.
    assert not DOMSlotMatcher(source).retains('Click the Then ')
    primary.find('p').text = 'Click the  only if valid.'
    assert _retains_text(primary, source)
    # Retained prose anchors this authored main; this test does not authorize
    # whole-page recovery for an otherwise ambiguous navigation-only document.
    intro = 'These measured samples apply only under the original documented conditions and the stated sampling interval.'
    for node in (source, primary):
        paragraph = etree.Element('p')
        paragraph.text = intro
        node.insert(0, paragraph)
    class Document:
        body = primary
    tree = html.fromstring('<html><body>' + etree.tostring(source, encoding='unicode') + '</body></html>')
    result, diagnostic = recover_structure(tree, Document(), 'Click the  only if valid.\nRange: 12–243 samples')
    assert diagnostic['recovery_applied'] and not diagnostic['unresolved']
    assert '**control** to select dates. Then **apply** only if valid.' in result
    assert '12–24' in result and '3 samples' in result


def test_work_budget_is_shared_across_units_and_exhaustion_rejects(monkeypatch):
    from deepresearch.engine.toolset import html_alignment as module
    monkeypatch.setattr(module, 'MAX_WORK', 300)
    source = html.fromstring('<p><span>Alpha</span><i>omitted</i><span>Beta</span></p>')
    matcher = DOMSlotMatcher(source)
    assert matcher.retains('AlphaBeta')
    outcomes = [matcher.retains('AlphaBeta') for _ in range(30)]
    assert False in outcomes and outcomes[-1] is False
    assert DOMSlotMatcher(source).retains('AlphaBeta')


def test_slot_state_and_unit_limits_fail_conservatively(monkeypatch):
    from deepresearch.engine.toolset import html_alignment as module
    source = html.fromstring('<p><span>A</span><i>omitted</i><span>B</span></p>')
    monkeypatch.setattr(module, 'MAX_SLOTS', 2)
    assert not DOMSlotMatcher(source).retains('AB')
    monkeypatch.setattr(module, 'MAX_SLOTS', 10)
    monkeypatch.setattr(module, 'MAX_STATES', 1)
    assert not DOMSlotMatcher(source).retains('AB')
    monkeypatch.setattr(module, 'MAX_UNIT', 1)
    assert not DOMSlotMatcher(source).retains('AB')
