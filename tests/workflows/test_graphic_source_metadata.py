"""Coverage reaches source consumers without exposing unread graphical metadata."""
from copy import deepcopy
import json

from deepresearch.workflows.components.source_access import source_descriptor, source_extraction_feedback
from tests.workflows.test_source_access import RetainedPort


def test_graphic_coverage_survives_but_unread_details_do_not_leak():
    source = RetainedPort(text='Recorded text').source
    graphics = {'method': 'selected-svg-labels/1', 'semantic_verification': False,
        'selection_bound': True, 'coverage_complete': True, 'selected_svg_count': 2,
        'labelled_svg_count': 1, 'unresolved_svg_count': 1, 'unassessed_candidate_count': 0,
        'author_hidden_svg_count': 0, 'presentational_svg_count': 0,
        'entries_truncated': False,
        'entries': [{'selected_dom_path': '/unread/table', 'private_label': 'UNREAD CONTENT'}]}
    source.provenance['html_extraction'] = {'graphics': graphics}
    original = deepcopy(source.provenance)
    descriptor = source_descriptor(source)
    feedback = source_extraction_feedback(source)
    assert descriptor['html_extraction']['graphics']['unresolved_svg_count'] == 1
    assert descriptor['html_extraction']['graphics']['labelled_svg_count'] == 1
    assert len(feedback) == 1 and '"unresolved_svg_count":1' in feedback[0]
    assert 'UNREAD CONTENT' not in json.dumps(descriptor) + json.dumps(feedback)
    assert '/unread/table' not in json.dumps(descriptor) + json.dumps(feedback)
    assert source.provenance == original


def test_historical_sources_without_graphic_audit_do_not_gain_a_coverage_claim():
    source = RetainedPort(text='Recorded text').source
    assert not source_extraction_feedback(source)
    assert source_descriptor(source)['html_extraction'] is None
