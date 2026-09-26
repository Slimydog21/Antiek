"""Deployment contracts for exact-SHA release construction and rollback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "infrastructure/ansible/playbooks/deploy_atomic.yml"
WORKFLOW = ROOT / ".github/workflows/deploy_backend.yml"
DEPENDENCY_TASK_NAMES = {
    "bootstrap the pinned lock reader into the service venv",
    "record the deploy-time lock-check receipt",
    "exact-sync the service venv from the gated SHA's lock",
    "remove the bootstrap lock reader from the service venv",
}


def _load() -> dict[str, Any]:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))


def _walk(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for task in tasks:
        result.append(task)
        for key in ("block", "rescue", "always"):
            result.extend(_walk(task.get(key, [])))
    return result


def _names(tasks: list[dict[str, Any]]) -> list[str]:
    return [task.get("name", "") for task in tasks]


def test_deploy_workflow_uses_the_atomic_release_playbook() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    deploy = next(step for step in steps if step.get("name") == "Deploy")
    assert "playbooks/deploy_atomic.yml" in deploy["run"]
    assert deploy["env"]["ANTIEK_TARGET_SHA"] == "${{ needs.gate.outputs.sha }}"


def test_release_identity_is_exact_and_not_a_mutable_branch() -> None:
    play = _load()[1]
    assert play["vars"]["antiek_release_dir"].endswith("/{{ antiek_target_sha }}")
    assert play["vars"]["antiek_release_root"] == "/opt/antiek-releases"
    exact = next(task for task in _walk(play["pre_tasks"]) if "exact 40-hex" in task.get("name", ""))
    assertions = exact["ansible.builtin.assert"]["that"]
    assert "antiek_target_sha | length == 40" in assertions
    assert "antiek_target_sha is match('^[0-9a-f]{40}$')" in assertions


def test_dependency_contract_survives_the_release_build() -> None:
    tasks = _walk(_load()[1]["tasks"])
    named = {name: tasks.index(task) for name, task in zip(_names(tasks), tasks, strict=False) if name in DEPENDENCY_TASK_NAMES}
    assert set(named) == DEPENDENCY_TASK_NAMES
    bootstrap = named["bootstrap the pinned lock reader into the service venv"]
    lock_check = named["record the deploy-time lock-check receipt"]
    sync = named["exact-sync the service venv from the gated SHA's lock"]
    remove = named["remove the bootstrap lock reader from the service venv"]
    assert bootstrap < lock_check < sync < remove
    bootstrap_task = tasks[bootstrap]
    assert bootstrap_task["ansible.builtin.pip"]["name"] == "uv==0.11.15"
    sync_task = tasks[sync]
    argv = sync_task["ansible.builtin.command"]["argv"]
    assert argv[:4] == [
        "{{ antiek_release_dir }}/.venv/bin/uv",
        "sync",
        "--frozen",
        "--no-dev",
    ]
    for required in ("--no-default-groups", "pdf", "urls", "embedding", "docs", "turbopuffer_shadow"):
        assert required in argv
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "pip install -r" not in text
    assert "uv export" not in text


def test_build_validation_precedes_the_single_public_cutover() -> None:
    tasks = _load()[1]["tasks"]
    names = _names(_walk(tasks))
    build = names.index("build and validate the exact-SHA release")
    receipt = names.index("require a valid release receipt before publication")
    frontend = names.index("assert frontend index is present and traversable")
    candidate_caddy = names.index("render the candidate Caddyfile for post-cutover activation")
    validate_caddy = names.index("validate the candidate Caddyfile without changing live routing")
    cutover = names.index("make the one public API/SPA cutover")
    assert build < receipt < frontend < candidate_caddy < validate_caddy < cutover
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "mv -Tf" in text
    assert ".building" not in text
    assert "ln -sfn \"{{ antiek_public_dir }}\"" not in text


def test_api_and_frontend_cutover_share_one_release_chain() -> None:
    variables = yaml.safe_load(
        (ROOT / "infrastructure/ansible/group_vars/all.yml").read_text(encoding="utf-8")
    )
    assert variables["frontend_dist_dir"] == "/opt/antiek/frontend-dist"
    tasks = _walk(_load()[1]["tasks"])
    names = _names(tasks)
    assert "put the frontend root on the stable public release chain" not in names
    cutover = names.index("make the one public API/SPA cutover")
    activate = names.index("atomically activate the validated Caddyfile on the release chain")
    reload = names.index("synchronously reload Caddy onto the candidate routes")
    start = names.index("start antiek into the candidate release")
    assert cutover < activate < reload < start


def test_database_snapshot_precedes_candidate_schema_migration() -> None:
    tasks = _walk(_load()[1]["tasks"])
    names = _names(tasks)
    assert names.index("checkpoint the quiesced previous database before snapshot") < names.index(
        "snapshot the quiesced DuckDB before migration"
    )
    assert names.index("snapshot the quiesced DuckDB before migration") < names.index(
        "initialize graph schema in the candidate release"
    )


def test_every_release_path_consumer_is_quiesced() -> None:
    tasks = _walk(_load()[1]["tasks"])
    stop = next(task for task in tasks if "pause every release-path consumer" in task.get("name", ""))
    assert set(stop["loop"]) == {
        "antiek-continuous-research.service",
        "antiek-arxiv-oai-sync.timer",
        "antiek-arxiv-oai-sync.service",
        "antiek-backup.timer",
        "antiek-backup.service",
        "antiek-health-probe.service",
        "antiek-health-probe.timer",
        "antiek-backup-freshness.service",
        "antiek-backup-freshness.timer",
    }


def test_failure_rescue_restores_and_verifies_the_previous_release() -> None:
    tasks = _walk(_load()[1]["tasks"])
    rescue_tasks = next(task["rescue"] for task in tasks if task.get("name") == "quiesce, migrate, cut over, and verify")
    names = _names(_walk(rescue_tasks))
    assert names.index("re-quiesce candidate consumers before rollback") < names.index(
        "stop a failing candidate before rollback"
    )
    legacy_recovery = names.index("restore an interrupted first legacy public-directory move")
    assert names.index("stop a failing candidate before rollback") < legacy_recovery
    assert legacy_recovery < names.index("restore the previous release pointer")
    recovery = next(
        task
        for task in _walk(rescue_tasks)
        if task.get("name") == "restore an interrupted first legacy public-directory move"
    )
    recovery_script = recovery["ansible.builtin.shell"]
    assert 'if [ -e "$PUBLIC" ] || [ -L "$PUBLIC" ] || [ ! -d "$MOVED" ]; then' in recovery_script
    assert 'actual=$(git -C "$MOVED" rev-parse HEAD)' in recovery_script
    assert 'if [ "$actual" != "{{ antiek_previous_sha }}" ]; then' in recovery_script
    assert 'Refusing recovery: moved release is $actual, expected {{ antiek_previous_sha }}' in recovery_script
    assert 'mv "$MOVED" "$PUBLIC"' in recovery_script
    assert recovery_script.index('if [ "$actual" != "{{ antiek_previous_sha }}" ]; then') < recovery_script.index(
        'mv "$MOVED" "$PUBLIC"'
    )
    assert names.index("restore the previous release pointer") < names.index("restart the previous release")
    restore = next(task for task in _walk(rescue_tasks) if task.get("name") == "restore the previous release pointer")
    restore_script = restore["ansible.builtin.shell"]
    assert 'if [ -L "$PUBLIC" ]' in restore_script
    assert 'elif [ -d "$PUBLIC" ]' in restore_script
    assert not any("SPA root" in name or "pre-atomic" in name for name in names)
    caddy_identity = next(
        task
        for task in _walk(rescue_tasks)
        if task.get("name") == "bind the rollback Caddyfile identity after pointer rollback"
    )
    assert (
        caddy_identity["ansible.builtin.set_fact"]["antiek_rollback_caddy_backup"]
        == "/etc/caddy/Caddyfile.pre-atomic-{{ antiek_target_sha }}"
    )
    assert names.index("restart the previous release") < names.index("verify public health after rollback")
    health = next(task for task in _walk(rescue_tasks) if task.get("name") == "verify public health after rollback")
    assert "rollback_health.json.build_sha == antiek_previous_sha" in health["until"]
    assert "rollback_health.json.registered_providers | length > 0" in health["until"]
    fail = next(task for task in _walk(rescue_tasks) if task.get("ansible.builtin.fail", {}))
    assert "Code rollback does not reverse database writes" in fail["ansible.builtin.fail"]["msg"]


def test_published_release_is_receipt_gated_and_write_frozen() -> None:
    tasks = _walk(_load()[1]["tasks"])
    names = _names(tasks)
    assert names.index("record the dependency and artifact release receipt") < names.index(
        "freeze release permissions after all writes"
    )
    freeze = next(task for task in tasks if task.get("name") == "freeze release permissions after all writes")
    assert freeze["ansible.builtin.command"]["argv"] == ["chmod", "-R", "a-w", "{{ antiek_release_dir }}"]
