from __future__ import annotations

import time
from pathlib import Path
from typing import Never

import duckdb
import pytest

import runtime.db_lock as db_lock


def _database(tmp_path: Path) -> str:
    path = str(tmp_path / "fallback.duckdb")
    with duckdb.connect(path) as connection:
        connection.execute("CREATE TABLE facts (value INTEGER)")
        connection.execute("INSERT INTO facts VALUES (7)")
    return path


def test_connect_read_reads_while_same_process_holds_sanctioned_writer(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    with db_lock.connect_write(path, purpose="test:held-writer") as writer:
        writer.execute("INSERT INTO facts VALUES (11)")
        with db_lock.connect_read(path) as reader:
            assert reader.execute("SELECT value FROM facts ORDER BY value").fetchall() == [
                (7,),
                (11,),
            ]


def test_connect_read_fallback_rejects_mutation(tmp_path: Path) -> None:
    path = _database(tmp_path)
    with (
        db_lock.connect_write(path, purpose="test:held-writer"),
        db_lock.connect_read(path) as reader,
        pytest.raises(duckdb.InvalidInputException, match="rejects non-read SQL"),
    ):
        reader.execute("INSERT INTO facts VALUES (13)")


def test_connect_read_coexists_with_unregistered_rw(tmp_path: Path) -> None:
    """Unflocked same-process RW (reuse substrate) must not 500 readers."""
    path = _database(tmp_path)
    with duckdb.connect(path) as peer:
        peer.execute("INSERT INTO facts VALUES (99)")
        with db_lock.connect_read(path) as reader:
            values = [
                row[0]
                for row in reader.execute(
                    "SELECT value FROM facts ORDER BY value"
                ).fetchall()
            ]
            assert values == [7, 99]


def test_connect_read_lazy_rw_rejects_mutation_with_unregistered_peer(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    with (
        duckdb.connect(path),
        db_lock.connect_read(path) as reader,
        pytest.raises(duckdb.InvalidInputException, match="rejects non-read SQL"),
    ):
        reader.execute("INSERT INTO facts VALUES (13)")


def test_writer_close_still_allows_coexist_read_with_peer_rw(tmp_path: Path) -> None:
    path = _database(tmp_path)
    writer = db_lock.connect_write(path, purpose="test:closed-writer")
    writer.close()

    with duckdb.connect(path), db_lock.connect_read(path) as reader:
        assert reader.execute("SELECT COUNT(*) FROM facts").fetchone() == (1,)


def test_coordinator_writer_also_authorizes_same_process_read(tmp_path: Path) -> None:
    path = _database(tmp_path)
    coordinator = db_lock.FlockWriteCoordinator(
        path,
        lock_path=str(tmp_path / "override.lock"),
    )
    with (
        coordinator.acquire_write_context("test:coordinator"),
        db_lock.connect_read(path) as reader,
    ):
        assert reader.execute("SELECT COUNT(*) FROM facts").fetchone() == (1,)


def test_connect_read_does_not_retry_unrelated_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def fail(_path: str, *, read_only: bool = False) -> Never:
        calls.append(read_only)
        raise duckdb.ConnectionException("unrelated failure")

    monkeypatch.setattr(duckdb, "connect", fail)
    with pytest.raises(duckdb.ConnectionException, match="unrelated failure"):
        db_lock.connect_read("missing.duckdb")
    assert calls == [True]


def test_connect_read_external_writer_retry_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def locked(_path: str, *, read_only: bool = False) -> Never:
        calls.append(read_only)
        raise duckdb.IOException(
            "Could not set lock on file: Conflicting lock is held in another process"
        )

    monkeypatch.setattr(duckdb, "connect", locked)
    with pytest.raises(duckdb.IOException, match="Conflicting lock"):
        db_lock.connect_read("held.duckdb")
    assert calls == [True]


def test_connect_read_external_writer_retry_expires_with_typed_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    clock = 0.0

    def locked(_path: str, *, read_only: bool = False) -> Never:
        nonlocal calls
        calls += 1
        raise duckdb.IOException(
            "Could not set lock on file: Conflicting lock is held in another process"
        )

    def monotonic() -> float:
        return clock

    def sleep(delay: float) -> None:
        nonlocal clock
        clock += delay

    monkeypatch.setattr(duckdb, "connect", locked)
    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(time, "sleep", sleep)
    with pytest.raises(db_lock.ReadLockTimeout):
        db_lock.connect_read("held.duckdb", external_lock_timeout_s=0.12)
    assert calls > 1
    assert clock == pytest.approx(0.12)


def test_connect_read_retries_mode_transition_from_rw_to_ro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real RW->RO handoff can straddle the RO attempt and RW fallback."""
    path = _database(tmp_path)
    connect = duckdb.connect
    writer = connect(path)
    reader_holder: duckdb.DuckDBPyConnection | None = None
    calls: list[bool] = []

    def transition(
        _path: str, *, read_only: bool = False
    ) -> duckdb.DuckDBPyConnection:
        nonlocal reader_holder
        calls.append(read_only)
        if len(calls) == 1:
            try:
                return connect(path, read_only=True)
            except duckdb.ConnectionException:
                writer.close()
                reader_holder = connect(path, read_only=True)
                raise
        if len(calls) == 2:
            try:
                return connect(path, read_only=False)
            finally:
                assert reader_holder is not None
                reader_holder.close()
        return connect(path, read_only=read_only)

    monkeypatch.setattr(duckdb, "connect", transition)
    try:
        with db_lock.connect_read(path) as reader:
            assert reader.execute("SELECT COUNT(*) FROM facts").fetchone() == (1,)
    finally:
        writer.close()
        if reader_holder is not None:
            reader_holder.close()

    assert calls == [True, False, True]


def test_connect_read_retries_binder_conflict_on_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two overlapping mode transitions can reject both initial open modes."""
    path = _database(tmp_path)
    connect = duckdb.connect
    calls: list[bool] = []

    def transition(_path: str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        calls.append(read_only)
        if len(calls) <= 2:
            raise duckdb.BinderException(
                'Unique file handle conflict: Cannot attach "fallback" - already attached'
            )
        return connect(_path, read_only=read_only)

    monkeypatch.setattr(duckdb, "connect", transition)
    with db_lock.connect_read(path) as reader:
        assert reader.execute("SELECT value FROM facts").fetchall() == [(7,)]
    assert calls == [True, False, True]


def test_external_writer_wait_does_not_consume_local_mode_retry_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A later local mode handoff gets its own window after an external writer."""
    path = _database(tmp_path)
    connect = duckdb.connect
    calls: list[bool] = []
    clock = 0.0

    def monotonic() -> float:
        return clock

    def sleep(delay: float) -> None:
        nonlocal clock
        clock += delay

    def transition(_path: str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        calls.append(read_only)
        index = len(calls)
        if index in (1, 2, 11, 12):
            raise duckdb.ConnectionException(db_lock._SAME_FILE_DIFFERENT_CONFIG)
        if 3 <= index <= 10:
            assert read_only
            raise duckdb.IOException(
                "Could not set lock on file: Conflicting lock is held in another process"
            )
        return connect(_path, read_only=read_only)

    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(duckdb, "connect", transition)
    with db_lock.connect_read(path, external_lock_timeout_s=1.0) as reader:
        assert reader.execute("SELECT value FROM facts").fetchall() == [(7,)]
    assert calls == [True, False] + [True] * 8 + [True, False, True]
    assert clock > db_lock._READ_MODE_RETRY_WINDOW_S


def test_connect_read_does_not_retry_unrelated_fallback_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _database(tmp_path)
    connect = duckdb.connect
    writer = connect(path)
    calls: list[bool] = []

    def fail_fallback(
        _path: str, *, read_only: bool = False
    ) -> duckdb.DuckDBPyConnection:
        calls.append(read_only)
        if read_only:
            try:
                return connect(path, read_only=True)
            except duckdb.ConnectionException:
                writer.close()
                raise
        raise duckdb.IOException("unrelated fallback failure")

    monkeypatch.setattr(duckdb, "connect", fail_fallback)
    try:
        with pytest.raises(duckdb.IOException, match="unrelated fallback failure"):
            db_lock.connect_read(path)
    finally:
        writer.close()

    assert calls == [True, False]


def test_connect_read_stops_retrying_persistent_mode_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []
    conflicts: list[duckdb.ConnectionException] = []
    slept: list[float] = []
    clock = 0.0

    def monotonic() -> float:
        return clock

    def sleep(delay: float) -> None:
        nonlocal clock
        slept.append(delay)
        clock += delay

    def conflict(_path: str, *, read_only: bool = False) -> Never:
        calls.append(read_only)
        error = duckdb.ConnectionException(
            f"Connection Error: {db_lock._SAME_FILE_DIFFERENT_CONFIG}"
        )
        conflicts.append(error)
        raise error

    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(duckdb, "connect", conflict)

    with pytest.raises(duckdb.ConnectionException) as raised:
        db_lock.connect_read("persistent-conflict.duckdb")

    assert raised.value is conflicts[-1]
    assert db_lock._SAME_FILE_DIFFERENT_CONFIG in str(raised.value)
    assert len(calls) > 2
    assert len(calls) <= 54
    assert calls == [mode for _ in range(len(calls) // 2) for mode in (True, False)]
    assert sum(slept) == pytest.approx(db_lock._READ_MODE_RETRY_WINDOW_S)
    assert clock == pytest.approx(db_lock._READ_MODE_RETRY_WINDOW_S)


def test_connect_write_waits_for_brief_ro_to_clear(tmp_path: Path) -> None:
    """RO holders briefly block DuckDB RW open; connect_write must retry."""
    import threading
    import time

    path = _database(tmp_path)
    release = threading.Event()
    opened = threading.Event()
    errors: list[BaseException] = []

    def hold_ro() -> None:
        con = duckdb.connect(path, read_only=True)
        opened.set()
        release.wait(5)
        con.close()

    def do_write() -> None:
        opened.wait(5)
        try:
            with db_lock.connect_write(
                path, purpose="test:after-ro", timeout_s=2.0, poll_interval_s=0.05
            ) as writer:
                writer.execute("INSERT INTO facts VALUES (42)")
        except BaseException as exc:  # noqa: BLE001 — capture for main thread
            errors.append(exc)

    t_ro = threading.Thread(target=hold_ro)
    t_w = threading.Thread(target=do_write)
    t_ro.start()
    t_w.start()
    time.sleep(0.15)
    release.set()
    t_ro.join(timeout=5)
    t_w.join(timeout=5)
    assert errors == []
    with db_lock.connect_read(path) as reader:
        assert 42 in [r[0] for r in reader.execute("SELECT value FROM facts").fetchall()]
