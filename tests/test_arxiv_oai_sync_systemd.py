from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_TEMPLATES = _REPO / "infrastructure" / "ansible" / "templates"
_DEPLOY = _REPO / "infrastructure" / "ansible" / "playbooks" / "deploy_atomic.yml"


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
    # #3065 renders --bulk into the unit; the assertion tracks the
    # shipped template (a bare --census-json pass is no longer what
    # the timer runs).
    assert (
        "python -m tools.arxiv_oai_sync incremental --bulk "
        "--persist-batch-size 200 --max-lock-seconds 15 --lock-yield-seconds 0.5 "
        "--census-json {{ antiek_state_dir }}/reports/arxiv_oai_census.json"
    ) in service
    exec_start = next(
        line for line in service.splitlines() if line.startswith("ExecStart=")
    )
    assert exec_start.startswith(
        "ExecStart=/usr/bin/env ANTIEK_WRITE_KEEPALIVE_S=0 "
        "{{ antiek_install_dir }}/.venv/bin/python -m tools.arxiv_oai_sync "
    )
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


def test_deploy_prod_parity_uses_python3():
    deploy = _DEPLOY.read_text(encoding="utf-8")
    assert (
        "python3 {{ playbook_dir }}/../../../tools/prod_parity/check.py"
        in deploy
    )
    assert (
        "python {{ playbook_dir }}/../../../tools/prod_parity/check.py"
        not in deploy
    )


def test_deploy_renders_and_enables_arxiv_oai_sync_timer():
    deploy = _DEPLOY.read_text(encoding="utf-8")

    assert "src: ../templates/antiek-arxiv-oai-sync.service.j2" in deploy
    assert "dest: /etc/systemd/system/antiek-arxiv-oai-sync.service" in deploy
    assert "src: ../templates/antiek-arxiv-oai-sync.timer.j2" in deploy
    assert "dest: /etc/systemd/system/antiek-arxiv-oai-sync.timer" in deploy
    # The deploy pauses this timer for exclusive schema migration, then resumes
    # it only after antiek.service is active on the immutable release.
    assert "pause every release-path consumer before cutover" in deploy
    assert "resume background consumers after candidate is active" in deploy
    assert deploy.index("pause every release-path consumer before cutover") < deploy.index(
        "resume background consumers after candidate is active"
    )


def test_arxiv_sync_unit_is_cgroup_capped_like_its_siblings():
    """Prod 2026-10-01: this was the ONE long-running worker with no cgroup
    caps — `systemctl show -p MemoryMax -p CPUQuotaPerSecUSec` returned
    `infinity` for both, while antiek.service is 12G/300% and
    antiek-continuous-research.service is 6G/200%. On a 15 GB / 4 vCPU box the
    uncapped unit walks a 4.5 GB metadata file next to the DuckDB writer, so a
    runaway here hurts the API, not itself."""
    unit = (_TEMPLATES / "antiek-arxiv-oai-sync.service.j2").read_text(encoding="utf-8")

    assert "MemoryMax=3G" in unit
    assert "MemoryHigh=2.5G" in unit
    assert "CPUQuota=150%" in unit
    assert "MemorySwapMax=0" in unit
    assert "TasksMax=256" in unit
    # The caps must be sibling to the hardening, inside [Service] — a directive
    # appended after a [Install] section would be ignored by systemd, which is
    # the silent way this fix could not work.
    service_at = unit.index("[Service]")
    install_at = unit.index("[Install]") if "[Install]" in unit else len(unit)
    for directive in ("MemoryMax=", "MemoryHigh=", "CPUQuota=", "TasksMax="):
        position = unit.index(directive)
        assert service_at < position < install_at, f"{directive} is outside [Service]"

    # The two sibling templates keep their own caps: this change must not have
    # been made by copying one of them over the other.
    services = (_TEMPLATES / "antiek.service.j2").read_text(encoding="utf-8")
    continuous = (_TEMPLATES / "antiek-continuous-research.service.j2").read_text(encoding="utf-8")
    assert "MemoryMax=12G" in services
    assert "MemoryMax=6G" in continuous
