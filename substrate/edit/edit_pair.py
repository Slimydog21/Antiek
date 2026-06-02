"""Structured before/after edit-pair capture (specs/write/ SPR-02 M1).

Today the only write-side capture is ``updateSectionProse``'s coarse
whole-section ``original_text`` vs ``prose_text`` — useless for paragraph-
level style or granular signal. This module captures *granular* edits as
``edit.captured`` events: a locator, an edit kind (insert/delete/replace/
reorder), the before/after text, and a ``reverted`` flag.

The event log IS the store — there is no parallel edit table. The whole
event log is already an immutable trajectory (architecture_notes §2.1);
edits are first-class typed events in it, which is exactly what the
authoring-trajectory reconstruction (M2) and the Loop-3 harvest (M3) read.

Stable locators: an edit anchors to ``section_id`` plus an optional
``outline_block_id`` / ``paragraph_index`` / ``sentence_index``. SPR-04's
editor produces these (and guarantees their stability across edits); this
module defines the schema they fill.

CAPTURE ≠ TRAINING. ``capture_edit`` writes an ungated event and never
computes a reward or touches the trainer.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Literal

try:
    from ..event_log import emit_typed
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed  # type: ignore[no-redef]

from substrate.schemas.events import EditCapturedPayload

EditKind = Literal["insert", "delete", "replace", "reorder"]
Granularity = Literal["block", "paragraph", "sentence"]

EDIT_KINDS: tuple[str, ...] = ("insert", "delete", "replace", "reorder")
GRANULARITIES: tuple[str, ...] = ("block", "paragraph", "sentence")


@dataclass(frozen=True)
class EditLocator:
    """A stable address for an edit within a deliverable. The optional
    fields narrow from section → block → paragraph → sentence."""

    deliverable_id: str
    section_id: str
    outline_block_id: str | None = None
    paragraph_index: int | None = None
    sentence_index: int | None = None

    def key(self) -> str:
        """A stable, comparable string key for this locator."""
        return "|".join(
            str(x) for x in (
                self.deliverable_id, self.section_id,
                self.outline_block_id or "-",
                self.paragraph_index if self.paragraph_index is not None else "-",
                self.sentence_index if self.sentence_index is not None else "-",
            )
        )


@dataclass(frozen=True)
class EditPair:
    """Read projection of one ``edit.captured`` event."""

    locator: EditLocator
    granularity: str
    edit_kind: str
    before_text: str | None
    after_text: str | None
    reverted: bool
    session_id: str | None
    event_id: str | None = None
    emitted_at: str | None = None

    @classmethod
    def from_event(cls, ev: dict) -> EditPair:
        p = ev.get("payload", {}) or {}
        return cls(
            locator=EditLocator(
                deliverable_id=p.get("deliverable_id", ""),
                section_id=p.get("section_id", ""),
                outline_block_id=p.get("outline_block_id"),
                paragraph_index=p.get("paragraph_index"),
                sentence_index=p.get("sentence_index"),
            ),
            granularity=p.get("granularity", "block"),
            edit_kind=p.get("edit_kind", "replace"),
            before_text=p.get("before_text"),
            after_text=p.get("after_text"),
            reverted=bool(p.get("reverted", False)),
            session_id=p.get("session_id"),
            event_id=ev.get("event_id"),
            emitted_at=ev.get("emitted_at"),
        )


def capture_edit(
    *,
    locator: EditLocator,
    edit_kind: EditKind,
    granularity: Granularity,
    before_text: str | None = None,
    after_text: str | None = None,
    reverted: bool = False,
    session_id: str | None = None,
    investigation_id: str = "__operator__",
    parent_event_id: str | None = None,
) -> str | None:
    """Capture one granular edit as an ``edit.captured`` event. Returns
    the event_id (or None when events are disabled).

    Ungated by design — capture always runs. The reward is never computed
    here; the training-bound harvest is gated downstream
    (``harvest_authoring.harvest_authoring_for_training``)."""
    payload = EditCapturedPayload(
        deliverable_id=locator.deliverable_id,
        section_id=locator.section_id,
        outline_block_id=locator.outline_block_id,
        granularity=granularity,
        edit_kind=edit_kind,
        paragraph_index=locator.paragraph_index,
        sentence_index=locator.sentence_index,
        before_text=before_text,
        after_text=after_text,
        reverted=reverted,
        session_id=session_id,
    )
    return emit_typed(
        investigation_id, payload,
        parent_event_id=parent_event_id,
        role="write_editor",
    )
