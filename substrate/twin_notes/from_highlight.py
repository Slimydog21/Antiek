"""Seed a twin note from a reading/research highlight (pure).

Supports the operator loop: select text → open floating deep research →
optionally record a twin substrate document for the parent asset.

This module does **not** call LLMs. It validates the highlight, optional
operator-supplied insights/questions, and produces a fail-closed seed
suitable for ``TwinNotesStore.record`` or HTTP handoff.

Rules:
* parent_asset_id required non-empty
* highlight text required non-empty after strip; control-char rejected
* gated/withheld highlights fail closed (``gated=True`` → error)
* empty insights+questions is allowed (seed only; LLM note-taker is separate)
* never invents insights/questions from the highlight text
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

MAX_HIGHLIGHT_LEN = 50_000
MAX_ITEMS = 128
MAX_ITEM_LEN = 4000


class HighlightTwinError(ValueError):
    """Fail-closed validation for highlight twin seeds."""


@dataclass(frozen=True)
class HighlightTwinSeed:
    parent_asset_id: str
    highlight: str
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    source_label: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "highlight": self.highlight,
            "insights": list(self.insights),
            "questions": list(self.questions),
            "source_label": self.source_label,
            "notes": list(self.notes),
            "llm_filled": False,
            "authority": "highlight_seed_only",
        }

    def record_kwargs(self) -> dict[str, Any]:
        """Keyword args safe for TwinNotesStore.record (no invent)."""
        return {
            "parent_asset_id": self.parent_asset_id,
            "insights": list(self.insights),
            "questions": list(self.questions),
            "source_label": self.source_label,
        }


def _clean_text(value: object, *, field: str, max_len: int) -> str:
    if not isinstance(value, str):
        raise HighlightTwinError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise HighlightTwinError(f"{field} must be non-empty")
    if len(text) > max_len:
        raise HighlightTwinError(f"{field} exceeds {max_len} chars")
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise HighlightTwinError(f"{field} contains control characters")
    return text


def _clean_items(items: Sequence[object] | None, *, field: str) -> tuple[str, ...]:
    if items is None:
        return ()
    if not isinstance(items, (list, tuple)):
        raise HighlightTwinError(f"{field} must be a list or tuple")
    if len(items) > MAX_ITEMS:
        raise HighlightTwinError(f"{field} exceeds max of {MAX_ITEMS}")
    out: list[str] = []
    for i, raw in enumerate(items):
        if not isinstance(raw, str):
            raise HighlightTwinError(f"{field}[{i}] must be a string")
        t = raw.strip()
        if not t:
            continue  # strip empties; do not invent
        if len(t) > MAX_ITEM_LEN:
            raise HighlightTwinError(f"{field}[{i}] exceeds {MAX_ITEM_LEN} chars")
        if any(ord(c) < 32 and c not in "\n\t" for c in t):
            raise HighlightTwinError(f"{field}[{i}] contains control characters")
        out.append(t)
    return tuple(out)


def build_highlight_twin_seed(
    *,
    parent_asset_id: object,
    highlight: object,
    insights: Sequence[object] | None = None,
    questions: Sequence[object] | None = None,
    source_label: object = "highlight",
    gated: object = False,
) -> HighlightTwinSeed:
    """Validate a highlight and build a twin seed (no LLM)."""
    if not isinstance(gated, bool):
        raise HighlightTwinError("gated must be a boolean")
    if gated:
        raise HighlightTwinError(
            "gated/withheld highlight body cannot seed a twin (fail closed)"
        )

    parent = _clean_text(parent_asset_id, field="parent_asset_id", max_len=512)
    hl = _clean_text(highlight, field="highlight", max_len=MAX_HIGHLIGHT_LEN)
    label = _clean_text(source_label, field="source_label", max_len=128)
    ins = _clean_items(insights, field="insights")
    qs = _clean_items(questions, field="questions")

    notes = [
        "llm_filled=false — insights/questions are operator-supplied only",
        "authority=highlight_seed_only",
        f"highlight_chars={len(hl)}",
    ]
    if not ins and not qs:
        notes.append("seed has no insights/questions yet — twin is highlight context only")

    return HighlightTwinSeed(
        parent_asset_id=parent,
        highlight=hl,
        insights=ins,
        questions=qs,
        source_label=label,
        notes=tuple(notes),
    )


__all__ = [
    "HighlightTwinError",
    "HighlightTwinSeed",
    "build_highlight_twin_seed",
]
