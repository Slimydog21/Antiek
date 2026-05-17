"""PhaseLog public exceptions + small helpers.

Kept separate from ``log.py`` so callers (Phase 9 readiness checks,
test fixtures, the operator CLI) can import the exception type
without dragging in the full state-machine implementation.
"""

from __future__ import annotations


class PhaseAssertionError(RuntimeError):
    """Raised by ``PhaseLog.assert_phase_completed`` and
    ``assert_ready_for_completion`` when a required phase did not
    enter, exit, or verify. Phase 9 catches this to gate the kanban
    transition: silent phase skipping is the failure mode the protocol
    is designed to make impossible (autonomous-deep-research SKILL.md
    "ALWAYS execute Phase 8" rule)."""
