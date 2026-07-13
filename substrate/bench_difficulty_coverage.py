r"""Bench difficulty coverage — does the benchmark span the difficulty spectrum?

Operator vision (ask #11, the recursive benchmark): *"...I would like to know on a
weekly basis what models are best at what tasks..."* and *"...sub-benchmarks within
it of differentiating tasks as the platform expands..."* To know what models are best
at WHAT tasks, the benchmark must span the full difficulty spectrum — it needs EASY
tasks (where weak models succeed, establishing a floor), MEDIUM tasks (where the
real comparison happens), and HARD tasks (where only frontier models succeed,
establishing the ceiling). A benchmark whose tasks all cluster at one difficulty
tier is BLIND to the others: if every task is hard (every model scores ~0.2), you
cannot tell which model is best at medium tasks; if every task is easy (every model
scores ~0.8), you cannot distinguish models at the capability frontier. Difficulty
coverage is the SPECTRUM-spanning property — does the benchmark probe the full range,
or stare at one band?

**Task difficulty is measured INVERSELY via mean model score:** a task where models
score LOW is HARD (few can do it); a task where models score HIGH is EASY (most can).
The per-task mean score IS the difficulty signal, inverted: difficulty = 1 − mean.
So task-difficulty-coverage measures the SPREAD of per-task mean-scores across the
``[0, 1]`` spectrum — do the means span the range (good coverage) or cluster at one
tier (narrow band)?

**Genuinely distinct from the entire bench surface:**

* ``task_discrimination`` (#1960): does a task SEPARATE models (inter-MODEL score
  spread on ONE task — the variance across models). Single-task variance.
* ``bench_stability`` (#1994): is a task REPRODUCIBLE (inter-RUN spread of one
  model+task — test-retest reliability). Single-pair variance.
* ``task_redundancy`` (#1984): do two TASKS measure the same capability (inter-task
  correlation). Pairwise task relationship.
* ``regression_detection`` (#1982): did a rewrite HURT a model (temporal).
* ``surface_coverage`` (#1889): does the bench task new platform surfaces.

NONE measures the DIFFICULTY-SPECTRUM coverage — the spread of per-task MEAN scores
across ``[0, 1]``. Discrimination (#1960) looks WITHIN one task (variance across
models); THIS looks ACROSS tasks (spread of each task's mean). Orthogonal: a task can
perfectly separate models (#1960 high) yet sit at the same difficulty as every other
task (THIS narrow — all tasks medium-hard); a benchmark can span the full difficulty
spectrum (THIS broad) yet have every task be a weak discriminator (#1960 low — every
model scores the same on each). Separation and spectrum-spanning are independent;
both must hold for a benchmark to tell you what models are best at what difficulty.

**The measurement (hard to vary).** Given each task's mean model score (the route
layer computes the mean of all model scores on that task), invert to difficulty
(``difficulty = 1.0 − mean_score``) and measure the spectrum coverage:

* ``task_count`` — tasks with a computable mean.
* ``difficulty_min`` / ``difficulty_max`` — the easiest and hardest tasks (the
  spectrum EXTENT — how wide a band the benchmark probes).
* ``difficulty_span`` — ``max - min`` (the width of the probed band; ``0.0`` means
  every task is the same difficulty).
* ``mean_difficulty`` — the average task difficulty (is the benchmark centered, or
  skewed easy/hard?).
* ``difficulty_spread`` — the standard deviation of task difficulties (are tasks
  clustered at one tier or spread across tiers? a complement to span).
* ``band_counts`` — how many tasks fall in each difficulty BAND (easy / medium /
  hard / frontier), auditable (the operator sees the spectrum shape — no black-box).
* ``empty_bands`` — difficulty bands with zero tasks (the BLIND SPOTS — tiers the
  benchmark cannot probe).

**Verdict (distinct honest states, never collapsed):**

* zero tasks (no computable means) -> ``unknown`` (defer — spectrum needs tasks;
  never fabricated ``broad``).
* one task -> ``single_task`` (one point has no spectrum to span — honest base case,
  distinct from ``unknown``).
* ``difficulty_span < narrow_span`` (default ``0.20``) -> ``narrow_band`` (tasks
  cluster at one tier — the benchmark is blind to other difficulties; the failure
  mode).
* ``empty_band_count >= 1`` AND ``difficulty_span >= narrow_span`` -> ``partial_coverage``
  (spans a band but leaves a blind spot — e.g., covers easy+medium but no hard tasks;
  the frontier is untested).
* otherwise (spans a wide band with every tier represented) -> ``broad_spectrum``
  (probes the full range — every difficulty tier has at least one task; a REAL
  measured verdict, NOT the default).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates ``broad_spectrum`` when there are no tasks (a spectrum
  needs points to span).
* ``single_task`` is its own base case (one difficulty point has no spread — never
  fabricated as ``narrow_band`` which implies a spread to measure, or
  ``broad_spectrum``).
* ``broad_spectrum`` is a REAL measured verdict (every tier represented, wide span),
  NOT the default — ``unknown`` and ``single_task`` are the defer states. Never
  collapsed.
* ``difficulty_spread`` / ``mean_difficulty`` / ``difficulty_span`` are ``None`` when
  ``unknown`` (defer — never ``0.0``).
* band counts carried verbatim in ``band_counts`` (auditable — the operator sees the
  exact spectrum shape); empty bands surfaced as ``empty_bands`` (the blind spots).
* scores must be finite in ``[0, 1]`` (raises); ``narrow_span`` in ``[0, 1]`` (raises).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted, reproducible output).
* import-free of off-main siblings (own ``TaskMeanScore`` shape; route layer adapts
  1:1 from the weekly recorder's per-task mean).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TaskMeanScore",
    "DifficultyCoverageReport",
    "measure_difficulty_coverage",
]

_DEFAULT_NARROW_SPAN = 0.20
_SCORE_FLOOR = 0.0
_SCORE_CEIL = 1.0

# Difficulty bands (difficulty = 1 - mean_score, so high difficulty = hard).
# easy: difficulty < 0.33 (models score > 0.67).
# medium: 0.33 <= difficulty < 0.67.
# hard: 0.67 <= difficulty < 0.85.
# frontier: difficulty >= 0.85 (models score < 0.15 — only frontier succeeds).
_BAND_FLOORS = (
    ("easy", 0.0, 0.33),
    ("medium", 0.33, 0.67),
    ("hard", 0.67, 0.85),
    ("frontier", 0.85, 1.0 + 1e-9),
)
_BAND_NAMES = tuple(name for name, _, _ in _BAND_FLOORS)


@dataclass(frozen=True)
class TaskMeanScore:
    """A task and its mean model score (the inverse-difficulty signal).

    Attributes:
        task_id: the benchmark task identifier.
        mean_score: the mean of all model scores on this task, in ``[0.0, 1.0]``.
            HIGH mean = easy task; LOW mean = hard task.
    """

    task_id: str
    mean_score: float


@dataclass(frozen=True)
class DifficultyCoverageReport:
    """The benchmark difficulty-spectrum-coverage verdict. Advisory, pure.

    Attributes:
        task_count: tasks with a computable mean.
        difficulty_min: easiest task's difficulty (1 - max mean); ``None`` when
            ``unknown``.
        difficulty_max: hardest task's difficulty (1 - min mean); ``None`` when
            ``unknown``.
        difficulty_span: ``max - min``; ``None`` when ``unknown``.
        mean_difficulty: average task difficulty; ``None`` when ``unknown``.
        difficulty_spread: std dev of difficulties; ``None`` when ``unknown``.
        band_counts: tasks per difficulty band (easy/medium/hard/frontier).
        empty_bands: bands with zero tasks, in band order.
        empty_band_count: len(empty_bands).
        narrow_span: the span floor for ``narrow_band``.
        verdict: ``broad_spectrum`` / ``partial_coverage`` / ``narrow_band`` /
            ``single_task`` / ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    task_count: int
    difficulty_min: float | None
    difficulty_max: float | None
    difficulty_span: float | None
    mean_difficulty: float | None
    difficulty_spread: float | None
    band_counts: dict[str, int]
    empty_bands: tuple[str, ...]
    empty_band_count: int
    narrow_span: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_score(value: float, task_id: str) -> None:
    if value != value:  # NaN
        raise ValueError(f"NaN mean score for task {task_id!r}")
    if not (_SCORE_FLOOR <= value <= _SCORE_CEIL):
        raise ValueError(
            f"mean score {value} for task {task_id!r} outside [0.0, 1.0]"
        )


