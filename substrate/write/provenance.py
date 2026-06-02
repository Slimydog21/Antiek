"""Provenance resolution for OutlineBlocks (specs/write/ SPR-01 M3).

Given a lego block, resolve back to its source of truth:

    block → node → document → chunks

This is the chain SPR-07 (trace-to-source) consumes: from a block or a
generated sentence's citation, open the source document in the shared
reader at the cited span. SPR-01 only makes the chain *resolvable*; the
reader UI is SPR-07.

Three terminal states, all explicit (no silent breakage):

- ``resolved``        → a graph node was found; document/chunks are
                        attached when the node links to a source.
- ``dangling``        → the block claims graph provenance but its source
                        node is gone (deleted/never-promoted). Surfaced,
                        not crashed — the writer sees "source unavailable".
- ``user_originated`` → the block is user-authored / synthesized /
                        brainstorm. It has no external document by design;
                        we report the origin honestly rather than
                        inventing a citation.

node → chunk linkage mirrors the existing block-palette search
(``interfaces/research/api/app.py``): a node's ``metadata.chunk_id``
points at the chunk it was distilled from, and any ``edges`` referencing
the node also carry ``chunk_id``s. We gather both, then resolve chunks to
their documents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from .outline_block import OutlineBlock, get_block

ProvenanceStatus = Literal["resolved", "dangling", "user_originated"]


@dataclass(frozen=True)
class ProvenanceChain:
    """The resolved provenance of one block. ``status`` is the single
    field a caller must branch on; the rest are populated as available."""

    outline_block_id: str
    status: ProvenanceStatus
    provenance_kind: str
    node_id: str | None = None
    node_label: str | None = None
    node_type: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    chunk_ids: list[str] = field(default_factory=list)
    # Human-readable explanation for non-``resolved``-with-document cases
    # (dangling source, user origin, or a node with no source document).
    detail: str | None = None

    @property
    def has_source_document(self) -> bool:
        return self.status == "resolved" and self.document_id is not None


def _node_metadata_chunk_id(metadata_text: str | None) -> str | None:
    if not metadata_text:
        return None
    try:
        meta = json.loads(metadata_text)
    except (json.JSONDecodeError, TypeError):
        return None
    cid = meta.get("chunk_id") if isinstance(meta, dict) else None
    return str(cid) if cid else None


def resolve_provenance(
    con: Any,
    block: OutlineBlock | str,
) -> ProvenanceChain:
    """Resolve a block's provenance chain. ``block`` may be an
    ``OutlineBlock`` or an ``outline_block_id``. ``con`` is any duckdb
    connection (read-only is fine)."""
    if isinstance(block, str):
        resolved = get_block(con, block)
        if resolved is None:
            return ProvenanceChain(
                outline_block_id=block, status="dangling",
                provenance_kind="unknown",
                detail="outline block not found",
            )
        block = resolved

    # User-originated: honest origin, no fabricated document.
    if block.is_user_originated:
        origin = {
            "user_authored": "operator-authored block (no external source)",
            "synthesized": "synthesized from other blocks (no external source)",
            "brainstorm": "emerged in a brainstorm session (user-originated)",
        }.get(block.provenance_kind, "user-originated block")
        return ProvenanceChain(
            outline_block_id=block.outline_block_id,
            status="user_originated",
            provenance_kind=block.provenance_kind,
            detail=origin,
        )

    # Graph-node-backed: resolve node → chunks → document.
    node_id = block.node_id
    assert node_id is not None  # invariant: graph_node ⟹ node_id present
    node_row = con.execute(
        "SELECT canonical_label, node_type, metadata FROM nodes WHERE node_id = ?",
        [node_id],
    ).fetchone()
    if node_row is None:
        return ProvenanceChain(
            outline_block_id=block.outline_block_id,
            status="dangling",
            provenance_kind=block.provenance_kind,
            node_id=node_id,
            detail=(
                "source node deleted or not yet promoted to the graph — "
                "trace shows 'source unavailable'"
            ),
        )

    node_label, node_type, node_meta = node_row[0], node_row[1], node_row[2]

    # Gather candidate chunk ids: the node's distillation chunk + any
    # chunks referenced by edges on this node. Deterministic ordering.
    chunk_ids: list[str] = []
    primary_chunk = _node_metadata_chunk_id(node_meta)
    if primary_chunk:
        chunk_ids.append(primary_chunk)
    edge_rows = con.execute(
        "SELECT DISTINCT chunk_id FROM edges "
        "WHERE (source_node_id = ? OR target_node_id = ?) "
        "AND chunk_id IS NOT NULL ORDER BY chunk_id",
        [node_id, node_id],
    ).fetchall()
    for er in edge_rows:
        if er[0] and er[0] not in chunk_ids:
            chunk_ids.append(er[0])

    document_id: str | None = None
    document_title: str | None = None
    if chunk_ids:
        doc_row = con.execute(
            "SELECT c.document_id, d.title FROM chunks c "
            "LEFT JOIN documents d ON c.document_id = d.document_id "
            "WHERE c.chunk_id = ? LIMIT 1",
            [chunk_ids[0]],
        ).fetchone()
        if doc_row is not None:
            document_id, document_title = doc_row[0], doc_row[1]

    detail = None
    if document_id is None:
        detail = (
            "node resolved but no source chunk/document is linked yet — "
            "trace lands on the node, not a document span"
        )
    return ProvenanceChain(
        outline_block_id=block.outline_block_id,
        status="resolved",
        provenance_kind=block.provenance_kind,
        node_id=node_id,
        node_label=node_label,
        node_type=node_type,
        document_id=document_id,
        document_title=document_title,
        chunk_ids=chunk_ids,
        detail=detail,
    )


def resolve_section_provenance(
    con: Any, section_id: str,
) -> list[ProvenanceChain]:
    """Resolve provenance for every block in a section (ordered). Handy
    for surfacing a section's dangling/user-originated blocks at a glance."""
    from .outline_block import list_section_blocks
    return [resolve_provenance(con, b) for b in list_section_blocks(con, section_id)]
