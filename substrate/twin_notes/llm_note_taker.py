"""LLM note-taker adapter for recursive twin documents (pure).

Operator vision: every information asset has a twin of LLM-proposed insights
and questions. This module is the **fail-closed boundary** that accepts only
*already-produced* insights/questions (from an injected LLM result or human)
and shapes them into a twin record payload for ``TwinNotesStore.record``.

It does **not**:
* call any model / provider
* invent insights or questions from ``asset_text`` / ``asset_text_sha256``
* write the twin store (caller does)

Rules:
* parent_asset_id required
* at least one insight or question required (empty twin rejected)
* llm_filled must be explicit bool from caller (true only if they assert LLM produced the lists)
* gated asset text cannot seed notes (gated=True → error)
* asset_text is never parsed for content extraction here
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

MAX_ITEMS = 256
MAX_ITEM_LEN = 4000
MAX_SOURCE_LABEL = 128


class LlmNoteTakerError(ValueError):
    """Fail-closed validation for LLM note-taker payloads."""


@dataclass(frozen=True)
class TwinNotePayload:
    parent_asset_id: str
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    source_label: str
    llm_filled: bool
    asset_text_sha256: str | None
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "insights": list(self.insights),
            "questions": list(self.questions),
            "source_label": self.source_label,
            "llm_filled": self.llm_filled,
            "asset_text_sha256": self.asset_text_sha256,
            "notes": list(self.notes),
            "authority": "note_taker_payload_only",
            "model_invoked": False,
        }

    def record_kwargs(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "insights": list(self.insights),
            "questions": list(self.questions),
            "source_label": self.source_label,
        }


def _clean_id(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise LlmNoteTakerError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise LlmNoteTakerError(f"{field} must be non-empty")
    if len(text) > 512:
        raise LlmNoteTakerError(f"{field} exceeds 512 chars")
    return text


def _clean_items(items: Sequence[object] | None, *, field: str) -> tuple[str, ...]:
    if items is None:
        return ()
    if not isinstance(items, (list, tuple)):
        raise LlmNoteTakerError(f"{field} must be a list or tuple")
    if len(items) > MAX_ITEMS:
        raise LlmNoteTakerError(f"{field} exceeds max of {MAX_ITEMS}")
    out: list[str] = []
    for i, raw in enumerate(items):
        if not isinstance(raw, str):
            raise LlmNoteTakerError(f"{field}[{i}] must be a string")
        t = raw.strip()
        if not t:
            continue
        if len(t) > MAX_ITEM_LEN:
            raise LlmNoteTakerError(f"{field}[{i}] exceeds {MAX_ITEM_LEN} chars")
        if any(ord(c) < 32 and c not in "\n\t" for c in t):
            raise LlmNoteTakerError(f"{field}[{i}] contains control characters")
        out.append(t)
    return tuple(out)


def build_twin_note_payload(
    *,
    parent_asset_id: object,
    insights: Sequence[object] | None = None,
    questions: Sequence[object] | None = None,
    source_label: object = "llm-note-taker",
    llm_filled: object = False,
    asset_text_sha256: object | None = None,
    gated: object = False,
    asset_text: object | None = None,
) -> TwinNotePayload:
    """Build a twin note payload from injected lists only.

    ``asset_text`` is accepted only for optional integrity hashing by the
    *caller* — this function never derives insights from it. Passing
    ``asset_text`` without insights/questions still fails closed.
    """
    if not isinstance(gated, bool):
        raise LlmNoteTakerError("gated must be an explicit boolean")
    if gated:
        raise LlmNoteTakerError(
            "gated/withheld asset cannot receive note-taker twin (fail closed)"
        )
    if not isinstance(llm_filled, bool):
        raise LlmNoteTakerError("llm_filled must be an explicit boolean")

    parent = _clean_id(parent_asset_id, field="parent_asset_id")
    label = _clean_id(source_label, field="source_label")
    if len(label) > MAX_SOURCE_LABEL:
        raise LlmNoteTakerError(f"source_label exceeds {MAX_SOURCE_LABEL} chars")

    ins = _clean_items(insights, field="insights")
    qs = _clean_items(questions, field="questions")
    if not ins and not qs:
        raise LlmNoteTakerError(
            "at least one insight or question required (will not invent from asset_text)"
        )

    # Explicitly ignore asset_text content — presence alone is fine for provenance.
    if asset_text is not None and not isinstance(asset_text, str):
        raise LlmNoteTakerError("asset_text must be a string or null")

    sha: str | None
    if asset_text_sha256 is None:
        sha = None
    elif not isinstance(asset_text_sha256, str) or not asset_text_sha256.strip():
        raise LlmNoteTakerError("asset_text_sha256 must be non-empty string when provided")
    else:
        sha = asset_text_sha256.strip().lower()
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise LlmNoteTakerError("asset_text_sha256 must be 64-char lowercase hex")

    notes = [
        "model_invoked=false — this adapter never calls providers",
        "authority=note_taker_payload_only",
        f"llm_filled={llm_filled}",
        f"insight_count={len(ins)} question_count={len(qs)}",
    ]
    if asset_text is not None:
        notes.append(
            "asset_text provided but not used for extraction (no invent)"
        )

    return TwinNotePayload(
        parent_asset_id=parent,
        insights=ins,
        questions=qs,
        source_label=label,
        llm_filled=llm_filled,
        asset_text_sha256=sha,
        notes=tuple(notes),
    )


__all__ = [
    "LlmNoteTakerError",
    "TwinNotePayload",
    "build_twin_note_payload",
]
