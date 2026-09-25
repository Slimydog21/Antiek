"""Reading-state routes (reading-global SPR-01) — the reading-state bus.

GET/PUT /books/{document_id}/reading-state: ONE position per owner+document
across every reader mount and device. A NEW router module (not more mass in
books.py's 3062 lines) following book_anchor_routes.py's conventions:
register_*_routes from create_app, _reader_owner_id for the owner boundary
(books.py:140 — ownership resolves from middleware state, never from
request data), _resolve_db_path for the initialized store.

The refs-only contract: the bus carries a page index, an optional unit-1
anchor REF, and an allowlisted prefs map that is EMPTY in v1 — any non-empty
prefs map is a 422 at this boundary AND a CHECK violation at the DB (the
anti-smuggling rule: an unvalidated JSON blob "for later" is how content
leaks into a refs-only store). Concurrency is optimistic: a PUT carries the
revision the client last saw; a stale revision is a 409, never a silent
clobber.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.books.highlights.schema import highlights_table_exists
from substrate.books.reading_state import (
    PREFS_V1_ALLOWLIST,
    ReadingStateRow,
    ReadingStateStore,
    serialize_prefs,
)


class ReadingStateIn(BaseModel):
    page_index: int = Field(ge=0)
    """The optional unit-1 anchor id of the passage the operator last
    engaged — a REF, never the passage."""
    anchor_ref: str | None = Field(default=None, max_length=20)
    prefs: dict[str, Any] = Field(default_factory=dict)
    """Optimistic concurrency: the revision the client last saw (0 for a
    first write — the row does not exist yet)."""
    revision: int = Field(ge=0)


class ReadingStateOut(BaseModel):
    document_id: str
    page_index: int
    anchor_ref: str | None
    prefs: dict[str, Any]
    revision: int
    updated_at: str


def _document_exists(con: Any, document_id: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
        ).fetchone()
        is not None
    )


def _anchor_belongs_to_document(
    con: Any, anchor_ref: str, owner: str, document_id: str
) -> bool:
    if not highlights_table_exists(con):
        return False
    return (
        con.execute(
            "SELECT 1 FROM anchored_highlights WHERE anchor_id = ? "
            "AND owner_user_id = ? AND document_id = ? LIMIT 1",
            [anchor_ref, owner, document_id],
        ).fetchone()
        is not None
    )


def _out(row: ReadingStateRow) -> ReadingStateOut:
    import json

    prefs = json.loads(row.prefs_json)
    return ReadingStateOut(
        document_id=row.document_id,
        page_index=row.page_index,
        anchor_ref=row.anchor_ref,
        prefs=prefs if isinstance(prefs, dict) else {},
        revision=row.revision,
        updated_at=row.updated_at,
    )


def register_reading_state_routes(app: FastAPI) -> None:
    """Mount the reading-state routes. Mirrors register_book_anchor_routes —
    one call from create_app."""

    @app.get(
        "/books/{document_id}/reading-state",
        response_model=ReadingStateOut,
        tags=["books", "reading-state"],
    )
    def get_reading_state(document_id: str, request: Request) -> ReadingStateOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            if not _document_exists(con, document_id):
                raise HTTPException(status_code=404, detail="book_not_found")
            row = ReadingStateStore().get(
                con, owner_user_id=owner, document_id=document_id
            )
        finally:
            con.close()
        if row is None:
            raise HTTPException(status_code=404, detail="reading_state_not_found")
        return _out(row)

    @app.put(
        "/books/{document_id}/reading-state",
        response_model=ReadingStateOut,
        tags=["books", "reading-state"],
    )
    def put_reading_state(
        document_id: str, body: ReadingStateIn, request: Request
    ) -> ReadingStateOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        # The v1 allowlist, enforced at the API: the reader exposes no
        # display prefs today, so ANY non-empty prefs map is refused (the
        # DB CHECK is the backstop for writers that skip this boundary).
        smuggled = sorted(k for k in body.prefs if k not in PREFS_V1_ALLOWLIST)
        if smuggled:
            raise HTTPException(
                status_code=422,
                detail=(
                    "prefs_not_allowlisted: the v1 prefs allowlist is empty; "
                    f"refused keys: {', '.join(smuggled)}"
                ),
            )
        db = _resolve_db_path()
        with connect_write(db, purpose="books/reading-state/put") as con:
            if not _document_exists(con, document_id):
                raise HTTPException(status_code=404, detail="book_not_found")
            if body.anchor_ref is not None and not _anchor_belongs_to_document(
                con, body.anchor_ref, owner, document_id
            ):
                raise HTTPException(status_code=422, detail="anchor_ref_invalid")
            row = ReadingStateStore().put(
                con,
                owner_user_id=owner,
                document_id=document_id,
                page_index=body.page_index,
                anchor_ref=body.anchor_ref,
                prefs_json=serialize_prefs(body.prefs),
                expected_revision=body.revision,
            )
            if row is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "reading_state_stale_revision: the position moved "
                        "elsewhere first — re-read and retry (never a silent clobber)"
                    ),
                )
        return _out(row)
