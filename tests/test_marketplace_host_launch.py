"""Consumer-path double-run for host_into_account + HTML view.

Drives the public package entry points with fixed fixtures so document ids
are content-addressed and stable across two runs. Assertions check title,
body, library membership, and non-PDF HTML — not merely non-empty.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.marketplace_host import (  # noqa: E402
    AccountLibrary,
    CatalogEntry,
    InMemoryHostStore,
    ManualPurchaseReceipt,
    host_into_account,
    make_catalog,
    project_hosted_book_html,
)

# Fixed fixture bytes — content-addressed ids must stay stable for these.
_PD_BODY = (
    "Opening paragraph about knowledge graphs.\n\n"
    "Second paragraph on twin notes."
)
_PAID_BYTES = b"%PDF-1.4 paid payload"
_OWNER = "op1"


def _fixture_catalog():
    return make_catalog(
        [
            CatalogEntry(
                book_id="pd-launch",
                title="Launch Essay",
                author="Operator",
                source="fixture",
                license_class="public_domain",
                is_free=True,
                body_text=_PD_BODY,
            ),
            CatalogEntry(
                book_id="buy-launch",
                title="Paid Title",
                author="Press",
                source="stub",
                license_class="purchased",
                is_free=False,
                source_format="pdf",
            ),
        ]
    )


def _run_once() -> tuple[str, str, int, int]:
    store = InMemoryHostStore()
    cat = _fixture_catalog()
    pd = host_into_account(
        owner_id=_OWNER,
        store=store,
        book_id="pd-launch",
        catalog=cat,
    )
    assert pd.title == "Launch Essay"
    assert "knowledge graphs" in pd.body_text
    assert not pd.body_text.lstrip().startswith("%PDF")
    assert pd.document_id.startswith("hdoc_")

    pd_html = project_hosted_book_html(pd.document_id, store=store)
    assert "Launch Essay" in pd_html or "knowledge" in pd_html.lower()
    assert not pd_html.lstrip().lower().startswith("%pdf")
    assert len(pd_html) > 40

    lib = AccountLibrary.load(_OWNER, store=store)
    assert pd.document_id in lib.document_ids

    receipt = ManualPurchaseReceipt(store=store).record_receipt(
        book_id="buy-launch",
        owner_id=_OWNER,
        opaque_reference="ORD-1",
    )
    paid = host_into_account(
        owner_id=_OWNER,
        store=store,
        book_id="buy-launch",
        catalog=cat,
        content=_PAID_BYTES,
        receipt_id=receipt.receipt_id,
    )
    assert paid.title == "Paid Title"
    assert not paid.body_text.lstrip().startswith("%PDF")
    assert "HTML" in paid.body_text or "hash" in paid.body_text.lower()

    paid_html = project_hosted_book_html(paid.document_id, store=store)
    assert "Paid Title" in paid_html or "License" in paid_html
    assert not paid_html.lstrip().lower().startswith("%pdf")
    assert len(paid_html) > 40

    return pd.document_id, paid.document_id, len(pd_html), len(paid_html)


def test_consumer_launch_double_run_stable_ids():
    """Two independent consumer launches must yield identical content-addressed ids."""
    a = _run_once()
    b = _run_once()
    assert a[0] == b[0], f"pd id drift: {a[0]} vs {b[0]}"
    assert a[1] == b[1], f"paid id drift: {a[1]} vs {b[1]}"
    assert a[2] == b[2]
    assert a[3] == b[3]
    # Golden content-addressed values for the fixed fixtures above (sha256 host:v1).
    assert a[0] == "hdoc_ad08b76de6662f4ed9aea2b5"
    assert a[1] == "hdoc_326b27e5369b6a53546432c0"
