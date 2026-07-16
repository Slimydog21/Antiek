from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

import runtime.db_lock as db_lock


def test_contending_writer_publishes_and_consumes_handoff_signal(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    outcome: list[str] = []

    with db_lock.connect_write(db_path, purpose="holder") as holder:
        holder.execute("CREATE TABLE proof (value INTEGER)")

        def contend() -> None:
            with db_lock.connect_write(
                db_path,
                purpose="waiter",
                timeout_s=2,
                poll_interval_s=0.01,
            ):
                outcome.append("acquired")

        waiter = threading.Thread(target=contend)
        waiter.start()
        deadline = time.monotonic() + 1
        while not db_lock.write_handoff_requested(db_path):
            assert time.monotonic() < deadline
            time.sleep(0.01)

    waiter.join(2)
    assert outcome == ["acquired"]
    assert not db_lock.write_handoff_requested(db_path)


def test_handoff_tokens_are_independent_and_abandoned_tokens_are_pruned(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    first = db_lock._register_write_waiter(db_path)
    second = db_lock._register_write_waiter(db_path)
    assert db_lock.write_handoff_requested(db_path)

    db_lock._unregister_write_waiter(first)
    assert db_lock.write_handoff_requested(db_path)
    db_lock._unregister_write_waiter(second)
    assert not db_lock.write_handoff_requested(db_path)

    waiter_dir = Path(f"{db_path}.write.waiters")
    abandoned = waiter_dir / "dead-process-token"
    abandoned.touch()
    assert not db_lock.write_handoff_requested(db_path)
    assert not abandoned.exists()

    hostile_fifo = waiter_dir / "hostile-fifo"
    os.mkfifo(hostile_fifo)
    assert not db_lock.write_handoff_requested(db_path)
    assert not hostile_fifo.exists()


def test_handoff_rejects_permissive_waiter_directory(tmp_path: Path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    waiter_dir = Path(f"{db_path}.write.waiters")
    waiter_dir.mkdir(mode=0o755)
    waiter_dir.chmod(0o755)

    with pytest.raises(OSError, match="owner-only"):
        db_lock.write_handoff_requested(db_path)


def test_connect_write_never_unlinks_a_stamped_dead_pid_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    lock_path = Path(f"{db_path}.write.lock")
    lock_path.write_text("999999999 crashed-writer\n")
    inode_before = lock_path.stat().st_ino
    real_unlink = os.unlink

    def refuse_lock_unlink(
        path: str | bytes, *, dir_fd: int | None = None,
    ) -> None:
        if os.fsdecode(path) == str(lock_path):
            raise AssertionError("write-lock inode must remain stable")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", refuse_lock_unlink)
    with db_lock.connect_write(db_path, purpose="inode-stability") as con:
        con.execute("CREATE TABLE proof (value INTEGER)")

    assert lock_path.stat().st_ino == inode_before
