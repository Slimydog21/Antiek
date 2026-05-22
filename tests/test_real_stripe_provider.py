"""RealStripeProvider + get_stripe_provider() factory.

Confirms the factory + the failure modes that produce actionable
``StripeUnavailable`` errors. Does NOT exercise live Stripe API calls.
"""

from __future__ import annotations

import pytest

from tools.stripe_connect import (
    MockStripeProvider,
    RealStripeProvider,
    StripeUnavailable,
    get_stripe_provider,
)


def test_factory_default_is_mock(monkeypatch):
    monkeypatch.delenv("ANTIEK_STRIPE_PROVIDER", raising=False)
    p = get_stripe_provider()
    assert isinstance(p, MockStripeProvider)


def test_factory_mock_explicit(monkeypatch):
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "mock")
    p = get_stripe_provider()
    assert isinstance(p, MockStripeProvider)


def test_factory_real_requires_secret_key(monkeypatch):
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "real")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(StripeUnavailable, match="STRIPE_SECRET_KEY"):
        get_stripe_provider()


def test_real_provider_requires_sdk(monkeypatch):
    """When the stripe SDK isn't installed, RealStripeProvider raises
    StripeUnavailable with an actionable message — the substrate
    boots either way, but a misconfigured production wiring fails
    loudly at the first activation attempt."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")

    # Pretend `stripe` module isn't installed by intercepting the
    # import. Saves us from actually adding/removing the package.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "stripe":
            raise ImportError("simulated: stripe not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(StripeUnavailable, match="not installed"):
        RealStripeProvider()


def test_real_provider_initializes_with_sdk(monkeypatch):
    """When the SDK is available + the key is set, RealStripeProvider
    constructs without error. Doesn't actually call Stripe."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")

    # Inject a fake stripe module into sys.modules so the lazy import
    # succeeds; we don't need a real stripe install for this test.
    import sys
    import types

    fake_stripe = types.ModuleType("stripe")
    fake_stripe.api_key = ""  # type: ignore[attr-defined]
    fake_stripe.api_version = ""  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)

    p = RealStripeProvider()
    assert p.api_key == "sk_test_dummy"
    assert p.stripe is fake_stripe
    # The SDK got the key + version set.
    assert fake_stripe.api_key == "sk_test_dummy"  # type: ignore[attr-defined]
    assert fake_stripe.api_version  # type: ignore[attr-defined]


def test_real_provider_uses_explicit_api_key(monkeypatch):
    """When api_key is passed explicitly, it overrides env var."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    import sys
    import types

    fake_stripe = types.ModuleType("stripe")
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)

    p = RealStripeProvider(api_key="sk_test_explicit")
    assert p.api_key == "sk_test_explicit"


def test_create_connect_account_calls_sdk(monkeypatch):
    """Smoke: create_connect_account hits the stripe SDK with the
    right shape."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    import sys
    import types

    captured: list[dict] = []

    class FakeAccount:
        @staticmethod
        def create(**params):
            captured.append(params)
            return {"id": "acct_test_123"}

    fake_stripe = types.ModuleType("stripe")
    fake_stripe.Account = FakeAccount  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)

    p = RealStripeProvider()
    acct_id = p.create_connect_account(
        display_name="MIT Press",
        legal_contact_email="legal@mitpress.mit.edu",
        account_kind="publisher",
    )
    assert acct_id == "acct_test_123"
    assert len(captured) == 1
    params = captured[0]
    assert params["type"] == "standard"
    assert params["business_profile"]["name"] == "MIT Press"
    assert params["email"] == "legal@mitpress.mit.edu"
    assert params["metadata"]["antiek_account_kind"] == "publisher"


def test_transfer_to_connect_calls_sdk(monkeypatch):
    """Smoke: transfer_to_connect hits Stripe Transfer.create with
    the supplied idempotency_key."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    import sys
    import types

    captured: list[dict] = []

    class FakeTransfer:
        @staticmethod
        def create(**params):
            captured.append(params)
            return {"id": "tr_test_abc"}

    fake_stripe = types.ModuleType("stripe")
    fake_stripe.Transfer = FakeTransfer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)

    p = RealStripeProvider()
    tr_id = p.transfer_to_connect(
        account_id="acct_test_123",
        amount_usd_cents=10_000,
        idempotency_key="payout-2026-05-22-mit",
        metadata={"publisher_id": "mit-press"},
    )
    assert tr_id == "tr_test_abc"
    assert captured[0]["amount"] == 10_000
    assert captured[0]["destination"] == "acct_test_123"
    assert captured[0]["idempotency_key"] == "payout-2026-05-22-mit"
    assert captured[0]["metadata"]["publisher_id"] == "mit-press"
