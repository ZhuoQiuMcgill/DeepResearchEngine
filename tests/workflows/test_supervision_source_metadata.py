"""Selected-source limitations survive the existing agent input contract."""
from copy import deepcopy

from deepresearch.workflows.components.source_access import source_descriptor, source_extraction_feedback
from tests.workflows.test_source_access import RetainedPort
from tests.toolset.test_html_structured_data import extract, markup
from tests.toolset.test_html_graphics import extract as extract_graphics, PATH


def supervision():
    return {'method': 'isolated-render/1', 'trigger': 'thin_script_html',
        'decision': 'static_retained_after_termination', 'selected_stage': 'static',
        'network_usage_complete': False, 'known_http_request_count': 2,
        'known_http_response_count': 2, 'known_decoded_body_bytes': 1203651,
        'render_request_grant': 38, 'render_decoded_byte_grant': 32350781,
        'render_outcome': 'terminated', 'render_error_code': 'MEMORY_LIMIT',
        'render_http_request_count': None, 'render_http_response_count': None,
        'render_decoded_body_bytes': None}


def test_static_fallback_and_unknown_traffic_are_visible_without_unread_source_values():
    source = RetainedPort(text='UNREAD_SOURCE_VALUE').source
    source.provenance['fetch_supervision'] = supervision()
    before = deepcopy(source.provenance)
    descriptor = source_descriptor(source)
    feedback = source_extraction_feedback(source)
    assert descriptor['fetch_supervision'] == supervision()
    assert len(feedback) == 1
    assert 'static_retained_after_termination' in feedback[0]
    assert '"render_http_request_count":null' in feedback[0]
    assert 'UNREAD_SOURCE_VALUE' not in str(descriptor) + str(feedback)
    assert source.provenance == before


def test_supervision_graphics_jsonld_and_repair_fit_distiller_feedback_limits():
    proposal = extract(markup(*['{}'] * 32))
    source = RetainedPort(text=proposal['text'].decode()).source
    source.provenance.update(proposal['provenance'])
    graphics, _ = extract_graphics('<svg aria-label="Undisclosed">' + PATH + '</svg>')
    source.provenance['html_extraction'] = graphics['provenance']['html_extraction']
    source.provenance['fetch_supervision'] = supervision()
    feedback = source_extraction_feedback(source) + ['Prior output failed quotation validation.']
    assert len(feedback) <= 8
    assert all(len(item) <= 1024 for item in feedback)
    assert any('html_graphics' in item for item in feedback)
    assert any('structured_data' in item for item in feedback)
    assert any('fetch_supervision' in item for item in feedback)
