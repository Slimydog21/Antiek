"""Cost-efficiency — was the Midnight Oil run's spend worth its delivered output?

Operator vision (ask #13): users *"set a time of work and goals (and the system
provides the user a recommended price ceiling to approve) then the agent goes off
to execute that task."* The operator APPROVES A PRICE CEILING and walks away. The
five existing accountability axes answer: did it stay in budget (cost ledger),
hit its goals, respect its time, stay in scope, and was the ceiling estimate
accurate. None answers the operator's follow-up question when they return: *"was
the spend WORTH it?"* — the value-per-dollar economics. A run can hit every goal,
stay perfectly in scope and under an accurately-estimated ceiling, yet still be a
poor deal (it spent the full approved ceiling to deliver a thin result). That gap
is this axis.

**Genuinely distinct (orthogonal — different object measured):**

* ``budget`` (cost ledger): did the run stay UNDER its budget? (absolute spend vs
  cap)
* ``goals`` (#1938): did the run ACHIEVE its goals? (achievement rate)
* ``time`` (#1963): did the run respect its time allocation?
* ``scope`` (#1967): did the run stay within its goals (no drift)?
* ``ceiling-accuracy`` (#1968): did the RECOMMENDED ceiling match the ACTUAL
  cost? (recommender estimation accuracy)
* ``budget projection`` (#1838): will THIS single prompt exceed the budget?
  (forward cost)
* THIS (``cost_efficiency``): was the spend WORTH the output? (value-per-dollar —
  ``cost / delivered``)

``ceiling-accuracy`` perfect (estimate == actual) does NOT imply
``cost_efficiency`` good — you can accurately estimate a wasteful spend.
``cost_efficiency`` good does NOT imply ``ceiling-accuracy`` — you can get great
value while the estimate was off. The two are orthogonal: one grades the
RECOMMENDER, the other grades the VALUE of the spend. A run that achieved all
goals (great ``goals`` score) at 10x the necessary cost is still wasteful here.

**The measurement (hard to vary):**

Given a portfolio of runs, each with ``cost_cents`` and ``delivered_units``
(caller-defined value unit — resolved goals, resolved insights, papers processed;
the axis is unit-agnostic, the caller must be consistent):

* ``total_cost`` = sum of run costs; ``total_delivered`` = sum of delivered units
* ``cost_per_unit = total_cost / total_delivered`` (cents per delivered unit) —
  the headline value-per-dollar number
* portfolio aggregation (sum/sum, NOT mean-of-per-run) is load-bearing: a run
  that cost money but delivered NOTHING drags up portfolio cost-per-unit (a cost
  sink makes the portfolio less efficient — honest)

**Verdict** (relative to the caller-provided ``efficiency_target``):

* ``unknown`` — zero runs, OR ``total_delivered == 0`` (delivered nothing —
  cannot measure value-per-dollar; defer, NEVER fabricate as "infinitely
  expensive". A run that delivered nothing is a GOALS/SCOPE failure, not an
  efficiency verdict)
* ``free_delivery`` — ``total_cost == 0`` with delivered output (a free run — a
  notable edge: possibly a cost-tracking gap, possibly a genuinely free tier)
* ``efficient`` — ``cost_per_unit <= efficiency_target`` (at or below target —
  good value; the boundary is inclusive)
* ``at_target`` — within the tolerance band above target (``target <
  cost_per_unit <= target * (1 + tolerance)``; default tolerance ``0.20``;
  boundary inclusive)
* ``expensive`` — ``cost_per_unit > target * (1 + tolerance)`` (poor value — the
  spend outran the output)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict when the value base is empty — defer
  rather than assert "infinitely expensive".
* ``cost_per_unit`` is ``None`` when ``total_delivered == 0`` (division by zero —
  defer, never fabricated).
* a zero ``efficiency_target`` is meaningless (it makes every positive spend
  "expensive" and is not a real target) — it raises.
* negative costs or delivered units raise (a recording error, not an input).
* ``tolerance`` must be in ``[0, 1]`` (raises otherwise).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``RunCost`` input shape
(the route layer adapts 1:1 from ``midnight_oil``'s real run records, which are
NOT on frozen main). Pure-Python: stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_TOLERANCE: float = 0.20


@dataclass(frozen=True)
class RunCost:
    """One run's actual cost and delivered value units. Pure input."""

    cost_cents: int  # actual spend, >= 0
    delivered_units: int  # delivered value units (caller-defined), >= 0


@dataclass(frozen=True)
class CostEfficiencyReport:
    """The cost-efficiency verdict. Advisory, pure."""

    run_count: int
    total_cost_cents: int
    total_delivered_units: int
    cost_per_unit: float | None  # cents per delivered unit; None if nothing delivered
    efficiency_target_cents_per_unit: float
    tolerance: float
    verdict: str  # unknown | free_delivery | efficient | at_target | expensive
    notes: tuple[str, ...]
    authority: str = "advisory"


class CostEfficiencyError(ValueError):
    """A cost-efficiency input violates a load-bearing invariant."""


