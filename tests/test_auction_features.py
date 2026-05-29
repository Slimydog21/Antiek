"""Auction feature-pipeline tests (SPR-10 M1).

Deterministic features, no target leakage, denylist honored. Golden-value
assertions to high precision, minimal mocking (mirrors test_intent_targeting)."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from substrate.ad_inventory.ad_bidding import AdInventoryItem
from substrate.ad_inventory.auction_features import (
    FEATURE_DIM,
    FEATURE_NAMES,
    AuctionCandidate,
    extract_features,
    feature_provenance,
)
from substrate.ad_inventory.intent_targeting import InventoryTargeting, PageContext
from substrate.ad_inventory.targeting import _FORBIDDEN_SIGNAL_KEYS


def _candidate(
    *,
    cpm: str = "5.00",
    target_sectors: tuple[str, ...] = (),
    target_sub_sectors: tuple[str, ...] = (),
    target_intents: tuple[str, ...] = (),
    target_topics: tuple[str, ...] = (),
) -> AuctionCandidate:
    return AuctionCandidate(
        item=AdInventoryItem(
            inventory_id="inv-1",
            advertiser_display_name="inv-1",
            target_topics=target_topics,
            cpm_usd=Decimal(cpm),
            creative_url="https://example.com/inv-1.png",
            landing_url="https://example.com/inv-1/lp",
        ),
        targeting=InventoryTargeting(
            target_sectors=target_sectors,
            target_sub_sectors=target_sub_sectors,
            target_audience_intents=target_intents,
        ),
    )


def test_vector_is_fixed_length_and_names_align() -> None:
    ctx = PageContext(sector="defense", sub_sector=None, audience_intents=())
    vec = extract_features(ctx, _candidate())
    assert len(vec) == FEATURE_DIM
    assert len(FEATURE_NAMES) == FEATURE_DIM
    assert FEATURE_NAMES[0] == "bias"
    assert vec[0] == 1.0  # bias term is always 1.0


def test_deterministic_same_input_same_vector() -> None:
    ctx = PageContext(
        sector="defense",
        sub_sector="hypersonics",
        audience_intents=("researcher", "procurement"),
        flat_topics=("defense", "quantum"),
    )
    cand = _candidate(
        cpm="12.50",
        target_sectors=("defense",),
        target_sub_sectors=("hypersonics",),
        target_intents=("researcher",),
        target_topics=("defense",),
    )
    a = extract_features(ctx, cand)
    b = extract_features(ctx, cand)
    assert a == b  # byte-identical (no clock/random/global state)


def test_golden_full_match_vector() -> None:
    ctx = PageContext(
        sector="defense",
        sub_sector="hypersonics",
        audience_intents=("researcher", "procurement"),
        flat_topics=("defense", "quantum"),
    )
    cand = _candidate(
        cpm="12.50",
        target_sectors=("defense",),
        target_sub_sectors=("hypersonics",),
        target_intents=("researcher",),
        target_topics=("defense",),
    )
    vec = extract_features(ctx, cand)
    # idx: bias, sector, sub_sector, intent_overlap, topic_overlap,
    #      rule_score_norm, log_cpm, targeting_specificity, context_richness
    assert vec[0] == 1.0
    assert vec[1] == 1.0   # sector hit
    assert vec[2] == 1.0   # sub_sector hit
    assert vec[3] == pytest.approx(0.5)  # 1 of 2 intents matched
    assert vec[4] == pytest.approx(0.5)  # 1 of 2 flat topics matched
    # rule score = 3 (sector) + 2 (sub) + 1 (intent) = 6 == max → 1.0
    assert vec[5] == pytest.approx(1.0)
    assert vec[6] == pytest.approx(math.log1p(12.5))
    assert vec[7] == pytest.approx(1.0)  # 3/3 targeting dims filled
    assert vec[8] == pytest.approx(1.0)  # 4/4 context dims filled


def test_no_match_zeros_the_overlap_features() -> None:
    ctx = PageContext(
        sector="defense", sub_sector="hypersonics",
        audience_intents=("researcher",), flat_topics=("defense",),
    )
    cand = _candidate(
        cpm="3.00",
        target_sectors=("biotech",),
        target_sub_sectors=("oncology",),
        target_intents=("clinician",),
        target_topics=("oncology",),
    )
    vec = extract_features(ctx, cand)
    assert vec[1] == 0.0
    assert vec[2] == 0.0
    assert vec[3] == 0.0
    assert vec[4] == 0.0
    assert vec[5] == 0.0  # rule score zero → normalized zero
    assert vec[6] == pytest.approx(math.log1p(3.0))


def test_empty_context_richness_is_zero() -> None:
    ctx = PageContext(sector=None, sub_sector=None, audience_intents=())
    vec = extract_features(ctx, _candidate())
    assert vec[8] == 0.0  # no context dimension filled


def test_no_label_field_in_feature_provenance() -> None:
    """The leakage guard: no feature may derive from a served-outcome / realized
    value. Provenance strings must not reference revenue/attention/dwell/value
    earned after the impression."""
    leak_terms = (
        "revenue", "realized", "earned", "attention", "dwell",
        "counted", "value_usd", "amount_cents", "weigh_second",
        "frame_attention", "impression_id", "served",
    )
    prov = feature_provenance()
    assert set(prov.keys()) == set(FEATURE_NAMES)
    for name, source in prov.items():
        low = source.lower()
        for term in leak_terms:
            assert term not in low, (
                f"feature {name!r} provenance {source!r} references the "
                f"served-outcome term {term!r} — that is target leakage"
            )


def test_forbidden_key_in_context_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """If PageContext ever grows a forbidden field, the guard trips loudly."""
    ctx = PageContext(sector="defense", sub_sector=None, audience_intents=())
    # Forge a forbidden attribute onto a frozen instance via object.__setattr__
    # to simulate a future shape regression.
    forbidden = next(iter(_FORBIDDEN_SIGNAL_KEYS))
    object.__setattr__(ctx, forbidden, "some gated body text")
    with pytest.raises(ValueError, match="forbidden"):
        extract_features(ctx, _candidate())
