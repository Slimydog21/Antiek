"""Hard-ceiling provider dispatch and deterministic recovery.

The gateway is the sole place where a hard-ceiling research run may cross a
billable provider boundary.  It composes the server-owned cost projector with
the durable spend ledger; adapters contribute transport and provider evidence,
never prices or authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Generic, Protocol, TypeVar

from substrate.research_spend import (
    FallbackChainManifest,
    FallbackRouteManifest,
    IdempotencyConflict,
    InvalidTransition,
    PaidHoldIntent,
    PaidHoldSnapshot,
    PaidHoldState,
    ResearchSpendLedger,
    RunBinding,
    RunSnapshot,
    ZeroCostAttemptSnapshot,
    ZeroCostIntent,
    ZeroCostState,
    ZeroReplayClass,
)

from .cost_projection import project_cascade_cost
from .protocol import CostProjection, CostProjectionRequest, ProjectionDisposition

T = TypeVar("T")
JsonEvidence = Mapping[str, str | int | bool | None]
Projector = Callable[[CostProjectionRequest], CostProjection]

# Every SPR-01 inventory seam has one hard-mode disposition. Tests compare the
# keys to dispatch_inventory.json so a newly reachable call cannot land without
# an explicit gateway or fail-closed decision.
HARD_MODE_DISPATCH_POLICY: Mapping[str, str] = {
    "cascade.operator.spend_approval": "zero_cost_receipt",
    "cascade.session.launch": "zero_cost_receipt",
    "cascade.plan.decomposer": "refused_before_dispatch",
    "cascade.gather.contract_stub": "zero_cost_receipt",
    "cascade.gather.exa.search": "refused_before_dispatch",
    "cascade.gather.url.fetch": "unreachable_when_exa_is_refused",
    "cascade.gather.embedding.bootstrap": "zero_cost_receipt",
    "cascade.tail.synthesizer": "refused_before_dispatch",
    "cascade.tail.knowledge_extractor": "unreachable_when_tail_is_refused",
}
HARD_MODE_SKIPPED_STAGES = tuple(
    seam_id.rsplit(".", 1)[-1]
    for seam_id in HARD_MODE_DISPATCH_POLICY
    if seam_id.startswith("cascade.tail.")
)


class DispatchIneligible(RuntimeError):
    """The selected route cannot honor the hard-ceiling contract."""


class ProviderOutcomeUnknown(RuntimeError):
    """A request may have reached a provider and must not be retried blindly."""

    def __init__(self, hold_id: str, message: str) -> None:
        self.hold_id = hold_id
        super().__init__(message)


class ProviderNotSent(RuntimeError):
    """Authoritative adapter proof that no billable operation was accepted.

    Adapters must raise this only from provider-authoritative evidence. A local
    transport guess could release a hold for work that is later billed.
    """

    def __init__(self, message: str, *, evidence: JsonEvidence) -> None:
        if not evidence:
            raise ValueError("not-sent proof requires provider evidence")
        self.evidence = evidence
        super().__init__(message)


@dataclass(frozen=True)
class ProviderCapabilities:
    durable_idempotency: bool
    authoritative_reconciliation: bool
    hidden_retries_disabled: bool

    @property
    def hard_ceiling_eligible(self) -> bool:
        return (
            self.durable_idempotency
            and self.authoritative_reconciliation
            and self.hidden_retries_disabled
        )


@dataclass(frozen=True)
class ProviderSuccess(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    value: T
    actual_cents: int
    evidence: JsonEvidence


class ReconciliationStatus(StrEnum):
    CHARGED = "charged"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderReconciliation:
    status: ReconciliationStatus
    evidence: JsonEvidence
    actual_cents: int | None = None


class HardCeilingProviderAdapter(Protocol[T]):
    provider: str
    model: str
    capabilities: ProviderCapabilities

    def send_once(
        self, operation: object, *, provider_idempotency_key: str
    ) -> ProviderSuccess[T]: ...

    def reconcile(self, *, provider_idempotency_key: str) -> ProviderReconciliation: ...


@dataclass(frozen=True)
class ProviderDispatchResult(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    hold: PaidHoldSnapshot
    run: RunSnapshot
    value: T | None = None
    recovered: bool = False


@dataclass(frozen=True)
class PaidFallbackRoute(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    projection_request: CostProjectionRequest
    adapter: HardCeilingProviderAdapter[T]


@dataclass(frozen=True)
class PaidFallbackAttempt:
    fallback_index: int
    provider: str
    model: str
    hold: PaidHoldSnapshot
    recovered: bool


class PaidFallbackOutcome(StrEnum):
    SETTLED = "settled"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True)
class PaidFallbackResult(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    outcome: PaidFallbackOutcome
    requested_provider: str
    requested_model: str
    actual_provider: str | None
    actual_model: str | None
    fallback_index: int | None
    attempts: tuple[PaidFallbackAttempt, ...]
    run: RunSnapshot
    value: T | None = None
    value_available: bool = False


class PaidFallbackOutcomeUnknown(ProviderOutcomeUnknown):
    """One fallback attempt may be charged, so no later route may run."""

    def __init__(
        self,
        hold_id: str,
        *,
        fallback_index: int,
        provider: str,
        model: str,
        completed_attempts: tuple[PaidFallbackAttempt, ...],
    ) -> None:
        self.fallback_index = fallback_index
        self.provider = provider
        self.model = model
        self.completed_attempts = completed_attempts
        super().__init__(hold_id, "fallback outcome is unknown; reconcile before continuing")


@dataclass(frozen=True)
class ZeroCostReceipt:
    attempt: ZeroCostAttemptSnapshot
    replayed: bool


def canonical_digest(value: object) -> str:
    """Hash structured intent without accepting repr-dependent identities."""

    def normalize(item: object) -> object:
        if is_dataclass(item) and not isinstance(item, type):
            return normalize(asdict(item))
        if isinstance(item, StrEnum):
            return item.value
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, Mapping):
            if not all(isinstance(key, str) for key in item):
                raise TypeError("canonical mapping keys must be strings")
            return {key: normalize(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(value) for value in item]
        if item is None or isinstance(item, (str, int, bool)):
            return item
        raise TypeError(f"unsupported canonical value: {type(item).__name__}")

    payload = json.dumps(
        normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_key(namespace: str, *parts: str) -> str:
    if not namespace or any(not part for part in parts):
        raise ValueError("deterministic key parts must be non-empty")
    digest = canonical_digest({"namespace": namespace, "parts": parts})
    return f"{namespace}:{digest}"


class ResearchProviderGateway:
    """Project, reserve, send once, and reconcile hard-ceiling operations."""

    def __init__(
        self,
        ledger: ResearchSpendLedger,
        *,
        projector: Projector = project_cascade_cost,
    ) -> None:
        self.ledger = ledger
        self._projector = projector

    def create_or_reopen_run(
        self, binding: RunBinding, *, ceiling_cents: int
    ) -> RunSnapshot:
        self.ledger.ensure_schema()
        return self.ledger.create_or_reopen_run(
            deterministic_key("research-run", binding.run_id), binding, ceiling_cents
        )

    def dispatch_paid(
        self,
        binding: RunBinding,
        *,
        logical_operation_id: str,
        projection_request: CostProjectionRequest,
        operation: object,
        adapter: HardCeilingProviderAdapter[T],
    ) -> ProviderDispatchResult[T]:
        projection = self._projector(projection_request)
        return self._dispatch_paid_projected(
            binding,
            logical_operation_id=logical_operation_id,
            projection_request=projection_request,
            projection=projection,
            operation=operation,
            adapter=adapter,
        )

    def dispatch_paid_fallbacks(
        self,
        binding: RunBinding,
        *,
        logical_operation_id: str,
        operation: object,
        routes: tuple[PaidFallbackRoute[T], ...],
    ) -> PaidFallbackResult[T]:
        """Dispatch ordered routes; only authoritative release advances."""
        if not 1 <= len(routes) <= 16:
            raise DispatchIneligible("paid fallback chain must contain 1 to 16 routes")
        if not logical_operation_id:
            raise DispatchIneligible("fallback logical operation id must be non-empty")

        route_keys = [
            (route.projection_request.provider, route.projection_request.model)
            for route in routes
        ]
        if len(route_keys) != len(set(route_keys)):
            raise DispatchIneligible("paid fallback routes must be unique")

        projections: list[CostProjection] = []
        workload: tuple[str, str, tuple[object, ...]] | None = None
        for route in routes:
            request = route.projection_request
            projection = self._projector(request)
            self._require_eligible(projection, request, route.adapter)
            current_workload = (request.seam_id, request.operation, request.bounded_usage)
            if workload is None:
                workload = current_workload
            elif current_workload != workload:
                raise DispatchIneligible(
                    "paid fallback routes must share seam, operation, and bounded usage"
                )
            projections.append(projection)

        chain_identity = {
            "operation": operation,
            "routes": tuple(
                {
                    "projection_request": route.projection_request,
                    "projection": projection,
                }
                for route, projection in zip(routes, projections, strict=True)
            ),
        }
        operation_digest = canonical_digest(chain_identity)
        chain_id = deterministic_key(
            "research-fallback-chain", binding.run_id, logical_operation_id
        )
        route_intents: list[PaidHoldIntent] = []
        route_manifests: list[FallbackRouteManifest] = []
        for index, (route, projection) in enumerate(zip(routes, projections, strict=True)):
            identity = (binding.run_id, logical_operation_id, f"fallback:{index}")
            reservation_key = deterministic_key("research-reservation", *identity)
            provider_key = deterministic_key(
                "research-provider", route.adapter.provider, route.adapter.model, *identity
            )
            intent = PaidHoldIntent(
                reservation_key=reservation_key,
                seam_id=projection.seam_id,
                provider=route.adapter.provider,
                model=route.adapter.model,
                operation=projection.operation,
                operation_digest=operation_digest,
                projection_digest=canonical_digest(projection),
                rate_snapshot=projection.rate_snapshot,
                provider_idempotency_key=provider_key,
            )
            route_intents.append(intent)
            route_manifests.append(
                FallbackRouteManifest(
                    fallback_index=index,
                    seam_id=intent.seam_id,
                    provider=intent.provider,
                    model=intent.model,
                    operation=intent.operation,
                    operation_digest=intent.operation_digest,
                    projection_digest=intent.projection_digest,
                    rate_snapshot=intent.rate_snapshot,
                    projected_max_cents=projection.reservation_cents,
                    reservation_key=intent.reservation_key,
                    provider_idempotency_key=intent.provider_idempotency_key,
                )
            )
        manifest = FallbackChainManifest(
            chain_id=chain_id,
            logical_operation_id=logical_operation_id,
            operation_digest=operation_digest,
            routes=tuple(route_manifests),
        )
        self.ledger.register_fallback_manifest(
            deterministic_key("research-fallback-manifest-command", chain_id),
            binding,
            manifest,
        )

        attempts: list[PaidFallbackAttempt] = []
        requested_provider, requested_model = route_keys[0]
        for index, (route, projection, route_intent) in enumerate(
            zip(routes, projections, route_intents, strict=True)
        ):
            try:
                result = self._dispatch_paid_projected(
                    binding,
                    logical_operation_id=f"{logical_operation_id}:fallback:{index}",
                    projection_request=route.projection_request,
                    projection=projection,
                    operation=operation,
                    identity_payload=chain_identity,
                    reservation_identity=(
                        binding.run_id,
                        logical_operation_id,
                        f"fallback:{index}",
                    ),
                    precomputed_intent=route_intent,
                    adapter=route.adapter,
                )
            except ProviderOutcomeUnknown as exc:
                raise PaidFallbackOutcomeUnknown(
                    exc.hold_id,
                    fallback_index=index,
                    provider=route.adapter.provider,
                    model=route.adapter.model,
                    completed_attempts=tuple(attempts),
                ) from exc
            attempt = PaidFallbackAttempt(
                fallback_index=index,
                provider=route.adapter.provider,
                model=route.adapter.model,
                hold=result.hold,
                recovered=result.recovered,
            )
            attempts.append(attempt)
            if result.hold.state is PaidHoldState.SETTLED:
                return PaidFallbackResult(
                    outcome=PaidFallbackOutcome.SETTLED,
                    requested_provider=requested_provider,
                    requested_model=requested_model,
                    actual_provider=route.adapter.provider,
                    actual_model=route.adapter.model,
                    fallback_index=index,
                    attempts=tuple(attempts),
                    run=result.run,
                    value=result.value,
                    value_available=not result.recovered,
                )
            if result.hold.state is not PaidHoldState.RELEASED:
                raise RuntimeError("paid fallback attempt ended in a non-terminal state")

        return PaidFallbackResult(
            outcome=PaidFallbackOutcome.EXHAUSTED,
            requested_provider=requested_provider,
            requested_model=requested_model,
            actual_provider=None,
            actual_model=None,
            fallback_index=None,
            attempts=tuple(attempts),
            run=self.ledger.balance(binding.run_id),
        )

    def _dispatch_paid_projected(
        self,
        binding: RunBinding,
        *,
        logical_operation_id: str,
        projection_request: CostProjectionRequest,
        projection: CostProjection,
        operation: object,
        identity_payload: object | None = None,
        reservation_identity: tuple[str, ...] | None = None,
        precomputed_intent: PaidHoldIntent | None = None,
        adapter: HardCeilingProviderAdapter[T],
    ) -> ProviderDispatchResult[T]:
        self._require_eligible(projection, projection_request, adapter)
        operation_digest = canonical_digest(
            operation if identity_payload is None else identity_payload
        )
        projection_digest = canonical_digest(projection)
        identity = reservation_identity or (
            binding.run_id,
            logical_operation_id,
            operation_digest,
        )
        reservation_key = deterministic_key("research-reservation", *identity)
        provider_key = deterministic_key(
            "research-provider", adapter.provider, adapter.model, *identity
        )
        derived_intent = PaidHoldIntent(
            reservation_key=reservation_key,
            seam_id=projection.seam_id,
            provider=adapter.provider,
            model=adapter.model,
            operation=projection.operation,
            operation_digest=operation_digest,
            projection_digest=projection_digest,
            rate_snapshot=projection.rate_snapshot,
            provider_idempotency_key=provider_key,
        )
        intent = precomputed_intent or derived_intent
        if precomputed_intent is not None and precomputed_intent != derived_intent:
            raise RuntimeError("precomputed fallback route identity drifted before dispatch")
        hold = self.ledger.reserve_paid(
            deterministic_key("research-reserve-command", reservation_key),
            binding,
            intent,
            projection.reservation_cents,
        )
        if hold.state in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
            return self._reconcile(hold, adapter)
        if hold.state in (PaidHoldState.SETTLED, PaidHoldState.RELEASED):
            return ProviderDispatchResult(
                hold=hold, run=self.ledger.balance(hold.run_id), recovered=True
            )

        hold = self.ledger.mark_dispatch_possible(
            deterministic_key("research-send-command", hold.hold_id), hold.hold_id
        )
        try:
            success = adapter.send_once(
                operation, provider_idempotency_key=provider_key
            )
        except ProviderNotSent as exc:
            self._release_or_converge(
                deterministic_key("research-not-sent-command", hold.hold_id),
                hold,
                exc.evidence,
            )
            return ProviderDispatchResult(
                hold=self.ledger.hold(hold.hold_id),
                run=self.ledger.balance(hold.run_id),
            )
        except Exception as exc:
            self._retain_unknown(hold, {"exception_type": type(exc).__name__})
            raise ProviderOutcomeUnknown(
                hold.hold_id, "provider outcome is unknown; reconcile before retry"
            ) from exc

        try:
            self._validate_success(success)
        except (TypeError, ValueError) as exc:
            self._retain_unknown(hold, {"invalid_provider_result": type(exc).__name__})
            raise ProviderOutcomeUnknown(
                hold.hold_id, "provider returned non-authoritative billing evidence"
            ) from exc
        run = self._settle_or_converge(
            deterministic_key("research-settle-command", hold.hold_id),
            hold,
            success.actual_cents,
            success.evidence,
        )
        return ProviderDispatchResult(
            hold=self.ledger.hold(hold.hold_id), run=run, value=success.value
        )

    def recover_paid(
        self, hold_id: str, adapter: HardCeilingProviderAdapter[T]
    ) -> ProviderDispatchResult[T]:
        hold = self.ledger.hold(hold_id)
        if (hold.intent.provider, hold.intent.model) != (adapter.provider, adapter.model):
            raise DispatchIneligible("recovery adapter does not match persisted route")
        if not adapter.capabilities.hard_ceiling_eligible:
            raise DispatchIneligible("recovery adapter lacks hard-ceiling capabilities")
        if hold.state is PaidHoldState.RESERVED:
            self.ledger.release(
                deterministic_key("research-restart-unsent", hold.hold_id),
                hold.hold_id,
                {"restart_proof": "send marker absent"},
            )
            return ProviderDispatchResult(
                hold=self.ledger.hold(hold_id),
                run=self.ledger.balance(hold.run_id),
                recovered=True,
            )
        if hold.state in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
            return self._reconcile(hold, adapter)
        return ProviderDispatchResult(
            hold=hold, run=self.ledger.balance(hold.run_id), recovered=True
        )

    def prepare_zero_cost(
        self,
        binding: RunBinding,
        *,
        logical_operation_id: str,
        projection_request: CostProjectionRequest,
        operation_payload: object,
        replay_class: ZeroReplayClass,
    ) -> ZeroCostReceipt:
        projection = self._projector(projection_request)
        if projection.disposition is not ProjectionDisposition.ZERO_COST_RECEIPT:
            reason = projection.ineligibility.value if projection.ineligibility else "ineligible"
            raise DispatchIneligible(f"zero-cost dispatch refused: {reason}")
        operation_digest = canonical_digest(
            {"operation_payload": operation_payload, "projection": projection}
        )
        attempt_key = deterministic_key(
            "research-zero", binding.run_id, logical_operation_id, operation_digest
        )
        intent = ZeroCostIntent(
            attempt_key=attempt_key,
            seam_id=projection.seam_id,
            operation=projection.operation,
            operation_digest=operation_digest,
            replay_class=replay_class,
        )
        existing = self.ledger.zero_attempt_for_key(binding.run_id, attempt_key)
        if existing is not None:
            if existing.intent != intent:
                raise DispatchIneligible("zero-cost attempt key changed intent")
            return ZeroCostReceipt(existing, replayed=True)
        attempt = self.ledger.prepare_zero_cost(
            deterministic_key("research-zero-prepare", attempt_key), binding, intent
        )
        return ZeroCostReceipt(attempt, replayed=False)

    def complete_zero_cost(
        self, receipt: ZeroCostReceipt, *, outcome: object
    ) -> ZeroCostAttemptSnapshot:
        digest = canonical_digest(outcome)
        if receipt.attempt.state is not ZeroCostState.PREPARED:
            return receipt.attempt
        return self.ledger.complete_zero_cost(
            deterministic_key("research-zero-complete", receipt.attempt.attempt_id),
            receipt.attempt.attempt_id,
            digest,
        )

    def fail_zero_cost(
        self, receipt: ZeroCostReceipt, *, outcome: object
    ) -> ZeroCostAttemptSnapshot:
        digest = canonical_digest(outcome)
        if receipt.attempt.state is not ZeroCostState.PREPARED:
            return receipt.attempt
        return self.ledger.fail_zero_cost(
            deterministic_key("research-zero-fail", receipt.attempt.attempt_id),
            receipt.attempt.attempt_id,
            digest,
        )

    def _reconcile(
        self, hold: PaidHoldSnapshot, adapter: HardCeilingProviderAdapter[T]
    ) -> ProviderDispatchResult[T]:
        try:
            result = adapter.reconcile(
                provider_idempotency_key=hold.intent.provider_idempotency_key
            )
        except Exception as exc:
            self._retain_unknown(hold, {"reconciliation_error": type(exc).__name__})
            raise ProviderOutcomeUnknown(
                hold.hold_id, "provider reconciliation is unavailable"
            ) from exc
        try:
            self._validate_evidence(result.evidence)
        except (TypeError, ValueError) as exc:
            self._retain_unknown(hold, {"reconciliation_evidence": "missing"})
            raise ProviderOutcomeUnknown(
                hold.hold_id, "provider reconciliation supplied invalid evidence"
            ) from exc
        if result.status is ReconciliationStatus.NOT_FOUND:
            if result.actual_cents is not None:
                self._retain_unknown(hold, {"reconciliation_result": "contradictory"})
                raise ProviderOutcomeUnknown(
                    hold.hold_id, "not-found reconciliation included a billing amount"
                )
            run = self._release_or_converge(
                deterministic_key("research-reconcile-release", hold.hold_id),
                hold,
                result.evidence,
            )
        elif result.status is ReconciliationStatus.CHARGED:
            if result.actual_cents is None:
                self._retain_unknown(hold, {"reconciliation_actual": "missing"})
                raise ProviderOutcomeUnknown(
                    hold.hold_id, "provider billing amount remains unknown"
                )
            if (
                isinstance(result.actual_cents, bool)
                or not isinstance(result.actual_cents, int)
                or not 0 <= result.actual_cents <= (1 << 63) - 1
            ):
                self._retain_unknown(hold, {"reconciliation_actual": "invalid"})
                raise ProviderOutcomeUnknown(
                    hold.hold_id, "provider billing amount is invalid"
                )
            run = self._settle_or_converge(
                deterministic_key("research-reconcile-settle", hold.hold_id),
                hold,
                result.actual_cents,
                result.evidence,
            )
        else:
            self._retain_unknown(hold, result.evidence)
            raise ProviderOutcomeUnknown(hold.hold_id, "provider outcome remains unknown")
        return ProviderDispatchResult(
            hold=self.ledger.hold(hold.hold_id), run=run, recovered=True
        )

    def _release_or_converge(
        self, command_key: str, hold: PaidHoldSnapshot, evidence: JsonEvidence
    ) -> RunSnapshot:
        try:
            return self.ledger.release(
                command_key,
                hold.hold_id,
                evidence,
                provider_authoritative=True,
            )
        except (IdempotencyConflict, InvalidTransition) as exc:
            current = self.ledger.hold(hold.hold_id)
            if current.state is PaidHoldState.RELEASED:
                return self.ledger.balance(hold.run_id)
            raise ProviderOutcomeUnknown(
                hold.hold_id, "provider terminal evidence conflicts with settled hold"
            ) from exc

    def _settle_or_converge(
        self,
        command_key: str,
        hold: PaidHoldSnapshot,
        actual_cents: int,
        evidence: JsonEvidence,
    ) -> RunSnapshot:
        try:
            return self.ledger.settle(
                command_key,
                hold.hold_id,
                actual_cents,
                evidence,
            )
        except (IdempotencyConflict, InvalidTransition) as exc:
            current = self.ledger.hold(hold.hold_id)
            if current.state is PaidHoldState.SETTLED and current.actual_cents == actual_cents:
                return self.ledger.balance(hold.run_id)
            raise ProviderOutcomeUnknown(
                hold.hold_id, "provider terminal evidence conflicts with resolved hold"
            ) from exc

    def _retain_unknown(self, hold: PaidHoldSnapshot, evidence: JsonEvidence) -> None:
        current = self.ledger.hold(hold.hold_id)
        if current.state is PaidHoldState.DISPATCH_POSSIBLE:
            self.ledger.mark_unknown(
                deterministic_key("research-unknown-command", hold.hold_id),
                hold.hold_id,
                evidence,
            )

    @staticmethod
    def _validate_success(success: ProviderSuccess[Any]) -> None:
        if isinstance(success.actual_cents, bool) or not isinstance(success.actual_cents, int):
            raise TypeError("actual_cents must be an integer")
        if not 0 <= success.actual_cents <= (1 << 63) - 1:
            raise ValueError("actual_cents is outside the ledger range")
        ResearchProviderGateway._validate_evidence(success.evidence)

    @staticmethod
    def _validate_evidence(evidence: JsonEvidence) -> None:
        if not evidence:
            raise ValueError("authoritative provider evidence is required")
        for key, value in evidence.items():
            if not isinstance(key, str) or not key:
                raise TypeError("provider evidence keys must be non-empty strings")
            if isinstance(value, float) or not isinstance(
                value, (str, int, bool, type(None))
            ):
                raise TypeError("provider evidence values must be JSON scalars without floats")

    @staticmethod
    def _require_eligible(
        projection: CostProjection,
        request: CostProjectionRequest,
        adapter: HardCeilingProviderAdapter[Any],
    ) -> None:
        if projection.disposition is not ProjectionDisposition.HOLD_ELIGIBLE:
            reason = projection.ineligibility.value if projection.ineligibility else "ineligible"
            raise DispatchIneligible(f"hard-ceiling dispatch refused: {reason}")
        if (
            projection.seam_id,
            projection.provider,
            projection.model,
            projection.operation,
            projection.bounded_usage,
        ) != (
            request.seam_id,
            request.provider,
            request.model,
            request.operation,
            request.bounded_usage,
        ):
            raise DispatchIneligible("projection differs from requested route or workload")
        if (adapter.provider, adapter.model) != (request.provider, request.model):
            raise DispatchIneligible("adapter route differs from projected route")
        if not adapter.capabilities.hard_ceiling_eligible:
            raise DispatchIneligible("adapter lacks hard-ceiling capabilities")
