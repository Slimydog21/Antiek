from __future__ import annotations

import json
from decimal import Decimal

import pytest

from substrate.research_budget import TIERS, TierBudget
from substrate.research_budget.projection import ModelPrice, project_cost
from substrate.research_budget.run_record import (
    BudgetVerdict,
    accumulate_actuals,
    declare_run,
    parse_run_record,
)
from substrate.research_budget.tiers import assert_strictly_monotone


def test_monotonicity_assertion_fires_for_equal_field() -> None:
    invalid = {
        "fast": TierBudget(2, 1, 20_000, 8),
        "deep": TierBudget(2, 2, 80_000, 32),
        "wrestle": TierBudget(8, 4, 200_000, 96),
    }

    with pytest.raises(AssertionError, match="breadth"):
        assert_strictly_monotone(invalid)


@pytest.mark.parametrize(
    ("tokens", "calls", "expected"),
    [
        (79, 7, BudgetVerdict.WITHIN),
        (80, 7, BudgetVerdict.WARNED),
        (99, 8, BudgetVerdict.WARNED),
        (100, 8, BudgetVerdict.WARNED),
        (101, 8, BudgetVerdict.EXCEEDED),
    ],
)
def test_verdict_boundaries(tokens: int, calls: int, expected: BudgetVerdict) -> None:
    budget = TierBudget(breadth=1, depth=1, token_budget=100, max_tool_calls=10)
    record = declare_run("run-1", "fast", budget)

    assert accumulate_actuals(record, tokens_spent=tokens, tool_calls_made=calls).verdict is expected


def test_declare_accumulate_serialize_parse_round_trip() -> None:
    record = declare_run("run-42", "deep", TIERS["deep"])
    updated = accumulate_actuals(record, tokens_spent=12_345, tool_calls_made=9)

    payload = json.loads(json.dumps(updated.to_payload()))

    assert parse_run_record(payload) == updated


def test_projection_matches_hand_computed_interval_to_cent() -> None:
    budget = TierBudget(breadth=4, depth=2, token_budget=100_000, max_tool_calls=32)
    prices = (
        ModelPrice("economy", Decimal("2.00"), Decimal("8.00")),
        ModelPrice("premium", Decimal("5.00"), Decimal("15.00")),
    )

    projection = project_cost(budget, prices)

    # Half-use at cheapest combined rate: 50k * ($2*1.25 + $8) / 1M = $0.525.
    # Full-use at priciest combined rate: 100k * ($5*1.25 + $15) / 1M = $2.125.
    assert projection.lower_usd == Decimal("0.53")
    assert projection.upper_usd == Decimal("2.13")
