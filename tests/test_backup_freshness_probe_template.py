"""Execution and deployment proofs for the scheduled backup observer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import jinja2  # type: ignore[import-untyped]

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "infrastructure" / "ansible" / "templates"
PLAYBOOKS = REPO / "infrastructure" / "ansible" / "playbooks"


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


def _render_probe(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    install = tmp_path / "install"
    state = tmp_path / "state"
    state.mkdir()
    _write_executable(
        install / ".venv/bin/python3",
        '#!/usr/bin/env bash\necho "${PROBE_VERDICT}"\nexit "${PROBE_STATUS}"\n',
    )
    source = (TEMPLATES / "antiek-backup-freshness-probe.sh.j2").read_text()
    rendered = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(source).render(
        ansible_managed="rendered by test",
        antiek_install_dir=str(install),
        antiek_state_dir=str(state),
    )
    script = tmp_path / "probe"
    _write_executable(script, rendered)

    curl_log = tmp_path / "curl.log"
    stub_bin = tmp_path / "bin"
    _write_executable(
        stub_bin / "curl",
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "${CURL_LOG}"\n',
    )
    env = dict(os.environ)
    env.update({"PATH": f"{stub_bin}:{env['PATH']}", "CURL_LOG": str(curl_log)})
    return script, env, curl_log


def test_fresh_probe_exits_zero_without_alert(tmp_path: Path) -> None:
    script, env, curl_log = _render_probe(tmp_path)
    env.update({"PROBE_STATUS": "0", "PROBE_VERDICT": "FRESH: verified backup"})
    proc = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "FRESH: verified backup" in proc.stdout
    assert not curl_log.exists()


def test_stale_probe_posts_webhook_and_stays_failed(tmp_path: Path) -> None:
    script, env, curl_log = _render_probe(tmp_path)
    env.update(
        {
            "PROBE_STATUS": "1",
            "PROBE_VERDICT": "STALE: no verified backup",
            "ANTIEK_ALERT_WEBHOOK": "https://alerts.invalid/hook",
        }
    )
    proc = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "STALE: no verified backup" in proc.stderr
    assert "https://alerts.invalid/hook" in curl_log.read_text()


def test_setup_and_deploy_enable_both_backup_timers() -> None:
    for name in ("setup.yml", "deploy.yml"):
        playbook = (PLAYBOOKS / name).read_text()
        assert "name: antiek-backup.timer" in playbook
        assert "name: antiek-backup-freshness.timer" in playbook
        assert "antiek-backup-freshness-probe.sh.j2" in playbook

    timer = (TEMPLATES / "antiek-backup-freshness.timer.j2").read_text()
    assert "Persistent=true" in timer
    assert "OnCalendar=" in timer

    backup_service = (TEMPLATES / "antiek-backup.service.j2").read_text()
    backup_script = (TEMPLATES / "backup.sh.j2").read_text()
    assert "RuntimeDirectory=antiek-backup" in backup_service
    assert "/run/antiek-backup/job.lock" in backup_script

    deploy = (PLAYBOOKS / "deploy.yml").read_text()
    assert deploy.index("re-render backup script before enabling its persistent timer") < deploy.index(
        "remove legacy backup cron job"
    ) < deploy.index("enable and start antiek-backup.timer")

    setup = (PLAYBOOKS / "setup.yml").read_text()
    assert "- jq" in setup
    assert "- util-linux" in setup
