"""Diligence routes (autonomous-diligence SPR-01) — the flag queue API.

POST /diligence/flags (idempotent) · GET /diligence/queue ·
POST /diligence/flags/{flag_id}/dismiss — owner-scoped throughout, a NEW
router module following book_anchor_routes.py's conventions
(register_*_routes from create_app, _reader_owner_id for the owner
boundary, _resolve_db_path for the initialized store).

WRITE-TIME ref validation (the spec's "only door" rule): the object ref is
resolved against its source BEFORE the row is written, and refs the server
cannot ground are refused with an honest 422 — a distilled-node flag
(open_question/insight) must name a real graph node of the matching type;
a concept flag's key is normalized (case/whitespace-insensitive, so
idempotency holds across variants) and must be non-empty. THE WITHHELD-TEXT
DOOR: a flag on a withheld-source object is lawful exactly because the row
carries the ref and NOTHING else — the gate-safe seed rule is honored at
write time by construction (no text column exists to smuggle through), and
a provided source_document_id must resolve to a real document. The queue
never becomes a side channel for withheld text.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.diligence.schema import NOTE_MAX_CHARS, OBJECT_REF_MAX_CHARS
from substrate.diligence.store import (
    DiligenceFlagRow,
    DiligenceStore,
    normalize_concept_key,
)

_KIND_TO_NODE_TYPE = {"open_question": "question", "insight": "insight"}


class FlagIn(BaseModel):
    kind: Literal["concept", "open_question", "insight"]
    object_ref: str = Field(min_length=1, max_length=OBJECT_REF_MAX_CHARS)
    note: str | None = Field(default=None, max_length=NOTE_MAX_CHARS)
    source_investigation_id: str | None = None
    source_document_id: str | None = None


class FlagOut(BaseModel):
    flag_id: str
    kind: str
    object_ref: str
    note: str | None
    source_investigation_id: str | None
    source_document_id: str | None
    status: str
    spawned_investigation_id: str | None
    created_at: str
    updated_at: str


class FlagListOut(BaseModel):
    flags: list[FlagOut]
    count: int


def _out(row: DiligenceFlagRow) -> FlagOut:
    return FlagOut(
        flag_id=row.flag_id,
        kind=row.kind,
        object_ref=row.object_ref,
        note=row.note,
        source_investigation_id=row.source_investigation_id,
        source_document_id=row.source_document_id,
        status=row.status,
        spawned_investigation_id=row.spawned_investigation_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _ground_ref(con: Any, kind: str, object_ref: str) -> None:
    """Resolve the object ref against its source; 422 with an honest reason
    when the server cannot ground it (write-time validation — the only door
    into the queue)."""
    node_type = _KIND_TO_NODE_TYPE.get(kind)
    if node_type is None:
        return  # a concept key grounds itself (normalized + non-empty)
    hit = con.execute(
        "SELECT 1 FROM nodes WHERE node_id = ? AND node_type = ? LIMIT 1",
        [object_ref, node_type],
    ).fetchone()
    if hit is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"diligence_ref_ungrounded: no {node_type} node with that ref — "
                "the flag was not written"
            ),
        )


def _ground_source_document(con: Any, source_document_id: str | None) -> None:
    if source_document_id is None:
        return
    hit = con.execute(
        "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1",
        [source_document_id],
    ).fetchone()
    if hit is None:
        raise HTTPException(
            status_code=422,
            detail="diligence_source_ungrounded: no document with that id",
        )


def register_diligence_routes(app: FastAPI) -> None:
    """Mount the diligence-queue routes. Mirrors register_book_anchor_routes —
    one call from create_app."""

    @app.post(
        "/diligence/flags",
        response_model=FlagOut,
        tags=["diligence"],
    )
    def create_flag(body: FlagIn, request: Request) -> FlagOut | JSONResponse:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        note = body.note.strip() if body.note else None
        # Concept keys normalize BEFORE grounding/idempotency, so casing and
        # spacing variants converge on ONE row.
        object_ref = (
            normalize_concept_key(body.object_ref)
            if body.kind == "concept"
            else body.object_ref.strip()
        )
        if not object_ref:
            raise HTTPException(
                status_code=422,
                detail="diligence_ref_ungrounded: an empty ref flags nothing",
            )
        db = _resolve_db_path()
        with connect_write(db, purpose="diligence/flags/create") as con:
            _ground_ref(con, body.kind, object_ref)
            _ground_source_document(con, body.source_document_id)
            row, created = DiligenceStore().create_flag(
                con,
                owner_user_id=owner,
                kind=body.kind,
                object_ref=object_ref,
                note=note or None,
                source_investigation_id=body.source_investigation_id,
                source_document_id=body.source_document_id,
            )
        out = _out(row)
        if created:
            return JSONResponse(status_code=201, content=out.model_dump())
        return out

    @app.get(
        "/diligence/queue",
        response_model=FlagListOut,
        tags=["diligence"],
    )
    def get_queue(request: Request) -> FlagListOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            rows = DiligenceStore().list_for_owner(con, owner_user_id=owner)
        finally:
            con.close()
        return FlagListOut(flags=[_out(r) for r in rows], count=len(rows))

    @app.post(
        "/diligence/flags/{flag_id}/dismiss",
        response_model=FlagOut,
        tags=["diligence"],
    )
    def dismiss_flag(flag_id: str, request: Request) -> FlagOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="diligence/flags/dismiss") as con:
            row = DiligenceStore().dismiss(con, owner_user_id=owner, flag_id=flag_id)
        if row is None:
            raise HTTPException(status_code=404, detail="diligence_flag_not_found")
        if row.status not in ("queued", "dismissed"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"diligence_not_dismissable: the flag is {row.status} — "
                    "only a queued flag can be dismissed"
                ),
            )
        return _out(row)
