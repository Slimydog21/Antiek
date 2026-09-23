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
from processing.embedding.embed import default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.ad_inventory.attribution import (
    PRIVATE_GRAPH_CONTENT_CLASS,
    PUBLIC_GRAPH_CONTENT_CLASSES,
)
from substrate.books.servability import servability_of
from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.dedup import normalize_isbn
from substrate.graph import default_db_path
from substrate.graph.retrieval_gate import (
    PERSONAL_ONLY_CONTENT_CLASSES,
    RESTRICTED_CONTENT_CLASSES,
    is_chunk_body_withheld,
)
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import EmbeddingModel, search

from .server import (
    CANONICAL_TOOLS,
    LICENSING_REQUIRED,
    AntiekMemoryServer,
    ResourceContent,
    ResourceError,
    ToolResult,
    serve_stdio,
)

_TRUSTED_FALSE = '<antiek:content trusted="false">{}</antiek:content>'

# Content classes whose chunk BODY this public MCP surface may return: in the
# public graph (ad_inventory.attribution) AND full-text servable (constants §I).
PUBLIC_SURFACE_CONTENT_CLASSES: frozenset[str] = frozenset(
    PUBLIC_GRAPH_CONTENT_CLASSES & SERVABLE_CONTENT_CLASSES
)
# The §9.0 gate (non_privileged_chunk_sql_clause) only removes restricted and
# personal_reading bodies: it still passes every user's private user_owned
# chunks and legacy NULL-rights rows. This allowlist is what makes the surface
# public; NULL is excluded because full-text serving is deny-by-default.
assert PUBLIC_SURFACE_CONTENT_CLASSES.isdisjoint(
    RESTRICTED_CONTENT_CLASSES | PERSONAL_ONLY_CONTENT_CLASSES
), "public MCP chunk bodies must exclude restricted and personal content"
assert PRIVATE_GRAPH_CONTENT_CLASS not in PUBLIC_SURFACE_CONTENT_CLASSES, (
    "public MCP chunk bodies must exclude private graph content"
)

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
    embedding_model: Callable[[], EmbeddingModel] = default_embedding_provider,
) -> tuple[dict[str, Callable[..., ToolResult]], Callable[[str], ResourceContent | None]]:
    """Build handler closures bound to *db_path*.

    ``embedding_model`` is a zero-argument factory for the ranked-retrieval
    model. Production resolves the process-singleton provider used to embed
    stored chunks; tests inject a deterministic stub. It is constructed lazily
    on the first search call so the server still starts where the model is not
    installed, and an owner who owns no documents gets an honest empty answer
    without ever loading it.
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
    def search_public(args: dict[str, Any]) -> ToolResult:
        """Rank public chunks through search()'s §9.0 retrieval gate.

        The public content-class allowlist also excludes user_owned and NULL
        rights state. Read full text only for ranked hits, then check the
        canonical body predicate and book takedown flag before returning it.
        The prompt-injection envelope is applied after those rights checks.
        """
        query = args["query"]
        top_k = args.get("top_k", 5)
        con = connect_read(db_path)
        try:
            hits = search(
                con,
                query,
                model=_model(),
                top_k=top_k,
                policy_tag="attribution_eligible",
                content_classes=PUBLIC_SURFACE_CONTENT_CLASSES,
            )["results"]
            rows: dict[str, tuple[str, str | None, bool]] = {}
            if hits:
                placeholders = ",".join("?" for _ in hits)
                rows = {
                    str(row[0]): (str(row[1]), row[2], bool(row[3]))
                    for row in con.execute(
                        "SELECT c.chunk_id, c.text, d.content_class, "
                        "COALESCE(b.taken_down, FALSE) "
                        "FROM chunks c JOIN documents d ON c.document_id = d.document_id "
                        "LEFT JOIN book_assets b ON b.document_id = d.document_id "
                        f"WHERE c.chunk_id IN ({placeholders})",
                        [hit["chunk_id"] for hit in hits],
                    ).fetchall()
                }
        finally:
            con.close()
        chunks = []
        for hit in hits:
            row = rows.get(hit["chunk_id"])
            if row is None:
                continue
            full_text, content_class, taken_down = row
            # Defence in depth over the SQL scope: a book_assets takedown can
            # sit on a document whose class still reads public_domain, and the
            # canonical body predicate is the one that decides that case.
            withheld, _label = is_chunk_body_withheld(content_class, taken_down=taken_down)
            if withheld or content_class not in PUBLIC_SURFACE_CONTENT_CLASSES:
                continue
            chunks.append({
                "chunk_id": hit["chunk_id"],
                "text": _TRUSTED_FALSE.format(full_text),
                "title": hit["document_title"],
                "source_tier": hit["source_tier"],
                "similarity": hit["similarity"],
            })
        return ToolResult(content=[{
            "type": "text",
            "text": json.dumps({"chunks": chunks, "query": query}),
        }])

    # ── cite_source ───────────────────────────────────────────────
    def cite_source(args: dict[str, Any]) -> ToolResult:
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
    def record_attribution(args: dict[str, Any]) -> ToolResult:
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
                if len(parts) != 5 or parts[:3] != ["antiek:", "", "books"]:
                    return None
                isbn, chunk_id = parts[3:]
                if not isbn or not chunk_id:
                    return None
                row = con.execute(
                    """
                    SELECT c.chunk_id, c.text, c.document_id, d.title,
                           d.content_class, d.ip_holder_id, d.metadata,
                           COALESCE(b.taken_down, FALSE)
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    LEFT JOIN book_assets b ON b.document_id = d.document_id
                    WHERE c.chunk_id = ?
                    """,
                    [chunk_id],
                ).fetchone()
                if row is None:
                    return None
                recorded_isbns: set[str] = set()
                try:
                    metadata = json.loads(row[6]) if row[6] else None
                except (ValueError, TypeError):
                    metadata = None
                if isinstance(metadata, dict):
                    for key in ("isbn", "isbn13", "ISBN"):
                        value = metadata.get(key)
                        if isinstance(value, str):
                            normalized = normalize_isbn(value)
                            if normalized is not None:
                                recorded_isbns.add(normalized)
                if isbn != row[2] and normalize_isbn(isbn) not in recorded_isbns:
                    return None
                content_class = row[4]
                if content_class == PRIVATE_GRAPH_CONTENT_CLASS:
                    return None
                taken_down = bool(row[7])
                withheld, label = is_chunk_body_withheld(content_class, taken_down=taken_down)
                if withheld or content_class not in PUBLIC_SURFACE_CONTENT_CLASSES:
                    raise ResourceError(
                        LICENSING_REQUIRED,
                        "Licensing required",
                        {
                            "uri": uri,
                            "chunk_id": row[0],
                            "document_id": row[2],
                            "title": row[3],
                            "servability": label if withheld else servability_of(content_class).value,
                        },
                    )
                return ResourceContent(
                    uri=uri,
                    mime_type="application/json",
                    text=json.dumps({
                        "chunk_id": row[0],
                        "isbn": isbn,
                        "document_id": row[2],
                        "title": row[3],
                        "ip_holder_id": row[5],
                        "servability": servability_of(content_class, taken_down=False).value,
                        "text": _TRUSTED_FALSE.format(row[1]),
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
