r"""Bench stability — is the benchmark reproducible across repeat runs?

Operator vision (ask #11, the recursive benchmark): *"...I would like for the
benchmark to be recursive where it learns from usage patterns...I would like to
know on a weekly basis what models are best at what tasks."* A weekly model-ranking
benchmark is only WORTH running if it is REPRODUCIBLE — if the SAME model scored on
the SAME task yields wildly different scores across repeat runs, then the score is
NOISE, not signal. Week-over-week comparisons become meaningless: you cannot tell
whether model X improved or whether its score just bounced. A benchmark that is not
test-retest reliable cannot rank models, cannot detect real regressions, and cannot
feed honest model-selection advice. Reproducibility is the FOUNDATIONAL trust
property — without it every other bench axis is built on sand.

**Genuinely distinct from the entire bench surface:**

* ``task_redundancy`` (#1984): do two TASKS measure the same capability (inter-task
  correlation)?
* ``task_discrimination`` (#1960): does a task SEPARATE models (inter-model score
  spread — are models distinguishable)?
* ``regression_detection`` (#1982): did a rewrite HURT a model over time (temporal,
  same model+task across a benchmark rewrite)?
* ``surface_coverage`` (#1889): does the bench task the platform's new surfaces?

NONE measures WITHIN-PAIR score dispersion — the test-retest reliability question:
for a FIXED (model, task), holding everything constant, do repeat runs AGREE?
Discrimination (#1960) looks ACROSS models on one task (spread between models);
THIS looks ACROSS RUNS of one model+task (spread between repeat measurements).
Orthogonal: a task can perfectly separate models (#1960 high) yet be non-reproducible
(THIS unstable — each model's score bounces run-to-run, so the separation is a
coin-flip artifact). And a task can be perfectly reproducible (THIS stable) yet fail
to discriminate (#1960 low — every model scores the same). Separation and
reproducibility are independent; both must hold for a ranking to be trustworthy.

**The measurement (hard to vary).** Given repeat-run score sets per (model, task)
pair (each set the scores from >= 2 independent runs of that model on that task), for
each pair compute the RANGE of its scores (``max - min``) — the worst-case swing
between runs. Range is the honest reproducibility bound: "the score could land
anywhere in this band on a given run." Pairs with only one run cannot be measured
(single-measurement reproducibility is undefined — fabricating a range of 0 would be
dishonest):

* ``measurable_pair_count`` — pairs with >= ``min_runs`` repeat scores (default 2).
* ``unmeasurable_pair_count`` — pairs with a single run (deferred — never counted as
  stable).
* ``unstable_groups`` — pairs whose range >= ``instability_threshold`` (default
  ``0.10`` — a 10-point swing; auditable: model id + task id + range + run_count +
  min + max — no black-box instability).
* ``max_range`` — the WORST-CASE pair (the least reproducible model+task — the
  safety-critical statistic for "can I trust this comparison").
* ``mean_range`` — the average range across pairs (typical reproducibility).
* ``min_range`` — the tightest pair (most reproducible).

**Verdict (distinct honest states, never collapsed):**

* zero measurable pairs (no pair with >= 2 runs) -> ``unknown`` (defer — test-retest
  reliability needs repeats; never fabricated ``stable``).
* ``unstable_group_count >= 1`` -> ``unstable`` (at least one model+task pair swings
  by >= threshold — the benchmark has a reproducibility problem; even one unstable
  pair is honest to flag because that pair's comparisons are untrustworthy).
* otherwise (every pair range < threshold) -> ``stable`` (all measured model+task
  pairs agree within the threshold — a REAL measured verdict, NOT the default).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates ``stable`` when there are no repeat runs (a single
  measurement has no reproducibility to assess — defer).
* ``stable`` is a REAL measured verdict (every pair measured and within band), NOT
  the default — ``unknown`` means nothing-to-measure; ``stable`` means
  measured-and-reproducible. Never collapsed.
* ``max_range`` / ``mean_range`` / ``min_range`` are ``None`` when ``unknown`` (defer
  — never ``0.0``).
* a single-run pair is ``unmeasurable`` (never counted as stable — range 0 on one
  run is a single point, not reproducibility).
* scores must be finite in ``[0, 1]`` (raises); ``min_runs >= 2`` (raises);
  ``instability_threshold`` in ``(0, 1]`` (raises).
* every unstable pair carries model id + task id + range + run_count + min + max
  verbatim (auditable — the operator sees exactly which model+task is bouncing).
* range sensitivity to run count: a pair measured across MORE runs has more
  opportunity for a wide spread, so pairs with different run counts are not directly
  comparable — ``run_count`` is carried per pair so the consumer can judge (disclosed
  honestly, not hidden).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``RepeatRunSet`` shape; route layer adapts
  1:1 from grouped repeat-run score records).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "RepeatRunSet",
    "UnstablePair",
    "BenchStabilityReport",
    "measure_bench_stability",
]

_DEFAULT_MIN_RUNS = 2
_DEFAULT_INSTABILITY_THRESHOLD = 0.10
_SCORE_FLOOR = 0.0
_SCORE_CEIL = 1.0


@dataclass(frozen=True)
class RepeatRunSet:
    """The repeat-run scores for one (model, task) pair.

    Attributes:
        model_id: the model identifier.
        task_id: the benchmark task identifier.
        scores: independent repeat-run scores for this pair, each in ``[0, 1]``.
    """

    model_id: str
    task_id: str
    scores: tuple[float, ...]


@dataclass(frozen=True)
class UnstablePair:
    """A model+task pair whose repeat-run scores swing beyond the threshold.

    Attributes:
        model_id: the model identifier.
        task_id: the task identifier.
        run_count: number of repeat runs measured.
        range_value: ``max(scores) - min(scores)`` (the worst-case swing).
        min_score: the lowest repeat-run score.
        max_score: the highest repeat-run score.
    """

    model_id: str
    task_id: str
    run_count: int
    range_value: float
    min_score: float
    max_score: float


@dataclass(frozen=True)
class BenchStabilityReport:
    """The bench test-retest-reliability verdict. Advisory, pure.

    Attributes:
        measurable_pair_count: pairs with >= min_runs repeat scores.
        unmeasurable_pair_count: pairs with a single run (deferred).
        unstable_groups: pairs swinging >= instability_threshold, sorted by
            range descending then ids.
        unstable_group_count: len(unstable_groups).
        max_range: worst-case pair range; ``None`` when ``unknown``.
        mean_range: average range across pairs; ``None`` when ``unknown``.
        min_range: tightest pair range; ``None`` when ``unknown``.
        min_runs: the repeat-run floor for measurability.
        instability_threshold: the range floor for an unstable verdict.
        verdict: ``stable`` / ``unstable`` / ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    measurable_pair_count: int
    unmeasurable_pair_count: int
    unstable_groups: tuple[UnstablePair, ...]
    unstable_group_count: int
    max_range: float | None
    mean_range: float | None
    min_range: float | None
    min_runs: int
    instability_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_score(value: float, model_id: str, task_id: str) -> None:
    if value != value:  # NaN
        raise ValueError(
            f"NaN score for model {model_id!r} task {task_id!r}"
        )
    if not (_SCORE_FLOOR <= value <= _SCORE_CEIL):
        raise ValueError(
            f"score {value} for model {model_id!r} task {task_id!r} "
            f"outside [0.0, 1.0]"
        )


