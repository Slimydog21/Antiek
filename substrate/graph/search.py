"""Vector search over the knowledge graph.

Ported from Researchmaxx ``search.py`` (231 LOC source → ~190 LOC here
after dropping the as-of temporal filter and inlining the embedding
model load behind an injectable Protocol).

What's here:

- ``cosine_similarity_sql`` — produces the DuckDB expression that
  computes cosine similarity against a chunk's embedding column. Pure
  SQL fragment, no dependencies.
- ``EmbeddingModel`` Protocol — minimal contract: ``encode(text) ->
  list[float]``. Tests inject a deterministic stub; production uses
  ``SentenceTransformerEmbedding`` which wraps ``sentence-transformers``.
- ``search(con, query, *, model, top_k, ...)`` — top-k chunks by
  cosine similarity, optionally with associated edges and connected
  nodes, optionally tier-filtered.
- ``search_nodes_by_label(con, query)`` — companion ILIKE search for
  node labels (the Researchmaxx ``node_matches`` array).

Deferred from the Researchmaxx version:

- ``as_of`` temporal filter — depends on ``graph_at_time`` which
  hasn't migrated. Add as an optional argument when temporal querying
  comes online.
- Embedding model auto-load from ``EMBEDDING_MODEL`` env var — too
  much hidden behavior; force callers to pass the model explicitly.
  ``SentenceTransformerEmbedding`` factory provided as a convenience.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional, Protocol, Sequence

try:
    from ...runtime.db_lock import connect_read
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# EmbeddingModel — injectable for tests
# ---------------------------------------------------------------------------


class EmbeddingModel(Protocol):
    """Minimal contract: encode a single string to a fixed-length
    float vector. Tests pass a deterministic stub; production wraps
    a sentence-transformers ``SentenceTransformer`` (see
    ``SentenceTransformerEmbedding`` below)."""

    dimension: int

    def encode(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedding:
    """Default production EmbeddingModel — wraps sentence-transformers.

    Lazy-imports the dependency so the rest of substrate/graph/ works
    in environments where the model isn't installed (tests using a
    stub, dev environments doing schema-only work)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers not installed. Run "
                "`pip install sentence-transformers` or pass a custom "
                "EmbeddingModel."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension() or 384)

    def encode(self, text: str) -> list[float]:
        vec = self._model.encode([text])[0]
        return [float(x) for x in vec]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def cosine_similarity_sql(
    embedding_col: str,
    query_vec: Sequence[float],
    dim: int,
) -> str:
    """Generate the DuckDB cosine-similarity expression for
    ``embedding_col`` against ``query_vec``.

    Inlines the query vector into the SQL string as a FLOAT[dim] cast,
    matching the Researchmaxx approach. This is safe because
    ``query_vec`` is always a numeric list under our control (not user
    input), and DuckDB's array casting validates the shape."""
    vec_str = "[" + ",".join(repr(float(x)) for x in query_vec) + "]"
    return (
        f"(list_dot_product({embedding_col}, {vec_str}::FLOAT[{dim}]) / "
        f" (sqrt(list_dot_product({embedding_col}, {embedding_col})) * "
        f"  sqrt(list_dot_product({vec_str}::FLOAT[{dim}], {vec_str}::FLOAT[{dim}]))))"
    )


# ---------------------------------------------------------------------------
# Public search API
# ---------------------------------------------------------------------------


