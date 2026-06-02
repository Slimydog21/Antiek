"""Emit helpers for PHASE_ENTER / PHASE_EXIT / PHASE_VERIFY.

Mirrors middleware/constraint_check/events.py — pure functions that
take envelope + payload fields and call
``substrate.event_log.emit_typed`` with the right Pydantic payload.

``phase`` rides on the event envelope (not the payload), so it is
passed as an ``emit_typed`` kwarg. The PhaseLog state machine in
``log.py`` calls these inside a swallow-errors guard so a telemetry
failure can never break a real synthesis — matches the
``_phase_log_safe`` pattern in upstream orchestrate.py.
"""

from __future__ import annotations

import os
import sys

try:
    from ...event_log import emit_typed
    from ...schemas import (
        PhaseEnterPayload,
        PhaseExitPayload,
        PhaseVerifyPayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        PhaseEnterPayload,
        PhaseExitPayload,
        PhaseVerifyPayload,
    )


_DEFAULT_POLICY_ID = "orchestrator-deterministic"


def emit_phase_enter(
    *,
    investigation_id: str,
    phase: int,
    entered_at: str,
    note: str | None = None,
    metadata_json: str | None = None,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit one PHASE_ENTER event."""
    return emit_typed(
        investigation_id,
        PhaseEnterPayload(
            entered_at=entered_at,
            note=note,
            metadata_json=metadata_json,
        ),
        parent_event_id=parent_event_id,
        phase=int(phase),
        role="phase_log",
        policy_id=_DEFAULT_POLICY_ID,
    )


def emit_phase_exit(
    *,
    investigation_id: str,
    phase: int,
    exited_at: str,
    outputs_hash: str | None = None,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit one PHASE_EXIT event. ``outputs_hash`` is the SHA-256 of
    the phase's output artifacts (paths + contents) when the caller
    computed one; None when the phase produced no concrete outputs."""
    return emit_typed(
        investigation_id,
        PhaseExitPayload(
            exited_at=exited_at,
            outputs_hash=outputs_hash,
        ),
        parent_event_id=parent_event_id,
        phase=int(phase),
        role="phase_log",
        policy_id=_DEFAULT_POLICY_ID,
    )


def emit_phase_verify(
    *,
    investigation_id: str,
    phase: int,
    verified_at: str,
    verification_evidence: str,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit one PHASE_VERIFY event. Load-bearing for Phase 8: without a
    verify event the knowledge graph did not actually compound, and Phase
    9 readiness must refuse to advance."""
    return emit_typed(
        investigation_id,
        PhaseVerifyPayload(
            verified_at=verified_at,
            verification_evidence=verification_evidence,
        ),
        parent_event_id=parent_event_id,
        phase=int(phase),
        role="phase_log",
        policy_id=_DEFAULT_POLICY_ID,
    )
