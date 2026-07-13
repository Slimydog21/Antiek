"""Midnight Oil budget safety margin — how close did each run come to stalling?

Operator vision (ask #13): *"...set a time of work and goals (and the system
provides the user a recommended price ceiling to approve) then the agent goes off
to execute that task."* The operator approves a ceiling and walks away. Two
distinct trust questions arise from that handoff, and they MUST NOT be collapsed:

* ``ceiling_accuracy`` (#1968): was the RECOMMENDATION right on average? It
  compares ``recommended`` against ``actual`` and judges the ESTIMATOR (signed
  bias, tolerance, hit-rate). A question about estimate QUALITY.
* THIS (``budget_safety_margin``): how close did the runs come to STALLING? It
  compares ``actual`` against the ``ceiling`` and measures OPERATIONAL HEADROOM
  (margin, utilization, danger-zone exposure). A question about execution RISK.

They are orthogonal. A recommender can be ``well_calibrated`` on average (mean
bias near zero) while EVERY run rides at 0.98 utilization — right on average,
fragile in practice (a single cost spike stalls it). Conversely a recommender
can leave a ``healthy_margin`` every run (utilization 0.5) while being badly
``over_estimating`` (#1968) — safe but wasteful, and that waste is
``cost_efficiency``'s (#1971) lane, not this one. Bias (estimate quality),
margin (execution safety), and value-per-dollar (economics) are three
independent failure surfaces of unattended mode; this axis owns the safety one.

The measurement (hard to vary). Given a sequence of completed runs, each with an
``approved_ceiling_cents`` (the cap the run operated under) and an
``actual_cost_cents`` (what it spent):

* ``margin_cents = ceiling - actual`` per run (signed headroom: positive = room
  to spare, zero = exactly at the cap, negative = overran the cap).
* ``utilization = actual / ceiling`` per run (scale-free ratio in [0, inf): 0.0 =
  a free run, 1.0 = exactly at the cap, > 1.0 = overran).

Aggregated over the complete runs:

* ``mean_utilization`` — the typical tightness.
* ``max_utilization`` — the WORST-CASE run, the load-bearing stall-risk driver
  (a portfolio is at stall risk if ANY run hit the cliff, because that run
  stalled or nearly did, regardless of how comfortable the others were).
* ``min_margin_cents`` — the tightest absolute headroom (most negative = worst
  overrun); the cents complement to the ratio view.
* ``mean_margin_cents`` — the average absolute headroom.
* ``danger_rate`` — the share of complete runs that operated at or above the
  ``danger_threshold`` (default 0.90, the stall-risk zone).

The verdict:

* zero complete runs -> ``unknown`` (defer — never fabricated; a verdict on no
  executions would hide a non-measured surface behind a phony all-clear).
* ``max_utilization >= danger_threshold`` -> ``at_stall_risk`` (at least one run
  ran in the danger zone — the portfolio contains stall exposure). Boundary
  inclusive: a run sitting exactly at 0.90 IS in the danger zone.
* else -> ``healthy_margin`` (every run stayed below the danger line — a REAL
  measured verdict, distinct from ``unknown``).

**Under-run is honest, not punished.** A run that spent nothing (``actual == 0``)
yields utilization 0.0 and full margin — a real, healthy signal, never flagged.
A run that overran (``actual > ceiling``) yields utilization > 1.0 and negative
margin, carried verbatim (the most extreme stall case; ``max_utilization``
captures it, ``min_margin_cents`` carries the deficit). No clamping: a recorded
1.3 utilization is honest ("ran 30 percent over cap").

**Honesty rules (load-bearing):**

* ``unknown`` when zero complete runs (never ``healthy_margin`` — fabricating a
  clean bill of health on no data would hide an unmeasured risk surface).
* ``mean_utilization`` / ``max_utilization`` / margins / ``danger_rate`` are
  ``None`` when zero complete runs (defer — never ``0.0``).
* Incomplete runs (``actual_cost_cents is None``) are EXCLUDED from all
  calculations (carried as ``incomplete_count``) — a run that did not finish has
  no actual cost to place against its ceiling; fabricating one would conflate
  "did not finish" with "spent X."
* ``approved_ceiling_cents`` must be positive (a zero/negative cap makes
  utilization undefined and margin meaningless); raises otherwise.
* Negative ``actual_cost_cents`` raises (a recording error, not input).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``midnight_oil`` package is not on
frozen origin/main (varying ``__init__.py`` would cause add/add collisions).
This module takes plain per-run numeric tuples; the route layer reads the
approved ceiling from the launch brief and the actual cost from the budget
ledger reconciliation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_DANGER_THRESHOLD: float = 0.90


class BudgetSafetyMarginError(ValueError):
    """A budget-safety-margin input violates a load-bearing invariant."""


@dataclass(frozen=True)
class BudgetSafetyMarginReport:
    """The portfolio's operational headroom / stall-risk profile. Advisory, pure."""

    run_count: int  # complete runs measured
    incomplete_count: int  # runs excluded (no actual cost)
    mean_utilization: float | None  # mean(actual / ceiling); None if zero runs
    max_utilization: float | None  # worst-case ratio; None if zero runs
    min_margin_cents: int | None  # tightest headroom (most negative = worst overrun)
    mean_margin_cents: float | None  # average headroom; None if zero runs
    danger_rate: float | None  # runs at/above danger_threshold / total; None if zero
    danger_threshold: float
    verdict: str  # healthy_margin | at_stall_risk | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_budget_safety_margin(
    runs: Sequence[tuple[int, int | None]],
    *,
    danger_threshold: float = _DEFAULT_DANGER_THRESHOLD,
) -> BudgetSafetyMarginReport:
    """Measure how close each Midnight-Oil run came to its approved ceiling.

    ``runs`` is a sequence of ``(approved_ceiling_cents, actual_cost_cents)``
    tuples per run. ``actual_cost_cents`` of ``None`` marks an incomplete run
    (excluded from measurement, counted as ``incomplete_count``). Returns a
    :class:`BudgetSafetyMarginReport` with utilization, margin, danger-rate, and
    verdict.

    Raises:
        BudgetSafetyMarginError: if a ceiling is not positive, an actual cost is
            negative, or ``danger_threshold`` is outside the open interval
            (0, 1].
    """
    if not 0.0 < danger_threshold <= 1.0:
        raise BudgetSafetyMarginError(
            "danger_threshold must be in the open-closed interval (0.0, 1.0]; "
            f"got {danger_threshold!r}"
        )

    margins: list[int] = []
    utilizations: list[float] = []
    incomplete = 0
    for ceiling, actual in runs:
        if ceiling <= 0:
            raise BudgetSafetyMarginError(
                f"approved_ceiling_cents must be positive; got {ceiling}"
            )
        if actual is None:
            incomplete += 1
            continue
        if actual < 0:
            raise BudgetSafetyMarginError(
                f"actual_cost_cents must be non-negative; got {actual}"
            )
        margins.append(ceiling - actual)
        utilizations.append(actual / ceiling)

    complete = len(margins)
    if complete == 0:
        return BudgetSafetyMarginReport(
            run_count=0,
            incomplete_count=incomplete,
            mean_utilization=None,
            max_utilization=None,
            min_margin_cents=None,
            mean_margin_cents=None,
            danger_rate=None,
            danger_threshold=danger_threshold,
            verdict="unknown",
            notes=("no complete runs to measure",),
        )

    mean_utilization = sum(utilizations) / complete
    max_utilization = max(utilizations)
    min_margin_cents = min(margins)
    mean_margin_cents = sum(margins) / complete
    danger_count = sum(1 for u in utilizations if u >= danger_threshold)
    danger_rate = danger_count / complete

    if max_utilization >= danger_threshold:
        verdict = "at_stall_risk"
        notes = (
            f"worst-case run utilized {max_utilization:.4f} of its ceiling "
            f"(danger_threshold {danger_threshold:.2f}); {danger_count} of "
            f"{complete} complete run(s) in the danger zone",
        )
    else:
        verdict = "healthy_margin"
        notes = (
            f"every run stayed below the danger threshold "
            f"(max_utilization {max_utilization:.4f} < {danger_threshold:.2f})",
        )

    return BudgetSafetyMarginReport(
        run_count=complete,
        incomplete_count=incomplete,
        mean_utilization=mean_utilization,
        max_utilization=max_utilization,
        min_margin_cents=min_margin_cents,
        mean_margin_cents=mean_margin_cents,
        danger_rate=danger_rate,
        danger_threshold=danger_threshold,
        verdict=verdict,
        notes=notes,
    )
