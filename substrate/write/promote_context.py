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


@dataclass
class InvestigationPromoteResult:
    """Outcome of promoting an investigation's synthesis into a seed
    deliverable (specs/write WV-SPR-01). Every field is honest about a
    real ordering state — none is silently coerced.

    - ``block_count``          blocks actually placed (one per pinned node).
    - ``dangling_count``       placed blocks whose source node is gone from
                               the graph (``block_count - dangling_count``
                               = live). Seeded, not dropped — the writer
                               sees 'source unavailable' via provenance.
    - ``source_node_count``    distinct nodes the synthesis pinned.
    - ``insufficient_evidence`` the dominant real case (the dogfood finding:
                               every real investigation ended here) — a
                               synthesis that exists but pinned zero nodes.
                               Surfaced as a flag, never papered over.
    """

    deliverable_id: str
    section_id: str
    block_ids: list[str] = field(default_factory=list)
    block_count: int = 0
    dangling_count: int = 0
    source_node_count: int = 0
    insufficient_evidence: bool = False
    synthesis_id: str | None = None
    synthesis_status: str | None = None
    synthesis_recommendation: str | None = None


# Outline block_kind for a synthesis-pinned graph node. The writing outline is
# composed of distilled-truth units; insight/question/claim map directly. Every
# other node_type (entity/person/metric/mechanism/...) falls back to 'insight':
# block_kind is descriptive, the node_id is the load-bearing provenance
# (``resolve_provenance`` reads it back). This is a documented mapping, not a
# silent coercion — a reviewer can argue for skipping non-distilled-truth nodes,
# but promoting them with their real node_id preserves the chain and the
# operator prunes in the SPR-02 dogfood.
_NODE_TYPE_TO_BLOCK_KIND: dict[str, str] = {
    "insight": "insight",
    "question": "open_question",
    "claim": "claim",
}


def _block_kind_for_node_type(node_type: str | None) -> str:
    return _NODE_TYPE_TO_BLOCK_KIND.get(node_type or "", "insight")


