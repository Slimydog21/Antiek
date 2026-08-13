"""AFA-S2 M5 — the anti-gaming filter inside aggregate_window (pure).

Filter-before-allocate: invalid frame seconds are excluded from BOTH the
numerator and the denominator of the per-window split; a BLOCK verdict or a
fully-filtered window routes the whole value to house; every excluded second is
counted and reported. Conservation stays exact throughout. All at the pure
aggregate_window layer (no DB) so it runs locally.
"""

from __future__ import annotations

from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import aggregate_window
from substrate.anti_gaming.frame_ivt import REASON_DUPLICATE_INDEX


def _sample(asset_id="pd-earner", area=0.6, prominence=0.7, dwell=800):
    # public_domain → monetization_eligible → produces an asset line (not house).
    return FrameAttentionSample(
        asset_id=asset_id,
        viewport_area_fraction=area,
        prominence=prominence,
        focused_dwell_ms=dwell,
        content_class="public_domain",
    )


def _second(index, asset_id="pd-earner"):
    return FrameSecond(second_index=index, lens="read", samples=(_sample(asset_id),))


def _batch(seconds, *, cents=1000):
    return WindowFrameBatch(
        window_id="win:read:filter",
        seconds=tuple(seconds),
        ad_value_usd_cents=cents,
    )


def _asset_total(result):
    return sum(line.amount_cents for line in result.asset_lines)


def test_clean_batch_is_unchanged_by_the_filter():
    # An all-valid contiguous batch: the filter is invisible — the single
    # eligible asset earns the whole window, house is zero, conservation exact.
    result = aggregate_window(_batch([_second(0), _second(1), _second(2)]))
    assert result.reconciles()
    assert _asset_total(result) == 700  # AFA-S5: 70% to creator pool
    assert result.house.amount_cents == 300  # AFA-S5: 30% platform cut
    assert result.excluded_second_counts == ()
    assert result.fraud_verdict == "pass"


def test_invalid_second_excluded_from_numerator_and_denominator():
    # 5 seconds, the last a DUPLICATE index (position 4) → GIVT-invalid, fraction
    # 0.2 → PASS verdict but the invalid second is still filtered. The 4 valid
    # seconds split the whole 1000; the invalid second earns nothing.
    seconds = [_second(0), _second(1), _second(2), _second(3), _second(1)]
    result = aggregate_window(_batch(seconds))
    assert result.reconciles()
    # Whole value went to the eligible asset over the 4 VALID seconds; the
    # excluded second neither earned nor diluted (denominator was 4, not 5).
    assert _asset_total(result) == 700  # AFA-S5: 70% to creator pool
    assert result.house.amount_cents == 300  # AFA-S5: 30% platform cut
    assert result.fraud_verdict == "pass"
    assert result.excluded_second_counts == ((REASON_DUPLICATE_INDEX, 1),)


def test_block_window_routes_all_to_house():
    # 4 duplicate index-0 seconds → 3 invalid / 4 = 0.75 → BLOCK. The whole value
    # routes to house; no contributor accrues.
    result = aggregate_window(_batch([_second(0), _second(0), _second(0), _second(0)]))
    assert result.reconciles()
    assert result.house.amount_cents == 1000
    assert result.asset_lines == ()
    assert result.fraud_verdict == "block"
    assert result.house.reason == "antigaming_block"


def test_majority_invalid_review_window_still_conserves():
    # 2 of 3 seconds duplicate-invalid → fraction 0.667 → REVIEW (below BLOCK's
    # 0.75). The single valid second earns; the 2 duplicates are excluded from
    # both sides. Conservation is exact and the excluded count is reported.
    # (The fully-filtered n_valid==0 branch is defensive: an all-invalid batch
    # scores GIVT fraction 1.0 → BLOCK, caught by the block branch first.)
    result = aggregate_window(_batch([_second(7), _second(7), _second(7)]))
    assert result.reconciles()
    assert result.house.amount_cents + _asset_total(result) == 1000
    assert result.fraud_verdict == "review"
    assert result.excluded_second_counts == ((REASON_DUPLICATE_INDEX, 2),)


def test_conservation_holds_under_partial_filter_multi_asset():
    # Two assets across valid seconds + one invalid second → Σ asset + house
    # == total EXACTLY (the money-conservation invariant survives filtering).
    seconds = [
        _second(0, "pd-a"),
        _second(1, "pd-b"),
        _second(2, "pd-a"),
        _second(1, "pd-b"),  # duplicate index → invalid
    ]
    result = aggregate_window(_batch(seconds, cents=1001))  # odd cents → rounding
    assert result.reconciles()
    assert _asset_total(result) + result.house.amount_cents == 1001
    assert result.excluded_second_counts == ((REASON_DUPLICATE_INDEX, 1),)


def test_weighting_version_is_v2_on_filtered_accrual():
    result = aggregate_window(_batch([_second(0), _second(1)]))
    assert result.weighting_version == "frame-weight-v2"
