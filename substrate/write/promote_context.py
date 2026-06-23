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

from .outline_block import place_block


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


def promote_to_outline(
    con: LockedConnection,
    *,
    title: str,
    deliverable_kind: str,
    specs: list[ContextBlockSpec],
    objective: str = "",
    investigation_id: str = "__operator__",
) -> PromoteResult:
    """Turn a context-window session into a structured deliverable with
    one section holding the placed blocks (provenance preserved). The
    objective is recorded on the deliverable metadata so the freeform
    intent survives the promotion."""
    did = insert_deliverable(
        con, title=title, deliverable_kind=deliverable_kind,
        metadata={"promoted_from": "context_window", "objective": objective},
    )
    sid = insert_section(
        con, deliverable_id=did, section_index=0,
        title=(objective[:120] if objective else None),
    )
    result = PromoteResult(deliverable_id=did, section_id=sid)
    for i, spec in enumerate(specs):
        obid = place_block(
            con,
            section_id=sid,
            block_kind=spec.block_kind,
            provenance_kind=spec.provenance_kind,
            node_id=spec.node_id,
            content=spec.content,
            block_index=i,
            deliverable_id=did,
            investigation_id=investigation_id,
        )
        result.block_ids.append(obid)
    return result
