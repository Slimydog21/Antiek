"""Voice-note follow-up output parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .._json_decode import extract_json_object

MAX_PROMPTS = 3
MIN_PROMPT_LEN = 12


class VoiceNoteFollowupValidationError(ValueError):
    """Raised when the role's output fails structural validation."""


@dataclass(frozen=True)
class FollowupPrompt:
    prompt: str
    anchor_block_id: Optional[str]
    rationale: str


@dataclass(frozen=True)
class VoiceNoteFollowupResult:
    prompts: List[FollowupPrompt]


def parse_voice_note_followup_response(
    raw: str, *, known_block_ids: Optional[set[str]] = None,
) -> VoiceNoteFollowupResult:
    """Parse + validate the role's output. When ``known_block_ids`` is
    passed, ``anchor_block_id`` values not in the set raise."""
    data = extract_json_object(raw)
    if data is None:
        raise VoiceNoteFollowupValidationError("no JSON object in response")

    prompts_raw = data.get("prompts")
    if not isinstance(prompts_raw, list):
        raise VoiceNoteFollowupValidationError(
            "`prompts` must be a list"
        )
    if not prompts_raw:
        raise VoiceNoteFollowupValidationError(
            "must produce at least one follow-up prompt"
        )
    if len(prompts_raw) > MAX_PROMPTS:
        raise VoiceNoteFollowupValidationError(
            f"too many prompts ({len(prompts_raw)}); max is {MAX_PROMPTS}"
        )

    parsed: List[FollowupPrompt] = []
    for i, item in enumerate(prompts_raw):
        if not isinstance(item, dict):
            raise VoiceNoteFollowupValidationError(
                f"prompts[{i}] must be an object"
            )
        prompt_text = item.get("prompt")
        if not isinstance(prompt_text, str) or len(prompt_text.strip()) < MIN_PROMPT_LEN:
            raise VoiceNoteFollowupValidationError(
                f"prompts[{i}].prompt must be a non-empty string of ≥{MIN_PROMPT_LEN} chars"
            )
        anchor = item.get("anchor_block_id")
        if anchor is not None and not isinstance(anchor, str):
            raise VoiceNoteFollowupValidationError(
                f"prompts[{i}].anchor_block_id must be string or null"
            )
        if (
            anchor is not None
            and known_block_ids is not None
            and anchor not in known_block_ids
        ):
            raise VoiceNoteFollowupValidationError(
                f"prompts[{i}].anchor_block_id {anchor!r} is not in known_block_ids"
            )
        rationale = item.get("rationale") or ""
        if not isinstance(rationale, str):
            raise VoiceNoteFollowupValidationError(
                f"prompts[{i}].rationale must be a string"
            )
        parsed.append(FollowupPrompt(
            prompt=prompt_text.strip(),
            anchor_block_id=anchor,
            rationale=rationale.strip(),
        ))

    return VoiceNoteFollowupResult(prompts=parsed)
