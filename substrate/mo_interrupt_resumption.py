r"""Midnight Oil interrupt resumption — did a paused run resume coherently?

Operator vision (ask #13): *"...set a time of work and goals... then the agent
goes off to execute that task."* An unattended run may span multiple SEGMENTS —
interrupted by rate limits, budget pauses, operator holds, or infrastructure
restarts — then resumed. The trust question for unattended mode: when the run
resumes, does it pick up COHERENTLY from where it paused (contiguous — no work
lost, no work redone), or does it SKIP ahead (a gap — work silently missed) or
REDO work (an overlap — wasted budget re-running a completed phase)?

**Genuinely distinct (different object):**

* ``goal_interdependence`` (#1985): the GOALS-to-GOALS dependency structure
  (assessed before execution — is the goal set schedulable?).
* ``time_adherence`` / ``budget_safety_margin`` (#1981) / ``ceiling_accuracy``
  (#1968): cost/time OUTCOMES (did the run finish within budget?).
* ``goal_delivery`` (#1938) / ``scope_adherence`` (#1967): findings-to-goals
  OUTCOMES (did the run deliver the right things?).
* ``reading_flow_continuity`` (#1983): a READER's positional path through a
  document (the reading surface — a different domain entirely).

ALL of these measure either structure (before execution) or final outcomes (after
execution). NONE measures EXECUTION CONTINUITY across the pause/resume boundary
(during execution, across segments). THIS is that axis: for each interruption, it
checks whether the resumption point matched the pause point. It is the integrity
signal on the pause/resume mechanism itself — a run that silently skips or redoes
work on every resume erodes trust in the unattended execution path.

**The measurement (hard to vary).** Given a chronological sequence of run
segments, each marking the run's normalized progress (``[0, 1]``) at the moment
of PAUSE and the next segment's progress at RESUME (the route layer normalizes
phase-index / findings-produced to a ``[0, 1]`` completion fraction):

For each pause/resume transition:

* ``gap = resume - pause`` (signed: positive = the run RESUMED AHEAD of where it
  paused — work was SKIPPED, the dangerous direction; negative = the run resumed
  BEHIND — work was REDONE, the wasteful direction; zero = PERFECT contiguous
  resumption).
* a transition is a GAP when ``gap > gap_tolerance`` (default 0.0 — any forward
  skip is a gap; boundary inclusive at zero).
* a transition is an OVERLAP when ``gap < -overlap_tolerance`` (default 0.0 — any
  backward redo is an overlap).

Aggregated:

* ``transition_count`` — how many pause/resume transitions were measured.
* ``gap_count`` / ``overlap_count`` — how many transitions skipped / redone work.
* ``perfect_resumption_rate`` — transitions with zero gap / total (contiguous
  resumptions — the trust signal).
* ``mean_gap`` — the average signed gap (positive = systematic skipping; negative
  = systematic redoing; near zero = coherent).
* ``max_gap`` — the worst-case signed gap (largest skip if positive, largest redo
  if negative — the single most damaging transition).

**Verdict (distinct honest states, never collapsed):**

* zero transitions -> ``unknown`` (defer — a single uninterrupted segment has no
  pause/resume boundary to assess; never fabricated).
* ``gap_count >= 1`` -> ``skipping`` (at least one resume skipped work — the
  dangerous signal: the operator may be missing findings).
* ``overlap_count >= 1`` AND ``gap_count == 0`` -> ``redoing`` (at least one resume
  redid work — the wasteful signal: budget spent on duplicate effort).
* all transitions contiguous (``gap_count == 0`` AND ``overlap_count == 0``) ->
  ``coherent`` (every resume matched its pause — a REAL measured verdict, distinct
  from ``unknown``).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates ``coherent`` on no transitions (a run that never
  paused has no resumption to assess — claiming it "resumed coherently" would be
  fabricated).
* ``perfect_resumption_rate`` / ``mean_gap`` / ``max_gap`` are ``None`` when zero
  transitions (defer — never ``0.0``).
* Progress must be finite in ``[0, 1]`` (a completion fraction outside the run is
  a recording error); raises otherwise.
* Resume must be >= 0 and pause must be <= 1 (internal progress is bounded);
  raises otherwise.
* Tolerances must be >= 0 (raises).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``midnight_oil`` package is not on
frozen origin/main. This module takes plain per-segment progress tuples; the route
layer adapts 1:1 from the run-segment ledger's pause/resume checkpoints.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class InterruptResumptionError(ValueError):
    """An interrupt-resumption input violates a load-bearing invariant."""


@dataclass(frozen=True)
class RunSegment:
    """One execution segment of a multi-segment run.

    ``pause_progress`` is the run's normalized completion at the moment this
    segment was interrupted (``[0, 1]``). ``resume_progress`` is where the NEXT
    segment picked up. For the LAST segment, ``resume_progress`` is ``None``
    (no resumption after the final segment).
    """

    segment_id: str
    pause_progress: float
    resume_progress: float | None


@dataclass(frozen=True)
class InterruptResumptionReport:
    """The pause/resume continuity verdict. Advisory, pure."""

    transition_count: int
    gap_count: int
    overlap_count: int
    perfect_resumption_rate: float | None  # contiguous / total; None when unknown
    mean_gap: float | None  # mean(resume - pause); None when unknown
    max_gap: float | None  # worst-case signed gap; None when unknown
    gap_tolerance: float
    overlap_tolerance: float
    verdict: str  # coherent | skipping | redoing | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_progress(value: float, label: str) -> None:
    if math.isnan(value) or math.isinf(value):
        raise InterruptResumptionError(f"{label} must be finite; got {value}")
    if not 0.0 <= value <= 1.0:
        raise InterruptResumptionError(f"{label} must be in [0, 1]; got {value}")


def measure_interrupt_resumption(
    segments: Sequence[RunSegment],
    *,
    gap_tolerance: float = 0.0,
    overlap_tolerance: float = 0.0,
) -> InterruptResumptionReport:
    """Measure whether a multi-segment run resumed coherently across pauses.

    ``segments`` is a chronological sequence of :class:`RunSegment`. For each
    segment with a non-None ``resume_progress``, the transition gap is
    ``resume - pause``. A gap (skip) is ``gap > gap_tolerance``; an overlap (redo)
    is ``gap < -overlap_tolerance``. Returns an
    :class:`InterruptResumptionReport`.

    Raises:
        InterruptResumptionError: if tolerances are negative or any progress value
            is non-finite or outside ``[0, 1]``.
    """
    if gap_tolerance < 0.0:
        raise InterruptResumptionError(
            f"gap_tolerance must be non-negative; got {gap_tolerance}"
        )
    if overlap_tolerance < 0.0:
        raise InterruptResumptionError(
            f"overlap_tolerance must be non-negative; got {overlap_tolerance}"
        )

    gaps: list[float] = []
    gap_count = 0
    overlap_count = 0
    for seg in segments:
        _validate_progress(seg.pause_progress, "pause_progress")
        if seg.resume_progress is None:
            continue
        _validate_progress(seg.resume_progress, "resume_progress")
        gap = seg.resume_progress - seg.pause_progress
        gaps.append(gap)
        if gap > gap_tolerance:
            gap_count += 1
        elif gap < -overlap_tolerance:
            overlap_count += 1

    total = len(gaps)
    if total == 0:
        return InterruptResumptionReport(
            transition_count=0,
            gap_count=0,
            overlap_count=0,
            perfect_resumption_rate=None,
            mean_gap=None,
            max_gap=None,
            gap_tolerance=gap_tolerance,
            overlap_tolerance=overlap_tolerance,
            verdict="unknown",
            notes=("no pause/resume transitions to measure",),
        )

    perfect = total - gap_count - overlap_count
    perfect_rate = perfect / total
    mean_gap = sum(gaps) / total
    max_gap = max(gaps)

    if gap_count >= 1:
        verdict = "skipping"
    elif overlap_count >= 1:
        verdict = "redoing"
    else:
        verdict = "coherent"

    notes = (
        f"{gap_count} gap(s), {overlap_count} overlap(s), {perfect} perfect "
        f"of {total} transition(s)",
    )

    return InterruptResumptionReport(
        transition_count=total,
        gap_count=gap_count,
        overlap_count=overlap_count,
        perfect_resumption_rate=perfect_rate,
        mean_gap=mean_gap,
        max_gap=max_gap,
        gap_tolerance=gap_tolerance,
        overlap_tolerance=overlap_tolerance,
        verdict=verdict,
        notes=notes,
    )
