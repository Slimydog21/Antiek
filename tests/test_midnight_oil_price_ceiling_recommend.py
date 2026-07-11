"""Red-proofs: Midnight Oil price ceiling recommender (advisory only)."""

from __future__ import annotations

import pytest

from substrate.midnight_oil.price_ceiling_recommend import (
    PriceCeilingError,
    PriceCeilingRecommendation,
    recommend_price_ceiling,
)


def test_recommend_happy_path() -> None:
    rec = recommend_price_ceiling(
        hours=2,
        goals=["q1", "q2"],
        usd_per_hour_low=1,
        usd_per_hour_high=3,
        usd_per_goal=0.5,
        contingency_fraction=0.1,
    )
    assert rec.authority == "advisory"
    assert rec.goal_count == 2
    assert rec.low_usd == 2 * 1 + 1.0  # 3
    assert rec.high_usd == 2 * 3 + 1.0  # 7
    # mid=5, contingency=0.5, recommended=5.5
    assert rec.recommended_ceiling_usd == pytest.approx(5.5)
    assert all(x >= 0 for x in (rec.low_usd, rec.high_usd, rec.recommended_ceiling_usd))
    d = rec.to_dict()
    assert d["authority"] == "advisory"
    assert "reserve" not in " ".join(d["notes"]).lower() or "does not reserve" in " ".join(d["notes"]).lower()


def test_rejects_nonpositive_hours() -> None:
    with pytest.raises(PriceCeilingError):
        recommend_price_ceiling(hours=0, goals=1)
    with pytest.raises(PriceCeilingError):
        recommend_price_ceiling(hours=-1, goals=1)


def test_rejects_inverted_rates() -> None:
    with pytest.raises(PriceCeilingError):
        recommend_price_ceiling(hours=1, goals=0, usd_per_hour_low=5, usd_per_hour_high=1)


def test_rejects_nan_inf() -> None:
    with pytest.raises(PriceCeilingError):
        recommend_price_ceiling(hours=float("nan"), goals=1)
    with pytest.raises(PriceCeilingError):
        recommend_price_ceiling(hours=1, goals=1, usd_per_hour_high=float("inf"))


def test_authority_forced_advisory() -> None:
    rec = PriceCeilingRecommendation(
        hours=1,
        goal_count=0,
        recommended_ceiling_usd=1.0,
        low_usd=1.0,
        high_usd=1.0,
        notes=[],
    )
    assert rec.authority == "advisory"


def test_int_goal_count() -> None:
    rec = recommend_price_ceiling(hours=1, goals=3, usd_per_hour_low=1, usd_per_hour_high=1, usd_per_goal=1, contingency_fraction=0)
    assert rec.goal_count == 3
    assert rec.recommended_ceiling_usd == pytest.approx(4.0)


def test_rejects_overflow_to_inf() -> None:
    with pytest.raises(PriceCeilingError, match="non-finite|overflow"):
        recommend_price_ceiling(
            hours=1e308, goals=0, usd_per_hour_low=1, usd_per_hour_high=5
        )
    with pytest.raises(PriceCeilingError, match="non-finite|overflow"):
        recommend_price_ceiling(
            hours=1e200,
            goals=0,
            usd_per_hour_low=1e200,
            usd_per_hour_high=1e200,
            contingency_fraction=0,
        )


def test_direct_construction_rejects_nonfinite() -> None:
    with pytest.raises(PriceCeilingError):
        PriceCeilingRecommendation(
            hours=1,
            goal_count=0,
            recommended_ceiling_usd=float("inf"),
            low_usd=1,
            high_usd=1,
            notes=[],
        )
