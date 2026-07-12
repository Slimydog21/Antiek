"""Midnight Oil cost estimation — the recommended price ceiling (ask #13).

The operator's vision (ask #13): *"...autonomous research sub-agent swarm mode
called 'midnight oil' where users can engage in a deep research without needing to
be in the workstation; all they need to do is set a time of work and goals (and the
system provides the user a recommended price ceiling to approve) then the agent
goes off to execute that task."*

The recommended price ceiling is the keystone of operator trust in an unattended
swarm: the operator is NOT at the workstation, so the system must bound the spend
BEFORE launch and name the worst-case number the operator approves. This module is
the PURE estimator that turns (duration, goals, cadence, tier pricing) into that
high-bound ceiling + an honest breakdown.

**Why pure + why high-bound.** The operator approves a CEILING — the most the
swarm may spend. So the estimate must be a *worst-case* (high) bound, not an
average; approving an average would let the swarm overshoot the operator's budget
half the time. High-bounding is the load-bearing choice: the ceiling is a *guarantee*
to the operator, and a guarantee that fails half the time is not a guarantee. The
actuals substrate (#1841 ``usage_ledger``) then tracks real spend against this
ceiling, and the execution gate (#1842 ``authorize_execution``) refuses any step
that would exceed it.

**Composes the dispatch-tier pricing (``substrate/dispatch/config.yaml``).** That
config carries per-tier ``input_per_mtok`` / ``output_per_mtok`` in USD per million
tokens, with a documented convention: a value of ``0.0`` means the operator has NOT
set real pricing yet ("Set 0.0 to disable cost tracking"). This estimator mirrors
that convention exactly — a ``0.0`` or ``None`` rate is an UNKNOWN, and an unknown
rate produces an UNKNOWN estimate (``None``), NEVER a fabricated ``$0``. This is the
honesty keystone shared with #1838 (budget projection) and #1842 (execution gate):
unknowns surface as None, never as false zeros.

**Pure — no I/O, no network, no dispatch, no clock.** A pure function over the
duration/goals/cadence/pricing handed to it. The caller owns the config read (it
parses the YAML and passes the rates in); this module never reads files.

**Honesty rules (load-bearing):**

  * **Placeholder pricing → None estimate.** If ANY tier in the cadence has a ``0.0``
    or ``None`` rate, the estimate for that tier is unknown, and the total ceiling
    is unknown (``None``) — never a fabricated number. The operator is told exactly
    which tiers are unpriced via ``unpriced_tiers``.
  * **Zero/None duration → None estimate.** Cannot bound the spend of zero work.
  * **The ceiling is a HIGH bound.** Every per-phase estimate uses the high end of
    the token range (``max_tokens``), and phases-per-goal is rounded UP (the swarm
    cannot run a fraction of a phase). This over-estimates deliberately so the
    approved ceiling is safe.
  * **Every component is auditable.** The breakdown names each tier's token budget,
    rate, and contribution — the operator can see exactly how the number was built.
  * **goals/duration must be non-negative.** Negative inputs raise (never coerced to
    zero — that would hide a caller bug).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class MidnightOilCostError(ValueError):
    """A cost-estimation input violates a load-bearing invariant."""


@dataclass(frozen=True)
class TierPricing:
    """One dispatch tier's pricing (USD per million tokens).

    A rate of ``0.0`` or ``None`` means "unpriced / placeholder" — the operator has
    not set a real value (mirrors ``dispatch/config.yaml`` convention). The estimator
    treats unpriced as UNKNOWN, never as free.
    """

    tier: str
    input_per_mtok: float | None
    output_per_mtok: float | None

    @property
    def is_priced(self) -> bool:
        in_ok = self.input_per_mtok is not None and self.input_per_mtok > 0
        out_ok = self.output_per_mtok is not None and self.output_per_mtok > 0
        return in_ok and out_ok


@dataclass(frozen=True)
class PhaseTokenBudget:
    """One research phase's token budget per tier (high-bound).

    ``input_tokens`` / ``output_tokens`` are the MAX the phase may consume on that
    tier. High-bound so the ceiling is a safe guarantee.
    """

    tier: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CadenceProfile:
    """How many phases each goal takes, and the per-phase token budgets.

    A "phase" is one pass of the deep-research cascade (retrieve → draft →
    synthesize → verify) mapped onto tiers. The operator's cascade is multi-phase;
    this profile makes the cadence explicit and auditable rather than a magic
    multiplier.
    """

    phases_per_goal: int
    phase_budgets: tuple[PhaseTokenBudget, ...]

    def __post_init__(self) -> None:
        if self.phases_per_goal < 1:
            raise MidnightOilCostError("phases_per_goal must be >= 1")
        if not self.phase_budgets:
            raise MidnightOilCostError("phase_budgets must be non-empty")


@dataclass(frozen=True)
class TierCostBreakdown:
    """One tier's estimated cost contribution (auditable)."""

    tier: str
    total_input_tokens: int
    total_output_tokens: int
    input_rate: float | None
    output_rate: float | None
    contribution_usd: float | None  # None when the tier is unpriced


@dataclass(frozen=True)
class MidnightOilCostEstimate:
    """The recommended price ceiling + honest breakdown. Pure value."""

    recommended_ceiling_usd: float | None
    total_phases: int
    breakdown: tuple[TierCostBreakdown, ...]
    unpriced_tiers: tuple[str, ...]
    pricing_known: bool
    notes: tuple[str, ...] = ()

    @property
    def is_estimable(self) -> bool:
        return self.recommended_ceiling_usd is not None


