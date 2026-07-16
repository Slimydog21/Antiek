"""Transport-free, process-fenced worker sessions for provider operations."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import re
import sqlite3
import stat
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import TracebackType

from .ledger import (
    BrokerLedgerError,
    BrokerOperationSnapshot,
    BrokerTransition,
    BrokerTransitionRefused,
    LookupDisposition,
    PrimaryBrokerLedger,
)
from .protocol import BrokerReceiptState, canonical_json_bytes

_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_VERSION = 1


class WorkerLeaseError(RuntimeError):
    """Base class for fail-closed worker lease errors."""


class WorkerLeaseUnavailable(WorkerLeaseError):
    """Lease authority or its integrity could not be proved."""


class WorkerLeaseBusy(WorkerLeaseError):
    """A live process holds the operation flock."""


class WorkerLeaseStale(WorkerLeaseError):
    """A session is closed, expired, or no longer owns its fence."""


class WorkerDispatchRefused(WorkerLeaseError):
    """The operation cannot receive a new first-send permit."""


class WorkerLeaseStatus(StrEnum):
    """What a session may safely do; never an outcome classification."""

    AUTHORIZED = "authorized"
    RECOVERY_ONLY = "recovery_only"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class WorkerLease:
    operation_id: str
    tenant_id: str
    idempotency_key: str
    holder_id: str
    fence: int
    attempt_id: str
    acquired_at: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    """One immutable authority handoff to a future, separate adapter."""

    operation_id: str
    tenant_id: str
    idempotency_key: str
    attempt_id: str
    command_id: str
    fence: int
    authorization_digest: str
    route_digest: str
    marked_version: int
    process_id: int


def _identity(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTITY.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded ASCII identity")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("clock must return UTC")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise WorkerLeaseUnavailable("lease timestamp is invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise WorkerLeaseUnavailable("lease timestamp is invalid") from exc
    if _timestamp(parsed) != value:
        raise WorkerLeaseUnavailable("lease timestamp is not canonical")
    return parsed


def _normalized_sql(value: str) -> str:
    return "".join(value.lower().split()).removesuffix(";")


_MIGRATION = """
CREATE TABLE worker_lease_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    version INTEGER NOT NULL CHECK (version = 1)
);
CREATE TABLE worker_leases (
    operation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    holder_id TEXT NOT NULL,
    fence INTEGER NOT NULL CHECK (fence > 0),
    attempt_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active','released','cancelled','recovery_only','terminal')),
    marker_seen INTEGER NOT NULL CHECK (marker_seen IN (0,1)),
    UNIQUE (tenant_id, idempotency_key)
);
CREATE TABLE worker_lease_events (
    operation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL CHECK (event_type IN ('acquired','released','cancelled','marker_recorded','recovered','terminal')),
    holder_id TEXT NOT NULL,
    fence INTEGER NOT NULL CHECK (fence > 0),
    attempt_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    PRIMARY KEY (operation_id, sequence),
    UNIQUE (operation_id, event_hash)
);
CREATE TRIGGER worker_events_no_update BEFORE UPDATE ON worker_lease_events
BEGIN SELECT RAISE(ABORT, 'worker lease events are append-only'); END;
CREATE TRIGGER worker_events_no_delete BEFORE DELETE ON worker_lease_events
BEGIN SELECT RAISE(ABORT, 'worker lease events are append-only'); END;
CREATE TRIGGER worker_leases_no_delete BEFORE DELETE ON worker_leases
BEGIN SELECT RAISE(ABORT, 'worker lease history is durable'); END;
CREATE TRIGGER worker_fence_monotonic BEFORE UPDATE OF fence ON worker_leases
WHEN NEW.fence <= OLD.fence
BEGIN SELECT RAISE(ABORT, 'worker fence must increase'); END;
CREATE TRIGGER worker_marker_irreversible BEFORE UPDATE OF marker_seen ON worker_leases
WHEN OLD.marker_seen = 1 AND NEW.marker_seen != 1
BEGIN SELECT RAISE(ABORT, 'worker marker observation is irreversible'); END;
CREATE TRIGGER worker_recovery_irreversible BEFORE UPDATE OF status ON worker_leases
WHEN (OLD.status = 'recovery_only' AND NEW.status NOT IN ('recovery_only','terminal'))
  OR (OLD.status = 'terminal' AND NEW.status != 'terminal')
