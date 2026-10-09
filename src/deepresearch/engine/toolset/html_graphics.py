"""Retain declared labels of inline table graphics after content selection.

No geometry, CSS names, symbol names or surrounding product knowledge supply a
value. The caller must already have selected the DOM it renders. Labels remain
authored text; uncertainty lives in provenance, never in a fabricated quotation.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from itertools import islice
import re

from .common import digest

MAX_NODES = 20000
MAX_GRAPHICS = 128
MAX_ENTRIES = 32
MAX_LABEL = 256
MAX_REFS = 4
TABLE_MARKER = 'data-deepresearch-graphic-table'


def diagnostic_schema():
    from .discovery_metadata import object_schema
    count = {'type': 'integer', 'minimum': 0}
    flag = {'type': 'boolean'}
    entry = object_schema({
        'selected_dom_path': {'type': ['string', 'null'], 'maxLength': 256},
        'parsed_svg_sha256': {'type': 'string'},
        'status': {'enum': ['source_label', 'unresolved']},
        'reason': {'type': 'string', 'maxLength': 80},
        'label_origins': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
    })
    return object_schema({
        'method': {'const': 'selected-svg-labels/1'},
        'semantic_verification': {'const': False},
        'selection_bound': flag, 'coverage_complete': flag,
        'selected_svg_count': count, 'labelled_svg_count': count,
        'unresolved_svg_count': count, 'unassessed_candidate_count': count,
        'author_hidden_svg_count': count, 'presentational_svg_count': count,
        'entries_truncated': flag, 'entries': {'type': 'array', 'maxItems': MAX_ENTRIES, 'items': entry},
    })


def _empty():
    return {'method': 'selected-svg-labels/1', 'semantic_verification': False,
        'selection_bound': True, 'coverage_complete': True,
        'selected_svg_count': 0, 'labelled_svg_count': 0, 'unresolved_svg_count': 0,
        'unassessed_candidate_count': 0, 'author_hidden_svg_count': 0,
        'presentational_svg_count': 0, 'entries_truncated': False, 'entries': []}


def unbound_diagnostic(scope):
    """Candidate counts disclose an unassessed scope, not selected evidence."""
    if scope is None:
        return None
    nodes = list(islice(scope.iter(), MAX_NODES + 1))
    count = sum(n.tag == 'svg' for n in nodes[:MAX_NODES])
    if not count and len(nodes) <= MAX_NODES:
        return None
    result = _empty()
    result.update(selection_bound=False, coverage_complete=False,
                  unassessed_candidate_count=count)
    return result


def _bounded(value):
    value = value.strip()
    if not value or len(value) > MAX_LABEL or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', value):
        raise ValueError('invalid_or_oversize_label')
    return value


def _metadata_text(node):
    nodes = list(islice(node.iter(), 33))
    if len(nodes) > 32 or any(n.tag not in {'span', 'title', 'desc', 'b', 'i', 'em', 'strong'}
                             or n.get('aria-label') or n.get('aria-labelledby') for n in nodes):
        raise ValueError('unsupported_label_subtree')
    return _bounded(''.join(node.itertext()))


def _labels(svg, table, id_counts):
    """A bounded explicit-metadata subset, not a browser accessible-name engine."""
    passive = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline',
               'polygon', 'title', 'desc', 'defs', 'lineargradient', 'radialgradient',
               'stop', 'clippath', 'mask', 'use', 'span', 'b', 'i', 'em', 'strong'}
    if (svg.xpath('.//svg|.//text|.//foreignobject|.//script|.//style')
            or any(n.tag not in passive for n in svg.iter() if isinstance(n.tag, str))):
        raise ValueError('outside_inline_nontext_subset')
    records = []
    if svg.get('aria-labelledby') is not None:
        refs = svg.get('aria-labelledby').split()
        if not refs or len(refs) > MAX_REFS or len(refs) != len(set(refs)):
            raise ValueError('invalid_label_references')
        values = []
        for ref in refs:
            if id_counts is None:
                raise ValueError('unverified_document_id_uniqueness')
            if id_counts.get(ref) != 1:
                raise ValueError('missing_ambiguous_or_outside_reference')
            matches = [n for n in table.iter() if n.get('id') == ref]
            if len(matches) != 1:
                raise ValueError('missing_ambiguous_or_outside_reference')
            values.append(_metadata_text(matches[0]))
        records.append(('aria-labelledby', _bounded(' '.join(values))))
    if svg.get('aria-label') is not None:
        records.append(('aria-label', _bounded(svg.get('aria-label'))))
    titles, descriptions = svg.findall('title'), svg.findall('desc')
    if len(titles) > 1 or len(descriptions) > 1:
        raise ValueError('multiple_direct_titles_or_descriptions')
    if svg.get('title') is not None:
        records.append(('title-attribute', _bounded(svg.get('title'))))
    for child in svg:
        if child.tag in {'title', 'desc'}:
            records.append(('svg-title' if child.tag == 'title' else 'svg-desc', _metadata_text(child)))
    names = {value for kind, value in records if kind != 'svg-desc'}
    if len(names) > 1:
        raise ValueError('conflicting_source_labels')
    if not records:
        raise ValueError('no_explicit_label')
    # Unknown text nodes in geometry cannot silently disappear on replacement.
    declared = ''.join(''.join(child.itertext()) for child in svg if child.tag in {'title', 'desc'})
    compact = lambda value: ''.join(value.split())
    if compact(''.join(svg.itertext())) != compact(declared):
        raise ValueError('unclassified_svg_text')
    return records


def project_selected_graphics(scope, *, source_tree=None):
    """Return an inert rendering copy plus bounded provenance of selected SVGs."""
    from lxml import etree, html

    nodes = list(islice(scope.iter(), MAX_NODES + 1))
    graphics = [n for n in nodes[:MAX_NODES] if n.tag == 'svg']
    if not graphics and len(nodes) <= MAX_NODES:
        return scope, None
    diagnostic = _empty()
    if len(nodes) > MAX_NODES or len(graphics) > MAX_GRAPHICS:
        diagnostic.update(coverage_complete=False, selected_svg_count=len(graphics),
                          unresolved_svg_count=len(graphics), entries_truncated=True)
        return scope, diagnostic
    projected = deepcopy(scope)
    copies = dict(zip(scope.iter(), projected.iter()))
    id_counts = None
    if any(n.get('aria-labelledby') is not None for n in graphics):
        # ID uniqueness is document-wide even when its text may only come from
        # the selected table. Count excluded/hidden IDs without reading labels
        # from their surrounding content into the selected rendering.
        origin = scope if source_tree is None else source_tree
        original_nodes = list(islice(origin.getroottree().getroot().iter(), MAX_NODES + 1))
        if len(original_nodes) <= MAX_NODES:
            id_counts = Counter(n.get('id') for n in original_nodes if n.get('id') is not None)
    diagnostic['selected_svg_count'] = len(graphics)
    for svg in graphics:
        ancestors = list(svg.iterancestors())
        hidden = any(n.get('aria-hidden', '').strip().lower() == 'true' for n in [svg, *ancestors])
        presentational = svg.get('role', '').strip().lower() in {'none', 'presentation'}
        diagnostic['author_hidden_svg_count'] += int(hidden)
        diagnostic['presentational_svg_count'] += int(presentational)
        path = svg.getroottree().getpath(svg)
        entry = {'selected_dom_path': path if len(path) <= 256 else None,
            'parsed_svg_sha256': digest(etree.tostring(svg, with_tail=False)),
            'status': 'unresolved', 'reason': '', 'label_origins': []}
        table = next((n for n in ancestors if n.tag == 'table'), None)
        cell = next((n for n in ancestors if n.tag in {'td', 'th'}), None)
        if table is not None:
            copies[table].set(TABLE_MARKER, '1')
        try:
            if hidden or presentational:
                raise ValueError('author_hidden' if hidden else 'author_presentational')
            if (cell is None or table is None or any(n.tag in {'pre', 'code', 'svg', 'math'} for n in ancestors)
                    or any('hidden' in n.attrib for n in [svg, *ancestors])):
                raise ValueError('outside_inline_table_subset')
            records = _labels(svg, table, id_counts)
            replacement = html.Element('span')
            # Only authored text is inserted; no invented "yes", "no" or
            # "unknown" marker can be mistaken for a source quotation.
            values = [value for kind, value in records if kind in {'svg-title', 'svg-desc'}]
            # Repeated title/description text was authored twice; do not erase
            # it while deduplicating equivalent attribute naming claims.
            for kind, value in reversed(records):
                if kind not in {'svg-title', 'svg-desc'} and value not in values:
                    values.insert(0, value)
            replacement.text, replacement.tail = ' '.join(values), copies[svg].tail
            copies[svg].getparent().replace(copies[svg], replacement)
            entry.update(status='source_label', reason='explicit_source_metadata',
                         label_origins=[kind for kind, _ in records])
            diagnostic['labelled_svg_count'] += 1
        except ValueError as error:
            entry['reason'] = str(error)
            diagnostic['unresolved_svg_count'] += 1
        if len(diagnostic['entries']) < MAX_ENTRIES:
            diagnostic['entries'].append(entry)
    diagnostic['entries_truncated'] = len(graphics) > len(diagnostic['entries'])
    return projected, diagnostic
