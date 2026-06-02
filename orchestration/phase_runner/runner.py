"""Phase runner library (Sprint 8 day 1 — orchestration substrate
closes here).

A thin coordinator on top of ``PhaseLog`` that the Loop 1
orchestrator (Day 3) calls between phase transitions. Composes:

- ``orchestration.phase_log.PhaseLog`` for the state machine
  (enter / exit / verify + typed PHASE_* event mirror landed
  Sprint 5 day 3-4).
- Callable-injected ``PostconditionCheck`` for the artifact-level
  gate. Day 2 ships ``orchestration.phase_runner.postconditions``
  with the real per-phase checks; until then the default no-op
  returns ``(True, "(no postcondition registered)")``.

Public API:

- ``enter_phase(investigation_id, phase, *, topic="", ...)``
- ``exit_phase(investigation_id, phase, *, outputs_paths=None, outputs_hash=None)``
- ``verify_phase(investigation_id, phase, *, postcondition_check=None) -> VerifyOutcome``
- ``assert_phase(investigation_id, phase)`` — re-export
- ``assert_ready_for_completion(investigation_id)`` — re-export
- ``check_precondition(investigation_id, phase) -> PreconditionOutcome``
- ``phase_status(investigation_id, *, postcondition_check=None) -> dict``

Discipline carried verbatim from upstream:

- ``verify`` is the load-bearing gate. On postcondition failure, the
  phase log is NOT marked verified; a subsequent assertion will
  refuse to advance. This is what makes Phase 8 mechanically
  enforceable rather than prose-only.
- Preconditions are computed from ``AUTONOMOUS_RESEARCH_PHASES``
  order: phase N requires every prior phase in the canonical tuple
  to be both entered AND exited. (Verification is NOT required for
  precondition — Phase 8's verify gate is checked separately by
  ``assert_ready_for_completion``.)
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from ...constants import (
        AUTONOMOUS_RESEARCH_PHASES,
        AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        AUTONOMOUS_RESEARCH_PHASES,
        AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
    )

from ..phase_log import PhaseAssertionError, PhaseLog

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


# Signature of the postcondition check the orchestrator can inject.
# Returns ``(passed, reason)``; ``reason`` becomes the verify-evidence
# string on pass and the stderr message on failure.
PostconditionCheck = Callable[[int, str], tuple[bool, str]]


def _default_postcondition_check(phase: int, investigation_id: str) -> tuple[bool, str]:
    """Default no-op postcondition. Day 2's postconditions module
    will replace this with the real per-phase checks; until then a
    verify call passes structurally (phase was entered + exited) and
    the recorded evidence captures that no domain check was
    configured."""
    return True, "(no postcondition registered)"


@dataclass(frozen=True)
class VerifyOutcome:
    """Result of ``verify_phase``. When ``passed`` is False, the phase
    log was NOT marked verified — a subsequent assertion will refuse
    to advance until either the check passes or the operator
    explicitly overrides."""

    passed: bool
    reason: str


@dataclass(frozen=True)
class PreconditionOutcome:
    """Result of ``check_precondition``. ``missing_phases`` lists the
    prior phases that haven't both entered AND exited yet — empty
    list means the phase is safe to enter."""

    ok: bool
    missing_phases: tuple[int, ...]
    reason: str


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


def check_precondition(
    investigation_id: str,
    phase: int,
    *,
    log_dir: str | None = None,
) -> PreconditionOutcome:
    """Verify every phase before ``phase`` in ``AUTONOMOUS_RESEARCH_PHASES``
    has been entered AND exited. Does NOT require verification — the
    verify gate is a separate concern enforced at completion time.

    Returns ``PreconditionOutcome(ok=True, ...)`` when the phase is
    safe to enter. ``ok=False`` carries the list of missing phases so
    the caller can either enter them or surface the gap."""
    if phase not in AUTONOMOUS_RESEARCH_PHASES:
        return PreconditionOutcome(
            ok=False, missing_phases=(),
            reason=(
                f"phase {phase} is not in AUTONOMOUS_RESEARCH_PHASES "
                f"({AUTONOMOUS_RESEARCH_PHASES})"
            ),
        )

    # First phase in the protocol has no precondition.
    if phase == AUTONOMOUS_RESEARCH_PHASES[0]:
        return PreconditionOutcome(
            ok=True, missing_phases=(), reason="first phase — no precondition",
        )

    log = PhaseLog.open(investigation_id, log_dir=log_dir)
    phases_data = log.data.get("phases", {})

    # Required prior phases = every phase strictly before ``phase`` in
    # the canonical tuple. Each must have both entered_at AND exited_at.
    missing: list[int] = []
    for prior in AUTONOMOUS_RESEARCH_PHASES:
        if prior >= phase:
            break
        rec = phases_data.get(str(prior), {})
        if not rec.get("entered_at") or not rec.get("exited_at"):
            missing.append(prior)

    if missing:
        return PreconditionOutcome(
            ok=False, missing_phases=tuple(missing),
            reason=(
                f"phase {phase} requires prior phases {missing} to be "
                "entered AND exited first"
            ),
        )
    return PreconditionOutcome(
        ok=True, missing_phases=(),
        reason="all prior phases entered + exited",
    )


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


def enter_phase(
    investigation_id: str,
    phase: int,
    *,
    topic: str = "",
    note: str | None = None,
    metadata_json: str | None = None,
    enforce_precondition: bool = True,
    log_dir: str | None = None,
) -> None:
    """Mark a phase entered. Raises ``PhaseAssertionError`` when
    ``enforce_precondition=True`` and a prior phase hasn't been
    completed — the operator can pass ``enforce_precondition=False``
    for recovery scenarios where a phase needs to be re-entered out
    of order."""
    if enforce_precondition:
        outcome = check_precondition(
            investigation_id, phase, log_dir=log_dir,
        )
        if not outcome.ok:
            raise PhaseAssertionError(outcome.reason)
    log = PhaseLog.open(investigation_id, topic=topic, log_dir=log_dir)
    log.enter(phase, note=note, metadata_json=metadata_json)


def exit_phase(
    investigation_id: str,
    phase: int,
    *,
    outputs_paths: list[str] | None = None,
    outputs_hash: str | None = None,
    log_dir: str | None = None,
) -> None:
    """Mark a phase exited. The phase log's atomic-write + typed
    PHASE_EXIT mirror handle persistence + telemetry."""
    log = PhaseLog.open(investigation_id, log_dir=log_dir)
    log.exit(
        phase,
        outputs_paths=outputs_paths or None,
        outputs_hash=outputs_hash,
    )


def verify_phase(
    investigation_id: str,
    phase: int,
    *,
    postcondition_check: PostconditionCheck | None = None,
    log_dir: str | None = None,
) -> VerifyOutcome:
    """Run the postcondition check; on pass, mark the phase verified
    via ``PhaseLog.verify`` with the check's reason as evidence.

    **The keystone subcommand.** On failure, the phase log is NOT
    updated — a subsequent ``assert_phase`` or
    ``assert_ready_for_completion`` will refuse to advance. This is
    what converts "ALWAYS execute Phase 8" from prose into a code-
    level invariant the orchestrator must satisfy.
    """
    check = postcondition_check or _default_postcondition_check
    passed, reason = check(phase, investigation_id)
    if not passed:
        print(
            f"phase_runner: phase {phase} postcondition FAILED — {reason}",
            file=sys.stderr,
        )
        return VerifyOutcome(passed=False, reason=reason)
    log = PhaseLog.open(investigation_id, log_dir=log_dir)
    log.verify(phase, evidence=reason or "(no reason)")
    return VerifyOutcome(passed=True, reason=reason)


# ---------------------------------------------------------------------------
# Assertions (re-exports)
# ---------------------------------------------------------------------------


def assert_phase(
    investigation_id: str,
    phase: int,
    *,
    log_dir: str | None = None,
) -> None:
    """Raise ``PhaseAssertionError`` when the phase did not pass
    verification. Mirrors ``PhaseLog.assert_phase_completed``."""
    log = PhaseLog.open(investigation_id, log_dir=log_dir)
    log.assert_phase_completed(phase)


def assert_ready_for_completion(
    investigation_id: str,
    *,
    log_dir: str | None = None,
) -> None:
    """Phase 9 gate. Raises on any required phase that did not
    verify (default: phases 6, 7, 8 per
    ``AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION``)."""
    log = PhaseLog.open(investigation_id, log_dir=log_dir)
    log.assert_ready_for_completion()


# ---------------------------------------------------------------------------
# Status (observe-only)
# ---------------------------------------------------------------------------


def phase_status(
    investigation_id: str,
    *,
    postcondition_check: PostconditionCheck | None = None,
    log_dir: str | None = None,
) -> dict[str, Any]:
    """Snapshot of the phase log PLUS a live re-run of every entered
    phase's postcondition. The live check does NOT modify the log —
    observe-only diagnostic for the operator CLI / dashboards."""
    log = PhaseLog.open(investigation_id, log_dir=log_dir)
    snap = log.snapshot()

    check = postcondition_check or _default_postcondition_check
    live: dict[str, dict[str, Any]] = {}
    phases = snap.get("phases", {})
    for phase_str in sorted(phases.keys(), key=int):
        try:
            phase_num = int(phase_str)
        except ValueError:
            continue
        passed, reason = check(phase_num, investigation_id)
        live[phase_str] = {"passed": passed, "reason": reason}

    return {
        "phase_log": snap,
        "postconditions_live": live,
        "required_for_completion": list(
            AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
        ),
    }
