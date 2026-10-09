"""Parent fetch supervision: real extraction, packed envelopes, controlled processes.

No acquisition, models, Engine, storage or SQLite are used. A returned prepared
proposal is the only object eligible for the caller's later snapshot commit.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import socket
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from deepresearch.engine.toolset import ToolCatalog, browser_capture, fetch_supervisor, fetch_transport, fetch_v2
from deepresearch.engine.toolset.article_extraction import extract_source
from deepresearch.engine.toolset.common import LIMITS, ToolFault, digest, encode, strict_json
from deepresearch.engine.toolset.fetch_policy import render_signal
from deepresearch.engine.toolset.process import ProcessOutcome
from deepresearch.engine.toolset.retrieval import build_index, pack_component, unpack_component
from tests.toolset.test_fetch_v2 import ARTICLE, SHELL, URL, info

COUNTS = ('http_request_count', 'http_response_count', 'decoded_body_bytes')
OBSERVATIONS = ('http_status', 'redirects', 'final_url', 'extraction_version', 'representation', 'fetch_attempts')
BACKEND = 'playwright/1.63.0/chromium'
LEAD = 'The study recorded 17 participants and a 12 minute observation period. These measurements describe the original sample and its limitations.'
FACT = 'The later experiment measured 23 participants during a 31 minute follow-up period, with a separately reported confidence interval.'
BODY = ('<h1>Measured observations</h1><p>' + LEAD + '</p>'
        '<p>Consult <a href="/methods?literal=+&amp;encoded=%2B">the original methods</a> '
        'for the protocol and the stated sampling limitations.</p>'
        '<ul><li>Control group: 7 participants.</li><li>Observed group: 10 participants.</li></ul>'
        '<table><tr><th>Group</th><th>Minutes</th></tr><tr><td>Control</td><td>12</td></tr></table>'
        '<pre><code>rate = count / minutes</code></pre>')
RECORD = '{"@context":"https://schema.org","@type":"Dataset","name":"Original observations","identifier":"sample-17","measurement":{"value":12,"unit":"minutes"}}'
SECOND_RECORD = '{"@type":"Dataset","name":"Additional observations","identifier":"sample-23"}'


def html_body(body=BODY, *, scripts=True, records=()):
    # The script is inert fixture bytes; a genuine >64 KiB script-dominated
    # document is necessary to exercise the production thin-page trigger.
    padding = '<script src="/bundle.js">/*' + 'x' * 70000 + '*/</script>' if scripts else ''
    structured = ''.join('<script type="application/ld+json">' + record + '</script>' for record in records)
    return ('<html><head><title>Measured observations</title>' + padding + structured +
            '</head><body><article>' + body + '</article></body></html>').encode()


@pytest.fixture(autouse=True)
def prohibit_acquisition(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Supervisor tests must not acquire network resources or launch a browser')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(fetch_transport.httpx, 'Client', forbidden)
    monkeypatch.setattr(fetch_transport, 'Session', forbidden)
    monkeypatch.setattr(browser_capture, 'sync_playwright', forbidden)


@dataclass
class Stage:
    body: bytes = field(default_factory=html_body)
    counts: tuple[int | None, int | None, int | None] | None = None
    final_url: str = URL
    failed_resources: int = 0
    error: str | None = None
    scope: str | None = 'fetch'
    termination: str | None = None
    cleanup: bool = True
    elapsed: float = 1
    stderr_bytes: int = 11
    stdout_bytes: int | None = None
    mutate: object = None
    raw: bytes | None = None
    deactivate: str | None = None
    pid: int | None = 101


class ParentContext:
    def __init__(self, clock, remaining=60):
        self.clock = clock
        self.ends_at = clock.now + remaining
        self.failure = None

    def remaining_seconds(self):
        return max(0, self.ends_at - self.clock.now)

    def assert_active(self):
        if self.failure:
            raise ToolFault(self.failure, 'Controlled inactive parent context', status='cancelled')
        if self.remaining_seconds() <= 0:
            raise ToolFault('DEADLINE_EXCEEDED', 'Parent deadline elapsed', status='timed_out')


def proposal_for(stage, kind, counts):
    proposal = extract_source(stage.body, info(stage.body, final_url=stage.final_url,
        http_request_count=counts[0], http_response_count=counts[1]), LIMITS)
    provenance = proposal['provenance']
    provenance.update(representation='rendered_dom' if kind == 'render' else 'content_decoded',
        transport='curl_cffi/0.16.3', capture=None,
        fetch_attempts=[attempt(kind, counts)])
    if kind == 'render':
        provenance.update(chosen_charset='utf-8', charset_source='browser', capture={
            'backend': BACKEND, 'captured_at': '2026-10-04T00:00:00Z',
            'relayed_requests': counts[0], 'blocked_requests': 0,
            'failed_resources': stage.failed_resources, 'dom_bytes': len(stage.body),
            'wait_until': 'domcontentloaded', 'settle_ms': 500})
    return proposal


def attempt(kind, counts, error=None):
    return {'backend': BACKEND if kind == 'render' else 'curl_cffi/0.16.3',
        'outcome': 'failed' if error else 'returned', 'elapsed_ms': 100,
        'http_status': 200, 'error_code': error, **dict(zip(COUNTS, counts))}


class Scenario:
    def __init__(self, monkeypatch, stages, *, limits=None, remaining=60, mode='auto'):
        self.clock = SimpleNamespace(now=1000.0)
        self.origin = datetime.now(timezone.utc)
        scenario = self

        class ClockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return scenario.origin + timedelta(seconds=scenario.clock.now - 1000)

        monkeypatch.setattr(fetch_supervisor, 'time', SimpleNamespace(monotonic=lambda: self.clock.now))
        monkeypatch.setattr(fetch_supervisor, 'datetime', ClockDateTime)
        monkeypatch.setattr(fetch_supervisor, 'deadline_after', lambda seconds:
            (self.origin + timedelta(seconds=self.clock.now - 1000 + seconds)).isoformat())
        self.context = ParentContext(self.clock, remaining)
        self.limits = {**LIMITS, **(limits or {})}
        self.definition = ToolCatalog().resolve('web.fetch', 3).unwrap()
        self.request = {'schema_version': 1, 'message_type': 'worker_request',
            'request_id': 'worker_static_fixture', 'tool': {'name': 'web.fetch', 'revision': 3},
            'invocation': {'run_id': 'run_fixture', 'root_run_id': 'run_fixture',
                'correlation_id': 'correlation_fixture', 'action_id': 'action_fixture',
                'attempt_id': 'attempt_fixture', 'context_kind': 'standalone_tool'},
            'arguments': {'url': URL, 'mode': mode},
            'execution': {'deadline_utc': (self.origin + timedelta(seconds=remaining)).isoformat(), 'limits': self.limits.copy()},
            'plan': {'kind': 'fetch', 'operation_id': 'snapshot_fixture', 'representation': 'selected_capture',
                'extraction_config_ref': 'adaptive/2', 'normalization_version': 'lf/1'}}
        self.original_request = copy.deepcopy(self.request)
        self.stages = stages
        self.calls, self.rows, self.sent, self.eligible = [], [], [], []

    async def dispatch(self, request, payload, seconds, stdout_cap, stderr_cap):
        assert len(self.calls) < len(self.stages), 'Unexpected extra stage or retry'
        stage = self.stages[len(self.calls)]
        self.calls.append({'request': copy.deepcopy(request), 'payload': payload,
            'seconds': seconds, 'stdout_cap': stdout_cap, 'stderr_cap': stderr_cap,
            'started': self.clock.now})
        assert strict_json(payload, self.limits['stdin_bytes']) == request
        kind = request['plan']['stage']
        counts = stage.counts or (1, 1, len(stage.body))
        response = {key: copy.deepcopy(request[key]) for key in ('schema_version', 'request_id', 'tool', 'invocation')}
        response.update(message_type='worker_response', phase='failed' if stage.error else 'prepared',
            prepared=None, error=None, observations={}, usage={**dict(zip(COUNTS, counts)),
                'duration_ms': round(stage.elapsed * 1000), 'text_utf8_bytes': None, 'monetary_cost': None})
        if not stage.termination and stage.raw is None:
            if stage.error:
                details = {} if stage.scope is None else {'failure_scope': stage.scope}
                response['error'] = ToolFault(stage.error, 'Controlled settled extraction failure', details=details).wire('observed')
                response['observations'] = {'http_status': 200, 'redirects': [], 'final_url': stage.final_url,
                    'extraction_version': None, 'representation': None,
                    'fetch_attempts': [attempt(kind, counts, stage.error)]}
            else:
                proposal = proposal_for(stage, kind, counts)
                response['prepared'] = {'operation_id': request['plan']['operation_id'],
                    'proposal': {**proposal, **{key: pack_component(proposal[key]) for key in ('original', 'text', 'index')}}}
                response['observations'] = {key: copy.deepcopy(proposal['provenance'][key]) for key in OBSERVATIONS}
                response['usage']['text_utf8_bytes'] = len(proposal['text'])
            if stage.mutate:
                stage.mutate(response, request)
        self.sent.append(copy.deepcopy(response))
        data = stage.raw if stage.raw is not None else (b'partial renderer output' if stage.termination else encode(response))
        process = ProcessOutcome(exit_code=None if stage.termination else (3 if stage.error else 0),
            stdout=data, stdin_bytes=len(payload), stdout_bytes=len(data) if stage.stdout_bytes is None else stage.stdout_bytes,
            stderr_bytes=stage.stderr_bytes, termination_reason=stage.termination, cleanup_complete=stage.cleanup, pid=stage.pid,
            duration_ms=round(stage.elapsed * 1000), peak_job_memory_bytes=32 << 20,
            peak_process_memory_bytes=16 << 20)
        self.calls[-1]['process'] = process
        self.clock.now += stage.elapsed
        self.context.failure = stage.deactivate
        return process

    def run(self):
        async def execute():
            selected = await fetch_supervisor.supervise(self.request, self.definition, self.limits,
                self.context, self.dispatch, self.rows.append)
            if selected[2]['phase'] == 'prepared':
                self.eligible.append(selected[2]['prepared'])
            return selected
        return asyncio.run(execute())


def components(response):
    proposal = response['prepared']['proposal']
    return {key: unpack_component(proposal[key], LIMITS[cap]) for key, cap in
            (('original', 'raw_bytes'), ('text', 'text_bytes'), ('index', 'index_bytes'))}


def public_view(response):
    proposal = response['prepared']['proposal']
    index = strict_json(components(response)['index'], LIMITS['index_bytes'])
    return {'snapshot_ref': {'schema_version': 1, 'store_id': 'fixture', 'snapshot_id': 'selected'},
        'extraction_version': proposal['extraction_version'], 'normalization_version': proposal['normalization_version'],
        'line_count': len(index['lines']), 'page_count': proposal['provenance']['physical_page_count'],
        'provenance': proposal['provenance'], 'preview': ''}


def assert_selected(scenario, result, stage):
    process, request, response, selected_stage = result
    assert selected_stage == stage
    selected_index = 0 if stage == 'static' else 1
    assert process is scenario.calls[selected_index]['process']
    assert request == scenario.calls[selected_index]['request']
    assert request['invocation'] == scenario.original_request['invocation']
    assert request['plan']['operation_id'] == 'snapshot_fixture'
    assert scenario.request == scenario.original_request, 'Parent mutated the authorized request'
    assert len(scenario.eligible) == 1
    actual = components(response)
    original = components(scenario.sent[selected_index])
    assert actual == original, 'Parent merged or rewrote the selected capture components'
    assert actual['original'] == scenario.stages[selected_index].body
    provenance = response['prepared']['proposal']['provenance']
    for key, data in actual.items():
        assert provenance[key + '_sha256'] == digest(data)
        assert provenance[key + '_bytes'] == len(data)
    index = strict_json(actual['index'], LIMITS['index_bytes'])
    assert index == build_index(actual['text'], index.get('pages'))
    assert response['usage']['text_utf8_bytes'] == len(actual['text'])
    assert response['observations']['fetch_attempts'] == provenance['fetch_attempts']
    assert provenance['requested_url'] == URL
    assert provenance['final_url'] == scenario.stages[selected_index].final_url
    Draft202012Validator(scenario.definition.output_schema).validate(public_view(response))
    assert len(scenario.rows) == len(scenario.calls)
    for row, call in zip(scenario.rows, scenario.calls):
        assert row['stage'] == call['request']['plan']['stage']
        assert row['request_sha256'] == digest(call['payload'])
        assert row['response_sha256'] == digest(call['process'].stdout)
        assert row['cleanup_complete'] is call['process'].cleanup_complete
    return response, actual


def assert_rejected(scenario, codes):
    with pytest.raises(ToolFault) as caught:
        scenario.run()
    assert caught.value.code in codes
    assert scenario.eligible == [], 'A failed or uncertain stage exposed a committable proposal'
    assert len(scenario.rows) == len(scenario.calls), 'Actual process outcome was not observed'
    return caught.value


@pytest.mark.parametrize('body,mode', [(ARTICLE, 'auto'), (html_body(scripts=False), 'auto'),
    (html_body(), 'static')], ids=['substantive-article', 'no-scripts', 'explicit-static'])
def test_static_without_thin_signal_skips_renderer(monkeypatch, body, mode):
    scenario = Scenario(monkeypatch, [Stage(body=body)], mode=mode)
    response, _ = assert_selected(scenario, scenario.run(), 'static')
    assert len(scenario.calls) == 1
    assert response == scenario.sent[0]


def test_thin_static_triggers_and_preserved_new_facts_select_render(monkeypatch):
    scenario = Scenario(monkeypatch, [Stage(), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False), counts=(3, 2, 90000))])
    response, data = assert_selected(scenario, scenario.run(), 'render')
    assert render_signal(proposal_for(scenario.stages[0], 'static', (1, 1, len(scenario.stages[0].body))), {'mode': 'auto'}) == 'thin_script_html'
    assert LEAD.encode() in data['text'] and FACT.encode() in data['text']
    assert b'https://example.org/methods?literal=+&encoded=%2B' in data['text']
    assert b'rate = count / minutes' in data['text']
    diagnostic = response['observations']['fetch_supervision']
    assert diagnostic['decision'] == 'rendered_with_preservation'
    assert diagnostic['selected_stage'] == 'render' and diagnostic['network_usage_complete']
    assert response['usage']['http_request_count'] == 4
    assert response['usage']['http_response_count'] == 3
    assert response['usage']['decoded_body_bytes'] == len(scenario.stages[0].body) + 90000
    assert [row['stage'] for row in scenario.rows] == ['static', 'render']
    assert scenario.calls[0]['request']['request_id'] != scenario.calls[1]['request']['request_id']
    assert scenario.calls[0]['request']['invocation'] == scenario.calls[1]['request']['invocation']


@pytest.mark.parametrize('change,decision', [
    ('url', 'changed_final_url'), ('resource', 'resource_failures'), ('same', 'no_body_growth'),
    ('value', 'static_body_not_preserved'), ('link', 'static_body_not_preserved'),
    ('order', 'static_body_not_preserved'), ('repeat', 'no_new_authored_token'),
])
def test_render_cannot_replace_static_without_fidelity_and_growth(monkeypatch, change, decision):
    body = BODY + '<p>' + FACT + '</p>'
    final_url, failed = URL, 0
    if change == 'url':
        final_url = URL.replace('%2B', '%2b')
    elif change == 'resource':
        failed = 1
    elif change == 'same':
        body = BODY
    elif change == 'value':
        body = body.replace('17 participants', '19 participants')
    elif change == 'link':
        body = body.replace('literal=+&amp;encoded=%2B', 'literal=%20&amp;encoded=%2B')
    elif change == 'order':
        body = BODY.replace('<p>' + LEAD + '</p>', '') + '<p>' + FACT + '</p><p>' + LEAD + '</p>'
    elif change == 'repeat':
        body = BODY + '<p>' + LEAD + '</p>'
    scenario = Scenario(monkeypatch, [Stage(), Stage(body=html_body(body, scripts=False), final_url=final_url, failed_resources=failed)])
    response, data = assert_selected(scenario, scenario.run(), 'static')
    assert response['observations']['fetch_supervision']['decision'] == decision
    assert FACT.encode() not in data['text']
    assert response['usage']['http_request_count'] == 2
    assert len(response['observations']['fetch_attempts']) == 2


@pytest.mark.parametrize('records,selected,decision', [
    ((SECOND_RECORD, RECORD), 'render', 'rendered_with_preservation'),
    ((SECOND_RECORD,), 'static', 'structured_record_not_preserved'),
    ((RECORD.replace('"value":12', '"value":13'),), 'static', 'structured_record_not_preserved'),
    ((RECORD.replace('"unit":"minutes"', '"unit":"hours"'),), 'static', 'structured_record_not_preserved'),
])
def test_whole_jsonld_record_preservation_is_independent_of_script_ordinal(monkeypatch, records, selected, decision):
    scenario = Scenario(monkeypatch, [Stage(body=html_body(records=(RECORD,))),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False, records=records))])
    response, data = assert_selected(scenario, scenario.run(), selected)
    diagnostic = response['observations']['fetch_supervision']
    assert diagnostic['decision'] == decision
    structured = response['prepared']['proposal']['provenance']['structured_data']
    retained = [data['text'][entry['start_byte']:entry['end_byte']] for entry in structured['entries']]
    assert RECORD.encode() in retained
    assert structured['base_text_bytes'] < len(data['text'])
    if selected == 'render':
        assert retained == [SECOND_RECORD.encode(), RECORD.encode()]
        assert structured['entries'][1]['script_ordinal'] == 2
        assert FACT.encode() in data['text'][:structured['base_text_bytes']]


@pytest.mark.parametrize('termination,code', [('memory_limit', 'MEMORY_LIMIT'),
    ('deadline', 'DEADLINE_EXCEEDED'), ('stream_limit', 'LIMIT_EXCEEDED')])
def test_confirmed_render_termination_retains_static_and_unknown_aggregate_counts(monkeypatch, termination, code):
    scenario = Scenario(monkeypatch, [Stage(counts=(2, 2, 150000)), Stage(termination=termination)])
    response, data = assert_selected(scenario, scenario.run(), 'static')
    assert LEAD.encode() in data['text']
    provenance = response['prepared']['proposal']['provenance']
    diagnostic = provenance['fetch_supervision']
    assert diagnostic == response['observations']['fetch_supervision']
    assert diagnostic['decision'] == 'static_retained_after_termination'
    assert diagnostic['render_outcome'] == 'terminated' and diagnostic['render_error_code'] == code
    assert diagnostic['network_usage_complete'] is False
    for key, known in zip(COUNTS, (2, 2, 150000)):
        assert response['usage'][key] is None
        assert diagnostic['known_' + key] == known
        assert diagnostic['render_' + key] is None
        assert provenance['fetch_attempts'][-1][key] is None
        assert scenario.rows[-1][key] is None
    assert provenance['http_request_count'] is provenance['http_response_count'] is None
    assert provenance['fetch_attempts'][-1]['http_status'] is None
    assert provenance['capture'] is None and provenance['representation'] == 'content_decoded'


@pytest.mark.parametrize('stage_index', [0, 1])
@pytest.mark.parametrize('termination,cleanup,codes', [
    ('memory_limit', False, {'CLEANUP_INCOMPLETE'}),
    (None, False, {'CLEANUP_INCOMPLETE'}),
    ('cancelled', True, {'CANCELLED'}),
    ('unexpected_reason', True, {'CLEANUP_INCOMPLETE'}),
])
def test_unknown_cleanup_or_cancellation_never_exposes_commit_candidate(monkeypatch, stage_index, termination, cleanup, codes):
    stages = [Stage(), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))]
    stages[stage_index].termination, stages[stage_index].cleanup = termination, cleanup
    scenario = Scenario(monkeypatch, stages)
    assert_rejected(scenario, codes)
    assert len(scenario.calls) == stage_index + 1


@pytest.mark.parametrize('deactivate', ['CANCELLED', 'CONTEXT_REVOKED'])
def test_inactive_parent_cannot_retain_static_after_render_kill(monkeypatch, deactivate):
    scenario = Scenario(monkeypatch, [Stage(), Stage(termination='memory_limit', deactivate=deactivate)])
    assert_rejected(scenario, {deactivate})


@pytest.mark.parametrize('code,body', [('EXTRACTION_EMPTY', b'<html><body></body></html>'),
    ('SOURCE_REQUIRES_RENDERING', SHELL)])
def test_empty_or_shell_static_failure_can_be_recovered_by_renderer(monkeypatch, code, body):
    with pytest.raises(ToolFault) as actual_static:
        fetch_v2._extract(body, info(body), LIMITS)
    assert actual_static.value.code == code
    scenario = Scenario(monkeypatch, [Stage(body=body, error=code, counts=(2, 2, len(body) * 2)),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))])
    response, data = assert_selected(scenario, scenario.run(), 'render')
    assert FACT.encode() in data['text']
    assert response['observations']['fetch_supervision']['decision'] == 'rendered_after_static_failure'
    assert response['observations']['fetch_attempts'][0]['error_code'] == code
    assert response['usage']['http_request_count'] == 3


@pytest.mark.parametrize('code', ['EXTRACTION_EMPTY', 'SOURCE_REQUIRES_RENDERING'])
@pytest.mark.parametrize('termination,error', [('memory_limit', 'MEMORY_LIMIT'),
    ('deadline', 'DEADLINE_EXCEEDED'), ('stream_limit', 'LIMIT_EXCEEDED')])
def test_killed_renderer_has_no_fallback_when_static_extraction_failed(monkeypatch, code, termination, error):
    scenario = Scenario(monkeypatch, [Stage(body=SHELL, error=code), Stage(termination=termination)])
    assert_rejected(scenario, {error})
    assert len(scenario.calls) == 2


@pytest.mark.parametrize('code,scope', [('WORKER_PROTOCOL_ERROR', None), ('FETCH_UNAVAILABLE', None),
    ('SOURCE_REQUIRES_RENDERING', None), ('SOURCE_REQUIRES_RENDERING', 'storage'),
    ('DEADLINE_EXCEEDED', 'fetch')])
def test_static_failure_without_admitted_render_boundary_does_not_render(monkeypatch, code, scope):
    scenario = Scenario(monkeypatch, [Stage(error=code, scope=scope)])
    result = scenario.run()
    assert result[2]['phase'] == 'failed' and result[2]['error']['code'] == code
    assert len(scenario.calls) == 1 and scenario.eligible == []


@pytest.mark.parametrize('scope', [None, 'storage'])
def test_renderer_failure_with_unknown_boundary_cannot_fallback(monkeypatch, scope):
    scenario = Scenario(monkeypatch, [Stage(), Stage(error='FETCH_UNAVAILABLE', scope=scope)])
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


def test_settled_renderer_resource_failure_retains_static_and_exact_counters(monkeypatch):
    scenario = Scenario(monkeypatch, [Stage(counts=(2, 2, 150000)),
        Stage(error='FETCH_UNAVAILABLE', counts=(4, 3, 10000))])
    response, _ = assert_selected(scenario, scenario.run(), 'static')
    assert tuple(response['usage'][key] for key in COUNTS) == (6, 5, 160000)
    diagnostic = response['observations']['fetch_supervision']
    assert diagnostic['render_outcome'] == 'failed' and diagnostic['network_usage_complete'] is True
    assert diagnostic['render_error_code'] == 'FETCH_UNAVAILABLE'
    assert tuple(diagnostic['render_' + key] for key in COUNTS) == (4, 3, 10000)


def test_residual_network_stream_and_absolute_time_budgets_are_shared(monkeypatch):
    scenario = Scenario(monkeypatch, [Stage(counts=(7, 6, 4 << 20), elapsed=20, stderr_bytes=4096),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))])
    assert_selected(scenario, scenario.run(), 'render')
    static, render = scenario.calls
    assert static['request']['plan']['network_grant'] == {'requests': 40, 'decoded_bytes': 32 << 20}
    assert render['request']['plan']['network_grant'] == {'requests': 33, 'decoded_bytes': 28 << 20}
    assert static['stdout_cap'] == 20 << 20 and static['stderr_cap'] == 64 << 10
    assert render['stdout_cap'] == (20 << 20) - static['process'].stdout_bytes
    assert render['stderr_cap'] == (64 << 10) - 4096
    assert static['seconds'] == 60 and render['seconds'] == 30
    render_deadline = datetime.fromisoformat(render['request']['execution']['deadline_utc'])
    assert render_deadline == scenario.origin + timedelta(seconds=50)
    assert render['started'] + render['seconds'] <= 1060
    assert render['request']['execution']['limits'] == static['request']['execution']['limits']


@pytest.mark.parametrize('remaining,elapsed,expected', [(60, 38, 12), (30, 10, 10), (50, 20, 20)])
def test_render_timeout_uses_residual_parent_deadline(monkeypatch, remaining, elapsed, expected):
    scenario = Scenario(monkeypatch, [Stage(elapsed=elapsed), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))], remaining=remaining)
    assert_selected(scenario, scenario.run(), 'render')
    render = scenario.calls[1]
    assert render['seconds'] == expected
    deadline = datetime.fromisoformat(render['request']['execution']['deadline_utc'])
    assert deadline == scenario.origin + timedelta(seconds=elapsed + expected)
    assert elapsed + expected <= remaining


@pytest.mark.parametrize('counts,elapsed,stdout,stderr,decision', [
    ((33, 33, 100000), 1, None, 11, 'insufficient_network_reserve'),
    ((1, 1, (24 << 20) + 1), 1, None, 11, 'insufficient_network_reserve'),
    ((1, 1, 100000), 46, None, 11, 'insufficient_time_reserve'),
    ((1, 1, 100000), 1, (19 << 20) + 1, 11, 'insufficient_stream_reserve'),
    ((1, 1, 100000), 1, None, (64 << 10) - 1023, 'insufficient_stream_reserve'),
])
def test_insufficient_reserve_keeps_valid_static_without_starting_render(monkeypatch, counts, elapsed, stdout, stderr, decision):
    scenario = Scenario(monkeypatch, [Stage(counts=counts, elapsed=elapsed, stdout_bytes=stdout, stderr_bytes=stderr)])
    response, _ = assert_selected(scenario, scenario.run(), 'static')
    diagnostic = response['observations']['fetch_supervision']
    assert diagnostic['decision'] == decision and diagnostic['render_outcome'] == 'not_started'
    assert diagnostic['render_request_grant'] == diagnostic['render_decoded_byte_grant'] == 0
    assert len(scenario.calls) == 1


def test_narrow_work_limit_controls_whole_attempt(monkeypatch):
    scenario = Scenario(monkeypatch, [Stage(elapsed=8), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))], limits={'work_seconds': 25})
    assert_selected(scenario, scenario.run(), 'render')
    assert scenario.calls[0]['seconds'] == 25
    assert scenario.calls[1]['seconds'] == 7


def corrupt(response, request, kind):
    proposal = response['prepared']['proposal']
    provenance = proposal['provenance']
    if kind == 'operation':
        response['prepared']['operation_id'] = 'snapshot_from_another_attempt'
    elif kind == 'request':
        response['request_id'] = 'worker_from_another_attempt'
    elif kind == 'invocation':
        response['invocation']['attempt_id'] = 'attempt_from_another_action'
    elif kind == 'tool':
        response['tool']['revision'] = 1
    elif kind == 'envelope_extra':
        response['unexpected'] = True
    elif kind == 'proposal_extra':
        proposal['unexpected'] = True
    elif kind == 'provenance_extra':
        provenance['unexpected'] = True
    elif kind.startswith('digest_'):
        proposal[kind.removeprefix('digest_')]['sha256'] = '0' * 64
    elif kind == 'provenance_digest':
        provenance['text_sha256'] = '0' * 64
    elif kind == 'index':
        index = strict_json(unpack_component(proposal['index'], LIMITS['index_bytes']), LIMITS['index_bytes'])
        index['lines'][0]['start_byte'] = 1
        data = encode(index)
        proposal['index'] = pack_component(data)
        provenance.update(index_bytes=len(data), index_sha256=digest(data))
    elif kind == 'representation':
        provenance['representation'] = 'rendered_dom' if request['plan']['stage'] == 'static' else 'content_decoded'
        response['observations']['representation'] = provenance['representation']
    elif kind == 'observation_url':
        response['observations']['final_url'] = 'https://other.example/changed'
    elif kind == 'provenance_usage':
        provenance['http_request_count'] += 1
    elif kind == 'text_usage':
        response['usage']['text_utf8_bytes'] += 1
    elif kind == 'phase':
        response['phase'] = 'committed'
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize('stage_index', [0, 1])
@pytest.mark.parametrize('kind', ['operation', 'request', 'invocation', 'tool', 'envelope_extra',
    'proposal_extra', 'provenance_extra', 'digest_original', 'digest_text', 'digest_index',
    'provenance_digest', 'index', 'representation', 'observation_url', 'provenance_usage', 'text_usage', 'phase'])
def test_bound_protocol_or_component_corruption_aborts_without_fallback(monkeypatch, stage_index, kind):
    stages = [Stage(), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))]
    stages[stage_index].mutate = lambda response, request: corrupt(response, request, kind)
    scenario = Scenario(monkeypatch, stages)
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR', 'INVALID_ARGUMENT'})
    assert len(scenario.calls) == stage_index + 1


@pytest.mark.parametrize('stage_index', [0, 1])
@pytest.mark.parametrize('raw', [b'{', b'{"schema_version":1,"schema_version":1}',
    b'\xef\xbb\xbf{}', b'{"usage":NaN}', b'\xff', b'{}'])
def test_malformed_worker_json_is_never_a_static_fallback_signal(monkeypatch, stage_index, raw):
    stages = [Stage(), Stage()]
    stages[stage_index].raw = raw
    scenario = Scenario(monkeypatch, stages)
    assert_rejected(scenario, {'INVALID_JSON', 'INVALID_ARGUMENT', 'WORKER_PROTOCOL_ERROR'})
    assert len(scenario.calls) == stage_index + 1


@pytest.mark.parametrize('phase', ['prepared', 'failed'])
@pytest.mark.parametrize('key,value', [('http_request_count', 40), ('http_response_count', 4),
    ('decoded_body_bytes', 32 << 20), ('http_request_count', -1),
    ('http_request_count', True), ('decoded_body_bytes', -1)])
def test_render_usage_cannot_exceed_residual_grant_even_on_settled_failure(monkeypatch, phase, key, value):
    def mutate(response, request):
        response['usage'][key] = value
        response['observations']['fetch_attempts'][0][key] = value
        if response['phase'] == 'prepared':
            provenance = response['prepared']['proposal']['provenance']
            provenance['fetch_attempts'][0][key] = value
            if key in {'http_request_count', 'http_response_count'}:
                provenance[key] = value
    scenario = Scenario(monkeypatch, [Stage(counts=(2, 2, 150000)),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False), counts=(3, 2, 10000),
            error='FETCH_UNAVAILABLE' if phase == 'failed' else None, mutate=mutate)])
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('key', COUNTS)
def test_prepared_renderer_cannot_omit_its_own_network_counters(monkeypatch, key):
    scenario = Scenario(monkeypatch, [Stage(), Stage(mutate=lambda response, request: response['usage'].pop(key))])
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('key', COUNTS)
def test_unknown_settled_render_counter_keeps_aggregate_unknown_and_static_lower_bound(monkeypatch, key):
    def unknown(response, request):
        response['usage'][key] = None
        response['observations']['fetch_attempts'][0][key] = None
    scenario = Scenario(monkeypatch, [Stage(counts=(2, 2, 150000)),
        Stage(error='FETCH_UNAVAILABLE', counts=(3, 2, 10000), mutate=unknown)])
    response, _ = assert_selected(scenario, scenario.run(), 'static')
    diagnostic = response['observations']['fetch_supervision']
    assert diagnostic['network_usage_complete'] is False
    assert all(response['usage'][counter] is None for counter in COUNTS)
    assert diagnostic['known_' + key] == dict(zip(COUNTS, (2, 2, 150000)))[key]
    assert diagnostic['render_' + key] is None


@pytest.mark.parametrize('error', ['CANCELLED', 'WORKER_PROTOCOL_ERROR', 'CLEANUP_INCOMPLETE'])
def test_render_error_envelope_cannot_hide_cancellation_or_protocol_failure(monkeypatch, error):
    scenario = Scenario(monkeypatch, [Stage(), Stage(error=error)])
    assert_rejected(scenario, {error, 'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('kind', ['attempt_requests', 'attempt_bytes', 'attempt_responses', 'capture_dom', 'capture_requests'])
def test_renderer_provenance_counters_must_bind_actual_capture_and_stage_usage(monkeypatch, kind):
    def change(response, request):
        proposal = response['prepared']['proposal']
        provenance = proposal['provenance']
        if kind.startswith('attempt_'):
            key = {'attempt_requests': 'http_request_count', 'attempt_responses': 'http_response_count',
                   'attempt_bytes': 'decoded_body_bytes'}[kind]
            provenance['fetch_attempts'][0][key] += 1
            response['observations']['fetch_attempts'] = copy.deepcopy(provenance['fetch_attempts'])
        elif kind == 'capture_dom':
            provenance['capture']['dom_bytes'] += 1
        else:
            provenance['capture']['relayed_requests'] = request['plan']['network_grant']['requests'] + 1
    scenario = Scenario(monkeypatch, [Stage(), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False), mutate=change)])
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('termination', [None, 'memory_limit'])
def test_expired_parent_after_render_cannot_publish_static_or_rendered(monkeypatch, termination):
    scenario = Scenario(monkeypatch, [Stage(elapsed=1),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False), elapsed=60, termination=termination)])
    assert_rejected(scenario, {'DEADLINE_EXCEEDED'})


@pytest.mark.parametrize('stage_index', [0, 1])
def test_parent_revocation_after_successful_stage_aborts_publication(monkeypatch, stage_index):
    stages = [Stage(body=ARTICLE if stage_index == 0 else html_body()),
              Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))]
    stages[stage_index].deactivate = 'CONTEXT_REVOKED'
    scenario = Scenario(monkeypatch, stages)
    assert_rejected(scenario, {'CONTEXT_REVOKED'})


@pytest.mark.parametrize('kill', [False, True])
def test_supervision_public_schema_is_closed_and_keeps_v1_contract(monkeypatch, kill):
    rendered = Stage(termination='memory_limit') if kill else Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))
    scenario = Scenario(monkeypatch, [Stage(), rendered])
    response, _ = assert_selected(scenario, scenario.run(), 'static' if kill else 'render')
    validator = Draft202012Validator(scenario.definition.output_schema)
    view = public_view(response)
    paths = [(), ('provenance',), ('provenance', 'fetch_supervision'), ('provenance', 'fetch_attempts', 0)]
    if not kill:
        paths.append(('provenance', 'capture'))
    for path in paths:
        changed = copy.deepcopy(view)
        target = changed
        for part in path:
            target = target[part]
        target['unexpected'] = True
        assert list(validator.iter_errors(changed)), path
    for key, invalid in [('known_http_request_count', None), ('known_decoded_body_bytes', -1),
        ('render_request_grant', -1), ('render_http_response_count', -1), ('network_usage_complete', 'false')]:
        changed = copy.deepcopy(view)
        changed['provenance']['fetch_supervision'][key] = invalid
        assert list(validator.iter_errors(changed)), key
    v1 = ToolCatalog().resolve('web.fetch', 1).unwrap().output_schema['properties']['provenance']
    assert 'fetch_supervision' not in v1['properties']
    assert 'capture' not in v1['properties']
    assert v1['properties']['representation'] == {'const': 'content_decoded'}
    assert v1['properties']['http_request_count']['type'] == 'integer'
    v2 = ToolCatalog().resolve('web.fetch', 2).unwrap().output_schema['properties']['provenance']
    assert 'fetch_supervision' not in v2['properties']
    assert v2['properties']['http_request_count']['type'] == 'integer'
    assert v2['properties']['http_response_count']['type'] == 'integer'
    assert v2['properties']['fetch_attempts']['items']['properties']['decoded_body_bytes']['type'] == 'integer'


@pytest.mark.parametrize('error', ['DESTINATION_DENIED', 'WORKER_FAILED', 'UNEXPECTED_CRASH'])
def test_security_denial_and_arbitrary_worker_failure_never_become_static_fallback(monkeypatch, error):
    scenario = Scenario(monkeypatch, [Stage(), Stage(error=error)])
    assert_rejected(scenario, {error, 'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('raw', [b'', b'process crashed without a worker envelope'])
def test_arbitrary_process_crash_without_bound_envelope_is_not_fallback(monkeypatch, raw):
    scenario = Scenario(monkeypatch, [Stage(), Stage(raw=raw)])
    assert_rejected(scenario, {'INVALID_JSON', 'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('pid,complete,render_count', [(None, True, 0), (202, False, None)])
def test_spawn_failure_without_pid_is_known_nondispatch_otherwise_counts_unknown(monkeypatch, pid, complete, render_count):
    scenario = Scenario(monkeypatch, [Stage(counts=(2, 2, 150000)),
        Stage(termination='spawn_failed', raw=b'', pid=pid)])
    response, _ = assert_selected(scenario, scenario.run(), 'static')
    diagnostic = response['observations']['fetch_supervision']
    assert diagnostic['network_usage_complete'] is complete
    assert diagnostic['render_error_code'] == 'WORKER_START_FAILED'
    assert scenario.rows[-1]['dispatched'] is (pid is not None)
    for key, static_count in zip(COUNTS, (2, 2, 150000)):
        assert diagnostic['render_' + key] == render_count
        assert scenario.rows[-1][key] == render_count
        assert response['usage'][key] == (static_count if complete else None)
        assert response['observations']['fetch_attempts'][-1][key] == render_count


@pytest.mark.parametrize('termination', ['memory_limit', 'deadline', 'stream_limit'])
def test_partial_terminated_stdout_is_observed_but_never_parsed(monkeypatch, termination):
    partial = b'{"schema_version":1,"message_type":"worker_response","prepared":'
    parsed = []
    original_parser = fetch_supervisor.strict_json

    def parse(raw, *args, **kwargs):
        parsed.append(raw)
        assert raw != partial, 'Parent tried to parse a killed renderer partial response'
        return original_parser(raw, *args, **kwargs)

    monkeypatch.setattr(fetch_supervisor, 'strict_json', parse)
    scenario = Scenario(monkeypatch, [Stage(), Stage(termination=termination, raw=partial)])
    assert_selected(scenario, scenario.run(), 'static')
    assert scenario.rows[-1]['response_sha256'] == digest(partial)
    assert partial not in parsed


def test_queue_wait_consumes_the_original_absolute_utc_deadline(monkeypatch):
    scenario = Scenario(monkeypatch, [Stage(), Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False))])
    scenario.clock.now += 20
    assert_selected(scenario, scenario.run(), 'render')
    assert scenario.calls[0]['seconds'] == 40
    assert scenario.calls[1]['seconds'] == 29
    render_deadline = datetime.fromisoformat(scenario.calls[1]['request']['execution']['deadline_utc'])
    assert render_deadline == scenario.origin + timedelta(seconds=50)
    assert render_deadline <= datetime.fromisoformat(scenario.original_request['execution']['deadline_utc'])


def test_expired_utc_deadline_prevents_dispatch_even_with_active_context(monkeypatch):
    scenario = Scenario(monkeypatch, [Stage()], remaining=120)
    scenario.request['execution']['deadline_utc'] = (scenario.origin - timedelta(seconds=1)).isoformat()
    assert_rejected(scenario, {'DEADLINE_EXCEEDED'})
    assert scenario.calls == []


def test_nonstarted_render_diagnostic_can_remain_only_in_observations_near_provenance_cap(monkeypatch):
    stage = Stage()
    size = len(encode(proposal_for(stage, 'static', (1, 1, len(stage.body)))['provenance']))
    scenario = Scenario(monkeypatch, [stage], limits={'provenance_bytes': size + 64})
    response, _ = assert_selected(scenario, scenario.run(), 'static')
    assert len(scenario.calls) == 1
    assert response['observations']['fetch_supervision']['decision'] == 'insufficient_provenance_reserve'
    assert response['observations']['fetch_supervision']['render_outcome'] == 'not_started'
    assert response['prepared'] == scenario.sent[0]['prepared']
    assert 'fetch_supervision' not in response['prepared']['proposal']['provenance']


def rewrite_text(response, new_text, pages=None):
    """Forge self-consistent envelopes to isolate semantic byte-map checks."""
    proposal = response['prepared']['proposal']
    index = encode(build_index(new_text, pages))
    proposal['text'], proposal['index'] = pack_component(new_text), pack_component(index)
    proposal['provenance'].update(text_bytes=len(new_text), text_sha256=digest(new_text),
        index_bytes=len(index), index_sha256=digest(index),
        physical_page_count=len(pages) if pages is not None else None)
    response['usage']['text_utf8_bytes'] = len(new_text)


@pytest.mark.parametrize('stage_index', [0, 1])
@pytest.mark.parametrize('prefix,suffix', [(b'\xef\xbb\xbf', b''), (b'', b'\r\n')], ids=['bom', 'crlf'])
def test_self_consistent_hashes_cannot_authorize_non_normalized_text(monkeypatch, stage_index, prefix, suffix):
    def alter(response, request):
        text = unpack_component(response['prepared']['proposal']['text'], LIMITS['text_bytes'])
        rewrite_text(response, prefix + text + suffix)
    stages = [Stage(), Stage()]
    stages[stage_index].mutate = alter
    scenario = Scenario(monkeypatch, stages)
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('kind', ['hash', 'range', 'base_range', 'supplement', 'overlap'])
def test_jsonld_ranges_and_hashes_are_validated_before_selection(monkeypatch, kind):
    def alter(response, request):
        structured = response['prepared']['proposal']['provenance']['structured_data']
        if kind == 'hash':
            structured['entries'][0]['sha256'] = '0' * 64
        elif kind == 'range':
            structured['entries'][0]['end_byte'] += 1
        elif kind == 'base_range':
            structured['base_text_bytes'] = response['prepared']['proposal']['text']['byte_length'] + 1
        elif kind == 'supplement':
            structured['supplement_bytes'] += 1
        else:
            structured['entries'][1] = copy.deepcopy(structured['entries'][0])
    scenario = Scenario(monkeypatch, [Stage(body=html_body(records=(RECORD, SECOND_RECORD))),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False, records=(RECORD, SECOND_RECORD)), mutate=alter)])
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('kind', ['ordinal', 'gap', 'bounds', 'incomplete', 'physical_count'])
def test_forged_self_consistent_page_index_cannot_publish_invalid_spans(monkeypatch, kind):
    def alter(response, request):
        text = unpack_component(response['prepared']['proposal']['text'], LIMITS['text_bytes'])
        pages = [{'page': 1, 'start_byte': 0, 'end_byte': len(text)}]
        if kind == 'ordinal':
            pages[0]['page'] = 2
        elif kind == 'gap':
            pages[0]['start_byte'] = 1
        elif kind == 'bounds':
            pages[0]['end_byte'] += 1
        elif kind == 'incomplete':
            pages[0]['end_byte'] -= 1
        rewrite_text(response, text, pages)
        if kind == 'physical_count':
            response['prepared']['proposal']['provenance']['physical_page_count'] = 2
    scenario = Scenario(monkeypatch, [Stage(), Stage(mutate=alter)])
    assert_rejected(scenario, {'WORKER_PROTOCOL_ERROR'})


@pytest.mark.parametrize('retained', [1, 2])
def test_duplicate_whole_jsonld_records_must_each_survive(monkeypatch, retained):
    scenario = Scenario(monkeypatch, [Stage(body=html_body(records=(RECORD, RECORD))),
        Stage(body=html_body(BODY + '<p>' + FACT + '</p>', scripts=False, records=(RECORD,) * retained))])
    response, data = assert_selected(scenario, scenario.run(), 'render' if retained == 2 else 'static')
    expected = 'rendered_with_preservation' if retained == 2 else 'structured_record_not_preserved'
    assert response['observations']['fetch_supervision']['decision'] == expected
    assert data['text'].count(RECORD.encode()) == 2
