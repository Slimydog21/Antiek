"""DeepResearchComplete — single falsifiable terminal contract for deep research.

Loop 1 (Ask) and DRW (Cascade) must converge on this definition before any
investigation is considered a completed deep-research product experience.

Semantics (ANT-DRL SPR-DRL-01):
  * Phases 6–9 postconditions pass (``synthesize.delivered`` with converged
    ``constraint_loop_status`` ∈ {single_pass, passed}, delivery, compounding,
    phase-log readiness).
  * ``investigation.completed`` is present in the trajectory when checking
    retrospective / session-level completion (DRW gather-only paths fail).

The split-brain failure mode this guards: DRW gather-only paths can reach
runner ``DONE`` without synthesis until Path A convergence (SPR-DRL-06).
"""

from __future__ import annotations

from orchestration.phase_runner.postconditions import (  # noqa: E402
    check_phase_6,
    check_phase_7,
    check_phase_8,
    check_phase_9,
    default_knowledge_skills_dir,
    default_research_dir,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import ActionType  # noqa: E402

# Phase postconditions delegated here — keep in sync with
# orchestration/phase_runner/postconditions.py check_phase_6..9.
DEEP_RESEARCH_TERMINAL_PHASES: tuple[int, ...] = (6, 7, 8, 9)


class DeepResearchIncompleteError(Exception):
    """Raised when an investigation has not satisfied DeepResearchComplete."""

    def __init__(self, investigation_id: str, reason: str) -> None:
        self.investigation_id = investigation_id
        self.reason = reason
        super().__init__(f"{investigation_id}: {reason}")


def check_deep_research_complete(
    investigation_id: str,
    *,
    research_dir: str | None = None,
    knowledge_skills_dir: str | None = None,
    require_terminal_event: bool = True,
) -> tuple[bool, str]:
    """Return ``(passed, reason)`` for the DeepResearchComplete contract.

    When ``require_terminal_event`` is False, phases 6–9 are checked only.
    Loop 1 uses this mode immediately before emitting ``investigation.completed``.
    Session reconstruction and DRW negative tests use the default (True).
    """
    failures: list[str] = []

    if require_terminal_event:
        has_completed = any(
            row.get("action_type") == ActionType.INVESTIGATION_COMPLETED.value
            for row in trajectory(investigation_id)
        )
        if not has_completed:
            failures.append("no investigation.completed event in trajectory")

    resolved_research_dir = research_dir or default_research_dir(investigation_id)
    resolved_skills_dir = (
        knowledge_skills_dir or default_knowledge_skills_dir()
    )

    phase_checks = (
        (6, lambda: check_phase_6(investigation_id)),
        (7, lambda: check_phase_7(
            investigation_id, research_dir=resolved_research_dir,
        )),
        (8, lambda: check_phase_8(
            investigation_id, knowledge_skills_dir=resolved_skills_dir,
        )),
        (9, lambda: check_phase_9(investigation_id)),
    )
    assert tuple(p for p, _ in phase_checks) == DEEP_RESEARCH_TERMINAL_PHASES
    for phase, run in phase_checks:
        ok, reason = run()
        if not ok:
            failures.append(f"phase {phase}: {reason}")

    if failures:
        return False, "; ".join(failures)

    terminal_note = (
        ", investigation.completed"
        if require_terminal_event else ""
    )
    return True, (
        f"deep research complete (phases 6-9{terminal_note})"
    )


def assert_deep_research_complete(
    investigation_id: str,
    *,
    research_dir: str | None = None,
    knowledge_skills_dir: str | None = None,
    require_terminal_event: bool = True,
) -> None:
    """Raise ``DeepResearchIncompleteError`` when the contract is not met."""
    ok, reason = check_deep_research_complete(
        investigation_id,
        research_dir=research_dir,
        knowledge_skills_dir=knowledge_skills_dir,
        require_terminal_event=require_terminal_event,
    )
    if not ok:
        raise DeepResearchIncompleteError(investigation_id, reason)