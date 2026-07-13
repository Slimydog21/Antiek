r"""Antiek-bench task redundancy — do sub-tasks measure distinct capabilities?

Operator vision (ask #11): *"...a benchmark called Antiek-bench... sub-benchmarks
within it of DIFFERENTIATING tasks as the platform expands."* The recursive
benchmark grows sub-tasks over time. A sub-task is only worth keeping if it
DIFFERENTIATES — if it measures a capability the other sub-tasks do not already
cover. Two sub-tasks that perfectly correlate (models who do well on one also do
well on the other) are REDUNDANT: they provide no additional signal about which
model to pick for which task. ``bench_task_redundancy`` detects this so the
recursive rewrite can merge or retire redundant sub-tasks and keep the benchmark
DIFFERENTIATING.

**Genuinely distinct (different question):**

* ``regression_detection`` (#1982): did the rewrite HURT a model on ONE task
  (temporal, same model+task across a rewrite boundary).
* ``model_fit_for_task`` (#1970): was the CHOSEN model the best pick (selection
  quality, one model+task at one moment).
* ``source_diversity`` / ``source_type_coverage`` (#1956/#1979): diversity of
  EVIDENCE SOURCES (arxiv vs substack vs journal), not benchmark TASKS.
* THIS (``bench_task_redundancy``): the INTER-TASK correlation structure — do two
  TASKS measure the same underlying capability (redundant) or distinct ones
  (differentiating)? A META-axis about the benchmark's own task DESIGN.

**The measurement (hard to vary).** Given a benchmark result set — a collection
of ``(model_id, task_id, score)`` triples, scores normalized to ``[0, 1]``:

For every pair of tasks ``(A, B)``: gather the models that have a score for BOTH.
If at least ``min_overlap`` models (default ``3`` — Pearson over two points is
trivially ±1 and carries no real signal) share both tasks, compute the Pearson
correlation over their common-model scores. A pair is REDUNDANT when its absolute
correlation meets or exceeds ``redundancy_threshold`` (default ``0.85`` — strong
agreement: knowing a model's score on A near-perfectly predicts B). ANTI-correlated pairs (models great at A, terrible at B) measure genuinely DIFFERENT capabilities and are kept — only strong POSITIVE agreement is redundancy.

Aggregated:

* ``redundant_pairs`` — flagged task pairs (both task_ids + correlation +
  shared_model_count, auditable).
* ``redundant_task_ids`` — the unique tasks implicated in any redundant pair.
* ``pair_count`` — how many task pairs were computable (enough shared models).
* ``max_correlation`` — the strongest redundancy signal, carried even when
  below threshold (the operator sees the highest agreement regardless).
* ``mean_correlation`` — the typical pairwise agreement.

**Verdict (distinct honest states, never collapsed):**

* zero computable pairs (fewer than two tasks, or no pair with enough shared
  models) -> ``unknown`` (defer — never fabricated; a differentiation verdict on
  no computable pairs would hide an unmeasured structure behind a phony all-clear).
* at least one redundant pair -> ``redundant`` (some sub-tasks do not
  differentiate — the operator MUST see each pair so the rewrite can merge them).
* zero redundant pairs AND at least one computable pair -> ``differentiating``
  (every computable pair measures a distinct capability — a REAL measured verdict,
  distinct from ``unknown``).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates ``differentiating`` on no computable pairs.
* Correlation is ``None`` for a pair when either task has zero variance among the
  shared models (all models scored identically — the task does not differentiate
  AT ALL, a degenerate case; carrying a fabricated ±1 would be dishonest). Such
  a pair is EXCLUDED from ``pair_count`` (deferred, not counted as measured).
* ``max_correlation`` / ``mean_correlation`` are ``None`` when zero
  computable pairs (defer — never ``0.0``).
* Scores must be finite in ``[0, 1]`` (raises otherwise).
* ``min_overlap`` must be >= 2 (raises); ``redundancy_threshold`` in ``(0, 1]``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``antiek_bench`` package is not on
frozen origin/main. This module defines its own ``TaskScore`` input shape; the
route layer adapts 1:1 from the weekly recorder's result matrix.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

_DEFAULT_MIN_OVERLAP: int = 3
_DEFAULT_REDUNDANCY_THRESHOLD: float = 0.85


class TaskRedundancyError(ValueError):
    """A task-redundancy input violates a load-bearing invariant."""


@dataclass(frozen=True)
class TaskScore:
    """One model's normalized score on one benchmark task."""

    model_id: str
    task_id: str
    score: float


@dataclass(frozen=True)
class RedundantTaskPair:
    """One flagged redundant task pair. Auditable."""

    task_a_id: str
    task_b_id: str
    correlation: float  # Pearson r over shared models, in [-1, 1]
    shared_model_count: int


