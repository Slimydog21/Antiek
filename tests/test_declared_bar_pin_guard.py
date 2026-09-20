"""The declared-bar gate must refuse to render a verdict with the wrong tool.

tools/lints/baselines/* are keyed by (path, line, col, code) against the EXACT
ruff/mypy versions recorded in tools/lints/constraints.txt. Run a different
version and the finding set shifts underneath the baseline, so the subtraction
stops meaning anything and the gate reports a confident wrong answer.

This is not hypothetical. On 2026-09-20 a developer machine had `mypy` on PATH
resolving to an unrelated 1.19.1 while the pin is 2.1.0. 1.19.1 predates PEP
695, so at the first `def f[T](...)` it emitted `syntax` and the gate reported
that as a NEW violation in a file nobody had touched.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tools.lints import declared_bar as db


def test_pin_is_readable_and_concrete() -> None:
    """The pins must exist and look like versions -- otherwise every other
    assertion here is vacuous."""
    for tool in ("ruff", "mypy"):
        pin = db._pinned_version(tool)
        assert pin, f"no pin recorded for {tool}"
        assert pin[0].isdigit(), f"{tool} pin {pin!r} is not a version"


def test_wrong_version_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mismatched tool version must raise, not silently produce findings."""
    expected = db._pinned_version("mypy")
    wrong = "0.0.1"
    assert wrong != expected

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(argv, 0, f"mypy {wrong}\n", "")

    monkeypatch.setattr(db.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as excinfo:
        db._assert_pinned_version("mypy", "mypy")
    msg = str(excinfo.value)
    assert wrong in msg and expected in msg, "error must name both versions"
    assert "constraints.txt" in msg, "error must point at the pin source"


def test_matching_version_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must NOT fire on the pinned version -- a guard that always
    raises is as useless as one that never does."""
    expected = db._pinned_version("ruff")

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(argv, 0, f"ruff {expected}\n", "")

    monkeypatch.setattr(db.subprocess, "run", fake_run)
    db._assert_pinned_version("ruff", "ruff")  # must not raise


def test_guard_runs_before_the_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_mypy must check the version BEFORE parsing output, so a wrong
    version can never contribute findings."""
    calls: list[str] = []

    def fake_assert(binary: str, tool: str) -> None:
        calls.append("guard")
        raise RuntimeError("version mismatch (stub)")

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append("tool")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(db, "_assert_pinned_version", fake_assert)
    monkeypatch.setattr(db.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        db.run_mypy()
    assert calls == ["guard"], f"tool ran despite a bad version: {calls}"


def test_real_interpreter_mypy_matches_the_pin() -> None:
    """The mypy importable from THIS interpreter should be the pinned one.

    Skipped rather than failed when mypy is absent: this asserts environment
    fidelity, and a missing mypy is a different problem with its own message.
    """
    try:
        import mypy.version  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - environment dependent
        pytest.skip("mypy not importable from this interpreter")
    assert mypy.version.__version__ == db._pinned_version("mypy"), (
        f"interpreter mypy {mypy.version.__version__} != pin "
        f"{db._pinned_version('mypy')} -- {sys.executable} cannot produce a "
        f"verdict the committed baseline is valid for"
    )
