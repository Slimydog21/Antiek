"""write_log must not block LockedConnection.close (Speak invite dogfood)."""

from __future__ import annotations

import subprocess
import sys
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


# The flock holder MUST be a subprocess, not a thread: same-process flock
# acquisitions do not contend (runtime/db_lock.py documents that two open()s
# of the sidecar in one process can both LOCK_EX, which is why
# _PROCESS_WRITE_GATE exists; BSD flock is process-scoped). The previous
# version of this test held the flock from a thread, so the "held flock"
# scenario was never actually exercised and the assertion reduced to an
# absolute wall-clock budget on an uncontended close() — a measurement of
# the runner, not of the code. It failed CI run 36951309552 with
# "close blocked for 0.812s" (assert 0.812 < 0.75) on a backend-only PR whose
# runtime/db_lock.py was byte-identical to main.
_FLOCK_HOLDER_SRC = """
import os, sys, fcntl, time
fd = os.open(sys.argv[1], os.O_CREAT | os.O_WRONLY, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("ACQUIRED", flush=True)
time.sleep(float(sys.argv[2]))
fcntl.flock(fd, fcntl.LOCK_UN)
os.close(fd)
"""


def _start_flock_holder(lock_path: str, hold_s: float) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", _FLOCK_HOLDER_SRC, lock_path, str(hold_s)],
        stdout=subprocess.PIPE,
        text=True,
    )


def _timed_blocking_log_wait(path: str, wait_s: float) -> float:
    """A control that genuinely waits on the held flock in this run.

    _log_write_event_sync only returns from its poll loop after the deadline
    has passed, so the measured elapsed is always >= wait_s — including under
    load, which inflates it further. This is the in-run yardstick for what
    "blocked on the lock" costs on this machine right now.
    """
    t0 = time.monotonic()
    db_lock._log_write_event(
        path, "test:blocking-control", 0.0, True, None,
        max_wait_s=wait_s, blocking=True,
    )
    return time.monotonic() - t0


_CONTROL_WAIT_S = 3.0


def test_close_returns_quickly_while_log_flock_held(tmp_path: Path) -> None:
    """close() must not wait on a contended write_log flock.

    Two load-invariant assertions, no absolute wall-clock budget:

    1. Structural: when close() returns, the flock is STILL owned by the
       subprocess (``is_locked``). close() therefore provably returned
       without waiting for the holder. If close() ever bounds itself on the
       lock again it returns only after the holder's safety timeout, the
       probe reads False, and the test fails.
    2. Relative: a control that genuinely waits on this same held flock in
       this same run costs >= 3s by construction; close() must cost less
       than half of that. Uniform machine slowness (the CI flake mode)
       inflates both sides and cannot break the ratio; the regression this
       test guards (close waiting seconds on the lock) breaks it by an
       order of magnitude.
    """
    path = _db_with_write_log(tmp_path)
    lock_path = db_lock._lock_path_for(path)

    w = db_lock.connect_write(path, purpose="test:nonblock-close")
    w.execute("INSERT INTO facts VALUES (1)")
    # Queued behind the writer's flock; granted the moment close() releases it.
    # 30s is only a safety net so a blocking close() regression fails the
    # is_locked probe below instead of hanging the test forever.
    holder = _start_flock_holder(lock_path, hold_s=30.0)
    try:
        t0 = time.monotonic()
        w.close()
        elapsed_close = time.monotonic() - t0

        # Structural: the subprocess owns the flock, so close() did not wait
        # for it. The kernel grants the queued holder only when it is
        # scheduled, so probe with a short wait-for-condition window: in the
        # passing case the holder owns the flock within a scheduling quantum
        # of close() releasing it; in the regression case close() returned
        # only because the holder's safety timeout RELEASED the flock, and
        # the probe reads False for the whole window no matter how long it is.
        deadline = time.monotonic() + 5.0
        while not db_lock.is_locked(path):
            assert time.monotonic() < deadline, (
                "the flock was free after close() returned — close() waited "
                "for the holder instead of dropping the write_log entry"
            )
            time.sleep(0.01)

        control_elapsed = _timed_blocking_log_wait(path, _CONTROL_WAIT_S)
        # Sanity: the control really waited on the flock (guards environments
        # where cross-process flock does not contend; fail loudly there
        # rather than silently green).
        assert control_elapsed >= _CONTROL_WAIT_S - 0.5, (
            f"blocking control returned after {control_elapsed:.3f}s; "
            "cross-process flock is not contending in this environment"
        )
        assert elapsed_close < control_elapsed / 2, (
            f"close() took {elapsed_close:.3f}s, more than half of a genuine "
            f"{control_elapsed:.3f}s lock wait in the same run"
        )
    finally:
        holder.kill()
        holder.wait()


def test_close_log_write_drops_at_cap_when_flock_held(tmp_path: Path) -> None:
    """The close-path log write drops at its 250ms cap, deterministically.

    The holder ALREADY owns the flock before the call (no acquire race), so
    this exercises the contended branch of _log_write_event on every run.
    blocking=False must cap the wait at 250ms even when max_wait_s=5.0 — that
    cap is the whole reason close() cannot park on a busy writer. The bound
    is relative to a blocking control measured in the same run, and the
    dropped row is asserted structurally.
    """
    path = _db_with_write_log(tmp_path)
    lock_path = db_lock._lock_path_for(path)

    holder = _start_flock_holder(lock_path, hold_s=10.0)
    try:
        assert holder.stdout is not None
        assert "ACQUIRED" in holder.stdout.readline()

        t0 = time.monotonic()
        db_lock._log_write_event(
            path, "test:nonblock-cap", 0.01, True, None,
            max_wait_s=5.0, blocking=False,  # close-path semantics
        )
        elapsed_capped = time.monotonic() - t0

        control_elapsed = _timed_blocking_log_wait(path, _CONTROL_WAIT_S)
        assert control_elapsed >= _CONTROL_WAIT_S - 0.5, (
            f"blocking control returned after {control_elapsed:.3f}s; "
            "cross-process flock is not contending in this environment"
        )
        assert elapsed_capped < control_elapsed / 2, (
            f"capped log write took {elapsed_capped:.3f}s, more than half of "
            f"a genuine {control_elapsed:.3f}s lock wait in the same run"
        )
        with duckdb.connect(path) as con:
            n = con.execute(
                "SELECT count(*) FROM write_log WHERE purpose='test:nonblock-cap'"
            ).fetchone()[0]
        assert n == 0, "contended close-path log write must be dropped, not waited out"
    finally:
        holder.kill()
        holder.wait()


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
