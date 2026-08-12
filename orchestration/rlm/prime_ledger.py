"""Durable SQLite reservation ledger for supplemental Prime calls.

The ledger grants authority; it deliberately cannot execute a call or write an
Antiek graph/database.  All money is integer micro-USD and all tokens are
integer buckets.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from dataclasses import fields
from pathlib import Path
from typing import cast

from .prime_authority import (
    PRIME_SESSION_CAP_MICRO_USD,
    PrimeAuthorizationRefused,
    PrimeAuthorizationRequest,
    PrimeCallState,
    PrimeEvent,
    PrimeLedgerCorrupt,
    PrimeReceipt,
    PrimeReplayMismatch,
    PrimeUsage,
)

_SCHEMA_VERSION = 2
_IMMUTABLE = tuple(field.name for field in fields(PrimeAuthorizationRequest))
_TERMINAL = {
    PrimeCallState.SUCCEEDED,
    PrimeCallState.FAILED,
    PrimeCallState.CANCELLED,
    PrimeCallState.UNKNOWN,
}


class PrimeLedger:
    """Single-file, concurrency-safe Prime authority and accounting ledger."""

    def __init__(
        self, path: Path | str, *, session_cap_micro_usd: int = PRIME_SESSION_CAP_MICRO_USD
    ) -> None:
        self.path = Path(path)
        if session_cap_micro_usd != PRIME_SESSION_CAP_MICRO_USD:
            raise ValueError("Prime session cap is fixed at 5,000,000 micro-USD")
        self._cap = session_cap_micro_usd
        self._validate_parent()
        self._initialize()

    def _validate_parent(self) -> None:
        try:
            parent = self.path.parent
            metadata = parent.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
                raise PrimeLedgerCorrupt("Prime ledger parent must be a real directory")
            if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
                raise PrimeLedgerCorrupt("Prime ledger parent must be owned and mode 0700")
        except OSError as exc:
            raise PrimeLedgerCorrupt("Prime ledger parent is unavailable") from exc

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise PrimeLedgerCorrupt("Prime ledger integrity check failed")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != _SCHEMA_VERSION:
                raise PrimeLedgerCorrupt(f"unsupported Prime ledger schema version: {version}")
            return connection
        except (sqlite3.DatabaseError, OSError) as exc:
            raise PrimeLedgerCorrupt("Prime ledger is unreadable") from exc

    def _initialize(self) -> None:
        existed = False
        try:
            try:
                metadata = self.path.lstat()
                existed = True
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                ):
                    raise PrimeLedgerCorrupt("Prime ledger file metadata is unsafe")
            except FileNotFoundError:
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                flags |= getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(self.path, flags, 0o600)
                os.close(descriptor)
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            # A private single file is easier to permission-audit than WAL/SHM
            # sidecars, while BEGIN IMMEDIATE still serializes reservations.
            connection.execute("PRAGMA journal_mode=DELETE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            if version == 0 and tables == 0:
                connection.executescript(_SCHEMA)
                connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            elif version != _SCHEMA_VERSION:
                raise PrimeLedgerCorrupt(f"unsupported Prime ledger schema version: {version}")
            connection.close()
            metadata = self.path.lstat()
            if stat.S_IMODE(metadata.st_mode) != 0o600:
                raise PrimeLedgerCorrupt("Prime ledger permissions are not private")
        except (sqlite3.DatabaseError, OSError) as exc:
            if isinstance(exc, PrimeLedgerCorrupt):
                raise
            raise PrimeLedgerCorrupt("Prime ledger initialization failed") from exc
        if existed:
            # Existing stores are checked after version validation too.
            with self._connect() as checked:
                checked.execute("SELECT 1 FROM authorizations LIMIT 1")

    def authorize(
        self, request: PrimeAuthorizationRequest, *, now_ms: int | None = None
    ) -> PrimeReceipt:
        """Atomically reserve the maximum cost, or return an exact replay."""
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM authorizations WHERE request_id=? OR idempotency_key=? OR nonce=?",
                (request.request_id, request.idempotency_key, request.nonce),
            ).fetchall()
            if existing:
                if len(existing) != 1 or not _same_request(existing[0], request):
                    raise PrimeReplayMismatch("request, idempotency key, or nonce replay mismatch")
                return _receipt(existing[0])
            if now < request.issued_at_ms or now >= request.expires_at_ms:
                raise PrimeAuthorizationRefused("authorization is not currently valid")
            session_identity = connection.execute(
                "SELECT owner_id,payer_id FROM authorizations WHERE session_id=? LIMIT 1",
                (request.session_id,),
            ).fetchone()
            if session_identity is not None and (
                session_identity["owner_id"] != request.owner_id
                or session_identity["payer_id"] != request.payer_id
            ):
                raise PrimeReplayMismatch("session owner or payer mismatch")
            frozen = connection.execute(
                "SELECT 1 FROM authorizations WHERE session_id=? AND state=? "
                "AND observed_cost_micro_usd > max_cost_micro_usd LIMIT 1",
                (request.session_id, PrimeCallState.UNKNOWN),
            ).fetchone()
            if frozen is not None:
                raise PrimeAuthorizationRefused("Prime session is frozen by overrun liability")
            spent, held = connection.execute(
                "SELECT COALESCE(SUM(charged_micro_usd),0), COALESCE(SUM(held_micro_usd),0) "
                "FROM authorizations WHERE session_id=?",
                (request.session_id,),
            ).fetchone()
            if spent + held + request.max_cost_micro_usd > self._cap:
                raise PrimeAuthorizationRefused("Prime session spend cap exceeded")
            values = [getattr(request, name) for name in _IMMUTABLE]
            connection.execute(
                f"INSERT INTO authorizations ({','.join(_IMMUTABLE)},state,held_micro_usd,charged_micro_usd,created_at_ms,updated_at_ms) "
                f"VALUES ({','.join('?' for _ in _IMMUTABLE)},?,?,?,?,?)",
                (*values, PrimeCallState.AUTHORIZED, request.max_cost_micro_usd, 0, now, now),
            )
            self._event(
                connection,
                request.request_id,
                PrimeCallState.AUTHORIZED,
                now,
                "reservation_created",
            )
            return self._get(connection, request.request_id)

    reserve = authorize

    def mark_started(self, request_id: str, *, now_ms: int | None = None) -> bool:
        """Claim launch exactly once; ``False`` is an already-started exact replay."""
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        expired = False
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            _validate_forward_time(row, now)
            state = PrimeCallState(row["state"])
            if state is PrimeCallState.AUTHORIZED:
                if now >= row["expires_at_ms"]:
                    self._finish(
                        connection,
                        row,
                        PrimeCallState.CANCELLED,
                        now,
                        "expired_before_start",
                        release=True,
                    )
                    expired = True
                else:
                    connection.execute(
                        "UPDATE authorizations SET state=?,started_at_ms=?,updated_at_ms=? WHERE request_id=?",
                        (PrimeCallState.STARTED, now, now, request_id),
                    )
                    self._event(
                        connection, request_id, PrimeCallState.STARTED, now, "launch_claimed"
                    )
                    return True
            elif state in {PrimeCallState.STARTED, PrimeCallState.USAGE_OBSERVED} | _TERMINAL:
                return False
            else:
                raise PrimeAuthorizationRefused("request cannot be started")
        if expired:
            raise PrimeAuthorizationRefused("authorization expired before launch")
        raise PrimeAuthorizationRefused("request cannot be started")

    start = mark_started

    def observe_usage(
        self, request_id: str, usage: PrimeUsage | None, *, now_ms: int | None = None
    ) -> PrimeReceipt:
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            _validate_forward_time(row, now)
            state = PrimeCallState(row["state"])
            if state is PrimeCallState.USAGE_OBSERVED:
                if usage is not None and _same_usage(row, usage):
                    return _receipt(row)
                raise PrimeReplayMismatch("usage replay mismatch")
            if state is not PrimeCallState.STARTED:
                raise PrimeAuthorizationRefused("usage requires a started request")
            if usage is not None and (
                usage.observed_at_ms < row["started_at_ms"] or usage.observed_at_ms > now
            ):
                raise PrimeAuthorizationRefused("usage timestamp is not monotonic")
            valid = usage is not None and _usage_authorized(row, usage)
            if not valid:
                if usage is not None:
                    self._store_usage(connection, request_id, usage)
                    connection.execute(
                        "UPDATE authorizations SET charged_micro_usd=? WHERE request_id=?",
                        (usage.cost_micro_usd, request_id),
                    )
                self._finish(
                    connection,
                    row,
                    PrimeCallState.UNKNOWN,
                    now,
                    "usage_invalid_or_over_authorized",
                    release=False,
                )
                return self._get(connection, request_id)
            assert usage is not None
            self._store_usage(connection, request_id, usage)
            connection.execute(
                "UPDATE authorizations SET state=?,usage_observed_at_ms=?,updated_at_ms=? WHERE request_id=?",
                (PrimeCallState.USAGE_OBSERVED, usage.observed_at_ms, now, request_id),
            )
            self._event(
                connection, request_id, PrimeCallState.USAGE_OBSERVED, now, "usage_verified"
            )
            return self._get(connection, request_id)

    def succeed(self, request_id: str, *, now_ms: int | None = None) -> PrimeReceipt:
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            _validate_forward_time(row, now)
            state = PrimeCallState(row["state"])
            if state is PrimeCallState.SUCCEEDED:
                return _receipt(row)
            if state is not PrimeCallState.USAGE_OBSERVED:
                if state is PrimeCallState.STARTED:
                    self._finish(
                        connection,
                        row,
                        PrimeCallState.UNKNOWN,
                        now,
                        "success_without_complete_usage",
                        release=False,
                    )
                    return self._get(connection, request_id)
                raise PrimeAuthorizationRefused("success requires verified usage")
            charge = row["observed_cost_micro_usd"]
            connection.execute(
                "UPDATE authorizations SET state=?,charged_micro_usd=?,held_micro_usd=0,terminal_at_ms=?,updated_at_ms=? WHERE request_id=?",
                (PrimeCallState.SUCCEEDED, charge, now, now, request_id),
            )
            self._event(
                connection, request_id, PrimeCallState.SUCCEEDED, now, "exact_charge_reconciled"
            )
            return self._get(connection, request_id)

    def mark_unknown(
        self,
        request_id: str,
        usage: PrimeUsage | None = None,
        *,
        now_ms: int | None = None,
    ) -> PrimeReceipt:
        """Durably quarantine an ambiguous launched call without releasing its hold."""
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            _validate_forward_time(row, now)
            state = PrimeCallState(row["state"])
            if state is PrimeCallState.UNKNOWN:
                if usage is None or _same_usage(row, usage):
                    return _receipt(row)
                raise PrimeReplayMismatch("unknown usage replay mismatch")
            if state not in {PrimeCallState.STARTED, PrimeCallState.USAGE_OBSERVED}:
                raise PrimeAuthorizationRefused("unknown requires a launched request")
            if usage is not None:
                if usage.observed_at_ms < row["started_at_ms"] or usage.observed_at_ms > now:
                    raise PrimeAuthorizationRefused("usage timestamp is not monotonic")
                identity_matches = (
                    usage.provider == row["provider"]
                    and usage.model == row["model"]
                    and usage.prime_version == row["prime_version"]
                )
                if identity_matches:
                    self._store_usage(connection, request_id, usage)
                    connection.execute(
                        "UPDATE authorizations SET charged_micro_usd=? WHERE request_id=?",
                        (usage.cost_micro_usd, request_id),
                    )
            elif state is PrimeCallState.USAGE_OBSERVED:
                connection.execute(
                    "UPDATE authorizations SET charged_micro_usd=observed_cost_micro_usd WHERE request_id=?",
                    (request_id,),
                )
            self._finish(
                connection,
                row,
                PrimeCallState.UNKNOWN,
                now,
                "execution_outcome_unknown",
                release=False,
            )
            return self._get(connection, request_id)

    def fail(self, request_id: str, *, now_ms: int | None = None) -> PrimeReceipt:
        return self._terminal_without_success(request_id, PrimeCallState.FAILED, now_ms)

    def cancel(self, request_id: str, *, now_ms: int | None = None) -> PrimeReceipt:
        return self._terminal_without_success(request_id, PrimeCallState.CANCELLED, now_ms)

    def _terminal_without_success(
        self, request_id: str, target: PrimeCallState, now_ms: int | None
    ) -> PrimeReceipt:
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            _validate_forward_time(row, now)
            state = PrimeCallState(row["state"])
            if state is target:
                return _receipt(row)
            if state in _TERMINAL:
                raise PrimeAuthorizationRefused("terminal state cannot be changed")
            if state is PrimeCallState.AUTHORIZED:
                self._finish(connection, row, target, now, f"{target}_before_start", release=True)
            elif state is PrimeCallState.USAGE_OBSERVED:
                charge = row["observed_cost_micro_usd"]
                connection.execute(
                    "UPDATE authorizations SET state=?,charged_micro_usd=?,held_micro_usd=0,terminal_at_ms=?,updated_at_ms=? WHERE request_id=?",
                    (target, charge, now, now, request_id),
                )
                self._event(connection, request_id, target, now, f"{target}_with_complete_usage")
            else:
                self._finish(
                    connection,
                    row,
                    PrimeCallState.UNKNOWN,
                    now,
                    f"{target}_after_start_without_usage",
                    release=False,
                )
            return self._get(connection, request_id)

    def receipt(self, request_id: str) -> PrimeReceipt:
        with self._connect() as connection:
            return self._get(connection, request_id)

    get_receipt = receipt

    def reconcile_unknown_no_charge(
        self, request_id: str, *, evidence_digest: str, now_ms: int | None = None,
    ) -> PrimeReceipt:
        """Operator-confirmed provider billing evidence that no charge occurred."""
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        if len(evidence_digest) != 64 or any(c not in "0123456789abcdef" for c in evidence_digest):
            raise PrimeAuthorizationRefused("billing evidence digest is invalid")
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            if PrimeCallState(row["state"]) not in {
                PrimeCallState.AUTHORIZED, PrimeCallState.STARTED, PrimeCallState.UNKNOWN,
            }:
                raise PrimeAuthorizationRefused("operation is not reconcilable")
            changed = connection.execute(
                "UPDATE authorizations SET state=?,held_micro_usd=0,charged_micro_usd=0,"
                "terminal_at_ms=?,updated_at_ms=? WHERE request_id=?",
                (PrimeCallState.CANCELLED, now, now, request_id),
            ).rowcount
            if changed != 1:
                raise PrimeLedgerCorrupt("reconcile update failed")
            self._event(connection, request_id, PrimeCallState.CANCELLED, now,
                        f"operator_confirmed_no_charge:{evidence_digest}")
            return self._get(connection, request_id)

    def reconcile_unknown_usage(
        self, request_id: str, usage: PrimeUsage, *, evidence_digest: str,
        now_ms: int | None = None,
    ) -> PrimeReceipt:
        """Settle exact trusted provider-billing usage, retaining overruns."""
        now = _now_ms() if now_ms is None else now_ms
        _validate_now(now)
        if len(evidence_digest) != 64 or any(c not in "0123456789abcdef" for c in evidence_digest):
            raise PrimeAuthorizationRefused("billing evidence digest is invalid")
        with self._transaction() as connection:
            row = self._row(connection, request_id)
            if PrimeCallState(row["state"]) not in {
                PrimeCallState.STARTED, PrimeCallState.USAGE_OBSERVED, PrimeCallState.UNKNOWN,
            }:
                raise PrimeAuthorizationRefused("operation is not reconcilable")
            if not _usage_authorized(row, usage):
                # Identity mismatch is never trusted. A cost overrun with exact
                # identity is retained as UNKNOWN with the full observed charge.
                identity = (
                    usage.provider == row["provider"] and usage.model == row["model"]
                    and usage.prime_version == row["prime_version"]
                )
                if not identity:
                    raise PrimeAuthorizationRefused("billing identity mismatch")
            self._store_usage(connection, request_id, usage)
            terminal = (
                PrimeCallState.SUCCEEDED
                if usage.cost_micro_usd <= row["max_cost_micro_usd"]
                else PrimeCallState.UNKNOWN
            )
            held = 0 if terminal is PrimeCallState.SUCCEEDED else row["held_micro_usd"]
            changed = connection.execute(
                "UPDATE authorizations SET state=?,charged_micro_usd=?,held_micro_usd=?,"
                "terminal_at_ms=?,updated_at_ms=? WHERE request_id=?",
                (terminal, usage.cost_micro_usd, held, now, now, request_id),
            ).rowcount
            if changed != 1:
                raise PrimeLedgerCorrupt("reconcile update failed")
            self._event(connection, request_id, terminal, now,
                        f"operator_billing_reconciled:{evidence_digest}")
            return self._get(connection, request_id)

    def events(self, request_id: str) -> tuple[PrimeEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE request_id=? ORDER BY sequence", (request_id,)
            ).fetchall()
        return tuple(
            PrimeEvent(
                row["sequence"],
                row["request_id"],
                PrimeCallState(row["state"]),
                row["occurred_at_ms"],
                row["fact"],
            )
            for row in rows
        )

    def _transaction(self) -> _ImmediateTransaction:
        return _ImmediateTransaction(self._connect())

    @staticmethod
    def _row(connection: sqlite3.Connection, request_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM authorizations WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None:
            raise PrimeAuthorizationRefused("unknown Prime request")
        return cast(sqlite3.Row, row)

    def _get(self, connection: sqlite3.Connection, request_id: str) -> PrimeReceipt:
        return _receipt(self._row(connection, request_id))

    @staticmethod
    def _event(
        connection: sqlite3.Connection, request_id: str, state: PrimeCallState, at: int, fact: str
    ) -> None:
        connection.execute(
            "INSERT INTO events(request_id,state,occurred_at_ms,fact) VALUES(?,?,?,?)",
            (request_id, state, at, fact),
        )

    @staticmethod
    def _store_usage(connection: sqlite3.Connection, request_id: str, usage: PrimeUsage) -> None:
        connection.execute(
            "UPDATE authorizations SET observed_provider=?,observed_model=?,observed_prime_version=?,input_tokens=?,output_tokens=?,cache_read_tokens=?,cache_write_tokens=?,observed_cost_micro_usd=?,stop_reason=?,evidence_digest=?,output_digest=?,provider_request_id=?,provider_event_id=?,usage_observed_at_ms=? WHERE request_id=?",
            (
                usage.provider,
                usage.model,
                usage.prime_version,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                usage.cost_micro_usd,
                usage.stop_reason,
                usage.evidence_digest,
                usage.output_digest,
                usage.provider_request_id,
                usage.provider_event_id,
                usage.observed_at_ms,
                request_id,
            ),
        )

    def _finish(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        state: PrimeCallState,
        now: int,
        fact: str,
        *,
        release: bool,
    ) -> None:
        connection.execute(
            "UPDATE authorizations SET state=?,held_micro_usd=?,terminal_at_ms=?,updated_at_ms=? WHERE request_id=?",
            (state, 0 if release else row["held_micro_usd"], now, now, row["request_id"]),
        )
        self._event(connection, row["request_id"], state, now, fact)


class _ImmediateTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(self, kind: object, value: object, traceback: object) -> None:
        try:
            self.connection.execute("COMMIT" if kind is None else "ROLLBACK")
        finally:
            self.connection.close()


def _same_request(row: sqlite3.Row, request: PrimeAuthorizationRequest) -> bool:
    return bool(all(row[name] == getattr(request, name) for name in _IMMUTABLE))


def _usage_authorized(row: sqlite3.Row, usage: PrimeUsage) -> bool:
    return bool(
        usage.provider == row["provider"]
        and usage.model == row["model"]
        and usage.prime_version == row["prime_version"]
        and usage.cost_micro_usd <= row["max_cost_micro_usd"]
    )


def _same_usage(row: sqlite3.Row, usage: PrimeUsage) -> bool:
    return bool(
        all(
            (
                row["observed_provider"] == usage.provider,
                row["observed_model"] == usage.model,
                row["observed_prime_version"] == usage.prime_version,
                row["input_tokens"] == usage.input_tokens,
                row["output_tokens"] == usage.output_tokens,
                row["cache_read_tokens"] == usage.cache_read_tokens,
                row["cache_write_tokens"] == usage.cache_write_tokens,
                row["observed_cost_micro_usd"] == usage.cost_micro_usd,
                row["stop_reason"] == usage.stop_reason,
                row["evidence_digest"] == usage.evidence_digest,
                row["output_digest"] == usage.output_digest,
                row["provider_request_id"] == usage.provider_request_id,
                row["provider_event_id"] == usage.provider_event_id,
                row["usage_observed_at_ms"] == usage.observed_at_ms,
            )
        )
    )


def _receipt(row: sqlite3.Row) -> PrimeReceipt:
    request = PrimeAuthorizationRequest(**{name: row[name] for name in _IMMUTABLE})
    return PrimeReceipt(
        authorization=request,
        state=PrimeCallState(row["state"]),
        held_micro_usd=row["held_micro_usd"],
        charged_micro_usd=row["charged_micro_usd"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cache_read_tokens=row["cache_read_tokens"],
        cache_write_tokens=row["cache_write_tokens"],
        observed_cost_micro_usd=row["observed_cost_micro_usd"],
        stop_reason=row["stop_reason"],
        evidence_digest=row["evidence_digest"],
        output_digest=row["output_digest"],
        provider_request_id=row["provider_request_id"],
        provider_event_id=row["provider_event_id"],
        created_at_ms=row["created_at_ms"],
        updated_at_ms=row["updated_at_ms"],
        started_at_ms=row["started_at_ms"],
        usage_observed_at_ms=row["usage_observed_at_ms"],
        terminal_at_ms=row["terminal_at_ms"],
    )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _validate_now(now: object) -> None:
    if type(now) is not int or not 0 <= now <= 2**63 - 1:
        raise PrimeAuthorizationRefused("now_ms must be a bounded integer timestamp")


def _validate_forward_time(row: sqlite3.Row, now: int) -> None:
    if now < row["created_at_ms"] or now < row["updated_at_ms"]:
        raise PrimeAuthorizationRefused("ledger time cannot move backwards")


_SCHEMA = """
CREATE TABLE authorizations (
 owner_id TEXT NOT NULL, payer_id TEXT NOT NULL, session_id TEXT NOT NULL,
 request_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, workflow TEXT NOT NULL,
 prompt_digest TEXT NOT NULL, provider TEXT NOT NULL, credential_id TEXT NOT NULL,
 credential_fingerprint TEXT NOT NULL, credential_env_name TEXT NOT NULL, model TEXT NOT NULL,
 prime_version TEXT NOT NULL, max_cost_micro_usd INTEGER NOT NULL CHECK(max_cost_micro_usd > 0),
 issued_at_ms INTEGER NOT NULL, expires_at_ms INTEGER NOT NULL, nonce TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL CHECK(state IN ('authorized','started','usage_observed','succeeded','failed','cancelled','unknown')),
 held_micro_usd INTEGER NOT NULL CHECK(held_micro_usd >= 0),
 charged_micro_usd INTEGER NOT NULL CHECK(charged_micro_usd >= 0),
 observed_provider TEXT, observed_model TEXT, observed_prime_version TEXT,
 input_tokens INTEGER CHECK(input_tokens >= 0), output_tokens INTEGER CHECK(output_tokens >= 0),
 cache_read_tokens INTEGER CHECK(cache_read_tokens >= 0),
 cache_write_tokens INTEGER CHECK(cache_write_tokens >= 0),
 observed_cost_micro_usd INTEGER CHECK(observed_cost_micro_usd >= 0),
 stop_reason TEXT, evidence_digest TEXT, output_digest TEXT,
 provider_request_id TEXT, provider_event_id TEXT,
 created_at_ms INTEGER NOT NULL, updated_at_ms INTEGER NOT NULL, started_at_ms INTEGER,
 usage_observed_at_ms INTEGER, terminal_at_ms INTEGER
);
CREATE INDEX session_authority ON authorizations(owner_id,payer_id,session_id);
CREATE TABLE events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
 state TEXT NOT NULL, occurred_at_ms INTEGER NOT NULL, fact TEXT NOT NULL,
 FOREIGN KEY(request_id) REFERENCES authorizations(request_id)
);
"""


# Compatibility spelling for callers which prefer an explicit store name.
PrimeAuthorizationLedger = PrimeLedger
