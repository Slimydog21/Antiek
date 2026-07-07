"""GF-7 graph DuckDB health probe tests."""

from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api.app import create_app  # noqa: E402
from substrate.graph.health import probe_duckdb_health  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402


def test_duckdb_health_reports_missing_file(tmp_path):
    missing = tmp_path / "missing.duckdb"

    health = probe_duckdb_health(str(missing))

    assert health.ready is False
    assert health.status == "missing"
    assert health.schema_present is False
    assert health.error == "DuckDB file does not exist"


def test_duckdb_health_reports_initialized_db(tmp_path):
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))

    health = probe_duckdb_health(str(db_path))

    assert health.ready is True
    assert health.status == "ok"
    assert health.schema_present is True
    assert health.database_size_ok is True
    assert health.integrity_check in {"ok", "unavailable"}
    assert health.error is None


def test_duckdb_health_reports_corrupt_file(tmp_path):
    db_path = tmp_path / "graph.duckdb"
    db_path.write_bytes(b"not a duckdb database")

    health = probe_duckdb_health(str(db_path))

    assert health.ready is False
    assert health.status == "open_failed"
    assert health.error is not None


def test_health_route_exposes_duckdb_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    body = TestClient(app).get("/health").json()

    assert body["duckdb_ready"] is True
    assert body["duckdb_status"] == "ok"
    assert body["duckdb_schema_present"] is True
    assert body["duckdb_database_size_ok"] is True
    assert body["duckdb_integrity_check"] in {"ok", "unavailable"}
    assert body["duckdb_wal_present"] is False
    assert body["duckdb_wal_bytes"] == 0
    assert body["duckdb_error"] is None
