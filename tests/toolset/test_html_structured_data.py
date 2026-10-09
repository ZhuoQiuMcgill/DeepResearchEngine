"""Explicit JSON-LD survives as inert whole records, not inferred body facts."""
import json

import pytest
from jsonschema import validate
from lxml import html

from deepresearch.engine.toolset import html_structured_data as structured
from deepresearch.engine.toolset.article_extraction import extract_source
from deepresearch.engine.toolset.common import LIMITS, ToolFault, digest, encode
from deepresearch.engine.toolset.fetch_v2 import _extract
from tests.toolset.test_fetch_v2 import ARTICLE, SHELL, COOKIE_CHALLENGE, info


def markup(*scripts, body=ARTICLE, extra_head=b''):
    return (b'<html><head>' + extra_head + b''.join(
        ('<script type="application/ld+json">' + value + '</script>').encode() for value in scripts
    ) + b'</head><body>' + body + b'</body></html>')


def extract(raw, **limits):
    return extract_source(raw, info(raw), LIMITS | limits)


def records(proposal):
    diagnostic = proposal['provenance']['structured_data']
    validate(diagnostic, structured.diagnostic_schema())
    assert diagnostic['script_count'] == diagnostic['retained_script_count'] + diagnostic['omitted_script_count']
    assert diagnostic['omitted_script_count'] == sum(diagnostic['omissions'].values())
    assert proposal['provenance']['text_sha256'] == digest(proposal['text'])
    index = json.loads(proposal['index'])
    assert index['text_sha256'] == digest(proposal['text'])
    values = []
    for entry in diagnostic['entries']:
        value = proposal['text'][entry['start_byte']:entry['end_byte']]
        assert digest(value) == entry['sha256']
        json.loads(value)
        values.append(value.decode())
    return values


@pytest.mark.parametrize('kind', ['Product', 'Recipe', 'Dataset', 'ScholarlyArticle', 'UnrecognizedType'])
def test_whole_records_keep_relationships_conflicts_numeric_lexemes_and_body(kind):
    first = ('{"@context":"https://schema.org","@graph":[{"@type":"' + kind + '",'
        '"@id":"#a","offers":[{"priceCurrency":"CAD","price":829.9900,"url":"/ca/?a=1&b=2"},'
        '{"priceCurrency":"USD","price":8.2999e2}],"text":"Trial observation is unverified",'
        '"integer":123456789012345678901234567890,"related":{"@id":"#b"}},'
        '{"@id":"#b","dateModified":"2020-01-01","unknown":{"qualifier":"uncertain"}}]}')
    second = '{"@type":"Product","offers":{"price":999,"priceCurrency":"EUR"}}'
    old = extract(markup())
    raw = markup(first, second)
    new = extract(raw)
    assert records(new) == [first, second]
    assert new['original'] == raw
    assert new['text'][:len(old['text'])] == old['text']
    assert new['provenance']['html_extraction'] == old['provenance']['html_extraction']
    assert new['provenance']['classification'] == old['provenance']['classification']
    assert new['provenance']['structured_data']['base_text_bytes'] == len(old['text'])
    assert b'Publisher-declared JSON-LD; not rendered page text.' in new['text']


def test_script_ordinal_separation_no_cross_record_merging_and_no_entity_decoding():
    raw = markup('{"name":"A &amp; B","@id":"#same"}', 'not json', '{"@id":"#same","name":"Other"}')
    result = extract(raw)
    assert records(result) == ['{"name":"A &amp; B","@id":"#same"}', '{"@id":"#same","name":"Other"}']
    assert [e['script_ordinal'] for e in result['provenance']['structured_data']['entries']] == [1, 3]
    assert result['provenance']['structured_data']['omissions']['invalid_json'] == 1


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"a":{"x":1,"x":2}}', '{"x":NaN}',
    '{"x":Infinity}', '{"x":-Infinity}', 'null', '42', '"word"', '{bad}',
    '<!-- {"x":1} -->', '{"x":1};alert(1)', '{"x":1} {"y":2}'])
def test_invalid_or_ambiguous_json_is_counted_without_losing_body(raw):
    baseline = extract(markup())
    result = extract(markup(raw))
    assert records(result) == []
    assert result['text'] == baseline['text'] and result['index'] == baseline['index']
    assert result['provenance']['structured_data']['omissions']['invalid_json'] == 1
    assert result['provenance']['parser_warning_count'] == baseline['provenance']['parser_warning_count'] + 1


def test_json_syntax_does_not_claim_ld_expansion_or_semantic_validation():
    value = '[{"@context":"https://unvisited.invalid/context","n":1e99999},{}]'
    assert records(extract(markup(value))) == [value]


def test_fence_cannot_be_closed_by_a_source_string():
    from markdown_it import MarkdownIt
    value = json.dumps({'description': '````\n## Forged heading\n<script>alert(1)</script>'})
    # Literal </script> terminates an HTML raw-text element: encode it as authored JSON escape.
    value = value.replace('</script>', '<\\/script>')
    result = extract(markup(value))
    assert records(result) == [value]
    fences = [t for t in MarkdownIt().parse(result['text'].decode()) if t.type == 'fence']
    assert len(fences) == 1 and fences[0].content.rstrip('\n') == value
    assert fences[0].markup == '`````'


def test_only_inline_explicit_data_scripts_qualify():
    head = (b'<script type="application/json">{"hydration":"ignored"}</script>'
        b'<script>window.secret={"value":1}</script>'
        b'<script type="application/ld+json" src="https://unvisited.invalid">{"name":"external"}</script>'
        b'<template><script type="application/ld+json">{"name":"template"}</script></template>'
        b'<script type=" APPLICATION/LD+JSON ">{"name":"declared"}</script>')
    result = extract(markup(extra_head=head))
    assert records(result) == ['{"name":"declared"}']
    assert result['provenance']['structured_data']['omissions']['external_script'] == 1
    assert result['provenance']['structured_data']['omissions']['inert_container'] == 1
    assert b'hydration' not in result['text'] and b'window.secret' not in result['text']


