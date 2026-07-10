"""Residual akr — L5 payment adapter boundary (offline-honest dual-gate).

Disabled posture: typed deferred error · zero upstream call · no $0 invent.
Enabled posture: only when env + upstream; charge required for entitlement.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.marketplace_host.payment_adapter import (  # noqa: E402
    ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV,
    CheckoutSession,
    DeferredPaymentAdapter,
    Entitlement,
    LivePaymentAdapter,
    LivePaymentDeferredError,
    build_payment_adapter,
    live_payment_enabled,
)


class CountingUpstream:
    """Fake live processor — counts invocations for zero-call proof."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_checkout_session(
        self, *, book_id: str, owner_id: str
    ) -> dict:
        self.calls.append(f"create:{book_id}:{owner_id}")
        return {
            "session_id": f"chk_live_{book_id}",
            "status": "ready",
            "book_id": book_id,
            "owner_id": owner_id,
        }

    def confirm_checkout_session(self, *, session_id: str) -> dict:
        self.calls.append(f"confirm:{session_id}")
        return {
            "session_id": session_id,
            "charged": True,
            "paid": True,
            "confirmed": True,
            "book_id": "buy-modern",
            "owner_id": "user-alice",
            "opaque_reference": "merchant_ord_99",
        }


class UnchargedUpstream(CountingUpstream):
    def confirm_checkout_session(self, *, session_id: str) -> dict:
        self.calls.append(f"confirm:{session_id}")
        return {
            "session_id": session_id,
            "charged": False,
            "book_id": "buy-modern",
            "owner_id": "user-alice",
        }


def test_live_payment_env_default_off():
    assert live_payment_enabled(environ={}) is False
    assert live_payment_enabled(environ={ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV: "0"}) is False
    assert live_payment_enabled(environ={ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV: "1"}) is True


def test_build_defaults_to_deferred_even_with_upstream():
    upstream = CountingUpstream()
    adapter = build_payment_adapter(environ={}, upstream=upstream)
    assert isinstance(adapter, DeferredPaymentAdapter)
    session = adapter.create_checkout(book_id="buy-modern", owner_id="user-alice")
    assert session.status == "deferred"
    assert session.live_payment is False
    assert session.payment_path == "manual_receipt_only"
    assert "dual-gate" in session.reason.lower() or "L5" in session.reason
    # Zero upstream calls while deferred.
    assert upstream.calls == []
    assert adapter.upstream_calls == 0


def test_deferred_create_checkout_never_calls_upstream():
    upstream = CountingUpstream()
    adapter = DeferredPaymentAdapter(upstream=upstream)
    session = adapter.create_checkout(book_id="buy-modern", owner_id="alice")
    assert isinstance(session, CheckoutSession)
    assert session.status == "deferred"
    assert session.live_payment is False
    assert upstream.calls == []


def test_deferred_confirm_checkout_raises_typed_error_zero_upstream():
    upstream = CountingUpstream()
    adapter = DeferredPaymentAdapter(upstream=upstream)
    with pytest.raises(LivePaymentDeferredError) as ei:
        adapter.confirm_checkout_session(session_id="chk_anything")
    err = ei.value
    assert err.code == "l5_live_payment_deferred"
    assert err.live_payment is False
    assert err.payment_path == "manual_receipt_only"
    assert upstream.calls == []


def test_deferred_confirm_receipt_manual_path():
    adapter = DeferredPaymentAdapter(upstream=CountingUpstream())
    ent = adapter.confirm_receipt(
        "merchant_order_abc",
        book_id="buy-modern",
        owner_id="user-alice",
    )
    assert isinstance(ent, Entitlement)
    assert ent.live_payment is False
    assert ent.payment_path == "manual_receipt_only"
    assert ent.opaque_reference == "merchant_order_abc"
    assert ent.book_id == "buy-modern"
    # Stable id across calls.
    ent2 = adapter.confirm_receipt(
        "merchant_order_abc",
        book_id="buy-modern",
        owner_id="user-alice",
    )
    assert ent.entitlement_id == ent2.entitlement_id


def test_deferred_confirm_receipt_rejects_card_like_and_empty():
    adapter = DeferredPaymentAdapter()
    with pytest.raises(ValueError, match="card number"):
        adapter.confirm_receipt(
            "4111111111111111",
            book_id="buy-modern",
            owner_id="user-alice",
        )
    with pytest.raises(ValueError, match="opaque_reference"):
        adapter.confirm_receipt("  ", book_id="buy-modern", owner_id="user-alice")
    with pytest.raises(ValueError, match="book_id"):
        adapter.confirm_receipt("ord_1", book_id="", owner_id="user-alice")


def test_live_adapter_requires_env_and_upstream():
    upstream = CountingUpstream()
    # Env alone without upstream → still deferred.
    adapter = build_payment_adapter(
        environ={ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV: "1"},
        upstream=None,
    )
    assert isinstance(adapter, DeferredPaymentAdapter)

    live = build_payment_adapter(
        environ={ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV: "true"},
        upstream=upstream,
    )
    assert isinstance(live, LivePaymentAdapter)
    session = live.create_checkout(book_id="buy-modern", owner_id="user-alice")
    assert session.live_payment is True
    assert session.status == "ready"
    assert session.payment_path == "live_checkout"
    assert "create:buy-modern:user-alice" in upstream.calls

    ent = live.confirm_checkout_session(session_id=session.session_id)
    assert ent.live_payment is True
    assert ent.payment_path == "live_checkout"
    assert ent.checkout_session_id == session.session_id
    assert any(c.startswith("confirm:") for c in upstream.calls)


def test_live_adapter_refuses_uncharged_zero_dollar():
    upstream = UnchargedUpstream()
    live = LivePaymentAdapter(upstream=upstream)
    with pytest.raises(LivePaymentDeferredError) as ei:
        live.confirm_checkout_session(session_id="chk_x")
    assert ei.value.code == "l5_charge_unconfirmed"
    assert ei.value.live_payment is False or ei.value.payment_path == "live_checkout"


def test_live_adapter_manual_receipt_still_available():
    upstream = CountingUpstream()
    live = LivePaymentAdapter(upstream=upstream)
    ent = live.confirm_receipt(
        "manual_ord_7",
        book_id="buy-modern",
        owner_id="user-alice",
    )
    assert ent.live_payment is False
    assert ent.payment_path == "manual_receipt_only"
    # Manual path must not touch live upstream.
    assert upstream.calls == []


def test_public_exports_via_marketplace_host_package():
    from substrate.marketplace_host import (  # noqa: PLC0415
        DeferredPaymentAdapter as ExportedDeferred,
    )
    from substrate.marketplace_host import (
        LivePaymentDeferredError as ExportedErr,
    )
    from substrate.marketplace_host import (
        build_payment_adapter as exported_build,
    )

    assert ExportedDeferred is DeferredPaymentAdapter
    assert ExportedErr is LivePaymentDeferredError
    assert exported_build is build_payment_adapter
