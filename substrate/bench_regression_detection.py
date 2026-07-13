r"""Antiek-bench regression detection — did a recursive rewrite hurt a model?

Operator vision (ask #11): *"...a benchmark called Antiek-bench that benchmarked
performance... the benchmark to be recursive where it learns from usage patterns
to understand what worked and what didn't in a given week to RE-WRITE the
benchmark (and sub-benchmarks within it of differentiating tasks)."* The
recursive rewrite is the engine's strength — it adapts to real usage — but it is
also an unguarded failure mode: a rewrite can change a task's definition or
scoring in a way that silently makes a previously-strong model score WORSE, and
without a guardrail the operator cannot tell a real capability change from
benchmark-definition drift. ``bench_regression_detection`` is that guardrail.

**Genuinely distinct (different question):**

* ``model_fit_for_task`` (#1970): was the CHOSEN model the best pick for a task
  (per-task selection QUALITY, a spatial/cross-model comparison at one moment).
* the bench recorder / scorer / weekly runner (#1828-#1832): they MEASURE and
  RECORD benchmark runs (the data path).
* THIS (``bench_regression_detection``): did the rewrite HURT anyone — a TEMPORAL
  comparison of the same (model, task) score ACROSS a rewrite boundary. It is the
  safety axis on the recursive rewrite itself; none of the above ask it.

Selection quality, measurement, and rewrite-safety are three different questions.
A model can be the best fit (#1970), measured correctly (recorder), and STILL
regress under a rewrite (this axis flags it so the rewrite can be rolled back or
repaired before the operator trusts the new weekly leaderboard).

**The measurement (hard to vary).** Given a sequence of score transitions — each
one the SAME (model, task) measured under the PRIOR benchmark version and the
CURRENT (just-rewritten) version, scores normalized to ``[0, 1]``:

* ``delta = current - prior`` per transition (signed: positive = the rewrite
  improved that pair, negative = it hurt).
* a transition is a REGRESSION when the drop STRICTLY exceeds ``tolerance``:
  ``prior - current > tolerance`` (i.e. ``delta < -tolerance``). A drop exactly
  at tolerance is within-tolerance noise, NOT a regression (boundary: only drops
  BEYOND the line count — a detector that flags noise as regression cries wolf).

Aggregated:

* ``regression_count`` / ``regression_rate`` — how many pairs regressed.
* ``mean_delta`` — the systematic direction (positive = the rewrite helped on
  average; near zero = held; negative = it hurt on average).
* ``worst_transition_delta`` — the smallest (most negative) delta, the single
  largest decrease; positive when every transition improved.
* ``regressed_models`` / ``regressed_tasks`` — the unique models and tasks
  implicated in at least one regression (two slicings of the same failures: did
  the rewrite hurt one model across the board, or make one task harder for
  everyone?).

**Verdict (distinct honest states, never collapsed):**

* zero transitions -> ``unknown`` (defer — never fabricated; a verdict on no data
  would hide an unguarded rewrite behind a phony all-clear).
* ``regression_count >= 1`` -> ``regressing`` (at least one model-task dropped
  beyond tolerance — the operator MUST see each one). The rate and regressed sets
  convey severity without a second verdict bucket.
* ``regression_count == 0`` -> ``held`` (every pair within tolerance or improved —
  a REAL measured verdict, distinct from ``unknown``).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates ``held`` on no data.
* ``regression_rate`` / ``mean_delta`` / ``worst_transition_delta`` are ``None``
  when zero transitions (defer — never ``0.0``).
* Scores must be finite and in ``[0, 1]`` (a normalized benchmark score outside
  that range is a recording error); raises otherwise. The route layer normalizes
  each task's raw score by its max before calling.
* ``tolerance`` must be non-negative (``>= 0``); raises otherwise.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``antiek_bench`` package is not on
frozen origin/main (varying ``__init__.py`` would cause add/add collisions). This
module defines its own ``ScoreTransition`` input shape; the route layer adapts
1:1 from the weekly recorder's before/after score pairs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class RegressionDetectionError(ValueError):
    """A regression-detection input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ScoreTransition:
    """One (model, task) score measured across a benchmark-rewrite boundary.

    ``prior_score`` is the score under the previous benchmark version;
    ``current_score`` is the score under the just-rewritten version. Both are
    normalized to ``[0, 1]`` by the route layer.
    """

    model_id: str
    task_id: str
    prior_score: float
    current_score: float


