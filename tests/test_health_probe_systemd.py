"""Deployment topology contract for the five-minute production health probe."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "infrastructure" / "ansible" / "templates"
DEPLOY_PATH = ROOT / "infrastructure" / "ansible" / "playbooks" / "deploy.yml"


def _tasks() -> list[dict[str, object]]:
    document = yaml.safe_load(DEPLOY_PATH.read_text(encoding="utf-8"))
    deploy_play = next(play for play in document if play.get("hosts") == "antiek_prod")
    return deploy_play["tasks"]


def _task(name: str) -> dict[str, object]:
    return next(task for task in _tasks() if task.get("name") == name)


def test_health_probe_templates_are_bounded_and_least_privilege() -> None:
    wrapper = (TEMPLATES / "antiek-health-probe.sh.j2").read_text(encoding="utf-8")
    service = (TEMPLATES / "antiek-health-probe.service.j2").read_text(
        encoding="utf-8"
    )
    timer = (TEMPLATES / "antiek-health-probe.timer.j2").read_text(encoding="utf-8")

    assert 'source "{{ antiek_secrets_file }}"' in wrapper
    assert 'exec "{{ antiek_install_dir }}/tools/ops/health_probe.sh" "$@"' in wrapper
    assert "Type=oneshot" in service
    assert "User={{ antiek_user }}" in service
    assert "Group={{ antiek_group }}" in service
    assert "NoNewPrivileges=true" in service
    assert "TimeoutStartSec=60" in service
    assert "OnBootSec=2min" in timer
    assert "OnUnitActiveSec=5min" in timer
    assert "Unit=antiek-health-probe.service" in timer
    assert "WantedBy=timers.target" in timer


def test_deploy_renders_health_probe_before_daemon_reload() -> None:
    wrapper = _task("re-render Antiek health-probe wrapper")["ansible.builtin.template"]
    service = _task("re-render antiek-health-probe.service")
    timer = _task("re-render antiek-health-probe.timer")
    reload_task = _task("systemd daemon-reload if any unit changed")

    assert wrapper == {
        "src": "../templates/antiek-health-probe.sh.j2",
        "dest": "/usr/local/bin/antiek-health-probe",
        "owner": "root",
        "group": "{{ antiek_group }}",
        "mode": "0750",
    }
    assert service["ansible.builtin.template"]["dest"] == (
        "/etc/systemd/system/antiek-health-probe.service"
    )
    assert service["register"] == "antiek_health_probe_unit"
    assert timer["ansible.builtin.template"]["dest"] == (
        "/etc/systemd/system/antiek-health-probe.timer"
    )
    assert timer["register"] == "antiek_health_probe_timer"
    assert "antiek_health_probe_unit.changed" in reload_task["when"]
    assert "antiek_health_probe_timer.changed" in reload_task["when"]
    assert "default(false)" in reload_task["when"]
    assert "health_probe" in reload_task["tags"]
    assert _tasks().index(service) < _tasks().index(reload_task)
    assert _tasks().index(timer) < _tasks().index(reload_task)


def test_deploy_verifies_enables_and_rearms_health_probe_timer() -> None:
    verify_units = _task("verify Antiek health-probe systemd units")
    enable = _task("enable and start antiek-health-probe.timer")
    rearm = _task("re-arm antiek-health-probe.timer after timer unit changes")
    enabled = _task("verify antiek-health-probe.timer is enabled")
    active = _task("verify antiek-health-probe.timer is active")

    assert verify_units["ansible.builtin.command"]["argv"] == [
        "systemd-analyze",
        "verify",
        "/etc/systemd/system/antiek-health-probe.service",
        "/etc/systemd/system/antiek-health-probe.timer",
    ]
    assert verify_units["changed_when"] is False
    assert enable["ansible.builtin.systemd"] == {
        "name": "antiek-health-probe.timer",
        "enabled": True,
        "state": "started",
    }
    assert rearm["ansible.builtin.systemd"]["state"] == "restarted"
    assert rearm["when"] == "antiek_health_probe_timer.changed"
    assert enabled["ansible.builtin.command"]["argv"][1] == "is-enabled"
    assert active["ansible.builtin.command"]["argv"][1] == "is-active"
    assert enabled["changed_when"] is False
    assert active["changed_when"] is False


def test_health_probe_tag_selects_the_complete_topology() -> None:
    names = {
        "re-render Antiek health-probe wrapper",
        "re-render antiek-health-probe.service",
        "re-render antiek-health-probe.timer",
        "systemd daemon-reload if any unit changed",
        "verify Antiek health-probe systemd units",
        "enable and start antiek-health-probe.timer",
        "re-arm antiek-health-probe.timer after timer unit changes",
        "verify antiek-health-probe.timer is enabled",
        "verify antiek-health-probe.timer is active",
    }

    for name in names:
        assert "health_probe" in _task(name)["tags"], name
