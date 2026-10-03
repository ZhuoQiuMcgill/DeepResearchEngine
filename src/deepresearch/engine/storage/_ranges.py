"""Validated immutable UTF-8 indexes and bounded slice continuation."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import time
from typing import Any

from ._backend import StorageFailure, digest, encode


def strict_json(raw: bytes, max_bytes: int) -> Any:
    if len(raw) > max_bytes:
        raise StorageFailure("LIMIT_EXCEEDED", "JSON exceeds its byte limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise StorageFailure("INVALID_DATA", "JSON cannot have a UTF-8 BOM")
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result
    def bad_constant(_):
        raise ValueError("Nonfinite number")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)
        def visit(value, depth=0):
            if depth > 32:
                raise ValueError("JSON depth")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Nonfinite number")
            if isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError("Key type")
                    key.encode("utf-8")
                    visit(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    visit(item, depth + 1)
            elif isinstance(value, str):
                value.encode("utf-8")
            elif value is not None and type(value) not in (int, float, bool):
                raise ValueError("JSON type")
        visit(result)
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise StorageFailure("INVALID_DATA", "Invalid finite unique-key UTF-8 JSON") from None


def canonical_json(value: Any, limit: int) -> bytes:
    try:
        encoded = encode(value).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise StorageFailure("INVALID_DATA", "Value is not strict JSON") from None
    strict_json(encoded, limit)
    return encoded


def line_spans(text: bytes) -> list[dict]:
    spans = []
    start = 0
    for end, byte in enumerate(text):
        if byte == 10:
            spans.append({"line": len(spans) + 1, "start_byte": start, "end_byte": end})
            start = end + 1
    if start < len(text):
        spans.append({"line": len(spans) + 1, "start_byte": start, "end_byte": len(text)})
    return spans


def boundary(text: bytes, offset: int) -> bool:
    return offset == len(text) or offset == 0 or text[offset] & 0xC0 != 0x80


def validate_index(text: bytes, raw_index: bytes) -> dict:
    if len(text) > 4 << 20 or len(raw_index) > 1 << 20:
        raise StorageFailure("LIMIT_EXCEEDED", "Snapshot text or index exceeds the component limit")
    try:
        decoded = text.decode("utf-8", errors="strict")
    except UnicodeError:
        raise StorageFailure("INVALID_DATA", "Snapshot text must be UTF-8") from None
    if decoded.startswith("\ufeff") or "\r" in decoded:
        raise StorageFailure("INVALID_DATA", "Snapshot text must have no BOM and LF line endings")
    value = strict_json(raw_index, 1 << 20)
    required = {"schema_version", "format", "text_sha256", "lines", "pages"}
    if not isinstance(value, dict) or set(value) != required or type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["format"] != "document_index/1":
        raise StorageFailure("INVALID_DATA", "Snapshot index does not match document_index/1")
    if value["text_sha256"] != digest(text) or value["lines"] != line_spans(text):
        raise StorageFailure("INTEGRITY_ERROR", "Snapshot line spans or text digest do not match retained text")
    pages = value["pages"]
    if pages is not None:
        if not isinstance(pages, list):
            raise StorageFailure("INVALID_DATA", "Physical pages must be a list or null")
        previous_end = None
        for position, page in enumerate(pages, 1):
            if not isinstance(page, dict) or set(page) != {"page", "start_byte", "end_byte"} or page["page"] != position or type(page["page"]) is not int:
                raise StorageFailure("INVALID_DATA", "Physical page spans must have sequential page IDs")
            start, end = page["start_byte"], page["end_byte"]
            if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(text) or not boundary(text, start) or not boundary(text, end):
                raise StorageFailure("INVALID_DATA", "Physical page span is not a valid UTF-8 range")
            if (previous_end is None and start != 0) or (previous_end is not None and text[previous_end:start] != b"\n"):
                raise StorageFailure("INVALID_DATA", "Physical page separators must be one declared LF")
            previous_end = end
        if (pages and previous_end != len(text)) or (not pages and text):
            raise StorageFailure("INVALID_DATA", "Physical pages do not cover retained text")
    return value


class CursorCodec:
    def __init__(self, key: bytes):
        self.key = key

    def seal(self, payload: dict) -> str:
        raw = canonical_json(payload, 16 << 10)
        mac = hmac.new(self.key, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + mac).rstrip(b"=").decode("ascii")

    def open(self, token: str) -> dict:
        try:
            if not isinstance(token, str) or len(token) > 24576:
                raise ValueError()
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            body, mac = raw[:-32], raw[-32:]
            if not hmac.compare_digest(mac, hmac.new(self.key, body, hashlib.sha256).digest()):
                raise ValueError()
            value = strict_json(body, 16 << 10)
            if not isinstance(value, dict) or value.get("expires", 0) < time.time():
                raise ValueError()
            return value
        except (ValueError, UnicodeError, StorageFailure):
            raise StorageFailure("INVALID_CURSOR", "Continuation is invalid, expired or belongs to another session") from None


def slice_document(text: bytes, index: dict, requested: dict, budget: int, position: dict | None) -> tuple[dict, dict | None]:
    if not isinstance(requested, dict) or set(requested) != {"kind", "start", "end_exclusive"}:
        raise StorageFailure("INVALID_DATA", "Document range must have exactly kind/start/end_exclusive")
    kind, start, end = requested["kind"], requested["start"], requested["end_exclusive"]
    if kind not in ("lines", "pages") or type(start) is not int or type(end) is not int:
        raise StorageFailure("INVALID_DATA", "Invalid document range types")
    units = index[kind]
    if units is None:
        raise StorageFailure("UNSUPPORTED_RANGE", "This immutable snapshot has no physical page map")
    if not 1 <= start <= end <= len(units) + 1:
        raise StorageFailure("INVALID_DATA", "Document range is out of bounds")
    if end - start > (200 if kind == "lines" else 10) or type(budget) is not int or not 1 <= budget <= 64 << 10:
        raise StorageFailure("LIMIT_EXCEEDED", "Read unit or UTF-8 byte budget exceeds its limit")
    unit_id = position["unit"] if position else start
    byte_offset = position["offset"] if position else (units[start - 1]["start_byte"] if start < end else None)
    if position and (type(unit_id) is not int or not start <= unit_id < end or type(byte_offset) is not int):
        raise StorageFailure("INVALID_CURSOR", "Continuation position is outside the requested range")
    returned_start = unit_id
    spans, parts = [], []
    remaining = budget
    while unit_id < end:
        unit = units[unit_id - 1]
        segment_end = units[unit_id]["start_byte"] if unit_id + 1 < end else unit["end_byte"]
        # The line index excludes delimiters. A range ending at the document's
        # last line must still make its retained terminal LF readable; there
        # is no following line through which a bridge could return that byte.
        if kind == "lines" and unit_id == len(units):
            segment_end = len(text)
        offset = unit["start_byte"] if byte_offset is None else byte_offset
        if not unit["start_byte"] <= offset <= segment_end or not boundary(text, offset):
            raise StorageFailure("INVALID_CURSOR", "Continuation byte position is invalid")
        proposed_end = min(segment_end, offset + remaining)
        while proposed_end > offset and not boundary(text, proposed_end):
            proposed_end -= 1
        if segment_end > offset and proposed_end == offset:
            if not parts and not spans:
                next_end = offset + 1
                while next_end < len(text) and not boundary(text, next_end):
                    next_end += 1
                raise StorageFailure("LIMIT_EXCEEDED", "The next UTF-8 codepoint does not fit", details={"minimum_next_codepoint_bytes": next_end - offset})
            break
        parts.append(text[offset:proposed_end])
        spans.append({"line": unit_id if kind == "lines" else None, "page": unit_id if kind == "pages" else None, "start_byte": offset, "end_byte": proposed_end})
        remaining -= proposed_end - offset
        if proposed_end < segment_end:
            byte_offset = proposed_end
            break
        unit_id += 1
        byte_offset = units[unit_id - 1]["start_byte"] if unit_id < end else None
        if remaining == 0 and unit_id < end and units[unit_id - 1]["start_byte"] < units[unit_id - 1]["end_byte"]:
            break
    next_position = {"unit": unit_id, "offset": byte_offset} if unit_id < end else None
    returned_end = spans[-1]["line" if kind == "lines" else "page"] + 1 if spans else returned_start
    return {"requested_range": requested, "returned_range": {"kind": kind, "start": returned_start, "end_exclusive": returned_end}, "spans": spans, "text": b"".join(parts).decode("utf-8"), "truncated": next_position is not None, "has_more_in_requested_range": next_position is not None, "has_more_in_document": next_position is not None or end <= len(units)}, next_position
