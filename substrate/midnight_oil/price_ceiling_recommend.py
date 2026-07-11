"""Recommend an operator-facing price ceiling for Midnight Oil runs.

Pure advisory math: given planned work hours, goal count, and injected unit
rates, produce a recommended USD ceiling for operator approval.

Never spends, never reserves, never calls providers. Authority is always
``advisory`` — the operator (or BudgetLedger after approval) remains the
spend authority.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


class PriceCeilingError(ValueError):
    """Malformed price-ceiling recommendation inputs."""


def _require_finite_nonneg(name: str, val: float) -> float:
    if not isinstance(val, (int, float)):
        raise PriceCeilingError(f"{name} must be a number")
    f = float(val)
    if not math.isfinite(f):
        raise PriceCeilingError(f"{name} must be finite")
    if f < 0:
        raise PriceCeilingError(f"{name} must be nonnegative")
    return f


@dataclass(frozen=True)
class PriceCeilingRecommendation:
    hours: float
    goal_count: int
    recommended_ceiling_usd: float
    low_usd: float
    high_usd: float
    notes: list[str] = field(default_factory=list)
    authority: str = field(default="advisory", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "authority", "advisory")
        for name in ("hours", "recommended_ceiling_usd", "low_usd", "high_usd"):
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                raise PriceCeilingError(f"{name} must be finite")
            if float(v) < 0:
                raise PriceCeilingError(f"{name} must be nonnegative")
        if not isinstance(self.goal_count, int) or self.goal_count < 0:
            raise PriceCeilingError("goal_count must be a nonnegative int")

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
    """Recommend a finite nonnegative USD ceiling for operator approval."""
    if not isinstance(hours, (int, float)) or not math.isfinite(float(hours)):
        raise PriceCeilingError("hours must be a finite number")
    h = float(hours)
    if h <= 0:
        raise PriceCeilingError("hours must be > 0")

    if isinstance(goals, int):
        if goals < 0:
            raise PriceCeilingError("goal_count must be nonnegative")
        goal_count = goals
    else:
        goal_count = len([g for g in goals if str(g).strip()])

    low_rate = _require_finite_nonneg("usd_per_hour_low", usd_per_hour_low)
    high_rate = _require_finite_nonneg("usd_per_hour_high", usd_per_hour_high)
    per_goal = _require_finite_nonneg("usd_per_goal", usd_per_goal)
    contingency_fraction_f = _require_finite_nonneg(
        "contingency_fraction", contingency_fraction
    )
    if high_rate < low_rate:
        raise PriceCeilingError("usd_per_hour_high must be >= usd_per_hour_low")

    try:
        goal_cost = goal_count * per_goal
        low = h * low_rate + goal_cost
        high = h * high_rate + goal_cost
        mid = (low + high) / 2.0
        contingency = mid * contingency_fraction_f
        recommended = mid + contingency
    except OverflowError as e:
        raise PriceCeilingError(
            "price ceiling arithmetic overflowed; reduce hours, goals, or unit rates"
        ) from e

    for name, val in (
        ("low_usd", low),
        ("high_usd", high),
        ("recommended_ceiling_usd", recommended),
    ):
        if not math.isfinite(val):
            raise PriceCeilingError(
                f"{name} overflowed to non-finite; reduce hours or unit rates"
            )

    notes = [
        "authority=advisory — operator must approve ceiling before unattended spend",
        "no live provider rates; unit rates are injected assumptions",
        f"base mid=${mid:.4f} + contingency ${contingency:.4f} ({contingency_fraction_f:.0%})",
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
