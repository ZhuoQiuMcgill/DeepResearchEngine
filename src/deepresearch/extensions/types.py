"""Immutable optional hook contracts, independent of Workflow implementations."""
from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
import math
from typing import Any, Literal, Protocol

from deepresearch.engine.contracts import EngineError
from ._snapshot import (
    MAX_CANDIDATES, MAX_CONFIG_BYTES, MAX_PAYLOAD_BYTES, MAX_POINTS,
    MAX_TIMEOUT_SECONDS, digest, identifier, plain, point_name, snapshot,
)


@dataclass(frozen=True, slots=True)
class HookEvent:
    run_id: str
    node_id: str | None
    point: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    payload_digest: str = field(init=False)

    def __post_init__(self) -> None:
        code = "extension.invalid_event"
        identifier(self.run_id, code)
        if self.node_id is not None:
            identifier(self.node_id, code)
        point_name(self.point, code)
        frozen = snapshot(self.payload, code=code, max_bytes=MAX_PAYLOAD_BYTES)
        object.__setattr__(self, "payload", frozen)
        object.__setattr__(self, "payload_digest", digest(frozen))

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "node_id": self.node_id, "point": self.point,
                "payload": plain(self.payload), "payload_digest": self.payload_digest}


@dataclass(frozen=True, slots=True)
class ExtensionSpec:
    extension_id: str
    revision: str
    points: tuple[str, ...]
    mode: Literal["observe", "control"] = "observe"
    timeout_seconds: float = 1.0
    config: Mapping[str, Any] = field(default_factory=dict)
    config_digest: str = field(init=False)

    def __post_init__(self) -> None:
        code = "extension.invalid_spec"
        identifier(self.extension_id, code)
        identifier(self.revision, code)
        if type(self.points) not in (tuple, list, set, frozenset) or not 1 <= len(self.points) <= MAX_POINTS:
            raise EngineError(code, "Extensions require a bounded nonempty collection of points")
        points = tuple(point_name(point, code) for point in self.points)
        if len(set(points)) != len(points):
            raise EngineError(code, "Extension points must be unique")
        object.__setattr__(self, "points", tuple(sorted(points)))
        if type(self.mode) is not str or self.mode not in ("observe", "control"):
            raise EngineError(code, "Unknown extension mode")
        if (type(self.timeout_seconds) not in (int, float)
                or not 0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS
                or not math.isfinite(self.timeout_seconds)):
            raise EngineError(code, "Hook timeouts must be positive and at most 30 seconds")
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        frozen = snapshot(self.config, code=code, max_bytes=MAX_CONFIG_BYTES)
        object.__setattr__(self, "config", frozen)
        object.__setattr__(self, "config_digest", digest(frozen))

    def to_dict(self) -> dict[str, Any]:
        return {"extension_id": self.extension_id, "revision": self.revision,
                "points": list(self.points), "mode": self.mode,
                "timeout_seconds": self.timeout_seconds, "config": plain(self.config),
                "config_digest": self.config_digest}


@dataclass(frozen=True, slots=True)
class HookDecision:
    """The entire control response: no actions, settings, grants or new IDs."""
    keep_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        code = "extension.invalid_decision"
        if type(self.keep_ids) is not tuple or len(self.keep_ids) > MAX_CANDIDATES:
            raise EngineError(code, "HookDecision requires a bounded tuple of candidate IDs")
        for item in self.keep_ids:
            identifier(item, code)

    def to_dict(self) -> dict[str, Any]:
        return {"keep_ids": list(self.keep_ids)}


class ObserverHandler(Protocol):
    def __call__(self, event: HookEvent, /) -> Awaitable[None]: ...


class ControlHandler(Protocol):
    def __call__(self, event: HookEvent, candidate_ids: tuple[str, ...], /) -> Awaitable[HookDecision]: ...


class RecordCallback(Protocol):
    def __call__(self, kind: str, payload: dict[str, Any], /) -> Awaitable[Any]: ...
