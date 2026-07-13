"""Midnight Oil time-budget adherence — did the run respect its time allocation?

Operator vision (ask #13): *"an autonomous research sub-agent swarm mode called
'midnight oil' where users can engage in a deep research without needing to be in
the workstation; all they need to do is set a time of work and goals (and the
system provides the user a recommended price ceiling to approve) then the agent
goes off to execute that task."* The operator sets THREE resources for an
unattended run: a GOAL set, a COST ceiling (price), and a TIME allocation ("a
time of work"). Two of the three closed loops are measured:
``budget_ledger`` reconciles COST (reserve-before-spend, cents) and
``goal_delivery`` reconciles GOALS (did the findings address the committed
deliverables). But the TIME closed loop is open: nothing measures whether the run
respected its time allocation. A run that nails every goal within its cost ceiling
but takes 3x the declared "time of work" is a partially-failed run — it either
genuinely needed more time (the operator should raise the allocation) or the agent
burned time without progress (a control failure). Either way the operator, having
walked away ("without needing to be in the workstation"), cannot see it.

**The measurement (hard to vary).** Given the operator-declared
``declared_budget_minutes`` (the "time of work" cap) and the recorded
``actual_elapsed_minutes`` (how long the run took; the route layer supplies this
from start/end timestamps):

* ``utilization_ratio = actual_elapsed / declared_budget`` — the share of the
  allocation consumed. ``1.0`` = exactly used the budget.
* The verdict:

  - ``actual_elapsed_minutes`` is ``None`` or ``<= 0`` → ``unknown`` (run did not
    finish or did not record its duration — defer, never fabricated).
  - ``declared_budget_minutes`` is ``None`` or ``<= 0`` → ``uncapped`` (the
    operator set no time budget — adherence against a cap that was never set is
    not measurable; distinct from ``within_budget``).
  - ``utilization_ratio <= 1.0`` → ``within_budget`` (the run respected its time
    allocation).
  - ``utilization_ratio > 1.0`` → ``over_budget`` (the run exceeded its time
    allocation — the overrun fact).

* ``overrun_minutes = max(0, actual - declared)`` and ``overrun_ratio =
  overrun_minutes / declared_budget`` (the overrun magnitude; ``0.0`` when within,
  ``None`` when uncapped/unknown).

**Per-phase attribution (the actionable diagnostic).** When an optional
``phase_breakdown`` is supplied — a sequence of ``(phase_name,
declared_minutes, actual_minutes)`` tuples — the module measures each phase's
utilization and reports ``overrun_phases`` (the phases that exceeded their
allocation). An unattended run that overran because ONE phase ran away is a
different signal from a uniform drift across all phases; the operator sees WHERE
the time went, not just THAT it went over. Phases with a ``None``/non-positive
declared or actual are ``uncapped``/``unknown`` respectively (the same honesty
rules, applied per-phase).

**The overrun is a FACT, not a cause judgment (load-bearing).** A time overrun
has two indistinguishable causes from pure measurement: the task was genuinely
harder than scoped (a planning miss — raise the allocation) or the agent was
inefficient (a control failure — fix the orchestration). THIS axis reports the
overrun fact and magnitude; the cause is deferred to composition with
``goal_delivery`` (an over-budget run that delivered every goal is a planning
miss; an over-budget run that delivered nothing is a control failure). Measuring
the fact honestly, without fabricating a cause, is the same discipline as
``merge_integrity``'s informational orphan ratio and ``search_quality``'s
NDCG-over-known-relevance bound.

**Honesty rules (load-bearing):**

* ``unknown`` when the run did not finish or record its duration (``None``/``<= 0``
  actual) — never ``within_budget`` or ``over_budget`` (fabricating a verdict on
  a run whose duration is unknown would hide an unfinished run behind a phony
  all-clear).
* ``uncapped`` when the operator set no time budget — distinct from
  ``within_budget`` (respecting a cap that was set vs having no cap to respect).
* ``utilization_ratio`` / ``overrun_ratio`` are ``None`` when unmeasurable
  (unknown or uncapped) — defer, never ``0.0``/``1.0``.
* Negative durations raise (a clock that ran backwards is a recording error, not
  a measurement input).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock (the route layer supplies ``actual_elapsed_minutes`` from timestamps), no
  mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** This module defines its own frozen
dataclasses and takes plain numeric inputs (the ``midnight_oil`` package is not
on frozen origin/main, so importing it would break the bar on frozen main). The
route layer adapts: it reads start/end timestamps and the declared time budget
from the run record and passes them as plain numbers.
"""

