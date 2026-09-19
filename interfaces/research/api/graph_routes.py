"""Read-only knowledge-graph explorer transport.

The operator surface needs a bounded, provenance-complete view of graph nodes
without opening a write connection or invoking a provider. Empty and missing
evidence stays explicit; the route never synthesizes relationships.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from runtime.db_lock import connect_read
from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.graph import default_db_path

graph_router = APIRouter(prefix="/graph", tags=["knowledge-graph"])


class GraphNodeOut(BaseModel):
    node_id: str
    label: str
    node_type: str
    graph_scope: str
    degree: int
    created_at: str


class GraphEvidenceOut(BaseModel):
    chunk_id: str | None = None
    chunk_text: str | None = None
    section_path: str | None = None
    source_document_id: str | None = None
    source_title: str | None = None
    source_author: str | None = None
    source_tier: int
    content_class: str | None = None
    ip_holder_id: str | None = None
    servable: bool


class GraphEdgeOut(BaseModel):
    edge_id: str
    source_node_id: str
    source_label: str
    target_node_id: str
    target_label: str
    relation: str
    graph_scope: str
    investigation_id: str | None = None
    confidence: float
    valid_from: str
    valid_until: str | None = None
    evidence: GraphEvidenceOut


class GraphExploreOut(BaseModel):
    query: str
    node_id: str | None
    node_type: str | None
    graph_scope: str | None
    investigation_id: str | None
    node_count: int
    edge_count: int
    truncated: bool
    read_only: Literal[True] = True
    access_policy: Literal["operator_only"] = "operator_only"
    view_format: Literal["html"] = "html"
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _bounded_text(value: Any, *, max_chars: int = 1_200) -> str | None:
    """Keep the operator evidence preview useful without an unbounded response."""
    if value is None:
        return None
    rendered = str(value)
    return rendered if len(rendered) <= max_chars else rendered[: max_chars - 1] + "…"


@graph_router.get("/explore", response_model=GraphExploreOut)
def explore_graph(
    request: Request,
    q: str = Query(default="", max_length=200),
    node_id: str | None = Query(default=None, min_length=1, max_length=256),
    node_type: str | None = Query(default=None, max_length=40),
    graph_scope: str | None = Query(default=None, max_length=40),
    investigation_id: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=60, ge=1, le=200),
) -> GraphExploreOut:
    """Return bounded nodes, adjacent edges, and stored evidence.

    This is an explicitly ``operator_only`` surface behind the research API's
    global operator-auth middleware. Local development without configured auth
    retains the application's existing single-operator trust model. Evidence
    previews may therefore include personal-reading text, but are never a
    portable/public servability decision.
    """
    where = ["1=1"]
    params: list[Any] = []
    authority = None
    strict = os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1"
    if strict:
        from interfaces.research.api.investigation_access import (
            InvestigationAccessDenied,
            authority_from_request,
            require_investigation_owner,
        )

        if not investigation_id:
            raise HTTPException(
                status_code=422,
                detail="investigation_id is required for legal graph reads",
            )
        try:
            access = authority_from_request(request, investigation_id)
            require_investigation_owner(access)
            authority = access.authority
        except InvestigationAccessDenied as exc:
            raise HTTPException(status_code=404, detail="knowledge graph not found") from exc
        where.append(
            "EXISTS (SELECT 1 FROM investigation_node_memberships lm "
            "WHERE lm.node_id = n.node_id AND lm.account_digest = ? "
            "AND lm.investigation_digest = ?)"
        )
        params.extend([authority.account_digest, authority.investigation_digest])
    query = q.strip()
    exact_node_id = node_id.strip() if node_id is not None else None
    if node_id is not None and not exact_node_id:
        raise HTTPException(status_code=422, detail="node_id must not be blank")
    if exact_node_id:
        where.append("n.node_id = ?")
        params.append(exact_node_id)
    if query:
        where.append("(n.canonical_label ILIKE ? OR n.node_id ILIKE ?)")
        term = f"%{query}%"
        params.extend([term, term])
    if node_type:
        where.append("n.node_type = ?")
        params.append(node_type)
    if graph_scope:
        where.append("n.graph_scope = ?")
        params.append(graph_scope)
    if investigation_id:
        investigation_clause = (
            "EXISTS (SELECT 1 FROM edges ie WHERE "
            "(ie.source_node_id = n.node_id OR ie.target_node_id = n.node_id) "
            "AND ie.investigation_id = ?"
        )
        params.append(investigation_id)
        if graph_scope:
            investigation_clause += " AND ie.graph_scope = ?"
            params.append(graph_scope)
        where.append(investigation_clause + ")")

    db = default_db_path()
    try:
        con = connect_read(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="knowledge graph is unavailable") from exc
    try:
        rows = con.execute(
            "SELECT n.node_id, n.canonical_label, n.node_type, n.graph_scope, "
            "n.degree_cached, n.created_at, n.metadata, "
            "(SELECT m.role FROM investigation_node_memberships m "
            "WHERE m.node_id = n.node_id AND m.account_digest = ? "
            "AND m.investigation_digest = ? ORDER BY m.role LIMIT 1) "
            "FROM nodes n WHERE "
            + " AND ".join(where)
            + " ORDER BY n.degree_cached DESC, n.created_at DESC, n.node_id LIMIT ?",
            [
                authority.account_digest if strict else "",
                authority.investigation_digest if strict else "",
                *params,
                limit + 1,
            ],
        ).fetchall()
        truncated = len(rows) > limit
        rows = rows[:limit]
        node_ids = [str(row[0]) for row in rows]
        edge_rows: list[Any] = []
        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            edge_where = (
                f"(e.source_node_id IN ({placeholders}) "
                f"OR e.target_node_id IN ({placeholders}))"
            )
            edge_params: list[Any] = [*node_ids, *node_ids]
            if investigation_id:
                edge_where += " AND e.investigation_id = ?"
                edge_params.append(investigation_id)
            if strict:
                edge_where += " AND e.account_digest = ? AND e.investigation_digest = ?"
                edge_params.extend(
                    [authority.account_digest, authority.investigation_digest]
                )
                edge_where += (
                    " AND EXISTS (SELECT 1 FROM investigation_node_memberships esm "
                    "WHERE esm.node_id = e.source_node_id AND esm.account_digest = ? "
                    "AND esm.investigation_digest = ?) "
                    "AND EXISTS (SELECT 1 FROM investigation_node_memberships etm "
                    "WHERE etm.node_id = e.target_node_id AND etm.account_digest = ? "
                    "AND etm.investigation_digest = ?)"
                )
                edge_params.extend(
                    [
                        authority.account_digest,
                        authority.investigation_digest,
                        authority.account_digest,
                        authority.investigation_digest,
                    ]
                )
            if graph_scope:
                edge_where += " AND e.graph_scope = ?"
                edge_params.append(graph_scope)
            edge_limit = min(limit * 4, 500)
            from substrate.legal_gate.read import graph_edge_projections_compatibility

            edge_rows = graph_edge_projections_compatibility(
                con,
                where_sql=edge_where,
                params=edge_params,
                limit=edge_limit + 1,
                authority=authority,
                enforce=strict,
            )
            if len(edge_rows) > edge_limit:
                truncated = True
                edge_rows = edge_rows[:edge_limit]
            if strict:
                from substrate.legal_gate.policy_store import LegalPolicyDenied
                from substrate.legal_gate.read import read_chunk, read_chunks

                readable: dict[str, set[str]] = {}
                denied: set[str] = set()
                filtered_edges = []
                denied_nodes: set[str] = set()
                for edge_row in edge_rows:
                    source_document_id = edge_row[14]
                    if source_document_id is None:
                        filtered_edges.append(edge_row)
                        continue
                    document_id = str(source_document_id)
                    if document_id not in readable and document_id not in denied:
                        try:
                            readable[document_id] = {
                                str(item["chunk_id"])
                                for item in read_chunks(con, authority, document_id)
                            }
                        except LegalPolicyDenied:
                            denied.add(document_id)
                            denied_nodes.update(
                                [str(edge_row[1]), str(edge_row[3])]
                            )
                    chunk_id = None if edge_row[11] is None else str(edge_row[11])
                    if document_id in readable and (
                        chunk_id is None or chunk_id in readable[document_id]
                    ):
                        filtered_edges.append(edge_row)
                edge_rows = filtered_edges
                for node_row in rows:
                    try:
                        metadata = json.loads(node_row[6]) if node_row[6] else {}
                    except (TypeError, ValueError):
                        metadata = {}
                    if not isinstance(metadata, dict):
                        metadata = {}
                    metadata_document = metadata.get("source_document_id")
                    metadata_chunk = metadata.get("chunk_id")
                    if not metadata_document and not metadata_chunk and node_row[7] != "note":
                        denied_nodes.add(str(node_row[0]))
                        continue
                    if metadata_chunk and not metadata_document:
                        try:
                            source = read_chunk(con, authority, str(metadata_chunk))
                            metadata_document = source["document_id"]
                        except LegalPolicyDenied:
                            denied_nodes.add(str(node_row[0]))
                            continue
                    if metadata_document:
                        document_id = str(metadata_document)
                        if document_id not in readable and document_id not in denied:
                            try:
                                readable[document_id] = {
                                    str(item["chunk_id"])
                                    for item in read_chunks(con, authority, document_id)
                                }
                            except LegalPolicyDenied:
                                denied.add(document_id)
                        if document_id in denied or (
                            metadata_chunk
                            and str(metadata_chunk) not in readable.get(document_id, set())
                        ):
                            denied_nodes.add(str(node_row[0]))
                rows = [row for row in rows if str(row[0]) not in denied_nodes]
                allowed_node_ids = (
                    {str(row[0]) for row in rows}
                    | {str(row[1]) for row in edge_rows}
                    | {str(row[3]) for row in edge_rows}
                ) - denied_nodes
                edge_rows = [
                    row
                    for row in edge_rows
                    if str(row[1]) in allowed_node_ids and str(row[3]) in allowed_node_ids
                ]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="knowledge graph query failed") from exc
    finally:
        con.close()

    nodes = [
        GraphNodeOut(
            node_id=str(row[0]),
            label=str(row[1]),
            node_type=str(row[2]),
            graph_scope=str(row[3]),
            degree=int(row[4] or 0),
            created_at=_iso(row[5]) or "",
        )
        for row in rows
    ]
    edges = []
    for row in edge_rows:
        content_class = str(row[18]) if row[18] is not None else None
        chunk_text = _bounded_text(row[12])
        edges.append(
            GraphEdgeOut(
                edge_id=str(row[0]),
                source_node_id=str(row[1]),
                source_label=str(row[2]),
                target_node_id=str(row[3]),
                target_label=str(row[4]),
                relation=str(row[5]),
                graph_scope=str(row[6]),
                investigation_id=str(row[7]) if row[7] is not None else None,
                confidence=float(row[8]),
                valid_from=_iso(row[9]) or "",
                valid_until=_iso(row[10]),
                evidence=GraphEvidenceOut(
                    chunk_id=str(row[11]) if row[11] is not None else None,
                    chunk_text=chunk_text,
                    section_path=str(row[13]) if row[13] is not None else None,
                    source_document_id=str(row[14]) if row[14] is not None else None,
                    source_title=str(row[15]) if row[15] is not None else None,
                    source_author=str(row[16]) if row[16] is not None else None,
                    source_tier=int(row[17]),
                    content_class=content_class,
                    ip_holder_id=str(row[19]) if row[19] is not None else None,
                    servable=content_class in SERVABLE_CONTENT_CLASSES,
                ),
            )
        )

    return GraphExploreOut(
        query=query,
        node_id=exact_node_id,
        node_type=node_type,
        graph_scope=graph_scope,
        investigation_id=investigation_id,
        node_count=len(nodes),
        edge_count=len(edges),
        truncated=truncated,
        nodes=nodes,
        edges=edges,
    )


__all__ = ["graph_router"]
