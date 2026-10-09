"""Bind undecoded PDF glyph names to opaque native glyphs, without decoding.

The pinned pypdf adapter reads actual text operands and font encodings. Literal
text resembling a glyph name grants no authority. Both complete page streams
and the native character dictionary must agree outside the bound opaque spans.
"""
from itertools import zip_longest
import re

LIMIT = 32768
FAILURES = ("text_limit", "unavailable", "content_disagreement")


def _font_name(value):
    return re.sub(r"^[A-Z]{6}\+", "", str(value).lstrip("/"))


class _Operands:
    def __init__(self, page):
        self.resources = page.get("/Resources", {}).get_object() if "/Resources" in page else {}
        self.font = None
        self.stack, self.forms, self.tokens = [], [], []
        self.cache = {}
        self.size = self.operations = 0
        self.failure = None

    def _emit(self, text, name="", opaque=False):
        self.size += len(text)
        if self.size > LIMIT:
            self.failure = "text_limit"
            return
        if opaque:
            self.tokens.append((text, name, True))
        else:
            self.tokens.extend((c, name, False) for c in text if not c.isspace())

    def _font(self):
        from pypdf._cmap import get_encoding  # Pinned pypdf 6.19.0 adapter.
        from pypdf.generic import NameObject
        resource = self.resources["/Font"][self.font].get_object()
        key = id(resource)
        if key not in self.cache:
            if len(self.cache) >= 128:
                raise ValueError("Too many font maps")
            encoding, mapping = get_encoding(resource)
            names = {}
            declared = resource.get("/Encoding")
            declared = declared.get_object() if declared is not None else None
            differences = declared.get("/Differences", []) if isinstance(declared, dict) else []
            differences = differences.get_object() if hasattr(differences, "get_object") else differences
            if len(differences) > 512:
                raise ValueError("Too many encoding differences")
            code = 0
            for item in differences:
                if isinstance(item, int):
                    code = item
                else:
                    if (isinstance(item, NameObject) and 0 <= code <= 255
                            and 1 < len(item) <= 128 and not any(c.isspace() for c in item)
                            and isinstance(encoding, dict) and encoding.get(code) == item):
                        names[code] = str(item)
                    code += 1
            self.cache[key] = encoding, mapping, names, _font_name(resource.get("/BaseFont", ""))
        return self.cache[key]

    def _text(self, operand):
        if isinstance(operand, str):
            self._emit(operand)  # pypdf's literal operands bypass font decoding.
            return
        if not isinstance(operand, bytes):
            return
        encoding, mapping, names, font = self._font()
        if isinstance(encoding, str):
            try:
                decoded = operand.decode(encoding, "surrogatepass")
            except (UnicodeError, LookupError):
                decoded = operand.decode("charmap", "surrogatepass")
            self._emit("".join(mapping.get(c, c) for c in decoded), font)
            return
        for code in operand:
            decoded = encoding[code] if code in encoding else bytes((code,)).decode()
            value = "".join(mapping.get(c, c) for c in decoded)
            self._emit(value, font, bool(font and names.get(code) == value))
            if self.failure:
                return

    def before(self, operator, operands, cm, tm):
        if self.failure:
            return
        self.operations += 1
        if self.operations > 131072:
            self.failure = "text_limit"
            return
        try:
            if operator == b"Tf":
                self.font = operands[0]
            elif operator == b"q":
                if len(self.stack) >= 64:
                    raise ValueError("Graphics nesting limit")
                self.stack.append(self.font)
            elif operator == b"Q":
                self.font = self.stack.pop()
            elif operator == b"Do":
                if len(self.forms) >= 32:
                    raise ValueError("Form nesting limit")
                obj = self.resources["/XObject"][operands[0]].get_object()
                self.forms.append((self.resources, self.font, self.stack))
                if obj.get("/Subtype") != "/Image":
                    self.resources = obj["/Resources"] if "/Resources" in obj else {}
                    self.font, self.stack = None, []
            elif operator in (b"Tj", b"'", b'"'):
                self._text(operands[-1])
            elif operator == b"TJ":
                for operand in operands[0]:
                    self._text(operand)
                    if self.failure:
                        break
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            self.failure = "unavailable"

    def after(self, operator, operands, cm, tm):
        if not self.failure and operator == b"Do":
            self.resources, self.font, self.stack = self.forms.pop()


def align_opaque_glyphs(page, original, native, geometry):
    """Return immutable (old-start, old-end, native-position) bindings or failure.

    An unknown name is retained verbatim. This only permits alignment past one
    native control glyph with the same font identity; it cannot supply a glyph,
    normalize a formula, skip ordinary text or accept a partial page match.
    """
    if max(len(original.encode("utf-8")), len(native.encode("utf-8"))) > LIMIT:
        return (), "text_limit"
    from .pdf_extraction import _can_decode, _undecoded
    try:
        trace = _Operands(page)
        observed = (page.extract_text(visitor_operand_before=trace.before,
            visitor_operand_after=trace.after) or "").replace("\r\n", "\n").replace("\r", "\n")
        if trace.failure:
            return (), trace.failure
        if observed != original:
            return (), "content_disagreement"
        raw = geometry()
        glyphs = ((g["c"], _font_name(s["font"])) for block in raw["blocks"] if block.get("type") == 0
                  for line in block["lines"] for s in line["spans"] for g in s["chars"] if not g["c"].isspace())
        old = iter((c, i) for i, c in enumerate(original) if not c.isspace())
        new = iter(zip_longest(((c, i) for i, c in enumerate(native) if not c.isspace()), glyphs))
        spans = []
        for token, font, opaque in trace.tokens:
            positions = []
            for c in token:
                match = next(old, None)
                if match is None or match[0] != c:
                    return (), "content_disagreement"
                positions.append(match[1])
            pair = next(new, None)
            if pair is None or pair[0] is None or pair[1] is None:
                return (), "content_disagreement"
            (character, index), (glyph, glyph_font) = pair
            if character != glyph:
                return (), "content_disagreement"
            if opaque:
                if (not _undecoded(character) or font != glyph_font
                        or original[positions[0]:positions[-1]+1] != token):
                    return (), "content_disagreement"
                spans.append((positions[0], positions[-1]+1, index))
            elif token != character and not _can_decode(token, character):
                return (), "content_disagreement"
        if next(old, None) is not None or next(new, None) is not None or not spans:
            return (), "content_disagreement"
        return tuple(spans), None
    except (AttributeError, IndexError, KeyError, RuntimeError, TypeError, ValueError):
        return (), "unavailable"