from __future__ import annotations

from dataclasses import dataclass


class TimeBudgetAdherenceError(ValueError):
    """A time-budget-adherence input violates a load-bearing invariant."""


@dataclass(frozen=True)
class PhaseAdherence:
    """One phase's time-budget adherence. Advisory, pure."""

    phase_name: str
    declared_minutes: float | None
    actual_minutes: float | None
    utilization_ratio: float | None  # None if uncapped/unknown
    verdict: str  # within_budget | over_budget | uncapped | unknown


@dataclass(frozen=True)
class TimeBudgetAdherenceReport:
    """An unattended run's time-budget adherence profile. Advisory, pure."""

    run_id: str
    declared_budget_minutes: float | None
    actual_elapsed_minutes: float | None
    utilization_ratio: float | None  # actual/declared; None if uncapped/unknown
    overrun_minutes: float  # max(0, actual - declared); 0.0 if within/uncapped/unknown
    overrun_ratio: float | None  # overrun/declared; None if uncapped/unknown
    verdict: str  # within_budget | over_budget | uncapped | unknown
    phase_adherences: tuple[PhaseAdherence, ...]
    overrun_phase_count: int  # phases that exceeded their allocation
    over_cap_phase_count: int  # phases with a set cap that was exceeded
    notes: tuple[str, ...]
    authority: str = "advisory"


def _phase_verdict(
    declared: float | None, actual: float | None, utilization: float | None
) -> str:
    if actual is None or actual <= 0:
        return "unknown"
    if declared is None or declared <= 0:
        return "uncapped"
    if utilization is None:
        return "unknown"
    return "over_budget" if utilization > 1.0 else "within_budget"


