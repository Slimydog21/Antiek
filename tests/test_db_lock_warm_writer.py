"""In-process warm writer keepalive — skip DuckDB re-open between writes.

Cite: runtime/db_lock.py WP-3; #3121 coexist; #3164/#3165 fill contention.
"""

from __future__ import annotations

import os
import threading
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


def test_parked_slot_releases_flock_on_expiry_without_another_writer(
    tmp_path: Path, monkeypatch
):
    """The documented 20s bound must hold on an IDLE process.

    Before the expiry timer, a parked writer released its flock only when the
    NEXT in-process write called _take_warm_slot. With no next write the
    cross-process flock was held forever: prod's nightly backup timed out
    after 180s three nights running and /export/my-graph answered 503.
    """
    import fcntl

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0.2")
    db = str(tmp_path / "idle.duckdb")
    with db_lock.connect_write(db, purpose="idle:1", timeout_s=5) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    lock_path = db + ".write.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        # Immediately after close the slot is parked and the flock is HELD.
        with pytest.raises(OSError):
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # ... and with NO further connect_write, it must free itself.
        deadline = time.monotonic() + 2.0
        acquired = False
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                time.sleep(0.02)
        assert acquired, "parked warm writer never released the flock on expiry"
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    assert db_lock.flush_warm_writers(db) == 0


# ---------------------------------------------------------------------------
# Expiry close in flight (2026-09-24): the timer pops the slot under the
# registry lock and closes the DuckDB handle OUTSIDE it, so for those
# milliseconds "nothing parked" is true while the file is still held open.
# Both in-process re-openers must wait for that close, or DuckDB answers
# "Unique file handle conflict" (seen by merge_staging's ATTACH).
# ---------------------------------------------------------------------------


class _BlockingCon:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def close(self) -> None:
        self.started.set()
        assert self.release.wait(5.0), "test never released the close"
        self.closed = True


def _park_expired_fake(tmp_path: Path) -> tuple[str, db_lock._WarmWriterSlot, _BlockingCon]:
    db = str(tmp_path / "race.duckdb")
    lock_path = db + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    con = _BlockingCon()
    slot = db_lock._WarmWriterSlot(
        con=con,
        lock_fd=fd,
        lock_path=lock_path,
        db_path=db,
        expires_mono=time.monotonic() - 1.0,
        last_purpose="test",
    )
    key = db_lock._warm_key(db)
    with db_lock._warm_slots_lock:
        db_lock._warm_slots[key] = slot
    return db, slot, con


