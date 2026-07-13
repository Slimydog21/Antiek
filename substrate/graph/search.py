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
from collections.abc import Sequence
from typing import Any, Protocol

from substrate.graph import retrieval_gate as _retrieval_gate
from substrate.graph.embedding_meta import assert_embedding_compatible
from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause

# Back-compat re-exports (tests / attribution import these from search).
PRIVILEGED_POLICY_TAGS = _retrieval_gate.PRIVILEGED_POLICY_TAGS
PERSONAL_ONLY_CONTENT_CLASSES = _retrieval_gate.PERSONAL_ONLY_CONTENT_CLASSES
RESTRICTED_CONTENT_CLASSES = _retrieval_gate.RESTRICTED_CONTENT_CLASSES
_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES = (
    _retrieval_gate._NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES
)

try:
    from ...runtime.db_lock import connect_read  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read


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
            from sentence_transformers import SentenceTransformer
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
# (Gate constants + helper are imported and re-exported at the top of this
# module — see the back-compat re-export block after the imports.)


def search(
    con: Any,
    query: str,
    *,
    model: EmbeddingModel,
    top_k: int = 5,
    source_tier_max: int | None = None,
    document_id: str | None = None,
    document_ids: Sequence[str] | None = None,
    with_edges: bool = False,
    policy_tag: str = "attribution_eligible",
    owner_user_id: str | None = None,
) -> dict[str, Any]:
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
        document_ids: Scope to chunks belonging to ANY document in this
            set (a single ``document_id IN (?,?,..)`` clause). This is the
            Read SPR-08 meta-reading "owned corpus" scope: synthesis over
            a bounded set of owned books ranks all their chunks by global
            similarity in ONE gated query, rather than iterating per-doc
            and re-merging (which would re-rank after the fact and risk
            applying the §9.0 gate inconsistently). When both
            ``document_id`` and ``document_ids`` are given, the single id
            is appended to the set (the union of the two scopes). An empty
            set is treated as "no documents in scope" → no results (an
            honest empty, never the whole corpus).
        with_edges: When True, attach the edges sourced from each
            returned chunk plus the nodes those edges connect.
        policy_tag: Retrieval-time gate per master-spec §9.0 + Personal-Reading
            Lane SPR-01. When ``policy_tag`` is in PRIVILEGED_POLICY_TAGS
            ({"private_research", "operator_only"}), BOTH restricted content
            (content_class='restricted_pending_opt_in') AND owner-only content
            (content_class='personal_reading') are included — this is the owner's
            full-read path. For ALL other policy_tag values — including the
            default 'attribution_eligible' (Sprint 18+ ad-attribution path) —
            both are excluded. The Sprint 18 legal gate (master §15.9) is
            non-negotiable: payouts on an ungated graph are explicitly forbidden
            by §16.2; and personal_reading (the owner's private third-party
            reading) must never reach a monetized / public read.

    Returns:
        ``{"query": ..., "top_k": ..., "results": [...], "node_matches": []}``
        — same shape as the Researchmaxx version so downstream
        consumers don't need adapter code.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    # Union the single-id scope into the set scope (a caller may pass
    # either or both). An EXPLICITLY-EMPTY set means "no documents in
    # scope" — return nothing rather than silently widening to the whole
    # corpus (the meta-reading owned-corpus scope must never leak past its
    # bound). `document_ids is None` ⇒ no set filter at all.
    scoped_ids: list[str] | None = None
    if document_ids is not None:
        scoped_ids = list(dict.fromkeys(document_ids))  # de-dup, keep order
        if document_id is not None and document_id not in scoped_ids:
            scoped_ids.append(document_id)
        if not scoped_ids:
            return {
                "query": query,
                "top_k": top_k,
                "results": [],
                "node_matches": [],
            }

    query_vec = list(model.encode(query))
    dim = model.dimension
    if len(query_vec) != dim:
        raise ValueError(
            f"EmbeddingModel.encode returned {len(query_vec)} dims; "
            f"model.dimension is {dim}. Match them."
        )
    assert_embedding_compatible(con, model)

    sim_expr = cosine_similarity_sql("c.embedding", query_vec, dim)

    sql = f"""
        SELECT
            c.chunk_id, c.section_path, c.text, c.token_count,
            c.document_id, c.chunk_index,
            d.title, d.source_tier, d.document_type,
            {sim_expr} AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.embedding IS NOT NULL
    """
    params: list[Any] = []
    if scoped_ids is not None:
        placeholders = ",".join("?" for _ in scoped_ids)
        sql += f" AND c.document_id IN ({placeholders})"
        params.extend(scoped_ids)
    elif document_id is not None:
        sql += " AND c.document_id = ?"
        params.append(document_id)
    if source_tier_max is not None:
        sql += " AND d.source_tier <= ?"
        params.append(int(source_tier_max))
    # Sprint 18 retrieval-time gate (master-spec §9.0) + Personal-Reading Lane
    # SPR-01 — emitted only via retrieval_gate.non_privileged_chunk_sql_clause.
    gate_sql, gate_params = non_privileged_chunk_sql_clause(
        table_alias="d",
        policy_tag=policy_tag,
        owner_user_id=owner_user_id or "__operator__",
    )
    sql += gate_sql
    params.extend(gate_params)
    sql += " ORDER BY similarity DESC LIMIT ?"
    params.append(int(top_k))

    rows = con.execute(sql, params).fetchall()

    results: list[dict[str, Any]] = []
    for (
        chunk_id, section, text, tokens, doc_id, chunk_index,
        title, tier, dtype, sim,
    ) in rows:
        item: dict[str, Any] = {
            "chunk_id": chunk_id,
            "section_path": section,
            "chunk_text": text[:500] + ("…" if text and len(text) > 500 else ""),
            "token_count": tokens,
            # document_id + chunk_index let a citation jump back to the
            # source: the Read surface maps section_path ("Page N") → a
            # reader page (page_index_from_section_path), and falls back to
            # the document when no page resolves (honest, never invented).
            "document_id": doc_id,
            "chunk_index": chunk_index,
            "document_title": title,
            "source_tier": tier,
            "document_type": dtype,
            "similarity": round(float(sim), 4),
        }
        if with_edges:
            item["edges"], item["nodes"] = _fetch_edges_and_nodes(
                con, chunk_id, policy_tag=policy_tag, owner_user_id=owner_user_id,
            )
        results.append(item)

    return {
        "query": query,
        "top_k": top_k,
        "results": results,
        "node_matches": search_nodes_by_label(
            con, query, limit=10, policy_tag=policy_tag, owner_user_id=owner_user_id,
        ),
    }


