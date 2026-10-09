"""Page-local native PDF text with an independent preservation check."""
from __future__ import annotations

from itertools import zip_longest
from io import StringIO
import re
from unicodedata import category

from .common import ToolFault

VERSION = "pdf_text/9+pymupdf/1.28.2+pypdf/6.19.0+pypdfium2/5.13.0"
_REASONS = ("reader_unavailable", "page_count_disagreement", "page_error", "content_disagreement", "spacing_loss")
_RECOVERY_REASONS = ("content_disagreement", "spacing_loss")
_NUMBERS = re.compile(r"(?<![\w.])(?:0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+|"
                      r"[vV]\d+(?:\.\d+)+|[+−-]?(?:\d+(?:[.:/_−–-]\d+)*|\.\d+)(?:[eE][+−-]?\d+)?)")


def _numeric_boundaries(text):
    """A streaming guard for decimal/exponent/date/time/version token interiors."""
    spans = iter(_NUMBERS.finditer(text))
    current = next(spans, None)
    def inside(left, right):
        nonlocal current
        if left >= 0 and text[left].isdecimal() and text[right].isdecimal():
            return True
        while current is not None and current.end() <= right:
            current = next(spans, None)
        return current is not None and current.start() <= left < right < current.end()
    return inside


def _undecoded(character):
    return not character.isspace() and (ord(character) < 32 or 127 <= ord(character) <= 159)


def _can_decode(before, after):
    return (_undecoded(before) and after.isprintable() and not after.isspace()
            and after != "\ufffd" and category(after) not in {"Co", "Cs", "Cn"})


def preservation(original, candidate):
    """Preserve characters/order and existing word boundaries, not just length.

    A C0/C1 control in the old extraction is an undecoded glyph, not usable
    textual evidence. Its single native glyph may replace it; this is counted.
    No case folding, punctuation/number repair or Unicode normalization occurs.
    """
    # Stream offsets: two lists of tuples for a 4-MiB page would themselves
    # consume hundreds of MiB inside the bounded fetch worker.
    left = ((c, i) for i, c in enumerate(original) if not c.isspace())
    right = ((c, i) for i, c in enumerate(candidate) if not c.isspace())
    replacements = 0
    previous_a = previous_b = -1
    numeric = _numeric_boundaries(original)
    for old, new in zip_longest(left, right):
        if old is None or new is None:
            return "content_disagreement", 0
        before, a = old
        after, b = new
        if before != after:
            if not _can_decode(before, after):
                return "content_disagreement", 0
            replacements += 1
        old_gap = original[previous_a + 1:a]
        new_gap = candidate[previous_b + 1:b]
        if old_gap and not new_gap:
            return "spacing_loss", 0
        if old_gap.count("\n") > new_gap.count("\n"):
            return "spacing_loss", 0
        old_padding = old_gap.rsplit("\n", 1)[-1].expandtabs(8)
        new_padding = new_gap.rsplit("\n", 1)[-1].expandtabs(8)
        if len(old_padding) > 1 and len(new_padding) < len(old_padding):
            return "spacing_loss", 0
        # Native positioning must not split an existing numeric token.
        if not old_gap and new_gap and numeric(previous_a, a):
            return "content_disagreement", 0
        previous_a, previous_b = a, b
    return None, replacements


