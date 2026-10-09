"""PDF recovery keeps source characters, page identity and bounded diagnostics."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pymupdf
import pytest
from jsonschema import Draft202012Validator
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from deepresearch.engine.toolset.common import LIMITS, ToolFault, digest
from deepresearch.engine.toolset.pdf_extraction import VERSION, diagnostic_schema, extract_pages, preservation, recover_page_text
from deepresearch.engine.toolset.pdf_spacing import spacing_agreement
from deepresearch.engine.toolset.retrieval import extract
from tests.toolset.test_protocol import pdf_fixture


def positioned_pdf():
    """An oversized declared space glyph, with independently positioned words."""
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    native_font = pymupdf.Font('helv')
    widths = [NumberObject(600 if c == 32 else round(1000 * native_font.glyph_advance(c)))
              for c in range(32, 127)]
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica'),
        NameObject('/FirstChar'): NumberObject(32), NameObject('/LastChar'): NumberObject(126),
        NameObject('/Widths'): ArrayObject(widths)})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
        DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 700 Td [(Observed)-180(difference:)-180(20)-180(mg.)] TJ ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    body = io.BytesIO()
    writer.write(body)
    return body.getvalue()


def test_actual_positioned_words_recover_without_changing_legacy_or_original():
    body = positioned_pdf()
    legacy = extract(body, {'content_type': 'application/pdf'})
    recovered = extract(body, {'content_type': 'application/pdf'}, recover_pdf=True)
    assert legacy['text'] == b'Observeddifference:20mg.'
    assert legacy['extraction_version'] == 'pypdf/6.19.0'
    assert 'pdf_extraction' not in legacy['provenance']
    assert recovered['text'] == b'Observed difference: 20 mg.\n'
    assert recovered['original'] == legacy['original'] == body
    assert recovered['provenance']['original_sha256'] == digest(body)
    assert recovered['extraction_version'] == VERSION
    diagnostic = recovered['provenance']['pdf_extraction']
    assert diagnostic['native_pages'] == diagnostic['changed_pages'] == 1
    assert diagnostic['fallback_pages'] == diagnostic['decoded_control_glyphs'] == 0
    Draft202012Validator(diagnostic_schema()).validate(diagnostic)
    assert list(Draft202012Validator(diagnostic_schema()).iter_errors(diagnostic | {'guaranteed_correct': True}))


@pytest.mark.parametrize('old,new,reason', [
    ('Oneword.', 'One word.\n', None),
    ('Dose20mg.', 'Dose 20 mg.', None),
    ('20 mg.', '2 mg.', 'content_disagreement'),
    ('20 mg.', '20 mcg.', 'content_disagreement'),
    ('Not effective.', 'Effective.', 'content_disagreement'),
    ('May help.', 'may help.', 'content_disagreement'),
    ('ab', 'ba', 'content_disagreement'),
    ('20', '2 0', 'content_disagreement'),
    ('20 mg', '20mg', 'spacing_loss'),
    ('left  right', 'left right', 'spacing_loss'),
    ('    code', 'code', 'spacing_loss'),
    ('a\n    b', 'a\nb', 'spacing_loss'),
    ('a\n\tb', 'a\n b', 'spacing_loss'),
    ('a\n\nb', 'a\nb', 'spacing_loss'),
    ('a\nb', 'a b', 'spacing_loss'),
    ('\x81', '\x82', 'content_disagreement'),
    ('', '', None),
    ('x', '', 'content_disagreement'),
    ('', 'x', 'content_disagreement'),
])
def test_preservation_rejects_changed_facts_order_boundaries_and_indentation(old, new, reason):
    assert preservation(old, new) == (reason, 0)


def test_undecoded_control_replacement_is_counted_not_called_semantic_verification():
    assert preservation('A\x81B', 'A≥B') == (None, 1)
    assert preservation('A\x81B', 'A≥≥B') == ('content_disagreement', 0)


def native_document(monkeypatch, page_texts, *, count=None):
    calls = []
    class Document:
        page_count = len(page_texts) if count is None else count
        closed = False
        def __getitem__(self, number):
            def get_text(kind, *, sort):
                calls.append((number, kind, sort))
                if isinstance(page_texts[number], Exception):
                    raise page_texts[number]
                return page_texts[number]
            return SimpleNamespace(get_text=get_text)
        def close(self):
            self.closed = True
    document = Document()
    monkeypatch.setattr(pymupdf, 'open', lambda **kwargs: document)
    return document, calls


def test_native_failure_and_disagreement_fall_back_per_physical_page(monkeypatch):
    body = pdf_fixture(['kept', '20 mg', 'third', None])
    document, calls = native_document(monkeypatch, ['kept\n', '2 mg', RuntimeError('page fault'), ''])
    result = extract(body, {'content_type': 'application/pdf'}, recover_pdf=True)
    diagnostic = result['provenance']['pdf_extraction']
    assert diagnostic['native_pages'] == diagnostic['fallback_pages'] == 2
    assert diagnostic['fallback_reasons']['content_disagreement'] == 1
    assert diagnostic['fallback_reasons']['page_error'] == 1
    assert result['text'] == b'kept\n\n20 mg\nthird\n'
    assert calls == [(n, 'text', False) for n in range(4)] and document.closed
    index = json.loads(result['index'])
    pages = index['pages']
    assert len(pages) == 4 and pages[-1]['start_byte'] == pages[-1]['end_byte']
    assert [result['text'][p['start_byte']:p['end_byte']] for p in pages] == [b'kept\n', b'20 mg', b'third', b'']
    assert index['text_sha256'] == digest(result['text'])


@pytest.mark.parametrize('failure', ['open', 'count'])
def test_native_unavailable_preserves_whole_legacy_document(monkeypatch, failure):
    body = pdf_fixture(['first', None, 'last'])
    document = None
    if failure == 'open':
        def unavailable(**kwargs):
            raise RuntimeError('native open failed')
        monkeypatch.setattr(pymupdf, 'open', unavailable)
    else:
        document, _ = native_document(monkeypatch, ['unexpected'], count=1)
    old = extract(body, {'content_type': 'application/pdf'})
    new = extract(body, {'content_type': 'application/pdf'}, recover_pdf=True)
    assert old['text'] == new['text'] and old['index'] == new['index']
    diagnostic = new['provenance']['pdf_extraction']
    assert diagnostic['fallback_pages'] == 3 and diagnostic['native_pages'] == 0
    reason = 'reader_unavailable' if failure == 'open' else 'page_count_disagreement'
    assert diagnostic['fallback_reasons'][reason] == 3
    assert document is None or document.closed


@pytest.mark.parametrize('body,limits,code', [
    (pdf_fixture(['secret'], encrypted=True), {}, 'PDF_ENCRYPTED'),
    (pdf_fixture([None]), {}, 'PDF_NO_TEXT'),
    (pdf_fixture(['one', 'two']), {'pdf_pages': 1}, 'PDF_PAGE_LIMIT'),
    (pdf_fixture(['x' * 10000]), {'text_bytes': 1024}, 'TEXT_LIMIT'),
    (b'%PDF-invalid', {}, 'PDF_INVALID'),
])
def test_native_cannot_bypass_pdf_admission_or_limits(body, limits, code):
    with pytest.raises(ToolFault) as caught:
        extract(body, {'content_type': 'application/pdf'}, limits, recover_pdf=True)
    assert caught.value.code == code


def test_native_growth_obeys_total_byte_cap_and_restores_resources(monkeypatch):
    body = pdf_fixture(['ab', 'cd'])
    document, _ = native_document(monkeypatch, ['a b', 'c d'])
    reader = PdfReader(io.BytesIO(body), strict=True)
    errors, warnings = pymupdf.TOOLS.mupdf_display_errors(), pymupdf.TOOLS.mupdf_display_warnings()
    with pytest.raises(ToolFault) as caught:
        extract_pages(reader, body, LIMITS | {'text_bytes': 6})
    assert caught.value.code == 'TEXT_LIMIT' and document.closed
    assert pymupdf.TOOLS.mupdf_display_errors() == errors
    assert pymupdf.TOOLS.mupdf_display_warnings() == warnings


@pytest.mark.parametrize('original,native,expected', [
    ('not available; Redclay12kg', 'notavailable; Red clay 12 kg', 'not available; Red clay 12 kg'),
    ('ifready:\n    return20', 'if ready:\nreturn 20', 'if ready:\n    return 20'),
    ('not ready; Dose20mg 3 0', 'notready; Dose 2 0 mg 30', 'not ready; Dose 20 mg 3 0'),
])
def test_local_spacing_recovery_keeps_old_boundaries_layout_and_numbers(monkeypatch, original, native, expected):
    body = pdf_fixture([original])
    native_document(monkeypatch, [native])
    result = extract(body, {'content_type': 'application/pdf'}, recover_pdf=True)
    assert result['text'].decode() == expected
    diagnostic = result['provenance']['pdf_extraction']
    assert diagnostic['recovered_pages'] == diagnostic['changed_pages'] == 1
    assert diagnostic['native_pages'] == diagnostic['fallback_pages'] == 0
    assert diagnostic['inserted_spaces'] > 0
    assert sum(diagnostic['recovery_reasons'].values()) == 1
    Draft202012Validator(diagnostic_schema()).validate(diagnostic)


@pytest.mark.parametrize('native', [
    'notavailable; Red clay 120 kg', 'notavailable; blue clay 12 kg',
    'notavailable; clay Red 12 kg', 'notavailable; Red clay 12 kg missing',
])
def test_local_recovery_is_atomic_on_later_content_disagreement(monkeypatch, native):
    original = 'not available; Redclay12kg'
    body = pdf_fixture([original])
    native_document(monkeypatch, [native])
    result = extract(body, {'content_type': 'application/pdf'}, recover_pdf=True)
    assert result['text'].decode() == original
    diagnostic = result['provenance']['pdf_extraction']
    assert diagnostic['recovered_pages'] == diagnostic['inserted_spaces'] == 0
    assert diagnostic['fallback_pages'] == 1


@pytest.mark.parametrize('replacement', ['\ufffd', '\ue001', '\u200b'])
def test_unknown_or_invisible_glyph_is_not_counted_as_decoded(replacement):
    assert preservation('A\x81B', 'A' + replacement + 'B') == ('content_disagreement', 0)


def test_local_recovery_growth_uses_same_text_cap(monkeypatch):
    original = 'not ready; Redclay12kg'
    body = pdf_fixture([original])
    document, _ = native_document(monkeypatch, ['notready; Red clay 12 kg'])
    with pytest.raises(ToolFault) as caught:
        extract(body, {'content_type': 'application/pdf'}, {'text_bytes': len(original.encode())}, recover_pdf=True)
    assert caught.value.code == 'TEXT_LIMIT' and document.closed


def test_partial_recovery_can_decode_glyph_without_losing_other_boundaries(monkeypatch):
    original = 'not ready; Redclay\x8120'
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: original)])
    document, _ = native_document(monkeypatch, ['notready; Red clay≥20'])
    values, diagnostic = extract_pages(reader, b'controlled-native-body', LIMITS)
    assert values == ['not ready; Red clay≥20'] and document.closed
    assert diagnostic['recovered_pages'] == diagnostic['decoded_control_glyphs'] == 1
    assert diagnostic['unresolved_control_glyphs'] == 0
    assert diagnostic['inserted_spaces'] == 1
    assert preservation(original, values[0]) == (None, 1)


def test_diagnostic_schema_reads_all_versions_without_mixing_fields():
    from copy import deepcopy
    value = extract(positioned_pdf(), {'content_type': 'application/pdf'}, recover_pdf=True)['provenance']['pdf_extraction']
    validator = Draft202012Validator(diagnostic_schema())
    validator.validate(value)
    assert value['method'] == 'page-text-preservation/8'
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/7'}))
    value = deepcopy(value)
    del value['opaque_glyph_alignment']
    value['method'] = 'page-text-preservation/7'
    validator.validate(value)
    assert value['method'] == 'page-text-preservation/7'
    visual_rows = deepcopy(value)
    visual_rows['method'] = 'page-text-preservation/6'
    visual_rows['layout']['method'] = 'repeated-page-margins/2'
    validator.validate(visual_rows)
    withdrawn = deepcopy(value)
    withdrawn['method'] = 'page-text-preservation/5'
    withdrawn['layout']['method'] = 'repeated-page-margins/1'
    validator.validate(withdrawn)
    prior = deepcopy(value)
    prior['method'] = 'page-text-preservation/4'
    del prior['layout']
    del prior['spacing_corroboration']['geometry_joins']
    validator.validate(prior)
    corroborated = deepcopy(prior)
    corroborated['method'] = 'page-text-preservation/3'
    for key in ['geometry_pages', 'geometry_spaces', 'geometry_failures']:
        del corroborated['spacing_corroboration'][key]
    validator.validate(corroborated)
    legacy = deepcopy(prior)
    partial = deepcopy(prior)
    partial['method'] = 'page-text-preservation/2'
    for key in ['removed_spaces', 'spacing_corroboration']:
        del partial[key]
        del legacy[key]
    validator.validate(partial)
    legacy['method'] = 'page-text-preservation/1'
    for key in ['recovered_pages', 'inserted_spaces', 'recovery_reasons']:
        del legacy[key]
    validator.validate(legacy)
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/1'}))
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/2'}))
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/3'}))
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/4'}))
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/5'}))
    assert list(validator.iter_errors(value | {'method': 'page-text-preservation/6'}))
    assert list(validator.iter_errors(legacy | {'method': 'page-text-preservation/2'}))
    assert list(validator.iter_errors(value | {'semantic_verification': True}))
    assert list(validator.iter_errors(value | {'inserted_spaces': -1}))


@pytest.mark.parametrize('old,native,secondary,expected', [
    ('not ready; red,green; d a n c e', 'notready; red, green; dance', 'not ready; red, green; dance', 'not ready; red, green; dance'),
    ('items:α,β; МОДУ ЛЯ', 'items: α, β; МОДУЛЯ', 'items: α, β; МОДУЛЯ', 'items: α, β; МОДУЛЯ'),
    ('T h i sﬂoor\n  stays\t here\n ', 'Thisﬂoor\nstays here', 'Thisfloor\nstays here', 'Thisﬂoor\n  stays\t here\n '),
    ('a b; c,d', 'ab; c, d', 'a b; c,d', 'a b; c,d'),
    ('a b; c,d', 'ab; c, d', 'ab; c, d extra', 'a b; c,d'),
])
def test_spacing_edits_require_independent_boundary_evidence(old, native, secondary, expected):
    result, _, _, _ = recover_page_text(old, native, 10000, lambda: spacing_agreement(native, secondary)[0])
    assert result == expected


@pytest.mark.parametrize('old,native', [
    ('20', '2 0'), ('1.25', '1. 25'), ('10:30', '10: 30'),
    ('2026-10-03', '2026 - 10 - 03'), ('v1.2.3', 'v1. 2. 3'), ('2e-3', '2 e-3'),
    ('-20', '- 20'), ('1/2', '1 / 2'), ('1–2', '1 – 2'),
    ('.5', '. 5'), ('-.5', '-. 5'), ('0x2A', '0x 2A'), ('0b10', '0b 10'),
    ('1_000', '1_ 000'), ('1.2e+4', '1.2e+ 4'),
    ('Dose20mg', 'Dose2 0mg'),
])
def test_even_agreeing_native_readers_cannot_split_numeric_tokens(old, native):
    assert preservation(old, native)[0] == 'content_disagreement'
    result, inserted, removed, decoded = recover_page_text(old, native, 1000,
        lambda: spacing_agreement(native, native)[0])
    assert result == old and inserted == removed == decoded == 0


@pytest.mark.parametrize('old,native', [
    ('Refs(3,18,31)', 'Refs(3, 18, 31)'), ('June4,2021', 'June4, 2021'),
    ('Nutr.2021.41:309', 'Nutr. 2021. 41:309'), ('Spain,46010', 'Spain, 46010'),
])
def test_numeric_guard_does_not_preserve_joined_lists_or_bibliographic_fields(old, native):
    assert preservation(old, native) == (None, 0)
    result, _, _, _ = recover_page_text(old, native, 1000, lambda: spacing_agreement(native, native)[0])
    assert result == native


def test_failed_character_alignment_never_opens_secondary():
    def forbidden(): raise AssertionError('secondary called for a non-aligning page')
    assert recover_page_text('d a n c e; red,green; 20', 'dance; red, green; 2', 1000, forbidden) == ('d a n c e; red,green; 20', 0, 0, 0)


def test_corroborated_growth_keeps_the_existing_utf8_cap():
    native = 'red, green; blue'
    with pytest.raises(ToolFault) as caught:
        recover_page_text('red,green;blue', native, len('red,green;blue'), lambda: spacing_agreement(native, native)[0])
    assert caught.value.code == 'TEXT_LIMIT'


def test_missing_secondary_keeps_prior_safe_word_recovery():
    result, inserted, removed, _ = recover_page_text('not ready; Redclay; d a n c e; x,y',
        'notready; Red clay; dance; x, y', 1000, lambda: None)
    assert result == 'not ready; Red clay; d a n c e; x,y'
    assert inserted == 1 and removed == 0


def test_partial_recovery_preserves_unicode_and_trailing_layout(monkeypatch):
    original = 'not ready; cafémélangé\n\t  '
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: original)])
    native_document(monkeypatch, ['notready; café mélangé\n'])
    values, diagnostic = extract_pages(reader, b'controlled-native-body', LIMITS)
    assert values == ['not ready; café mélangé\n\t  ']
    assert diagnostic['inserted_spaces'] == 1
    with pytest.raises(ToolFault) as caught:
        extract_pages(reader, b'controlled-native-body', LIMITS | {'text_bytes': len(original.encode())})
    assert caught.value.code == 'TEXT_LIMIT'
