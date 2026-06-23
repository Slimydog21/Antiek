"""DRW SPR-04 M1 — scoped insight/question retrieval for the context pack.

Retrieves the project's ``insight`` / ``question`` nodes (SPR-01) ranked by
similarity to the current task, reusing the SPR-01 embeddings and the
graph's existing ``cosine_similarity_sql`` helper. This is the "what does
the project already know" feed that the maximum-context pack injects so the
worker never times out on lost context.

Scope honesty (rigor #1): the ``nodes`` table carries no ``investigation_id``
column — investigation scope lives on ``edges`` and on the
``GRAPH_NODE_INSERTED`` event envelope, not on the node row. So v1 scopes at
the **project (whole-graph) level**, which is exactly right for the
single-operator phase (one operator = one project until gate G7 / Sprint 22).
A caller that has pre-scoped a node set (e.g. by walking ``edges`` for an
investigation) can pass ``restrict_node_ids`` to narrow it.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

try:
    from ..graph.search import cosine_similarity_sql
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))
    from graph.search import cosine_similarity_sql  # type: ignore[no-redef]


@dataclass(frozen=True)
class RetrievedNote:
    node_id: str
    node_type: str            # "insight" | "question"
    text: str                 # canonical_label (the living current text)
    similarity: float         # cosine vs task; 0.0 for embedding-less fallback
    confidence: str           # from metadata; "unknown" if absent
    created_at: Any           # for recency ranking
    has_embedding: bool


def retrieve_project_notes(
    con: Any,
    *,
    task_text: str,
    embedding_provider: Any,
    node_types: Sequence[str] = ("insight", "question"),
    limit: int = 500,
    restrict_node_ids: Sequence[str] | None = None,
) -> list[RetrievedNote]:
    """Return project notes ranked by similarity to ``task_text``.

    Embedding-less nodes (should not exist post-SPR-01, but handled) are
    appended after the embedded matches with ``similarity=0.0`` so they are
    retrievable by recency rather than silently dropped."""
    types_csv = ", ".join("?" for _ in node_types)
    type_params = list(node_types)
    id_filter = ""
    id_params: list[Any] = []
    if restrict_node_ids is not None:
        if not restrict_node_ids:
            return []
        id_filter = f" AND node_id IN ({', '.join('?' for _ in restrict_node_ids)})"
        id_params = list(restrict_node_ids)

    query_vec = list(embedding_provider.encode(task_text))
    dim = getattr(embedding_provider, "dimension", len(query_vec))
    sim_expr = cosine_similarity_sql("embedding", query_vec, dim)

    rows = con.execute(
        f"SELECT node_id, node_type, canonical_label, metadata, created_at, "
        f"{sim_expr} AS similarity "
        f"FROM nodes "
        f"WHERE node_type IN ({types_csv}) AND embedding IS NOT NULL{id_filter} "
        f"ORDER BY similarity DESC LIMIT ?",
        type_params + id_params + [int(limit)],
    ).fetchall()
    out = [_row_to_note(r, has_embedding=True) for r in rows]

    # Embedding-less fallback (graceful, should be empty post-SPR-01).
    if len(out) < limit:
        fb = con.execute(
            f"SELECT node_id, node_type, canonical_label, metadata, created_at, "
            f"0.0 AS similarity FROM nodes "
            f"WHERE node_type IN ({types_csv}) AND embedding IS NULL{id_filter} "
            f"ORDER BY created_at DESC LIMIT ?",
            type_params + id_params + [int(limit - len(out))],
        ).fetchall()
        out.extend(_row_to_note(r, has_embedding=False) for r in fb)
    return out


def _row_to_note(row: Any, *, has_embedding: bool) -> RetrievedNote:
    node_id, node_type, label, metadata, created_at, similarity = row
    confidence = "unknown"
    if metadata:
        try:
            confidence = json.loads(metadata).get("confidence", "unknown")
        except (TypeError, ValueError):
            pass
    return RetrievedNote(
        node_id=node_id, node_type=node_type, text=label,
        similarity=float(similarity or 0.0), confidence=confidence,
        created_at=created_at, has_embedding=has_embedding,
    )
