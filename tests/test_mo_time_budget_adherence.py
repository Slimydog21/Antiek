"""Tests for the Midnight Oil time-budget-adherence axis (ask #13).

Exercises: within/over/uncapped/unknown verdicts, utilization + overrun ratios,
per-phase attribution, overrun-phase counting, honesty (None handling), purity/
immutability, validation. Hand-counted numeric fixtures.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_time_budget_adherence import (
    PhaseAdherence,
    TimeBudgetAdherenceError,
    TimeBudgetAdherenceReport,
    measure_time_budget_adherence,
)

# --- within budget --------------------------------------------------------


def test_within_budget_exact() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=60.0
    )
    assert r.verdict == "within_budget"
    assert r.utilization_ratio == 1.0
    assert r.overrun_minutes == 0.0
    assert r.overrun_ratio == 0.0
    assert r.authority == "advisory"


def test_within_budget_underused() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=15.0
    )
    assert r.verdict == "within_budget"
    assert r.utilization_ratio == pytest.approx(0.25)
    assert r.overrun_minutes == 0.0
    assert r.overrun_ratio == 0.0


# --- over budget ----------------------------------------------------------


def test_over_budget_double() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=120.0
    )
    assert r.verdict == "over_budget"
    assert r.utilization_ratio == pytest.approx(2.0)
    assert r.overrun_minutes == 60.0
    assert r.overrun_ratio == 1.0


def test_over_budget_slight() -> None:
    # 65/60 = 1.0833...; overrun 5 min, ratio 5/60 ~= 0.0833
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=65.0
    )
    assert r.verdict == "over_budget"
    assert r.utilization_ratio == pytest.approx(1.0833, abs=0.001)
    assert r.overrun_minutes == 5.0
    assert r.overrun_ratio == pytest.approx(0.0833, abs=0.001)


# --- uncapped / unknown honesty ------------------------------------------


def test_uncapped_when_no_budget_declared() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=None, actual_elapsed_minutes=90.0
    )
    assert r.verdict == "uncapped"
    assert r.utilization_ratio is None
    assert r.overrun_ratio is None
    assert r.overrun_minutes == 0.0


def test_uncapped_when_budget_zero() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=0.0, actual_elapsed_minutes=90.0
    )
    assert r.verdict == "uncapped"


def test_unknown_when_run_did_not_finish() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=None
    )
    assert r.verdict == "unknown"
    assert r.utilization_ratio is None
    assert r.overrun_ratio is None


def test_unknown_when_actual_zero() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=0.0
    )
    assert r.verdict == "unknown"


# --- per-phase attribution ------------------------------------------------


def test_phase_attribution_identifies_runaway_phase() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1",
        declared_budget_minutes=90.0,
        actual_elapsed_minutes=90.0,
        phase_breakdown=(
            ("ingest", 30.0, 30.0),      # within
            ("research", 40.0, 55.0),    # over (55/40 = 1.375)
            ("synthesis", 20.0, 5.0),    # within
        ),
    )
    assert r.verdict == "within_budget"  # overall respected
    by_name = {p.phase_name: p for p in r.phase_adherences}
    assert by_name["ingest"].verdict == "within_budget"
    assert by_name["research"].verdict == "over_budget"
    assert by_name["research"].utilization_ratio == pytest.approx(1.375)
    assert by_name["synthesis"].verdict == "within_budget"
    assert r.overrun_phase_count == 1


def test_phase_uncapped_and_unknown_propagate() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1",
        declared_budget_minutes=60.0,
        actual_elapsed_minutes=60.0,
        phase_breakdown=(
            ("no-cap", None, 20.0),    # uncapped
            ("not-run", 20.0, None),   # unknown
        ),
    )
    by_name = {p.phase_name: p for p in r.phase_adherences}
    assert by_name["no-cap"].verdict == "uncapped"
    assert by_name["no-cap"].utilization_ratio is None
    assert by_name["not-run"].verdict == "unknown"
    assert r.overrun_phase_count == 0


def test_no_phase_breakdown_is_clean() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=60.0
    )
    assert r.phase_adherences == ()
    assert r.overrun_phase_count == 0


# --- validation -----------------------------------------------------------


def test_empty_run_id_raises() -> None:
    with pytest.raises(TimeBudgetAdherenceError, match="run_id"):
        measure_time_budget_adherence(
            run_id="", declared_budget_minutes=60.0, actual_elapsed_minutes=60.0
        )


@pytest.mark.parametrize("field", ["declared_budget_minutes", "actual_elapsed_minutes"])
def test_negative_duration_raises(field: str) -> None:
    kwargs: dict[str, object] = {
        "run_id": "run-1",
        "declared_budget_minutes": 60.0,
        "actual_elapsed_minutes": 60.0,
    }
    kwargs[field] = -5.0
    with pytest.raises(TimeBudgetAdherenceError, match="non-negative"):
        measure_time_budget_adherence(**kwargs)  # type: ignore[arg-type]


def test_negative_phase_duration_raises() -> None:
    with pytest.raises(TimeBudgetAdherenceError, match="phase"):
        measure_time_budget_adherence(
            run_id="run-1",
            declared_budget_minutes=60.0,
            actual_elapsed_minutes=60.0,
            phase_breakdown=(("bad", 10.0, -1.0),),
        )


def test_empty_phase_name_raises() -> None:
    with pytest.raises(TimeBudgetAdherenceError, match="phase names"):
        measure_time_budget_adherence(
            run_id="run-1",
            declared_budget_minutes=60.0,
            actual_elapsed_minutes=60.0,
            phase_breakdown=(("", 10.0, 10.0),),
        )


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    r1 = measure_time_budget_adherence(
        run_id="run-1",
        declared_budget_minutes=60.0,
        actual_elapsed_minutes=70.0,
        phase_breakdown=(("research", 40.0, 45.0),),
    )
    r2 = measure_time_budget_adherence(
        run_id="run-1",
        declared_budget_minutes=60.0,
        actual_elapsed_minutes=70.0,
        phase_breakdown=(("research", 40.0, 45.0),),
    )
    assert dataclasses.is_dataclass(r1)
    assert isinstance(r1.phase_adherences, tuple)
    assert all(isinstance(p, PhaseAdherence) for p in r1.phase_adherences)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]


def test_notes_are_non_empty_and_auditable() -> None:
    r = measure_time_budget_adherence(
        run_id="run-1", declared_budget_minutes=60.0, actual_elapsed_minutes=60.0
    )
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)
    assert isinstance(r, TimeBudgetAdherenceReport)
