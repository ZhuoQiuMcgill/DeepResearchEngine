"""Bounded repeated-margin annotations mapped to immutable PDF text bytes.

No page text is removed, reordered or rewritten here. Coordinates and repeated
appearance identify candidates; unique character alignment binds each to the
actual retained text. Consumers must still retain the original quotation span.
"""
from collections import Counter, defaultdict
from math import isfinite
import re

from .common import digest, encode


def layout_schema(method="repeated-page-margins/3"):
    from .discovery_metadata import object_schema
    count = {"type": "integer", "minimum": 0}
    sha = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    span = object_schema({"page": {"type": "integer", "minimum": 1},
        "start_byte": count, "end_byte": count, "text_sha256": sha,
        "kind": {"enum": ["header", "footer", "side"]},
        "repeated_pages": {"type": "integer", "minimum": 3}})
    return object_schema({"method": {"const": method},
        "semantic_verification": {"const": False}, "text_sha256": sha,
        "checked_pages": count, "skipped_pages": count, "omitted_spans": count, "omitted_candidates": count,
        "page_breaks": {"type": "array", "maxItems": 499, "items": count},
        "spans": {"type": "array", "maxItems": 1024, "items": span}})


def _lines(raw):
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            text = "".join(s.get("text", "".join(c["c"] for c in s.get("chars", []))) for s in spans)
            if text.strip():
                yield {"text": text.strip(), "bbox": line["bbox"], "dir": tuple(line["dir"]),
                       "baseline": spans[0]["origin"][1], "size": max(s["size"] for s in spans)}


def _counter_consistent(rows):
    """Only constant numeric fields or one actual page-counter progression."""
    fields = [re.findall(r"\d+", r["text"]) for r in rows]
    if not fields or any(len(f) != len(fields[0]) for f in fields):
        return False
    varying = [i for i in range(len(fields[0])) if len({f[i] for f in fields}) > 1]
    return not varying or (len(varying) == 1 and len({int(f[varying[0]]) - r["page"] for f, r in zip(fields, rows)}) == 1)


