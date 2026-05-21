"""Multi-dimensional ad targeting tests (Sprint 25+ phase 1)."""

from __future__ import annotations

from decimal import Decimal

from substrate.ad_inventory import (
    AdInventoryItem,
    InventoryTargeting,
    MIN_MATCH_SCORE,
    PageContext,
    TargetedInventoryItem,
    context_from_decomposer_topics,
    score_inventory_match,
    select_targeted_ad,
)
from substrate.ad_inventory.intent_targeting import (
    WEIGHT_AUDIENCE_INTENT_MATCH,
    WEIGHT_SECTOR_MATCH,
    WEIGHT_SUB_SECTOR_MATCH,
)


def _item(
    inv_id: str,
    cpm: str,
    *,
    target_sectors=(),
    target_sub_sectors=(),
    target_intents=(),
    flat_topics=(),
) -> TargetedInventoryItem:
    return TargetedInventoryItem(
        item=AdInventoryItem(
            inventory_id=inv_id,
            advertiser_display_name=inv_id,
            target_topics=flat_topics,
            cpm_usd=Decimal(cpm),
            creative_url=f"https://example.com/{inv_id}.png",
            landing_url=f"https://example.com/{inv_id}/lp",
        ),
        targeting=InventoryTargeting(
            target_sectors=target_sectors,
            target_sub_sectors=target_sub_sectors,
            target_audience_intents=target_intents,
        ),
    )


# ── Match scoring ──────────────────────────────────────────────────


def test_zero_score_when_no_dimension_overlaps():
    ctx = PageContext(
        sector="defense", sub_sector="hypersonics",
        audience_intents=("researcher",),
    )
    tgt = InventoryTargeting(
        target_sectors=("biotech",),
        target_sub_sectors=("oncology",),
        target_audience_intents=("clinician",),
    )
    assert score_inventory_match(ctx, tgt) == 0.0


def test_sector_match_only_scores_sector_weight():
    ctx = PageContext(
        sector="defense", sub_sector="hypersonics",
        audience_intents=("researcher",),
    )
    tgt = InventoryTargeting(
        target_sectors=("defense",),
    )
    assert score_inventory_match(ctx, tgt) == WEIGHT_SECTOR_MATCH


def test_full_three_dimension_match_sums_all_weights():
    ctx = PageContext(
        sector="defense", sub_sector="hypersonics",
        audience_intents=("researcher", "procurement"),
    )
    tgt = InventoryTargeting(
        target_sectors=("defense", "aerospace"),
        target_sub_sectors=("hypersonics",),
        target_audience_intents=("procurement",),
    )
    assert score_inventory_match(ctx, tgt) == (
        WEIGHT_SECTOR_MATCH
        + WEIGHT_SUB_SECTOR_MATCH
        + WEIGHT_AUDIENCE_INTENT_MATCH
    )


def test_empty_targeting_dimension_does_not_contribute():
    # The matcher must not give credit for an empty target tuple.
    ctx = PageContext(sector="defense", sub_sector=None, audience_intents=())
    tgt = InventoryTargeting(target_sectors=("defense",))  # other dims empty
    assert score_inventory_match(ctx, tgt) == WEIGHT_SECTOR_MATCH


# ── Selection ──────────────────────────────────────────────────────


def test_select_targeted_ad_picks_highest_score_times_cpm():
    ctx = PageContext(
        sector="defense", sub_sector="hypersonics",
        audience_intents=("procurement",),
    )
    inventory = [
        _item("inv-low", "5.00", target_sectors=("defense",)),
        _item(
            "inv-high", "8.00",
            target_sectors=("defense",),
            target_sub_sectors=("hypersonics",),
            target_intents=("procurement",),
        ),
        _item("inv-off", "100.00", target_sectors=("biotech",)),
    ]
    chosen = select_targeted_ad(context=ctx, targeted_inventory=inventory)
    assert chosen is not None
    assert chosen.inventory_id == "inv-high"


def test_select_targeted_ad_returns_none_below_min_score():
    ctx = PageContext(sector="defense", sub_sector=None, audience_intents=())
    # Item targets only biotech → 0 score → below MIN_MATCH_SCORE.
    inventory = [_item("inv-x", "10.00", target_sectors=("biotech",))]
    assert select_targeted_ad(context=ctx, targeted_inventory=inventory) is None


