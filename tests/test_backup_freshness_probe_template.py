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
        "#!/usr/bin/env bash\n"
        'if [[ "${PYTHON_CALL:-}" == "freshness" ]]; then\n'
        '    echo "${PROBE_VERDICT}"\n'
        '    exit "${PROBE_STATUS}"\n'
        "fi\n"
        'if [[ "${PYTHON_MODE:-}" == "email" ]]; then\n'
        '    printf \'to=%s args=%s\\n\' "${EMAIL_TO:-}" "$*" >> "${EMAIL_LOG}"\n'
        '    exit "${EMAIL_STATUS:-0}"\n'
        "fi\n"
        'echo "${PROBE_VERDICT}"\n'
        'exit "${PROBE_STATUS}"\n',
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
        '#!/usr/bin/env bash\n'
        'printf \'%s\\n\' "$*" >> "${CURL_LOG}"\n'
        'exit "${CURL_STATUS:-0}"\n',
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


def test_stale_probe_uses_email_when_webhook_fails(tmp_path: Path) -> None:
    script, env, curl_log = _render_probe(tmp_path)
    email_log = tmp_path / "email.log"
    env.update(
        {
            "PROBE_STATUS": "1",
            "PROBE_VERDICT": "STALE: no verified backup",
            "ANTIEK_ALERT_WEBHOOK": "https://alerts.invalid/hook",
            "ANTIEK_OPERATOR_EMAIL": "operator@antiek.ai",
            "ANTIEK_EMAIL_PROVIDER": "agentmail",
            "PYTHON_MODE": "email",
            "EMAIL_TO": "operator@antiek.ai",
            "EMAIL_STATUS": "0",
            "EMAIL_LOG": str(email_log),
            "CURL_STATUS": "22",
        }
    )
    proc = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "WARN: backup freshness webhook delivery failed" in proc.stderr
    assert "STALE: no verified backup" in proc.stderr
    assert email_log.exists()
    assert "to=operator@antiek.ai" in email_log.read_text()
    assert "https://alerts.invalid/hook" in curl_log.read_text()


def test_stale_probe_warns_when_no_alert_channel_works(tmp_path: Path) -> None:
    script, env, _ = _render_probe(tmp_path)
    env.update(
        {
            "PROBE_STATUS": "1",
            "PROBE_VERDICT": "STALE: no verified backup",
            "ANTIEK_OPERATOR_EMAIL": "operator@antiek.ai",
            "ANTIEK_EMAIL_PROVIDER": "mock",
            "PYTHON_MODE": "email",
            "EMAIL_STATUS": "3",
        }
    )
    proc = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "WARN: backup freshness email fallback failed" in proc.stderr
    assert "WARN: no working backup freshness alert channel" in proc.stderr


def test_setup_and_deploy_enable_both_backup_timers() -> None:
    setup = (PLAYBOOKS / "setup.yml").read_text()
    deploy = (PLAYBOOKS / "deploy_atomic.yml").read_text()
    assert "name: antiek-backup.timer" in setup
    assert "antiek-backup.timer" in deploy
    assert "/etc/systemd/system/antiek-backup-freshness.timer" in deploy
    assert "../templates/antiek-backup-freshness-probe.sh.j2" in deploy

    # Deploy owns the timer lifecycle around DuckDB migration: pause before
    # the exclusive writer window, resume only after antiek is active.
    pause = deploy.index("pause every release-path consumer before cutover")
    resume = deploy.index("resume background consumers after candidate is active")
    ready = deploy.index("wait for systemd active")
    assert pause < ready < resume

    timer = (TEMPLATES / "antiek-backup-freshness.timer.j2").read_text()
    assert "Persistent=true" in timer
    assert "OnCalendar=" in timer

    backup_service = (TEMPLATES / "antiek-backup.service.j2").read_text()
    backup_script = (TEMPLATES / "backup.sh.j2").read_text()
    assert "StateDirectory=antiek-backup" in backup_service
    assert '${STAGING_ROOT%/}/job.lock' in backup_script

    assert deploy.index("render scripts consumed through the stable release path") < pause

    assert "- jq" in setup
    assert "- util-linux" in setup
