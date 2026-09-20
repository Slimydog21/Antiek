from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import runtime.db_lock as db_lock

# The contender must be a separate PROCESS: since the in-process write gate
# (38171a350, "stop multi-fd flock hang") serializes every connect_write in
# one process, a same-process waiter cannot reach _register_write_waiter
# while the holder is active. Cross-process publication is the mechanism's
# real contract — its only consumer (the recovery worker in app.py) yields
# when "another process has actually reported contention".
_CONTENDER_SCRIPT = """\
import sys
sys.path.insert(0, {repo!r})
import runtime.db_lock as db_lock
with db_lock.connect_write({db!r}, purpose="waiter", timeout_s=30, poll_interval_s=0.01):
    print("acquired", flush=True)
"""


def test_contending_writer_publishes_and_consumes_handoff_signal(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    repo = str(Path(__file__).resolve().parents[1])

    with db_lock.connect_write(db_path, purpose="holder") as holder:
        holder.execute("CREATE TABLE proof (value INTEGER)")
        proc = subprocess.Popen(
            [sys.executable, "-c", _CONTENDER_SCRIPT.format(repo=repo, db=db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Deadline covers interpreter + duckdb import in the child on a
        # loaded CI box; the holder must observe the token well before.
        deadline = time.monotonic() + 30
        while not db_lock.write_handoff_requested(db_path):
            if proc.poll() is not None:
                _, stderr = proc.communicate()
                raise AssertionError(
                    f"contender exited {proc.returncode} before publishing: {stderr}"
                )
            assert time.monotonic() < deadline
            time.sleep(0.01)
    # Holder exited -> child acquires -> exits 0.
    stdout, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0
    assert "acquired" in stdout
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
