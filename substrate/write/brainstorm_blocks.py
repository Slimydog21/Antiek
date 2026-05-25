"""Brainstorm drivers → lego blocks (specs/write/ SPR-05 M4).

After the brainstorm-interview identifies the insights/questions/data
driving an idea (``roles/interviewer/drivers.DriverSet``), this module
takes notes as **OutlineBlocks** (SPR-01) the writer can place in an
outline — each marked honestly:

- insights      → block_kind ``insight``,       provenance_kind ``brainstorm``
- questions     → block_kind ``open_question``,  provenance_kind ``brainstorm``
- data_points   → block_kind ``user_authored``,  provenance_kind ``brainstorm``,
                  flagged ``unverified_claim`` in metadata

The provenance is the brainstorm **session**, not an external document —
so blocks carry NO ``node_id`` (no fabricated citation; the DB CHECK +
``place_block`` enforce this). Data the user merely asserted is flagged as
a claim to verify, never minted as established data (rigor #1).

Dedup (rigor #3): a content-addressed ``outline_block_id`` derived from
``(section_id, kind, normalized_text)`` makes re-emitting the same driver
idempotent — a vague idea re-dumped does not spawn duplicate blocks.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import content_addressed_id
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import content_addressed_id  # type: ignore[no-redef]

from .outline_block import place_block

# Local import of the DriverSet type for annotations only (avoids a hard
# roles→substrate dependency cycle at import time).
try:
    from roles.interviewer.drivers import DriverSet
except Exception:  # pragma: no cover
    DriverSet = Any  # type: ignore[assignment,misc]


@dataclass
class BrainstormResult:
    """What a brainstorm-to-blocks run produced."""

    block_ids: list[str] = field(default_factory=list)
    insight_count: int = 0
    question_count: int = 0
    data_count: int = 0
    skipped_duplicates: int = 0
    # The block_ids whose content is an unverified asserted "data" claim.
    flagged_unverified: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def drivers_to_blocks(
    con: LockedConnection,
    *,
    section_id: str,
    drivers: "DriverSet",
    deliverable_id: str | None = None,
    investigation_id: str = "__operator__",
    start_index: int = 0,
) -> BrainstormResult:
    """Place a brainstorm's drivers as OutlineBlocks. Idempotent per
    (section, kind, text). Returns a ``BrainstormResult``."""
    result = BrainstormResult()
    index = start_index

    def _place(text: str, block_kind: str, *, unverified: bool = False) -> None:
        nonlocal index
        obid = content_addressed_id(
            "oblk", f"{section_id}|brainstorm|{block_kind}|{_normalize(text)}"
        )
        already = con.execute(
            "SELECT 1 FROM outline_blocks WHERE outline_block_id = ? LIMIT 1",
            [obid],
        ).fetchone() is not None
        if already:
            result.skipped_duplicates += 1
            return
        place_block(
            con,
            section_id=section_id,
            block_kind=block_kind,
            provenance_kind="brainstorm",
            content=text,
            block_index=index,
            outline_block_id=obid,
            deliverable_id=deliverable_id,
            investigation_id=investigation_id,
            metadata=(
                {"origin": "brainstorm", "unverified_claim": True}
                if unverified else {"origin": "brainstorm"}
            ),
            on_conflict="ignore",
        )
        result.block_ids.append(obid)
        if unverified:
            result.flagged_unverified.append(obid)
        index += 1

    for text in drivers.insights:
        _place(text, "insight")
        result.insight_count += 1
    for text in drivers.questions:
        _place(text, "open_question")
        result.question_count += 1
    for text in drivers.data_points:
        # Asserted data is a claim to verify — flagged, never minted as fact.
        _place(text, "user_authored", unverified=True)
        result.data_count += 1

    return result
