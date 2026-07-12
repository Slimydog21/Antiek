"""Tests for the Midnight Oil run receipt (ask #13 delivery surface)."""

from __future__ import annotations

import pytest

from substrate.midnight_oil.run_receipt import (
    ApprovedEnvelope,
    PhaseActual,
    RunReceipt,
    RunReceiptError,
    build_run_receipt,
)


def _envelope(*, ceiling=0.50, planned=3, goals=("g0", "g1")) -> ApprovedEnvelope:
    return ApprovedEnvelope(
        approved_ceiling_usd=ceiling,
        planned_phase_count=planned,
        planned_duration_minutes=60,
        goals=goals,
    )


def _actual(
    ordinal,
    *,
    goal=0,
    authorized=True,
    ran=True,
    errored=False,
    cost=0.10,
    refs=(),
    stop="",
) -> PhaseActual:
    return PhaseActual(
        ordinal=ordinal,
        goal_index=goal,
        gate_authorized=authorized,
        ran=ran,
        errored=errored,
        actual_cost_usd=cost,
        finding_refs=refs,
        stop_reason=stop,
    )


# --------------------------------------------------------------------------- #
# Invariant #1 — budget verdict computed, never asserted.
# --------------------------------------------------------------------------- #
def test_within_budget_true_when_actual_under_ceiling():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(ceiling=0.50, planned=2),
        phase_actuals=[_actual(0, cost=0.10), _actual(1, cost=0.20)],
    )
    assert receipt.actual_total_usd == pytest.approx(0.30)
    assert receipt.within_budget is True
    assert receipt.overage_usd is None


def test_within_budget_unknown_when_ceiling_none():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(ceiling=None, planned=1),
        phase_actuals=[_actual(0, cost=0.10)],
    )
    assert receipt.within_budget is None
    assert receipt.overage_usd is None
    assert any("no approved ceiling" in n for n in receipt.honesty_notes)


def test_within_budget_unknown_when_any_cost_unreported():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(ceiling=0.50, planned=2),
        phase_actuals=[_actual(0, cost=0.10), _actual(1, cost=None)],
    )
    assert receipt.actual_total_usd is None
    assert receipt.within_budget is None
    assert any("cost unreported" in n for n in receipt.honesty_notes)


# --------------------------------------------------------------------------- #
# Invariant #2 — overage surfaced explicitly, never hidden.
# --------------------------------------------------------------------------- #
def test_overage_surfaced_when_over_budget():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(ceiling=0.20, planned=2),
        phase_actuals=[_actual(0, cost=0.15), _actual(1, cost=0.20)],
    )
    assert receipt.within_budget is False
    assert receipt.overage_usd == pytest.approx(0.15)
    assert any("OVER BUDGET" in n for n in receipt.honesty_notes)


def test_exactly_at_ceiling_is_within_budget():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(ceiling=0.30, planned=2),
        phase_actuals=[_actual(0, cost=0.15), _actual(1, cost=0.15)],
    )
    assert receipt.within_budget is True
    assert receipt.overage_usd is None


# --------------------------------------------------------------------------- #
# Invariant #3 — completion is the truth; stopped-at named.
# --------------------------------------------------------------------------- #
def test_completed_when_all_planned_phases_ran():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=2),
        phase_actuals=[_actual(0), _actual(1)],
    )
    assert receipt.completion == "completed"
    assert receipt.stopped_at_ordinal is None
    assert receipt.stopped_reason == ""


def test_stopped_early_with_explicit_reason():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=3),
        phase_actuals=[
            _actual(0),
            _actual(1, stop="gate denied: budget headroom exhausted"),
        ],
    )
    assert receipt.completion == "stopped_early"
    assert receipt.stopped_at_ordinal == 1
    assert "budget headroom exhausted" in receipt.stopped_reason


def test_unknown_when_fewer_actuals_no_stop_reason():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=3),
        phase_actuals=[_actual(0)],
    )
    assert receipt.completion == "unknown"
    assert any("no stop reason" in n for n in receipt.honesty_notes)


# --------------------------------------------------------------------------- #
# Invariant #4 — planned-vs-executed exact count.
# --------------------------------------------------------------------------- #
def test_executed_and_skipped_counts():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=4),
        phase_actuals=[_actual(0), _actual(1, stop="time budget exhausted")],
    )
    assert receipt.executed_phase_count == 2
    assert receipt.skipped_phase_count == 2


