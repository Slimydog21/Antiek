"""Document-fork routes (thread-merge + document fork SPR-01).

The fork primitive's API, owner-scoped on the unit conventions
(_reader_owner_id resolves from middleware state, never request data;
_resolve_db_path for the initialized store; register_*_routes from
create_app):

  POST /books/{document_id}/forks   — create a fork. Two lawful shapes:
      copy mode (default): the parent's body is copied in full into a new
        library document registered through the rights chokepoint;
      adopt mode (``derived_document_id`` present): the reformat flow's
        "officially fork" — a provisional derived document is promoted to
        the named fork, carrying its generation record ref.
      Both are idempotent on the client-supplied ``operation_id``.
  GET  /books/{document_id}/forks   — forks-of-this, plus ``forked_from``:
      the lineage row where THIS document is the fork (the parent
      direction), so a reader opening either side learns the whole
      depth-1 neighbourhood in one call.
  GET  /forks/{fork_id}             — the row, with its parent.
  GET  /forks/{fork_id}/lineage     — both directions, one row per hop.

Fork-of-fork is depth-1 this wave: refused with a 409 that NAMES the limit.
A parent whose rights class grants no transformation right
(rights/register.py's derivation rule — gated classes) is a 422, never a
fork. No route here serves a body: serving stays behind
serve_full_text_guarded alone (the spec's rights-trust gate).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.documents.forks import (
    LOCATOR_MAX_CHARS,
    NOTE_MAX_CHARS,
    OPERATION_ID_MAX_CHARS,
    DocumentForkRow,
    DocumentForkStore,
    ForkConflictError,
    ForkDepthLimitError,
    forks_table_exists,
)
from substrate.rights.register import DerivationRefusedError


class ForkIn(BaseModel):
    """The fork request. ``operation_id`` is the idempotency key: a replay
    returns the original fork (200), never a second one."""

    operation_id: str = Field(min_length=1, max_length=OPERATION_ID_MAX_CHARS)
    note: str | None = Field(default=None, max_length=NOTE_MAX_CHARS)
    """A page index or unit-1 anchor ref marking where the fork was taken;
    null is the honest unknown."""
    fork_point_locator: str | None = Field(default=None, max_length=LOCATOR_MAX_CHARS)
    """Adopt mode: promote this existing provisional derived document
    instead of copying the parent's body."""
    derived_document_id: str | None = Field(default=None, max_length=200)
    """The reformat generation record the adopt mode carries (validated
    against the provenance store when given)."""
    generation_id: str | None = Field(default=None, max_length=200)


class ForkOut(BaseModel):
    fork_id: str
    parent_document_id: str
    fork_document_id: str
    operation_id: str
    fork_point_locator: str | None
    note: str | None
    generation_id: str | None
    parent_body_sha256: str
    fork_body_sha256: str
    created_at: str
    """Joined for display (the badge + provenance header), null when the
    parent has no title. Never a raw body."""
    parent_title: str | None


class ForksOfOut(BaseModel):
    forks: list[ForkOut]
    forked_from: ForkOut | None


class ForkHopOut(BaseModel):
    """One lineage hop: the neighbour's fork row and document title."""

    fork_id: str
    document_id: str
    title: str | None
    created_at: str


class ForkLineageOut(BaseModel):
    fork_id: str
    parent: ForkHopOut | None
    children: list[ForkHopOut]


def _titles(con: Any, document_ids: list[str]) -> dict[str, str | None]:
    """Titles for a handful of document ids, one query."""
    if not document_ids:
        return {}
    marks = ", ".join("?" for _ in document_ids)
    rows = con.execute(
        f"SELECT document_id, title FROM documents WHERE document_id IN ({marks})",
        document_ids,
    ).fetchall()
    return {str(r[0]): (None if r[1] is None else str(r[1])) for r in rows}


def _out(row: DocumentForkRow, titles: dict[str, str | None]) -> ForkOut:
    return ForkOut(
        fork_id=row.fork_id,
        parent_document_id=row.parent_document_id,
        fork_document_id=row.fork_document_id,
        operation_id=row.operation_id,
        fork_point_locator=row.fork_point_locator,
        note=row.note,
        generation_id=row.generation_id,
        parent_body_sha256=row.parent_body_sha256,
        fork_body_sha256=row.fork_body_sha256,
        created_at=row.created_at,
        parent_title=titles.get(row.parent_document_id),
    )


def _hop(row: DocumentForkRow, document_id: str, titles: dict[str, str | None]) -> ForkHopOut:
    return ForkHopOut(
        fork_id=row.fork_id,
        document_id=document_id,
        title=titles.get(document_id),
        created_at=row.created_at,
    )


