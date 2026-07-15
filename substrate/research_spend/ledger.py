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
import re
import sqlite3
import uuid
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from .billing_evidence import (
    BillingAssessment,
    BillingClassification,
    BillingEvidenceKind,
    BillingRefusalReason,
    billing_assessment_id,
    canonical_billing_evidence,
    classify_billing_evidence,
)

__all__ = [
    "BindingConflict",
    "BillingAssessment",
    "BillingClassification",
    "BillingEvidenceKind",
    "BillingRefusalReason",
    "default_research_spend_db_path",
    "IdempotencyConflict",
    "InvalidTransition",
    "LedgerIntegrityError",
    "LaunchExecutionIntent",
    "LaunchExecutionSnapshot",
    "LaunchOperationIntent",
    "LaunchOperationSnapshot",
    "LaunchOperationState",
    "PaidHoldIntent",
    "PaidHoldSnapshot",
    "PaidHoldState",
    "ProviderObservationSnapshot",
    "ProviderSubmissionIntent",
    "ProviderSubmissionSnapshot",
    "ProviderSubmissionState",
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
SCHEMA_VERSION: Final = 5
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


class LaunchOperationState(StrEnum):
    PENDING = "pending"
    BLOCKED_PROVIDER_INELIGIBLE = "blocked_provider_ineligible"
    CLAIMED = "claimed"
    DISPATCH_POSSIBLE = "dispatch_possible"
    UNKNOWN = "unknown"
    SETTLED = "settled"
    SUCCEEDED = "succeeded"
    FAILED_TERMINAL = "failed_terminal"


class ProviderSubmissionState(StrEnum):
    PREPARED = "prepared"
    SUBMIT_POSSIBLE = "submit_possible"
    CREATE_OUTCOME_UNKNOWN = "create_outcome_unknown"
    IDENTITY_BOUND = "identity_bound"
    RUNNING = "running"
    PROVIDER_TERMINAL = "provider_terminal"
    BILLING_PENDING = "billing_pending"
    FAILED_PRE_ACCEPTANCE = "failed_pre_acceptance"
    INTEGRITY_CONFLICT = "integrity_conflict"


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


@dataclass(frozen=True)
class LaunchExecutionIntent:
    execution_id: str
    authority_kind: str
    launch_reservation_id: str
    launch_manifest_digest: str
    prepared_integrity_digest: str
    provider: str
    model: str
    route_digest: str
    pricing_digest: str
    workload_digest: str
    operation_count: int
    request_digest: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "operation_count":
                _bounded_int(name, value, minimum=1, maximum=10_000)
            else:
                _required_text(name, cast(str, value))


@dataclass(frozen=True)
class LaunchOperationIntent:
    operation_id: str
    ordinal: int
    stable_source_id: str
    question: str
    payload_digest: str
    provider: str
    model: str
    logical_operation_id: str
    state: LaunchOperationState
    blocked_reason: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "stable_source_id",
            "question",
            "payload_digest",
            "provider",
            "model",
            "logical_operation_id",
        ):
            _required_text(name, cast(str, getattr(self, name)))
        _bounded_int("ordinal", self.ordinal, minimum=0, maximum=9_999)
        if not isinstance(self.state, LaunchOperationState):
            raise TypeError("state must be LaunchOperationState")
        if (self.state is LaunchOperationState.BLOCKED_PROVIDER_INELIGIBLE) != (
            self.blocked_reason is not None
        ):
            raise ValueError("blocked reason must exactly match blocked state")


@dataclass(frozen=True)
class LaunchOperationSnapshot:
    execution_id: str
    intent: LaunchOperationIntent
    hold_id: str | None
    result_json: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LaunchExecutionSnapshot:
    run_id: str
    owner_id: str
    intent: LaunchExecutionIntent
    operations: tuple[LaunchOperationSnapshot, ...]
    created_at: str

    @property
    def state(self) -> str:
        states = {item.intent.state for item in self.operations}
        if (
            LaunchOperationState.UNKNOWN in states
            or LaunchOperationState.DISPATCH_POSSIBLE in states
        ):
            return "recovery_required"
        if LaunchOperationState.CLAIMED in states or LaunchOperationState.SETTLED in states:
            return "active"
        if states == {LaunchOperationState.BLOCKED_PROVIDER_INELIGIBLE}:
            return "blocked"
        if states <= {LaunchOperationState.SUCCEEDED, LaunchOperationState.FAILED_TERMINAL}:
            return "terminal"
        if LaunchOperationState.PENDING in states:
            return "runnable"
        return "materialized"


@dataclass(frozen=True)
class ProviderSubmissionIntent:
    submission_id: str
    operation_id: str
    provider: str
    model: str
    adapter_contract: str
    account_digest: str
    region: str
    provider_model_id: str
    client_request_token: str
    create_request_json: str
    recovery_strategy: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _required_text(name, cast(str, getattr(self, name)))
        if len(self.client_request_token) != 64 or any(
            char not in "0123456789abcdef" for char in self.client_request_token
        ):
            raise ValueError("client_request_token must be a lowercase SHA-256")
        try:
            parsed = json.loads(self.create_request_json)
        except json.JSONDecodeError as exc:
            raise ValueError("create_request_json must be canonical JSON") from exc

        def validate_scalar_tree(value: object) -> None:
            if value is None or isinstance(value, (str, int, bool)):
                return
            if isinstance(value, list):
                for item in value:
                    validate_scalar_tree(item)
                return
            if isinstance(value, dict) and all(isinstance(key, str) for key in value):
                for item in value.values():
                    validate_scalar_tree(item)
                return
            raise ValueError("create_request_json accepts JSON scalars without floats")

        validate_scalar_tree(parsed)
        if (
            json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            != self.create_request_json
        ):
            raise ValueError("create_request_json must be canonical JSON")


