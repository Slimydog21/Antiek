"""Guard Ansible keywords against accidental inclusion in module arguments."""

from __future__ import annotations

import yaml

from tests.test_deploy_atomic_release import PLAYBOOK, _load, _walk


def test_database_checkpoint_become_is_a_task_keyword() -> None:
    tasks = _walk(_load()[1]["tasks"])
    task = next(
        task
        for task in tasks
        if task.get("name") == "checkpoint the quiesced previous database before snapshot"
    )
    assert task["ansible.builtin.command"]["argv"][0] == "{{ antiek_public_dir }}/.venv/bin/python"
    assert "become" not in task["ansible.builtin.command"]
    assert "become_user" not in task["ansible.builtin.command"]
    assert task["become"] is True
    assert task["become_user"] == "{{ antiek_user }}"


def test_playbook_has_no_become_keywords_nested_in_module_arguments() -> None:
    documents = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    for play in documents:
        for task in _walk(play.get("tasks", []) + play.get("pre_tasks", [])):
            module = next(
                (key for key in task if key.startswith(("ansible.builtin.", "ansible.posix."))),
                None,
            )
            if module is None:
                continue
            assert "become" not in task[module]
            assert "become_user" not in task[module]
