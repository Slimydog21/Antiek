"""Stats distinguish a lazy skill registry from failed table counts."""

from __future__ import annotations

import hashlib

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.graph import ensure_initialized


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "stats.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(path))
    ensure_initialized(str(path))
    return path


def stats():
    response = TestClient(create_app(register_wrestling=False)).get("/stats")
    assert response.status_code == 200
    return response.json()


def test_fresh_database_has_quiet_optional_zero_without_schema_write(db_path):
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    body = stats()
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()

    assert body["counts"]["skill_rules"] == 0
    assert not any("skill_rules" in warning for warning in body["warnings"])
    assert before == after
    with duckdb.connect(str(db_path), read_only=True) as con:
        assert con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'skill_rules'"
        ).fetchone() is None


def test_present_skill_registry_is_counted(db_path):
    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE TABLE skill_rules (rule_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO skill_rules VALUES ('rule-a'), ('rule-b')")

    body = stats()
    assert body["counts"]["skill_rules"] == 2
    assert not any("skill_rules" in warning for warning in body["warnings"])


def test_missing_required_table_still_warns(db_path):
    with duckdb.connect(str(db_path)) as con:
        con.execute("DROP TABLE payout_transfers")

    body = stats()
    assert body["counts"]["payout_transfers"] == 0
    assert "table 'payout_transfers' not present" in body["warnings"]


def test_present_registry_count_failure_is_not_labeled_absent(db_path, monkeypatch):
    from runtime import db_lock

    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE TABLE skill_rules (rule_id TEXT PRIMARY KEY)")

    original_connect_read = db_lock.connect_read

    class FailingCountConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, *args):
            if sql == "SELECT COUNT(*) FROM skill_rules":
                raise duckdb.CatalogException("synthetic count failure")
            return self.connection.execute(sql, *args)

    def failing_connect_read(path):
        return FailingCountConnection(original_connect_read(path))

    monkeypatch.setattr(db_lock, "connect_read", failing_connect_read)
    body = stats()
    assert body["counts"]["skill_rules"] == 0
    assert any(
        "skill_rules" in warning and "synthetic count failure" in warning
        for warning in body["warnings"]
    )
    assert "table 'skill_rules' not present" not in body["warnings"]
