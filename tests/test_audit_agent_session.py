"""ANT-EXEC-H2V SPR-04 — subprocess tests for scripts/audit_agent_session.sh.

Fixtures under tests/fixtures/agent_execution/handoff_*.md:
  - handoff_pass.md — clean session (AUDIT_OK)
  - handoff_fail_pytest_tail.md — F1 pytest|tail theater
  - handoff_fail_platform_ok.md — F3 platform OK without Scope Map
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_agent_session.sh"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "agent_execution"


def _run_audit(*handoff_paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(AUDIT_SCRIPT), *(str(p) for p in handoff_paths)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_audit_pass_fixture() -> None:
    proc = _run_audit(FIXTURES / "handoff_pass.md")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "AUDIT_OK" in proc.stdout


def test_audit_fails_on_pytest_tail_fixture() -> None:
    proc = _run_audit(FIXTURES / "handoff_fail_pytest_tail.md")
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "F1" in combined
    assert "pytest" in combined.lower()


def test_audit_fails_on_platform_ok_without_scope_map_fixture() -> None:
    proc = _run_audit(FIXTURES / "handoff_fail_platform_ok.md")
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "F3" in combined
    assert "Scope Map" in combined or "scope map" in combined.lower()