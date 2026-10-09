"""Select omitted structures beside retained prose without expanding a page.

This projects the source DOM in source order. It uses no URL, topic, or CSS-name
rules. Callers must still verify preservation of prior evidence and rendering.
"""
from __future__ import annotations

from copy import deepcopy

from .html_recovery import _compact


def _text(node):
    return _compact(''.join(node.itertext()))


def _intact(original, projected):
    """Verify the resulting subtree, including structure retained via children."""
    if original.tag != projected.tag or original.attrib != projected.attrib:
        return False
    before, after = ''.join(original.itertext()), ''.join(projected.itertext())
    if (before != after if original.tag in {'pre', 'code'} else _compact(before) != _compact(after)):
        return False
    left = [n for n in original if isinstance(n.tag, str)]
    right = [n for n in projected if isinstance(n.tag, str)]
    return len(left) == len(right) and all(_intact(a, b) for a, b in zip(left, right))


def _section_anchored(section, anchors, block):
    # A nested section has its own scope and cannot borrow its parent's prose.
    paragraphs = [p for p in section.iter('p') if len(_text(p)) >= 40
        and block not in p.iterancestors()
        and next((a for a in p.iterancestors() if a.tag == 'section'), None) is section]
    retained = [p for p in paragraphs if p in anchors]
    return len(retained) >= 2 and sum(len(_text(p)) for p in retained) >= .8 * sum(len(_text(p)) for p in paragraphs)


def _retain_headings(block, section, complete):
    """Keep local headings that give a recovered block its original context."""
    branch = block
    for parent in block.iterancestors():
        for sibling in parent:
            if sibling is branch:
                continue
            headings = [n for n in sibling.iter() if n.tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}]
            if (len(headings) == 1 and _text(sibling) == _text(headings[0])
                    and not any(n.tag in {'p', 'ul', 'ol', 'dl', 'table', 'pre'} for n in sibling.iter())):
                complete.add(headings[0])
        if parent is section:
            break
        branch = parent


def select_anchored_structure(scope, document, damaged):
    return _select(scope, document, damaged, prose=False)


def select_prose(scope, document, missing):
    """Project missing paragraphs within one explicit article/main boundary."""
    if scope.tag not in {'article', 'main'} and scope.get('role') != 'main':
        return None, 0
    missing = [p for p in missing if p.tag == 'p' and len(_text(p)) >= 80
               and not any(a.tag == 'article' and a is not scope for a in p.iterancestors())]
    return _select(scope, document, missing, prose=True)


def _select(scope, document, damaged, *, prose):
    projected = deepcopy(scope)
    copies = dict(zip(scope.iter(), projected.iter()))
    selected = _text(document)
    anchors = {node for node in projected.iter('p') if len(_text(node)) >= 40 and _text(node) in selected}
    complete, text_slots = set(), set()
    for node in projected.iter():
        if not isinstance(node.tag, str):
            continue
        text = _text(node)
        if text and text in selected:
            complete.add(node)
        for attribute in ('text', 'tail'):
            value = _compact(getattr(node, attribute) or '')
            if value and value in selected:
                text_slots.add((node, attribute))

    record_matcher = None
    for original in damaged:
        block = copies[original]
        if prose:
            complete.add(block)
            _retain_headings(block, projected, complete)
            continue
        if original.tag in {'ol', 'ul'}:
            from .html_records import RecordMatcher
            if record_matcher is None:
                record_matcher = RecordMatcher(document)
            if record_matcher.retains_records(original):
                complete.add(block)
                continue
        branch = block
        for parent in block.iterancestors():
            if parent.tag in {'body', 'html'} or (parent is projected and parent.tag != 'section'):
                break
            if parent.tag == 'section' and _section_anchored(parent, anchors, block):
                complete.add(block)
                _retain_headings(block, parent, complete)
                break
            # Unwrap a single paragraph, not an unrelated article/card subtree.
            siblings = [list(child.iter('p')) for child in parent if child is not branch]
            if any(len(paragraphs) == 1 and paragraphs[0] in anchors for paragraphs in siblings):
                paragraphs = [p for p in parent.iter('p') if len(_text(p)) >= 40]
                covered = sum(len(_text(p)) for p in paragraphs if p in anchors)
                if covered >= .8 * sum(len(_text(p)) for p in paragraphs):
                    complete.add(block)
                # A weak local context must not be replaced by a larger wrapper.
                break
            if parent.tag == 'section':
                break  # Never borrow anchors from outside this authored section.
            branch = parent

    def trim(node):
        if node in complete:
            return True
        if (node, 'text') not in text_slots and not (node.text or '').isspace():
            node.text = None
        for child in list(node):
            tail = child.tail
            if (child, 'tail') not in text_slots and not (tail or '').isspace():
                tail = None
            child.tail = tail
            if not isinstance(child.tag, str) or not trim(child):
                previous = child.getprevious()
                if tail:
                    if previous is None:
                        node.text = (node.text or '') + tail
                    else:
                        previous.tail = (previous.tail or '') + tail
                node.remove(child)
        return bool(len(node) or (node.text or '').strip())

    trim(projected)
    surviving = set(projected.iter())
    recovered = sum(copies[node] in surviving and _intact(node, copies[node]) for node in damaged)
    if not recovered:
        return None, 0
    return projected, recovered
