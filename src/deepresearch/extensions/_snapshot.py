"""Bounded metadata copies; never serialize arbitrary live Python objects."""
from __future__ import annotations

import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any

from deepresearch.engine.contracts import EngineError

MAX_PAYLOAD_BYTES = 16_384
MAX_CONFIG_BYTES = 8_192
MAX_DEPTH = 8
MAX_VALUES = 1_024
MAX_STRING_BYTES = 512
MAX_CANDIDATES = 128
MAX_EXTENSIONS = 32
MAX_POINTS = 32
MAX_TIMEOUT_SECONDS = 30.0
MAX_ACTIVE_HANDLERS = 32

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_POINT = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")
_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
_PRIVATE_FIELDS = frozenset({
    "text", "rawtext", "content", "rawcontent", "body", "prompt", "prompts",
    "instructions", "query", "snippet", "title", "secret", "secrets",
    "password", "passwords", "credential", "credentials", "authorization",
    "apikey", "token", "accesstoken", "refreshtoken", "clientsecret",
    "headers", "cookies",
})


def identifier(value: Any, code: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise EngineError(code, "Hook identities must be bounded opaque identifiers")
    return value


def point_name(value: Any, code: str) -> str:
    if type(value) is not str or len(value) > 128 or _POINT.fullmatch(value) is None:
        raise EngineError(code, "Hook points must be bounded lowercase dotted names")
    return value


def plain(value: Any) -> Any:
    """Export a fresh JSON value from an already validated immutable snapshot."""
    if type(value) in (dict, MappingProxyType):
        return {key: plain(child) for key, child in value.items()}
    if type(value) is tuple:
        return [plain(child) for child in value]
    return value


def digest(value: Any) -> str:
    encoded = json.dumps(plain(value), sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def snapshot(value: Any, *, code: str, max_bytes: int) -> MappingProxyType:
    """Copy only native JSON metadata, counting bytes/values during traversal."""
    size = 0
    values = 0
    active: set[int] = set()

    def reject() -> None:
        raise EngineError(code, "Hook metadata must be bounded finite JSON without private content fields")

    def charge(amount: int) -> None:
        nonlocal size
        size += amount
        if size > max_bytes:
            reject()

    def string_bytes(item: str, limit: int) -> int:
        if len(item) > limit:
            reject()
        try:
            raw = item.encode("utf-8")
            encoded = json.dumps(item, ensure_ascii=False).encode("utf-8")
        except UnicodeError:
            reject()
        if len(raw) > limit:
            reject()
        return len(encoded)

    def copy(item: Any, depth: int) -> Any:
        nonlocal values
        values += 1
        if depth > MAX_DEPTH or values > MAX_VALUES:
            reject()
        kind = type(item)
        if kind in (dict, MappingProxyType, list, tuple):
            if id(item) in active or len(item) > MAX_VALUES - values:
                reject()
            active.add(id(item))
            charge(2 + max(0, len(item) - 1))
            try:
                if kind in (dict, MappingProxyType):
                    result = {}
                    for key, child in item.items():
                        if type(key) is not str or _KEY.fullmatch(key) is None:
                            reject()
                        normalized = key.lower().replace("_", "").replace("-", "").replace(".", "")
                        if normalized in _PRIVATE_FIELDS or normalized.endswith(("apikey", "password", "secret")):
                            reject()
                        charge(string_bytes(key, 64) + 1)
                        result[key] = copy(child, depth + 1)
                    return MappingProxyType(result)
                return tuple(copy(child, depth + 1) for child in item)
            finally:
                active.remove(id(item))
        if kind is str:
            charge(string_bytes(item, MAX_STRING_BYTES))
        elif kind is bool or item is None:
            charge(len(json.dumps(item)))
        elif kind is int:
            if item.bit_length() > 64:
                reject()
            charge(len(str(item)))
        elif kind is float:
            if not math.isfinite(item):
                reject()
            charge(len(json.dumps(item)))
        else:
            reject()
        return item

    if type(value) not in (dict, MappingProxyType):
        reject()
    return copy(value, 0)


def candidates(value: Any) -> tuple[str, ...]:
    code = "extension.invalid_candidates"
    if type(value) not in (list, tuple) or len(value) > MAX_CANDIDATES:
        raise EngineError(code, "Hook candidate IDs require a bounded list or tuple")
    ids = tuple(identifier(item, code) for item in value)
    if len(set(ids)) != len(ids):
        raise EngineError(code, "Host candidate IDs must be unique")
    return ids
