"""The operator CLI cannot substitute structural success for a missing checker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INVESTIGATION = "cli-checker-regression"


@pytest.fixture
def cli(tmp_path):
    state = tmp_path / "state"
    modules = tmp_path / "modules"
    modules.mkdir()
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "ANTIEK_HOME": str(state),
        "ANTIEK_RESEARCH_PHASE_LOG_DIR": str(state / "phases"),
        "ANTIEK_RESEARCH_EVENTS_DIR": str(state / "events"),
        "ANTIEK_EVENTS_DISABLED": "0",
        "ANTIEK_RESEARCH_DIR": str(state / "research"),
        "PYTHONPATH": os.pathsep.join((str(ROOT), str(modules))),
    }

    def invoke(command, *extra):
        args = [sys.executable, "-m", "orchestration.phase_runner.cli", command,
                "--investigation-id", INVESTIGATION]
        if command != "status":
            args += ["--phase", "1"]
        return subprocess.run(
            [*args, *extra], cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=30,
        )

    for command in ("enter", "exit"):
        result = invoke(command)
        assert result.returncode == 0, result.stderr
    assert (state / "events" / f"{INVESTIGATION}.jsonl").is_file()
    return invoke, state, modules


def snapshot(state):
    return {str(p.relative_to(state)): p.read_bytes()
            for p in state.rglob("*") if p.is_file()}


@pytest.mark.parametrize("command", ["verify", "status"])
@pytest.mark.parametrize("module,source,diagnostic", [
    ("", None, "module"),
    ("   ", None, "module"),
    ("nonexistent_cli_checker", None, "nonexistent_cli_checker"),
    ("broken_checker", "import missing_nested_cli_dependency\n", "missing_nested_cli_dependency"),
    ("crashing_checker", "raise RuntimeError('checker initialization failed')\n", "initialization failed"),
    ("no_check", "other = 1\n", "run_check"),
    ("not_callable", "run_check = 42\n", "run_check"),
])
def test_bad_checker_cannot_verify_or_report_success(cli, command, module, source, diagnostic):
    invoke, state, modules = cli
    if source is not None:
        (modules / f"{module}.py").write_text(source)
    before = snapshot(state)
    result = invoke(command, "--postcondition-module", module)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert diagnostic in result.stderr
    assert not result.stdout
    assert snapshot(state) == before
    assert invoke("assert").returncode == 2


@pytest.mark.parametrize("passed", [True, False])
def test_callable_checker_controls_real_verification_and_status(cli, passed):
    invoke, state, modules = cli
    reason = "artifact accepted" if passed else "artifact missing"
    (modules / "fixture_checker.py").write_text(
        "def run_check(phase, investigation_id):\n"
        f"    assert (phase, investigation_id) == (1, {INVESTIGATION!r})\n"
        f"    return {passed!r}, {reason!r}\n"
    )
    before = snapshot(state)
    options = ("--postcondition-module", "fixture_checker")
    result = invoke("verify", *options)
    assert result.returncode == (0 if passed else 2), result.stderr
    assert reason in result.stdout + result.stderr
    phase = json.loads((state / "phases" / f"{INVESTIGATION}.json").read_text())["phases"]["1"]
    assert bool(phase.get("verified")) is passed
    if passed:
        assert phase["verification_evidence"] == reason
        events = [json.loads(line) for line in
                  (state / "events" / f"{INVESTIGATION}.jsonl").read_text().splitlines()]
        assert len(events) == 3
        assert events[-1]["action_type"] == "phase.verify"
    else:
        assert snapshot(state) == before
    assert invoke("assert").returncode == (0 if passed else 2)
    before_status = snapshot(state)
    status = invoke("status", *options)
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["postconditions_live"]["1"] == {
        "passed": passed, "reason": reason,
    }
    assert snapshot(state) == before_status


def test_falsey_callable_is_executed(cli):
    invoke, state, modules = cli
    (modules / "falsey_checker.py").write_text(
        "class Check:\n"
        "    def __bool__(self): return False\n"
        "    def __call__(self, phase, investigation_id):\n"
        "        return False, 'artifact rejected'\n"
        "run_check = Check()\n"
    )
    before = snapshot(state)
    result = invoke("verify", "--postcondition-module", "falsey_checker")
    assert result.returncode == 2
    assert "artifact rejected" in result.stderr
    assert snapshot(state) == before


def test_default_checker_requires_real_artifact(cli):
    invoke, state, _ = cli
    before = snapshot(state)
    result = invoke("verify")
    assert result.returncode == 2
    assert "orientation.md" in result.stderr
    assert snapshot(state) == before
    research = state / "research" / INVESTIGATION
    research.mkdir(parents=True)
    (research / "orientation.md").write_text(
        "# Orientation\n" + "Evidence for this investigation. " * 100
        + "\n## Prior Graph Knowledge\nA prior result cites chunk-regression.\n"
    )
    result = invoke("verify")
    assert result.returncode == 0, result.stderr
    assert "orientation.md OK" in result.stdout
    assert invoke("assert").returncode == 0
