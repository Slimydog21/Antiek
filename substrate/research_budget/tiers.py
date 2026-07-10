"""Canonical, operator-tunable research tier budgets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class TierBudget:
    """A declared research effort envelope."""

    breadth: int
    depth: int
    token_budget: int
    max_tool_calls: int

    def __post_init__(self) -> None:
        if min(self.breadth, self.depth, self.token_budget, self.max_tool_calls) <= 0:
            raise ValueError("every tier budget field must be positive")


# OPERATOR_TUNABLE: breadth=2, depth=1 are the below-deep GPT-Researcher posture;
# token_budget=20_000 and max_tool_calls=8 are conservative effort hypotheses from
# doctrine I-1's token-usage and max-tool-calls quality curves, not measured optima.
FAST = TierBudget(breadth=2, depth=1, token_budget=20_000, max_tool_calls=8)
# OPERATOR_TUNABLE: breadth=4, depth=2 come from GPT-Researcher deep mode;
# token_budget=80_000 and max_tool_calls=32 are doctrine I-1 effort-scaling hypotheses.
DEEP = TierBudget(breadth=4, depth=2, token_budget=80_000, max_tool_calls=32)
# OPERATOR_TUNABLE: breadth=10 and depth=5 represent the doctrine's 10+ subagent
# wrestle posture; token_budget=200_000 and max_tool_calls=96 follow Anthropic's
# effort-scaling tiers and doctrine I-1, pending Antiek W0 curve calibration.
WRESTLE = TierBudget(breadth=10, depth=5, token_budget=200_000, max_tool_calls=96)

TIERS: Mapping[str, TierBudget] = {
    "fast": FAST,
    "deep": DEEP,
    "wrestle": WRESTLE,
}


def assert_strictly_monotone(tiers: Mapping[str, TierBudget]) -> None:
    """Assert fast < deep < wrestle independently for every tuple field."""
    ordered = (tiers["fast"], tiers["deep"], tiers["wrestle"])
    for field in ("breadth", "depth", "token_budget", "max_tool_calls"):
        values = tuple(getattr(tier, field) for tier in ordered)
        assert values[0] < values[1] < values[2], f"{field} must be strictly monotone: {values}"


assert_strictly_monotone(TIERS)
