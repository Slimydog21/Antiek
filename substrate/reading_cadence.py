"""Reading cadence axis — is the reader's within-session rhythm steady or bursty?

The reading surface measures annotation density, passage coverage, flow continuity (direction of
position steps), engagement distribution, cross-session re-engagement, and highlight topology —
all SPATIAL / directional / textual dimensions. THIS axis is the missing **temporal** dimension:
the RHYTHM of reading events within a single session. Are the reader's events (highlights,
checkpoints, page-turns) evenly spaced in time (a metronomic sip) or clustered into bursts
separated by long pauses (a binge-then-pause shape)?

Measured via the **burstiness parameter** ``B = (gap_std - gap_mean) / (gap_std + gap_mean)`` in
``[-1, 1]`` — the network-science burstiness coefficient, baselined against a Poisson (random)
event process:

* ``B = -1`` — perfectly regular timing (a metronome; gap_std = 0).
* ``B ~= 0`` — random / memoryless timing (Poisson; gap_std = gap_mean, i.e. CV = 1).
* ``B -> 1`` — maximally bursty (long pauses punctuated by rapid clusters).

``B`` is bounded and scale-robust (unlike the raw coefficient of variation, which is unbounded);
both are carried for audit.

This is genuinely distinct from every other reading axis: none measures WHEN events occur over
time (density = marks per content; coverage = spatial breadth; continuity = position-step
DIRECTION; distribution = spread across sections; re-engagement = CROSS-session return; topology =
spatial contiguity). Cadence is the WITHIN-session temporal rhythm — orthogonal machinery.

**Measured fields:**

* ``event_count`` — number of reading events in the session.
* ``gap_count`` = ``event_count - 1`` — number of inter-event time gaps.
* ``session_duration`` — ``last - first`` timestamp (the temporal span).
* ``mean_gap`` — average inter-event gap.
* ``gap_std`` — population standard deviation of the gaps.
* ``gap_cv`` — coefficient of variation ``gap_std / gap_mean`` (``>= 0``; the unbounded
  inconsistency; ``None`` when undefined).
* ``min_gap`` / ``max_gap`` — the gap range (auditable: the operator sees the shortest burst and
  the longest pause).
* ``burstiness_coefficient`` — ``B`` in ``[-1, 1]`` (``None`` when undefined).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero events -> ``unknown`` (no rhythm to measure — defer, never fabricated).
* one event -> ``single_event`` (one timestamp — no gap, no rhythm; honest base case distinct
  from ``unknown`` which has none).
* ``>= 2`` events but all at the same instant (``session_duration == 0``) -> ``unmeasurable``
  (no temporal spread — defer, never fabricated).
* ``B <= steady_threshold`` (default ``-0.30``) -> ``steady_cadence`` (more regular than random
  — a metronomic reading pace).
* ``B >= bursty_threshold`` (default ``0.30``) -> ``bursty_cadence`` (more bursty than random —
  rapid clusters separated by long pauses).
* otherwise -> ``irregular_cadence`` (near-random timing — neither metronomic nor bursty).

**DESCRIPTIVE NOT NORMATIVE:** ``steady_cadence`` does NOT mean "good" — a metronomic pace can be
mechanical plodding without depth. ``bursty_cadence`` does NOT mean "bad" — binge deep-dives are
often the most valuable reading. The operator judges whether the rhythm reflects reading INTENT
(sustained study vs opportunistic sprints). This axis surfaces the FACT of temporal rhythm; it
does not prescribe the right cadence.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero events are supplied.
* ``single_event`` is its own honest base case (one timestamp — distinct from ``unknown`` and
  from any rhythm verdict).
* ``unmeasurable`` is its own honest state when all events share one instant — it is NOT collapsed
  into ``irregular_cadence`` (a real near-zero ``B``).
* ``burstiness_coefficient`` is ``None`` only for ``unknown`` / ``single_event`` / ``unmeasurable``;
  a real near-zero ``B`` is carried as a measured value, never deferred.
* ``B`` is scale-robust (baselined against Poisson; a 0.3 threshold means the same rhythm strength
  whether gaps are in seconds or hours).
* timestamps sorted ascending for determinism (unordered input is normalized, not rejected).
* ``min_gap`` / ``max_gap`` carried verbatim (auditable rhythm extremes — no black-box coefficient).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain float-timestamp inputs; route layer adapts 1:1 from the
  reading event-timestamp log).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ReadingCadenceReport",
    "measure_reading_cadence",
]

_DEFAULT_STEADY_THRESHOLD = -0.30
_DEFAULT_BURSTY_THRESHOLD = 0.30


@dataclass(frozen=True)
class ReadingCadenceReport:
    """The within-session temporal-rhythm surface for one reading session. Advisory, pure."""

    event_count: int
    gap_count: int
    session_duration: float | None
    mean_gap: float | None
    gap_std: float | None
    gap_cv: float | None
    min_gap: float | None
    max_gap: float | None
    burstiness_coefficient: float | None
    steady_threshold: float
    bursty_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_reading_cadence(
    timestamps: Sequence[float],
    *,
    steady_threshold: float = _DEFAULT_STEADY_THRESHOLD,
    bursty_threshold: float = _DEFAULT_BURSTY_THRESHOLD,
) -> ReadingCadenceReport:
    r"""Measure the within-session temporal rhythm (cadence) of reading events.

    ``timestamps`` are the times (seconds) of reading events within ONE session (the route layer
    supplies these from the reading event-timestamp log). Returns a
    :class:`ReadingCadenceReport` with the burstiness coefficient and verdict.

    Raises:
        ValueError: if a threshold is outside its valid range.
    """
    if not -1.0 <= steady_threshold < 0.0:
        raise ValueError(
            f"steady_threshold must be in [-1.0, 0.0); got {steady_threshold}"
        )
    if not 0.0 < bursty_threshold <= 1.0:
        raise ValueError(
            f"bursty_threshold must be in (0.0, 1.0]; got {bursty_threshold}"
        )

    events = sorted(timestamps)
    event_count = len(events)

    if event_count == 0:
        return ReadingCadenceReport(
            event_count=0,
            gap_count=0,
            session_duration=None,
            mean_gap=None,
            gap_std=None,
            gap_cv=None,
            min_gap=None,
            max_gap=None,
            burstiness_coefficient=None,
            steady_threshold=steady_threshold,
            bursty_threshold=bursty_threshold,
            verdict="unknown",
            notes=("no events — reading rhythm unmeasurable",),
        )

    if event_count == 1:
        return ReadingCadenceReport(
            event_count=1,
            gap_count=0,
            session_duration=None,
            mean_gap=None,
            gap_std=None,
            gap_cv=None,
            min_gap=None,
            max_gap=None,
            burstiness_coefficient=None,
            steady_threshold=steady_threshold,
            bursty_threshold=bursty_threshold,
            verdict="single_event",
            notes=("one event — no inter-event gap to measure rhythm",),
        )

    gaps = [events[i + 1] - events[i] for i in range(event_count - 1)]
    gap_count = len(gaps)
    session_duration = events[-1] - events[0]
    mean_gap = session_duration / gap_count
    gap_std = math.sqrt(sum((g - mean_gap) ** 2 for g in gaps) / gap_count)
    min_gap = min(gaps)
    max_gap = max(gaps)

    if session_duration == 0.0:
        return ReadingCadenceReport(
            event_count=event_count,
            gap_count=gap_count,
            session_duration=0.0,
            mean_gap=0.0,
            gap_std=0.0,
            gap_cv=None,
            min_gap=min_gap,
            max_gap=max_gap,
            burstiness_coefficient=None,
            steady_threshold=steady_threshold,
            bursty_threshold=bursty_threshold,
            verdict="unmeasurable",
            notes=("all events at one instant — no temporal spread to measure rhythm",),
        )

    gap_cv = gap_std / mean_gap
    burstiness = (gap_std - mean_gap) / (gap_std + mean_gap)

    if burstiness <= steady_threshold:
        verdict = "steady_cadence"
        notes = (
            f"burstiness {burstiness:.4f} <= steady_threshold {steady_threshold:.2f} — "
            "more regular than random (metronomic reading pace)",
        )
    elif burstiness >= bursty_threshold:
        verdict = "bursty_cadence"
        notes = (
            f"burstiness {burstiness:.4f} >= bursty_threshold {bursty_threshold:.2f} — "
            "more bursty than random (rapid clusters separated by long pauses)",
        )
    else:
        verdict = "irregular_cadence"
        notes = (
            f"burstiness {burstiness:.4f} between thresholds — near-random timing",
        )

    return ReadingCadenceReport(
        event_count=event_count,
        gap_count=gap_count,
        session_duration=session_duration,
        mean_gap=mean_gap,
        gap_std=gap_std,
        gap_cv=gap_cv,
        min_gap=min_gap,
        max_gap=max_gap,
        burstiness_coefficient=burstiness,
        steady_threshold=steady_threshold,
        bursty_threshold=bursty_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
