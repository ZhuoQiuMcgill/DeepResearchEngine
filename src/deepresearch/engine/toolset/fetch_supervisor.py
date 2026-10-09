"""Parent-owned, bounded fetch phases; no renderer owns the static fallback.

One recorded ToolAttempt authorizes at most a static worker and a render worker.
Only the final selected proposal is committed by ToolExecutor. Worker envelopes,
process outcomes and unknown counters remain distinct from that selection.
"""
from __future__ import annotations

import copy
import time
from datetime import datetime, timezone

from jsonschema import Draft202012Validator

from deepresearch.engine.contracts import deadline_after, new_id
from .common import ToolFault, closed, digest, encode, strict_json
from .fetch_policy import MAX_NETWORK_BYTES, MAX_REQUESTS, RENDERABLE, render_signal, select_rendered
from .retrieval import build_index, unpack_component

_COUNTS = ('http_request_count', 'http_response_count', 'decoded_body_bytes')
_OBSERVATIONS = {'http_status', 'redirects', 'final_url', 'extraction_version', 'fetch_attempts', 'representation'}
_USAGE = {'duration_ms', *_COUNTS, 'text_utf8_bytes', 'monetary_cost'}
_TERMINATION = {'deadline': ('DEADLINE_EXCEEDED', 'timed_out'),
    'memory_limit': ('MEMORY_LIMIT', 'limit_exhausted'), 'stream_limit': ('LIMIT_EXCEEDED', 'limit_exhausted'),
    'cancelled': ('CANCELLED', 'cancelled'), 'spawn_failed': ('WORKER_START_FAILED', 'failed')}
_SETTLED_RENDER_FAILURES = {'BROWSER_UNAVAILABLE', 'EXTRACTION_EMPTY', 'SOURCE_REQUIRES_RENDERING',
    'SOURCE_CHALLENGE', 'SOURCE_LOGIN', 'SOURCE_DENIED', 'FETCH_HTTP_ERROR', 'FETCH_UNAVAILABLE',
    'RESPONSE_LIMIT', 'REQUEST_LIMIT', 'DEADLINE_EXCEEDED', 'CONTENT_TYPE_MISMATCH',
    'UNSUPPORTED_CONTENT', 'UNSUPPORTED_ENCODING', 'DECODING_ERROR', 'LIMIT_EXCEEDED'}


def _protocol(message):
    raise ToolFault('WORKER_PROTOCOL_ERROR', message)


