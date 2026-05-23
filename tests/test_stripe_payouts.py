"""Rev-share payout router integration tests.

Exercises the Sprint 23-24 attribution → rev-share payout pipeline
end-to-end against the MockStripeProvider."""

from __future__ import annotations

import pytest

from substrate.anti_gaming.verdict import (
    FraudSignal,
    FraudVerdict,
    FraudVerdictKind,
)
from substrate.rev_share import MINIMUM_PAYOUT_USD_CENTS
from tools.stripe_connect import (
    MockStripeProvider,
    StripeAccountStatus,
    StripeConnectAccount,
)
from tools.stripe_connect.payouts import (
    RevSharePayoutRouter,
    export_tax_year,
    route_impression_revenue,
    _idem_key,
)


def _pass_verdict() -> FraudVerdict:
    return FraudVerdict(kind=FraudVerdictKind.PASS, signals=())


def _review_verdict() -> FraudVerdict:
    return FraudVerdict(
        kind=FraudVerdictKind.REVIEW,
        signals=(FraudSignal(name="review_test", score=0.5, detail="test"),),
    )


def _block_verdict() -> FraudVerdict:
    return FraudVerdict(
        kind=FraudVerdictKind.BLOCK,
        signals=(FraudSignal(name="block_test", score=0.9, detail="test"),),
    )


def _make_router_with_active_creator(creator_id: str = "u-1") -> RevSharePayoutRouter:
    provider = MockStripeProvider()
    router = RevSharePayoutRouter(provider=provider)
    acct_id = provider.create_connect_account(
        display_name=creator_id,
        legal_contact_email=None,
        account_kind="user_creator",
    )
    router.register_account(StripeConnectAccount(
        connect_account_id=acct_id,
        account_kind="user_creator",
        substrate_ref=creator_id,
        status=StripeAccountStatus.ACTIVE,
    ))
    return router


def test_idempotency_key_is_deterministic():
    assert _idem_key("imp-1", "u-1") == _idem_key("imp-1", "u-1")
    assert _idem_key("imp-1", "u-1") != _idem_key("imp-2", "u-1")


def test_block_verdict_drops_revenue_audit_logged():
    router = _make_router_with_active_creator()
    outcomes, result = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=10_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_block_verdict(),
        current_month_index=100,
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "blocked"
    assert result.lines == ()
    # Operations log got the blocked entry.
    assert any(e["op_type"] == "payout_blocked" for e in router.operations_log.log_entries)
    # No transfer made.
    assert len(router.provider.transfers) == 0


def test_review_verdict_escrows_no_transfer():
    router = _make_router_with_active_creator()
    outcomes, _ = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=MINIMUM_PAYOUT_USD_CENTS * 5,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_review_verdict(),
        current_month_index=100,
    )
    assert all(o.status == "escrowed" for o in outcomes)
    assert len(router.provider.transfers) == 0
    # No accrual in the ledger either — review queue holds it.
    assert router.rollover_ledger.entry_for("u-1").balance_cents == 0


def test_pass_above_threshold_transfers_via_stripe():
    router = _make_router_with_active_creator()
    outcomes, _ = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=10_000,  # 100% → creator pool 7000 × 1.0 share = 7000 ≥ 1000
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "transferred"
    assert outcomes[0].provider_ref is not None
    assert outcomes[0].amount_cents == 7000
    # Stripe got one transfer.
    assert len(router.provider.transfers) == 1
    # Platform residual collected the 3000.
    assert router.platform_residual_cents == 3000


def test_pass_below_threshold_rolls_over():
    router = _make_router_with_active_creator()
    outcomes, _ = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=100,  # → creator gets 70 cents < 1000c threshold
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    assert outcomes[0].status == "rolled_over"
    assert len(router.provider.transfers) == 0
    assert router.rollover_ledger.entry_for("u-1").balance_cents == 70


def test_pass_no_active_account_kyc_pending():
    """A creator with no Stripe account gets accrued but not paid."""
    provider = MockStripeProvider()
    router = RevSharePayoutRouter(provider=provider)
    outcomes, _ = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=10_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-unknown")},
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    assert outcomes[0].status == "kyc_pending"
    assert len(router.provider.transfers) == 0
    # Accrual is in the ledger so the creator is owed.
    assert router.rollover_ledger.entry_for("u-unknown").balance_cents == 7000


def test_pending_account_status_kyc_pending():
    """A registered but PENDING account (KYC incomplete) also blocks transfer."""
    provider = MockStripeProvider()
    router = RevSharePayoutRouter(provider=provider)
    acct_id = provider.create_connect_account(
        display_name="u-1", legal_contact_email=None, account_kind="user_creator",
    )
    router.register_account(StripeConnectAccount(
        connect_account_id=acct_id,
        account_kind="user_creator",
        substrate_ref="u-1",
        status=StripeAccountStatus.PENDING,
    ))
    outcomes, _ = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=10_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    assert outcomes[0].status == "kyc_pending"
    assert len(router.provider.transfers) == 0


def test_replay_same_impression_no_double_charge():
    """Stripe idempotency_key ensures re-running the same impression
    yields the same transfer id, not two transfers."""
    router = _make_router_with_active_creator()
    args = dict(
        impression_id="imp-1",
        ad_revenue_cents=10_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    out1, _ = route_impression_revenue(router, **args)
    transfers_after_first = len(router.provider.transfers)
    # The router accrued + settled — second call accrues again so the
    # ledger crosses threshold again; but the idempotency key is keyed
    # on (impression_id, recipient_ref), so Stripe re-uses the prior
    # transfer id.
    out2, _ = route_impression_revenue(router, **args)
    assert out1[0].provider_ref == out2[0].provider_ref
    # Stripe saw two attempts but only one transfer id was created.
    assert len(router.provider.transfers) == transfers_after_first


def test_mixed_creator_and_publisher_split():
    router = _make_router_with_active_creator(creator_id="u-1")
    # Register a publisher account too.
    pub_id = router.provider.create_connect_account(
        display_name="pub-1", legal_contact_email=None, account_kind="publisher",
    )
    router.register_account(StripeConnectAccount(
        connect_account_id=pub_id,
        account_kind="publisher",
        substrate_ref="ip-1",
        status=StripeAccountStatus.ACTIVE,
    ))
    outcomes, result = route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=10_000,
        attribution_shares={"doc-A": 0.5, "doc-B": 0.5},
        document_to_recipient={
            "doc-A": ("creator", "u-1"),
            "doc-B": ("publisher", "ip-1"),
        },
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    by_kind = {o.kind: o for o in outcomes}
    assert by_kind["creator"].status == "transferred"
    assert by_kind["publisher"].status == "transferred"
    # 30/70 of 10000 → 7000 IP pool. 50/50 split → 3500 each.
    assert by_kind["creator"].amount_cents == 3500
    assert by_kind["publisher"].amount_cents == 3500


def test_export_tax_year_aggregates_completed_transfers():
    router = _make_router_with_active_creator()
    route_impression_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_cents=10_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={"doc-1": ("creator", "u-1")},
        verdict=_pass_verdict(),
        current_month_index=100,
    )
    # Pull a tax year that matches "now" — completion timestamps are ISO with
    # a current-year prefix. We accept that the test runs in a year matching
    # datetime.utcnow().year.
    from datetime import datetime, timezone
    year = datetime.now(timezone.utc).year
    rows = export_tax_year(router, year=year)
    assert len(rows) == 1
    assert rows[0].recipient_ref == "u-1"
    assert rows[0].total_paid_cents == 7000
    assert len(rows[0].transfer_refs) == 1
