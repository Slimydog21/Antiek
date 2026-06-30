"""Read-only DuckDB access for the MCP server.

Respects the single-writer invariant (§16): every connection opened here
is read-only via ``runtime.db_lock.connect_read``. No writes, no lock
acquisition.
"""

from __future__ import annotations

import json
import os
from typing import Any

import duckdb

from .errors import NoteNotFoundError


def _resolve_db_path() -> str:
    """Resolve the DuckDB path from environment.

    Follows the same convention as the rest of the substrate:
    ``ANTIEK_DUCKDB_PATH`` is the canonical env var.
    """
    path = os.environ.get("ANTIEK_DUCKDB_PATH")
    if not path:
        raise RuntimeError(
            "ANTIEK_DUCKDB_PATH is not set. "
            "Point it at the Antiek DuckDB file."
        )
    return path


def get_note(
    con: duckdb.DuckDBPyConnection,
    user_id: str,
    note_id: str,
) -> dict[str, Any]:
    """Fetch a private note by user_id + note_id from the documents table.

    A "private note" is a document whose ``document_id`` matches ``note_id``
    and whose ``owner_user_id`` matches ``user_id``. Returns content + metadata.

    Raises ``NoteNotFoundError`` when no matching document exists.
    """
    row = con.execute(
        """
        SELECT document_id, title, author, raw_text, metadata,
               source_tier, document_type, owner_user_id,
               content_class, acquired_at
        FROM documents
        WHERE document_id = ? AND owner_user_id = ?
        """,
        [note_id, user_id],
    ).fetchone()

    if row is None:
        raise NoteNotFoundError(user_id, note_id)

    doc_id, title, author, raw_text, metadata_json, tier, doc_type, owner, content_class, acquired_at = row

    metadata: dict[str, Any] = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except (json.JSONDecodeError, TypeError):
            metadata = {"_raw": metadata_json}

    return {
        "document_id": doc_id,
        "title": title,
        "author": author,
        "content": raw_text,
        "metadata": metadata,
        "source_tier": tier,
        "document_type": doc_type,
        "owner_user_id": owner,
        "content_class": content_class,
        "acquired_at": acquired_at.isoformat() if acquired_at else None,
    }


def list_user_notes(
    con: duckdb.DuckDBPyConnection,
    user_id: str,
) -> list[dict[str, Any]]:
    """List all notes owned by a user. Returns summary rows (no raw_text)."""
    rows = con.execute(
        """
        SELECT document_id, title, author, document_type,
               source_tier, content_class, acquired_at
        FROM documents
        WHERE owner_user_id = ?
        ORDER BY acquired_at DESC
        """,
        [user_id],
    ).fetchall()

    return [
        {
            "document_id": r[0],
            "title": r[1],
            "author": r[2],
            "document_type": r[3],
            "source_tier": r[4],
            "content_class": r[5],
            "acquired_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]