def _response(process, request, limits, stdout_cap, definition):
    if not process.cleanup_complete:
        raise ToolFault('CLEANUP_INCOMPLETE', 'Fetch stage resources did not settle')
    if process.termination_reason:
        code, status = _TERMINATION.get(process.termination_reason, ('CLEANUP_INCOMPLETE', 'failed'))
        raise ToolFault(code, 'Fetch stage stopped under parent control', status=status)
    value = strict_json(process.stdout, stdout_cap, limits['json_depth'])
    closed(value, {'schema_version', 'message_type', 'request_id', 'tool', 'invocation',
                   'phase', 'prepared', 'error', 'observations', 'usage'})
    if (type(value['schema_version']) is not int or value['schema_version'] != 1 or
            value['message_type'] != 'worker_response' or
            any(value[key] != request[key] for key in ('request_id', 'tool', 'invocation'))):
        _protocol('Fetch stage response changed its bound identity')
    phase = value['phase']
    if phase not in {'prepared', 'failed'}:
        _protocol('Unknown fetch stage response phase')
    if phase == 'prepared' and (process.exit_code != 0 or value['error'] is not None or value['prepared'] is None):
        _protocol('Inconsistent prepared fetch stage')
    if phase == 'failed':
        if value['prepared'] is not None or not isinstance(value['error'], dict) or process.exit_code not in range(2, 7):
            _protocol('Inconsistent failed fetch stage')
        closed(value['error'], {'code', 'message', 'details', 'observed_effect_state'})
    closed(value['observations'], _OBSERVATIONS, required=_OBSERVATIONS if phase == 'prepared' else set())
    usage = closed(value['usage'], _USAGE, required=set())
    if any(v is not None and (type(v) is not int or v < 0) for k, v in usage.items() if k != 'monetary_cost') or usage.get('monetary_cost') is not None:
        _protocol('Fetch stage supplied invalid usage')
    # A settled stage reports its own counters. A killed worker has no response
    # and is handled separately; it cannot borrow the preceding stage's values.
    if phase == 'prepared' and any(type(usage.get(k)) is not int for k in _COUNTS):
        _protocol('Prepared fetch stage omitted network usage')
    grant = request['plan']['network_grant']
    requests, responses, decoded = (usage.get(k) for k in _COUNTS)
    # Failures are accountable too. A transport can observe the chunk that
    # crosses its byte threshold before aborting; retain those actual bytes only
    # with the explicit, settled byte-limit failure, never clamp them to a grant.
    error = value['error'] or {}
    details = error.get('details') or {}
    byte_limit = (phase == 'failed' and error.get('code') == 'RESPONSE_LIMIT'
        and details.get('limit_kind') == 'decoded_bytes'
        and details.get('limit_scope') in {'resource', 'fetch'}
        and type(details.get('limit')) is int and 0 < details['limit'] <= grant['decoded_bytes'])
    if ((requests is not None and requests > grant['requests']) or
            (responses is not None and responses > grant['requests']) or
            (requests is not None and responses is not None and responses > requests) or
            (decoded is not None and decoded > grant['decoded_bytes'] and not byte_limit)):
        _protocol('Fetch stage exceeded its residual grant without a settled limit boundary')
    attempts = value['observations'].get('fetch_attempts')
    if phase == 'prepared' or details.get('failure_scope') == 'fetch' or attempts is not None:
        schema = definition.output_schema['properties']['provenance']['properties']['fetch_attempts']
        if list(Draft202012Validator(schema).iter_errors(attempts)):
            _protocol('Fetch stage returned an invalid backend history')
        backends = [entry['backend'] for entry in attempts]
        allowed = ([['curl_cffi/0.16.3'], ['curl_cffi/0.16.3', 'httpx/0.28.1']]
            if request['plan']['stage'] == 'static' else [['playwright/1.63.0/chromium']])
        if backends not in allowed:
            _protocol('Fetch stage returned an unplanned backend sequence')
        for key in _COUNTS:
            if key not in usage:
                _protocol('Fetch stage omitted its aggregate counter')
            entries = [entry[key] for entry in attempts]
            total = None if None in entries else sum(entries)
            if total != usage[key] or (phase == 'prepared' and total is None):
                _protocol('Fetch stage backend history and usage disagree')
        if (attempts[-1]['outcome'] != ('returned' if phase == 'prepared' else 'failed') or
                attempts[-1]['error_code'] != (None if phase == 'prepared' else error['code']) or
                any(entry['outcome'] != 'failed' or entry['error_code'] is None for entry in attempts[:-1])):
            _protocol('Fetch stage backend outcomes disagree with its envelope')
    return value


