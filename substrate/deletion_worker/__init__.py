"""Deletion worker — Sprint 22 Phase 6 §13.3 30-day SLA enforcement.

Per master-spec §13.3: *"a 'delete everything' button that actually
deletes everything within 30 days."* This module is what makes the
SLA real. Without a worker, the existing
`/trust-center/deletion-requests` endpoint just queues rows — no
substrate-side actor unwinds the user's data.

Discipline:
- `run_one_cycle` is pure-functional over (deletion-requests
  iterator, cascade-delete strategy, clock). No I/O hidden inside.
- 7-day cancellation window before any destructive action
- 30-day SLA from request to completion
- Idempotent on `request_id` — replaying a completion is safe
- Strict per-user scope at cascade-delete time
"""

from .worker import (
    CascadeDeleteStrategy,
    DeletionRequest,
    DeletionRequestStatus,
    DeletionResult,
    DeletionResultKind,
    CASCADE_TARGETS,
    CANCELLATION_WINDOW_DAYS,
    SLA_DAYS,
    run_one_cycle,
    process_request,
)

__all__ = [
    "CASCADE_TARGETS",
    "CANCELLATION_WINDOW_DAYS",
    "CascadeDeleteStrategy",
    "DeletionRequest",
    "DeletionRequestStatus",
    "DeletionResult",
    "DeletionResultKind",
    "SLA_DAYS",
    "process_request",
    "run_one_cycle",
]
