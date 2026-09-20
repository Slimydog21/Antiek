"""Own Your Mind P0 — provenance explain routes (D1, the trust wedge).

Read-only endpoints that render the full grounding chain for a claim,
a synthesis, or a document, straight from the graph store:

- ``GET /claims/{claim_node_id}/explain`` — the claim node, its supporting
  edges (each carrying the chunk + document evidence it was extracted
  from), the chunk excerpts, the documents, and any chunk tier overrides
  (who retiered a chunk and why).
- ``GET /syntheses/{synthesis_id}/explain`` — the same chain via the
  ``synthesis_substrate_manifest`` pins (entity_kind document / chunk /
  node / edge), so "what grounded this synthesis" is exactly what the
  archive pinned, nothing more.
- ``GET /docs/{document_id}/explain`` — reverse provenance: document →
  chunks → the edges (and their source nodes) that cite those chunks.

Read APIs: every query runs through the sanctioned graph read path —
``runtime.db_lock.connect_read`` over ``substrate.graph.default_db_path``
(the same path ``services/html_projection/adapters/synthesis.py`` uses).
There is no row-level read helper in ``substrate/graph/`` for these five
tables (the helpers there are search/traverse/ops), so the reads are
parameterized SELECTs over the read connection — the established adapter
pattern, never hand-rolled SQL outside the sanctioned connection.

Zero mutation endpoints. Text excerpts are truncated to 500 chars
(``_EXCERPT_MAX_CHARS``, matching ``substrate.constants.SERVE_SNIPPET_MAX_CHARS``).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException

_EXCERPT_MAX_CHARS = 500

explain_router = APIRouter(tags=["explain"])


def _resolve_db_path() -> str | None:
    """Resolve the graph DB path WITHOUT creating or mutating it.

    These endpoints are strictly read-only (P0 principle): a GET must
    never initialize a store that does not exist (that would be a write
    side effect on a read surface, and ``ensure_initialized`` needs a
    write connection). A missing store is an honest 404, not a creation
    event. Existing adapters that DO initialize (e.g. the synthesis
    artifact exporter) keep their behavior; the explain surface does not
    inherit it."""
    from substrate.graph import default_db_path

    path = os.path.expanduser(default_db_path())
    if not os.path.exists(path):
        return None
    return path


def _iso(value: Any) -> str | None:
    """Serialize a DuckDB timestamp / None to an ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return str(value.isoformat())
    except AttributeError:
        return str(value)


def _excerpt(text: str | None) -> str | None:
    if text is None:
        return None
    return text[:_EXCERPT_MAX_CHARS]


# ---------------------------------------------------------------------------
# Row resolvers (shared by all three endpoints)
# ---------------------------------------------------------------------------


def _load_node(con: Any, node_id: str) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT node_id, canonical_label, node_type, graph_scope, created_at "
        "FROM nodes WHERE node_id = ?",
        [node_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "node_id": row[0],
        "canonical_label": row[1],
        "node_type": row[2],
        "graph_scope": row[3],
        "created_at": _iso(row[4]),
    }


def _load_edges_from(con: Any, source_node_id: str) -> list[dict[str, Any]]:
    """Supporting edges sourced from a node: each edge's evidence pointers
    (chunk_id + source_document_id) are the grounding chain link."""
    rows = con.execute(
        "SELECT edge_id, source_node_id, target_node_id, relation, chunk_id, "
        "source_document_id, source_tier, extraction_confidence, graph_scope "
        "FROM edges WHERE source_node_id = ? "
        "ORDER BY extraction_confidence DESC, edge_id",
        [source_node_id],
    ).fetchall()
    return [
        {
            "edge_id": r[0],
            "source_node_id": r[1],
            "target_node_id": r[2],
            "relation": r[3],
            "chunk_id": r[4],
            "document_id": r[5],
            "source_tier": r[6],
            "extraction_confidence": r[7],
            "graph_scope": r[8],
        }
        for r in rows
    ]


def _load_edge(con: Any, edge_id: str) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT edge_id, source_node_id, target_node_id, relation, chunk_id, "
        "source_document_id, source_tier, extraction_confidence, graph_scope "
        "FROM edges WHERE edge_id = ?",
        [edge_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "edge_id": row[0],
        "source_node_id": row[1],
        "target_node_id": row[2],
        "relation": row[3],
        "chunk_id": row[4],
        "document_id": row[5],
        "source_tier": row[6],
        "extraction_confidence": row[7],
        "graph_scope": row[8],
    }


def _load_chunks(con: Any, chunk_ids: list[str]) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = con.execute(
        f"SELECT chunk_id, document_id, section_path, text, chunk_index "
        f"FROM chunks WHERE chunk_id IN ({placeholders}) "
        f"ORDER BY chunk_id",
        chunk_ids,
    ).fetchall()
    return [
        {
            "chunk_id": r[0],
            "document_id": r[1],
            "section_path": r[2],
            "text": _excerpt(r[3]),
            "chunk_index": r[4],
        }
        for r in rows
    ]