def _proposal(response, request, definition, limits):
    prepared = closed(response['prepared'], {'operation_id', 'proposal'})
    if prepared['operation_id'] != request['plan']['operation_id']:
        _protocol('Fetch stage changed its snapshot operation')
    packed = closed(prepared['proposal'], {'original', 'text', 'index', 'provenance',
                                         'extraction_version', 'normalization_version', 'media_type'})
    components = {key: unpack_component(packed[key], limits[cap]) for key, cap in
                  (('original', 'raw_bytes'), ('text', 'text_bytes'), ('index', 'index_bytes'))}
    decoded_text = components['text'].decode('utf-8', errors='strict')
    if '\r' in decoded_text or decoded_text.startswith('\ufeff'):
        _protocol('Fetch stage text is not normalized LF UTF-8')
    index = strict_json(components['index'], limits['index_bytes'])
    if not isinstance(index, dict) or index != build_index(components['text'], index.get('pages')):
        _protocol('Fetch stage index does not bind the exact extracted text')
    provenance = packed['provenance']
    encode(provenance, limits['provenance_bytes'])
    for key, data in components.items():
        if provenance.get(key + '_bytes') != len(data) or provenance.get(key + '_sha256') != digest(data):
            _protocol('Fetch stage component provenance does not match its bytes')
    if any(provenance.get(key) != packed[key] for key in ('extraction_version', 'normalization_version', 'media_type')):
        _protocol('Fetch stage component interpretation changed')
    if provenance['requested_url'] != request['arguments']['url'] or not 200 <= provenance['http_status'] < 300:
        _protocol('Fetch stage did not return the requested successful capture')
    if any(provenance[k] != response['usage'][k] for k in ('http_request_count', 'http_response_count')):
        _protocol('Fetch stage provenance and usage disagree')
    if response['usage'].get('text_utf8_bytes') != len(components['text']):
        _protocol('Fetch stage usage does not match extracted bytes')
    pages = index['pages']
    if pages is not None:
        if not isinstance(pages, list):
            _protocol('Fetch stage page map is invalid')
        previous = None
        for ordinal, page in enumerate(pages, 1):
            closed(page, {'page', 'start_byte', 'end_byte'})
            a, b = page['start_byte'], page['end_byte']
            if (type(page['page']) is not int or page['page'] != ordinal or type(a) is not int or type(b) is not int
                    or not 0 <= a <= b <= len(components['text']) or
                    (previous is None and a != 0) or (previous is not None and components['text'][previous:a] != b'\n')):
                _protocol('Fetch stage page spans do not cover the text')
            components['text'][a:b].decode('utf-8', errors='strict')
            previous = b
        if (pages and previous != len(components['text'])) or (not pages and components['text']):
            _protocol('Fetch stage page map is incomplete')
    if provenance['physical_page_count'] != (len(pages) if pages is not None else None):
        _protocol('Fetch stage physical page count changed')
    structured = provenance.get('structured_data')
    if structured:
        previous = structured['base_text_bytes']
        if not 0 <= previous <= len(components['text']) or structured['supplement_bytes'] != len(components['text']) - previous:
            _protocol('Fetch stage structured-data base range is invalid')
        components['text'][:previous].decode('utf-8', errors='strict')
        for entry in structured['entries']:
            a, b = entry['start_byte'], entry['end_byte']
            if not previous <= a < b <= len(components['text']) or digest(components['text'][a:b]) != entry['sha256']:
                _protocol('Fetch stage structured-data record range or hash changed')
            components['text'][a:b].decode('utf-8', errors='strict')
            previous = b
    representation = 'content_decoded' if request['plan']['stage'] == 'static' else 'rendered_dom'
    if provenance['representation'] != representation or response['observations']['representation'] != representation:
        _protocol('Fetch stage returned the wrong capture representation')
    for key in _OBSERVATIONS:
        if provenance[key] != response['observations'][key]:
            _protocol('Fetch stage observations differ from its selected capture')
    view = {'snapshot_ref': {'schema_version': 1, 'store_id': 'validation', 'snapshot_id': 'validation'},
        'extraction_version': packed['extraction_version'], 'normalization_version': packed['normalization_version'],
        'line_count': len(index['lines']), 'page_count': provenance['physical_page_count'],
        'provenance': provenance, 'preview': ''}
    if list(Draft202012Validator(definition.output_schema).iter_errors(view)):
        _protocol('Fetch stage proposal violates the public capture schema')
    attempts = provenance['fetch_attempts']
    if any(sum(entry[k] for entry in attempts if type(entry[k]) is int) != response['usage'][k]
            or any(type(entry[k]) is not int for entry in attempts) for k in _COUNTS):
        _protocol('Fetch stage backend counters do not bind its usage')
    backends = [entry['backend'] for entry in attempts]
    if request['plan']['stage'] == 'static':
        if backends not in [['curl_cffi/0.16.3'], ['curl_cffi/0.16.3', 'httpx/0.28.1']] or provenance['capture'] is not None:
            _protocol('Static fetch stage returned an unplanned backend')
    else:
        capture = provenance['capture']
        if (backends != ['playwright/1.63.0/chromium'] or capture is None or
                capture['dom_bytes'] != len(components['original']) or
                capture['relayed_requests'] > response['usage']['http_request_count']):
            _protocol('Renderer provenance does not bind its actual capture')
    if (attempts[-1]['outcome'] != 'returned' or attempts[-1]['error_code'] is not None or
            any(entry['outcome'] != 'failed' or entry['error_code'] is None for entry in attempts[:-1])):
        _protocol('Fetch stage backend outcomes disagree with its prepared capture')
    return {**packed, **components}


def _row(stage, request, payload, process, usage=None):
    return {'stage': stage, 'request_id': request['request_id'],
        'dispatched': not (process.termination_reason == 'spawn_failed' and process.pid is None),
        'request_sha256': digest(payload), 'response_sha256': digest(process.stdout),
        'exit_code': process.exit_code, 'termination_reason': process.termination_reason,
        'cleanup_complete': process.cleanup_complete, 'duration_ms': process.duration_ms,
        'stdin_bytes': process.stdin_bytes, 'stdout_bytes': process.stdout_bytes, 'stderr_bytes': process.stderr_bytes,
        'peak_job_memory_bytes': process.peak_job_memory_bytes,
        'peak_process_memory_bytes': process.peak_process_memory_bytes,
        **{k: (usage or {}).get(k) for k in _COUNTS}}


