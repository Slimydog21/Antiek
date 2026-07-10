"""Book marketplace + host-into-account (package B).

Pure offline substrate:

* **Catalog** — PD + purchasable stubs with explicit ``license_class``
* **Host-into-account** — content-addressed document id owned by an account
* **Library** — per-owner listing of hosted document ids
* **Purchase** — pluggable receipt protocol; default is manual/opaque proof
* **Payment adapter (akr / L5 Sprint 1)** — live rails dual-gate deferred by default
* **View** — HTML projection (PDF may be ingest *source* only)

No Stripe, no DRM circumvention, no live payment rails (unless operator dual-gate).
"""

from __future__ import annotations

from .catalog import Catalog, CatalogEntry, LicenseClass, make_catalog
from .host import HostResult, host_into_account
from .library import AccountLibrary, InMemoryHostStore
from .payment_adapter import (
    ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV,
    CheckoutSession,
    DeferredPaymentAdapter,
    Entitlement,
    LivePaymentAdapter,
    LivePaymentDeferredError,
    PaymentAdapter as LiveRailsPaymentAdapter,
    PaymentUpstream,
    build_payment_adapter,
    live_payment_enabled,
)
from .product_path import (
    MarketplaceHostProductResult,
    default_demo_catalog,
    host_book_into_account,
    list_account_library_html,
    project_catalog_html,
    record_purchase_and_host,
)
from .purchase import ManualPurchaseReceipt, PurchaseAdapter, PurchaseReceipt
from .view import project_hosted_book_html

__all__ = [
    "ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV",
    "AccountLibrary",
    "Catalog",
    "CatalogEntry",
    "CheckoutSession",
    "DeferredPaymentAdapter",
    "Entitlement",
    "HostResult",
    "InMemoryHostStore",
    "LicenseClass",
    "LivePaymentAdapter",
    "LivePaymentDeferredError",
    "LiveRailsPaymentAdapter",
    "ManualPurchaseReceipt",
    "MarketplaceHostProductResult",
    "PaymentUpstream",
    "PurchaseAdapter",
    "PurchaseReceipt",
    "build_payment_adapter",
    "default_demo_catalog",
    "host_book_into_account",
    "host_into_account",
    "list_account_library_html",
    "live_payment_enabled",
    "make_catalog",
    "project_catalog_html",
    "project_hosted_book_html",
    "record_purchase_and_host",
]
