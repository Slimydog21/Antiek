"""Block repository search (specs/write/ SPR-03 M2).

Search the block repository — insight/question/claim graph nodes — by
text, optional embedding similarity, source document, and folder
membership, with a **documented, deterministic** ranking. Determinism is
a hard requirement: the same query + corpus always returns the same
ranked list, so the drag-into-outline experience is reproducible and the
tests are mechanical.

Ranking (documented):

    score = text_score + EMBED_WEIGHT * embedding_cosine

- ``text_score`` ∈ [0, 1]: token-overlap fraction of the query against the
  node label (+ a small substring bonus). Pure-Python so it is identical
  across DuckDB versions.
- ``embedding_cosine`` ∈ [0, 1]: only when the caller passes a
  ``query_embedding`` (generation of the query vector belongs to
  ``processing/embedding``, not here) and the node carries an embedding.
- Ties break by ``node_id`` (lexicographic) so the order is total and
  stable.

Filters (``folder_id``, ``source_document_id``) are applied before
ranking. ``folder_id`` reuses the SPR-03 ``write_folder_members`` view —
folders are edges over nodes, so filtering by folder never duplicates a
node.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

EMBED_WEIGHT = 1.0  # embedding contributes up to +1.0 atop text_score


@dataclass(frozen=True)
class BlockHit:
    node_id: str
    label: str
    node_type: str
    source_tier: Optional[int]
    document_id: Optional[str]
    document_title: Optional[str]
    score: float


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"\W+", s.lower()) if t]


def _text_score(query: str, label: str) -> float:
    """Token-overlap fraction + substring bonus, in [0, 1]. Deterministic."""
    q = _tokens(query)
    if not q:
        return 0.0
    label_tokens = set(_tokens(label))
    overlap = sum(1 for t in q if t in label_tokens) / len(q)
    bonus = 0.2 if query.strip().lower() in (label or "").lower() else 0.0
    return min(1.0, overlap + bonus)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _node_chunk_id(metadata_text: Optional[str]) -> Optional[str]:
    if not metadata_text:
        return None
    try:
        meta = json.loads(metadata_text)
    except (json.JSONDecodeError, TypeError):
        return None
    cid = meta.get("chunk_id") if isinstance(meta, dict) else None
    return str(cid) if cid else None


def search_blocks(
    con: Any,
    *,
    query: str = "",
    folder_id: Optional[str] = None,
    source_document_id: Optional[str] = None,
    query_embedding: Optional[Sequence[float]] = None,
    node_types: Optional[Sequence[str]] = None,
    limit: int = 20,
) -> list[BlockHit]:
    """Search the repository. Returns up to ``limit`` ranked ``BlockHit``s.

    ``con`` is any duckdb connection (read-only is fine). Ranking is
    documented above and deterministic."""
    # Base candidate set, narrowed by folder membership if requested.
    if folder_id is not None:
        base_sql = (
            "SELECT n.node_id, n.canonical_label, n.node_type, n.metadata, n.embedding "
            "FROM nodes n JOIN write_folder_members m ON n.node_id = m.node_id "
            "WHERE m.folder_id = ?"
        )
        params: list[Any] = [folder_id]
    else:
        base_sql = (
            "SELECT n.node_id, n.canonical_label, n.node_type, n.metadata, n.embedding "
            "FROM nodes n WHERE 1=1"
        )
        params = []
    if node_types:
        placeholders = ",".join("?" for _ in node_types)
        base_sql += f" AND n.node_type IN ({placeholders})"
        params.extend(node_types)

    rows = con.execute(base_sql, params).fetchall()

    hits: list[BlockHit] = []
    for node_id, label, node_type, metadata, embedding in rows:
        # Resolve source document (for filter + display) via the node's
        # distillation chunk.
        document_id = document_title = source_tier = None
        chunk_id = _node_chunk_id(metadata)
        if chunk_id is not None:
            doc_row = con.execute(
                "SELECT c.document_id, d.title, d.source_tier FROM chunks c "
                "LEFT JOIN documents d ON c.document_id = d.document_id "
                "WHERE c.chunk_id = ? LIMIT 1",
                [chunk_id],
            ).fetchone()
            if doc_row is not None:
                document_id, document_title, source_tier = doc_row

        if source_document_id is not None and document_id != source_document_id:
            continue

        score = _text_score(query, label or "")
        if query_embedding is not None and embedding is not None:
            score += EMBED_WEIGHT * _cosine(query_embedding, list(embedding))

        # When there's no query and no embedding, surface everything
        # (score 0) so an empty-query browse still lists the repository.
        hits.append(BlockHit(
            node_id=node_id, label=label or "(no label)", node_type=node_type,
            source_tier=source_tier, document_id=document_id,
            document_title=document_title, score=round(score, 6),
        ))

    # Total, stable order: score desc, then node_id asc.
    hits.sort(key=lambda h: (-h.score, h.node_id))
    return hits[:limit]
