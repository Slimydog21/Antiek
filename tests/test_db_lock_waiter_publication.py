from __future__ import annotations

import errno
import fcntl
import os
import time
from pathlib import Path

import pytest

import runtime.db_lock as db_lock


def test_waiter_retries_when_probe_prunes_new_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "synthetic.duckdb")
    real_open = os.open
    attempts = 0

    def open_with_first_token_pruned(
        path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal attempts
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if flags & os.O_EXCL:
            attempts += 1
            if attempts == 1:
                assert not db_lock.write_handoff_requested(db_path)
        return fd

    monkeypatch.setattr(os, "open", open_with_first_token_pruned)
    waiter = db_lock._register_write_waiter(db_path, deadline=time.monotonic() + 1)
    try:
        fd, path = waiter
        assert attempts == 2
        assert (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (
            os.stat(path).st_dev,
            os.stat(path).st_ino,
        )
        assert db_lock.write_handoff_requested(db_path)
    finally:
        db_lock._unregister_write_waiter(waiter)
    assert not list(Path(f"{db_path}.write.waiters").iterdir())


def test_publication_timeout_closes_sidecar_and_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "synthetic.duckdb")
    lock_path = db_lock._lock_path_for(db_path)
    holder_fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    real_open = os.open
    contender_fds: list[int] = []
    attempts = 0

    def open_with_every_token_pruned(
        path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal attempts
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == lock_path:
            contender_fds.append(fd)
        if flags & os.O_EXCL:
            attempts += 1
            assert not db_lock.write_handoff_requested(db_path)
        return fd

    monkeypatch.setattr(os, "open", open_with_every_token_pruned)
    try:
        with pytest.raises(db_lock.WriteLockTimeout, match="publishing write waiter"):
            db_lock.connect_write(
                db_path, timeout_s=0.03, poll_interval_s=0.001, keepalive_s=0
            )
        assert attempts >= 1
        assert len(contender_fds) == 1
        with pytest.raises(OSError) as exc_info:
            os.fstat(contender_fds[0])
        assert exc_info.value.errno == errno.EBADF
        assert not list(Path(f"{db_path}.write.waiters").iterdir())
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)
