"""write_log must not block LockedConnection.close (Speak invite dogfood)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import duckdb

import runtime.db_lock as db_lock


def _db_with_write_log(tmp_path: Path) -> str:
    path = str(tmp_path / "wlog.duckdb")
    with duckdb.connect(path) as con:
        con.execute(
            "CREATE TABLE write_log ("
            "purpose VARCHAR, duration_s DOUBLE, success BOOLEAN, error VARCHAR)"
        )
        con.execute("CREATE TABLE facts (v INTEGER)")
    return path


def test_close_returns_quickly_while_log_flock_held(tmp_path: Path) -> None:
    """Caller close must not wait on contended write_log flock (fire-and-forget)."""
    path = _db_with_write_log(tmp_path)
    lock_path = db_lock._lock_path_for(path)
    hold = threading.Event()
    release = threading.Event()

    def hold_flock() -> None:
        fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            hold.set()
            release.wait(timeout=10)
        finally:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    t = threading.Thread(target=hold_flock, daemon=True)
    t.start()
    assert hold.wait(timeout=2)

    w = db_lock.connect_write(path, purpose="test:nonblock-close")
    w.execute("INSERT INTO facts VALUES (1)")
    t0 = time.monotonic()
    w.close()
    elapsed = time.monotonic() - t0
    release.set()
    t.join(timeout=2)
    # Close-path write_log wait capped at 250ms; under held flock must drop fast.
    assert elapsed < 0.75, f"close blocked for {elapsed:.3f}s"


def test_blocking_log_still_writes_row(tmp_path: Path) -> None:
    path = _db_with_write_log(tmp_path)
    db_lock._log_write_event(
        path,
        "test:blocking-log",
        0.01,
        True,
        None,
        max_wait_s=2.0,
        blocking=True,
    )
    with duckdb.connect(path) as con:
        n = con.execute(
            "SELECT count(*) FROM write_log WHERE purpose='test:blocking-log'"
        ).fetchone()[0]
    assert n == 1


def test_async_log_eventually_writes(tmp_path: Path) -> None:
    path = _db_with_write_log(tmp_path)
    w = db_lock.connect_write(path, purpose="test:async-log")
    w.execute("INSERT INTO facts VALUES (2)")
    w.close()
    deadline = time.monotonic() + 3.0
    n = 0
    while time.monotonic() < deadline:
        with duckdb.connect(path) as con:
            n = con.execute(
                "SELECT count(*) FROM write_log WHERE purpose='test:async-log'"
            ).fetchone()[0]
        if n >= 1:
            break
        time.sleep(0.05)
    assert n >= 1
