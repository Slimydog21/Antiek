"""Primary transactional ledger for the durable provider broker."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from .protocol import (
    BrokerAuthorization,
    BrokerReceiptState,
    authorization_digest,
    authorization_from_mapping,
    canonical_json_bytes,
    route_digest,
)

SCHEMA_VERSION = 2
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_TERMINAL = frozenset({BrokerReceiptState.CHARGED, BrokerReceiptState.NOT_FOUND})
_ALLOWED_TRANSITIONS = {
    BrokerReceiptState.AUTHORIZED: frozenset(
        {BrokerReceiptState.DISPATCH_POSSIBLE, BrokerReceiptState.NOT_FOUND}
    ),
    BrokerReceiptState.DISPATCH_POSSIBLE: frozenset(
        {
            BrokerReceiptState.UPSTREAM_BOUND,
            BrokerReceiptState.UNKNOWN,
            BrokerReceiptState.CHARGED,
        }
    ),
    BrokerReceiptState.UPSTREAM_BOUND: frozenset(
        {BrokerReceiptState.UNKNOWN, BrokerReceiptState.CHARGED}
    ),
    BrokerReceiptState.UNKNOWN: frozenset(
        {BrokerReceiptState.UPSTREAM_BOUND, BrokerReceiptState.CHARGED}
    ),
}


class BrokerLedgerError(RuntimeError):
    """Base class for fail-closed ledger errors."""


class BrokerConflict(BrokerLedgerError):
    """Persisted authority or command bytes differ from requested bytes."""


class BrokerUnavailable(BrokerLedgerError):
    """Primary authority could not be proved."""


class BrokerIntegrityError(BrokerLedgerError):
    """Persisted authority or audit evidence is inconsistent."""


class BrokerTransitionRefused(BrokerLedgerError):
    """A state transition is stale or forbidden."""


class LookupDisposition(StrEnum):
    FOUND = "found"
    AUTHORITATIVE_MISSING = "authoritative_missing"


@dataclass(frozen=True, slots=True)
class BrokerOperationSnapshot:
    operation_id: str
    authorization: BrokerAuthorization
    authorization_digest: str
    route_digest: str
    state: BrokerReceiptState
    version: int
    send_marker: bool
    attempt_id: str | None
    dispatch_intent: BrokerDispatchIntent | None
    charge_cents: int | None
    provider_charge_cents: int | None
    broker_loss_cents: int | None
    evidence_digest: str | None
    output_digest: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class BrokerLookup:
    disposition: LookupDisposition
    operation: BrokerOperationSnapshot | None

    def __post_init__(self) -> None:
        if (self.disposition is LookupDisposition.FOUND) != (self.operation is not None):
            raise ValueError("lookup disposition and operation disagree")


@dataclass(frozen=True, slots=True)
class BrokerTransition:
    command_id: str
    expected_version: int
    target: BrokerReceiptState
    attempt_id: str | None = None
    dispatch_intent: BrokerDispatchIntent | None = None
    charge_cents: int | None = None
    evidence_digest: str | None = None
    output_digest: str | None = None

    def __post_init__(self) -> None:
        _identity("command_id", self.command_id)
        if type(self.expected_version) is not int or self.expected_version < 0:
            raise ValueError("expected_version must be a nonnegative integer")
        if not isinstance(self.target, BrokerReceiptState):
            raise TypeError("target must be BrokerReceiptState")
        if self.attempt_id is not None:
            _identity("attempt_id", self.attempt_id)
        if self.dispatch_intent is not None and not isinstance(
            self.dispatch_intent, BrokerDispatchIntent
        ):
            raise TypeError("dispatch_intent must be BrokerDispatchIntent")
        for name in ("evidence_digest", "output_digest"):
            value = getattr(self, name)
            if value is not None and _DIGEST.fullmatch(value) is None:
                raise ValueError(f"{name} must be a canonical SHA-256 digest")
        if self.charge_cents is not None and (
            isinstance(self.charge_cents, bool)
            or not isinstance(self.charge_cents, int)
            or self.charge_cents < 0
            or self.charge_cents > (1 << 62) - 1
        ):
            raise ValueError("charge_cents must be nonnegative integer cents")


@dataclass(frozen=True, slots=True)
class BrokerDispatchIntent:
    """Exact immutable authority for one idempotent provider create request."""

    request_envelope_digest: str
    provider_idempotency_token: str
    adapter_contract_digest: str
    qualification_digest: str
    replay_expires_at: str

    def __post_init__(self) -> None:
        for name in (
            "request_envelope_digest",
            "adapter_contract_digest",
            "qualification_digest",
        ):
            if _DIGEST.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} must be a canonical SHA-256 digest")
        _identity("provider_idempotency_token", self.provider_idempotency_token)
        expected_token = provider_idempotency_token(
            self.request_envelope_digest,
            self.adapter_contract_digest,
            self.qualification_digest,
        )
        if self.provider_idempotency_token != expected_token:
            raise ValueError("provider_idempotency_token is not deterministic")
        _parse_timestamp(self.replay_expires_at)


def _identity(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTITY.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded ASCII identity")
    return value


def provider_idempotency_token(
    request_envelope_digest: str,
    adapter_contract_digest: str,
    qualification_digest: str,
) -> str:
    """Derive the stable provider-create token from immutable request authority."""
    for name, value in (
        ("request_envelope_digest", request_envelope_digest),
        ("adapter_contract_digest", adapter_contract_digest),
        ("qualification_digest", qualification_digest),
    ):
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise ValueError(f"{name} must be a canonical SHA-256 digest")
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "adapter_contract_digest": adapter_contract_digest,
                "purpose": "provider-idempotent-create-v1",
                "qualification_digest": qualification_digest,
                "request_envelope_digest": request_envelope_digest,
            }
        )
    ).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("clock must return UTC")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or _UTC_SECOND.fullmatch(value) is None:
        raise ValueError("timestamp is not canonical UTC")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp is not canonical UTC")
    return parsed


def _command_digest(command: BrokerTransition) -> str:
    return hashlib.sha256(canonical_json_bytes(command)).hexdigest()


def _result_json(row: sqlite3.Row) -> str:
    intent = _intent_from_row(row)
    payload = {
        "attempt_id": row["attempt_id"],
        "dispatch_intent": intent,
        "broker_loss_cents": row["broker_loss_cents"],
        "charge_cents": row["charge_cents"],
        "evidence_digest": row["evidence_digest"],
        "operation_id": row["operation_id"],
        "output_digest": row["output_digest"],
        "provider_charge_cents": row["provider_charge_cents"],
        "send_marker": bool(row["send_marker"]),
        "state": row["state"],
        "updated_at": row["updated_at"],
        "version": row["version"],
    }
    return canonical_json_bytes(payload).decode("ascii")


def _event_hash(
    *,
    operation_id: str,
    sequence: int,
    from_state: str | None,
    to_state: str,
    version: int,
    command_id: str,
    command_digest: str,
    result_digest: str,
    recorded_at: str,
    previous_hash: str | None,
) -> str:
    payload = {
        "command_digest": command_digest,
        "command_id": command_id,
        "from_state": from_state,
        "operation_id": operation_id,
        "previous_hash": previous_hash,
        "recorded_at": recorded_at,
        "result_digest": result_digest,
        "sequence": sequence,
        "to_state": to_state,
        "version": version,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


_MIGRATION_1 = """
CREATE TABLE broker_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    version INTEGER NOT NULL CHECK (version = 1)
);
CREATE TABLE broker_operations (
    operation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation_digest TEXT NOT NULL,
    authorization_json TEXT NOT NULL,
    authorization_digest TEXT NOT NULL,
    route_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('authorized','dispatch_possible','upstream_bound','unknown','charged','not_found')),
    version INTEGER NOT NULL CHECK (version >= 0),
    send_marker INTEGER NOT NULL CHECK (send_marker IN (0,1)),
    attempt_id TEXT,
    charge_cents INTEGER,
    provider_charge_cents INTEGER,
    broker_loss_cents INTEGER,
    evidence_digest TEXT,
    output_digest TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, operation_digest)
);
CREATE TABLE broker_commands (
    operation_id TEXT NOT NULL REFERENCES broker_operations(operation_id),
    command_id TEXT NOT NULL,
    command_json TEXT NOT NULL,
    command_digest TEXT NOT NULL,
    resulting_version INTEGER NOT NULL,
    PRIMARY KEY (operation_id, command_id)
);
CREATE TABLE broker_audit (
    operation_id TEXT NOT NULL REFERENCES broker_operations(operation_id),
    sequence INTEGER NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    version INTEGER NOT NULL,
    command_id TEXT NOT NULL,
    command_digest TEXT NOT NULL,
    result_json TEXT NOT NULL,
    result_digest TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    PRIMARY KEY (operation_id, sequence),
    UNIQUE (operation_id, event_hash)
);
CREATE INDEX broker_operations_state_idx ON broker_operations(state);
CREATE TRIGGER broker_audit_no_update BEFORE UPDATE ON broker_audit
BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END;
CREATE TRIGGER broker_audit_no_delete BEFORE DELETE ON broker_audit
BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END;
CREATE TRIGGER broker_commands_no_update BEFORE UPDATE ON broker_commands
BEGIN SELECT RAISE(ABORT, 'broker commands are immutable'); END;
CREATE TRIGGER broker_commands_no_delete BEFORE DELETE ON broker_commands
BEGIN SELECT RAISE(ABORT, 'broker commands are immutable'); END;
CREATE TRIGGER broker_terminal_no_update BEFORE UPDATE ON broker_operations
WHEN OLD.state IN ('charged', 'not_found')
BEGIN SELECT RAISE(ABORT, 'terminal broker operation is immutable'); END;
CREATE TRIGGER broker_operations_no_delete BEFORE DELETE ON broker_operations
BEGIN SELECT RAISE(ABORT, 'broker operations are durable'); END;
INSERT INTO broker_schema(singleton, version) VALUES (1, 1);
"""

_MIGRATION_2 = """
ALTER TABLE broker_operations ADD COLUMN request_envelope_digest TEXT;
ALTER TABLE broker_operations ADD COLUMN provider_idempotency_token TEXT;
ALTER TABLE broker_operations ADD COLUMN adapter_contract_digest TEXT;
ALTER TABLE broker_operations ADD COLUMN qualification_digest TEXT;
ALTER TABLE broker_operations ADD COLUMN replay_expires_at TEXT;
CREATE TRIGGER broker_dispatch_intent_all_or_none BEFORE UPDATE ON broker_operations
WHEN ((NEW.request_envelope_digest IS NULL) + (NEW.provider_idempotency_token IS NULL) +
      (NEW.adapter_contract_digest IS NULL) + (NEW.qualification_digest IS NULL) +
      (NEW.replay_expires_at IS NULL)) NOT IN (0,5)
