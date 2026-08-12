"""Antiek Memory MCP server — subprocess entry point.

Run with: python -m tools.antiek_memory

Reads ANTIEK_DUCKDB_PATH from the environment (falls back to
~/.antiek/research_graph.duckdb).  Initialises the schema on cold
start, wires the four canonical tool handlers + resource handler
against the real substrate, and serves JSON-RPC over stdio.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.graph import default_db_path

from .server import (
    AntiekMemoryServer,
    CANONICAL_TOOLS,
    ResourceContent,
    ToolResult,
    serve_stdio,
)

_TRUSTED_FALSE = '<antiek:content trusted="false">{}</antiek:content>'


def _make_handlers(db_path: str):
    """Build handler closures bound to *db_path*."""

    # ── search_personal ───────────────────────────────────────────
    def search_personal(args: dict) -> ToolResult:
        query = args["query"]
        top_k = args.get("top_k", 5)
        con = connect_read(db_path)
        try:
            rows = con.execute(
                """
                SELECT c.chunk_id, c.text, d.title, d.source_tier, d.owner_user_id
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                WHERE d.owner_user_id = ?
                ORDER BY c.chunk_index
                LIMIT ?
                """,
                ["__operator__", top_k],
            ).fetchall()
        finally:
            con.close()
        chunks = [
            {
                "chunk_id": r[0],
                "text": r[1],
                "title": r[2],
                "source_tier": r[3],
                "owner_user_id": r[4],
            }
            for r in rows
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
        now = datetime.now(timezone.utc).isoformat()
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
    )
    serve_stdio(server)


if __name__ == "__main__":
    main()
