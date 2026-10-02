"""Explicit pinned registrations; never discover or import extension code."""
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

from ebd.engine.contracts import EngineError
from ._snapshot import MAX_EXTENSIONS
from .types import ControlHandler, ExtensionSpec, ObserverHandler


def _async_callable(value: Any) -> bool:
    return callable(value) and (inspect.iscoroutinefunction(value)
                               or inspect.iscoroutinefunction(getattr(type(value), "__call__", None)))


@dataclass(frozen=True, slots=True)
class _Registration:
    spec: ExtensionSpec
    handler: ObserverHandler | ControlHandler


class ExtensionRegistry:
    """One immutable exact revision per extension ID in this registry."""

    def __init__(self) -> None:
        self._entries: dict[str, _Registration] = {}

    def register(self, spec: ExtensionSpec, handler: ObserverHandler | ControlHandler) -> ExtensionSpec:
        if type(spec) is not ExtensionSpec or not _async_callable(handler):
            raise EngineError("extension.invalid_registration", "Hooks require an ExtensionSpec and an async handler")
        try:
            inspect.signature(handler).bind(*(object(),) * (1 if spec.mode == "observe" else 2))
        except (TypeError, ValueError):
            raise EngineError("extension.invalid_registration", "Handler signature does not match its hook mode") from None
        existing = self._entries.get(spec.extension_id)
        if existing is not None:
            if existing.spec == spec and existing.handler is handler:
                return existing.spec
            raise EngineError("extension.registration_conflict", "An extension ID already has a different pinned registration",
                              {"extension_id": spec.extension_id, "revision": existing.spec.revision})
        if len(self._entries) >= MAX_EXTENSIONS:
            raise EngineError("extension.capacity", "Extension registry capacity is exhausted")
        self._entries[spec.extension_id] = _Registration(spec, handler)
        return spec

    @property
    def specs(self) -> tuple[ExtensionSpec, ...]:
        return tuple(entry.spec for entry in self._snapshot())

    def _snapshot(self) -> tuple[_Registration, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))
