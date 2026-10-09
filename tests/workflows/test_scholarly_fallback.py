"""Settled bad metadata is local to one read-only discovery backend."""
import json
import sys
import pytest
from deepresearch.engine.contracts import EngineError
from deepresearch.workflows.components.retrieval import _must_stop,retrieve_candidates
from tests.workflows.test_retrieval import SearchPort,context,web,settled_search_unavailable


def failed():
    result=settled_search_unavailable()
    result['tool']={'name':'scholar.crossref.search','revision':2}
    result['error']['code']='SCHOLAR_PROTOCOL_ERROR'
    result['error']['details']={'provider':'crossref','reason':'invalid_provider_response','http_status':200,'observed_requests':1,'observed_responses':1}
    result['observations']={'scholarly_attempt':{'provider':'crossref','http_status':200,'http_request_count':1,'http_response_count':1}}
    return result


@pytest.mark.asyncio
async def test_bad_metadata_keeps_prior_results_and_allows_next_backend():
    result=failed()
    def respond(name,args):
        return result if name=='scholar.crossref.search' else web([('Topic','https://example.org/article')],args['query'])
    port=SearchPort(respond)
    items,entries=await retrieve_candidates(context(port),['Topic'],['scholar.crossref.search','web.search'],5,
        topic='Topic',recovery_limit=0,rewrite_queries=False,screen_candidates=False)
    assert [x.url for x in items]==['https://example.org/article']
    assert [x['status'] for x in entries]==['failed','succeeded']
    assert port.artifact(entries[0]['artifact_ref'])==result
    assert len(port.reads)==2


@pytest.mark.parametrize('path,value',[
    (('error','commit_state'),'unknown'),(('persistence','commit_state'),'unknown'),
    (('recording','status'),'incomplete'),(('process','cleanup','complete'),False),
    (('process','exit_code'),2),(('process','termination_reason'),'deadline'),
    (('process','dispatched'),False),(('error','details','observed_responses'),0),
    (('error','details','http_status'),None),(('error','details','reason'),'transport_unavailable'),
    (('error','code'),'INVALID_ARGUMENT'),(('tool','name'),'web.fetch'),
    (('status',),'timed_out'),(('status',),'unknown'),(('error','retryable_delivery'),True),
    (('observations','scholarly_attempt','http_response_count'),0),
])
def test_unknown_or_unsettled_failures_still_stop(path,value):
    result=failed();target=result
    for part in path[:-1]: target=target[part]
    target[path[-1]]=value
    with pytest.raises(EngineError):_must_stop(result,'scholar.crossref.search')


@pytest.mark.asyncio
async def test_native_worker_records_bad_metadata_and_continues_with_shared_budget(tmp_path, monkeypatch):
    from deepresearch.application.platform import ResearchPlatformPort
    from deepresearch.application.research_runs import LiveResearchRun
    from deepresearch.engine import Engine, EngineSettings, RunOptions
    from deepresearch.engine.contracts import ToolRef
    from deepresearch.workflows import ResearchRunView
    script = '''
import json,sys
from deepresearch.engine.toolset import scholarly
import deepresearch.engine.toolset.search as search_module
from deepresearch.engine.toolset.common import encode
from deepresearch.engine.toolset.worker import run
body=encode({'status':'ok','message':{'total-results':1,'items':[{'title':['Topic'],'DOI':'not-a-doi'}]}})
def respond(*args,on_headers,**kwargs):
    facts={'http_status':200,'content_type':'application/json','http_request_count':1,
        'http_response_count':1,'response_transfer_bytes':len(body),'response_decoded_bytes':len(body)}
    on_headers(facts,[])
    return body,facts,None
scholarly.request_body=respond
payload=''' + repr(web([('Topic', 'https://example.org/article')], 'Topic')) + '''
def search(arguments,plan,timeout,revision):
    return payload,{'backend_attempts':[],'disabled_backends':plan['disabled_backends']},{'http_request_count':0,'http_response_count':0,'monetary_cost':None},None
search_module.search=search
request=json.loads(sys.stdin.buffer.read())
response,code=run(request,request['tool']['name'],request['tool']['revision'])
sys.stdout.buffer.write(encode(response));sys.stdout.buffer.flush();sys.exit(code)
'''
    engine = (await Engine.open(EngineSettings(workspace=tmp_path, storage_root=tmp_path / 'store'))).unwrap()
    session = ctx = None
    try:
        dispatched = []
        native = engine.executor.runner.run
        async def controlled(argv, payload, **kwargs):
            dispatched.append(json.loads(payload))
            return await native([sys.executable, '-c', script], payload, **kwargs)
        monkeypatch.setattr(engine.executor.runner, 'run', controlled)
        refs = (ToolRef('scholar.crossref.search', 2), ToolRef('web.search', 2))
        session = (await engine.open_workflow_session(tools=refs, invocation_rules=(),
            options=RunOptions(timeout_seconds=30))).unwrap()
        view = ResearchRunView(run_id=session.context.run_id, method_id='metadata-test', method_revision=1,
            client_request_id='metadata-test', accepted_at='2026-10-03T00:00:00Z', status='running', active=True)
        port = ResearchPlatformPort(engine, LiveResearchRun(session, view, 'sha256:' + '0' * 64, refs), {})
        ctx = context(port); ctx.run_id = view.run_id
        items, entries = await retrieve_candidates(ctx, ['Topic'], [r.name for r in refs], 5,
            topic='Topic', recovery_limit=0, rewrite_queries=False, screen_candidates=False)
        assert [item.url for item in items] == ['https://example.org/article']
        assert [entry['status'] for entry in entries] == ['failed', 'succeeded']
        saved = json.loads(await port.read_artifact(entries[0]['artifact_ref']))
        assert saved['error']['code'] == 'SCHOLAR_PROTOCOL_ERROR'
        assert saved['error']['details']['reason'] == 'invalid_provider_response'
        assert saved['observations']['scholarly_attempt']['http_status'] == 200
        assert saved['recording'] == {'status': 'complete', 'error': None}
        assert saved['process']['cleanup']['complete'] and saved['process']['exit_code'] == 3
        assert port.failure is None and len(dispatched) == 2
        assert session.context.ledger.used['tool_calls'] == 2
        assert len({x['invocation']['attempt_id'] for x in dispatched}) == 2
        assert not engine.executor.runner._active
    finally:
        if ctx is not None:
            assert (await ctx.hooks.close()).complete
        if session is not None:
            assert (await session.close()).complete
        assert (await engine.close()).complete