def _band_for(difficulty: float) -> str:
    for name, lo, hi in _BAND_FLOORS:
        if lo <= difficulty < hi:
            return name
    # difficulty could be exactly 1.0 — frontier covers [0.85, 1.0+eps].
    return "frontier"


def measure_difficulty_coverage(
    task_means: Sequence[TaskMeanScore],
    *,
    narrow_span: float = _DEFAULT_NARROW_SPAN,
) -> DifficultyCoverageReport:
    r"""Measure whether the benchmark spans the difficulty spectrum.

    ``task_means`` are each task's mean model score. Returns a
    :class:`DifficultyCoverageReport` with difficulty-span statistics, band counts,
    and verdict.

    Raises:
        ValueError: if ``narrow_span`` is outside ``[0.0, 1.0]`` or any mean score
            is NaN or outside ``[0.0, 1.0]``.
    """
    if not 0.0 <= narrow_span <= 1.0:
        raise ValueError(f"narrow_span must be in [0.0, 1.0]; got {narrow_span}")

    for tm in task_means:
        _validate_score(tm.mean_score, tm.task_id)

    task_count = len(task_means)

    if task_count == 0:
        return DifficultyCoverageReport(
            task_count=0,
            difficulty_min=None,
            difficulty_max=None,
            difficulty_span=None,
            mean_difficulty=None,
            difficulty_spread=None,
            band_counts={name: 0 for name in _BAND_NAMES},
            empty_bands=_BAND_NAMES,
            empty_band_count=len(_BAND_NAMES),
            narrow_span=narrow_span,
            verdict="unknown",
            notes=("no tasks with computable means",),
        )

    # difficulty = 1 - mean_score (high mean = easy = low difficulty).
    difficulties = [1.0 - tm.mean_score for tm in task_means]

    difficulty_min = min(difficulties)
    difficulty_max = max(difficulties)
    difficulty_span = difficulty_max - difficulty_min
    mean_difficulty = sum(difficulties) / task_count

    if task_count >= 2:
        variance = sum((d - mean_difficulty) ** 2 for d in difficulties) / task_count
        difficulty_spread = math.sqrt(variance)
    else:
        difficulty_spread = 0.0

    band_counts: dict[str, int] = {name: 0 for name in _BAND_NAMES}
    for d in difficulties:
        band_counts[_band_for(d)] += 1
    empty_bands = tuple(name for name in _BAND_NAMES if band_counts[name] == 0)
    empty_band_count = len(empty_bands)

    note_parts = [
        f"{task_count} task(s); difficulty span {difficulty_span:.4f} "
        f"(min {difficulty_min:.2f}, max {difficulty_max:.2f})",
    ]
    bands_summary = ", ".join(f"{n}={band_counts[n]}" for n in _BAND_NAMES)
    note_parts.append(f"bands: {bands_summary}")

    if task_count == 1:
        verdict = "single_task"
    elif difficulty_span < narrow_span:
        verdict = "narrow_band"
        note_parts.append("tasks cluster at one difficulty tier")
    elif empty_band_count >= 1:
        verdict = "partial_coverage"
        note_parts.append(
            f"blind spot(s): {', '.join(empty_bands)}"
        )
    else:
        verdict = "broad_spectrum"

    return DifficultyCoverageReport(
        task_count=task_count,
        difficulty_min=difficulty_min,
        difficulty_max=difficulty_max,
        difficulty_span=difficulty_span,
        mean_difficulty=mean_difficulty,
        difficulty_spread=difficulty_spread,
        band_counts=band_counts,
        empty_bands=empty_bands,
        empty_band_count=empty_band_count,
        narrow_span=narrow_span,
        verdict=verdict,
        notes=tuple(note_parts),
    )
