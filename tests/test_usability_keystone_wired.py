"""The usability-keystone probe must be run by something that can block a merge.

docs/decisions/usability-keystone.md has carried
``Status: NOT INSTALLED — the probe is written; nothing runs it`` since its
2026-09-20 correction, which found that none of the four artifacts the record
cited actually existed.

The probe is the only one asserting the CONJUNCTION — login, launch, compound,
read and §9 attribution as ONE journey through the real ``create_app()``
factory. Every other probe asserts a single leg in isolation, so "all five green
individually" never proved the journey worked.

This file is the tripwire the record lacked. A decision record claiming a probe
is installed, with nothing that fails when it is not, is how the claim drifted
from the code.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_PROBE_ID = "usability_keystone"
_STEP = "Usability keystone probe"
# The job that is BOTH required by the ruleset and free of a paths: filter.
_REQUIRED_JOB = "keystone"


def _keystone_steps() -> list[dict]:
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8")) or {}
    job = (doc.get("jobs") or {}).get(_REQUIRED_JOB) or {}
    steps = job.get("steps") or []
    assert len(steps) > 3, f"parsed only {len(steps)} keystone steps; the parse is broken"
    return steps


def _step() -> dict:
    match = [s for s in _keystone_steps() if _STEP in (s.get("name") or "")]
    assert match, (
        f"no {_STEP!r} step in the required {_REQUIRED_JOB!r} job — the probe is "
        f"written but nothing runs it, which is the exact state "
        f"docs/decisions/usability-keystone.md was corrected to describe"
    )
    return match[0]


def test_the_probe_is_run_by_a_required_job() -> None:
    run = _step().get("run") or ""
    assert "tools.reachability.probe_runner" in run, f"step does not run the runner: {run!r}"
    assert _PROBE_ID in run, f"the step runs the probe runner but not {_PROBE_ID!r}: {run!r}"


def test_the_step_does_not_swallow_the_exit_code() -> None:
    """A BLOCKED verdict must red the job, or the probe is decoration."""
    step = _step()
    run = step.get("run") or ""
    assert "|| true" not in run, "the step swallows a failure with `|| true`"
    assert "set +e" not in run, "the step disables errexit"
    assert step.get("continue-on-error") is not True, (
        "the step is continue-on-error, so a BLOCKED probe cannot red the job"
    )


def test_it_runs_only_the_keystone_probe() -> None:
    """Running the whole suite here would wire a permanently-red gate.

    `compounding` measures cost_cold vs cost_warm and both read 0 without
    provider credentials, which CI does not have — so it is BLOCKED there by
    construction. `--only` keeps this gate to the probe that genuinely passes
    credential-free.
    """
    run = _step().get("run") or ""
    assert "--only" in run, (
        "the step runs every probe; `compounding` cannot pass without provider "
        "credentials, so this would be red on every PR forever"
    )


def test_the_probe_module_exists_and_registers_itself() -> None:
    """Guards the other direction: a wired step pointing at a probe that is gone."""
    probe = _ROOT / "tools" / "reachability" / "probes" / f"{_PROBE_ID}.py"
    assert probe.exists(), f"{probe} is missing but ci.yml runs it"
    body = probe.read_text(encoding="utf-8")
    assert "PROBE = Probe(" in body, (
        f"{probe.name} no longer exposes a module-level PROBE, so "
        f"discover_probes() will not find it and --only will match nothing"
    )
