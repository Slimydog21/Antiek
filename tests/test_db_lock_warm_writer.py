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


def _external_writer(db: str, timeout: float = 2.0):
    import subprocess
    import sys

    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["ANTIEK_WRITE_KEEPALIVE_S"] = "0"
    return subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "from runtime.db_lock import connect_write; import sys; "
            "c=connect_write(sys.argv[1], timeout_s=float(sys.argv[2]), "
            'poll_interval_s=0.01, purpose="external-test", close_log_max_wait_s=0); '
            'print(c.execute("SELECT count(*) FROM t").fetchone()[0], flush=True); c.close()',
            db,
            str(timeout),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_idle_warm_owner_releases_without_another_local_acquisition(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0.15")
    db = str(tmp_path / "idle.duckdb")
    with db_lock.connect_write(db, purpose="idle-owner") as con:
        con.execute("CREATE TABLE t (id INTEGER)")
    child = _external_writer(db)
    try:
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, stderr
        assert stdout.strip() == "0"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_hot_local_writer_yields_to_published_external_waiter(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = str(tmp_path / "hot.duckdb")
    with db_lock.connect_write(db, purpose="hot-owner") as con:
        con.execute("CREATE TABLE t (id INTEGER)")
    child = _external_writer(db)
    try:
        deadline = time.monotonic() + 5
        while not db_lock.write_handoff_requested(db):
            assert child.poll() is None, child.communicate()
            assert time.monotonic() < deadline
            time.sleep(0.005)
        # A published contender must get a turn even if a local writer arrives.
        with db_lock.connect_write(db, timeout_s=4, poll_interval_s=0.01) as con:
            con.execute("INSERT INTO t VALUES (1)")
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, stderr
        assert stdout.strip() == "0", "Local reuse overtook an existing external waiter"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_idle_expiry_releases_for_unannounced_flock_contender(tmp_path, monkeypatch):
    import subprocess
    import sys

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0.15")
    db = str(tmp_path / "raw-contender.duckdb")
    with db_lock.connect_write(db) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,sys; "
            'f=open(sys.argv[1]+".write.lock","w"); '
            'fcntl.flock(f,fcntl.LOCK_EX); print("acquired",flush=True)',
            db,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, stderr
        assert stdout.strip() == "acquired"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_stale_expiry_cannot_close_reused_or_reparked_connection(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = str(tmp_path / "generation.duckdb")
    key = db_lock._warm_key(db)
    with db_lock.connect_write(db) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
    old = db_lock._warm_slots[key]
    with db_lock.connect_write(db) as con:
        old.expires_mono = 0
        assert db_lock._expire_warm_slot(key, old)
        con.execute("INSERT INTO t VALUES (1)")
    replacement = db_lock._warm_slots[key]
    assert replacement is not old
    assert db_lock._expire_warm_slot(key, old)
    assert db_lock._warm_slots[key] is replacement
    with db_lock.connect_write(db) as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 1


def test_expiry_start_failure_closes_handle_and_releases_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = str(tmp_path / "thread-failure.duckdb")

    def unavailable(*args, **kwargs):
        raise RuntimeError("cannot start new thread")

    monkeypatch.setattr(db_lock, "_schedule_warm_expiry", unavailable)
    with db_lock.connect_write(db, close_log_max_wait_s=0) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
    assert db_lock.flush_warm_writers(db) == 0
    assert not db_lock._PROCESS_WRITE_GATE.locked()
    with db_lock.connect_write(db, timeout_s=1) as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 0


def test_handoff_probe_failure_does_not_strand_warm_connection(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = str(tmp_path / "probe-failure.duckdb")
    con = db_lock.connect_write(db, close_log_max_wait_s=0)
    con.execute("CREATE TABLE t (id INTEGER)")

    def inaccessible(path):
        raise OSError("waiter directory unavailable")

    monkeypatch.setattr(db_lock, "write_handoff_requested", inaccessible)
    con.close()
    assert db_lock.flush_warm_writers(db) == 0
    assert not db_lock._PROCESS_WRITE_GATE.locked()
    assert not db_lock._has_local_writer(db)


def test_flush_and_expiry_destroy_each_lease_once(tmp_path, monkeypatch):
    import threading

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    destroyed = []
    real_destroy = db_lock._destroy_warm_slot

    def count_destroy(slot):
        destroyed.append(slot)
        real_destroy(slot)

    monkeypatch.setattr(db_lock, "_destroy_warm_slot", count_destroy)
    db = str(tmp_path / "flush-race.duckdb")
    for _ in range(10):
        with db_lock.connect_write(db) as con:
            con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
        slot = db_lock._warm_slots[db_lock._warm_key(db)]
        slot.expires_mono = 0
        barrier = threading.Barrier(3)

        def expire(barrier=barrier, slot=slot):
            barrier.wait()
            db_lock._expire_warm_slot(db_lock._warm_key(db), slot)

        def flush(barrier=barrier):
            barrier.wait()
            db_lock.flush_warm_writers(db)

        threads = [threading.Thread(target=expire), threading.Thread(target=flush)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()
        assert sum(item is slot for item in destroyed) == 1
    assert len(destroyed) == 10


def test_waiter_yield_timeout_releases_local_gate_without_erasing_waiter(tmp_path):
    db = str(tmp_path / "yield-timeout.duckdb")
    waiter = db_lock._register_write_waiter(db)
    started = time.monotonic()
    try:
        with pytest.raises(db_lock.WriteLockTimeout, match="yielding to prior waiters"):
            db_lock.connect_write(db, timeout_s=0.05, poll_interval_s=0.005)
        assert 0.05 <= time.monotonic() - started < 1
        assert not db_lock._PROCESS_WRITE_GATE.locked()
        assert db_lock.write_handoff_requested(db)
        assert not Path(db).exists()
    finally:
        db_lock._unregister_write_waiter(waiter)
    with db_lock.connect_write(db, timeout_s=1) as con:
        con.execute("SELECT 1")
