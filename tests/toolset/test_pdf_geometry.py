"""Coordinate confirmation is bounded, font-local, baseline-local and atomic."""
import pytest

from deepresearch.engine.toolset.pdf_geometry import GEOMETRY_LIMIT, confirm_spaces
from deepresearch.engine.toolset.pdf_spacing import PdfSpacingReader, spacing_agreement
from deepresearch.engine.toolset.pdf_extraction import recover_page_text
from tests.toolset.test_pdf_spacing import fake_reader


def drawing(words, *, gaps=None):
    x = 0
    chars = []
    for index, word in enumerate(words):
        if index:
            x += .5 if gaps is None else gaps[index - 1]
        for char in word:
            chars.append({'c': char, 'origin': (x, 10), 'bbox': (x, 1, x + 1, 12)})
            x += 1
    return {'blocks': [{'type': 0, 'lines': [{'dir': (1, 0),
        'spans': [{'font': 'ExampleFont', 'size': 10, 'chars': chars}]}]}]}


def test_narrow_observed_gaps_calibrate_one_missed_gap_on_same_baseline():
    words = ['red', 'blue', 'green', 'gold', 'tan']
    native = ''.join(words)
    flags, _ = spacing_agreement(native, 'red blue green goldtan')
    physical = confirm_spaces(native, flags, drawing(words))
    assert physical.count(8) == 4 and flags.count(8) == 0
    result, inserted, removed, _ = recover_page_text('r e dbluegreengoldtan', native, 1000, lambda: physical)
    assert result == 'red blue green gold tan' and inserted == 4 and removed == 2


def test_geometry_does_not_infer_from_fewer_than_three_observed_spaces():
    words = ['red', 'blue', 'green', 'gold']
    native = ''.join(words)
    flags, _ = spacing_agreement(native, 'red blue greengold')
    physical = confirm_spaces(native, flags, drawing(words))
    assert physical.count(8) == 2
    assert physical[native.index('gold')] == 1


def test_different_physical_gap_is_not_a_word_boundary():
    words = ['red', 'blue', 'green', 'gold', 'tan']
    native = ''.join(words)
    flags, _ = spacing_agreement(native, 'red blue green goldtan')
    physical = confirm_spaces(native, flags, drawing(words, gaps=[.5, .5, .5, .1]))
    assert physical.count(8) == 3 and physical[native.index('tan')] == 1


@pytest.mark.parametrize('change', ['font', 'size', 'baseline', 'rotation'])
def test_no_inference_across_font_size_baseline_or_orientation(change):
    words = ['red', 'blue', 'green', 'gold', 'tan']
    native = ''.join(words);flags, _ = spacing_agreement(native, 'red blue green goldtan')
    raw = drawing(words);line = raw['blocks'][0]['lines'][0];span = line['spans'][0]
    if change == 'rotation':
        line['dir'] = (0, 1)
    elif change == 'baseline':
        for glyph in span['chars'][-3:]:
            glyph['origin'] = (glyph['origin'][0], 10.1)
    else:
        second = {**span, 'chars': span['chars'][-3:]};span['chars'] = span['chars'][:-3]
        second[change] = 'DifferentFont' if change == 'font' else 11
        line['spans'].append(second)
    physical = confirm_spaces(native, flags, raw)
    assert physical[native.index('tan')] == 1


@pytest.mark.parametrize('word',['ﬁrst','bold'])
def test_secondary_space_at_font_transition_requires_same_line_calibration(word):
    words=['red','blue','green','gold',word]
    native=''.join(words);flags,_=spacing_agreement(native,' '.join(words))
    raw=drawing(words);line=raw['blocks'][0]['lines'][0];span=line['spans'][0]
    count=len(word);other={**span,'font':'UnrelatedFontName','chars':span['chars'][-count:]}
    span['chars']=span['chars'][:-count];line['spans'].append(other)
    index=native.index(word);assert flags[index]==4
    physical=confirm_spaces(native,flags,raw)
    assert physical[index]==8


@pytest.mark.parametrize('change',['few_anchors','different_gap','size','baseline','unobserved'])
def test_font_transition_does_not_infer_space_without_matching_independent_evidence(change):
    words=['red','blue','green','gold','ﬁrst'];native=''.join(words)
    secondary='red bluegreengold ﬁrst' if change=='few_anchors' else 'red blue green gold ﬁrst'
    if change=='unobserved':secondary='red blue green goldﬁrst'
    flags,_=spacing_agreement(native,secondary)
    raw=drawing(words,gaps=[.5,.5,.5,.2 if change=='different_gap' else .5])
    line=raw['blocks'][0]['lines'][0];span=line['spans'][0]
    other={**span,'font':'SupplementFont','chars':span['chars'][-4:]};span['chars']=span['chars'][:-4]
    if change=='size':other['size']=9
    if change=='baseline':
        for g in other['chars']:g['origin']=(g['origin'][0],10.1)
    line['spans'].append(other)
    assert confirm_spaces(native,flags,raw)[native.index('ﬁrst')]!=8


