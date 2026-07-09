"""Real-path tests for book marketplace host-into-account (package B).

Drives shipped functions: catalog, host_into_account, library membership,
manual receipt, HTML view. No network, no Stripe.
"""

from __future__ import annotations

import os
import sys

import pytest

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
from substrate.marketplace_host.library import FileHostStore  # noqa: E402


@pytest.fixture
def store():
    return InMemoryHostStore()


@pytest.fixture
def pd_catalog():
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
            CatalogEntry(
                book_id="unk-1",
                title="Mystery Scan",
                author="Unknown",
                source="upload",
                license_class="unknown",
                is_free=False,
            ),
        ]
    )


def test_catalog_license_classes_and_search(pd_catalog):
    hits = pd_catalog.search("pride")
    assert len(hits) == 1
    assert hits[0].license_class == "public_domain"
    assert hits[0].is_free is True
    buy = pd_catalog.get("buy-modern")
    assert buy is not None
    assert buy.is_free is False
    assert buy.license_class == "purchased"


def test_catalog_rejects_incoherent_free_flags():
    cat = make_catalog()
    with pytest.raises(ValueError, match="is_free"):
        cat.add(
            CatalogEntry(
                book_id="x",
                title="t",
                author="a",
                source="s",
                license_class="purchased",
                is_free=True,
            )
        )


def test_host_pd_content_addressed_idempotent(store, pd_catalog):
    r1 = host_into_account(
        owner_id="user-alice",
        store=store,
        book_id="pd-pride",
        catalog=pd_catalog,
    )
    assert r1.document_id.startswith("hdoc_")
    assert r1.already_hosted is False
    assert r1.license_class == "public_domain"
    assert "truth universally acknowledged" in r1.body_text

    r2 = host_into_account(
        owner_id="user-alice",
        store=store,
        book_id="pd-pride",
        catalog=pd_catalog,
    )
    assert r2.document_id == r1.document_id
    assert r2.already_hosted is True
    assert r2.content_hash == r1.content_hash

    # Different owner → different document_id (per-owner addressing)
    r3 = host_into_account(
        owner_id="user-bob",
        store=store,
        book_id="pd-pride",
        catalog=pd_catalog,
    )
    assert r3.document_id != r1.document_id


def test_library_lists_hosted_document(store, pd_catalog):
    r = host_into_account(
        owner_id="user-alice",
        store=store,
        book_id="pd-pride",
        catalog=pd_catalog,
    )
    lib = AccountLibrary.load("user-alice", store=store)
    assert r.document_id in lib.document_ids


def test_host_purchased_requires_receipt(store, pd_catalog):
    with pytest.raises(ValueError, match="receipt"):
        host_into_account(
            owner_id="user-alice",
            store=store,
            book_id="buy-modern",
            catalog=pd_catalog,
            content=b"%PDF-1.4 fake binary book body for host test",
        )

    adapter = ManualPurchaseReceipt(store=store)
    receipt = adapter.record_receipt(
        book_id="buy-modern",
        owner_id="user-alice",
        opaque_reference="ORDER-ACME-998877",
        note="manual operator receipt",
    )
    assert receipt.receipt_id.startswith("rcpt_")
    # No card-like digits-only reference
    with pytest.raises(ValueError, match="card"):
        adapter.record_receipt(
            book_id="buy-modern",
            owner_id="user-alice",
            opaque_reference="4111111111111111",
        )

    hosted = host_into_account(
        owner_id="user-alice",
        store=store,
        book_id="buy-modern",
        catalog=pd_catalog,
        content=b"%PDF-1.4 fake binary book body for host test",
        receipt_id=receipt.receipt_id,
    )
    assert hosted.license_class == "purchased"
    assert hosted.document_id in AccountLibrary.load("user-alice", store=store).document_ids
    # Body is HTML-view text, not raw PDF requirement
    assert not hosted.body_text.lstrip().startswith("%PDF")
    assert "HTML" in hosted.body_text or "hash" in hosted.body_text.lower()


def test_host_unknown_denied_by_default(store, pd_catalog):
    with pytest.raises(ValueError, match="unknown"):
        host_into_account(
            owner_id="user-alice",
            store=store,
            book_id="unk-1",
            catalog=pd_catalog,
            content=b"mystery text",
        )


def test_project_hosted_book_html_not_pdf(store, pd_catalog):
    r = host_into_account(
        owner_id="user-alice",
        store=store,
        book_id="pd-pride",
        catalog=pd_catalog,
    )
    html = project_hosted_book_html(r.document_id, store=store)
    assert html and len(html) > 40
    assert "<" in html
    assert not html.lstrip().lower().startswith("%pdf")
    assert "Pride" in html or "truth" in html.lower() or "License" in html
    # view_format contract
    doc = store.get_document(r.document_id)
    assert doc is not None
    assert doc.get("view_format") == "html"


def test_host_from_path_file_store(tmp_path):
    path = tmp_path / "essay.txt"
    path.write_text("Chapter one.\n\nChapter two about graphs.", encoding="utf-8")
    store = FileHostStore(tmp_path / "host-root")
    r = host_into_account(
        owner_id="user-path",
        store=store,
        path=path,
        title="Essay",
        license_class="public_domain",
        book_id="local-essay",
    )
    assert r.document_id.startswith("hdoc_")
    html = project_hosted_book_html(r.document_id, store=store)
    assert "Chapter" in html or "Essay" in html
    lib = AccountLibrary.load("user-path", store=store)
    assert r.document_id in lib.document_ids
