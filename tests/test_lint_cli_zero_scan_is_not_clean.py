"""A baseline lint that scanned ZERO files is not clean — it is unverified
(2026-09-22 audit, finding #4). Four of these lints are REQUIRED keystone
contexts; a typo'd --paths used to pass byte-identically to a real scan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.lints.baseline import write_baseline
from tools.lints.cli_with_baseline import LINT_REGISTRY, main


def _empty_baseline(path: Path, lint: str) -> None:
    write_baseline(path, lint=LINT_REGISTRY[lint][2], violations=[])


@pytest.mark.parametrize("lint", sorted(LINT_REGISTRY))
def test_enforce_over_a_nonexistent_path_is_exit_2_not_clean(tmp_path: Path, lint: str) -> None:
    baseline = tmp_path / "b.json"
    _empty_baseline(baseline, lint)
    rc = main(["enforce", lint, "--paths", str(tmp_path / "no-such-dir"), "--baseline-file", str(baseline)])
    assert rc == 2, f"{lint}: a zero-file scan must be a verification failure, not a pass"


def test_enforce_over_a_dir_with_no_python_is_exit_2(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("no code here\n")
    baseline = tmp_path / "b.json"
    lint = sorted(LINT_REGISTRY)[0]
    _empty_baseline(baseline, lint)
    assert main(["enforce", lint, "--paths", str(tmp_path / "docs"), "--baseline-file", str(baseline)]) == 2


def test_capture_over_a_nonexistent_path_writes_nothing(tmp_path: Path) -> None:
    baseline = tmp_path / "b.json"
    lint = sorted(LINT_REGISTRY)[0]
    assert main(["capture", lint, "--paths", str(tmp_path / "nope"), "--baseline-file", str(baseline)]) == 2
    assert not baseline.exists()


def test_control_a_real_python_file_still_scans(tmp_path: Path) -> None:
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "clean.py").write_text("def f() -> int:\n    return 1\n")
    baseline = tmp_path / "b.json"
    lint = sorted(LINT_REGISTRY)[0]
    assert main(["capture", lint, "--paths", str(src), "--baseline-file", str(baseline)]) == 0
    assert baseline.exists()
    assert main(["enforce", lint, "--paths", str(src), "--baseline-file", str(baseline)]) == 0
