"""An admitted 40-source run must survive containers and frontend projection."""
import httpx
import pytest
from pydantic import ValidationError

from deepresearch.engine.contracts import canonical_json
from deepresearch.interfaces.http import create_app
from deepresearch.interfaces.http.research import install_research_routes
from deepresearch.workflows.contracts import FetchManifest, SourceManifest, ResearchQuality
from tests.application.test_parallel_roles import environment, start, terminal


def fetch_items(count):
    return [{'item_id': f'source-{n}', 'url': f'https://example.test/source/{n}'} for n in range(count)]


def sources(count):
    return {'items': [{**item, 'status': 'failed', 'recording_status': 'complete',
                       'error': {'code': 'CONTROLLED_FETCH_FAILURE'}} for item in fetch_items(count)]}


def quality(count):
    return {'status': 'insufficient', 'evidence_sufficient': False, 'attempted_sources': count,
            'substantive_sources': 0, 'fully_read_sources': 0, 'distilled_sources': 0}


@pytest.mark.parametrize('count', [0, 32, 33, 40])
def test_whole_run_attempts_fit_fetch_source_and_quality_containers(count):
    fetch = FetchManifest(items=fetch_items(count))
    saved = SourceManifest.model_validate(sources(count))
    result = ResearchQuality.model_validate(quality(count))
    assert len(fetch.items) == len(saved.items) == result.attempted_sources == count
    assert SourceManifest.model_validate_json(saved.model_dump_json()) == saved


def test_success_counters_can_reach_the_admitted_source_ceiling():
    result = ResearchQuality.model_validate({**quality(40), 'status': 'sufficient',
        'evidence_sufficient': True, 'substantive_sources': 40, 'fully_read_sources': 40, 'distilled_sources': 40})
    assert result.to_dict()['distilled_sources'] == 40


def test_oversized_containers_still_fail_without_silently_clamping():
    for model, value in [(FetchManifest, {'items': fetch_items(41)}), (SourceManifest, sources(41))]:
        with pytest.raises(ValidationError):
            model.model_validate(value)
    for counter in ['attempted_sources', 'substantive_sources', 'fully_read_sources', 'distilled_sources']:
        with pytest.raises(ValidationError):
            ResearchQuality.model_validate({**quality(40), counter: 41})


class CapacityMethod:
    async def run(self, context, task_input, parameters):
        manifest = SourceManifest.model_validate(sources(40))
        coverage = ResearchQuality.model_validate(quality(40))
        await context.port.update(sources=manifest.to_dict(), quality=coverage.to_dict())
        ref = await context.port.publish(canonical_json(manifest.to_dict()), 'application/json', 'sources.json')
        return {'report_ref': ref}


@pytest.mark.asyncio
async def test_forty_recorded_attempts_survive_http_state_events_and_reopen(tmp_path):
    async with environment(tmp_path, CapacityMethod()) as (engine, service):
        view = await terminal(service, (await start(service, 'forty-sources')).run_id)
        assert view.status == 'succeeded', view.error
        assert len(view.sources.items) == view.quality.attempted_sources == 40
        assert all(s.status == 'failed' for s in view.sources.items)
        app = create_app(engine=engine)
        app.state.research_service = service
        install_research_routes(app)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
                response = await client.get(f'/api/v1/research-runs/{view.run_id}/sources')
                assert response.status_code == 200
                assert SourceManifest.model_validate(response.json()) == view.sources
                response = await client.get(f'/api/v1/research-runs/{view.run_id}')
                assert response.status_code == 200 and response.json()['quality']['attempted_sources'] == 40
                schema = (await client.get('/openapi.json')).json()['components']['schemas']
                assert schema['SourceManifest']['properties']['items']['maxItems'] == 40
                assert schema['ResearchQuality']['properties']['attempted_sources']['maximum'] == 40
            rows = (await service.events(view.run_id, limit=100))['events']
            finished = next(r['event']['payload'] for r in rows if r['event']['kind'] == 'workflow.finished')
            assert finished['quality_status'] == 'insufficient'
            assert finished['evidence_sufficient'] is False
        finally:
            assert (await app.state.run_service.close()).complete
    async with environment(tmp_path, CapacityMethod()) as (_, restored):
        reopened = await restored.get_run(view.run_id)
        assert reopened.sources == view.sources and reopened.quality == view.quality
        assert reopened.terminal_event_receipt == view.terminal_event_receipt
        assert not reopened.active
