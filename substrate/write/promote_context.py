"""Promote a pre-outline context window to a structured outline
(specs/write/ SPR-08 M4).

The outline-optional path: before any formal outline, a writer drops lego
blocks into a context window and states an objective (text/voice), then
generates directly (reusing SPR-06). If the piece grows, the loose context
can be **promoted** into a structured Deliverable/Section/OutlineBlock
(SPR-01) — preserving every block's provenance.

This module owns that promotion (the backend-testable core; the context-
window surface + the objective-by-voice intake are the SPR-08 UI). The
generation step itself is NOT re-implemented here — a context window maps
to a ``CreativeWriterContext`` via SPR-06's ``build_creative_writer_context``
(``context_specs_to_blocks`` below produces the OutlineBlocks SPR-06
consumes), so the freeform and outline paths share one generator and one
citation+gate contract.

Provenance is preserved on promotion: a node-backed context block stays a
``graph_node`` OutlineBlock (same node_id), a user-originated one stays
user-originated (no fabricated citation). The DB CHECK + ``place_block``
enforce it identically to every other Write path.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Literal

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import insert_deliverable, insert_section
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import insert_deliverable, insert_section  # type: ignore[no-redef]

from .outline_block import OutlineBlockError, place_block


@dataclass(frozen=True)
class ContextBlockSpec:
    """One block placed in the pre-outline context window. Either a
    reference to a graph node (provenance), or a user-originated block."""

    block_kind: str
    provenance_kind: Literal["graph_node", "user_authored", "synthesized", "brainstorm"]
    node_id: str | None = None
    content: str | None = None


@dataclass
class PromoteResult:
    deliverable_id: str
    section_id: str
    block_ids: list[str] = field(default_factory=list)


def _deliverable_investigation_id(con: LockedConnection, deliverable_id: str) -> str | None:
    row = con.execute(
        "SELECT investigation_root_id FROM deliverables WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    if row is None:
        raise OutlineBlockError(f"deliverable not found: {deliverable_id!r}")
    return row[0]


def promote_to_outline(
    con: LockedConnection,
    *,
    title: str,
    deliverable_kind: str,
    specs: list[ContextBlockSpec],
    objective: str = "",
    investigation_id: str = "__operator__",
    deliverable_id: str | None = None,
    section_id: str | None = None,
) -> PromoteResult:
    """Turn a context-window session into structured outline blocks.

    Default behavior creates a new deliverable with one section. When an
    existing ``deliverable_id`` is supplied, promotion creates a new section
    inside that piece instead. When ``section_id`` is supplied, it appends to
    that exact section. All paths preserve block provenance.
    """
    start_index = 0
    if section_id:
        row = con.execute(
            "SELECT deliverable_id FROM deliverable_sections WHERE section_id = ?",
            [section_id],
        ).fetchone()
        if row is None:
            raise OutlineBlockError(f"section not found: {section_id!r}")
        did = row[0]
        if deliverable_id and deliverable_id != did:
            raise OutlineBlockError(
                f"section {section_id!r} belongs to deliverable {did!r}, "
                f"not {deliverable_id!r}"
            )
        sid = section_id
        row = con.execute(
            "SELECT COALESCE(MAX(block_index), -1) + 1 "
            "FROM outline_blocks WHERE section_id = ?",
            [sid],
        ).fetchone()
        start_index = int(row[0] if row else 0)
    elif deliverable_id:
        _deliverable_investigation_id(con, deliverable_id)
        did = deliverable_id
        row = con.execute(
            "SELECT COALESCE(MAX(section_index), -1) + 1 "
            "FROM deliverable_sections WHERE deliverable_id = ?",
            [did],
        ).fetchone()
        sid = insert_section(
            con, deliverable_id=did, section_index=int(row[0] if row else 0),
            title=(objective[:120] if objective else title[:120]),
        )
    else:
        did = insert_deliverable(
            con, title=title, deliverable_kind=deliverable_kind,
            metadata={"promoted_from": "context_window", "objective": objective},
        )
        sid = insert_section(
            con, deliverable_id=did, section_index=0,
            title=(objective[:120] if objective else None),
        )
    result = PromoteResult(deliverable_id=did, section_id=sid)
    event_investigation_id = (
        _deliverable_investigation_id(con, did)
        if deliverable_id or section_id
        else investigation_id
    ) or investigation_id
    for i, spec in enumerate(specs):
        obid = place_block(
            con,
            section_id=sid,
            block_kind=spec.block_kind,
            provenance_kind=spec.provenance_kind,
            node_id=spec.node_id,
            content=spec.content,
            block_index=start_index + i,
            deliverable_id=did,
            investigation_id=event_investigation_id,
        )
        result.block_ids.append(obid)
    return result
