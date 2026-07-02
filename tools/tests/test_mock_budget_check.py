"""Tests for tools.lint.mock_budget_check — per-module mock-ratio lock.

Assert the gate's OUTPUT (exit code + reports) against fixture census/baseline
JSON. Do not mock the gate internals.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.lint import mock_budget_check as mbc

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mock_budget"
REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [PYTHON, "-m", "tools.lint.mock_budget_check", *args]
    return subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Ratchet: regression reds, improvement passes, stale surfaces tightening
# ---------------------------------------------------------------------------


def test_capture_then_enforce_exits_clean(tmp_path: Path) -> None:
    baseline = tmp_path / "mock_budget.json"
    census = FIXTURES / "census_at_baseline.json"
    cap = _run_gate(
        "capture",
        "--baseline-file", str(baseline),
        "--census-file", str(census),
        "--root", str(REPO),
    )
    assert cap.returncode == 0, cap.stderr
    enf = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(census),
        "--root", str(REPO),
    )
    assert enf.returncode == 0, enf.stderr


def test_enforce_reds_on_upward_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "mock_budget.json"
    baseline.write_text((FIXTURES / "baseline.json").read_text())
    enf = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(FIXTURES / "census_regressed.json"),
        "--root", str(REPO),
    )
    assert enf.returncode == 1
    assert "REGRESSED: tests/fixture_alpha.py" in enf.stdout
    assert "0.5000 -> 0.6000" in enf.stdout
    assert "test_new_mock" in enf.stdout


def test_improvement_passes_enforce_and_shows_stale(tmp_path: Path) -> None:
    baseline = tmp_path / "mock_budget.json"
    baseline.write_text((FIXTURES / "baseline.json").read_text())
    enf = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(FIXTURES / "census_improved.json"),
        "--root", str(REPO),
    )
    assert enf.returncode == 0
    stale = _run_gate(
        "stale",
        "--baseline-file", str(baseline),
        "--census-file", str(FIXTURES / "census_improved.json"),
        "--root", str(REPO),
    )
    assert stale.returncode == 0
    assert "stale: tests/fixture_alpha.py" in stale.stdout
    assert "0.5000 -> 0.4000" in stale.stdout


def test_new_module_is_unlocked_not_red(tmp_path: Path) -> None:
    baseline = tmp_path / "mock_budget.json"
    baseline.write_text((FIXTURES / "baseline.json").read_text())
    enf = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(FIXTURES / "census_with_new_module.json"),
        "--root", str(REPO),
    )
    assert enf.returncode == 0
    assert "unlocked: tests/fixture_gamma.py" in enf.stdout


def test_enforce_never_mutates_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "mock_budget.json"
    baseline.write_text((FIXTURES / "baseline.json").read_text())
    before = _sha256(baseline)
    _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(FIXTURES / "census_regressed.json"),
        "--root", str(REPO),
    )
    after = _sha256(baseline)
    assert before == after


def test_remint_requires_capture(tmp_path: Path) -> None:
    """The only way to raise a lock is a deliberate capture re-mint."""
    baseline = tmp_path / "mock_budget.json"
    baseline.write_text((FIXTURES / "baseline.json").read_text())
    regressed = FIXTURES / "census_regressed.json"

    enf = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(regressed),
        "--root", str(REPO),
    )
    assert enf.returncode == 1
    data_before = json.loads(baseline.read_text())
    assert data_before["modules"]["tests/fixture_alpha.py"]["locked_ratio"] == 0.5

    cap = _run_gate(
        "capture",
        "--baseline-file", str(baseline),
        "--census-file", str(regressed),
        "--root", str(REPO),
    )
    assert cap.returncode == 0
    data_after = json.loads(baseline.read_text())
    assert data_after["modules"]["tests/fixture_alpha.py"]["locked_ratio"] == 0.6

    enf2 = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(regressed),
        "--root", str(REPO),
    )
    assert enf2.returncode == 0


def test_baseline_shape_on_capture(tmp_path: Path) -> None:
    baseline = tmp_path / "mock_budget.json"
    census = FIXTURES / "census_at_baseline.json"
    mbc.run_capture(
        baseline_file=baseline,
        root=REPO,
        census_file=census,
        tests_dir=None,
    )
    data = json.loads(baseline.read_text())
    assert "captured_at" in data
    assert data["census_tree_sha"] == "fixture-baseline-sha"
    assert "suite_locked_mock_ratio" in data
    alpha = data["modules"]["tests/fixture_alpha.py"]
    assert alpha == {"locked_ratio": 0.5, "n_tests": 4}


def test_gate_does_not_recompute_mock_ratio() -> None:
    """No mock-classification logic — only census load."""
    src = (REPO / "tools" / "lint" / "mock_budget_check.py").read_text()
    forbidden = (
        "BEHAVIORAL_TARGET_HINTS",
        "uses_mock is True",
        "ast.parse",
        "analyse_file",
        "discover_test_files",
    )
    for token in forbidden:
        assert token not in src, f"gate must not recompute mocks; found {token!r}"


@pytest.mark.parametrize("epsilon,expect_red", [(0.0, True), (0.15, False)])
def test_epsilon_band(tmp_path: Path, epsilon: float, expect_red: bool) -> None:
    baseline = tmp_path / "mock_budget.json"
    baseline.write_text((FIXTURES / "baseline.json").read_text())
    enf = _run_gate(
        "enforce",
        "--baseline-file", str(baseline),
        "--census-file", str(FIXTURES / "census_regressed.json"),
        "--root", str(REPO),
        "--epsilon", str(epsilon),
    )
    if expect_red:
        assert enf.returncode == 1
    else:
        assert enf.returncode == 0