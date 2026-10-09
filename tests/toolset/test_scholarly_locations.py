"""Malformed optional source URLs must not discard unrelated discoveries."""
from copy import deepcopy
import pytest
from deepresearch.engine.toolset.common import ToolFault
from deepresearch.engine.toolset.scholarly import project
from tests.toolset.test_discovery_metadata import crossref,openalex,ARGUMENTS,valid

@pytest.mark.parametrize('bad', ['https://example.org/a https://example.org/b','file:///x','https://u:p@example.org/a','https://example.org/a?token=fixture-only',True,None,9000*'x'],ids=['joined','scheme','userinfo','credential','type','null','length'])
def test_crossref_invalid_optional_link_is_flagged_without_dropping_row_or_other_link(bad):
    source=crossref();original=source['message']['items'][0]
    original['link'].append({'URL':bad,'content-type':'application/pdf'})
    source['message']['items'].append({'title':['Another source'],'DOI':'10.1234/other','URL':'https://doi.org/10.1234/other'})
    saved=deepcopy(source)
    out=project('crossref',source,ARGUMENTS,2)
    valid(out,'crossref')
    assert len(out['results'])==2 and out['coverage']['returned_results']==2
    first=out['results'][0]
    assert len(first['links'])==1 and first['links'][0]['url']==original['link'][0]['URL']
    assert first['doi_url']==original['URL'] and first['titles']==original['title']
    assert 'links[1].url' in first['bibliography']['invalid_fields']
    assert source==saved

@pytest.mark.parametrize('provider',['crossref','openalex'])
def test_invalid_optional_doi_url_remains_unknown_and_is_flagged(provider):
    source=crossref() if provider=='crossref' else openalex()
    row=source['message']['items'][0] if provider=='crossref' else source['results'][0]
    row['URL' if provider=='crossref' else 'doi']='https://example.org/a b'
    out=project(provider,source,ARGUMENTS,2)
    valid(out,provider)
    assert out['results'][0]['doi_url'] is None
    assert 'doi_url' in out['results'][0]['bibliography']['invalid_fields']


def test_openalex_invalid_nested_url_does_not_lose_other_location_facts():
    source=openalex();loc=source['results'][0]['primary_location']
    loc['pdf_url']='javascript:alert(1)'
    out=project('openalex',source,ARGUMENTS,2);valid(out,'openalex')
    locout=out['results'][0]['primary_location']
    assert locout['pdf_url'] is None and locout['landing_page_url']==loc['landing_page_url']
    assert 'primary_location.pdf_url' in out['results'][0]['bibliography']['invalid_fields']


def test_legacy_result_remains_strict_but_labels_invalid_provider_metadata():
    source=crossref();source['message']['items'][0]['link'][0]['URL']='https://example.org/a https://example.org/b'
    with pytest.raises(ToolFault) as caught:project('crossref',source,ARGUMENTS,1)
    assert caught.value.code=='SCHOLAR_PROTOCOL_ERROR'
