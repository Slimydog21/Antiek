"""Marketplace host-into-account REST surface.

Standalone APIRouter. Process-local store + demo catalog by default.
No Stripe / live payment rails.
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from services.hosted_documents import HostAuthorization, ingest_hosted_document
from substrate.marketplace_host import (
    Catalog,
    InMemoryHostStore,
    default_demo_catalog,
    list_account_library_html,
    project_catalog_html,
    project_hosted_book_html,
)
from substrate.marketplace_host.library import HostStore
from substrate.marketplace_host.purchase import ManualPurchaseReceipt

marketplace_host_router = APIRouter(prefix="/marketplace", tags=["marketplace-host"])

_store: HostStore | None = None
_catalog: Catalog | None = None


def reset_marketplace_host_store(store: HostStore | None = None) -> None:
    global _store, _catalog
    _store = store if store is not None else InMemoryHostStore()
    _catalog = default_demo_catalog()


def _s() -> HostStore:
    global _store
    if _store is None:
        _store = InMemoryHostStore()
    return _store


def get_marketplace_host_store() -> HostStore:
    """Return the shared account-host store used by all hosted-document routes."""
    return _s()


def _c() -> Catalog:
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


def _request_owner(request: Request) -> str:
    owner_id = str(getattr(request.state, "user_id", "") or "").strip()
    if not owner_id:
        raise HTTPException(
            status_code=503,
            detail="authenticated request identity is unavailable",
        )
    return owner_id


def _authorized_owner(request: Request, requested_owner: str) -> str:
    """Bind a legacy owner parameter to middleware-authenticated identity."""

    owner_id = _request_owner(request)
    requested = requested_owner.strip()
    aliases = {owner_id}
    if owner_id == "__operator__":
        aliases.add("operator")
    if requested not in aliases:
        raise HTTPException(
            status_code=403,
            detail="account scope does not match authenticated identity",
        )
    return owner_id


def _decode_content_b64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="content_b64 is not valid base64") from exc


def _source_format(raw: bytes, declared: str) -> str:
    stripped = raw.lstrip()
    if raw.startswith(b"%PDF"):
        return "pdf"
    if raw.startswith(b"PK\x03\x04"):
        return "epub"
    if stripped[:64].lower().startswith((b"<!doctype html", b"<html", b"<body")):
        return "html"
    return declared or "text"


def _canonical_marketplace_host(
    *,
    owner_id: str,
    book_id: str,
    content: bytes | None,
    receipt_id: str | None,
) -> dict[str, Any]:
    entry = _c().get(book_id)
    if entry is None:
        raise KeyError(f"unknown book_id: {book_id}")
    if entry.license_class == "unknown":
        raise ValueError("license_class=unknown is deny-by-default")
    if entry.license_class == "public_domain" and content is not None:
        raise ValueError("caller-supplied bytes cannot inherit a catalog public-domain license")
    raw = content if content is not None else entry.body_text.encode()
    if not raw:
        raise ValueError("content is empty")
    entitlement_id = None
    if entry.license_class == "purchased":
        if not receipt_id:
            raise ValueError("purchased license requires receipt_id")
        receipt = _s().get_receipt(receipt_id)
        if receipt is None:
            raise ValueError(f"unknown receipt_id: {receipt_id}")
        if receipt.get("owner_id") != owner_id or receipt.get("book_id") != book_id:
            raise ValueError("receipt does not authorize this owner and book")
        entitlement_id = receipt_id

    # Local import avoids a module cycle: the general route imports this
    # module only to share the account host store.
    from .hosted_document_routes import _emit_document_loaded

    hosted = ingest_hosted_document(
        owner_id=owner_id,
        raw=raw,
        source_format=_source_format(raw, entry.source_format),
        store=_s(),
        authorization=HostAuthorization(
            entry.license_class,
            entitlement_id=entitlement_id,
        ),
        emit_document_loaded=_emit_document_loaded,
        investigation_id=f"marketplace:{book_id}",
        title=entry.title,
        source_uri=f"marketplace://{book_id}",
        # Curated public-domain catalog excerpts are intentionally short but
        # fully identified/licensed. Untrusted uploads and purchases retain
        # the shared 50-word quality floor.
        minimum_viewable_words=1 if entry.license_class == "public_domain" else 50,
    )
    if hosted.state != "ready":
        return {
            "document_id": hosted.document_id,
            "owner_id": owner_id,
            "book_id": book_id,
            "content_hash": hosted.canonical_content_hash,
            "title": hosted.title,
            "license_class": entry.license_class,
            "already_hosted": hosted.already_hosted,
            "source_format": hosted.source_format,
            "library_document_ids": _s().list_membership(owner_id),
            "view_format": "html",
            "state": hosted.state,
            "html": "",
            "body_preview": "",
            "non_viewable_reason": hosted.non_viewable_reason,
            "document_loaded_event_id": None,
        }
    return {
        "document_id": hosted.document_id,
        "owner_id": owner_id,
        "book_id": book_id,
        "content_hash": hosted.canonical_content_hash,
        "title": hosted.title,
        "license_class": entry.license_class,
        "already_hosted": hosted.already_hosted,
        "source_format": hosted.source_format,
        "library_document_ids": _s().list_membership(owner_id),
        "view_format": "html",
        "state": hosted.state,
        "html": project_hosted_book_html(hosted.document_id, store=_s()),
        "body_preview": hosted.body_text[:280],
        "non_viewable_reason": None,
        "document_loaded_event_id": hosted.document_loaded_event_id,
    }


def catalog_honesty_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Residual (iq): by_source + license counts for catalog honesty audit.

    Residual (lw): by_subject multi-label counts for research-domain filter.
    Pure over already-serialized entry dicts. Never invents payment rails.
    """
    by_source: dict[str, int] = {}
    by_license: dict[str, int] = {}
    by_subject: dict[str, int] = {}
    free_count = 0
    for e in entries:
        src = str(e.get("source") or "unknown").strip() or "unknown"
        lic = str(e.get("license_class") or "unknown").strip() or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        by_license[lic] = by_license.get(lic, 0) + 1
        # Residual (abn): free_count is is_free only (not OR public_domain).
        # public_domain_count remains by_license; never invent free when paid PD.
        if e.get("is_free") is True:
            free_count += 1
        # Residual (lw): multi-label subjects (entry may appear in many domains).
        raw_subjects = e.get("subjects") or []
        if isinstance(raw_subjects, str):
            raw_subjects = [raw_subjects]
        for s in raw_subjects:
            token = str(s or "").strip().lower()
            if not token:
                continue
            by_subject[token] = by_subject.get(token, 0) + 1
    return {
        "by_source": by_source,
        "by_license": by_license,
        "by_subject": by_subject,
        "public_domain_count": by_license.get("public_domain", 0),
        "purchased_count": by_license.get("purchased", 0),
        "free_count": free_count,
        "payment_rails": "manual_receipt_only",
        "view_format": "html",
    }


