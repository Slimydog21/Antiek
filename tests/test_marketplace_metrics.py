"""Marketplace metrics tests (Sprint 25+ §2 dashboard data layer)."""

from __future__ import annotations

import pytest

from substrate.marketplace_metrics import (
    AdvertiserActivity,
    AdvertiserRetentionReport,
    CreatorEarningsDistribution,
    EarningsBucket,
    MarketplaceHealth,
    MarketplaceSnapshot,
    PublisherEscrowReport,
    PublisherStatusCounts,
    assemble_snapshot,
    classify_health,
    compute_advertiser_retention,
    compute_creator_distribution,
    compute_publisher_escrow,
)


# ── Creator distribution ──────────────────────────────────────────


def test_empty_creator_distribution_is_zero_everything():
    d = compute_creator_distribution({})
    assert d.creator_count == 0
    assert d.total_paid_cents == 0
    assert d.median_cents == 0
    assert d.p90_cents == 0
    assert d.long_tail_mass == 0.0
    assert d.buckets == ()


def test_creator_distribution_percentiles():
    # 100 creators with linearly rising earnings: 100, 200, ..., 10000.
    creators = {f"u-{i}": i * 100 for i in range(1, 101)}
    d = compute_creator_distribution(creators)
    assert d.creator_count == 100
    assert d.total_paid_cents == sum(creators.values())
    # Median of a linear distribution ≈ midpoint.
    assert 4900 <= d.median_cents <= 5100
    # p90 should be near the top.
    assert 8900 <= d.p90_cents <= 9100


def test_long_tail_mass_concentrated_when_winner_takes_all():
    """When top creator owns 99% of earnings, long-tail mass is tiny."""
    creators = {"top": 99_000}
    for i in range(99):
        creators[f"u-{i}"] = 10
    d = compute_creator_distribution(creators)
    # Bottom-50 should hold a tiny share of total.
    assert d.long_tail_mass < 0.05


def test_long_tail_mass_high_when_distribution_flat():
    """A perfectly flat distribution has long-tail mass = 0.5 - epsilon."""
    creators = {f"u-{i}": 1000 for i in range(20)}
    d = compute_creator_distribution(creators)
    assert d.long_tail_mass == pytest.approx(0.5)


def test_buckets_classify_correctly():
    creators = {
        "u-cents": 50,         # < $1
        "u-dollars": 500,      # $1-9.99
        "u-tens": 1500,        # $10-49.99
        "u-hundred": 7500,     # $50-249.99
        "u-thousand": 50_000,  # $250-999.99
        "u-big": 200_000,      # $1000+
    }
    d = compute_creator_distribution(creators)
    by_lo = {b.lower_cents: b.creator_count for b in d.buckets}
    assert by_lo[0] == 1
    assert by_lo[100] == 1
    assert by_lo[1_000] == 1
    assert by_lo[5_000] == 1
    assert by_lo[25_000] == 1
    assert by_lo[100_000] == 1


# ── Publisher escrow ──────────────────────────────────────────────


def test_publisher_status_counts_claim_rate():
    counts = PublisherStatusCounts(pre_onboarded=10, invited=4, claimed=4, opted_out=2)
    # claim_rate = 4 / (4 + 4 + 2) = 0.4
    assert counts.claim_rate == pytest.approx(0.4)
    assert counts.opt_out_rate == pytest.approx(0.2)
    assert counts.total == 20


def test_publisher_escrow_zero_decided_is_zero_rate():
    counts = PublisherStatusCounts(pre_onboarded=10)
    assert counts.claim_rate == 0.0
    assert counts.opt_out_rate == 0.0


def test_compute_publisher_escrow_aggregates():
    rows = [
        ("ip-1", "claimed"),
        ("ip-2", "invited"),
        ("ip-3", "opted_out"),
        ("ip-4", "pre_onboarded"),
    ]
    accruals = {"ip-1": 50_000, "ip-2": 10_000, "ip-3": 2_000, "ip-4": 0}
    paid = {"ip-1": 30_000}
    report = compute_publisher_escrow(
        publisher_status_rows=rows,
        publisher_accrual_cents=accruals,
        publisher_paid_cents=paid,
    )
    assert report.status_counts.claimed == 1
    assert report.total_escrow_accrued_cents == 62_000
    assert report.total_escrow_paid_cents == 30_000
    # ip-2 + ip-3 + ip-4 are not claimed → their accrual is unclaimed.
    assert report.unclaimed_escrow_cents == 12_000
    # ip-1, ip-2, ip-3 each ≥ 1000c ($10 threshold); ip-4 = 0.
    assert report.publishers_with_nontrivial_accrual == 3


# ── Advertiser retention ──────────────────────────────────────────


def test_advertiser_retention_basic():
    current = {"adv-A": 1_000_000, "adv-B": 500_000, "adv-C": 200_000}
    prior = {"adv-A": 800_000, "adv-B": 400_000, "adv-D": 100_000}
    r = compute_advertiser_retention(
        current_period_spend=current, prior_period_spend=prior,
    )
    assert r.advertiser_count_current == 3
    assert r.advertiser_count_prior == 3
    assert r.retained_advertiser_count == 2  # A, B
    assert r.new_advertiser_count == 1  # C
    assert r.churned_advertiser_count == 1  # D
    # retention_rate = retained / prior = 2/3
    assert r.retention_rate == pytest.approx(2/3)


