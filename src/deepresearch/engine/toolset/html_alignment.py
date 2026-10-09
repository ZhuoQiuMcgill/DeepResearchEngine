"""Explain extractor flattening using whole source DOM text slots.

This is only a preservation guard for re-rendering original source structure.
It does not validate quotations or synthesize missing words and numbers.
"""
from __future__ import annotations

from .html_recovery import _compact

BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "dd", "td", "th"}
BOUNDARIES = BLOCKS | {"section", "article", "main", "ol", "ul", "dl", "table", "tr", "pre", "code", "blockquote"}
MAX_WORK = 2_000_000
MAX_UNIT = 65_536
MAX_SLOTS = 2048
MAX_STATES = 512


class _Limit(Exception):
    pass


class DOMSlotMatcher:
    """One shared work bound covers indexing and every attempted unit match."""

    def __init__(self, scope):
        self.scope = scope
        self.remaining = MAX_WORK
        self.blocks = None

    def _charge(self, amount=1):
        self.remaining -= amount
        if self.remaining < 0:
            raise _Limit

    def _blocks(self):
        result = []
        for node in self.scope.iter():
            self._charge()
            if node.tag not in BLOCKS | {"div"}:
                continue
            literal = False
            for parent in node.iterancestors():
                self._charge()
                if parent.tag in {"pre", "code"}:
                    literal = True
                    break
            if literal:
                continue
            # A list item/cell may contain div wrappers, but never borrow from
            # another record, paragraph or literal. A div must be a leaf block.
            boundaries = BOUNDARIES | {"div"} if node.tag == "div" else BOUNDARIES
            for child in node.iterdescendants():
                self._charge()
                if child.tag in boundaries:
                    break
            else:
                slots = []
                for text in node.itertext():
                    self._charge(len(text) + 1)
                    slot = _compact(text)
                    if slot:
                        slots.append(slot)
                    if len(slots) > MAX_SLOTS:
                        break
                else:
                    if slots:
                        result.append(tuple(slots))
        return result

    def retains(self, text):
        try:
            self._charge(len(text) + 1)
            needle = _compact(text)
            if not needle or len(needle) > MAX_UNIT:
                return False
            if self.blocks is None:
                self.blocks = self._blocks()
            for slots in self.blocks:
                states = {0}
                for slot in slots:
                    advanced = set()
                    for offset in sorted(states):
                        self._charge(min(len(slot), len(needle) - offset) + 1)
                        if needle.startswith(slot, offset):
                            advanced.add(offset + len(slot))
                    if len(needle) in advanced:
                        return True
                    states.update(advanced)
                    if len(states) > MAX_STATES:
                        break
            return False
        except _Limit:
            # Limits must never become evidence of retention.
            return False
