"""Glyph-name authority comes from actual operands and full-page alignment."""
import io
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from deepresearch.engine.toolset.pdf_glyphs import LIMIT, align_opaque_glyphs
from deepresearch.engine.toolset.pdf_extraction import recover_page_text


def fixture(*, literal=False, form=False):
    writer=PdfWriter();page=writer.add_blank_page(612,792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),
        NameObject('/BaseFont'):NameObject('/Helvetica'),NameObject('/Encoding'):DictionaryObject({
            NameObject('/BaseEncoding'):NameObject('/WinAnsiEncoding'),
            NameObject('/Differences'):ArrayObject([NumberObject(1),NameObject('/UnmappedGlyph')])})})
    resources=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    text=b'/UnmappedGlyph' if literal else b'\\001'
    data=b'BT /F1 12 Tf 50 700 Td (redblue '+text+b' green gold) Tj ET'
    if form:
        child=DecodedStreamObject();child.set_data(data)
        child.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
            NameObject('/BBox'):ArrayObject([NumberObject(x) for x in (0,0,612,792)]),NameObject('/Resources'):resources})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Child'):writer._add_object(child)})})
        data=b'q /Child Do Q'
    else:page[NameObject('/Resources')]=resources
    stream=DecodedStreamObject();stream.set_data(data);page[NameObject('/Contents')]=writer._add_object(stream)
    out=io.BytesIO();writer.write(out)
    return PdfReader(io.BytesIO(out.getvalue()),strict=True).pages[0]


def geometry(text, font='Helvetica'):
    return {'blocks':[{'type':0,'lines':[{'spans':[{'font':font,'chars':[{'c':c} for c in text]}]}]}]}


@pytest.mark.parametrize('form',[False,True])
def test_bound_raw_character_code_preserves_unknown_name_and_recovers_other_words(form):
    page=fixture(form=form);original=page.extract_text();native='red blue \x02 green gold'
    spans,reason=align_opaque_glyphs(page,original,native,lambda:geometry(native))
    assert reason is None and len(spans)==1
    a,z,b=spans[0];assert original[a:z]=='/UnmappedGlyph' and native[b]=='\x02'
    assert recover_page_text(original,native,1000)[0]==original
    text,added,removed,replaced=recover_page_text(original,native,1000,opaque_spans=spans)
    assert text=='red blue /UnmappedGlyph green gold' and (added,removed,replaced)==(1,0,0)
    assert page.extract_text()==original  # No original resource or operand mutation.


def test_literal_glyph_name_spelling_is_not_an_undecoded_character():
    page=fixture(literal=True);original=page.extract_text();native='red blue \x02 green gold'
    assert align_opaque_glyphs(page,original,native,lambda:geometry(native))==((),'content_disagreement')


@pytest.mark.parametrize('change',['font','printable','late_text','geometry','truncated','original'])
def test_unknown_character_cannot_hide_font_text_or_geometry_disagreement(change):
    page=fixture();original=page.extract_text();native='red blue \x02 green gold'
    if change=='printable':native=native.replace('\x02','≥')
    if change=='late_text':native+=' altered'
    if change=='truncated':native=native[:-1]
    if change=='original':original=original.replace('gold','Gold')
    raw=geometry(native,'Courier' if change=='font' else 'Helvetica')
    if change=='geometry':raw['blocks'][0]['lines'][0]['spans'][0]['chars'][-1]['c']='X'
    assert align_opaque_glyphs(page,original,native,lambda:raw)==((),'content_disagreement')


def test_overlarge_page_does_not_trace_or_allocate_geometry():
    def forbidden(*a,**kw):raise AssertionError('unbounded trace')
    assert align_opaque_glyphs(SimpleNamespace(extract_text=forbidden),'a'*(LIMIT+1),'x',forbidden)==((),'text_limit')


def test_unknown_names_keep_both_neighbor_gaps_even_with_other_space_permissions():
    old='redblue X /Opaque Y tailend';native='red blue X\x02Y tail end'
    a=old.index('/Opaque');b=native.index('\x02');spans=((a,a+7,b),)
    result=recover_page_text(old,native,1000,lambda:bytearray([8]*len(native)),opaque_spans=spans)
    assert result[0]=='red blue X /Opaque Y tail end'
    assert result[3]==0


def test_late_disagreement_discards_earlier_opaque_alignment_and_spacing():
    old='redblue /Opaque tail';native='red blue \x02 altered'
    spans=((8,15,native.index('\x02')),)
    def forbidden():raise AssertionError('partial-page recovery')
    assert recover_page_text(old,native,1000,forbidden,opaque_spans=spans)==(old,0,0,0)


def test_opaque_span_cannot_point_to_another_native_position():
    old='redblue /Opaque tail';native='red blue \x02 tail\x02'
    assert recover_page_text(old,native,1000,opaque_spans=((8,15,len(native)-1),))==(old,0,0,0)
