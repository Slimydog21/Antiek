from __future__ import annotations

import os
from pathlib import Path

import pytest

import runtime.db_lock as db_lock


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
