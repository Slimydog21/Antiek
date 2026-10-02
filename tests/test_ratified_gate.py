"""The ratified-scoring gate must be wired into a job that can block a merge.

docs/decisions/ratified-scoring-gate.md carried
``Status: NOT WIRED — the tool exists, the CI step does not`` from its
2026-09-20 correction. The record had previously claimed a ``Ratified-scoring
gate`` step in the ``pytest`` job of ci.yml; ``git log -S ratified_gate --
.github/workflows/`` returned zero commits. The step never existed, and the
self-test named here as its tripwire was never written either.

This is that tripwire. A decision record asserting a gate is active, with
nothing that fails when it is not, is how the claim drifted from the code in the
first place.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_TOOL = _ROOT / "tools" / "ratified_gate.py"
_STEP = "Ratified-scoring gate"
# The job that is BOTH required by the ruleset and free of a paths: filter.
_REQUIRED_JOB = "keystone"


def _keystone_steps() -> list[dict]:
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8")) or {}
    job = (doc.get("jobs") or {}).get(_REQUIRED_JOB) or {}
    steps = job.get("steps") or []
    assert len(steps) > 3, f"parsed only {len(steps)} keystone steps; the parse is broken"
    return steps


def test_the_gate_has_a_ci_step_at_all() -> None:
    """The exact claim the record made falsely for months."""
    names = [s.get("name") or "" for s in _keystone_steps()]
    assert any(_STEP in n for n in names), (
        f"no {_STEP!r} step in the required {_REQUIRED_JOB!r} job. "
        f"docs/decisions/ratified-scoring-gate.md describes this gate as "
        f"enforced; without the step that is a claim, not a gate. Steps: {names}"
    )


def test_the_ci_step_does_not_swallow_the_exit_code() -> None:
    """`|| true`, `continue-on-error` or a captured rc would make it decorative."""
    step = next(s for s in _keystone_steps() if _STEP in (s.get("name") or ""))
    run = step.get("run") or ""
    assert "tools/ratified_gate.py" in run, f"step does not invoke the tool: {run!r}"
    assert "|| true" not in run, "the step swallows a failure with `|| true`"
    assert "set +e" not in run, "the step disables errexit"
    assert step.get("continue-on-error") is not True, (
        "the step is continue-on-error, so a BLOCKED verdict cannot red the job"
    )


def test_the_gate_actually_blocks_an_unratified_scored_artifact(tmp_path) -> None:
    """Non-vacuity: it reports OK over zero scored artifacts today, so the only
    way to know it still works is to give it one that must fail.

    A scored artifact is ``mock_run=false``; the rule is that it must carry
    ``parameters_ratified`` and a ``ratification_ref``.
    """
    results = _ROOT / "compounding" / "benchmark" / "results"
    template = next(results.glob("*.json"), None)
    assert template is not None, "no artifact to use as a shape template"

    data = json.loads(template.read_text(encoding="utf-8"))
    data["mock_run"] = False
    data.pop("parameters_ratified", None)
    data.pop("ratification_ref", None)
    planted = results / "_pytest_unratified_probe.json"
    planted.write_text(json.dumps(data), encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(_TOOL)],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode != 0, (
            "an unratified scored artifact did NOT red the gate — it is "
            f"vacuous:\n{proc.stdout[-1500:]}"
        )
        assert "BLOCKED" in proc.stdout, proc.stdout[-500:]
    finally:
        planted.unlink(missing_ok=True)

    clean = subprocess.run(
        [sys.executable, str(_TOOL)],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert clean.returncode == 0, (
        f"the gate stayed red after the probe was removed:\n{clean.stdout[-800:]}"
    )
