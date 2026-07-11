"""Recursive twin bind for every information asset (pure, fail-closed).

Every information asset may carry a twin of insights and questions.
This pure layer decides whether a twin *link* may be proposed and carries
only operator- or LLM-provided notes — never invents content from asset text.

twin_created is always False here (bind decision / payload only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TwinBindSource = Literal["operator", "llm_note_taker", "highlight_seed", "unknown"]

MAX_ID = 256
MAX_NOTE = 4000


class RecursiveTwinBindError(ValueError):
    """Fail-closed validation for recursive twin bind."""


@dataclass(frozen=True)
class RecursiveTwinBindDecision:
    parent_asset_id: str
    twin_id: str | None
    bind_allowed: bool
    twin_created: bool
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    source: TwinBindSource
    llm_filled: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "twin_id": self.twin_id,
            "bind_allowed": self.bind_allowed,
            "twin_created": False,
            "insights": list(self.insights),
            "questions": list(self.questions),
            "source": self.source,
            "llm_filled": self.llm_filled,
            "notes": list(self.notes),
            "authority": "twin_bind_advisory",
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise RecursiveTwinBindError(f"{field} must be an explicit boolean")
    return value


def _require_nonempty(value: object, *, field: str, max_len: int = MAX_ID) -> str:
    if not isinstance(value, str):
        raise RecursiveTwinBindError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise RecursiveTwinBindError(f"{field} must be non-empty")
    if len(text) > max_len:
        raise RecursiveTwinBindError(f"{field} exceeds {max_len} chars")
    return text


def _clean_string_list(value: object | None, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RecursiveTwinBindError(f"{field} must be a list of strings or null")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise RecursiveTwinBindError(f"{field}[{i}] must be a string")
        t = item.strip()
        if not t:
            continue
        if len(t) > MAX_NOTE:
            raise RecursiveTwinBindError(f"{field}[{i}] exceeds {MAX_NOTE} chars")
        out.append(t)
    return tuple(out)


def evaluate_recursive_twin_bind(
    *,
    parent_asset_id: object,
    gated: object,
    llm_filled: object,
    source: object,
    twin_id: object | None = None,
    insights: object | None = None,
    questions: object | None = None,
) -> RecursiveTwinBindDecision:
    """Decide whether a recursive twin bind may proceed. Never invents content."""
    gated_b = _require_bool(gated, field="gated")
    llm_filled_b = _require_bool(llm_filled, field="llm_filled")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    if not isinstance(source, str) or source not in (
        "operator",
        "llm_note_taker",
        "highlight_seed",
        "unknown",
    ):
        raise RecursiveTwinBindError(
            "source must be operator|llm_note_taker|highlight_seed|unknown"
        )
    src: TwinBindSource = source  # type: ignore[assignment]

    tid: str | None = None
    if twin_id is not None:
        if not isinstance(twin_id, str) or not twin_id.strip():
            raise RecursiveTwinBindError("twin_id must be non-empty string or null")
        tid = twin_id.strip()
        if len(tid) > MAX_ID:
            raise RecursiveTwinBindError(f"twin_id exceeds {MAX_ID} chars")

    notes: list[str] = []

    if gated_b is True:
        notes.append("gated parent asset — bind_allowed=false")
        return RecursiveTwinBindDecision(
            parent_asset_id=parent,
            twin_id=tid,
            bind_allowed=False,
            twin_created=False,
            insights=(),
            questions=(),
            source=src,
            llm_filled=False,
            notes=tuple(notes + ["twin_created=false", "insights/questions withheld"]),
            authority="twin_bind_advisory",
        )

    insight_t = _clean_string_list(insights, field="insights")
    question_t = _clean_string_list(questions, field="questions")

    if llm_filled_b is True:
        if src != "llm_note_taker":
            raise RecursiveTwinBindError(
                "llm_filled=true requires source=llm_note_taker (no invent provenance)"
            )
        if not insight_t and not question_t:
            raise RecursiveTwinBindError(
                "llm_filled=true requires non-empty insights or questions from caller (no invent)"
            )
        notes.append("llm_note_taker payload accepted — content is caller-supplied only")
    else:
        if src == "llm_note_taker":
            raise RecursiveTwinBindError(
                "source=llm_note_taker requires llm_filled=true with supplied lists"
            )
        if not insight_t and not question_t:
            notes.append(
                "no insights/questions supplied — bind still allowed as empty twin scaffold"
            )
        else:
            notes.append("operator/highlight insights-questions accepted as-supplied")

    if src == "unknown":
        notes.append("source=unknown — bind_allowed=false (provenance required)")
        return RecursiveTwinBindDecision(
            parent_asset_id=parent,
            twin_id=tid,
            bind_allowed=False,
            twin_created=False,
            insights=(),
            questions=(),
            source=src,
            llm_filled=False,
            notes=tuple(notes + ["twin_created=false"]),
            authority="twin_bind_advisory",
        )

    notes.append("bind_allowed=true — pure decision only")
    notes.append("twin_created=false")
    return RecursiveTwinBindDecision(
        parent_asset_id=parent,
        twin_id=tid,
        bind_allowed=True,
        twin_created=False,
        insights=insight_t,
        questions=question_t,
        source=src,
        llm_filled=llm_filled_b,
        notes=tuple(notes),
        authority="twin_bind_advisory",
    )


__all__ = [
    "RecursiveTwinBindDecision",
    "RecursiveTwinBindError",
    "evaluate_recursive_twin_bind",
]
