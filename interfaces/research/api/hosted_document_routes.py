"""Owner-bound API for canonical HTML-native hosted documents."""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from acquisition.documents import ExtractedDocument
from services.hosted_documents import HostAuthorization, ingest_hosted_document
from substrate.event_log import emit_typed, trajectory
from substrate.marketplace_host import project_hosted_book_html
from substrate.marketplace_host.library import HostStore
from substrate.schemas import DocumentLoadedPayload

from .marketplace_host_routes import get_marketplace_host_store

hosted_document_router = APIRouter(prefix="/hosted-documents", tags=["hosted-documents"])
HOSTED_HTML_PROJECTION_VERSION = "hosted-html-projection-v1"


class HostedDocumentIngestBody(BaseModel):
    content_b64: str = Field(min_length=1)
    source_format: str = Field(min_length=1, max_length=16)
    investigation_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    source_uri: str | None = Field(default=None, max_length=2_000)
    intent: Literal["user_owned"] = "user_owned"


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
    if not any(row.get("event_id") == event_id for row in trajectory(investigation_id)):
        raise RuntimeError("document.loaded append was not durably observable")
    return event_id


def _projection_hash(html: str) -> str:
    return "sha256:" + hashlib.sha256(html.encode()).hexdigest()


def _acknowledge_projection(
    document_id: str, html: str, *, store: HostStore
) -> dict[str, Any]:
    doc = store.get_document(document_id)
    if doc is None:
        raise RuntimeError("hosted document disappeared before projection acknowledgement")
    projection_hash = _projection_hash(html)
    if (
        doc.get("projection_state") == "ready"
        and doc.get("projection_hash") == projection_hash
        and doc.get("projection_version") == HOSTED_HTML_PROJECTION_VERSION
    ):
        return doc
    doc["projection_state"] = "ready"
    doc["projection_hash"] = projection_hash
    doc["projection_version"] = HOSTED_HTML_PROJECTION_VERSION
    try:
        store.put_document(document_id, doc)
    except OSError as exc:
        raise RuntimeError("hosted HTML projection checkpoint failed") from exc
    return doc


def _receipt_fields(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_event_id": doc.get("document_loaded_event_id"),
        "author": doc.get("author"),
        "page_count": doc.get("page_count"),
        "word_count": doc.get("word_count"),
        "projection_state": doc.get("projection_state") or (
            "non_viewable" if doc.get("state") == "non_viewable" else "pending"
        ),
        "projection_hash": doc.get("projection_hash"),
        "projection_version": doc.get("projection_version"),
        "extraction_receipt": {
            "extractor_version": doc.get("extractor_version"),
            "source_byte_hash": doc.get("source_byte_hash"),
            "extracted_content_hash": doc.get("extracted_content_hash"),
            "canonical_content_hash": doc.get("canonical_content_hash"),
            "source_format": doc.get("source_format"),
            "word_count": doc.get("word_count"),
            "minimum_viewable_words": doc.get("minimum_viewable_words"),
            "truncated": bool(doc.get("truncated")),
            "viewable": doc.get("state") == "ready",
            "non_viewable_reason": doc.get("non_viewable_reason"),
        },
    }


def _payload(result: Any, *, store: HostStore) -> dict[str, Any]:
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
        "intent": "user_owned",
        "html": None,
    }
    if result.state == "ready":
        html = project_hosted_book_html(
            result.document_id,
            store=store,
        )
        out["html"] = html
        doc = _acknowledge_projection(result.document_id, html, store=store)
    else:
        doc = store.get_document(result.document_id) or {}
    out.update(_receipt_fields(doc))
    return out


@hosted_document_router.post("/ingest")
def post_hosted_document(body: HostedDocumentIngestBody, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    store = get_marketplace_host_store(request)
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="content_b64 is not valid base64") from exc
    try:
        result = ingest_hosted_document(
            owner_id=owner_id,
            raw=raw,
            source_format=body.source_format,
            store=store,
            authorization=HostAuthorization("private_upload"),
            emit_document_loaded=_emit_document_loaded,
            investigation_id=body.investigation_id,
            title=body.title,
            source_uri=body.source_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (KeyError, RuntimeError, TypeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return _payload(result, store=store)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@hosted_document_router.get("/{document_id}/html")
def get_hosted_document_html(document_id: str, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    store = get_marketplace_host_store(request)
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
    try:
        html = project_hosted_book_html(document_id, store=store)
        doc = _acknowledge_projection(document_id, html, store=store)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "document_id": document_id,
        "owner_id": owner_id,
        "state": "ready",
        "source_byte_hash": doc.get("source_byte_hash"),
        "canonical_content_hash": doc.get("canonical_content_hash"),
        "source_format": doc.get("source_format"),
        "view_format": "html",
        "html": html,
        "title": doc.get("title") or document_id,
        "document_loaded_event_id": doc.get("document_loaded_event_id"),
        "already_hosted": True,
        "non_viewable_reason": None,
        **_receipt_fields(doc),
    }


def register_hosted_document_routes(app: FastAPI) -> None:
    app.include_router(hosted_document_router)


__all__ = [
    "HOSTED_HTML_PROJECTION_VERSION",
    "hosted_document_router",
    "register_hosted_document_routes",
]