class PdfLayout:
    def __init__(self):
        self.checked, self.skipped, self.candidates, self.omitted = 0, 0, [], 0

    def skip(self):
        self.skipped += 1

    def add(self, page, text, raw, width, height):
        if not all(isfinite(x) and x > 0 for x in (width, height)):
            raise ValueError("Invalid PDF dimensions")
        lines = list(_lines(raw))
        fonts = Counter()
        for line in lines:
            x0, y0, x1, y1 = line["bbox"]
            if (line["dir"] == (1., 0.) and .12 * height <= y0 < y1 <= .85 * height
                    and isfinite(line["size"]) and line["size"] > 0):
                fonts[round(line["size"], 1)] += len(line["text"])
        if not fonts:
            raise ValueError("No body font evidence")
        body_size = fonts.most_common(1)[0][0]
        # Reconstruct complete physical rows BEFORE comparing fonts. A small
        # bold inline word is still body text, even if the PDF emits it as a
        # separate block near a page edge. Ambiguous overlapping rows stay literal.
        rows, vertical = [], []
        if any(not isfinite(line["baseline"]) for line in lines):
            raise ValueError("Invalid text baseline")
        for line in sorted(lines, key=lambda r: r["baseline"]):
            if line["dir"] != (1., 0.):
                vertical.append(line)
            elif rows and abs(rows[-1][0]["baseline"] - line["baseline"]) <= .5:
                rows[-1].append(line)
            else:
                rows.append([line])
        visual = list(vertical)
        for row in rows:
            row = sorted(row, key=lambda r: r["bbox"][0])
            if any(a["bbox"][2] > z["bbox"][0] for a, z in zip(row, row[1:])):
                continue
            visual.append({**row[0], "text": " ".join(r["text"] for r in row),
                "size": max(r["size"] for r in row),
                "bbox": (row[0]["bbox"][0], min(r["bbox"][1] for r in row),
                         row[-1]["bbox"][2], max(r["bbox"][3] for r in row))})
        grouped = []
        for line in visual:
            x0, y0, x1, y1 = line["bbox"]
            size = line["size"]
            if not all(isfinite(v) for v in (*line["bbox"], size)):
                continue
            smaller, kind, confirmed = 0 < size <= body_size * .95, None, False
            if line["dir"] == (1., 0.):
                if y1 <= .10 * height:
                    kind = "header"
                    confirmed = smaller or y1 <= .04 * height
                elif y0 >= .89 * height:
                    kind = "footer"
                    confirmed = smaller or y0 >= .95 * height
            elif (line["dir"] in {(0., -1.), (0., 1.)} and (x1 <= .05 * width or x0 >= .95 * width)
                    and y1 - y0 >= .25 * height):
                kind = "side"  # Short chart labels cannot qualify as watermarks.
                confirmed = True
            if kind and size > 0:
                grouped.append({**line, "kind": kind, "page": page, "confirmed": confirmed})
        compact, positions = [], []
        for i, c in enumerate(text):
            if not c.isspace():
                compact.append(c)
                positions.append(i)
        compact = "".join(compact)
        pending = []
        self.omitted += max(0, len(grouped) - 16)
        # A weak candidate cannot crowd an independently confirmed margin out
        # of the bounded page budget. It cannot establish a family itself.
        for line in sorted(grouped, key=lambda r: not r["confirmed"])[:16]:
            key = "".join(line["text"].split())
            if not key or len(key) > 512 or compact.count(key) != 1:
                continue
            left = compact.index(key)
            start, end = positions[left], positions[left + len(key) - 1] + 1
            # Require full textual lines, never delete a matching phrase inside
            # substantive prose or a table row elsewhere on the page.
            if text[text.rfind("\n", 0, start) + 1:start].strip() or text[end:text.find("\n", end) if "\n" in text[end:] else len(text)].strip():
                continue
            axis = line["bbox"][0] / width if line["kind"] == "side" else line["bbox"][1] / height
            fingerprint = (line["kind"], re.sub(r"\d+", "#", key), round(axis, 2), round(line["size"], 1))
            pending.append({"page": page, "start_byte": len(text[:start].encode("utf-8")),
                "end_byte": len(text[:end].encode("utf-8")), "text_sha256": digest(text[start:end].encode("utf-8")),
                "kind": line["kind"], "fingerprint": fingerprint, "text": line["text"],
                "confirmed": line["confirmed"]})
        self.candidates.extend(pending)
        self.checked += 1

    def finish(self, pages, byte_limit):
        offsets, offset = [], 0
        for page in pages:
            offsets.append(offset)
            offset += len(page.encode("utf-8")) + 1
        groups = defaultdict(list)
        for row in self.candidates:
            groups[row["fingerprint"]].append(row)
        accepted = []
        for rows in groups.values():
            repetitions = len({r["page"] for r in rows})
            # Tables, references and captions can dominate a page's font vote.
            # Three independently confirmed pages establish the same complete
            # margin row, position, size and counter sequence on those pages.
            confirmed = len({r["page"] for r in rows if r["confirmed"]})
            if confirmed < 3 or not _counter_consistent(rows):
                continue
            for row in rows:
                base = offsets[row["page"] - 1]
                accepted.append({k: row[k] for k in ("page", "text_sha256", "kind")} |
                    {"start_byte": base + row["start_byte"], "end_byte": base + row["end_byte"],
                     "repeated_pages": repetitions})
        result = {"method": "repeated-page-margins/3", "semantic_verification": False,
            "text_sha256": digest("\n".join(pages).encode("utf-8")), "checked_pages": self.checked,
            "skipped_pages": self.skipped, "omitted_spans": 0,
            "omitted_candidates": self.omitted,
            "page_breaks": offsets[1:], "spans": sorted(accepted, key=lambda r: r["start_byte"])}
        while len(result["spans"]) > 1024 or len(encode(result)) > byte_limit:
            if not result["spans"]:
                break
            result["spans"].pop()
            result["omitted_spans"] += 1
        return result
