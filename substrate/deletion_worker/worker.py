"""Deletion-request processing — pure-functional cycle."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional


CANCELLATION_WINDOW_DAYS = 7
SLA_DAYS = 30


# Master list of substrate-side cascade-delete targets per user_id.
# Order matters: dependents first so foreign-key-style references
# aren't dangling after cascade.
CASCADE_TARGETS: tuple[str, ...] = (
    "notebook_blocks",
    "notebooks",
    "section_blocks",
    "deliverable_sections",
    "deliverables",
    "claim_evidence",
    "claims",
    "chunks",
    "documents",
    "interviews",
    "interview_projects",
    "investigations",
    "user_telemetry_preferences",
    "personal_graph_metadata",
)


class DeletionRequestStatus(str, enum.Enum):
    PENDING = "pending"
    CANCELLED = "cancelled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class DeletionRequest:
    """The shape one /trust-center/deletion-requests row takes."""

    request_id: str
    user_id: str
    status: DeletionRequestStatus
    requested_at: datetime
    updated_at: datetime
    reason: Optional[str] = None


class DeletionResultKind(str, enum.Enum):
    SKIPPED_CANCELLATION_WINDOW = "skipped_cancellation_window"
    SKIPPED_ALREADY_TERMINAL = "skipped_already_terminal"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class DeletionResult:
    """The outcome of processing one request in one cycle."""

    request_id: str
    user_id: str
    kind: DeletionResultKind
    rows_deleted: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    sla_remaining_days: Optional[int] = None
    error: Optional[str] = None


# A strategy is a Callable that, given a user_id, performs the
# cascade delete and returns {table_name: rows_deleted}.
CascadeDeleteStrategy = Callable[[str], dict[str, int]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def process_request(
    req: DeletionRequest,
    *,
    cascade: CascadeDeleteStrategy,
    now: Optional[datetime] = None,
) -> DeletionResult:
    """Apply the state machine to one request.

    Transitions:
        PENDING (age < 7 days) → SKIPPED_CANCELLATION_WINDOW
        PENDING (age ≥ 7 days) → CONFIRMED (cascade fires)
                              → COMPLETED
        CONFIRMED → COMPLETED (idempotent replay)
        CANCELLED/COMPLETED/FAILED → SKIPPED_ALREADY_TERMINAL
    """
    clock = _normalize(now if now is not None else _now())
    requested = _normalize(req.requested_at)
    age = clock - requested

    if req.status in {
        DeletionRequestStatus.CANCELLED,
        DeletionRequestStatus.COMPLETED,
        DeletionRequestStatus.FAILED,
    }:
        return DeletionResult(
            request_id=req.request_id,
            user_id=req.user_id,
            kind=DeletionResultKind.SKIPPED_ALREADY_TERMINAL,
            reason=f"status={req.status.value}",
        )

    if req.status == DeletionRequestStatus.PENDING:
        if age < timedelta(days=CANCELLATION_WINDOW_DAYS):
            remaining = CANCELLATION_WINDOW_DAYS - age.days
            return DeletionResult(
                request_id=req.request_id,
                user_id=req.user_id,
                kind=DeletionResultKind.SKIPPED_CANCELLATION_WINDOW,
                reason=(
                    f"in {CANCELLATION_WINDOW_DAYS}-day cancellation window; "
                    f"{remaining} days remain"
                ),
                sla_remaining_days=max(0, SLA_DAYS - age.days),
            )

    try:
        rows_deleted = cascade(req.user_id)
    except Exception as e:
        return DeletionResult(
            request_id=req.request_id,
            user_id=req.user_id,
            kind=DeletionResultKind.FAILED,
            error=str(e),
            sla_remaining_days=max(0, SLA_DAYS - age.days),
        )

    return DeletionResult(
        request_id=req.request_id,
        user_id=req.user_id,
        kind=DeletionResultKind.COMPLETED,
        rows_deleted=dict(rows_deleted),
        sla_remaining_days=max(0, SLA_DAYS - age.days),
    )


def run_one_cycle(
    requests: Iterable[DeletionRequest],
    *,
    cascade: CascadeDeleteStrategy,
    now: Optional[datetime] = None,
) -> list[DeletionResult]:
    """Process every request once. The caller persists status
    transitions back to the deletion_requests table."""
    return [
        process_request(req, cascade=cascade, now=now)
        for req in requests
    ]
