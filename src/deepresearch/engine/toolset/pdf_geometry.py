"""Corroborate narrow word spaces against original PDF glyph coordinates."""
from collections import defaultdict
from math import isfinite
import re

GEOMETRY_LIMIT = 32768  # Bound the expensive per-character native dictionary.


def hyphen_boundaries(text):
    """Word-internal ASCII hyphens only; numbers and identifiers stay literal."""
    return {i for word in re.finditer(r"(?<!\w)[^\W\d_]+(?:-[^\W\d_]+)+(?!\w)", text)
            for i in range(word.start() + 1, word.end()) if text[i] == "-" or text[i - 1] == "-"}


def confirm_spaces(native, flags, raw):
    """Return a full-page aligned map, or None; never reorder or emit glyphs.

    Flags 2/4 identify spaces independently observed by the secondary reader.
    A positive physical gap can confirm a secondary-only space (4 -> 8).
    On one horizontal baseline/font/size, at least three observed word gaps
    also establish a physical spacing sample: another equal gap may be restored
    even if both text readers missed it. At a font transition, only a space
    already observed by the secondary reader can be confirmed, and it must
    match that same line's calibrated gaps in the preceding font. Font size
    and baseline must still match; no font-family names are inferred.
    """
    positions = iter((c, i) for i, c in enumerate(native) if not c.isspace())
    result = bytearray(flags)
    hyphens = hyphen_boundaries(native)
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            glyphs = []
            for span in line["spans"]:
                for glyph in span["chars"]:
                    character = glyph["c"]
                    if character.isspace():
                        continue
                    item = next(positions, None)
                    if item is None or character != item[0]:
                        return None
                    glyphs.append((item[1], glyph, span["font"], span["size"]))
            if tuple(line["dir"]) != (1.0, 0.0):
                continue
            pairs, anchors = [], defaultdict(list)
            for left, right in zip(glyphs, glyphs[1:]):
                _, a, font, size = left
                index, b, other_font, other_size = right
                if (size != other_size or not isfinite(size) or size <= 0
                        or a["origin"][1] != b["origin"][1]):
                    continue
                same_font = font == other_font
                gap = b["origin"][0] - a["bbox"][2]
                if (same_font and index in hyphens and flags[index] == 1 and isfinite(gap)
                        and -size * .5 <= gap <= size * .01):
                    result[index] = 16  # Two readers and tight same-style glyphs.
                if not isfinite(gap) or gap <= 0 or not a["c"].isalpha() or not b["c"].isalpha():
                    continue
                key = font, size
                pairs.append((index, gap, key, same_font))
                if same_font and flags[index] in (2, 4):
                    anchors[key].append(gap)
            for index, gap, key, same_font in pairs:
                reference = anchors[key]
                calibrated = (len(reference) >= 3
                    and any(abs(gap - observed) <= key[1] * .002 for observed in reference))
                if ((same_font and (flags[index] == 4 or (flags[index] == 1 and calibrated)))
                        or (not same_font and flags[index] == 4 and calibrated)):
                    result[index] = 8
    if next(positions, None) is not None:
        return None
    return result