def measure_time_budget_adherence(
    *,
    run_id: str,
    declared_budget_minutes: float | None,
    actual_elapsed_minutes: float | None,
    phase_breakdown: tuple[tuple[str, float | None, float | None], ...] = (),
) -> TimeBudgetAdherenceReport:
    """Measure whether an unattended run respected its declared time allocation.

    ``declared_budget_minutes`` is the operator's "time of work" cap.
    ``actual_elapsed_minutes`` is the recorded run duration (the route layer
    supplies this from start/end timestamps). ``phase_breakdown`` is an optional
    per-phase ``(name, declared, actual)`` sequence for attribution. Returns a
    :class:`TimeBudgetAdherenceReport` with the utilization ratio, verdict, and
    per-phase attribution.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not run_id or not run_id.strip():
        raise TimeBudgetAdherenceError("run_id must be a non-empty string")
    for label, value in (
        ("declared_budget_minutes", declared_budget_minutes),
        ("actual_elapsed_minutes", actual_elapsed_minutes),
    ):
        if value is not None and value < 0:
            raise TimeBudgetAdherenceError(
                f"{label} must be non-negative or None, got {value!r}"
            )
    for name, p_declared, p_actual in phase_breakdown:
        if not name or not name.strip():
            raise TimeBudgetAdherenceError(
                "phase names in phase_breakdown must be non-empty"
            )
        for label, value in (("declared", p_declared), ("actual", p_actual)):
            if value is not None and value < 0:
                raise TimeBudgetAdherenceError(
                    f"phase {name!r} {label} must be non-negative or None, got {value!r}"
                )

    capped = declared_budget_minutes is not None and declared_budget_minutes > 0
    recorded = actual_elapsed_minutes is not None and actual_elapsed_minutes > 0

    if not recorded:
        utilization: float | None = None
        verdict = "unknown"
        overrun_minutes = 0.0
        overrun_ratio: float | None = None
    elif not capped:
        utilization = None
        verdict = "uncapped"
        overrun_minutes = 0.0
        overrun_ratio = None
    else:
        assert declared_budget_minutes is not None and actual_elapsed_minutes is not None
        utilization = actual_elapsed_minutes / declared_budget_minutes
        verdict = "over_budget" if utilization > 1.0 else "within_budget"
        overrun_minutes = max(
            0.0, actual_elapsed_minutes - declared_budget_minutes
        )
        overrun_ratio = (
            overrun_minutes / declared_budget_minutes if declared_budget_minutes else None
        )

    phase_adherences: list[PhaseAdherence] = []
    overrun_phase_count = 0
    for name, p_declared, p_actual in phase_breakdown:
        p_capped = p_declared is not None and p_declared > 0
        p_recorded = p_actual is not None and p_actual > 0
        if not p_recorded:
            p_util: float | None = None
        elif not p_capped:
            p_util = None
        else:
            assert p_declared is not None and p_actual is not None
            p_util = p_actual / p_declared
        p_verdict = _phase_verdict(p_declared, p_actual, p_util)
        if p_verdict == "over_budget":
            overrun_phase_count += 1
        phase_adherences.append(
            PhaseAdherence(
                phase_name=name,
                declared_minutes=p_declared,
                actual_minutes=p_actual,
                utilization_ratio=p_util,
                verdict=p_verdict,
            )
        )

    over_cap_phase_count = sum(
        1 for ph in phase_adherences if ph.verdict == "over_budget"
    )

    notes: list[str] = [
        "time-budget adherence measures whether an unattended Midnight Oil run "
        "respected its declared 'time of work' allocation — the TIME closed loop; "
        "budget_ledger reconciles COST (cents) and goal_delivery reconciles GOALS "
        "(did findings address deliverables), but nothing checked the time cap",
        "utilization_ratio = actual_elapsed / declared_budget (1.0 = exactly used); "
        "verdict: within_budget (<=1.0), over_budget (>1.0), uncapped (no budget "
        "declared), unknown (run did not finish/record duration)",
        "the overrun is a FACT, not a cause judgment — a time overrun is a planning "
        "miss (task harder than scoped) OR a control failure (agent inefficient); "
        "this axis cannot distinguish them purely, so it reports the magnitude and "
        "defers the cause to composition with goal_delivery (over-budget + goals "
        "delivered = planning miss; over-budget + nothing delivered = control failure)",
        "unknown when the run did not record its duration (never fabricated as "
        "within/over — hides an unfinished run behind a phony verdict); uncapped when "
        "the operator set no time budget (respecting a set cap vs having no cap)",
        "per-phase attribution shows WHERE the time went (runaway phase vs uniform "
        "drift); phases with no declared cap are uncapped, phases that did not run are "
        "unknown — the same honesty rules applied per-phase",
    ]
    util_str = (
        f"{utilization:.0%}" if utilization is not None else "n/a"
    )
    over_str = (
        f"{overrun_ratio:.0%}" if overrun_ratio is not None else "n/a"
    )
    notes.append(
        f"verdict {verdict}: utilization {util_str}, overrun {overrun_minutes:.0f} min "
        f"(ratio {over_str}); {overrun_phase_count} of {len(phase_adherences)} "
        f"phase(s) overran"
    )

    return TimeBudgetAdherenceReport(
        run_id=run_id,
        declared_budget_minutes=declared_budget_minutes,
        actual_elapsed_minutes=actual_elapsed_minutes,
        utilization_ratio=utilization,
        overrun_minutes=overrun_minutes,
        overrun_ratio=overrun_ratio,
        verdict=verdict,
        phase_adherences=tuple(phase_adherences),
        overrun_phase_count=overrun_phase_count,
        over_cap_phase_count=over_cap_phase_count,
        notes=tuple(notes),
    )