@dataclass(frozen=True)
class RegressionReport:
    """The recursive-rewrite guardrail verdict. Advisory, pure."""

    transition_count: int
    regression_count: int
    regression_rate: float | None  # regressions / transitions; None when unknown
    mean_delta: float | None  # mean(current - prior); None when unknown
    worst_transition_delta: float | None  # min(current - prior); None when unknown
    regressed_models: tuple[str, ...]  # sorted unique model_ids with >=1 regression
    regressed_tasks: tuple[str, ...]  # sorted unique task_ids with >=1 regression
    tolerance: float
    verdict: str  # held | regressing | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_score(value: float, label: str) -> None:
    if math.isnan(value) or math.isinf(value):
        raise RegressionDetectionError(f"{label} must be finite; got {value}")
    if not 0.0 <= value <= 1.0:
        raise RegressionDetectionError(f"{label} must be in [0, 1]; got {value}")


def measure_regression(
    transitions: Sequence[ScoreTransition],
    *,
    tolerance: float = 0.05,
) -> RegressionReport:
    """Detect whether a recursive benchmark rewrite regressed any model-task pair.

    ``transitions`` is a sequence of :class:`ScoreTransition` (same model+task,
    prior-version vs current-version score, normalized to ``[0, 1]``). A pair
    regresses when its drop strictly exceeds ``tolerance`` (default 0.05). Returns
    a :class:`RegressionReport`.

    Raises:
        RegressionDetectionError: if ``tolerance`` is negative or any score is
            non-finite or outside ``[0, 1]``.
    """
    if tolerance < 0.0:
        raise RegressionDetectionError(
            f"tolerance must be non-negative; got {tolerance}"
        )

    deltas: list[float] = []
    regressed_models: set[str] = set()
    regressed_tasks: set[str] = set()
    for t in transitions:
        _validate_score(t.prior_score, "prior_score")
        _validate_score(t.current_score, "current_score")
        delta = t.current_score - t.prior_score
        deltas.append(delta)
        if t.prior_score - t.current_score > tolerance:
            regressed_models.add(t.model_id)
            regressed_tasks.add(t.task_id)

    total = len(deltas)
    if total == 0:
        return RegressionReport(
            transition_count=0,
            regression_count=0,
            regression_rate=None,
            mean_delta=None,
            worst_transition_delta=None,
            regressed_models=(),
            regressed_tasks=(),
            tolerance=tolerance,
            verdict="unknown",
            notes=("no transitions to measure",),
        )

    # Count regressing PAIRS (a model can regress on several tasks).
    regression_count = sum(
        1
        for t in transitions
        if t.prior_score - t.current_score > tolerance
    )
    rate = regression_count / total
    mean_delta = sum(deltas) / total
    worst = min(deltas)

    if regression_count >= 1:
        verdict = "regressing"
        notes = (
            f"{regression_count} of {total} transition(s) regressed beyond "
            f"tolerance {tolerance} (rate {rate:.4f}); "
            f"{len(regressed_models)} model(s), {len(regressed_tasks)} task(s)",
        )
    else:
        verdict = "held"
        notes = (
            f"all {total} transition(s) within tolerance {tolerance} "
            f"(worst delta {worst:.4f})",
        )

    return RegressionReport(
        transition_count=total,
        regression_count=regression_count,
        regression_rate=rate,
        mean_delta=mean_delta,
        worst_transition_delta=worst,
        regressed_models=tuple(sorted(regressed_models)),
        regressed_tasks=tuple(sorted(regressed_tasks)),
        tolerance=tolerance,
        verdict=verdict,
        notes=notes,
    )
