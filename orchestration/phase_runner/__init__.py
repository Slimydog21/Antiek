"""Phase runner (Sprint 8 day 1 — orchestration substrate).

Library API + CLI on top of ``orchestration.phase_log.PhaseLog`` and
(Day 2) ``orchestration.phase_runner.postconditions``. The Loop 1
orchestrator (Sprint 8 day 3) calls these library functions between
phase transitions to enforce the 9-phase protocol mechanically.

Day 1 ships:

- ``runner`` module — library API (enter / exit / verify / assert /
  status / precondition). Callable-injected ``PostconditionCheck``.
- ``cli`` module — argparse wrapper mirroring the upstream
  subcommands so operators can drive phase transitions from the
  shell during recovery.

What's deferred to Day 2:

- ``postconditions`` module with the real per-phase checks
  (Phase 6 = synthesis archived, Phase 7 = delivery artifacts
  present, Phase 8 = skill file growth).
- ``orchestration/audit/hub_audit.py`` migration.
"""

from . import postconditions
from .postconditions import (
    CHECKS,
    default_knowledge_skills_dir,
    default_research_dir,
    run_check,
)
from .runner import (
    PostconditionCheck,
    PreconditionOutcome,
    VerifyOutcome,
    assert_phase,
    assert_ready_for_completion,
    check_precondition,
    enter_phase,
    exit_phase,
    phase_status,
    verify_phase,
)

__all__ = [
    "PostconditionCheck",
    "PreconditionOutcome",
    "VerifyOutcome",
    "check_precondition",
    "enter_phase",
    "exit_phase",
    "verify_phase",
    "assert_phase",
    "assert_ready_for_completion",
    "phase_status",
    # postconditions
    "postconditions",
    "CHECKS",
    "run_check",
    "default_research_dir",
    "default_knowledge_skills_dir",
]
