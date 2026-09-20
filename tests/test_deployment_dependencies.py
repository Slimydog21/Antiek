"""Deployment must reject missing or stale security pins before service work."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "infrastructure/ansible/tasks/python-dependencies.yml"
PINS = ROOT / "infrastructure/requirements-security.txt"


def tasks():
    return yaml.safe_load(TASKS.read_text())


@pytest.mark.parametrize("playbook", ["setup", "deploy"])
def test_dependency_tasks_run_under_code_tag_before_service_changes(playbook):
    plays = yaml.safe_load(
        (ROOT / f"infrastructure/ansible/playbooks/{playbook}.yml").read_text()
    )
    remote = next(play for play in plays if play["hosts"] == "antiek_prod")
    entries = remote["tasks"]
    imports = [
        i for i, task in enumerate(entries)
        if task.get("ansible.builtin.import_tasks") == "../tasks/python-dependencies.yml"
    ]
    assert len(imports) == 1, "Expected one shared dependency gate"
    index = imports[0]
    assert "code" in entries[index]["tags"]
    assert not entries[index].get("ignore_errors", False)
    assert remote["become"] is True
    assert "youtube" in entries[index]["vars"]["antiek_dependency_extras"].split(",")
    def assert_no_service_change(task):
        for key, value in task.items():
            action = key.rsplit(".", 1)[-1]
            assert action not in {"systemd", "systemd_service", "service"}
            if action in {"command", "shell"}:
                assert "systemctl" not in str(value)
            if action == "meta":
                assert value != "flush_handlers"
            if key in {"block", "rescue", "always"}:
                for nested in value:
                    assert_no_service_change(nested)

    for task in entries[:index]:
        assert_no_service_change(task)
    install, verify, consistency = tasks()
    pip = install["ansible.builtin.pip"]
    assert pip["extra_args"].split(maxsplit=1)[0] in {"-r", "--requirement"}
    assert "requirements-security.txt" in pip["extra_args"]
    assert pip["editable"] is True
    assert verify["ansible.builtin.command"]["argv"][0].endswith("/.venv/bin/python")
    assert consistency["ansible.builtin.command"]["argv"][1:] == ["-m", "pip", "check"]
    assert all(not task.get("ignore_errors", False) for task in tasks())


@pytest.mark.parametrize("failure", [None, "missing", "stale", "empty"])
def test_installed_version_gate_executes_against_package_metadata(tmp_path, failure):
    pins = {
        line.split("==")[0]: line.split("==")[1]
        for line in PINS.read_text().splitlines()
        if line and not line.startswith("#")
    }
    for name, version in pins.items():
        if failure == "missing" and name == "yt-dlp":
            continue
        if failure == "stale" and name == "cryptography":
            version = "49.0.0"
        distribution = tmp_path / f"{name.replace('-', '_')}-{version}.dist-info"
        distribution.mkdir()
        (distribution / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        )
    constraint = tmp_path / "security.txt"
    constraint.write_text("# empty\n" if failure == "empty" else PINS.read_text())
    script = tasks()[1]["ansible.builtin.command"]["argv"][2]
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-S", "-c", script, str(constraint)],
        env=env, capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) is (failure is None), result.stderr
    if failure == "stale":
        assert '"installed": "49.0.0"' in result.stderr
    if failure == "missing":
        assert '"installed": null' in result.stderr
