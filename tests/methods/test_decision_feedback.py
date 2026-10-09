"""Invalid decisions need actionable feedback without changing their evidence."""
from copy import deepcopy

import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.methods.baseline.contracts import ResearchPlan
from deepresearch.methods.baseline.evidence_contracts import DistilledAnalysis
from deepresearch.methods.baseline.stages.roles import validate_findings
from tests.methods.test_parallel_baseline import ALPHA, PLAN, _analysis, _configured, _lines, _request, _settle
from tests.methods.test_selection_baseline import _decision
from tests.methods.test_systemic_baseline import valid_report


@pytest.mark.parametrize('fault,field,kind', [
    ('unknown', 'source_ids', 'unknown_source_ids'),
    ('duplicate', 'source_ids', 'duplicate_source_ids'),
    ('question', 'question', 'unplanned_question'),
    ('blank', 'claim', 'blank_text'),
])
def test_finding_feedback_identifies_the_field_and_permitted_values(fault, field, kind):
    allowed=['original.a', 'additional.b']
    data=_analysis({'available_source_ids':allowed, 'plan':PLAN})
    if fault=='unknown':data['findings'][1]['source_ids']=['original.a', 'unknown.b']
    if fault=='duplicate':data['findings'][1]['source_ids']=['original.a', 'original.a']
    if fault=='question':data['findings'][1]['question']='Unplanned question'
    if fault=='blank':data['findings'][1]['claim']='  '
    value=DistilledAnalysis.model_validate(data)
    before=deepcopy(value.to_dict())
    with pytest.raises(EngineError) as caught:
        validate_findings(value,allowed,ResearchPlan.model_validate(PLAN))
    details=caught.value.details
    assert details['allowed_source_ids']==allowed
    assert details['allowed_questions']==PLAN['questions']
    assert details['validation_errors'][0]['path']==['findings',1,field]
    assert details['validation_errors'][0]['type']==kind
    if fault=='unknown':assert details['validation_errors'][0]['unknown_source_ids']==['unknown.b']
    assert value.to_dict()==before  # Host never guesses a replacement citation.


@pytest.mark.asyncio
@pytest.mark.parametrize('corrects', [True,False])
async def test_recorded_repair_receives_binding_diagnostic_and_stays_bounded(tmp_path,monkeypatch,corrects):
    def respond(role,value,ordinal):
        if role=='baseline.selector':return _decision(value)
        if role=='baseline.analyst':
            output=_analysis(value)
            if ordinal==1 or not corrects:
                output['findings'][0]['source_ids']=['foreign.source']
            else:
                feedback=value['repair']['errors'][0]['details']
                assert feedback['allowed_source_ids']==value['available_source_ids']
                assert feedback['validation_errors'][0]['unknown_source_ids']==['foreign.source']
            return output
        if role=='baseline.writer':return valid_report(value)
        return None
    async with _configured(tmp_path,monkeypatch,{ALPHA:_lines('VALID')},respond=respond) as h:
        request=_request(max_sources=1,max_rounds=1,min_substantive_sources=1).model_copy(update={'method_revision':12})
        view=await _settle(h.service,(await h.service.start_run(request)).run_id)
        assert view.status==('succeeded' if corrects else 'failed'),view.error
        calls=h.role_calls('analyst')
        assert len(calls)==2
        assert calls[0]['input']['evidence']==calls[1]['input']['evidence']
        assert calls[0]['input']['available_source_ids']==calls[1]['input']['available_source_ids']
        assert 'foreign.source' in calls[1]['input']['repair']['previous_output']
        if not corrects:assert view.error['code']=='INVALID_EVIDENCE_REFERENCE'
