"""Tests for substrate.deletion_worker — 30-day SLA cascade delete."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from substrate.deletion_worker import (
    CASCADE_TARGETS,
    CANCELLATION_WINDOW_DAYS,
    DeletionRequest,
    DeletionRequestStatus,
    DeletionResultKind,
    SLA_DAYS,
    process_request,
    run_one_cycle,
)


def _request_at(days_ago: float, *, status=DeletionRequestStatus.PENDING) -> DeletionRequest:
    requested = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return DeletionRequest(
        request_id=f"del-{days_ago}",
        user_id=f"u-{days_ago}",
        status=status,
        requested_at=requested,
        updated_at=requested,
        reason="test",
    )


def _record_cascade(captured: list[str]):
    """Cascade strategy that records the user_id called against it."""
    def strategy(user_id: str) -> dict[str, int]:
        captured.append(user_id)
        return {target: 1 for target in CASCADE_TARGETS}
    return strategy


# ── 7-day cancellation window ──────────────────────────────────


def test_pending_inside_cancellation_window_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=3)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_CANCELLATION_WINDOW
    assert captured == []
    assert result.sla_remaining_days == SLA_DAYS - 3


def test_pending_at_window_edge_processes():
    """Exactly 7 days old → fires cascade (> 7 days strictly)."""
    captured: list[str] = []
    # Just past the 7-day boundary.
    req = _request_at(days_ago=CANCELLATION_WINDOW_DAYS + 0.5)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.COMPLETED
    assert len(captured) == 1


def test_pending_past_window_processes_cascade():
    captured: list[str] = []
    req = _request_at(days_ago=15)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.COMPLETED
    assert captured == [req.user_id]
    # All cascade targets reported deleted rows.
    assert set(result.rows_deleted.keys()) == set(CASCADE_TARGETS)


# ── Terminal states are skipped ────────────────────────────────


def test_cancelled_request_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=10, status=DeletionRequestStatus.CANCELLED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_ALREADY_TERMINAL
    assert captured == []


def test_completed_request_skipped_idempotent_replay():
    captured: list[str] = []
    req = _request_at(days_ago=10, status=DeletionRequestStatus.COMPLETED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_ALREADY_TERMINAL
    assert captured == []


def test_failed_request_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=10, status=DeletionRequestStatus.FAILED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_ALREADY_TERMINAL


# ── Cascade error handling ─────────────────────────────────────


def test_cascade_exception_yields_failed_result():
    def bad_cascade(user_id: str) -> dict[str, int]:
        raise RuntimeError("DB unreachable")

    req = _request_at(days_ago=15)
    result = process_request(req, cascade=bad_cascade)
    assert result.kind == DeletionResultKind.FAILED
    assert result.error == "DB unreachable"
    # SLA timing still reported.
    assert result.sla_remaining_days is not None


# ── SLA remaining days ─────────────────────────────────────────


def test_sla_remaining_zero_at_or_past_30_days():
    captured: list[str] = []
    req = _request_at(days_ago=35)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.COMPLETED
    assert result.sla_remaining_days == 0  # max(0, 30-35) = 0


def test_sla_remaining_positive_when_within_window():
    captured: list[str] = []
    req = _request_at(days_ago=10)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.sla_remaining_days == SLA_DAYS - 10


# ── run_one_cycle ───────────────────────────────────────────────


def test_run_one_cycle_processes_all_requests():
    captured: list[str] = []
    requests = [
        _request_at(days_ago=15),  # COMPLETED
        _request_at(days_ago=3),   # SKIPPED window
        _request_at(days_ago=8, status=DeletionRequestStatus.CANCELLED),  # SKIPPED terminal
    ]
    results = run_one_cycle(requests, cascade=_record_cascade(captured))
    assert len(results) == 3
    kinds = [r.kind for r in results]
    assert DeletionResultKind.COMPLETED in kinds
    assert DeletionResultKind.SKIPPED_CANCELLATION_WINDOW in kinds
    assert DeletionResultKind.SKIPPED_ALREADY_TERMINAL in kinds
    # Only one cascade actually fired.
    assert len(captured) == 1


# ── Cascade targets include all the spec-relevant tables ───────


def test_cascade_targets_cover_personal_graph_dependents():
    """Spec §13.2: deletion must unwind chunks, embeddings, derived
    skills, per-user attribution shares. Verify CASCADE_TARGETS
    enumerates these (or their equivalent tables)."""
    targets = set(CASCADE_TARGETS)
    # Spec-named categories.
    assert "documents" in targets  # the source for chunks
    assert "chunks" in targets
    assert "claims" in targets
    assert "claim_evidence" in targets
    assert "user_telemetry_preferences" in targets
    assert "personal_graph_metadata" in targets


# ── Custom clock for deterministic tests ───────────────────────


def test_clock_injection_controls_age():
    fixed_now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    req = DeletionRequest(
        request_id="del-clock",
        user_id="u-1",
        status=DeletionRequestStatus.PENDING,
        requested_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    captured: list[str] = []
    result = process_request(req, cascade=_record_cascade(captured), now=fixed_now)
    # 31 days old → completed; SLA exhausted.
    assert result.kind == DeletionResultKind.COMPLETED
    assert result.sla_remaining_days == 0
