"""Declarative production lifecycle for the continuous-research daemon."""

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / "infrastructure" / "ansible"
DEPLOY_PATH = ANSIBLE / "playbooks" / "deploy.yml"


def _tasks() -> list[dict[str, object]]:
    document = yaml.safe_load(DEPLOY_PATH.read_text(encoding="utf-8"))
    deploy = next(play for play in document if play.get("hosts") == "antiek_prod")
    return deploy["tasks"]


def _task(name: str) -> dict[str, object]:
    return next(task for task in _tasks() if task.get("name") == name)


def test_continuous_research_defaults_live_and_documents_durable_pause() -> None:
    variables = yaml.safe_load(
        (ANSIBLE / "group_vars" / "all.yml").read_text(encoding="utf-8")
    )
    inventory = (ANSIBLE / "inventory.ini.example").read_text(encoding="utf-8")
    runbook = (ROOT / "infrastructure" / "runbooks" / "code-update.md").read_text(
        encoding="utf-8"
    )

    assert variables["antiek_continuous_research_paused"] is False
    assert "# antiek_continuous_research_paused=true" in inventory
    assert "A manual `systemctl stop" in runbook
    assert "per-investigation pause/resume controls do not stop the" in runbook
    assert "not proof\nthat this systemd process is currently active" in runbook


def test_deploy_reconciles_live_pause_and_code_change_states() -> None:
    policy = _task("require a boolean continuous-research pause policy")
    normalize = _task("normalize continuous-research pause policy")
    reconcile = _task("reconcile antiek-continuous-research lifecycle")
    systemd = reconcile["ansible.builtin.systemd"]

    policy_expression = policy["ansible.builtin.assert"]["that"]
    assert "antiek_continuous_research_paused is boolean" in policy_expression
    assert "antiek_continuous_research_paused is string" in policy_expression
    assert "['true', 'false']" in policy_expression
    assert "| bool" in normalize["ansible.builtin.set_fact"][
        "antiek_continuous_research_is_paused"
    ]
    assert systemd["name"] == "antiek-continuous-research.service"
    assert systemd["enabled"] == "{{ not antiek_continuous_research_is_paused }}"
    assert "'stopped'" in systemd["state"]
    assert "'restarted'" in systemd["state"]
    assert "antiek_continuous_unit.changed | default(false)" in systemd["state"]
    assert "git_pull.changed | default(false)" in systemd["state"]
    assert "'started'" in systemd["state"]
    for task in (policy, normalize, reconcile):
        assert "code" in task["tags"]


def test_pause_policy_accepts_documented_forms_and_rejects_junk(tmp_path: Path) -> None:
    expression = _task("require a boolean continuous-research pause policy")[
        "ansible.builtin.assert"
    ]["that"]
    playbook = tmp_path / "pause-policy.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "tasks": [
                        {
                            "ansible.builtin.assert": {
                                "that": expression,
                                "quiet": True,
                            }
                        }
                    ],
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    for value in (True, False, "true", "false"):
        result = subprocess.run(
            [
                "ansible-playbook",
                str(playbook),
                "-i",
                "localhost,",
                "-c",
                "local",
                "-e",
                json.dumps({"antiek_continuous_research_paused": value}),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    junk = subprocess.run(
        [
            "ansible-playbook",
            str(playbook),
            "-i",
            "localhost,",
            "-c",
            "local",
            "-e",
            json.dumps({"antiek_continuous_research_paused": "stopped"}),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert junk.returncode != 0


def test_deploy_verifies_live_and_declared_paused_states() -> None:
    live = _task("verify live continuous-research daemon is active")
    inactive = _task("verify paused continuous-research daemon is inactive")
    disabled = _task("verify paused continuous-research daemon is disabled")

    assert live["ansible.builtin.command"]["argv"][1] == "is-active"
    assert live["when"] == "not antiek_continuous_research_is_paused"
    assert live["changed_when"] is False
    assert inactive["ansible.builtin.command"]["argv"][1] == "is-active"
    assert "!= 'inactive'" in inactive["failed_when"]
    assert "--quiet" not in inactive["ansible.builtin.command"]["argv"]
    assert disabled["ansible.builtin.command"]["argv"][1] == "is-enabled"
    assert "!= 'disabled'" in disabled["failed_when"]
    assert "--quiet" not in disabled["ansible.builtin.command"]["argv"]
    assert inactive["when"] == "antiek_continuous_research_is_paused"
    assert disabled["when"] == "antiek_continuous_research_is_paused"
    for task in (live, inactive, disabled):
        assert "code" in task["tags"]
