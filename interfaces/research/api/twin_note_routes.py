"""Authenticated, no-oracle HTTP transport for database-authoritative twin notes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from substrate.twin_note_taker.serving import (
    TwinNoteInputError, TwinNoteIntegrityError, TwinNoteServingService, TwinNoteUnavailable,
)

twin_note_router = APIRouter(prefix="/research/twin-notes", tags=["twin-notes"])
NO_STORE = {"Cache-Control": "private, no-store"}
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
HTML_HEADERS = {**NO_STORE, "X-Content-Type-Options": "nosniff", "Content-Security-Policy": CSP}


class ComposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision_ids: list[str] = Field(min_length=2, max_length=20)


def _account(request: Request) -> str:
    account = getattr(request.state, "user_id", None)
    if type(account) is not str or not account:
        raise HTTPException(401, "authentication required", headers=NO_STORE)
    return account


def _service() -> TwinNoteServingService:
    return TwinNoteServingService()


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TwinNoteUnavailable):
        return HTTPException(404, "twin-note resource is unavailable", headers=NO_STORE)
    if isinstance(exc, TwinNoteIntegrityError):
        return HTTPException(409, "twin-note integrity conflict", headers=NO_STORE)
    return HTTPException(422, "twin-note request is invalid", headers=NO_STORE)


@twin_note_router.get("")
def list_twin_notes(request: Request) -> Response:
    try:
        rows = _service().assets(_account(request))
    except HTTPException:
        raise
    except (TwinNoteUnavailable, TwinNoteIntegrityError, TwinNoteInputError) as exc:
        raise _map_error(exc) from None
    return Response(content=json.dumps({"assets": rows}, separators=(",", ":")), media_type="application/json", headers=NO_STORE)


@twin_note_router.get("/assets/{asset_id}/revisions")
def list_twin_note_history(asset_id: str, request: Request) -> Response:
    try:
        history = _service().history(_account(request), asset_id)
        result = {"asset_id": asset_id, "revisions": [r.metadata() for r in history]}
    except HTTPException:
        raise
    except (TwinNoteUnavailable, TwinNoteIntegrityError, TwinNoteInputError) as exc:
        raise _map_error(exc) from None
    return Response(content=json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE)


@twin_note_router.get("/revisions/{revision_id}")
def get_twin_note_revision(revision_id: str, request: Request) -> Response:
    try:
        content = _service().revision(_account(request), revision_id).html_bytes
    except HTTPException:
        raise
    except (TwinNoteUnavailable, TwinNoteIntegrityError, TwinNoteInputError) as exc:
        raise _map_error(exc) from None
    return Response(content=content, media_type="text/html", headers=HTML_HEADERS)


@twin_note_router.post("/compositions")
def post_twin_note_composition(body: ComposeIn, request: Request) -> Response:
    try:
        result = _service().compose(_account(request), body.revision_ids)
    except HTTPException:
        raise
    except (TwinNoteUnavailable, TwinNoteIntegrityError, TwinNoteInputError) as exc:
        raise _map_error(exc) from None
    return Response(content=json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE)


@twin_note_router.get("/compositions/{composition_id}")
def get_twin_note_composition(composition_id: str, request: Request) -> Response:
    try:
        content = _service().composition(_account(request), composition_id)
    except HTTPException:
        raise
    except (TwinNoteUnavailable, TwinNoteIntegrityError, TwinNoteInputError) as exc:
        raise _map_error(exc) from None
    return Response(content=content, media_type="text/html", headers=HTML_HEADERS)


__all__ = ["twin_note_router"]
