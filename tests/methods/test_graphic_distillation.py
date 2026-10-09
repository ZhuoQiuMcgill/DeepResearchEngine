"""Actual archive/role-input/repair/synthesis boundaries for graphical sources."""
import pytest

from tests.toolset.test_html_graphics import extract, PATH


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', [False, True])
async def test_authored_labels_and_coverage_reach_distiller_and_analyst(tmp_path, monkeypatch, repair):
    from deepresearch.engine.contracts import SnapshotProposal, ToolExecutionResult
    from tests.methods.test_parallel_baseline import (
        ALPHA, Document, _configured, _distillation, _request, _settle, _events, _json)
    from tests.methods.test_selection_baseline import _decision
    from tests.methods.test_systemic_baseline import valid_report

    extracted, _ = extract('<svg aria-label="Not recorded">' + PATH + '</svg> / <svg>' + PATH + '</svg>')
    def respond(role, value, ordinal):
        if role == 'baseline.selector':
            return _decision(value)
        if role == 'baseline.distiller':
            assert '"unresolved_svg_count":1' in value['feedback'][0]
            assert 'selected_dom_path' not in value['feedback'][0]
            if repair and ordinal == 1:
                return {'invalid': 'controlled role contract failure'}
            result = _distillation(value)
            for finding in result['findings']:
                finding.update(quote='Not recorded', claim='The declared graphic label is Not recorded.')
            result['findings'].append({**result['findings'][0], 'quote': 'SVG graphic: meaning unresolved'})
            return result
        if role == 'baseline.writer':
            return valid_report(value)

    async with _configured(tmp_path, monkeypatch, {ALPHA: Document(extracted['text'].decode(), media_type='text/html')}, respond=respond) as h:
        original_execute = h.engine.executor.execute
        async def tool(definition, arguments, context, plan):
            if definition.name != 'web.fetch':
                return await original_execute(definition, arguments, context, plan)
            plan.assert_recorded()
            receipt = (await plan.snapshot_store.commit(context, plan.operation_id, plan.scope,
                SnapshotProposal(extracted['original'], extracted['text'], extracted['index'], extracted['provenance']))).unwrap()
            import json
            result = ToolExecutionResult(definition.ref, context.descriptor(), 'succeeded',
                process={'dispatched': True, 'cleanup': {'complete': True}})
            result.result = {'snapshot_ref': receipt.snapshot_ref.to_dict(),
                'line_count': len(json.loads(extracted['index'])['lines']), 'page_count': None,
                'provenance': extracted['provenance']}
            result.persistence = {'required': True, 'commit_state': 'committed', 'operation_id': plan.operation_id,
                                  'receipt': receipt.to_dict()}
            return result
        monkeypatch.setattr(h.engine.executor, 'execute', tool)
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={'method_revision': 12})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == 'succeeded', view.error
        assert len(h.role_calls('distiller')) == 1 + repair
        evidence = h.role_calls('analyst')[0]['input']['evidence']
        assert 'Not recorded' in evidence and '"unresolved_svg_count":1' in evidence
        assert 'SVG graphic: meaning unresolved' not in evidence and 'selected_dom_path' not in evidence
        event = next(e for e in await _events(h.service, view.run_id) if e['kind'] == 'workflow.evidence.distilled')
        validated = await _json(h.service, view.run_id, event['payload']['validation_ref'])
        assert len(validated['distillation']['findings']) == 2
        assert all(f['quote'] == 'Not recorded' for f in validated['distillation']['findings'])
        assert sum(c.get('action') == 'excluded_unverified_quote' for c in validated['validation_changes']) == 1
