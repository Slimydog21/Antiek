"""Tests for tools.marketplace.programmatic_gate."""

from __future__ import annotations

from substrate.marketplace_metrics import build_snapshot_from_inputs
from tools.marketplace.programmatic_gate import (
    ProgrammaticVerdictKind,
    evaluate_programmatic_gate,
    format_verdict_markdown,
)


def _snapshot_with_spend(current_cents: int, prior_cents: int = 0):
    return build_snapshot_from_inputs(
        creator_paid_cents={},
        publisher_status_rows=[],
        publisher_accrual_cents={},
        publisher_paid_cents={},
        current_advertiser_spend={"_agg": current_cents} if current_cents else {},
        prior_advertiser_spend={"_agg": prior_cents} if prior_cents else {},
    )


def test_zero_spend_defers():
    snapshot = _snapshot_with_spend(0)
    verdict = evaluate_programmatic_gate(snapshot)
    assert verdict.verdict == ProgrammaticVerdictKind.DEFER
    assert verdict.current_monthly_spend_cents == 0
    assert verdict.crosses_programmatic_capacity is False


def test_high_spend_alone_defers_without_hours_signal():
    snapshot = _snapshot_with_spend(30_000_000)  # $300K
    verdict = evaluate_programmatic_gate(snapshot)
    assert verdict.verdict == ProgrammaticVerdictKind.DEFER
    assert "manual-curation hours not measured" in verdict.reasoning


def test_high_spend_with_low_hours_defers():
    snapshot = _snapshot_with_spend(30_000_000)
    verdict = evaluate_programmatic_gate(
        snapshot, operator_manual_hours_per_week=10,
    )
    assert verdict.verdict == ProgrammaticVerdictKind.DEFER
    assert "below threshold" in verdict.reasoning


def test_high_spend_with_high_hours_gos():
    snapshot = _snapshot_with_spend(30_000_000)
    verdict = evaluate_programmatic_gate(
        snapshot, operator_manual_hours_per_week=25,
    )
    assert verdict.verdict == ProgrammaticVerdictKind.GO
    assert verdict.crosses_programmatic_capacity is True


def test_low_spend_with_high_hours_still_defers():
    """Operator pain alone isn't enough — needs the demand signal too."""
    snapshot = _snapshot_with_spend(5_000_000)  # $50K, below capacity
    verdict = evaluate_programmatic_gate(
        snapshot, operator_manual_hours_per_week=30,
    )
    assert verdict.verdict == ProgrammaticVerdictKind.DEFER
    assert "programmatic capacity" in verdict.reasoning


def test_self_service_threshold_independent_of_programmatic():
    """Self-service ($50K) and programmatic ($250K) thresholds are separate.
    Crossing self-service alone does not trigger programmatic."""
    snapshot = _snapshot_with_spend(10_000_000)  # $100K — crosses self-service
    verdict = evaluate_programmatic_gate(
        snapshot, operator_manual_hours_per_week=30,
    )
    assert verdict.crosses_self_service_threshold is True
    assert verdict.crosses_programmatic_capacity is False
    assert verdict.verdict == ProgrammaticVerdictKind.DEFER


def test_format_verdict_markdown_includes_renewal_note_when_defer():
    snapshot = _snapshot_with_spend(0)
    verdict = evaluate_programmatic_gate(snapshot)
    md = format_verdict_markdown(verdict, quarter_label="2026-Q3")
    assert "2026-Q3" in md
    assert "DEFER" in md
    assert "rejection is renewed" in md


def test_format_verdict_markdown_includes_go_next_steps():
    snapshot = _snapshot_with_spend(30_000_000)
    verdict = evaluate_programmatic_gate(
        snapshot, operator_manual_hours_per_week=25,
    )
    md = format_verdict_markdown(verdict)
    assert "GO" in md
    assert "Next steps" in md
    assert "Brand-safety classifier" in md
