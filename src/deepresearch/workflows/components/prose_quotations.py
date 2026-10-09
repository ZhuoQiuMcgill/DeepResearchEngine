"""Paired double-quote delimiters in exactly mapped CommonMark prose.

Only top-level paragraphs qualify. Parsed code, link destinations/titles, raw
HTML, escaped/entity-decoded text and unsupported syntax grant no equivalence.
The private comparison markers cannot occur in valid UTF-8 evidence. They keep
literal curly quotes in protected contexts distinct from prose delimiters.
"""
from __future__ import annotations

import re
import unicodedata

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from .markdown_quotations import _link_end

_OPEN, _CLOSE = '\ud800', '\ud801'
_PAIRS = re.compile(r'“([^“”"]{1,2046})”|"([^“”"]{1,2046})"')
_URL = re.compile(r'(?:[A-Za-z][A-Za-z0-9+.-]*://|mailto:|www\.)[^\s]+')
_WORD = re.compile(r'[^\W\d_]{2,}', re.UNICODE)


def _delimiters(visible, positions):
    # CommonMark has no math token. Ambiguous formula/prime syntax therefore
    # disables this optional comparison for the whole paragraph.
    if any(c in '$\\^_′″‴' or unicodedata.category(c) == 'Sm' for c in visible):
        return {}
    # A URL's characters remain literal even when a Markdown parser calls it
    # ordinary text. Suppress its quote glyphs before considering prose pairs.
    protected = set()
    for url in _URL.finditer(visible):
        protected.update(range(url.start(), url.end()))
    result = {}
    for match in _PAIRS.finditer(visible):
        left, right = match.start(), match.end() - 1
        body = match.group(1) if match.group(1) is not None else match.group(2)
        if (left in protected or right in protected
                or (left and visible[left - 1] not in ' \t\r\n([{—–:;')
                or (right + 1 < len(visible) and (visible[right + 1].isalnum() or visible[right + 1] == '_'))
                or body != body.strip() or _WORD.search(body) is None
                or any(c in '$\\^_=+*/<>[]{}′″‴' or unicodedata.category(c) == 'Sm' for c in body)):
            continue
        result[positions[left]], result[positions[right]] = _OPEN, _CLOSE
    return result


def _inline_text(token):
    """Account for every raw character; expose only parsed prose text."""
    text, cursor, link = token.content, 0, None
    visible, positions = [], []
    for child in token.children or []:
        if child.type in {'strong_open', 'strong_close', 'em_open', 'em_close'}:
            value = child.markup
        elif child.type == 'link_open':
            if link is not None or not text.startswith('[', cursor):
                return None
            link = child, cursor + 1
            cursor += 1
            continue
        elif child.type == 'link_close':
            if link is None or not 0 < cursor - link[1] <= 1024:
                return None
            end = _link_end(text, cursor, link[0])
            if end is None:
                return None
            cursor, link = end, None
            continue
        elif child.type == 'text':
            value = child.content
            visible.extend(value)
            positions.extend(range(cursor, cursor + len(value)))
        elif child.type == 'softbreak':
            gap = re.match(r'[ \t]*\n', text[cursor:])
            if gap is None:
                return None
            value = gap.group()
            visible.extend(value)
            positions.extend(range(cursor, cursor + len(value)))
        elif child.type == 'code_inline':
            marker = child.markup
            end = re.search(r'(?<!`)' + re.escape(marker) + r'(?!`)', text[cursor + len(marker):])
            if not text.startswith(marker, cursor) or end is None:
                return None
            value = text[cursor:cursor + len(marker) + end.end()]
            # A protected placeholder preserves the surrounding prose's pair
            # boundaries without exposing any code-body delimiter as prose.
            visible.append('\0')
            positions.append(cursor)
        else:
            return None
        if not text.startswith(value, cursor):
            return None
        cursor += len(value)
    if cursor != len(text) or link is not None:
        return None
    return ''.join(visible), positions


def prose_delimiters(text):
    """Return original offsets of bounded, balanced prose double delimiters.

    The caller supplies admitted HTML-derived Markdown with known document-start
    context. This function never reparses a formatting projection as evidence.
    Unsupported paragraphs retain literal matching; other blocks are excluded.
    """
    if not any(c in text for c in '“”"'):
        return {}
    try:
        root = SyntaxTreeNode(MarkdownIt('commonmark').enable('table').parse(text))
    except (IndexError, RecursionError):
        return {}
    starts = [0, *(m.end() for m in re.finditer('\n', text)), len(text)]
    result = {}
    for node in root.children:
        if node.type != 'paragraph' or len(node.children) != 1 or node.children[0].type != 'inline':
            continue
        token = node.children[0].token
        left, right = (starts[i] for i in token.map)
        raw = text[left:right]
        # CommonMark normalizes CRLF. Map that known line-break operation back
        # before locating token text; only delimiter offsets use this view.
        raw_positions = [i for i, c in enumerate(raw) if c != '\r' or raw[i:i + 2] != '\r\n']
        comparison = ''.join(raw[i] for i in raw_positions)
        if not token.content or comparison.count(token.content) != 1:
            continue
        mapped = _inline_text(token)
        if mapped is None:
            continue
        begin = comparison.index(token.content)
        visible, positions = mapped
        result.update(_delimiters(visible, [left + raw_positions[begin + i] for i in positions]))
    return result


def delimiter_projection(text, delimiters, positions=None):
    """Replace only verified endpoints, keeping the existing original map."""
    return ''.join(delimiters.get(i, c) for c, i in zip(text, positions if positions is not None else range(len(text))))
