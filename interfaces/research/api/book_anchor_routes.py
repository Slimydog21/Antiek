"""Book anchor routes (anchor-first SPR-03).

Owner-scoped anchored-highlight API, a NEW router module (not more mass in
books.py's 3062 lines) following its conventions: register_*_routes from
create_app, _reader_owner_id / _owner_read_policy_tag for the owner
boundary (books.py:106-154), _resolve_db_path for the initialized store.

  POST   /books/{document_id}/anchors                 pin (server-resolved)
  GET    /books/{document_id}/anchors                 list + live validity
  DELETE /books/{document_id}/anchors/{anchor_id}     owner-scoped, idempotent
  GET    /books/{document_id}/anchor-map              public-gated manifest
  GET    /books/{document_id}/anchor-map/owner        owner-readable manifest

Rights truth stays server-side everywhere: the pin's owner and the
quote-persistence decision come from the server's own rows, never from the
request body; a non-servable document's quote fields are DROPPED at the
persistence boundary regardless of what the client sent. The manifest never
carries body text — ids, offsets, hashes only.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from interfaces.research.api.books import (
    _OWNER_READ_POLICY_TAG,
    _owner_read_policy_tag,
    _reader_owner_id,
    _resolve_db_path,
)
from substrate.books.highlights.anchor_map import build_anchor_map
from substrate.books.highlights.resolve import (
    PinResolutionError,
    document_servable,
    reanchor_document,
    resolve_pin,
)
from substrate.books.highlights.schema import highlights_table_exists
from substrate.books.highlights.store import (
    AnchorRow,
    CreatePinCommand,
    HighlightSource,
    HighlightsStore,
)

_VALID_SOURCES = {str(s) for s in HighlightSource}


class AnchorIn(BaseModel):
    quote: str | None = None
    prefix: str = ""
    suffix: str = ""
    page_index_hint: int | None = None
    source: str = "pin"


class AnchorOut(BaseModel):
    anchor_id: str
    document_id: str
    anchor: dict[str, Any]
    servable_at_pin: bool
    selection_text_sha256: str
    page_index_hint: int | None
    source: str
    status: str
    exact_valid: bool
    """The SPR-04 seam — present from day one, null until a thread links."""
    investigation_id: str | None
    created_at: str
    updated_at: str


class AnchorListOut(BaseModel):
    document_id: str
    anchors: list[AnchorOut]
    count: int


class AnchorMapChunkOut(BaseModel):
    chunk_id: str
    section_path: str | None
    body_start: int
    body_end: int
    node_text_sha256: str


class AnchorMapOut(BaseModel):
    document_id: str
    chunks: list[AnchorMapChunkOut]
    complete: bool


def _document_exists(con: Any, document_id: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
        ).fetchone()
        is not None
    )


def _anchor_out(row: AnchorRow, *, exact_valid: bool) -> AnchorOut:
    servable = row.servable_at_pin
    return AnchorOut(
        anchor_id=row.anchor_id,
        document_id=row.document_id,
        anchor={
            "normalization": row.anchor.normalization,
            "node_id": row.anchor.node_id,
            "node_text_sha256": row.anchor.node_text_sha256,
            "start_scalar": row.anchor.start_scalar,
            "end_scalar": row.anchor.end_scalar,
            # Metadata-only rows surface the text fields as null, matching
            # what the row lawfully holds.
            "quote": row.anchor.quote if servable else None,
            "prefix": row.anchor.prefix if servable else None,
            "suffix": row.anchor.suffix if servable else None,
        },
        servable_at_pin=row.servable_at_pin,
        selection_text_sha256=row.selection_text_sha256,
        page_index_hint=row.page_index_hint,
        source=str(row.source),
        status=str(row.status),
        exact_valid=exact_valid,
        investigation_id=row.investigation_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def register_book_anchor_routes(app: FastAPI) -> None:
    """Mount the anchored-highlight routes. Mirrors register_book_routes —
    one call from create_app."""

    @app.post(
        "/books/{document_id}/anchors",
        response_model=AnchorOut,
        status_code=201,
        tags=["books", "anchors"],
    )
    def create_anchor(document_id: str, body: AnchorIn, request: Request) -> AnchorOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        if body.source not in _VALID_SOURCES:
            raise HTTPException(status_code=422, detail=f"anchor_source_invalid: {body.source}")
        if body.quote is None or not body.quote.strip():
            raise HTTPException(
                status_code=422,
                detail="anchor_quote_required: the server locates the passage from the quote",
            )
        db = _resolve_db_path()
        with connect_write(db, purpose="books/anchors/create") as con:
            if not _document_exists(con, document_id):
                raise HTTPException(status_code=404, detail="book_not_found")
            try:
                resolution = resolve_pin(
                    con,
                    document_id=document_id,
                    quote=body.quote,
                    prefix=body.prefix,
                    suffix=body.suffix,
                    page_index_hint=body.page_index_hint,
                )
            except PinResolutionError as exc:
                raise HTTPException(
                    status_code=422, detail=f"anchor_resolution_{exc.reason}: {exc}"
                ) from exc
            # The servability decision is the SERVER's, from its own rights
            # rows — a non-servable document drops the quote fields at the
            # persistence boundary regardless of what the client sent.
            servable = document_servable(con, document_id)
            row = HighlightsStore().create_pin(
                con,
                CreatePinCommand(
                    owner_user_id=owner,
                    document_id=document_id,
                    anchor=resolution.anchor,
                    servable_at_pin=servable,
                    source=HighlightSource(body.source),
                    page_index_hint=resolution.page_index_hint,
                ),
            )
        return _anchor_out(row, exact_valid=True)

    @app.get(
        "/books/{document_id}/anchors",
        response_model=AnchorListOut,
        tags=["books", "anchors"],
    )
    def list_anchors(document_id: str, request: Request) -> AnchorListOut:
        from runtime.db_lock import connect_read, connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        store = HighlightsStore()

        def _exact_map(con: Any, rows: list[AnchorRow]) -> dict[str, bool]:
            import hashlib

            from substrate.feedback.domain import normalize_node_text

            out: dict[str, bool] = {}
            chunk_hashes: dict[str, str] = {}
            for row in rows:
                node_id = row.anchor.node_id
                if node_id not in chunk_hashes:
                    hit = con.execute(
                        "SELECT text FROM chunks WHERE chunk_id = ? LIMIT 1",
                        [node_id],
                    ).fetchone()
                    chunk_hashes[node_id] = (
                        ""
                        if hit is None
                        else hashlib.sha256(
                            normalize_node_text(str(hit[0])).encode("utf-8")
                        ).hexdigest()
                    )
                out[row.anchor_id] = chunk_hashes[node_id] == row.anchor.node_text_sha256
            return out

        con = connect_read(db)
        try:
            if not _document_exists(con, document_id):
                raise HTTPException(status_code=404, detail="book_not_found")
            if not highlights_table_exists(con):
                return AnchorListOut(document_id=document_id, anchors=[], count=0)
            rows = [
                r for r in store.list_for_document(con, document_id) if r.owner_user_id == owner
            ]
            exact = _exact_map(con, rows)
        finally:
            con.close()

        if not all(exact.values()):
            # The books.py:247 precedent (an audit write on a read path):
            # escalate to the full re-resolution pass under the write lock
            # ONLY when a live exact check fails, then re-read and re-check.
            with connect_write(db, purpose="books/anchors/reanchor-on-read") as wcon:
                reanchor_document(wcon, document_id=document_id)
            rcon = connect_read(db)
            try:
                rows = [
                    r
                    for r in store.list_for_document(rcon, document_id)
                    if r.owner_user_id == owner
                ]
                exact = _exact_map(rcon, rows)
            finally:
                rcon.close()

        return AnchorListOut(
            document_id=document_id,
            anchors=[_anchor_out(r, exact_valid=exact[r.anchor_id]) for r in rows],
            count=len(rows),
        )

    @app.delete(
        "/books/{document_id}/anchors/{anchor_id}",
        status_code=204,
        tags=["books", "anchors"],
    )
    def delete_anchor(document_id: str, anchor_id: str, request: Request) -> None:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="books/anchors/delete") as con:
            # Owner-scoped AND idempotent: deleting twice (or deleting an
            # anchor that was never yours) is a 204, never a 404 — the only
            # removal path reveals nothing about what exists.
            HighlightsStore().delete(con, anchor_id, owner)
        return

    @app.get(
        "/books/{document_id}/anchor-map",
        response_model=AnchorMapOut,
        tags=["books", "anchors"],
    )
    def get_anchor_map(document_id: str) -> AnchorMapOut:
        from runtime.db_lock import connect_read
        from substrate.books.serve_guard import serve_full_text_guarded

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            result = serve_full_text_guarded(con, document_id)
            if not result.found:
                raise HTTPException(status_code=404, detail="book_not_found")
            # Gated EXACTLY like the public body serve: full text or nothing.
            if not result.servable or result.full_text is None:
                raise HTTPException(status_code=403, detail="anchor_map_gated")
            manifest = build_anchor_map(con, document_id=document_id, served_text=result.full_text)
        finally:
            con.close()
        return AnchorMapOut(
            document_id=document_id,
            chunks=[
                AnchorMapChunkOut(
                    chunk_id=c.chunk_id,
                    section_path=c.section_path,
                    body_start=c.body_start,
                    body_end=c.body_end,
                    node_text_sha256=c.node_text_sha256,
                )
                for c in manifest.chunks
            ],
            complete=manifest.complete,
        )

    @app.get(
        "/books/{document_id}/anchor-map/owner",
        response_model=AnchorMapOut,
        tags=["books", "anchors"],
    )
    def get_owner_anchor_map(document_id: str, request: Request) -> AnchorMapOut:
        """The owner-readable manifest — mirrors get_owner_book_full_text:
        the hardened owner signal admits personal-reading offsets without
        claiming the book is publicly servable."""
        from runtime.db_lock import connect_read
        from substrate.books.serve_guard import serve_full_text_guarded

        if _owner_read_policy_tag(request) != _OWNER_READ_POLICY_TAG:
            raise HTTPException(status_code=403, detail="owner_read_required")
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            result = serve_full_text_guarded(con, document_id, owner=True)
            if not result.found:
                raise HTTPException(status_code=404, detail="book_not_found")
            if result.full_text is None:
                raise HTTPException(status_code=403, detail="anchor_map_gated")
            manifest = build_anchor_map(con, document_id=document_id, served_text=result.full_text)
        finally:
            con.close()
        return AnchorMapOut(
            document_id=document_id,
            chunks=[
                AnchorMapChunkOut(
                    chunk_id=c.chunk_id,
                    section_path=c.section_path,
                    body_start=c.body_start,
                    body_end=c.body_end,
                    node_text_sha256=c.node_text_sha256,
                )
                for c in manifest.chunks
            ],
            complete=manifest.complete,
        )
