"""Host-into-account: content-addressed document owned by an account (SPR-02).

PDF/EPUB bytes may be the *ingest source*; the stored view body is always
text/HTML content and human view is via ``project_hosted_book_html``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import Catalog, CatalogEntry
from .library import HostStore


@dataclass(frozen=True)
class HostResult:
    document_id: str
    owner_id: str
    book_id: str
    content_hash: str
    title: str
    license_class: str
    body_text: str
    source_format: str
    already_hosted: bool


def _content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _document_id(owner_id: str, content_hash: str) -> str:
    """Content-addressed per owner — same bytes + owner → same document_id."""
    digest = hashlib.sha256(f"host:v1:{owner_id}:{content_hash}".encode()).hexdigest()[
        :24
    ]
    return f"hdoc_{digest}"


def _load_bytes(
    *,
    content: bytes | None,
    path: str | Path | None,
    entry: CatalogEntry | None,
) -> tuple[bytes, str]:
    """Return (raw_bytes, source_format)."""
    if content is not None:
        return content, "bytes"
    if path is not None:
        p = Path(path)
        raw = p.read_bytes()
        suffix = p.suffix.lower().lstrip(".")
        fmt = suffix if suffix else "bin"
        return raw, fmt
    if entry is not None and entry.body_text:
        return entry.body_text.encode("utf-8"), entry.source_format or "text"
    raise ValueError("content, path, or catalog entry body_text is required")


def _html_view_placeholder(raw: bytes, source_format: str) -> str:
    """Honest non-PDF view body for binary / PDF ingest sources."""
    digest = hashlib.sha256(raw).hexdigest()[:16]
    fmt = source_format or "binary"
    return (
        f"[Hosted from {fmt} source; content hash {digest}. "
        f"Human view is HTML, not PDF.]\n"
        f"Raw size: {len(raw)} bytes."
    )


def _decode_body(raw: bytes, source_format: str) -> str:
    """Decode ingest bytes to a text body for HTML view.

    PDF/EPUB as *source* is allowed; the stored view body is never a PDF
    document (``%PDF`` magic is rewritten to an HTML-view placeholder).
    Real PDF text extraction lives in acquisition; this package stays offline-pure.
    """
    fmt = (source_format or "").lower()
    # Explicit PDF/EPUB ingest format → never store PDF as view body.
    if fmt in ("pdf", "epub") or raw[:4] == b"%PDF":
        return _html_view_placeholder(raw, source_format or "pdf")
    try:
        text = raw.decode("utf-8")
        if text.lstrip().startswith("%PDF"):
            return _html_view_placeholder(raw, "pdf")
        if text.strip():
            return text
    except UnicodeDecodeError:
        pass
    return _html_view_placeholder(raw, source_format or "binary")


def host_into_account(
    *,
    owner_id: str,
    store: HostStore,
    book_id: str | None = None,
    catalog: Catalog | None = None,
    content: bytes | None = None,
    path: str | Path | None = None,
    title: str | None = None,
    license_class: str | None = None,
    receipt_id: str | None = None,
    allow_unknown: bool = False,
) -> HostResult:
    """Host a book into an account library.

    Content-addressed and idempotent: re-hosting the same bytes for the same
    owner returns the same ``document_id`` with ``already_hosted=True``.

    License rules:
    * ``public_domain`` — host freely
    * ``purchased`` — requires a stored ``receipt_id`` for this owner+book
    * ``unknown`` — refused unless ``allow_unknown=True`` (operator override)
    """
    oid = (owner_id or "").strip()
    if not oid:
        raise ValueError("owner_id is required")

    entry: CatalogEntry | None = None
    if book_id and catalog is not None:
        entry = catalog.get(book_id)
        if entry is None:
            raise KeyError(f"unknown book_id: {book_id}")

    raw, source_format = _load_bytes(content=content, path=path, entry=entry)
    if not raw:
        raise ValueError("content is empty")

    lic = license_class or (entry.license_class if entry else "unknown")
    if lic not in ("public_domain", "purchased", "unknown"):
        raise ValueError(f"invalid license_class: {lic!r}")
    if lic == "unknown" and not allow_unknown:
        raise ValueError(
            "license_class=unknown is deny-by-default; pass allow_unknown=True "
            "only for operator override"
        )
    if lic == "purchased":
        if not receipt_id:
            raise ValueError("purchased license requires receipt_id")
        receipt = store.get_receipt(receipt_id)
        if receipt is None:
            raise ValueError(f"unknown receipt_id: {receipt_id}")
        if receipt.get("owner_id") != oid:
            raise ValueError("receipt owner_id does not match host owner_id")
        if book_id and receipt.get("book_id") != book_id:
            raise ValueError("receipt book_id does not match host book_id")

    chash = _content_hash(raw)
    doc_id = _document_id(oid, chash)
    existing = store.get_document(doc_id)
    body = _decode_body(raw, source_format if source_format != "bytes" else (
        entry.source_format if entry else "text"
    ))
    resolved_title = (
        title
        or (entry.title if entry else None)
        or (book_id or f"Hosted {doc_id}")
    )
    bid = book_id or (entry.book_id if entry else doc_id)

    if existing is not None:
        # Idempotent: ensure membership, return prior
        store.put_membership(oid, doc_id)
        return HostResult(
            document_id=doc_id,
            owner_id=oid,
            book_id=str(existing.get("book_id") or bid),
            content_hash=chash,
            title=str(existing.get("title") or resolved_title),
            license_class=str(existing.get("license_class") or lic),
            body_text=str(existing.get("body_text") or body),
            source_format=str(existing.get("source_format") or source_format),
            already_hosted=True,
        )

    doc: dict[str, Any] = {
        "document_id": doc_id,
        "owner_id": oid,
        "book_id": bid,
        "content_hash": chash,
        "title": resolved_title,
        "license_class": lic,
        "body_text": body,
        "source_format": (
            entry.source_format if entry and source_format == "bytes" else source_format
        ),
        "receipt_id": receipt_id,
        "view_format": "html",  # PDF is never the primary view surface
    }
    store.put_document(doc_id, doc)
    store.put_membership(oid, doc_id)
    return HostResult(
        document_id=doc_id,
        owner_id=oid,
        book_id=str(bid),
        content_hash=chash,
        title=str(resolved_title),
        license_class=lic,
        body_text=body,
        source_format=str(doc["source_format"]),
        already_hosted=False,
    )
