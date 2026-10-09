"""PDF margins are structural annotations, never deleted source text."""
import json

import pymupdf
import pytest
from jsonschema import Draft202012Validator

from deepresearch.engine.toolset.pdf_layout import PdfLayout, layout_schema
from deepresearch.engine.toolset.retrieval import extract
from deepresearch.engine.toolset.common import digest


def document(*, pages=4, changing=False):
    with pymupdf.open() as pdf:
        for n in range(pages):
            page = pdf.new_page(width=612, height=792)
            page.insert_text((60,40), 'Research Journal', fontsize=9)
            if n != 1: page.insert_text((60,65), 'Repeated body text near the top.', fontsize=12)
            if n == 1: page.insert_text((60,95), 'continues with the recorded result.', fontsize=12)
            page.insert_text((60,300), 'Substantive body prose with conditions and source evidence.', fontsize=12)
            page.insert_text((60,330), f'The document describes observation number {n+1}.', fontsize=12)
            if n == 0: page.insert_text((60,680), 'The supported sentence', fontsize=12)
            page.insert_text((60,750), f'Journal footer. Page {40 + (n*n if changing else n)}', fontsize=9)
            page.insert_text((15,500), 'Publisher download notice for personal reading and individual research use.', fontsize=8, rotate=90)
        return pdf.tobytes()


def test_actual_coordinates_repeat_and_bind_without_deleting_or_reordering():
    body = document()
    value = extract(body, {'content_type':'application/pdf'}, recover_pdf=True)
    layout = value['provenance']['pdf_extraction']['layout']
    Draft202012Validator(layout_schema()).validate(layout)
    assert layout['checked_pages'] == 4 and layout['skipped_pages'] == 0
    assert len(layout['spans']) == 12
    assert layout['text_sha256'] == digest(value['text'])
    for span in layout['spans']:
        original = value['text'][span['start_byte']:span['end_byte']]
        assert digest(original) == span['text_sha256']
        assert b'Repeated body text' not in original and b'Substantive' not in original
        assert span['repeated_pages'] == 4
    index = json.loads(value['index'])
    assert layout['page_breaks'] == [p['start_byte'] for p in index['pages'][1:]]
    assert value['text'].count(b'Journal footer.') == 4
    assert value['text'].count(b'Publisher download notice') == 4
    assert value['original'] == body


def test_two_pages_do_not_establish_repeated_margin_authority():
    value = extract(document(pages=2), {'content_type':'application/pdf'}, recover_pdf=True)
    layout = value['provenance']['pdf_extraction']['layout']
    assert layout['spans'] == [] and layout['skipped_pages'] == 2


def test_changed_numeric_conditions_cannot_masquerade_as_page_counters():
    value = extract(document(changing=True), {'content_type':'application/pdf'}, recover_pdf=True)
    layout = value['provenance']['pdf_extraction']['layout']
    assert not any(s['kind']=='footer' for s in layout['spans'])


def test_annotations_respect_size_cap_and_count_omissions():
    pages, collector = [], PdfLayout()
    with pymupdf.open(stream=document(), filetype='pdf') as pdf:
        for n,p in enumerate(pdf,1):
            text = p.get_text('text');pages.append(text)
            collector.add(n,text,p.get_text('rawdict'),p.rect.width,p.rect.height)
    layout = collector.finish(pages, 800)
    assert len(json.dumps(layout,separators=(',',':')).encode()) <= 800
    assert layout['omitted_spans'] > 0 and len(layout['spans']) < 12
    assert '\n'.join(pages).count('Journal footer.') == 4


def test_layout_malformed_coordinates_do_not_change_source():
    collector = PdfLayout()
    with pytest.raises(ValueError): collector.add(1,'body',{'blocks':[]},float('nan'),792)
    assert collector.candidates == [] and collector.checked == 0


def test_ambiguous_margin_phrase_inside_body_cannot_be_annotated():
    collector = PdfLayout();pages=[]
    with pymupdf.open(stream=document(),filetype='pdf') as pdf:
        for n,p in enumerate(pdf,1):
            text=p.get_text('text')+'\nResearch Journal is also discussed in this body paragraph.'
            pages.append(text);collector.add(n,text,p.get_text('rawdict'),p.rect.width,p.rect.height)
    layout=collector.finish(pages,32768)
    assert not any(s['kind']=='header' for s in layout['spans'])


