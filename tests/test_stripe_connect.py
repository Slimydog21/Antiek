"""Stripe Connect + pricing tests (Sprint 18-19, master-spec §9.5 + §13.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tools.stripe_connect import (
    BillingEvent,
    MockStripeProvider,
    PricingTier,
    StripeAccountStatus,
    StripeConnectAccount,
    StripeOperationsLog,
    TokenUsageRecord,
    apply_margin,
    create_publisher_account,
    create_user_creator_account,
    record_token_usage,
)
from tools.stripe_connect.pricing import (
    CREATOR_AD_REV_SHARE,
    FREE_TIER_MODEL,
    FREE_TIER_MONTHLY_TOKEN_CAP,
    MARGIN_RATES,
    PUBLISHER_AD_REV_SHARE,
)


# ── Pricing-model invariants (operator-decided 2026-05-17) ───────────


def test_margin_rates_match_operator_voice_notes():
    """The 50% private / 10% public / 0% free invariant from operator
    voice notes 2026-05-17 verbatim. Drift here = pollution of the
    'hard-to-vary creative ideas on pricing and ads' the operator
    explicitly named."""
    assert MARGIN_RATES[PricingTier.PAID_PRIVATE] == Decimal("0.50")
    assert MARGIN_RATES[PricingTier.PAID_PUBLIC] == Decimal("0.10")
    assert MARGIN_RATES[PricingTier.FREE_PUBLIC] == Decimal("0.00")


def test_free_tier_monthly_cap_matches_master_spec():
    """Master-spec §13.5: 5M tokens/month free-tier cap with
    DeepSeek-Flash as the model. The cap is what fixes the
    unit-economics problem named in §13.5."""
    assert FREE_TIER_MONTHLY_TOKEN_CAP == 5_000_000
    assert FREE_TIER_MODEL == "deepseek/deepseek-v4-flash"


def test_creator_and_publisher_ad_rev_share_at_70_percent():
    """Master-spec §13.5 + §13.9: 70% of ad revenue routes to the
    contributing user (creator) OR to the IP holder (publisher).
    Same architecture, different population (§13.9 user-as-IP-holder)."""
    assert CREATOR_AD_REV_SHARE == Decimal("0.70")
    assert PUBLISHER_AD_REV_SHARE == Decimal("0.70")
    assert CREATOR_AD_REV_SHARE == PUBLISHER_AD_REV_SHARE  # same architecture


def test_apply_margin_private_50_percent():
    raw = Decimal("10.00")
    margin = apply_margin(raw, PricingTier.PAID_PRIVATE)
    assert margin == Decimal("5.00")


def test_apply_margin_public_10_percent():
    raw = Decimal("10.00")
    margin = apply_margin(raw, PricingTier.PAID_PUBLIC)
    assert margin == Decimal("1.00")


def test_apply_margin_free_zero():
    raw = Decimal("10.00")
    margin = apply_margin(raw, PricingTier.FREE_PUBLIC)
    assert margin == Decimal("0.00")


def test_record_token_usage_computes_billable_correctly():
    record = record_token_usage(
        user_id="user-1",
        tier=PricingTier.PAID_PRIVATE,
        raw_token_cost_usd=Decimal("2.40"),
        investigation_id="inv-x",
    )
    assert record.raw_token_cost_usd == Decimal("2.40")
    assert record.margin_usd == Decimal("1.20")
    assert record.billable_to_user_usd == Decimal("3.60")
    assert record.tier == PricingTier.PAID_PRIVATE


# ── Stripe operations log + idempotency ──────────────────────────────


def test_operations_log_idempotency():
    log = StripeOperationsLog()
    entry1 = log.append_intent(
        op_type="publisher_payout",
        amount_usd_cents=1234,
        substrate_ref="ipholder-X",
        idempotency_key="key-1",
    )
    entry2 = log.append_intent(
        op_type="publisher_payout",
        amount_usd_cents=1234,
        substrate_ref="ipholder-X",
        idempotency_key="key-1",
    )
    # Same idempotency key → same entry, no duplicate.
    assert entry1 is entry2
    assert len(log.log_entries) == 1


def test_operations_log_marks_complete():
    log = StripeOperationsLog()
    log.append_intent(
        op_type="user_creator_payout",
        amount_usd_cents=500,
        substrate_ref="user-creator-1",
        idempotency_key="key-2",
    )
    log.mark_complete(idempotency_key="key-2", provider_ref="tr_real_abc")
    entry = log._find_by_idem("key-2")
    assert entry is not None
    assert entry["status"] == "completed"
    assert entry["completed_at"] is not None
    assert entry["provider_ref"] == "tr_real_abc"


# ── Mock provider ────────────────────────────────────────────────────


def test_mock_provider_creates_connect_account():
    provider = MockStripeProvider()
    acct = create_publisher_account(
        provider,
        display_name="MIT Press",
        legal_contact_email="legal@mitpress.mit.edu",
        ip_holder_id="ipholder-mit",
    )
    assert acct.account_kind == "publisher"
    assert acct.substrate_ref == "ipholder-mit"
    assert acct.status == StripeAccountStatus.PENDING
    assert acct.connect_account_id.startswith("acct_mock_")
    assert acct.connect_account_id in provider.accounts


def test_mock_provider_user_creator_account_same_architecture():
    """Per master-spec §13.9: user-as-IP-holder uses the SAME
    Stripe Connect architecture as publishers — only the population
    differs. The substrate must not duplicate code paths."""
    provider = MockStripeProvider()
    pub_acct = create_publisher_account(
        provider, display_name="A", legal_contact_email=None, ip_holder_id="ip-A",
    )
    user_acct = create_user_creator_account(
        provider, user_id="user-B",
    )
    # Both go through create_connect_account; only account_kind differs.
    assert pub_acct.account_kind == "publisher"
    assert user_acct.account_kind == "user_creator"
    assert pub_acct.status == user_acct.status  # both start PENDING


def test_mock_provider_record_usage_idempotent():
    provider = MockStripeProvider()
    cus_id = provider.create_customer(email="op@x.com", metadata={})
    rec1 = provider.record_usage(
        customer_id=cus_id, amount_usd_cents=100,
        idempotency_key="usage-key-1", metadata={"chunk_id": "c-1"},
    )
    rec2 = provider.record_usage(
        customer_id=cus_id, amount_usd_cents=100,
        idempotency_key="usage-key-1", metadata={"chunk_id": "c-1"},
    )
    assert rec1 == rec2
    assert len(provider.usage_records) == 1
