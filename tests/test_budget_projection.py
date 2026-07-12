"""Budget projection — pure contract tests.

Pins the hard-to-vary honesty invariants for ask #8's projection bar. The module
is pure: every unknown surfaces as None — never a fabricated 0 or False.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from substrate.budget.projection import (  # noqa: E402
    BudgetProjectionError,
    BudgetState,
    CostBand,
    project_budget,
)


def _budget(
    *,
    cap: float | None = 10.0,
    spent: float | None = 3.0,
    remaining: float | None = 7.0,
    cap_known: bool = True,
    spent_known: bool = True,
) -> BudgetState:
    return BudgetState(
        daily_cap_usd=cap,
        spent_usd=spent,
        remaining_usd=remaining,
        cap_known=cap_known,
        spent_known=spent_known,
    )


def _cost(
    *,
    low: float | None = 0.50,
    high: float | None = 1.50,
    pricing_known: bool = True,
) -> CostBand:
    return CostBand(
        estimated_usd_low=low,
        estimated_usd_high=high,
        pricing_known=pricing_known,
    )


# --- honesty keystone: unknowns surface as None, never fabricated ---


def test_unknown_cap_all_projections_none() -> None:
    result = project_budget(
        _budget(cap=None, cap_known=False, remaining=None), _cost()
    )

    assert result.would_exceed_budget is None
    assert result.usage_pct is None
    assert result.headroom_pct is None
    assert result.projected_remaining_worst is None
    assert result.cap_known is False
    assert any("cap unknown" in n for n in result.notes)


def test_unknown_spend_all_projections_none() -> None:
    result = project_budget(
        _budget(spent=None, remaining=None, spent_known=False), _cost()
    )

    assert result.would_exceed_budget is None
    assert result.usage_pct is None
    assert result.headroom_pct is None
    assert result.spent_known is False
    assert any("spend unknown" in n for n in result.notes)


def test_unknown_pricing_would_exceed_none_advisory() -> None:
    result = project_budget(_budget(), _cost(low=None, high=None, pricing_known=False))

    assert result.would_exceed_budget is None
    assert result.certain_exceed is None
    assert result.possible_exceed is None
    assert result.projected_remaining_worst is None
    assert result.pricing_known is False
    assert any("pricing unknown" in n for n in result.notes)
    # But usage bar STILL renders — cap + spend are known.
    assert result.usage_pct is not None


def test_would_exceed_false_never_fabricated_against_unknown() -> None:
    # The keystone: a False would_exceed against unknowns is a lie.
    result = project_budget(
        _budget(cap=None, cap_known=False, remaining=None), _cost()
    )

    assert result.would_exceed_budget is None  # NOT False — no fabricated safety


# --- known everything: prompt fits ---


def test_prompt_within_budget_no_exceed() -> None:
    result = project_budget(_budget(), _cost(low=0.50, high=1.50))

    assert result.would_exceed_budget is False
    assert result.certain_exceed is False
    assert result.possible_exceed is False
    assert any("within budget" in n for n in result.notes)


# --- known everything: possible exceed (high > remaining, low <= remaining) ---


def test_possible_exceed_high_over_remaining() -> None:
    result = project_budget(
        _budget(remaining=1.00, spent=9.0, cap=10.0),
        _cost(low=0.50, high=1.50),
    )

    assert result.would_exceed_budget is True
    assert result.certain_exceed is False  # low (0.50) fits
    assert result.possible_exceed is True  # high (1.50) blows it
    assert any("possible exceed" in n for n in result.notes)


# --- known everything: certain exceed (low > remaining) ---


def test_certain_exceed_low_over_remaining() -> None:
    result = project_budget(
        _budget(remaining=0.30, spent=9.70, cap=10.0),
        _cost(low=0.50, high=1.50),
    )

    assert result.would_exceed_budget is True
    assert result.certain_exceed is True  # even the cheap path blows it
    assert result.possible_exceed is True
    assert any("certain exceed" in n for n in result.notes)


# --- already over budget ---


def test_already_over_budget_exceeds_even_for_zero_cost() -> None:
    result = project_budget(
        _budget(remaining=-1.0, spent=11.0, cap=10.0),
        _cost(low=0.0, high=0.0),
    )

    # remaining is negative; any positive cost exceeds. Even zero-cost against
    # negative remaining is an honest "already exceeded" state.
    assert result.would_exceed_budget is True


# --- usage bar computation ---


def test_usage_bar_percentages() -> None:
    result = project_budget(
        _budget(cap=10.0, spent=3.0, remaining=7.0), _cost()
    )

    assert result.usage_pct == 30.0  # 3/10
    assert result.headroom_pct == 70.0  # 7/10
    assert result.headroom_usd == 7.0


def test_full_usage_bar_at_cap() -> None:
    result = project_budget(
        _budget(cap=10.0, spent=10.0, remaining=0.0), _cost(low=0.0, high=0.0)
    )

    assert result.usage_pct == 100.0
    assert result.headroom_pct == 0.0


# --- projected remaining ---


def test_projected_remaining_worst_and_best() -> None:
    result = project_budget(
        _budget(remaining=7.0, spent=3.0, cap=10.0),
        _cost(low=1.0, high=3.0),
    )

    assert result.projected_remaining_worst == 4.0  # 7 - 3 (high)
    assert result.projected_remaining_best == 6.0  # 7 - 1 (low)


def test_projected_usage_pct_uses_high() -> None:
    result = project_budget(
        _budget(remaining=7.0, spent=3.0, cap=10.0),
        _cost(low=1.0, high=3.0),
    )

    assert result.projected_usage_pct == 60.0  # (3 + 3) / 10


def test_projected_remaining_can_go_negative() -> None:
    # Honest: if the prompt blows the budget, projected remaining is negative.
    result = project_budget(
        _budget(remaining=1.0, spent=9.0, cap=10.0),
        _cost(low=0.50, high=2.0),
    )

    assert result.projected_remaining_worst == -1.0  # 1 - 2


# --- structural validation ---


def test_negative_cost_rejected() -> None:
    with pytest.raises(BudgetProjectionError, match="non-negative"):
        project_budget(_budget(), _cost(low=-1.0, high=1.0))


def test_low_exceeds_high_rejected() -> None:
    with pytest.raises(BudgetProjectionError, match="must not exceed"):
        project_budget(_budget(), _cost(low=2.0, high=1.0))


def test_pricing_known_with_none_bounds_rejected() -> None:
    with pytest.raises(BudgetProjectionError, match="requires both"):
        project_budget(_budget(), _cost(low=None, high=1.0, pricing_known=True))


def test_non_positive_cap_rejected() -> None:
    with pytest.raises(BudgetProjectionError, match="positive"):
        project_budget(
            _budget(cap=0.0, remaining=0.0, spent=0.0), _cost()
        )


# --- notes honest for each unknown combination ---


def test_both_cap_and_spend_unknown_two_notes() -> None:
    result = project_budget(
        _budget(cap=None, cap_known=False, spent=None, spent_known=False, remaining=None),
        _cost(),
    )

    joined = " ".join(result.notes)
    assert "cap unknown" in joined
    assert "spend unknown" in joined


def test_all_three_unknown_three_notes() -> None:
    result = project_budget(
        _budget(cap=None, cap_known=False, spent=None, spent_known=False, remaining=None),
        _cost(low=None, high=None, pricing_known=False),
    )

    joined = " ".join(result.notes)
    assert "cap unknown" in joined
    assert "spend unknown" in joined
    assert "pricing unknown" in joined


# --- idempotent ---


def test_idempotent_same_inputs_same_output() -> None:
    budget = _budget()
    cost = _cost()
    one = project_budget(budget, cost)
    two = project_budget(budget, cost)

    assert one == two
