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
from hashlib import sha256
from typing import Literal

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import insert_deliverable, insert_section
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import insert_deliverable, insert_section  # type: ignore[no-redef]

from substrate.event_log import trajectory

from .outline_block import emit_block_placed, place_block


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
    """

    deliverable_id: str
    section_id: str
    block_ids: list[str] = field(default_factory=list)
    block_count: int = 0
    dangling_count: int = 0
    source_node_count: int = 0
    synthesis_id: str | None = None
    synthesis_status: str | None = None
    synthesis_recommendation: str | None = None


@dataclass(frozen=True)
class InvestigationPromotionRefusal:
    """A synthesis exists, but cannot honestly seed a writing deliverable.

    This is distinct from ``None`` (no completed synthesis). Keeping the
    refusal typed lets the HTTP boundary report a stable conflict reason
    without repeating the promotion query or creating placeholder rows.
    """

    synthesis_id: str
    synthesis_status: str
    synthesis_recommendation: str
    gate_failed: Literal[
        "status", "recommendation", "no_source_nodes", "all_dangling"
    ]
    source_node_count: int
    live_source_node_count: int
    dangling_count: int


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


def _ensure_placement_events(
    *,
    investigation_id: str,
    deliverable_id: str,
    section_id: str,
    blocks: list[tuple[str, str, str | None, int]],
) -> None:
    emitted_ids = {
        row.get("payload", {}).get("outline_block_id")
        for row in trajectory(investigation_id)
        if row.get("action_type") == "outline_block.placed"
    }
    for block_id, block_kind, node_id, index in blocks:
        if block_id in emitted_ids:
            continue
        emit_block_placed(
            outline_block_id=block_id,
            deliverable_id=deliverable_id,
            section_id=section_id,
            block_kind=block_kind,
            provenance_kind="graph_node",
            node_id=node_id,
            block_index=index,
            investigation_id=investigation_id,
        )


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


def promote_investigation_to_deliverable(
    con: LockedConnection,
    investigation_id: str,
    *,
    deliverable_kind: str,
    title: str | None = None,
) -> InvestigationPromoteResult | InvestigationPromotionRefusal | None:
    """Promote a completed investigation's synthesis into a seed deliverable
    (specs/write WV-SPR-01 M2) — the compounding flywheel's missing writing
    arm. A deliverable is created with one outline section holding one
    graph-node block per synthesis-pinned source node, each carrying
    provenance back to its graph node (``resolve_provenance`` resolves
    node → document → chunks).

    Returns ``None`` when the investigation has **no** depositable synthesis
    (the route maps this to 404). Returns an
    ``InvestigationPromotionRefusal`` when a synthesis exists but its verdict
    or provenance cannot support a writing seed (the route maps this to 409).
    Refusal happens before the first write, so it cannot leave an empty
    deliverable or section behind.

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
    #      escalated) all represent completed runs. Their recommendation and
    #      evidence still have to pass the promotion gate below.
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

    # 4. Decide whether the synthesis can honestly seed writing before the
    #    first insert. DuckDB statements autocommit through this connection;
    #    preflight ordering is what guarantees a refusal creates zero rows.
    dangling = len(source_node_ids) - len(live_types)
    effective_title = title or target_question or "(untitled deliverable)"
    identity_material = "\0".join(
        (synthesis_id, deliverable_kind, effective_title)
    )
    identity = sha256(identity_material.encode()).hexdigest()[:24]
    did = f"dlv-promote-{identity}"
    sid = f"sec-promote-{identity}"
    existing = con.execute(
        "SELECT 1 FROM deliverables WHERE deliverable_id = ?",
        [did],
    ).fetchone()
    if existing is not None:
        placed_blocks = [
            (row[0], row[1], row[2], int(row[3]))
            for row in con.execute(
                "SELECT outline_block_id, block_kind, node_id, block_index "
                "FROM outline_blocks WHERE section_id = ? "
                "ORDER BY block_index, outline_block_id",
                [sid],
            ).fetchall()
        ]
        _ensure_placement_events(
            investigation_id=investigation_id,
            deliverable_id=did,
            section_id=sid,
            blocks=placed_blocks,
        )
        return InvestigationPromoteResult(
            deliverable_id=did,
            section_id=sid,
            block_ids=[row[0] for row in placed_blocks],
            block_count=len(placed_blocks),
            dangling_count=dangling,
            source_node_count=len(source_node_ids),
            synthesis_id=synthesis_id,
            synthesis_status=synthesis_status,
            synthesis_recommendation=recommendation,
        )

    if synthesis_status != "passed":
        return InvestigationPromotionRefusal(
            synthesis_id=synthesis_id,
            synthesis_status=synthesis_status,
            synthesis_recommendation=recommendation,
            gate_failed="status",
            source_node_count=len(source_node_ids),
            live_source_node_count=len(live_types),
            dangling_count=dangling,
        )
    if recommendation in {"undetermined", "insufficient_evidence"}:
        return InvestigationPromotionRefusal(
            synthesis_id=synthesis_id,
            synthesis_status=synthesis_status,
            synthesis_recommendation=recommendation,
            gate_failed="recommendation",
            source_node_count=len(source_node_ids),
            live_source_node_count=len(live_types),
            dangling_count=dangling,
        )
    if not source_node_ids:
        return InvestigationPromotionRefusal(
            synthesis_id=synthesis_id,
            synthesis_status=synthesis_status,
            synthesis_recommendation=recommendation,
            gate_failed="no_source_nodes",
            source_node_count=0,
            live_source_node_count=0,
            dangling_count=0,
        )
    if not live_types:
        return InvestigationPromotionRefusal(
            synthesis_id=synthesis_id,
            synthesis_status=synthesis_status,
            synthesis_recommendation=recommendation,
            gate_failed="all_dangling",
            source_node_count=len(source_node_ids),
            live_source_node_count=0,
            dangling_count=dangling,
        )

    # Stable request identity lets transport retries converge without collapsing
    # intentionally different title or deliverable-kind seeds.
    con.execute("BEGIN TRANSACTION")
    try:
        insert_deliverable(
            con,
            title=effective_title,
            deliverable_kind=deliverable_kind,
            investigation_root_id=investigation_id,
            metadata={
                "promoted_from": "investigation_synthesis",
                "source_synthesis_id": synthesis_id,
            },
            deliverable_id=did,
        )
        insert_section(
            con,
            deliverable_id=did,
            section_index=0,
            title=(target_question[:120] if target_question else None),
            section_id=sid,
        )

        # 6. One graph-node block per pinned source node. A dangling node's type
        #    is unknown, so it places as a generic insight whose provenance
        #    resolves to source unavailable. No node is silently dropped.
        block_ids: list[str] = []
        placed_blocks: list[tuple[str, str, str | None, int]] = []
        for index, node_id in enumerate(source_node_ids):
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
                outline_block_id=f"oblk-promote-{identity}-{index}",
                emit_event=False,
            )
            block_ids.append(obid)
            placed_blocks.append((obid, block_kind, node_id, index))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    _ensure_placement_events(
        investigation_id=investigation_id,
        deliverable_id=did,
        section_id=sid,
        blocks=placed_blocks,
    )

    return InvestigationPromoteResult(
        deliverable_id=did,
        section_id=sid,
        block_ids=block_ids,
        block_count=len(block_ids),
        dangling_count=dangling,
        source_node_count=len(source_node_ids),
        synthesis_id=synthesis_id,
        synthesis_status=synthesis_status,
        synthesis_recommendation=recommendation,
    )