def _validate_nonneg(value: float | int, name: str) -> None:
    if value < 0:
        raise MidnightOilCostError(f"{name} must be >= 0 (got {value})")


def estimate_midnight_oil_cost(
    *,
    duration_minutes: float,
    goals: int,
    cadence: CadenceProfile,
    pricing: list[TierPricing],
    minutes_per_phase: float = 3.0,
) -> MidnightOilCostEstimate:
    """Estimate the recommended price ceiling for an unattended Midnight Oil run.

    ``duration_minutes`` is the operator-set wall-clock budget. ``goals`` is the
    number of research goals. ``cadence`` maps goals → phases and phases → per-tier
    token budgets. ``pricing`` is the dispatch-tier rate table. ``minutes_per_phase``
    is the assumed wall-clock cost of one phase (how many phases fit in the duration).

    Returns a ``MidnightOilCostEstimate`` with the high-bound ceiling. Pure: no I/O.
    """
    _validate_nonneg(duration_minutes, "duration_minutes")
    _validate_nonneg(goals, "goals")
    if goals == 0 or duration_minutes <= 0:
        return MidnightOilCostEstimate(
            recommended_ceiling_usd=None,
            total_phases=0,
            breakdown=(),
            unpriced_tiers=(),
            pricing_known=True,
            notes=("zero work requested — no spend to bound",),
        )
    if minutes_per_phase <= 0:
        raise MidnightOilCostError("minutes_per_phase must be > 0")

    # Phases the duration can sustain, capped by the goals' declared cadence.
    duration_limited_phases = math.floor(duration_minutes / minutes_per_phase)
    goal_limited_phases = goals * cadence.phases_per_goal
    # The swarm runs at most what the goals need, but no more than time allows.
    total_phases = min(duration_limited_phases, goal_limited_phases)
    if total_phases < 1:
        return MidnightOilCostEstimate(
            recommended_ceiling_usd=None,
            total_phases=0,
            breakdown=(),
            unpriced_tiers=(),
            pricing_known=True,
            notes=(
                f"duration {duration_minutes}m too short for even one phase "
                f"(need >= {minutes_per_phase}m); no spend",
            ),
        )

    pricing_by_tier: dict[str, TierPricing] = {p.tier: p for p in pricing}

    # Aggregate per-tier token budgets across the cadence's phases, scaled to total_phases.
    tier_input: dict[str, int] = {}
    tier_output: dict[str, int] = {}
    for budget in cadence.phase_budgets:
        phases_on_this_tier = total_phases  # each phase runs all tiers in the cascade
        tier_input[budget.tier] = tier_input.get(budget.tier, 0) + budget.input_tokens * phases_on_this_tier
        tier_output[budget.tier] = tier_output.get(budget.tier, 0) + budget.output_tokens * phases_on_this_tier

    breakdown: list[TierCostBreakdown] = []
    unpriced: list[str] = []
    total_usd = 0.0
    all_priced = True

    for tier in sorted(tier_input):
        in_tok = tier_input[tier]
        out_tok = tier_output[tier]
        tp = pricing_by_tier.get(tier)
        if tp is None or not tp.is_priced:
            unpriced.append(tier)
            breakdown.append(
                TierCostBreakdown(
                    tier=tier,
                    total_input_tokens=in_tok,
                    total_output_tokens=out_tok,
                    input_rate=tp.input_per_mtok if tp else None,
                    output_rate=tp.output_per_mtok if tp else None,
                    contribution_usd=None,
                )
            )
            all_priced = False
            continue
        assert tp.input_per_mtok is not None and tp.output_per_mtok is not None  # is_priced guard
        in_rate = tp.input_per_mtok
        out_rate = tp.output_per_mtok
        contribution = (in_tok / 1_000_000.0) * in_rate + (out_tok / 1_000_000.0) * out_rate
        total_usd += contribution
        breakdown.append(
            TierCostBreakdown(
                tier=tier,
                total_input_tokens=in_tok,
                total_output_tokens=out_tok,
                input_rate=in_rate,
                output_rate=out_rate,
                contribution_usd=contribution,
            )
        )

    notes: list[str] = [
        f"high-bound ceiling over {total_phases} phase(s) "
        f"(duration-limited {duration_limited_phases} vs goal-limited {goal_limited_phases})"
    ]
    if not all_priced:
        notes.append(
            f"UNPRICED tier(s) {unpriced}: rates are 0.0/None (operator placeholder); "
            "ceiling is None (unknown) — set real rates in dispatch/config.yaml to estimate"
        )
        return MidnightOilCostEstimate(
            recommended_ceiling_usd=None,
            total_phases=total_phases,
            breakdown=tuple(breakdown),
            unpriced_tiers=tuple(unpriced),
            pricing_known=False,
            notes=tuple(notes),
        )

    notes.append(f"ceiling ${total_usd:.4f} is a HIGH bound (max tokens per phase); actuals tracked via #1841")
    return MidnightOilCostEstimate(
        recommended_ceiling_usd=total_usd,
        total_phases=total_phases,
        breakdown=tuple(breakdown),
        unpriced_tiers=(),
        pricing_known=True,
        notes=tuple(notes),
    )


__all__ = [
    "MidnightOilCostError",
    "TierPricing",
    "PhaseTokenBudget",
    "CadenceProfile",
    "TierCostBreakdown",
    "MidnightOilCostEstimate",
    "estimate_midnight_oil_cost",
]
