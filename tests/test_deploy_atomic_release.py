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


def _all_strings(node: Any) -> list[str]:
    """Every string value in the parsed playbook (comments are not values)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [item for value in node.values() for item in _all_strings(value)]
    if isinstance(node, list):
        return [item for entry in node for item in _all_strings(entry)]
    return []


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
    frontend = names.index("assert the frozen frontend is readable and traversable")
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


def test_frozen_frontend_modes_are_safe_for_public_serving() -> None:
    tasks = _walk(_load()[1]["tasks"])
    named = {task.get("name", ""): task for task in tasks}
    stat = named["stat the frozen frontend entrypoint and root"]["ansible.builtin.stat"]
    root_stat = named["stat the frozen frontend root"]["ansible.builtin.stat"]
    assertions = named["assert the frozen frontend is readable and traversable"]["ansible.builtin.assert"]["that"]
    assert stat["path"] == "{{ antiek_release_dir }}/frontend-dist/index.html"
    assert root_stat["path"] == "{{ antiek_release_dir }}/frontend-dist"
    assert "release_frontend_index.stat.mode == '0444'" in assertions
    assert "release_frontend_root.stat.mode == '0555'" in assertions


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
    play = _load()[1]
    tasks = _walk(play["tasks"])
    stop = next(task for task in tasks if "pause every release-path consumer" in task.get("name", ""))
    expected = {
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
    # The pause loop and the "require complete consumer pause" post-condition
    # both read ONE declared list, so the post-condition cannot drift from what
    # was actually paused. Pin both halves: the loop reads the var, and the var
    # is still exactly the release-path consumer set.
    assert stop["loop"] == "{{ release_path_consumers }}"
    assert set(play["vars"]["release_path_consumers"]) == expected


def test_the_consumer_pause_post_condition_is_state_based_not_result_shaped() -> None:
    """Prod 2026-10-01: `selectattr('skipped', 'equalto', true)` over a loop
    result raised `object of type 'dict' has no attribute 'skipped'` — once in
    the pause assert and again in the rescue's classifier, which is why the
    rescue never ran and the box stayed dark. The post-condition must ask the
    BOX for unit state, which is both safer and strictly stronger."""
    # Scan the PARSED playbook, not the file text: a comment describing the
    # defect must not satisfy (or trip) the gate.
    offenders = [
        expr
        for expr in _all_strings(_load())
        if "selectattr('skipped'" in expr or "rejectattr('skipped'" in expr
    ]
    assert offenders == [], f"version-coupled loop-result introspection returned: {offenders}"

    tasks = _walk(_load()[1]["tasks"])
    probe = next(
        task for task in tasks
        if "observe every release-path consumer state after the pause" in task.get("name", "")
    )
    assert probe["ansible.builtin.command"]["argv"][-1] == "--property=ActiveState"
    assert probe["loop"] == "{{ release_path_consumers }}"

    assert_task = next(
        task for task in tasks
        if "require complete consumer pause before schema or cutover" in task.get("name", "")
    )
    assertions = assert_task["ansible.builtin.assert"]["that"]
    joined = "\n".join(assertions)
    assert "consumer_pause_states.results | map(attribute='stdout')" in joined
    assert "ActiveState=inactive" in joined and "ActiveState=failed" in joined


def test_a_failed_deploy_cannot_leave_monitoring_or_backups_stopped() -> None:
    """Prod 2026-10-01: the deploy died on the consumer-pause assert and its
    rescue died on the same conditional, so antiek-backup.timer,
    antiek-backup-freshness.timer, antiek-health-probe.timer and
    antiek-continuous-research.service were left stopped with no later task to
    notice — a failed deploy silently unscheduled the operator's backups.
    The block must therefore carry an `always` that restarts them: `always`
    runs after a failing rescue too, which a rescue's own task list does not."""
    tasks = _walk(_load()[1]["tasks"])
    guard = next(
        task for task in tasks
        if "never leave release-path monitoring or backups stopped" in task.get("name", "")
    )
    assert set(guard["loop"]) == {
        "antiek-continuous-research.service",
        "antiek-backup.timer",
        "antiek-health-probe.timer",
        "antiek-backup-freshness.timer",
    }
    assert guard["ansible.builtin.systemd"] == {
        "name": "{{ item }}",
        "enabled": True,
        "state": "started",
    }
    assert guard["failed_when"] is False

    containers = [task for task in tasks if "always" in task]
    assert containers, "the release block no longer has an always section"
    assert any(
        any(inner.get("name") == guard["name"] for inner in container["always"])
        for container in containers
    ), "the monitoring guard is not inside an always section"


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


def test_duckdb_pre_migration_snapshots_are_pruned_with_the_three_live_ones_protected() -> None:
    """Prod 2026-10-01: the playbook wrote one ~940 MB
    ``antiek.duckdb.pre-atomic-<sha>`` per deploy and NOTHING pruned them —
    46 copies / 40.6 GB in six days (17 in one day) on a 150 GB disk with
    72 GB free, while release directories WERE pruned to a retention count.
    A deploy must not be a net drain on the operator's disk."""
    play = _load()[1]
    tasks = _walk(play["tasks"])
    retention = play["vars"]["antiek_duckdb_snapshot_retention_count"]
    assert isinstance(retention, int) and retention >= 2, retention

    prune = next(
        task for task in tasks
        if "prune DuckDB pre-migration snapshots" in task.get("name", "")
    )
    script = prune["ansible.builtin.shell"]
    # Only the one file family, this filesystem, never a directory.
    assert "-name 'antiek.duckdb.pre-atomic-*'" in script
    assert "-type f" in script
    assert "--one-file-system" in script
    # The three SHAs the playbook can still need, named explicitly.
    for protected in ('"$keep"', '"$previous"', '"$current"'):
        assert protected in script, protected
    assert 'keep="{{ antiek_target_sha }}"' in script
    assert 'previous="{{ antiek_previous_sha }}"' in script
    assert 'current=$(basename "$(readlink -f "{{ antiek_public_dir }}")")' in script
    # Newest-first, same discipline as the release prune beside it.
    assert "sort -nr" in script
    assert 'count" -gt "{{ antiek_duckdb_snapshot_retention_count }}"' in script
    # It runs only on a SUCCESSFUL deploy: it is a sibling task after the
    # block, not an always/rescue task, so a failed deploy never deletes the
    # snapshot an operator may be about to restore from.
    assert "always" not in prune and "rescue" not in prune
    assert "always" not in play["tasks"][-1]
