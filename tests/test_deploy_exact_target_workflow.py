"""Exercise the deploy workflow's post-deploy SHA assertion without a live host."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy_backend.yml"
TARGET = "a" * 40


def _assertion_script() -> str:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["deploy"]["steps"]
    return next(
        step["run"]
        for step in steps
        if step.get("name") == "Assert production runs the gated commit"
    )


def _run_assertion(
    tmp_path: Path,
    health: object,
    *,
    target: str = TARGET,
    curl_fails: bool = False,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        'if [ "${FAKE_CURL_FAIL:-0}" = 1 ]; then exit 7; fi\n'
        "printf '%s\\n' \"$FAKE_HEALTH_JSON\"\n"
    )
    curl.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "SHA": target,
            "FAKE_HEALTH_JSON": json.dumps(health),
            "FAKE_CURL_FAIL": "1" if curl_fails else "0",
        }
    )
    return subprocess.run(
        ["bash", "-c", _assertion_script()],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_exact_target_is_the_only_success(tmp_path: Path) -> None:
    result = _run_assertion(tmp_path, {"build_sha": TARGET})
    assert result.returncode == 0, result.stderr
    assert "exact match" in result.stdout


def test_assertion_uses_the_gated_sha_after_deploy() -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["deploy"]["steps"]
    names = [step.get("name") for step in steps]
    assertion = names.index("Assert production runs the gated commit")
    assert (
        names.index("Deploy")
        < assertion
        < names.index("Assert production is on main's line, and providers are live")
    )
    assert steps[assertion]["env"]["SHA"] == "${{ needs.gate.outputs.sha }}"


@pytest.mark.parametrize(
    "observed",
    [
        "b" * 40,
        "short",
        "",
    ],
)
def test_other_observed_sha_cannot_credit_the_target(tmp_path: Path, observed: str) -> None:
    result = _run_assertion(tmp_path, {"build_sha": observed})
    assert result.returncode != 0
    assert "cannot claim that target is live" in result.stdout


def test_real_ancestry_does_not_replace_exact_target(tmp_path: Path) -> None:
    repo = tmp_path / "history"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    commit = [
        "git",
        "-C",
        str(repo),
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-q",
        "-m",
    ]
    subprocess.run([*commit, "target"], check=True)
    target = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run([*commit, "later"], check=True)
    descendant = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", target, descendant], check=True
    )

    result = _run_assertion(tmp_path, {"build_sha": descendant}, target=target, cwd=repo)
    assert result.returncode != 0
    assert "cannot claim that target is live" in result.stdout

    ancestor = _run_assertion(tmp_path, {"build_sha": target}, target=descendant, cwd=repo)
    assert ancestor.returncode != 0
    assert "cannot claim that target is live" in ancestor.stdout


def test_missing_or_unreadable_health_fails_closed(tmp_path: Path) -> None:
    missing = _run_assertion(tmp_path, {})
    assert missing.returncode != 0
    unreachable = _run_assertion(tmp_path, {}, curl_fails=True)
    assert unreachable.returncode != 0
