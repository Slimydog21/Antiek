"""Note-taker output contract — the living-note distillation shape.

Owned by **DRW SPR-03** (the async note-taker). Mirrors
``roles/note_taker/parser.py``'s ``ExtractedNote`` exactly (verified L31-41):
a distilled insight parsed from a role response, which the bridge turns into
a ``NoteEmergedPayload`` and emits through the typed event log. The note is
later promoted into an insight node (``promote_from_note_event``), at which
point it becomes an :class:`~substrate.contracts.nodes.InsightNodeContract`.

The load-bearing field is ``source_event_ids``: a note with no attribution is
a hallucination and is dropped at parse time (parser rule 4). The contract
keeps that field required so a consumer cannot construct an unattributed note.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .nodes import ConfidenceLevel


class NoteTakerOutputContract(BaseModel):
    """One emerged insight from the note-taker. Field-for-field identical to
    ``roles.note_taker.parser.ExtractedNote`` (the in-tree dataclass), so a
    conformance check can verify the role's output satisfies this shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note_id: str
    text: str
    confidence: ConfidenceLevel
    # references *events*, not nodes (cannot be supported_by edges directly);
    # an empty tuple is invalid upstream — the parser drops unattributed notes.
    source_event_ids: tuple[str, ...]
