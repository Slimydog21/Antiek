"""Fail-closed recall over one physically isolated personal graph."""

from __future__ import annotations

import math
import re
from typing import Any

from processing.embedding import (
    default_embedding_provider,
    embedding_provider_fingerprint,
)
from runtime.db_lock import connect_read
from substrate.graph.search import cosine_similarity_sql
from substrate.graph_per_user.runtime import existing_owner_graph_db_path

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}")
# A cosine below 0.20 is too weak to spend scarce prompt context on. This is
# intentionally a recall floor, not an empirical quality claim; Antiek-bench
# should replace it with a task-calibrated threshold once labeled usage exists.
MIN_PERSONAL_NODE_COSINE = 0.20


def _tokens(value: str) -> list[str]:
    return list(dict.fromkeys(token.lower() for token in _TOKEN.findall(value)))[:16]


def _personal_item(
    *, node_id: str, node_type: str, label: str, confidence: float
) -> dict[str, Any]:
    return {
        "note_id": node_id,
        "note_text": label,
        "source_event_ids": [],
        "source_node_ids": [node_id],
        "confidence": round(max(0.0, min(float(confidence), 1.0)), 4),
        "knowledge_scope": "personal_owner",
        "node_type": node_type,
    }


def recall_personal_nodes(
    db_path: str,
    query: str,
    *,
    model: Any = None,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Return bounded insight/question recall from exactly ``db_path``.

    Semantic comparison is allowed only when the node records the same
    embedding fingerprint as the query provider. Legacy nodes without a
    fingerprint remain reachable through a bounded lexical fallback.
    """
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    cleaned = query.strip()
    if not cleaned:
        return []
    provider = model or default_embedding_provider()
    vector = list(provider.encode(cleaned))
    if len(vector) != int(provider.dimension):
        raise ValueError("embedding provider returned an incompatible dimension")
    fingerprint = embedding_provider_fingerprint(provider)
    similarity = cosine_similarity_sql("n.embedding", vector, int(provider.dimension))
    con = connect_read(db_path)
    try:
        semantic_rows = con.execute(
            f"""
            SELECT n.node_id, n.node_type, n.canonical_label, {similarity} AS score
            FROM nodes n
            WHERE n.node_type IN ('insight', 'question')
              AND n.embedding IS NOT NULL
              AND array_length(n.embedding) = ?
              AND json_extract_string(n.metadata, '$.embedding_fingerprint') = ?
            ORDER BY score DESC
            LIMIT ?
            """,
            [int(provider.dimension), fingerprint, int(top_k * 2)],
        ).fetchall()
        terms = _tokens(cleaned)
        lexical_rows: list[tuple[Any, ...]] = []
        if terms:
            clauses = " OR ".join("n.canonical_label ILIKE ?" for _ in terms)
            lexical_rows = con.execute(
                f"""
                SELECT n.node_id, n.node_type, n.canonical_label
                FROM nodes n
                WHERE n.node_type IN ('insight', 'question')
                  AND ({clauses})
                LIMIT ?
                """,
                [*(f"%{term}%" for term in terms), int(top_k * 8)],
            ).fetchall()
    finally:
        con.close()

    candidates: dict[str, dict[str, Any]] = {}
    for node_id, node_type, label, raw_score in semantic_rows:
        score = float(raw_score or 0.0)
        if not math.isfinite(score) or score < MIN_PERSONAL_NODE_COSINE:
            continue
        candidates[str(node_id)] = _personal_item(
            node_id=str(node_id),
            node_type=str(node_type),
            label=str(label),
            confidence=(score + 1.0) / 2.0,
        )
    term_set = set(terms)
    for node_id, node_type, label in lexical_rows:
        label_tokens = set(_tokens(str(label)))
        overlap = len(term_set & label_tokens) / max(1, len(term_set))
        lexical_score = min(0.79, 0.45 + overlap * 0.34)
        key = str(node_id)
        prior = candidates.get(key)
        if prior is None or lexical_score > float(prior["confidence"]):
            candidates[key] = _personal_item(
                node_id=key,
                node_type=str(node_type),
                label=str(label),
                confidence=lexical_score,
            )
    return sorted(
        candidates.values(),
        key=lambda item: (-float(item["confidence"]), str(item["note_id"])),
    )[:top_k]


def recall_owner_nodes(
    owner_id: str,
    query: str,
    *,
    model: Any = None,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Resolve and recall one owner without canonical fallback or writes."""
    if owner_id == "__operator__":
        return []
    path = existing_owner_graph_db_path(owner_id)
    if path is None:
        return []
    return recall_personal_nodes(path, query, model=model, top_k=top_k)


def get_owner_node(owner_id: str, node_id: str) -> dict[str, str] | None:
    """Resolve one explicit personal node; foreign/absent graphs read missing."""
    if owner_id == "__operator__":
        return None
    path = existing_owner_graph_db_path(owner_id)
    if path is None:
        return None
    con = connect_read(path)
    try:
        row = con.execute(
            "SELECT node_id, node_type, canonical_label FROM nodes "
            "WHERE node_id = ? AND node_type IN ('insight', 'question') LIMIT 1",
            [node_id],
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    return {"node_id": str(row[0]), "node_type": str(row[1]), "label": str(row[2])}
