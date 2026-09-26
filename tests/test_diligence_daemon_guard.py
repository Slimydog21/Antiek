"""The diligence daemon cannot spawn until spawning is real and consented (LB-10).

With ANTIEK_DAEMON_SPAWN_ENABLED set, main() used to wire make_emit_spawn_fn
over a fresh EventBroadcaster in the daemon's own process, and the investigation
handler lives in the API process. So each "spawn" logged a start_requested
nobody ran, while its $0.50 reserve and its concurrency slot were still taken.
It also launched a flag with no per-flag consent, against D4
(specs/antiek-mothership/DECISIONS.md) and THREAD-CONTRACT §1.13. Until spawns
route through the API with consent, turning the switch on is refused with
EX_CONFIG, before anything is wired.

The store's post-write re-reads also must not vanish under ``python -O``.
"""

from __future__ import annotations

import pytest

import orchestration.continuous.daemon as daemon_mod
from runtime.db_lock import connect_write
from substrate.diligence.store import DiligenceStore
from substrate.graph import ensure_initialized


def test_the_switch_on_refuses_to_start_before_anything_is_wired(monkeypatch, tmp_path):
    ran: list[dict] = []
    built: list[str] = []
    monkeypatch.setattr(daemon_mod, "run_forever", lambda **kw: ran.append(kw))
    monkeypatch.setattr(daemon_mod, "make_emit_spawn_fn", lambda *a, **k: built.append("spawn"))
    monkeypatch.setattr(daemon_mod, "DbFlagSource", lambda *a, **k: built.append("flags"))
    monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "g.duckdb"))
    with pytest.raises(SystemExit) as exit_info:
        daemon_mod.main()
    assert exit_info.value.code == daemon_mod.EX_CONFIG == 78
    assert ran == [] and built == []


def test_the_switch_off_still_runs_the_scoring_only_daemon(monkeypatch):
    ran: list[dict] = []
    monkeypatch.setattr(daemon_mod, "run_forever", lambda **kw: ran.append(kw))
    monkeypatch.delenv("ANTIEK_DAEMON_SPAWN_ENABLED", raising=False)
    daemon_mod.main()
    (kwargs,) = ran
    assert kwargs["spawn_fn"] is daemon_mod.no_op_spawn
    assert kwargs["flag_source"] is None


@pytest.mark.parametrize("method", ["dismiss", "mark_spawned"])
def test_a_flag_that_vanishes_after_its_write_fails_loudly(monkeypatch, tmp_path, method):
    db = str(tmp_path / "g.duckdb")
    ensure_initialized(db)
    store = DiligenceStore()
    with connect_write(db, purpose="test/diligence-vanish") as con:
        created, _ = store.create_flag(
            con, owner_user_id="owner-1", kind="concept", object_ref="concept:x",
            note=None, source_investigation_id=None, source_document_id=None,
        )
        flag_id = created.flag_id
        real_get = store.get_for_owner
        calls = {"n": 0}

        def get_then_vanish(*args, **kwargs):
            calls["n"] += 1
            return real_get(*args, **kwargs) if calls["n"] == 1 else None

        monkeypatch.setattr(store, "get_for_owner", get_then_vanish)
        extra = {"spawned_investigation_id": "inv-x"} if method == "mark_spawned" else {}
        with pytest.raises(RuntimeError, match=f"diligence flag {flag_id} vanished"):
            getattr(store, method)(con, owner_user_id="owner-1", flag_id=flag_id, **extra)


def test_the_unit_does_not_restart_a_refused_configuration():
    # Restart=on-failure with RestartSec=30s would relaunch an EX_CONFIG exit
    # forever; the unit must hold the refusal down, on the same code main() uses.
    from pathlib import Path

    unit = Path("infrastructure/ansible/templates/antiek-continuous-research.service.j2").read_text()
    prevent = [line.split("=", 1)[1].split() for line in unit.splitlines()
               if line.startswith("RestartPreventExitStatus=")]
    assert prevent and str(daemon_mod.EX_CONFIG) in prevent[0]


def test_the_once_smoke_run_refuses_the_switch_like_the_service(monkeypatch):
    import sys

    import orchestration.continuous.__main__ as cli

    ran: list[str] = []
    monkeypatch.setattr(daemon_mod, "run_one_iteration", lambda **kw: ran.append("tick"))
    monkeypatch.setattr(sys, "argv", ["python -m orchestration.continuous", "--once"])
    monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_ENABLED", "1")
    with pytest.raises(SystemExit) as refused:
        cli.main()
    assert refused.value.code == daemon_mod.EX_CONFIG
    assert ran == []
