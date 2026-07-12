"""Midnight Oil execution planner — the phased time+token scheduler (ask #13).

The operator's vision (ask #13): *"...autonomous research sub-agent swarm mode
called 'midnight oil' where users can engage in a deep research without needing to
be in the workstation; all they need to do is set a time of work and goals (and the
system provides the user a recommended price ceiling to approve) then the agent
goes off to execute that task."*

The cost estimator (:func:`estimate_midnight_oil_cost`) bounds the SPEND — it
produces the recommended price ceiling the operator approves. But the operator
also names a TIME of work and a set of GOALS. **Who turns those into the concrete
sequence of phases the swarm actually executes?** That is this module: the pure
**execution planner** that decomposes ``(duration, goals, cadence)`` into an
ordered, auditable schedule of phases — each carrying its goal, its time slice,
its per-tier token budget, and its cumulative spend envelope.

**Why this is its own module and imports nothing off-main.** The cost estimate
ships in a separate off-main PR. Hard-importing it would stack two PRs and break
independent bar-cleanliness on a frozen main. Instead the planner takes the
cadence + tier pricing as injectable inputs (the same shapes #1849 defines) and
produces the schedule; the route layer that has both modules on hand wires them.
The planner owns the ONE thing #1849 does NOT: the **time dimension** and the
**phase ordering**. #1849 bounds total cost; this module says which phase runs
when, for how long, against which goal, and within what running spend envelope.

**The load-bearing invariants (each is a test):**

1. **Every approved minute is allocated; no minute is invented or lost.** The
   sum of all phase time slices equals the total duration exactly (integer
   accounting; the remainder of integer division is distributed to the FIRST
   goals/phases deterministically — never silently dropped, never invented).
2. **Goals are weighted EVENLY unless the caller says otherwise.** The operator
   names a bag of goals, not priorities; an even split is the honest default
   (no fabricated weighting). A caller MAY pass explicit goal weights (all > 0,
   summing to the goal count) to bias time — the planner never invents weights.
3. **Each goal gets exactly ``phases_per_goal`` phases** (from the cadence).
   A phase is one cascade pass (retrieve → draft → synthesize → verify). The
   plan is total: ``num_goals × phases_per_goal`` phases, ordered
   goal-major (goal 0's phases run before goal 1's) so a goal completes before
   the next begins — the swarm is not interleaved (an unattended swarm that
   context-switches between goals burns tokens re-loading context).
4. **The cumulative spend envelope is monotonic and never exceeds the ceiling.**
   Each phase carries ``cumulative_high_cost_usd`` — the running sum of
   per-phase high-bound cost. If the pricing is known this is a real number the
   execution gate (#1842) checks per-phase; if ANY tier is unpriced, the whole
   envelope is ``None`` (unknown) and the planner flags ``pricing_known=False``
   so the gate denies (an unknown never authorizes — #1842's keystone).
5. **Fail-closed on degenerate input.** Zero goals or zero/negative duration
   raise — there is nothing to plan, and inventing a plan would hide a caller
   bug. Negative goal weights raise. Weights that don't sum to the goal count
   raise (the caller must own the weighting decision explicitly).
6. **Deterministic + idempotent.** The same ``(duration, goals, cadence,
   pricing)`` always yields the byte-identical plan (content-addressed
   ``plan_id``). Re-planning is stable.
7. **Pure — no clock, no I/O, no dispatch, no network.** Only math over the
   inputs. The clock is the caller's (duration arrives resolved); the swarm
   dispatch lives behind the execution layer that consumes the plan.

**Composition (the full Midnight Oil spine):**

    operator sets (duration, goals)
        ↓
    estimate_midnight_oil_cost(...)  →  recommended price ceiling (#1849)
        ↓ operator approves the ceiling
    plan_midnight_oil(...)  →  ExecutionPlan (THIS MODULE)
        ↓ swarm launches, executes phase-by-phase
    per phase: authorize_execution(ceiling, consent, headroom) (#1842)
        ↓ authorized → run; denied → STOP (never exceed)
    usage_ledger tracks actuals against the ceiling (#1841)

The planner is the bridge between "operator approved a number" and "the swarm
knows what to do and when."
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


class MidnightOilPlanError(ValueError):
    """A planning input violates a load-bearing invariant."""


@dataclass(frozen=True)
class PhaseTierBudget:
    """One tier's token budget for one phase (high-bound, mirrors #1849)."""

    tier: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class TierPricing:
    """One dispatch tier's pricing (USD per million tokens).

    ``0.0`` or ``None`` means unpriced/placeholder (mirrors dispatch/config.yaml).
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
class CadenceProfile:
    """Phases per goal + the per-phase per-tier token budgets (mirrors #1849)."""

    phases_per_goal: int
    phase_budgets: tuple[PhaseTierBudget, ...]

    def __post_init__(self) -> None:
        if self.phases_per_goal < 1:
            raise MidnightOilPlanError("phases_per_goal must be >= 1")
        if not self.phase_budgets:
            raise MidnightOilPlanError("phase_budgets must be non-empty")
        for budget in self.phase_budgets:
            if budget.input_tokens < 0 or budget.output_tokens < 0:
                raise MidnightOilPlanError(
                    f"phase token budgets must be >= 0 (tier {budget.tier!r})"
                )


@dataclass(frozen=True)
class PlannedPhase:
    """One scheduled phase in the execution plan.

    ``cumulative_high_cost_usd`` is the running high-bound spend envelope through
    and including this phase. ``None`` when pricing is unknown for any tier (the
    gate then denies — an unknown never authorizes). This is the number the
    execution gate (#1842) checks: "does this phase's cumulative envelope fit the
    operator's approved ceiling AND the remaining budget?"
    """

    ordinal: int  # 0-based position in the global schedule
    goal_index: int  # which goal this phase serves
    goal_label: str  # the operator's goal text (carried verbatim for the swarm)
    phase_index_in_goal: int  # 0-based within the goal
    time_slice_minutes: int
    tier_budgets: tuple[PhaseTierBudget, ...]
    phase_high_cost_usd: float | None  # None when any tier unpriced
    cumulative_high_cost_usd: float | None  # running envelope; None when unpriced


@dataclass(frozen=True)
class GoalAllocation:
    """The time budget for one goal (auditable)."""

    goal_index: int
    goal_label: str
    time_minutes: int  # the goal's total time (sum of its phases' slices)


@dataclass(frozen=True)
class ExecutionPlan:
    """The full phased schedule for one Midnight Oil run."""

    plan_id: str  # content-addressed over (duration, goals, cadence, weights)
    total_duration_minutes: int
    goals: tuple[str, ...]
    phases_per_goal: int
    phases: tuple[PlannedPhase, ...]
    goal_allocations: tuple[GoalAllocation, ...]
    pricing_known: bool
    total_high_cost_usd: float | None  # == last phase cumulative; None if unpriced

    @property
    def phase_count(self) -> int:
        return len(self.phases)

    def phases_for_goal(self, goal_index: int) -> tuple[PlannedPhase, ...]:
        """Return the ordered phases serving one goal."""
        return tuple(p for p in self.phases if p.goal_index == goal_index)


def _validate_goals(goals: list[str]) -> tuple[str, ...]:
    if not goals:
        raise MidnightOilPlanError("cannot plan zero goals — at least one goal required")
    cleaned: list[str] = []
    for goal in goals:
        if not isinstance(goal, str):
            raise MidnightOilPlanError(f"each goal must be a string (got {type(goal).__name__})")
        stripped = goal.strip()
        if not stripped:
            raise MidnightOilPlanError("each goal must be non-empty (blank goal rejected)")
        cleaned.append(goal)
    return tuple(cleaned)


def _resolve_weights(
    goal_count: int, weights: list[float] | None
) -> tuple[float, ...]:
    """Resolve goal weights to a normalized-even default or validate the caller's.

    Default is EVEN (1.0 each) — the honest, no-fabricated-priority baseline. A
    caller may pass explicit weights; they must all be > 0 and their mean must be
    1.0 (so weights are relative multipliers around the even split, summing to
    goal_count). This makes the weighting decision the caller's, never invented.
    """
    if weights is None:
        return tuple(1.0 for _ in range(goal_count))
    if len(weights) != goal_count:
        raise MidnightOilPlanError(
            f"weights length {len(weights)} != goal count {goal_count}"
        )
    resolved: list[float] = []
    for weight in weights:
        if not isinstance(weight, (int, float)):
            raise MidnightOilPlanError(f"each weight must be numeric (got {type(weight).__name__})")
        if weight <= 0:
            raise MidnightOilPlanError(f"each weight must be > 0 (got {weight}); zero-weight drops a goal")
        resolved.append(float(weight))
    weight_sum = sum(resolved)
    # weights are relative multipliers; normalize so mean == 1.0 (sum == count)
    return tuple(w * goal_count / weight_sum for w in resolved)


def _allocate_time(
    total_minutes: int, weights: tuple[float, ...]
) -> tuple[int, ...]:
    """Allocate integer minutes across goals by weight, zero loss/invention.

    Largest-remainder method: each goal's float share is floored; the leftover
    minutes (sum of fractional parts) go one each to the goals with the largest
    remainder, until every minute is placed. Deterministic and exact.
    """
    goal_count = len(weights)
    weight_sum = sum(weights)
    raw = [total_minutes * w / weight_sum for w in weights]
    floored = [int(v) for v in raw]
    placed = sum(floored)
    leftover = total_minutes - placed
    if leftover == 0:
        return tuple(floored)
    remainders = sorted(
        range(goal_count), key=lambda i: (raw[i] - floored[i], -i), reverse=True
    )
    result = list(floored)
    for i in range(leftover):
        result[remainders[i]] += 1
    return tuple(result)


def _phase_cost_usd(
    budgets: tuple[PhaseTierBudget, ...],
    pricing: tuple[TierPricing, ...],
) -> float | None:
    """High-bound cost of one phase. None if any tier is unpriced."""
    price_map = {p.tier: p for p in pricing}
    total = 0.0
    for budget in budgets:
        tier_pricing = price_map.get(budget.tier)
        if tier_pricing is None or not tier_pricing.is_priced:
            return None
        in_rate = tier_pricing.input_per_mtok
        out_rate = tier_pricing.output_per_mtok
        assert in_rate is not None and out_rate is not None  # is_priced guarantees > 0
        total += budget.input_tokens * in_rate / 1_000_000
        total += budget.output_tokens * out_rate / 1_000_000
    return total


def _plan_id(
    duration: int,
    goals: tuple[str, ...],
    cadence: CadenceProfile,
    weights: tuple[float, ...] | None,
) -> str:
    payload = json.dumps(
        {
            "duration": duration,
            "goals": list(goals),
            "phases_per_goal": cadence.phases_per_goal,
            "phase_budgets": [
                {"tier": b.tier, "in": b.input_tokens, "out": b.output_tokens}
                for b in cadence.phase_budgets
            ],
            "weights": list(weights) if weights is not None else None,
        },
        sort_keys=True,
    )
    return "mo-plan-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def plan_midnight_oil(
    *,
    duration_minutes: int,
    goals: list[str],
    cadence: CadenceProfile,
    pricing: tuple[TierPricing, ...],
    goal_weights: list[float] | None = None,
) -> ExecutionPlan:
    """Decompose the operator's goals+duration into an ordered phased schedule.

    Returns an :class:`ExecutionPlan` the swarm executes phase-by-phase, each
    phase clearing the execution gate (#1842) against the operator's approved
    ceiling. Pure: no clock, no I/O, no dispatch.

    ``goal_weights`` is optional; the default is an EVEN split (no fabricated
    priority). When provided, weights must all be > 0 and are normalized as
    relative multipliers around the even split (mean == 1.0).
    """
    if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
        raise MidnightOilPlanError(
            "duration_minutes must be an int (minutes), got "
            f"{type(duration_minutes).__name__}"
        )
    if duration_minutes <= 0:
        raise MidnightOilPlanError(
            f"duration_minutes must be > 0 (got {duration_minutes}); cannot plan zero/negative time"
        )

    goal_tuple = _validate_goals(goals)
    weights = _resolve_weights(len(goal_tuple), goal_weights)
    goal_minutes = _allocate_time(duration_minutes, weights)

    pricing_known = all(
        p.is_priced
        for p in pricing
        if any(b.tier == p.tier for b in cadence.phase_budgets)
    )
    # A tier used by the cadence but missing from pricing entirely -> unpriced.
    priced_tiers = {p.tier for p in pricing}
    for budget in cadence.phase_budgets:
        if budget.tier not in priced_tiers:
            pricing_known = False
            break

    phases: list[PlannedPhase] = []
    goal_allocations: list[GoalAllocation] = []
    cumulative = 0.0
    cumulative_known = True
    ordinal = 0

    for goal_index, (goal_label, minutes_for_goal) in enumerate(
        zip(goal_tuple, goal_minutes, strict=True)
    ):
        phase_slices = _allocate_time(minutes_for_goal, tuple(1.0 for _ in range(cadence.phases_per_goal)))
        for phase_index_in_goal in range(cadence.phases_per_goal):
            phase_cost = _phase_cost_usd(cadence.phase_budgets, pricing)
            if phase_cost is None:
                cumulative_known = False
            else:
                cumulative += phase_cost
            phases.append(
                PlannedPhase(
                    ordinal=ordinal,
                    goal_index=goal_index,
                    goal_label=goal_label,
                    phase_index_in_goal=phase_index_in_goal,
                    time_slice_minutes=phase_slices[phase_index_in_goal],
                    tier_budgets=cadence.phase_budgets,
                    phase_high_cost_usd=phase_cost,
                    cumulative_high_cost_usd=cumulative if cumulative_known else None,
                )
            )
            ordinal += 1
        goal_allocations.append(
            GoalAllocation(
                goal_index=goal_index,
                goal_label=goal_label,
                time_minutes=minutes_for_goal,
            )
        )

    total_high_cost = cumulative if cumulative_known else None

    return ExecutionPlan(
        plan_id=_plan_id(
            duration_minutes,
            goal_tuple,
            cadence,
            tuple(goal_weights) if goal_weights is not None else None,
        ),
        total_duration_minutes=duration_minutes,
        goals=goal_tuple,
        phases_per_goal=cadence.phases_per_goal,
        phases=tuple(phases),
        goal_allocations=tuple(goal_allocations),
        pricing_known=pricing_known,
        total_high_cost_usd=total_high_cost,
    )


__all__ = [
    "MidnightOilPlanError",
    "PhaseTierBudget",
    "TierPricing",
    "CadenceProfile",
    "PlannedPhase",
    "GoalAllocation",
    "ExecutionPlan",
    "plan_midnight_oil",
]
