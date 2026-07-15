"""Durable authorization ledger for cascade research.

The ledger bounds what Antiek authorizes, not what a provider may misbill.
Ceiling, authorized, and held values are constrained integer cents. Observed
provider spend is canonical decimal text so evidence remains exact even after
the cumulative total exceeds SQLite's signed-integer range.

Every mutation opens a fresh SQLite connection and starts ``BEGIN IMMEDIATE``.
The conditional run update in :meth:`ResearchSpendLedger.reserve_paid` is the
single reservation authority. No Python lock participates in correctness.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

__all__ = [
    "BindingConflict",
    "default_research_spend_db_path",
    "IdempotencyConflict",
    "InvalidTransition",
    "LedgerIntegrityError",
    "PaidHoldIntent",
    "PaidHoldSnapshot",
    "PaidHoldState",
    "RecoveryItem",
    "ResearchSpendLedger",
    "RunBinding",
    "RunNotFound",
    "RunSnapshot",
    "RunStatus",
    "SpendCeilingExceeded",
    "SpendEvent",
    "ZeroCostAttemptSnapshot",
    "ZeroCostIntent",
    "ZeroCostState",
    "ZeroReplayClass",
]

APPLICATION_ID: Final = 0x52535044  # RSPD
SCHEMA_VERSION: Final = 2
MAX_AUTHORITY_CENTS: Final = (1 << 62) - 1
MAX_ACTUAL_CENTS: Final = (1 << 63) - 1
BUSY_TIMEOUT_MS: Final = 30_000

JsonScalar = str | int | bool | None
FailureInjector = Callable[[str], None]


def default_research_spend_db_path() -> Path:
    """Resolve the authority ledger shared by research launch and execution."""
    configured = os.environ.get("ANTIEK_RESEARCH_SPEND_DB")
    if configured:
        return Path(configured).expanduser()
    from substrate.graph import default_db_path

    graph = Path(default_db_path())
    return graph.with_name(f"{graph.name}.research-spend.sqlite3")


class RunStatus(StrEnum):
    ACTIVE = "active"
    CEILING_BREACHED = "ceiling_breached"
    CLOSED_UNRESOLVED = "closed_unresolved"
    CLOSED_RECONCILED = "closed_reconciled"


class PaidHoldState(StrEnum):
    RESERVED = "reserved"
    DISPATCH_POSSIBLE = "dispatch_possible"
    UNKNOWN = "unknown"
    SETTLED = "settled"
    RELEASED = "released"


class ZeroCostState(StrEnum):
    PREPARED = "prepared"
    COMPLETED = "completed"
    FAILED = "failed"


class ZeroReplayClass(StrEnum):
    PURE = "pure"
    CHECKPOINT_RESUMABLE = "checkpoint_resumable"


class LedgerIntegrityError(RuntimeError):
    """Persisted data or schema does not satisfy the ledger contract."""


class RunNotFound(RuntimeError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Research spend run {run_id!r} does not exist")


class BindingConflict(RuntimeError):
    """A run or operation identity disagrees with persisted authority."""


class IdempotencyConflict(RuntimeError):
    """A command or operation key was replayed with changed intent."""


class InvalidTransition(RuntimeError):
    def __init__(self, entity_id: str, state: str, operation: str) -> None:
        self.entity_id = entity_id
        self.state = state
        self.operation = operation
        super().__init__(f"{entity_id!r} in state {state!r} cannot {operation}")


class SpendCeilingExceeded(RuntimeError):
    def __init__(self, run_id: str, requested_cents: int, available_cents: int) -> None:
        self.run_id = run_id
        self.requested_cents = requested_cents
        self.available_cents = available_cents
        super().__init__(
            f"Run {run_id!r} requested {requested_cents} cents with "
            f"{available_cents} cents available"
        )


def _required_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _bounded_int(name: str, value: int, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    owner_id: str
    session_id: str
    plan_digest: str
    approval_revision: int
    currency: str = "USD"
    mode: str = "hard_ceiling"

    def __post_init__(self) -> None:
        for name in ("run_id", "owner_id", "session_id", "plan_digest"):
            _required_text(name, cast(str, getattr(self, name)))
        _bounded_int(
            "approval_revision",
            self.approval_revision,
            minimum=0,
            maximum=MAX_AUTHORITY_CENTS,
        )
        if self.currency != "USD":
            raise ValueError("research hard-ceiling runs are USD-only")
        if self.mode != "hard_ceiling":
            raise ValueError("research spend ledger only accepts hard_ceiling mode")


@dataclass(frozen=True)
class PaidHoldIntent:
    reservation_key: str
    seam_id: str
    provider: str
    model: str
    operation: str
    operation_digest: str
    projection_digest: str
    rate_snapshot: str
    provider_idempotency_key: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _required_text(name, cast(str, getattr(self, name)))


@dataclass(frozen=True)
class ZeroCostIntent:
    attempt_key: str
    seam_id: str
    operation: str
    operation_digest: str
    replay_class: ZeroReplayClass

    def __post_init__(self) -> None:
        for name in ("attempt_key", "seam_id", "operation", "operation_digest"):
            _required_text(name, cast(str, getattr(self, name)))
        if not isinstance(self.replay_class, ZeroReplayClass):
            raise TypeError("replay_class must be ZeroReplayClass")


@dataclass(frozen=True)
class RunSnapshot:
    binding: RunBinding
    ceiling_cents: int
    authorized_spent_cents: int
    observed_provider_spend_cents: int
    held_cents: int
    status: RunStatus
    ceiling_breached: bool
    created_at: str
    updated_at: str
    closed_at: str | None

    @property
    def available_cents(self) -> int:
        return self.ceiling_cents - self.authorized_spent_cents - self.held_cents


@dataclass(frozen=True)
class PaidHoldSnapshot:
    hold_id: str
    run_id: str
    intent: PaidHoldIntent
    projected_max_cents: int
    state: PaidHoldState
    actual_cents: int | None
    authorized_applied_cents: int | None
    dispatch_possible_at: str | None
    resolved_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ZeroCostAttemptSnapshot:
    attempt_id: str
    run_id: str
    intent: ZeroCostIntent
    state: ZeroCostState
    outcome_digest: str | None
    resolved_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SpendEvent:
    event_seq: int
    event_id: str
    run_id: str
    hold_id: str | None
    attempt_id: str | None
    command_key: str
    event_kind: str
    authorized_delta_cents: int
    held_delta_cents: int
    observed_delta_cents: int
    post_authorized_cents: int
    post_held_cents: int
    post_observed_cents: int
    evidence_json: str
    created_at: str


@dataclass(frozen=True)
class RecoveryItem:
    item_id: str
    kind: str
    state: str
    action: str


_DDL: Final[tuple[str, ...]] = (
    """
    CREATE TABLE research_spend_runs (
        run_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        plan_digest TEXT NOT NULL,
        approval_revision INTEGER NOT NULL CHECK (approval_revision >= 0),
        currency TEXT NOT NULL CHECK (currency = 'USD'),
        mode TEXT NOT NULL CHECK (mode = 'hard_ceiling'),
        ceiling_cents INTEGER NOT NULL
            CHECK (ceiling_cents BETWEEN 1 AND 4611686018427387903),
        authorized_spent_cents INTEGER NOT NULL DEFAULT 0
            CHECK (authorized_spent_cents BETWEEN 0 AND 4611686018427387903),
        observed_provider_spend_dec TEXT NOT NULL DEFAULT '0'
            CHECK (
                observed_provider_spend_dec = '0'
                OR (
                    length(observed_provider_spend_dec) > 0
                    AND observed_provider_spend_dec NOT GLOB '*[^0-9]*'
                    AND substr(observed_provider_spend_dec, 1, 1) BETWEEN '1' AND '9'
                )
            ),
        held_cents INTEGER NOT NULL DEFAULT 0
            CHECK (held_cents BETWEEN 0 AND 4611686018427387903),
        status TEXT NOT NULL CHECK (
            status IN ('active', 'ceiling_breached',
                       'closed_unresolved', 'closed_reconciled')
        ),
        ceiling_breached INTEGER NOT NULL DEFAULT 0
            CHECK (ceiling_breached IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        closed_at TEXT,
        CHECK (held_cents <= ceiling_cents - authorized_spent_cents),
        CHECK (
            (status = 'active' AND ceiling_breached = 0 AND closed_at IS NULL)
            OR (status = 'ceiling_breached' AND ceiling_breached = 1
                AND closed_at IS NULL)
            OR (status IN ('closed_unresolved', 'closed_reconciled')
                AND closed_at IS NOT NULL)
        )
    ) STRICT
    """,
    """
    CREATE TABLE research_spend_holds (
        hold_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES research_spend_runs(run_id),
        reservation_key TEXT NOT NULL,
        intent_json TEXT NOT NULL,
        intent_sha256 TEXT NOT NULL,
        seam_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        operation TEXT NOT NULL,
        operation_digest TEXT NOT NULL,
        projection_digest TEXT NOT NULL,
        rate_snapshot TEXT NOT NULL,
        provider_idempotency_key TEXT NOT NULL,
        projected_max_cents INTEGER NOT NULL
            CHECK (projected_max_cents BETWEEN 1 AND 4611686018427387903),
        state TEXT NOT NULL CHECK (
            state IN ('reserved', 'dispatch_possible', 'unknown',
                      'settled', 'released')
        ),
        actual_cents INTEGER CHECK (
            actual_cents IS NULL OR actual_cents BETWEEN 0 AND 9223372036854775807
        ),
        authorized_applied_cents INTEGER CHECK (
            authorized_applied_cents IS NULL
            OR authorized_applied_cents BETWEEN 0 AND 4611686018427387903
        ),
        resolution_key TEXT,
        resolution_intent_json TEXT,
        resolution_intent_sha256 TEXT,
        resolution_evidence_json TEXT,
        created_at TEXT NOT NULL,
        dispatch_possible_at TEXT,
        resolved_at TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE (run_id, reservation_key),
        UNIQUE (provider, provider_idempotency_key),
        CHECK (
            (state = 'reserved' AND dispatch_possible_at IS NULL
             AND resolved_at IS NULL AND resolution_key IS NULL)
            OR (state IN ('dispatch_possible', 'unknown')
                AND dispatch_possible_at IS NOT NULL AND resolved_at IS NULL
                AND resolution_key IS NULL)
            OR (state = 'settled' AND dispatch_possible_at IS NOT NULL
                AND resolved_at IS NOT NULL AND actual_cents IS NOT NULL
                AND authorized_applied_cents IS NOT NULL
                AND resolution_key IS NOT NULL
                AND resolution_intent_json IS NOT NULL
                AND resolution_intent_sha256 IS NOT NULL
                AND resolution_evidence_json IS NOT NULL)
            OR (state = 'released' AND resolved_at IS NOT NULL
                AND actual_cents IS NULL AND authorized_applied_cents = 0
                AND resolution_key IS NOT NULL
                AND resolution_intent_json IS NOT NULL
                AND resolution_intent_sha256 IS NOT NULL
                AND resolution_evidence_json IS NOT NULL)
        )
    ) STRICT
    """,
    """
    CREATE TABLE research_spend_zero_attempts (
        attempt_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES research_spend_runs(run_id),
        attempt_key TEXT NOT NULL,
        intent_json TEXT NOT NULL,
        intent_sha256 TEXT NOT NULL,
        seam_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        operation_digest TEXT NOT NULL,
        replay_class TEXT NOT NULL CHECK (
            replay_class IN ('pure', 'checkpoint_resumable')
        ),
        state TEXT NOT NULL CHECK (state IN ('prepared', 'completed', 'failed')),
        resolution_key TEXT,
        resolution_intent_json TEXT,
        resolution_intent_sha256 TEXT,
        outcome_digest TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE (run_id, attempt_key),
        CHECK (
            (state = 'prepared' AND resolution_key IS NULL
             AND outcome_digest IS NULL AND resolved_at IS NULL)
            OR (state IN ('completed', 'failed')
                AND resolution_key IS NOT NULL
                AND resolution_intent_json IS NOT NULL
                AND resolution_intent_sha256 IS NOT NULL
                AND outcome_digest IS NOT NULL AND resolved_at IS NOT NULL)
        )
    ) STRICT
    """,
    """
    CREATE TABLE research_spend_commands (
        command_key TEXT PRIMARY KEY,
        command_kind TEXT NOT NULL,
        scope_id TEXT NOT NULL,
        intent_json TEXT NOT NULL,
        intent_sha256 TEXT NOT NULL,
        result_json TEXT NOT NULL,
        result_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE research_spend_events (
        event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL REFERENCES research_spend_runs(run_id),
        hold_id TEXT REFERENCES research_spend_holds(hold_id),
        attempt_id TEXT REFERENCES research_spend_zero_attempts(attempt_id),
        command_key TEXT NOT NULL REFERENCES research_spend_commands(command_key),
        event_kind TEXT NOT NULL,
        authorized_delta_cents INTEGER NOT NULL,
        held_delta_cents INTEGER NOT NULL,
        observed_delta_dec TEXT NOT NULL CHECK (
            observed_delta_dec = '0'
            OR (length(observed_delta_dec) > 0
                AND observed_delta_dec NOT GLOB '*[^0-9]*'
                AND substr(observed_delta_dec, 1, 1) BETWEEN '1' AND '9')
        ),
        post_authorized_cents INTEGER NOT NULL CHECK (post_authorized_cents >= 0),
        post_held_cents INTEGER NOT NULL CHECK (post_held_cents >= 0),
        post_observed_dec TEXT NOT NULL CHECK (
            post_observed_dec = '0'
            OR (length(post_observed_dec) > 0
                AND post_observed_dec NOT GLOB '*[^0-9]*'
                AND substr(post_observed_dec, 1, 1) BETWEEN '1' AND '9')
        ),
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK ((hold_id IS NULL) OR (attempt_id IS NULL))
    ) STRICT
    """,
    "CREATE INDEX research_spend_holds_recovery_idx "
    "ON research_spend_holds(run_id, state)",
    "CREATE INDEX research_spend_zero_recovery_idx "
    "ON research_spend_zero_attempts(run_id, state)",
    "CREATE INDEX research_spend_events_run_idx "
    "ON research_spend_events(run_id, event_seq)",
    """
    CREATE TRIGGER research_spend_events_no_update
    BEFORE UPDATE ON research_spend_events
    BEGIN SELECT RAISE(ABORT, 'research spend events are append-only'); END
    """,
    """
    CREATE TRIGGER research_spend_events_no_delete
    BEFORE DELETE ON research_spend_events
    BEGIN SELECT RAISE(ABORT, 'research spend events are append-only'); END
    """,
    """
    CREATE TRIGGER research_spend_commands_no_update
    BEFORE UPDATE ON research_spend_commands
    BEGIN SELECT RAISE(ABORT, 'research spend commands are immutable'); END
    """,
    """
    CREATE TRIGGER research_spend_commands_no_delete
    BEFORE DELETE ON research_spend_commands
    BEGIN SELECT RAISE(ABORT, 'research spend commands are immutable'); END
    """,
)

_MIGRATIONS: Final[dict[int, tuple[str, ...]]] = {
    1: (
        "ALTER TABLE research_spend_runs ADD COLUMN mode TEXT NOT NULL "
        "DEFAULT 'hard_ceiling' CHECK (mode = 'hard_ceiling')",
    ),
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(payload: Mapping[str, JsonScalar]) -> str:
    normalized: dict[str, JsonScalar] = {}
    for key, value in payload.items():
        _required_text("JSON key", key)
        if isinstance(value, float) or not isinstance(value, (str, int, bool, type(None))):
            raise TypeError("ledger intent values must be JSON scalars without floats")
        normalized[key] = value
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _binding_payload(binding: RunBinding) -> dict[str, JsonScalar]:
    # Mode is enforced by RunBinding and the run-row CHECK. Keep it out of
    # command/hold intent JSON so implicit-hard-mode schema-v1 records replay
    # byte-for-byte after the v2 mode-column migration.
    return {
        "approval_revision": binding.approval_revision,
        "currency": binding.currency,
        "owner_id": binding.owner_id,
        "plan_digest": binding.plan_digest,
        "run_id": binding.run_id,
        "session_id": binding.session_id,
    }


class ResearchSpendLedger:
    """SQLite-backed authority and evidence ledger for research hard mode."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._failure_injector = failure_injector

    def _checkpoint(self, name: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(name)

    def _connect(self, *, initialize: bool = False) -> sqlite3.Connection:
        if initialize:
            Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        elif not Path(self._db_path).expanduser().is_file():
            raise sqlite3.OperationalError("research spend ledger is unavailable")
        connection = sqlite3.connect(
            self._db_path,
            timeout=BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextlib.contextmanager
    def _write(self, operation: str) -> Generator[sqlite3.Connection]:
        connection = self._connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            self._checkpoint(f"{operation}:before_commit")
            connection.execute("COMMIT")
            committed = True
        except BaseException:
            if not committed:
                with contextlib.suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        self._checkpoint(f"{operation}:after_commit")

    def ensure_schema(self) -> None:
        connection = self._connect(initialize=True)
        committed = False
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN IMMEDIATE")
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if application_id not in (0, APPLICATION_ID):
                raise LedgerIntegrityError("database belongs to another application")
            if version > SCHEMA_VERSION:
                raise LedgerIntegrityError(f"unsupported research spend schema {version}")
            if version > 0 and application_id != APPLICATION_ID:
                raise LedgerIntegrityError("research spend schema has no matching application id")
            if version == 0:
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                for index, statement in enumerate(_DDL, start=1):
                    connection.execute(statement)
                    self._checkpoint(f"schema:after_statement:{index}")
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            else:
                while version < SCHEMA_VERSION:
                    migration = _MIGRATIONS.get(version)
                    if migration is None:
                        raise LedgerIntegrityError(
                            f"no migration from research spend schema {version}"
                        )
                    for index, statement in enumerate(migration, start=1):
                        connection.execute(statement)
                        self._checkpoint(f"schema:{version}:after_migration:{index}")
                    version += 1
                    connection.execute(f"PRAGMA user_version = {version}")
            self._checkpoint("schema:before_commit")
            connection.execute("COMMIT")
            committed = True
        except BaseException:
            if not committed:
                with contextlib.suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        self._checkpoint("schema:after_commit")

    def create_or_reopen_run(
        self,
        command_key: str,
        binding: RunBinding,
        ceiling_cents: int,
    ) -> RunSnapshot:
        _required_text("command_key", command_key)
        _bounded_int(
            "ceiling_cents", ceiling_cents, minimum=1, maximum=MAX_AUTHORITY_CENTS
        )
        intent_json = _canonical({**_binding_payload(binding), "ceiling_cents": ceiling_cents})
        with self._write("create_run") as connection:
            replay = self._replay(connection, command_key, "create_run", binding.run_id, intent_json)
            if replay is not None:
                return self._load_run(connection, binding.run_id)
            existing = connection.execute(
                "SELECT * FROM research_spend_runs WHERE run_id = ?", (binding.run_id,)
            ).fetchone()
            if existing is not None:
                snapshot = self._run_from_row(existing)
                if snapshot.binding != binding or snapshot.ceiling_cents != ceiling_cents:
                    raise BindingConflict("run identity or ceiling changed")
            else:
                now = _now()
                connection.execute(
                    "INSERT INTO research_spend_runs "
                    "(run_id, owner_id, session_id, plan_digest, approval_revision, "
                    "currency, mode, ceiling_cents, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'USD', 'hard_ceiling', ?, 'active', ?, ?)",
                    (
                        binding.run_id,
                        binding.owner_id,
                        binding.session_id,
                        binding.plan_digest,
                        binding.approval_revision,
                        ceiling_cents,
                        now,
                        now,
                    ),
                )
                snapshot = self._load_run(connection, binding.run_id)
            result_json = self._run_result(snapshot)
            self._record_command(
                connection, command_key, "create_run", binding.run_id, intent_json, result_json
            )
            self._append_event(
                connection,
                snapshot,
                command_key=command_key,
                event_kind="run_created" if existing is None else "run_reopened",
                evidence_json=intent_json,
            )
            return snapshot

    def reserve_paid(
        self,
        command_key: str,
        binding: RunBinding,
        intent: PaidHoldIntent,
        projected_max_cents: int,
    ) -> PaidHoldSnapshot:
        _required_text("command_key", command_key)
        _bounded_int(
            "projected_max_cents",
            projected_max_cents,
            minimum=1,
            maximum=MAX_AUTHORITY_CENTS,
        )
        intent_json = self._paid_intent_json(binding, intent, projected_max_cents)
        with self._write("reserve_paid") as connection:
            replay = self._replay(
                connection, command_key, "reserve_paid", binding.run_id, intent_json
            )
            if replay is not None:
                return self._load_hold(connection, self._hold_from_result(replay).hold_id)
            run = self._require_binding(connection, binding)
            if run.status is not RunStatus.ACTIVE:
                raise InvalidTransition(binding.run_id, run.status.value, "reserve paid work")
            collision = connection.execute(
                "SELECT intent_json FROM research_spend_holds "
                "WHERE (run_id = ? AND reservation_key = ?) "
                "OR (provider = ? AND provider_idempotency_key = ?)",
                (
                    binding.run_id,
                    intent.reservation_key,
                    intent.provider,
                    intent.provider_idempotency_key,
                ),
            ).fetchone()
            if collision is not None:
                raise IdempotencyConflict("reservation or provider identity already exists")
            now = _now()
            authority = connection.execute(
                "UPDATE research_spend_runs SET held_cents = held_cents + ?, "
                "updated_at = ? WHERE run_id = ? AND owner_id = ? AND session_id = ? "
                "AND plan_digest = ? AND approval_revision = ? AND currency = 'USD' "
                "AND status = 'active' AND ceiling_breached = 0 "
                "AND ? <= ceiling_cents - authorized_spent_cents - held_cents "
                "RETURNING held_cents",
                (
                    projected_max_cents,
                    now,
                    binding.run_id,
                    binding.owner_id,
                    binding.session_id,
                    binding.plan_digest,
                    binding.approval_revision,
                    projected_max_cents,
                ),
            ).fetchone()
            if authority is None:
                current = self._require_binding(connection, binding)
                raise SpendCeilingExceeded(
                    binding.run_id, projected_max_cents, current.available_cents
                )
            self._checkpoint("reserve_paid:after_authority")
            hold_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO research_spend_holds "
                "(hold_id, run_id, reservation_key, intent_json, intent_sha256, "
                "seam_id, provider, model, operation, operation_digest, "
                "projection_digest, rate_snapshot, provider_idempotency_key, "
                "projected_max_cents, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)",
                (
                    hold_id,
                    binding.run_id,
                    intent.reservation_key,
                    intent_json,
                    _sha256(intent_json),
                    intent.seam_id,
                    intent.provider,
                    intent.model,
                    intent.operation,
                    intent.operation_digest,
                    intent.projection_digest,
                    intent.rate_snapshot,
                    intent.provider_idempotency_key,
                    projected_max_cents,
                    now,
                    now,
                ),
            )
            self._checkpoint("reserve_paid:after_hold")
            hold = self._load_hold(connection, hold_id)
            result_json = self._hold_result(hold)
            self._record_command(
                connection, command_key, "reserve_paid", binding.run_id, intent_json, result_json
            )
            self._checkpoint("reserve_paid:after_command")
            run = self._load_run(connection, binding.run_id)
            self._append_event(
                connection,
                run,
                command_key=command_key,
                event_kind="hold_reserved",
                hold_id=hold_id,
                held_delta_cents=projected_max_cents,
                evidence_json=intent_json,
            )
            self._checkpoint("reserve_paid:after_event")
            return hold

    def prepare_zero_cost(
        self,
        command_key: str,
        binding: RunBinding,
        intent: ZeroCostIntent,
    ) -> ZeroCostAttemptSnapshot:
        _required_text("command_key", command_key)
        intent_json = _canonical(
            {
                **_binding_payload(binding),
                "attempt_key": intent.attempt_key,
                "operation": intent.operation,
                "operation_digest": intent.operation_digest,
                "replay_class": intent.replay_class.value,
                "seam_id": intent.seam_id,
            }
        )
        with self._write("prepare_zero") as connection:
            replay = self._replay(
                connection, command_key, "prepare_zero", binding.run_id, intent_json
            )
            if replay is not None:
                return self._load_zero(connection, self._zero_from_result(replay).attempt_id)
            run = self._require_binding(connection, binding)
            if run.status is not RunStatus.ACTIVE:
                raise InvalidTransition(binding.run_id, run.status.value, "prepare local work")
            if connection.execute(
                "SELECT 1 FROM research_spend_zero_attempts "
                "WHERE run_id = ? AND attempt_key = ?",
                (binding.run_id, intent.attempt_key),
            ).fetchone():
                raise IdempotencyConflict("zero-cost attempt identity already exists")
            attempt_id = uuid.uuid4().hex
            now = _now()
            connection.execute(
                "INSERT INTO research_spend_zero_attempts "
                "(attempt_id, run_id, attempt_key, intent_json, intent_sha256, "
                "seam_id, operation, operation_digest, replay_class, state, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "'prepared', ?, ?)",
                (
                    attempt_id,
                    binding.run_id,
                    intent.attempt_key,
                    intent_json,
                    _sha256(intent_json),
                    intent.seam_id,
                    intent.operation,
                    intent.operation_digest,
                    intent.replay_class.value,
                    now,
                    now,
                ),
            )
            attempt = self._load_zero(connection, attempt_id)
            result_json = self._zero_result(attempt)
            self._record_command(
                connection, command_key, "prepare_zero", binding.run_id, intent_json, result_json
            )
            self._append_event(
                connection,
                run,
                command_key=command_key,
                event_kind="zero_prepared",
                attempt_id=attempt_id,
                evidence_json=intent_json,
            )
            return attempt

    def mark_dispatch_possible(
        self, command_key: str, hold_id: str
    ) -> PaidHoldSnapshot:
        _required_text("command_key", command_key)
        _required_text("hold_id", hold_id)
        intent_json = _canonical({"hold_id": hold_id})
        with self._write("mark_dispatch_possible") as connection:
            replay = self._replay(
                connection, command_key, "mark_dispatch_possible", hold_id, intent_json
            )
            if replay is not None:
                return self._load_hold(connection, hold_id)
            hold = self._load_hold(connection, hold_id)
            run = self._load_run(connection, hold.run_id)
            if hold.state is not PaidHoldState.RESERVED:
                raise InvalidTransition(hold_id, hold.state.value, "mark dispatch possible")
            if run.status is not RunStatus.ACTIVE:
                raise InvalidTransition(run.binding.run_id, run.status.value, "dispatch")
            now = _now()
            updated = connection.execute(
                "UPDATE research_spend_holds SET state = 'dispatch_possible', "
                "dispatch_possible_at = ?, updated_at = ? "
                "WHERE hold_id = ? AND state = 'reserved' RETURNING hold_id",
                (now, now, hold_id),
            ).fetchone()
            if updated is None:
                raise LedgerIntegrityError("dispatch transition lost its reserved hold")
            hold = self._load_hold(connection, hold_id)
            result_json = self._hold_result(hold)
            self._record_command(
                connection,
                command_key,
                "mark_dispatch_possible",
                hold_id,
                intent_json,
                result_json,
            )
            self._checkpoint("mark_dispatch_possible:after_command")
            self._append_event(
                connection,
                run,
                command_key=command_key,
                event_kind="dispatch_possible",
                hold_id=hold_id,
                evidence_json=intent_json,
            )
            self._checkpoint("mark_dispatch_possible:after_event")
            return hold

    def mark_unknown(
        self,
        command_key: str,
        hold_id: str,
        evidence: Mapping[str, JsonScalar],
    ) -> PaidHoldSnapshot:
        evidence_json = _canonical(evidence)
        if evidence_json == "{}":
            raise ValueError("unknown outcome requires evidence")
        intent_json = _canonical({"evidence_sha256": _sha256(evidence_json), "hold_id": hold_id})
        with self._write("mark_unknown") as connection:
            replay = self._replay(connection, command_key, "mark_unknown", hold_id, intent_json)
            if replay is not None:
                return self._load_hold(connection, hold_id)
            hold = self._load_hold(connection, hold_id)
            if hold.state is not PaidHoldState.DISPATCH_POSSIBLE:
                raise InvalidTransition(hold_id, hold.state.value, "mark unknown")
            now = _now()
            updated = connection.execute(
                "UPDATE research_spend_holds SET state = 'unknown', updated_at = ? "
                "WHERE hold_id = ? AND state = 'dispatch_possible' RETURNING hold_id",
                (now, hold_id),
            ).fetchone()
            if updated is None:
                raise LedgerIntegrityError("unknown transition lost its dispatched hold")
            hold = self._load_hold(connection, hold_id)
            result_json = self._hold_result(hold)
            self._record_command(
                connection, command_key, "mark_unknown", hold_id, intent_json, result_json
            )
            self._append_event(
                connection,
                self._load_run(connection, hold.run_id),
                command_key=command_key,
                event_kind="hold_unknown",
                hold_id=hold_id,
                evidence_json=evidence_json,
            )
            return hold

    def settle(
        self,
        command_key: str,
        hold_id: str,
        actual_cents: int,
        evidence: Mapping[str, JsonScalar],
    ) -> RunSnapshot:
        _bounded_int(
            "actual_cents", actual_cents, minimum=0, maximum=MAX_ACTUAL_CENTS
        )
        evidence_json = _canonical(evidence)
        if evidence_json == "{}":
            raise ValueError("settlement requires authoritative provider evidence")
        intent_json = _canonical(
            {
                "actual_cents": actual_cents,
                "evidence_sha256": _sha256(evidence_json),
                "hold_id": hold_id,
            }
        )
        with self._write("settle") as connection:
            replay = self._replay(connection, command_key, "settle", hold_id, intent_json)
            if replay is not None:
                return self._load_run(connection, self._load_hold(connection, hold_id).run_id)
            hold = self._load_hold(connection, hold_id)
            if hold.state not in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
                raise InvalidTransition(hold_id, hold.state.value, "settle")
            run = self._load_run(connection, hold.run_id)
            authorized_delta = min(actual_cents, hold.projected_max_cents)
            observed = run.observed_provider_spend_cents + actual_cents
            breach = actual_cents > hold.projected_max_cents
            now = _now()
            next_status = run.status
            if breach and run.status is RunStatus.ACTIVE:
                next_status = RunStatus.CEILING_BREACHED
            updated_run = connection.execute(
                "UPDATE research_spend_runs SET "
                "authorized_spent_cents = authorized_spent_cents + ?, "
                "observed_provider_spend_dec = ?, held_cents = held_cents - ?, "
                "status = ?, ceiling_breached = CASE WHEN ? THEN 1 "
                "ELSE ceiling_breached END, updated_at = ? "
                "WHERE run_id = ? AND held_cents >= ? RETURNING run_id",
                (
                    authorized_delta,
                    str(observed),
                    hold.projected_max_cents,
                    next_status.value,
                    breach,
                    now,
                    hold.run_id,
                    hold.projected_max_cents,
                ),
            ).fetchone()
            if updated_run is None:
                raise LedgerIntegrityError("settlement could not consume the persisted hold")
            self._checkpoint("settle:after_run_update")
            updated_hold = connection.execute(
                "UPDATE research_spend_holds SET state = 'settled', actual_cents = ?, "
                "authorized_applied_cents = ?, resolution_key = ?, "
                "resolution_intent_json = ?, resolution_intent_sha256 = ?, "
                "resolution_evidence_json = ?, resolved_at = ?, updated_at = ? "
                "WHERE hold_id = ? AND state IN ('dispatch_possible', 'unknown') "
                "RETURNING hold_id",
                (
                    actual_cents,
                    authorized_delta,
                    command_key,
                    intent_json,
                    _sha256(intent_json),
                    evidence_json,
                    now,
                    now,
                    hold_id,
                ),
            ).fetchone()
            if updated_hold is None:
                raise LedgerIntegrityError("settlement lost its dispatch state")
            self._checkpoint("settle:after_hold_update")
            self._advance_closed_reconciliation(connection, hold.run_id, now)
            run = self._load_run(connection, hold.run_id)
            result_json = self._run_result(run)
            self._record_command(connection, command_key, "settle", hold_id, intent_json, result_json)
            self._checkpoint("settle:after_command")
            self._append_event(
                connection,
                run,
                command_key=command_key,
                event_kind="hold_breached" if breach else "hold_settled",
                hold_id=hold_id,
                authorized_delta_cents=authorized_delta,
                held_delta_cents=-hold.projected_max_cents,
                observed_delta_cents=actual_cents,
                evidence_json=evidence_json,
            )
            self._checkpoint("settle:after_event")
            return run

    def release(
        self,
        command_key: str,
        hold_id: str,
        evidence: Mapping[str, JsonScalar],
        *,
        provider_authoritative: bool = False,
    ) -> RunSnapshot:
        evidence_json = _canonical(evidence)
        if evidence_json == "{}":
            raise ValueError("release requires no-send or provider evidence")
        intent_json = _canonical(
            {
                "evidence_sha256": _sha256(evidence_json),
                "hold_id": hold_id,
                "provider_authoritative": provider_authoritative,
            }
        )
        with self._write("release") as connection:
            replay = self._replay(connection, command_key, "release", hold_id, intent_json)
            if replay is not None:
                return self._load_run(connection, self._load_hold(connection, hold_id).run_id)
            hold = self._load_hold(connection, hold_id)
            if hold.state is PaidHoldState.RESERVED:
                pass
            elif hold.state in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
                if not provider_authoritative:
                    raise InvalidTransition(
                        hold_id, hold.state.value, "release without provider authority"
                    )
            else:
                raise InvalidTransition(hold_id, hold.state.value, "release")
            now = _now()
            updated_run = connection.execute(
                "UPDATE research_spend_runs SET held_cents = held_cents - ?, "
                "updated_at = ? WHERE run_id = ? AND held_cents >= ? RETURNING run_id",
                (hold.projected_max_cents, now, hold.run_id, hold.projected_max_cents),
            ).fetchone()
            if updated_run is None:
                raise LedgerIntegrityError("release could not consume the persisted hold")
            updated_hold = connection.execute(
                "UPDATE research_spend_holds SET state = 'released', "
                "actual_cents = NULL, authorized_applied_cents = 0, "
                "resolution_key = ?, resolution_intent_json = ?, "
                "resolution_intent_sha256 = ?, resolution_evidence_json = ?, "
                "resolved_at = ?, updated_at = ? WHERE hold_id = ? "
                "AND state IN ('reserved', 'dispatch_possible', 'unknown') RETURNING hold_id",
                (
                    command_key,
                    intent_json,
                    _sha256(intent_json),
                    evidence_json,
                    now,
                    now,
                    hold_id,
                ),
            ).fetchone()
            if updated_hold is None:
                raise LedgerIntegrityError("release lost its releasable hold")
            self._checkpoint("release:after_state_updates")
            self._advance_closed_reconciliation(connection, hold.run_id, now)
            run = self._load_run(connection, hold.run_id)
            result_json = self._run_result(run)
            self._record_command(connection, command_key, "release", hold_id, intent_json, result_json)
            self._checkpoint("release:after_command")
            self._append_event(
                connection,
                run,
                command_key=command_key,
                event_kind="hold_released",
                hold_id=hold_id,
                held_delta_cents=-hold.projected_max_cents,
                evidence_json=evidence_json,
            )
            self._checkpoint("release:after_event")
            return run

    def complete_zero_cost(
        self, command_key: str, attempt_id: str, outcome_digest: str
    ) -> ZeroCostAttemptSnapshot:
        return self._resolve_zero(command_key, attempt_id, outcome_digest, success=True)

    def fail_zero_cost(
        self, command_key: str, attempt_id: str, outcome_digest: str
    ) -> ZeroCostAttemptSnapshot:
        return self._resolve_zero(command_key, attempt_id, outcome_digest, success=False)

    def _resolve_zero(
        self,
        command_key: str,
        attempt_id: str,
        outcome_digest: str,
        *,
        success: bool,
    ) -> ZeroCostAttemptSnapshot:
        _required_text("outcome_digest", outcome_digest)
        kind = "complete_zero" if success else "fail_zero"
        intent_json = _canonical(
            {"attempt_id": attempt_id, "outcome_digest": outcome_digest}
        )
        with self._write(kind) as connection:
            replay = self._replay(connection, command_key, kind, attempt_id, intent_json)
            if replay is not None:
                return self._load_zero(connection, attempt_id)
            attempt = self._load_zero(connection, attempt_id)
            if attempt.state is not ZeroCostState.PREPARED:
                raise InvalidTransition(attempt_id, attempt.state.value, kind)
            now = _now()
            state = ZeroCostState.COMPLETED if success else ZeroCostState.FAILED
            updated = connection.execute(
                "UPDATE research_spend_zero_attempts SET state = ?, resolution_key = ?, "
                "resolution_intent_json = ?, resolution_intent_sha256 = ?, "
                "outcome_digest = ?, resolved_at = ?, updated_at = ? "
                "WHERE attempt_id = ? AND state = 'prepared' RETURNING attempt_id",
                (
                    state.value,
                    command_key,
                    intent_json,
                    _sha256(intent_json),
                    outcome_digest,
                    now,
                    now,
                    attempt_id,
                ),
            ).fetchone()
            if updated is None:
                raise LedgerIntegrityError("zero-cost resolution lost its prepared attempt")
            self._checkpoint(f"{kind}:after_state_update")
            attempt = self._load_zero(connection, attempt_id)
            result_json = self._zero_result(attempt)
            self._record_command(connection, command_key, kind, attempt_id, intent_json, result_json)
            self._checkpoint(f"{kind}:after_command")
            self._append_event(
                connection,
                self._load_run(connection, attempt.run_id),
                command_key=command_key,
                event_kind="zero_completed" if success else "zero_failed",
                attempt_id=attempt_id,
                evidence_json=intent_json,
            )
            self._checkpoint(f"{kind}:after_event")
            return attempt

    def close_execution(
        self, command_key: str, run_id: str, reason: str
    ) -> RunSnapshot:
        _required_text("reason", reason)
        intent_json = _canonical({"reason": reason, "run_id": run_id})
        with self._write("close_execution") as connection:
            replay = self._replay(
                connection, command_key, "close_execution", run_id, intent_json
            )
            if replay is not None:
                return self._load_run(connection, run_id)
            run = self._load_run(connection, run_id)
            if run.status in (RunStatus.CLOSED_UNRESOLVED, RunStatus.CLOSED_RECONCILED):
                raise InvalidTransition(run_id, run.status.value, "close execution")
            now = _now()
            reserved = connection.execute(
                "SELECT hold_id, projected_max_cents FROM research_spend_holds "
                "WHERE run_id = ? AND state = 'reserved' ORDER BY hold_id",
                (run_id,),
            ).fetchall()
            released_total = sum(int(row["projected_max_cents"]) for row in reserved)
            for row in reserved:
                evidence_json = _canonical({"kind": "execution_closed", "reason": reason})
                resolution_intent = _canonical(
                    {"evidence_sha256": _sha256(evidence_json), "hold_id": str(row["hold_id"])}
                )
                connection.execute(
                    "UPDATE research_spend_holds SET state = 'released', "
                    "authorized_applied_cents = 0, resolution_key = ?, "
                    "resolution_intent_json = ?, resolution_intent_sha256 = ?, "
                    "resolution_evidence_json = ?, resolved_at = ?, updated_at = ? "
                    "WHERE hold_id = ? AND state = 'reserved'",
                    (
                        command_key,
                        resolution_intent,
                        _sha256(resolution_intent),
                        evidence_json,
                        now,
                        now,
                        row["hold_id"],
                    ),
                )
            prepared = connection.execute(
                "SELECT attempt_id FROM research_spend_zero_attempts "
                "WHERE run_id = ? AND state = 'prepared' ORDER BY attempt_id",
                (run_id,),
            ).fetchall()
            for row in prepared:
                attempt_intent = _canonical(
                    {"attempt_id": str(row["attempt_id"]), "outcome_digest": "execution_closed"}
                )
                connection.execute(
                    "UPDATE research_spend_zero_attempts SET state = 'failed', "
                    "resolution_key = ?, resolution_intent_json = ?, "
                    "resolution_intent_sha256 = ?, outcome_digest = 'execution_closed', "
                    "resolved_at = ?, updated_at = ? WHERE attempt_id = ?",
                    (
                        command_key,
                        attempt_intent,
                        _sha256(attempt_intent),
                        now,
                        now,
                        row["attempt_id"],
                    ),
                )
            unresolved = int(
                connection.execute(
                    "SELECT COUNT(*) FROM research_spend_holds WHERE run_id = ? "
                    "AND state IN ('dispatch_possible', 'unknown')",
                    (run_id,),
                ).fetchone()[0]
            )
            status = (
                RunStatus.CLOSED_UNRESOLVED
                if unresolved
                else RunStatus.CLOSED_RECONCILED
            )
            updated_run = connection.execute(
                "UPDATE research_spend_runs SET held_cents = held_cents - ?, "
                "status = ?, closed_at = ?, updated_at = ? WHERE run_id = ? "
                "AND held_cents >= ? RETURNING run_id",
                (released_total, status.value, now, now, run_id, released_total),
            ).fetchone()
            if updated_run is None:
                raise LedgerIntegrityError("close could not release its reserved total")
            self._checkpoint("close_execution:after_state_updates")
            run = self._load_run(connection, run_id)
            result_json = self._run_result(run)
            self._record_command(
                connection, command_key, "close_execution", run_id, intent_json, result_json
            )
            self._checkpoint("close_execution:after_command")
            event_run = replace(run, held_cents=run.held_cents + released_total)
            for row in reserved:
                event_run = replace(
                    event_run,
                    held_cents=event_run.held_cents - int(row["projected_max_cents"]),
                )
                self._append_event(
                    connection,
                    event_run,
                    command_key=command_key,
                    event_kind="hold_released_on_close",
                    hold_id=str(row["hold_id"]),
                    held_delta_cents=-int(row["projected_max_cents"]),
                    evidence_json=intent_json,
                )
            for row in prepared:
                self._append_event(
                    connection,
                    run,
                    command_key=command_key,
                    event_kind="zero_failed_on_close",
                    attempt_id=str(row["attempt_id"]),
                    evidence_json=intent_json,
                )
            self._append_event(
                connection,
                run,
                command_key=command_key,
                event_kind="execution_closed",
                evidence_json=intent_json,
            )
            self._checkpoint("close_execution:after_events")
            return run

    def balance(self, run_id: str) -> RunSnapshot:
        connection = self._connect()
        try:
            return self._load_run(connection, run_id)
        finally:
            connection.close()

    def balance_for_session(self, owner_id: str, session_id: str) -> RunSnapshot | None:
        """Return the hard-ceiling run visible to one owner and session.

        Session status and recovery APIs must not accept a caller-supplied run id: doing
        so would turn the opaque ledger identity into a cross-owner lookup capability.
        The binding is unique by construction, but fail closed if corrupted state ever
        contains more than one match.
        """
        _required_text("owner_id", owner_id)
        _required_text("session_id", session_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT run_id FROM research_spend_runs "
                "WHERE owner_id = ? AND session_id = ? ORDER BY run_id",
                (owner_id, session_id),
            ).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise LedgerIntegrityError(
                    "multiple hard-ceiling runs share an owner/session binding"
                )
            return self._load_run(connection, str(rows[0]["run_id"]))
        finally:
            connection.close()

    def owner_for_session(self, session_id: str) -> str | None:
        """Resolve a hard-ceiling session owner for route-level access control."""
        _required_text("session_id", session_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT DISTINCT owner_id FROM research_spend_runs WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise LedgerIntegrityError(
                    "hard-ceiling session is bound to multiple owners"
                )
            return str(rows[0]["owner_id"])
        finally:
            connection.close()

    def hold(self, hold_id: str) -> PaidHoldSnapshot:
        connection = self._connect()
        try:
            return self._load_hold(connection, hold_id)
        finally:
            connection.close()

    def zero_attempt(self, attempt_id: str) -> ZeroCostAttemptSnapshot:
        connection = self._connect()
        try:
            return self._load_zero(connection, attempt_id)
        finally:
            connection.close()

    def zero_attempt_for_key(
        self, run_id: str, attempt_key: str
    ) -> ZeroCostAttemptSnapshot | None:
        """Return the durable receipt for one logical zero-cost operation."""
        _required_text("run_id", run_id)
        _required_text("attempt_key", attempt_key)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT attempt_id FROM research_spend_zero_attempts "
                "WHERE run_id = ? AND attempt_key = ?",
                (run_id, attempt_key),
            ).fetchone()
            if row is None:
                return None
            return self._load_zero(connection, str(row["attempt_id"]))
        finally:
            connection.close()

    def events(self, run_id: str) -> tuple[SpendEvent, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM research_spend_events WHERE run_id = ? ORDER BY event_seq",
                (run_id,),
            ).fetchall()
            return tuple(self._event_from_row(row) for row in rows)
        finally:
            connection.close()

    def recovery_work(self, run_id: str) -> tuple[RecoveryItem, ...]:
        connection = self._connect()
        try:
            paid = connection.execute(
                "SELECT hold_id, state FROM research_spend_holds WHERE run_id = ? "
                "AND state IN ('reserved', 'dispatch_possible', 'unknown') ORDER BY hold_id",
                (run_id,),
            ).fetchall()
            zero = connection.execute(
                "SELECT attempt_id, state FROM research_spend_zero_attempts "
                "WHERE run_id = ? AND state = 'prepared' ORDER BY attempt_id",
                (run_id,),
            ).fetchall()
            items = [
                RecoveryItem(
                    str(row["hold_id"]),
                    "paid",
                    str(row["state"]),
                    "resume_or_release" if row["state"] == "reserved" else "reconcile_provider",
                )
                for row in paid
            ]
            items.extend(
                RecoveryItem(str(row["attempt_id"]), "zero_local", str(row["state"]), "resume")
                for row in zero
            )
            return tuple(items)
        finally:
            connection.close()

    def integrity_check(self) -> str:
        connection = self._connect()
        try:
            run_ids = connection.execute(
                "SELECT run_id FROM research_spend_runs ORDER BY run_id"
            ).fetchall()
            for row in run_ids:
                self._load_run(connection, str(row["run_id"]))
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            connection.close()

    def _advance_closed_reconciliation(
        self, connection: sqlite3.Connection, run_id: str, now: str
    ) -> None:
        unresolved = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_spend_holds WHERE run_id = ? "
                "AND state IN ('dispatch_possible', 'unknown')",
                (run_id,),
            ).fetchone()[0]
        )
        if unresolved == 0:
            connection.execute(
                "UPDATE research_spend_runs SET status = 'closed_reconciled', "
                "updated_at = ? WHERE run_id = ? AND status = 'closed_unresolved'",
                (now, run_id),
            )

    def _require_binding(
        self, connection: sqlite3.Connection, binding: RunBinding
    ) -> RunSnapshot:
        run = self._load_run(connection, binding.run_id)
        if run.binding != binding:
            raise BindingConflict("owner, session, plan, revision, mode, or currency changed")
        return run

    def _load_run(self, connection: sqlite3.Connection, run_id: str) -> RunSnapshot:
        row = connection.execute(
            "SELECT * FROM research_spend_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        snapshot = self._run_from_row(row)
        unresolved_total = int(
            connection.execute(
                "SELECT COALESCE(SUM(projected_max_cents), 0) "
                "FROM research_spend_holds WHERE run_id = ? "
                "AND state IN ('reserved', 'dispatch_possible', 'unknown')",
                (run_id,),
            ).fetchone()[0]
        )
        if snapshot.held_cents != unresolved_total:
            raise LedgerIntegrityError(
                f"run {run_id!r} held authority disagrees with unresolved holds"
            )
        return snapshot

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> RunSnapshot:
        return RunSnapshot(
            binding=RunBinding(
                run_id=str(row["run_id"]),
                owner_id=str(row["owner_id"]),
                session_id=str(row["session_id"]),
                plan_digest=str(row["plan_digest"]),
                approval_revision=int(row["approval_revision"]),
                currency=str(row["currency"]),
                mode=str(row["mode"]),
            ),
            ceiling_cents=int(row["ceiling_cents"]),
            authorized_spent_cents=int(row["authorized_spent_cents"]),
            observed_provider_spend_cents=int(str(row["observed_provider_spend_dec"])),
            held_cents=int(row["held_cents"]),
            status=RunStatus(str(row["status"])),
            ceiling_breached=bool(row["ceiling_breached"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            closed_at=None if row["closed_at"] is None else str(row["closed_at"]),
        )

    def _load_hold(
        self, connection: sqlite3.Connection, hold_id: str
    ) -> PaidHoldSnapshot:
        row = connection.execute(
            "SELECT * FROM research_spend_holds WHERE hold_id = ?", (hold_id,)
        ).fetchone()
        if row is None:
            raise BindingConflict(f"paid hold {hold_id!r} does not exist")
        payload = cast(dict[str, JsonScalar], json.loads(str(row["intent_json"])))
        intent = PaidHoldIntent(
            reservation_key=str(row["reservation_key"]),
            seam_id=str(row["seam_id"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            operation=str(row["operation"]),
            operation_digest=str(row["operation_digest"]),
            projection_digest=str(row["projection_digest"]),
            rate_snapshot=str(row["rate_snapshot"]),
            provider_idempotency_key=str(row["provider_idempotency_key"]),
        )
        expected = {
            **_binding_payload(self._load_run(connection, str(row["run_id"])).binding),
            "model": intent.model,
            "operation": intent.operation,
            "operation_digest": intent.operation_digest,
            "projected_max_cents": int(row["projected_max_cents"]),
            "projection_digest": intent.projection_digest,
            "provider": intent.provider,
            "provider_idempotency_key": intent.provider_idempotency_key,
            "rate_snapshot": intent.rate_snapshot,
            "reservation_key": intent.reservation_key,
            "seam_id": intent.seam_id,
        }
        intent_json = str(row["intent_json"])
        if payload != expected or str(row["intent_sha256"]) != _sha256(intent_json):
            raise LedgerIntegrityError("paid hold intent does not match columns")
        return PaidHoldSnapshot(
            hold_id=str(row["hold_id"]),
            run_id=str(row["run_id"]),
            intent=intent,
            projected_max_cents=int(row["projected_max_cents"]),
            state=PaidHoldState(str(row["state"])),
            actual_cents=None if row["actual_cents"] is None else int(row["actual_cents"]),
            authorized_applied_cents=(
                None
                if row["authorized_applied_cents"] is None
                else int(row["authorized_applied_cents"])
            ),
            dispatch_possible_at=(
                None
                if row["dispatch_possible_at"] is None
                else str(row["dispatch_possible_at"])
            ),
            resolved_at=None if row["resolved_at"] is None else str(row["resolved_at"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _load_zero(
        self, connection: sqlite3.Connection, attempt_id: str
    ) -> ZeroCostAttemptSnapshot:
        row = connection.execute(
            "SELECT * FROM research_spend_zero_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise BindingConflict(f"zero-cost attempt {attempt_id!r} does not exist")
        intent_json = str(row["intent_json"])
        payload = cast(dict[str, JsonScalar], json.loads(intent_json))
        expected = {
            **_binding_payload(self._load_run(connection, str(row["run_id"])).binding),
            "attempt_key": str(row["attempt_key"]),
            "operation": str(row["operation"]),
            "operation_digest": str(row["operation_digest"]),
            "replay_class": str(row["replay_class"]),
            "seam_id": str(row["seam_id"]),
        }
        if payload != expected or str(row["intent_sha256"]) != _sha256(intent_json):
            raise LedgerIntegrityError("zero-cost intent does not match columns")
        return ZeroCostAttemptSnapshot(
            attempt_id=str(row["attempt_id"]),
            run_id=str(row["run_id"]),
            intent=ZeroCostIntent(
                attempt_key=str(row["attempt_key"]),
                seam_id=str(row["seam_id"]),
                operation=str(row["operation"]),
                operation_digest=str(row["operation_digest"]),
                replay_class=ZeroReplayClass(str(row["replay_class"])),
            ),
            state=ZeroCostState(str(row["state"])),
            outcome_digest=(
                None if row["outcome_digest"] is None else str(row["outcome_digest"])
            ),
            resolved_at=None if row["resolved_at"] is None else str(row["resolved_at"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _paid_intent_json(
        binding: RunBinding, intent: PaidHoldIntent, projected_max_cents: int
    ) -> str:
        return _canonical(
            {
                **_binding_payload(binding),
                "model": intent.model,
                "operation": intent.operation,
                "operation_digest": intent.operation_digest,
                "projected_max_cents": projected_max_cents,
                "projection_digest": intent.projection_digest,
                "provider": intent.provider,
                "provider_idempotency_key": intent.provider_idempotency_key,
                "rate_snapshot": intent.rate_snapshot,
                "reservation_key": intent.reservation_key,
                "seam_id": intent.seam_id,
            }
        )

    @staticmethod
    def _replay(
        connection: sqlite3.Connection,
        command_key: str,
        command_kind: str,
        scope_id: str,
        intent_json: str,
    ) -> str | None:
        _required_text("command_key", command_key)
        row = connection.execute(
            "SELECT command_kind, scope_id, intent_json, intent_sha256, "
            "result_json, result_sha256 "
            "FROM research_spend_commands WHERE command_key = ?",
            (command_key,),
        ).fetchone()
        if row is None:
            return None
        stored_intent = str(row["intent_json"])
        if str(row["intent_sha256"]) != _sha256(stored_intent):
            raise LedgerIntegrityError(f"command {command_key!r} has corrupt intent")
        stored_result = str(row["result_json"])
        if str(row["result_sha256"]) != _sha256(stored_result):
            raise LedgerIntegrityError(f"command {command_key!r} has corrupt result")
        if (
            str(row["command_kind"]),
            str(row["scope_id"]),
            stored_intent,
        ) != (command_kind, scope_id, intent_json):
            raise IdempotencyConflict(f"command {command_key!r} changed intent")
        return stored_result

    @staticmethod
    def _record_command(
        connection: sqlite3.Connection,
        command_key: str,
        command_kind: str,
        scope_id: str,
        intent_json: str,
        result_json: str,
    ) -> None:
        connection.execute(
            "INSERT INTO research_spend_commands "
            "(command_key, command_kind, scope_id, intent_json, intent_sha256, "
            "result_json, result_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                command_key,
                command_kind,
                scope_id,
                intent_json,
                _sha256(intent_json),
                result_json,
                _sha256(result_json),
                _now(),
            ),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        run: RunSnapshot,
        *,
        command_key: str,
        event_kind: str,
        hold_id: str | None = None,
        attempt_id: str | None = None,
        authorized_delta_cents: int = 0,
        held_delta_cents: int = 0,
        observed_delta_cents: int = 0,
        evidence_json: str = "{}",
    ) -> None:
        connection.execute(
            "INSERT INTO research_spend_events "
            "(event_id, run_id, hold_id, attempt_id, command_key, event_kind, "
            "authorized_delta_cents, held_delta_cents, observed_delta_dec, "
            "post_authorized_cents, post_held_cents, post_observed_dec, "
            "evidence_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex,
                run.binding.run_id,
                hold_id,
                attempt_id,
                command_key,
                event_kind,
                authorized_delta_cents,
                held_delta_cents,
                str(observed_delta_cents),
                run.authorized_spent_cents,
                run.held_cents,
                str(run.observed_provider_spend_cents),
                evidence_json,
                _now(),
            ),
        )

    @staticmethod
    def _run_result(run: RunSnapshot) -> str:
        return json.dumps(
            {
                "approval_revision": run.binding.approval_revision,
                "authorized": run.authorized_spent_cents,
                "breached": run.ceiling_breached,
                "ceiling": run.ceiling_cents,
                "closed_at": run.closed_at,
                "created_at": run.created_at,
                "currency": run.binding.currency,
                "mode": run.binding.mode,
                "held": run.held_cents,
                "observed": str(run.observed_provider_spend_cents),
                "owner_id": run.binding.owner_id,
                "plan_digest": run.binding.plan_digest,
                "run_id": run.binding.run_id,
                "session_id": run.binding.session_id,
                "status": run.status.value,
                "updated_at": run.updated_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _run_from_result(result_json: str) -> RunSnapshot:
        value = cast(dict[str, object], json.loads(result_json))
        return RunSnapshot(
            binding=RunBinding(
                run_id=str(value["run_id"]),
                owner_id=str(value["owner_id"]),
                session_id=str(value["session_id"]),
                plan_digest=str(value["plan_digest"]),
                approval_revision=int(cast(int, value["approval_revision"])),
                currency=str(value["currency"]),
                mode=str(value.get("mode", "hard_ceiling")),
            ),
            ceiling_cents=int(cast(int, value["ceiling"])),
            authorized_spent_cents=int(cast(int, value["authorized"])),
            observed_provider_spend_cents=int(str(value["observed"])),
            held_cents=int(cast(int, value["held"])),
            status=RunStatus(str(value["status"])),
            ceiling_breached=bool(value["breached"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            closed_at=None if value["closed_at"] is None else str(value["closed_at"]),
        )

    @staticmethod
    def _hold_result(hold: PaidHoldSnapshot) -> str:
        return json.dumps(
            {
                "actual": hold.actual_cents,
                "authorized_applied": hold.authorized_applied_cents,
                "created_at": hold.created_at,
                "dispatch_possible_at": hold.dispatch_possible_at,
                "hold_id": hold.hold_id,
                "intent": hold.intent.__dict__,
                "projected": hold.projected_max_cents,
                "resolved_at": hold.resolved_at,
                "run_id": hold.run_id,
                "state": hold.state.value,
                "updated_at": hold.updated_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _hold_from_result(result_json: str) -> PaidHoldSnapshot:
        value = cast(dict[str, object], json.loads(result_json))
        intent_value = cast(dict[str, str], value["intent"])
        return PaidHoldSnapshot(
            hold_id=str(value["hold_id"]),
            run_id=str(value["run_id"]),
            intent=PaidHoldIntent(**intent_value),
            projected_max_cents=int(cast(int, value["projected"])),
            state=PaidHoldState(str(value["state"])),
            actual_cents=None if value["actual"] is None else int(cast(int, value["actual"])),
            authorized_applied_cents=(
                None
                if value["authorized_applied"] is None
                else int(cast(int, value["authorized_applied"]))
            ),
            dispatch_possible_at=(
                None
                if value["dispatch_possible_at"] is None
                else str(value["dispatch_possible_at"])
            ),
            resolved_at=(
                None if value["resolved_at"] is None else str(value["resolved_at"])
            ),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
        )

    @staticmethod
    def _zero_result(attempt: ZeroCostAttemptSnapshot) -> str:
        return json.dumps(
            {
                "attempt_id": attempt.attempt_id,
                "created_at": attempt.created_at,
                "intent": {
                    **attempt.intent.__dict__,
                    "replay_class": attempt.intent.replay_class.value,
                },
                "outcome_digest": attempt.outcome_digest,
                "resolved_at": attempt.resolved_at,
                "run_id": attempt.run_id,
                "state": attempt.state.value,
                "updated_at": attempt.updated_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _zero_from_result(result_json: str) -> ZeroCostAttemptSnapshot:
        value = cast(dict[str, object], json.loads(result_json))
        intent_value = cast(dict[str, str], value["intent"])
        return ZeroCostAttemptSnapshot(
            attempt_id=str(value["attempt_id"]),
            run_id=str(value["run_id"]),
            intent=ZeroCostIntent(
                attempt_key=intent_value["attempt_key"],
                seam_id=intent_value["seam_id"],
                operation=intent_value["operation"],
                operation_digest=intent_value["operation_digest"],
                replay_class=ZeroReplayClass(intent_value["replay_class"]),
            ),
            state=ZeroCostState(str(value["state"])),
            outcome_digest=(
                None if value["outcome_digest"] is None else str(value["outcome_digest"])
            ),
            resolved_at=(
                None if value["resolved_at"] is None else str(value["resolved_at"])
            ),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> SpendEvent:
        return SpendEvent(
            event_seq=int(row["event_seq"]),
            event_id=str(row["event_id"]),
            run_id=str(row["run_id"]),
            hold_id=None if row["hold_id"] is None else str(row["hold_id"]),
            attempt_id=None if row["attempt_id"] is None else str(row["attempt_id"]),
            command_key=str(row["command_key"]),
            event_kind=str(row["event_kind"]),
            authorized_delta_cents=int(row["authorized_delta_cents"]),
            held_delta_cents=int(row["held_delta_cents"]),
            observed_delta_cents=int(str(row["observed_delta_dec"])),
            post_authorized_cents=int(row["post_authorized_cents"]),
            post_held_cents=int(row["post_held_cents"]),
            post_observed_cents=int(str(row["post_observed_dec"])),
            evidence_json=str(row["evidence_json"]),
            created_at=str(row["created_at"]),
        )
