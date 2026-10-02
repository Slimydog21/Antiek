"""In-process write gate: second connect_write fails fast while first holds."""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

from runtime.db_lock import WriteLockTimeout, connect_write


def test_second_writer_times_out_while_first_holds_in_process():
    tmp = tempfile.mkdtemp(prefix="antiek-pwg-")
    db = os.path.join(tmp, "t.duckdb")
    release = threading.Event()
    held = threading.Event()

    def holder():
        with connect_write(db, purpose="test:hold", timeout_s=5) as con:
            con.execute("SELECT 1")
            held.set()
            release.wait(timeout=20)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert held.wait(timeout=5)
    t0 = time.monotonic()
    with pytest.raises(WriteLockTimeout), connect_write(db, purpose="test:second", timeout_s=1.0):
        pass
    elapsed = time.monotonic() - t0
    release.set()
    t.join(timeout=5)
    assert elapsed < 2.5, f"second writer took {elapsed:.3f}s"


def test_gate_waiter_wakes_when_the_gate_is_released():
    """A writer waiting on the in-process gate must get it as soon as the
    holder lets go, not on its next poll tick.

    The gate is held directly (no flock, no DuckDB handle) so the only thing
    the waiter can be waiting for is the gate. poll_interval_s=2.0 makes a
    sleep-polling gate deterministic: the first retry would land ~1.8 s after
    the release. A blocking acquire wakes within milliseconds.
    """
    from runtime import db_lock

    tmp = tempfile.mkdtemp(prefix="antiek-pwg-wake-")
    db = os.path.join(tmp, "t.duckdb")
    assert db_lock._PROCESS_WRITE_GATE.acquire(timeout=5)
    released_at: dict[str, float] = {}

    def release_later() -> None:
        time.sleep(0.2)
        released_at["t"] = time.monotonic()
        db_lock._PROCESS_WRITE_GATE.release()

    releaser = threading.Thread(target=release_later, daemon=True)
    releaser.start()
    with connect_write(db, purpose="test:gate-wake", timeout_s=5, poll_interval_s=2.0) as con:
        acquired_at = time.monotonic()
        con.execute("SELECT 1")
    releaser.join(timeout=5)
    lag = acquired_at - released_at["t"]
    assert lag < 0.5, f"waiter got the gate {lag:.3f}s after it was released"
