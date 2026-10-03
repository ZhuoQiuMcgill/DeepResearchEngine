"""Read retained source text with recorded ranges and a text-free access manifest."""
from __future__ import annotations

import re
from typing import Any

from deepresearch.engine.contracts import EngineError, canonical_json, digest_bytes
from deepresearch.workflows.contracts import ArtifactReference, SourceRange, SourceRecord


_CHUNK_BYTES = 65536


def _integrity(message: str) -> None:
    raise EngineError("INTEGRITY_ERROR", message)


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    if type(result) is not dict:
        _integrity("Retained-source read returned an invalid outcome")
    for key in ("recording", "persistence", "process", "invocation"):
        if key in result and type(result[key]) is not dict:
            _integrity("Retained-source read returned invalid lifecycle metadata")
    error = result.get("error") or {}
    if type(error) is not dict:
        _integrity("Retained-source read returned an invalid error")
    flags = {
        "observed_effect_state": error.get("observed_effect_state", "not_observed"),
        "commit_state": error.get("commit_state", "not_applicable"),
    }
    if result.get("recording", {}).get("status") != "complete":
        raise EngineError("RECORDING_INCOMPLETE", "Retained-source read recording is incomplete", **flags)
    if (result.get("status") == "unknown"
            or result.get("persistence", {}).get("commit_state") == "unknown"
            or flags["commit_state"] == "unknown" or flags["observed_effect_state"] == "unknown"):
        raise EngineError("OUTCOME_UNKNOWN", "Retained-source read outcome is unresolved",
                          observed_effect_state="unknown", commit_state="unknown")
    cleanup = result.get("process", {}).get("cleanup", {})
    if type(cleanup) is not dict:
        _integrity("Retained-source read returned invalid cleanup metadata")
    if not cleanup.get("complete", True):
        raise EngineError("CLEANUP_INCOMPLETE", "Retained-source read cleanup is incomplete", **flags)
    if result.get("status") != "succeeded":
        code = error.get("code") or ("CANCELLED" if result.get("status") == "cancelled" else "SOURCE_READ_FAILED")
        raise EngineError(code, "Retained-source read did not succeed", error.get("details") or {}, **flags)
    if error:
        _integrity("Retained-source read claimed success while reporting an error")
    value = result.get("result")
    if type(value) is not dict:
        _integrity("Retained-source read omitted its document slice")
    return value


def _slice(value, snapshot, requested, cap, position):
    """Check the public DocumentSlice contract without reaching into Storage."""
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        _integrity("Retained-source read returned an unsupported slice schema")
    if value.get("snapshot_ref") != snapshot or value.get("requested_range") != requested:
        _integrity("Retained-source read changed the snapshot or requested range")
    if type(value.get("text")) is not str:
        _integrity("Retained-source read did not return UTF-8 text")
    try:
        raw = value["text"].encode("utf-8", errors="strict")
    except UnicodeError:
        _integrity("Retained-source read returned invalid UTF-8")
    if type(value.get("byte_length")) is not int or value["byte_length"] != len(raw) or len(raw) > cap:
        _integrity("Retained-source read byte length violates its allowance")
    for flag in ("truncated", "has_more_in_requested_range", "has_more_in_document"):
        if type(value.get(flag)) is not bool:
            _integrity("Retained-source read omitted its coverage flags")
    more = value["has_more_in_requested_range"]
    if value["truncated"] != more:
        _integrity("Retained-source read has inconsistent truncation flags")
    spans = value.get("spans")
    if type(spans) is not list or len(spans) > requested["end_exclusive"] - requested["start"]:
        _integrity("Retained-source read has an invalid span count")
    unit_key = "page" if requested["kind"] == "pages" else "line"
    other_key = "line" if unit_key == "page" else "page"
    consumed, previous_unit, previous_end = 0, None, None
    for span in spans:
        if type(span) is not dict:
            _integrity("Retained-source read has an invalid span")
        unit, start, end = span.get(unit_key), span.get("start_byte"), span.get("end_byte")
        if (type(unit) is not int or not requested["start"] <= unit < requested["end_exclusive"]
                or span.get(other_key) is not None or type(start) is not int
                or type(end) is not int or not 0 <= start <= end):
            _integrity("Retained-source read span lies outside the requested range")
        if previous_unit is not None and (unit != previous_unit + 1 or start != previous_end):
            _integrity("Retained-source read spans contain gaps or repeated units")
        length = end - start
        try:
            raw[consumed:consumed + length].decode("utf-8", errors="strict")
        except UnicodeError:
            _integrity("Retained-source read span splits a UTF-8 codepoint")
        consumed += length
        previous_unit, previous_end = unit, end
    if consumed != len(raw) or (not spans and (raw or more)):
        _integrity("Retained-source read spans do not account for the delivered text")
    returned = value.get("returned_range")
    expected_returned = {
        "kind": requested["kind"],
        "start": spans[0][unit_key] if spans else requested["start"],
        "end_exclusive": spans[-1][unit_key] + 1 if spans else requested["start"],
    }
    if returned != expected_returned:
        _integrity("Retained-source read returned range differs from its spans")
    if spans:
        expected_unit = position["unit"] if position else requested["start"]
        if spans[0][unit_key] != expected_unit or (
                position and spans[0]["start_byte"] != position["offset"]):
            _integrity("Retained-source continuation skipped or replayed a position")
    next_position, cursor = value.get("next_position"), value.get("continuation")
    if more:
        if (type(next_position) is not dict or type(next_position.get("unit")) is not int
                or type(next_position.get("offset")) is not int
                or not requested["start"] <= next_position["unit"] < requested["end_exclusive"]
                or next_position["offset"] != previous_end
                or next_position["unit"] not in (previous_unit, previous_unit + 1)
                or type(cursor) is not str or not cursor or len(cursor) > 8192):
            _integrity("Retained-source read omitted an advancing continuation")
        prior = (position["unit"], position["offset"]) if position else (
            spans[0][unit_key], spans[0]["start_byte"])
        if (next_position["unit"], next_position["offset"]) <= prior:
            _integrity("Retained-source continuation made no position progress")
    elif next_position is not None or cursor is not None:
        _integrity("Retained-source read supplied a cursor after range completion")
    return raw, spans, next_position, cursor


