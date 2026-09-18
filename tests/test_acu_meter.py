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
    gate_investigation_start,
    record_investigation_start_acu,
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
