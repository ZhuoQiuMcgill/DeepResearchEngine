"""Independent PDF spacing evidence; comparison never supplies output text."""
from __future__ import annotations

from itertools import zip_longest
from threading import RLock

_LIGATURES = dict(zip("ﬀﬁﬂﬃﬄﬅﬆ", ("ff", "fi", "fl", "ffi", "ffl", "st", "st")))
_LOCK = RLock()  # PDFium itself is not thread-safe, even across documents.
FAILURES = ("reader_unavailable", "page_count_disagreement", "page_error", "text_limit", "content_disagreement")


def _opaque(character):
    return not character.isspace() and (ord(character) < 32 or 127 <= ord(character) <= 159)


def _characters(text):
    for index, character in enumerate(text):
        if not character.isspace():
            # These presentation ligatures expand only in this comparison.
            for part in _LIGATURES.get(character, character):
                yield part, index


def spacing_agreement(native, secondary):
    """Map offsets: 1=joint no-gap, 2=joint space, 4=secondary-only space.

    Require the complete ordered character streams to align. A secondary C0/C1
    placeholder may occupy one character position, but neither adjacent boundary
    can authorize a whitespace edit. It never decodes or replaces output glyphs.
    Other disagreements discard the entire map, including any earlier matches.
    """
    flags = bytearray(len(native))
    previous_a = previous_b = -1
    previous_match = False
    opaque = 0
    for left, right in zip_longest(_characters(native), _characters(secondary)):
        if left is None or right is None:
            return None, 0
        a, i = left
        b, j = right
        exact = a == b and not _opaque(a)
        if _opaque(b):
            opaque += 1
        if a != b:
            if not _opaque(b):
                return None, 0
        if i != previous_a and previous_a >= 0 and previous_match and exact:
            gap = native[previous_a + 1:i]
            if gap == secondary[previous_b + 1:j] and gap in ("", " "):
                flags[i] = 1 if gap == "" else 2
            elif not gap and secondary[previous_b + 1:j] == " ":
                flags[i] = 4  # Requires physical confirmation before insertion.
        previous_a, previous_b, previous_match = i, j, exact
    return flags, opaque


class PdfSpacingReader:
    """Lazily own one secondary document; every page/text handle is closed."""

    def __init__(self, body, pages):
        self.body, self.pages = body, pages
        self.document = None
        self.unavailable = None
        self.diagnostic = {"attempted_pages": 0, "aligned_pages": 0, "opaque_glyphs": 0,
                           "failures": dict.fromkeys(FAILURES, 0),
                           "geometry_pages": 0, "geometry_spaces": 0,
                           "geometry_joins": 0,
                           "geometry_failures": dict.fromkeys(("text_limit", "unavailable", "content_disagreement"), 0)}

    def _read(self, number):
        # Called under the process-wide lock, including library initialization.
        if self.document is None and self.unavailable is None:
            try:
                import pypdfium2
                self.document = pypdfium2.PdfDocument(self.body)
                if len(self.document) != self.pages:
                    self.unavailable = "page_count_disagreement"
            except (ImportError, OSError, RuntimeError, ValueError):
                self.unavailable = "reader_unavailable"
        if self.unavailable:
            return None, self.unavailable
        page = textpage = None
        try:
            page = self.document[number]
            textpage = page.get_textpage()
            return textpage.get_text_bounded(errors="strict"), None
        except (RuntimeError, ValueError):
            return None, "page_error"
        finally:
            try:
                if textpage is not None:
                    textpage.close()
            finally:
                if page is not None:
                    page.close()

    def compare(self, number, native, text_limit, geometry=None):
        self.diagnostic["attempted_pages"] += 1
        with _LOCK:
            text, reason = self._read(number)
        flags, opaque = None, 0
        if reason is None:
            if len(text.encode("utf-8")) > text_limit:
                reason = "text_limit"
            else:
                flags, opaque = spacing_agreement(native, text)
                if flags is None:
                    reason = "content_disagreement"
        if reason:
            self.diagnostic["failures"][reason] += 1
        else:
            self.diagnostic["aligned_pages"] += 1
            self.diagnostic["opaque_glyphs"] += opaque
            from .pdf_geometry import GEOMETRY_LIMIT, confirm_spaces, hyphen_boundaries
            if 4 in flags or any(flags[i] == 1 for i in hyphen_boundaries(native)):
                failure = None
                if len(native.encode("utf-8")) > GEOMETRY_LIMIT:
                    failure = "text_limit"
                elif geometry is None:
                    failure = "unavailable"
                else:
                    try:
                        physical = confirm_spaces(native, flags, geometry())
                        if physical is None:
                            failure = "content_disagreement"
                        else:
                            flags = physical
                            self.diagnostic["geometry_pages"] += 1
                            self.diagnostic["geometry_spaces"] += flags.count(8)
                            self.diagnostic["geometry_joins"] += flags.count(16)
                    except (RuntimeError, ValueError, TypeError, KeyError):
                        failure = "unavailable"
                if failure:
                    self.diagnostic["geometry_failures"][failure] += 1
        return flags

    def close(self):
        with _LOCK:
            if self.document is not None:
                self.document.close()
                self.document = None