@dataclass(frozen=True)
class TaskRedundancyReport:
    """The benchmark's inter-task differentiation verdict. Advisory, pure."""

    task_count: int
    pair_count: int  # computable pairs (enough shared models + non-zero variance)
    redundant_pairs: tuple[RedundantTaskPair, ...]
    redundant_task_ids: tuple[str, ...]  # sorted unique tasks in any redundant pair
    max_correlation: float | None  # strongest positive agreement; None when zero pairs
    mean_correlation: float | None  # typical pairwise correlation; None when zero pairs
    min_overlap: int
    redundancy_threshold: float
    verdict: str  # differentiating | redundant | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_score(value: float) -> None:
    if math.isnan(value) or math.isinf(value):
        raise TaskRedundancyError(f"score must be finite; got {value}")
    if not 0.0 <= value <= 1.0:
        raise TaskRedundancyError(f"score must be in [0, 1]; got {value}")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation over paired vectors. None if variance is zero."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx == 0.0 or dy == 0.0:
        return None  # zero variance — correlation undefined (degenerate task)
    return num / math.sqrt(dx * dy)


def measure_task_redundancy(
    scores: Sequence[TaskScore],
    *,
    min_overlap: int = _DEFAULT_MIN_OVERLAP,
    redundancy_threshold: float = _DEFAULT_REDUNDANCY_THRESHOLD,
) -> TaskRedundancyReport:
    r"""Measure whether benchmark sub-tasks redundantly measure the same capability.

    ``scores`` is a collection of :class:`TaskScore` (model_id, task_id, score
    normalized to ``[0, 1]``). For each task pair with at least ``min_overlap``
    shared models, computes Pearson correlation; a pair is redundant when
    ``r >= redundancy_threshold`` (strong positive agreement). Returns a :class:`TaskRedundancyReport`.

    Raises:
        TaskRedundancyError: if ``min_overlap < 2``, ``redundancy_threshold``
            outside ``(0, 1]``, or any score is non-finite or outside ``[0, 1]``.
    """
    if min_overlap < 2:
        raise TaskRedundancyError(f"min_overlap must be >= 2; got {min_overlap}")
    if not 0.0 < redundancy_threshold <= 1.0:
        raise TaskRedundancyError(
            "redundancy_threshold must be in (0.0, 1.0]; "
            f"got {redundancy_threshold!r}"
        )

    for s in scores:
        _validate_score(s.score)

    # Group scores by (task_id) -> {model_id: score}
    task_models: dict[str, dict[str, float]] = defaultdict(dict)
    for s in scores:
        task_models[s.task_id][s.model_id] = s.score

    tasks = sorted(task_models)
    correlations: list[float] = []
    redundant_pairs: list[RedundantTaskPair] = []
    redundant_task_ids: set[str] = set()

    for task_a, task_b in combinations(tasks, 2):
        models_a = task_models[task_a]
        models_b = task_models[task_b]
        shared = sorted(set(models_a) & set(models_b))
        if len(shared) < min_overlap:
            continue
        xs = [models_a[m] for m in shared]
        ys = [models_b[m] for m in shared]
        corr = _pearson(xs, ys)
        if corr is None:
            continue  # zero-variance degenerate pair — excluded (deferred)
        correlations.append(corr)
        if corr >= redundancy_threshold:
            redundant_pairs.append(
                RedundantTaskPair(
                    task_a_id=task_a,
                    task_b_id=task_b,
                    correlation=corr,
                    shared_model_count=len(shared),
                )
            )
            redundant_task_ids.add(task_a)
            redundant_task_ids.add(task_b)

    # Sort redundant pairs deterministically (by task_a then task_b)
    redundant_pairs.sort(key=lambda p: (p.task_a_id, p.task_b_id))

    pair_count = len(correlations)
    if pair_count == 0:
        return TaskRedundancyReport(
            task_count=len(tasks),
            pair_count=0,
            redundant_pairs=(),
            redundant_task_ids=(),
            max_correlation=None,
            mean_correlation=None,
            min_overlap=min_overlap,
            redundancy_threshold=redundancy_threshold,
            verdict="unknown",
            notes=("no computable task pairs (insufficient shared models)",),
        )

    max_corr = max(correlations)
    mean_corr = sum(correlations) / pair_count

    if redundant_pairs:
        verdict = "redundant"
        notes = (
            f"{len(redundant_pairs)} of {pair_count} computable pair(s) redundant "
            f"(threshold {redundancy_threshold}); "
            f"{len(redundant_task_ids)} task(s) implicated",
        )
    else:
        verdict = "differentiating"
        notes = (
            f"all {pair_count} computable pair(s) below redundancy threshold "
            f"(max r {max_corr:.4f})",
        )

    return TaskRedundancyReport(
        task_count=len(tasks),
        pair_count=pair_count,
        redundant_pairs=tuple(redundant_pairs),
        redundant_task_ids=tuple(sorted(redundant_task_ids)),
        max_correlation=max_corr,
        mean_correlation=mean_corr,
        min_overlap=min_overlap,
        redundancy_threshold=redundancy_threshold,
        verdict=verdict,
        notes=notes,
    )
