"""Event -- the atomic unit of the conversation log."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

EventKind = Literal[
    "user_message", "assistant_message", "tool_call",
    "tool_result", "model_config", "system_marker",
]

_VALID_KINDS: frozenset[str] = frozenset(EventKind.__args__)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Event:
    position: int
    ts: str
    kind: EventKind
    payload: dict[str, Any]
    parent_checkpoint: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"unknown EventKind {self.kind!r}; valid kinds: {sorted(_VALID_KINDS)}"
            )
        if self.position < 1:
            raise ValueError(f"position must be >= 1, got {self.position}")

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
