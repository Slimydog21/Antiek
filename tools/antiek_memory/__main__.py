"""Antiek Memory MCP server — subprocess entry point.

Run with: python -m tools.antiek_memory

Reads ANTIEK_DUCKDB_PATH from the environment (falls back to
~/.antiek/research_graph.duckdb) and ANTIEK_MEMORY_OWNER, the owner this
process serves (unset: search_personal refuses every call).  Initialises the schema on cold
start, wires the four canonical tool handlers + resource handler
against the real substrate, and serves JSON-RPC over stdio.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from typing import Any

from interfaces.research.api.account_memory_identity import FORBIDDEN_OWNERS
from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import EmbeddingModel, SentenceTransformerEmbedding, search

from .server import (
    CANONICAL_TOOLS,
    AntiekMemoryServer,
    ResourceContent,
    ToolResult,
    serve_stdio,
)

_TRUSTED_FALSE = '<antiek:content trusted="false">{}</antiek:content>'

# Longest owner id the handler will bind; mirrors account_memory_identity.
_MAX_OWNER_LENGTH = 256


def _authenticated_owner(auth_context: object) -> str | None:
    """Resolve the caller's owner id from the transport-filled ``auth_context``.

    The claim is ``auth_context["user_id"]`` — the same subject the API's auth
    middleware places on ``request.state.user_id``. Storage sentinels that name
    a deployment rather than a person (``FORBIDDEN_OWNERS``, shared with every
    other private-memory boundary) are refused: "per-user OAuth scope" in the
    published manifest means a distinct human, and a shared identity would
    hand one caller every operator-authenticated document. Returns ``None``
    whenever proof is absent so the caller fails closed instead of falling
    back to any default owner.
    """
    if not isinstance(auth_context, dict):
        return None
    value = auth_context.get("user_id")
    if not isinstance(value, str):
        return None
    owner = value.strip()
    if not owner or len(owner) > _MAX_OWNER_LENGTH or owner.casefold() in FORBIDDEN_OWNERS:
        return None
    return owner


def _error_result(message: str, *, query: str) -> ToolResult:
    return ToolResult(
        content=[{
            "type": "text",
            "text": json.dumps({"chunks": [], "query": query, "error": message}),
        }],
        is_error=True,
    )


def _make_handlers(
    db_path: str,
    *,
    embedding_model: Callable[[], EmbeddingModel] = SentenceTransformerEmbedding,
) -> tuple[dict[str, Callable[..., ToolResult]], Callable[[str], ResourceContent | None]]:
    """Build handler closures bound to *db_path*.

    ``embedding_model`` is a zero-argument factory for the ranked-retrieval
    model. Production keeps the default (the same sentence-transformers wrapper
    the thought partner's library grounding uses); tests inject a deterministic
    stub. It is constructed lazily on the first ``search_personal`` call so the
    server still starts where the model is not installed, and an owner who owns
    no documents gets an honest empty answer without ever loading it.
    """
    model_slot: list[EmbeddingModel] = []

    def _model() -> EmbeddingModel:
        if not model_slot:
            model_slot.append(embedding_model())
        return model_slot[0]

    # ── search_personal ───────────────────────────────────────────
    def search_personal(args: dict[str, Any], *, auth_context: object = None) -> ToolResult:
        """Ranked retrieval over the caller's OWN documents.

        The owner comes from the transport's ``auth_context`` (see
        ``AntiekMemoryServer``), never from ``args``. Scope is the set of
        documents whose ``owner_user_id`` is that owner, expressed through
        ``search()``'s existing ``document_ids`` bound so the §9.0 gate and the
        ranking stay the one reviewed implementation; ``private_research`` is
        the owner reading their own library, which is what "personal" means.
        """
        query = args["query"]
        top_k = args.get("top_k", 5)
        owner = _authenticated_owner(auth_context)
        if owner is None:
            return _error_result(
                "search_personal requires an authenticated per-user owner in "
                "auth_context.user_id",
                query=query,
            )
        con = connect_read(db_path)
        try:
            owned = [
                str(row[0])
                for row in con.execute(
                    "SELECT document_id FROM documents WHERE owner_user_id = ? "
                    "ORDER BY document_id",
                    [owner],
                ).fetchall()
            ]
            hits: list[dict[str, Any]] = []
            if owned:
                hits = search(
                    con,
                    query,
                    model=_model(),
                    top_k=top_k,
                    document_ids=owned,
                    policy_tag="private_research",
                    owner_user_id=owner,
                )["results"]
            # search() truncates chunk_text for prompt budgets; this surface
            # has always returned the whole chunk, so read it back by id.
            full_text: dict[str, str] = {}
            if hits:
                placeholders = ",".join("?" for _ in hits)
                full_text = {
                    str(row[0]): str(row[1])
                    for row in con.execute(
                        f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})",
                        [hit["chunk_id"] for hit in hits],
                    ).fetchall()
                }
        finally:
            con.close()
        chunks = [
            {
                "chunk_id": hit["chunk_id"],
                "text": full_text.get(hit["chunk_id"], hit["chunk_text"]),
                "title": hit["document_title"],
                "source_tier": hit["source_tier"],
                "owner_user_id": owner,
                "similarity": hit["similarity"],
            }
            for hit in hits
        ]
        return ToolResult(content=[{
            "type": "text",
            "text": json.dumps({"chunks": chunks, "query": query}),
        }])

    # ── search_public ─────────────────────────────────────────────
    def search_public(args: dict) -> ToolResult:
        query = args["query"]
        top_k = args.get("top_k", 5)
        con = connect_read(db_path)
        try:
            rows = con.execute(
                """
                SELECT c.chunk_id, c.text, d.title, d.source_tier
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                ORDER BY c.chunk_index
                LIMIT ?
                """,
                [top_k],
            ).fetchall()
        finally:
            con.close()
        # §13.8.3: wrap public content in prompt-injection envelope
        chunks = []
        for r in rows:
            envelope = _TRUSTED_FALSE.format(r[1])
            chunks.append({
                "chunk_id": r[0],
                "text": envelope,
                "title": r[2],
                "source_tier": r[3],
            })
        return ToolResult(content=[{
            "type": "text",
            "text": json.dumps({"chunks": chunks, "query": query}),
        }])

    # ── cite_source ───────────────────────────────────────────────
    def cite_source(args: dict) -> ToolResult:
        src_id = args["id"]
        id_type = args.get("id_type", "chunk")
        con = connect_read(db_path)
        try:
            if id_type == "chunk":
                row = con.execute(
                    """
                    SELECT c.chunk_id, d.document_id, d.title, d.source_tier,
                           d.author, c.section_path
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    WHERE c.chunk_id = ?
                    """,
                    [src_id],
                ).fetchone()
            else:
                row = None
        finally:
            con.close()
        if row is None:
            return ToolResult(
                content=[{"type": "text", "text": json.dumps({"error": "not found"})}],
                is_error=True,
            )
        citation = {
            "chunk_id": row[0],
            "document_id": row[1],
            "title": row[2],
            "source_tier": row[3],
            "author": row[4],
            "section_path": row[5],
        }
        return ToolResult(content=[{
            "type": "text",
            "text": json.dumps(citation),
        }])

    # ── record_attribution ────────────────────────────────────────
    def record_attribution(args: dict) -> ToolResult:
        chunk_id = args["chunk_id"]
        investigation_id = args["investigation_id"]
        dwell = args.get("session_dwell_seconds", 0)
        audit_id = str(uuid.uuid4())
        con = connect_write(db_path, purpose="mcp_record_attribution")
        try:
            con.execute(
                """
                INSERT INTO attribution_audit
                    (audit_id, impression_set_ref, page_id, algorithm,
                     algorithm_version, inputs_json, shares_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [audit_id, investigation_id, chunk_id,
                 "equal_split_per_chunk_citation", "1.0",
                 json.dumps({"chunk_id": chunk_id, "investigation_id": investigation_id, "dwell_seconds": dwell}),
                 json.dumps({chunk_id: 1.0})],
            )
        finally:
            con.close()
        return ToolResult(content=[{
            "type": "text",
            "text": json.dumps({
                "status": "recorded",
                "audit_id": audit_id,
                "chunk_id": chunk_id,
                "investigation_id": investigation_id,
                "dwell_seconds": dwell,
            }),
        }])

    # ── resource handler ──────────────────────────────────────────
    def resource_handler(uri: str) -> ResourceContent | None:
        con = connect_read(db_path)
        try:
            if uri.startswith("antiek://private/notes/"):
                parts = uri.split("/")
                # antiek://private/notes/{user_id}/{note_id}
                user_id = parts[4] if len(parts) > 4 else None
                note_id = parts[5] if len(parts) > 5 else None
                if not user_id or not note_id:
                    return None
                # Notes are stored as notebook_blocks with block_type='note'
                row = con.execute(
                    """
                    SELECT nb.block_id, nb.content_json, n.title, n.owner_user_id
                    FROM notebook_blocks nb
                    JOIN notebooks n ON nb.notebook_id = n.notebook_id
                    WHERE nb.block_id = ? AND n.owner_user_id = ?
                    """,
                    [note_id, user_id],
                ).fetchone()
                if row is None:
                    return None
                # §13.8.3: wrap in prompt-injection envelope
                raw = row[1] or json.dumps({"note_id": note_id, "title": row[2]})
                envelope = _TRUSTED_FALSE.format(raw)
                return ResourceContent(
                    uri=uri,
                    mime_type="application/json",
                    text=json.dumps({
                        "note_id": note_id,
                        "user_id": user_id,
                        "title": row[2],
                        "content": envelope,
                    }),
                )

            if uri.startswith("antiek://public/notes/"):
                parts = uri.split("/")
                note_id = parts[4] if len(parts) > 4 else None
                if not note_id:
                    return None
                row = con.execute(
                    """
                    SELECT nb.block_id, nb.content_json, n.title
                    FROM notebook_blocks nb
                    JOIN notebooks n ON nb.notebook_id = n.notebook_id
                    WHERE nb.block_id = ? AND n.content_class = 'user_public_contribution'
                    """,
                    [note_id],
                ).fetchone()
                if row is None:
                    return None
                raw = row[1] or json.dumps({"note_id": note_id, "title": row[2]})
                envelope = _TRUSTED_FALSE.format(raw)
                return ResourceContent(
                    uri=uri,
                    mime_type="application/json",
                    text=json.dumps({
                        "note_id": note_id,
                        "title": row[2],
                        "content": envelope,
                    }),
                )

            if uri.startswith("antiek://books/"):
                parts = uri.split("/")
                isbn = parts[3] if len(parts) > 3 else None
                chunk_id = parts[4] if len(parts) > 4 else None
                if not isbn or not chunk_id:
                    return None
                row = con.execute(
                    """
                    SELECT c.chunk_id, c.text, d.title
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    WHERE c.chunk_id = ?
                    """,
                    [chunk_id],
                ).fetchone()
                if row is None:
                    return None
                return ResourceContent(
                    uri=uri,
                    mime_type="application/json",
                    text=json.dumps({
                        "chunk_id": row[0],
                        "isbn": isbn,
                        "text": row[1],
                        "title": row[2],
                    }),
                )

            return None
        finally:
            con.close()

    return {
        "search_personal": search_personal,
        "search_public": search_public,
        "cite_source": cite_source,
        "record_attribution": record_attribution,
    }, resource_handler


def main() -> None:
    db_path = default_db_path()
    init_database_at_path(db_path)
    handlers, res_handler = _make_handlers(db_path)
    server = AntiekMemoryServer(
        tools=list(CANONICAL_TOOLS),
        handler_fns=handlers,
        resource_handler=res_handler,
        bound_owner=_authenticated_owner(
            {"user_id": os.environ.get("ANTIEK_MEMORY_OWNER")}
        ),
    )
    serve_stdio(server)


if __name__ == "__main__":
    main()