def measure_bench_stability(
    run_sets: Sequence[RepeatRunSet],
    *,
    min_runs: int = _DEFAULT_MIN_RUNS,
    instability_threshold: float = _DEFAULT_INSTABILITY_THRESHOLD,
) -> BenchStabilityReport:
    r"""Measure the test-retest reliability of the benchmark across repeat runs.

    ``run_sets`` are the repeat-run score sets per (model, task) pair. Returns a
    :class:`BenchStabilityReport` with per-pair ranges, unstable-pair detection, and
    verdict.

    Raises:
        ValueError: if ``min_runs < 2``, ``instability_threshold`` outside
            ``(0.0, 1.0]``, or any score is NaN or outside ``[0.0, 1.0]``.
    """
    if min_runs < 2:
        raise ValueError(f"min_runs must be >= 2; got {min_runs}")
    if not 0.0 < instability_threshold <= 1.0:
        raise ValueError(
            f"instability_threshold must be in (0.0, 1.0]; "
            f"got {instability_threshold}"
        )

    for rs in run_sets:
        for sc in rs.scores:
            _validate_score(sc, rs.model_id, rs.task_id)

    unstable: list[UnstablePair] = []
    ranges: list[float] = []
    unmeasurable = 0

    for rs in run_sets:
        if len(rs.scores) < min_runs:
            unmeasurable += 1
            continue
        lo = min(rs.scores)
        hi = max(rs.scores)
        rng = hi - lo
        ranges.append(rng)
        if rng >= instability_threshold:
            unstable.append(
                UnstablePair(
                    model_id=rs.model_id,
                    task_id=rs.task_id,
                    run_count=len(rs.scores),
                    range_value=rng,
                    min_score=lo,
                    max_score=hi,
                )
            )

    unstable.sort(
        key=lambda u: (-u.range_value, u.model_id, u.task_id)
    )

    measurable = len(ranges)

    if measurable == 0:
        return BenchStabilityReport(
            measurable_pair_count=0,
            unmeasurable_pair_count=unmeasurable,
            unstable_groups=(),
            unstable_group_count=0,
            max_range=None,
            mean_range=None,
            min_range=None,
            min_runs=min_runs,
            instability_threshold=instability_threshold,
            verdict="unknown",
            notes=("no pairs with enough repeat runs to assess reproducibility",),
        )

    max_range = max(ranges)
    min_range = min(ranges)
    mean_range = sum(ranges) / measurable

    unstable_count = len(unstable)
    verdict = "unstable" if unstable_count >= 1 else "stable"

    note_parts = [
        f"{measurable} measurable pair(s); max range {max_range:.4f}, "
        f"mean {mean_range:.4f}",
    ]
    if unstable_count:
        note_parts.append(
            f"{unstable_count} pair(s) swing >= {instability_threshold:.2f} "
            f"(non-reproducible)"
        )
    if unmeasurable:
        note_parts.append(
            f"{unmeasurable} pair(s) had < {min_runs} runs (unmeasurable)"
        )

    return BenchStabilityReport(
        measurable_pair_count=measurable,
        unmeasurable_pair_count=unmeasurable,
        unstable_groups=tuple(unstable),
        unstable_group_count=unstable_count,
        max_range=max_range,
        mean_range=mean_range,
        min_range=min_range,
        min_runs=min_runs,
        instability_threshold=instability_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
