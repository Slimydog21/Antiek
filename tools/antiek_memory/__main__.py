"""Antiek Memory MCP server — subprocess entry point.

Run with: python -m tools.antiek_memory

Reads ANTIEK_DUCKDB_PATH from the environment (falls back to
~/.antiek/research_graph.duckdb) and ANTIEK_MEMORY_OWNER, the owner this
process serves (unset: private reads refuse every call). Initialises the schema on cold
start, wires the four canonical tool handlers + resource handler
against the real substrate, and serves JSON-RPC over stdio.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from interfaces.research.api.account_memory_identity import FORBIDDEN_OWNERS
from runtime.db_lock import connect_read
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

# A public class is necessary but not sufficient for licensed material: its
# rights holder must still have an active opt-in, and a takedown always wins.
_NOT_TAKEN_DOWN_SQL = """
    NOT EXISTS (
        SELECT 1 FROM book_assets b
        WHERE b.document_id = d.document_id AND b.taken_down
    )
"""
_PUBLIC_DOCUMENT_SQL = """
    (
        d.content_class = 'user_public_contribution'
        OR (
            d.owner_user_id = '__operator__'
            AND (
                d.content_class IN ('public_domain', 'source_declared_open')
                OR (
                    d.content_class = 'opt_in_licensed'
                    AND EXISTS (
                        SELECT 1 FROM ip_holders h
                        WHERE h.ip_holder_id = d.ip_holder_id AND h.status = 'claimed'
                    )
                )
            )
        )
    )
"""


def _authenticated_owner(auth_context: object) -> str | None:
    """Resolve the process-bound owner from the server-filled ``auth_context``.

    The stdio launcher supplies ``auth_context["user_id"]`` from
    ``ANTIEK_MEMORY_OWNER``. Storage sentinels that name a deployment rather
    than a person (``FORBIDDEN_OWNERS``) are refused. The launch environment
    is not itself proof that an SSH principal owns the chosen account.
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
) -> tuple[dict[str, Callable[..., ToolResult]], Callable[..., ResourceContent | None]]:
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
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return _error_result("query is required", query="")
        top_k = args.get("top_k", 5)
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 50:
            return _error_result("top_k must be between 1 and 50", query=query)
        con = connect_read(db_path)
        try:
            rows = con.execute(
                f"""
                SELECT c.chunk_id, c.text, d.title, d.source_tier
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                WHERE ({_PUBLIC_DOCUMENT_SQL}) AND {_NOT_TAKEN_DOWN_SQL}
                  AND (contains(lower(c.text), lower(?))
                       OR contains(lower(COALESCE(d.title, '')), lower(?)))
                ORDER BY d.document_id, c.chunk_index
                LIMIT ?
                """,
                [query.strip(), query.strip(), top_k],
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
    def cite_source(args: dict, *, auth_context: object = None) -> ToolResult:
        src_id = args["id"]
        id_type = args.get("id_type", "chunk")
        owner = _authenticated_owner(auth_context)
        con = connect_read(db_path)
        try:
            if id_type == "chunk":
                row = con.execute(
                    f"""
                    SELECT c.chunk_id, d.document_id, d.title, d.source_tier,
                           d.author, c.section_path
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    WHERE c.chunk_id = ?
                      AND (d.owner_user_id = ? OR ({_PUBLIC_DOCUMENT_SQL}))
                      AND {_NOT_TAKEN_DOWN_SQL}
                    """,
                    [src_id, owner],
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
        # This store has no authenticated investigation or dwell record to join
        # to a client claim. An unverified event must not become payout evidence.
        return ToolResult(
            content=[{"type": "text", "text": json.dumps({"error": "not authorized"})}],
            is_error=True,
        )

    # ── resource handler ──────────────────────────────────────────
    def resource_handler(
        uri: str, *, auth_context: object = None
    ) -> ResourceContent | None:
        try:
            parsed = urlsplit(uri)
        except ValueError:
            return None
        if (
            parsed.scheme != "antiek"
            or uri != f"antiek://{parsed.netloc}{parsed.path}"
            or parsed.query
            or parsed.fragment
            or "%" in uri
            or parsed.username is not None
            or any(part in {".", ".."} for part in parsed.path.split("/"))
        ):
            return None
        parts = parsed.path.split("/")
        if parsed.netloc == "books":
            # No persisted ISBN-to-edition and owner entitlement authority
            # exists in this MCP store. A chunk ID or client ISBN cannot
            # prove either right, so do not fetch the body or metadata.
            return None
        con = connect_read(db_path)
        try:
            if parsed.netloc == "private" and len(parts) == 4 and parts[1] == "notes":
                user_id, note_id = parts[2:]
                owner = _authenticated_owner(auth_context)
                if not owner or user_id != owner or not note_id or "/" in note_id:
                    return None
                # Notes are stored as notebook_blocks with block_type='note'
                row = con.execute(
                    """
                    SELECT nb.block_id, nb.content_json, n.title, n.owner_user_id
                    FROM notebook_blocks nb
                    JOIN notebooks n ON nb.notebook_id = n.notebook_id
                    WHERE nb.block_id = ? AND n.owner_user_id = ?
                      AND nb.block_type = 'note' AND n.content_class = 'user_owned'
                    """,
                    [note_id, owner],
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

            if parsed.netloc == "public" and len(parts) == 3 and parts[1] == "notes":
                note_id = parts[2]
                if not note_id:
                    return None
                row = con.execute(
                    """
                    SELECT nb.block_id, nb.content_json, n.title
                    FROM notebook_blocks nb
                    JOIN notebooks n ON nb.notebook_id = n.notebook_id
                    WHERE nb.block_id = ? AND nb.block_type = 'note'
                      AND n.content_class = 'user_public_contribution'
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
