"""API-key usage bar + prompt cost projection (pure honesty).

Operator vision: show how much of a budget cap has been used and how a
proposed prompt would affect remaining — without inventing $0 remaining
when spend or cap is unknown.

This module does **not** read live provider meters or dispatch models.
Callers inject spent/cap/projection figures (from settings budget honesty
lanes or offline fixtures).

``would_exceed`` is:
* ``None`` when remaining is unknown **or** projected high is unknown
* ``True`` when projected high > remaining
* ``False`` when projected high ≤ remaining
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UsageBar:
    """Snapshot of spend vs cap for one budget/key scope."""

    daily_cap_usd: float | None
    spent_usd: float | None
    remaining_usd: float | None
    """Signed when both cap and spent known (negative ⇒ over budget)."""
    over_budget: bool | None
    fraction_used: float | None
    """spent/cap when both known and cap > 0; else None (never 0-faked)."""
    spend_basis: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PromptProjection:
    projected_cost_usd_low: float | None
    projected_cost_usd_high: float | None
    remaining_before_usd: float | None
    remaining_after_high_usd: float | None
    """remaining − high when both known; signed; None if either unknown."""
    would_exceed: bool | None
    notes: list[str] = field(default_factory=list)


def compute_usage_bar(
    *,
    daily_cap_usd: float | None,
    spent_usd: float | None,
    spend_basis: str = "reserved_estimate",
) -> UsageBar:
    """Build an honest usage bar from optional cap and spent figures."""
    notes: list[str] = []
    if daily_cap_usd is None:
        notes.append("daily_cap_usd unknown — remaining and fraction_used are null")
    if spent_usd is None:
        notes.append("spent_usd unknown — remaining and fraction_used are null")

    remaining: float | None = None
    over: bool | None = None
    fraction: float | None = None

    if daily_cap_usd is not None and spent_usd is not None:
        remaining = float(daily_cap_usd) - float(spent_usd)
        over = remaining < 0.0
        if float(daily_cap_usd) > 0.0:
            fraction = float(spent_usd) / float(daily_cap_usd)
        else:
            notes.append("daily_cap_usd is zero — fraction_used null (not 0-faked)")
            fraction = None
        if over:
            notes.append(
                f"over display budget by ${abs(remaining):.4f} "
                f"(remaining_usd is signed, not clamped to 0)"
            )
    else:
        remaining = None
        over = None
        fraction = None

    return UsageBar(
        daily_cap_usd=daily_cap_usd,
        spent_usd=spent_usd,
        remaining_usd=remaining,
        over_budget=over,
        fraction_used=fraction,
        spend_basis=spend_basis,
        notes=notes,
    )


def project_prompt_against_bar(
    bar: UsageBar,
    *,
    projected_cost_usd_low: float | None,
    projected_cost_usd_high: float | None,
) -> PromptProjection:
    """Project how a proposed prompt would affect remaining budget."""
    notes: list[str] = list(bar.notes)
    remaining = bar.remaining_usd
    after: float | None = None
    would: bool | None = None

    if projected_cost_usd_high is None:
        notes.append("projected_cost_usd_high unknown — would_exceed is null")
        would = None
    elif remaining is None:
        notes.append("remaining_usd unknown — would_exceed is null (not zero-faked)")
        would = None
    else:
        after = float(remaining) - float(projected_cost_usd_high)
        would = float(projected_cost_usd_high) > float(remaining)
        if would:
            notes.append(
                f"projection high ${float(projected_cost_usd_high):.4f} exceeds "
                f"remaining ${float(remaining):.4f}"
            )

    return PromptProjection(
        projected_cost_usd_low=projected_cost_usd_low,
        projected_cost_usd_high=projected_cost_usd_high,
        remaining_before_usd=remaining,
        remaining_after_high_usd=after,
        would_exceed=would,
        notes=notes,
    )


def usage_bar_to_dict(bar: UsageBar) -> dict[str, Any]:
    return {
        "daily_cap_usd": bar.daily_cap_usd,
        "spent_usd": bar.spent_usd,
        "remaining_usd": bar.remaining_usd,
        "over_budget": bar.over_budget,
        "fraction_used": bar.fraction_used,
        "spend_basis": bar.spend_basis,
        "notes": list(bar.notes),
    }


def prompt_projection_to_dict(proj: PromptProjection) -> dict[str, Any]:
    return {
        "projected_cost_usd_low": proj.projected_cost_usd_low,
        "projected_cost_usd_high": proj.projected_cost_usd_high,
        "remaining_before_usd": proj.remaining_before_usd,
        "remaining_after_high_usd": proj.remaining_after_high_usd,
        "would_exceed": proj.would_exceed,
        "notes": list(proj.notes),
    }


__all__ = [
    "PromptProjection",
    "UsageBar",
    "compute_usage_bar",
    "project_prompt_against_bar",
    "prompt_projection_to_dict",
    "usage_bar_to_dict",
]
