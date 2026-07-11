"""Red-proof tests for unattended launch gate."""

from __future__ import annotations

import pytest

from substrate.midnight_oil.unattended_launch_gate import (
    LaunchGateError,
    evaluate_unattended_launch_gate,
)


def test_approved_with_receipt_dispatch_ready_not_live() -> None:
    d = evaluate_unattended_launch_gate(
        operator_approved=True,
        consent_receipt_id="rcpt-abc",
        duration_minutes=60,
        goals=["deep research X"],
        approved_ceiling_cents=250,
    )
    body = d.to_dict()
    assert body["dispatch_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["authority"] == "launch_gate_advisory"
    assert body["consent_receipt_id"] == "rcpt-abc"
    assert body["brief"]["live_execution_authorized"] is False


def test_approved_zero_ceiling_dry_run() -> None:
    d = evaluate_unattended_launch_gate(
        operator_approved=True,
        consent_receipt_id=None,
        duration_minutes=30,
        goals=["read only"],
        approved_ceiling_cents=0,
    )
    assert d.dispatch_ready is True
    assert d.zero_ceiling_dry_run is True
    assert d.live_execution_authorized is False


def test_ceiling_without_receipt_not_ready() -> None:
    d = evaluate_unattended_launch_gate(
        operator_approved=True,
        consent_receipt_id=None,
        duration_minutes=60,
        goals=["x"],
        approved_ceiling_cents=100,
    )
    assert d.dispatch_ready is False
    assert any("consent_receipt_id" in r for r in d.reasons)


def test_not_approved_not_ready() -> None:
    d = evaluate_unattended_launch_gate(
        operator_approved=False,
        consent_receipt_id="rcpt",
        duration_minutes=60,
        goals=["x"],
        approved_ceiling_cents=100,
    )
    assert d.dispatch_ready is False
    assert any("operator_approved" in r for r in d.reasons)


def test_operator_approved_must_be_bool() -> None:
    with pytest.raises(LaunchGateError, match="operator_approved"):
        evaluate_unattended_launch_gate(
            operator_approved="yes",  # type: ignore[arg-type]
            duration_minutes=60,
            goals=["x"],
            approved_ceiling_cents=0,
        )


def test_invalid_brief_surfaces() -> None:
    with pytest.raises(LaunchGateError, match="invalid brief"):
        evaluate_unattended_launch_gate(
            operator_approved=True,
            duration_minutes=0,
            goals=["x"],
            approved_ceiling_cents=0,
        )


def test_never_sets_live_true_in_to_dict() -> None:
    d = evaluate_unattended_launch_gate(
        operator_approved=True,
        consent_receipt_id="r",
        duration_minutes=60,
        goals=["x"],
        approved_ceiling_cents=1,
    )
    # Mutating attempt simulation: to_dict always forces false
    out = d.to_dict()
    assert out["live_execution_authorized"] is False
