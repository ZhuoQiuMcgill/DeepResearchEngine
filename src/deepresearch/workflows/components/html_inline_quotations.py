"""Original-index views of inline presentation inside explicit HTML blocks.

Only complete balanced blocks qualify. Separate paragraphs, cells, list items
and code blocks never become one plain-text sequence. Table-wide views retain
all relationship tags while omitting verified inline presentation tags.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re

from .html_quotations import _without_markdown_code

_BLOCKS = {'p', 'td', 'th', 'dt', 'dd', 'li', 'pre'}
_INLINE = {'span', 'b', 'strong', 'i', 'em', 'code', 'a'}
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
_OPAQUE = {'script', 'style', 'textarea', 'math', 'svg', 'noscript', 'template'}
_BLOCK_ATTRS = {'id', 'title', 'scope', 'headers', 'rowspan', 'colspan', 'value'}


@dataclass
class _Node:
    tag: str
    attrs: list
    start: int
    content: int
    parent: _Node | None
    end: int = 0
    close: int = 0
    valid: bool = True
    children: list = field(default_factory=list)


def _inline(node):
    if not node.valid or not node.end or node.tag not in _INLINE:
        return False
    names = [name for name, _ in node.attrs]
    if len(set(names)) != len(names):
        return False
    allowed = {'id', 'title', 'href'} if node.tag == 'a' else {'id'}
    if set(names) - allowed:
        return False
    if node.tag == 'a':
        href = dict(node.attrs).get('href')
        if href is not None and not href.lower().startswith(('https://', 'http://', 'mailto:', 'tel:')):
            return False
    # A hard break remains literal, but need not invalidate balanced inline
    # presentation elsewhere in the same wrapper.
    return all(_inline(child) or (child.tag == 'br' and child.valid and child.end
                                 and not child.attrs) for child in node.children)


def _ancestors(node):
    while node.parent is not None:
        node = node.parent
        yield node


def inline_html_projections(text):
    """Yield (visible original characters, indexes, prose-or-literal mode)."""
    starts = [0, *(m.end() for m in re.finditer('\n', text))]
    masked = _without_markdown_code(text)
    from markdown_it import MarkdownIt
    try:
        tokens = MarkdownIt('commonmark').parse(text)
    except (IndexError, RecursionError):
        return
    protected = bytearray(len(text))
    for token in tokens:
        if token.type in {'fence', 'code_block'} and token.map is not None:
            begin, end = token.map
            left = starts[begin]
            right = starts[end] if end < len(starts) else len(text)
            protected[left:right] = b'\1' * (right - left)
    masked = ''.join(' ' if protected[i] and c not in '\r\n' else c for i, c in enumerate(masked))
    nodes, stack = [], []

    class LimitReached(Exception):
        pass

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)

        def position(self):
            line, column = self.getpos()
            return starts[line - 1] + column

        def handle_starttag(self, tag, attrs):
            if len(nodes) >= 32768 or len(stack) >= 128:
                raise LimitReached
            start = self.position()
            end = start + len(self.get_starttag_text())
            node = _Node(tag, attrs, start, end, stack[-1] if stack else None)
            if node.parent is not None:
                node.parent.children.append(node)
            nodes.append(node)
            if tag in _VOID:
                node.close = node.end = end
            else:
                stack.append(node)

        def handle_endtag(self, tag):
            if not stack or stack[-1].tag != tag:
                # No browser-style repair of malformed nesting is evidence.
                for node in stack:
                    node.valid = False
                return
            node = stack.pop()
            node.close = self.position()
            node.end = text.find('>', node.close) + 1

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag not in _VOID:
                node = stack.pop()
                node.close = node.end = node.content
                node.valid = False

        def handle_comment(self, data):
            for node in stack:
                node.valid = False

    parser = Parser()
    try:
        parser.feed(masked)
        parser.close()
    except LimitReached:
        return
    omissions = []
    for node in nodes:
        if node.tag not in _BLOCKS or not node.valid or not node.end:
            continue
        parents = list(_ancestors(node))
        if (len(dict(node.attrs)) != len(node.attrs) or set(dict(node.attrs)) - _BLOCK_ATTRS
                or any(p.tag in _OPAQUE or p.tag in {'pre', 'code'} or not p.valid
                       or any(a in {'hidden', 'style'} for a, _ in p.attrs) for p in parents)
                or masked[node.start:node.end] != text[node.start:node.end]):
            continue
        # A list/definition containing paragraphs supplies each paragraph's own
        # view; the parent cannot flatten those separate structural blocks.
        removed = []
        def mark(child):
            if child.tag == 'br':
                return
            removed.extend(((child.start, child.content), (child.close, child.end)))
            for inner in child.children:
                mark(inner)
        for child in node.children:
            # Unsupported siblings stay literal, including their boundaries.
            # A later line break or annotation cannot disable an earlier link.
            if _inline(child):
                mark(child)
        if not removed:
            continue
        kept = bytearray(b'\1' * (node.close - node.content))
        for left, right in removed:
            kept[left - node.content:right - node.content] = b'\0' * (right - left)
        positions = [node.content + i for i, keep in enumerate(kept) if keep]
        if positions:
            mode = 'literal' if node.tag == 'pre' else 'html_prose'
            yield ''.join(text[i] for i in positions), positions, mode
        if node.tag != 'pre':
            omissions.extend(removed)
    for table in nodes:
        if table.tag != 'table' or not table.valid or not table.end:
            continue
        if (masked[table.start:table.end] != text[table.start:table.end]
                or any(p.tag in _OPAQUE or p.tag in {'pre', 'code'} or not p.valid for p in _ancestors(table))):
            continue
        removed = [(a, b) for a, b in omissions if table.content <= a < b <= table.close]
        if not removed:
            continue
        kept = bytearray(b'\1' * (table.end - table.start))
        for left, right in removed:
            kept[left - table.start:right - table.start] = b'\0' * (right - left)
        positions = [table.start + i for i, keep in enumerate(kept) if keep]
        yield ''.join(text[i] for i in positions), positions, 'literal'
