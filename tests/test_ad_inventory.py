"""Ad inventory + attribution + payout tests (Sprint 23-24)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from substrate.ad_inventory import (
    AdInventoryItem,
    AttributionAlgorithm,
    BiddingPolicy,
    LeadGenAdInventory,
    PayoutRouter,
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
    distribute_session_ad_revenue,
    enforce_per_document_daily_cap,
    select_lead_gen_ad,
)
from substrate.ad_inventory.payout import (
    CREATOR_REV_SHARE,
    PLATFORM_CUT,
    RevShareKind,
)


# ── Attribution algorithms ──────────────────────────────────────────


def test_option_a_equal_split():
    """Doc-A has 2 chunks, Doc-B has 1: shares should be 2/3, 1/3."""
    result = compute_attribution_option_a(
        page_id="page-1",
        chunk_to_document={
            "c-1": "doc-A", "c-2": "doc-A", "c-3": "doc-B",
        },
    )
    assert result.algorithm == AttributionAlgorithm.OPTION_A_EQUAL_SPLIT
    assert abs(result.shares["doc-A"] - 2/3) < 1e-9
    assert abs(result.shares["doc-B"] - 1/3) < 1e-9
    assert abs(sum(result.shares.values()) - 1.0) < 1e-9


def test_option_b_weights_by_confidence_times_tier():
    """Higher-confidence claim from a Tier-1 doc should outweigh a
    same-count lower-confidence claim from Tier-3 doc."""
    result = compute_attribution_option_b(
        page_id="page-1",
        chunk_to_document={"c-1": "doc-tier1", "c-2": "doc-tier3"},
        chunk_to_claim_confidence={"c-1": 0.9, "c-2": 0.4},
        document_to_source_tier={"doc-tier1": 1, "doc-tier3": 3},
    )
    # doc-tier1: 0.9 * (6-1) = 4.5
    # doc-tier3: 0.4 * (6-3) = 1.2
    # total: 5.7
    assert result.shares["doc-tier1"] > result.shares["doc-tier3"]
    assert abs(result.shares["doc-tier1"] - 4.5/5.7) < 1e-9


def test_option_c_load_bearing():
    """Doc whose claim has high load-bearing score gets disproportionate share."""
    result = compute_attribution_option_c(
        page_id="page-1",
        chunk_to_document={"c-1": "doc-A", "c-2": "doc-B"},
        chunk_to_claim_id={"c-1": "claim-X", "c-2": "claim-Y"},
        claim_load_bearing_scores={"claim-X": 0.9, "claim-Y": 0.1},
    )
    # doc-A weight = 0.9, doc-B weight = 0.1
    assert abs(result.shares["doc-A"] - 0.9) < 1e-9
    assert abs(result.shares["doc-B"] - 0.1) < 1e-9


def test_option_a_empty_returns_empty():
    result = compute_attribution_option_a(
        page_id="page-1",
        chunk_to_document={},
    )
    assert result.shares == {}


# ── Ad bidding / inventory ──────────────────────────────────────────


def test_lead_gen_inventory_filters_by_topic():
    inv = LeadGenAdInventory()
    inv.add(AdInventoryItem(
        inventory_id="a-1",
        advertiser_display_name="QuantumConsulting",
        target_topics=("quantum",),
        cpm_usd=Decimal("40.00"),
        creative_url="x", landing_url="y",
    ))
    inv.add(AdInventoryItem(
        inventory_id="a-2",
        advertiser_display_name="DefenseStrategy",
        target_topics=("defense",),
        cpm_usd=Decimal("60.00"),
        creative_url="x", landing_url="y",
    ))
    matched = inv.by_topics(["quantum"])
    assert len(matched) == 1
    assert matched[0].inventory_id == "a-1"


def test_select_lead_gen_ad_picks_highest_cpm():
    inv = LeadGenAdInventory()
    inv.add(AdInventoryItem(
        inventory_id="a-1",
        advertiser_display_name="A",
        target_topics=("quantum",),
        cpm_usd=Decimal("40.00"),
        creative_url="", landing_url="",
    ))
    inv.add(AdInventoryItem(
        inventory_id="a-2",
        advertiser_display_name="B",
        target_topics=("quantum", "defense"),
        cpm_usd=Decimal("75.00"),
        creative_url="", landing_url="",
    ))
    picked = select_lead_gen_ad(inv, page_topics=["quantum"])
    assert picked is not None
    assert picked.inventory_id == "a-2"


def test_select_returns_none_when_no_match():
    inv = LeadGenAdInventory()
    inv.add(AdInventoryItem(
        inventory_id="a-1",
        advertiser_display_name="A",
        target_topics=("quantum",),
        cpm_usd=Decimal("40.00"),
        creative_url="", landing_url="",
    ))
    picked = select_lead_gen_ad(inv, page_topics=["unrelated_topic"])
    assert picked is None


# ── Payout routing ──────────────────────────────────────────────────


def test_creator_rev_share_constants_match_master_spec():
    """Master-spec §13.5 + §13.9 + §9.0.1: 70% creator + 30% platform."""
    assert CREATOR_REV_SHARE == Decimal("0.70")
    assert PLATFORM_CUT == Decimal("0.30")


def test_distribute_session_revenue_70_30_split():
    router = PayoutRouter()
    decisions = distribute_session_ad_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=1000,
        attribution_shares={"doc-A": 1.0},
        document_to_recipient={
            "doc-A": (RevShareKind.CREATOR, "user-creator-1", False),
        },
    )
    # Find the creator + platform decisions.
    creator_d = next(d for d in decisions if d.kind == RevShareKind.CREATOR)
    platform_d = next(d for d in decisions if d.kind == RevShareKind.PLATFORM)
    assert creator_d.amount_usd_cents == 700
    assert platform_d.amount_usd_cents == 300


def test_distribute_session_publisher_requires_escrow_flag():
    router = PayoutRouter()
    decisions = distribute_session_ad_revenue(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=1000,
        attribution_shares={"doc-A": 1.0},
        document_to_recipient={
            "doc-A": (RevShareKind.PUBLISHER, "ipholder-mit", True),
        },
    )
    publisher_d = next(d for d in decisions if d.kind == RevShareKind.PUBLISHER)
    assert publisher_d.requires_escrow is True
    assert publisher_d.amount_usd_cents == 700


def test_per_document_daily_cap_enforced():
    """Master-spec §9.7 anti-gaming: no document can earn more than
    the daily cap regardless of citation volume."""
    router = PayoutRouter(per_document_daily_cap_usd=Decimal("1.00"))  # $1/day
    # First payout under cap.
    cents1, capped1 = enforce_per_document_daily_cap(router, "doc-X", 50)
    assert cents1 == 50
    assert not capped1
    # Second payout would push over $1.00 = 100 cents.
    cents2, capped2 = enforce_per_document_daily_cap(router, "doc-X", 80)
    assert cents2 == 50  # only the remaining 50¢ available
    assert capped2 is True


def test_attribution_shares_sum_to_one():
    """Invariant: Option B shares always sum to 1.0 (or 0.0 if no input)."""
    result = compute_attribution_option_b(
        page_id="x",
        chunk_to_document={
            "c-1": "doc-A", "c-2": "doc-B", "c-3": "doc-C",
        },
        chunk_to_claim_confidence={"c-1": 0.7, "c-2": 0.8, "c-3": 0.6},
        document_to_source_tier={"doc-A": 1, "doc-B": 2, "doc-C": 3},
    )
    total = sum(result.shares.values())
    assert abs(total - 1.0) < 1e-9
