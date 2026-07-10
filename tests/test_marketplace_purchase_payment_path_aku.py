"""Residual aku — L5 Sprint 2 purchase path via payment adapter (offline-safe).

checkout_session_id on deferred dual-gate → LivePaymentDeferredError (no host).
opaque_reference manual path unchanged. Live path only with env + upstream.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.marketplace_host import (  # noqa: E402
    ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV,
    InMemoryHostStore,
    LivePaymentDeferredError,
    build_payment_adapter,
    default_demo_catalog,
    record_purchase_and_host,
)
from substrate.marketplace_host.catalog import CatalogEntry, make_catalog  # noqa: E402


@pytest.fixture
def store():
    return InMemoryHostStore()


@pytest.fixture
def catalog():
    # Ensure a purchased stub exists (demo catalog may vary).
    base = default_demo_catalog()
    entries = list(base.entries) if hasattr(base, "entries") else []
    # default_demo_catalog is Catalog — use get + inject buy-modern if missing.
    if base.get("buy-modern") is None:
        entries = [
            CatalogEntry(
                book_id="buy-modern",
                title="Modern Systems Research",
                author="Example Press",
                source="marketplace_stub",
                license_class="purchased",
                is_free=False,
                body_text="",
                source_format="pdf",
            )
        ]
        # merge with pride if needed
        pride = base.get("pd-pride")
        if pride is not None:
            entries.insert(0, pride)
        return make_catalog(entries)
    return base


class LiveUpstream:
    def create_checkout_session(self, *, book_id: str, owner_id: str) -> dict:
        return {
            "session_id": f"chk_{book_id}",
            "status": "ready",
            "book_id": book_id,
            "owner_id": owner_id,
        }

    def confirm_checkout_session(self, *, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "charged": True,
            "paid": True,
            "confirmed": True,
            "book_id": "buy-modern",
            "owner_id": "user-alice",
            "opaque_reference": "merchant_live_99",
        }


def test_manual_opaque_path_unchanged(store, catalog):
    receipt, result = record_purchase_and_host(
        owner_id="user-alice",
        store=store,
        book_id="buy-modern",
        catalog=catalog,
        opaque_reference="ORDER-ACME-42",
        content=b"%PDF-1.4 purchase body",
    )
    assert receipt.receipt_id.startswith("rcpt_")
    assert result.view_format == "html"
    assert result.host.license_class == "purchased"
    assert not result.host.body_text.lstrip().startswith("%PDF")


def test_checkout_session_deferred_raises_no_host(store, catalog):
    """Sprint 2 offline-safe: checkout_session without dual-gate never hosts."""
    before = AccountLibrary_load_safe(store, "user-alice")
    with pytest.raises(LivePaymentDeferredError) as ei:
        record_purchase_and_host(
            owner_id="user-alice",
            store=store,
            book_id="buy-modern",
            catalog=catalog,
            checkout_session_id="chk_would_be_live",
            content=b"%PDF-1.4 should not host",
        )
    assert ei.value.code == "l5_live_payment_deferred"
    assert ei.value.live_payment is False
    after = AccountLibrary_load_safe(store, "user-alice")
    assert after == before


def test_requires_opaque_or_session(store, catalog):
    with pytest.raises(ValueError, match="opaque_reference or checkout_session_id"):
        record_purchase_and_host(
            owner_id="user-alice",
            store=store,
            book_id="buy-modern",
            catalog=catalog,
            content=b"%PDF-1.4",
        )


def test_manual_wins_when_both_provided(store, catalog):
    """Prefer offline-honest manual receipt when both paths supplied."""
    receipt, result = record_purchase_and_host(
        owner_id="user-alice",
        store=store,
        book_id="buy-modern",
        catalog=catalog,
        opaque_reference="MANUAL-WINS",
        checkout_session_id="chk_ignored",
        content=b"%PDF-1.4 manual wins body",
    )
    assert receipt.opaque_reference == "MANUAL-WINS"
    assert result.view_format == "html"


def test_live_checkout_hosts_when_dual_gate_and_upstream(store, catalog):
    rails = build_payment_adapter(
        environ={ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV: "1"},
        upstream=LiveUpstream(),
    )
    session = rails.create_checkout(book_id="buy-modern", owner_id="user-alice")
    assert session.live_payment is True
    receipt, result = record_purchase_and_host(
        owner_id="user-alice",
        store=store,
        book_id="buy-modern",
        catalog=catalog,
        checkout_session_id=session.session_id,
        content=b"%PDF-1.4 live charged body",
        payment_adapter=rails,
    )
    assert receipt.opaque_reference == "merchant_live_99"
    assert "live_checkout" in (receipt.note or "")
    assert result.view_format == "html"
    assert result.host.document_id in result.library_document_ids


def AccountLibrary_load_safe(store, owner_id: str) -> list[str]:
    from substrate.marketplace_host.library import AccountLibrary

    try:
        return list(AccountLibrary.load(owner_id, store=store).document_ids)
    except Exception:
        return []
