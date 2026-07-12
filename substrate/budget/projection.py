"""Budget projection — pure usage bar + forward prompt-cost impact (ask #8).

The operator's ask: *"include a bar of how much usage has been used on that API
key given the limit I set in my budget in settings; also it would be cool to
display a projection of how the proposed prompt would affect that limit (I want
to know this just in case a given prompt will go over my budget)."*

This module is the **pure projection core**: given a budget state (cap, spent,
remaining, unknown-flags) and a proposed prompt's cost band (low, high), it
returns a structured projection that a Settings UI bar can render directly:
current usage %, headroom, would-exceed, certain-vs-possible exceed, and the
projected remaining AFTER the prompt fires.

**Pure** — no I/O, no config loading, no env vars, no network. The caller
(``estimate_prompt_cost`` in the routes layer, or a future budget-bar endpoint)
supplies the budget state + cost band; this module computes the projection.
This extracts the 3-line ``would_exceed = high > remaining`` buried in the route
into a complete, testable, honest projection substrate.

**Honesty about the unknown.** Budget projection has THREE independent unknowns:
(1) the cap itself (operator hasn't set one); (2) the spend (daemon hasn't
reported); (3) the pricing (dispatch config has placeholder 0.0 rates). Each
must surface as ``None`` (unknown), NEVER as a fabricated 0 or False. A
``would_exceed=False`` against an unknown cap is a lie — it implies safety the
data doesn't support. This is the keystone invariant.
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetProjectionError(ValueError):
    """Fail-closed: structurally invalid budget/cost inputs."""


@dataclass(frozen=True)
class BudgetState:
    """The operator's budget state at a moment in time.

    Mirrors the on-main ``BudgetResponse`` shape (settings_budget.py:52) but as
    a pure dataclass — no pydantic, no I/O. ``unknown`` flags drive honest
    ``None`` projections rather than fabricated zeros.
    """

    daily_cap_usd: float | None
    spent_usd: float | None
    remaining_usd: float | None
    cap_known: bool
    spent_known: bool


@dataclass(frozen=True)
class CostBand:
    """A proposed prompt's estimated cost range (low/high in USD).

    ``pricing_known=False`` when dispatch config has placeholder rates. Both
    bounds are ``None`` in that case — the projection cannot be numeric.
    """

    estimated_usd_low: float | None
    estimated_usd_high: float | None
    pricing_known: bool


@dataclass(frozen=True)
class BudgetProjection:
    """The structured projection a Settings UI bar renders.

    Every ``None`` is an honest unknown — never a fabricated 0 or False.
    """

    # Current usage bar (how much of the cap is spent).
    usage_pct: float | None  # spent / cap * 100; None when cap or spend unknown
    headroom_pct: float | None  # remaining / cap * 100; None when cap or spend unknown
    headroom_usd: float | None  # remaining_usd; None when unknown

    # Forward projection (impact of firing the proposed prompt NOW).
    would_exceed_budget: bool | None  # True/False/None(unknown)
    certain_exceed: bool | None  # even the LOW estimate blows the budget
    possible_exceed: bool | None  # the HIGH estimate might blow the budget
    projected_remaining_worst: float | None  # remaining - high (most costly path)
    projected_remaining_best: float | None  # remaining - low (least costly path)
    projected_usage_pct: float | None  # (spent + high) / cap * 100 — after-prompt bar

    # Provenance of the projection — honest about what was known.
    cap_known: bool
    spent_known: bool
    pricing_known: bool
    notes: tuple[str, ...]


def project_budget(
    budget: BudgetState,
    cost: CostBand,
) -> BudgetProjection:
    """Project a proposed prompt's impact on the operator's budget.

    Pure: no I/O. Every unknown surfaces as ``None`` — never fabricated. See the
    module docstring for the three-independent-unknowns honesty keystone.
    """
    # Structural validation: cost band must be well-formed when pricing is known.
    if cost.pricing_known:
        lo = cost.estimated_usd_low
        hi = cost.estimated_usd_high
        if lo is None or hi is None:
            raise BudgetProjectionError(
                "pricing_known=True requires both estimated_usd_low and _high"
            )
        if lo < 0 or hi < 0:
            raise BudgetProjectionError("cost estimates must be non-negative")
        if lo > hi:
            raise BudgetProjectionError(
                "estimated_usd_low must not exceed estimated_usd_high"
            )

    # Structural validation: budget state consistency.
    if budget.cap_known and budget.daily_cap_usd is not None and budget.daily_cap_usd <= 0:
        raise BudgetProjectionError("daily_cap_usd must be positive when known")
    # Note: spent > cap is NOT an error — the operator may have overspent and
    # remaining is honestly negative. The projection handles it (would_exceed=True).

    notes: list[str] = []

    # --- current usage bar ---
    usage_pct: float | None
    headroom_pct: float | None
    headroom_usd: float | None
    if budget.cap_known and budget.spent_known and budget.daily_cap_usd and budget.spent_usd is not None:
        cap = budget.daily_cap_usd
        spent = budget.spent_usd
        usage_pct = round((spent / cap) * 100.0, 4)
        remaining = budget.remaining_usd if budget.remaining_usd is not None else (cap - spent)
        headroom_pct = round((remaining / cap) * 100.0, 4)
        headroom_usd = round(remaining, 8)
    else:
        usage_pct = None
        headroom_pct = None
        headroom_usd = budget.remaining_usd  # may still be None — honest
        if not budget.cap_known:
            notes.append("daily cap unknown — usage bar cannot render")
        if not budget.spent_known:
            notes.append("spend unknown — usage bar cannot render")

    # --- forward projection (would-exceed + projected-remaining) ---
    can_project_exceed = (
        budget.cap_known
        and budget.spent_known
        and budget.remaining_usd is not None
        and cost.pricing_known
        and cost.estimated_usd_low is not None
        and cost.estimated_usd_high is not None
    )

    if can_project_exceed:
        # can_project_exceed guarantees all four are non-None; narrow for mypy.
        assert budget.remaining_usd is not None
        assert cost.estimated_usd_low is not None
        assert cost.estimated_usd_high is not None
        remaining = budget.remaining_usd
        lo = cost.estimated_usd_low
        hi = cost.estimated_usd_high
        cap = budget.daily_cap_usd or 0.0
        spent = budget.spent_usd or 0.0

        certain_exceed = lo > remaining
        possible_exceed = hi > remaining
        would_exceed = certain_exceed or possible_exceed

        projected_remaining_worst = round(remaining - hi, 8)
        projected_remaining_best = round(remaining - lo, 8)
        projected_usage_pct = round(((spent + hi) / cap) * 100.0, 4) if cap > 0 else None

        if certain_exceed:
            notes.append(
                f"certain exceed — even the low estimate (${lo}) exceeds remaining (${remaining})"
            )
        elif possible_exceed:
            notes.append(
                f"possible exceed — high estimate (${hi}) exceeds remaining (${remaining})"
            )
        else:
            notes.append(
                f"within budget — high estimate (${hi}) fits remaining (${remaining})"
            )
    else:
        would_exceed = None
        certain_exceed = None
        possible_exceed = None
        projected_remaining_worst = None
        projected_remaining_best = None
        projected_usage_pct = None
        if not (budget.cap_known and budget.spent_known):
            notes.append("budget state incomplete — cannot assert would_exceed")
        if not cost.pricing_known:
            notes.append("pricing unknown — cost projection is advisory-only")

    return BudgetProjection(
        usage_pct=usage_pct,
        headroom_pct=headroom_pct,
        headroom_usd=headroom_usd,
        would_exceed_budget=would_exceed,
        certain_exceed=certain_exceed,
        possible_exceed=possible_exceed,
        projected_remaining_worst=projected_remaining_worst,
        projected_remaining_best=projected_remaining_best,
        projected_usage_pct=projected_usage_pct,
        cap_known=budget.cap_known,
        spent_known=budget.spent_known,
        pricing_known=cost.pricing_known,
        notes=tuple(notes),
    )


__all__ = [
    "BudgetProjection",
    "BudgetProjectionError",
    "BudgetState",
    "CostBand",
    "project_budget",
]
