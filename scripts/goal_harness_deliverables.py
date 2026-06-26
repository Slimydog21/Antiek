"""Goal harness registry — imports prove shipped deep-research + reading paths exist."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Re-export canonical entrypoints (do not mock in goal tests).
from interfaces.reading.kb_artifact import consume_kb_artifact  # noqa: F401
from orchestration.phase_runner import enter_phase, exit_phase, verify_phase  # noqa: F401
from substrate.research_artifact.projection_verify import (  # noqa: F401
    verify_kb_projection,
)
from substrate.research_artifact.reading_surface import (  # noqa: F401
    kb_artifact_minimal_fixture_path,
)

HARNESS_ROOT = ROOT
VERIFICATION_SCRIPT = ROOT / "scripts" / "run_goal_verification_plan.sh"


def assert_goal_deliverables_on_disk() -> None:
    """Mechanical audit used by tests and goal evidence capture."""
    fixture = kb_artifact_minimal_fixture_path()
    if not fixture.is_file():
        raise FileNotFoundError(fixture)
    if not VERIFICATION_SCRIPT.is_file():
        raise FileNotFoundError(VERIFICATION_SCRIPT)