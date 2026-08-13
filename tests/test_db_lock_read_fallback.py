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


def test_connect_read_does_not_mask_unregistered_config_conflict(tmp_path: Path) -> None:
    path = _database(tmp_path)
    with (
        duckdb.connect(path),
        pytest.raises(duckdb.ConnectionException, match="different configuration"),
    ):
        db_lock.connect_read(path)


def test_writer_close_removes_fallback_authority(tmp_path: Path) -> None:
    path = _database(tmp_path)
    writer = db_lock.connect_write(path, purpose="test:closed-writer")
    writer.close()

    with (
        duckdb.connect(path),
        pytest.raises(duckdb.ConnectionException, match="different configuration"),
    ):
        db_lock.connect_read(path)


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
