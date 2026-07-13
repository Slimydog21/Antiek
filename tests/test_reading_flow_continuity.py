"""Tests for the reading-flow-continuity axis (asks #2/#6).

Measures the reader's sequential positional progression through a document.
Exercises linear_progress / fragmented / regressive / unknown verdicts, the
continuity-ratio path-efficiency, backward-step rate, the stationary edge case,
threshold boundary, validation, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.reading_flow_continuity import (
    ReadingEvent,
    ReadingFlowContinuityError,
    measure_reading_flow_continuity,
)


def ev(positions: list[float]) -> list[ReadingEvent]:
    return [ReadingEvent(event_id=f"e{i}", position=p) for i, p in enumerate(positions)]


# --- unknown --------------------------------------------------------------


def test_unknown_when_zero_events() -> None:
    r = measure_reading_flow_continuity([])
    assert r.verdict == "unknown"
    assert r.event_count == 0
    assert r.continuity_ratio is None
    assert r.net_progress is None
    assert r.total_distance is None
    assert r.backward_step_rate is None
    assert r.max_backward_step is None
    assert r.authority == "advisory"


def test_unknown_when_single_event() -> None:
    r = measure_reading_flow_continuity(ev([0.5]))
    assert r.verdict == "unknown"
    assert r.event_count == 1
    assert r.continuity_ratio is None


def test_unknown_when_stationary_all_same_position() -> None:
    # Five events all at 0.3 — nothing moved; cannot measure flow.
    r = measure_reading_flow_continuity(ev([0.3, 0.3, 0.3, 0.3, 0.3]))
    assert r.verdict == "unknown"
    assert r.event_count == 5
    assert r.continuity_ratio is None
    assert r.backward_step_rate is None


# --- linear_progress ------------------------------------------------------


def test_linear_progress_perfectly_monotonic() -> None:
    r = measure_reading_flow_continuity(ev([0.1, 0.2, 0.3, 0.4, 0.5]))
    assert r.verdict == "linear_progress"
    # net_progress 0.4, distance 0.4 -> ratio 1.0.
    assert r.continuity_ratio == pytest.approx(1.0)
    assert r.net_progress == pytest.approx(0.4)
    assert r.total_distance == pytest.approx(0.4)
    assert r.backward_step_rate == 0.0
    assert r.max_backward_step == pytest.approx(0.1)  # smallest forward step


def test_linear_progress_uneven_but_monotonic() -> None:
    # forward steps of varying size — still perfectly monotonic, ratio 1.0.
    r = measure_reading_flow_continuity(ev([0.1, 0.15, 0.5, 0.51, 0.9]))
    assert r.verdict == "linear_progress"
    assert r.continuity_ratio == pytest.approx(1.0)
    assert r.backward_step_rate == 0.0


def test_linear_progress_small_back_step_still_efficient() -> None:
    # 0.1 -> 0.5 (forward .4) -> 0.45 (back .05) -> 0.9 (forward .45)
    # net .8, distance .9 -> ratio .888... >= 0.85 -> linear.
    r = measure_reading_flow_continuity(ev([0.1, 0.5, 0.45, 0.9]))
    assert r.continuity_ratio == pytest.approx(0.8 / 0.9)
    assert r.verdict == "linear_progress"
    assert r.backward_step_rate == pytest.approx(1 / 3)
    assert r.max_backward_step == pytest.approx(-0.05)


# --- fragmented -----------------------------------------------------------


def test_fragmented_forward_but_inefficient() -> None:
    # lots of back-and-forth, but net forward.
    # steps: +0.3, -0.2, +0.3, -0.2, +0.3 -> net +0.5, distance 1.3 -> ratio .3846.
    r = measure_reading_flow_continuity(ev([0.1, 0.4, 0.2, 0.5, 0.3, 0.6]))
    assert r.continuity_ratio == pytest.approx(0.5 / 1.3)
    assert r.continuity_ratio is not None
    assert 0.0 < r.continuity_ratio < 0.85
    assert r.verdict == "fragmented"
    # 2 of 5 steps backward.
    assert r.backward_step_rate == pytest.approx(2 / 5)
    assert r.max_backward_step == pytest.approx(-0.2)


# --- regressive -----------------------------------------------------------


def test_regressive_net_zero_after_movement() -> None:
    # forward then back to start: net 0.0, distance 0.6 -> ratio 0.0 -> regressive.
    r = measure_reading_flow_continuity(ev([0.1, 0.4, 0.1]))
    assert r.continuity_ratio == pytest.approx(0.0)
    assert r.verdict == "regressive"
    assert r.backward_step_rate == pytest.approx(0.5)
    assert r.max_backward_step == pytest.approx(-0.3)


def test_regressive_net_backward() -> None:
    # ended earlier than started: net negative, ratio negative.
    # steps: +0.3, -0.5 -> net -0.2, distance 0.8 -> ratio -0.25.
    r = measure_reading_flow_continuity(ev([0.2, 0.5, 0.0]))
    assert r.continuity_ratio == pytest.approx(-0.25)
    assert r.verdict == "regressive"


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_can_shift_fragmented_to_linear() -> None:
    positions = [0.1, 0.5, 0.45, 0.9]  # ratio .888
    r_default = measure_reading_flow_continuity(ev(positions))
    assert r_default.verdict == "linear_progress"
    # threshold 0.95 makes .888 fragmented.
    r_strict = measure_reading_flow_continuity(ev(positions), linear_threshold=0.95)
    assert r_strict.verdict == "fragmented"
    assert r_strict.linear_threshold == 0.95


def test_threshold_of_one_requires_perfect_monotonic() -> None:
    # threshold 1.0: only ratio exactly 1.0 (perfect monotonic) is linear.
    r_perfect = measure_reading_flow_continuity(ev([0.1, 0.2, 0.3]), linear_threshold=1.0)
    assert r_perfect.verdict == "linear_progress"
    r_imperfect = measure_reading_flow_continuity(ev([0.1, 0.5, 0.45, 0.9]), linear_threshold=1.0)
    assert r_imperfect.verdict == "fragmented"


# --- validation -----------------------------------------------------------


def test_position_below_zero_raises() -> None:
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity(ev([-0.1, 0.5]))


def test_position_above_one_raises() -> None:
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity(ev([0.1, 1.5]))


def test_non_finite_position_raises() -> None:
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity([ReadingEvent("e0", float("nan"))])
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity([ReadingEvent("e0", float("inf")), ReadingEvent("e1", 0.5)])


def test_invalid_threshold_raises() -> None:
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity(ev([0.1, 0.2]), linear_threshold=0.0)
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity(ev([0.1, 0.2]), linear_threshold=-0.1)
    with pytest.raises(ReadingFlowContinuityError):
        measure_reading_flow_continuity(ev([0.1, 0.2]), linear_threshold=1.01)


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    events = ev([0.1, 0.5, 0.45, 0.9])
    assert measure_reading_flow_continuity(events) == measure_reading_flow_continuity(events)


def test_report_is_frozen_immutable() -> None:
    r = measure_reading_flow_continuity(ev([0.1, 0.2]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "regressive"  # type: ignore[misc]


def test_max_backward_step_zero_when_all_forward() -> None:
    # No backward steps -> max_backward_step is the smallest (positive) step, >= 0.
    r = measure_reading_flow_continuity(ev([0.1, 0.3, 0.4]))
    assert r.verdict == "linear_progress"
    assert r.max_backward_step is not None
    assert r.max_backward_step == pytest.approx(0.1)
    assert r.max_backward_step >= 0.0


def test_notes_carry_context() -> None:
    r = measure_reading_flow_continuity(ev([0.1, 0.5, 0.2, 0.6]))
    assert any("continuity_ratio" in note for note in r.notes)
    assert any("backward" in note for note in r.notes)
