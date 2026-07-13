"""Tests for the Midnight Oil interrupt-resumption axis (ask #13).

Measures whether a multi-segment run resumed coherently across pause/resume
boundaries — contiguous (no work lost/redone), skipping (work silently missed),
or redoing (wasted budget). Exercises coherent/skipping/redoing/unknown verdicts,
gap/overlap detection, perfect-resumption rate, tolerances, validation,
purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_interrupt_resumption import (
    InterruptResumptionError,
    RunSegment,
    measure_interrupt_resumption,
)


def seg(
    rows: list[tuple[str, float, float | None]],
) -> list[RunSegment]:
    return [
        RunSegment(segment_id=sid, pause_progress=p, resume_progress=r)
        for sid, p, r in rows
    ]


# --- unknown (no transitions) ---------------------------------------------


def test_unknown_when_no_segments() -> None:
    r = measure_interrupt_resumption([])
    assert r.verdict == "unknown"
    assert r.transition_count == 0
    assert r.perfect_resumption_rate is None
    assert r.mean_gap is None
    assert r.max_gap is None
    assert r.authority == "advisory"


def test_unknown_when_single_uninterrupted_segment() -> None:
    # One segment, resume None (final segment) -> no pause/resume boundary.
    r = measure_interrupt_resumption(seg([("s1", 0.5, None)]))
    assert r.verdict == "unknown"
    assert r.transition_count == 0


def test_unknown_when_all_final() -> None:
    r = measure_interrupt_resumption(seg([("s1", 0.3, None), ("s2", 0.7, None)]))
    assert r.verdict == "unknown"
    assert r.transition_count == 0


# --- coherent -------------------------------------------------------------


def test_coherent_all_contiguous() -> None:
    # resume == pause exactly -> gap 0 -> perfect contiguous.
    r = measure_interrupt_resumption(
        seg([("s1", 0.3, 0.3), ("s2", 0.6, 0.6), ("s3", 0.9, None)])
    )
    assert r.verdict == "coherent"
    assert r.transition_count == 2
    assert r.gap_count == 0
    assert r.overlap_count == 0
    assert r.perfect_resumption_rate == 1.0
    assert r.mean_gap == 0.0
    assert r.max_gap == 0.0


# --- skipping -------------------------------------------------------------


def test_skipping_one_gap() -> None:
    # s1 resumes at 0.5 but paused at 0.3 -> gap 0.2 (work skipped).
    r = measure_interrupt_resumption(seg([("s1", 0.3, 0.5), ("s2", 0.8, None)]))
    assert r.verdict == "skipping"
    assert r.gap_count == 1
    assert r.overlap_count == 0
    assert r.perfect_resumption_rate == 0.0
    assert r.mean_gap == pytest.approx(0.2)
    assert r.max_gap == pytest.approx(0.2)


def test_skipping_mixed_gaps_and_overlaps() -> None:
    # gap then overlap -> gap_count >= 1 wins (skipping is the dangerous signal).
    r = measure_interrupt_resumption(
        seg([("s1", 0.2, 0.5), ("s2", 0.6, 0.4), ("s3", 0.9, None)])
    )
    assert r.verdict == "skipping"
    assert r.gap_count == 1
    assert r.overlap_count == 1
    assert r.perfect_resumption_rate == 0.0
    # gaps: 0.3, -0.2 -> mean 0.05, max 0.3.
    assert r.mean_gap == pytest.approx(0.05)
    assert r.max_gap == pytest.approx(0.3)


# --- redoing --------------------------------------------------------------


def test_redoing_one_overlap() -> None:
    # s1 resumes at 0.2 but paused at 0.4 -> gap -0.2 (work redone).
    r = measure_interrupt_resumption(seg([("s1", 0.4, 0.2), ("s2", 0.8, None)]))
    assert r.verdict == "redoing"
    assert r.overlap_count == 1
    assert r.gap_count == 0
    assert r.perfect_resumption_rate == 0.0
    assert r.mean_gap == pytest.approx(-0.2)
    assert r.max_gap == pytest.approx(-0.2)


def test_redoing_multiple_overlaps_no_gaps() -> None:
    r = measure_interrupt_resumption(
        seg([("s1", 0.4, 0.2), ("s2", 0.5, 0.3), ("s3", 0.9, None)])
    )
    assert r.verdict == "redoing"
    assert r.overlap_count == 2
    assert r.gap_count == 0
    # gaps: -0.2, -0.2 -> mean -0.2, max -0.2.
    assert r.mean_gap == pytest.approx(-0.2)


# --- perfect resumption rate ----------------------------------------------


def test_partial_perfect_rate() -> None:
    # 3 transitions: 1 perfect, 1 gap, 1 overlap -> perfect_rate 1/3.
    r = measure_interrupt_resumption(
        seg([("s1", 0.2, 0.2), ("s2", 0.4, 0.5), ("s3", 0.7, 0.6), ("s4", 1.0, None)])
    )
    assert r.transition_count == 3
    assert r.perfect_resumption_rate == pytest.approx(1 / 3)
    # gap_count 1 (0.5-0.4=0.1>0), overlap_count 1 (0.6-0.7=-0.1<0) -> skipping.
    assert r.verdict == "skipping"


# --- tolerances -----------------------------------------------------------


def test_gap_tolerance_absorbs_small_skip() -> None:
    # gap 0.02 within gap_tolerance 0.05 -> not counted as gap.
    r = measure_interrupt_resumption(
        seg([("s1", 0.3, 0.32), ("s2", 0.9, None)]), gap_tolerance=0.05
    )
    assert r.verdict == "coherent"
    assert r.gap_count == 0


def test_overlap_tolerance_absorbs_small_redo() -> None:
    # overlap -0.02 within overlap_tolerance 0.05 -> not counted.
    r = measure_interrupt_resumption(
        seg([("s1", 0.3, 0.28), ("s2", 0.9, None)]), overlap_tolerance=0.05
    )
    assert r.verdict == "coherent"
    assert r.overlap_count == 0


# --- validation -----------------------------------------------------------


def test_negative_gap_tolerance_raises() -> None:
    with pytest.raises(InterruptResumptionError):
        measure_interrupt_resumption([], gap_tolerance=-0.01)


def test_negative_overlap_tolerance_raises() -> None:
    with pytest.raises(InterruptResumptionError):
        measure_interrupt_resumption([], overlap_tolerance=-0.01)


def test_progress_out_of_range_raises() -> None:
    with pytest.raises(InterruptResumptionError):
        measure_interrupt_resumption(seg([("s1", 1.5, 0.5)]))
    with pytest.raises(InterruptResumptionError):
        measure_interrupt_resumption(seg([("s1", 0.5, -0.1)]))


def test_non_finite_progress_raises() -> None:
    with pytest.raises(InterruptResumptionError):
        measure_interrupt_resumption(
            [RunSegment("s1", float("nan"), 0.5)]
        )
    with pytest.raises(InterruptResumptionError):
        measure_interrupt_resumption(
            [RunSegment("s1", 0.5, float("inf"))]
        )


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    segments = seg([("s1", 0.3, 0.5), ("s2", 0.6, 0.6), ("s3", 0.9, None)])
    assert measure_interrupt_resumption(segments) == measure_interrupt_resumption(
        segments
    )


def test_report_is_frozen_immutable() -> None:
    r = measure_interrupt_resumption(seg([("s1", 0.5, None)]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "skipping"  # type: ignore[misc]


def test_segment_dataclass_is_frozen() -> None:
    s = RunSegment(segment_id="s1", pause_progress=0.5, resume_progress=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.pause_progress = 0.6  # type: ignore[misc]


def test_notes_carry_context() -> None:
    r = measure_interrupt_resumption(
        seg([("s1", 0.2, 0.5), ("s2", 0.9, None)])
    )
    assert r.verdict == "skipping"
    assert any("gap" in note for note in r.notes)
