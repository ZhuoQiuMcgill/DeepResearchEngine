"""Archive explicit JSON-LD separately from extracted, visible HTML prose.

This is a syntax-preserving supplement, not JSON-LD expansion or verification.
Never execute scripts, resolve contexts, choose an entity or merge records.
"""
from __future__ import annotations

import json
import re

from .common import ToolFault, digest, encode
from .retrieval import build_index, normalize

MAX_SCRIPTS = 32
MAX_SCRIPT_BYTES = 65536
MAX_SUPPLEMENT_BYTES = 131072
MAX_DEPTH = 64
_REASONS = ('inert_container', 'external_script', 'script_count_limit',
            'script_size_limit', 'invalid_json', 'depth_limit',
            'supplement_size_limit', 'text_limit', 'index_limit', 'provenance_limit')
_HEADING = ('\n\n## Embedded structured data\n\n'
    'Publisher-declared JSON-LD; not rendered page text. These records may '
    'describe different entities, variants or dates. Their accuracy, currency '
    'and relationship to the visible page are not verified. No scripts or '
    'remote contexts were executed or resolved.\n')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError('Non-JSON numeric constant')


def _check_json(raw):
    # Parse numbers as strings for validation only; the original lexemes below
    # are retained, without float rounding, key sorting or entity decoding.
    value = json.loads(raw, object_pairs_hook=_pairs, parse_int=str,
                       parse_float=str, parse_constant=_invalid_constant)
    if not isinstance(value, (dict, list)):
        raise ValueError('JSON-LD container must be an object or array')
    pending = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if depth > MAX_DEPTH:
            return False
        if isinstance(node, dict):
            pending.extend((item, depth + 1) for item in node.values())
        elif isinstance(node, list):
            pending.extend((item, depth + 1) for item in node)
    return True


def append_structured_data(proposal, tree, limits):
    """Append whole bounded script records, keeping the old text as a prefix.

    Diagnostics and readable byte ranges contain no source values. An omitted
    record remains in original bytes; optional data must not evict body text or
    turn a successful body extraction into a text/index limit failure.
    """
    scripts = [node for node in tree.iter('script')
               if (node.get('type') or '').strip().lower() == 'application/ld+json']
    if not scripts:
        return proposal
    base = text = proposal['text']
    index = proposal['index']
    entries, omitted = [], {reason: 0 for reason in _REASONS}
    for ordinal, node in enumerate(scripts, 1):
        reason = None
        if any(parent.tag in {'template', 'noscript'} for parent in node.iterancestors()):
            reason = 'inert_container'
        elif node.get('src') is not None:
            reason = 'external_script'
        elif ordinal > MAX_SCRIPTS:
            reason = 'script_count_limit'
        raw = normalize(node.text or '')
        data = raw.encode('utf-8')
        if not reason and len(data) > MAX_SCRIPT_BYTES:
            reason = 'script_size_limit'
        if not reason:
            try:
                if not _check_json(raw):
                    reason = 'depth_limit'
            except (ValueError, RecursionError):
                reason = 'invalid_json'
        if reason:
            omitted[reason] += 1
            continue
        # An authored backtick run cannot close the containing code fence.
        fence = '`' * max(3, 1 + max((len(m.group()) for m in re.finditer(r'`+', raw)), default=0))
        prefix = ((_HEADING if not entries else '\n') +
                  f'\n### JSON-LD script {ordinal} (publisher-declared)\n\n{fence}json\n').encode('utf-8')
        suffix = ('\n' + fence + '\n').encode('utf-8')
        addition = prefix + data + suffix
        if len(text) - len(base) + len(addition) > MAX_SUPPLEMENT_BYTES:
            reason = 'supplement_size_limit'
        elif len(text) + len(addition) > limits['text_bytes']:
            reason = 'text_limit'
        else:
            candidate = text + addition
            try:
                candidate_index = encode(build_index(candidate, None), limits['index_bytes'])
            except ToolFault as error:
                if error.code != 'LIMIT_EXCEEDED':
                    raise
                reason = 'index_limit'
        if reason:
            omitted[reason] += 1
            continue
        start = len(text) + len(prefix)
        entries.append({'script_ordinal': ordinal, 'start_byte': start,
                        'end_byte': start + len(data), 'sha256': digest(data)})
        text, index = candidate, candidate_index
    diagnostic = {'method': 'inline-jsonld/1', 'origin': 'publisher_declared_not_verified',
        'visible_body': False, 'semantic_verification': False,
        'base_text_bytes': len(base), 'script_count': len(scripts),
        'retained_script_count': len(entries), 'omitted_script_count': sum(omitted.values()),
        'supplement_bytes': len(text) - len(base), 'omissions': omitted, 'entries': entries}
    original_provenance = proposal['provenance']
    provenance = dict(original_provenance)
    provenance.update(structured_data=diagnostic,
        text_bytes=len(text), text_sha256=digest(text),
        index_bytes=len(index), index_sha256=digest(index))
    provenance['parser_warning_count'] += int(bool(diagnostic['omitted_script_count']))
    try:
        encode(provenance, limits['provenance_bytes'])
    except ToolFault as error:
        if error.code != 'LIMIT_EXCEEDED':
            raise
        # Keep the body and its diagnostics. Prefer an explicit omission record;
        # if even that cannot fit, retain a generic warning in the existing
        # count field without adding bytes to a previously valid provenance.
        text, index = base, proposal['index']
        omitted['provenance_limit'] += len(entries)
        diagnostic.update(entries=[], retained_script_count=0,
            omitted_script_count=sum(omitted.values()), supplement_bytes=0)
        provenance = {**original_provenance, 'structured_data': diagnostic,
            'parser_warning_count': max(1, original_provenance['parser_warning_count'])}
        try:
            encode(provenance, limits['provenance_bytes'])
        except ToolFault as compact_error:
            if compact_error.code != 'LIMIT_EXCEEDED':
                raise
            provenance = {**original_provenance,
                'parser_warning_count': max(1, original_provenance['parser_warning_count'])}
    proposal.update(text=text, index=index, provenance=provenance)
    return proposal


def diagnostic_schema():
    from .discovery_metadata import object_schema
    count = {'type': 'integer', 'minimum': 0}
    return object_schema({'method': {'const': 'inline-jsonld/1'},
        'origin': {'const': 'publisher_declared_not_verified'},
        'visible_body': {'const': False}, 'semantic_verification': {'const': False},
        'base_text_bytes': count, 'script_count': count, 'retained_script_count': count,
        'omitted_script_count': count, 'supplement_bytes': count,
        'omissions': object_schema({name: count for name in _REASONS}),
        'entries': {'type': 'array', 'maxItems': MAX_SCRIPTS,
                    'items': object_schema({'script_ordinal': {'type': 'integer', 'minimum': 1},
                        'start_byte': count, 'end_byte': count,
                        'sha256': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}})}})
