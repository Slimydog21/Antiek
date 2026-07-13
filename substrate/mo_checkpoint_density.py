r"""Checkpoint density — is the autonomous run's save cadence well-balanced?

Operator vision (ask #13, Midnight Oil): *"...brainstorm and build an autonomous
research sub-agent swarm mode called 'midnight oil' where users can engage in a
deep research without needing to be in the workstation; all they need to do is set
a time of work and goals (and the system provides the user a recommended price
ceiling to approve) then the agent goes off to execute that task."* An unattended
run must be RESILIENT: when it fails or is interrupted mid-flight, it should resume
from the last CHECKPOINT (saved progress snapshot) rather than restart from zero.
The checkpoint CADENCE — how often the run saves — is a planning-quality property
the operator never directly sees but pays for in two opposite failure modes.

**Two opposite failure modes (both cost the operator):**

* **Too SPARSE** (few checkpoints, large gaps between them): high BLAST RADIUS. A
  failure between two widely-spaced checkpoints loses all the work done since the
  last save. A run with one checkpoint at the start that fails at 99% loses 99% of
  the work — the operator pays again for the redo. Fragile.
* **Too DENSE** (checkpoints every tiny step): high BOOKKEEPING OVERHEAD. Saving
  state has a cost (serialization, storage, context churn); checkpointing every 1%
  of progress on a long run spends the budget on bookkeeping rather than research.
  Wasteful.
* **BALANCED**: checkpoints at a sensible cadence that bounds the worst-case blast
  radius without spending the budget on saving. The Goldilocks zone.

**Genuinely distinct from every existing Midnight Oil axis:**

* ``goal_interdependence`` (#1985): goal STRUCTURE (is the goal set schedulable?).
* ``interrupt_resumption`` (#1986): resume CONTINUITY (does a resumed run pick up
  coherently — no gaps, no redone work?). It takes explicit pause/resume SEGMENTS
  and measures whether resume reconnects to where pause left off.
* ``budget_safety_margin`` (#1981) / ``ceiling_accuracy`` (#1968) /
  ``cost_efficiency`` (#1971): cost ECONOMICS (headroom, accuracy, value).
* ``time_adherence``: execution time.
* ``goal_delivery`` (#1938) / ``scope_adherence`` (#1967): FINDINGS outcomes.

NONE measures checkpoint CADENCE — the planned FREQUENCY of save points. This is
independent of resume continuity: a run can checkpoint densely (this axis:
balanced) yet resume with a gap (#1986: skipping — the resume logic dropped work),
OR checkpoint sparsely (this axis: sparse — a failure loses a huge span) yet resume
perfectly (#1986: coherent). #1986 asks "did resume reconnect?"; THIS asks "how
much work was at risk between saves?" A run with perfect contiguous resumption but
a single checkpoint at the start has a 100% blast radius — #1986 says "coherent,"
this says "fragile." Different questions, both load-bearing for unattended trust.

**The measurement (hard to vary).** Given an ordered set of checkpoints each at a
normalized progress in ``[0, 1]`` (fraction of total work completed when saved),
the checkpoints partition the work span ``[0, 1]`` into gaps (spans between
consecutive save points, including the boundaries ``[0, first]`` and
``[last, 1.0]``). Each gap's width IS the blast radius for a failure inside it (the
work that would be lost — unsaved — if the run died mid-gap):

* ``checkpoint_count`` — distinct save points (exact-duplicate progress deduped).
* ``duplicate_checkpoint_count`` — checkpoints at an already-saved progress
  (redundant saves — a bookkeeping-waste signal, surfaced separately).
* ``gaps`` — every partition span, each auditable (its bounding checkpoint ids +
  width). Sorted by start.
* ``max_gap`` — the WORST-CASE blast radius (the largest unprotected span). The
  safety-critical statistic.
* ``mean_gap`` — the average span (the overhead indicator — tiny mean = saves
  constantly). For a full-span partition the gaps always sum to ``1.0``, so
  ``mean_gap == 1.0 / (checkpoint_count + 1)`` exactly — the overhead signal is
  equivalently "how many checkpoints"; carried as a spacing for readability.
* ``min_gap`` — the tightest span.
* ``gap_spread`` — ``max_gap - min_gap`` (evenness — clustered checkpoints have a
  large spread).

**Verdict (distinct honest states, never collapsed):**

* zero checkpoints (no save points recorded at all) -> ``unknown`` (defer — cadence
  is not measurable without checkpoints; never fabricated balanced).
* ``max_gap >= sparse_threshold`` (default ``0.40``) -> ``sparse`` (a single failure
  could lose 40%+ of the work — the run is fragile; blast radius dominates).
* ``mean_gap <= dense_threshold`` (default ``0.02``) -> ``excessive`` (saves so often
  — ~50+ effective checkpoints — that bookkeeping overhead dominates; wasteful).
* otherwise -> ``balanced`` (sensible cadence — bounded blast radius, modest
  overhead). A REAL measured verdict, NOT the default: ``unknown`` means
  nothing-to-measure; ``balanced`` means measured-and-sound. Never collapsed.

When BOTH sparse and excessive trigger (checkpoints clustered in one region leaving
a huge unprotected gap elsewhere), ``sparse`` wins the verdict — blast radius is the
safety-critical concern — but both conditions are carried in ``notes`` so the
consumer sees the clustered shape.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero checkpoints (cadence needs save points to
  measure — defer).
* ``balanced`` is a REAL measured verdict (every gap measured and within bounds),
  NOT the default — ``unknown`` means nothing-to-measure; ``balanced`` means
  measured-and-sound. Never collapsed.
* ``max_gap`` / ``mean_gap`` / ``min_gap`` / ``gap_spread`` are ``None`` when
  ``unknown`` (defer — never ``0.0``).
* exact-duplicate progress checkpoints are deduped (a zero-width gap is not a real
  blast-radius span); the redundancy is carried as ``duplicate_checkpoint_count``.
* progress must be finite in ``[0.0, 1.0]`` (raises on out-of-range / NaN).
* every gap carries its bounding checkpoint ids verbatim (auditable — no black-box
  cadence; the operator can see exactly which spans are unprotected).
* thresholds must be in ``(0.0, 1.0]`` (raises otherwise).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``Checkpoint`` shape; the route layer adapts
  1:1 from the run's checkpoint ledger).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "Checkpoint",
    "CheckpointGap",
    "CheckpointDensityReport",
    "measure_checkpoint_density",
]

_DEFAULT_SPARSE_THRESHOLD = 0.40
_DEFAULT_DENSE_THRESHOLD = 0.02
_WORK_START = 0.0
_WORK_END = 1.0


@dataclass(frozen=True)
class Checkpoint:
    """A single saved progress snapshot in an autonomous run.

    Attributes:
        checkpoint_id: stable identifier (for provenance / audit).
        progress: normalized fraction of total work completed when saved, in
            ``[0.0, 1.0]``.
    """

    checkpoint_id: str
    progress: float


@dataclass(frozen=True)
class CheckpointGap:
    """A span of work between two consecutive save points (or a boundary).

    The width IS the blast radius: the work lost if the run fails inside this span
    (before the next checkpoint saves it).

    Attributes:
        start_progress: inclusive start of the span (the last saved point, or
            ``0.0`` for the leading boundary gap).
        end_progress: exclusive end of the span (the next save point, or ``1.0``
            for the trailing boundary gap).
        width: ``end_progress - start_progress`` (the blast radius).
        preceding_checkpoint_id: id of the checkpoint at ``start_progress``;
            ``None`` for the leading ``[0, first]`` boundary.
        following_checkpoint_id: id of the checkpoint at ``end_progress``;
            ``None`` for the trailing ``[last, 1.0]`` boundary.
    """

    start_progress: float
    end_progress: float
    width: float
    preceding_checkpoint_id: str | None
    following_checkpoint_id: str | None


@dataclass(frozen=True)
class CheckpointDensityReport:
    """The checkpoint-cadence verdict. Advisory, pure.

    Attributes:
        checkpoint_count: distinct save points (deduped).
        duplicate_checkpoint_count: checkpoints at an already-saved progress.
        gaps: every partition span, sorted by start_progress (auditable).
        max_gap: worst-case blast radius; ``None`` when ``unknown``.
        mean_gap: average span; ``None`` when ``unknown``.
        min_gap: tightest span; ``None`` when ``unknown``.
        gap_spread: ``max_gap - min_gap`` (evenness); ``None`` when ``unknown``.
        sparse_threshold: max-gap floor for the ``sparse`` verdict.
        dense_threshold: mean-gap ceiling for the ``excessive`` verdict.
        verdict: ``sparse`` / ``excessive`` / ``balanced`` / ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    checkpoint_count: int
    duplicate_checkpoint_count: int
    gaps: tuple[CheckpointGap, ...]
    max_gap: float | None
    mean_gap: float | None
    min_gap: float | None
    gap_spread: float | None
    sparse_threshold: float
    dense_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_progress(value: float, checkpoint_id: str) -> None:
    if value != value:  # NaN
        raise ValueError(
            f"checkpoint {checkpoint_id!r} progress is NaN"
        )
    if not (_WORK_START <= value <= _WORK_END):
        raise ValueError(
            f"checkpoint {checkpoint_id!r} progress {value} outside [0.0, 1.0]"
        )