def recover_page_text(original, native, text_limit, corroborate=None, *, opaque_spans=()):
    """Recover gaps/glyphs with complete character alignment and bounded growth.

    The complete non-whitespace streams must align before any result is used.
    A native ASCII space may separate adjacent alphanumerics, except two digits.
    Other inserted spaces, and removal of a single ASCII space between letters,
    require an independently corroborated native boundary. Numeric interiors,
    line breaks, indentation and trailing whitespace remain untouched;
    the only character replacement is the same counted control-glyph decoding
    admitted for whole native pages. Font/operand-bound opaque names may align
    with one native control glyph, but their text and both adjacent gaps remain
    original. No dictionary or inferred word is used.
    """
    bindings = {}
    end = 0
    for a, z, b in opaque_spans:
        if not (end <= a < z <= len(original) and 0 <= b < len(native)
                and _undecoded(native[b]) and not any(c.isspace() for c in original[a:z])):
            return original, 0, 0, 0
        bindings[a] = z, b
        end = z
    def old_tokens():
        skip = 0
        for i, c in enumerate(original):
            if i < skip or c.isspace():
                continue
            if i in bindings:
                skip, b = bindings[i]
                yield original[i:skip], i, skip, b
            else:
                yield c, i, i + 1, None
    def pairs():
        return zip_longest(old_tokens(),
                           ((c, i) for i, c in enumerate(native) if not c.isspace()))
    # A late content/order disagreement must not invoke the secondary reader or
    # retain an earlier tentative repair. No per-character tuple lists are kept.
    for old, new in pairs():
        if old is None or new is None:
            return original, 0, 0, 0
        if old[3] is not None:
            if old[3] != new[1]:
                return original, 0, 0, 0
        elif old[0] != new[0] and not _can_decode(old[0], new[0]):
            return original, 0, 0, 0
    output = StringIO()
    previous_a = previous_b = -1
    previous_character = ""
    previous_opaque = False
    spaces = removed = replacements = delta_bytes = 0
    flags, checked = None, False
    from .pdf_geometry import hyphen_boundaries
    hyphens = hyphen_boundaries(native)
    numeric = _numeric_boundaries(original)
    for old, new in pairs():
        before, a, end, opaque_at = old
        after, b = new
        opaque = opaque_at is not None
        safe = not opaque and not previous_opaque
        if before != after and not opaque:
            replacements += 1
            delta_bytes += len(after.encode("utf-8")) - len(before.encode("utf-8"))
        gap = original[previous_a + 1:a]
        native_gap = native[previous_b + 1:b]
        insert = safe and previous_a >= 0 and not gap and native_gap == " " and not numeric(previous_a, a)
        word_gap = insert and previous_character.isalnum() and before.isalnum()
        join = safe and gap == " " and not native_gap and previous_character.isalpha() and before.isalpha()
        hyphen_join = safe and gap == " " and not native_gap and b in hyphens
        if corroborate is not None and (join or hyphen_join or (insert and not word_gap)) and not checked:
            flags, checked = corroborate(), True
        agreement = flags[b] if flags is not None else 0
        physical_gap = safe and previous_a >= 0 and not gap and agreement == 8 and not numeric(previous_a, a)
        if (join and agreement == 1) or (hyphen_join and agreement == 16):
            removed += 1
        else:
            output.write(gap)
        if word_gap or (insert and agreement == 2) or physical_gap:
            output.write(" ")
            spaces += 1
        output.write(after if before != after and not opaque else before)
        previous_a, previous_b, previous_character, previous_opaque = end - 1, b, before, opaque
    output.write(original[previous_a + 1:])
    if len(original.encode("utf-8")) + spaces - removed + delta_bytes > text_limit:
        raise ToolFault("TEXT_LIMIT", "PDF recovered page exceeds limit", status="limit_exhausted")
    return (output.getvalue(), spaces, removed, replacements) if spaces or removed or replacements else (original, 0, 0, 0)


