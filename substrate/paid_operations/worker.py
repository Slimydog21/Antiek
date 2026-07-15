"""Generation-fenced paid-operation worker and fake provider protocol."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from substrate.paid_operations.ledger import (
    BudgetExceeded,
    LeaseFence,
    Movement,
    PaidOperationLedger,
    logical_movement_key,
)
from substrate.paid_operations.store import (
    OperationConflict,
    PaidOperationCorruptionError,
    PaidOperationStore,
)

_MIGRATION = Path(__file__).with_name("migrations") / "001_authority.sql"
_IDEMPOTENCY_DOMAIN = b"antiek.paid-operation.dispatch.v1\0"
_CHECKPOINT_DOMAIN = b"antiek.paid-operation.checkpoint.v1\0"
_HASH_CHARS = frozenset("0123456789abcdef")
_MAX_RESPONSE_BODY_BYTES = 1_048_576
_ATTESTED_BEHAVIOR = {
    "request_body_scope": "intent+step",
    "duplicate_same_body_behavior": "same logical result",
    "duplicate_changed_body_behavior": "conflict",
    "billing_semantics": "one charge per idempotency key",
}


class ProviderCapabilityError(RuntimeError):
    """Live dispatch capability evidence is missing or contradictory."""


class UnknownProviderOutcome(RuntimeError):
    """The provider may have accepted/billed the request but no receipt returned."""


@dataclass(frozen=True)
class ProviderCapabilityAttestation:
    provider_id: str
    endpoint_id: str
    operation_kind: str
    api_version: str
    retention_window_ms: int
    documentation_url: str
    request_body_scope: str
    duplicate_same_body_behavior: str
    duplicate_changed_body_behavior: str
    billing_semantics: str
    live_smoke_receipt_hash: str | None
    expires_at_ms: int
    enabled: bool = False
    documentation_hash: str | None = None
    behavior_evidence_hash: str | None = None
    live_smoke_operator_id: str | None = None
    live_smoke_authorization_hash: str | None = None

    def validate(self, *, now_ms: int) -> None:
        _exact_non_negative_int("now_ms", now_ms, error=ProviderCapabilityError)
        required = (
            self.provider_id,
            self.endpoint_id,
            self.operation_kind,
            self.api_version,
            self.documentation_url,
            self.request_body_scope,
            self.duplicate_same_body_behavior,
            self.duplicate_changed_body_behavior,
            self.billing_semantics,
        )
        if any(not isinstance(value, str) or not value for value in required):
            raise ProviderCapabilityError("provider capability attestation is incomplete")
        if not isinstance(self.enabled, bool):
            raise ProviderCapabilityError("provider capability enabled flag is invalid")
        for name, value in (
            ("provider_id", self.provider_id),
            ("endpoint_id", self.endpoint_id),
            ("operation_kind", self.operation_kind),
            ("api_version", self.api_version),
        ):
            _capability_identifier(name, value)
        if self.operation_kind not in {"collective_interrogation_v1", "midnight_oil_v1"}:
            raise ProviderCapabilityError("provider capability operation kind is unsupported")
        _exact_non_negative_int(
            "retention_window_ms",
            self.retention_window_ms,
            positive=True,
            error=ProviderCapabilityError,
        )
        _exact_non_negative_int("expires_at_ms", self.expires_at_ms, error=ProviderCapabilityError)
        parsed_url = urlsplit(self.documentation_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ProviderCapabilityError("provider documentation URL must be authoritative HTTPS")
        for name, expected in _ATTESTED_BEHAVIOR.items():
            if getattr(self, name) != expected:
                raise ProviderCapabilityError(f"provider {name} is not an attested behavior")
        if self.enabled:
            for evidence_name, evidence_value in (
                ("documentation_hash", self.documentation_hash),
                ("behavior_evidence_hash", self.behavior_evidence_hash),
                ("live_smoke_receipt_hash", self.live_smoke_receipt_hash),
                ("live_smoke_authorization_hash", self.live_smoke_authorization_hash),
            ):
                _capability_hash(evidence_name, evidence_value)
            if self.live_smoke_operator_id is None:
                raise ProviderCapabilityError("enabled provider lacks operator-authorized live smoke")
            _capability_identifier("live_smoke_operator_id", self.live_smoke_operator_id)
            if now_ms >= self.expires_at_ms:
                raise ProviderCapabilityError("enabled provider capability has expired")


@dataclass(frozen=True)
class ProviderRequest:
    account_id: str
    owner_user_id: str
    operation_id: str
    operation_kind: str
    provider_id: str
    route_id: str
    intent_hash: str
    step_id: str
    idempotency_key: str
    body: Mapping[str, object]


@dataclass(frozen=True)
class ProviderResult:
    body: Mapping[str, object]
    provider_receipt: str
    observed_cost_cents: int


class PaidOperationProvider(Protocol):
    capability: ProviderCapabilityAttestation

    def dispatch(self, request: ProviderRequest) -> ProviderResult:
        """Execute one idempotent fake-provider request."""


@dataclass
class FakePaidOperationProvider:
    """Injected hermetic provider for SPR-03 tests; performs no network I/O."""

    capability: ProviderCapabilityAttestation
    results: dict[str, ProviderResult | UnknownProviderOutcome] = field(default_factory=dict)
    calls: list[ProviderRequest] = field(default_factory=list)
    logical_results: dict[str, ProviderResult] = field(default_factory=dict)

    def dispatch(self, request: ProviderRequest) -> ProviderResult:
        self.calls.append(request)
        replay = self.logical_results.get(request.idempotency_key)
        if replay is not None:
            return replay
        outcome = self.results.get(request.step_id)
        if isinstance(outcome, UnknownProviderOutcome):
            raise outcome
        result = outcome or ProviderResult(
            body={"operation_id": request.operation_id, "step_id": request.step_id, "status": "ok"},
            provider_receipt=f"fake:{request.operation_id}:{request.step_id}",
            observed_cost_cents=0,
        )
        self.logical_results[request.idempotency_key] = result
        return result


@dataclass(frozen=True)
class LeasedOperation:
    account_id: str
    owner_user_id: str
    operation_id: str
    operation_kind: str
    provider_id: str
    route_id: str
    intent_hash: str
    canonical_intent_json: str
    ceiling_cents: int
    version: int
    lease_worker_id: str
    lease_generation: int
    lease_expires_at_ms: int

    @property
    def fence(self) -> LeaseFence:
        return LeaseFence(
            account_id=self.account_id,
            owner_user_id=self.owner_user_id,
            operation_id=self.operation_id,
            intent_hash=self.intent_hash,
            lease_worker_id=self.lease_worker_id,
            lease_generation=self.lease_generation,
            expected_operation_version=self.version,
        )

    def after_movement(self, movement: Movement) -> LeasedOperation:
        advanced = self.fence.after(movement)
        return replace(self, version=advanced.expected_operation_version)

    def after_checkpoint(self, checkpoint: _Checkpoint) -> LeasedOperation:
        if (
            checkpoint.lease_worker_id == self.lease_worker_id
            and checkpoint.lease_generation == self.lease_generation
            and checkpoint.expected_operation_version == self.version
        ):
            return replace(self, version=checkpoint.operation_version)
        return self


@dataclass(frozen=True)
class DispatchReceipt:
    operation_id: str
    state: str
    idempotency_key: str
    reserve: Movement
    terminal_movement: Movement | None
    checkpoint_hash: str | None


class PaidOperationWorker:
    """Serial dispatch boundary with leases, budget holds and checkpoint replay."""

    def __init__(
        self,
        db_path: str | Path,
        provider: PaidOperationProvider,
        *,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._provider = provider
        self._clock_ms = clock_ms or _epoch_ms
        self.ledger = PaidOperationLedger(self._db_path)
        with self._connect() as con:
            con.executescript(_MIGRATION.read_text(encoding="utf-8"))
        PaidOperationStore(self._db_path)
        self._provider.capability.validate(now_ms=self._clock_ms())

    def claim_next(self, worker_id: str, *, lease_ms: int) -> LeasedOperation | None:
        if lease_ms <= 0:
            raise ValueError("lease_ms must be positive")
        now_ms = self._clock_ms()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute(
                    "SELECT p.account_id, p.owner_user_id, p.operation_id, p.kind, p.intent_hash, "
                    "p.canonical_intent_json, p.ceiling_cents, p.version, "
                    "COALESCE(p.lease_generation, 0), "
                    "json_extract(p.canonical_intent_json, '$.provider_id'), "
                    "json_extract(p.canonical_intent_json, '$.route_id') "
                    "FROM paid_operations p JOIN paid_operation_queue q "
                    "ON p.account_id = q.account_id AND p.owner_user_id = q.owner_user_id "
                    "AND p.operation_id = q.operation_id "
                    "WHERE p.kind = ? "
                    "AND json_extract(p.canonical_intent_json, '$.provider_id') = ? "
                    "AND json_extract(p.canonical_intent_json, '$.route_id') = ? "
                    "AND (p.state = 'queued' OR (p.state = 'running' AND p.lease_expires_at_ms <= ?)) "
                    "ORDER BY q.enqueued_at_ms, p.operation_id LIMIT 1",
                    (
                        self._provider.capability.operation_kind,
                        self._provider.capability.provider_id,
                        self._provider.capability.endpoint_id,
                        now_ms,
                    ),
                ).fetchone()
                if row is None:
                    con.execute("COMMIT")
                    return None
                generation = int(row[8]) + 1
                lease_expires_at_ms = now_ms + lease_ms
                cur = con.execute(
                    "UPDATE paid_operations SET state = 'running', version = version + 1, "
                    "updated_at_ms = ?, lease_worker_id = ?, lease_generation = ?, lease_expires_at_ms = ? "
                    "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
                    "AND version = ? AND (state = 'queued' OR (state = 'running' AND lease_expires_at_ms <= ?))",
                    (
                        now_ms,
                        worker_id,
                        generation,
                        lease_expires_at_ms,
                        row[0],
                        row[1],
                        row[2],
                        row[7],
                        now_ms,
                    ),
                )
                if cur.rowcount != 1:
                    raise OperationConflict("lease CAS precondition failed")
                con.execute("COMMIT")
                return LeasedOperation(
                    account_id=row[0],
                    owner_user_id=row[1],
                    operation_id=row[2],
                    operation_kind=row[3],
                    provider_id=_as_text(row[9]),
                    route_id=_as_text(row[10]),
                    intent_hash=row[4],
                    canonical_intent_json=_as_text(row[5]),
                    ceiling_cents=int(row[6]),
                    version=int(row[7]) + 1,
                    lease_worker_id=worker_id,
                    lease_generation=generation,
                    lease_expires_at_ms=lease_expires_at_ms,
                )
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def execute_one(self, worker_id: str, *, lease_ms: int, step_id: str = "dispatch") -> DispatchReceipt | None:
        leased = self.claim_next(worker_id, lease_ms=lease_ms)
        if leased is None:
            return None
        return self.execute_leased(leased, step_id=step_id)

    def execute_leased(self, leased: LeasedOperation, *, step_id: str = "dispatch") -> DispatchReceipt:
        try:
            self._provider.capability.validate(now_ms=self._clock_ms())
        except ProviderCapabilityError:
            self._budget_halt(leased, "provider_capability_disabled")
            raise
        if not self._provider.capability.enabled:
            self._budget_halt(leased, "provider_capability_disabled")
            raise ProviderCapabilityError("provider capability is disabled")
        intent_body = _intent_body(leased.canonical_intent_json)
        self._validate_intent_route(leased, intent_body)
        if leased.ceiling_cents == 0:
            self._budget_halt(leased, "zero_reserve_cannot_retain_unknown_outcome")
            raise BudgetExceeded("zero-cent reserve cannot retain an unknown paid outcome")
        now_ms = self._clock_ms()
        try:
            reserve = self.ledger.reserve(leased.fence, leased.ceiling_cents, step_id=step_id, now_ms=now_ms)
        except BudgetExceeded:
            self._budget_halt(leased, "paid_operation_budget_exceeded")
            raise
        leased = leased.after_movement(reserve)
        idempotency_key = stable_idempotency_key(
            leased.account_id,
            leased.owner_user_id,
            leased.operation_id,
            step_id,
            leased.intent_hash,
        )
        checkpoint = self._checkpoint(leased, step_id)
        if (
            checkpoint is None
            and now_ms - reserve.created_at_ms >= self._provider.capability.retention_window_ms
        ):
            retain = self._retain_and_failed_reconcile(
                leased,
                step_id,
                reserve.movement_key,
                "provider_idempotency_window_expired",
            )
            return DispatchReceipt(leased.operation_id, "failed_reconcile", idempotency_key, reserve, retain, None)
        if checkpoint is not None:
            if checkpoint.observed_cost_cents > reserve.cents:
                retain = self._retain_and_failed_reconcile(
                    leased,
                    step_id,
                    reserve.movement_key,
                    "settled_cost_exceeds_reserve",
                    checkpoint_hash=checkpoint.response_body_hash,
                )
                return DispatchReceipt(
                    leased.operation_id,
                    "failed_reconcile",
                    idempotency_key,
                    reserve,
                    retain,
                    checkpoint.response_body_hash,
                )
            terminal = self.ledger.settle(
                leased.fence,
                checkpoint.observed_cost_cents,
                step_id=step_id,
                reserve_key=reserve.movement_key,
                now_ms=self._clock_ms(),
            )
            leased = leased.after_movement(terminal)
            if reserve.cents > checkpoint.observed_cost_cents:
                release = self.ledger.release(
                    leased.fence,
                    reserve.cents - checkpoint.observed_cost_cents,
                    step_id=step_id,
                    reserve_key=reserve.movement_key,
                    now_ms=self._clock_ms(),
                )
                leased = leased.after_movement(release)
            self._complete(leased, checkpoint.response_body_hash, checkpoint.observed_cost_cents)
            return DispatchReceipt(leased.operation_id, "complete", idempotency_key, reserve, terminal, checkpoint.response_body_hash)
        request = ProviderRequest(
            account_id=leased.account_id,
            owner_user_id=leased.owner_user_id,
            operation_id=leased.operation_id,
            operation_kind=leased.operation_kind,
            provider_id=leased.provider_id,
            route_id=leased.route_id,
            intent_hash=leased.intent_hash,
            step_id=step_id,
            idempotency_key=idempotency_key,
            body=intent_body,
        )
        self._provider.capability.validate(now_ms=self._clock_ms())
        self._validate_intent_route(leased, intent_body)
        try:
            result = self._provider.dispatch(request)
        except UnknownProviderOutcome:
            retain = self._retain_and_failed_reconcile(leased, step_id, reserve.movement_key, "unknown_provider_outcome")
            return DispatchReceipt(leased.operation_id, "failed_reconcile", idempotency_key, reserve, retain, None)
        _observed_cost(result.observed_cost_cents)
        written_checkpoint = self._write_checkpoint(leased, step_id, idempotency_key, result)
        leased = leased.after_checkpoint(written_checkpoint)
        checkpoint_hash = written_checkpoint.response_body_hash
        if result.observed_cost_cents > reserve.cents:
            retain = self._retain_and_failed_reconcile(
                leased,
                step_id,
                reserve.movement_key,
                "settled_cost_exceeds_reserve",
                checkpoint_hash=checkpoint_hash,
            )
            return DispatchReceipt(
                leased.operation_id,
                "failed_reconcile",
                idempotency_key,
                reserve,
                retain,
                checkpoint_hash,
            )
        terminal = self.ledger.settle(
            leased.fence,
            result.observed_cost_cents,
            step_id=step_id,
            reserve_key=reserve.movement_key,
            now_ms=self._clock_ms(),
        )
        leased = leased.after_movement(terminal)
        if reserve.cents > result.observed_cost_cents:
            release = self.ledger.release(
                leased.fence,
                reserve.cents - result.observed_cost_cents,
                step_id=step_id,
                reserve_key=reserve.movement_key,
                now_ms=self._clock_ms(),
            )
            leased = leased.after_movement(release)
        self._complete(leased, checkpoint_hash, result.observed_cost_cents)
        return DispatchReceipt(leased.operation_id, "complete", idempotency_key, reserve, terminal, checkpoint_hash)

    def renew(self, leased: LeasedOperation, *, lease_ms: int) -> LeasedOperation:
        if lease_ms <= 0:
            raise ValueError("lease_ms must be positive")
        now_ms = self._clock_ms()
        expires = now_ms + lease_ms
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                cur = con.execute(
                    "UPDATE paid_operations SET updated_at_ms = ?, lease_expires_at_ms = ?, version = version + 1 "
                    "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
                    "AND state = 'running' AND lease_worker_id = ? AND lease_generation = ? "
                    "AND version = ? AND lease_expires_at_ms > ?",
                    (
                        now_ms,
                        expires,
                        leased.account_id,
                        leased.owner_user_id,
                        leased.operation_id,
                        leased.lease_worker_id,
                        leased.lease_generation,
                        leased.version,
                        now_ms,
                    ),
                )
                if cur.rowcount != 1:
                    raise OperationConflict("lease fence rejected")
                con.execute("COMMIT")
                return LeasedOperation(**{**leased.__dict__, "version": leased.version + 1, "lease_expires_at_ms": expires})
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _write_checkpoint(
        self,
        leased: LeasedOperation,
        step_id: str,
        idempotency_key: str,
        result: ProviderResult,
    ) -> _Checkpoint:
        try:
            body_bytes = json.dumps(
                result.body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OperationConflict("provider response body is not durable JSON") from exc
        if len(body_bytes) > _MAX_RESPONSE_BODY_BYTES:
            raise OperationConflict("provider response body exceeds durable limit")
        response_body_json = body_bytes.decode("utf-8")
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        provider_receipt = _safe_text("provider_receipt", result.provider_receipt)
        _observed_cost(result.observed_cost_cents)
        now_ms = self._clock_ms()
        material_hash = _checkpoint_material_hash(
            leased,
            step_id,
            self._provider.capability.provider_id,
            self._provider.capability.endpoint_id,
            idempotency_key,
            body_hash,
            provider_receipt,
            result.observed_cost_cents,
        )
        expected = _Checkpoint(
            response_body_hash=body_hash,
            response_body_json=response_body_json,
            provider_receipt=provider_receipt,
            observed_cost_cents=result.observed_cost_cents,
            provider_id=self._provider.capability.provider_id,
            endpoint_id=self._provider.capability.endpoint_id,
            idempotency_key=idempotency_key,
            lease_worker_id=leased.lease_worker_id,
            lease_generation=leased.lease_generation,
            expected_operation_version=leased.version,
            operation_version=leased.version + 1,
            checkpoint_material_hash=material_hash,
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                existing = self._checkpoint_in_tx(con, leased, step_id)
                if existing is not None:
                    if (
                        existing.response_body_hash != body_hash
                        or existing.response_body_json != response_body_json
                        or existing.provider_receipt != provider_receipt
                        or existing.observed_cost_cents != result.observed_cost_cents
                        or existing.provider_id != self._provider.capability.provider_id
                        or existing.endpoint_id != self._provider.capability.endpoint_id
                        or existing.idempotency_key != idempotency_key
                        or existing.checkpoint_material_hash != material_hash
                    ):
                        raise OperationConflict("checkpoint replay conflicts")
                    self._require_active_lease_in_tx(con, leased, now_ms, allow_prior_mutation=existing)
                    con.execute("COMMIT")
                    return existing
                self._require_active_lease_in_tx(con, leased, now_ms)
                con.execute(
                    "INSERT INTO paid_operation_checkpoints "
                    "(account_id, owner_user_id, operation_id, step_id, intent_hash, lease_worker_id, "
                    "lease_generation, expected_operation_version, operation_version, provider_id, "
                    "endpoint_id, idempotency_key, response_body_hash, response_body_json, "
                    "provider_receipt, observed_cost_cents, checkpoint_material_hash, created_at_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        leased.account_id,
                        leased.owner_user_id,
                        leased.operation_id,
                        step_id,
                        leased.intent_hash,
                        leased.lease_worker_id,
                        leased.lease_generation,
                        leased.version,
                        leased.version + 1,
                        self._provider.capability.provider_id,
                        self._provider.capability.endpoint_id,
                        idempotency_key,
                        body_hash,
                        response_body_json,
                        provider_receipt,
                        result.observed_cost_cents,
                        material_hash,
                        now_ms,
                    ),
                )
                cur = con.execute(
                    "UPDATE paid_operations SET version = version + 1, updated_at_ms = ? "
                    "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
                    "AND state = 'running' AND lease_worker_id = ? AND lease_generation = ? "
                    "AND intent_hash = ? AND version = ? AND lease_expires_at_ms > ?",
                    (
                        now_ms,
                        leased.account_id,
                        leased.owner_user_id,
                        leased.operation_id,
                        leased.lease_worker_id,
                        leased.lease_generation,
                        leased.intent_hash,
                        leased.version,
                        now_ms,
                    ),
                )
                if cur.rowcount != 1:
                    raise OperationConflict("operation CAS precondition failed")
                con.execute("COMMIT")
                return expected
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _checkpoint(self, leased: LeasedOperation, step_id: str) -> _Checkpoint | None:
        with self._connect() as con:
            return self._checkpoint_in_tx(con, leased, step_id)

    def _checkpoint_in_tx(self, con: sqlite3.Connection, leased: LeasedOperation, step_id: str) -> _Checkpoint | None:
        row = con.execute(
            "SELECT response_body_hash, provider_receipt, observed_cost_cents, provider_id, endpoint_id, "
            "idempotency_key, response_body_json, lease_worker_id, lease_generation, "
            "expected_operation_version, operation_version, checkpoint_material_hash "
            "FROM paid_operation_checkpoints WHERE account_id = ? AND owner_user_id = ? "
            "AND operation_id = ? AND step_id = ? AND intent_hash = ?",
            (leased.account_id, leased.owner_user_id, leased.operation_id, step_id, leased.intent_hash),
        ).fetchone()
        if row is None:
            return None
        checkpoint = _Checkpoint(
            row[0],
            row[6],
            row[1],
            int(row[2]),
            row[3],
            row[4],
            row[5],
            row[7],
            int(row[8]),
            int(row[9]),
            int(row[10]),
            row[11],
        )
        expected_key = stable_idempotency_key(
            leased.account_id, leased.owner_user_id, leased.operation_id, step_id, leased.intent_hash
        )
        if (
            checkpoint.provider_id != self._provider.capability.provider_id
            or checkpoint.endpoint_id != self._provider.capability.endpoint_id
            or checkpoint.idempotency_key != expected_key
        ):
            raise PaidOperationCorruptionError("checkpoint provider material conflicts")
        return checkpoint

    def _complete(self, leased: LeasedOperation, checkpoint_hash: str, settled_cents: int) -> None:
        self._terminal(leased, "complete", "complete", "provider_completed", checkpoint_hash, settled_cents)

    def _budget_halt(self, leased: LeasedOperation, reason: str) -> None:
        self._terminal(leased, "budget_halted", "budget_halted", reason, None, 0)

    def _retain_and_failed_reconcile(
        self,
        leased: LeasedOperation,
        step_id: str,
        reserve_key: str,
        reason: str,
        *,
        checkpoint_hash: str | None = None,
    ) -> Movement:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                retain = self.ledger._movement_in_tx(  # noqa: SLF001
                    con,
                    leased.fence,
                    movement_key=logical_movement_key(
                        leased.account_id,
                        leased.owner_user_id,
                        leased.operation_id,
                        step_id,
                        "retain",
                    ),
                    step_id=step_id,
                    movement_type="retain",
                    cents=0,
                    prior_movement_key=reserve_key,
                    now_ms=self._clock_ms(),
                )
                leased = leased.after_movement(retain)
                self._terminal_in_tx(
                    con,
                    leased,
                    "failed_reconcile",
                    "unknown_outcome",
                    reason,
                    checkpoint_hash,
                    None,
                )
                con.execute("COMMIT")
                return retain
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _validate_intent_route(
        self,
        leased: LeasedOperation,
        intent_body: Mapping[str, object],
    ) -> None:
        capability = self._provider.capability
        if capability.operation_kind != leased.operation_kind:
            raise ProviderCapabilityError("provider capability kind mismatch")
        intent_provider = intent_body.get("provider_id")
        intent_route = intent_body.get("route_id")
        if (
            leased.provider_id != intent_provider
            or leased.route_id != intent_route
            or capability.provider_id != intent_provider
            or capability.endpoint_id != intent_route
        ):
            raise ProviderCapabilityError("immutable intent provider route mismatch")

    def _failed_reconcile(
        self,
        leased: LeasedOperation,
        reason: str,
        *,
        settled_cents: int | None,
        checkpoint_hash: str | None,
    ) -> None:
        self._terminal(leased, "failed_reconcile", "unknown_outcome", reason, checkpoint_hash, settled_cents)

    def _terminal(
        self,
        leased: LeasedOperation,
        state: str,
        code: str,
        reason: str,
        checkpoint_hash: str | None,
        settled_cents: int | None,
    ) -> None:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                self._terminal_in_tx(con, leased, state, code, reason, checkpoint_hash, settled_cents)
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _terminal_in_tx(
        self,
        con: sqlite3.Connection,
        leased: LeasedOperation,
        state: str,
        code: str,
        reason: str,
        checkpoint_hash: str | None,
        settled_cents: int | None,
    ) -> None:
        now_ms = self._clock_ms()
        cur = con.execute(
            "UPDATE paid_operations SET state = ?, version = version + 1, updated_at_ms = ?, "
            "terminal_code = ?, terminal_reason = ?, reconciliation_status = ?, "
            "result_checkpoint_hash = ?, settled_cents = ? "
            "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
            "AND state = 'running' AND lease_worker_id = ? AND lease_generation = ? "
            "AND intent_hash = ? AND version = ? AND lease_expires_at_ms > ?",
            (
                state,
                now_ms,
                code,
                reason,
                "pending" if state == "failed_reconcile" else "none",
                checkpoint_hash,
                settled_cents,
                leased.account_id,
                leased.owner_user_id,
                leased.operation_id,
                leased.lease_worker_id,
                leased.lease_generation,
                leased.intent_hash,
                leased.version,
                now_ms,
            ),
        )
        if cur.rowcount != 1:
            raise OperationConflict("lease fence rejected")

    def _require_active_lease_in_tx(
        self,
        con: sqlite3.Connection,
        leased: LeasedOperation,
        now_ms: int,
        *,
        allow_prior_mutation: _Checkpoint | None = None,
    ) -> None:
        row = con.execute(
            "SELECT version, lease_expires_at_ms FROM paid_operations WHERE account_id = ? AND owner_user_id = ? "
            "AND operation_id = ? AND state = 'running' AND lease_worker_id = ? "
            "AND lease_generation = ? AND intent_hash = ?",
            (
                leased.account_id,
                leased.owner_user_id,
                leased.operation_id,
                leased.lease_worker_id,
                leased.lease_generation,
                leased.intent_hash,
            ),
        ).fetchone()
        if row is None:
            raise OperationConflict("lease fence rejected")
        if row[1] is None or int(row[1]) <= now_ms:
            raise OperationConflict("lease has expired")
        if int(row[0]) == leased.version:
            return
        if (
            allow_prior_mutation is not None
            and allow_prior_mutation.expected_operation_version == leased.version
            and int(row[0]) >= allow_prior_mutation.operation_version
        ):
            return
        raise OperationConflict("operation CAS precondition failed")

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        con = sqlite3.connect(self._db_path, timeout=30.0, isolation_level=None, check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
        return closing(con)


@dataclass(frozen=True)
class _Checkpoint:
    response_body_hash: str
    response_body_json: str
    provider_receipt: str
    observed_cost_cents: int
    provider_id: str
    endpoint_id: str
    idempotency_key: str
    lease_worker_id: str
    lease_generation: int
    expected_operation_version: int
    operation_version: int
    checkpoint_material_hash: str


def stable_idempotency_key(
    account_id: str,
    owner_user_id: str,
    operation_id: str,
    step_id: str,
    intent_hash: str,
) -> str:
    material = json.dumps(
        {
            "account_id": account_id,
            "intent_hash": intent_hash,
            "operation_id": operation_id,
            "owner_user_id": owner_user_id,
            "step_id": step_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(_IDEMPOTENCY_DOMAIN + material).hexdigest()


def _checkpoint_material_hash(
    leased: LeasedOperation,
    step_id: str,
    provider_id: str,
    endpoint_id: str,
    idempotency_key: str,
    response_body_hash: str,
    provider_receipt: str,
    observed_cost_cents: int,
) -> str:
    material = json.dumps(
        {
            "account_id": leased.account_id,
            "endpoint_id": endpoint_id,
            "expected_operation_version": leased.version,
            "idempotency_key": idempotency_key,
            "intent_hash": leased.intent_hash,
            "lease_generation": leased.lease_generation,
            "lease_worker_id": leased.lease_worker_id,
            "observed_cost_cents": observed_cost_cents,
            "operation_id": leased.operation_id,
            "operation_version": leased.version + 1,
            "owner_user_id": leased.owner_user_id,
            "provider_id": provider_id,
            "provider_receipt": provider_receipt,
            "response_body_hash": response_body_hash,
            "step_id": step_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(_CHECKPOINT_DOMAIN + material).hexdigest()


def _observed_cost(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 9_223_372_036_854_775_807:
        raise OperationConflict("observed_cost_cents is invalid")
    return value


def _epoch_ms() -> int:
    return time.time_ns() // 1_000_000


def _exact_non_negative_int(
    name: str,
    value: object,
    *,
    positive: bool = False,
    error: type[ProviderCapabilityError],
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (1 if positive else 0)
        or value > 9_223_372_036_854_775_807
    ):
        raise error(f"{name} is invalid")
    return value


def _capability_hash(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HASH_CHARS for character in value)
    ):
        raise ProviderCapabilityError(f"{name} must be a lowercase sha256 digest")
    return value


def _capability_identifier(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 192
        or not value[0].isalnum()
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._:-" for character in value)
    ):
        raise ProviderCapabilityError(f"{name} must be a canonical identifier")
    return value


def _intent_body(canonical_intent_json: str) -> Mapping[str, object]:
    try:
        body = json.loads(canonical_intent_json)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PaidOperationCorruptionError("canonical intent is malformed") from exc
    if not isinstance(body, dict):
        raise PaidOperationCorruptionError("canonical intent is not an object")
    return body


def _as_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if not isinstance(value, str):
        raise PaidOperationCorruptionError("canonical intent is malformed")
    return value


def _safe_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        raise OperationConflict(f"{name} is invalid")
    return value


__all__ = [
    "DispatchReceipt",
    "FakePaidOperationProvider",
    "LeasedOperation",
    "PaidOperationProvider",
    "PaidOperationWorker",
    "ProviderCapabilityAttestation",
    "ProviderCapabilityError",
    "ProviderRequest",
    "ProviderResult",
    "UnknownProviderOutcome",
    "stable_idempotency_key",
]
