from __future__ import annotations

import json

from substrate.ducklake.catalog import PostgresCatalogBackend
from tools.ops import ducklake_postgres_probe


class _FakeCursor:
    def __init__(self, rows=None, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakePostgresConnection:
    def __init__(self):
        self.rows = {}
        self.commits = 0

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        if compact.startswith("CREATE TABLE"):
            return _FakeCursor()
        if compact.startswith("INSERT INTO catalog_entries"):
            assert params is not None
            self.rows[params[0]] = tuple(params)
            return _FakeCursor(rowcount=1)
        if (
            compact.startswith("SELECT ")
            and compact.endswith("FROM catalog_entries WHERE user_id = %s")
        ):
            assert params is not None
            row = self.rows.get(params[0])
            return _FakeCursor(rows=[] if row is None else [row])
        if compact.startswith("SELECT ") and compact.endswith("FROM catalog_entries"):
            return _FakeCursor(rows=self.rows.values())
        if compact.startswith("DELETE FROM catalog_entries"):
            assert params is not None
            existed = self.rows.pop(params[0], None) is not None
            return _FakeCursor(rowcount=1 if existed else 0)
        raise AssertionError(f"unexpected SQL: {compact}")

    def commit(self):
        self.commits += 1


def _backend_factory(conn: _FakePostgresConnection):
    def factory(_: str) -> PostgresCatalogBackend:
        return PostgresCatalogBackend(conn=conn)

    return factory


def test_ducklake_postgres_probe_fails_without_dsn():
    result = ducklake_postgres_probe.probe_ducklake_postgres(dsn="")

    assert result.status == "FAIL"
    assert result.dsn_configured is False
    assert result.checks[0].name == "dsn_configured"


def test_ducklake_postgres_probe_passes_round_trip_and_cleanup():
    conn = _FakePostgresConnection()

    result = ducklake_postgres_probe.probe_ducklake_postgres(
        dsn="postgresql://example.invalid/antiek",
        backend_factory=_backend_factory(conn),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "PASS"
    assert checks["register_lookup_round_trip"].passed is True
    assert checks["cleanup_removed_probe_row"].passed is True
    assert "antiek-oa012-postgres-probe" not in conn.rows
    assert result.does_not_close_oa012 is True


def test_ducklake_postgres_probe_can_leave_row_for_inspection():
    conn = _FakePostgresConnection()

    result = ducklake_postgres_probe.probe_ducklake_postgres(
        dsn="postgresql://example.invalid/antiek",
        cleanup=False,
        backend_factory=_backend_factory(conn),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "PASS"
    assert checks["cleanup_removed_probe_row"].detail == (
        "cleanup skipped by operator request"
    )
    assert "antiek-oa012-postgres-probe" in conn.rows


def test_ducklake_postgres_probe_reports_backend_constructor_failure():
    def factory(_: str) -> PostgresCatalogBackend:
        raise RuntimeError("driver missing")

    result = ducklake_postgres_probe.probe_ducklake_postgres(
        dsn="postgresql://example.invalid/antiek",
        backend_factory=factory,
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["postgres_backend_constructed"].passed is False
    assert "driver missing" in checks["postgres_backend_constructed"].detail


def test_ducklake_postgres_probe_json_cli(monkeypatch, capsys):
    conn = _FakePostgresConnection()
    monkeypatch.setenv("ANTIEK_DUCKLAKE_POSTGRES_DSN", "postgresql://secret")
    monkeypatch.setattr(
        ducklake_postgres_probe,
        "_default_backend_factory",
        _backend_factory(conn),
    )

    exit_code = ducklake_postgres_probe.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["dsn_configured"] is True
    assert "postgresql://secret" not in json.dumps(payload)
