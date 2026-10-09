"""Bounded optional rendering decisions, independent of transport and storage."""
from __future__ import annotations

import re

MAX_REQUESTS = 40
MAX_NETWORK_BYTES = 32 << 20
RENDERABLE = {'EXTRACTION_EMPTY', 'SOURCE_REQUIRES_RENDERING', 'SOURCE_CHALLENGE'}


def render_signal(proposal, arguments):
    if arguments.get('mode', 'auto') != 'auto':
        return 'static_mode'
    provenance = proposal['provenance']
    if provenance['media_type'] not in {'text/html', 'application/xhtml+xml'}:
        return 'ineligible_media'
    base_bytes = (provenance.get('structured_data') or {}).get('base_text_bytes', len(proposal['text']))
    if not 0 < base_bytes <= 2048 or not 65536 <= len(proposal['original']) <= 8 << 20:
        return 'outside_size_band'
    from lxml import html
    from .retrieval import decode_text
    raw = proposal['original']
    text, _, _ = decode_text(raw, provenance['content_type'], html=True)
    tree = html.document_fromstring(text, parser=html.HTMLParser(no_network=True))
    scripts = tree.xpath('//script')
    external = any(n.get('src') and (n.get('type') or '').strip().lower() in
                   {'', 'module', 'text/javascript', 'application/javascript'} for n in scripts)
    size = sum(len(html.tostring(n, encoding='utf-8', with_tail=False)) for n in scripts)
    for node in tree.xpath('//script|//style|//template|//noscript|//head|//svg'):
        if node.getparent() is not None:
            node.drop_tree()
    visible = ' '.join(tree.text_content().split()).encode('utf-8')
    return 'thin_script_html' if external and size * 2 >= len(raw) and len(visible) <= 8192 else 'insufficient_structural_signal'


def _body(proposal):
    stop = (proposal['provenance'].get('structured_data') or {}).get('base_text_bytes', len(proposal['text']))
    return proposal['text'][:stop]


def _ordered_blocks(before, after):
    # Preserve literal whitespace too: indentation, newlines and repeated spaces
    # can be authored code or table relationships. Conservative rejection of a
    # formatting change is preferable to selecting changed source semantics.
    from markdown_it import MarkdownIt
    def blocks(raw):
        source = raw.decode('utf-8')
        lines = source.splitlines(keepends=True)
        tokens = MarkdownIt('commonmark', {'html': True}).parse(source)
        values = []
        for index, token in enumerate(tokens):
            if token.level != 0 or token.map is None:
                continue
            children = []
            if token.type == 'paragraph_open':
                children = tokens[index + 1].children or []
            signatures = [(child.type, child.tag, child.nesting, child.markup,
                child.content, child.attrs) for child in children]
            values.append((token.type, ''.join(lines[token.map[0]:token.map[1]]).rstrip('\n'), signatures))
        return values
    def preserved(block, value):
        if block == value:
            return True
        # Extraction can append a new prose line to the final paragraph. Admit
        # only its exact raw prefix AND unchanged parsed inline tokens; code,
        # list containers and tables cannot be silently reinterpreted.
        kind, raw, children = block
        return (kind == value[0] == 'paragraph_open' and bool(children)
            and value[1].startswith(raw + '\n') and value[2][:len(children)] == children)
    try:
        original, candidate = blocks(before), iter(blocks(after))
        # Whole top-level blocks keep code blank lines, indentation and container
        # context intact. A matching substring in a different code/list context
        # does not establish preservation.
        return bool(original) and all(any(preserved(block, value) for value in candidate) for block in original)
    except (ValueError, IndexError, RecursionError):
        return False


def _tokens(text):
    from markdown_it import MarkdownIt
    from lxml import html
    parts = []
    def visit(token):
        if token.children:
            for child in token.children:
                visit(child)
        elif token.type in {'text', 'code_inline', 'code_block', 'fence'}:
            parts.append(token.content)
        elif token.type in {'html_block', 'html_inline'}:
            try:
                parts.append(html.fragment_fromstring(token.content, create_parent=True).text_content())
            except (ValueError, html.etree.ParserError):
                pass
    for token in MarkdownIt('commonmark', {'html': True}).parse(text.decode('utf-8')):
        visit(token)
    return set(re.findall(r'\w+', ' '.join(parts)))


def select_rendered(static, rendered):
    if rendered['provenance']['final_url'] != static['provenance']['final_url']:
        return 'changed_final_url'
    capture = rendered['provenance'].get('capture')
    if not capture or capture.get('failed_resources') != 0:
        return 'resource_failures'
    if rendered['provenance']['media_type'] not in {'text/html', 'application/xhtml+xml'}:
        return 'changed_media'
    before, after = _body(static), _body(rendered)
    if not _ordered_blocks(before, after):
        return 'static_body_not_preserved'
    dates_before = static['provenance'].get('document_dates') or {}
    dates_after = rendered['provenance'].get('document_dates') or {}
    for kind in ('published', 'modified'):
        remaining_dates = list(dates_after.get(kind, []))
        for declared in dates_before.get(kind, []):
            if declared not in remaining_dates:
                return 'document_dates_not_preserved'
            remaining_dates.remove(declared)
    # Preserve every already-retained structured record exactly, independently
    # of its ordinal or host framing after DOM serialization. No fact merging.
    def records(proposal):
        return [proposal['text'][e['start_byte']:e['end_byte']] for e in
                (proposal['provenance'].get('structured_data') or {}).get('entries', [])]
    remaining = list(records(rendered))
    for record in records(static):
        if record not in remaining:
            return 'structured_record_not_preserved'
        remaining.remove(record)
    if len(after) <= len(before):
        return 'no_body_growth'
    if not (_tokens(after) - _tokens(before)):
        return 'no_new_authored_token'
    return 'rendered_with_preservation'


def supervision_schema():
    from .discovery_metadata import object_schema
    count = {'type': 'integer', 'minimum': 0}
    nullable_count = {'type': ['integer', 'null'], 'minimum': 0}
    return object_schema({'method': {'const': 'isolated-render/1'},
        'trigger': {'enum': ['thin_script_html', 'static_extraction_failed']},
        'decision': {'type': 'string', 'maxLength': 64},
        'selected_stage': {'enum': ['static', 'render']},
        'network_usage_complete': {'type': 'boolean'},
        'known_http_request_count': count, 'known_http_response_count': count,
        'known_decoded_body_bytes': count,
        'render_request_grant': count, 'render_decoded_byte_grant': count,
        'render_outcome': {'enum': ['not_started', 'prepared', 'failed', 'terminated']},
        'render_error_code': {'type': ['string', 'null'], 'maxLength': 64},
        'render_http_request_count': nullable_count, 'render_http_response_count': nullable_count,
        'render_decoded_body_bytes': nullable_count})
