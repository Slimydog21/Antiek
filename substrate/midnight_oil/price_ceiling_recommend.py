"""Recommend an operator-facing price ceiling for Midnight Oil runs.

Pure advisory math: given planned work hours, goal count, and injected unit
rates, produce a recommended USD ceiling for operator approval.

Never spends, never reserves, never calls providers. Authority is always
``advisory`` — the operator (or BudgetLedger after approval) remains the
spend authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


class PriceCeilingError(ValueError):
    """Malformed price-ceiling recommendation inputs."""


@dataclass(frozen=True)
class PriceCeilingRecommendation:
    hours: float
    goal_count: int
    recommended_ceiling_usd: float
    low_usd: float
    high_usd: float
    authority: str = field(default="advisory", init=False)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "authority", "advisory")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hours": self.hours,
            "goal_count": self.goal_count,
            "recommended_ceiling_usd": self.recommended_ceiling_usd,
            "low_usd": self.low_usd,
            "high_usd": self.high_usd,
            "authority": self.authority,
            "notes": list(self.notes),
        }


def recommend_price_ceiling(
    *,
    hours: float,
    goals: Sequence[str] | int,
    usd_per_hour_low: float = 1.0,
    usd_per_hour_high: float = 5.0,
    usd_per_goal: float = 0.5,
    contingency_fraction: float = 0.15,
) -> PriceCeilingRecommendation:
    """Recommend a finite nonnegative USD ceiling for operator approval.

    Parameters are injected unit rates — not live market quotes.
    """
    if not isinstance(hours, (int, float)) or not (hours == hours) or hours == float("inf"):
        raise PriceCeilingError("hours must be a finite number")
    h = float(hours)
    if h <= 0:
        raise PriceCeilingError("hours must be > 0")

    if isinstance(goals, int):
        goal_count = goals
    else:
        goal_count = len([g for g in goals if str(g).strip()])
    if goal_count < 0:
        raise PriceCeilingError("goal_count must be nonnegative")

    for name, val in (
        ("usd_per_hour_low", usd_per_hour_low),
        ("usd_per_hour_high", usd_per_hour_high),
        ("usd_per_goal", usd_per_goal),
        ("contingency_fraction", contingency_fraction),
    ):
        if not isinstance(val, (int, float)) or not (val == val) or val == float("inf"):
            raise PriceCeilingError(f"{name} must be finite")
        if float(val) < 0:
            raise PriceCeilingError(f"{name} must be nonnegative")

    low_rate = float(usd_per_hour_low)
    high_rate = float(usd_per_hour_high)
    if high_rate < low_rate:
        raise PriceCeilingError("usd_per_hour_high must be >= usd_per_hour_low")

    goal_cost = goal_count * float(usd_per_goal)
    low = h * low_rate + goal_cost
    high = h * high_rate + goal_cost
    mid = (low + high) / 2.0
    contingency = mid * float(contingency_fraction)
    recommended = mid + contingency

    notes = [
        "authority=advisory — operator must approve ceiling before unattended spend",
        "no live provider rates; unit rates are injected assumptions",
        f"base mid=${mid:.4f} + contingency ${contingency:.4f} ({contingency_fraction:.0%})",
        "does not reserve, debit, or call BudgetLedger",
    ]
    return PriceCeilingRecommendation(
        hours=h,
        goal_count=goal_count,
        recommended_ceiling_usd=recommended,
        low_usd=low,
        high_usd=high,
        notes=notes,
    )


__all__ = [
    "PriceCeilingError",
    "PriceCeilingRecommendation",
    "recommend_price_ceiling",
]
