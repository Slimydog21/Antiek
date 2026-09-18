from __future__ import annotations

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

    monkeypatch.setattr("runtime.db_lock.duckdb.connect", fail)
    with pytest.raises(duckdb.ConnectionException, match="unrelated failure"):
        db_lock.connect_read("missing.duckdb")
    assert calls == [True]


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