BEGIN SELECT RAISE(ABORT, 'worker recovery status is irreversible'); END;
INSERT INTO worker_lease_schema(singleton, version) VALUES (1, 1);
"""

_EXPECTED_TRIGGERS = {
    "worker_events_no_update": """CREATE TRIGGER worker_events_no_update BEFORE UPDATE ON worker_lease_events BEGIN SELECT RAISE(ABORT, 'worker lease events are append-only'); END""",
    "worker_events_no_delete": """CREATE TRIGGER worker_events_no_delete BEFORE DELETE ON worker_lease_events BEGIN SELECT RAISE(ABORT, 'worker lease events are append-only'); END""",
    "worker_leases_no_delete": """CREATE TRIGGER worker_leases_no_delete BEFORE DELETE ON worker_leases BEGIN SELECT RAISE(ABORT, 'worker lease history is durable'); END""",
    "worker_fence_monotonic": """CREATE TRIGGER worker_fence_monotonic BEFORE UPDATE OF fence ON worker_leases WHEN NEW.fence <= OLD.fence BEGIN SELECT RAISE(ABORT, 'worker fence must increase'); END""",
    "worker_marker_irreversible": """CREATE TRIGGER worker_marker_irreversible BEFORE UPDATE OF marker_seen ON worker_leases WHEN OLD.marker_seen = 1 AND NEW.marker_seen != 1 BEGIN SELECT RAISE(ABORT, 'worker marker observation is irreversible'); END""",
    "worker_recovery_irreversible": """CREATE TRIGGER worker_recovery_irreversible BEFORE UPDATE OF status ON worker_leases WHEN (OLD.status = 'recovery_only' AND NEW.status NOT IN ('recovery_only','terminal')) OR (OLD.status = 'terminal' AND NEW.status != 'terminal') BEGIN SELECT RAISE(ABORT, 'worker recovery status is irreversible'); END""",
}

_EXPECTED_TABLES = {
    "worker_lease_schema": """CREATE TABLE worker_lease_schema (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), version INTEGER NOT NULL CHECK (version = 1))""",
    "worker_leases": """CREATE TABLE worker_leases (operation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, holder_id TEXT NOT NULL, fence INTEGER NOT NULL CHECK (fence > 0), attempt_id TEXT NOT NULL, acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('active','released','cancelled','recovery_only','terminal')), marker_seen INTEGER NOT NULL CHECK (marker_seen IN (0,1)), UNIQUE (tenant_id, idempotency_key))""",
    "worker_lease_events": """CREATE TABLE worker_lease_events (operation_id TEXT NOT NULL, sequence INTEGER NOT NULL CHECK (sequence > 0), event_type TEXT NOT NULL CHECK (event_type IN ('acquired','released','cancelled','marker_recorded','recovered','terminal')), holder_id TEXT NOT NULL, fence INTEGER NOT NULL CHECK (fence > 0), attempt_id TEXT NOT NULL, recorded_at TEXT NOT NULL, previous_hash TEXT, event_hash TEXT NOT NULL, PRIMARY KEY (operation_id, sequence), UNIQUE (operation_id, event_hash))""",
}


class WorkerLeaseSession:
    """A per-operation flock held continuously until context exit."""

    def __init__(
        self,
        coordinator: ProviderWorkerLeaseCoordinator,
        lease: WorkerLease,
        status: WorkerLeaseStatus,
        snapshot: BrokerOperationSnapshot,
        descriptor: int,
    ) -> None:
        self._coordinator = coordinator
        self.lease = lease
        self.status = status
        self.snapshot = snapshot
        self._descriptor: int | None = descriptor
        self._thread_id = threading.get_ident()
        self._process_id = os.getpid()
        self._entered = False
        self._exited = False
        self._permit_consumed = False

    def __enter__(self) -> WorkerLeaseSession:
        if self._entered:
            raise WorkerLeaseStale("worker lease session was already entered")
        if os.getpid() != self._process_id:
            raise WorkerLeaseStale("worker lease session belongs to another process")
        if threading.get_ident() != self._thread_id:
            raise WorkerLeaseStale("worker lease session belongs to another thread")
        self._entered = True
        self._assert_live()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._exited:
            return
        if os.getpid() != self._process_id:
            descriptor, self._descriptor = self._descriptor, None
            self._exited = True
            if descriptor is not None:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            raise WorkerLeaseStale("forked child cannot close parent worker lease session")
        if threading.get_ident() != self._thread_id:
            raise WorkerLeaseStale("another thread cannot close worker lease session")
        cleanup_error: BaseException | None = None
        try:
            self._coordinator._close_session(self, cancelled=exc_type is not None)  # noqa: SLF001
        except BaseException as cleanup_exc:
            cleanup_error = cleanup_exc
        finally:
            descriptor, self._descriptor = self._descriptor, None
            self._exited = True
            if descriptor is not None:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError as unlock_exc:
                    cleanup_error = cleanup_error or unlock_exc
                try:
                    os.close(descriptor)
                except OSError as close_exc:
                    cleanup_error = cleanup_error or close_exc
        if cleanup_error is not None:
            if exc is not None:
                exc.add_note(f"worker lease cleanup also failed: {cleanup_error!r}")
            else:
                raise cleanup_error

    def __del__(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            if os.getpid() == self._process_id:
                with contextlib.suppress(OSError):
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(descriptor)

    def prepare_dispatch(self) -> DispatchPermit:
        self._assert_live()
        return self._coordinator._prepare_dispatch(self)  # noqa: SLF001

    def refresh(self) -> BrokerOperationSnapshot:
        """Reconstruct exact primary state without creating send authority."""
        self._assert_live()
        return self._coordinator._refresh_session(self)  # noqa: SLF001

    def assert_permit_active(self, permit: DispatchPermit) -> BrokerOperationSnapshot:
        """Fence a future adapter immediately before it consumes the permit."""
        self._assert_live()
        return self._coordinator._assert_permit_active(self, permit)  # noqa: SLF001

    def _assert_live(self) -> None:
        if not self._entered:
            raise WorkerLeaseStale("worker lease session has not entered its context")
        if self._exited or self._descriptor is None:
            raise WorkerLeaseStale("worker lease session has exited")
        if os.getpid() != self._process_id:
            raise WorkerLeaseStale("worker lease session belongs to another process")
        if threading.get_ident() != self._thread_id:
            raise WorkerLeaseStale("worker lease session belongs to another thread")


class ProviderWorkerLeaseCoordinator:
    """Creates fenced sessions; deliberately contains no provider transport."""

    def __init__(
        self,
        ledger: PrimaryBrokerLedger,
        lease_db_path: str | Path,
        *,
        lease_ttl_seconds: int = 30,
        lock_timeout_seconds: float = 5.0,
        clock: Callable[[], datetime] = _utc_now,
        after_primary_dispatch: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(ledger, PrimaryBrokerLedger):
            raise TypeError("ledger must be PrimaryBrokerLedger")
        if type(lease_ttl_seconds) is not int or lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be a positive integer")
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")
        self._ledger = ledger
        self._path = Path(lease_db_path).resolve()
        self._lock_dir = Path(f"{ledger._path}.worker-operation-locks")  # noqa: SLF001
        self._ttl = lease_ttl_seconds
        self._lock_timeout = lock_timeout_seconds
        self._clock = clock
        self._after_primary_dispatch = after_primary_dispatch or (lambda: None)

    def ensure_schema(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = self._acquire_flock("__schema__")
        try:
            db = self._connect(create=True)
            try:
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='worker_lease_schema'"
                ).fetchone()
                if exists is None:
                    db.executescript(f"BEGIN IMMEDIATE;\n{_MIGRATION}\nCOMMIT;")
                db.execute("BEGIN IMMEDIATE")
                self._check_schema(db)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(descriptor)

    def session(self, tenant_id: str, idempotency_key: str, holder_id: str) -> WorkerLeaseSession:
        """Acquire the operation flock and return its context-managed owner."""
        _identity("tenant_id", tenant_id)
        _identity("idempotency_key", idempotency_key)
        _identity("holder_id", holder_id)
        initial = self._lookup(tenant_id, idempotency_key)
        descriptor = self._acquire_flock(initial.operation_id)
        try:
            snapshot = self._lookup(tenant_id, idempotency_key)
            if snapshot.operation_id != initial.operation_id:
                raise WorkerLeaseUnavailable("primary operation identity changed")
            now = self._now()
            with self._transaction() as db:
                self._verify_events(db)
                prior = db.execute(
                    "SELECT * FROM worker_leases WHERE operation_id=?", (snapshot.operation_id,)
                ).fetchone()
                if prior is not None:
                    self._verify_current_row(db, prior)
                fence = 1 if prior is None else int(prior["fence"]) + 1
                attempt_id = self._attempt_id(snapshot.operation_id)
                status = self._classify(snapshot)
                acquired_at = _timestamp(now)
                expires_at = _timestamp(now + timedelta(seconds=self._ttl))
                stored_status = {
                    WorkerLeaseStatus.AUTHORIZED: "active",
                    WorkerLeaseStatus.RECOVERY_ONLY: "recovery_only",
                    WorkerLeaseStatus.TERMINAL: "terminal",
                }[status]
                marker_seen = int(
                    snapshot.send_marker or (prior is not None and prior["marker_seen"] == 1)
                )
                if marker_seen and status is WorkerLeaseStatus.AUTHORIZED:
                    raise WorkerLeaseUnavailable("sidecar marker contradicts primary authority")
                if prior is None:
                    db.execute(
                        "INSERT INTO worker_leases VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            snapshot.operation_id,
                            tenant_id,
                            idempotency_key,
                            holder_id,
                            fence,
                            attempt_id,
                            acquired_at,
                            expires_at,
                            stored_status,
                            marker_seen,
                        ),
                    )
                else:
                    if (
                        prior["tenant_id"] != tenant_id
                        or prior["idempotency_key"] != idempotency_key
                        or prior["attempt_id"] != attempt_id
                    ):
                        raise WorkerLeaseUnavailable("worker lease identity differs")
                    db.execute(
                        "UPDATE worker_leases SET holder_id=?,fence=?,acquired_at=?,expires_at=?,status=?,marker_seen=? WHERE operation_id=?",
                        (
                            holder_id,
                            fence,
                            acquired_at,
                            expires_at,
                            stored_status,
                            marker_seen,
                            snapshot.operation_id,
                        ),
                    )
                lease = WorkerLease(
                    snapshot.operation_id,
                    tenant_id,
                    idempotency_key,
                    holder_id,
                    fence,
                    attempt_id,
                    acquired_at,
                    expires_at,
                )
                event = (
                    "acquired"
                    if status is WorkerLeaseStatus.AUTHORIZED
                    else ("recovered" if status is WorkerLeaseStatus.RECOVERY_ONLY else "terminal")
                )
                self._append_event(db, lease, event, acquired_at)
            return WorkerLeaseSession(self, lease, status, snapshot, descriptor)
        except BaseException:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(descriptor)
            raise

    def verify_integrity(self) -> int:
        with self._transaction() as db:
            self._verify_events(db)
            rows = db.execute("SELECT * FROM worker_leases ORDER BY operation_id").fetchall()
            for row in rows:
                self._verify_current_row(db, row)
            return len(rows)

    def _prepare_dispatch(self, session: WorkerLeaseSession) -> DispatchPermit:
        lease = session.lease
        with self._transaction() as db:
            row = self._current_row(db, lease)
            snapshot = self._lookup(lease.tenant_id, lease.idempotency_key)
            session.snapshot = snapshot
            session.status = self._classify(snapshot)
            if session.status is WorkerLeaseStatus.TERMINAL:
                raise WorkerDispatchRefused("operation is terminal")
            if snapshot.send_marker:
                self._record_recovery(db, lease, snapshot)
                session.status = self._classify(snapshot)
                raise WorkerDispatchRefused("dispatch marker already exists; recovery only")
            if session.status is not WorkerLeaseStatus.AUTHORIZED or row["status"] != "active":
                raise WorkerDispatchRefused("operation is not authorized for first dispatch")
            now = self._now()
            if not (
                _parse_timestamp(lease.acquired_at) <= now < _parse_timestamp(lease.expires_at)
            ):
                raise WorkerLeaseStale("worker lease is outside its dispatch window")
            if not (
                _parse_timestamp(snapshot.authorization.not_before)
                <= now
                < _parse_timestamp(snapshot.authorization.expires_at)
            ):
                raise WorkerDispatchRefused("broker authorization is not currently valid")
            command_id = self._command_id(snapshot.operation_id)
            try:
                marked = self._ledger.transition(
                    lease.tenant_id,
                    lease.idempotency_key,
                    BrokerTransition(
                        command_id,
                        snapshot.version,
                        BrokerReceiptState.DISPATCH_POSSIBLE,
                        attempt_id=lease.attempt_id,
                    ),
                )
            except BrokerTransitionRefused as exc:
                raise WorkerDispatchRefused("primary ledger refused dispatch marker") from exc
            self._after_primary_dispatch()
            db.execute(
                "UPDATE worker_leases SET status='recovery_only',marker_seen=1 WHERE operation_id=?",
                (lease.operation_id,),
            )
            self._append_event(db, lease, "marker_recorded", _timestamp(self._now()))
            session.snapshot = marked
            session.status = WorkerLeaseStatus.RECOVERY_ONLY
            return DispatchPermit(
                lease.operation_id,
                lease.tenant_id,
                lease.idempotency_key,
                lease.attempt_id,
                command_id,
                lease.fence,
                marked.authorization_digest,
                marked.route_digest,
                marked.version,
                os.getpid(),
            )

    def _assert_permit_active(
        self, session: WorkerLeaseSession, permit: DispatchPermit
    ) -> BrokerOperationSnapshot:
        if not isinstance(permit, DispatchPermit):
            raise TypeError("permit must be DispatchPermit")
        if session._permit_consumed:  # noqa: SLF001
            raise WorkerLeaseStale("dispatch permit was already consumed")
        lease = session.lease
        expected = DispatchPermit(
            lease.operation_id,
            lease.tenant_id,
            lease.idempotency_key,
            lease.attempt_id,
            self._command_id(lease.operation_id),
            lease.fence,
            session.snapshot.authorization_digest,
            session.snapshot.route_digest,
            session.snapshot.version,
            os.getpid(),
        )
        if permit != expected:
            raise WorkerLeaseStale("dispatch permit differs from active session authority")
        now = self._now()
        if not (_parse_timestamp(lease.acquired_at) <= now < _parse_timestamp(lease.expires_at)):
            raise WorkerLeaseStale("worker lease expired before permit consumption")
        with self._transaction() as db:
            self._current_row(db, lease)
            snapshot = self._lookup(lease.tenant_id, lease.idempotency_key)
            if (
                not snapshot.send_marker
                or snapshot.attempt_id != permit.attempt_id
                or snapshot.authorization_digest != permit.authorization_digest
                or snapshot.route_digest != permit.route_digest
                or snapshot.version != permit.marked_version
            ):
                raise WorkerLeaseStale("primary authority differs from dispatch permit")
            if not (
                _parse_timestamp(snapshot.authorization.not_before)
                <= now
                < _parse_timestamp(snapshot.authorization.expires_at)
            ):
                raise WorkerLeaseStale("broker authorization is invalid at permit consumption")
            session._permit_consumed = True  # noqa: SLF001
            return snapshot

    def _refresh_session(self, session: WorkerLeaseSession) -> BrokerOperationSnapshot:
        with self._transaction() as db:
            self._current_row(db, session.lease)
            snapshot = self._lookup(session.lease.tenant_id, session.lease.idempotency_key)
            status = self._classify(snapshot)
            if status is WorkerLeaseStatus.TERMINAL:
                self._record_terminal(db, session.lease)
            elif snapshot.send_marker:
                self._record_recovery(db, session.lease, snapshot)
            session.snapshot = snapshot
            session.status = status
            return snapshot

    def _close_session(self, session: WorkerLeaseSession, *, cancelled: bool) -> None:
        lease = session.lease
        with self._transaction() as db:
            self._current_row(db, lease)
            snapshot = self._lookup(lease.tenant_id, lease.idempotency_key)
            status = self._classify(snapshot)
            if status is WorkerLeaseStatus.TERMINAL:
                self._record_terminal(db, lease)
                session.status = status
                return
            if snapshot.send_marker:
                self._record_recovery(db, lease, snapshot)
                session.status = status
                return
            event = "cancelled" if cancelled else "released"
            db.execute(
                "UPDATE worker_leases SET status=? WHERE operation_id=?",
                (event, lease.operation_id),
            )
            self._append_event(db, lease, event, _timestamp(self._now()))

    def _record_terminal(self, db: sqlite3.Connection, lease: WorkerLease) -> None:
        row = self._current_row(db, lease)
        if row["status"] != "terminal":
            db.execute(
                "UPDATE worker_leases SET status='terminal' WHERE operation_id=?",
                (lease.operation_id,),
            )
            self._append_event(db, lease, "terminal", _timestamp(self._now()))

    def _record_recovery(
        self, db: sqlite3.Connection, lease: WorkerLease, snapshot: BrokerOperationSnapshot
    ) -> None:
        if snapshot.operation_id != lease.operation_id or snapshot.attempt_id != lease.attempt_id:
            raise WorkerLeaseUnavailable("dispatch marker identity differs")
        row = self._current_row(db, lease)
        if row["status"] != "recovery_only" or row["marker_seen"] != 1:
            db.execute(
                "UPDATE worker_leases SET status='recovery_only',marker_seen=1 WHERE operation_id=?",
                (lease.operation_id,),
            )
            self._append_event(db, lease, "recovered", _timestamp(self._now()))

    @staticmethod
    def _classify(snapshot: BrokerOperationSnapshot) -> WorkerLeaseStatus:
        if snapshot.state in {BrokerReceiptState.CHARGED, BrokerReceiptState.NOT_FOUND}:
            return WorkerLeaseStatus.TERMINAL
        if snapshot.send_marker:
            return WorkerLeaseStatus.RECOVERY_ONLY
        if snapshot.state is BrokerReceiptState.AUTHORIZED:
            return WorkerLeaseStatus.AUTHORIZED
        raise WorkerLeaseUnavailable("primary operation has an impossible lease classification")

    def _lookup(self, tenant_id: str, idempotency_key: str) -> BrokerOperationSnapshot:
        try:
            lookup = self._ledger.lookup(tenant_id, idempotency_key)
        except BrokerLedgerError as exc:
            raise WorkerLeaseUnavailable("primary broker authority is unavailable") from exc
        if lookup.disposition is not LookupDisposition.FOUND or lookup.operation is None:
            raise WorkerDispatchRefused("broker operation does not exist")
        return lookup.operation

    @staticmethod
    def _attempt_id(operation_id: str) -> str:
        digest = hashlib.sha256(
            canonical_json_bytes(
                {"operation_id": operation_id, "purpose": "provider-dispatch-attempt-v1"}
            )
        ).hexdigest()
        return f"attempt:{digest}"

    @staticmethod
    def _command_id(operation_id: str) -> str:
        digest = hashlib.sha256(
            canonical_json_bytes(
                {"operation_id": operation_id, "purpose": "provider-dispatch-command-v1"}
            )
        ).hexdigest()
        return f"dispatch:{digest}"

    def _current_row(self, db: sqlite3.Connection, lease: WorkerLease) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM worker_leases WHERE operation_id=?", (lease.operation_id,)
        ).fetchone()
        if row is None:
            raise WorkerLeaseUnavailable("worker lease record is missing")
        for name in (
            "tenant_id",
            "idempotency_key",
            "holder_id",
            "fence",
            "attempt_id",
            "acquired_at",
            "expires_at",
        ):
            if row[name] != getattr(lease, name):
                raise WorkerLeaseStale("worker lease holder or fence is stale")
        self._verify_events(db)
        self._verify_current_row(db, row)
        return row

    def _append_event(
        self, db: sqlite3.Connection, lease: WorkerLease, event_type: str, recorded_at: str
    ) -> None:
        last = db.execute(
            "SELECT sequence,event_hash,recorded_at FROM worker_lease_events "
            "WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",
            (lease.operation_id,),
        ).fetchone()
        if last is not None and _parse_timestamp(recorded_at) < _parse_timestamp(
            last["recorded_at"]
        ):
            raise WorkerLeaseUnavailable("worker lease event time moved backward")
        sequence = 1 if last is None else int(last["sequence"]) + 1
        previous = None if last is None else last["event_hash"]
        payload = {
            "attempt_id": lease.attempt_id,
            "event_type": event_type,
            "fence": lease.fence,
            "holder_id": lease.holder_id,
            "operation_id": lease.operation_id,
            "previous_hash": previous,
            "recorded_at": recorded_at,
            "sequence": sequence,
        }
        event_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        db.execute(
            "INSERT INTO worker_lease_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                lease.operation_id,
                sequence,
                event_type,
                lease.holder_id,
                lease.fence,
                lease.attempt_id,
                recorded_at,
                previous,
                event_hash,
            ),
        )

    def _verify_events(self, db: sqlite3.Connection) -> None:
        previous_by_operation: dict[str, str | None] = {}
        expected_sequence: dict[str, int] = {}
        fence_by_operation: dict[str, int] = {}
        event_by_operation: dict[str, str] = {}
        holder_by_operation: dict[str, str] = {}
        attempt_by_operation: dict[str, str] = {}
        recorded_by_operation: dict[str, datetime] = {}
        for row in db.execute("SELECT * FROM worker_lease_events ORDER BY operation_id,sequence"):
            operation_id = row["operation_id"]
            sequence = expected_sequence.get(operation_id, 1)
            previous = previous_by_operation.get(operation_id)
            if (
                row["sequence"] != sequence
                or row["previous_hash"] != previous
                or _DIGEST.fullmatch(row["event_hash"]) is None
            ):
                raise WorkerLeaseUnavailable("worker lease event chain is corrupt")
            payload = {
                "attempt_id": row["attempt_id"],
                "event_type": row["event_type"],
                "fence": row["fence"],
                "holder_id": row["holder_id"],
                "operation_id": operation_id,
                "previous_hash": previous,
                "recorded_at": row["recorded_at"],
                "sequence": sequence,
            }
            if hashlib.sha256(canonical_json_bytes(payload)).hexdigest() != row["event_hash"]:
                raise WorkerLeaseUnavailable("worker lease event hash is corrupt")
            _identity("operation_id", operation_id)
            _identity("holder_id", row["holder_id"])
            _identity("attempt_id", row["attempt_id"])
            recorded_at = _parse_timestamp(row["recorded_at"])
            prior_recorded = recorded_by_operation.get(operation_id)
            if prior_recorded is not None and recorded_at < prior_recorded:
                raise WorkerLeaseUnavailable("worker lease event time moved backward")
            prior_fence = fence_by_operation.get(operation_id)
            if prior_fence is None or row["fence"] != prior_fence:
                expected_fence = 1 if prior_fence is None else prior_fence + 1
                prior_event = event_by_operation.get(operation_id)
                if prior_event == "terminal" and row["event_type"] != "terminal":
                    raise WorkerLeaseUnavailable("worker lease terminal history is irreversible")
                if row["fence"] != expected_fence or row["event_type"] not in {
                    "acquired",
                    "recovered",
                    "terminal",
                }:
                    raise WorkerLeaseUnavailable("worker lease fence progression is invalid")
            else:
                allowed_same_fence = {
                    "acquired": {
                        "released",
                        "cancelled",
                        "marker_recorded",
                        "recovered",
                        "terminal",
                    },
                    "marker_recorded": {"terminal"},
                    "recovered": {"terminal"},
                }
                if (
                    row["holder_id"] != holder_by_operation[operation_id]
                    or row["attempt_id"] != attempt_by_operation[operation_id]
                    or row["event_type"]
                    not in allowed_same_fence.get(event_by_operation[operation_id], set())
                ):
                    raise WorkerLeaseUnavailable("worker lease event progression is invalid")
            previous_by_operation[operation_id] = row["event_hash"]
            expected_sequence[operation_id] = sequence + 1
            fence_by_operation[operation_id] = row["fence"]
            event_by_operation[operation_id] = row["event_type"]
            holder_by_operation[operation_id] = row["holder_id"]
            attempt_by_operation[operation_id] = row["attempt_id"]
            recorded_by_operation[operation_id] = recorded_at
        orphan = db.execute(
            "SELECT e.operation_id FROM worker_lease_events AS e "
            "LEFT JOIN worker_leases AS l ON l.operation_id=e.operation_id "
            "WHERE l.operation_id IS NULL LIMIT 1"
        ).fetchone()
        if orphan is not None:
            raise WorkerLeaseUnavailable("worker lease event chain has no current row")

    def _verify_current_row(self, db: sqlite3.Connection, row: sqlite3.Row) -> None:
        for name in ("operation_id", "tenant_id", "idempotency_key", "holder_id", "attempt_id"):
            _identity(name, row[name])
        if type(row["fence"]) is not int or row["fence"] <= 0:
            raise WorkerLeaseUnavailable("worker lease fence is invalid")
        if row["attempt_id"] != self._attempt_id(row["operation_id"]):
            raise WorkerLeaseUnavailable("worker lease attempt identity differs")
        acquired = _parse_timestamp(row["acquired_at"])
        expires = _parse_timestamp(row["expires_at"])
        if expires <= acquired:
            raise WorkerLeaseUnavailable("worker lease validity window is invalid")
        tip = db.execute(
            "SELECT * FROM worker_lease_events WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",
            (row["operation_id"],),
        ).fetchone()
        first_for_fence = db.execute(
            "SELECT * FROM worker_lease_events WHERE operation_id=? AND fence=? "
            "ORDER BY sequence LIMIT 1",
            (row["operation_id"], row["fence"]),
        ).fetchone()
        if tip is None or first_for_fence is None:
            raise WorkerLeaseUnavailable("worker lease row has no event authority")
        for name in ("holder_id", "fence", "attempt_id"):
            if tip[name] != row[name] or first_for_fence[name] != row[name]:
                raise WorkerLeaseUnavailable("worker lease row differs from event authority")
        if first_for_fence["recorded_at"] != row["acquired_at"] or first_for_fence[
            "event_type"
        ] not in {"acquired", "recovered", "terminal"}:
            raise WorkerLeaseUnavailable("worker lease acquisition event differs")
        expected_tip = {
            "active": {"acquired"},
            "released": {"released"},
            "cancelled": {"cancelled"},
            "recovery_only": {"marker_recorded", "recovered"},
            "terminal": {"terminal"},
        }
        if (
            row["status"] not in expected_tip
            or tip["event_type"] not in expected_tip[row["status"]]
        ):
            raise WorkerLeaseUnavailable("worker lease status differs from event authority")
        marker_seen = row["marker_seen"]
        if marker_seen not in (0, 1) or (
            marker_seen == 1
            and row["status"]
            not in {
                "recovery_only",
                "terminal",
            }
        ):
            raise WorkerLeaseUnavailable("worker lease marker authority is inconsistent")

    def _now(self) -> datetime:
        value = self._clock()
        _timestamp(value)
        return value.astimezone(UTC).replace(microsecond=0)

    def _connect(self, *, create: bool) -> sqlite3.Connection:
        if not create and not self._path.is_file():
            raise WorkerLeaseUnavailable("worker lease database does not exist")
        try:
            db = sqlite3.connect(
                f"file:{self._path}?mode={'rwc' if create else 'rw'}",
                uri=True,
                timeout=self._lock_timeout,
                isolation_level=None,
            )
            db.row_factory = sqlite3.Row
            db.execute(f"PRAGMA busy_timeout={int(self._lock_timeout * 1000)}")
            return db
        except (OSError, sqlite3.Error) as exc:
            raise WorkerLeaseUnavailable("worker lease database is unavailable") from exc

    def _check_schema(self, db: sqlite3.Connection) -> None:
        row = db.execute("SELECT version FROM worker_lease_schema WHERE singleton=1").fetchone()
        if row is None or row[0] != _SCHEMA_VERSION:
            raise WorkerLeaseUnavailable("unsupported worker lease schema")
        objects = {
            (row[0], row[1]): row[2]
            for row in db.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','trigger')"
            )
        }
        for name, sql in _EXPECTED_TABLES.items():
            if _normalized_sql(objects.get(("table", name), "")) != _normalized_sql(sql):
                raise WorkerLeaseUnavailable(f"worker lease table {name} differs")
        for name, sql in _EXPECTED_TRIGGERS.items():
            if _normalized_sql(objects.get(("trigger", name), "")) != _normalized_sql(sql):
                raise WorkerLeaseUnavailable(f"worker lease trigger {name} differs")
        if set(objects) != {
            *(("table", name) for name in _EXPECTED_TABLES),
            *(("trigger", name) for name in _EXPECTED_TRIGGERS),
        }:
            raise WorkerLeaseUnavailable("worker lease schema has unexpected objects")

    @contextlib.contextmanager
    def _transaction(self):
        db: sqlite3.Connection | None = None
        try:
            db = self._connect(create=False)
            db.execute("BEGIN IMMEDIATE")
            self._check_schema(db)
            yield db
            db.commit()
        except WorkerLeaseError:
            if db is not None:
                db.rollback()
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError) as exc:
            if db is not None:
                db.rollback()
            raise WorkerLeaseUnavailable("worker lease transaction failed") from exc
        finally:
            if db is not None:
                db.close()

    def _acquire_flock(self, operation_id: str) -> int:
        digest = hashlib.sha256(operation_id.encode("ascii")).hexdigest()
        path = self._lock_dir / f"{digest}.lock"
        descriptor: int | None = None
        try:
            self._lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory = self._lock_dir.stat(follow_symlinks=False)
            if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid():
                raise WorkerLeaseUnavailable("operation lock directory is not trusted")
            flags = os.O_CREAT | os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags, 0o600)
        except OSError as exc:
            raise WorkerLeaseUnavailable("operation lock is unavailable") from exc
        deadline = time.monotonic() + self._lock_timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = os.fstat(descriptor)
                named = path.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(locked.st_mode)
                    or locked.st_nlink != 1
                    or (locked.st_dev, locked.st_ino) != (named.st_dev, named.st_ino)
                ):
                    raise WorkerLeaseUnavailable("operation lock pathname changed")
                return descriptor
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    with contextlib.suppress(OSError):
                        os.close(descriptor)
                    raise WorkerLeaseBusy("operation flock is held by a live session") from None
                time.sleep(min(0.01, self._lock_timeout / 10))
            except (OSError, WorkerLeaseUnavailable) as exc:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
                if isinstance(exc, WorkerLeaseUnavailable):
                    raise
                raise WorkerLeaseUnavailable("operation lock is unavailable") from exc


__all__ = [
    "DispatchPermit",
    "ProviderWorkerLeaseCoordinator",
    "WorkerDispatchRefused",
    "WorkerLease",
    "WorkerLeaseBusy",
    "WorkerLeaseError",
    "WorkerLeaseSession",
    "WorkerLeaseStale",
    "WorkerLeaseStatus",
    "WorkerLeaseUnavailable",
]