def diagnostic_schema():
    from .discovery_metadata import object_schema
    from .pdf_spacing import FAILURES
    count = {"type": "integer", "minimum": 0}
    legacy = object_schema({"method": {"const": "page-text-preservation/1"},
        "semantic_verification": {"const": False}, "pages": count,
        "native_pages": count, "fallback_pages": count, "changed_pages": count,
        "decoded_control_glyphs": count, "unresolved_control_glyphs": count,
        "native_warning_count": count,
        "fallback_reasons": object_schema({reason: count for reason in _REASONS})})
    partial = object_schema({**legacy["properties"], "method": {"const": "page-text-preservation/2"},
        "recovered_pages": count, "inserted_spaces": count,
        "recovery_reasons": object_schema({reason: count for reason in _RECOVERY_REASONS})})
    corroborated = object_schema({**partial["properties"], "method": {"const": "page-text-preservation/3"},
        "removed_spaces": count, "spacing_corroboration": object_schema({"attempted_pages": count,
            "aligned_pages": count, "opaque_glyphs": count,
            "failures": object_schema({reason: count for reason in FAILURES})})})
    current = object_schema({**corroborated["properties"], "method": {"const": "page-text-preservation/4"},
        "spacing_corroboration": object_schema({**corroborated["properties"]["spacing_corroboration"]["properties"],
            "geometry_pages": count, "geometry_spaces": count,
            "geometry_failures": object_schema({reason: count for reason in ("text_limit", "unavailable", "content_disagreement")})})})
    from .pdf_layout import layout_schema
    structured = object_schema({**current["properties"], "method": {"const": "page-text-preservation/5"},
        "layout": layout_schema("repeated-page-margins/1"),
        "spacing_corroboration": object_schema({**current["properties"]["spacing_corroboration"]["properties"],
            "geometry_joins": count})})
    visual_rows = object_schema({**structured["properties"], "method": {"const": "page-text-preservation/6"},
        "layout": layout_schema("repeated-page-margins/2")})
    repeated_families = object_schema({**visual_rows["properties"], "method": {"const": "page-text-preservation/7"},
        "layout": layout_schema()})
    from .pdf_glyphs import FAILURES as GLYPH_FAILURES
    glyph_boundaries = object_schema({**repeated_families["properties"], "method": {"const": "page-text-preservation/8"},
        "opaque_glyph_alignment": object_schema({"attempted_pages": count, "aligned_pages": count,
            "retained_glyph_names": count, "failures": object_schema({reason: count for reason in GLYPH_FAILURES})})})
    return {"oneOf": [legacy, partial, corroborated, current, structured, visual_rows, repeated_families, glyph_boundaries]}


