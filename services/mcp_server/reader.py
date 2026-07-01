"""Read-only DuckDB access for the MCP server.

Respects the single-writer invariant (§16): every connection opened here
is read-only via ``runtime.db_lock.connect_read``. No writes, no lock
acquisition.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from importlib import import_module
from typing import Any, Protocol, cast

import duckdb

from .errors import (
    BookChunkNotFoundError,
    LicensingRequiredError,
    NoteNotFoundError,
    PublicNoteNotFoundError,
)

_USER_REGISTERED = "user.registered"
_USER_IDENTITY_ATTACHED = "user.identity_attached"
_GRAPH_SCOPE_CHANGED = "graph.scope_changed"


class _ServedFullText(Protocol):
    full_text: str | None
    tier: str | None
    ad_eligible: bool
    canonical_url: str | None
    license: str | None


def connect_readonly(db_path: str) -> duckdb.DuckDBPyConnection:
    """Open a read-only substrate connection without importing legacy types.

    ``runtime.db_lock`` still carries repo-wide mypy baseline debt. The MCP
    package owns a narrow typed adapter so its strict gate covers MCP code
    instead of inheriting unrelated substrate typing work.
    """
    module = import_module("runtime.db_lock")
    connect_read = cast(
        Callable[[str], duckdb.DuckDBPyConnection],
        module.connect_read,
    )
    return connect_read(db_path)


def _default_events_dir() -> str:
    module = import_module("substrate.event_log")
    default_events_dir = cast(Callable[[], str], module.default_events_dir)
    return default_events_dir()


def _trajectory(investigation_id: str, *, events_dir: str | None = None) -> list[dict[str, Any]]:
    module = import_module("substrate.event_log")
    trajectory = cast(
        Callable[..., list[dict[str, Any]]],
        module.trajectory,
    )
    return trajectory(investigation_id, events_dir=events_dir)


def _serve_full_text_guarded(
    con: duckdb.DuckDBPyConnection,
    document_id: str,
) -> _ServedFullText:
    module = import_module("substrate.books.serve_guard")
    serve = cast(
        Callable[[duckdb.DuckDBPyConnection, str], _ServedFullText],
        module.serve_full_text_guarded,
    )
    return serve(con, document_id)


def _is_chunk_body_withheld(content_class: str | None) -> tuple[bool, str | None]:
    module = import_module("substrate.graph.retrieval_gate")
    predicate = cast(
        Callable[[str | None], tuple[bool, str | None]],
        module.is_chunk_body_withheld,
    )
    return predicate(content_class)


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


def _resolve_events_dir() -> str:
    """Resolve the Antiek event-log directory for read-only MCP resources."""
    return _default_events_dir()


def _iter_event_log_rows(*, events_dir: str | None = None) -> list[dict[str, Any]]:
    """Read every live/sealed trajectory row in the event-log directory."""
    root = events_dir or _resolve_events_dir()
    if not os.path.isdir(root):
        return []

    rows: list[dict[str, Any]] = []
    investigation_ids: set[str] = set()
    for name in os.listdir(root):
        if name.endswith(".jsonl"):
            investigation_ids.add(name[: -len(".jsonl")])
        elif name.endswith(".parquet"):
            investigation_ids.add(name[: -len(".parquet")])

    for investigation_id in sorted(investigation_ids):
        rows.extend(_trajectory(investigation_id, events_dir=root))

    rows.sort(key=lambda row: (row.get("emitted_at") or "", row.get("event_id") or ""))
    return rows


_ACCOUNT_EVENT_TYPES: frozenset[str] = frozenset({
    _USER_REGISTERED,
    _USER_IDENTITY_ATTACHED,
    _GRAPH_SCOPE_CHANGED,
})


def list_account_events(
    user_id: str,
    *,
    events_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Return typed account lifecycle/scope events for one user.

    Sprint 19 keeps this read-only and event-log-backed: it lets MCP clients
    reconstruct account and graph-scope state without enabling auth,
    per-user routing, or the Sprint 22+ multi-user pivot.
    """
    user_id = user_id.strip()
    if not user_id:
        raise ValueError("user_id is required")

    matched: list[dict[str, Any]] = []
    for event in _iter_event_log_rows(events_dir=events_dir):
        action_type = event.get("action_type")
        if action_type not in _ACCOUNT_EVENT_TYPES:
            continue
        payload = event.get("payload") or {}
        if not isinstance(payload, dict) or payload.get("user_id") != user_id:
            continue
        matched.append({
            "event_id": event.get("event_id"),
            "investigation_id": event.get("investigation_id"),
            "action_type": action_type,
            "emitted_at": event.get("emitted_at"),
            "payload": payload,
        })
    return matched


