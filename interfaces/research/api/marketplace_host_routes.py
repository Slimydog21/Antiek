"""Marketplace host-into-account REST surface.

Standalone APIRouter. Process-local store + demo catalog by default.
No Stripe / live payment rails.
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_host import (
    InMemoryHostStore,
    default_demo_catalog,
    host_book_into_account,
    list_account_library_html,
    project_hosted_book_html,
    record_purchase_and_host,
)
from substrate.marketplace_host.library import HostStore

marketplace_host_router = APIRouter(prefix="/marketplace", tags=["marketplace-host"])

_store: HostStore | None = None
_catalog = None


def reset_marketplace_host_store(store: HostStore | None = None) -> None:
    global _store, _catalog
    _store = store if store is not None else InMemoryHostStore()
    _catalog = default_demo_catalog()


def _s() -> HostStore:
    global _store
    if _store is None:
        _store = InMemoryHostStore()
    return _store


def _c():
    global _catalog
    if _catalog is None:
        _catalog = default_demo_catalog()
    return _catalog


class HostBody(BaseModel):
    owner_id: str
    book_id: str
    receipt_id: str | None = None
    content_b64: str | None = None  # optional raw bytes for purchased/PDF ingest
    # Residual (bv): offline recursive note-taker seed into engagement twins
    seed_twins: bool = True


class PurchaseHostBody(BaseModel):
    owner_id: str
    book_id: str
    opaque_reference: str
    content_b64: str = Field(
        description="Base64 of book bytes (PDF ingest source allowed; view is HTML)"
    )
    note: str = ""
    seed_twins: bool = True


@marketplace_host_router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    cat = _c()
    # Empty search returns all entries (catalog.search contract).
    entries = []
    for e in cat.search(""):
        entries.append(
            {
                "book_id": e.book_id,
                "title": e.title,
                "author": e.author,
                "license_class": e.license_class,
                "is_free": e.is_free,
                "source": e.source,
            }
        )
    return {"entries": entries, "count": len(entries), "view_format": "html"}


def _maybe_seed_twins(
    *,
    document_id: str,
    title: str,
    body_preview: str = "",
    seed: bool,
) -> dict[str, Any] | None:
    """Seed engagement twin notes for a hosted document (residual bv).

    Uses the process-local engagement store so twins join research context
    flywheel. Offline stubs only.
    """
    if not seed:
        return None
    try:
        from substrate.engagement_spine import seed_twins_for_asset

        from .engagement_routes import get_engagement_store

        eng = get_engagement_store(create_if_missing=True)
        return seed_twins_for_asset(
            document_id,
            store=eng,
            title=title or document_id,
            body_text=body_preview,
            include_html=True,
        )
    except Exception as exc:
        return {
            "seeded": False,
            "seed_skipped": f"seed_failed: {exc}",
            "view_format": "html",
        }


@marketplace_host_router.post("/host")
def post_host(body: HostBody) -> dict[str, Any]:
    content = None
    if body.content_b64:
        try:
            content = base64.b64decode(body.content_b64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid content_b64: {e}") from e
    try:
        result = host_book_into_account(
            owner_id=body.owner_id,
            store=_s(),
            book_id=body.book_id,
            catalog=_c(),
            content=content,
            receipt_id=body.receipt_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = result.to_dict()
    twins = _maybe_seed_twins(
        document_id=result.host.document_id,
        title=result.host.title,
        body_preview=(out.get("body_preview") or "")[:200],
        seed=body.seed_twins,
    )
    if twins is not None:
        out["twins"] = twins
    return out


@marketplace_host_router.post("/purchase-and-host")
def post_purchase_and_host(body: PurchaseHostBody) -> dict[str, Any]:
    try:
        content = base64.b64decode(body.content_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid content_b64: {e}") from e
    try:
        receipt, result = record_purchase_and_host(
            owner_id=body.owner_id,
            store=_s(),
            book_id=body.book_id,
            catalog=_c(),
            opaque_reference=body.opaque_reference,
            content=content,
            note=body.note,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = result.to_dict()
    out["receipt_id"] = receipt.receipt_id
    twins = _maybe_seed_twins(
        document_id=result.host.document_id,
        title=result.host.title,
        body_preview=(out.get("body_preview") or "")[:200],
        seed=body.seed_twins,
    )
    if twins is not None:
        out["twins"] = twins
    return out


@marketplace_host_router.get("/library/{owner_id}")
def get_library(owner_id: str) -> dict[str, Any]:
    store = _s()
    from substrate.marketplace_host import AccountLibrary

    lib = AccountLibrary.load(owner_id, store=store)
    docs = []
    for doc_id in lib.document_ids:
        doc = store.get_document(doc_id) or {}
        docs.append(
            {
                "document_id": doc_id,
                "title": doc.get("title"),
                "license_class": doc.get("license_class"),
                "view_format": doc.get("view_format", "html"),
            }
        )
    return {
        "owner_id": owner_id,
        "documents": docs,
        "count": len(docs),
        "view_format": "html",
        "html": list_account_library_html(owner_id, store=store),
    }


@marketplace_host_router.get("/documents/{document_id}/html")
def get_document_html(document_id: str) -> dict[str, Any]:
    try:
        html = project_hosted_book_html(document_id, store=_s())
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {
        "document_id": document_id,
        "view_format": "html",
        "html": html,
    }


def register_marketplace_host_routes(app: FastAPI) -> None:
    app.include_router(marketplace_host_router)


__all__ = [
    "marketplace_host_router",
    "register_marketplace_host_routes",
    "reset_marketplace_host_store",
]
