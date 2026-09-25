"""Guard the production dependency path against re-resolution and tool orphans."""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_DEPLOY = _REPO / "infrastructure" / "ansible" / "playbooks" / "deploy.yml"


def _code_tasks() -> list[dict[str, object]]:
    plays = yaml.safe_load(_DEPLOY.read_text(encoding="utf-8"))
    return [task for task in plays[1]["tasks"] if "code" in task.get("tags", [])]


def _task_args(task: dict[str, object], module: str) -> dict[str, object]:
    """Return args for a fully qualified Ansible module."""
    args = task.get(module)
    assert isinstance(args, dict)
    return args


def test_deploy_exact_syncs_the_locked_production_extras() -> None:
    tasks = _code_tasks()
    sync = next(
        task
        for task in tasks
        if task.get("name")
        == "exact-sync the service venv from the gated SHA's lock"
    )
    argv = _task_args(sync, "ansible.builtin.command")["argv"]
    assert argv[1:] == [
        "sync",
        "--frozen",
        "--no-dev",
        "--no-default-groups",
        "--extra",
        "pdf",
        "--extra",
        "urls",
        "--extra",
        "embedding",
        "--extra",
        "docs",
        "--extra",
        "turbopuffer_shadow",
    ]


def test_bootstrap_uv_is_pinned_then_removed_after_exact_sync() -> None:
    tasks = _code_tasks()
    bootstrap_task = next(
        task
        for task in tasks
        if task.get("name")
        == "bootstrap the pinned lock reader into the service venv"
    )
    sync = next(
        task
        for task in tasks
        if task.get("name")
        == "exact-sync the service venv from the gated SHA's lock"
    )
    cleanup_task = next(
        task
        for task in tasks
        if task.get("name") == "remove the bootstrap lock reader from the service venv"
    )

    assert tasks.index(bootstrap_task) < tasks.index(sync) < tasks.index(cleanup_task)
    bootstrap_args = _task_args(bootstrap_task, "ansible.builtin.pip")
    cleanup_args = _task_args(cleanup_task, "ansible.builtin.pip")

    assert bootstrap_args["name"].startswith("uv==")
    assert cleanup_args == {
        "name": "uv",
        "state": "absent",
        "virtualenv": "{{ antiek_install_dir }}/.venv",
    }


def test_deploy_does_not_claim_uv_self_removal() -> None:
    text = _DEPLOY.read_text(encoding="utf-8")
    assert "the exact sync removes it again" not in text
    assert "the bootstrap uv itself are" not in text


def test_deploy_has_no_legacy_re_resolution_paths() -> None:
    text = _DEPLOY.read_text(encoding="utf-8")
    assert "uv export" not in text
    assert "pip install -r" not in text
    assert "pip install --no-deps" not in text
