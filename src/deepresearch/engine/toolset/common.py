"""Bounded, finite JSON and tool transport validation."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

LIMITS = {
    "stdin_bytes": 1 << 20, "fetch_stdout_bytes": 20 << 20,
    "stdout_bytes": 512 << 10, "stderr_bytes": 64 << 10,
    "raw_bytes": 8 << 20, "text_bytes": 4 << 20, "index_bytes": 1 << 20,
    "provenance_bytes": 64 << 10, "preview_bytes": 64 << 10,
    "metadata_bytes": 1 << 20, "pdf_pages": 500,
    "json_depth": 32, "work_seconds": 60,
}


class ToolFault(Exception):
    def __init__(self, code: str, message: str, *, status: str = "failed", details: dict | None = None):
        self.code, self.message, self.status = code, message, status
        self.details = details or {}
        super().__init__(message)

    def wire(self, effect: str = "unknown") -> dict:
        return {"code": self.code, "message": self.message[:1024], "details": self.details,
                "observed_effect_state": effect}


def wire(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: wire(getattr(value, field.name)) for field in dataclasses.fields(value)
                if not field.name.startswith("_")}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def encode(value: Any, cap: int | None = None) -> bytes:
    try:
        result = json.dumps(wire(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ToolFault("INVALID_JSON", "Value is not finite UTF-8 JSON", status="validation_failed") from exc
    if cap is not None and len(result) > cap:
        raise ToolFault("LIMIT_EXCEEDED", "Encoded JSON exceeds its byte limit", status="limit_exhausted")
    return result


def strict_json(raw: bytes, cap: int, depth: int = 32) -> Any:
    if len(raw) > cap or raw.startswith(b"\xef\xbb\xbf"):
        raise ToolFault("INVALID_JSON", "JSON bytes exceed limits or contain a BOM", status="validation_failed")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def bad_constant(_):
        raise ValueError("nonfinite number")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs, parse_constant=bad_constant)
        def check(node, level=0):
            if level > depth:
                raise ValueError("depth limit")
            if isinstance(node, float) and not math.isfinite(node):
                raise ValueError("nonfinite number")
            if isinstance(node, dict):
                for item in node.values(): check(item, level + 1)
            elif isinstance(node, list):
                for item in node: check(item, level + 1)
            elif isinstance(node, str): node.encode("utf-8", errors="strict")
        check(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ToolFault("INVALID_JSON", "Malformed, duplicate-key, nonfinite or excessively nested JSON", status="validation_failed") from exc


def closed(value: Any, keys: set[str], required: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or set(value) - keys or not (keys if required is None else required).issubset(value):
        raise ToolFault("INVALID_ARGUMENT", "Object fields do not match the closed schema", status="validation_failed")
    return value


def url(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 8192:
        raise ToolFault("INVALID_ARGUMENT", "URL must be bounded HTTP(S)", status="validation_failed")
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid URL")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("invalid port")
        if re.search(r"[\x00-\x20\x7f]", value): raise ValueError("control in URL")
        # Query-bearing discoveries remain intact, but credential fields never enter traces.
        if re.search(r"(?:^|[?&])(?:api[_-]?key|access[_-]?token|token|password|secret|authorization)=", parsed.query, re.I):
            raise ValueError("credential query")
    except ValueError as exc:
        raise ToolFault("INVALID_ARGUMENT", "Unsafe or malformed HTTP(S) URL", status="validation_failed") from exc
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def prefix_utf8(text: str, cap: int) -> str:
    return text.encode("utf-8")[:cap].decode("utf-8", errors="ignore")


def validate_arguments(name: str, arguments: Any, revision: int = 1) -> dict:
    encode(arguments, LIMITS["stdin_bytes"])
    if name in ("web.search", "scholar.crossref.search", "scholar.openalex.search"):
        value = closed(arguments, {"query", "max_results"}, {"query"})
        query = value["query"]
        count = value.get("max_results", 5)
        if not isinstance(query, str) or not query.strip() or len(query.encode("utf-8")) > 4096:
            raise ToolFault("INVALID_ARGUMENT", "Query must be nonblank and at most 4096 UTF-8 bytes", status="validation_failed")
        if type(count) is not int or not 1 <= count <= 10:
            raise ToolFault("INVALID_ARGUMENT", "max_results must be an integer in 1..10", status="validation_failed")
        return {"query": query, "max_results": count}
    if name == "web.fetch":
        value = closed(arguments, {"url", "mode"}, {"url"})
        mode = value.get("mode", "auto" if revision >= 2 else "static")
        if mode not in (("static", "auto") if revision >= 2 else ("static",)):
            raise ToolFault("INVALID_ARGUMENT", "Unsupported retrieval mode for this revision", status="validation_failed")
        return {"url": url(value["url"]), "mode": mode}
    if name == "document.read":
        value = closed(arguments, {"snapshot_ref", "range", "max_text_bytes", "continuation"}, {"snapshot_ref", "range"})
        interval = closed(value["range"], {"kind", "start", "end_exclusive"})
        start, end = interval["start"], interval["end_exclusive"]
        if interval["kind"] not in ("lines", "pages") or type(start) is not int or type(end) is not int or not 1 <= start <= end:
            raise ToolFault("INVALID_ARGUMENT", "Invalid one-based half-open range", status="validation_failed")
        if end - start > (200 if interval["kind"] == "lines" else 10):
            raise ToolFault("LIMIT_EXCEEDED", "Requested range exceeds unit cap", status="limit_exhausted")
        budget, cursor = value.get("max_text_bytes", 65536), value.get("continuation")
        if type(budget) is not int or not 1 <= budget <= 65536 or (cursor is not None and (not isinstance(cursor, str) or len(cursor.encode()) > 8192)):
            raise ToolFault("INVALID_ARGUMENT", "Invalid read budget or continuation", status="validation_failed")
        if not isinstance(value["snapshot_ref"], dict):
            raise ToolFault("INVALID_ARGUMENT", "snapshot_ref must be a typed reference object", status="validation_failed")
        return {"snapshot_ref": value["snapshot_ref"], "range": interval, "max_text_bytes": budget, "continuation": cursor}
    raise ToolFault("UNKNOWN_TOOL", "Tool is not registered", status="validation_failed")