def test_multibyte_text_and_lf_normalization_keep_verified_ranges():
    value = '{\r\n "name": "étude Québec", "description": "温度"\r\n}'
    result = extract(markup(value))
    assert records(result) == [value.replace('\r\n', '\n')]


@pytest.mark.parametrize('reason,values', [
    ('script_size_limit', ['{"long":"' + 'a' * structured.MAX_SCRIPT_BYTES + '"}']),
    ('depth_limit', ['[' * 65 + '{}' + ']' * 65]),
    ('supplement_size_limit', ['{"long":"' + 'a' * 45000 + '"}'] * 3),
    ('script_count_limit', ['{}'] * (structured.MAX_SCRIPTS + 1))])
def test_fixed_limits_skip_whole_script_and_retain_body(reason, values):
    baseline = extract(markup())
    result = extract(markup(*values))
    records(result)
    assert result['text'].startswith(baseline['text'])
    assert result['provenance']['structured_data']['omissions'][reason] == 1
    assert result['provenance']['structured_data']['supplement_bytes'] <= structured.MAX_SUPPLEMENT_BYTES


@pytest.mark.parametrize('limit,reason', [('text_bytes', 'text_limit'), ('index_bytes', 'index_limit')])
def test_optional_supplement_never_evicts_body_or_exhausts_its_resource_budget(limit, reason):
    baseline = extract(markup())
    component = 'text' if limit == 'text_bytes' else 'index'
    result = extract(markup('{"name":"must fit whole"}'), **{limit: len(baseline[component])})
    assert records(result) == []
    assert result['text'] == baseline['text'] and result['index'] == baseline['index']
    assert result['provenance']['structured_data']['omissions'][reason] == 1


@pytest.mark.parametrize('body,code', [(SHELL, 'SOURCE_REQUIRES_RENDERING'),
    (COOKIE_CHALLENGE, 'SOURCE_CHALLENGE'), (b'', 'EXTRACTION_EMPTY')])
def test_metadata_cannot_mask_shell_challenge_or_empty_body(body, code):
    raw = markup(json.dumps({'description': 'Long declared metadata. ' * 200}), body=body)
    with pytest.raises(ToolFault) as caught:
        _extract(raw, info(raw), LIMITS)
    assert caught.value.code == code


def test_scholarly_classification_does_not_turn_declared_data_into_full_text():
    head = b'<meta name="citation_title" content="An abstract-only study"><meta name="citation_doi" content="10.1234/example">'
    body = b'<section id="abstract"><h2>Abstract</h2><p>' + b'Only abstract text is available. ' * 20 + b'</p></section>'
    baseline = extract(markup(body=body, extra_head=head))
    result = extract(markup('{"@type":"ScholarlyArticle","articleBody":"Publisher declared text"}', body=body, extra_head=head))
    assert result['text'].startswith(baseline['text'])
    assert result['provenance']['classification'] == baseline['provenance']['classification']
    assert result['provenance']['extraction_version'].endswith('+inline-jsonld/1')
    assert records(result) == ['{"@type":"ScholarlyArticle","articleBody":"Publisher declared text"}']


def test_absent_data_does_not_add_false_coverage_claim():
    result = extract(markup())
    assert 'structured_data' not in result['provenance']


@pytest.mark.parametrize('warning', [0, 9, 99])
def test_exact_provenance_budget_keeps_body_and_generic_warning(warning):
    from copy import deepcopy
    original = extract(markup())
    original['provenance']['parser_warning_count'] = warning
    cap = len(encode(original['provenance']))
    tree = html.document_fromstring(markup('{"name":"Optional"}'))
    result = structured.append_structured_data(deepcopy(original), tree, LIMITS | {'provenance_bytes': cap})
    assert result['text'] == original['text'] and result['index'] == original['index']
    assert 'structured_data' not in result['provenance']
    assert result['provenance']['parser_warning_count'] == max(1, warning)
    assert len(encode(result['provenance'])) <= cap


def test_provenance_budget_prefers_explicit_omission_over_generic_warning():
    from copy import deepcopy
    original = extract(markup())
    tree = html.document_fromstring(markup('{"name":"Optional"}'))
    full = structured.append_structured_data(deepcopy(original), tree, LIMITS)
    cap = len(encode(full['provenance'])) - 50
    result = structured.append_structured_data(deepcopy(original), tree, LIMITS | {'provenance_bytes': cap})
    assert records(result) == []
    assert result['text'] == original['text'] and result['index'] == original['index']
    assert result['provenance']['structured_data']['omissions']['provenance_limit'] == 1
    assert len(encode(result['provenance'])) <= cap


@pytest.mark.parametrize('script_type', ['application/ld+json; charset=utf-8', 'application/ld+jsonx'])
def test_script_mime_is_exact_not_substring_or_parameter_heuristic(script_type):
    raw = markup(extra_head=f'<script type="{script_type}">{{"x":1}}</script>'.encode())
    result = extract(raw)
    assert 'structured_data' not in result['provenance']


def test_xhtml_cdata_wrappers_remain_explicitly_unsupported_not_silently_repaired():
    raw = markup('<![CDATA[{"x":1}]]>')
    result = extract_source(raw, info(raw, content_type='application/xhtml+xml'), LIMITS)
    assert records(result) == []
    assert result['provenance']['structured_data']['omissions']['invalid_json'] == 1
