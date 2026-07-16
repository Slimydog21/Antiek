"""
DuckDB write-side coordination via advisory file lock.

DuckDB is single-writer-per-process on the raw file. Researchmaxx has three
writer surfaces (daily ingest cron, weekly monitor cron, on-demand kanban
research worker) sharing one file. Without a coordinator, a scheduling overlap
corrupts state. This module provides the smallest mechanism that prevents
that: an exclusive flock on a sidecar lock file acquired before opening
DuckDB for write, released on close.

Quack-swap pathway: this module IS the swap point. When Quack v2.0 ships
(autumn 2026) the body of connect_write() becomes "open a Quack client", the
flock disappears, and every caller continues to work unchanged because the
LockedConnection wrapper still forwards every DuckDB method via __getattr__.
Do NOT introduce a parallel WriteCoordinator class above this one — the call
shape (connect_write returning a context-manager connection) is already the
abstraction the plan asked for. The `WriteCoordinator` / `WriteContext`
Protocols below describe the same call shape in spec-aligned terms and the
`FlockWriteCoordinator` class is a thin facade over `connect_write`; the
swap is still a one-factory-line change in `init_db.get_write_coordinator()`.

Usage — drop-in replacement for `duckdb.connect(path)` at write sites:

    from db_lock import connect_write

    with connect_write(db_path, purpose="ingest") as con:
        con.execute(...)

`purpose` is freeform and gets stamped into the sidecar lock file so a stuck
writer can be diagnosed with `cat <db>.write.lock` (PID + purpose). It is
also logged to the `write_log` table (created by migrate_v7_write_log.py)
along with duration and success/error status for observability.

Read-only callers should use `connect_read()` rather than raw
`duckdb.connect(path, read_only=True)` so all DB access funnels through one
module — the place to add observability later.

WP-2 (2026-05-14): added `write_log` observability with best-effort logging
on close, `WriteCoordinator`/`WriteContext` Protocols, `FlockWriteCoordinator`
facade. The Protocols document the interface for the Quack swap; today's
implementation remains the flock + LockedConnection pair.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import secrets
import stat
import threading
import time
from collections.abc import Iterable, Sequence
from typing import Any, Protocol, runtime_checkable

import duckdb

DEFAULT_TIMEOUT_S = 300  # 5 minutes — long enough for a 200-paper ingest

# Sentinel db_path used by the internal write_log logger to skip recursive
# logging. (We do NOT log the log writes themselves; that would be an
# observability liability without paying for itself.)
_WRITE_LOG_PURPOSE = "_write_log_internal"


def _lock_path_for(db_path: str) -> str:
    return db_path + ".write.lock"


def _waiter_dir_for(db_path: str) -> str:
    return db_path + ".write.waiters"


def _ensure_waiter_dir(db_path: str) -> str:
    waiter_dir = _waiter_dir_for(db_path)
    os.makedirs(waiter_dir, mode=0o700, exist_ok=True)
    metadata = os.lstat(waiter_dir)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise OSError("write-waiter directory must be owner-only and non-symlinked")
    return waiter_dir


def _register_write_waiter(db_path: str) -> tuple[int, str]:
    waiter_dir = _ensure_waiter_dir(db_path)
    path = os.path.join(
        waiter_dir,
        f"{os.getpid()}-{threading.get_ident()}-{secrets.token_hex(8)}",
    )
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd, path


def _unregister_write_waiter(waiter: tuple[int, str] | None) -> None:
    if waiter is None:
        return
    fd, path = waiter
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)
    with contextlib.suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)
    with contextlib.suppress(OSError):
        os.close(fd)


def write_handoff_requested(db_path: str) -> bool:
    """Return whether any live writer is waiting; prune abandoned tokens."""
    try:
        waiter_dir = _ensure_waiter_dir(db_path)
    except FileNotFoundError:
        return False
    dir_fd = os.open(waiter_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    live_waiter = False
    try:
        entries = list(os.scandir(dir_fd))
        for entry in entries:
            try:
                fd = os.open(
                    entry.name,
                    os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                    dir_fd=dir_fd,
                )
            except OSError:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(entry.name, dir_fd=dir_fd)
                continue
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(entry.name, dir_fd=dir_fd)
                    continue
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    live_waiter = True
                    continue
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(entry.name, dir_fd=dir_fd)
            finally:
                os.close(fd)
    finally:
        os.close(dir_fd)
    return live_waiter


class WriteLockTimeout(RuntimeError):
    """Raised when the flock could not be acquired within the timeout."""


# Spec-facing alias. The spec names this WriteCoordinatorTimeout; the existing
# WriteLockTimeout is the same condition. Keep both names so old call sites
# keep working and new code can use the spec terminology.
WriteCoordinatorTimeout = WriteLockTimeout


def _log_write_event(
    db_path: str,
    purpose: str,
    duration_s: float,
    success: bool,
    error: str | None = None,
    max_wait_s: float = 5.0,
) -> None:
    """Append one row to the `write_log` table on a fresh, briefly-locked
    connection.

    Called from `LockedConnection.close()` (clean exit) and from
    `connect_write()` itself when the lock acquire fails (so we capture
    WriteLockTimeout events too). This intentionally opens a *separate*
    coordinator-respecting connection rather than reusing the caller's
    handle — the spec requires the log write not extend the caller's
    critical section, and the caller may have already committed/closed.

    Best-effort: any exception is swallowed (with stderr breadcrumb). The
    main pipeline must NEVER fail because the log table is missing or
    contended. Designed to no-op gracefully when migrate_v7_write_log.py
    hasn't been applied yet.
    """
    if purpose == _WRITE_LOG_PURPOSE:
        # Defensive: we never log the log. Should never happen since the
        # logger opens its own connection bypassing this path, but it
        # guarantees no recursion if someone wires it up incorrectly.
        return
    try:
        # Re-acquire the flock briefly. Short timeout: log writes are
        # append-only and tiny; if the lock is heavily contested, drop the
        # log entry rather than block the caller's clean exit.
        lock_path = _lock_path_for(db_path)
        fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
        deadline = time.monotonic() + max_wait_s
        acquired = False
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        return  # give up; main pipeline already done
                    time.sleep(0.1)
            con = duckdb.connect(db_path)
            try:
                con.execute(
                    "INSERT INTO write_log (purpose, duration_s, success, error) "
                    "VALUES (?, ?, ?, ?)",
                    [purpose, float(duration_s), bool(success), error],
                )
            finally:
                con.close()
        finally:
            if acquired:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                os.close(fd)
            except OSError:
                pass
    except Exception as e:  # pragma: no cover — observability is best-effort
        # If write_log doesn't exist yet (pre-migration), or any other failure,
        # don't propagate. A single line on stderr is enough for ops.
        try:
            import sys as _sys
            _sys.stderr.write(
                f"db_lock: write_log insert failed (non-fatal): {type(e).__name__}: {e}\n"
            )
        except Exception:
            pass


class LockedConnection:
    """Thin wrapper that forwards DuckDB Connection methods and releases the
    advisory flock on close. Intentionally __getattr__-based so this stays
    forward-compatible with new DuckDB API surface.

    WP-2: records a row to the `write_log` table on close, capturing
    duration_s + success/error. The log write happens AFTER the caller's
    flock is released so log latency never extends the critical section.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        lock_fd: int,
        lock_path: str,
        *,
        db_path: str = "",
        purpose: str = "",
        acquired_at: float = 0.0,
        close_log_max_wait_s: float = 5.0,
    ):
        self._con = con
        self._lock_fd = lock_fd
        self._lock_path = lock_path
        self._closed = False
        self._db_path = db_path
        self._purpose = purpose or "-"
        self._acquired_at = acquired_at or time.monotonic()
        self._error: str | None = None
        self._close_log_max_wait_s = close_log_max_wait_s

    def __getattr__(self, name):
        return getattr(self._con, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            # Capture the in-flight exception so write_log records the failure
            # mode. Don't suppress it — we still return False.
            self._error = f"{exc_type.__name__}: {exc}"
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._con.close()
        finally:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                try:
                    os.close(self._lock_fd)
                except OSError:
                    pass
        # Log AFTER the lock is released, on a fresh connection (briefly
        # re-locked). The main pipeline never blocks on this.
        if self._db_path:
            duration = max(0.0, time.monotonic() - self._acquired_at)
            _log_write_event(
                self._db_path,
                self._purpose,
                duration,
                success=(self._error is None),
                error=self._error,
                max_wait_s=self._close_log_max_wait_s,
            )


def connect_write(
    db_path: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = 0.25,
    purpose: str = "",
    close_log_max_wait_s: float = 5.0,
) -> LockedConnection:
    """Acquire an exclusive flock on the sidecar lock file, then open DuckDB
    for write. Returns a LockedConnection that releases the lock on close().

    Blocks up to timeout_s waiting for the lock; raises WriteLockTimeout if
    it can't be acquired. Polls rather than using a blocking flock so we can
    enforce a deadline.

    `purpose` is a short tag (e.g. "ingest", "extract", "supersession-review")
    stamped into the sidecar lock file so a stuck writer is identifiable.
    """
    from runtime.test_store_guard import assert_write_path_not_real_store

    assert_write_path_not_real_store(db_path)
    lock_path = _lock_path_for(db_path)
    parent = os.path.dirname(lock_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    # Never unlink the sidecar. flock authority belongs to its inode; replacing
    # the pathname while another process still holds the old inode would allow
    # two writers to acquire different locks. A dead process releases flock in
    # the kernel, so the permanent file needs no stale-file cleanup.
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    deadline = time.monotonic() + timeout_s
    acquire_start = time.monotonic()
    waiter: tuple[int, str] | None = None
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
                # The lock holder cannot see flock waiters directly. Each
                # contender owns a separately flocked token so peers cannot
                # erase its request and dead-process tokens can be pruned.
                if waiter is None:
                    waiter = _register_write_waiter(db_path)
                if time.monotonic() >= deadline:
                    # Record the failed-acquire in write_log so timeout events
                    # are observable. Log AFTER closing the fd so we don't
                    # contend with the lock-holder.
                    os.close(fd)
                    _unregister_write_waiter(waiter)
                    elapsed = time.monotonic() - acquire_start
                    _log_write_event(
                        db_path,
                        purpose or "-",
                        elapsed,
                        success=False,
                        error=f"WriteLockTimeout after {timeout_s}s",
                        # The caller's acquisition deadline has expired;
                        # observability must not add a second wait budget.
                        max_wait_s=0.0,
                    )
                    raise WriteLockTimeout(
                        f"Could not acquire write lock on {lock_path} within {timeout_s}s. "
                        f"Another writer is holding it; inspect with `lsof {lock_path}`."
                    )
                time.sleep(
                    min(poll_interval_s, max(0.0, deadline - time.monotonic()))
                )
    except WriteLockTimeout:
        raise
    except Exception:
        _unregister_write_waiter(waiter)
        try:
            os.close(fd)
        except OSError:
            pass
        raise

    _unregister_write_waiter(waiter)

    # Stamp pid + purpose + ISO timestamp for ops debugging — best-effort.
    try:
        os.ftruncate(fd, 0)
        stamp = f"{os.getpid()} {purpose or '-'} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        os.write(fd, stamp.encode())
    except OSError:
        pass

    try:
        con = duckdb.connect(db_path)
    except Exception:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        raise
    return LockedConnection(
        con,
        fd,
        lock_path,
        db_path=db_path,
        purpose=purpose or "-",
        acquired_at=time.monotonic(),
        close_log_max_wait_s=close_log_max_wait_s,
    )


def connect_read(db_path: str) -> duckdb.DuckDBPyConnection:
    """Open the DB read-only. Use this instead of raw duckdb.connect(...,
    read_only=True) at read sites so every DB access funnels through one
    module — the future place to add per-purpose observability.

    Read-only connections can run concurrently with an active writer.
    """
    return duckdb.connect(db_path, read_only=True)


def connect_write_retrying(
    db_path: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = 0.25,
    max_retries: int = 3,
    retry_delay_s: float = 60.0,
    purpose: str = "",
) -> LockedConnection:
    """Acquire a write lock with retry across lock-timeout boundaries.

    When a cron job collides with another writer, a single connect_write()
    may exhaust its 300s timeout and raise WriteLockTimeout. This wrapper
    retries the entire lock-acquire cycle (releasing O_CREAT semantics each
    time since the sidecar may still exist) up to max_retries times with a
    fixed delay between attempts.

    Use this at cron entry points (ingest, extract, monitor); keep the
    simpler connect_write() for human-invoked operations that should fail
    fast.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return connect_write(
                db_path,
                timeout_s=timeout_s,
                poll_interval_s=poll_interval_s,
                purpose=purpose,
            )
        except WriteLockTimeout as e:
            last_exc = e
            if attempt >= max_retries:
                raise WriteLockTimeout(
                    f"Could not acquire write lock after {max_retries + 1} attempts "
                    f"({(max_retries + 1) * timeout_s:.0f}s total). Last error: {e}"
                ) from e
            print(
                f"Write lock busy (attempt {attempt + 1}/{max_retries + 1}). "
                f"Waiting {retry_delay_s:.0f}s before retry...",
                flush=True,
            )
            time.sleep(retry_delay_s)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Spec-shaped WriteCoordinator / WriteContext Protocols (WP-2, 2026-05-14)
#
# The execution spec describes the write surface in Protocol terms:
#
#     class WriteCoordinator(Protocol):
#         def acquire_write_context(self, purpose: str) -> WriteContext: ...
#
#     class WriteContext(Protocol):
#         def execute(self, sql, params=None): ...
#         def executemany(self, sql, params_list): ...
#         def query(self, sql, params=None): ...
#         def commit(self): ...
#         def rollback(self): ...
#
# The existing `connect_write` returning a `LockedConnection` already satisfies
# this shape via __getattr__ forwarding. We declare the Protocols here for
# type-checking + documentation, and expose `FlockWriteCoordinator` as the
# named today-implementation referenced in the spec. The autumn-2026 swap
# becomes a single line in `init_db.get_write_coordinator()`:
#
#     return QuackWriteCoordinator(...)  # instead of FlockWriteCoordinator(...)
#
# All existing call sites that use `connect_write(...)` directly keep working
# — Quack will provide a drop-in replacement for that function too.
# ---------------------------------------------------------------------------


@runtime_checkable
class WriteContext(Protocol):
    """The handle yielded by `WriteCoordinator.acquire_write_context()`.

    LockedConnection satisfies this Protocol via __getattr__ forwarding to
    the underlying DuckDB connection. The Protocol exists for type-checking
    + documentation; the implementation is the existing LockedConnection.
    """

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any: ...
    def executemany(self, sql: str, params_list: Iterable[Sequence[Any]]) -> Any: ...
    def query(self, sql: str, params: Sequence[Any] | None = None) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


@runtime_checkable
class WriteCoordinator(Protocol):
    """The substrate-write surface, Protocol-shaped.

    Two implementations:
      - FlockWriteCoordinator (today, this file)
      - QuackWriteCoordinator (autumn 2026, when Quack v2.0 ships)

    Callers select the active coordinator via `init_db.get_write_coordinator()`.
    """

    def acquire_write_context(self, purpose: str): ...


class FlockWriteCoordinator:
    """Today's coordinator. A facade over `connect_write` so spec-aligned
    call sites work, while existing `connect_write(...)` call sites continue
    to function unchanged.

    Usage:

        coord = FlockWriteCoordinator(db_path)
        with coord.acquire_write_context("daily_ingest") as ctx:
            ctx.execute("INSERT INTO ...", [...])

    The yielded `ctx` is a LockedConnection (which satisfies WriteContext
    by __getattr__ forwarding).
    """

    def __init__(
        self,
        db_path: str,
        lock_path: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self.db_path = db_path
        # lock_path override is exposed for testing only; production uses the
        # canonical sidecar location.
        self._lock_path_override = lock_path
        self.timeout_s = timeout_s

    @contextlib.contextmanager
    def acquire_write_context(self, purpose: str):
        if not purpose:
            raise ValueError(
                "WriteCoordinator.acquire_write_context: purpose is mandatory. "
                "Pass a short string like 'daily_ingest' or 'orchestrate_session_init'."
            )
        # The spec calls for lock_path override support; if the caller passed
        # one to __init__, monkey-patch the sidecar path computation for
        # this single call. Production never uses this path.
        if self._lock_path_override is not None:
            # Use a manual flock + duckdb open instead of connect_write so
            # the override actually takes effect.
            yield from self._acquire_with_override(purpose)
            return
        con = connect_write(self.db_path, timeout_s=self.timeout_s, purpose=purpose)
        try:
            yield con
        except Exception as exc:
            con._error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            con.close()

    def _acquire_with_override(self, purpose: str):
        """Test-only path: honor a non-default lock_path. Mirrors connect_write
        but uses self._lock_path_override.
        """
        lock_path = self._lock_path_override  # type: ignore[assignment]
        parent = os.path.dirname(lock_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
        deadline = time.monotonic() + self.timeout_s
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        os.close(fd)
                        raise WriteLockTimeout(
                            f"Could not acquire write lock on {lock_path} within {self.timeout_s}s."
                        )
                    time.sleep(0.1)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()} {purpose} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n".encode())
        except OSError:
            pass
        con = duckdb.connect(self.db_path)
        wrapped = LockedConnection(
            con, fd, lock_path,
            db_path=self.db_path, purpose=purpose, acquired_at=time.monotonic(),
        )
        try:
            yield wrapped
        except Exception as exc:
            wrapped._error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            wrapped.close()


def is_locked(db_path: str) -> bool:
    """Probe whether the write lock is currently held by another process.
    Returns True if a non-blocking acquire would have to wait. For diagnostics
    only — do not gate logic on this; it races with the actual writer.
    """
    lock_path = _lock_path_for(db_path)
    if not os.path.exists(lock_path):
        return False
    fd = os.open(lock_path, os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return True
            raise
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)