def extract_pages(reader, body, limits):
    """Keep physical pages, including blanks; never mix or reorder page text.

    Only web.fetch revision 2 opts in. Whole native pages or local word/glyph
    recovery require character preservation. Other pages retain legacy text.
    """
    import pymupdf
    from .pdf_spacing import PdfSpacingReader
    from .pdf_layout import PdfLayout
    from .pdf_geometry import GEOMETRY_LIMIT
    from .pdf_glyphs import align_opaque_glyphs, FAILURES as GLYPH_FAILURES

    secondary = PdfSpacingReader(body, len(reader.pages))
    layout = PdfLayout()
    diagnostic = {"method": "page-text-preservation/8", "semantic_verification": False,
        "pages": len(reader.pages), "native_pages": 0, "fallback_pages": 0, "changed_pages": 0,
        "decoded_control_glyphs": 0, "unresolved_control_glyphs": 0, "native_warning_count": 0,
        "fallback_reasons": dict.fromkeys(_REASONS, 0),
        "recovered_pages": 0, "inserted_spaces": 0, "removed_spaces": 0,
        "spacing_corroboration": secondary.diagnostic,
        "opaque_glyph_alignment": {"attempted_pages": 0, "aligned_pages": 0, "retained_glyph_names": 0,
            "failures": dict.fromkeys(GLYPH_FAILURES, 0)},
        "recovery_reasons": dict.fromkeys(_RECOVERY_REASONS, 0)}
    tools = pymupdf.TOOLS
    previous_errors, previous_warnings = tools.mupdf_display_errors(), tools.mupdf_display_warnings()
    tools.mupdf_display_errors(False)
    tools.mupdf_display_warnings(False)
    tools.mupdf_warnings()
    document, unavailable = None, None
    values, used = [], 0
    try:
        try:
            document = pymupdf.open(stream=body, filetype="pdf")
            if document.page_count != len(reader.pages):
                unavailable = "page_count_disagreement"
        except (RuntimeError, ValueError):
            unavailable = "reader_unavailable"
        for number, page in enumerate(reader.pages):
            raw_geometry = None
            def geometry():
                nonlocal raw_geometry
                if raw_geometry is None:
                    raw_geometry = document[number].get_text("rawdict", sort=False,
                        flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
                return raw_geometry
            original = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
            if len(original.encode("utf-8")) > limits["text_bytes"]:
                raise ToolFault("TEXT_LIMIT", "PDF extracted page exceeds limit", status="limit_exhausted")
            candidate, reason, replacements = original, unavailable, 0
            if not reason:
                try:
                    candidate = document[number].get_text("text", sort=False)
                    candidate = candidate.replace("\r\n", "\n").replace("\r", "\n")
                    reason, replacements = preservation(original, candidate)
                except (RuntimeError, ValueError):
                    reason = "page_error"
            if reason:
                def corroborate():
                    return secondary.compare(number, candidate, limits["text_bytes"], geometry)
                recovered, inserted, removed, replacements = (recover_page_text(original, candidate, limits["text_bytes"],
                    corroborate)
                    if reason in _RECOVERY_REASONS else (original, 0, 0, 0))
                if (reason in _RECOVERY_REASONS and recovered == original and "/" in original
                        and any(_undecoded(c) for c in candidate)):
                    glyphs = diagnostic["opaque_glyph_alignment"]
                    glyphs["attempted_pages"] += 1
                    spans, failure = align_opaque_glyphs(page, original, candidate, geometry)
                    if failure:
                        glyphs["failures"][failure] += 1
                    else:
                        glyphs["aligned_pages"] += 1
                        glyphs["retained_glyph_names"] += len(spans)
                        recovered, inserted, removed, replacements = recover_page_text(
                            original, candidate, limits["text_bytes"], corroborate, opaque_spans=spans)
                if recovered != original:
                    candidate = recovered
                    diagnostic["recovered_pages"] += 1
                    diagnostic["recovery_reasons"][reason] += 1
                    diagnostic["inserted_spaces"] += inserted
                    diagnostic["removed_spaces"] += removed
                    diagnostic["decoded_control_glyphs"] += replacements
                else:
                    candidate = original
                    diagnostic["fallback_pages"] += 1
                    diagnostic["fallback_reasons"][reason] += 1
            else:
                diagnostic["native_pages"] += 1
                diagnostic["decoded_control_glyphs"] += replacements
            diagnostic["changed_pages"] += candidate != original
            diagnostic["unresolved_control_glyphs"] += sum(_undecoded(c) for c in candidate)
            used += len(candidate.encode("utf-8")) + (number > 0)
            if used > limits["text_bytes"]:
                raise ToolFault("TEXT_LIMIT", "PDF extracted text exceeds limit", status="limit_exhausted")
            values.append(candidate)
            if (document is None or unavailable or len(reader.pages) < 3
                    or len(candidate.encode("utf-8")) > GEOMETRY_LIMIT):
                layout.skip()
            else:
                try:
                    rect = document[number].rect
                    layout.add(number + 1, candidate, geometry(), rect.width, rect.height)
                except (RuntimeError, ValueError, TypeError, KeyError, AttributeError):
                    layout.skip()
            raw_geometry = None
        diagnostic["layout"] = layout.finish(values, min(32768, limits["provenance_bytes"] // 2))
        return values, diagnostic
    finally:
        try:
            try:
                secondary.close()
            finally:
                if document is not None:
                    document.close()
        finally:
            diagnostic["native_warning_count"] = len(tools.mupdf_warnings().splitlines())
            tools.mupdf_display_errors(previous_errors)
            tools.mupdf_display_warnings(previous_warnings)