async def supervise(request, definition, limits, context, dispatch, observe):
    """Return the selected genuine process/request plus parent-enriched response.

    dispatch owns the process runner; observe records every actual process even
    on exceptions. No intermediate response is committed or exposed as success.
    """
    initial = copy.deepcopy(request)
    initial['plan'].update(extraction_config_ref='adaptive/2', stage='static',
        network_grant={'requests': MAX_REQUESTS, 'decoded_bytes': MAX_NETWORK_BYTES})
    declared_remaining = (datetime.fromisoformat(initial['execution']['deadline_utc'].replace('Z', '+00:00'))
                          - datetime.now(timezone.utc)).total_seconds()
    overall_deadline = time.monotonic() + min(limits['work_seconds'], context.remaining_seconds(), declared_remaining)
    def active():
        context.assert_active()
        if time.monotonic() >= overall_deadline:
            raise ToolFault('DEADLINE_EXCEEDED', 'Shared fetch work deadline expired', status='timed_out')
    remaining_stream = limits['fetch_stdout_bytes']
    remaining_stderr = limits['stderr_bytes']

    async def call(bound, seconds):
        nonlocal remaining_stream, remaining_stderr
        active()
        payload = encode(bound, limits['stdin_bytes'])
        cap = remaining_stream
        process = await dispatch(bound, payload, seconds, cap, remaining_stderr)
        remaining_stream -= process.stdout_bytes
        remaining_stderr -= process.stderr_bytes
        row = _row(bound['plan']['stage'], bound, payload, process)
        observe(row)
        if process.termination_reason:
            return process, None, row
        response = _response(process, bound, limits, cap, definition)
        row.update({k: response['usage'].get(k) for k in _COUNTS})
        return process, response, row

    process, static_response, static_row = await call(initial, max(.001, overall_deadline - time.monotonic()))
    if static_response is None:
        _response(process, initial, limits, limits['fetch_stdout_bytes'], definition)
    static = _proposal(static_response, initial, definition, limits) if static_response['phase'] == 'prepared' else None
    active()
    if static is not None:
        trigger = render_signal(static, request['arguments'])
        if trigger != 'thin_script_html':
            return process, initial, static_response, 'static'
    else:
        error = static_response['error']
        history = static_response['observations'].get('fetch_attempts', [])
        # Preserve revision 2's existing chain: a renderable curl response can
        # still require Chromium when the one HTTPX fallback is unavailable.
        alternate_failed = (len(history) == 2 and history[0]['error_code'] in RENDERABLE
            and history[-1]['backend'] == 'httpx/0.28.1'
            and error['code'] in {'FETCH_HTTP_ERROR', 'FETCH_UNAVAILABLE'})
        if (request['arguments'].get('mode', 'auto') != 'auto' or
                (error['code'] not in RENDERABLE and not alternate_failed) or
                error['details'].get('failure_scope') != 'fetch' or
                any(type(static_response['usage'].get(k)) is not int for k in _COUNTS)):
            return process, initial, static_response, 'static'
        trigger = 'static_extraction_failed'
    used = static_response['usage']
    request_grant = max(0, MAX_REQUESTS - used['http_request_count'])
    byte_grant = max(0, MAX_NETWORK_BYTES - used['decoded_body_bytes'])
    seconds = overall_deadline - time.monotonic()
    decision = None
    if seconds < 15:
        decision = 'insufficient_time_reserve'
    elif request_grant < 8 or byte_grant < 8 << 20:
        decision = 'insufficient_network_reserve'
    elif remaining_stream < 1 << 20 or remaining_stderr < 1024:
        decision = 'insufficient_stream_reserve'
    elif static is not None and len(encode(static['provenance'])) > limits['provenance_bytes'] - 4096:
        decision = 'insufficient_provenance_reserve'
    diagnostic = {'method': 'isolated-render/1', 'trigger': trigger, 'decision': decision or 'pending',
        'selected_stage': 'static', 'network_usage_complete': True,
        'known_http_request_count': used['http_request_count'], 'known_http_response_count': used['http_response_count'],
        'known_decoded_body_bytes': used['decoded_body_bytes'],
        'render_request_grant': 0, 'render_decoded_byte_grant': 0,
        'render_outcome': 'not_started', 'render_error_code': None,
        'render_http_request_count': 0, 'render_http_response_count': 0, 'render_decoded_body_bytes': 0}
    chosen_response, chosen_process, chosen_request = static_response, process, initial
    render_response, render_process = None, None
    if decision is None:
        render = copy.deepcopy(initial)
        render['request_id'] = new_id('worker_')
        render['plan'].update(stage='render', network_grant={'requests': request_grant, 'decoded_bytes': byte_grant})
        render_seconds = min(30, seconds - 10)
        render['execution']['deadline_utc'] = deadline_after(render_seconds)
        diagnostic.update(render_request_grant=request_grant, render_decoded_byte_grant=byte_grant)
        render_process, render_response, render_row = await call(render, render_seconds)
        active()
        if not render_process.cleanup_complete:
            raise ToolFault('CLEANUP_INCOMPLETE', 'Renderer cleanup was not confirmed')
        if render_process.termination_reason:
            if render_process.termination_reason not in {'memory_limit', 'deadline', 'stream_limit', 'spawn_failed'}:
                _response(render_process, render, limits, max(0, remaining_stream), definition)
            code, status = _TERMINATION[render_process.termination_reason]
            if static is None:
                raise ToolFault(code, 'Renderer stopped without a valid static capture', status=status)
            diagnostic.update(decision='static_retained_after_termination', render_outcome='terminated',
                render_error_code=code, network_usage_complete=False,
                render_http_request_count=None, render_http_response_count=None, render_decoded_body_bytes=None)
            if render_process.termination_reason == 'spawn_failed' and render_process.pid is None:
                diagnostic.update(network_usage_complete=True, render_http_request_count=0,
                    render_http_response_count=0, render_decoded_body_bytes=0)
                render_row.update({key: 0 for key in _COUNTS})
        else:
            diagnostic['render_outcome'] = render_response['phase']
            for key in _COUNTS:
                value = render_response['usage'].get(key)
                diagnostic['render_' + key] = value
                if value is None:
                    diagnostic['network_usage_complete'] = False
                else:
                    diagnostic['known_' + key] += value
            if render_response['phase'] == 'failed':
                error = render_response['error']
                diagnostic.update(decision='static_retained_after_render_failure', render_error_code=error['code'])
                if static is None:
                    chosen_response, chosen_process, chosen_request = render_response, render_process, render
                    diagnostic['selected_stage'] = 'render'
                elif error['details'].get('failure_scope') != 'fetch' or error['code'] not in _SETTLED_RENDER_FAILURES:
                    _protocol('Renderer failure lacks a settled fetch boundary')
            else:
                rendered = _proposal(render_response, render, definition, limits)
                decision = select_rendered(static, rendered) if static is not None else 'rendered_after_static_failure'
                diagnostic['decision'] = decision
                if decision in {'rendered_with_preservation', 'rendered_after_static_failure'}:
                    chosen_response, chosen_process, chosen_request = render_response, render_process, render
                    diagnostic['selected_stage'] = 'render'
    response = copy.deepcopy(chosen_response)
    history = list(static_response['observations'].get('fetch_attempts', []))
    if render_response is not None:
        history += render_response['observations'].get('fetch_attempts', [])
    elif render_process is not None:
        history.append({'backend': 'playwright/1.63.0/chromium', 'outcome': 'failed',
            'elapsed_ms': render_process.duration_ms, 'http_status': None, 'error_code': diagnostic['render_error_code'],
            **{key: diagnostic['render_' + key] for key in _COUNTS}})
    for key in _COUNTS:
        response['usage'][key] = diagnostic['known_' + key] if diagnostic['network_usage_complete'] else None
    response['observations'].update(fetch_attempts=history, fetch_supervision=diagnostic)
    if response['phase'] == 'prepared':
        provenance = response['prepared']['proposal']['provenance']
        provenance.update(fetch_attempts=history, fetch_supervision=diagnostic,
            http_request_count=response['usage']['http_request_count'], http_response_count=response['usage']['http_response_count'])
        # The original/static proposal remains intact until every selected field
        # fits. Never commit an unverified or partially received worker payload.
        try:
            encode(provenance, limits['provenance_bytes'])
        except ToolFault as error:
            if error.code != 'LIMIT_EXCEEDED' or static is None:
                raise
            # No render is started without space for its bounded failure record.
            # A nonstarted optional attempt can leave its diagnostic solely in
            # the durable tool observations when the existing provenance is full.
            if render_process is None:
                response['prepared'] = copy.deepcopy(static_response['prepared'])
            else:
                diagnostic.update(decision='render_provenance_did_not_fit', selected_stage='static')
                chosen_process, chosen_request = process, initial
                response['prepared'] = copy.deepcopy(static_response['prepared'])
                response['usage']['text_utf8_bytes'] = len(static['text'])
                response['observations'].update({k: v for k, v in static_response['observations'].items() if k != 'fetch_attempts'})
                fallback = response['prepared']['proposal']['provenance']
                fallback.update(fetch_attempts=history, fetch_supervision=diagnostic,
                    http_request_count=response['usage']['http_request_count'], http_response_count=response['usage']['http_response_count'])
                encode(fallback, limits['provenance_bytes'])
                for key in ('request_id', 'tool', 'invocation'):
                    response[key] = initial[key]
    active()
    return chosen_process, chosen_request, response, diagnostic['selected_stage']