def test_denied_phase_not_counted_as_executed():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=2),
        phase_actuals=[_actual(0), _actual(1, authorized=False, ran=False, cost=None, stop="gate denied")],
    )
    assert receipt.executed_phase_count == 1
    assert receipt.skipped_phase_count == 0  # both phases reported; one denied


# --------------------------------------------------------------------------- #
# Invariant #5 — every phase actual auditable; denied/errored surfaced.
# --------------------------------------------------------------------------- #
def test_denied_phase_without_stop_reason_surfaced():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=2),
        phase_actuals=[_actual(0), _actual(1, authorized=False, ran=False, cost=None)],
    )
    assert any("denied by the gate" in n for n in receipt.honesty_notes)


def test_errored_phase_without_stop_reason_surfaced():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=2),
        phase_actuals=[_actual(0), _actual(1, errored=True, ran=True, cost=None)],
    )
    assert any("errored without" in n for n in receipt.honesty_notes)


# --------------------------------------------------------------------------- #
# Invariant #6 — findings carried verbatim; 0 shown honestly.
# --------------------------------------------------------------------------- #
def test_findings_aggregated_verbatim():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=2),
        phase_actuals=[
            _actual(0, refs=("finding-a", "finding-b")),
            _actual(1, refs=("finding-c",)),
        ],
    )
    assert receipt.total_finding_refs == ("finding-a", "finding-b", "finding-c")


def test_zero_findings_shown_honestly():
    receipt = build_run_receipt(
        run_label="MO #1",
        envelope=_envelope(planned=1),
        phase_actuals=[_actual(0, refs=())],
    )
    assert receipt.total_finding_refs == ()


# --------------------------------------------------------------------------- #
# Invariant #7 — deterministic + pure + fail-closed.
# --------------------------------------------------------------------------- #
def test_receipt_id_deterministic():
    args = dict(
        run_label="MO #1",
        envelope=_envelope(planned=2),
        phase_actuals=[_actual(0, cost=0.10), _actual(1, cost=0.20)],
    )
    r1 = build_run_receipt(**args)
    r2 = build_run_receipt(**args)
    assert r1.receipt_id == r2.receipt_id


def test_receipt_id_changes_with_actuals():
    base = dict(run_label="MO #1", envelope=_envelope(planned=1))
    r1 = build_run_receipt(**base, phase_actuals=[_actual(0, cost=0.10)])
    r2 = build_run_receipt(**base, phase_actuals=[_actual(0, cost=0.20)])
    assert r1.receipt_id != r2.receipt_id


def test_blank_run_label_rejected():
    with pytest.raises(RunReceiptError, match="run_label"):
        build_run_receipt(run_label="  ", envelope=_envelope(), phase_actuals=[_actual(0)])


def test_duplicate_ordinal_rejected():
    with pytest.raises(RunReceiptError, match="duplicate"):
        build_run_receipt(
            run_label="MO #1",
            envelope=_envelope(planned=2),
            phase_actuals=[_actual(0), _actual(0)],
        )


def test_unsorted_ordinals_rejected():
    with pytest.raises(RunReceiptError, match="ascending order"):
        build_run_receipt(
            run_label="MO #1",
            envelope=_envelope(planned=2),
            phase_actuals=[_actual(1), _actual(0)],
        )


def test_more_actuals_than_planned_rejected():
    with pytest.raises(RunReceiptError, match="more actuals"):
        build_run_receipt(
            run_label="MO #1",
            envelope=_envelope(planned=1),
            phase_actuals=[_actual(0), _actual(1)],
        )


def test_purity_no_io_imports():
    import inspect

    from substrate.midnight_oil import run_receipt as mod

    src = inspect.getsource(mod)
    for forbidden in ("import os", "import time", "import asyncio", "open(", "datetime.now", "requests"):
        assert forbidden not in src, f"purity breach: {forbidden!r}"


# --------------------------------------------------------------------------- #
# Boundary types frozen.
# --------------------------------------------------------------------------- #
def test_boundary_types_frozen():
    import dataclasses

    for cls in (ApprovedEnvelope, PhaseActual, RunReceipt):
        assert dataclasses.is_dataclass(cls)
