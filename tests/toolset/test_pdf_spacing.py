"""Independent spacing agreement, bounded failures and owned native handles."""
from types import SimpleNamespace

import pypdfium2
import pytest

from deepresearch.engine.toolset.pdf_spacing import PdfSpacingReader, spacing_agreement


@pytest.mark.parametrize('primary,secondary', [
    ('danceﬂoor; blue, green', 'dancefloor; blue, green'),
    ('dancefloor; blue, green', 'danceﬂoor; blue, green'),
    ('café ﬃ; МОДУЛЯ', 'café ffi; МОДУЛЯ'),
])
def test_ligatures_only_align_offsets_never_replace_text(primary, secondary):
    flags, opaque = spacing_agreement(primary, secondary)
    assert opaque == 0 and len(flags) == len(primary)
    for index in range(1, len(primary)):
        if primary[index - 1:index + 1].isalpha():
            assert flags[index] == 1
        if primary[index - 1] == ' ' and not primary[index].isspace():
            assert flags[index] == 2


@pytest.mark.parametrize('secondary', ['Red green', 'red green added', 'green red', 'red 20', 'red gree'])
def test_late_content_disagreement_discards_all_earlier_flags(secondary):
    assert spacing_agreement('red green', secondary) == (None, 0)


def test_opaque_secondary_position_cannot_authorize_neighbor_changes():
    native = 'left, right; co-operation; dancefloor'
    flags, count = spacing_agreement(native, native.replace('-', '\x02'))
    assert count == 1
    assert flags[native.index('-')] == flags[native.index('-') + 1] == 0
    assert flags[native.index('right')] == 2
    assert flags[native.index('floor')] == 1
    # An unknown primary glyph does not become known through the spacing reader.
    assert spacing_agreement('co\x02operation', 'co-operation') == (None, 0)
    same, count = spacing_agreement('co\x02operation', 'co\x02operation')
    assert count == 1 and same[2] == same[3] == 0


@pytest.mark.parametrize('secondary', ['a\nb', 'a\tb', 'a\u00a0b', 'a  b', 'ab'])
def test_ascii_space_requires_exact_agreement_not_whitespace_normalization(secondary):
    flags, _ = spacing_agreement('a b', secondary)
    assert flags[2] == 0


def fake_reader(monkeypatch, *, text='red, green', count=1, failure=None):
    state = {'opened': 0, 'text_closed': 0, 'page_closed': 0, 'doc_closed': 0, 'pages_loaded': 0}
    class Document:
        def __len__(self): return count
        def __getitem__(self, number):
            state['pages_loaded'] += 1
            if failure == 'page': raise RuntimeError('page')
            def get_textpage():
                if failure == 'textpage': raise RuntimeError('textpage')
                def get_text_bounded(*, errors):
                    assert errors == 'strict'
                    if failure == 'text': raise ValueError('decode')
                    return text
                def close(): state['text_closed'] += 1
                return SimpleNamespace(get_text_bounded=get_text_bounded, close=close)
            def close(): state['page_closed'] += 1
            return SimpleNamespace(get_textpage=get_textpage, close=close)
        def close(self): state['doc_closed'] += 1
    def open_document(body):
        state['opened'] += 1
        if failure == 'open': raise RuntimeError('open')
        return Document()
    monkeypatch.setattr(pypdfium2, 'PdfDocument', open_document)
    return state


def test_reader_is_lazy_reuses_document_and_closes_every_handle(monkeypatch):
    state = fake_reader(monkeypatch, count=2)
    reader = PdfSpacingReader(b'pdf', 2)
    assert state['opened'] == 0
    for page in range(2):
        assert reader.compare(page, 'red, green', 100)[5] == 2
    reader.close()
    reader.close()
    assert state == {'opened': 1, 'text_closed': 2, 'page_closed': 2, 'doc_closed': 1, 'pages_loaded': 2}
    assert reader.diagnostic['attempted_pages'] == reader.diagnostic['aligned_pages'] == 2
    assert not any(reader.diagnostic['failures'].values())


@pytest.mark.parametrize('failure,reason,closed', [
    ('open', 'reader_unavailable', (0, 0, 0)),
    ('count', 'page_count_disagreement', (0, 0, 1)),
    ('page', 'page_error', (0, 0, 1)),
    ('textpage', 'page_error', (0, 2, 1)),
    ('text', 'page_error', (2, 2, 1)),
    ('limit', 'text_limit', (2, 2, 1)),
    ('content', 'content_disagreement', (2, 2, 1)),
])
def test_secondary_failures_are_bounded_recorded_and_release_handles(monkeypatch, failure, reason, closed):
    state = fake_reader(monkeypatch, count=2 if failure == 'count' else 1, failure=failure)
    reader = PdfSpacingReader(b'pdf', 1)
    for _ in range(2):
        assert reader.compare(0, 'red, blue' if failure == 'content' else 'red, green', 2 if failure == 'limit' else 100) is None
    reader.close()
    assert (state['text_closed'], state['page_closed'], state['doc_closed']) == closed
    assert state['opened'] == 1
    assert reader.diagnostic['failures'][reason] == reader.diagnostic['attempted_pages'] == 2
    assert reader.diagnostic['aligned_pages'] == 0


def test_secondary_utf8_limit_is_bytes_not_characters(monkeypatch):
    fake_reader(monkeypatch, text='漢字')
    reader = PdfSpacingReader(b'pdf', 1)
    assert reader.compare(0, '漢字', 5) is None
    assert reader.diagnostic['failures']['text_limit'] == 1
    reader.close()
