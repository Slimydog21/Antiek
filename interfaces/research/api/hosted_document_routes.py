"""Owner-bound API for canonical HTML-native hosted documents."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from acquisition.documents import ExtractedDocument
from services.hosted_documents import HostAuthorization, ingest_hosted_document
from substrate.event_log import emit_typed, trajectory
from substrate.marketplace_host import project_hosted_book_html
from substrate.schemas import DocumentLoadedPayload

from .marketplace_host_routes import get_marketplace_host_store

hosted_document_router = APIRouter(prefix="/hosted-documents", tags=["hosted-documents"])


class HostedDocumentIngestBody(BaseModel):
    content_b64: str = Field(min_length=1)
    source_format: str = Field(min_length=1, max_length=16)
    investigation_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    source_uri: str | None = Field(default=None, max_length=2_000)


def _request_owner(request: Request) -> str:
    owner_id = str(getattr(request.state, "user_id", "") or "").strip()
    if not owner_id:
        raise HTTPException(
            status_code=503,
            detail="authenticated request identity is unavailable",
        )
    return owner_id


def _emit_document_loaded(
    investigation_id: str,
    document_id: str,
    extracted: ExtractedDocument,
    size_bytes: int,
    source_uri: str | None,
) -> str:
    # Recover the event receipt after a process crash between append and host
    # store persistence. The service serializes live writers; this durable-log
    # lookup closes the remaining retry window without emitting a duplicate.
    for row in trajectory(investigation_id):
        payload = row.get("payload") if isinstance(row, dict) else None
        if (
            row.get("action_type") == "document.loaded"
            and row.get("document_id") == document_id
            and isinstance(payload, dict)
            and payload.get("content_hash") == extracted.canonical_content_hash
        ):
            prior_event_id = str(row.get("event_id") or "").strip()
            if prior_event_id:
                return prior_event_id
    media_type: Literal["pdf", "markdown"] = (
        "pdf" if extracted.source_format == "pdf" else "markdown"
    )
    event_id = emit_typed(
        investigation_id,
        DocumentLoadedPayload(
            media_type=media_type,
            content_hash=extracted.canonical_content_hash,
            size_bytes=size_bytes,
            title=extracted.title,
            page_count=extracted.page_count,
            source_uri=source_uri,
        ),
        document_id=document_id,
        role="acquisition",
        policy_id="services/hosted_documents",
    )
    if event_id is None:
        raise RuntimeError("event log is disabled; hosted document was not persisted")
    return event_id


def _payload(result: Any) -> dict[str, Any]:
    out = {
        "document_id": result.document_id,
        "owner_id": result.owner_id,
        "state": result.state,
        "source_byte_hash": result.source_byte_hash,
        "canonical_content_hash": result.canonical_content_hash,
        "source_format": result.source_format,
        "title": result.title,
        "document_loaded_event_id": result.document_loaded_event_id,
        "already_hosted": result.already_hosted,
        "non_viewable_reason": result.non_viewable_reason,
        "view_format": "html",
        "html": None,
    }
    if result.state == "ready":
        out["html"] = project_hosted_book_html(
            result.document_id,
            store=get_marketplace_host_store(),
        )
    return out


@hosted_document_router.post("/ingest")
def post_hosted_document(body: HostedDocumentIngestBody, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="content_b64 is not valid base64") from exc
    try:
        result = ingest_hosted_document(
            owner_id=owner_id,
            raw=raw,
            source_format=body.source_format,
            store=get_marketplace_host_store(),
            authorization=HostAuthorization("private_upload"),
            emit_document_loaded=_emit_document_loaded,
            investigation_id=body.investigation_id,
            title=body.title,
            source_uri=body.source_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _payload(result)


@hosted_document_router.get("/{document_id}/html")
def get_hosted_document_html(document_id: str, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    store = get_marketplace_host_store()
    doc = store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="hosted document was not found")
    if str(doc.get("owner_id") or "") != owner_id:
        raise HTTPException(status_code=403, detail="document belongs to another account")
    if doc.get("state") != "ready":
        raise HTTPException(
            status_code=409,
            detail=str(doc.get("non_viewable_reason") or "document is not viewable"),
        )
    return {
        "document_id": document_id,
        "owner_id": owner_id,
        "state": "ready",
        "view_format": "html",
        "html": project_hosted_book_html(document_id, store=store),
        "title": doc.get("title") or document_id,
        "document_loaded_event_id": doc.get("document_loaded_event_id"),
    }


def register_hosted_document_routes(app: FastAPI) -> None:
    app.include_router(hosted_document_router)


__all__ = ["hosted_document_router", "register_hosted_document_routes"]
