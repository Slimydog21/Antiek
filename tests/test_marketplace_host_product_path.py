"""Product path: catalog → host-into-account → library → HTML (residual ae)."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.marketplace_host import (  # noqa: E402
    InMemoryHostStore,
    default_demo_catalog,
    host_book_into_account,
    list_account_library_html,
    record_purchase_and_host,
)


@pytest.fixture
def store():
    return InMemoryHostStore()


@pytest.fixture
def catalog():
    return default_demo_catalog()


def test_host_pd_product_path_stable_identity(store, catalog):
    r1 = host_book_into_account(
        owner_id="user-alice",
        store=store,
        book_id="pd-pride",
        catalog=catalog,
    )
    assert r1.view_format == "html"
    assert r1.host.document_id.startswith("hdoc_")
    assert r1.host.already_hosted is False
    assert r1.host.document_id in r1.library_document_ids
    assert r1.html.strip()
    assert not r1.html.lstrip().lower().startswith("%pdf")
    assert "truth" in r1.html.lower() or "Pride" in r1.html

    r2 = host_book_into_account(
        owner_id="user-alice",
        store=store,
        book_id="pd-pride",
        catalog=catalog,
    )
    assert r2.host.document_id == r1.host.document_id
    assert r2.host.already_hosted is True
    assert r2.host.content_hash == r1.host.content_hash


def test_purchased_requires_receipt_then_succeeds(store, catalog):
    with pytest.raises(ValueError, match="receipt"):
        host_book_into_account(
            owner_id="user-alice",
            store=store,
            book_id="buy-modern",
            catalog=catalog,
            content=b"%PDF-1.4 fake body for purchase host",
        )

    receipt, result = record_purchase_and_host(
        owner_id="user-alice",
        store=store,
        book_id="buy-modern",
        catalog=catalog,
        opaque_reference="ORDER-ACME-42",
        content=b"%PDF-1.4 fake body for purchase host",
    )
    assert receipt.receipt_id.startswith("rcpt_")
    assert result.host.license_class == "purchased"
    assert result.view_format == "html"
    assert not result.host.body_text.lstrip().startswith("%PDF")
    assert result.html.strip()
    assert result.host.document_id in result.library_document_ids


def test_library_html_lists_hosted(store, catalog):
    host_book_into_account(
        owner_id="user-lib",
        store=store,
        book_id="pd-pride",
        catalog=catalog,
    )
    html = list_account_library_html("user-lib", store=store)
    assert "Library" in html or "pd-pride" in html or "Pride" in html
    assert "application/pdf" not in html.lower()


def test_double_run_launch_stable(store, catalog):
    a = host_book_into_account(
        owner_id="launch-user",
        store=store,
        book_id="pd-pride",
        catalog=catalog,
    )
    b = host_book_into_account(
        owner_id="launch-user",
        store=store,
        book_id="pd-pride",
        catalog=catalog,
    )
    assert a.host.document_id == b.host.document_id
    assert a.html and b.html
    assert a.view_format == b.view_format == "html"
