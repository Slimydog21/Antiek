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
    FallbackSpendApproval,
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
from .protocol import (
    BillingUnit,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)

T = TypeVar("T")
JsonEvidence = Mapping[str, str | int | bool | None]
Projector = Callable[[CostProjectionRequest], CostProjection]
FallbackRouteAuthorizer = Callable[
    [CostProjectionRequest, "HardCeilingProviderAdapter[Any]"], "PaidRouteAuthorityIdentity"
]

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
    billing_units: frozenset[BillingUnit] = frozenset()

    @property
    def hard_ceiling_eligible(self) -> bool:
        return (
            self.durable_idempotency
            and self.authoritative_reconciliation
            and self.hidden_retries_disabled
            and bool(self.billing_units)
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
    endpoint: str
    capabilities: ProviderCapabilities

    def send_once(
        self,
        operation: object,
        *,
        provider_idempotency_key: str,
        authorized_endpoint: str,
    ) -> ProviderSuccess[T]: ...

    def reconcile(
        self, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderReconciliation: ...


@dataclass(frozen=True)
class ProviderDispatchResult(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    hold: PaidHoldSnapshot
    run: RunSnapshot
    value: T | None = None
    recovered: bool = False


@dataclass(frozen=True, slots=True)
class PaidRouteAuthorityIdentity:
    """Stable identity returned by the server-owned Cycle 75 authority gate."""

    provider_kind: str
    provider_id: str
    endpoint: str
    model: str
    seam_id: str
    operation: str
    rate_snapshot: str
    currency: str
    rates: tuple[ProjectionRate, ...]

    def __post_init__(self) -> None:
        if not all(value for name, value in asdict(self).items() if name != "rates"):
            raise ValueError("paid route authority identity fields must be non-empty")
        if not self.rates:
            raise ValueError("paid route authority identity requires exact rates")


@dataclass(frozen=True)
class PaidFallbackRoute(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    projection_request: CostProjectionRequest
    adapter: HardCeilingProviderAdapter[T]


@dataclass(frozen=True)
class PaidFallbackPreparation:
    chain_id: str
    manifest_sha256: str
    ceiling_cents: int
    currency: str
    maximum_chain_exposure_cents: int


@dataclass(frozen=True)
class _FallbackPlan:
    manifest: FallbackChainManifest
    projections: tuple[CostProjection, ...]
    route_intents: tuple[PaidHoldIntent, ...]
    chain_identity: object
    authorities: tuple[PaidRouteAuthorityIdentity, ...]


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
        fallback_route_authorizer: FallbackRouteAuthorizer | None = None,
    ) -> None:
        self.ledger = ledger
        self._projector = projector
        self._fallback_route_authorizer = fallback_route_authorizer

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
        approval_id: str | None = None,
    ) -> PaidFallbackResult[T]:
        """Dispatch an exactly approved ordered chain; no implicit authority exists."""
        plan = self._fallback_plan(
            binding, logical_operation_id=logical_operation_id, operation=operation,
            routes=routes,
        )
        self.ledger.register_fallback_manifest(
            deterministic_key("research-fallback-manifest-command", plan.manifest.chain_id),
            binding,
            plan.manifest,
        )
        if approval_id is None:
            raise DispatchIneligible("exact durable fallback approval is required")
        self.ledger.require_fallback_approval(approval_id, binding, plan.manifest)

        projections = plan.projections
        route_intents = plan.route_intents
        chain_identity = plan.chain_identity
        authorities = plan.authorities
        manifest = plan.manifest

        attempts: list[PaidFallbackAttempt] = []
        requested_provider = authorities[0].provider_id
        requested_model = authorities[0].model
        for index, (route, projection, authority, route_intent) in enumerate(
            zip(routes, projections, authorities, route_intents, strict=True)
        ):
            try:
                result = self._dispatch_paid_projected(
                    binding,
                    logical_operation_id=f"{logical_operation_id}:fallback:{index}",
                    projection_request=route.projection_request,
                    projection=projection,
                    operation=operation,
                    identity_payload=chain_identity,
                    reservation_identity=(binding.run_id, logical_operation_id, f"fallback:{index}"),
                    provider_route_identity=canonical_digest(authority),
                    precomputed_intent=route_intent,
                    fallback_approval=(approval_id, binding, manifest),
                    adapter=route.adapter,
                )
            except ProviderOutcomeUnknown as exc:
                raise PaidFallbackOutcomeUnknown(
                    exc.hold_id, fallback_index=index, provider=route.adapter.provider,
                    model=route.adapter.model, completed_attempts=tuple(attempts),
                ) from exc
            attempt = PaidFallbackAttempt(
                fallback_index=index, provider=route.adapter.provider,
                model=route.adapter.model, hold=result.hold, recovered=result.recovered,
            )
            attempts.append(attempt)
            if result.hold.state is PaidHoldState.SETTLED:
                return PaidFallbackResult(
                    outcome=PaidFallbackOutcome.SETTLED,
                    requested_provider=requested_provider, requested_model=requested_model,
                    actual_provider=route.adapter.provider, actual_model=route.adapter.model,
                    fallback_index=index, attempts=tuple(attempts), run=result.run,
                    value=result.value, value_available=not result.recovered,
                )
            if result.hold.state is not PaidHoldState.RELEASED:
                raise RuntimeError("paid fallback attempt ended in a non-terminal state")
        return PaidFallbackResult(
            outcome=PaidFallbackOutcome.EXHAUSTED,
            requested_provider=requested_provider, requested_model=requested_model,
            actual_provider=None, actual_model=None, fallback_index=None,
            attempts=tuple(attempts), run=self.ledger.balance(binding.run_id),
        )

    def prepare_paid_fallbacks(
        self,
        binding: RunBinding,
        *,
        logical_operation_id: str,
        operation: object,
        routes: tuple[PaidFallbackRoute[T], ...],
    ) -> PaidFallbackPreparation:
        """Persist an immutable plan without reserving or contacting a provider."""
        plan = self._fallback_plan(
            binding, logical_operation_id=logical_operation_id, operation=operation,
            routes=routes,
        )
        self.ledger.register_fallback_manifest(
            deterministic_key("research-fallback-manifest-command", plan.manifest.chain_id),
            binding, plan.manifest,
        )
        run = self.ledger.balance(binding.run_id)
        return PaidFallbackPreparation(
            chain_id=plan.manifest.chain_id,
            manifest_sha256=canonical_digest(plan.manifest),
            ceiling_cents=run.ceiling_cents,
            currency=binding.currency,
            maximum_chain_exposure_cents=max(
                route.projected_max_cents for route in plan.manifest.routes
            ),
        )

    def approve_paid_fallbacks(
        self,
        command_key: str,
        binding: RunBinding,
        preparation: PaidFallbackPreparation,
    ) -> FallbackSpendApproval:
        return self.ledger.issue_fallback_approval(
            command_key, binding, preparation.chain_id,
            expected_manifest_sha256=preparation.manifest_sha256,
            expected_ceiling_cents=preparation.ceiling_cents,
        )

    def _fallback_plan(
        self,
        binding: RunBinding,
        *,
        logical_operation_id: str,
        operation: object,
        routes: tuple[PaidFallbackRoute[T], ...],
    ) -> _FallbackPlan:
        if not 1 <= len(routes) <= 16:
            raise DispatchIneligible("paid fallback chain must contain 1 to 16 routes")
        if not logical_operation_id:
            raise DispatchIneligible("fallback logical operation id must be non-empty")
        if self._fallback_route_authorizer is None:
            raise DispatchIneligible("paid fallback route authority is not configured")

        projections: list[CostProjection] = []
        authorities: list[PaidRouteAuthorityIdentity] = []
        workload: tuple[str, str, tuple[object, ...]] | None = None
        for route in routes:
            request = route.projection_request
            authority = self._fallback_route_authorizer(request, route.adapter)
            if (
                authority.provider_id,
                authority.model,
                authority.seam_id,
                authority.operation,
            ) != (request.provider, request.model, request.seam_id, request.operation):
                raise DispatchIneligible("route authority differs from requested route")
            projection = self._projector(request)
            if (
                authority.rate_snapshot,
                authority.currency,
                authority.rates,
            ) != (projection.rate_snapshot, projection.currency, projection.rates):
                raise DispatchIneligible("route authority differs from exact projected rates")
            self._require_eligible(projection, request, route.adapter)
            current_workload = (request.seam_id, request.operation, request.bounded_usage)
            if workload is None:
                workload = current_workload
            elif current_workload != workload:
                raise DispatchIneligible(
                    "paid fallback routes must share seam, operation, and bounded usage"
                )
            projections.append(projection)
            authorities.append(authority)

        if len(authorities) != len(set(authorities)):
            raise DispatchIneligible("paid fallback routes must have unique authority")

        chain_identity = {
            "operation": operation,
            "routes": tuple(
                {
                    "authority": authority,
                    "projection_request": route.projection_request,
                    "projection": projection,
                }
                for route, projection, authority in zip(
                    routes, projections, authorities, strict=True
                )
            ),
        }
        operation_digest = canonical_digest(chain_identity)
        chain_id = deterministic_key(
            "research-fallback-chain", binding.run_id, logical_operation_id
        )
        route_intents: list[PaidHoldIntent] = []
        route_manifests: list[FallbackRouteManifest] = []
        for index, (route, projection, authority) in enumerate(
            zip(routes, projections, authorities, strict=True)
        ):
            identity = (binding.run_id, logical_operation_id, f"fallback:{index}")
            reservation_key = deterministic_key("research-reservation", *identity)
            authority_digest = canonical_digest(authority)
            provider_key = deterministic_key(
                "research-provider",
                route.adapter.provider,
                route.adapter.model,
                *(identity + (authority_digest,)),
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
                route_authority_digest=authority_digest,
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
                    route_authority_digest=authority_digest,
                )
            )
        manifest = FallbackChainManifest(
            chain_id=chain_id,
            logical_operation_id=logical_operation_id,
            operation_digest=operation_digest,
            routes=tuple(route_manifests),
        )
        return _FallbackPlan(
            manifest=manifest,
            projections=tuple(projections),
            route_intents=tuple(route_intents),
            chain_identity=chain_identity,
            authorities=tuple(authorities),
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
        provider_route_identity: str | None = None,
        precomputed_intent: PaidHoldIntent | None = None,
        fallback_approval: tuple[str, RunBinding, FallbackChainManifest] | None = None,
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
            "research-provider",
            adapter.provider,
            adapter.model,
            *(identity + ((provider_route_identity,) if provider_route_identity else ())),
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
            route_authority_digest=provider_route_identity,
        )
        intent = precomputed_intent or derived_intent
        if precomputed_intent is not None and precomputed_intent != derived_intent:
            raise RuntimeError("precomputed fallback route identity drifted before dispatch")
        with self.ledger.dispatch_guard(reservation_key) as database_identity:
            # Approval is revalidated inside the same process/database guard
            # immediately before reservation. Later-route recovery therefore
            # cannot race a changed or revoked authority boundary.
            if fallback_approval is not None:
                approval_id, approval_binding, approval_manifest = fallback_approval
                self.ledger.require_fallback_approval(
                    approval_id, approval_binding, approval_manifest
                )
            hold = self.ledger.reserve_paid(
                deterministic_key("research-reserve-command", reservation_key),
                binding,
                intent,
                projection.reservation_cents,
            )
            hold = self.ledger.hold(hold.hold_id)
            if hold.state in (PaidHoldState.SETTLED, PaidHoldState.RELEASED):
                return ProviderDispatchResult(
                    hold=hold, run=self.ledger.balance(hold.run_id), recovered=True
                )
            authorized_endpoint = adapter.endpoint
            if provider_route_identity is not None:
                authority = self._revalidate_route_authority(
                    projection_request,
                    projection,
                    adapter,
                    expected_digest=provider_route_identity,
                )
                authorized_endpoint = authority.endpoint
            if hold.state in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
                self.ledger.assert_dispatch_identity(database_identity)
                return self._reconcile(
                    hold, adapter, authorized_endpoint=authorized_endpoint
                )

            hold = self.ledger.mark_dispatch_possible(
                deterministic_key("research-send-command", hold.hold_id), hold.hold_id
            )
            try:
                self.ledger.assert_dispatch_identity(database_identity)
                success = adapter.send_once(
                    operation,
                    provider_idempotency_key=provider_key,
                    authorized_endpoint=authorized_endpoint,
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
        self,
        hold_id: str,
        adapter: HardCeilingProviderAdapter[T],
        *,
        projection_request: CostProjectionRequest | None = None,
    ) -> ProviderDispatchResult[T]:
        hold = self.ledger.hold(hold_id)
        if (hold.intent.provider, hold.intent.model) != (adapter.provider, adapter.model):
            raise DispatchIneligible("recovery adapter does not match persisted route")
        if not adapter.capabilities.hard_ceiling_eligible:
            raise DispatchIneligible("recovery adapter lacks hard-ceiling capabilities")
        with self.ledger.dispatch_guard(hold.intent.reservation_key) as database_identity:
            hold = self.ledger.hold(hold_id)
            if hold.state in (PaidHoldState.SETTLED, PaidHoldState.RELEASED):
                return ProviderDispatchResult(
                    hold=hold, run=self.ledger.balance(hold.run_id), recovered=True
                )
            authorized_endpoint = adapter.endpoint
            if hold.intent.route_authority_digest is not None:
                if projection_request is None:
                    raise DispatchIneligible("recovery requires exact paid route authority")
                projection = self._projector(projection_request)
                authority = self._revalidate_route_authority(
                    projection_request,
                    projection,
                    adapter,
                    expected_digest=hold.intent.route_authority_digest,
                )
                authorized_endpoint = authority.endpoint
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
                self.ledger.assert_dispatch_identity(database_identity)
                return self._reconcile(
                    hold, adapter, authorized_endpoint=authorized_endpoint
                )
            return ProviderDispatchResult(
                hold=hold, run=self.ledger.balance(hold.run_id), recovered=True
            )

    def _revalidate_route_authority(
        self,
        request: CostProjectionRequest,
        projection: CostProjection,
        adapter: HardCeilingProviderAdapter[Any],
        *,
        expected_digest: str,
    ) -> PaidRouteAuthorityIdentity:
        if self._fallback_route_authorizer is None:
            raise DispatchIneligible("paid fallback route authority is not configured")
        authority = self._fallback_route_authorizer(request, adapter)
        if canonical_digest(authority) != expected_digest:
            raise DispatchIneligible("recovery route authority changed")
        if (
            authority.rate_snapshot,
            authority.currency,
            authority.rates,
        ) != (projection.rate_snapshot, projection.currency, projection.rates):
            raise DispatchIneligible("route authority differs from exact projected rates")
        self._require_eligible(projection, request, adapter)
        return authority

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
        self,
        hold: PaidHoldSnapshot,
        adapter: HardCeilingProviderAdapter[T],
        *,
        authorized_endpoint: str,
    ) -> ProviderDispatchResult[T]:
        try:
            result = adapter.reconcile(
                provider_idempotency_key=hold.intent.provider_idempotency_key,
                authorized_endpoint=authorized_endpoint,
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
        projection_units = frozenset(rate.unit for rate in projection.rates)
        if adapter.capabilities.billing_units != projection_units:
            raise DispatchIneligible("adapter billing units differ from projected route")