@dataclass(frozen=True)
class ProviderSubmissionSnapshot:
    intent: ProviderSubmissionIntent
    run_id: str
    owner_id: str
    hold_id: str
    state: ProviderSubmissionState
    job_arn: str | None
    attempt_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProviderObservationSnapshot:
    observation_id: str
    submission_id: str
    source: str
    evidence_json: str
    raw_digest: str
    provider_identity: str | None
    provider_status: str | None
    created_at: str


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
    "CREATE INDEX research_spend_holds_recovery_idx ON research_spend_holds(run_id, state)",
    "CREATE INDEX research_spend_zero_recovery_idx ON research_spend_zero_attempts(run_id, state)",
    "CREATE INDEX research_spend_events_run_idx ON research_spend_events(run_id, event_seq)",
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
    2: (
        """
        CREATE TABLE research_launch_executions (
            execution_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE REFERENCES research_spend_runs(run_id),
            owner_id TEXT NOT NULL,
            authority_kind TEXT NOT NULL,
            launch_reservation_id TEXT NOT NULL UNIQUE,
            launch_manifest_digest TEXT NOT NULL,
            prepared_integrity_digest TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            route_digest TEXT NOT NULL,
            pricing_digest TEXT NOT NULL,
            workload_digest TEXT NOT NULL,
            operation_count INTEGER NOT NULL CHECK(operation_count BETWEEN 1 AND 10000),
            request_digest TEXT NOT NULL,
            intent_json TEXT NOT NULL,
            intent_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """,
        """
        CREATE TABLE research_launch_operations (
            operation_id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL REFERENCES research_launch_executions(execution_id),
            ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 9999),
            stable_source_id TEXT NOT NULL,
            question TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            logical_operation_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('pending','blocked_provider_ineligible','claimed',
                'dispatch_possible','unknown','settled','succeeded','failed_terminal')),
            blocked_reason TEXT,
            intent_json TEXT NOT NULL,
            intent_sha256 TEXT NOT NULL,
            hold_id TEXT REFERENCES research_spend_holds(hold_id),
            result_json TEXT,
            result_sha256 TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(execution_id, ordinal), UNIQUE(execution_id, stable_source_id),
            UNIQUE(execution_id, logical_operation_id),
            CHECK((state='blocked_provider_ineligible')=(blocked_reason IS NOT NULL)),
            CHECK((result_json IS NULL)=(result_sha256 IS NULL))
        ) STRICT
        """,
        "CREATE INDEX research_launch_operations_order_idx ON research_launch_operations(execution_id, ordinal)",
        """
        CREATE TRIGGER research_launch_executions_no_update
        BEFORE UPDATE ON research_launch_executions
        BEGIN SELECT RAISE(ABORT, 'research launch executions are immutable'); END
        """,
        """
        CREATE TRIGGER research_launch_executions_no_delete
        BEFORE DELETE ON research_launch_executions
        BEGIN SELECT RAISE(ABORT, 'research launch executions are immutable'); END
        """,
        """
        CREATE TRIGGER research_launch_operations_no_update
        BEFORE UPDATE ON research_launch_operations
        BEGIN SELECT RAISE(ABORT, 'research launch operations are immutable'); END
        """,
        """
        CREATE TRIGGER research_launch_operations_no_delete
        BEFORE DELETE ON research_launch_operations
        BEGIN SELECT RAISE(ABORT, 'research launch operations are immutable'); END
        """,
    ),
    3: (
        "DROP TRIGGER research_launch_operations_no_update",
        """
        CREATE TRIGGER research_launch_operations_guard_update
        BEFORE UPDATE ON research_launch_operations
        WHEN NEW.operation_id != OLD.operation_id
          OR NEW.execution_id != OLD.execution_id OR NEW.ordinal != OLD.ordinal
          OR NEW.stable_source_id != OLD.stable_source_id OR NEW.question != OLD.question
          OR NEW.payload_digest != OLD.payload_digest OR NEW.provider != OLD.provider
          OR NEW.model != OLD.model OR NEW.logical_operation_id != OLD.logical_operation_id
          OR NEW.blocked_reason IS NOT OLD.blocked_reason OR NEW.intent_json != OLD.intent_json
          OR NEW.intent_sha256 != OLD.intent_sha256 OR NEW.created_at != OLD.created_at
        BEGIN SELECT RAISE(ABORT, 'research launch operations are immutable'); END
        """,
        """
        CREATE TABLE research_provider_submissions (
            submission_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL UNIQUE REFERENCES research_launch_operations(operation_id),
            hold_id TEXT NOT NULL UNIQUE REFERENCES research_spend_holds(hold_id),
            run_id TEXT NOT NULL REFERENCES research_spend_runs(run_id),
            owner_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            adapter_contract TEXT NOT NULL,
            account_digest TEXT NOT NULL,
            region TEXT NOT NULL,
            provider_model_id TEXT NOT NULL,
            client_request_token TEXT NOT NULL UNIQUE CHECK(length(client_request_token)=64),
            create_request_json TEXT NOT NULL,
            create_request_sha256 TEXT NOT NULL,
            recovery_strategy TEXT NOT NULL,
            intent_json TEXT NOT NULL,
            intent_sha256 TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('prepared','submit_possible',
                'create_outcome_unknown','identity_bound','running','provider_terminal',
                'billing_pending','failed_pre_acceptance','integrity_conflict')),
            job_arn TEXT UNIQUE,
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        ) STRICT
        """,
        """
        CREATE TABLE research_provider_observations (
            observation_seq INTEGER PRIMARY KEY AUTOINCREMENT,
            observation_id TEXT NOT NULL UNIQUE,
            submission_id TEXT NOT NULL REFERENCES research_provider_submissions(submission_id),
            source TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            evidence_sha256 TEXT NOT NULL,
            raw_digest TEXT NOT NULL,
            provider_identity TEXT,
            provider_status TEXT,
            created_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX research_provider_observations_submission_idx ON research_provider_observations(submission_id, observation_seq)",
        """
        CREATE TRIGGER research_provider_submissions_guard_update
        BEFORE UPDATE ON research_provider_submissions
        WHEN NEW.submission_id != OLD.submission_id OR NEW.operation_id != OLD.operation_id
          OR NEW.hold_id != OLD.hold_id OR NEW.run_id != OLD.run_id OR NEW.owner_id != OLD.owner_id
          OR NEW.provider != OLD.provider OR NEW.model != OLD.model
          OR NEW.adapter_contract != OLD.adapter_contract OR NEW.account_digest != OLD.account_digest
          OR NEW.region != OLD.region OR NEW.provider_model_id != OLD.provider_model_id
          OR NEW.client_request_token != OLD.client_request_token
          OR NEW.create_request_json != OLD.create_request_json
          OR NEW.create_request_sha256 != OLD.create_request_sha256
          OR NEW.recovery_strategy != OLD.recovery_strategy OR NEW.intent_json != OLD.intent_json
          OR NEW.intent_sha256 != OLD.intent_sha256 OR NEW.created_at != OLD.created_at
        BEGIN SELECT RAISE(ABORT, 'research provider submission immutable fields changed'); END
        """,
        """
        CREATE TRIGGER research_provider_submissions_guard_transition
        BEFORE UPDATE ON research_provider_submissions
        WHEN NOT (
          (OLD.state='prepared' AND NEW.state='submit_possible')
          OR (OLD.state='submit_possible' AND NEW.state IN ('create_outcome_unknown','identity_bound','failed_pre_acceptance','integrity_conflict'))
          OR (OLD.state='create_outcome_unknown' AND NEW.state IN ('create_outcome_unknown','identity_bound','integrity_conflict'))
          OR (OLD.state='identity_bound' AND NEW.state IN ('identity_bound','running','billing_pending','integrity_conflict'))
          OR (OLD.state='running' AND NEW.state IN ('running','billing_pending','integrity_conflict'))
        )
        OR NEW.attempt_count < OLD.attempt_count
        OR NEW.attempt_count > OLD.attempt_count + 1
        OR (OLD.job_arn IS NOT NULL AND NEW.job_arn IS NOT OLD.job_arn)
        OR (NEW.state IN ('prepared','submit_possible','create_outcome_unknown',
                          'failed_pre_acceptance') AND NEW.job_arn IS NOT NULL)
        OR (NEW.state IN ('identity_bound','running','provider_terminal','billing_pending')
            AND NEW.job_arn IS NULL)
        BEGIN SELECT RAISE(ABORT, 'research provider submission transition rejected'); END
        """,
        """
        CREATE TRIGGER research_provider_submissions_no_delete
        BEFORE DELETE ON research_provider_submissions
        BEGIN SELECT RAISE(ABORT, 'research provider submissions are durable'); END
        """,
        """
        CREATE TRIGGER research_provider_observations_no_update
        BEFORE UPDATE ON research_provider_observations
        BEGIN SELECT RAISE(ABORT, 'research provider observations are append-only'); END
        """,
        """
        CREATE TRIGGER research_provider_observations_no_delete
        BEFORE DELETE ON research_provider_observations
        BEGIN SELECT RAISE(ABORT, 'research provider observations are append-only'); END
        """,
    ),
    4: (
        """
        CREATE TABLE research_provider_billing_assessments (
            assessment_seq INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id TEXT NOT NULL UNIQUE,
            assessment_key TEXT NOT NULL,
            submission_id TEXT NOT NULL REFERENCES research_provider_submissions(submission_id),
            hold_id TEXT NOT NULL REFERENCES research_spend_holds(hold_id),
            operation_id TEXT NOT NULL REFERENCES research_launch_operations(operation_id),
            run_id TEXT NOT NULL REFERENCES research_spend_runs(run_id),
            owner_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            job_arn TEXT NOT NULL,
            evidence_kind TEXT NOT NULL CHECK(evidence_kind IN (
                'provider_metering','derived_list_price','cur_open_period',
                'cur_final_unattributable','unsupported')),
            evidence_json TEXT NOT NULL,
            evidence_sha256 TEXT NOT NULL,
            raw_digest TEXT NOT NULL,
            classification TEXT NOT NULL CHECK(classification IN (
                'provider_metering_only','derived_list_price','cur_aggregate_observed',
                'invoice_period_finalized_unattributable',
                'exact_job_final_cost_unavailable')),
            reason_codes_json TEXT NOT NULL,
            settlement_authorized INTEGER NOT NULL DEFAULT 0
                CHECK(settlement_authorized = 0),
            created_at TEXT NOT NULL,
            UNIQUE(submission_id, assessment_key)
        ) STRICT
        """,
        "CREATE INDEX research_provider_billing_assessments_submission_idx "
        "ON research_provider_billing_assessments(submission_id, assessment_seq)",
        """
        CREATE TRIGGER research_provider_billing_assessments_no_update
        BEFORE UPDATE ON research_provider_billing_assessments
        BEGIN SELECT RAISE(ABORT, 'provider billing assessments are append-only'); END
        """,
        """
        CREATE TRIGGER research_provider_billing_assessments_no_delete
        BEFORE DELETE ON research_provider_billing_assessments
        BEGIN SELECT RAISE(ABORT, 'provider billing assessments are append-only'); END
        """,
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
                for index, statement in enumerate(
                    (*_DDL, *_MIGRATIONS[2], *_MIGRATIONS[3], *_MIGRATIONS[4]), start=1
                ):
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
        _bounded_int("ceiling_cents", ceiling_cents, minimum=1, maximum=MAX_AUTHORITY_CENTS)
        intent_json = _canonical({**_binding_payload(binding), "ceiling_cents": ceiling_cents})
        with self._write("create_run") as connection:
            replay = self._replay(
                connection, command_key, "create_run", binding.run_id, intent_json
            )
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
                "SELECT 1 FROM research_spend_zero_attempts WHERE run_id = ? AND attempt_key = ?",
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

    def mark_dispatch_possible(self, command_key: str, hold_id: str) -> PaidHoldSnapshot:
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
        _bounded_int("actual_cents", actual_cents, minimum=0, maximum=MAX_ACTUAL_CENTS)
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
            self._record_command(
                connection, command_key, "settle", hold_id, intent_json, result_json
            )
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
            self._record_command(
                connection, command_key, "release", hold_id, intent_json, result_json
            )
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
        intent_json = _canonical({"attempt_id": attempt_id, "outcome_digest": outcome_digest})
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
            self._record_command(
                connection, command_key, kind, attempt_id, intent_json, result_json
            )
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

    def close_execution(self, command_key: str, run_id: str, reason: str) -> RunSnapshot:
        _required_text("reason", reason)
        intent_json = _canonical({"reason": reason, "run_id": run_id})
        with self._write("close_execution") as connection:
            replay = self._replay(connection, command_key, "close_execution", run_id, intent_json)
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
            status = RunStatus.CLOSED_UNRESOLVED if unresolved else RunStatus.CLOSED_RECONCILED
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
                raise LedgerIntegrityError("hard-ceiling session is bound to multiple owners")
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

    def zero_attempt_for_key(self, run_id: str, attempt_key: str) -> ZeroCostAttemptSnapshot | None:
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

    def materialize_launch_execution(
        self,
        command_key: str,
        binding: RunBinding,
        intent: LaunchExecutionIntent,
        operations: tuple[LaunchOperationIntent, ...],
    ) -> tuple[LaunchExecutionSnapshot, bool]:
        """Atomically fix a complete, ordered launch manifest and its receipt."""
        _required_text("command_key", command_key)
        if len(operations) != intent.operation_count:
            raise BindingConflict("launch operation count changed")
        if tuple(item.ordinal for item in operations) != tuple(range(len(operations))):
            raise BindingConflict("launch operations are not exactly ordered")
        if any(
            item.provider != intent.provider or item.model != intent.model for item in operations
        ):
            raise BindingConflict("launch operation provider route changed")
        execution_json = _canonical(
            {name: cast(JsonScalar, getattr(intent, name)) for name in intent.__dataclass_fields__}
        )
        operation_jsons = tuple(self._launch_operation_json(item) for item in operations)
        manifest_digest = _sha256("[" + ",".join(operation_jsons) + "]")
        command_intent = _canonical(
            {
                "execution_intent_digest": _sha256(execution_json),
                "execution_id": intent.execution_id,
                "manifest_digest": manifest_digest,
                "operation_count": len(operations),
                "owner_id": binding.owner_id,
                "run_id": binding.run_id,
            }
        )
        with self._write("materialize_launch") as connection:
            replay = self._replay(
                connection, command_key, "materialize_launch", intent.execution_id, command_intent
            )
            if replay is not None:
                return self._load_launch_execution(
                    connection, intent.execution_id, binding.owner_id
                ), False
            self._require_binding(connection, binding)
            collision = connection.execute(
                "SELECT execution_id FROM research_launch_executions "
                "WHERE run_id=? OR launch_reservation_id=? OR execution_id=?",
                (binding.run_id, intent.launch_reservation_id, intent.execution_id),
            ).fetchone()
            if collision is not None:
                raise IdempotencyConflict("launch execution identity already exists")
            now = _now()
            values = (
                intent.execution_id,
                binding.run_id,
                binding.owner_id,
                intent.authority_kind,
                intent.launch_reservation_id,
                intent.launch_manifest_digest,
                intent.prepared_integrity_digest,
                intent.provider,
                intent.model,
                intent.route_digest,
                intent.pricing_digest,
                intent.workload_digest,
                intent.operation_count,
                intent.request_digest,
                execution_json,
                _sha256(execution_json),
                now,
            )
            connection.execute(
                "INSERT INTO research_launch_executions VALUES ("
                + ",".join("?" for _ in values)
                + ")",
                values,
            )
            for operation, raw in zip(operations, operation_jsons, strict=True):
                connection.execute(
                    "INSERT INTO research_launch_operations "
                    "(operation_id,execution_id,ordinal,stable_source_id,question,payload_digest,"
                    "provider,model,logical_operation_id,state,blocked_reason,intent_json,"
                    "intent_sha256,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        operation.operation_id,
                        intent.execution_id,
                        operation.ordinal,
                        operation.stable_source_id,
                        operation.question,
                        operation.payload_digest,
                        operation.provider,
                        operation.model,
                        operation.logical_operation_id,
                        operation.state.value,
                        operation.blocked_reason,
                        raw,
                        _sha256(raw),
                        now,
                        now,
                    ),
                )
                self._checkpoint(f"materialize_launch:after_operation:{operation.ordinal}")
            result = _canonical(
                {"execution_id": intent.execution_id, "manifest_digest": manifest_digest}
            )
            self._record_command(
                connection,
                command_key,
                "materialize_launch",
                intent.execution_id,
                command_intent,
                result,
            )
            return self._load_launch_execution(
                connection, intent.execution_id, binding.owner_id
            ), True

    def launch_execution_for_run(
        self, run_id: str, owner_id: str
    ) -> LaunchExecutionSnapshot | None:
        _required_text("run_id", run_id)
        _required_text("owner_id", owner_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT execution_id FROM research_launch_executions WHERE run_id=? AND owner_id=?",
                (run_id, owner_id),
            ).fetchone()
            return (
                None
                if row is None
                else self._load_launch_execution(connection, str(row["execution_id"]), owner_id)
            )
        finally:
            connection.close()

    def record_launch_advance(
        self, command_key: str, execution_id: str, owner_id: str
    ) -> LaunchExecutionSnapshot:
        """Record a pull command; blocked/terminal manifests remain stable and effect-free."""
        command_intent = _canonical({"execution_id": execution_id, "owner_id": owner_id})
        with self._write("advance_launch") as connection:
            replay = self._replay(
                connection, command_key, "advance_launch", execution_id, command_intent
            )
            snapshot = self._load_launch_execution(connection, execution_id, owner_id)
            if replay is None:
                self._record_command(
                    connection,
                    command_key,
                    "advance_launch",
                    execution_id,
                    command_intent,
                    _canonical({"execution_id": execution_id}),
                )
            return snapshot

    def prepare_provider_submission(
        self,
        command_key: str,
        binding: RunBinding,
        hold_intent: PaidHoldIntent,
        projected_max_cents: int,
        intent: ProviderSubmissionIntent,
    ) -> ProviderSubmissionSnapshot:
        """Atomically claim one launch operation, reserve its hold, and bind replay intent."""
        _bounded_int(
            "projected_max_cents", projected_max_cents, minimum=1, maximum=MAX_AUTHORITY_CENTS
        )
        if (hold_intent.provider, hold_intent.model) != (intent.provider, intent.model):
            raise BindingConflict("submission and hold provider route changed")
        hold_json = self._paid_intent_json(binding, hold_intent, projected_max_cents)
        submission_json = self._provider_submission_json(intent)
        command_intent = _canonical(
            {
                "hold_intent_sha256": _sha256(hold_json),
                "owner_id": binding.owner_id,
                "run_id": binding.run_id,
                "submission_id": intent.submission_id,
                "submission_intent_sha256": _sha256(submission_json),
            }
        )
        with self._write("prepare_provider_submission") as connection:
            replay = self._replay(
                connection,
                command_key,
                "prepare_provider_submission",
                intent.submission_id,
                command_intent,
            )
            if replay is not None:
                return self._load_provider_submission(
                    connection, intent.submission_id, binding.owner_id
                )
            run = self._require_binding(connection, binding)
            if run.status is not RunStatus.ACTIVE:
                raise InvalidTransition(
                    binding.run_id, run.status.value, "prepare provider submission"
                )
            operation = connection.execute(
                "SELECT o.state,o.provider,o.model,o.logical_operation_id FROM research_launch_operations o "
                "JOIN research_launch_executions e ON e.execution_id=o.execution_id "
                "WHERE operation_id=? AND e.run_id=? AND e.owner_id=?",
                (intent.operation_id, binding.run_id, binding.owner_id),
            ).fetchone()
            if operation is None:
                raise BindingConflict("launch operation is unavailable")
            if str(operation["state"]) != LaunchOperationState.PENDING.value:
                raise InvalidTransition(
                    intent.operation_id, str(operation["state"]), "prepare provider submission"
                )
            if (str(operation["provider"]), str(operation["model"])) != (
                intent.provider,
                intent.model,
            ):
                raise BindingConflict("launch operation provider route changed")
            if hold_intent.provider_idempotency_key != intent.client_request_token:
                raise BindingConflict("provider hold does not bind the launch operation")
            if (
                connection.execute(
                    "SELECT 1 FROM research_provider_submissions WHERE submission_id=? OR operation_id=? OR client_request_token=?",
                    (intent.submission_id, intent.operation_id, intent.client_request_token),
                ).fetchone()
                is not None
            ):
                raise IdempotencyConflict("provider submission identity already exists")
            if (
                connection.execute(
                    "SELECT 1 FROM research_spend_holds WHERE (run_id=? AND reservation_key=?) OR (provider=? AND provider_idempotency_key=?)",
                    (
                        binding.run_id,
                        hold_intent.reservation_key,
                        hold_intent.provider,
                        hold_intent.provider_idempotency_key,
                    ),
                ).fetchone()
                is not None
            ):
                raise IdempotencyConflict("reservation or provider identity already exists")
            now = _now()
            if (
                connection.execute(
                    "UPDATE research_spend_runs SET held_cents=held_cents+?,updated_at=? WHERE run_id=? "
                    "AND owner_id=? AND session_id=? AND plan_digest=? AND approval_revision=? "
                    "AND status='active' AND ceiling_breached=0 "
                    "AND ? <= ceiling_cents-authorized_spent_cents-held_cents RETURNING run_id",
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
                is None
            ):
                raise SpendCeilingExceeded(binding.run_id, projected_max_cents, run.available_cents)
            self._checkpoint("prepare_provider_submission:after_authority")
            hold_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO research_spend_holds (hold_id,run_id,reservation_key,intent_json,intent_sha256,seam_id,provider,model,operation,operation_digest,projection_digest,rate_snapshot,provider_idempotency_key,projected_max_cents,state,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'reserved',?,?)",
                (
                    hold_id,
                    binding.run_id,
                    hold_intent.reservation_key,
                    hold_json,
                    _sha256(hold_json),
                    hold_intent.seam_id,
                    hold_intent.provider,
                    hold_intent.model,
                    hold_intent.operation,
                    hold_intent.operation_digest,
                    hold_intent.projection_digest,
                    hold_intent.rate_snapshot,
                    hold_intent.provider_idempotency_key,
                    projected_max_cents,
                    now,
                    now,
                ),
            )
            self._checkpoint("prepare_provider_submission:after_hold")
            connection.execute(
                "INSERT INTO research_provider_submissions (submission_id,operation_id,hold_id,run_id,owner_id,provider,model,adapter_contract,account_digest,region,provider_model_id,client_request_token,create_request_json,create_request_sha256,recovery_strategy,intent_json,intent_sha256,state,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'prepared',?,?)",
                (
                    intent.submission_id,
                    intent.operation_id,
                    hold_id,
                    binding.run_id,
                    binding.owner_id,
                    intent.provider,
                    intent.model,
                    intent.adapter_contract,
                    intent.account_digest,
                    intent.region,
                    intent.provider_model_id,
                    intent.client_request_token,
                    intent.create_request_json,
                    _sha256(intent.create_request_json),
                    intent.recovery_strategy,
                    submission_json,
                    _sha256(submission_json),
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_launch_operations SET state='claimed',hold_id=?,updated_at=? WHERE operation_id=? AND state='pending'",
                (hold_id, now, intent.operation_id),
            )
            self._checkpoint("prepare_provider_submission:after_submission")
            snapshot = self._load_provider_submission(
                connection, intent.submission_id, binding.owner_id
            )
            self._record_command(
                connection,
                command_key,
                "prepare_provider_submission",
                intent.submission_id,
                command_intent,
                _canonical({"hold_id": hold_id, "submission_id": intent.submission_id}),
            )
            self._append_event(
                connection,
                self._load_run(connection, binding.run_id),
                command_key=command_key,
                event_kind="provider_submission_prepared",
                hold_id=hold_id,
                held_delta_cents=projected_max_cents,
                evidence_json=command_intent,
            )
            return snapshot

    def transition_provider_submission(
        self,
        command_key: str,
        submission_id: str,
        owner_id: str,
        target: ProviderSubmissionState,
        *,
        job_arn: str | None = None,
        source: str,
        evidence_json: str,
        raw_digest: str,
        provider_status: str | None = None,
        increment_attempt: bool = False,
    ) -> ProviderSubmissionSnapshot:
        """Apply one guarded provider transition and append exactly one observation."""
        if not isinstance(target, ProviderSubmissionState):
            raise TypeError("target must be ProviderSubmissionState")
        for name, value in (
            ("source", source),
            ("evidence_json", evidence_json),
            ("raw_digest", raw_digest),
        ):
            _required_text(name, value)
        try:
            parsed_evidence = json.loads(evidence_json)
        except json.JSONDecodeError as exc:
            raise ValueError("evidence_json must be canonical JSON") from exc
        if (
            json.dumps(parsed_evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            != evidence_json
        ):
            raise ValueError("evidence_json must be canonical JSON")
        intent_json = _canonical(
            {
                "evidence_sha256": _sha256(evidence_json),
                "job_arn": job_arn,
                "owner_id": owner_id,
                "raw_digest": raw_digest,
                "source": source,
                "submission_id": submission_id,
                "target": target.value,
            }
        )
        allowed = {
            ProviderSubmissionState.PREPARED: {ProviderSubmissionState.SUBMIT_POSSIBLE},
            ProviderSubmissionState.SUBMIT_POSSIBLE: {
                ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN,
                ProviderSubmissionState.IDENTITY_BOUND,
                ProviderSubmissionState.FAILED_PRE_ACCEPTANCE,
                ProviderSubmissionState.INTEGRITY_CONFLICT,
            },
            ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN: {
                ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN,
                ProviderSubmissionState.IDENTITY_BOUND,
                ProviderSubmissionState.INTEGRITY_CONFLICT,
            },
            ProviderSubmissionState.IDENTITY_BOUND: {
                ProviderSubmissionState.IDENTITY_BOUND,
                ProviderSubmissionState.RUNNING,
                ProviderSubmissionState.BILLING_PENDING,
                ProviderSubmissionState.INTEGRITY_CONFLICT,
            },
            ProviderSubmissionState.RUNNING: {
                ProviderSubmissionState.RUNNING,
                ProviderSubmissionState.BILLING_PENDING,
                ProviderSubmissionState.INTEGRITY_CONFLICT,
            },
        }
        with self._write("transition_provider_submission") as connection:
            replay = self._replay(
                connection,
                command_key,
                "transition_provider_submission",
                submission_id,
                intent_json,
            )
            if replay is not None:
                return self._load_provider_submission(connection, submission_id, owner_id)
            current = self._load_provider_submission(connection, submission_id, owner_id)
            if target not in allowed.get(current.state, set()):
                raise InvalidTransition(submission_id, current.state.value, target.value)
            bound_arn = current.job_arn
            if target is ProviderSubmissionState.IDENTITY_BOUND:
                if job_arn is None and bound_arn is None:
                    raise BindingConflict("provider identity is required")
                if job_arn is not None:
                    bound_arn = job_arn
            elif job_arn is not None and job_arn != bound_arn:
                raise BindingConflict("provider identity changed")
            now = _now()
            operation_state = {
                ProviderSubmissionState.SUBMIT_POSSIBLE: "dispatch_possible",
                ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN: "unknown",
                ProviderSubmissionState.IDENTITY_BOUND: "unknown",
                ProviderSubmissionState.RUNNING: "unknown",
                ProviderSubmissionState.BILLING_PENDING: "unknown",
                ProviderSubmissionState.INTEGRITY_CONFLICT: "unknown",
                ProviderSubmissionState.FAILED_PRE_ACCEPTANCE: "failed_terminal",
            }.get(target)
            if target is ProviderSubmissionState.SUBMIT_POSSIBLE:
                connection.execute(
                    "UPDATE research_spend_holds SET state='dispatch_possible',dispatch_possible_at=?,updated_at=? WHERE hold_id=? AND state='reserved'",
                    (now, now, current.hold_id),
                )
            elif target in {
                ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN,
                ProviderSubmissionState.IDENTITY_BOUND,
                ProviderSubmissionState.RUNNING,
                ProviderSubmissionState.BILLING_PENDING,
                ProviderSubmissionState.INTEGRITY_CONFLICT,
            }:
                connection.execute(
                    "UPDATE research_spend_holds SET state='unknown',updated_at=? WHERE hold_id=? AND state IN ('dispatch_possible','unknown')",
                    (now, current.hold_id),
                )
            elif target is ProviderSubmissionState.FAILED_PRE_ACCEPTANCE:
                hold = self._load_hold(connection, current.hold_id)
                if hold.state is not PaidHoldState.DISPATCH_POSSIBLE:
                    raise LedgerIntegrityError("pre-acceptance failure has no releasable hold")
                connection.execute(
                    "UPDATE research_spend_holds SET state='released',actual_cents=NULL,"
                    "authorized_applied_cents=0,resolution_key=?,resolution_intent_json=?,"
                    "resolution_intent_sha256=?,resolution_evidence_json=?,resolved_at=?,updated_at=? "
                    "WHERE hold_id=? AND state='dispatch_possible'",
                    (
                        command_key,
                        intent_json,
                        _sha256(intent_json),
                        evidence_json,
                        now,
                        now,
                        current.hold_id,
                    ),
                )
                if (
                    connection.execute(
                        "UPDATE research_spend_runs SET held_cents=held_cents-?,updated_at=? "
                        "WHERE run_id=? AND held_cents>=? RETURNING run_id",
                        (hold.projected_max_cents, now, current.run_id, hold.projected_max_cents),
                    ).fetchone()
                    is None
                ):
                    raise LedgerIntegrityError("pre-acceptance release could not consume authority")
            connection.execute(
                "UPDATE research_provider_submissions SET state=?,job_arn=?,attempt_count=attempt_count+?,updated_at=? WHERE submission_id=? AND state=?",
                (
                    target.value,
                    bound_arn,
                    int(increment_attempt),
                    now,
                    submission_id,
                    current.state.value,
                ),
            )
            if operation_state is not None:
                connection.execute(
                    "UPDATE research_launch_operations SET state=?,updated_at=? WHERE operation_id=?",
                    (operation_state, now, current.intent.operation_id),
                )
            observation_id = hashlib.sha256(f"{submission_id}:{command_key}".encode()).hexdigest()
            connection.execute(
                "INSERT INTO research_provider_observations (observation_id,submission_id,source,evidence_json,evidence_sha256,raw_digest,provider_identity,provider_status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    observation_id,
                    submission_id,
                    source,
                    evidence_json,
                    _sha256(evidence_json),
                    raw_digest,
                    bound_arn,
                    provider_status,
                    now,
                ),
            )
            self._record_command(
                connection,
                command_key,
                "transition_provider_submission",
                submission_id,
                intent_json,
                _canonical({"observation_id": observation_id, "state": target.value}),
            )
            return self._load_provider_submission(connection, submission_id, owner_id)

    def assess_provider_billing(
        self,
        command_key: str,
        submission_id: str,
        owner_id: str,
        assessment_key: str,
        evidence_kind: BillingEvidenceKind,
        evidence: Mapping[str, object],
        raw_digest: str,
    ) -> BillingAssessment:
        """Append a deterministic refusal assessment without changing authority state."""
        for name, value in (
            ("command_key", command_key),
            ("submission_id", submission_id),
            ("owner_id", owner_id),
            ("assessment_key", assessment_key),
        ):
            _required_text(name, value)
        if not isinstance(evidence_kind, BillingEvidenceKind):
            raise TypeError("evidence_kind must be BillingEvidenceKind")
        if re.fullmatch(r"[0-9a-f]{64}", raw_digest) is None:
            raise ValueError("raw_digest must be a lowercase SHA-256")
        evidence_json = canonical_billing_evidence(evidence)
        classification, reasons = classify_billing_evidence(evidence_kind, evidence)
        assessment_id = billing_assessment_id(submission_id, assessment_key)
        reason_codes_json = json.dumps([reason.value for reason in reasons], separators=(",", ":"))
        command_intent = _canonical(
            {
                "assessment_id": assessment_id,
                "assessment_key": assessment_key,
                "evidence_kind": evidence_kind.value,
                "evidence_sha256": _sha256(evidence_json),
                "owner_id": owner_id,
                "raw_digest": raw_digest,
                "submission_id": submission_id,
            }
        )
        with self._write("assess_provider_billing") as connection:
            replay = self._replay(
                connection,
                command_key,
                "assess_provider_billing",
                assessment_id,
                command_intent,
            )
            if replay is not None:
                return self._load_billing_assessment(connection, assessment_id, owner_id)
            submission = self._load_provider_submission(connection, submission_id, owner_id)
            if (
                submission.state is not ProviderSubmissionState.BILLING_PENDING
                or submission.job_arn is None
            ):
                raise InvalidTransition(
                    submission_id,
                    submission.state.value,
                    "assess provider billing",
                )
            hold = self._load_hold(connection, submission.hold_id)
            run = self._load_run(connection, submission.run_id)
            operation = connection.execute(
                "SELECT state,hold_id FROM research_launch_operations WHERE operation_id=?",
                (submission.intent.operation_id,),
            ).fetchone()
            if (
                hold.state is not PaidHoldState.UNKNOWN
                or run.held_cents < hold.projected_max_cents
                or operation is None
                or str(operation["state"]) != LaunchOperationState.UNKNOWN.value
                or str(operation["hold_id"]) != hold.hold_id
            ):
                raise LedgerIntegrityError("billing assessment requires the full unknown hold")
            expected_identity = {
                "account_digest": submission.intent.account_digest,
                "job_arn": submission.job_arn,
                "model": submission.intent.model,
                "owner_id": owner_id,
                "provider": submission.intent.provider,
                "region": submission.intent.region,
                "run_id": submission.run_id,
                "submission_id": submission_id,
            }
            if any(evidence.get(key) != value for key, value in expected_identity.items()):
                raise BindingConflict("billing evidence identity conflicts with submission")
            if (
                evidence_kind is BillingEvidenceKind.PROVIDER_METERING
                and classification is BillingClassification.PROVIDER_METERING_ONLY
            ):
                terminal = connection.execute(
                    "SELECT 1 FROM research_provider_observations WHERE submission_id=? "
                    "AND evidence_sha256=? AND provider_status='Completed'",
                    (submission_id, evidence.get("terminal_observation_digest")),
                ).fetchone()
                if terminal is None or evidence.get("manifest_digest") != raw_digest:
                    classification = BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
                    reasons = (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
                    reason_codes_json = json.dumps(
                        [reason.value for reason in reasons], separators=(",", ":")
                    )
            elif (
                evidence_kind is BillingEvidenceKind.DERIVED_LIST_PRICE
                and classification is BillingClassification.DERIVED_LIST_PRICE
            ):
                metering = connection.execute(
                    "SELECT evidence_json FROM research_provider_billing_assessments WHERE submission_id=? "
                    "AND evidence_sha256=? AND classification='provider_metering_only'",
                    (submission_id, evidence.get("metering_digest")),
                ).fetchone()
                metering_evidence = None if metering is None else json.loads(str(metering[0]))
                if metering_evidence is None or any(
                    evidence.get(name) != metering_evidence.get(name)
                    for name in ("input_token_count", "output_token_count")
                ):
                    classification = BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
                    reasons = (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
                    reason_codes_json = json.dumps(
                        [reason.value for reason in reasons], separators=(",", ":")
                    )
            existing = connection.execute(
                "SELECT assessment_id FROM research_provider_billing_assessments "
                "WHERE assessment_id=? OR (submission_id=? AND assessment_key=?)",
                (assessment_id, submission_id, assessment_key),
            ).fetchone()
            if existing is not None:
                raise IdempotencyConflict("billing assessment identity already exists")
            now = _now()
            connection.execute(
                "INSERT INTO research_provider_billing_assessments "
                "(assessment_id,assessment_key,submission_id,hold_id,operation_id,run_id,"
                "owner_id,provider,model,job_arn,evidence_kind,evidence_json,evidence_sha256,"
                "raw_digest,classification,reason_codes_json,settlement_authorized,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                (
                    assessment_id,
                    assessment_key,
                    submission_id,
                    submission.hold_id,
                    submission.intent.operation_id,
                    submission.run_id,
                    owner_id,
                    submission.intent.provider,
                    submission.intent.model,
                    submission.job_arn,
                    evidence_kind.value,
                    evidence_json,
                    _sha256(evidence_json),
                    raw_digest,
                    classification.value,
                    reason_codes_json,
                    now,
                ),
            )
            result_json = _canonical(
                {
                    "assessment_id": assessment_id,
                    "classification": classification.value,
                    "created_at": now,
                    "settlement_authorized": False,
                }
            )
            self._record_command(
                connection,
                command_key,
                "assess_provider_billing",
                assessment_id,
                command_intent,
                result_json,
            )
            return self._load_billing_assessment(connection, assessment_id, owner_id)

    def provider_billing_assessments(
        self, submission_id: str, owner_id: str
    ) -> tuple[BillingAssessment, ...]:
        connection = self._connect()
        try:
            self._load_provider_submission(connection, submission_id, owner_id)
            rows = connection.execute(
                "SELECT assessment_id FROM research_provider_billing_assessments "
                "WHERE submission_id=? ORDER BY assessment_seq",
                (submission_id,),
            ).fetchall()
            return tuple(
                self._load_billing_assessment(connection, str(row[0]), owner_id) for row in rows
            )
        finally:
            connection.close()

    def provider_submission(self, submission_id: str, owner_id: str) -> ProviderSubmissionSnapshot:
        connection = self._connect()
        try:
            return self._load_provider_submission(connection, submission_id, owner_id)
        finally:
            connection.close()

    def provider_observations(
        self, submission_id: str, owner_id: str
    ) -> tuple[ProviderObservationSnapshot, ...]:
        connection = self._connect()
        try:
            self._load_provider_submission(connection, submission_id, owner_id)
            rows = connection.execute(
                "SELECT * FROM research_provider_observations WHERE submission_id=? ORDER BY observation_seq",
                (submission_id,),
            ).fetchall()
            snapshots = []
            for row in rows:
                evidence_json = str(row["evidence_json"])
                if str(row["evidence_sha256"]) != _sha256(evidence_json):
                    raise LedgerIntegrityError("provider observation evidence conflicts")
                snapshots.append(
                    ProviderObservationSnapshot(
                        str(row["observation_id"]),
                        submission_id,
                        str(row["source"]),
                        evidence_json,
                        str(row["raw_digest"]),
                        None if row["provider_identity"] is None else str(row["provider_identity"]),
                        None if row["provider_status"] is None else str(row["provider_status"]),
                        str(row["created_at"]),
                    )
                )
            return tuple(snapshots)
        finally:
            connection.close()

    @staticmethod
    def _launch_operation_json(intent: LaunchOperationIntent) -> str:
        return _canonical(
            {
                "blocked_reason": intent.blocked_reason,
                "logical_operation_id": intent.logical_operation_id,
                "model": intent.model,
                "operation_id": intent.operation_id,
                "ordinal": intent.ordinal,
                "payload_digest": intent.payload_digest,
                "provider": intent.provider,
                "question": intent.question,
                "stable_source_id": intent.stable_source_id,
                "state": intent.state.value,
            }
        )

    def _load_launch_execution(
        self, connection: sqlite3.Connection, execution_id: str, owner_id: str
    ) -> LaunchExecutionSnapshot:
        row = connection.execute(
            "SELECT * FROM research_launch_executions WHERE execution_id=? AND owner_id=?",
            (execution_id, owner_id),
        ).fetchone()
        if row is None:
            raise RunNotFound(execution_id)
        raw = str(row["intent_json"])
        if raw != _canonical(
            {
                name: cast(JsonScalar, row[name])
                for name in LaunchExecutionIntent.__dataclass_fields__
            }
        ) or str(row["intent_sha256"]) != _sha256(raw):
            raise LedgerIntegrityError("launch execution integrity conflict")
        intent = LaunchExecutionIntent(**json.loads(raw))
        op_rows = connection.execute(
            "SELECT * FROM research_launch_operations WHERE execution_id=? ORDER BY ordinal",
            (execution_id,),
        ).fetchall()
        if len(op_rows) != intent.operation_count:
            raise LedgerIntegrityError("launch operation count conflict")
        operations: list[LaunchOperationSnapshot] = []
        for ordinal, op in enumerate(op_rows):
            op_raw = str(op["intent_json"])
            try:
                value = json.loads(op_raw)
                operation_intent = LaunchOperationIntent(
                    **{**value, "state": LaunchOperationState(value["state"])}
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise LedgerIntegrityError("launch operation is malformed") from exc
            expected = self._launch_operation_json(operation_intent)
            initial_scalar = (
                operation_intent.operation_id,
                execution_id,
                operation_intent.ordinal,
                operation_intent.stable_source_id,
                operation_intent.question,
                operation_intent.payload_digest,
                operation_intent.provider,
                operation_intent.model,
                operation_intent.logical_operation_id,
                operation_intent.blocked_reason,
            )
            actual = tuple(
                op[name]
                for name in (
                    "operation_id",
                    "execution_id",
                    "ordinal",
                    "stable_source_id",
                    "question",
                    "payload_digest",
                    "provider",
                    "model",
                    "logical_operation_id",
                    "blocked_reason",
                )
            )
            if (
                ordinal != operation_intent.ordinal
                or actual != initial_scalar
                or op_raw != expected
                or str(op["intent_sha256"]) != _sha256(op_raw)
                or (
                    (op["result_json"] is not None)
                    and str(op["result_sha256"]) != _sha256(str(op["result_json"]))
                )
            ):
                raise LedgerIntegrityError("launch operation integrity conflict")
            operations.append(
                LaunchOperationSnapshot(
                    execution_id=execution_id,
                    intent=replace(
                        operation_intent,
                        state=LaunchOperationState(str(op["state"])),
                    ),
                    hold_id=None if op["hold_id"] is None else str(op["hold_id"]),
                    result_json=None if op["result_json"] is None else str(op["result_json"]),
                    created_at=str(op["created_at"]),
                    updated_at=str(op["updated_at"]),
                )
            )
        return LaunchExecutionSnapshot(
            run_id=str(row["run_id"]),
            owner_id=owner_id,
            intent=intent,
            operations=tuple(operations),
            created_at=str(row["created_at"]),
        )

    def integrity_check(self) -> str:
        connection = self._connect()
        try:
            run_ids = connection.execute(
                "SELECT run_id FROM research_spend_runs ORDER BY run_id"
            ).fetchall()
            for row in run_ids:
                self._load_run(connection, str(row["run_id"]))
            executions = connection.execute(
                "SELECT execution_id, owner_id FROM research_launch_executions "
                "ORDER BY execution_id"
            ).fetchall()
            for row in executions:
                self._load_launch_execution(
                    connection, str(row["execution_id"]), str(row["owner_id"])
                )
            submissions = connection.execute(
                "SELECT submission_id,owner_id FROM research_provider_submissions ORDER BY submission_id"
            ).fetchall()
            for row in submissions:
                snapshot = self._load_provider_submission(
                    connection, str(row["submission_id"]), str(row["owner_id"])
                )
                observations = connection.execute(
                    "SELECT evidence_json,evidence_sha256 FROM research_provider_observations WHERE submission_id=?",
                    (snapshot.intent.submission_id,),
                ).fetchall()
                for observation in observations:
                    evidence_json = str(observation["evidence_json"])
                    try:
                        parsed = json.loads(evidence_json)
                    except json.JSONDecodeError as exc:
                        raise LedgerIntegrityError(
                            "provider observation evidence is invalid"
                        ) from exc
                    canonical = json.dumps(
                        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                    )
                    if canonical != evidence_json or str(observation["evidence_sha256"]) != _sha256(
                        evidence_json
                    ):
                        raise LedgerIntegrityError("provider observation evidence conflicts")
            assessments = connection.execute(
                "SELECT assessment_id,owner_id FROM research_provider_billing_assessments "
                "ORDER BY assessment_id"
            ).fetchall()
            for row in assessments:
                self._load_billing_assessment(
                    connection, str(row["assessment_id"]), str(row["owner_id"])
                )
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

    def _require_binding(self, connection: sqlite3.Connection, binding: RunBinding) -> RunSnapshot:
        run = self._load_run(connection, binding.run_id)
        if run.binding != binding:
            raise BindingConflict("owner, session, plan, revision, mode, or currency changed")
        return run

    @staticmethod
    def _provider_submission_json(intent: ProviderSubmissionIntent) -> str:
        return _canonical(
            {name: cast(JsonScalar, getattr(intent, name)) for name in intent.__dataclass_fields__}
        )

    def _load_provider_submission(
        self, connection: sqlite3.Connection, submission_id: str, owner_id: str
    ) -> ProviderSubmissionSnapshot:
        row = connection.execute(
            "SELECT * FROM research_provider_submissions WHERE submission_id=? AND owner_id=?",
            (submission_id, owner_id),
        ).fetchone()
        if row is None:
            raise RunNotFound(submission_id)
        intent = ProviderSubmissionIntent(
            submission_id=str(row["submission_id"]),
            operation_id=str(row["operation_id"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            adapter_contract=str(row["adapter_contract"]),
            account_digest=str(row["account_digest"]),
            region=str(row["region"]),
            provider_model_id=str(row["provider_model_id"]),
            client_request_token=str(row["client_request_token"]),
            create_request_json=str(row["create_request_json"]),
            recovery_strategy=str(row["recovery_strategy"]),
        )
        raw = str(row["intent_json"])
        if (
            raw != self._provider_submission_json(intent)
            or str(row["intent_sha256"]) != _sha256(raw)
            or str(row["create_request_sha256"]) != _sha256(intent.create_request_json)
        ):
            raise LedgerIntegrityError("provider submission intent does not match columns")
        binding = connection.execute(
            "SELECT o.hold_id,o.state AS operation_state,e.run_id,e.owner_id,"
            "h.run_id AS hold_run_id,h.provider AS hold_provider,h.model AS hold_model,"
            "h.provider_idempotency_key,h.operation_digest,h.state AS hold_state "
            "FROM research_launch_operations o "
            "JOIN research_launch_executions e ON e.execution_id=o.execution_id "
            "JOIN research_spend_holds h ON h.hold_id=? WHERE o.operation_id=?",
            (str(row["hold_id"]), intent.operation_id),
        ).fetchone()
        if binding is None or (
            str(binding["hold_id"]) != str(row["hold_id"])
            or str(binding["run_id"]) != str(row["run_id"])
            or str(binding["hold_run_id"]) != str(row["run_id"])
            or str(binding["owner_id"]) != str(row["owner_id"])
            or str(binding["hold_provider"]) != intent.provider
            or str(binding["hold_model"]) != intent.model
            or str(binding["provider_idempotency_key"]) != intent.client_request_token
        ):
            raise LedgerIntegrityError("provider submission cross-table binding conflicts")
        return ProviderSubmissionSnapshot(
            intent=intent,
            run_id=str(row["run_id"]),
            owner_id=str(row["owner_id"]),
            hold_id=str(row["hold_id"]),
            state=ProviderSubmissionState(str(row["state"])),
            job_arn=None if row["job_arn"] is None else str(row["job_arn"]),
            attempt_count=int(row["attempt_count"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _load_billing_assessment(
        self, connection: sqlite3.Connection, assessment_id: str, owner_id: str
    ) -> BillingAssessment:
        row = connection.execute(
            "SELECT * FROM research_provider_billing_assessments "
            "WHERE assessment_id=? AND owner_id=?",
            (assessment_id, owner_id),
        ).fetchone()
        if row is None:
            raise RunNotFound(assessment_id)
        submission = self._load_provider_submission(connection, str(row["submission_id"]), owner_id)
        evidence_json = str(row["evidence_json"])
        try:
            evidence = json.loads(evidence_json)
            canonical = canonical_billing_evidence(evidence)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LedgerIntegrityError("billing assessment evidence is invalid") from exc
        kind = BillingEvidenceKind(str(row["evidence_kind"]))
        if not isinstance(evidence, dict):
            raise LedgerIntegrityError("billing assessment evidence must be an object")
        classification, reasons = classify_billing_evidence(kind, evidence)
        if (
            kind is BillingEvidenceKind.PROVIDER_METERING
            and classification is BillingClassification.PROVIDER_METERING_ONLY
        ):
            terminal = connection.execute(
                "SELECT 1 FROM research_provider_observations WHERE submission_id=? "
                "AND evidence_sha256=? AND provider_status='Completed'",
                (submission.intent.submission_id, evidence.get("terminal_observation_digest")),
            ).fetchone()
            if terminal is None or evidence.get("manifest_digest") != str(row["raw_digest"]):
                classification = BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
                reasons = (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
        elif (
            kind is BillingEvidenceKind.DERIVED_LIST_PRICE
            and classification is BillingClassification.DERIVED_LIST_PRICE
        ):
            metering = connection.execute(
                "SELECT evidence_json FROM research_provider_billing_assessments WHERE submission_id=? "
                "AND evidence_sha256=? AND classification='provider_metering_only'",
                (submission.intent.submission_id, evidence.get("metering_digest")),
            ).fetchone()
            metering_evidence = None if metering is None else json.loads(str(metering[0]))
            if metering_evidence is None or any(
                evidence.get(name) != metering_evidence.get(name)
                for name in ("input_token_count", "output_token_count")
            ):
                classification = BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
                reasons = (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
        expected_reasons = json.dumps([reason.value for reason in reasons], separators=(",", ":"))
        expected_id = billing_assessment_id(
            submission.intent.submission_id, str(row["assessment_key"])
        )
        receipt = connection.execute(
            "SELECT intent_json,intent_sha256,result_json,result_sha256 "
            "FROM research_spend_commands "
            "WHERE command_kind='assess_provider_billing' AND scope_id=?",
            (expected_id,),
        ).fetchone()
        if receipt is None:
            raise LedgerIntegrityError("billing assessment has no immutable command receipt")
        receipt_json = str(receipt["intent_json"])
        if str(receipt["intent_sha256"]) != _sha256(receipt_json):
            raise LedgerIntegrityError("billing assessment receipt is corrupt")
        receipt_intent = json.loads(receipt_json)
        receipt_result_json = str(receipt["result_json"])
        if str(receipt["result_sha256"]) != _sha256(receipt_result_json):
            raise LedgerIntegrityError("billing assessment result receipt is corrupt")
        receipt_result = json.loads(receipt_result_json)
        expected_identity = {
            "account_digest": submission.intent.account_digest,
            "job_arn": submission.job_arn,
            "model": submission.intent.model,
            "owner_id": owner_id,
            "provider": submission.intent.provider,
            "region": submission.intent.region,
            "run_id": submission.run_id,
            "submission_id": submission.intent.submission_id,
        }
        if (
            canonical != evidence_json
            or str(row["evidence_sha256"]) != _sha256(evidence_json)
            or str(row["assessment_id"]) != expected_id
            or str(row["hold_id"]) != submission.hold_id
            or str(row["operation_id"]) != submission.intent.operation_id
            or str(row["run_id"]) != submission.run_id
            or str(row["provider"]) != submission.intent.provider
            or str(row["model"]) != submission.intent.model
            or str(row["job_arn"]) != submission.job_arn
            or str(row["classification"]) != classification.value
            or str(row["reason_codes_json"]) != expected_reasons
            or int(row["settlement_authorized"]) != 0
            or re.fullmatch(r"[0-9a-f]{64}", str(row["raw_digest"])) is None
            or receipt_intent.get("raw_digest") != str(row["raw_digest"])
            or receipt_intent.get("evidence_sha256") != str(row["evidence_sha256"])
            or receipt_intent.get("evidence_kind") != kind.value
            or receipt_result.get("created_at") != str(row["created_at"])
            or any(evidence.get(key) != value for key, value in expected_identity.items())
        ):
            raise LedgerIntegrityError("billing assessment binding conflicts")
        return BillingAssessment(
            assessment_id=expected_id,
            assessment_key=str(row["assessment_key"]),
            submission_id=submission.intent.submission_id,
            evidence_kind=kind,
            evidence_json=evidence_json,
            raw_digest=str(row["raw_digest"]),
            classification=classification,
            reason_codes=reasons,
            settlement_authorized=False,
            created_at=str(row["created_at"]),
        )

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

    def _load_hold(self, connection: sqlite3.Connection, hold_id: str) -> PaidHoldSnapshot:
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
                None if row["dispatch_possible_at"] is None else str(row["dispatch_possible_at"])
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
            outcome_digest=(None if row["outcome_digest"] is None else str(row["outcome_digest"])),
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
            resolved_at=(None if value["resolved_at"] is None else str(value["resolved_at"])),
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
            resolved_at=(None if value["resolved_at"] is None else str(value["resolved_at"])),
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
