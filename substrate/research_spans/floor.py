"""Retrieval floor — refuse-or-requery quality gate.

The floor scores a result set's quality; below a threshold it returns
a typed ``Requery`` or ``InsufficientSources`` outcome instead of
letting thin evidence reach the assembler.

Policy (doctrine I-6, Perplexity discard-and-restart):
    The floor threshold is a **named, commented policy value** — not an
    inline literal.  The threshold, the quality metric, and the
    re-query limit are operator-tunable; each carries a comment naming
    its evidence and the condition under which the operator should
    retune it.

    OPERATOR_TUNABLE: the threshold (0.3) is a hypothesis from
    Perplexity's discard-and-restart behavior — below ~30% of the
    retrieval score range, results are "thin" (few relevant spans,
    low scores).  W0 calibration may shift this; retune when the
    measured floor-trip rate diverges from the doctrine's expected
    ~5-15% of investigations.  W0 NOT MEASURED.

Visible outcomes (REJECT fix #4):
    Every floor trip emits a trace event (``FloorTripTrace``) so the
    operator can see the floor working.  The outcome types
    (``Requery``, ``InsufficientSources``) are returned — not raised
    as exceptions — so callers handle them explicitly.  **No public
    convenience API may discard the trace.**  ``check_floor`` returns
    ``(outcome, trace_or_None)``; ``assemble_or_refuse`` preserves
    the trace in its return value.

Select-before-floor (REJECT fix #3):
    ``check_floor`` takes a ``SelectionResult`` (output of
    ``_select_candidates`` or ``extract_select``) rather than raw spans.
    This guarantees that the floor never returns a ``SelectionResult``
    with ``total_tokens > budget`` — the budget was already enforced by
    the selection step.

Validation (REJECT fix G):
    Validates query nonempty, threshold finite [0,1], attempts/top_k
    true ints nonnegative, rejects bool-as-int where relevant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .select import SelectionResult
from .span import ExtractiveSpan

# ---------------------------------------------------------------------------
# Floor policy
# ---------------------------------------------------------------------------

# OPERATOR_TUNABLE: quality threshold below which the result set is
# considered "thin".  Derived from Perplexity's discard-and-restart
# behavior (doctrine I-6): below ~30% of the max retrieval score,
# results lack sufficient relevance for synthesis.  Retune when W0
# calibration shows the floor-trip rate diverges from the expected
# ~5-15% of investigations.  W0 NOT MEASURED.
FLOOR_QUALITY_THRESHOLD: float = 0.3

# OPERATOR_TUNABLE: maximum re-query attempts before giving up.
# Perplexity retries 1-2 times; we allow 3 before refusing.
# Retune when the observed retry distribution changes.
FLOOR_MAX_REQUERIES: int = 3

# Minimum number of spans required for a result set to pass the floor.
# Below this, the set is structurally thin regardless of scores.
FLOOR_MIN_SPANS: int = 2


# ---------------------------------------------------------------------------
# Quality metric
# ---------------------------------------------------------------------------


def result_set_quality(
    selected: tuple[ExtractiveSpan, ...],
) -> float:
    """Compute a quality score for a result set of selected spans.

    The score is in [0.0, 1.0].  It combines:
    - span count adequacy (how many spans vs. a minimum);
    - average retrieval score (how relevant the spans are);
    - token coverage (whether the spans provide enough content).

    A result set with 0 spans scores 0.0.

    REJECT fix #8: clamps NaN/inf/negative/>1 scores.  Quality is
    always in [0, 1].
    """
    if not selected:
        return 0.0

    # Span-count component: ramps from 0 at 0 spans to 1.0 at
    # FLOOR_MIN_SPANS or above.
    count_score = min(1.0, len(selected) / FLOOR_MIN_SPANS)

    # Average retrieval score component — clamp to [0, 1].
    raw_avg = sum(s.retrieval_score for s in selected) / len(selected)
    # REJECT fix #8: clamp NaN/inf/negative/>1.
    avg_score = 0.0 if raw_avg != raw_avg else max(0.0, min(1.0, raw_avg))

    # Token-coverage component: total tokens / (FLOOR_MIN_SPANS * 200).
    # 200 tokens is the minimum useful extractive span size (doctrine I-2).
    # Use char/4 heuristic inline (no counter dependency from select).
    total_chars = sum(len(s.text) for s in selected)
    total_tokens = max(1, (total_chars + 3) // 4) if total_chars > 0 else 0
    target_tokens = FLOOR_MIN_SPANS * 200
    token_score = min(1.0, total_tokens / target_tokens)

    # Geometric mean — all components must be non-zero for a high score.
    result: float = (count_score * avg_score * token_score) ** (1 / 3)
    # Final clamp to [0, 1].
    return max(0.0, min(1.0, result))


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requery:
    """Floor outcome: the result set is thin; re-query with adjusted params.

    ``reason`` is a human-readable explanation of why the floor tripped.
    ``attempt`` is which re-query attempt this is (1-indexed).
    ``adjusted_top_k`` is the suggested new top_k for the re-query
    (the floor increases it to cast a wider net).
    """

    reason: str
    attempt: int
    adjusted_top_k: int


@dataclass(frozen=True)
class InsufficientSources:
    """Floor outcome: re-query limit exhausted; refuse to synthesize.

    ``reason`` is a human-readable explanation.
    ``attempts_made`` is how many re-queries were tried.
    """

    reason: str
    attempts_made: int


# Union type for floor check results.
FloorOutcome = SelectionResult | Requery | InsufficientSources


# ---------------------------------------------------------------------------
# Trace event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FloorTripTrace:
    """Trace event emitted on every floor trip.

    This is the visible evidence that the floor is working.  The
    caller (the research loop) should log or emit this to the event
    log so it appears in the investigation trajectory.
    """

    quality_score: float
    threshold: float
    span_count: int
    total_tokens: int
    outcome_kind: Literal["requery", "insufficient_sources"]
    reason: str


# ---------------------------------------------------------------------------
# Floor check
# ---------------------------------------------------------------------------


def check_floor(
    selection: SelectionResult,
    *,
    current_attempt: int = 0,
    initial_top_k: int = 5,
    threshold: float = FLOOR_QUALITY_THRESHOLD,
) -> tuple[FloorOutcome, FloorTripTrace | None]:
    """Check whether a selection result passes the retrieval floor.

    Takes a ``SelectionResult`` (from ``_select_candidates`` or
    ``extract_select``) rather than raw spans.  This guarantees the
    budget invariant: the floor never returns a ``SelectionResult``
    with ``total_tokens > budget``.

    Returns ``(outcome, trace_or_None)``.  ``trace`` is ``None`` when
    the floor passes (no trip).  When the floor trips, ``trace`` is
    always populated.

    ``current_attempt`` is 0-indexed (0 = first check, before any
    re-query).  When it exceeds ``FLOOR_MAX_REQUERIES``, the outcome
    is ``InsufficientSources``.

    REJECT fix #3: select-before-floor — selection already enforced
    the budget.  REJECT fix #4: trace always populated on trip.
    REJECT fix G: validates threshold/attempt/top_k.  Rejects
    bool-as-int, NaN/inf threshold, negative/non-int attempts.
    """
    # Validate threshold: must be float (not bool), finite, in [0, 1].
    if isinstance(threshold, bool):
        raise TypeError(
            f"threshold must be float, not bool, got {threshold!r}"
        )
    if not isinstance(threshold, (int, float)):
        raise TypeError(
            f"threshold must be int or float, got {type(threshold).__name__}"
        )
    if math.isnan(threshold):
        raise ValueError("threshold must not be NaN")
    if math.isinf(threshold):
        raise ValueError("threshold must not be infinite")
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")

    # Validate current_attempt: must be int (not bool), non-negative.
    if isinstance(current_attempt, bool):
        raise TypeError(
            f"current_attempt must be int, not bool, got {current_attempt!r}"
        )
    if not isinstance(current_attempt, int):
        raise TypeError(
            f"current_attempt must be int, got {type(current_attempt).__name__}"
        )
    if current_attempt < 0:
        raise ValueError(
            f"current_attempt must be >= 0, got {current_attempt}"
        )

    # Validate initial_top_k: must be int (not bool), positive.
    if isinstance(initial_top_k, bool):
        raise TypeError(
            f"initial_top_k must be int, not bool, got {initial_top_k!r}"
        )
    if not isinstance(initial_top_k, int):
        raise TypeError(
            f"initial_top_k must be int, got {type(initial_top_k).__name__}"
        )
    if initial_top_k < 1:
        raise ValueError(f"initial_top_k must be >= 1, got {initial_top_k}")

    quality = result_set_quality(selection.selected)

    if quality >= threshold and len(selection.selected) >= FLOOR_MIN_SPANS:
        # Floor passes — return the SelectionResult unchanged.
        # The budget invariant is guaranteed because selection ran first.
        return selection, None

    # Floor tripped.
    reason = (
        f"quality {quality:.4f} < threshold {threshold:.4f} "
        f"({len(selection.selected)} spans, attempt {current_attempt})"
    )

    if current_attempt >= FLOOR_MAX_REQUERIES:
        outcome: FloorOutcome = InsufficientSources(
            reason=f"Re-query limit exhausted after {current_attempt} attempts. {reason}",
            attempts_made=current_attempt,
        )
        trace = FloorTripTrace(
            quality_score=quality,
            threshold=threshold,
            span_count=len(selection.selected),
            total_tokens=selection.total_tokens,
            outcome_kind="insufficient_sources",
            reason=reason,
        )
        return outcome, trace

    # Suggest a wider re-query.
    adjusted_top_k = initial_top_k * (current_attempt + 2)
    outcome = Requery(
        reason=reason,
        attempt=current_attempt + 1,
        adjusted_top_k=adjusted_top_k,
    )
    trace = FloorTripTrace(
        quality_score=quality,
        threshold=threshold,
        span_count=len(selection.selected),
        total_tokens=selection.total_tokens,
        outcome_kind="requery",
        reason=reason,
    )
    return outcome, trace
