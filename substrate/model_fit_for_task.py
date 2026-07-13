"""Model-fit-for-task — was the chosen model the best fit for the task?

Operator vision (asks #8/#9/#10): *"a decision tree tab where the model should be
selected"*, *"a choice on what AI model to use as the driver for any given
prompt"*, and the recursive benchmark (ask #11) that *"learns from usage patterns
to understand what worked ... to re-write the benchmark."* The benchmark
measures which models are best at which tasks; this axis closes the loop by
measuring whether an ACTUAL selection leveraged that knowledge — did the operator
(Or the recommender) pick the best model for the task, or leave performance on the
table?

**Genuinely distinct (different object measured):**

* ``task-discrimination`` (bench): does the TASK separate models? (is the
  benchmark task discriminative — do models score differently on it?)
* ``ceiling-accuracy`` (#1968): did the recommended COST ceiling match actual
  cost? (recommendation calibration in the COST domain)
* ``budget projection`` (#budget): will THIS prompt exceed the budget? (forward
  single-prompt cost)
* ``rewrite-quality`` (#1965): did the self-rewrite improve the benchmark?
  (recursion success)
* THIS: was the CHOSEN MODEL the best fit for the task? (selection DECISION
  quality — did the pick leave performance on the table?)

``task-discrimination`` and this axis are complementary, not redundant:
discrimination asks *"does selection matter for this task?"* (variance across
models); this asks *"did you pick well?"* (the chosen model's rank). A
non-discriminative task (all models tied) makes every selection ``optimal_fit``
(honestly — the task does not separate models, so no choice leaves performance on
the table); a discriminative task makes the rank load-bearing.

**The measurement (hard to vary):**

Given a benchmark score table (model, task) -> score in ``[0, 1]``, the chosen
model, and the task:

* filter to models scored for THIS task -> ``scored`` (``n`` models)
* ``best_score`` = max of ``scored``; ``chosen_score`` = the chosen model's score
* ``chosen_rank`` = ``1 + (count of models scoring STRICTLY higher)`` (ties share
  the better rank — standard "min" competition ranking)
* ``rank_ratio = (n - chosen_rank) / (n - 1)`` in ``[0, 1]`` (``1.0`` = best,
  ``0.0`` = worst) — direction-normalized so it is comparable across tasks with
  different model counts
* ``relative_gap = (best_score - chosen_score) / best_score`` in ``[0, 1]``
  (``0`` = best) — the share of peak performance the pick leaves on the table

**Verdict:**

* ``optimal_fit`` — ``chosen_score == best_score`` (the pick is AT the top; ties
  count — a model tied for best IS optimal)
* ``near_optimal`` — ``relative_gap <= tolerance`` (default ``0.10`` — within 10%
  of peak; the boundary is inclusive: a pick exactly at the tolerance band edge
  counts as near-optimal)
* ``suboptimal_fit`` — ``relative_gap > tolerance`` (the pick leaves meaningful
  performance on the table)
* ``unknown`` — no comparison possible (zero models scored for the task, the
  chosen model unbenchmarked for the task, a single scored model with no peer, or
  ``best_score == 0`` — no model demonstrates competence so "best fit" is vacuous)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict when the comparison set is empty or the
  chosen model is unmeasured — defer rather than assert.
* ties at the top are ``optimal_fit`` (a model tied for best IS optimal — never
  downgraded for an unbroken tie).
* scores must be in ``[0, 1]``; out-of-range raises (a recording error, not an
  input). A duplicate score for the same (model, task) raises (ambiguous data).
* ``relative_gap`` is ``None`` when ``best_score == 0`` (division by zero — defer,
  never fabricate) or when the comparison set is too small to rank.
* ``rank_ratio`` / ``chosen_rank`` are ``None`` when ``n < 2`` (a single model
  cannot be ranked against itself).
* ``best_score == 0`` -> ``unknown`` (no competent baseline — vacuous to call a
  pick "optimal" at a task no model can do).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``ModelTaskScore`` input
shape (the route layer adapts 1:1 from ``antiek_bench``'s real score table, which
is NOT on frozen main). Pure-Python: stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_TOLERANCE: float = 0.10


@dataclass(frozen=True)
class ModelTaskScore:
    """One model's measured benchmark score for one task. Pure input."""

    model_id: str
    task_id: str
    score: float  # in [0, 1]