BEGIN SELECT RAISE(ABORT, 'broker dispatch intent must be complete or absent'); END;
CREATE TRIGGER broker_dispatch_intent_insert_complete BEFORE INSERT ON broker_operations
WHEN ((NEW.request_envelope_digest IS NULL) + (NEW.provider_idempotency_token IS NULL) +
      (NEW.adapter_contract_digest IS NULL) + (NEW.qualification_digest IS NULL) +
      (NEW.replay_expires_at IS NULL)) NOT IN (0,5)
BEGIN SELECT RAISE(ABORT, 'broker dispatch intent must be complete or absent'); END;
CREATE TRIGGER broker_dispatch_intent_immutable BEFORE UPDATE OF request_envelope_digest,
provider_idempotency_token,adapter_contract_digest,qualification_digest,replay_expires_at
ON broker_operations
WHEN (OLD.request_envelope_digest IS NOT NULL AND
      (NEW.request_envelope_digest IS NOT OLD.request_envelope_digest OR
       NEW.provider_idempotency_token IS NOT OLD.provider_idempotency_token OR
       NEW.adapter_contract_digest IS NOT OLD.adapter_contract_digest OR
       NEW.qualification_digest IS NOT OLD.qualification_digest OR
       NEW.replay_expires_at IS NOT OLD.replay_expires_at)) OR
     (OLD.request_envelope_digest IS NULL AND NOT
     ((NEW.request_envelope_digest IS NULL AND NEW.provider_idempotency_token IS NULL AND
       NEW.adapter_contract_digest IS NULL AND NEW.qualification_digest IS NULL AND
       NEW.replay_expires_at IS NULL) OR
      (OLD.state = 'authorized' AND OLD.send_marker = 0 AND
          NEW.state = 'dispatch_possible' AND NEW.send_marker = 1 AND
          NEW.request_envelope_digest IS NOT NULL AND
          NEW.provider_idempotency_token IS NOT NULL AND
          NEW.adapter_contract_digest IS NOT NULL AND
          NEW.qualification_digest IS NOT NULL AND NEW.replay_expires_at IS NOT NULL)))
