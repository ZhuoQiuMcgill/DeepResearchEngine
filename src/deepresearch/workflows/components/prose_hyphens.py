"""Narrow source-index comparison of ASCII/nonbreaking lexical hyphens.

Callers admit HTML-derived Markdown and recorded document-start context. Only
exactly mapped top-level paragraphs and flat unordered-list paragraphs qualify.
This is a comparison map, never rewritten evidence or Unicode normalization.
"""
from __future__ import annotations

import re
import unicodedata

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from .prose_quotations import _inline_text

_HYPHEN = '\ud802'  # Impossible in valid UTF-8 evidence; distinct from quote markers.
_COMPOUND = re.compile(r'(?<![\w.\-/@:+‑])(?:[a-z]{2,}|[0-9]{1,3})[-‑][a-z]{2,}(?![\w\-/@:+‑]|\.\w)')
_URL = re.compile(r'(?:[A-Za-z][A-Za-z0-9+.-]*:|www\.)[^\s\0]+|(?:[\w‑-]+\.)+[A-Za-z]{2,}(?:[/?:#][^\s\0]*)?')


def _hyphens(visible, positions, compounds):
    # CommonMark has no math grammar. Fail closed on ambiguous notation in
    # the mapped prose; code-body placeholders never expose code characters.
    if any(c in '$\\^_=+*/<>[]{}′″‴' or unicodedata.category(c) == 'Sm' for c in visible):
        return {}
    protected = set()
    for match in _URL.finditer(visible):
        protected.update(range(match.start(), match.end()))
    result = {}
    for match in _COMPOUND.finditer(visible):
        if any(i in protected for i in range(match.start(), match.end())):
            continue
        for i in range(match.start(), match.end()):
            if visible[i] in '-‑':
                result[positions[i]] = _HYPHEN
                compounds[positions[i]] = (positions[match.start()], positions[match.end() - 1] + 1)
    return result


def _positions(token, text, starts, *, list_item=False):
    """Verify raw lines including CRLF and each explicit continuation prefix."""
    first, last = token.map
    values = token.content.split('\n')
    if len(values) != last - first:
        return None
    positions, width = [], None
    for line, value in zip(range(first, last), values):
        raw = text[starts[line]:starts[line + 1]].removesuffix('\n').removesuffix('\r')
        if list_item:
            if width is None:
                marker = re.match(r' {0,3}[-+*][ ]{1,4}', raw)
                if marker is None:
                    return None
                width = marker.end()
            prefix = raw[:width] if line == first else ' ' * width
        else:
            prefix = re.match(r' {0,3}', raw).group()
        if raw != prefix + value:
            return None
        positions.extend(range(starts[line] + len(prefix), starts[line] + len(raw)))
        if line + 1 < last:
            # Map normalized LF to the original LF, retaining CR in evidence.
            positions.append(starts[line + 1] - 1)
    return positions


def prose_hyphens(text, *, compounds=None):
    """Return only original offsets of admitted hyphens, with bounded parsing.

    Lowercase word compounds and small integer-to-lowercase-word compounds
    qualify. Numeric interiors/ranges, minus, uppercase/dotted/underscored or
    slash-separated identifiers remain literal. Ambiguous ordinary lowercase
    hyphenated identifiers cannot be distinguished semantically from prose.
    Unsupported mapping, parser failure and other block types grant nothing.
    """
    if type(text) is not str or len(text) > 2162688 or not any(c in text for c in '-‑'):
        return {}
    try:
        if len(text.encode('utf-8', errors='strict')) > 2162688:
            return {}
        root = SyntaxTreeNode(MarkdownIt('commonmark').enable('table').parse(text))
    except (UnicodeError, IndexError, RecursionError):
        return {}
    starts = [0, *(m.end() for m in re.finditer('\n', text)), len(text)]
    if compounds is None:
        compounds = {}
    result = {}
    for node in root.children:
        if node.type == 'paragraph':
            paragraphs = [(node, False)]
        elif node.type == 'bullet_list' and node.children and all(
                len(item.children) == 1 and item.children[0].type == 'paragraph'
                for item in node.children):
            paragraphs = [(item.children[0], True) for item in node.children]
        else:
            continue
        for paragraph, list_item in paragraphs:
            if len(paragraph.children) != 1 or paragraph.children[0].type != 'inline':
                continue
            token = paragraph.children[0].token
            mapped = _inline_text(token)
            raw_positions = _positions(token, text, starts, list_item=list_item)
            if mapped is None or raw_positions is None:
                continue
            visible, positions = mapped
            result.update(_hyphens(visible, [raw_positions[i] for i in positions], compounds))
    return result
