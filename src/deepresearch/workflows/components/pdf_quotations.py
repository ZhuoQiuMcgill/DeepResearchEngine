"""Translate trusted PDF margin annotations to a bounded, already-read window."""
from deepresearch.engine.contracts import EngineError, digest_bytes


def layout_window(provenance, window):
    media = provenance.get("media_type", "")
    layout = (provenance.get("pdf_extraction") or {}).get("layout")
    if (not isinstance(media, str) or media.split(";", 1)[0].strip().lower() != "application/pdf"
            or not layout or layout.get("method") not in {"repeated-page-margins/2", "repeated-page-margins/3"}):
        return (), ()
    def invalid():
        raise EngineError("INTEGRITY_ERROR", "PDF layout annotations do not match their immutable source text")
    if layout.get("text_sha256") != provenance.get("text_sha256"):
        invalid()
    start = window.get("start_byte")
    if type(start) is not int or start < 0:
        return (), ()
    raw = window["text"].encode("utf-8")
    end = start + len(raw)
    spans, breaks, previous = [], [], -1
    for part in layout["spans"]:
        a, b = part["start_byte"], part["end_byte"]
        if type(a) is not int or type(b) is not int or not 0 <= a < b or a < previous:
            invalid()
        previous = b
        if not start <= a < b <= end:
            continue  # A partly read margin grants no deletion permission.
        if digest_bytes(raw[a - start:b - start]) != part["text_sha256"]:
            invalid()
        try:
            spans.append((len(raw[:a - start].decode("utf-8")), len(raw[:b - start].decode("utf-8"))))
        except UnicodeError:
            invalid()
    previous = -1
    for point in layout["page_breaks"]:
        if type(point) is not int or point <= previous:
            invalid()
        previous = point
        if start < point < end:
            try:
                breaks.append(len(raw[:point - start].decode("utf-8")))
            except UnicodeError:
                invalid()
    return tuple(spans), tuple(breaks)


def margin_projection(text, spans):
    """Comparison only: retain each surviving character's original position."""
    positions, cursor = [], 0
    for start, end in spans:
        positions.extend(range(cursor, start))
        cursor = end
    positions.extend(range(cursor, len(text)))
    return "".join(text[i] for i in positions), positions
