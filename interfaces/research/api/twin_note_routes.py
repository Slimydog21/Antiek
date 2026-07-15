"""Authenticated, no-oracle HTTP transport for database-authoritative twin notes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import connect_read
from substrate.graph import default_db_path
from substrate.twin_note_taker.discovery import (
    TwinNoteDiscoveryIntegrity,
    TwinNoteDiscoveryService,
    TwinNoteDiscoveryUnavailable,
)
from substrate.twin_note_taker.merge_bridge import (
    MergeBridgeConflict,
    MergeBridgeIntegrity,
    MergeBridgeUnavailable,
    SelectedNote,
    TwinNoteMergeBridge,
)
from substrate.twin_note_taker.serving import (
    TwinNoteInputError,
    TwinNoteIntegrityError,
    TwinNoteServingService,
    TwinNoteUnavailable,
)
from substrate.twin_note_taker.workflow import (
    TwinNoteWorkflow,
    TwinNoteWorkflowConflict,
    TwinNoteWorkflowInput,
    TwinNoteWorkflowIntegrity,
    TwinNoteWorkflowUnavailable,
)

NO_STORE = {"Cache-Control": "private, no-store"}
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
HTML_HEADERS = {**NO_STORE, "X-Content-Type-Options": "nosniff", "Content-Security-Policy": CSP}

class _TwinNotePrivateRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private_handler(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422,
                    content={"detail":"twin-note request is invalid"},headers=NO_STORE)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), **NO_STORE}
                raise
            response.headers.update(NO_STORE)
            return response
        return private_handler

twin_note_router = APIRouter(prefix="/research/twin-notes", tags=["twin-notes"],
                             route_class=_TwinNotePrivateRoute)


class ComposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision_ids: list[str] = Field(min_length=2, max_length=20)

class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(min_length=1, max_length=512)
    window_ids: list[str] = Field(min_length=1, max_length=1000)

class ApplyIn(PreviewIn):
    expected_predecessor: str | None = None
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=16, max_length=128)


class MergeProjectionSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["revision", "composition"]
    id: str = Field(pattern=r"^tn[rc]-[0-9a-f]{32}$")


class MergeProjectionNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision_id: str = Field(pattern=r"^tnr-[0-9a-f]{32}$")
    note_ordinal: int = Field(ge=0)


class MergeProjectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_projection_id: str = Field(pattern=r"^hproj-[0-9a-f]{64}$")
    source: MergeProjectionSourceIn
    selected_notes: list[MergeProjectionNoteIn] = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=16, max_length=128)


def _account(request: Request) -> str:
    account = getattr(request.state, "user_id", None)
    if type(account) is not str or not account:
        raise HTTPException(401, "authentication required", headers=NO_STORE)
    return account


def _service() -> TwinNoteServingService:
    return TwinNoteServingService()

def _workflow() -> TwinNoteWorkflow:
    db_path = default_db_path()
    def resolver(account: str, asset: str, investigation: str) -> bool:
        # Asset identity is a document PK, never a display label.  Require both
        # sides of the binding on the same owner-scoped notebook row.  Resolve
        # before compression takes its writer lock.
        with connect_read(db_path) as con:
            return con.execute(
                "SELECT EXISTS (SELECT 1 FROM documents d JOIN notebooks n "
                "ON n.document_id=d.document_id AND n.owner_user_id=d.owner_user_id "
                "WHERE d.document_id=? AND d.owner_user_id=? "
                "AND n.investigation_id=? AND n.owner_user_id=?)",
                [asset, account, investigation, account],
            ).fetchone() == (True,)
    return TwinNoteWorkflow(resolver, db_path=db_path,
        publication_root=os.environ.get("ANTIEK_TWIN_NOTE_PUBLICATION_ROOT", "data/twin-notes"),
        events_dir=os.environ.get("ANTIEK_RESEARCH_EVENTS_DIR"))


def _discovery() -> TwinNoteDiscoveryService:
    return TwinNoteDiscoveryService(db_path=default_db_path())


def _merge_bridge() -> TwinNoteMergeBridge:
    root = os.environ.get("ANTIEK_HTML_OBJECT_ROOT", "").strip()
    if not root:
        raise RuntimeError("HTML object root is not configured")
    return TwinNoteMergeBridge(db_path=default_db_path(), publication_root=Path(root))


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TwinNoteUnavailable):
        return HTTPException(404, "twin-note resource is unavailable", headers=NO_STORE)
    if isinstance(exc, TwinNoteIntegrityError):
        return HTTPException(409, "twin-note integrity conflict", headers=NO_STORE)
    return HTTPException(422, "twin-note request is invalid", headers=NO_STORE)

def _map_workflow_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TwinNoteWorkflowUnavailable):
        return HTTPException(404, "twin-note member is unavailable", headers=NO_STORE)
    if isinstance(exc, (TwinNoteWorkflowIntegrity, TwinNoteWorkflowConflict)):
        return HTTPException(409, "twin-note workflow conflict", headers=NO_STORE)
    return HTTPException(422, "twin-note request is invalid", headers=NO_STORE)


@twin_note_router.get("/revision-candidates")
async def get_revision_candidates(request: Request) -> Response:
    # Discovery is deliberately parameter-free. Reject even otherwise ignored
    # GET bodies and query keys without reflecting their names or values.
    if request.query_params or await request.body():
        raise HTTPException(422, "twin-note request is invalid", headers=NO_STORE)
    try:
        result = _discovery().candidates(_account(request))
    except HTTPException:
        raise
    except TwinNoteDiscoveryUnavailable:
        raise HTTPException(503, "twin-note discovery is unavailable", headers=NO_STORE) from None
    except TwinNoteDiscoveryIntegrity:
        raise HTTPException(409, "twin-note discovery integrity conflict", headers=NO_STORE) from None
    return Response(content=json.dumps(result, separators=(",", ":")),
                    media_type="application/json", headers=NO_STORE)

@twin_note_router.post("/revision-previews")
def post_revision_preview(body: PreviewIn, request: Request) -> Response:
    try:
        result = _workflow().preview(account_id=_account(request), asset_id=body.asset_id,
                                     window_ids=body.window_ids).response()
    except HTTPException:
        raise
    except (TwinNoteWorkflowUnavailable,TwinNoteWorkflowIntegrity,TwinNoteWorkflowConflict,TwinNoteWorkflowInput) as exc:
        raise _map_workflow_error(exc) from None
    return Response(content=json.dumps(result,separators=(",",":")),media_type="application/json",headers=NO_STORE)

@twin_note_router.post("/revisions")
def post_revision(body: ApplyIn, request: Request) -> Response:
    try:
        result = _workflow().apply(account_id=_account(request), **body.model_dump())
    except HTTPException:
        raise
    except (TwinNoteWorkflowUnavailable,TwinNoteWorkflowIntegrity,TwinNoteWorkflowConflict,TwinNoteWorkflowInput) as exc:
        raise _map_workflow_error(exc) from None
    return Response(content=json.dumps(result,separators=(",",":")),media_type="application/json",headers=NO_STORE)


@twin_note_router.post("/merge-projections", status_code=201)
def post_merge_projection(body: MergeProjectionIn, request: Request) -> Response:
    try:
        result = _merge_bridge().create(
            owner_user_id=_account(request),
            source_projection_id=body.source_projection_id,
            source_kind=body.source.kind,
            source_id=body.source.id,
            selected_notes=[SelectedNote(item.revision_id, item.note_ordinal)
                            for item in body.selected_notes],
            idempotency_key=body.idempotency_key,
        ).response()
    except HTTPException:
        raise
    except MergeBridgeUnavailable:
        raise HTTPException(404, "twin-note merge source is unavailable", headers=NO_STORE) from None
    except (MergeBridgeConflict, MergeBridgeIntegrity):
        raise HTTPException(409, "twin-note merge conflict", headers=NO_STORE) from None
    except RuntimeError:
        raise HTTPException(503, "twin-note merge service is unavailable", headers=NO_STORE) from None
    return Response(
        content=json.dumps(result, separators=(",", ":")),
        media_type="application/json",
        status_code=201,
        headers=NO_STORE,
    )


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
