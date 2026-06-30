"""MCP tool definitions for the Antiek Memory server.

Exposes search_personal and search_public tools backed by DuckDB.
Uses substring-match BM25-style scoring over the documents table
(consistent with the rest of the substrate's search patterns).

Single-writer invariant (§16): every connection here is read-only
via ``runtime.db_lock.connect_read``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import duckdb
from mcp.server.fastmcp import FastMCP

from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause

from .errors import EmptyQueryError
from .reader import _resolve_db_path

# ---------------------------------------------------------------------------
# BM25-style scoring helpers
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "because", "as", "until", "while", "of",
    "at", "by", "for", "with", "about", "against", "between", "through",
    "during", "before", "after", "above", "below", "to", "from", "up",
    "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "this", "that", "these", "those", "it", "its", "i", "me",
    "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "they", "them", "their", "what", "which", "who", "whom",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase-alphanumeric tokenization, matching DuckDB FTS conventions."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _extract_query_terms(query: str) -> list[str]:
    """Extract meaningful query terms, dropping stopwords."""
    return [t for t in _tokenize(query) if t not in _STOPWORDS and len(t) > 1]


def _compute_bm25_score(
    text: str,
    query_terms: list[str],
    *,
    k1: float = 1.2,
    b: float = 0.75,
    avg_doc_len: float = 500.0,
) -> float:
    """Simplified BM25 score for a single document.

    Follows the standard BM25 formula:
      score = Σ IDF(term) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl/avgdl))
    where f is term frequency in the document.
    """
    if not query_terms:
        return 0.0

    doc_tokens = _tokenize(text)
    doc_len = len(doc_tokens)
    if doc_len == 0:
        return 0.0

    term_freq: dict[str, int] = {}
    for token in doc_tokens:
        term_freq[token] = term_freq.get(token, 0) + 1

    score = 0.0
    for term in query_terms:
        f = term_freq.get(term, 0)
        if f == 0:
            continue
        idf = 1.0 + (1000.0 / (1.0 + len(term) * 10.0))
        tf_component = (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_doc_len))
        score += idf * tf_component

    return score


def _extract_snippet(
    text: str, query_terms: list[str], *, context_chars: int = 200,
) -> str:
    """Extract the most relevant snippet from text for the given query terms."""
    if not text:
        return ""

    lower = text.lower()
    best_pos = -1
    best_density = 0

    for term in query_terms:
        pos = lower.find(term)
        while pos != -1:
            window_start = max(0, pos - context_chars // 2)
            window_end = min(len(text), pos + context_chars // 2)
            window = lower[window_start:window_end]
            density = sum(1 for t in query_terms if t in window)
            if density > best_density:
                best_density = density
                best_pos = pos
            pos = lower.find(term, pos + 1)

    if best_pos == -1:
        return text[:context_chars] + ("…" if len(text) > context_chars else "")

    start = max(0, best_pos - context_chars // 2)
    end = min(len(text), best_pos + context_chars // 2)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


# ---------------------------------------------------------------------------
# Tool result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """One search result with relevance metadata."""

    note_id: str
    title: str | None
    snippet: str
    score: float
    source_tier: int | None = None
    document_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "note_id": self.note_id,
            "title": self.title,
            "snippet": self.snippet,
            "score": round(self.score, 4),
        }
        if self.source_tier is not None:
            d["source_tier"] = self.source_tier
        if self.document_type is not None:
            d["document_type"] = self.document_type
        return d


@dataclass(frozen=True)
class PublicSearchResult(SearchResult):
    """Search result from the public graph with attribution metadata."""

    ip_holder_id: str | None = None
    content_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["document_id"] = self.note_id
        if self.ip_holder_id is not None:
            d["ip_holder_id"] = self.ip_holder_id
        if self.content_class is not None:
            d["content_class"] = self.content_class
        return d


# ---------------------------------------------------------------------------
# Search implementations
# ---------------------------------------------------------------------------


def search_personal(
    con: duckdb.DuckDBPyConnection,
    query: str,
    *,
    user_id: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """BM25 search over a user's personal notes.

    Returns ranked results with relevance scores. Each result carries
    note_id, title, snippet, and score.

    Args:
        con: Read-only DuckDB connection.
        query: Search query string.
        user_id: Scope results to this user's documents.
        top_k: Maximum number of results to return.

    Returns:
        Dict with query, top_k, and results list.

    Raises:
        EmptyQueryError: When query is empty or whitespace-only.
    """
    query = query.strip()
    if not query:
        raise EmptyQueryError("search_personal")

    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    query_terms = _extract_query_terms(query)
    if not query_terms:
        query_terms = _tokenize(query)

    rows = con.execute(
        """
        SELECT document_id, title, raw_text, source_tier, document_type
        FROM documents
        WHERE owner_user_id = ?
          AND raw_text IS NOT NULL
        ORDER BY acquired_at DESC
        LIMIT 500
        """,
        [user_id],
    ).fetchall()

    results: list[SearchResult] = []
    for doc_id, title, raw_text, tier, doc_type in rows:
        if not raw_text:
            continue
        score = _compute_bm25_score(raw_text, query_terms)
        if score <= 0:
            continue
        snippet = _extract_snippet(raw_text, query_terms)
        results.append(SearchResult(
            note_id=doc_id,
            title=title,
            snippet=snippet,
            score=score,
            source_tier=tier,
            document_type=doc_type,
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    top_results = results[:top_k]

    return {
        "query": query,
        "top_k": top_k,
        "results": [r.to_dict() for r in top_results],
    }


def search_public(
    con: duckdb.DuckDBPyConnection,
    query: str,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """BM25 search over the public graph with attribution metadata.

    Applies the §9.0 retrieval-time gate: restricted_pending_opt_in and
    personal_reading content classes are excluded on non-privileged paths.
    Results carry attribution-routing metadata (ip_holder_id, content_class).

    Args:
        con: Read-only DuckDB connection.
        query: Search query string.
        top_k: Maximum number of results to return.

    Returns:
        Dict with query, top_k, and results list (with attribution metadata).

    Raises:
        EmptyQueryError: When query is empty or whitespace-only.
    """
    query = query.strip()
    if not query:
        raise EmptyQueryError("search_public")

    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    query_terms = _extract_query_terms(query)
    if not query_terms:
        query_terms = _tokenize(query)

    gate_sql, gate_params = non_privileged_chunk_sql_clause(table_alias="d")

    rows = con.execute(
        f"""
        SELECT d.document_id, d.title, d.raw_text, d.source_tier,
               d.document_type, d.ip_holder_id, d.content_class
        FROM documents d
        WHERE d.raw_text IS NOT NULL
          {gate_sql}
        ORDER BY d.acquired_at DESC
        LIMIT 500
        """,
        gate_params,
    ).fetchall()

    results: list[PublicSearchResult] = []
    for doc_id, title, raw_text, tier, doc_type, ip_holder_id, content_class in rows:
        if not raw_text:
            continue
        score = _compute_bm25_score(raw_text, query_terms)
        if score <= 0:
            continue
        snippet = _extract_snippet(raw_text, query_terms)
        results.append(PublicSearchResult(
            note_id=doc_id,
            title=title,
            snippet=snippet,
            score=score,
            source_tier=tier,
            document_type=doc_type,
            ip_holder_id=ip_holder_id,
            content_class=content_class,
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    top_results = results[:top_k]

    return {
        "query": query,
        "top_k": top_k,
        "results": [r.to_dict() for r in top_results],
    }


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP) -> None:
    """Register all Antiek MCP tools on the given FastMCP server."""

    @mcp.tool(
        name="search_personal",
        description=(
            "BM25 search over a user's personal notes. "
            "Returns ranked results with note_id, title, snippet, "
            "and relevance score."
        ),
    )
    def search_personal_tool(user_id: str, query: str, top_k: int = 5) -> str:
        """Search a user's personal notes."""
        from runtime.db_lock import connect_read

        db_path = _resolve_db_path()
        con = connect_read(db_path)
        try:
            result = search_personal(con, query, user_id=user_id, top_k=top_k)
        finally:
            con.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        name="search_public",
        description=(
            "BM25 search over the public knowledge graph. "
            "Returns results with attribution-routing metadata "
            "(ip_holder_id, content_class). Respects §9.0 retrieval-time gating."
        ),
    )
    def search_public_tool(query: str, top_k: int = 5) -> str:
        """Search the public knowledge graph."""
        from runtime.db_lock import connect_read

        db_path = _resolve_db_path()
        con = connect_read(db_path)
        try:
            result = search_public(con, query, top_k=top_k)
        finally:
            con.close()
        return json.dumps(result, default=str)