@pytest.mark.parametrize('word', ['MAY', 'MUST', 'NOT', 'optional'])
def test_small_inline_type_remains_part_of_its_complete_visual_body_row(word):
    def line(text, x0, x1, size, baseline, top):
        return {'bbox':(x0,top,x1,baseline+2), 'dir':(1.,0.), 'spans':[
            {'text':text,'size':size,'origin':(x0,baseline)}]}
    raw={'blocks':[{'type':0,'lines':[
        line('Substantive body text and conditions.',60,420,12,300,287),
        line('A client',60,120,12,75,62),
        line(word,120,170,10,75,64),
        line('perform the described action.',170,440,12,75,62),
        line('Running Journal',60,180,8,35,26),
    ]}]}
    # The retained parser emits the smaller inline span separately, as in the
    # RFC fixture. Physical row membership still forbids treating it as a header.
    text=f'A client perform the described action.\n{word}\nSubstantive body text and conditions.\nRunning Journal'
    collector=PdfLayout()
    for page in range(1,5):collector.add(page,text,raw,612,792)
    layout=collector.finish([text]*4,32768);saved='\n'.join([text]*4).encode()
    assert len(layout['spans'])==4
    assert all(saved[s['start_byte']:s['end_byte']]==b'Running Journal' for s in layout['spans'])


def test_short_rotated_chart_label_does_not_become_download_watermark():
    raw={'blocks':[{'type':0,'lines':[
        {'bbox':(60,290,420,310),'dir':(1.,0.),'spans':[{'text':'Body prose and evidence.','size':12,'origin':(60,300)}]},
        {'bbox':(5,200,15,230),'dir':(0.,-1.),'spans':[{'text':'Age','size':8,'origin':(15,230)}]},
    ]}]}
    collector=PdfLayout()
    for page in range(1,5):collector.add(page,'Body prose and evidence.\nAge',raw,612,792)
    assert collector.finish(['Body prose and evidence.\nAge']*4,32768)['spans']==[]


def footer_family(*, strong_pages=3, change=None):
    """A table-dominated page uses the margin's font for most body text."""
    collector, pages = PdfLayout(), []
    with pymupdf.open() as pdf:
        for n in range(strong_pages+1):
            weak = n == strong_pages
            p = pdf.new_page(width=612,height=792)
            p.insert_text((60,300), 'Repeated body prose or table cells with evidence.',
                          fontsize=9 if weak else 12)
            label = 'Archive Journal Page ' + str(41+n if not (weak and change=='counter') else 90)
            if weak and change=='text': label = 'Different Journal Page ' + str(41+n)
            p.insert_text((60,720 if not (weak and change=='position') else 680),label,
                          fontsize=10 if weak and change=='font' else 9)
            if weak and change=='inline':
                p.insert_text((360,720), 'Substantive sentence continues.', fontsize=12)
        for n,p in enumerate(pdf,1):
            text=p.get_text('text');pages.append(text)
            collector.add(n,text,p.get_text('rawdict'),p.rect.width,p.rect.height)
    return collector.finish(pages,32768), '\n'.join(pages).encode()


def test_repeated_confirmed_footer_survives_table_dominated_body_font():
    layout,saved=footer_family()
    assert len(layout['spans'])==4
    assert all(s['repeated_pages']==4 and s['kind']=='footer' for s in layout['spans'])
    for span in layout['spans']:
        assert digest(saved[span['start_byte']:span['end_byte']])==span['text_sha256']
    assert saved.count(b'Archive Journal Page')==4


def test_weak_font_evidence_cannot_establish_a_margin_family():
    assert footer_family(strong_pages=2)[0]['spans']==[]


@pytest.mark.parametrize('change',['text','font','position','inline'])
def test_footer_family_does_not_transfer_authority_to_different_or_partial_row(change):
    layout,_=footer_family(change=change)
    assert len(layout['spans'])==3
    assert {s['page'] for s in layout['spans']}=={1,2,3}


def test_weak_page_with_inconsistent_counter_invalidates_family():
    assert footer_family(change='counter')[0]['spans']==[]