def _fetch_edges_and_nodes(
    con: Any, chunk_id: str, *, policy_tag: str = "attribution_eligible",
    owner_user_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Helper for ``with_edges=True``: returns the edges sourced from
    a chunk and the nodes those edges connect.

    SPR-01/§9.0 (the fix for the residual node-label leak, #206): the edge
    endpoints' ``canonical_label`` is a §9.0 serve surface — the same surface
    ``search_nodes_by_label`` gates. A public-provenance edge can link to a
    node whose provenance is ``personal_reading``/restricted (semantic dedup
    lets a public insight attach to a surviving personal node), so serving
    that endpoint label on a non-privileged path leaks the personal headline.
    Both endpoint nodes (n1, n2) are gated with the canonical
    ``non_privileged_node_provenance_clause`` (most-restrictive-wins +
    fail-closed on unresolved provenance — identical contract to
    ``search_nodes_by_label``); an edge is withheld if EITHER endpoint is
    gated, since serving either label would leak. ``policy_tag`` defaults to
    the non-privileged value (fail-safe): a caller that forgets it gets the
    gated result, never the leak."""
    g1_sql, g1_params = _retrieval_gate.non_privileged_node_provenance_clause(
        node_alias="n1", policy_tag=policy_tag,
    )
    g2_sql, g2_params = _retrieval_gate.non_privileged_node_provenance_clause(
        node_alias="n2", policy_tag=policy_tag,
    )
    o1_sql, o1_params = _retrieval_gate.node_owner_sql_clause(
        node_alias="n1", owner_user_id=owner_user_id,
    )
    o2_sql, o2_params = _retrieval_gate.node_owner_sql_clause(
        node_alias="n2", owner_user_id=owner_user_id,
    )
    edge_rows = con.execute(
        f"""
        SELECT e.edge_id, e.source_node_id, e.target_node_id, e.relation,
               e.extraction_confidence, e.source_tier,
               n1.canonical_label AS source_label,
               n2.canonical_label AS target_label
        FROM edges e
        JOIN nodes n1 ON e.source_node_id = n1.node_id
        JOIN nodes n2 ON e.target_node_id = n2.node_id
        WHERE e.chunk_id = ?{g1_sql}{g2_sql}{o1_sql}{o2_sql}
        LIMIT 20
        """,
        [chunk_id, *g1_params, *g2_params, *o1_params, *o2_params],
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
    nodes: list[dict[str, Any]] = []
    if node_ids:
        placeholders = ",".join(["?"] * len(node_ids))
        gn_sql, gn_params = _retrieval_gate.non_privileged_node_provenance_clause(
            node_alias="n", policy_tag=policy_tag,
        )
        own_sql, own_params = _retrieval_gate.node_owner_sql_clause(
            node_alias="n", owner_user_id=owner_user_id,
        )
        node_rows = con.execute(
            f"""
            SELECT n.node_id, n.node_type, n.canonical_label
            FROM nodes n
            WHERE n.node_id IN ({placeholders}){gn_sql}{own_sql}
            LIMIT 30
            """,
            [*node_ids, *gn_params, *own_params],
        ).fetchall()
        nodes = [
            {"node_id": n[0], "node_type": n[1], "label": n[2]}
            for n in node_rows
        ]
    return edges, nodes


def search_nodes_by_label(
    con: Any, query: str, limit: int = 10,
    *,
    policy_tag: str = "attribution_eligible",
    owner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """ILIKE search over ``nodes.canonical_label``, §9.0-gated (SPR-01).

    Companion to vector search for label-direct hits — "PsiQuantum" as a query
    should find the PsiQuantum node even if no chunk embedding is closer than
    another. This result is returned as ``node_matches`` on the serve payload
    (``retrieval_substrate.py`` / ``search()``) and read by the LLM, so it is a
    §9.0 serve surface: a ``personal_reading`` node label must NOT reach a
    non-owner.

    ``policy_tag`` **defaults to the non-privileged (safe) value**
    ``"attribution_eligible"`` on purpose: a caller that forgets the argument
    gets the *gated* result, never the leak (fail-safe, not fail-open — the
    §9.0 legal invariant makes an accidental leak unacceptable). Only tags in
    ``retrieval_gate.PRIVILEGED_POLICY_TAGS`` (owner ``private_research`` /
    ``operator_only``) return every labeled node.

    The gate — the exclusion set and privileged-tag logic, and the
    node→document provenance join with most-restrictive-wins + fail-closed on
    unresolved provenance — lives entirely in
    ``retrieval_gate.non_privileged_node_provenance_clause`` (the single
    canonical source, reused not reinvented)."""
    gate_sql, gate_params = _retrieval_gate.non_privileged_node_provenance_clause(
        node_alias="n",
        policy_tag=policy_tag,
    )
    owner_sql, owner_params = _retrieval_gate.node_owner_sql_clause(
        node_alias="n", owner_user_id=owner_user_id,
    )
    rows = con.execute(
        f"""
        SELECT n.node_id, n.node_type, n.canonical_label
        FROM nodes n
        WHERE n.canonical_label ILIKE ?{gate_sql}{owner_sql}
        LIMIT ?
        """,
        [f"%{query}%", *gate_params, *owner_params, int(limit)],
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
