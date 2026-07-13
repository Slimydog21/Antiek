r"""Reading-flow continuity — did the reader progress or jump around?

Operator vision (asks #2/#6): *"I want to read books or papers (and engage with
it in the same way I would the research workstation)."* Reading and research are
the same surface. The third reading-side measurement axis, after highlight density
(how DENSELY the reader marks) and annotation substantiveness (how much INFORMATION
each note carries): THIS measures the reader's PROGRESSION through the document —
did attention advance linearly, or fragment across the text?

**Genuinely distinct (different object):**

* ``highlight_density`` (#1973): count of marks per passage (a SPATIAL-INTENSITY
  measure at a moment — how thickly a region is marked).
* ``annotation_substantiveness`` (#1978): content quality of each note (a TEXT
  measure — how much information the reader put into a note).
* THIS (``reading_flow_continuity``): the SEQUENTIAL progression of where the
  reader's attention moved over TIME (a TEMPORAL/POSITIONAL measure — the path
  the reader traced through the document).

They are independent. A reader can mark densely (#1973 high), write rich notes
(#1978 high), yet trace an erratic path — forward, back, skip, re-read — OR mark
sparingly with thin notes but progress perfectly linearly. The three failure
modes (over-marking, shallow notes, fragmented attention) are separate; each needs
its own detector. Continuity tells the platform whether the reader is in flow
(linear) or struggling (jumping), which informs the reading UX (nudge a stalled
reader, offer a navigation aid to a fragmented one).

**The measurement (hard to vary).** Given a chronological sequence of reading
events, each carrying a normalized document position in ``[0, 1]`` (0 = start,
1 = end; the route layer normalizes the raw offset/section anchor):

* consecutive signed ``step = pos[i] - pos[i-1]`` (positive = forward, negative
  = backward re-read).
* ``net_progress = pos[last] - pos[first]`` (the net forward distance covered).
* ``total_distance = sum(|step|)`` (the actual path length traveled, counting
  back-and-forth).
* ``continuity_ratio = net_progress / total_distance`` — the path-efficiency of
  forward reading, in ``[-1, 1]``: ``1.0`` = perfectly monotonic forward (every
  step advanced); ``0.0`` = net zero (went forward then came back, or balanced
  back-and-forth); negative = net backward (ended earlier than started).
* ``backward_step_rate = backward_steps / total_steps`` — how often a step moved
  the reader backward.
* ``max_backward_step`` — the largest single backward jump (the most aggressive
  re-read), carried even when ``0.0`` (never withheld).

**Verdict (distinct honest states, never collapsed):**

* fewer than two events, OR ``total_distance == 0`` (all events at the same
  position — nothing moved) -> ``unknown`` (defer — never fabricated; continuity
  cannot be measured from a stationary point).
* ``continuity_ratio >= linear_threshold`` (default ``0.85``) -> ``linear_progress``
  (efficient forward reading).
* ``0 < continuity_ratio < linear_threshold`` -> ``fragmented`` (forward on net,
  but the path was inefficient — lots of back-and-forth).
* ``continuity_ratio <= 0`` -> ``regressive`` (net backward or net-zero after
  movement — the reader ended no further along, or further back, than they began).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict on fewer than two events or a stationary
  sequence (a reader who marked the same spot five times did not "flow").
* ``continuity_ratio`` / ``backward_step_rate`` / ``max_backward_step`` are
  ``None`` when ``unknown`` (defer — never ``0.0``).
* Positions must be finite in ``[0, 1]`` (a reading position outside the document
  is a recording error); raises otherwise.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``ReadingEvent`` input
shape (the route layer adapts 1:1 from the reader's highlight/annotation stream,
normalizing each event's document offset to ``[0, 1]``). Pure-Python: stdlib only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_LINEAR_THRESHOLD: float = 0.85


class ReadingFlowContinuityError(ValueError):
    """A reading-flow-continuity input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ReadingEvent:
    """One reading-engagement event at a normalized document position.

    ``position`` is the event's location in the document, normalized to
    ``[0, 1]`` (0 = start, 1 = end). Events are supplied in chronological order.
    """

    event_id: str
    position: float