def measure_checkpoint_density(
    checkpoints: Sequence[Checkpoint],
    *,
    sparse_threshold: float = _DEFAULT_SPARSE_THRESHOLD,
    dense_threshold: float = _DEFAULT_DENSE_THRESHOLD,
) -> CheckpointDensityReport:
    r"""Measure whether an autonomous run's checkpoint cadence is well-balanced.

    ``checkpoints`` are the run's saved progress snapshots. Returns a
    :class:`CheckpointDensityReport` with the gap structure, blast-radius /
    overhead statistics, and verdict.

    Raises:
        ValueError: if thresholds are outside ``(0.0, 1.0]`` or any checkpoint
            progress is NaN or outside ``[0.0, 1.0]``.
    """
    if not 0.0 < sparse_threshold <= 1.0:
        raise ValueError(
            f"sparse_threshold must be in (0.0, 1.0]; got {sparse_threshold}"
        )
    if not 0.0 < dense_threshold <= 1.0:
        raise ValueError(
            f"dense_threshold must be in (0.0, 1.0]; got {dense_threshold}"
        )

    for cp in checkpoints:
        _validate_progress(cp.progress, cp.checkpoint_id)

    # Dedupe exact-duplicate progress (a zero-width gap is not a real blast-radius
    # span); carry the redundancy as a separate signal.
    seen_progress: dict[float, str] = {}
    duplicate_count = 0
    unique: list[Checkpoint] = []
    for cp in checkpoints:
        if cp.progress in seen_progress:
            duplicate_count += 1
            continue
        seen_progress[cp.progress] = cp.checkpoint_id
        unique.append(cp)

    # Sort by progress (stable on insertion order for ties — already deduped).
    unique.sort(key=lambda c: c.progress)

    if not unique:
        return CheckpointDensityReport(
            checkpoint_count=0,
            duplicate_checkpoint_count=duplicate_count,
            gaps=(),
            max_gap=None,
            mean_gap=None,
            min_gap=None,
            gap_spread=None,
            sparse_threshold=sparse_threshold,
            dense_threshold=dense_threshold,
            verdict="unknown",
            notes=("no checkpoints recorded — cadence not measurable",),
        )

    # Build the partition boundaries: [0.0] + checkpoint progresses + [1.0].
    # Map boundary progress -> checkpoint id (None for the work-span ends).
    bounds: list[tuple[float, str | None]] = [(_WORK_START, None)]
    for cp in unique:
        bounds.append((cp.progress, cp.checkpoint_id))
    bounds.append((_WORK_END, None))

    gaps: list[CheckpointGap] = []
    for idx in range(len(bounds) - 1):
        start_prog, preceding_id = bounds[idx]
        end_prog, following_id = bounds[idx + 1]
        width = end_prog - start_prog
        gaps.append(
            CheckpointGap(
                start_progress=start_prog,
                end_progress=end_prog,
                width=width,
                preceding_checkpoint_id=preceding_id,
                following_checkpoint_id=following_id,
            )
        )

    gap_widths = [g.width for g in gaps]
    max_gap = max(gap_widths)
    min_gap = min(gap_widths)
    mean_gap = sum(gap_widths) / len(gap_widths)
    gap_spread = max_gap - min_gap

    is_sparse = max_gap >= sparse_threshold
    is_excessive = mean_gap <= dense_threshold

    if is_sparse:
        verdict = "sparse"
    elif is_excessive:
        verdict = "excessive"
    else:
        verdict = "balanced"

    note_parts: list[str] = [
        f"{len(unique)} checkpoint(s); max blast-radius gap {max_gap:.4f}",
        f"mean gap {mean_gap:.4f}",
    ]
    if duplicate_count:
        note_parts.append(f"{duplicate_count} redundant duplicate checkpoint(s)")
    if is_sparse and is_excessive:
        note_parts.append(
            "checkpoints clustered: large unprotected gap AND frequent saves"
        )

    return CheckpointDensityReport(
        checkpoint_count=len(unique),
        duplicate_checkpoint_count=duplicate_count,
        gaps=tuple(gaps),
        max_gap=max_gap,
        mean_gap=mean_gap,
        min_gap=min_gap,
        gap_spread=gap_spread,
        sparse_threshold=sparse_threshold,
        dense_threshold=dense_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