def measure_cost_efficiency(
    runs: Sequence[RunCost],
    efficiency_target_cents_per_unit: float,
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
) -> CostEfficiencyReport:
    """Measure whether the runs' spend was worth their delivered output.

    ``runs`` is the portfolio of completed runs (cost + delivered units).
    ``efficiency_target_cents_per_unit`` is the caller's "good value" target.
    ``tolerance`` is the at-target band above the target (default 0.20).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if efficiency_target_cents_per_unit <= 0:
        raise CostEfficiencyError(
            "efficiency_target_cents_per_unit must be > 0, got "
            f"{efficiency_target_cents_per_unit!r}"
        )
    if not 0.0 <= tolerance <= 1.0:
        raise CostEfficiencyError(f"tolerance must be in [0,1], got {tolerance!r}")

    for run in runs:
        if run.cost_cents < 0:
            raise CostEfficiencyError(
                f"cost_cents must be >= 0, got {run.cost_cents!r}"
            )
        if run.delivered_units < 0:
            raise CostEfficiencyError(
                f"delivered_units must be >= 0, got {run.delivered_units!r}"
            )

    run_count = len(runs)
    total_cost = sum(run.cost_cents for run in runs)
    total_delivered = sum(run.delivered_units for run in runs)

    # Nothing delivered -> value-per-dollar is undefined (a goals/scope failure,
    # not an efficiency verdict). Defer, never fabricate "infinitely expensive".
    if run_count == 0 or total_delivered == 0:
        reason = (
            "zero runs in the portfolio"
            if run_count == 0
            else "the portfolio delivered zero value units — value-per-dollar is "
            "undefined (a goals/scope failure, not an efficiency verdict)"
        )
        return _report(
            run_count,
            total_cost,
            total_delivered,
            None,
            efficiency_target_cents_per_unit,
            tolerance,
            "unknown",
            [
                "cost-efficiency measures whether the runs' spend was WORTH their "
                "delivered output (value-per-dollar = cost/delivered); distinct from "
                "budget (absolute spend), goals (achievement), time, scope, "
                "ceiling-accuracy (estimation), and budget-projection (forward cost)",
                "verdict unknown — value base is empty; cost_per_unit is None (defer, "
                "never fabricated); a verdict requires >=1 run AND total_delivered > 0",
                reason,
            ],
        )

    cost_per_unit = total_cost / total_delivered

    # Delivered output for free — a notable edge (cost-tracking gap or free tier).
    if total_cost == 0:
        return _report(
            run_count,
            total_cost,
            total_delivered,
            cost_per_unit,
            efficiency_target_cents_per_unit,
            tolerance,
            "free_delivery",
            [
                "cost-efficiency measures whether the runs' spend was WORTH their "
                "delivered output (value-per-dollar = cost/delivered); distinct from "
                "budget (absolute spend), goals (achievement), time, scope, "
                "ceiling-accuracy (estimation), and budget-projection (forward cost)",
                "verdict free_delivery — total_cost is 0 with delivered output > 0 (a "
                "free run: possibly a cost-tracking gap, possibly a genuinely free "
                "tier); cost_per_unit is 0.0",
                "portfolio aggregation (sum/sum) is load-bearing: a run that cost "
                "money but delivered nothing drags up cost_per_unit — a cost sink "
                "makes the portfolio less efficient (honest)",
            ],
        )

    upper_band = efficiency_target_cents_per_unit * (1.0 + tolerance)
    if cost_per_unit <= efficiency_target_cents_per_unit:
        verdict = "efficient"
    elif cost_per_unit <= upper_band:
        verdict = "at_target"
    else:
        verdict = "expensive"

    notes: list[str] = [
        "cost-efficiency measures whether the runs' spend was WORTH their delivered "
        "output (value-per-dollar = cost/delivered); ceiling-accuracy grades the "
        "RECOMMENDER (did the estimate match actual cost?), THIS grades the VALUE "
        "(was the spend worth it?) — orthogonal: an accurate estimate of a wasteful "
        "spend is still wasteful",
        "cost_per_unit = total_cost / total_delivered (portfolio sum/sum, NOT "
        "mean-of-per-run); a run that cost money but delivered nothing drags it up",
        "verdict: efficient (cost_per_unit <= target, boundary inclusive), at_target "
        "(within tolerance band above target, boundary inclusive), expensive (beyond "
        "the band), free_delivery (total_cost==0), unknown (value base empty)",
        "unknown when zero runs OR total_delivered==0 — a run that delivered nothing "
        "is a goals/scope failure, NOT an efficiency verdict (defer, never fabricate "
        "'infinitely expensive'); efficiency_target must be > 0; negative "
        "cost/units raise",
    ]
    notes.append(
        f"verdict {verdict}: cost_per_unit {cost_per_unit:.2f} cents/unit over "
        f"{run_count} run(s) (total_cost {total_cost}c, total_delivered "
        f"{total_delivered}); target {efficiency_target_cents_per_unit:.2f}c/unit, "
        f"tolerance {tolerance:.0%}, upper_band {upper_band:.2f}c/unit"
    )

    return _report(
        run_count,
        total_cost,
        total_delivered,
        cost_per_unit,
        efficiency_target_cents_per_unit,
        tolerance,
        verdict,
        notes,
    )


def _report(
    run_count: int,
    total_cost: int,
    total_delivered: int,
    cost_per_unit: float | None,
    efficiency_target: float,
    tolerance: float,
    verdict: str,
    notes: list[str],
) -> CostEfficiencyReport:
    return CostEfficiencyReport(
        run_count=run_count,
        total_cost_cents=total_cost,
        total_delivered_units=total_delivered,
        cost_per_unit=cost_per_unit,
        efficiency_target_cents_per_unit=efficiency_target,
        tolerance=tolerance,
        verdict=verdict,
        notes=tuple(notes),
    )
