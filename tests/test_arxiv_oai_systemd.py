"""ASR SR-09 P4 operator wiring for the arXiv OAI-PMH sync.

The sync code path itself is covered by ``tests/test_arxiv_oai_sync.py`` with
mocked OAI pages. These tests guard the production surface that can otherwise
strand the code path: systemd templates plus Ansible render/enable tasks.
"""

from __future__ import annotations

from pathlib import Path


_REPO = Path(__file__).resolve().parents[1]
_TEMPLATES = _REPO / "infrastructure" / "ansible" / "templates"
_PLAYBOOKS = _REPO / "infrastructure" / "ansible" / "playbooks"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_arxiv_oai_sync_service_runs_incremental_with_live_state_paths():
    service = _read(_TEMPLATES / "antiek-arxiv-oai-sync.service.j2")

    assert "Type=oneshot" in service
    assert "User={{ antiek_user }}" in service
    assert "ConditionPathExists={{ antiek_state_dir }}/antiek.duckdb" in service
    assert "EnvironmentFile={{ antiek_secrets_file }}" in service
    assert (
        'Environment="ANTIEK_DUCKDB_PATH={{ antiek_state_dir }}/antiek.duckdb"'
        in service
    )
    assert (
        'Environment="ANTIEK_ARXIV_OAI_SYNC_PATH={{ antiek_state_dir }}/'
        'arxiv_oai_sync.json"'
    ) in service
    assert (
        'Environment="ANTIEK_ARXIV_GOVERNOR_LOCK_PATH={{ antiek_state_dir }}/'
        'arxiv_governor.lock"'
    ) in service
    assert (
        "ExecStart={{ antiek_install_dir }}/.venv/bin/python -m "
        "tools.arxiv_oai_sync incremental --census-json "
        "{{ antiek_state_dir }}/arxiv_oai_sync_census.json"
    ) in service
    assert "ReadWritePaths={{ antiek_state_dir }} /tmp /var/tmp" in service
    assert "ProtectSystem=strict" in service
    assert "MemoryDenyWriteExecute=true" in service


def test_arxiv_oai_sync_timer_is_persistent_daily_timer():
    timer = _read(_TEMPLATES / "antiek-arxiv-oai-sync.timer.j2")

    assert "OnCalendar=*-*-* 04:20:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "RandomizedDelaySec=20min" in timer
    assert "Unit=antiek-arxiv-oai-sync.service" in timer
    assert "WantedBy=timers.target" in timer


def test_ansible_setup_and_deploy_render_and_enable_oai_timer():
    setup = _read(_PLAYBOOKS / "setup.yml")
    deploy = _read(_PLAYBOOKS / "deploy.yml")

    for playbook in (setup, deploy):
        assert "antiek-arxiv-oai-sync.service.j2" in playbook
        assert "dest: /etc/systemd/system/antiek-arxiv-oai-sync.service" in playbook
        assert "antiek-arxiv-oai-sync.timer.j2" in playbook
        assert "dest: /etc/systemd/system/antiek-arxiv-oai-sync.timer" in playbook
        assert "name: antiek-arxiv-oai-sync.timer" in playbook
        assert "enabled: true" in playbook
        assert "tags: [systemd, arxiv, oai]" in playbook

    assert "state: started" in deploy
