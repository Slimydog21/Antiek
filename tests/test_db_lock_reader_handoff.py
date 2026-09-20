"""Residual RW readers must get a bounded handoff after warm-owner expiry."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import pytest

from runtime import db_lock

REPO = Path(__file__).resolve().parents[1]


def _wait_for(predicate, *, timeout_s=10):
    deadline = time.monotonic() + timeout_s
    while not predicate():
        assert time.monotonic() < deadline, "handoff condition did not arrive"
        time.sleep(0.01)


@pytest.fixture
def residual_reader(tmp_path, monkeypatch):
    db = str(tmp_path / "reader.duckdb")
    monkeypatch.setattr(db_lock, "_write_keepalive_s", lambda: 0.2)
    with db_lock.connect_write(db, purpose="reader-fixture") as writer:
        writer.execute("CREATE TABLE payload (value INTEGER)")
        writer.execute("INSERT INTO payload VALUES (42)")
    reader = db_lock.connect_read(db)
    assert isinstance(reader, db_lock._ReadOrientedConnection)
    # The real timer closes the parked writer; the fallback reader retains
    # DuckDB's native RW file lock after the sidecar flock has been released.
    _wait_for(lambda: not db_lock._has_local_writer(db))
    try:
        yield db, reader
    finally:
        reader.close()
        db_lock.flush_warm_writers(db)


_CHILD = r'''
import fcntl
import json
import sys
import time
from pathlib import Path
import duckdb
from runtime import db_lock

db, kind, signal, timeout = sys.argv[1:]
real_connect = duckdb.connect
attempts = 0

def observed_connect(*args, **kwargs):
    global attempts
    attempts += 1
    try:
        return real_connect(*args, **kwargs)
    except duckdb.IOException as exc:
        Path(signal).write_text(str(exc))
        raise

duckdb.connect = observed_connect
started = time.monotonic()
try:
    factory = db_lock.connect_write if kind == "writer" else db_lock.snapshot_read
    with factory(db, timeout_s=float(timeout), poll_interval_s=0.02, purpose="reader-handoff") as con:
        value = con.execute("SELECT value FROM payload").fetchone()[0]
    print(json.dumps({"value": value, "attempts": attempts, "elapsed": time.monotonic()-started}), flush=True)
except Exception as exc:
    gate_free = db_lock._PROCESS_WRITE_GATE.acquire(blocking=False)
    if gate_free:
        db_lock._PROCESS_WRITE_GATE.release()
    with open(db + ".write.lock", "a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            flock_free = True
        except BlockingIOError:
            flock_free = False
    print(json.dumps({"error": type(exc).__name__, "attempts": attempts,
                      "elapsed": time.monotonic()-started,
                      "gate_free": gate_free, "flock_free": flock_free}), flush=True)
'''


def _contender(db, kind, signal, timeout_s):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["ANTIEK_WRITE_KEEPALIVE_S"] = "0"
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD, db, kind, str(signal), str(timeout_s)],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _assert_coordination_released(db):
    with open(db + ".write.lock", "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    waiters = Path(db + ".write.waiters")
    assert not waiters.exists() or not list(waiters.iterdir())


@pytest.mark.parametrize("kind", ["writer", "snapshot"])
def test_external_open_waits_for_residual_reader_to_close(residual_reader, tmp_path, kind):
    db, reader = residual_reader
    signal = tmp_path / "native-lock-observed"
    child = _contender(db, kind, signal, 3)
    try:
        _wait_for(signal.exists)
        assert "Could not set lock on file" in signal.read_text()
        assert "Conflicting lock is held" in signal.read_text()
        # The child has encountered real DuckDB contention, not merely waited
        # for the sidecar. Release only after that evidence exists.
        reader.close()
        stdout, stderr = child.communicate(timeout=10)
        result = json.loads(stdout)
        assert result.get("value") == 42, (result, stderr)
        assert result["attempts"] >= 2
        _assert_coordination_released(db)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()


@pytest.mark.parametrize("kind", ["writer", "snapshot"])
def test_residual_reader_timeout_releases_coordination(residual_reader, tmp_path, kind):
    db, reader = residual_reader
    signal = tmp_path / "native-lock-observed"
    child = _contender(db, kind, signal, 0.2)
    try:
        stdout, stderr = child.communicate(timeout=10)
        result = json.loads(stdout)
        assert signal.exists(), stderr
        assert result.get("error") == "IOException", result
        assert result["attempts"] > 1, result
        assert 0.18 <= result["elapsed"] < 2, result
        assert result["gate_free"] is True, result
        assert result["flock_free"] is True, result
        _assert_coordination_released(db)
        reader.close()
        with db_lock.snapshot_read(db, timeout_s=1) as con:
            assert con.execute("SELECT value FROM payload").fetchone() == (42,)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()


@pytest.mark.parametrize("kind", ["writer", "snapshot"])
@pytest.mark.parametrize("message", [
    "IO Error: Permission denied opening database",
    "IO Error: Could not set lock on file scratch: Operation not supported",
])
def test_unrelated_io_failure_is_not_retried(tmp_path, monkeypatch, kind, message):
    db = str(tmp_path / "bad.duckdb")
    calls = []

    def broken_connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise duckdb.IOException(message)

    monkeypatch.setattr(db_lock.duckdb, "connect", broken_connect)
    factory = db_lock.connect_write if kind == "writer" else db_lock.snapshot_read
    started = time.monotonic()
    with (
        pytest.raises(duckdb.IOException, match=message),
        factory(db, timeout_s=1, poll_interval_s=0.02),
    ):
        pytest.fail("a failing open must never yield a connection")
    assert len(calls) == 1
    assert time.monotonic() - started < 0.5
    _assert_coordination_released(db)
    assert db_lock._PROCESS_WRITE_GATE.acquire(blocking=False)
    db_lock._PROCESS_WRITE_GATE.release()