def get_account_scope(
    user_id: str,
    *,
    events_dir: str | None = None,
) -> dict[str, Any]:
    """Reconstruct the latest account/scope summary from typed events."""
    events = list_account_events(user_id, events_dir=events_dir)
    registered = next(
        (event for event in events if event["action_type"] == _USER_REGISTERED),
        None,
    )
    identities = [
        event["payload"]
        for event in events
        if event["action_type"] == _USER_IDENTITY_ATTACHED
    ]
    scope_events = [
        event
        for event in events
        if event["action_type"] == _GRAPH_SCOPE_CHANGED
    ]
    latest_scope = scope_events[-1] if scope_events else None

    return {
        "user_id": user_id,
        "registered": registered is not None,
        "registered_at": (
            registered["payload"].get("registered_at") if registered is not None else None
        ),
        "auth_provider": (
            registered["payload"].get("auth_provider") if registered is not None else None
        ),
        "identity_count": len(identities),
        "identities": identities,
        "current_scope": (
            latest_scope["payload"].get("new_scope") if latest_scope is not None else None
        ),
        "scope_changed_at": (
            latest_scope["payload"].get("changed_at") if latest_scope is not None else None
        ),
        "scope_event_id": latest_scope["event_id"] if latest_scope is not None else None,
        "event_count": len(events),
    }


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


def get_public_note(
    con: duckdb.DuckDBPyConnection,
    note_id: str,
) -> dict[str, Any]:
    """Fetch a public note by note_id with attribution metadata.

    A "public note" is a document accessible on a non-privileged retrieval
    path. Per §9.0 retrieval-time gating, documents with content_class in
    {restricted_pending_opt_in, personal_reading} raise
    ``LicensingRequiredError``.

    Returns note content + attribution-routing metadata (ip_holder_id,
    content_class).

    Raises:
        PublicNoteNotFoundError: When no matching document exists.
        LicensingRequiredError: When the note's content_class is gated.
    """
    row = con.execute(
        """
        SELECT document_id, title, author, metadata,
               source_tier, document_type, owner_user_id,
               content_class, ip_holder_id, acquired_at
        FROM documents
        WHERE document_id = ?
        """,
        [note_id],
    ).fetchone()

    if row is None:
        raise PublicNoteNotFoundError(note_id)

    (doc_id, title, author, metadata_json, tier, doc_type,
     owner, content_class, ip_holder_id, acquired_at) = row

    served = _serve_full_text_guarded(con, note_id)
    if served.full_text is None:
        raise LicensingRequiredError(note_id, content_class)

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
        "content": served.full_text,
        "metadata": metadata,
        "source_tier": tier,
        "document_type": doc_type,
        "owner_user_id": owner,
        "content_class": content_class,
        "ip_holder_id": ip_holder_id,
        "acquired_at": acquired_at.isoformat() if acquired_at else None,
        "tier": served.tier,
        "ad_eligible": served.ad_eligible,
        "canonical_url": served.canonical_url,
        "license": served.license,
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


def get_book_chunk(
    con: duckdb.DuckDBPyConnection,
    isbn: str,
    chunk_id: str,
) -> dict[str, Any]:
    """Fetch a book chunk by ISBN + chunk_id with §9.0 retrieval-time gating.

    Looks up the document by ISBN (stored in ``documents.metadata`` JSON),
    then fetches the matching chunk from the ``chunks`` table. Applies
    ``is_chunk_body_withheld`` to enforce the non-privileged gate:
    public-domain books return content; gated books raise
    ``LicensingRequiredError``.

    Raises:
        BookChunkNotFoundError: When the ISBN has no matching document or
            the chunk_id does not exist for that document.
        LicensingRequiredError: When the book's content_class is gated on
            a non-privileged retrieval path (§9.0).
    """
    doc_row = con.execute(
        """
        SELECT document_id, title, author, content_class, ip_holder_id
        FROM documents
        WHERE metadata IS NOT NULL
          AND json_extract_string(metadata, '$.isbn') = ?
        """,
        [isbn],
    ).fetchone()

    if doc_row is None:
        raise BookChunkNotFoundError(isbn, chunk_id)

    doc_id, title, author, content_class, ip_holder_id = doc_row

    withheld, _label = _is_chunk_body_withheld(content_class)
    if withheld:
        raise LicensingRequiredError(chunk_id, content_class)

    chunk_row = con.execute(
        """
        SELECT chunk_id, section_path, text, token_count
        FROM chunks
        WHERE chunk_id = ? AND document_id = ?
        """,
        [chunk_id, doc_id],
    ).fetchone()

    if chunk_row is None:
        raise BookChunkNotFoundError(isbn, chunk_id)

    return {
        "chunk_id": chunk_row[0],
        "document_id": doc_id,
        "isbn": isbn,
        "title": title,
        "author": author,
        "section_path": chunk_row[1],
        "text": chunk_row[2],
        "token_count": chunk_row[3],
        "content_class": content_class,
        "ip_holder_id": ip_holder_id,
    }