def _run_in_thread(fn, *args):
    out: dict = {}

    def target() -> None:
        try:
            out["result"] = fn(*args)
        except BaseException as exc:  # pragma: no cover - surfaced by the assert
            out["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, out


def test_flush_waits_for_an_expiry_close_in_flight(tmp_path: Path):
    db, slot, con = _park_expired_fake(tmp_path)
    key = db_lock._warm_key(db)
    try:
        expiry, _ = _run_in_thread(db_lock._expire_warm_slot, key, slot)
        assert con.started.wait(5.0)
        # The registry already says "nothing parked" while close() is stuck.
        with db_lock._warm_slots_lock:
            assert key not in db_lock._warm_slots
            assert key in db_lock._warm_closing

        flusher, out = _run_in_thread(db_lock.flush_warm_writers, db)
        flusher.join(0.3)
        assert flusher.is_alive(), "flush returned while the expiry close was still in flight"

        con.release.set()
        flusher.join(5.0)
        expiry.join(5.0)
        assert not flusher.is_alive()
        assert "error" not in out
        assert out["result"] == 0  # the timer's close is not ours to count
        assert con.closed
        with db_lock._warm_slots_lock:
            assert key not in db_lock._warm_closing
    finally:
        con.release.set()
        db_lock.flush_warm_writers(db)


def test_take_warm_slot_waits_for_an_expiry_close_in_flight(tmp_path: Path):
    db, slot, con = _park_expired_fake(tmp_path)
    key = db_lock._warm_key(db)
    try:
        expiry, _ = _run_in_thread(db_lock._expire_warm_slot, key, slot)
        assert con.started.wait(5.0)

        taker, out = _run_in_thread(db_lock._take_warm_slot, db)
        taker.join(0.3)
        assert taker.is_alive(), "a new writer would have reopened the file mid-close"

        con.release.set()
        taker.join(5.0)
        expiry.join(5.0)
        assert not taker.is_alive()
        assert "error" not in out
        assert out["result"] is None
        assert con.closed
    finally:
        con.release.set()
        db_lock.flush_warm_writers(db)


def test_flush_raises_when_the_expiry_close_outlasts_the_bound(tmp_path: Path):
    """A close that is still running when the bound lapses is NOT silently
    ignored: the file is still held open, so the caller must not proceed."""
    db, slot, con = _park_expired_fake(tmp_path)
    key = db_lock._warm_key(db)
    try:
        expiry, _ = _run_in_thread(db_lock._expire_warm_slot, key, slot)
        assert con.started.wait(5.0)
        with pytest.raises(db_lock.WarmWriterCloseTimeout, match="still closing"):
            db_lock.flush_warm_writers(db, close_wait_s=0.2)
        assert isinstance(db_lock.WarmWriterCloseTimeout("x"), db_lock.WriteLockTimeout)
        con.release.set()
        expiry.join(5.0)
        assert con.closed
    finally:
        con.release.set()
        db_lock.flush_warm_writers(db)


def test_take_warm_slot_raises_within_the_caller_deadline(tmp_path: Path):
    db, slot, con = _park_expired_fake(tmp_path)
    key = db_lock._warm_key(db)
    try:
        expiry, _ = _run_in_thread(db_lock._expire_warm_slot, key, slot)
        assert con.started.wait(5.0)
        t0 = time.monotonic()
        with pytest.raises(db_lock.WarmWriterCloseTimeout):
            db_lock._take_warm_slot(db, close_wait_s=0.2)
        assert time.monotonic() - t0 < 2.0
        con.release.set()
        expiry.join(5.0)
    finally:
        con.release.set()
        db_lock.flush_warm_writers(db)


def test_connect_write_before_open_runs_under_the_gate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0")
    db = str(tmp_path / "hook.duckdb")
    seen: list[tuple[bool, int]] = []

    def hook() -> None:
        seen.append((db_lock._PROCESS_WRITE_GATE.locked(), len(db_lock._active_writers)))

    with db_lock.connect_write(db, purpose="hook-test", before_open=hook) as con:
        con.execute("SELECT 1")
    assert seen == [(True, 0)]  # gate held, nothing opened yet
    assert not db_lock._PROCESS_WRITE_GATE.locked()


def test_connect_write_before_open_failure_releases_the_gate(tmp_path: Path):
    db = str(tmp_path / "hook-fail.duckdb")

    def hook() -> None:
        raise db_lock.WarmWriterCloseTimeout("simulated: staging still closing")

    with pytest.raises(db_lock.WarmWriterCloseTimeout):
        db_lock.connect_write(db, purpose="hook-fail", before_open=hook)
    assert not db_lock._PROCESS_WRITE_GATE.locked()
    assert not os.path.exists(db)  # nothing was opened or created


def test_connect_write_retrying_forwards_before_open(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "0")
    db = str(tmp_path / "retrying-hook.duckdb")
    seen: list[bool] = []
    with db_lock.connect_write_retrying(
        db, purpose="retrying-hook", max_retries=0,
        before_open=lambda: seen.append(db_lock._PROCESS_WRITE_GATE.locked()),
    ) as con:
        con.execute("SELECT 1")
    assert seen == [True]


def test_has_parked_writer(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    db = str(tmp_path / "parked.duckdb")
    assert not db_lock.has_parked_writer(db)
    with db_lock.connect_write(db, purpose="park"):
        assert not db_lock.has_parked_writer(db)  # active, not parked
    assert db_lock.has_parked_writer(db)
    assert db_lock.flush_warm_writers(db) == 1
    assert not db_lock.has_parked_writer(db)
