"""Locked-DB fault injector — real ``flock`` contention on the sidecar lock.

``runtime/db_lock.py`` serializes DuckDB writers with an advisory
``fcntl.flock`` on a sidecar file ``<db_path>.write.lock``. A writer that
cannot acquire it within its timeout raises ``WriteLockTimeout``. This injector
reproduces that fault at the *real* seam: it acquires a genuine exclusive
``flock`` on the exact sidecar path ``runtime.db_lock`` uses, so a concurrent
``connect_write(db_path, timeout_s=<short>)`` hits real lock contention and
raises the real ``WriteLockTimeout`` — no mock of the connection, no patch of
the lock logic. On teardown the ``flock`` is released and the fd closed.

The sidecar path is taken from ``runtime.db_lock._lock_path_for`` itself (single
source of truth) so the injector automatically follows any future change to the
sidecar naming — including the autumn-2026 Quack swap the module documents.

This is a **state fault**: the lock is held for the whole ``with`` block, so
``fail_on_call`` does not apply (there is no per-call decision to gate). The
parameter is accepted for API symmetry with the other injectors and rejected if
a caller passes it, to fail loud rather than silently ignore. Use
``readonly_fs`` / ``provider_fault`` when you need per-call gating.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager

__all__ = ["locked_db"]


@contextmanager
def locked_db(
    db_path: str | os.PathLike[str],
    *,
    fail_on_call: int | None = None,
) -> Iterator[None]:
    """Hold a real exclusive lock on ``db_path``'s sidecar for the block.

    While armed, ``runtime.db_lock.connect_write(db_path, ...)`` contends and
    raises ``WriteLockTimeout`` once its timeout elapses. On teardown the lock
    is released; a subsequent ``connect_write`` succeeds.
    """
    if fail_on_call is not None:
        raise ValueError(
            "locked_db is a state fault (the lock is held for the whole block); "
            "fail_on_call does not apply. Use readonly_fs/provider_fault for "
            "per-call gating."
        )

    # Single source of truth for the sidecar path — import lazily so
    # `import tools.faultinject` stays cheap and side-effect-free (duckdb is
    # imported by runtime.db_lock at module load).
    from runtime.db_lock import _lock_path_for

    lock_path = _lock_path_for(os.fspath(db_path))
    parent = os.path.dirname(lock_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        # Non-blocking exclusive acquire: if we cannot take it, another writer
        # already holds it — surface that loudly rather than block the test.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise

    # Stamp PID + purpose for parity with db_lock's own diagnostics
    # (`cat <db>.write.lock` shows who is holding it).
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()} faultinject.locked_db\n".encode())
    except OSError:
        pass

    try:
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
