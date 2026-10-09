"""Authorize recovery from the retained fields of each original list record.

This is a scope check, not fuzzy text matching: a selected prefix must consist
of whole original DOM slots, in order, after a unique record anchor. Rendering
and evidence-preservation checks remain the caller's responsibility.
"""
from __future__ import annotations

from collections import Counter
import re

from .html_recovery import _compact

MAX_RECORDS = 128
MAX_SLOTS = 512
MAX_CHARS = 65536
MAX_UNITS = 8192
MAX_DOCUMENT_CHARS = 262144
MAX_STATES = 512
MAX_WORK = 2_000_000


class RecordMatcher:
    def __init__(self, document):
        from .html_structure import _text_units

        self.work = MAX_WORK
        self.units = []
        size = 0
        for text in _text_units(document):
            unit = _compact(text)
            if not unit:
                continue
            size += len(unit)
            if len(self.units) >= MAX_UNITS or size > MAX_DOCUMENT_CHARS:
                self.units = []
                break
            self.units.append(unit)
        counts = Counter(self.units)
        self.anchors = {unit: index for index, unit in enumerate(self.units) if counts[unit] == 1}

    def retains_records(self, block):
        if block.tag not in {'ol', 'ul'} or not self.units or self.work <= 0:
            return False
        records = [node for node in block if isinstance(node.tag, str)]
        if (not 2 <= len(records) <= MAX_RECORDS or len({r.tag for r in records}) != 1
                or records[0].tag not in {'li', 'div'} or _compact(block.text or '')
                or any(_compact(r.tail or '') for r in records)):
            return False
        rows, size = [], 0
        for record in records:
            slots = []
            for text in record.itertext():
                slot = _compact(text)
                if not slot:
                    continue
                size += len(slot)
                if len(slots) >= MAX_SLOTS or size > MAX_CHARS:
                    return False
                slots.append(slot)
            if not slots:
                return False
            rows.append(slots)
        counts = Counter(slot for row in rows for slot in set(row))
        anchors = []
        for row in rows:
            anchor = next((slot for slot in row if len(slot) >= 4 and re.search(r'\w', slot)
                           and counts[slot] == 1 and slot in self.anchors), None)
            if anchor is None:
                return False
            anchors.append(self.anchors[anchor])
        if anchors != sorted(set(anchors)):
            return False
        for row, start, end in zip(rows, anchors, [*anchors[1:], len(self.units)]):
            if not self._retains_record(row, start, end):
                return False
        return True

    def _retains_record(self, row, start, end):
        total = sum(map(len, row))
        parts, boundaries, size = [], set(), 0
        for unit in self.units[start:end]:
            if size + len(unit) > total:
                break
            parts.append(unit)
            size += len(unit)
            boundaries.add(size)
        if len(parts) < 3 or size * 5 < total * 4:
            return False
        needle, states = ''.join(parts), {0}
        for slot in row:
            advanced = set()
            for offset in sorted(states):
                self.work -= min(len(slot), len(needle) - offset) + 1
                if self.work < 0:
                    return False
                if needle.startswith(slot, offset):
                    advanced.add(offset + len(slot))
            states.update(advanced)
            if len(states) > MAX_STATES:
                return False
        # Stop only at a selected unit boundary. A substring of a number or
        # field must not authorize insertion of the rest of a source record.
        return max(states & boundaries, default=0) * 5 >= total * 4
