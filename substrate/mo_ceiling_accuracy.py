"""Midnight Oil ceiling accuracy — did the recommended price ceiling match actual cost?

Operator vision (ask #13): *"...the system provides the user a recommended price
ceiling to approve then the agent goes off to execute that task."* The operator
approves a RECOMMENDED ceiling and walks away. The quality of that recommendation
is the trust foundation of unattended mode: a ceiling that systematically
UNDER-estimates means the run hits the cap and stalls with incomplete work (the
operator returns to a half-finished job); a ceiling that systematically
OVER-estimates means the operator approved more budget than needed (harmless to
the work but erodes trust in the recommendation). ``confidence_calibration``
(#1953) measures whether an artifact's confidence LABELS are honest (epistemic,
content domain). ``budget`` projection (#1838/#783) measures whether THIS prompt
will exceed the budget (forward, single-prompt). NEITHER measures whether the
ceiling RECOMMENDATION was historically accurate across runs — the economic
calibration signal that tells the system (and ask #11's learning loop) whether
its cost estimates need recalibration.

**The measurement (hard to vary).** Given a sequence of completed runs, each
with a ``recommended_ceiling_cents`` and an ``actual_cost_cents``:

* ``error = actual - recommended`` per run (signed: positive = under-estimated,
  the run cost MORE than recommended; negative = over-estimated).
* ``mean_bias = mean(error)`` — the systematic direction. Positive bias = the
  recommendation engine consistently UNDER-estimates (the dangerous direction:
  runs stall at the ceiling). Negative = consistently over-estimates.
* ``mean_abs_error = mean(|error|)`` — the average magnitude (direction-agnostic;
  how far off the recommendation is regardless of which way).
* ``within_tolerance_rate = runs within ±tolerance of actual / total`` — the
  fraction of runs where the recommendation was "close enough" (default tolerance
  0.20 = within 20% of actual).
* ``ceiling_hit_rate = runs where actual >= recommended / total`` — the stall
  signal: how often the run exhausted its recommended budget.

The verdict:

* zero runs (or all incomplete) → ``unknown`` (defer, never fabricated).
* ``mean_bias > bias_threshold`` (default > 0, i.e. positive) AND
  ``ceiling_hit_rate >= stall_threshold`` (default 0.50) → ``under_estimating``
  (the dangerous failure: recommendations are too low AND runs are stalling).
* ``mean_bias < -bias_threshold`` → ``over_estimating`` (recommendations are
  consistently too high — erodes trust but does not stall work).
* else → ``well_calibrated`` (recommendations are close to actual, no systematic
  bias).

**Under-estimation is the critical signal (load-bearing).** The operator's
directive — "a recommended price ceiling to approve" — means the recommendation
is a PROMISE: approve this and the work will complete. An under-estimate breaks
that promise: the operator approved in good faith, the run stalled, and the work
is incomplete. An over-estimate keeps the promise (the work completes, just with
budget to spare). So the bias DIRECTION is carried as a signed signal (not just
the magnitude), and ``under_estimating`` requires BOTH a positive bias AND a
meaningful ceiling-hit rate (a positive bias from one outlier run is not a
systematic failure; a positive bias with half the runs stalling IS).

**Honesty rules (load-bearing):**

* ``unknown`` when zero runs (never ``well_calibrated`` — fabricating a verdict
  on no data would hide a non-calibrated recommender behind a phony all-clear).
* ``mean_bias`` / ``mean_abs_error`` / rates are ``None`` when zero runs (defer —
  never ``0.0``).
* Incomplete runs (``actual_cost_cents is None``) are EXCLUDED from all
  calculations (carried as ``incomplete_count``) — a run that didn't finish has
  no actual cost to compare; fabricating one would conflate "didn't finish" with
  "cost X."
* Negative costs raise (a negative cost is a recording error, not input).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``midnight_oil`` package is not on
frozen origin/main. This module takes plain per-run numeric tuples (the route
layer reads the recommended ceiling from the launch brief and the actual cost
from the budget ledger reconciliation).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_TOLERANCE: float = 0.20
_DEFAULT_STALL_THRESHOLD: float = 0.50


class CeilingAccuracyError(ValueError):
    """A ceiling-accuracy input violates a load-bearing invariant."""


@dataclass(frozen=True)
class CeilingAccuracyReport:
    """The recommendation engine's historical calibration profile. Advisory, pure."""

    run_count: int  # completed runs measured
    incomplete_count: int  # runs excluded (no actual cost)
    mean_bias: float | None  # mean(actual - recommended); None if zero runs
    mean_abs_error: float | None  # mean(|actual - recommended|); None if zero runs
    mean_bias_pct: float | None  # mean_bias / mean(recommended); None if zero runs
    within_tolerance_rate: float | None  # runs within tolerance / total; None if zero
    ceiling_hit_rate: float | None  # runs that hit the ceiling / total; None if zero
    tolerance: float
    stall_threshold: float
    verdict: str  # well_calibrated | under_estimating | over_estimating | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_ceiling_accuracy(
    runs: Sequence[tuple[int | None, int | None]],
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
    stall_threshold: float = _DEFAULT_STALL_THRESHOLD,
) -> CeilingAccuracyReport:
    """Measure whether the recommended price ceiling matched actual run costs.

    ``runs`` is a sequence of ``(recommended_ceiling_cents, actual_cost_cents)``
    tuples per completed run. ``actual_cost_cents`` of ``None`` marks an
    incomplete run (excluded from measurement). Returns a
    :class:`CeilingAccuracyReport` with the bias, error magnitude, rates, and
    verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= tolerance <= 1.0:
        raise CeilingAccuracyError(
            f"tolerance must be in [0,1], got {tolerance!r}"
        )
    if not 0.0 <= stall_threshold <= 1.0:
        raise CeilingAccuracyError(
            f"stall_threshold must be in [0,1], got {stall_threshold!r}"
        )

    errors: list[int] = []
    within_tolerance = 0
    ceiling_hits = 0
    incomplete = 0
    recommended_total = 0

    for recommended, actual in runs:
        if recommended is None or recommended < 0:
            raise CeilingAccuracyError(
                f"recommended_ceiling_cents must be a non-negative int, got {recommended!r}"
            )
        if actual is None:
            incomplete += 1
            continue
        if actual < 0:
            raise CeilingAccuracyError(
                f"actual_cost_cents must be non-negative or None, got {actual!r}"
            )
        error = actual - recommended
        errors.append(error)
        recommended_total += recommended
        if recommended > 0 and abs(error) <= recommended * tolerance:
            within_tolerance += 1
        if actual >= recommended:
            ceiling_hits += 1

    run_count = len(errors)
    if run_count == 0:
        return CeilingAccuracyReport(
            run_count=0,
            incomplete_count=incomplete,
            mean_bias=None,
            mean_abs_error=None,
            mean_bias_pct=None,
            within_tolerance_rate=None,
            ceiling_hit_rate=None,
            tolerance=tolerance,
            stall_threshold=stall_threshold,
            verdict="unknown",
            notes=_notes_zero_runs(incomplete, tolerance, stall_threshold),
        )

    mean_bias = sum(errors) / run_count
    mean_abs_error = sum(abs(e) for e in errors) / run_count
    mean_recommended = recommended_total / run_count
    mean_bias_pct = mean_bias / mean_recommended if mean_recommended else None
    within_tolerance_rate = within_tolerance / run_count
    ceiling_hit_rate = ceiling_hits / run_count

    if mean_bias > 0 and ceiling_hit_rate >= stall_threshold:
        verdict = "under_estimating"
    elif mean_bias < 0:
        verdict = "over_estimating"
    else:
        verdict = "well_calibrated"

    notes: list[str] = [
        "ceiling accuracy measures whether the RECOMMENDED price ceiling matched "
        "actual run costs — the recommendation engine's historical calibration "
        "signal; confidence_calibration #1953 checks confidence LABELS (epistemic), "
        "budget projection #1838/#783 checks forward single-prompt projection; THIS "
        "checks whether the ceiling recommendation was historically right",
        "mean_bias = mean(actual - recommended): positive = systematically "
        "under-estimated (the DANGEROUS direction — runs stall at the ceiling with "
        "incomplete work); negative = over-estimated (erodes trust but work completes); "
        "the bias DIRECTION is carried signed because under vs over are asymmetric "
        "failures",
        "under_estimating requires BOTH a positive mean_bias AND ceiling_hit_rate "
        ">= stall_threshold — a positive bias from one outlier is not a systematic "
        "failure, but a positive bias with half the runs stalling IS the dangerous "
        "pattern the operator cannot catch live",
        "unknown when zero completed runs (never fabricated well_calibrated — hides a "
        "non-calibrated recommender behind a phony all-clear); incomplete runs "
        "(actual is None) excluded from all calculations (carried as incomplete_count "
        "— a run that didn't finish has no actual cost to compare); rates None when "
        "zero runs (defer, never 0.0)",
        "within_tolerance_rate = runs within +/- tolerance of actual (default 20%); "
        "ceiling_hit_rate = runs where actual >= recommended (the stall signal); "
        "the operator's 'recommended price ceiling to approve' is a PROMISE — "
        "under-estimation breaks it",
    ]
    bias_str = f"{mean_bias:+.0f} cents"
    bias_pct_str = (
        f"{mean_bias_pct:+.0%}" if mean_bias_pct is not None else "n/a"
    )
    notes.append(
        f"verdict {verdict}: mean_bias {bias_str} ({bias_pct_str} of recommended), "
        f"mean_abs_error {mean_abs_error:.0f} cents, within_tolerance "
        f"{within_tolerance_rate:.0%}, ceiling_hit {ceiling_hit_rate:.0%} over "
        f"{run_count} run(s) ({incomplete} incomplete excluded)"
    )

    return CeilingAccuracyReport(
        run_count=run_count,
        incomplete_count=incomplete,
        mean_bias=mean_bias,
        mean_abs_error=mean_abs_error,
        mean_bias_pct=mean_bias_pct,
        within_tolerance_rate=within_tolerance_rate,
        ceiling_hit_rate=ceiling_hit_rate,
        tolerance=tolerance,
        stall_threshold=stall_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )


def _notes_zero_runs(incomplete: int, tolerance: float, stall_threshold: float) -> tuple[str, ...]:
    """Notes for the zero-completed-runs case."""
    return (
        "ceiling accuracy measures whether the RECOMMENDED price ceiling matched "
        "actual run costs — the recommendation engine's historical calibration "
        "signal; confidence_calibration #1953 checks confidence LABELS (epistemic), "
        "budget projection #1838/#783 checks forward single-prompt projection; THIS "
        "checks whether the ceiling recommendation was historically right",
        "unknown when zero completed runs (never fabricated well_calibrated — hides "
        "a non-calibrated recommender behind a phony all-clear)",
        f"{incomplete} incomplete run(s) excluded (actual cost is None — a run that "
        "didn't finish has no actual cost to compare); tolerance "
        f"{tolerance:.0%}, stall_threshold {stall_threshold:.0%}",
    )