def search(
    con: Any,
    query: str,
    *,
    model: EmbeddingModel,
    top_k: int = 5,
    source_tier_max: Optional[int] = None,
    document_id: Optional[str] = None,
    with_edges: bool = False,
) -> dict:
    """Vector search over ``chunks.embedding``. Returns top-``k``
    chunks ordered by cosine similarity desc.

    Args:
        con: A DuckDB connection (read-only is fine).
        query: The natural-language query.
        model: An ``EmbeddingModel`` — production passes
            ``SentenceTransformerEmbedding()``; tests pass a stub.
        top_k: Max results.
        source_tier_max: Filter to chunks whose document has source_tier
            ``<=`` this value (lower = higher trust per
            ``substrate.constants.TIER_HIGHEST``). Use 2 to restrict to
            primary + peer-reviewed; None for no tier filter.
        document_id: Scope to chunks belonging to a single document.
            Used by the grounder to check claims against the document
            the user was wrestling, not the whole corpus.
        with_edges: When True, attach the edges sourced from each
            returned chunk plus the nodes those edges connect.

    Returns:
        ``{"query": ..., "top_k": ..., "results": [...], "node_matches": []}``
        — same shape as the Researchmaxx version so downstream
        consumers don't need adapter code.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    query_vec = list(model.encode(query))
    dim = model.dimension
    if len(query_vec) != dim:
        raise ValueError(
            f"EmbeddingModel.encode returned {len(query_vec)} dims; "
            f"model.dimension is {dim}. Match them."
        )

    sim_expr = cosine_similarity_sql("c.embedding", query_vec, dim)

    sql = f"""
        SELECT
            c.chunk_id, c.section_path, c.text, c.token_count,
            d.title, d.source_tier, d.document_type,
            {sim_expr} AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.embedding IS NOT NULL
    """
    params: list[Any] = []
    if document_id is not None:
        sql += " AND c.document_id = ?"
        params.append(document_id)
    if source_tier_max is not None:
        sql += " AND d.source_tier <= ?"
        params.append(int(source_tier_max))
    sql += " ORDER BY similarity DESC LIMIT ?"
    params.append(int(top_k))

    rows = con.execute(sql, params).fetchall()

    results: list[dict] = []
    for chunk_id, section, text, tokens, title, tier, dtype, sim in rows:
        item: dict[str, Any] = {
            "chunk_id": chunk_id,
            "section_path": section,
            "chunk_text": text[:500] + ("…" if text and len(text) > 500 else ""),
            "token_count": tokens,
            "document_title": title,
            "source_tier": tier,
            "document_type": dtype,
            "similarity": round(float(sim), 4),
        }
        if with_edges:
            item["edges"], item["nodes"] = _fetch_edges_and_nodes(con, chunk_id)
        results.append(item)

    return {
        "query": query,
        "top_k": top_k,
        "results": results,
        "node_matches": search_nodes_by_label(con, query, limit=10),
    }


def _fetch_edges_and_nodes(con: Any, chunk_id: str) -> tuple[list[dict], list[dict]]:
    """Helper for ``with_edges=True``: returns the edges sourced from
    a chunk and the nodes those edges connect."""
    edge_rows = con.execute(
        """
        SELECT e.edge_id, e.source_node_id, e.target_node_id, e.relation,
               e.extraction_confidence, e.source_tier,
               n1.canonical_label AS source_label,
               n2.canonical_label AS target_label
        FROM edges e
        JOIN nodes n1 ON e.source_node_id = n1.node_id
        JOIN nodes n2 ON e.target_node_id = n2.node_id
        WHERE e.chunk_id = ?
        LIMIT 20
        """,
        [chunk_id],
    ).fetchall()

    edges = [
        {
            "edge_id": e[0],
            "source": {"id": e[1], "label": e[6]},
            "target": {"id": e[2], "label": e[7]},
            "relation": e[3],
            "confidence": round(float(e[4]), 3),
            "source_tier": e[5],
        }
        for e in edge_rows
    ]

    node_ids = {e[1] for e in edge_rows} | {e[2] for e in edge_rows}
    nodes: list[dict] = []
    if node_ids:
        placeholders = ",".join(["?"] * len(node_ids))
        node_rows = con.execute(
            f"""
            SELECT node_id, node_type, canonical_label
            FROM nodes
            WHERE node_id IN ({placeholders})
            LIMIT 30
            """,
            list(node_ids),
        ).fetchall()
        nodes = [
            {"node_id": n[0], "node_type": n[1], "label": n[2]}
            for n in node_rows
        ]
    return edges, nodes


def search_nodes_by_label(con: Any, query: str, limit: int = 10) -> list[dict]:
    """ILIKE search over ``nodes.canonical_label``. Used as a companion
    to vector search for label-direct hits — "PsiQuantum" as a query
    should find the PsiQuantum node even if no chunk embedding is
    closer than another."""
    rows = con.execute(
        """
        SELECT node_id, node_type, canonical_label
        FROM nodes
        WHERE canonical_label ILIKE ?
        LIMIT ?
        """,
        [f"%{query}%", int(limit)],
    ).fetchall()
    return [
        {"node_id": r[0], "node_type": r[1], "label": r[2]}
        for r in rows
    ]


def open_read(db_path: str) -> Any:
    """Convenience: open a read-only connection. Same as
    ``runtime.db_lock.connect_read`` — exposed here so search.py is
    the one-stop import for read-side graph queries."""
    return connect_read(db_path)
