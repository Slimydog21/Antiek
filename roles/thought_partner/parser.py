"""Thought-partner response parser (Sprint 18, Surface E)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from roles._json_decode import extract_json_object


VALID_SHAPES: frozenset[str] = frozenset({"challenge", "synthesis", "extension"})


@dataclass(frozen=True)
class Challenge:
    condition: str
    note_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Synthesis:
    text: str


@dataclass(frozen=True)
class Extension:
    sub_question: str
    tag: Optional[str] = None
    rationale: Optional[str] = None


@dataclass(frozen=True)
class ThoughtPartnerResponse:
    shape: str  # one of VALID_SHAPES
    challenges: list[Challenge] = field(default_factory=list)
    synthesis: Optional[Synthesis] = None
    extensions: list[Extension] = field(default_factory=list)


def parse_thought_partner_response(text: str) -> ThoughtPartnerResponse:
    """Parse the JSON response from the thought-partner role.

    Defensive: malformed JSON, missing shape, or unknown shape values
    all coerce to a synthesis-shape response with the raw text. This
    avoids silent failures during Sprint 18 iteration when the prompt
    + parser are co-evolving.
    """
    obj = extract_json_object(text)
    if obj is None:
        return ThoughtPartnerResponse(
            shape="synthesis",
            synthesis=Synthesis(text=text.strip()),
        )

    shape = str(obj.get("shape", "synthesis")).lower()
    if shape not in VALID_SHAPES:
        shape = "synthesis"

    challenges_raw = obj.get("challenges", []) or []
    challenges: list[Challenge] = []
    for c in challenges_raw:
        if not isinstance(c, dict):
            continue
        condition = str(c.get("condition", "")).strip()
        if not condition:
            continue
        note_ids = [str(n) for n in (c.get("note_ids") or []) if n]
        challenges.append(Challenge(condition=condition, note_ids=note_ids))

    synthesis_text = obj.get("synthesis_text")
    synthesis = None
    if isinstance(synthesis_text, str) and synthesis_text.strip():
        synthesis = Synthesis(text=synthesis_text.strip())

    extensions_raw = obj.get("extensions", []) or []
    extensions: list[Extension] = []
    for e in extensions_raw:
        if not isinstance(e, dict):
            continue
        sub_q = str(e.get("sub_question", "")).strip()
        if not sub_q:
            continue
        tag = e.get("tag")
        rationale = e.get("rationale")
        extensions.append(Extension(
            sub_question=sub_q,
            tag=str(tag).strip() if tag else None,
            rationale=str(rationale).strip() if rationale else None,
        ))

    return ThoughtPartnerResponse(
        shape=shape,
        challenges=challenges,
        synthesis=synthesis,
        extensions=extensions,
    )
