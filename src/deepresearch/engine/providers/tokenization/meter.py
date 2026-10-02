"""Prospective content counts through explicit, pinned host tokenizers only."""
from __future__ import annotations

import hashlib
import inspect
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock

from deepresearch.engine.contracts import EngineError

from .counts import TokenCount, TokenScope

_ESTIMATOR = "utf8-byte-size/4"
_RENDERING = "source-text/1"
_SCOPES = frozenset({"document", "selected", "assembled"})
_CACHE_ENTRIES = 1024


@dataclass(frozen=True, slots=True)
class _Tokenizer:
    tokenizer_id: str
    tokenizer_revision: str
    count_callback: Callable[[str], int]
    registration: int


def _identity(value: str, name: str, max_length: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise EngineError("INVALID_DATA", f"{name} must be a nonblank bounded string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise EngineError("INVALID_DATA", f"{name} must be valid UTF-8") from None


def _nonnegative(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise EngineError("INVALID_DATA", f"{name} must be a nonnegative integer")


def _encode(text: str) -> bytes:
    if not isinstance(text, str):
        raise EngineError("INVALID_DATA", "Text must be a Unicode string")
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise EngineError("INVALID_DATA", "Text must be valid UTF-8") from None


class TokenMeter:
    """Measure supplied text without model requests or tokenizer discovery.

    Registration attests that the trusted host's synchronous local callback
    matches the named tokenizer revision. The callback counts the entire string
    without implicit splitting or service-added wrappers. Cache entries retain
    only frozen facts, never the source text or callbacks.
    """

    def __init__(self) -> None:
        self._tokenizers: dict[str, _Tokenizer] = {}
        self._cache: OrderedDict[tuple[object, ...], TokenCount] = OrderedDict()
        self._registration = 0
        self._lock = RLock()

    def register(
        self,
        model_ref: str,
        tokenizer_id: str,
        tokenizer_revision: str,
        count_callback: Callable[[str], int],
    ) -> None:
        """Bind or replace one model's tokenizer; invalidate its cached facts."""
        _identity(model_ref, "model_ref", 128)
        _identity(tokenizer_id, "tokenizer_id", 256)
        _identity(tokenizer_revision, "tokenizer_revision", 128)
        if not callable(count_callback) or inspect.iscoroutinefunction(count_callback):
            raise EngineError("INVALID_DATA", "Tokenizer count_callback must be synchronous and callable")
        with self._lock:
            self._registration += 1
            self._tokenizers[model_ref] = _Tokenizer(
                tokenizer_id, tokenizer_revision, count_callback, self._registration,
            )
            for key in tuple(self._cache):
                if key[0] == model_ref:
                    del self._cache[key]

    def measure(
        self,
        text: str,
        model_ref: str,
        scope: TokenScope = "selected",
        rendering_revision: str = _RENDERING,
        require_verified: bool = False,
    ) -> TokenCount:
        """Count the actual supplied rendering, or explicitly estimate its bytes."""
        if not isinstance(scope, str) or scope not in _SCOPES:
            raise EngineError("INVALID_DATA", "Unsupported token measurement scope")
        _identity(rendering_revision, "rendering_revision", 128)
        raw = _encode(text)
        tokenizer = self._profile(model_ref, require_verified)
        return self._measure(text, raw, model_ref, tokenizer, scope, rendering_revision)

    def estimate_document(
        self, text_bytes: int, text_sha256: str, model_ref: str,
    ) -> TokenCount:
        """Plan from retained metadata; size alone is always an estimate."""
        _nonnegative(text_bytes, "text_bytes")
        if not isinstance(text_sha256, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", text_sha256) is None:
            raise EngineError("INVALID_DATA", "text_sha256 must be a SHA-256 descriptor")
        tokenizer = self._profile(model_ref, False)
        return self._count(
            None, text_bytes, text_sha256, model_ref, tokenizer, "document", _RENDERING,
        )

    def fit(
        self,
        text: str,
        model_ref: str,
        token_budget: int,
        max_text_bytes: int,
        require_verified: bool = False,
    ) -> tuple[str, TokenCount, bool]:
        """Return a measured Unicode prefix, its facts and whether text was cut.

        A binary search retains only prefixes actually measured within budget.
        Callbacks need not have monotonic prefix counts, so this does not promise
        the longest possible prefix. Estimated counts give no actual-token bound.
        """
        _nonnegative(token_budget, "token_budget")
        _nonnegative(max_text_bytes, "max_text_bytes")
        raw = _encode(text)
        # Pin one registration across all probes, including the final selection.
        tokenizer = self._profile(model_ref, require_verified)
        # The original bytes are valid UTF-8; ignore only an incomplete final code point.
        candidate = raw[:max_text_bytes].decode("utf-8", errors="ignore")
        measurement = self._measure(
            candidate, candidate.encode("utf-8"), model_ref, tokenizer, "selected", _RENDERING,
        )
        if measurement.count <= token_budget:
            return candidate, measurement, candidate != text

        empty = self._measure("", b"", model_ref, tokenizer, "selected", _RENDERING)
        if empty.count > token_budget:
            raise EngineError("INVALID_DATA", "Even empty text exceeds the supplied token budget")
        lower, upper = 0, len(candidate)
        while lower + 1 < upper:
            middle = (lower + upper) // 2
            prefix = candidate[:middle]
            probe = self._measure(
                prefix, prefix.encode("utf-8"), model_ref, tokenizer, "selected", _RENDERING,
            )
            if probe.count <= token_budget:
                lower = middle
            else:
                upper = middle
        selected = candidate[:lower]
        measurement = self._measure(
            selected, selected.encode("utf-8"), model_ref, tokenizer, "selected", _RENDERING,
        )
        return selected, measurement, selected != text

    def _profile(self, model_ref: str, require_verified: bool) -> _Tokenizer | None:
        _identity(model_ref, "model_ref", 128)
        if type(require_verified) is not bool:
            raise EngineError("INVALID_DATA", "require_verified must be a boolean")
        with self._lock:
            tokenizer = self._tokenizers.get(model_ref)
        if require_verified and tokenizer is None:
            raise EngineError(
                "UNVERIFIED_TOKENIZER", "A pinned host tokenizer is required for this model",
                {"model_ref": model_ref},
            )
        return tokenizer

    def _measure(
        self, text: str, raw: bytes, model_ref: str, tokenizer: _Tokenizer | None,
        scope: TokenScope, rendering_revision: str,
    ) -> TokenCount:
        return self._count(
            text, len(raw), "sha256:" + hashlib.sha256(raw).hexdigest(),
            model_ref, tokenizer, scope, rendering_revision,
        )

    def _count(
        self, text: str | None, text_bytes: int, text_sha256: str,
        model_ref: str, tokenizer: _Tokenizer | None,
        scope: TokenScope, rendering_revision: str,
    ) -> TokenCount:
        verified = text is not None and tokenizer is not None
        kind = "verified" if verified else "estimated"
        estimator = None if verified else _ESTIMATOR
        tokenizer_id = tokenizer.tokenizer_id if tokenizer else None
        tokenizer_revision = tokenizer.tokenizer_revision if tokenizer else None
        key = (
            model_ref, tokenizer_id, tokenizer_revision, text_sha256,
            rendering_revision, scope, kind, estimator, text_bytes,
            tokenizer.registration if tokenizer else 0,
        )
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached

        if verified:
            try:
                count = tokenizer.count_callback(text)
            except Exception:
                # Retained content and arbitrary host exception messages are private.
                raise EngineError("INVALID_DATA", "Pinned tokenizer callback failed") from None
            if inspect.iscoroutine(count):
                count.close()
            _nonnegative(count, "Tokenizer callback count")
        else:
            count = (text_bytes + 3) // 4
        measurement = TokenCount(
            model_ref=model_ref, tokenizer_id=tokenizer_id,
            tokenizer_revision=tokenizer_revision, text_sha256=text_sha256,
            rendering_revision=rendering_revision, kind=kind, count=count,
            text_bytes=text_bytes, estimator=estimator, scope=scope,
        )
        with self._lock:
            # A callback may finish after its registration was replaced. Do not
            # repopulate invalidated entries; a fit still uses its pinned callback.
            if self._tokenizers.get(model_ref) is tokenizer:
                self._cache[key] = measurement
                self._cache.move_to_end(key)
                if len(self._cache) > _CACHE_ENTRIES:
                    self._cache.popitem(last=False)
        return measurement
