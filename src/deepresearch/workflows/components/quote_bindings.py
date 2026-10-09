"""Bind a quotation across adjacent, actually delivered immutable reads."""
from __future__ import annotations

from deepresearch.engine.contracts import EngineError, digest_bytes


def _integrity():
    raise EngineError("INTEGRITY_ERROR", "Cross-read quotation has inconsistent recorded byte authority")


def _recorded(segment):
    """Incomplete legacy fixtures cannot authorize cross-read matching."""
    required = {"segment_id", "text", "start_byte", "end_byte", "text_sha256", "read_action_id", "range"}
    if not required <= segment.keys():
        return False
    raw = segment["text"].encode("utf-8")
    if (type(segment["start_byte"]) is not int or type(segment["end_byte"]) is not int
            or segment["start_byte"] < 0 or segment["end_byte"] != segment["start_byte"] + len(raw)
            or digest_bytes(raw) != segment["text_sha256"] or not segment["read_action_id"]):
        _integrity()
    return bool(raw)


def _part(segment, start, end):
    raw = segment["text"].encode("utf-8")[start - segment["start_byte"]:end - segment["start_byte"]]
    return {"segment_id": segment["segment_id"], "start_byte": start, "end_byte": end,
            "text_sha256": digest_bytes(raw), "read_action_id": segment["read_action_id"]}


class AdjacentQuoteSource:
    """Bounded windows at byte-contiguous boundaries within a single Agent input.

    A returned original quote is at most 2048 characters. Keeping 2048 characters
    on each side of each boundary covers it without parsing an entire document.
    The caller supplies the same source-format matcher as for individual reads.
    Gaps and overlaps split runs; outside access-manifest bytes are never added.
    """

    def __init__(self, segments, prepare):
        self._segments, self._prepare, self._windows = segments, prepare, None

    def _build(self):
        eligible = [s for s in self._segments if _recorded(s)]
        ordered = sorted(eligible, key=lambda s: s["start_byte"])
        if len({s["segment_id"] for s in ordered}) != len(ordered):
            _integrity()
        runs = []
        for segment in ordered:
            if runs and runs[-1][-1]["end_byte"] == segment["start_byte"]:
                runs[-1].append(segment)
            else:
                runs.append([segment])
        windows = []
        for run in runs:
            if len(run) < 2:
                continue
            # The public stage chunks below this byte allowance already.
            if sum(len(s["text"].encode("utf-8")) for s in run) > 262144:
                raise EngineError("LIMIT_EXCEEDED", "Cross-read quote input exceeds its chunk allowance")
            text = "".join(s["text"] for s in run)
            cursor, seen = 0, set()
            for segment in run[:-1]:
                cursor += len(segment["text"])
                left, right = max(0, cursor - 2048), min(len(text), cursor + 2048)
                if (left, right) in seen:
                    continue
                seen.add((left, right))
                start = run[0]["start_byte"] + len(text[:left].encode("utf-8"))
                window = {"text": text[left:right], "start_byte": start}
                windows.append((window, run, self._prepare(window)))
        self._windows = windows

    def locate(self, quote):
        if self._windows is None:
            self._build()
        matches = {}
        for window, run, prepared in self._windows:
            for index, last in prepared.locate_spans(quote):
                exact = window["text"][index:last]
                start = window["start_byte"] + len(window["text"][:index].encode("utf-8"))
                end = start + len(exact.encode("utf-8"))
                parts = [_part(s, max(start, s["start_byte"]), min(end, s["end_byte"]))
                         for s in run if s["start_byte"] < end and s["end_byte"] > start]
                if len(parts) > 1:
                    matches[(start, end)] = (exact, {"quote_sha256": digest_bytes(exact.encode("utf-8")), "parts": parts})
        return next(iter(matches.values())) if len(matches) == 1 else None


def bound_quote_units(finding, binding, segments):
    """Verify persisted host binding and return one unit per original read.

    `segments` must be restricted to that distiller invocation's segment_ids.
    No synthetic action, new source bytes or normalized comparison text enters
    ContextSelection; every part keeps its original read action and range.
    """
    if (set(binding) != {"finding_index", "quote_sha256", "parts"}
            or type(binding["parts"]) is not list or len(binding["parts"]) < 2
            or digest_bytes(finding["quote"].encode("utf-8")) != binding["quote_sha256"]):
        _integrity()
    units, previous, seen = [], None, set()
    for part in binding["parts"]:
        if set(part) != {"segment_id", "start_byte", "end_byte", "text_sha256", "read_action_id"}:
            _integrity()
        segment = segments.get(part["segment_id"])
        if segment is None or not _recorded(segment) or part["segment_id"] in seen:
            _integrity()
        start, end = part["start_byte"], part["end_byte"]
        if (type(start) is not int or type(end) is not int
                or not segment["start_byte"] <= start < end <= segment["end_byte"]
                or (previous is not None and previous != start)
                or part != _part(segment, start, end)):
            _integrity()
        try:
            text = segment["text"].encode("utf-8")[start - segment["start_byte"]:end - segment["start_byte"]].decode("utf-8")
        except UnicodeError:
            _integrity()
        units.append({**segment, **part, "text": text})
        previous = end
        seen.add(part["segment_id"])
    if (units[0]["segment_id"] != finding["segment_id"]
            or "".join(u["text"] for u in units) != finding["quote"]):
        _integrity()
    return units


def indexed_quote_bindings(record):
    """Keep one host binding per valid retained-finding index."""
    bindings = {}
    for binding in record.get("quote_bindings", []):
        index = binding.get("finding_index")
        if (type(index) is not int or not 0 <= index < len(record["distillation"]["findings"])
                or index in bindings):
            _integrity()
        bindings[index] = binding
    return bindings
