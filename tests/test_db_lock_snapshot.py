"""Read-only snapshots share warm-writer handoff without source mutations."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import duckdb
import pytest

from runtime import db_lock


@pytest.fixture(autouse=True)
def clean_warm_slots():
    yield
    db_lock.flush_warm_writers()


def seed(path: Path) -> str:
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")
        con.execute("CREATE TABLE write_log (purpose VARCHAR)")
        con.execute("CHECKPOINT")
    return str(path)


def digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_snapshot_is_read_only_and_never_logs_even_on_body_failure(tmp_path):
    db = seed(tmp_path / "snapshot.duckdb")
    before = digest(db)
    with pytest.raises(ValueError, match="consumer"), db_lock.snapshot_read(db) as con:
        assert con.execute("SELECT * FROM t").fetchall() == [(1,)]
        with pytest.raises(duckdb.InvalidInputException):
            con.execute("INSERT INTO t VALUES (2)")
        raise ValueError("consumer error")
    assert digest(db) == before
    with db_lock.snapshot_read(db, timeout_s=1) as con:
        assert con.execute("SELECT count(*) FROM write_log").fetchone()[0] == 0
    assert not list(Path(db + ".write.waiters").glob("*"))


def test_snapshot_timeout_preserves_lock_inode_and_cleans_token(tmp_path):
    import fcntl

    db = seed(tmp_path / "busy.duckdb")
    lock_path = Path(db + ".write.lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        inode = lock_path.stat().st_ino
        before = digest(db)
        with (
            pytest.raises(db_lock.WriteLockTimeout),
            db_lock.snapshot_read(db, timeout_s=0.05, poll_interval_s=0.005),
        ):
            pytest.fail("must not enter snapshot")
        assert lock_path.stat().st_ino == inode
        assert digest(db) == before
        assert not list(Path(db + ".write.waiters").iterdir())


def test_snapshot_waits_for_existing_local_read_fallback_to_close(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = seed(tmp_path / "reader.duckdb")
    with db_lock.connect_write(db) as con:
        con.execute("SELECT * FROM t")
    reader = db_lock.connect_read(db)
    assert isinstance(reader, db_lock._ReadOrientedConnection)
    # DuckDB cannot open a physically RO handle until the same-config reader
    # releases its RW handle, even after the parked writer has yielded.
    close_reader = threading.Timer(0.25, reader.close)
    close_reader.start()
    try:
        with db_lock.snapshot_read(db, timeout_s=2, poll_interval_s=0.01) as con:
            assert con.execute("SELECT * FROM t").fetchall() == [(1,)]
            with pytest.raises(duckdb.InvalidInputException):
                con.execute("INSERT INTO t VALUES (2)")
    finally:
        close_reader.join()
        reader.close()


def test_snapshot_open_error_cleans_lock_without_creating_database(tmp_path):
    db = str(tmp_path / "absent.duckdb")
    with pytest.raises(duckdb.IOException), db_lock.snapshot_read(db, timeout_s=0.2):
        pytest.fail("must not create missing source")
    assert not Path(db).exists()
    with duckdb.connect(db) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
    with db_lock.snapshot_read(db, timeout_s=0.2) as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 0