def test_late_geometry_character_disagreement_discards_earlier_confirmation():
    native = 'abcde';flags, _ = spacing_agreement(native, 'a b c d e');raw = drawing(list(native))
    raw['blocks'][0]['lines'][0]['spans'][0]['chars'][-1]['c'] = 'X'
    assert confirm_spaces(native, flags, raw) is None
    assert confirm_spaces(native + 'z', flags + b'\0', drawing(list(native))) is None


def test_physical_spaces_cannot_override_a_changed_or_unknown_text_position():
    flags, _ = spacing_agreement('abcde', 'a b\x02 d e')
    physical = confirm_spaces('abcde', flags, drawing(list('abcde')))
    assert physical[2] == physical[3] == 0


@pytest.mark.parametrize('gap', [0, -.1, float('nan'), float('inf')], ids=['zero', 'overlap', 'nan', 'infinite'])
def test_nonpositive_or_nonfinite_gap_cannot_confirm_a_space(gap):
    flags, _ = spacing_agreement('ab', 'a b')
    physical = confirm_spaces('ab', flags, drawing(['a', 'b'], gaps=[gap]))
    assert physical[1] == 4


def test_reader_records_geometry_and_closes_resources(monkeypatch):
    state = fake_reader(monkeypatch, text='a b c d e')
    reader = PdfSpacingReader(b'pdf', 1)
    flags = reader.compare(0, 'abcde', 100, lambda: drawing(list('abcde')))
    reader.close()
    assert flags.count(8) == reader.diagnostic['geometry_spaces'] == 4
    assert reader.diagnostic['geometry_pages'] == 1 and state['doc_closed'] == 1


def test_large_geometry_is_not_allocated_and_existing_evidence_survives(monkeypatch):
    native = 'a' * GEOMETRY_LIMIT + 'b'
    fake_reader(monkeypatch, text=native[:-1] + ' b')
    def forbidden(): raise AssertionError('oversized dictionary requested')
    reader = PdfSpacingReader(b'pdf', 1)
    flags = reader.compare(0, native, len(native) + 1, forbidden)
    reader.close()
    assert flags[-1] == 4 and 8 not in flags
    assert reader.diagnostic['geometry_failures']['text_limit'] == 1


def test_geometry_failure_keeps_joint_reader_evidence(monkeypatch):
    fake_reader(monkeypatch, text='red, blue green')
    reader = PdfSpacingReader(b'pdf', 1)
    flags = reader.compare(0, 'red, bluegreen', 100, lambda: {'blocks': []})
    reader.close()
    assert flags[5] == 2 and flags[9] == 4 and 8 not in flags
    assert reader.diagnostic['geometry_failures']['content_disagreement'] == 1


@pytest.mark.parametrize('old,native', [('word -based', 'word-based'), ('step- by-step', 'step-by-step'), ('e- mail', 'e-mail')])
def test_hyphen_spacing_needs_both_readers_and_tight_glyphs(old, native):
    flags, _ = spacing_agreement(native, native)
    assert recover_page_text(old, native, 1000, lambda: flags)[0] == old
    physical = confirm_spaces(native, flags, drawing([native]))
    assert recover_page_text(old, native, 1000, lambda: physical)[0] == native


@pytest.mark.parametrize('native', ['12-34', 'ID_word-wrap', 'word-wrap2', 'two--words', 'left−right'])
def test_hyphen_geometry_does_not_repair_numeric_identifier_or_other_dash(native):
    flags, _ = spacing_agreement(native, native)
    physical = confirm_spaces(native, flags, drawing([native]))
    assert 16 not in physical


@pytest.mark.parametrize('change', ['gap', 'font', 'size', 'baseline', 'direction', 'disagreement', 'nan'])
def test_hyphen_confirmation_rejects_ambiguous_geometry_and_reader_disagreement(change):
    native = 'word-based';raw = drawing(['word-', 'based'], gaps=[1 if change == 'gap' else 0])
    line = raw['blocks'][0]['lines'][0];span = line['spans'][0]
    if change in {'font', 'size'}:
        second = {**span, 'chars': span['chars'][5:]};span['chars'] = span['chars'][:5]
        second[change] = 'other' if change == 'font' else 11
        line['spans'].append(second)
    if change in {'baseline', 'nan'}:
        glyph = span['chars'][5];x,y = glyph['origin'];glyph['origin'] = (float('nan'),y) if change == 'nan' else (x,y+1)
    if change == 'direction': line['dir'] = (0,1)
    flags, _ = spacing_agreement(native, 'word- based' if change == 'disagreement' else native)
    physical = confirm_spaces(native, flags, raw)
    assert physical[5] != 16
    assert recover_page_text('word- based', native, 1000, lambda: physical)[0] == 'word- based'
