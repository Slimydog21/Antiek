"""ACU meter + soft/hard gate at investigation start."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.compute_capacity.acu_meter import (
    ACU_PER_INVESTIGATION_START,
    WALL_TOPUP_MAX_ACU,
    WALL_TOPUP_QUANTUM_SECONDS,
    compute_wall_topup_acu,
    gate_investigation_start,
    record_investigation_start_acu,
    record_investigation_wall_topup_acu,
    wall_topup_ledger_id,
)
from substrate.compute_capacity.store import set_capacity


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-acu-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "soft")
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_one_acu_per_investigation_start_constant():
    assert ACU_PER_INVESTIGATION_START == 1


def test_record_increments_and_is_idempotent(isolated_db):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:acu") as con:
        set_capacity(con, owner_user_id="owner-a", tier="starter")
        r1 = record_investigation_start_acu(
            con, owner_user_id="owner-a", investigation_id="inv-1"
        )
        assert r1.replayed is False
        assert r1.capacity.used_status == "known"
        assert r1.capacity.used_compute_units == 1
        r2 = record_investigation_start_acu(
            con, owner_user_id="owner-a", investigation_id="inv-1"
        )
        assert r2.replayed is True
        assert r2.capacity.used_compute_units == 1
        r3 = record_investigation_start_acu(
            con, owner_user_id="owner-a", investigation_id="inv-2"
        )
        assert r3.capacity.used_compute_units == 2


def test_soft_warn_near_limit(isolated_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "soft")
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:soft") as con:
        set_capacity(
            con, owner_user_id="owner-a", tier="custom", monthly_compute_units=5
        )
        for i in range(4):
            record_investigation_start_acu(
                con, owner_user_id="owner-a", investigation_id=f"inv-n{i}"
            )
        gate = gate_investigation_start(con, "owner-a")
        assert gate.verdict == "soft_warn"
        assert gate.warning is not None


def test_hard_refuse_when_exhausted(isolated_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:hard") as con:
        set_capacity(
            con, owner_user_id="owner-a", tier="custom", monthly_compute_units=1
        )
        record_investigation_start_acu(
            con, owner_user_id="owner-a", investigation_id="inv-only"
        )
        gate = gate_investigation_start(con, "owner-a")
        assert gate.verdict == "hard_refuse"
        assert gate.detail == "compute_capacity_exhausted"


def test_http_post_investigations_meters_and_soft_warns(isolated_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "soft")
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:seed-cap") as con:
        set_capacity(
            con, owner_user_id="__operator__", tier="custom", monthly_compute_units=2
        )
        record_investigation_start_acu(
            con, owner_user_id="__operator__", investigation_id="inv-seed"
        )

    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    r = client.post("/investigations", json={"question": "What is ACU metering?"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "started"
    assert body.get("capacity_warning") is not None
    assert r.headers.get("X-Antiek-Capacity-Warn") == "compute_capacity_soft_warn"

    g = client.get("/settings/compute-capacity")
    assert g.status_code == 200
    assert g.json()["used_status"] == "known"
    assert g.json()["used_compute_units"] >= 2


def test_http_hard_refuse_429(isolated_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:hard-http") as con:
        set_capacity(
            con, owner_user_id="__operator__", tier="custom", monthly_compute_units=1
        )
        record_investigation_start_acu(
            con, owner_user_id="__operator__", investigation_id="inv-fill"
        )

    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    r = client.post("/investigations", json={"question": "Should be refused"})
    assert r.status_code == 429
    assert r.json()["detail"] == "compute_capacity_exhausted"



def test_wall_topup_heuristic():
    assert WALL_TOPUP_QUANTUM_SECONDS == 300
    assert WALL_TOPUP_MAX_ACU == 12
    assert compute_wall_topup_acu(0) == 0
    assert compute_wall_topup_acu(299.9) == 0
    assert compute_wall_topup_acu(300) == 1
    assert compute_wall_topup_acu(599) == 1
    assert compute_wall_topup_acu(600) == 2
    assert compute_wall_topup_acu(300 * 20) == 12  # capped
    assert wall_topup_ledger_id("inv-x") == "inv-x#wall_topup"


def test_wall_topup_increments_and_idempotent(isolated_db):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:wall") as con:
        set_capacity(con, owner_user_id="owner-a", tier="starter")
        record_investigation_start_acu(
            con, owner_user_id="owner-a", investigation_id="inv-long"
        )
        assert get_used(con, "owner-a") == 1
        r1 = record_investigation_wall_topup_acu(
            con,
            investigation_id="inv-long",
            wall_seconds=900,  # 3 quanta
        )
        assert r1 is not None
        assert r1.replayed is False
        assert r1.acu_units == 3
        assert get_used(con, "owner-a") == 4
        r2 = record_investigation_wall_topup_acu(
            con,
            investigation_id="inv-long",
            wall_seconds=900,
        )
        assert r2 is not None
        assert r2.replayed is True
        assert get_used(con, "owner-a") == 4


def test_wall_topup_zero_under_quantum(isolated_db):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:wall0") as con:
        set_capacity(con, owner_user_id="owner-a", tier="starter")
        record_investigation_start_acu(
            con, owner_user_id="owner-a", investigation_id="inv-short"
        )
        r = record_investigation_wall_topup_acu(
            con, investigation_id="inv-short", wall_seconds=120
        )
        assert r is None
        assert get_used(con, "owner-a") == 1


def test_wall_topup_no_start_row(isolated_db):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:wall-none") as con:
        set_capacity(con, owner_user_id="owner-a", tier="starter")
        r = record_investigation_wall_topup_acu(
            con, investigation_id="never-started", wall_seconds=600
        )
        assert r is None


def get_used(con, owner):
    from substrate.compute_capacity.store import get_capacity

    return get_capacity(con, owner).used_compute_units