def test_select_targeted_ad_falls_back_to_flat_topics():
    ctx = PageContext(
        sector=None, sub_sector=None, audience_intents=(),
        flat_topics=("quantum", "computing"),
    )
    # No targeted item matches.
    targeted = [
        _item("inv-targeted-miss", "20.00", target_sectors=("biotech",)),
    ]
    flat = [
        AdInventoryItem(
            inventory_id="inv-flat-a",
            advertiser_display_name="A",
            target_topics=("quantum",),
            cpm_usd=Decimal("3.00"),
            creative_url="https://x", landing_url="https://x",
        ),
        AdInventoryItem(
            inventory_id="inv-flat-b",
            advertiser_display_name="B",
            target_topics=("quantum", "computing"),
            cpm_usd=Decimal("7.00"),
            creative_url="https://y", landing_url="https://y",
        ),
    ]
    chosen = select_targeted_ad(
        context=ctx,
        targeted_inventory=targeted,
        flat_inventory_fallback=flat,
    )
    assert chosen is not None
    assert chosen.inventory_id == "inv-flat-b"  # higher CPM


def test_select_targeted_ad_no_fallback_returns_none_on_empty_match():
    ctx = PageContext(sector=None, sub_sector=None, audience_intents=())
    assert select_targeted_ad(context=ctx, targeted_inventory=[]) is None


def test_select_targeted_ad_tiebreak_is_deterministic():
    ctx = PageContext(
        sector="defense", sub_sector=None, audience_intents=(),
    )
    # Identical CPM + identical score; tiebreak by inventory_id desc-string
    # (score × cpm equal; cpm equal → falls through to inventory_id).
    inventory = [
        _item("inv-a", "5.00", target_sectors=("defense",)),
        _item("inv-b", "5.00", target_sectors=("defense",)),
        _item("inv-c", "5.00", target_sectors=("defense",)),
    ]
    # Run multiple times — must be stable.
    chosen_ids = {
        select_targeted_ad(context=ctx, targeted_inventory=inventory).inventory_id
        for _ in range(10)
    }
    assert len(chosen_ids) == 1


def test_is_empty_targeting_skipped_even_if_score_would_zero():
    # An InventoryTargeting with no dimensions filled must be ignored
    # by the targeted matcher (it falls through to flat).
    ctx = PageContext(
        sector="defense", sub_sector="hypersonics",
        audience_intents=("procurement",),
        flat_topics=("defense",),
    )
    empty = TargetedInventoryItem(
        item=AdInventoryItem(
            inventory_id="inv-empty",
            advertiser_display_name="E",
            target_topics=("defense",),
            cpm_usd=Decimal("99.00"),
            creative_url="https://e", landing_url="https://e",
        ),
        targeting=InventoryTargeting(),
    )
    # No fallback supplied → returns None even though flat-topic would match.
    assert select_targeted_ad(
        context=ctx, targeted_inventory=[empty],
    ) is None
    # Fallback supplied → flat-topic match picks it up.
    chosen = select_targeted_ad(
        context=ctx, targeted_inventory=[empty],
        flat_inventory_fallback=[empty.item],
    )
    assert chosen is not None
    assert chosen.inventory_id == "inv-empty"


# ── Context helper ─────────────────────────────────────────────────


def test_context_from_decomposer_topics_carries_flat_topics():
    ctx = context_from_decomposer_topics(
        ["defense", "hypersonics"],
        sector="defense",
        sub_sector="hypersonics",
        audience_intents=("procurement",),
    )
    assert ctx.sector == "defense"
    assert ctx.sub_sector == "hypersonics"
    assert ctx.audience_intents == ("procurement",)
    assert ctx.flat_topics == ("defense", "hypersonics")


def test_min_match_score_constant_is_at_least_one():
    # MIN_MATCH_SCORE acts as the floor — a single weakest-dimension
    # match (audience_intent only) should still clear it so a page
    # with intent-only signal can serve an intent-only inventory item.
    assert MIN_MATCH_SCORE <= WEIGHT_AUDIENCE_INTENT_MATCH
