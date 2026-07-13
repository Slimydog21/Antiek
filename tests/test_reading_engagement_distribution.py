"""Tests for substrate/reading_engagement_distribution.py — attention distribution."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.reading_engagement_distribution import (
    SectionTouches,
    measure_engagement_distribution,
)


def _secs(*pairs: tuple[str, int]) -> list[SectionTouches]:
    return [SectionTouches(section_id=s, touch_count=c) for s, c in pairs]


# --- unread ----------------------------------------------------------------


def test_unread_no_touches() -> None:
    r = measure_engagement_distribution([])
    assert r.verdict == "unread"
    assert r.gini is None
    assert r.mean_touches_per_section is None
    assert r.max_touches is None
    assert r.authority == "advisory"


def test_unread_all_zero_touches() -> None:
    r = measure_engagement_distribution(_secs(("a", 0), ("b", 0)))
    assert r.verdict == "unread"
    assert r.touched_section_count == 0


def test_unread_never_fabricates_even() -> None:
    assert measure_engagement_distribution([]).verdict != "even"


# --- focused (one section — honest base case) -----------------------------


def test_focused_single_section() -> None:
    r = measure_engagement_distribution(_secs(("a", 5)))
    assert r.verdict == "focused"
    assert r.gini is None  # degenerate, deferred
    assert r.mean_touches_per_section == pytest.approx(5.0)
    assert "a" in r.hot_spot_sections


def test_focused_distinct_from_unread_and_even() -> None:
    assert measure_engagement_distribution([]).verdict == "unread"
    assert measure_engagement_distribution(_secs(("a", 5))).verdict == "focused"


# --- even (uniform spread) ------------------------------------------------


def test_even_uniform_spread() -> None:
    r = measure_engagement_distribution(_secs(("a", 3), ("b", 3), ("c", 3), ("d", 3)))
    assert r.verdict == "even"
    assert r.gini == pytest.approx(0.0)
    assert r.hot_spot_sections == ()


def test_even_is_measured_not_default() -> None:
    assert measure_engagement_distribution([]).verdict == "unread"
    assert measure_engagement_distribution(_secs(("a", 3))).verdict == "focused"
    assert (
        measure_engagement_distribution(_secs(("a", 2), ("b", 2), ("c", 2))).verdict
        == "even"
    )


# --- concentrated (hot spot) ----------------------------------------------


def test_concentrated_one_hot_spot() -> None:
    # One section has 20 touches, others 1 each -> high Gini.
    r = measure_engagement_distribution(
        _secs(("hot", 20), ("a", 1), ("b", 1), ("c", 1))
    )
    assert r.verdict == "concentrated"
    assert r.gini is not None and r.gini >= 0.60
    assert "hot" in r.hot_spot_sections


def test_concentrated_max_gini() -> None:
    # 3 sections strongly skewed: 100, 1, 1 -> Gini ~0.65 (concentrated).
    r = measure_engagement_distribution(_secs(("hot", 100), ("a", 1), ("b", 1)))
    assert r.gini is not None and r.gini > 0.60


# --- moderate (in between) ------------------------------------------------


def test_moderate_partial_skew() -> None:
    # 8,2,2,2 -> Gini 0.32 (genuine moderate, in (0.20, 0.60)).
    r = measure_engagement_distribution(_secs(("a", 8), ("b", 2), ("c", 2), ("d", 2)))
    assert r.verdict == "moderate"
    assert r.gini is not None and 0.20 < r.gini < 0.60


# --- load-bearing: breadth vs distribution orthogonal ---------------------


def test_breadth_vs_distribution_orthogonal() -> None:
    # Two readers both touch all 4 sections (breadth 100% under #1987) but differ
    # in distribution: one even, one concentrated. Proves distribution != breadth.
    even = measure_engagement_distribution(
        _secs(("a", 5), ("b", 5), ("c", 5), ("d", 5))
    )
    concentrated = measure_engagement_distribution(
        _secs(("a", 20), ("b", 1), ("c", 1), ("d", 1))
    )
    assert even.touched_section_count == concentrated.touched_section_count == 4
    assert even.verdict == "even"
    assert concentrated.verdict == "concentrated"


# --- Gini correctness ------------------------------------------------------


def test_gini_uniform_is_zero() -> None:
    r = measure_engagement_distribution(_secs(("a", 4), ("b", 4), ("c", 4)))
    assert r.gini == pytest.approx(0.0)


def test_gini_extreme_skew_high() -> None:
    r = measure_engagement_distribution(_secs(("a", 50), ("b", 1), ("c", 1)))
    assert r.gini is not None and r.gini > 0.50


def test_gini_invariant_to_scale() -> None:
    # Touching each section 10x evenly has the same Gini as 1x evenly.
    r1 = measure_engagement_distribution(_secs(("a", 1), ("b", 1), ("c", 1)))
    r2 = measure_engagement_distribution(_secs(("a", 10), ("b", 10), ("c", 10)))
    assert r1.gini == pytest.approx(r2.gini)


# --- hot spots + stats -----------------------------------------------------


def test_hot_spot_threshold() -> None:
    # mean = (10+2+2+2)/4 = 4; threshold 2.0 -> hot spots at >= 8 -> only "hot".
    r = measure_engagement_distribution(_secs(("hot", 10), ("a", 2), ("b", 2), ("c", 2)))
    assert r.hot_spot_sections == ("hot",)
    assert r.max_touches == 10
    assert r.mean_touches_per_section == pytest.approx(4.0)


def test_total_and_mean() -> None:
    r = measure_engagement_distribution(_secs(("a", 3), ("b", 5), ("c", 4)))
    assert r.total_touches == 12
    assert r.mean_touches_per_section == pytest.approx(4.0)


# --- zero-touch sections filtered -----------------------------------------


def test_zero_touch_sections_excluded_from_touched() -> None:
    r = measure_engagement_distribution(_secs(("a", 3), ("b", 0), ("c", 3)))
    assert r.touched_section_count == 2  # b excluded


# --- custom thresholds -----------------------------------------------------


def test_custom_high_concentration() -> None:
    base = _secs(("a", 8), ("b", 2), ("c", 2), ("d", 2))  # Gini 0.32 (moderate)
    assert measure_engagement_distribution(base).verdict == "moderate"
    # Lower the floor so moderate becomes concentrated.
    assert (
        measure_engagement_distribution(base, high_concentration=0.30).verdict
        == "concentrated"
    )


def test_custom_low_concentration() -> None:
    base = _secs(("a", 4), ("b", 4), ("c", 5))  # Gini 0.15, near-uniform
    # Under default low 0.20 this is already even.
    assert measure_engagement_distribution(base).verdict == "even"


# --- validation ------------------------------------------------------------


def test_invalid_hot_spot_threshold_below_one() -> None:
    with pytest.raises(ValueError, match="hot_spot_threshold"):
        measure_engagement_distribution([], hot_spot_threshold=0.5)


def test_invalid_high_concentration_over_one() -> None:
    with pytest.raises(ValueError, match="high_concentration"):
        measure_engagement_distribution([], high_concentration=1.5)


def test_invalid_low_ge_high() -> None:
    with pytest.raises(ValueError, match="low_concentration"):
        measure_engagement_distribution(
            [], low_concentration=0.40, high_concentration=0.40
        )


def test_negative_touch_count() -> None:
    with pytest.raises(ValueError, match="negative"):
        measure_engagement_distribution(_secs(("a", -1)))


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_engagement_distribution(_secs(("a", 3), ("b", 3)))
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]
