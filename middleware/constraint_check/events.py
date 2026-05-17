"""Emit helpers for the 3 typed constraint payloads.

Mirrors the pattern in middleware/source_tier/rules.py and
middleware/archive/archive.py — pure functions that take envelope +
payload fields and call ``substrate.event_log.emit_typed`` with the
right Pydantic payload.

The constraint-loop machinery (Sprint 5) calls these helpers; the
helpers don't drive the loop themselves.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Optional

try:
    from ...event_log import emit_typed
    from ...schemas import (
        ConstraintLoopResolvedPayload,
        ConstraintRevisionTriggeredPayload,
        ConstraintViolationFoundPayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        ConstraintLoopResolvedPayload,
        ConstraintRevisionTriggeredPayload,
        ConstraintViolationFoundPayload,
    )

from .constraints import Violation


def emit_constraint_violation_found(
    *,
    investigation_id: str,
    iteration: int,
    violation: Violation,
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit one CONSTRAINT_VIOLATION_FOUND event. Called once per
    violation per iteration — a high-violation iteration produces many
    of these in sequence."""
    return emit_typed(
        investigation_id,
        ConstraintViolationFoundPayload(
            constraint_id=violation.constraint_id,
            strictness=violation.strictness,  # type: ignore[arg-type]
            constraint_kind=violation.constraint_kind,  # type: ignore[arg-type]
            iteration=int(iteration),
            target_claim_id=violation.target_claim_id,
            reason=violation.reason,
        ),
        parent_event_id=parent_event_id,
        role="constraint_checker",
    )


def emit_constraint_revision_triggered(
    *,
    investigation_id: str,
    iteration: int,
    triggering_constraint_ids: Iterable[str],
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit a CONSTRAINT_REVISION_TRIGGERED event when the loop
    decides to re-invoke the synthesizer because at least one HARD
    constraint is still violated. The ``triggering_constraint_ids``
    list lets cohort analysis correlate which constraint kinds
    consume the most iterations."""
    return emit_typed(
        investigation_id,
        ConstraintRevisionTriggeredPayload(
            iteration=int(iteration),
            triggering_constraint_ids=list(triggering_constraint_ids),
        ),
        parent_event_id=parent_event_id,
        role="constraint_checker",
    )


def emit_constraint_loop_resolved(
    *,
    investigation_id: str,
    final_status: str,
    total_iterations: int,
    final_violation_count: int,
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit exactly one CONSTRAINT_LOOP_RESOLVED event on loop
    termination. The ``final_status`` mirrors the Researchmaxx
    terminal vocabulary so a migrated cohort backtest stays
    compatible (status NOT IN ('passed', 'single_pass') ⇒ escalation)."""
    return emit_typed(
        investigation_id,
        ConstraintLoopResolvedPayload(
            final_status=final_status,  # type: ignore[arg-type]
            total_iterations=int(total_iterations),
            final_violation_count=int(final_violation_count),
        ),
        parent_event_id=parent_event_id,
        role="constraint_checker",
    )