async def read_retained_source(
    context, source: SourceRecord, *, max_read_bytes=4194304, node_prefix=""
) -> dict:
    """Read through the port; failures propagate and never produce a complete manifest.

    PDF batches overlap one physical page. Line batches keep their 200-line
    boundaries and use a two-line bridge to deliver the LF between batches.
    Duplicate bytes are verified and removed. The allowance charges all tool
    payload bytes, including overlap; read_bytes counts unique returned bytes.
    The manifest omits segment text and its own access_ref. An allowance too
    small for the next UTF-8 codepoint yields an explicitly partial result.
    """
    if type(max_read_bytes) is not int or max_read_bytes < 0 or type(node_prefix) is not str:
        raise EngineError("INVALID_DATA", "Source access requires a nonnegative integer byte allowance and a node prefix")
    context.port.assert_active()
    if (not isinstance(source, SourceRecord) or source.status != "succeeded"
            or source.snapshot_ref is None or source.recording_status != "complete"
            or source.persistence_state != "committed"):
        raise EngineError("SOURCE_NOT_READY", "Source access requires a completely recorded retained snapshot")
    if (type(source.text_bytes) is not int or source.text_bytes < 0
            or type(source.text_sha256) is not str
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", source.text_sha256)):
        raise EngineError("INVALID_DATA", "Source access requires declared document bytes and SHA-256")
    kind = "pages" if source.page_count is not None else "lines"
    count = source.page_count if kind == "pages" else source.line_count
    step = 10 if kind == "pages" else 200
    if count == 0 and source.text_bytes != 0:
        _integrity("Nonempty retained text has no declared readable units")
    snapshot = source.snapshot_ref.to_dict()
    materialized = bytearray()
    segments, actions = [], set()
    spent, serial, start = 0, 0, 1
    next_line_start = None
    exhausted = max_read_bytes == 0
    finished = False
    # An empty document still needs a recorded read. The Tool permits [1,1);
    # SourceRange deliberately excludes empty evidence, so it creates no segment.
    while not exhausted and (start <= count or count == 0):
        # Both native page and line spans exclude their terminal separator.
        # A bridge covers the old final line and the new first line, then the
        # main scan resumes at 201, 401, ... without changing its unit bound.
        width = 2 if next_line_start is not None else step
        end = min(start + width, count + 1)
        interval = SourceRange(kind=kind, start=start, end_exclusive=end) if count else None
        requested = interval.tool_range() if interval else {"kind": kind, "start": 1, "end_exclusive": 1}
        cursor, position, cursors = None, None, set()
        while not exhausted:
            cap = min(_CHUNK_BYTES, max_read_bytes - spent)
            if cap <= 0:
                exhausted = True
                break
            node_id = f"{node_prefix}source.read.{source.item_id}.{serial}"
            segment_id = f"{node_prefix}segment.{source.item_id}.{serial}"
            serial += 1
            try:
                async with context.node(node_id, "source_read", {"item_id": source.item_id, "range": requested}) as node:
                    result = await context.port.run_tool("document.read", {
                        "snapshot_ref": snapshot, "range": requested,
                        "max_text_bytes": cap, "continuation": cursor,
                    })
                    value = _outcome(result)
                    raw, spans, next_position, next_cursor = _slice(value, snapshot, requested, cap, position)
                    action = result.get("invocation", {}).get("action_id")
                    if type(action) is not str or not action:
                        _integrity("Retained-source read omitted its recorded action identity")
                    if action in actions:
                        _integrity("Retained-source read reused a recorded action identity")
                    actions.add(action)
                    if next_cursor is not None and next_cursor in cursors:
                        _integrity("Retained-source continuation repeats an earlier cursor")
                    spent += len(raw)
                    if spans:
                        offset, limit = spans[0]["start_byte"], spans[-1]["end_byte"]
                        if limit > source.text_bytes or offset > len(materialized):
                            _integrity("Retained-source read skipped bytes or exceeded the document length")
                        overlap = min(len(raw), len(materialized) - offset)
                        if bytes(materialized[offset:offset + overlap]) != raw[:overlap]:
                            _integrity("Repeated retained-source bytes changed across reads")
                        tail = raw[overlap:]
                        first = len(materialized) if tail else limit
                        materialized.extend(tail)
                        if tail or not raw:
                            segments.append({
                                "segment_id": segment_id, "range": interval.to_dict(),
                                "start_byte": first, "end_byte": first + len(tail),
                                "text": tail.decode("utf-8"), "text_sha256": digest_bytes(tail),
                                "read_action_id": action,
                            })
                    node["detail"].update({"read_action_id": action, "read_bytes": len(raw)})
                    # A final page may contain no text. Only delivered coverage,
                    # not the requested range's size, determines completion.
                    if not value["has_more_in_requested_range"]:
                        if spans and spans[-1]["page" if kind == "pages" else "line"] != end - 1:
                            _integrity("Retained-source read ended before its last requested unit")
                        if not spans and count:
                            _integrity("Retained-source read omitted nonempty requested units")
                        if value["has_more_in_document"] != (end <= count):
                            _integrity("Retained-source read document coverage contradicts the declared unit count")
                    elif not value["has_more_in_document"]:
                        _integrity("Retained-source continuation contradicts document coverage")
            except EngineError as error:
                minimum = error.details.get("minimum_next_codepoint_bytes")
                if (error.code == "LIMIT_EXCEEDED" and cap == max_read_bytes - spent
                        and type(minimum) is int and cap < minimum <= 4
                        and error.commit_state != "unknown" and error.observed_effect_state != "unknown"):
                    exhausted = True
                    break
                raise
            if next_cursor is None:
                break
            cursors.add(next_cursor)
            cursor, position = next_cursor, next_position
            if spent >= max_read_bytes:
                exhausted = True
        if exhausted:
            break
        if end == count + 1:
            finished = True
            break
        if kind == "pages":
            start = end - 1
        elif next_line_start is not None:
            start, next_line_start = next_line_start, None
        else:
            next_line_start, start = end, end - 1

    if finished:
        if len(materialized) != source.text_bytes or digest_bytes(bytes(materialized)) != source.text_sha256:
            _integrity("Complete retained-source bytes differ from the declared document bytes or SHA-256")
    access = {
        "schema_version": 1, "source_id": source.item_id, "snapshot_ref": snapshot,
        "document_bytes": source.text_bytes, "read_bytes": len(materialized),
        "complete": finished, "segments": segments,
    }
    manifest = {**access, "segments": [
        {key: value for key, value in segment.items() if key != "text"} for segment in segments
    ]}
    async with context.node(f"{node_prefix}source.access.{source.item_id}", "publication", {
        "item_id": source.item_id, "read_bytes": len(materialized), "complete": finished,
    }):
        ref = await context.port.publish(
            canonical_json(manifest), "application/json", f"{node_prefix}source-access.{source.item_id}.json",
        )
        try:
            access["access_ref"] = ArtifactReference.model_validate(ref).to_dict()
        except ValueError:
            _integrity("Retained-source access publication returned an invalid artifact reference")
    return access
