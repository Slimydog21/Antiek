"""A linter killed by a signal must not read as clean.

`tools/lints/declared_bar.py` runs ruff and mypy and refuses to treat a tool
that did not produce a finding list as a clean run. Its guards tested
`returncode >= 2`, which covers a normal failure (bad pyproject config, unknown
rule, INTERNAL ERROR) but NOT a child that dies by signal: `subprocess` reports
-15 for SIGTERM and -9 for SIGKILL, and both are less than 2 and not equal to 1.

So on a runner that OOM-kills or times out the linter — the ordinary way a
linter dies without producing findings — the gate returned 0: a REQUIRED check
green over a tool that never ran. That is the same false green the surrounding
comments were written to prevent, one return code to the left of the one they
guarded.

Verified directly rather than assumed:

    SIGKILL returncode: -9    SIGTERM returncode: -15
    rc=-9 : ">=2" False, "==1 and empty" False, "not in (0, 1)" True
    rc=-15: ">=2" False, "==1 and empty" False, "not in (0, 1)" True

The fix tests the two codes that mean "the tool ran", instead of a threshold.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.lints import declared_bar as db

# The codes CPython reports for a child killed by these signals. Not guessed:
# reproduce with a Popen, `.kill()` / `.terminate()`, then read `.returncode`.
SIGNAL_CODES = (-15, -9)


def _fake_run(returncode: int, stdout: str = "", stderr: str = "killed by signal"):
    """Stand in for subprocess.run returning a signal-killed child."""

    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )

    return run


def _pin_ok(monkeypatch):
    """Skip the pinned-version probe so the test reaches the return-code guard."""
    monkeypatch.setattr(db, "_assert_pinned_version", lambda *_a, **_k: None)


@pytest.mark.parametrize("returncode", SIGNAL_CODES)
def test_signal_killed_ruff_is_a_tool_failure(monkeypatch, returncode):
    _pin_ok(monkeypatch)
    monkeypatch.setattr(db.subprocess, "run", _fake_run(returncode))
    with pytest.raises(RuntimeError, match="tool failure, not a finding"):
        db.run_ruff("/usr/bin/ruff", Path("."))


@pytest.mark.parametrize("returncode", SIGNAL_CODES)
def test_signal_killed_mypy_is_a_tool_failure(monkeypatch, returncode):
    _pin_ok(monkeypatch)
    monkeypatch.setattr(db.subprocess, "run", _fake_run(returncode, stdout="{}"))
    with pytest.raises(RuntimeError, match="tool failure, not a finding"):
        db.run_mypy(["x.py"], "/usr/bin/mypy", Path("."))


def test_clean_run_is_still_a_clean_run(monkeypatch):
    """The fix must not turn a normal, clean run into a tool failure."""
    _pin_ok(monkeypatch)
    monkeypatch.setattr(db.subprocess, "run", _fake_run(0, stdout="[]"))
    monkeypatch.setattr(db, "parse_ruff_json", lambda *_a, **_k: [])
    assert db.run_ruff("/usr/bin/ruff", Path(".")) == []
