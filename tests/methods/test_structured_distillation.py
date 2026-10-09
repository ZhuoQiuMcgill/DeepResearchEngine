"""Whole JSON-LD records travel through real archive/read/distillation boundaries."""
import json

import pytest

from tests.toolset.test_html_structured_data import extract, markup


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', [False, True])
async def test_declared_record_and_coverage_reach_distiller_and_synthesis(tmp_path, monkeypatch, repair):
    from deepresearch.engine.contracts import SnapshotProposal, ToolExecutionResult
    from tests.methods.test_parallel_baseline import (
        ALPHA, Document, _configured, _distillation, _request, _settle, _events, _json)
    from tests.methods.test_selection_baseline import _decision
    from tests.methods.test_systemic_baseline import valid_report
    record = '{"@type":"Dataset","name":"Trial A","conditions":{"temperature":21,"unit":"C"},"status":"provisional"}'
    proposal = extract(markup(record))
    def respond(role, value, ordinal):
        if role == 'baseline.selector':
            return _decision(value)
        if role == 'baseline.distiller':
            assert '"origin":"publisher_declared_not_verified"' in value['feedback'][0]
            assert record in ''.join(s['text'] for s in value['segments'])
            assert 'Trial A' not in value['feedback'][0]
            if repair and ordinal == 1:
                return {'invalid': 'controlled role contract failure'}
            result = _distillation(value)
            for finding in result['findings']:
                finding.update(quote=record, claim='The publisher-declared dataset record states Trial A is provisional at 21 C.')
            return result
        if role == 'baseline.writer':
            return valid_report(value)
    async with _configured(tmp_path, monkeypatch,
        {ALPHA: Document(proposal['text'].decode(), media_type='text/html')}, respond=respond) as h:
        original_execute = h.engine.executor.execute
        async def tool(definition, arguments, context, plan):
            if definition.name != 'web.fetch':
                return await original_execute(definition, arguments, context, plan)
            plan.assert_recorded()
            receipt = (await plan.snapshot_store.commit(context, plan.operation_id, plan.scope,
                SnapshotProposal(proposal['original'], proposal['text'], proposal['index'], proposal['provenance']))).unwrap()
            result = ToolExecutionResult(definition.ref, context.descriptor(), 'succeeded',
                process={'dispatched': True, 'cleanup': {'complete': True}})
            result.result = {'snapshot_ref': receipt.snapshot_ref.to_dict(),
                'line_count': len(json.loads(proposal['index'])['lines']), 'page_count': None,
                'provenance': proposal['provenance']}
            result.persistence = {'required': True, 'commit_state': 'committed', 'operation_id': plan.operation_id,
                                  'receipt': receipt.to_dict()}
            return result
        monkeypatch.setattr(h.engine.executor, 'execute', tool)
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={'method_revision': 12})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == 'succeeded', view.error
        assert len(h.role_calls('distiller')) == 1 + repair
        evidence = h.role_calls('analyst')[0]['input']['evidence']
        assert record in evidence and 'publisher_declared_not_verified' in evidence
        event = next(e for e in await _events(h.service, view.run_id) if e['kind'] == 'workflow.evidence.distilled')
        validation = await _json(h.service, view.run_id, event['payload']['validation_ref'])
        assert all(f['quote'] == record for f in validation['distillation']['findings'])
        assert not validation['validation_changes']
