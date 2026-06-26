#!/usr/bin/env python3
"""antiek check — unified verification CLI (substrate + research workflows).

Goal harness on ``~/Antiek`` delegates ``all`` to ``scripts/run_goal_verification_plan.sh``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _python() -> str:
    venv_py = ROOT / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def run_cmd(label: str, cmd: list[str], *, cwd: Path | None = None) -> bool:
    print(f"→ {label}...")
    result = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return False
    return True


def run_mypy(py: str) -> bool:
    """Strict check on workflow-touched packages (full tree has legacy debt)."""
    targets = [
        "substrate/research_artifact/",
        "orchestration/phase_runner/",
        "orchestration/phase_log/",
        "acquisition/snapshot/",
    ]
    return run_cmd(
        "mypy --strict (workflow packages)",
        [py, "-m", "mypy", "--strict", *targets],
    )


def run_workflows(py: str) -> bool:
    script = ROOT / "scripts" / "canonical_verify.sh"
    if not script.is_file():
        print("✗ missing scripts/canonical_verify.sh", file=sys.stderr)
        return False
    ok = True
    ok &= run_cmd(
        "canonical_verify deep-research",
        ["bash", str(script), "deep-research"],
    )
    ok &= run_cmd(
        "canonical_verify html-transport",
        ["bash", str(script), "html-transport"],
    )
    ok &= run_cmd(
        "goal + KB static workflow tests",
        [
            py,
            "-m",
            "pytest",
            "tests/test_goal_harness_deliverables.py",
            "tests/test_goal_workflow_verification.py",
            "tests/test_reading_kb_artifact.py",
            "tests/test_research_artifact_kb_static.py",
            "tests/test_research_artifact_hooks.py",
            "-q",
            "--tb=short",
        ],
    )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Antiek unified verification")
    parser.add_argument(
        "check",
        nargs="?",
        default="all",
        choices=["all", "mypy", "workflows"],
    )
    args = parser.parse_args()
    py = _python()
    success = True
    if args.check == "mypy":
        success &= run_mypy(py)
    if args.check in ("all", "workflows"):
        success &= run_workflows(py)
    if success:
        print("\n✓ All checks passed")
        return 0
    print("\n✗ Some checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())