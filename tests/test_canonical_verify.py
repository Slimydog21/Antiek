"""ANT-EXEC-H2V SPR-08 — subprocess tests for scripts/canonical_verify.sh."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "canonical_verify.sh"
PY = ROOT / ".venv" / "bin" / "python"
PASS_FIXTURE = ROOT / "tests" / "fixtures" / "agent_execution" / "handoff_pass.md"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_canonical_verify_profile_exit_zero() -> None:
    proc = _run("profile")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: profile" in proc.stdout


def test_canonical_verify_handoff_pass_fixture() -> None:
    proc = _run("handoff", str(PASS_FIXTURE))
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "HANDOFF_OK" in proc.stdout or "HANDOFF_OK" in proc.stderr
    assert "AUDIT_OK" in proc.stdout


def test_canonical_verify_cascade_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("cascade")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: cascade" in proc.stdout


def test_canonical_verify_deep_research_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("deep-research")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: deep-research" in proc.stdout