BEGIN SELECT RAISE(ABORT, 'broker dispatch intent is immutable'); END;
CREATE TABLE broker_schema_v2 (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    version INTEGER NOT NULL CHECK (version = 2)
);
INSERT INTO broker_schema_v2 VALUES (1,2);
DROP TABLE broker_schema;
ALTER TABLE broker_schema_v2 RENAME TO broker_schema;
"""

_EXPECTED_TRIGGER_SQL = {
    "broker_audit_no_update": """
        CREATE TRIGGER broker_audit_no_update BEFORE UPDATE ON broker_audit
        BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END
    """,
    "broker_audit_no_delete": """
        CREATE TRIGGER broker_audit_no_delete BEFORE DELETE ON broker_audit
        BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END
    """,
    "broker_commands_no_update": """
        CREATE TRIGGER broker_commands_no_update BEFORE UPDATE ON broker_commands
        BEGIN SELECT RAISE(ABORT, 'broker commands are immutable'); END
    """,
    "broker_commands_no_delete": """
        CREATE TRIGGER broker_commands_no_delete BEFORE DELETE ON broker_commands
        BEGIN SELECT RAISE(ABORT, 'broker commands are immutable'); END
    """,
    "broker_terminal_no_update": """
        CREATE TRIGGER broker_terminal_no_update BEFORE UPDATE ON broker_operations
        WHEN OLD.state IN ('charged', 'not_found')
        BEGIN SELECT RAISE(ABORT, 'terminal broker operation is immutable'); END
    """,
    "broker_operations_no_delete": """
        CREATE TRIGGER broker_operations_no_delete BEFORE DELETE ON broker_operations
        BEGIN SELECT RAISE(ABORT, 'broker operations are durable'); END
    """,
    "broker_dispatch_intent_all_or_none": """
        CREATE TRIGGER broker_dispatch_intent_all_or_none BEFORE UPDATE ON broker_operations
        WHEN ((NEW.request_envelope_digest IS NULL) + (NEW.provider_idempotency_token IS NULL) + (NEW.adapter_contract_digest IS NULL) + (NEW.qualification_digest IS NULL) + (NEW.replay_expires_at IS NULL)) NOT IN (0,5)
        BEGIN SELECT RAISE(ABORT, 'broker dispatch intent must be complete or absent'); END
    """,
    "broker_dispatch_intent_insert_complete": """
        CREATE TRIGGER broker_dispatch_intent_insert_complete BEFORE INSERT ON broker_operations
        WHEN ((NEW.request_envelope_digest IS NULL) + (NEW.provider_idempotency_token IS NULL) + (NEW.adapter_contract_digest IS NULL) + (NEW.qualification_digest IS NULL) + (NEW.replay_expires_at IS NULL)) NOT IN (0,5)
        BEGIN SELECT RAISE(ABORT, 'broker dispatch intent must be complete or absent'); END
    """,
    "broker_dispatch_intent_immutable": """
        CREATE TRIGGER broker_dispatch_intent_immutable BEFORE UPDATE OF request_envelope_digest,provider_idempotency_token,adapter_contract_digest,qualification_digest,replay_expires_at ON broker_operations
        WHEN (OLD.request_envelope_digest IS NOT NULL AND (NEW.request_envelope_digest IS NOT OLD.request_envelope_digest OR NEW.provider_idempotency_token IS NOT OLD.provider_idempotency_token OR NEW.adapter_contract_digest IS NOT OLD.adapter_contract_digest OR NEW.qualification_digest IS NOT OLD.qualification_digest OR NEW.replay_expires_at IS NOT OLD.replay_expires_at)) OR (OLD.request_envelope_digest IS NULL AND NOT ((NEW.request_envelope_digest IS NULL AND NEW.provider_idempotency_token IS NULL AND NEW.adapter_contract_digest IS NULL AND NEW.qualification_digest IS NULL AND NEW.replay_expires_at IS NULL) OR (OLD.state = 'authorized' AND OLD.send_marker = 0 AND NEW.state = 'dispatch_possible' AND NEW.send_marker = 1 AND NEW.request_envelope_digest IS NOT NULL AND NEW.provider_idempotency_token IS NOT NULL AND NEW.adapter_contract_digest IS NOT NULL AND NEW.qualification_digest IS NOT NULL AND NEW.replay_expires_at IS NOT NULL)))
        BEGIN SELECT RAISE(ABORT, 'broker dispatch intent is immutable'); END
    """,
}


def _intent_from_row(row: sqlite3.Row) -> BrokerDispatchIntent | None:
    values = tuple(
        row[name]
        for name in (
            "request_envelope_digest",
            "provider_idempotency_token",
            "adapter_contract_digest",
            "qualification_digest",
            "replay_expires_at",
        )
    )
    if values == (None,) * 5:
        return None
    if any(value is None for value in values):
        raise BrokerIntegrityError("dispatch intent is incomplete")
    return BrokerDispatchIntent(*values)


def _normalized_sql(value: str) -> str:
    return "".join(value.lower().split()).removesuffix(";")


def _execute_script_in_transaction(db: sqlite3.Connection, script: str) -> None:
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ""
    if statement.strip():
        raise BrokerIntegrityError("broker migration script is incomplete")


class PrimaryBrokerLedger:
    """SQLite primary ledger; it has no replica or read-only missing path."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        lock_timeout_seconds: float = 5.0,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._path = Path(db_path).resolve()
        self._lock_dir = Path(f"{self._path}.broker-locks")
        self._lock_timeout = lock_timeout_seconds
        self._clock = clock
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")

    def ensure_schema(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._key_lock("__schema__", "__schema__"):
            connection = self._connect(create=True)
            try:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_schema'"
                ).fetchone()
                if tables is None:
                    connection.executescript(f"BEGIN IMMEDIATE;\n{_MIGRATION_1}\nCOMMIT;")
                    connection.execute("BEGIN IMMEDIATE")
                    _execute_script_in_transaction(connection, _MIGRATION_2)
                    self._check_schema(connection, full=True)
                else:
                    connection.execute("BEGIN IMMEDIATE")
                    version = connection.execute(
                        "SELECT version FROM broker_schema WHERE singleton=1"
                    ).fetchone()
                    if version is not None and version[0] == 1:
                        self._migrate_v1(connection)
                    self._check_schema(connection, full=True)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _migrate_v1(self, db: sqlite3.Connection) -> None:
        """Add replay columns without altering append-only v1 evidence."""
        _execute_script_in_transaction(db, _MIGRATION_2)

    def authorize(self, authorization: BrokerAuthorization) -> BrokerOperationSnapshot:
        if not isinstance(authorization, BrokerAuthorization):
            raise TypeError("authorization must be BrokerAuthorization")
        canonical = canonical_json_bytes(authorization).decode("ascii")
        digest = authorization_digest(authorization)
        with self._serialized(authorization.tenant_id, authorization.idempotency_key) as db:
            existing = db.execute(
                "SELECT * FROM broker_operations WHERE tenant_id=? AND idempotency_key=?",
                (authorization.tenant_id, authorization.idempotency_key),
            ).fetchone()
            if existing is not None:
                self._verify_operation(db, existing["operation_id"])
                if existing["authorization_json"] != canonical:
                    raise BrokerConflict("idempotency key is bound to different authorization")
                return self._snapshot(existing)
            now = _timestamp(self._clock())
            now_value = _parse_timestamp(now)
            if not (
                _parse_timestamp(authorization.not_before)
                <= now_value
                < _parse_timestamp(authorization.expires_at)
            ):
                raise BrokerTransitionRefused("authorization is not currently valid")
            operation_collision = db.execute(
                "SELECT idempotency_key FROM broker_operations WHERE tenant_id=? AND operation_digest=?",
                (authorization.tenant_id, authorization.operation_digest),
            ).fetchone()
            if operation_collision is not None:
                raise BrokerConflict("operation digest is bound to a different idempotency key")
            operation_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO broker_operations "
                "(operation_id,tenant_id,idempotency_key,operation_digest,"
                "authorization_json,authorization_digest,route_digest,state,version,"
                "send_marker,attempt_id,charge_cents,provider_charge_cents,"
                "broker_loss_cents,evidence_digest,output_digest,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,'authorized',0,0,NULL,NULL,NULL,NULL,NULL,NULL,?,?)",
                (
                    operation_id,
                    authorization.tenant_id,
                    authorization.idempotency_key,
                    authorization.operation_digest,
                    canonical,
                    digest,
                    route_digest(authorization.route),
                    now,
                    now,
                ),
            )
            command_id = f"authorize:{digest}"
            self._append_event(
                db,
                operation_id=operation_id,
                sequence=0,
                from_state=None,
                to_state=BrokerReceiptState.AUTHORIZED,
                version=0,
                command_id=command_id,
                command_json=canonical,
                command_digest=digest,
                recorded_at=now,
                previous_hash=None,
                result_row=db.execute(
                    "SELECT * FROM broker_operations WHERE operation_id=?", (operation_id,)
                ).fetchone(),
            )
            db.execute(
                "INSERT INTO broker_commands VALUES (?,?,?,?,0)",
                (operation_id, command_id, canonical, digest),
            )
            return self._snapshot(
                db.execute(
                    "SELECT * FROM broker_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
            )

    def lookup(self, tenant_id: str, idempotency_key: str) -> BrokerLookup:
        _identity("tenant_id", tenant_id)
        _identity("idempotency_key", idempotency_key)
        with self._serialized(tenant_id, idempotency_key) as db:
            row = db.execute(
                "SELECT * FROM broker_operations WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if row is None:
                return BrokerLookup(LookupDisposition.AUTHORITATIVE_MISSING, None)
            snapshot = self._snapshot(row)
            self._verify_operation(db, snapshot.operation_id)
            return BrokerLookup(LookupDisposition.FOUND, snapshot)

    def transition(
        self,
        tenant_id: str,
        idempotency_key: str,
        command: BrokerTransition,
    ) -> BrokerOperationSnapshot:
        _identity("tenant_id", tenant_id)
        _identity("idempotency_key", idempotency_key)
        if not isinstance(command, BrokerTransition):
            raise TypeError("command must be BrokerTransition")
        digest = _command_digest(command)
        command_json = canonical_json_bytes(command).decode("ascii")
        with self._serialized(tenant_id, idempotency_key) as db:
            row = db.execute(
                "SELECT * FROM broker_operations WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if row is None:
                raise BrokerTransitionRefused("operation does not exist")
            snapshot = self._snapshot(row)
            self._verify_operation(db, snapshot.operation_id)
            replay = db.execute(
                "SELECT command_json, command_digest, resulting_version FROM broker_commands "
                "WHERE operation_id=? AND command_id=?",
                (snapshot.operation_id, command.command_id),
            ).fetchone()
            if replay is not None:
                if replay["command_json"] != command_json or replay["command_digest"] != digest:
                    raise BrokerConflict("command identity is bound to different bytes")
                if snapshot.version < replay["resulting_version"]:
                    raise BrokerIntegrityError("command result is ahead of operation")
                result = db.execute(
                    "SELECT result_json FROM broker_audit WHERE operation_id=? AND sequence=?",
                    (snapshot.operation_id, replay["resulting_version"]),
                ).fetchone()
                if result is None:
                    raise BrokerIntegrityError("command result audit is missing")
                return self._historical_snapshot(snapshot, result["result_json"])
            now = _timestamp(self._clock())
            self._validate_transition(snapshot, command, now=_parse_timestamp(now))
            version = snapshot.version + 1
            send_marker = (
                snapshot.send_marker or command.target is BrokerReceiptState.DISPATCH_POSSIBLE
            )
            attempt_id = (
                command.attempt_id if command.attempt_id is not None else snapshot.attempt_id
            )
            dispatch_intent = command.dispatch_intent or snapshot.dispatch_intent
            provider_charge = (
                command.charge_cents if command.target is BrokerReceiptState.CHARGED else None
            )
            client_charge = (
                min(command.charge_cents, snapshot.authorization.maximum_charge_cents)
                if provider_charge is not None
                else command.charge_cents
            )
            broker_loss = provider_charge - client_charge if provider_charge is not None else None
            db.execute(
                "UPDATE broker_operations SET state=?,version=?,send_marker=?,attempt_id=?,"
                "request_envelope_digest=?,provider_idempotency_token=?,adapter_contract_digest=?,"
                "qualification_digest=?,replay_expires_at=?,"
                "charge_cents=?,provider_charge_cents=?,broker_loss_cents=?,"
                "evidence_digest=?,output_digest=?,updated_at=? "
                "WHERE operation_id=? AND version=?",
                (
                    command.target.value,
                    version,
                    int(send_marker),
                    attempt_id,
                    dispatch_intent.request_envelope_digest if dispatch_intent else None,
                    dispatch_intent.provider_idempotency_token if dispatch_intent else None,
                    dispatch_intent.adapter_contract_digest if dispatch_intent else None,
                    dispatch_intent.qualification_digest if dispatch_intent else None,
                    dispatch_intent.replay_expires_at if dispatch_intent else None,
                    client_charge,
                    provider_charge,
                    broker_loss,
                    command.evidence_digest,
                    command.output_digest,
                    now,
                    snapshot.operation_id,
                    snapshot.version,
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise BrokerTransitionRefused("operation version changed")
            previous = db.execute(
                "SELECT event_hash FROM broker_audit WHERE operation_id=? AND sequence=?",
                (snapshot.operation_id, snapshot.version),
            ).fetchone()
            if previous is None:
                raise BrokerIntegrityError("audit predecessor is missing")
            result_row = db.execute(
                "SELECT * FROM broker_operations WHERE operation_id=?",
                (snapshot.operation_id,),
            ).fetchone()
            self._append_event(
                db,
                operation_id=snapshot.operation_id,
                sequence=version,
                from_state=snapshot.state,
                to_state=command.target,
                version=version,
                command_id=command.command_id,
                command_json=command_json,
                command_digest=digest,
                recorded_at=now,
                previous_hash=previous["event_hash"],
                result_row=result_row,
            )
            db.execute(
                "INSERT INTO broker_commands VALUES (?,?,?,?,?)",
                (
                    snapshot.operation_id,
                    command.command_id,
                    command_json,
                    digest,
                    version,
                ),
            )
            return self._snapshot(result_row)

    def verify_integrity(self) -> int:
        try:
            connection = self._connect(create=False)
            connection.execute("BEGIN IMMEDIATE")
            self._check_schema(connection, full=True)
            operation_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT operation_id FROM broker_operations ORDER BY operation_id"
                )
            ]
            for operation_id in operation_ids:
                self._verify_operation(connection, operation_id)
            connection.rollback()
            return len(operation_ids)
        except BrokerLedgerError:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            raise BrokerIntegrityError("broker ledger integrity could not be proved") from exc
        finally:
            if "connection" in locals():
                connection.close()

    def _validate_transition(
        self,
        snapshot: BrokerOperationSnapshot,
        command: BrokerTransition,
        *,
        now: datetime,
    ) -> None:
        if snapshot.state in _TERMINAL:
            raise BrokerTransitionRefused("terminal operations are immutable")
        if command.expected_version != snapshot.version:
            raise BrokerTransitionRefused("expected version is stale")
        if command.target not in _ALLOWED_TRANSITIONS.get(snapshot.state, frozenset()):
            raise BrokerTransitionRefused("state transition is forbidden")
        if (
            command.target is not BrokerReceiptState.DISPATCH_POSSIBLE
            and command.attempt_id is not None
        ):
            raise BrokerTransitionRefused("attempt identity is immutable after dispatch")
        if (
            command.target is not BrokerReceiptState.DISPATCH_POSSIBLE
            and command.dispatch_intent is not None
        ):
            raise BrokerTransitionRefused("dispatch intent is immutable after dispatch")
        if command.target is BrokerReceiptState.DISPATCH_POSSIBLE:
            if (
                command.attempt_id is None
                or command.dispatch_intent is None
                or any(
                    value is not None
                    for value in (
                        command.charge_cents,
                        command.evidence_digest,
                        command.output_digest,
                    )
                )
            ):
                raise BrokerTransitionRefused("dispatch marker requires attempt and intent only")
        elif command.target is BrokerReceiptState.NOT_FOUND:
            if snapshot.send_marker or _parse_timestamp(snapshot.authorization.expires_at) <= now:
                raise BrokerTransitionRefused(
                    "not-found requires unexpired proven-unsent authority"
                )
            if (
                command.charge_cents != 0
                or command.evidence_digest is None
                or command.output_digest
            ):
                raise BrokerTransitionRefused(
                    "not-found requires zero charge evidence and no output"
                )
        elif command.target is BrokerReceiptState.UPSTREAM_BOUND:
            if (
                command.evidence_digest is None
                or command.charge_cents is not None
                or command.output_digest
            ):
                raise BrokerTransitionRefused("upstream-bound requires identity evidence only")
        elif command.target is BrokerReceiptState.UNKNOWN:
            if command.charge_cents is not None or command.output_digest is not None:
                raise BrokerTransitionRefused("unknown cannot claim charge or output")
        elif command.target is BrokerReceiptState.CHARGED and (
            command.charge_cents is None
            or command.evidence_digest is None
            or command.output_digest is None
        ):
            raise BrokerTransitionRefused("charged result exceeds authority or lacks evidence")

    def _snapshot(self, row: sqlite3.Row) -> BrokerOperationSnapshot:
        try:
            raw = json.loads(row["authorization_json"])
            authorization = authorization_from_mapping(raw)
            if canonical_json_bytes(authorization).decode("ascii") != row["authorization_json"]:
                raise BrokerIntegrityError("authorization JSON is not canonical")
            if authorization_digest(authorization) != row["authorization_digest"]:
                raise BrokerIntegrityError("authorization digest differs")
            if route_digest(authorization.route) != row["route_digest"]:
                raise BrokerIntegrityError("route digest differs")
            if (
                authorization.tenant_id != row["tenant_id"]
                or authorization.idempotency_key != row["idempotency_key"]
                or authorization.operation_digest != row["operation_digest"]
            ):
                raise BrokerIntegrityError("authorization identity differs")
            return BrokerOperationSnapshot(
                operation_id=row["operation_id"],
                authorization=authorization,
                authorization_digest=row["authorization_digest"],
                route_digest=row["route_digest"],
                state=BrokerReceiptState(row["state"]),
                version=row["version"],
                send_marker=bool(row["send_marker"]),
                attempt_id=row["attempt_id"],
                dispatch_intent=_intent_from_row(row),
                charge_cents=row["charge_cents"],
                provider_charge_cents=row["provider_charge_cents"],
                broker_loss_cents=row["broker_loss_cents"],
                evidence_digest=row["evidence_digest"],
                output_digest=row["output_digest"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except BrokerLedgerError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BrokerIntegrityError("operation row is malformed") from exc

    def _verify_operation(self, db: sqlite3.Connection, operation_id: str) -> None:
        row = db.execute(
            "SELECT * FROM broker_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if row is None:
            raise BrokerIntegrityError("operation disappeared")
        snapshot = self._snapshot(row)
        self._validate_snapshot(snapshot)
        events = db.execute(
            "SELECT * FROM broker_audit WHERE operation_id=? ORDER BY sequence",
            (operation_id,),
        ).fetchall()
        if len(events) != snapshot.version + 1:
            raise BrokerIntegrityError("audit length differs from operation version")
        if events[0]["recorded_at"] != snapshot.created_at:
            raise BrokerIntegrityError("audit genesis differs from operation creation")
        command_count = db.execute(
            "SELECT COUNT(*) FROM broker_commands WHERE operation_id=?", (operation_id,)
        ).fetchone()[0]
        if command_count != len(events):
            raise BrokerIntegrityError("command count differs from audit history")
        previous_hash: str | None = None
        previous_state: str | None = None
        previous_result: dict[str, object] | None = None
        for sequence, event in enumerate(events):
            if (
                event["sequence"] != sequence
                or event["version"] != sequence
                or event["from_state"] != previous_state
                or event["previous_hash"] != previous_hash
            ):
                raise BrokerIntegrityError("audit chain ordering differs")
            try:
                _identity("audit command_id", event["command_id"])
                _parse_timestamp(event["recorded_at"])
                if _DIGEST.fullmatch(event["command_digest"]) is None:
                    raise ValueError("invalid command digest")
                to_state = BrokerReceiptState(event["to_state"])
                from_state = (
                    BrokerReceiptState(event["from_state"])
                    if event["from_state"] is not None
                    else None
                )
            except (TypeError, ValueError) as exc:
                raise BrokerIntegrityError("audit event fields are malformed") from exc
            if sequence == 0:
                if from_state is not None or to_state is not BrokerReceiptState.AUTHORIZED:
                    raise BrokerIntegrityError("audit genesis is invalid")
            elif from_state is None or to_state not in _ALLOWED_TRANSITIONS.get(
                from_state, frozenset()
            ):
                raise BrokerIntegrityError("audit transition is forbidden")
            expected_hash = _event_hash(
                operation_id=operation_id,
                sequence=sequence,
                from_state=event["from_state"],
                to_state=event["to_state"],
                version=event["version"],
                command_id=event["command_id"],
                command_digest=event["command_digest"],
                result_digest=event["result_digest"],
                recorded_at=event["recorded_at"],
                previous_hash=event["previous_hash"],
            )
            if event["event_hash"] != expected_hash:
                raise BrokerIntegrityError("audit event hash differs")
            try:
                result_value = json.loads(event["result_json"])
                canonical_result = canonical_json_bytes(result_value).decode("ascii")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise BrokerIntegrityError("audit result bytes are malformed") from exc
            if (
                canonical_result != event["result_json"]
                or hashlib.sha256(event["result_json"].encode("ascii")).hexdigest()
                != event["result_digest"]
            ):
                raise BrokerIntegrityError("audit result digest differs")
            if (
                result_value.get("operation_id") != operation_id
                or result_value.get("version") != sequence
                or result_value.get("state") != event["to_state"]
            ):
                raise BrokerIntegrityError("audit result identity differs")
            historical = self._historical_snapshot(snapshot, event["result_json"])
            command = db.execute(
                "SELECT command_json,command_digest,resulting_version FROM broker_commands "
                "WHERE operation_id=? AND command_id=?",
                (operation_id, event["command_id"]),
            ).fetchone()
            if command is None:
                raise BrokerIntegrityError("audit command evidence differs")
            try:
                command_value = json.loads(command["command_json"])
                canonical_command = canonical_json_bytes(command_value).decode("ascii")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise BrokerIntegrityError("command bytes are malformed") from exc
            if (
                canonical_command != command["command_json"]
                or hashlib.sha256(command["command_json"].encode("ascii")).hexdigest()
                != command["command_digest"]
                or command["command_digest"] != event["command_digest"]
                or command["resulting_version"] != event["version"]
            ):
                raise BrokerIntegrityError("audit command evidence differs")
            expected_result = self._expected_historical_result(
                operation_id=operation_id,
                authorization=snapshot.authorization,
                sequence=sequence,
                command_value=command_value,
                previous_result=previous_result,
                recorded_at=event["recorded_at"],
                legacy_result="dispatch_intent" not in result_value,
            )
            if canonical_json_bytes(expected_result).decode("ascii") != event["result_json"]:
                raise BrokerIntegrityError("command semantics differ from audit result")
            if historical.state.value != expected_result["state"]:
                raise BrokerIntegrityError("historical state verification differs")
            previous_hash = event["event_hash"]
            previous_state = event["to_state"]
            previous_result = result_value
        if previous_state != snapshot.state.value:
            raise BrokerIntegrityError("audit tip differs from operation state")
        if historical != snapshot:
            raise BrokerIntegrityError("audit result tip differs from operation row")

    def _validate_snapshot(self, snapshot: BrokerOperationSnapshot) -> None:
        try:
            created_at = _parse_timestamp(snapshot.created_at)
            updated_at = _parse_timestamp(snapshot.updated_at)
        except ValueError as exc:
            raise BrokerIntegrityError("operation timestamps are malformed") from exc
        if updated_at < created_at or snapshot.version < 0:
            raise BrokerIntegrityError("operation version or timestamps are inconsistent")
        try:
            _identity("operation_id", snapshot.operation_id)
            if snapshot.attempt_id is not None:
                _identity("attempt_id", snapshot.attempt_id)
            for value in (snapshot.evidence_digest, snapshot.output_digest):
                if value is not None and _DIGEST.fullmatch(value) is None:
                    raise ValueError("invalid outcome digest")
        except (TypeError, ValueError) as exc:
            raise BrokerIntegrityError("operation identity or evidence is malformed") from exc
        outcome = (
            snapshot.charge_cents,
            snapshot.provider_charge_cents,
            snapshot.broker_loss_cents,
            snapshot.evidence_digest,
            snapshot.output_digest,
        )
        if snapshot.state is BrokerReceiptState.AUTHORIZED and (
            snapshot.send_marker
            or snapshot.attempt_id is not None
            or snapshot.dispatch_intent is not None
            or outcome != (None, None, None, None, None)
        ):
            raise BrokerIntegrityError("authorized row claims dispatch or outcome")
        if snapshot.state is BrokerReceiptState.DISPATCH_POSSIBLE and (
            not snapshot.send_marker
            or snapshot.attempt_id is None
            or outcome != (None, None, None, None, None)
        ):
            raise BrokerIntegrityError("dispatch row lacks exact marker authority")
        if snapshot.dispatch_intent is not None and not snapshot.send_marker:
            raise BrokerIntegrityError("dispatch intent exists without marker")
        if snapshot.state is BrokerReceiptState.UPSTREAM_BOUND and (
            not snapshot.send_marker
            or snapshot.attempt_id is None
            or snapshot.charge_cents is not None
            or snapshot.provider_charge_cents is not None
            or snapshot.broker_loss_cents is not None
            or snapshot.evidence_digest is None
            or snapshot.output_digest is not None
        ):
            raise BrokerIntegrityError("upstream-bound row has invalid evidence")
        if snapshot.state is BrokerReceiptState.UNKNOWN and (
            not snapshot.send_marker
            or snapshot.attempt_id is None
            or snapshot.charge_cents is not None
            or snapshot.provider_charge_cents is not None
            or snapshot.broker_loss_cents is not None
            or snapshot.output_digest is not None
        ):
            raise BrokerIntegrityError("unknown row has invalid outcome authority")
        if snapshot.state is BrokerReceiptState.CHARGED and (
            not snapshot.send_marker
            or snapshot.attempt_id is None
            or isinstance(snapshot.charge_cents, bool)
            or not isinstance(snapshot.charge_cents, int)
            or snapshot.charge_cents < 0
            or snapshot.charge_cents > snapshot.authorization.maximum_charge_cents
            or not isinstance(snapshot.provider_charge_cents, int)
            or snapshot.provider_charge_cents < snapshot.charge_cents
            or snapshot.broker_loss_cents != snapshot.provider_charge_cents - snapshot.charge_cents
            or snapshot.evidence_digest is None
            or snapshot.output_digest is None
        ):
            raise BrokerIntegrityError("charged row has invalid outcome authority")
        if snapshot.state is BrokerReceiptState.NOT_FOUND and (
            snapshot.send_marker
            or snapshot.attempt_id is not None
            or snapshot.charge_cents != 0
            or snapshot.provider_charge_cents is not None
            or snapshot.broker_loss_cents is not None
            or snapshot.evidence_digest is None
            or snapshot.output_digest is not None
        ):
            raise BrokerIntegrityError("not-found row has invalid absence authority")

    def _historical_snapshot(
        self, current: BrokerOperationSnapshot, result_json: str
    ) -> BrokerOperationSnapshot:
        try:
            value = json.loads(result_json)
            if canonical_json_bytes(value).decode("ascii") != result_json:
                raise ValueError("noncanonical result")
            result_fields = {
                "attempt_id",
                "dispatch_intent",
                "broker_loss_cents",
                "charge_cents",
                "evidence_digest",
                "operation_id",
                "output_digest",
                "provider_charge_cents",
                "send_marker",
                "state",
                "updated_at",
                "version",
            }
            legacy_fields = result_fields - {"dispatch_intent"}
            if set(value) not in {frozenset(result_fields), frozenset(legacy_fields)}:
                raise ValueError("invalid result fields")
            historical = replace(
                current,
                state=BrokerReceiptState(value["state"]),
                version=value["version"],
                send_marker=value["send_marker"],
                attempt_id=value["attempt_id"],
                dispatch_intent=(
                    BrokerDispatchIntent(**value["dispatch_intent"])
                    if value.get("dispatch_intent") is not None
                    else None
                ),
                charge_cents=value["charge_cents"],
                provider_charge_cents=value["provider_charge_cents"],
                broker_loss_cents=value["broker_loss_cents"],
                evidence_digest=value["evidence_digest"],
                output_digest=value["output_digest"],
                updated_at=value["updated_at"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BrokerIntegrityError("historical command result is malformed") from exc
        if historical.operation_id != value.get("operation_id"):
            raise BrokerIntegrityError("historical command result identity differs")
        self._validate_snapshot(historical)
        return historical

    def _expected_historical_result(
        self,
        *,
        operation_id: str,
        authorization: BrokerAuthorization,
        sequence: int,
        command_value: object,
        previous_result: dict[str, object] | None,
        recorded_at: str,
        legacy_result: bool,
    ) -> dict[str, object]:
        if sequence == 0:
            if (
                command_value != json.loads(canonical_json_bytes(authorization))
                or previous_result is not None
            ):
                raise BrokerIntegrityError("authorization command bytes differ")
            expected = {
                "attempt_id": None,
                "dispatch_intent": None,
                "broker_loss_cents": None,
                "charge_cents": None,
                "evidence_digest": None,
                "operation_id": operation_id,
                "output_digest": None,
                "provider_charge_cents": None,
                "send_marker": False,
                "state": BrokerReceiptState.AUTHORIZED.value,
                "updated_at": recorded_at,
                "version": 0,
            }
            if legacy_result:
                del expected["dispatch_intent"]
            return expected
        transition_fields = set(BrokerTransition.__dataclass_fields__)
        legacy_fields = transition_fields - {"dispatch_intent"}
        if not isinstance(command_value, dict) or frozenset(command_value) not in {
            frozenset(transition_fields),
            frozenset(legacy_fields),
        }:
            raise BrokerIntegrityError("transition command fields are malformed")
        if previous_result is None:
            raise BrokerIntegrityError("transition predecessor is missing")
        try:
            command = BrokerTransition(
                command_id=command_value["command_id"],
                expected_version=command_value["expected_version"],
                target=BrokerReceiptState(command_value["target"]),
                attempt_id=command_value["attempt_id"],
                dispatch_intent=(
                    BrokerDispatchIntent(**command_value["dispatch_intent"])
                    if command_value.get("dispatch_intent") is not None
                    else None
                ),
                charge_cents=command_value["charge_cents"],
                evidence_digest=command_value["evidence_digest"],
                output_digest=command_value["output_digest"],
            )
            previous_state = BrokerReceiptState(previous_result["state"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BrokerIntegrityError("transition command bytes are malformed") from exc
        if (
            command.expected_version != sequence - 1
            or command.target not in _ALLOWED_TRANSITIONS.get(previous_state, frozenset())
            or (
                command.target is not BrokerReceiptState.DISPATCH_POSSIBLE
                and (command.attempt_id is not None or command.dispatch_intent is not None)
            )
        ):
            raise BrokerIntegrityError("historical transition authority is invalid")
        send_marker = bool(previous_result["send_marker"]) or (
            command.target is BrokerReceiptState.DISPATCH_POSSIBLE
        )
        attempt_id = (
            command.attempt_id
            if command.target is BrokerReceiptState.DISPATCH_POSSIBLE
            else previous_result["attempt_id"]
        )
        dispatch_intent = (
            command.dispatch_intent
            if command.target is BrokerReceiptState.DISPATCH_POSSIBLE
            else previous_result.get("dispatch_intent")
        )
        provider_charge = (
            command.charge_cents if command.target is BrokerReceiptState.CHARGED else None
        )
        client_charge = (
            min(provider_charge, authorization.maximum_charge_cents)
            if provider_charge is not None
            else command.charge_cents
        )
        broker_loss = provider_charge - client_charge if provider_charge is not None else None
        expected = {
            "attempt_id": attempt_id,
            "dispatch_intent": dispatch_intent,
            "broker_loss_cents": broker_loss,
            "charge_cents": client_charge,
            "evidence_digest": command.evidence_digest,
            "operation_id": operation_id,
            "output_digest": command.output_digest,
            "provider_charge_cents": provider_charge,
            "send_marker": send_marker,
            "state": command.target.value,
            "updated_at": recorded_at,
            "version": sequence,
        }
        if legacy_result:
            if dispatch_intent is not None:
                raise BrokerIntegrityError("legacy result cannot contain replay authority")
            del expected["dispatch_intent"]
        if command.target is BrokerReceiptState.NOT_FOUND and (
            _parse_timestamp(recorded_at) >= _parse_timestamp(authorization.expires_at)
            or bool(previous_result["send_marker"])
        ):
            raise BrokerIntegrityError("historical not-found authority is invalid")
        return expected

    def _append_event(
        self,
        db: sqlite3.Connection,
        *,
        operation_id: str,
        sequence: int,
        from_state: BrokerReceiptState | None,
        to_state: BrokerReceiptState,
        version: int,
        command_id: str,
        command_json: str,
        command_digest: str,
        recorded_at: str,
        previous_hash: str | None,
        result_row: sqlite3.Row,
    ) -> None:
        from_value = from_state.value if from_state is not None else None
        if hashlib.sha256(command_json.encode("ascii")).hexdigest() != command_digest:
            raise BrokerIntegrityError("command bytes differ from command digest")
        result_json = _result_json(result_row)
        result_digest = hashlib.sha256(result_json.encode("ascii")).hexdigest()
        event_hash = _event_hash(
            operation_id=operation_id,
            sequence=sequence,
            from_state=from_value,
            to_state=to_state.value,
            version=version,
            command_id=command_id,
            command_digest=command_digest,
            result_digest=result_digest,
            recorded_at=recorded_at,
            previous_hash=previous_hash,
        )
        db.execute(
            "INSERT INTO broker_audit VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                operation_id,
                sequence,
                from_value,
                to_state.value,
                version,
                command_id,
                command_digest,
                result_json,
                result_digest,
                recorded_at,
                previous_hash,
                event_hash,
            ),
        )

    def _check_schema(self, db: sqlite3.Connection, *, full: bool) -> None:
        row = db.execute("SELECT version FROM broker_schema WHERE singleton=1").fetchone()
        if row is None or row[0] != SCHEMA_VERSION:
            raise BrokerIntegrityError("unsupported broker ledger schema")
        actual_triggers = {
            row[0]: _normalized_sql(row[1])
            for row in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'broker_%'"
            )
        }
        expected_triggers = {
            name: _normalized_sql(sql) for name, sql in _EXPECTED_TRIGGER_SQL.items()
        }
        if actual_triggers != expected_triggers:
            raise BrokerIntegrityError("broker immutability trigger definitions differ")
        if full:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise BrokerIntegrityError("SQLite integrity check failed")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise BrokerIntegrityError("broker ledger contains orphaned authority")

    def _connect(self, *, create: bool) -> sqlite3.Connection:
        if not create and not self._path.is_file():
            raise BrokerUnavailable("primary broker database does not exist")
        mode = "rwc" if create else "rw"
        try:
            connection = sqlite3.connect(
                f"file:{self._path}?mode={mode}",
                uri=True,
                timeout=self._lock_timeout,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={int(self._lock_timeout * 1000)}")
            return connection
        except (OSError, sqlite3.Error) as exc:
            raise BrokerUnavailable("primary broker database is unavailable") from exc

    @contextlib.contextmanager
    def _serialized(self, tenant_id: str, idempotency_key: str) -> Iterator[sqlite3.Connection]:
        with self._key_lock(tenant_id, idempotency_key):
            connection: sqlite3.Connection | None = None
            try:
                connection = self._connect(create=False)
                connection.execute("BEGIN IMMEDIATE")
                self._check_schema(connection, full=False)
                yield connection
                connection.commit()
            except BrokerLedgerError:
                if connection is not None:
                    connection.rollback()
                raise
            except (OSError, OverflowError, sqlite3.Error, ValueError, TypeError) as exc:
                if connection is not None:
                    connection.rollback()
                raise BrokerUnavailable("primary broker transaction failed") from exc
            finally:
                if connection is not None:
                    connection.close()

    @contextlib.contextmanager
    def _key_lock(self, tenant_id: str, idempotency_key: str) -> Iterator[None]:
        identity = hashlib.sha256(f"{tenant_id}\0{idempotency_key}".encode("ascii")).hexdigest()
        lock_path = self._lock_dir / f"{identity}.lock"
        try:
            self._lock_dir.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise BrokerUnavailable("tenant/key lock authority is unavailable") from exc
        deadline = time.monotonic() + self._lock_timeout
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise BrokerUnavailable("tenant/key serialization timed out") from None
                    time.sleep(min(0.01, self._lock_timeout / 10))
                except OSError as exc:
                    raise BrokerUnavailable("tenant/key lock authority is unavailable") from exc
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


__all__ = [
    "BrokerConflict",
    "BrokerDispatchIntent",
    "BrokerIntegrityError",
    "BrokerLedgerError",
    "BrokerLookup",
    "BrokerOperationSnapshot",
    "BrokerTransition",
    "BrokerTransitionRefused",
    "BrokerUnavailable",
    "LookupDisposition",
    "PrimaryBrokerLedger",
    "provider_idempotency_token",
]
