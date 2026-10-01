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

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from substrate.write.folders import _folders_schema_exists

EMBED_WEIGHT = 1.0  # embedding contributes up to +1.0 atop text_score


@dataclass(frozen=True)
class BlockHit:
    node_id: str
    label: str
    node_type: str
    source_tier: int | None
    document_id: str | None
    document_title: str | None
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
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search_blocks(
    con: Any,
    *,
    query: str = "",
    folder_id: str | None = None,
    source_document_id: str | None = None,
    query_embedding: Sequence[float] | None = None,
    node_types: Sequence[str] | None = None,
    limit: int = 20,
    policy_tag: str = "attribution_eligible",
    owner_user_id: str | None = None,
) -> list[BlockHit]:
    """Search the repository. Returns up to ``limit`` ranked ``BlockHit``s.

    ``con`` is any duckdb connection (read-only is fine). Ranking is
    documented above and deterministic."""
    from substrate.graph.retrieval_gate import non_privileged_node_provenance_clause
    from substrate.rights.document_visibility import document_discoverability_sql

    if folder_id is not None and not _folders_schema_exists(con):
        return []
    node_sql, node_params = non_privileged_node_provenance_clause(
        node_alias="n", policy_tag=policy_tag, owner_user_id=owner_user_id,
    )
    display_sql, display_params = document_discoverability_sql(
        owner_user_id=owner_user_id, document_alias="d",
    )
    meta = "TRY_CAST(n.metadata AS JSON)"
    chunk_id = (
        f"CASE WHEN json_type(json_extract({meta}, '$.chunk_id')) = 'VARCHAR' "
        f"THEN json_extract_string({meta}, '$.chunk_id') END"
    )
    direct_document_id = (
        f"CASE WHEN json_type(json_extract({meta}, '$.source_document_id')) = 'VARCHAR' "
        f"THEN json_extract_string({meta}, '$.source_document_id') END"
    )
    base_sql = (
        "SELECT n.node_id, n.canonical_label, n.node_type, n.embedding, "
        "d.document_id, d.title, d.source_tier FROM nodes n "
        f"LEFT JOIN chunks c ON c.chunk_id = ({chunk_id}) "
        "LEFT JOIN documents chunk_document ON chunk_document.document_id = c.document_id "
        "LEFT JOIN documents d ON d.document_id = "
        f"COALESCE(chunk_document.document_id, ({direct_document_id})) AND {display_sql} "
    )
    if folder_id is not None:
        base_sql += "JOIN write_folder_members m ON n.node_id = m.node_id "
    base_sql += "WHERE 1=1"
    params: list[Any] = list(display_params)
    if folder_id is not None:
        base_sql += " AND m.folder_id = ?"
        params.append(folder_id)
    if node_types:
        placeholders = ",".join("?" for _ in node_types)
        base_sql += f" AND n.node_type IN ({placeholders})"
        params.extend(node_types)
    base_sql += node_sql
    params.extend(node_params)
    if source_document_id is not None:
        base_sql += " AND d.document_id = ?"
        params.append(source_document_id)

    rows = con.execute(base_sql, params).fetchall()

    hits: list[BlockHit] = []
    for node_id, label, node_type, embedding, document_id, document_title, source_tier in rows:
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