@marketplace_host_router.get("/catalog")
def get_catalog(
    free_only: bool = False,
    subject: str | None = None,
    source: str | None = None,
    include_html: bool = True,
) -> dict[str, Any]:
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
                # Residual (lw): research-domain subjects for workstation filter.
                "subjects": list(e.subjects),
            }
        )
    # Residual (iq/lw): knowledge-source + subject honesty for research marketplace.
    honesty = catalog_honesty_payload(entries)
    out: dict[str, Any] = {
        "entries": entries,
        "count": len(entries),
        "view_format": "html",
        **honesty,
    }
    # Residual (ly): HTML-first catalog projection (optional filters for chip parity).
    if include_html:
        out["html"] = project_catalog_html(
            cat,
            free_only=free_only,
            subject=subject,
            source=source,
        )
    return out


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


def _maybe_record_marketplace_host_usage(
    *,
    book_id: str,
    title: str,
    license_class: str,
    already_hosted: bool,
) -> dict[str, Any] | None:
    """Residual (ma): feed marketplace host → Antiek-bench book_qa usage.

    Best-effort only (never raises to host path). Uses the shared process-local
    usage store so Settings suite-proposal rewrite can learn book_qa patterns
    from HTML-first catalog hosts. propose ≠ promote still holds on rewrite.
    """
    try:
        from substrate.antiek_bench import UsageEvent, record_usage_event

        from .engagement_routes import get_bench_usage_store

        store = get_bench_usage_store(create_if_missing=True)
        if store is None:
            return None
        entry = _c().get(book_id)
        subjects = ",".join(entry.subjects) if entry and entry.subjects else ""
        source_name = (entry.source if entry else "") or "unknown"
        hint = (
            f"host {book_id} · {title} · {license_class}"
            f" · source={source_name}"
            + (f" · subjects={subjects}" if subjects else "")
            + (" · rehost" if already_hosted else "")
        )[:280]
        return record_usage_event(
            UsageEvent(
                task_class="book_qa",
                outcome="worked",
                prompt_hint=hint,
                source="marketplace_host",
                model_id=None,
            ),
            store=store,
        )
    except Exception as exc:
        return {
            "recorded": False,
            "record_skipped": f"usage_failed: {exc}",
            "task_class": "book_qa",
            "source": "marketplace_host",
        }


