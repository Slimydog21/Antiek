"""ANT-EXEC-H2V SPR-05 — subprocess tests for scripts/agent_ams_ref_lint.sh.

Fixtures:
  - docs/htmlspec/.../sprint-05-ams-bridge.html — NEW: chips + verified paths
  - tests/fixtures/agent_execution/sprint_fiction_chip.html — bare v1 fiction → exit 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "scripts" / "agent_ams_ref_lint.sh"
SPRINT_PAGE = (
    REPO_ROOT
    / "docs/htmlspec/antiek-hard-to-vary-execution/sprint-05-ams-bridge.html"
)
FICTION_FIXTURE = REPO_ROOT / "tests/fixtures/agent_execution/sprint_fiction_chip.html"


def _run_wrapper(*html_paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WRAPPER), *(str(p) for p in html_paths)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_agent_ams_ref_lint_passes_sprint_page() -> None:
    proc = _run_wrapper(SPRINT_PAGE)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "verify_spec_refs" in proc.stdout or "PASS" in proc.stdout


def test_agent_ams_ref_lint_fails_on_fiction_chip_fixture() -> None:
    proc = _run_wrapper(FICTION_FIXTURE)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "FloatingSurface" in combined or "FICTION" in combined