def promote_to_outline(
    con: LockedConnection,
    *,
    title: str,
    deliverable_kind: str,
    specs: list[ContextBlockSpec],
    owner_user_id: str,
    objective: str = "",
    investigation_id: str = "__operator__",
) -> PromoteResult:
    """Turn a context-window session into a structured deliverable with
    one section holding the placed blocks (provenance preserved). The
    objective is recorded on the deliverable metadata so the freeform
    intent survives the promotion."""
    did = insert_deliverable(
        con, title=title, deliverable_kind=deliverable_kind,
        owner_user_id=owner_user_id,
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


def promote_investigation_to_deliverable(
    con: LockedConnection,
    investigation_id: str,
    *,
    deliverable_kind: str,
    owner_user_id: str,
    title: str | None = None,
) -> InvestigationPromoteResult | None:
    """Promote a completed investigation's synthesis into a seed deliverable
    (specs/write WV-SPR-01 M2) — the compounding flywheel's missing writing
    arm. A deliverable is created with one outline section holding one
    graph-node block per synthesis-pinned source node, each carrying
    provenance back to its graph node (``resolve_provenance`` resolves
    node → document → chunks).

    Returns ``None`` when the investigation has **no** depositable synthesis
    (the route maps this to 404 — never an empty 200). Returns a result with
    ``insufficient_evidence=True`` when the synthesis exists but pinned zero
    source nodes — the dominant real case per the dogfood finding, surfaced
    honestly rather than papered over with placeholder blocks.

    Dangling source nodes (pinned by the synthesis but since deleted from the
    graph) are STILL placed — with their ``node_id`` — so the writer sees
    'source unavailable' via ``resolve_provenance`` (status ``dangling``)
    rather than a silent drop. ``block_count - dangling_count`` = live blocks.

    Single-writer discipline: ``con`` must be a ``LockedConnection`` from
    ``runtime.db_lock.connect_write``. Reads (synthesis lookup, node types)
    and writes (deliverable/section/blocks) share one lock so the promotion
    is atomic.
    """
    # 1. Find the investigation's most-recent DEPOSITABLE synthesis.
    #    - DEPOSITABLE = the research run finished: status != 'draft'. A draft
    #      is in-flight / unevaluated, not a completed conclusion, so it is not
    #      promoted as a deliverable (→ 404 if a draft is all that exists).
    #      The terminal outcomes (passed / regressed / max_iterations_reached /
    #      escalated) all represent a completed run and ARE promoted — the
    #      insufficient_evidence dogfood case is a terminal non-passed synthesis,
    #      which must still reach the arm. status is surfaced in the result so
    #      the operator sees exactly what was promoted.
    #    - MOST RECENT = by synthesis_timestamp (when it was made), NOT
    #      archived_at: a late backfill/retry archives an OLD synthesis LATE, so
    #      archived_at would wrongly win. synthesis_timestamp is NOT NULL.
    #    syntheses.investigation_id is a free TEXT (no FK), so an arbitrary id
    #    is a legitimate "no synthesis" → the caller (route) returns 404.
    syn = con.execute(
        "SELECT synthesis_id, target_question, implicit_recommendation, status "
        "FROM syntheses WHERE investigation_id = ? AND status != 'draft' "
        "ORDER BY synthesis_timestamp DESC, synthesis_id DESC LIMIT 1",
        [investigation_id],
    ).fetchone()
    if syn is None:
        return None
    synthesis_id, target_question, recommendation, synthesis_status = (
        syn[0], syn[1], syn[2], syn[3]
    )

    # 2. The synthesis's pinned source NODES — the distilled-truth units the
    #    writing outline is built from (manifest entity_kind='node').
    node_rows = con.execute(
        "SELECT entity_id FROM synthesis_substrate_manifest "
        "WHERE synthesis_id = ? AND entity_kind = 'node' "
        "ORDER BY entity_id",
        [synthesis_id],
    ).fetchall()
    source_node_ids: list[str] = [r[0] for r in node_rows]

    # 3. Resolve each pinned node's type + liveness in one query. Nodes absent
    #    here are dangling (deleted since the synthesis pinned them).
    live_types: dict[str, str | None] = {}
    if source_node_ids:
        placeholders = ", ".join(["?"] * len(source_node_ids))
        type_rows = con.execute(
            f"SELECT node_id, node_type FROM nodes "
            f"WHERE node_id IN ({placeholders})",
            source_node_ids,
        ).fetchall()
        live_types = {r[0]: r[1] for r in type_rows}

    # 4. Create the deliverable (linked to its source investigation) + one
    #    section titled with the synthesis's target question.
    did = insert_deliverable(
        con,
        title=title or target_question or "(untitled deliverable)",
        deliverable_kind=deliverable_kind,
        owner_user_id=owner_user_id,
        investigation_root_id=investigation_id,
        metadata={
            "promoted_from": "investigation_synthesis",
            "source_synthesis_id": synthesis_id,
        },
    )
    sid = insert_section(
        con,
        deliverable_id=did,
        section_index=0,
        title=(target_question[:120] if target_question else None),
    )

    # 5. One graph-node block per pinned source node. A dangling node's type is
    #    unknown (it is gone) → it places as a generic 'insight' block whose
    #    resolve_provenance is 'dangling'. No node is dropped.
    block_ids: list[str] = []
    dangling = 0
    for index, node_id in enumerate(source_node_ids):
        if node_id not in live_types:
            dangling += 1
        block_kind = _block_kind_for_node_type(live_types.get(node_id))
        obid = place_block(
            con,
            section_id=sid,
            block_kind=block_kind,
            provenance_kind="graph_node",
            node_id=node_id,
            block_index=index,
            deliverable_id=did,
            investigation_id=investigation_id,
        )
        block_ids.append(obid)

    return InvestigationPromoteResult(
        deliverable_id=did,
        section_id=sid,
        block_ids=block_ids,
        block_count=len(block_ids),
        dangling_count=dangling,
        source_node_count=len(source_node_ids),
        insufficient_evidence=(len(block_ids) == 0),
        synthesis_id=synthesis_id,
        synthesis_status=synthesis_status,
        synthesis_recommendation=recommendation,
    )
