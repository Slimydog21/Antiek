"""Resource-count measurement primitives for the nygard steady-state proofs
(SPR-07 M1).

stdlib-only by design — psutil is NOT a dependency of this repo, and SPR-07's
constraint is "no new dependency casually for measurement; prefer stdlib / /proc
with a documented fallback." Everything here is process-scoped: it measures THIS
process, which is what the N-fault leak loops need.

Platform notes (the CI host is the reference; macOS-vs-Linux differences noted):

- ``open_fd_count`` — Linux reads ``/proc/self/fd``; macOS/BSD reads ``/dev/fd``.
  Both list exactly one entry per open descriptor. Counting is cheap and exact
  for the current process.
- ``open_db_connection_count`` — resolves each open fd to its path and counts the
  DuckDB-family files (``.duckdb`` / ``.db`` / ``.wal`` / ``.write.lock``). Path
  resolution: Linux via ``os.readlink('/proc/self/fd/N')``; macOS via
  ``fcntl(fd, F_GETPATH)``. If neither is available the count degrades to ``-1``
  (documented sentinel) rather than lying — callers assert on ``open_fd_count``
  in that case.
- ``active_semaphore_count`` — the ORIGINAL Phase-A leak metric was leaked
  loky/multiprocessing OS semaphores. The research runner has since migrated to
  an in-process ``asyncio.Semaphore`` (``runtime/research_runner/host_local.py``
  lines 4-10 + 287, ``async with self._semaphore``), so it creates NO OS
  semaphores; this counts named POSIX semaphores the process holds (Linux
  ``/dev/shm/sem.*`` + the multiprocessing resource-tracker cache) and is
  expected to be 0 in the asyncio architecture. See
  ``test_steady_state_semaphores.py`` for the modern asyncio-permit steady-state
  proof and the honest note on the eliminated loky leak.
"""

from __future__ import annotations

import contextlib
import os
import sys
from dataclasses import dataclass

_DB_SUFFIXES = (".duckdb", ".db", ".wal", ".write.lock")


def _fd_dir() -> str | None:
    for d in ("/proc/self/fd", "/dev/fd"):
        if os.path.isdir(d):
            return d
    return None  # pragma: no cover - every supported host has one


def open_fd_count() -> int:
    """Number of open file descriptors held by this process."""
    d = _fd_dir()
    if d is None:  # pragma: no cover - defensive
        raise RuntimeError("no /proc/self/fd or /dev/fd available for fd counting")
    # Exclude the transient fd opened by listdir itself is not necessary: listdir
    # closes its own handle before returning. Count what remains.
    return len(os.listdir(d))


def _fd_path(fd: int) -> str | None:
    """Best-effort resolve an fd to its filesystem path (stdlib only)."""
    # Linux: /proc/self/fd/N is a symlink to the target.
    link = f"/proc/self/fd/{fd}"
    if os.path.islink(link):
        try:
            return os.readlink(link)
        except OSError:
            return None
    # macOS/BSD: fcntl F_GETPATH fills a buffer with the path.
    f_getpath = getattr(__import__("fcntl"), "F_GETPATH", None)
    if f_getpath is not None:
        import fcntl

        try:
            raw = fcntl.fcntl(fd, f_getpath, b"\x00" * 1024)
            return raw.split(b"\x00", 1)[0].decode(errors="replace") or None
        except OSError:
            return None
    return None  # pragma: no cover - platform without either mechanism


def open_db_connection_count() -> int:
    """Open fds pointing at a DuckDB-family file (``.duckdb``/``.db``/``.wal``/
    ``.write.lock``). Returns ``-1`` if fd→path resolution is unavailable on this
    platform (callers should then rely on ``open_fd_count``)."""
    d = _fd_dir()
    if d is None:  # pragma: no cover
        return -1
    resolved_any = False
    count = 0
    for name in os.listdir(d):
        try:
            fd = int(name)
        except ValueError:  # pragma: no cover
            continue
        path = _fd_path(fd)
        if path is None:
            continue
        resolved_any = True
        if any(path.endswith(sfx) for sfx in _DB_SUFFIXES):
            count += 1
    return count if resolved_any else -1


def active_semaphore_count() -> int:
    """Named OS/POSIX semaphores this process holds — the Phase-A loky leak
    metric. Expected 0 in the current asyncio-based runner (no OS semaphores).

    Counts Linux ``/dev/shm/sem.*`` plus any semaphore entries the
    multiprocessing resource-tracker is tracking. On macOS there is no
    ``/dev/shm``; POSIX semaphores are anonymous there, so this reflects only the
    resource-tracker cache. Either way, 0 is the healthy steady state — the leak
    class this counts was eliminated by the asyncio migration, not merely reaped.
    """
    total = 0
    shm = "/dev/shm"
    if os.path.isdir(shm):
        # OSError suppressed: a vanishing /dev/shm entry mid-listdir is benign.
        with contextlib.suppress(OSError):
            total += sum(1 for n in os.listdir(shm) if n.startswith("sem."))
    try:  # multiprocessing's resource-tracker cache, when present
        from multiprocessing import resource_tracker as _rt

        tracker = getattr(_rt, "_resource_tracker", None)
        cache = getattr(tracker, "_cache", None)
        if isinstance(cache, dict):
            total += sum(1 for _name, rtype in cache.items() if "sem" in str(rtype))
    except Exception:  # pragma: no cover - resource_tracker internals vary
        pass
    return total


def asyncio_semaphore_permits(sem) -> int:
    """Available permits on an ``asyncio.Semaphore`` (``sem._value``).

    The runner's bounded concurrency (host_local.py) is an asyncio.Semaphore used
    as ``async with self._semaphore`` — a permit is released on every exit path,
    including exceptions. This exposes the permit count so a steady-state test can
    prove no permit is leaked when a task under the semaphore faults repeatedly.
    """
    return int(sem._value)


@dataclass(frozen=True)
class ResourceBaseline:
    """A quiescent-point snapshot of all three resource counts."""

    fds: int
    db_connections: int
    semaphores: int

    def describe(self) -> str:
        return (
            f"fds={self.fds} db_connections={self.db_connections} "
            f"semaphores={self.semaphores} (platform={sys.platform})"
        )


def capture_baseline() -> ResourceBaseline:
    """Snapshot fd / db-connection / semaphore counts at a quiescent point."""
    return ResourceBaseline(
        fds=open_fd_count(),
        db_connections=open_db_connection_count(),
        semaphores=active_semaphore_count(),
    )
