"""A short external read must not make a sidecar-owning writer fail open."""

from __future__ import annotations

import fcntl
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import pytest

from runtime import db_lock
from runtime.db_lock import WriteLockTimeout, connect_write

_READER_SCRIPT = (
    "import duckdb, sys, time; "
    "con = duckdb.connect(sys.argv[1], read_only=True); "
    "print('ready', flush=True); "
    "time.sleep(float(sys.argv[2])); con.close()"
)


def _start_reader(db_path: str, hold_s: float) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [sys.executable, "-c", _READER_SCRIPT, db_path, str(hold_s)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    ready_line = b""
    deadline = time.monotonic() + 5
    while b"\n" not in ready_line:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        readable, _, _ = select.select([proc.stdout.fileno()], [], [], remaining)
        if not readable:
            break
        chunk = os.read(proc.stdout.fileno(), 64)
        if not chunk:
            break
        ready_line += chunk
    if ready_line.strip() != b"ready":
        if proc.poll() is None:
            proc.kill()
        _, stderr = proc.communicate(timeout=5)
        pytest.fail(f"reader did not become ready: {stderr}")
    return proc


def _stop_reader(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
    _, stderr = proc.communicate(timeout=5)
    assert proc.returncode in (0, -15), stderr


def test_writer_retries_until_external_reader_closes(tmp_path: Path) -> None:
    db = str(tmp_path / "reader.duckdb")
    with connect_write(db, purpose="setup", keepalive_s=0) as con:
        con.execute("CREATE TABLE proof (value INTEGER)")

    reader = _start_reader(db, 0.4)
    try:
        with connect_write(
            db, purpose="after-reader", timeout_s=3, poll_interval_s=0.02,
            keepalive_s=0,
        ) as con:
            con.execute("INSERT INTO proof VALUES (1)")
            assert con.execute("SELECT count(*) FROM proof").fetchone() == (1,)
    finally:
        _stop_reader(reader)


def test_reader_conflict_times_out_and_releases_sidecar(tmp_path: Path) -> None:
    db = str(tmp_path / "reader-timeout.duckdb")
    with connect_write(db, purpose="setup", keepalive_s=0) as con:
        con.execute("CREATE TABLE proof (value INTEGER)")

    reader = _start_reader(db, 3)
    try:
        started = time.monotonic()
        with pytest.raises(WriteLockTimeout, match="DuckDB file lock"):
            connect_write(
                db, purpose="blocked-reader", timeout_s=0.2,
                poll_interval_s=0.02, keepalive_s=0,
            )
        assert time.monotonic() - started < 1.5

        fd = os.open(db + ".write.lock", os.O_WRONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    finally:
        _stop_reader(reader)

    with connect_write(db, purpose="after-timeout", timeout_s=3, keepalive_s=0):
        pass


def test_unrelated_duckdb_open_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "unrelated-error.duckdb")
    with connect_write(db, purpose="setup", keepalive_s=0):
        pass

    opens = 0

    def fail_open(_db_path: str) -> duckdb.DuckDBPyConnection:
        nonlocal opens
        opens += 1
        raise duckdb.IOException("IO Error: unrelated storage failure")

    monkeypatch.setattr(db_lock.duckdb, "connect", fail_open)
    with pytest.raises(duckdb.IOException, match="unrelated storage failure"):
        connect_write(
            db, purpose="unrelated-error", timeout_s=2, poll_interval_s=0.02,
            keepalive_s=0,
        )
    assert opens == 1

    fd = os.open(db + ".write.lock", os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
