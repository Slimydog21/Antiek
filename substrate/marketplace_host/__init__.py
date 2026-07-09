"""Book marketplace + host-into-account (package B).

Pure offline substrate:

* **Catalog** — PD + purchasable stubs with explicit ``license_class``
* **Host-into-account** — content-addressed document id owned by an account
* **Library** — per-owner listing of hosted document ids
* **Purchase** — pluggable receipt protocol; default is manual/opaque proof
* **View** — HTML projection (PDF may be ingest *source* only)

No Stripe, no DRM circumvention, no live payment rails.
"""

from __future__ import annotations

from .catalog import Catalog, CatalogEntry, LicenseClass, make_catalog
from .host import HostResult, host_into_account
from .library import AccountLibrary, InMemoryHostStore
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
    "AccountLibrary",
    "Catalog",
    "CatalogEntry",
    "HostResult",
    "InMemoryHostStore",
    "LicenseClass",
    "ManualPurchaseReceipt",
    "MarketplaceHostProductResult",
    "PurchaseAdapter",
    "PurchaseReceipt",
    "default_demo_catalog",
    "host_book_into_account",
    "host_into_account",
    "list_account_library_html",
    "make_catalog",
    "project_catalog_html",
    "project_hosted_book_html",
    "record_purchase_and_host",
]
