"""nygard SPR-07 M4 — DB-connection + lock steady-state under repeated fault.

Three fault shapes over the db_lock write path:

1. Injector lock release under repetition (N>=50, fast): locked_db holds a real
   flock inside the block and releases it every cycle — no orphaned lock
   accumulates, no fd leak.
2. Fault during the write window (N>=50): an exception inside a live
   connect_write must still close the connection AND release its flock
   (LockedConnection.__exit__ try/finally) — the SPR-05 release, stress-tested
   for accumulation.
3. connect_write timeout cleanup under contention (small N): a contended
   connect_write raises WriteLockTimeout and closes its own lock fd before
   raising — proven per-call so it needs only a few iterations.

Perf note (honest): db_lock logs a WriteLockTimeout event via a fresh
coordinator-respecting connection with a 5s grace; while our injector holds the
lock, that logging waits out its grace. That is a per-call cost of the *timeout*
path, so scenario 3 keeps a small N (fd cleanup is per-call, not
accumulation-dependent) and scenarios 1+2 carry the N>=50 no-leak proof cheaply.
"""

from __future__ import annotations

import pytest

from tests.resilience.resource_probe import open_db_connection_count, open_fd_count


def test_injector_lock_released_under_repetition_no_leak(tmp_path):
    from runtime.db_lock import is_locked
    from tools.faultinject import locked_db

    db = str(tmp_path / "t.duckdb")
    baseline_fds = open_fd_count()

    n = 50
    for _ in range(n):
        with locked_db(db):
            assert is_locked(db) is True
        assert is_locked(db) is False  # released every cycle — no orphaned lock

    assert open_fd_count() <= baseline_fds + 2


def test_fault_during_write_window_closes_connection_and_releases_lock(tmp_path):
    from runtime.db_lock import connect_write, is_locked

    db = str(tmp_path / "t.duckdb")
    connect_write(db, timeout_s=5, purpose="warmup").close()
    baseline_fds = open_fd_count()
    baseline_db = open_db_connection_count()

    class _WriteWindowFault(RuntimeError):
        pass

    n = 50
    for _ in range(n):
        with pytest.raises(_WriteWindowFault):
            with connect_write(db, timeout_s=5, purpose="write") as con:
                con.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
                raise _WriteWindowFault("fault mid-write")
        # The LockedConnection closed the DuckDB handle and released the flock on
        # the exception path (try/finally in __exit__/close).
        assert is_locked(db) is False

    assert open_fd_count() <= baseline_fds + 2
    if baseline_db >= 0:  # fd->path resolution available on this platform
        assert open_db_connection_count() <= baseline_db + 1


def test_connect_write_timeout_cleans_up_fd_under_contention(tmp_path):
    from runtime.db_lock import WriteLockTimeout, connect_write, is_locked
    from tools.faultinject import locked_db

    db = str(tmp_path / "t.duckdb")
    connect_write(db, timeout_s=5, purpose="warmup").close()
    baseline_fds = open_fd_count()

    # Small N: the fd-cleanup on the WriteLockTimeout path is a per-call
    # invariant (db_lock closes the lock fd before raising). See the module
    # perf note for why this loop stays small.
    for _ in range(5):
        with locked_db(db):
            with pytest.raises(WriteLockTimeout):
                connect_write(db, timeout_s=0.2, poll_interval_s=0.05, purpose="probe")
        assert is_locked(db) is False

    assert open_fd_count() <= baseline_fds + 2
