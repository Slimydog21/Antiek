"""Product path: catalog → host-into-account → library → HTML view.

Composes existing ``host_into_account``, receipt adapter, library list, and
``project_hosted_book_html`` without reimplementing content-addressing or
license gates. PDF may be ingest source only; human view is HTML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import Catalog, CatalogEntry
from .host import HostResult, host_into_account
from .library import AccountLibrary, HostStore
from .purchase import ManualPurchaseReceipt, PurchaseReceipt
from .view import project_hosted_book_html


@dataclass(frozen=True)
class MarketplaceHostProductResult:
    """Outcome of the host-into-account product entry."""

    host: HostResult
    library_document_ids: tuple[str, ...]
    html: str
    view_format: str = "html"

    def to_dict(self) -> dict[str, Any]:
        h = self.host
        return {
            "document_id": h.document_id,
            "owner_id": h.owner_id,
            "book_id": h.book_id,
            "content_hash": h.content_hash,
            "title": h.title,
            "license_class": h.license_class,
            "already_hosted": h.already_hosted,
            "source_format": h.source_format,
            "library_document_ids": list(self.library_document_ids),
            "view_format": self.view_format,
            "html": self.html,
            "body_preview": (h.body_text or "")[:280],
        }


def host_book_into_account(
    *,
    owner_id: str,
    store: HostStore,
    book_id: str,
    catalog: Catalog,
    content: bytes | None = None,
    receipt_id: str | None = None,
    allow_unknown: bool = False,
) -> MarketplaceHostProductResult:
    """Product entry: host catalog book into account and return HTML view.

    * public_domain / free catalog body hosts without receipt
    * purchased requires ``receipt_id`` already on the store
    * Re-host same content → same ``document_id`` / ``already_hosted=True``
    """
    if not owner_id or not owner_id.strip():
        raise ValueError("owner_id is required")
    if not book_id or not book_id.strip():
        raise ValueError("book_id is required")
    entry = catalog.get(book_id)
    if entry is None:
        raise KeyError(f"unknown book_id: {book_id}")

    host = host_into_account(
        owner_id=owner_id.strip(),
        store=store,
        book_id=book_id.strip(),
        catalog=catalog,
        content=content,
        receipt_id=receipt_id,
        allow_unknown=allow_unknown,
    )
    lib = AccountLibrary.load(owner_id.strip(), store=store)
    if host.document_id not in lib.document_ids:
        raise RuntimeError("host succeeded but document missing from library membership")
    html = project_hosted_book_html(host.document_id, store=store)
    if not html or not html.strip():
        raise RuntimeError("HTML projection empty after host")
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("hosted view must not be PDF")
    return MarketplaceHostProductResult(
        host=host,
        library_document_ids=tuple(lib.document_ids),
        html=html,
        view_format="html",
    )


def record_purchase_and_host(
    *,
    owner_id: str,
    store: HostStore,
    book_id: str,
    catalog: Catalog,
    opaque_reference: str,
    content: bytes,
    note: str = "",
) -> tuple[PurchaseReceipt, MarketplaceHostProductResult]:
    """Product entry for purchased books: record manual receipt, then host.

    No Stripe — opaque order/receipt token only.
    """
    entry = catalog.get(book_id)
    if entry is None:
        raise KeyError(f"unknown book_id: {book_id}")
    if entry.license_class != "purchased":
        raise ValueError(
            f"record_purchase_and_host requires purchased book; got {entry.license_class!r}"
        )
    adapter = ManualPurchaseReceipt(store=store)
    receipt = adapter.record_receipt(
        book_id=book_id,
        owner_id=owner_id,
        opaque_reference=opaque_reference,
        note=note,
    )
    result = host_book_into_account(
        owner_id=owner_id,
        store=store,
        book_id=book_id,
        catalog=catalog,
        content=content,
        receipt_id=receipt.receipt_id,
    )
    return receipt, result


def list_account_library_html(
    owner_id: str,
    *,
    store: HostStore,
) -> str:
    """HTML listing of hosted documents for an account (never PDF)."""
    from substrate.engagement_spine.project import project_to_html

    lib = AccountLibrary.load(owner_id, store=store)
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": f"Library — {owner_id}"}],
        }
    ]
    if not lib.document_ids:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(empty library)"}],
            }
        )
    for doc_id in lib.document_ids:
        doc = store.get_document(doc_id) or {}
        title = str(doc.get("title") or doc_id)
        lic = str(doc.get("license_class") or "?")
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[{lic}] {title} ({doc_id})",
                    }
                ],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"lib-{owner_id}",
        creator="marketplace_host",
    )


def default_demo_catalog() -> Catalog:
    """Fixed offline catalog fixture for product/API tests and demos."""
    from .catalog import make_catalog

    return make_catalog(
        [
            CatalogEntry(
                book_id="pd-pride",
                title="Pride and Prejudice",
                author="Jane Austen",
                source="standard_ebooks",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "It is a truth universally acknowledged, that a single man "
                    "in possession of a good fortune, must be in want of a wife.\n\n"
                    "However little known the feelings or views of such a man may be."
                ),
                source_format="html",
            ),
            CatalogEntry(
                book_id="buy-modern",
                title="Modern Systems Research",
                author="Example Press",
                source="marketplace_stub",
                license_class="purchased",
                is_free=False,
                body_text="",
                source_format="pdf",
            ),
        ]
    )
