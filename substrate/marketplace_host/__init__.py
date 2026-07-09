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
    "PurchaseAdapter",
    "PurchaseReceipt",
    "host_into_account",
    "make_catalog",
    "project_hosted_book_html",
]