@dataclass(frozen=True)
class ModelFitReport:
    """The model-fit-for-task verdict. Advisory, pure."""

    task_id: str
    chosen_model: str
    chosen_score: float | None  # None if chosen model unbenchmarked for task
    best_score: float | None  # None if no models scored for task
    scored_model_count: int  # models scored for this task (0 if none)
    chosen_rank: int | None  # 1-based, 1=best; None if unbenchmarked or n<2
    rank_ratio: float | None  # (n-rank)/(n-1), 1.0=best; None if n<2/unbenchmarked
    relative_gap: float | None  # (best-chosen)/best, 0=best; None if best==0/unmeasurable
    tolerance: float
    verdict: str  # optimal_fit | near_optimal | suboptimal_fit | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


class ModelFitError(ValueError):
    """A model-fit input violates a load-bearing invariant."""


def measure_model_fit_for_task(
    chosen_model: str,
    task_id: str,
    scores: Sequence[ModelTaskScore],
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
) -> ModelFitReport:
    """Measure whether the chosen model is the best fit for the task.

    ``chosen_model`` is the model that was (or will be) selected.
    ``task_id`` is the task the selection serves.
    ``scores`` is the benchmark score table (any tasks; filtered to ``task_id``).
    ``tolerance`` is the near-optimal band as a fraction of peak (default 0.10).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not chosen_model.strip():
        raise ModelFitError("chosen_model must be non-empty")
    if not task_id.strip():
        raise ModelFitError("task_id must be non-empty")
    if not 0.0 <= tolerance <= 1.0:
        raise ModelFitError(f"tolerance must be in [0,1], got {tolerance!r}")

    # Validate every passed score (a malformed score anywhere is a recording error).
    for row in scores:
        if not row.model_id.strip():
            raise ModelFitError(f"model_id must be non-empty, got {row.model_id!r}")
        if not row.task_id.strip():
            raise ModelFitError(f"task_id must be non-empty, got {row.task_id!r}")
        if not 0.0 <= row.score <= 1.0:
            raise ModelFitError(
                f"score for {row.model_id!r}/{row.task_id!r} must be in [0,1], "
                f"got {row.score!r}"
            )

    # Filter to this task; detect a duplicate (model, task) score (ambiguous data).
    scored: dict[str, float] = {}
    for row in scores:
        if row.task_id != task_id:
            continue
        if row.model_id in scored:
            raise ModelFitError(
                f"duplicate score for model {row.model_id!r} on task {task_id!r}"
            )
        scored[row.model_id] = row.score

    n = len(scored)
    hedge = (tolerance,)

    if n == 0:
        return _unknown_report(
            chosen_model,
            task_id,
            None,
            None,
            0,
            hedge,
            "no models scored for this task — defer, never fabricate a fit verdict",
        )

    best_score = max(scored.values())
    chosen_score: float | None = scored.get(chosen_model)

    # Chosen model unbenchmarked for this task — we cannot rank an unmeasured pick.
    if chosen_score is None:
        return _unknown_report(
            chosen_model,
            task_id,
            None,
            best_score,
            n,
            hedge,
            f"chosen model {chosen_model!r} has no measured score for task "
            f"{task_id!r} — defer, never fabricate a fit verdict",
        )

    # No competent baseline — every model scores 0; "best fit" is vacuous.
    if best_score == 0.0:
        return _unknown_report(
            chosen_model,
            task_id,
            chosen_score,
            best_score,
            n,
            hedge,
            "best_score is 0.0 — no model demonstrates competence; best-fit is "
            "vacuous (defer, never fabricate optimal_fit at a task no model can do)",
        )

    # Single scored model — no peer to rank against.
    if n < 2:
        return _unknown_report(
            chosen_model,
            task_id,
            chosen_score,
            best_score,
            n,
            hedge,
            "only one model scored for this task — no comparison set; rank/gap are "
            "vacuous (defer, never fabricate optimal_fit from a set of one)",
        )

    # Comparison set is valid (n >= 2, best_score > 0, chosen is scored).
    strictly_greater = sum(1 for value in scored.values() if value > chosen_score)
    chosen_rank = 1 + strictly_greater
    rank_ratio = (n - chosen_rank) / (n - 1)
    relative_gap = (best_score - chosen_score) / best_score

    if relative_gap == 0.0:
        verdict = "optimal_fit"
    elif relative_gap <= tolerance:
        verdict = "near_optimal"
    else:
        verdict = "suboptimal_fit"

    notes: list[str] = [
        "model-fit-for-task measures whether the CHOSEN MODEL is the best fit for "
        "the task (selection DECISION quality); task-discrimination checks whether "
        "the TASK separates models (does selection matter?), ceiling-accuracy "
        "checks COST-ceiling calibration, budget-projection checks forward cost — "
        "none measure whether the model pick left performance on the table",
        "rank_ratio = (n - chosen_rank)/(n - 1) direction-normalized in [0,1] "
        "(1.0=best, 0.0=worst); relative_gap = (best-chosen)/best in [0,1] "
        "(0=best) — the share of peak performance the pick leaves on the table",
        "verdict: optimal_fit (chosen AT the top, ties count — a model tied for "
        "best IS optimal), near_optimal (relative_gap <= tolerance), suboptimal_fit "
        "(relative_gap > tolerance — meaningful performance left on the table)",
        "ties share the better rank (min competition ranking: rank = 1 + count of "
        "STRICTLY higher scores); a non-discriminative task (all models tied) makes "
        "every pick optimal_fit honestly (the task does not separate models)",
        "unknown when: zero scored models, chosen unbenchmarked, single scored "
        "model (no peer), or best_score==0 (no competent baseline) — defer, never "
        "fabricate; scores out of [0,1] and duplicate (model,task) scores raise",
    ]
    notes.append(
        f"verdict {verdict}: chosen {chosen_model!r} scores {chosen_score:.3f} "
        f"on {task_id!r}, rank {chosen_rank} of {n}, rank_ratio {rank_ratio:.3f}, "
        f"relative_gap {relative_gap:.3f}, tolerance {tolerance:.0%}, "
        f"best_score {best_score:.3f}"
    )

    return ModelFitReport(
        task_id=task_id,
        chosen_model=chosen_model,
        chosen_score=chosen_score,
        best_score=best_score,
        scored_model_count=n,
        chosen_rank=chosen_rank,
        rank_ratio=rank_ratio,
        relative_gap=relative_gap,
        tolerance=tolerance,
        verdict=verdict,
        notes=tuple(notes),
    )


def _unknown_report(
    chosen_model: str,
    task_id: str,
    chosen_score: float | None,
    best_score: float | None,
    n: int,
    tolerance_hedge: tuple[float, ...],
    reason: str,
) -> ModelFitReport:
    notes: list[str] = [
        "model-fit-for-task measures whether the CHOSEN MODEL is the best fit for "
        "the task (selection DECISION quality); distinct from task-discrimination "
        "(does the task separate models?), ceiling-accuracy (cost calibration), "
        "and budget-projection (forward cost)",
        "verdict unknown — comparison metrics are None (defer, never fabricated); "
        "a fit verdict requires n>=2 scored models AND a measured chosen-model "
        "score AND best_score>0",
        reason,
    ]
    return ModelFitReport(
        task_id=task_id,
        chosen_model=chosen_model,
        chosen_score=chosen_score,
        best_score=best_score,
        scored_model_count=n,
        chosen_rank=None,
        rank_ratio=None,
        relative_gap=None,
        tolerance=tolerance_hedge[0],
        verdict="unknown",
        notes=tuple(notes),
    )