def test_advertiser_self_service_threshold():
    # $50K = 5_000_000 cents
    below = compute_advertiser_retention(
        current_period_spend={"adv-A": 4_999_999},
        prior_period_spend={},
    )
    above = compute_advertiser_retention(
        current_period_spend={"adv-A": 5_000_000},
        prior_period_spend={},
    )
    assert below.crosses_self_service_threshold is False
    assert above.crosses_self_service_threshold is True


def test_advertiser_activity_is_retained_predicate():
    a = AdvertiserActivity(
        advertiser_id="adv-A",
        current_period_spend_cents=100,
        prior_period_spend_cents=100,
    )
    assert a.is_retained
    b = AdvertiserActivity(
        advertiser_id="adv-B",
        current_period_spend_cents=0,
        prior_period_spend_cents=100,
    )
    assert not b.is_retained


def test_empty_periods():
    r = compute_advertiser_retention(current_period_spend={}, prior_period_spend={})
    assert r.advertiser_count_current == 0
    assert r.retention_rate == 0.0


# ── Composite snapshot + health classification ────────────────────


def _healthy_creators() -> CreatorEarningsDistribution:
    # 35 creators all above the $10 threshold.
    return compute_creator_distribution({f"u-{i}": 1500 for i in range(35)})


def _watch_creators() -> CreatorEarningsDistribution:
    return compute_creator_distribution({f"u-{i}": 1500 for i in range(15)})


def _unhealthy_creators() -> CreatorEarningsDistribution:
    return compute_creator_distribution({f"u-{i}": 1500 for i in range(3)})


def _healthy_publishers() -> PublisherEscrowReport:
    rows = [("ip-1", "claimed"), ("ip-2", "claimed"), ("ip-3", "invited")]
    return compute_publisher_escrow(
        publisher_status_rows=rows,
        publisher_accrual_cents={"ip-1": 10_000, "ip-2": 5_000, "ip-3": 1_000},
        publisher_paid_cents={"ip-1": 8_000},
    )


def _unhealthy_publishers() -> PublisherEscrowReport:
    # 0 claimed, 5 invited, 5 opted_out — claim rate = 0.
    rows = (
        [("ip-i-" + str(i), "invited") for i in range(5)] +
        [("ip-o-" + str(i), "opted_out") for i in range(5)]
    )
    return compute_publisher_escrow(
        publisher_status_rows=rows,
        publisher_accrual_cents={},
        publisher_paid_cents={},
    )


def _healthy_advertisers() -> AdvertiserRetentionReport:
    return compute_advertiser_retention(
        current_period_spend={"adv-A": 1000, "adv-B": 1000, "adv-C": 500},
        prior_period_spend={"adv-A": 1000, "adv-B": 1000},
    )


def _unhealthy_advertisers() -> AdvertiserRetentionReport:
    return compute_advertiser_retention(
        current_period_spend={"adv-NEW": 100},  # all new, none retained
        prior_period_spend={"adv-A": 100, "adv-B": 100},
    )


def test_all_healthy_classifies_healthy():
    snap = assemble_snapshot(
        creators=_healthy_creators(),
        publishers=_healthy_publishers(),
        advertisers=_healthy_advertisers(),
    )
    assert snap.health == MarketplaceHealth.HEALTHY
    assert len(snap.health_signals) == 3


def test_one_failing_dimension_classifies_watch():
    snap = assemble_snapshot(
        creators=_watch_creators(),
        publishers=_healthy_publishers(),
        advertisers=_healthy_advertisers(),
    )
    assert snap.health == MarketplaceHealth.WATCH


def test_two_failing_dimensions_classifies_unhealthy():
    snap = assemble_snapshot(
        creators=_unhealthy_creators(),
        publishers=_unhealthy_publishers(),
        advertisers=_healthy_advertisers(),
    )
    assert snap.health == MarketplaceHealth.UNHEALTHY


def test_health_signals_explain_the_verdict():
    snap = assemble_snapshot(
        creators=_unhealthy_creators(),
        publishers=_healthy_publishers(),
        advertisers=_healthy_advertisers(),
    )
    # The creators signal must call out the failing dimension.
    joined = " | ".join(snap.health_signals)
    assert "creators_above_threshold" in joined
    assert "unhealthy" in joined.lower() or "watch" in joined.lower()


def test_no_prior_advertisers_is_watch_signal():
    snap = assemble_snapshot(
        creators=_healthy_creators(),
        publishers=_healthy_publishers(),
        advertisers=compute_advertiser_retention(
            current_period_spend={"adv-A": 100},
            prior_period_spend={},
        ),
    )
    # No prior period → watch on advertisers axis.
    joined = " | ".join(snap.health_signals)
    assert "advertiser_retention" in joined
    assert snap.health in {MarketplaceHealth.WATCH, MarketplaceHealth.UNHEALTHY}
