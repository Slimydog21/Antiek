"""Interviewer role output parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .._json_decode import extract_json_object

MIN_UTTERANCE_LEN = 4


class InterviewerValidationError(ValueError):
    """Raised when the role's output fails structural validation."""


@dataclass(frozen=True)
class InterviewerResult:
    interviewer_text: str
    should_end: bool
    must_cover_remaining_indices: List[int]
    follow_up_for_prior_turn: bool
    reasoning_note: Optional[str]


def parse_interviewer_response(raw: str) -> InterviewerResult:
    """Parse + validate one interviewer-role turn output."""
    data = extract_json_object(raw)
    if data is None:
        raise InterviewerValidationError("no JSON object in response")
    text = data.get("interviewer_text")
    if not isinstance(text, str) or len(text.strip()) < MIN_UTTERANCE_LEN:
        raise InterviewerValidationError(
            f"interviewer_text must be a non-empty string of ≥{MIN_UTTERANCE_LEN} chars"
        )
    should_end = bool(data.get("should_end", False))
    raw_indices = data.get("must_cover_remaining_indices") or []
    if not isinstance(raw_indices, list):
        raise InterviewerValidationError(
            "must_cover_remaining_indices must be a list"
        )
    indices: List[int] = []
    for v in raw_indices:
        if not isinstance(v, int) or v < 0:
            raise InterviewerValidationError(
                f"must_cover_remaining_indices entries must be non-negative ints; got {v!r}"
            )
        indices.append(v)
    follow_up = bool(data.get("follow_up_for_prior_turn", False))
    rationale = data.get("reasoning_note")
    if rationale is not None and not isinstance(rationale, str):
        raise InterviewerValidationError(
            "reasoning_note must be a string or null"
        )
    return InterviewerResult(
        interviewer_text=text.strip(),
        should_end=should_end,
        must_cover_remaining_indices=indices,
        follow_up_for_prior_turn=follow_up,
        reasoning_note=rationale.strip() if isinstance(rationale, str) else None,
    )
