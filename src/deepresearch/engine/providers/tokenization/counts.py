"""Engine-native, immutable retained-content measurement metadata."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

TokenScope = Literal["document", "selected", "assembled"]
TokenKind = Literal["verified", "estimated", "unknown"]


@dataclass(frozen=True, slots=True)
class TokenCount:
    """Wire-compatible facts; ``to_dict`` returns a new, independent dictionary."""

    model_ref: str
    text_sha256: str
    kind: TokenKind
    text_bytes: int
    tokenizer_id: str | None = None
    tokenizer_revision: str | None = None
    rendering_revision: str = "source-text/1"
    count: int | None = None
    estimator: str | None = None
    scope: TokenScope = "selected"
    schema_version: int = field(default=1, init=False)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