@dataclass(frozen=True)
class ReadingFlowContinuityReport:
    """The reading-progression verdict. Advisory, pure."""

    event_count: int
    continuity_ratio: float | None  # net_progress / total_distance; None if unknown
    net_progress: float | None  # last - first; None if unknown
    total_distance: float | None  # sum of |step|; None if unknown
    backward_step_rate: float | None  # backward steps / total steps; None if unknown
    max_backward_step: float | None  # most negative single step; None if unknown
    linear_threshold: float
    verdict: str  # linear_progress | fragmented | regressive | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _validate_position(value: float) -> None:
    if math.isnan(value) or math.isinf(value):
        raise ReadingFlowContinuityError(f"position must be finite; got {value}")
    if not 0.0 <= value <= 1.0:
        raise ReadingFlowContinuityError(f"position must be in [0, 1]; got {value}")


def measure_reading_flow_continuity(
    events: Sequence[ReadingEvent],
    *,
    linear_threshold: float = _DEFAULT_LINEAR_THRESHOLD,
) -> ReadingFlowContinuityReport:
    """Measure the reader's sequential progression through a document.

    ``events`` is a chronological sequence of :class:`ReadingEvent` (each carrying
    a normalized ``[0, 1]`` position). Returns a
    :class:`ReadingFlowContinuityReport` with the continuity ratio, backward-step
    rate, and verdict.

    Raises:
        ReadingFlowContinuityError: if ``linear_threshold`` is outside ``(0, 1]``
            or any position is non-finite or outside ``[0, 1]``.
    """
    if not 0.0 < linear_threshold <= 1.0:
        raise ReadingFlowContinuityError(
            "linear_threshold must be in the open-closed interval (0.0, 1.0]; "
            f"got {linear_threshold!r}"
        )

    for ev in events:
        _validate_position(ev.position)

    n = len(events)
    if n < 2:
        return ReadingFlowContinuityReport(
            event_count=n,
            continuity_ratio=None,
            net_progress=None,
            total_distance=None,
            backward_step_rate=None,
            max_backward_step=None,
            linear_threshold=linear_threshold,
            verdict="unknown",
            notes=("fewer than two events — progression undefined",),
        )

    positions = [ev.position for ev in events]
    steps = [positions[i] - positions[i - 1] for i in range(1, n)]
    net_progress = positions[-1] - positions[0]
    total_distance = sum(abs(step) for step in steps)
    backward_steps = sum(1 for step in steps if step < 0.0)
    backward_step_rate = backward_steps / len(steps)
    max_backward_step = min(steps)  # most negative (or >= 0 if none backward)

    if total_distance == 0.0:
        # All events at the same position — nothing moved; cannot measure flow.
        return ReadingFlowContinuityReport(
            event_count=n,
            continuity_ratio=None,
            net_progress=None,
            total_distance=None,
            backward_step_rate=None,
            max_backward_step=None,
            linear_threshold=linear_threshold,
            verdict="unknown",
            notes=("all events at the same position — stationary",),
        )

    continuity_ratio = net_progress / total_distance

    if continuity_ratio >= linear_threshold:
        verdict = "linear_progress"
    elif continuity_ratio > 0.0:
        verdict = "fragmented"
    else:
        verdict = "regressive"

    notes = (
        f"continuity_ratio {continuity_ratio:.4f} "
        f"(net_progress {net_progress:.4f}, distance {total_distance:.4f}); "
        f"{backward_steps} of {len(steps)} step(s) backward",
    )

    return ReadingFlowContinuityReport(
        event_count=n,
        continuity_ratio=continuity_ratio,
        net_progress=net_progress,
        total_distance=total_distance,
        backward_step_rate=backward_step_rate,
        max_backward_step=max_backward_step,
        linear_threshold=linear_threshold,
        verdict=verdict,
        notes=notes,
    )