@marketplace_host_router.post("/host")
def post_host(body: HostBody, request: Request) -> dict[str, Any]:
    owner_id = _authorized_owner(request, body.owner_id)
    content = _decode_content_b64(body.content_b64) if body.content_b64 else None
    try:
        out = _canonical_marketplace_host(
            owner_id=owner_id,
            book_id=body.book_id,
            content=content,
            receipt_id=body.receipt_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    twins = (
        _maybe_seed_twins(
            document_id=str(out["document_id"]),
            title=str(out["title"]),
            body_preview=(out.get("body_preview") or "")[:200],
            seed=body.seed_twins,
        )
        if out["state"] == "ready"
        else None
    )
    if twins is not None:
        out["twins"] = twins
    # Residual (ma): Antiek-bench book_qa usage for recursive suite rewrite feed.
    usage = (
        _maybe_record_marketplace_host_usage(
            book_id=str(out["book_id"]),
            title=str(out["title"]),
            license_class=str(out["license_class"]),
            already_hosted=bool(out["already_hosted"]),
        )
        if out["state"] == "ready"
        else None
    )
    if usage is not None:
        out["usage_event"] = usage
    return out


@marketplace_host_router.post("/purchase-and-host")
def post_purchase_and_host(body: PurchaseHostBody, request: Request) -> dict[str, Any]:
    owner_id = _authorized_owner(request, body.owner_id)
    content = _decode_content_b64(body.content_b64)
    try:
        entry = _c().get(body.book_id)
        if entry is None:
            raise KeyError(f"unknown book_id: {body.book_id}")
        if entry.license_class != "purchased":
            raise ValueError("purchase-and-host requires a purchased catalog entry")
        receipt = ManualPurchaseReceipt(store=_s()).record_receipt(
            book_id=body.book_id,
            owner_id=owner_id,
            opaque_reference=body.opaque_reference,
            note=body.note,
        )
        out = _canonical_marketplace_host(
            owner_id=owner_id,
            book_id=body.book_id,
            content=content,
            receipt_id=receipt.receipt_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out["receipt_id"] = receipt.receipt_id
    twins = (
        _maybe_seed_twins(
            document_id=str(out["document_id"]),
            title=str(out["title"]),
            body_preview=(out.get("body_preview") or "")[:200],
            seed=body.seed_twins,
        )
        if out["state"] == "ready"
        else None
    )
    if twins is not None:
        out["twins"] = twins
    # Residual (ma): Antiek-bench book_qa usage (purchase host path).
    usage = (
        _maybe_record_marketplace_host_usage(
            book_id=str(out["book_id"]),
            title=str(out["title"]),
            license_class=str(out["license_class"]),
            already_hosted=bool(out["already_hosted"]),
        )
        if out["state"] == "ready"
        else None
    )
    if usage is not None:
        out["usage_event"] = usage
    return out


@marketplace_host_router.get("/library/{owner_id}")
def get_library(owner_id: str, request: Request) -> dict[str, Any]:
    owner_id = _authorized_owner(request, owner_id)
    store = _s()
    from substrate.marketplace_host import AccountLibrary

    if owner_id == "__operator__":
        # The campaign UI historically persisted the literal ``operator``.
        # Migrate those memberships idempotently into the canonical middleware
        # identity before projecting the account library.
        for document_id in store.list_membership("operator"):
            store.put_membership(owner_id, document_id)
    lib = AccountLibrary.load(owner_id, store=store)
    docs = []
    free_count = 0
    for doc_id in lib.document_ids:
        doc = store.get_document(doc_id) or {}
        lic = str(doc.get("license_class") or "").strip()
        # Residual (abu): is_free inventory for library free honesty (parity free doctrine).
        # Hosted public_domain is free host path; purchased never free.
        is_free = lic == "public_domain"
        if is_free:
            free_count += 1
        docs.append(
            {
                "document_id": doc_id,
                "title": doc.get("title"),
                "license_class": doc.get("license_class"),
                "view_format": doc.get("view_format", "html"),
                "is_free": is_free,
            }
        )
    return {
        "owner_id": owner_id,
        "documents": docs,
        "count": len(docs),
        # Residual (acb): free_count aggregate for library free inventory honesty.
        "free_count": free_count,
        "view_format": "html",
        "html": list_account_library_html(owner_id, store=store),
    }


@marketplace_host_router.get("/documents/{document_id}/html")
def get_document_html(document_id: str, request: Request) -> dict[str, Any]:
    """Residual (dp): return HTML body plus title/license for library rehydrate."""
    store = _s()
    owner_id = _request_owner(request)
    doc = store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"unknown document_id: {document_id}")
    stored_owner = str(doc.get("owner_id") or "")
    allowed_owners = {owner_id}
    if owner_id == "__operator__":
        allowed_owners.add("operator")
    if stored_owner not in allowed_owners:
        raise HTTPException(
            status_code=403,
            detail="document does not belong to authenticated identity",
        )
    try:
        html = project_hosted_book_html(document_id, store=store)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        # PDF / empty projection — honest 400, not a fake HTML body.
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "document_id": document_id,
        "view_format": "html",
        "html": html,
        "title": doc.get("title") or document_id,
        "license_class": doc.get("license_class"),
        "owner_id": doc.get("owner_id"),
        "source": "marketplace_host.project_hosted_book_html",
    }


def register_marketplace_host_routes(app: FastAPI) -> None:
    app.include_router(marketplace_host_router)


__all__ = [
    "marketplace_host_router",
    "register_marketplace_host_routes",
    "reset_marketplace_host_store",
    "get_marketplace_host_store",
    "catalog_honesty_payload",
]
