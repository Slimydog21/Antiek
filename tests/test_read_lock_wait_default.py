"""The read-wait default: a read that loses a short race must wait, not 503.

`runtime/db_lock.connect_read` always supported a bounded wait for another
process to release the file, but its default was `external_lock_timeout_s=0.0`
— fail at once. Only 3 of 202 production read sites passed a timeout, so the
other 199 turned an ordinary few-hundred-millisecond race into
503 + `Retry-After` for the client.

That is not a theoretical concern. CLAUDE.md invariant 1 pins uvicorn to a
single worker, so a conflict comes from a write in flight in this same
process, and the generate-then-view flow writes and then reads — its own read
is the thing that fails. Measured incident: 6,793 uncaught HTTP 500s in 24h on
the busiest read path before the typed-error fix, which turned them into
retryable 503s without ever letting a read wait.

The fix cannot simply raise the default, because a synchronous wait on the
event loop stalls every other request with one worker. So the default is now
resolved from the context the call actually runs in: on the loop, fail fast
exactly as before; off it (a threadpool worker, a script, a worker process), a
bounded `_DEFAULT_LOCK_WAIT_S`. An explicit float still wins, which is why the
pinned 503 contract in test_read_lock_conflict_http.py is untouched.

These tests pin both halves of that decision. Without the second one a future
change could "fix" contention by blocking the loop and no test would object.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time

import duckdb
import pytest

# A hold long enough to be unambiguous, short enough to stay inside the
# default wait with room to spare.
_HOLD_S = 0.6

_HOLDER_CODE = """
import sys
import time

import duckdb

con = duckdb.connect(sys.argv[1])  # plain RW open: holds the file lock
con.execute("CREATE TABLE IF NOT EXISTS probe AS SELECT 1 AS x")
print("held", flush=True)
time.sleep(float(sys.argv[2]))
con.close()
print("released", flush=True)
"""


def _make_db(tmpdir: str) -> str:
    path = os.path.join(tmpdir, "antiek.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS probe AS SELECT 1 AS x")
    con.close()
    return path


def _spawn_holder(path: str, hold_s: float):
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CODE, path, str(hold_s)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    line = proc.stdout.readline() if proc.stdout else ""
    assert "held" in line, f"holder did not take the file lock: {line!r}"
    return proc


def test_connect_read_waits_out_a_short_hold() -> None:
    """Off the event loop, the default waits for a short writer and succeeds.

    This is the regression test for the fail-fast default. With
    ANTIEK_READ_LOCK_WAIT_S=0 (the old behaviour) connect_read raises
    ReadLockTimeout instead, so this test detects the defect it documents.
    """
    from runtime.db_lock import ReadLockTimeout, connect_read

    with tempfile.TemporaryDirectory(prefix="antiek-read-wait-") as tmpdir:
        path = _make_db(tmpdir)
        proc = _spawn_holder(path, _HOLD_S)
        try:
            started = time.monotonic()
            with connect_read(path) as con:
                assert con.execute("SELECT 1").fetchone() == (1,)
            waited = time.monotonic() - started
        except ReadLockTimeout as exc:  # pragma: no cover - the old behaviour
            pytest.fail(
                "connect_read failed instantly instead of waiting for a "
                f"{_HOLD_S}s external hold ({exc}); the read-wait default has "
                "regressed to fail-fast, which answers 503 to a reader that "
                "only needed to wait a moment"
            )
        finally:
            proc.wait(timeout=30)

        assert waited >= _HOLD_S * 0.5, (
            f"connect_read returned in {waited:.3f}s while another process held "
            "the file, so it cannot have waited for the writer to finish"
        )


def test_connect_read_still_fails_fast_on_the_event_loop() -> None:
    """On the event loop the default must NOT wait: it would stall the server.

    One uvicorn worker (CLAUDE.md invariant 1) means a blocking wait here
    serialises every concurrent request behind a lock. `runtime/db_lock.py`
    states the constraint for routes that opt in; this pins it for the default
    path, so the availability fix cannot be bought with loop latency.
    """
    from runtime.db_lock import ReadLockTimeout, connect_read

    with tempfile.TemporaryDirectory(prefix="antiek-read-wait-loop-") as tmpdir:
        path = _make_db(tmpdir)
        proc = _spawn_holder(path, _HOLD_S * 4)

        async def read_on_the_loop() -> None:
            connect_read(path)

        try:
            started = time.monotonic()
            with pytest.raises(ReadLockTimeout):
                asyncio.run(read_on_the_loop())
            elapsed = time.monotonic() - started
        finally:
            proc.kill()
            proc.wait(timeout=30)

        assert elapsed < _HOLD_S, (
            f"connect_read blocked the event loop for {elapsed:.3f}s under an "
            "external hold; waiting must happen in the threadpool, never on "
            "the loop"
        )
