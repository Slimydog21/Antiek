"""Deployment topology contract for the five-minute production health probe."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "infrastructure" / "ansible" / "templates"
DEPLOY_PATH = ROOT / "infrastructure" / "ansible" / "playbooks" / "deploy_atomic.yml"


def _tasks() -> list[dict[str, object]]:
    document = yaml.safe_load(DEPLOY_PATH.read_text(encoding="utf-8"))
    deploy_play = next(play for play in document if play.get("hosts") == "antiek_prod")

    def walk(tasks: list[dict[str, object]]):
        for task in tasks:
            yield task
            for key in ("block", "rescue", "always"):
                yield from walk(task.get(key, []))

    return list(walk(deploy_play["tasks"]))


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


def test_deploy_renders_and_verifies_the_health_probe_topology() -> None:
    units = _task("render background and probe units")["loop"]
    scripts = _task("render scripts consumed through the stable release path")["loop"]
    verify = _task("verify all rendered systemd units")["ansible.builtin.command"]["argv"]
    assert {
        "src": "../templates/antiek-health-probe.service.j2",
        "dest": "/etc/systemd/system/antiek-health-probe.service",
    } in units
    assert {
        "src": "../templates/antiek-health-probe.timer.j2",
        "dest": "/etc/systemd/system/antiek-health-probe.timer",
    } in units
    assert {
        "src": "../templates/antiek-health-probe.sh.j2",
        "dest": "/usr/local/bin/antiek-health-probe",
    } in scripts
    assert "/etc/systemd/system/antiek-health-probe.service" in verify
    assert "/etc/systemd/system/antiek-health-probe.timer" in verify


def test_deploy_quiesces_and_resumes_the_health_probe_around_cutover() -> None:
    pause = _task("pause every release-path consumer before cutover")
    resume = _task("resume background consumers after candidate is active")
    assert "antiek-health-probe.service" in pause["loop"]
    assert "antiek-health-probe.timer" in pause["loop"]
    assert "antiek-health-probe.timer" in resume["loop"]
    assert _tasks().index(pause) < _tasks().index(resume)


def test_health_probe_release_uses_the_exact_candidate_chain() -> None:
    names = [task.get("name", "") for task in _tasks()]
    cutover = names.index("make the one public API/SPA cutover")
    start = names.index("start antiek into the candidate release")
    verify = names.index("run blocking public parity on the candidate")
    assert cutover < start < verify