def _load_documents(con: Any, document_ids: list[str]) -> list[dict[str, Any]]:
    if not document_ids:
        return []
    placeholders = ",".join("?" for _ in document_ids)
    rows = con.execute(
        f"SELECT document_id, title, author, source_tier, acquired_at "
        f"FROM documents WHERE document_id IN ({placeholders}) "
        f"ORDER BY document_id",
        document_ids,
    ).fetchall()
    return [
        {
            "document_id": r[0],
            "title": r[1],
            "author": r[2],
            "source_tier": r[3],
            "acquired_at": _iso(r[4]),
        }
        for r in rows
    ]


def _load_chunk_tier_overrides(
    con: Any, chunk_ids: list[str]
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = con.execute(
        f"SELECT chunk_id, original_tier, override_tier, set_by, reason, set_at "
        f"FROM chunk_tier_overrides WHERE chunk_id IN ({placeholders}) "
        f"ORDER BY chunk_id, set_at",
        chunk_ids,
    ).fetchall()
    return [
        {
            "chunk_id": r[0],
            "original_tier": r[1],
            "override_tier": r[2],
            "set_by": r[3],
            "reason": r[4],
            "set_at": _iso(r[5]),
        }
        for r in rows
    ]


def _chain_for_node(con: Any, node_id: str) -> dict[str, Any] | None:
    """The full claim-style provenance chain for one node."""
    node = _load_node(con, node_id)
    if node is None:
        return None
    edges = _load_edges_from(con, node_id)
    chunk_ids = sorted({e["chunk_id"] for e in edges if e["chunk_id"]})
    document_ids = sorted({e["document_id"] for e in edges if e["document_id"]})
    return {
        "claim_node": node,
        "supporting_edges": edges,
        "chunks": _load_chunks(con, chunk_ids),
        "documents": _load_documents(con, document_ids),
        "chunk_tier_overrides": _load_chunk_tier_overrides(con, chunk_ids),
    }


def _chain_for_pin(
    con: Any, entity_kind: str, entity_id: str
) -> dict[str, Any] | None:
    """Resolve one synthesis_substrate_manifest pin into the same uniform
    chain shape, per entity_kind."""
    if entity_kind == "node":
        return _chain_for_node(con, entity_id)
    if entity_kind == "edge":
        edge = _load_edge(con, entity_id)
        if edge is None:
            return None
        chunk_ids = [edge["chunk_id"]] if edge["chunk_id"] else []
        document_ids = (
            [edge["document_id"]] if edge["document_id"] else []
        )
        return {
            "edge": edge,
            "chunks": _load_chunks(con, chunk_ids),
            "documents": _load_documents(con, document_ids),
            "chunk_tier_overrides": _load_chunk_tier_overrides(con, chunk_ids),
        }
    if entity_kind == "chunk":
        chunk_ids = [entity_id]
        chunks = _load_chunks(con, chunk_ids)
        if not chunks:
            return None
        document_ids = [chunks[0]["document_id"]] if chunks[0]["document_id"] else []
        return {
            "chunk": chunks[0],
            "documents": _load_documents(con, document_ids),
            "chunk_tier_overrides": _load_chunk_tier_overrides(con, chunk_ids),
        }
    if entity_kind == "document":
        documents = _load_documents(con, [entity_id])
        if not documents:
            return None
        return {"document": documents[0]}
    return None


# ---------------------------------------------------------------------------
# Public resolvers (importable + testable without HTTP)
# ---------------------------------------------------------------------------


def resolve_claim_explain(
    claim_node_id: str, *, db_path: str | None = None
) -> dict[str, Any] | None:
    """Full provenance chain for a claim node, or None when the node does
    not exist."""
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    if db is None:
        return None
    con = connect_read(db)
    try:
        return _chain_for_node(con, claim_node_id)
    finally:
        con.close()


def resolve_synthesis_explain(
    synthesis_id: str, *, db_path: str | None = None
) -> dict[str, Any] | None:
    """Provenance chain via the synthesis_substrate_manifest pins, or None
    when the synthesis does not exist. An existing synthesis with zero pins
    returns an honest empty pins map (never a fabricated chain)."""
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    if db is None:
        return None
    con = connect_read(db)
    try:
        exists = con.execute(
            "SELECT 1 FROM syntheses WHERE synthesis_id = ?", [synthesis_id]
        ).fetchone()
        if exists is None:
            return None
        rows = con.execute(
            "SELECT entity_kind, entity_id, pinned_at "
            "FROM synthesis_substrate_manifest WHERE synthesis_id = ? "
            "ORDER BY entity_kind, entity_id",
            [synthesis_id],
        ).fetchall()
        pins: dict[str, list[dict[str, Any]]] = {
            "document": [], "chunk": [], "node": [], "edge": [],
        }
        for entity_kind, entity_id, pinned_at in rows:
            resolved = _chain_for_pin(con, entity_kind, entity_id)
            if resolved is None:
                # A pin that no longer resolves is honest data drift — the
                # manifest references a row that was since removed. Surface
                # it as an unresolved pin rather than dropping it silently.
                pins.setdefault(entity_kind, []).append(
                    {"entity_kind": entity_kind, "entity_id": entity_id,
                     "pinned_at": _iso(pinned_at), "unresolved": True}
                )
                continue
            resolved["entity_kind"] = entity_kind
            resolved["entity_id"] = entity_id
            resolved["pinned_at"] = _iso(pinned_at)
            pins.setdefault(entity_kind, []).append(resolved)
        return {
            "synthesis_id": synthesis_id,
            "pins": pins,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    finally:
        con.close()


def resolve_document_explain(
    document_id: str, *, db_path: str | None = None
) -> dict[str, Any] | None:
    """Reverse provenance: document → chunks → the edges that cite those
    chunks (and the nodes those edges come from). None when the document
    does not exist."""
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    if db is None:
        return None
    con = connect_read(db)
    try:
        documents = _load_documents(con, [document_id])
        if not documents:
            return None
        chunk_rows = con.execute(
            "SELECT chunk_id, chunk_index, section_path, text "
            "FROM chunks WHERE document_id = ? ORDER BY chunk_index, chunk_id",
            [document_id],
        ).fetchall()
        chunks = [
            {
                "chunk_id": r[0],
                "chunk_index": r[1],
                "section_path": r[2],
                "text": _excerpt(r[3]),
                "document_id": document_id,
            }
            for r in chunk_rows
        ]
        chunk_ids = [c["chunk_id"] for c in chunks]
        citing_edges: list[dict[str, Any]] = []
        if chunk_ids:
            placeholders = ",".join("?" for _ in chunk_ids)
            rows = con.execute(
                f"SELECT edge_id, source_node_id, target_node_id, relation, "
                f"chunk_id, source_document_id, source_tier, "
                f"extraction_confidence, graph_scope "
                f"FROM edges WHERE chunk_id IN ({placeholders}) "
                f"ORDER BY source_node_id, edge_id",
                chunk_ids,
            ).fetchall()
            citing_edges = [
                {
                    "edge_id": r[0],
                    "source_node_id": r[1],
                    "target_node_id": r[2],
                    "relation": r[3],
                    "chunk_id": r[4],
                    "document_id": r[5],
                    "source_tier": r[6],
                    "extraction_confidence": r[7],
                    "graph_scope": r[8],
                }
                for r in rows
            ]
        node_ids = sorted(
            {e["source_node_id"] for e in citing_edges if e["source_node_id"]}
        )
        citing_nodes = [
            node for nid in node_ids if (node := _load_node(con, nid)) is not None
        ]
        return {
            "document": documents[0],
            "chunks": chunks,
            "citing_edges": citing_edges,
            "citing_nodes": citing_nodes,
            "chunk_tier_overrides": _load_chunk_tier_overrides(con, chunk_ids),
            "generated_at": datetime.now(UTC).isoformat(),
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@explain_router.get("/claims/{claim_node_id}/explain")
async def claim_explain(claim_node_id: str) -> dict[str, Any]:
    chain = resolve_claim_explain(claim_node_id)
    if chain is None:
        raise HTTPException(
            status_code=404, detail=f"claim node {claim_node_id!r} not found"
        )
    chain["generated_at"] = datetime.now(UTC).isoformat()
    return chain


@explain_router.get("/syntheses/{synthesis_id}/explain")
async def synthesis_explain(synthesis_id: str) -> dict[str, Any]:
    chain = resolve_synthesis_explain(synthesis_id)
    if chain is None:
        raise HTTPException(
            status_code=404, detail=f"synthesis {synthesis_id!r} not found"
        )
    return chain


@explain_router.get("/docs/{document_id}/explain")
async def document_explain(document_id: str) -> dict[str, Any]:
    chain = resolve_document_explain(document_id)
    if chain is None:
        raise HTTPException(
            status_code=404, detail=f"document {document_id!r} not found"
        )
    return chain


def register_explain_routes(app: FastAPI) -> None:
    """Mount the three read-only explain endpoints. One call from
    ``create_app`` (Own Your Mind P0 D1)."""
    app.include_router(explain_router)


__all__ = [
    "register_explain_routes",
    "resolve_claim_explain",
    "resolve_synthesis_explain",
    "resolve_document_explain",
]