def _document_owned(con: Any, owner: str, document_id: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? AND owner_user_id = ? "
            "LIMIT 1",
            [document_id, owner],
        ).fetchone()
        is not None
    )


def register_fork_routes(app: FastAPI) -> None:
    """Mount the fork routes. Mirrors register_reading_state_routes — one
    call from create_app."""

    @app.post(
        "/books/{document_id}/forks",
        response_model=ForkOut,
        status_code=201,
        tags=["books", "forks"],
    )
    def create_fork(
        document_id: str, body: ForkIn, request: Request, response: Response
    ) -> ForkOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        store = DocumentForkStore()
        with connect_write(db, purpose="books/forks/create") as con:
            if not _document_owned(con, owner, document_id):
                raise HTTPException(status_code=404, detail="book_not_found")
            try:
                if body.derived_document_id is not None:
                    row, created = store.adopt_fork(
                        con,
                        owner_user_id=owner,
                        parent_document_id=document_id,
                        derived_document_id=body.derived_document_id,
                        generation_id=body.generation_id,
                        operation_id=body.operation_id,
                        note=body.note,
                        fork_point_locator=body.fork_point_locator,
                    )
                else:
                    row, created = store.create_copy_fork(
                        con,
                        owner_user_id=owner,
                        parent_document_id=document_id,
                        operation_id=body.operation_id,
                        note=body.note,
                        fork_point_locator=body.fork_point_locator,
                    )
            except KeyError as missing:
                raise HTTPException(
                    status_code=404, detail="book_not_found"
                ) from missing
            except ForkDepthLimitError as depth:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"fork_depth_limit: {depth} — fork-of-fork is "
                        "depth-1 this wave"
                    ),
                ) from depth
            except ForkConflictError as conflict:
                raise HTTPException(
                    status_code=409, detail=f"fork_conflict: {conflict}"
                ) from conflict
            except DerivationRefusedError as refused:
                raise HTTPException(
                    status_code=422, detail=f"fork_rights_refused: {refused}"
                ) from refused
            except ValueError as invalid:
                raise HTTPException(
                    status_code=422, detail=str(invalid)
                ) from invalid
            titles = _titles(con, [row.parent_document_id])
        # An idempotent replay is a 200: the fork already existed.
        if not created:
            response.status_code = 200
        return _out(row, titles)

    @app.get(
        "/books/{document_id}/forks",
        response_model=ForksOfOut,
        tags=["books", "forks"],
    )
    def list_forks(document_id: str, request: Request) -> ForksOfOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            if not _document_owned(con, owner, document_id):
                raise HTTPException(status_code=404, detail="book_not_found")
            store = DocumentForkStore()
            forks = store.forks_of(con, owner_user_id=owner, document_id=document_id)
            forked_from = store.forked_from(
                con, owner_user_id=owner, document_id=document_id
            )
            wanted = [row.parent_document_id for row in forks]
            if forked_from is not None:
                wanted.append(forked_from.parent_document_id)
            titles = _titles(con, wanted)
        finally:
            con.close()
        return ForksOfOut(
            forks=[_out(row, titles) for row in forks],
            forked_from=None if forked_from is None else _out(forked_from, titles),
        )

    @app.get(
        "/forks/{fork_id}",
        response_model=ForkOut,
        tags=["forks"],
    )
    def get_fork(fork_id: str, request: Request) -> ForkOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            row = DocumentForkStore().get(con, owner_user_id=owner, fork_id=fork_id)
            titles = (
                _titles(con, [row.parent_document_id]) if row is not None else {}
            )
        finally:
            con.close()
        if row is None:
            raise HTTPException(status_code=404, detail="fork_not_found")
        return _out(row, titles)

    @app.get(
        "/forks/{fork_id}/lineage",
        response_model=ForkLineageOut,
        tags=["forks"],
    )
    def get_fork_lineage(fork_id: str, request: Request) -> ForkLineageOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            found = DocumentForkStore().lineage(con, owner_user_id=owner, fork_id=fork_id)
            if found is None:
                titles: dict[str, str | None] = {}
            else:
                row, children = found
                titles = _titles(
                    con,
                    [row.parent_document_id]
                    + [child.fork_document_id for child in children],
                )
        finally:
            con.close()
        if found is None:
            raise HTTPException(status_code=404, detail="fork_not_found")
        row, children = found
        return ForkLineageOut(
            fork_id=row.fork_id,
            parent=_hop(row, row.parent_document_id, titles),
            children=[
                _hop(child, child.fork_document_id, titles) for child in children
            ],
        )


__all__ = ["register_fork_routes", "forks_table_exists"]
