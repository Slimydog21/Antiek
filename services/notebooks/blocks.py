"""Closed block taxonomy for the per-document notebook (SPR-08 M2).

Mirrors the table in ``BLOCK_TAXONOMY.md`` in Python form. The
auto-populator + persistence layer import from here; renderers
(``apps/reading/src/modes/Notebook/blocks/``) mirror the same closed
set in TS.

Why closed?
-----------
Same argument as ``substrate.behavior.taxonomy``: each block becomes
a row joined into the medium-horizon reward proxy. An ad-hoc block
vocabulary breaks the join and pollutes the RL training signal. The
cost is one migration per added type; the cost of skipping the
discipline is policy-level garbage data.

Adding a block type
-------------------
1. Append a new value to ``BlockType``.
2. If the new block is sourced from an event type, extend
   ``EVENT_TYPE_TO_BLOCK_TYPE``.
3. Update ``BLOCK_TAXONOMY.md`` with the new row + rationale.
4. Bump ``BLOCK_TAXONOMY_VERSION``.
5. Add the corresponding TS block component + Storybook story.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


BLOCK_TAXONOMY_VERSION: Final[int] = 1
"""Bump when ``BlockType`` expands or the event→block mapping
changes. Stamped into ``notebook_documents.format_version``."""


class BlockType(str, Enum):
    """Closed set of per-document notebook block types (SPR-08).

    Values are stored strings; names are SCREAMING_SNAKE for Python
    import ergonomics. Do NOT repurpose a value; deprecate by adding
    a new one and leaving the old in the enum so historical rows
    decode.
    """

    HIGHLIGHT_CARD = "highlight_card"
    VOICE_BLOCK = "voice_block"
    AI_QA = "ai_qa"
    CITE_LINK = "cite_link"
    CROSS_DOC_JUMP = "cross_doc_jump"
    PROSE = "prose"


BLOCK_TYPES: Final[tuple[str, ...]] = tuple(b.value for b in BlockType)


# Tier-1 event type → block type. Used by the auto-populator.
# Values must be members of ``substrate.behavior.taxonomy.BehaviorEventType``.
# ``prose`` is intentionally NOT a target — operators don't create
# free-standing prose; see BLOCK_TAXONOMY.md "Why no + new block".
EVENT_TYPE_TO_BLOCK_TYPE: Final[dict[str, BlockType]] = {
    "highlight_created": BlockType.HIGHLIGHT_CARD,
    "voice_note_recorded": BlockType.VOICE_BLOCK,
    "ai_response_accepted": BlockType.AI_QA,
    "cite_jump": BlockType.CITE_LINK,
    "cross_doc_link_clicked": BlockType.CROSS_DOC_JUMP,
}


# Events the auto-populator deliberately ignores. Logged at debug
# level but not warned — these are the per-doc-span bookends.
EVENT_TYPES_SKIPPED: Final[frozenset[str]] = frozenset(
    {
        "document_opened",
        "document_closed",
        "reading_mode_toggled",
        "ai_prompt_sent",  # joined into ai_qa via prompt_id, not its own block
        "ai_response_rejected",  # negative signal — not a notebook block
        "highlight_removed",  # mutation, handled by populator merge logic
        "voice_note_played",  # playback, not creation
        "cross_doc_link_surfaced",  # only the CLICKED variant becomes a block
        "cross_doc_link_dismissed",  # negative signal
        "notebook_block_demoted",  # we EMIT this; we don't ingest it
        "notebook_block_edited",  # ditto
    }
)


def event_type_for_block(block_type: "str | BlockType") -> tuple[str, ...]:
    """Reverse lookup: which event type(s) source a given block type.

    Returns a tuple (always — even when only one event maps) so
    callers can write membership checks uniformly. Returns ``()`` for
    ``prose`` (no source event).
    """
    coerced = block_type if isinstance(block_type, BlockType) else BlockType(block_type)
    return tuple(
        ev for ev, bt in EVENT_TYPE_TO_BLOCK_TYPE.items() if bt is coerced
    )


__all__ = [
    "BLOCK_TAXONOMY_VERSION",
    "BLOCK_TYPES",
    "BlockType",
    "EVENT_TYPE_TO_BLOCK_TYPE",
    "EVENT_TYPES_SKIPPED",
    "event_type_for_block",
]
