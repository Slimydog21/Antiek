"""The declared bar must reject failed tool processes before parsing output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.lints import declared_bar as db
from tools.lints.baseline import write_baseline


def _mock_tool(
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    status: int,
    stdout: str = "",
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, f"{tool} {db._pinned_version(tool)}\n", "")
        return subprocess.CompletedProcess(argv, status, stdout, "synthetic tool failure")

    monkeypatch.setattr(db.subprocess, "run", fake_run)
    return calls


def _run_tool(tool: str, tmp_path: Path):
    if tool == "ruff":
        return db.run_ruff(cwd=tmp_path)
    return db.run_mypy(targets=["example.py"], cwd=tmp_path)


def _finding_output(tool: str, tmp_path: Path) -> str:
    if tool == "ruff":
        return json.dumps(
            [
                {
                    "filename": str(tmp_path / "example.py"),
                    "location": {"row": 1, "column": 1},
                    "code": "F401",
                }
            ]
        )
    return "example.py:1: error: synthetic finding  [arg-type]\n"


@pytest.mark.parametrize("tool", ["ruff", "mypy"])
@pytest.mark.parametrize("has_finding", [False, True])
def test_negative_tool_result_is_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str, has_finding: bool
) -> None:
    stdout = _finding_output(tool, tmp_path) if has_finding else ""
    calls = _mock_tool(monkeypatch, tool, -1, stdout)
    with pytest.raises(RuntimeError, match=f"{tool} exited -1"):
        _run_tool(tool, tmp_path)
    assert calls[0][-1] == "--version"
    assert len(calls) == 2


@pytest.mark.parametrize("tool", ["ruff", "mypy"])
def test_negative_tool_result_makes_enforce_exit_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str
) -> None:
    _mock_tool(monkeypatch, tool, -1)
    baseline = tmp_path / "baseline.json"
    write_baseline(baseline, lint=f"declared_bar_{tool}", violations=[])
    assert db.main(["enforce", tool, "--baseline-file", str(baseline)]) == 2


@pytest.mark.parametrize("tool", ["ruff", "mypy"])
def test_ordinary_tool_failure_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str
) -> None:
    _mock_tool(monkeypatch, tool, 2)
    with pytest.raises(RuntimeError, match=f"{tool} exited 2"):
        _run_tool(tool, tmp_path)


@pytest.mark.parametrize("tool", ["ruff", "mypy"])
@pytest.mark.parametrize("status", [0, 1])
def test_clean_and_parseable_findings_keep_their_meaning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str, status: int
) -> None:
    stdout = _finding_output(tool, tmp_path)
    _mock_tool(monkeypatch, tool, status, stdout if status == 1 else "")
    findings = _run_tool(tool, tmp_path)
    assert len(findings) == status


@pytest.mark.parametrize("tool", ["ruff", "mypy"])
def test_unparseable_findings_still_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str
) -> None:
    _mock_tool(monkeypatch, tool, 1, "unparseable output")
    with pytest.raises(RuntimeError, match="unreadable report"):
        _run_tool(tool, tmp_path)
