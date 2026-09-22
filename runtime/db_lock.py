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
# WP-2b (2026-09-18): write_log close-path wait capped at 250ms (drop if
# contended); no daemon RW thread (races in-process RO / #3121 coexist)
on close, `WriteCoordinator`/`WriteContext` Protocols, `FlockWriteCoordinator`
facade. The Protocols document the interface for the Quack swap; today's
implementation remains the flock + LockedConnection pair.

WP-3 (2026-09-18): optional in-process warm writer keepalive
(`ANTIEK_WRITE_KEEPALIVE_S`, default 20s; disabled under pytest). Parks the
DuckDB handle + flock after close so the next `connect_write` in this process
skips the ~6.8s open on large DBs. Flock stays held while warm (cross-process
writers wait). Cite: #3121 coexist; #3164/#3165 fill contention.
"""

from __future__ import annotations

import atexit
import contextlib
import errno
import fcntl
import os
import secrets
import stat
import threading
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

import duckdb

DEFAULT_TIMEOUT_S = 300  # 5 minutes — long enough for a 200-paper ingest

# Linux flock is per-file-description: two open()s of the sidecar in the
# SAME process can both LOCK_EX, then the second duckdb.connect hangs.
# Serialize writers in-process. Cite: #3121; Ads #3157–#3161.
_PROCESS_WRITE_GATE = threading.Lock()

# ---------------------------------------------------------------------------
# Warm writer keepalive (WP-3 / 2026-09-18)
#
# Prod open of ~881–925MB DuckDB is ~6.7s every connect_write; lease + fills
# thrash open/close. Keep the RW handle + flock for a short idle window so the
# next in-process writer reuses it (process gate still serializes). Cross-
# process writers block on flock until keepalive expires — bounded by default
# 20s. Disabled under pytest so lock-release tests stay honest.
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _write_keepalive_s() -> float:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return 0.0
    return max(0.0, _env_float("ANTIEK_WRITE_KEEPALIVE_S", 20.0))


@dataclass
class _WarmWriterSlot:
    con: Any
    lock_fd: int
    lock_path: str
    db_path: str
    expires_mono: float
    last_purpose: str


_warm_slots: dict[str, _WarmWriterSlot] = {}
_warm_slots_lock = threading.Lock()


def _warm_key(db_path: str) -> str:
    return os.path.abspath(os.fspath(db_path))


def _destroy_warm_slot(slot: _WarmWriterSlot) -> None:
    """Fully release a parked writer (DuckDB close + flock + local registry)."""
    with contextlib.suppress(Exception):
        slot.con.close()
    with contextlib.suppress(Exception):
        _unregister_local_writer(slot.db_path)
    with contextlib.suppress(OSError):
        fcntl.flock(slot.lock_fd, fcntl.LOCK_UN)
    with contextlib.suppress(OSError):
        os.close(slot.lock_fd)


def _take_warm_slot(db_path: str) -> _WarmWriterSlot | None:
    """Return a live warm slot for reuse, or None. Caller holds process gate."""
    key = _warm_key(db_path)
    with _warm_slots_lock:
        slot = _warm_slots.pop(key, None)
    if slot is None:
        return None
    if time.monotonic() >= slot.expires_mono:
        _destroy_warm_slot(slot)
        return None
    return slot


def _park_warm_slot(
    *,
    con: Any,
    lock_fd: int,
    lock_path: str,
    db_path: str,
    purpose: str,
    keepalive_s: float,
) -> None:
    """Park after a successful write session. Caller still holds process gate
    until this returns; gate is released by LockedConnection.close afterward.
    """
    key = _warm_key(db_path)
    new_slot = _WarmWriterSlot(
        con=con,
        lock_fd=lock_fd,
        lock_path=lock_path,
        db_path=db_path,
        expires_mono=time.monotonic() + keepalive_s,
        last_purpose=purpose or "warm-idle",
    )
    try:
        os.ftruncate(lock_fd, 0)
        stamp = (
            f"{os.getpid()} warm-idle/{purpose or '-'} "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        )
        os.write(lock_fd, stamp.encode())
    except OSError:
        pass
    with _warm_slots_lock:
        old = _warm_slots.pop(key, None)
        _warm_slots[key] = new_slot
    if old is not None:
        # Should be unreachable under the process gate; destroy defensively.
        _destroy_warm_slot(old)
    _schedule_warm_expiry(key, new_slot, keepalive_s)


def _expire_warm_slot(key: str, slot: _WarmWriterSlot) -> None:
    """Timer callback: release a parked writer whose keepalive has lapsed.

    Only destroys the slot if it is STILL the parked one for this key — a
    writer that already took it (``_take_warm_slot`` pops under the same
    lock) is never touched, and a newer slot parked after ours is left for
    its own timer.
    """
    with _warm_slots_lock:
        current = _warm_slots.get(key)
        if current is not slot:
            return
        if time.monotonic() < slot.expires_mono:
            return
        _warm_slots.pop(key, None)
    _destroy_warm_slot(slot)


def _schedule_warm_expiry(key: str, slot: _WarmWriterSlot, keepalive_s: float) -> None:
    # WHY A TIMER EXISTS (2026-09-21): ``expires_mono`` used to be consulted
    # only lazily, inside ``_take_warm_slot`` — i.e. on the NEXT in-process
    # write. On an idle service nothing ever called that, so the parked
    # writer held the cross-process flock INDEFINITELY, not "bounded by
    # default 20s" as documented above. Measured on prod: the nightly backup
    # could not acquire the flock in 180s three nights running (RPO breach),
    # GET /export/my-graph answered 503 after its 15s wait, and the
    # workaround was to stop antiek.service for every backup. The timer
    # makes the documented bound true.
    t = threading.Timer(max(keepalive_s, 0.0) + 0.01, _expire_warm_slot, args=(key, slot))
    t.daemon = True
    t.start()


def flush_warm_writers(db_path: str | None = None) -> int:
    """Drop parked warm writers (tests / deploy). Returns number destroyed."""
    with _warm_slots_lock:
        if db_path is None:
            slots = list(_warm_slots.values())
            _warm_slots.clear()
        else:
            key = _warm_key(db_path)
            slot = _warm_slots.pop(key, None)
            slots = [slot] if slot is not None else []
    for slot in slots:
        _destroy_warm_slot(slot)
    return len(slots)


def _atexit_flush_warm_writers() -> None:
    flush_warm_writers()


atexit.register(_atexit_flush_warm_writers)

# Sentinel db_path used by the internal write_log logger to skip recursive
# logging. (We do NOT log the log writes themselves; that would be an
# observability liability without paying for itself.)
_WRITE_LOG_PURPOSE = "_write_log_internal"

_SAME_FILE_DIFFERENT_CONFIG = (
    "Can't open a connection to same database file with a different configuration"
)
_active_writer_lock = threading.Lock()
_active_writers: dict[str, tuple[int, int]] = {}


def _db_identity(db_path: str) -> str:
    return os.path.realpath(os.path.abspath(os.fspath(db_path)))


def _register_local_writer(db_path: str) -> None:
    identity = _db_identity(db_path)
    pid = os.getpid()
    with _active_writer_lock:
        registered_pid, count = _active_writers.get(identity, (pid, 0))
        if registered_pid != pid:
            count = 0
        _active_writers[identity] = (pid, count + 1)


def _unregister_local_writer(db_path: str) -> None:
    identity = _db_identity(db_path)
    pid = os.getpid()
    with _active_writer_lock:
        registered_pid, count = _active_writers.get(identity, (pid, 0))
        if registered_pid != pid or count <= 1:
            _active_writers.pop(identity, None)
        else:
            _active_writers[identity] = (pid, count - 1)


def _has_local_writer(db_path: str) -> bool:
    with _active_writer_lock:
        registered_pid, count = _active_writers.get(_db_identity(db_path), (os.getpid(), 0))
    return registered_pid == os.getpid() and count > 0


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


class TransactionAborted(RuntimeError):
    """A ``transaction()`` block exited cleanly after swallowing a failure.

    DuckDB aborts the entire transaction on the first failing statement, and a
    later COMMIT then succeeds while applying nothing. Raising here converts
    that silence into a signal: the caller learns its write did not land
    instead of being told it did.
    """


def _log_write_event(
    db_path: str,
    purpose: str,
    duration_s: float,
    success: bool,
    error: str | None = None,
    max_wait_s: float = 5.0,
    *,
    blocking: bool = False,
) -> None:
    """Best-effort ``write_log`` append with a hard wait ceiling.

    Cite: #3121 coexist / LazyRW; Speak invite GET hangs when close() waited
    up to 5s (or forever on ``duckdb.connect``) under ``agent_work`` contention.

    Always synchronous (no daemon thread — a background RW connect races
    in-process RO peers with SAME_FILE config errors). ``blocking=False``
    (close path) caps wait at 250ms then drops the log entry. ``blocking=True``
    honors ``max_wait_s`` for tests that assert the row.
    """
    if purpose == _WRITE_LOG_PURPOSE:
        return
    wait = float(max_wait_s) if blocking else min(float(max_wait_s), 0.25)
    _log_write_event_sync(
        db_path, purpose, duration_s, success, error, wait
    )


def _log_write_event_sync(
    db_path: str,
    purpose: str,
    duration_s: float,
    success: bool,
    error: str | None = None,
    max_wait_s: float = 5.0,
) -> None:
    """Synchronous write_log insert. Hard-bounded; never hangs the pipeline.
    """
    if purpose == _WRITE_LOG_PURPOSE:
        # Defensive: we never log the log. Should never happen since the
        # logger opens its own connection bypassing this path, but it
        # guarantees no recursion if someone wires it up incorrectly.
        return
    if not os.path.exists(db_path):
        # NEVER create the store just to log about it. `duckdb.connect` creates
        # the file when absent, and `authority_handoff_guard` reaches here from
        # its release path — including when its body RAISED before the store was
        # created. Its callers in research_owner_dispatch.py pass a **SQLite**
        # path (~/.antiek/owner-launches.sqlite3), so this wrote a DuckDB header
        # at a SQLite path and broke it permanently: every later
        # `sqlite3.connect` then fails with "file is not a database".
        # A missing store means there is nothing to append to. Say nothing.
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
            con = None
            # Retry SAME_FILE config clash for the full wait budget (#3121
            # coexist). Never raise into the caller — drop the log entry if
            # peers still hold RO/RW when the deadline hits.
            open_budget = max(0.0, float(max_wait_s))
            open_deadline = time.monotonic() + (open_budget if open_budget > 0 else 0.0)
            while True:
                try:
                    con = duckdb.connect(db_path)
                    break
                except Exception as open_exc:
                    if _SAME_FILE_DIFFERENT_CONFIG not in str(open_exc):
                        raise
                    if open_budget <= 0 or time.monotonic() >= open_deadline:
                        return  # peer still open; skip observability
                    time.sleep(0.05)
            assert con is not None
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
                with contextlib.suppress(OSError):
                    fcntl.flock(fd, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(fd)
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
        close_log_max_wait_s: float = 0.25,
        from_warm: bool = False,
        keepalive_s: float | None = None,
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
        self._in_explicit_transaction = False
        self._txn_statement_failed = False
        self._from_warm = from_warm
        self._keepalive_s = (
            _write_keepalive_s() if keepalive_s is None else max(0.0, float(keepalive_s))
        )
        # Warm reuse already counted in _active_writers; do not double-register.
        if self._db_path and not from_warm:
            _register_local_writer(self._db_path)

    @property
    def in_explicit_transaction(self) -> bool:
        """Whether this wrapper has successfully entered an explicit txn."""
        return self._in_explicit_transaction

    def execute(
        self, sql: str, parameters: Sequence[Any] | None = None
    ) -> Any:
        """Forward SQL while tracking explicit transaction ownership safely.

        A statement that raises INSIDE an explicit transaction is recorded,
        because DuckDB aborts the whole transaction at that point and a later
        ``COMMIT`` then succeeds while applying nothing. See
        ``transaction()`` for why that silence has to be turned into a raise.
        """
        try:
            result = self._con.execute(sql, parameters)
        except Exception:
            if self._in_explicit_transaction:
                self._txn_statement_failed = True
            raise
        command = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if command == "BEGIN":
            self._in_explicit_transaction = True
            self._txn_statement_failed = False
        elif command in {"COMMIT", "ROLLBACK"}:
            self._in_explicit_transaction = False
            self._txn_statement_failed = False
        return result

    @contextlib.contextmanager
    def transaction(self) -> Iterator[LockedConnection]:
        """Run a multi-statement write atomically.

        The flock this connection holds gives **mutual exclusion**, not
        **atomicity**. They are different properties and conflating them is a
        live source of data loss: DuckDB autocommits every statement, so a
        DELETE followed by a failing INSERT leaves the DELETE durable with no
        rollback. Holding the lock does not help, because nothing else was
        ever racing — the second statement simply failed after the first had
        already committed.

        Any handler whose correctness depends on two or more statements
        landing together, or not at all, must put them inside this block::

            with connect_write(db, purpose="sections/reorder") as con:
                with con.transaction():
                    con.execute("DELETE ...")
                    con.execute("INSERT ...")

        Re-entrant: entering while already inside an explicit transaction
        yields the outermost one rather than issuing a nested BEGIN, which
        DuckDB does not support.

        On the way out of the outermost block this COMMITs, or ROLLBACKs and
        re-raises. ``close()`` already refuses to park a warm slot while
        ``_in_explicit_transaction`` is set, so a transaction that escapes
        cannot be handed to the next caller.

        A block that exits cleanly after SWALLOWING a failed statement raises
        ``TransactionAborted`` rather than committing. DuckDB aborts the whole
        transaction on the first failing statement, and — verified on DuckDB
        1.5.4 — a subsequent ``COMMIT`` then *succeeds* while applying
        nothing::

            BEGIN; DELETE ...; INSERT ... -> ConstraintException (caught)
            COMMIT  -> succeeds
            SELECT  -> the DELETE is gone too; nothing was applied

        Committing there would tell the caller its write landed when the
        datastore is unchanged, which is worse than the non-atomic behaviour
        this contextmanager exists to remove. Catch the failure OUTSIDE the
        ``with`` block instead, which is what the 409 path in
        ``POST /sections/reorder-block`` does.
        """
        if self._in_explicit_transaction:
            yield self
            return
        self.execute("BEGIN")
        try:
            yield self
        except BaseException:
            with contextlib.suppress(Exception):
                self.execute("ROLLBACK")
            raise
        if self._txn_statement_failed:
            with contextlib.suppress(Exception):
                self.execute("ROLLBACK")
            raise TransactionAborted(
                "a statement failed inside this transaction and the error was "
                "swallowed; DuckDB had already aborted the transaction, so "
                "COMMIT would have reported success while applying nothing. "
                "Handle the failure outside the `with con.transaction()` block."
            )
        self.execute("COMMIT")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._con, name)

    def __enter__(self) -> LockedConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if exc is not None and exc_type is not None:
            # Capture the in-flight exception so write_log records the failure
            # mode. Don't suppress it — we still return False.
            self._error = f"{exc_type.__name__}: {exc}"
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        duration = max(0.0, time.monotonic() - self._acquired_at)
        can_park = (
            self._keepalive_s > 0.0
            and bool(self._db_path)
            and not self._in_explicit_transaction
            and self._error is None
            and self._lock_fd >= 0
        )
        if can_park:
            # Log on the warm connection — re-opening for write_log would
            # deadlock on the flock we are about to keep held.
            with contextlib.suppress(Exception):
                self._con.execute(
                    "INSERT INTO write_log (purpose, duration_s, success, error) "
                    "VALUES (?, ?, ?, ?)",
                    [self._purpose, float(duration), True, None],
                )
            _park_warm_slot(
                con=self._con,
                lock_fd=self._lock_fd,
                lock_path=self._lock_path,
                db_path=self._db_path,
                purpose=self._purpose,
                keepalive_s=self._keepalive_s,
            )
            with contextlib.suppress(RuntimeError):
                _PROCESS_WRITE_GATE.release()
            return
        try:
            self._con.close()
        finally:
            if self._db_path:
                _unregister_local_writer(self._db_path)
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                with contextlib.suppress(OSError):
                    os.close(self._lock_fd)
            with contextlib.suppress(RuntimeError):
                _PROCESS_WRITE_GATE.release()
        # Log AFTER the lock is released, on a fresh connection (briefly
        # re-locked). The main pipeline never blocks on this.
        if self._db_path:
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
    close_log_max_wait_s: float = 0.25,
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

    gate_deadline = time.monotonic() + timeout_s
    while True:
        if _PROCESS_WRITE_GATE.acquire(blocking=False):
            break
        if time.monotonic() >= gate_deadline:
            raise WriteLockTimeout(
                f"Could not acquire in-process write gate within {timeout_s}s "
                f"(another connect_write holds it in this process)."
            )
        time.sleep(min(poll_interval_s, max(0.0, gate_deadline - time.monotonic())))

    try:
        return _connect_write_after_process_gate(
            db_path,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            purpose=purpose,
            close_log_max_wait_s=close_log_max_wait_s,
        )
    except BaseException:
        _PROCESS_WRITE_GATE.release()
        raise


def _connect_write_after_process_gate(
    db_path: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = 0.25,
    purpose: str = "",
    close_log_max_wait_s: float = 0.25,
) -> LockedConnection:
    # Fast path: reuse parked in-process writer (skips ~6.8s duckdb.connect).
    warm = _take_warm_slot(db_path)
    if warm is not None:
        try:
            os.ftruncate(warm.lock_fd, 0)
            stamp = (
                f"{os.getpid()} {purpose or '-'} "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            )
            os.write(warm.lock_fd, stamp.encode())
        except OSError:
            pass
        return LockedConnection(
            warm.con,
            warm.lock_fd,
            warm.lock_path,
            db_path=db_path,
            purpose=purpose or "-",
            acquired_at=time.monotonic(),
            close_log_max_wait_s=close_log_max_wait_s,
            from_warm=True,
        )

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
                    ) from e
                time.sleep(
                    min(poll_interval_s, max(0.0, deadline - time.monotonic()))
                )
    except WriteLockTimeout:
        raise
    except Exception:
        _unregister_write_waiter(waiter)
        with contextlib.suppress(OSError):
            os.close(fd)
        raise

    _unregister_write_waiter(waiter)

    # Stamp pid + purpose + ISO timestamp for ops debugging — best-effort.
    try:
        os.ftruncate(fd, 0)
        stamp = f"{os.getpid()} {purpose or '-'} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        os.write(fd, stamp.encode())
    except OSError:
        pass

    # DuckDB rejects RW when any same-process handle is open read-only.
    # Hold the flock while we wait for brief RO sessions (health, spin seed
    # reads) to close — writers stay serialized; readers are short-lived.
    con = None
    open_error: Exception | None = None
    while True:
        try:
            con = duckdb.connect(db_path)
            break
        except Exception as exc:
            open_error = exc
            if _SAME_FILE_DIFFERENT_CONFIG not in str(exc):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(
                min(poll_interval_s, max(0.0, deadline - time.monotonic()))
            )
    if con is None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        assert open_error is not None
        raise open_error
    return LockedConnection(
        con,
        fd,
        lock_path,
        db_path=db_path,
        purpose=purpose or "-",
        acquired_at=time.monotonic(),
        close_log_max_wait_s=close_log_max_wait_s,
    )


class _ReadOrientedConnection:
    """Restrict a same-config fallback to SQL that cannot mutate the catalog."""

    _ALLOWED_STATEMENT_NAMES = {
        "EXPLAIN",
        "LOAD",
        "PRAGMA",
        "SELECT",
        "SET",
        "TRANSACTION",
        "VARIABLE_SET",
    }

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self._con = con

    def _reject_mutation(self, sql: str) -> None:
        statements = self._con.extract_statements(sql)
        rejected = [
            statement.type.name
            for statement in statements
            if statement.type.name not in self._ALLOWED_STATEMENT_NAMES
        ]
        if rejected:
            raise duckdb.InvalidInputException(
                "connect_read fallback rejects non-read SQL statement type(s): "
                + ", ".join(rejected)
            )

    def execute(self, sql: str, parameters: Sequence[Any] | None = None) -> _ReadOrientedConnection:
        self._reject_mutation(sql)
        self._con.execute(sql, parameters)
        return self

    def executemany(self, sql: str, parameters: Sequence[Sequence[Any]]) -> _ReadOrientedConnection:
        self._reject_mutation(sql)
        self._con.executemany(sql, parameters)
        return self

    def cursor(self) -> _ReadOrientedConnection:
        return _ReadOrientedConnection(self._con.cursor())

    def query(self, query: str, *, alias: str = "") -> Any:
        self._reject_mutation(query)
        return self._con.query(query, alias=alias)

    def sql(self, query: str, *, alias: str = "") -> Any:
        self._reject_mutation(query)
        return self._con.sql(query, alias=alias)

    def append(self, *_args: Any, **_kwargs: Any) -> None:
        raise duckdb.InvalidInputException("connect_read fallback rejects append")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._con, name)

    def __enter__(self) -> _ReadOrientedConnection:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        self.close()
        return False

    def close(self) -> None:
        self._con.close()


ReadConnection: TypeAlias = (  # noqa: UP040 -- runtime supports Python 3.11
    duckdb.DuckDBPyConnection | _ReadOrientedConnection
)


def connect_read(
    db_path: str,
) -> ReadConnection:
    """Open the DB read-only. Use this instead of raw duckdb.connect(...,
    read_only=True) at read sites so every DB access funnels through one
    module — the future place to add per-purpose observability.

    DuckDB rejects a true read-only connection when this process already has
    the same file open read-write (``connect_write``, unflocked reuse
    substrates, etc.). On that configuration conflict **or** a unique-file-
    handle / already-attached BinderError (newer DuckDB), fall back to a
    same-config read-write handle whose direct SQL mutation surfaces are
    rejected (``_ReadOrientedConnection``). Other connection failures stay
    explicit rather than being retried with broader privileges.

    Cite: #3121 LazyRW coexist; Ads fills #3157/#3158 (BinderException wedge).
    """
    try:
        return duckdb.connect(db_path, read_only=True)
    except Exception as exc:
        msg = str(exc)
        lazy_ok = (
            _SAME_FILE_DIFFERENT_CONFIG in msg
            or "Unique file handle conflict" in msg
            or "already attached" in msg
        )
        if not lazy_ok:
            raise
        return _ReadOrientedConnection(duckdb.connect(db_path, read_only=False))


@contextlib.contextmanager
def authority_handoff_guard(
    db_path: str,
    *,
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.05,
    purpose: str = "authority-handoff",
) -> Iterator[None]:
    """Bounded exclusive writer-flock guard without opening DuckDB for write.

    Intended for a short authorization handoff that must serialize with every
    ``connect_write`` mutation while an already-open read connection supplies
    the authority facts. It uses the same permanent inode, waiter registry,
    timeout, diagnostic stamp, and best-effort write-log path as writers. Never
    hold this guard over network I/O.
    """
    if timeout_s <= 0 or poll_interval_s <= 0:
        raise ValueError("timeout and poll interval must be positive")
    lock_path = _lock_path_for(db_path)
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    started = time.monotonic()
    deadline = started + timeout_s
    waiter: tuple[int, str] | None = None
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
                if waiter is None:
                    waiter = _register_write_waiter(db_path)
                if time.monotonic() >= deadline:
                    elapsed = time.monotonic() - started
                    _log_write_event(
                        db_path, purpose, elapsed, success=False,
                        error=f"WriteLockTimeout after {timeout_s}s", max_wait_s=0.0,
                    )
                    raise WriteLockTimeout(
                        f"Could not acquire authority handoff lock on {lock_path} "
                        f"within {timeout_s}s; inspect with `lsof {lock_path}`."
                    ) from None
                time.sleep(min(poll_interval_s, max(0.0, deadline - time.monotonic())))
        _unregister_write_waiter(waiter)
        waiter = None
        try:
            os.ftruncate(fd, 0)
            stamp = (
                f"{os.getpid()} {purpose} "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            )
            os.write(fd, stamp.encode())
        except OSError:
            pass
        yield None
    finally:
        _unregister_write_waiter(waiter)
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        if acquired:
            _log_write_event(
                db_path, purpose, time.monotonic() - started,
                success=True, error=None, max_wait_s=0.0,
            )


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

    def acquire_write_context(self, purpose: str) -> Iterator[WriteContext]: ...


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
    def acquire_write_context(self, purpose: str) -> Iterator[WriteContext]:
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

    def _acquire_with_override(self, purpose: str) -> Iterator[LockedConnection]:
        """Test-only path: honor a non-default lock_path. Mirrors connect_write
        but uses self._lock_path_override.
        """
        lock_path = self._lock_path_override
        assert lock_path is not None  # caller branch guarantees an override
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
                        ) from e
                    time.sleep(0.1)
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        with contextlib.suppress(OSError):
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()} {purpose} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n".encode())
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
