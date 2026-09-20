"""In-process warm writer keepalive — skip DuckDB re-open between writes.

Cite: runtime/db_lock.py WP-3; #3121 coexist; #3164/#3165 fill contention.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import duckdb
import pytest

from runtime import db_lock


@pytest.fixture(autouse=True)
def _flush_warm():
    yield
    db_lock.flush_warm_writers()


def _count_opens(monkeypatch, db: str) -> list[str]:
    opens: list[str] = []
    real_connect = duckdb.connect

    def counting_connect(path, *a, **k):
        # Ignore write_log / other sidecar opens — only the primary DB path.
        if os.path.abspath(str(path)) == os.path.abspath(db):
            opens.append(str(path))
        return real_connect(path, *a, **k)

    monkeypatch.setattr(db_lock.duckdb, "connect", counting_connect)
    return opens


def test_warm_reuse_skips_second_duckdb_connect(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    assert db_lock._write_keepalive_s() == 30.0

    db = str(tmp_path / "warm.duckdb")
    opens = _count_opens(monkeypatch, db)

    with db_lock.connect_write(db, purpose="warm:first", timeout_s=5) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")
    assert len(opens) == 1

    with db_lock.connect_write(db, purpose="warm:second", timeout_s=5) as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 1
        con.execute("INSERT INTO t VALUES (2)")
    assert len(opens) == 1, opens

    db_lock.flush_warm_writers(db)
    with db_lock.connect_write(db, purpose="warm:after-flush", timeout_s=5) as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 2
    assert len(opens) == 2


def test_keepalive_zero_closes_fully(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0")
    assert db_lock._write_keepalive_s() == 0.0
    db = str(tmp_path / "cold.duckdb")
    opens = _count_opens(monkeypatch, db)
    with db_lock.connect_write(db, purpose="cold:1", timeout_s=5) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    assert db_lock.flush_warm_writers(db) == 0
    n_after_first = len(opens)
    assert n_after_first >= 1
    with db_lock.connect_write(db, purpose="cold:2", timeout_s=5) as con:
        con.execute("INSERT INTO t VALUES (1)")
    # keepalive=0 must open again (write_log may also connect to same path)
    assert len(opens) > n_after_first, opens


def test_open_transaction_does_not_park(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = str(tmp_path / "txn.duckdb")
    with db_lock.connect_write(db, purpose="txn:begin", timeout_s=5) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
        con.execute("BEGIN TRANSACTION")
        con.execute("INSERT INTO t VALUES (1)")
    assert db_lock.flush_warm_writers(db) == 0


def test_expired_warm_slot_reopens(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0.05")
    db = str(tmp_path / "exp.duckdb")
    opens = _count_opens(monkeypatch, db)
    with db_lock.connect_write(db, purpose="exp:1", timeout_s=5) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    time.sleep(0.12)
    with db_lock.connect_write(db, purpose="exp:2", timeout_s=5) as con:
        con.execute("INSERT INTO t VALUES (1)")
    assert len(opens) == 2


def test_pytest_forces_keepalive_off(monkeypatch):
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "99")
    assert os.environ.get("PYTEST_CURRENT_TEST")
    assert db_lock._write_keepalive_s() == 0.0
