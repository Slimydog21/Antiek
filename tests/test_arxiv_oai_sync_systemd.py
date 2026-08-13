from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_TEMPLATES = _REPO / "infrastructure" / "ansible" / "templates"
_DEPLOY = _REPO / "infrastructure" / "ansible" / "playbooks" / "deploy.yml"


def test_arxiv_oai_sync_service_pins_state_and_runs_incremental_cli():
    service = (_TEMPLATES / "antiek-arxiv-oai-sync.service.j2").read_text(
        encoding="utf-8"
    )

    assert "Type=oneshot" in service
    assert "User={{ antiek_user }}" in service
    assert "EnvironmentFile={{ antiek_secrets_file }}" in service
    assert (
        "ANTIEK_DUCKDB_PATH={{ antiek_state_dir }}/antiek.duckdb" in service
    )
    assert (
        "ANTIEK_ARXIV_THROTTLE_PATH={{ antiek_state_dir }}/arxiv_throttle.json"
        in service
    )
    assert (
        "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH={{ antiek_state_dir }}/arxiv_throttle.json.governor.lock"
        in service
    )
    assert (
        "ANTIEK_ARXIV_OAI_STATE_PATH={{ antiek_state_dir }}/arxiv_oai_harvest.json"
        in service
    )
    assert (
        "ANTIEK_ARXIV_OAI_SYNC_PATH={{ antiek_state_dir }}/arxiv_oai_sync.json"
        in service
    )
    assert (
        "python -m tools.arxiv_oai_sync incremental --bulk --census-json "
        "{{ antiek_state_dir }}/reports/arxiv_oai_census.json"
    ) in service
    assert (
        "python -m tools.source_census --source arxiv --db-path "
        "{{ antiek_state_dir }}/antiek.duckdb --out "
        "{{ antiek_state_dir }}/reports/source_census.json"
    ) in service
    assert "ReadWritePaths={{ antiek_state_dir }} /tmp /var/tmp" in service


def test_arxiv_oai_sync_timer_is_persistent_daily_timer():
    timer = (_TEMPLATES / "antiek-arxiv-oai-sync.timer.j2").read_text(
        encoding="utf-8"
    )

    assert "OnCalendar=*-*-* 04:20:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "Unit=antiek-arxiv-oai-sync.service" in timer
    assert "WantedBy=timers.target" in timer


def test_deploy_renders_and_enables_arxiv_oai_sync_timer():
    deploy = _DEPLOY.read_text(encoding="utf-8")

    assert "src: ../templates/antiek-arxiv-oai-sync.service.j2" in deploy
    assert "dest: /etc/systemd/system/antiek-arxiv-oai-sync.service" in deploy
    assert "src: ../templates/antiek-arxiv-oai-sync.timer.j2" in deploy
    assert "dest: /etc/systemd/system/antiek-arxiv-oai-sync.timer" in deploy
    assert (
        "name: antiek-arxiv-oai-sync.timer\n"
        "        enabled: true\n"
        "        state: started"
    ) in deploy
    assert "antiek_arxiv_oai_sync_unit.changed" in deploy
    assert "antiek_arxiv_oai_sync_timer.changed" in deploy
