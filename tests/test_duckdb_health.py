"""GF-7 graph DuckDB health probe tests."""

from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api.app import create_app  # noqa: E402
from substrate.graph.health import (  # noqa: E402
    _storage_integrity,
    probe_duckdb_health,
)
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
    # Not `in {"ok", "unavailable"}`: that passed vacuously for the life of
    # this probe, because DuckDB has no `PRAGMA integrity_check` and the value
    # was always "unavailable". Asserting "ok" is what proves a check ran.
    assert health.integrity_check == "ok"
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
    assert body["duckdb_integrity_check"] == "ok"
    assert body["duckdb_wal_present"] is False
    assert body["duckdb_wal_bytes"] == 0
    assert body["duckdb_error"] is None


def test_storage_integrity_reports_catalog_failure():
    """The failure path is wired: a catalog that will not read is not 'ok'."""

    class _Boom:
        def execute(self, _sql):
            raise RuntimeError("catalog unreadable")

    assert _storage_integrity(_Boom()) == "failed: catalog: RuntimeError"


def test_storage_integrity_names_the_table_that_fails():
    """A table whose storage metadata will not parse is named, not swallowed."""

    class _OneBadTable:
        def __init__(self):
            self._first = True

        def execute(self, sql):
            if "duckdb_tables()" in sql:
                return _Rows([("good",), ("bad",)])
            if "pragma_storage_info('bad')" in sql:
                raise RuntimeError("block metadata unreadable")
            return _Rows([(1,)])

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0]

    assert _storage_integrity(_OneBadTable()) == "failed: bad: RuntimeError"


def test_storage_integrity_ok_on_a_real_initialized_database(tmp_path):
    """End to end against a real file: every base table's blocks parse."""
    import duckdb

    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        table_count = con.execute(
            "SELECT count(*) FROM duckdb_tables() "
            "WHERE schema_name = 'main' AND NOT internal"
        ).fetchone()[0]
        assert table_count > 0, "fixture must have tables for this to mean anything"
        assert _storage_integrity(con) == "ok"
    finally:
        con.close()


def test_empty_database_is_reported_empty_and_not_ready(tmp_path):
    """A valid file with no tables is 'empty' — distinct from 'ok' and not ready."""
    import duckdb

    db_path = tmp_path / "empty.duckdb"
    duckdb.connect(str(db_path)).close()

    health = probe_duckdb_health(str(db_path))

    assert health.integrity_check == "empty"
    assert health.schema_present is False
    assert health.ready is False
