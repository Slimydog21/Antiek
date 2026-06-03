"""Block clustering (specs/write/ SPR-01 M4).

Group related lego blocks so a writer can assemble a section from like
material. Two deterministic signals, applied in order:

1. **Shared source document** — blocks distilled from the same document
   cluster together (``doc:<document_id>``). This is the strongest,
   cheapest signal and needs no embeddings.
2. **Node-embedding similarity** — among the remaining node-backed blocks
   that carry an embedding, a single-pass greedy agglomeration groups
   blocks whose node embeddings exceed a cosine threshold
   (``emb:<lexicographically-smallest block id>``). Reuses the embeddings
   already on ``nodes`` — no new embedding work.

Everything else (user-originated blocks, node-backed blocks with neither
a shared document nor an embedding) lands as a singleton
(``solo:<block id>``). Determinism is a hard requirement: the same blocks
+ threshold always produce the same clusters, so a maintainer can reason
about the grouping and tests are mechanical.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

from .outline_block import OutlineBlock, list_section_blocks


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _node_document(con: Any, node_id: str) -> str | None:
    """Resolve a node's source document id via its distillation chunk."""
    row = con.execute(
        "SELECT metadata FROM nodes WHERE node_id = ?", [node_id]
    ).fetchone()
    if row is None or not row[0]:
        return None
    try:
        meta = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None
    chunk_id = meta.get("chunk_id") if isinstance(meta, dict) else None
    if not chunk_id:
        return None
    doc_row = con.execute(
        "SELECT document_id FROM chunks WHERE chunk_id = ?", [chunk_id]
    ).fetchone()
    return doc_row[0] if doc_row else None


def _node_embedding(con: Any, node_id: str) -> list[float] | None:
    row = con.execute(
        "SELECT embedding FROM nodes WHERE node_id = ?", [node_id]
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return list(row[0])


def cluster_blocks(
    con: Any,
    blocks: str | Sequence[OutlineBlock],
    *,
    threshold: float = 0.82,
) -> dict[str, list[OutlineBlock]]:
    """Cluster blocks deterministically. ``blocks`` is either a
    ``section_id`` (cluster that section's blocks) or an explicit list of
    ``OutlineBlock``. Returns ``{cluster_id: [blocks...]}`` with clusters
    ordered by id and members ordered by block id.

    ``con`` is any duckdb connection (read-only is fine)."""
    if isinstance(blocks, str):
        blocks = list_section_blocks(con, blocks)
    # Deterministic input order.
    items = sorted(blocks, key=lambda b: b.outline_block_id)

    clusters: dict[str, list[OutlineBlock]] = {}
    remaining: list[OutlineBlock] = []

    # Pass 1 — shared source document.
    by_doc: dict[str, list[OutlineBlock]] = {}
    for b in items:
        doc_id = _node_document(con, b.node_id) if b.node_id else None
        if doc_id:
            by_doc.setdefault(doc_id, []).append(b)
        else:
            remaining.append(b)
    for doc_id, group in by_doc.items():
        if len(group) >= 2:
            clusters[f"doc:{doc_id}"] = group
        else:
            remaining.extend(group)  # a lone doc block falls through

    # Pass 2 — node-embedding similarity (greedy single-linkage).
    embedded: list[tuple[OutlineBlock, list[float]]] = []
    leftovers: list[OutlineBlock] = []
    for b in sorted(remaining, key=lambda b: b.outline_block_id):
        emb = _node_embedding(con, b.node_id) if b.node_id else None
        if emb:
            embedded.append((b, emb))
        else:
            leftovers.append(b)

    assigned: set[str] = set()
    for i, (b, emb) in enumerate(embedded):
        if b.outline_block_id in assigned:
            continue
        group = [b]
        assigned.add(b.outline_block_id)
        for ob, oemb in embedded[i + 1:]:
            if ob.outline_block_id in assigned:
                continue
            if _cosine(emb, oemb) >= threshold:
                group.append(ob)
                assigned.add(ob.outline_block_id)
        if len(group) >= 2:
            clusters[f"emb:{group[0].outline_block_id}"] = group
        else:
            leftovers.append(b)

    # Pass 3 — singletons.
    for b in sorted(leftovers, key=lambda b: b.outline_block_id):
        clusters[f"solo:{b.outline_block_id}"] = [b]

    # Return with deterministic cluster ordering + member ordering.
    return {
        cid: sorted(members, key=lambda b: b.outline_block_id)
        for cid, members in sorted(clusters.items())
    }
