"""Source values require archive reads; metadata cannot masquerade as full text."""
from copy import deepcopy
import json

from deepresearch.workflows.components.source_access import source_descriptor, source_extraction_feedback, source_span_origin
from deepresearch.methods.baseline.stages.distillation import content_hint
from tests.workflows.test_source_access import RetainedPort
from tests.toolset.test_html_structured_data import extract, markup


def test_declared_data_values_are_absent_until_read_and_diagnostics_do_not_mutate():
    raw = markup('{"name":"UNREAD UNIQUE ENTITY","price":12345.6789}')
    proposal = extract(raw)
    source = RetainedPort(text=proposal['text'].decode()).source
    source.provenance.update(proposal['provenance'])
    original = deepcopy(source.provenance)
    descriptor = source_descriptor(source)
    feedback = source_extraction_feedback(source)
    assert descriptor['structured_data']['origin'] == 'publisher_declared_not_verified'
    assert descriptor['structured_data']['entries'][0]['start_byte'] > 0
    assert len(feedback) == 2 and '"retained_script_count":1' in feedback[0]
    assert 'entries' not in feedback[0]
    assert 'UNREAD UNIQUE ENTITY' not in json.dumps(descriptor) + json.dumps(feedback)
    assert '12345.6789' not in json.dumps(descriptor) + json.dumps(feedback)
    assert source.provenance == original


def test_long_declared_data_cannot_upgrade_short_body_or_followup_metadata_to_substantive():
    result = extract(markup(json.dumps({'description': 'Declared data. ' * 300}),
        body='<p>A short étude remains short.</p>'.encode()))
    text = result['text'].decode()
    assert len(text.encode()) > 2048
    assert content_hint({'segments': [{'text': text, 'start_byte': 0}]}, provenance=result['provenance']) == 'abstract'
    cutoff = result['provenance']['structured_data']['base_text_bytes']
    assert content_hint({'segments': [{'text': result['text'][cutoff:].decode(), 'start_byte': cutoff}]},
        provenance=result['provenance']) == 'abstract'


def test_delivered_span_annotation_does_not_infer_unread_entity_or_currency():
    from deepresearch.methods.baseline.stages.evidence_delivery import _block, _quote_units
    from deepresearch.engine.contracts import digest_bytes
    result = extract(markup('{"name":"UNREAD ENTITY","offers":{"priceCurrency":"CAD","price":123.45}}'))
    source = RetainedPort(text=result['text'].decode()).source
    source.provenance.update(result['provenance'])
    entry = result['provenance']['structured_data']['entries'][0]
    a = result['text'].index(b'123.45'); b = a + 6
    seg = {'segment_id': 'seg', 'text': '123.45', 'start_byte': a, 'end_byte': b,
        'text_sha256': digest_bytes(b'123.45'), 'read_action_id': 'read',
        'range': {'kind': 'lines', 'start': 1, 'end_exclusive': 2}}
    access = {'segments': [seg], 'read_bytes': 6, 'complete': False}
    record = {'chunk_id': 'chunk', 'segment_ids': ['seg'], 'content_kind': 'abstract',
        'distillation': {'summary': 'Declared number', 'limitations': [], 'findings': [
            {'question': 'Observed value?', 'claim': 'A declared value is 123.45.', 'segment_id': 'seg', 'quote': '123.45'}]}}
    units = _quote_units([record], access)
    delivered = _block(source, access, [record], units)
    assert units[0]['text'] == '123.45' and units[0]['start_byte'] == a
    assert 'publisher_declared_structured_data' in delivered
    assert 'not a source quotation' in delivered
    assert 'UNREAD ENTITY' not in delivered and 'CAD' not in delivered
    feedback = source_extraction_feedback(source)
    assert any(str(entry['start_byte']) in f and 'not rendered body text' in f for f in feedback)
    assert source_span_origin(source, 0, b)['kind'] == 'mixed_body_and_structured_supplement'
    assert source_span_origin(source, 0, 1)['kind'] == 'extracted_body'
    assert source_span_origin(source, entry['start_byte'] - 1, entry['start_byte'])['kind'] == 'structured_data_host_framing'


def test_graphics_plus_many_script_ranges_fit_existing_role_feedback_contract():
    from deepresearch.engine.toolset.html_graphics import diagnostic_schema
    from tests.toolset.test_html_graphics import extract as extract_graphics, PATH
    from deepresearch.agent_catalog import AgentCatalog
    from jsonschema import validate
    proposal = extract(markup(*['{}'] * 32))
    source = RetainedPort(text=proposal['text'].decode()).source
    source.provenance.update(proposal['provenance'])
    graphics, _ = extract_graphics('<svg aria-label="Undisclosed">' + PATH + '</svg>')
    source.provenance['html_extraction'] = graphics['provenance']['html_extraction']
    feedback = source_extraction_feedback(source)
    assert len(feedback) <= 6
    assert all(len(value) <= 1024 for value in feedback)
    assert any('html_graphics' in value for value in feedback)
    assert any('structured_data' in value for value in feedback)
