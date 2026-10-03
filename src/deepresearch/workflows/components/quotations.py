"""Locate an exact saved substring, permitting whitespace and PDF soft wraps."""
from __future__ import annotations

import re

_SOFT_WORD = re.compile(r"(?<!\w)[A-Za-z]+(?:-[ \t]*\r?\n[ \t]*[A-Za-z]+)+(?!\w)")
_SOFT_SEPARATOR = re.compile(r"-[ \t]*\r?\n[ \t]*")


def _normalized(value, join_words):
    omitted = bytearray(len(value))
    if join_words:
        for word in _SOFT_WORD.finditer(value):
            for separator in _SOFT_SEPARATOR.finditer(value, word.start(), word.end()):
                omitted[separator.start():separator.end()] = b"\1" * (separator.end() - separator.start())
    output, spans = [], []
    for index, character in enumerate(value):
        if omitted[index]:
            continue
        if character.isspace():
            if output and output[-1] == " ":
                spans[-1] = (spans[-1][0], index + 1)
                continue
            character = " "
        output.append(character)
        spans.append((index, index + 1))
    return "".join(output), spans


def locate_quote(quote: str, text: str) -> str | None:
    """Return an original contiguous saved substring, or None.

    Case, punctuation, letters, numbers and order remain exact. Whitespace may
    differ. ASCII alphabetic fragments separated by hyphen + LF/CRLF (optional
    horizontal whitespace) may join on BOTH query and source sides. Inline
    hyphens and number/identifier wraps are preserved; no fuzzy or Unicode
    compatibility matching occurs. The whitespace-only comparison remains
    available for quotations explicitly retaining a wrapped hyphen.

    Select the earliest original match across both comparisons, breaking a
    same-start tie by the shorter span. Ambiguity does not imply uniqueness.
    Quote and returned span are bounded to 2048 characters; text to 65536 UTF-8
    bytes. Invalid/empty/oversized input returns None. The index map is used
    only to slice original text: callers compute offsets/digests from that
    original substring, never from normalized comparison text.
    """
    if (type(quote) is not str or type(text) is not str or not quote
            or len(quote) > 2048 or len(text) > 65536):
        return None
    try:
        quote.encode("utf-8", errors="strict")
        if len(text.encode("utf-8", errors="strict")) > 65536:
            return None
    except UnicodeError:
        return None
    matches = []
    for join_words in (False, True):
        needle, _ = _normalized(quote, join_words)
        needle = needle.strip()
        if not needle:
            return None
        haystack, spans = _normalized(text, join_words)
        found = haystack.find(needle)
        if found >= 0:
            matches.append((spans[found][0], spans[found + len(needle) - 1][1]))
    if not matches:
        return None
    start, end = min(matches, key=lambda pair: (pair[0], pair[1]))
    return text[start:end] if end - start <= 2048 else None
