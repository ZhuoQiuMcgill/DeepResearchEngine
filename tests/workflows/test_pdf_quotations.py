"""A PDF body projection requires real layout, read bytes and a crossed page."""
import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.engine.toolset.retrieval import extract
from deepresearch.workflows.components.pdf_quotations import layout_window
from deepresearch.workflows.components.quotations import PreparedQuoteSource
from tests.toolset.test_pdf_layout import document


def prepared():
    value=extract(document(),{'content_type':'application/pdf'},recover_pdf=True)
    text=value['text'].decode();window={'text':text,'start_byte':0}
    margins,breaks=layout_window(value['provenance'],window)
    return value,window,PreparedQuoteSource(text,pdf_margins=margins,pdf_page_breaks=breaks)


def test_cross_page_body_quote_returns_full_original_span_including_margins():
    value,window,locator=prepared()
    quote='The supported sentence continues with the recorded result.'
    assert PreparedQuoteSource(window['text']).locate(quote) is None
    exact=locator.locate(quote)
    assert exact is not None and exact in window['text']
    assert 'Journal footer. Page 40' in exact and 'Publisher download notice' in exact
    assert 'Research Journal' in exact
    assert locator.locate(quote.replace('recorded','invented')) is None


def test_previous_visual_row_layout_remains_readable():
    value,window,_=prepared()
    value['provenance']['pdf_extraction']['layout']['method']='repeated-page-margins/2'
    margins,breaks=layout_window(value['provenance'],window)
    locator=PreparedQuoteSource(window['text'],pdf_margins=margins,pdf_page_breaks=breaks)
    assert locator.locate('The supported sentence continues with the recorded result.') is not None


@pytest.mark.parametrize('change',['hash','part_hash','overlap','utf8','breaks'])
def test_annotations_with_changed_source_authority_are_rejected(change):
    value,window,_=prepared();layout=value['provenance']['pdf_extraction']['layout']
    if change=='hash':layout['text_sha256']='sha256:wrong'
    if change=='part_hash':layout['spans'][0]['text_sha256']='sha256:wrong'
    if change=='overlap':layout['spans'][1]['start_byte']=0
    if change=='utf8':window['text']='☃'+window['text'][1:]
    if change=='breaks':layout['page_breaks'].reverse()
    with pytest.raises(EngineError):layout_window(value['provenance'],window)


@pytest.mark.parametrize('case',['nonpdf','legacy','withdrawn','no_break','partial_margin'])
def test_no_projection_permission_from_wrong_media_or_incomplete_structure(case):
    value,window,_=prepared()
    if case=='nonpdf':value['provenance']['media_type']='text/plain'
    if case=='legacy':del value['provenance']['pdf_extraction']['layout']
    if case=='withdrawn':value['provenance']['pdf_extraction']['layout']['method']='repeated-page-margins/1'
    if case=='no_break':value['provenance']['pdf_extraction']['layout']['page_breaks']=[]
    if case=='partial_margin':
        span=value['provenance']['pdf_extraction']['layout']['spans'][0]
        window={'text':window['text'][span['start_byte']+1:span['end_byte']], 'start_byte':span['start_byte']+1}
    margins,breaks=layout_window(value['provenance'],window)
    locator=PreparedQuoteSource(window['text'],pdf_margins=margins,pdf_page_breaks=breaks)
    assert locator.locate('The supported sentence continues with the recorded result.') is None


def test_margin_projection_cannot_join_prose_within_one_page():
    text='The sentence\nRepeated margin\ncontinues here.\nNext page.'
    a=text.index('Repeated');b=text.index('\ncontinues')
    locator=PreparedQuoteSource(text,pdf_margins=((a,b),),pdf_page_breaks=(text.index('Next'),))
    assert locator.locate('The sentence continues here.') is None


def test_cross_page_original_span_limit_still_applies():
    text='Before\n'+'m'*2048+'\nAfter'
    locator=PreparedQuoteSource(text,pdf_margins=((7,2055),),pdf_page_breaks=(2056,))
    assert locator.locate('Before After') is None


def test_pdf_layout_survives_cross_read_binding_and_quote_compaction():
    from tests.methods.test_cross_read_distillation import example
    from deepresearch.methods.baseline.stages.distillation import validate_distillation
    from deepresearch.methods.baseline.stages.evidence_delivery import _quote_units
    value,window,_=prepared();text=window['text']
    split=text.index('Publisher download notice')+10
    distilled,job,plan=example((text[:split],text[split:]))
    job['source'].provenance=value['provenance']
    distilled.findings[0].quote='The supported sentence continues with the recorded result.'
    result=validate_distillation(distilled,job,plan,adjacent_reads=True,pdf_layout=True)
    assert len(job['quote_bindings'])==1
    record={'segment_ids':[s['segment_id'] for s in job['segments']],
            'distillation':result.to_dict(),'quote_bindings':job['quote_bindings']}
    units=_quote_units([record],{'segments':job['segments']})
    assert ''.join(u['text'] for u in units)==result.findings[0].quote
    assert len(units)==2 and len({u['read_action_id'] for u in units})==2
    assert 'Publisher download notice' in result.findings[0].quote


def test_pdf_metadata_requires_hardened_opt_in():
    from tests.methods.test_cross_read_distillation import example
    from deepresearch.methods.baseline.stages.distillation import validate_distillation
    value,window,_=prepared()
    distilled,job,plan=example((window['text'],))
    job['source'].provenance=value['provenance']
    distilled.findings[0].segment_id='s0'
    distilled.findings[0].quote='The supported sentence continues with the recorded result.'
    with pytest.raises(EngineError):validate_distillation(distilled,job,plan,adjacent_reads=True)
