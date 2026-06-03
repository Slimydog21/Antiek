"""Parse the note-taker's JSON response into typed insights.

Same code-fence / prose-preamble tolerance as the other role parsers
(wrestling, grounding, extraction). Tolerant of malformed responses —
returns empty list rather than raising.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

# Shared JSON-tolerant decoder. See roles/_json_decode.py for the
# extraction rationale (avoids import cycles through wrestling.py).
try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import (
        extract_json_object as _extract_json_object,  # type: ignore[no-redef]
    )


# Confidence vocabulary must match ConfidenceLevel Literal on the
# Claim/Note payloads. Same set used by the synthesizer's claims.
_VALID_CONFIDENCE = {"high", "moderate", "low", "unknown"}


@dataclass(frozen=True)
class ExtractedNote:
    """One emerged insight parsed from the role's response. The
    bridge handler turns this into a ``NoteEmergedPayload`` and emits
    via the typed event log."""

    note_id: str
    text: str
    confidence: str  # one of ConfidenceLevel
    source_event_ids: tuple[str, ...]


def _new_note_id() -> str:
    return "n-" + uuid.uuid4().hex[:12]


def _normalize_confidence(raw: Any) -> str:
    """Coerce to one of the 4 ConfidenceLevel values. Unknown input
    → ``"unknown"`` (matches the schema's "I don't know" value)."""
    if isinstance(raw, str) and raw.lower() in _VALID_CONFIDENCE:
        return raw.lower()
    return "unknown"


def parse_notes_response(text: str) -> list[ExtractedNote]:
    """Parse the role response into ``ExtractedNote`` list.

    Failure modes tolerated:
    - Non-JSON or unparseable → empty list (no notes; the next
      synthesis tick will try again with fresh wrestling history).
    - Missing ``notes`` key → empty list.
    - Note missing ``text`` or with non-string text → dropped.
    - Note with no ``source_event_ids`` → dropped (rule 4 of the
      prompt — unattributed notes are hallucinations).
    """
    obj = _extract_json_object(text)
    if obj is None:
        return []

    raw_notes = obj.get("notes")
    if not isinstance(raw_notes, list):
        return []

    out: list[ExtractedNote] = []
    for rn in raw_notes:
        if not isinstance(rn, dict):
            continue
        body = rn.get("text")
        if not isinstance(body, str) or not body.strip():
            continue
        attribution = rn.get("source_event_ids")
        if not isinstance(attribution, list):
            continue
        cleaned_attrib = tuple(
            str(a).strip() for a in attribution
            if isinstance(a, str) and str(a).strip()
        )
        if not cleaned_attrib:
            # Rule 4: drop unattributed notes. Hallucination defense.
            continue
        out.append(ExtractedNote(
            note_id=_new_note_id(),
            text=body.strip(),
            confidence=_normalize_confidence(rn.get("confidence")),
            source_event_ids=cleaned_attrib,
        ))
    return out
