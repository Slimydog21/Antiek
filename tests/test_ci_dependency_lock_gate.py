"""Keep the pre-merge dependency lock contract enforced.

Deployment is allowed to be the strict consumer of the lock, never the first
detector of a lock drift: a declaration-only dependency bump must fail CI
before it becomes a release candidate.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_CI = _REPO / ".github" / "workflows" / "ci.yml"
_UV_PIN = "uv==0.11.15"


def _workflow() -> dict[object, object]:
    workflow = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def _lock_job() -> dict[str, object]:
    jobs = _workflow().get("jobs")
    assert isinstance(jobs, dict)
    job = jobs.get("dependency-lock")
    assert isinstance(job, dict), "required dependency-lock job is absent"
    return job


def _commands(steps: object) -> list[str]:
    assert isinstance(steps, list)
    return [
        command
        for step in steps
        if isinstance(step, dict) and isinstance(command := step.get("run"), str)
    ]


def _needs_contains(needs: object, job_id: str) -> bool:
    if isinstance(needs, str):
        return needs == job_id
    if isinstance(needs, list):
        return job_id in needs
    return False


def test_ci_runs_the_deploy_pinned_lock_check_before_expensive_suites() -> None:
    jobs = _workflow().get("jobs")
    assert isinstance(jobs, dict)
    assert "dependency-lock" in jobs
    pytest_suite = jobs.get("pytest-suite")
    assert isinstance(pytest_suite, dict)
    assert _needs_contains(pytest_suite.get("needs"), "dependency-lock")
    job = _lock_job()
    assert job.get("permissions") == {"contents": "read"}
    assert job.get("continue-on-error") is not True
    assert job.get("if") is None
    commands = _commands(job.get("steps"))
    assert commands == [
        f"python -m pip install {_UV_PIN}",
        "uv lock --check",
    ]


def test_lock_failure_fails_the_required_pytest_rollup() -> None:
    jobs = _workflow().get("jobs")
    assert isinstance(jobs, dict)
    rollup = jobs.get("pytest")
    assert isinstance(rollup, dict), "required pytest rollup is absent"
    assert _needs_contains(rollup.get("needs"), "dependency-lock")
    assert _needs_contains(rollup.get("needs"), "pytest-suite")
    assert rollup.get("if") == "${{ !cancelled() }}"
    assert rollup.get("continue-on-error") is not True
    steps = rollup.get("steps")
    assert isinstance(steps, list)
    gate = steps[0]
    assert isinstance(gate, dict)
    assert gate.get("name") == "Fail closed unless the lock gate and shards succeeded"
    env = gate.get("env")
    assert env == {
        "LOCK_RESULT": "${{ needs.dependency-lock.result }}",
        "SHARD_RESULT": "${{ needs.pytest-suite.result }}",
    }
    command = gate.get("run")
    assert isinstance(command, str)
    assert '[[ "$LOCK_RESULT" != "success" || "$SHARD_RESULT" != "success" ]]' in command
    assert "exit 1" in command


def test_lock_gate_covers_main_promotions_and_targeted_pull_requests() -> None:
    # YAML 1.1 parses the bare `on` key as boolean true.
    on = _workflow()[True]
    assert isinstance(on, dict)
    assert "pull_request" in on
    assert "push" in on
    push = on["push"]
    pull_request = on["pull_request"]
    assert isinstance(push, dict)
    assert isinstance(pull_request, dict)
    push_branches = push.get("branches")
    pull_branches = pull_request.get("branches")
    assert isinstance(push_branches, list)
    assert isinstance(pull_branches, list)
    assert "main" in push_branches
    assert "main" in pull_branches


def test_lock_context_is_in_the_recorded_required_fence() -> None:
    contract = yaml.safe_load((_REPO / ".github" / "required-checks.yml").read_text(encoding="utf-8"))
    assert isinstance(contract, dict)
    required = contract.get("required")
    assert isinstance(required, list)
    assert "dependency lock" in required
    exempt = contract.get("emitted_but_not_required")
    assert isinstance(exempt, dict)
    assert "dependency lock" not in exempt


def test_deploy_gate_checks_the_lock_context() -> None:
    script = (_REPO / "tools" / "deploy" / "require_green.sh").read_text(encoding="utf-8")
    assert "  'dependency lock'\n" in script


def test_lock_gate_uses_the_same_uv_pin_as_deployment() -> None:
    # Keep this test and the deploy contract in one pin family. The deploy side
    # has its own exact Ansible assertions; parse the pip name there rather than
    # matching an incidental substring such as uv==0.11.150.
    deploy = yaml.safe_load(
        (_REPO / "infrastructure" / "ansible" / "playbooks" / "deploy_atomic.yml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(deploy, list)

    def contains_pinned_uv(node: object) -> bool:
        if isinstance(node, dict):
            module = node.get("ansible.builtin.pip")
            if isinstance(module, dict) and module.get("name") == _UV_PIN:
                return True
            return any(contains_pinned_uv(child) for child in node.values())
        if isinstance(node, list):
            return any(contains_pinned_uv(child) for child in node)
        return False

    assert contains_pinned_uv(deploy)
