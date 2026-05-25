"""Write workflow substrate (specs/write/).

The authoring layer: a lego-block path from research to finished prose
where the edit is the product *and* the data. This package owns the two
genuinely net-new Write substrates:

- ``outline_block`` — the OutlineBlock composition layer (SPR-01). The
  "lego block" primitive: a unit of meaning placed in an outline section
  that either references an insight/question/claim graph node for
  provenance, or is explicitly marked user-originated. No orphan prose.
- ``outline`` / ``provenance`` / ``clustering`` / ``migrate_outline_block``
  — the SPR-01 satellites: hierarchy over deliverable_sections,
  block → node → document → chunks resolution (+ dangling detection),
  block grouping, and the idempotent migration from ``section_blocks``.

Everything here extends the existing Deliverable/Section/Block model
(``substrate/graph/schema.py``); none of it forks a parallel store.
Outlines and folders are *views over graph nodes* — the provenance chain
is the moat.

Edit/trajectory capture (SPR-02) lives in the sibling ``substrate/edit/``
package, not here, because it is write-side capture over the editor's
edits rather than composition over blocks.
"""

from __future__ import annotations

from .outline_block import (  # noqa: F401
    BLOCK_KINDS,
    PROVENANCE_KINDS,
    OutlineBlock,
    OutlineBlockError,
    get_block,
    list_section_blocks,
    move_block,
    place_block,
    place_node_block,
    place_user_authored_block,
    remove_block,
)

__all__ = [
    "BLOCK_KINDS",
    "PROVENANCE_KINDS",
    "OutlineBlock",
    "OutlineBlockError",
    "place_block",
    "place_node_block",
    "place_user_authored_block",
    "move_block",
    "remove_block",
    "list_section_blocks",
    "get_block",
]
