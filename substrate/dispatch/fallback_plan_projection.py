"""Pure operator preview for an ordered hard-ceiling fallback plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from runtime.research_runner.protocol import (
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
)
from runtime.research_runner.provider_route_authority import RouteExecutionStatus

_MAX_ROUTES = 16
_MAX_IDENTITY_CHARS = 256


@dataclass(frozen=True, slots=True)
class ConfiguredFallbackRoute:
    provider: str
    model: str

    def __post_init__(self) -> None:
        _identity(self.provider, "provider")
        _identity(self.model, "model")


@dataclass(frozen=True, slots=True)
class FallbackExecutionAuthority:
    hard_ceiling_eligible: bool
    execution_status: RouteExecutionStatus

    def __post_init__(self) -> None:
        if type(self.hard_ceiling_eligible) is not bool:
            raise TypeError("hard ceiling eligibility must be bool")
        if not isinstance(self.execution_status, RouteExecutionStatus):
            raise TypeError("execution status must be RouteExecutionStatus")
        if self.hard_ceiling_eligible is not (
            self.execution_status is RouteExecutionStatus.EXECUTABLE
        ):
            raise ValueError("execution status conflicts with hard ceiling eligibility")


class CostProjector(Protocol):
    def __call__(self, request: CostProjectionRequest) -> CostProjection: ...


ExecutionResolver = Callable[[ConfiguredFallbackRoute], FallbackExecutionAuthority]


@dataclass(frozen=True, slots=True)
class FallbackPlanRoute:
    fallback_index: int
    provider: str
    model: str
    registered: bool
    projection: CostProjection
    hard_ceiling_eligible: bool
    execution_status: RouteExecutionStatus

    def __post_init__(self) -> None:
        if (
            isinstance(self.fallback_index, bool)
            or not isinstance(self.fallback_index, int)
            or self.fallback_index < 0
        ):
            raise ValueError("fallback index must be a non-negative integer")
        _identity(self.provider, "provider")
        _identity(self.model, "model")
        if type(self.registered) is not bool:
            raise TypeError("registered must be bool")
        if type(self.projection) is not CostProjection:
            raise TypeError("route projection must be CostProjection")
        self.projection.__post_init__()
        if (self.projection.provider, self.projection.model) != (
            self.provider,
            self.model,
        ):
            raise ValueError("route projection identity differs from configured route")
        FallbackExecutionAuthority(
            self.hard_ceiling_eligible,
            self.execution_status,
        )


@dataclass(frozen=True, slots=True)
class FallbackPlanProjection:
    """Preview of ``dispatch_paid_fallbacks``, not the zero-cost gateway path."""
    tier: str
    routes: tuple[FallbackPlanRoute, ...]
    status: str
    maximum_chain_exposure_cents: int | None
    remaining_budget_usd: Decimal | None
    would_exceed_budget: bool | None
    authority: str = "advisory_fallback_plan"

    def __post_init__(self) -> None:
        _identity(self.tier, "tier")
        if self.authority != "advisory_fallback_plan":
            raise ValueError("fallback plan authority must remain advisory")
        if type(self.routes) is not tuple or not 1 <= len(self.routes) <= _MAX_ROUTES:
            raise ValueError("fallback plan must contain 1 to 16 routes")
        for route in self.routes:
            if type(route) is not FallbackPlanRoute:
                raise TypeError("fallback plan route has an invalid type")
            route.__post_init__()
        if [route.fallback_index for route in self.routes] != list(range(len(self.routes))):
            raise ValueError("fallback route indexes must be contiguous and ordered")
        identities = [(route.provider, route.model) for route in self.routes]
        if len(identities) != len(set(identities)):
            raise ValueError("fallback route identities must be unique")
        workload = {
            (
                route.projection.seam_id,
                route.projection.operation,
                route.projection.bounded_usage,
            )
            for route in self.routes
        }
        if len(workload) != 1:
            raise ValueError("fallback routes must share one exact bounded workload")
        # Cycle 76's paid fallback gateway accepts only hold-eligible routes.
        # ZERO_COST_RECEIPT executes through prepare_zero_cost as a separate
        # operation and cannot be advertised as one link in this paid chain.
        executable = all(
            route.registered
            and route.hard_ceiling_eligible
            and route.projection.disposition is ProjectionDisposition.HOLD_ELIGIBLE
            for route in self.routes
        )
        expected_status = "executable" if executable else "blocked"
        if self.status != expected_status:
            raise ValueError("fallback plan status conflicts with route authority")
        expected_exposure = (
            max(route.projection.reservation_cents for route in self.routes)
            if executable
            else None
        )
        if self.maximum_chain_exposure_cents != expected_exposure:
            raise ValueError("fallback chain exposure must be max eligible reservation")
        if self.remaining_budget_usd is not None and (
            not isinstance(self.remaining_budget_usd, Decimal)
            or not self.remaining_budget_usd.is_finite()
            or self.remaining_budget_usd < 0
        ):
            raise ValueError("remaining budget must be a finite non-negative Decimal or None")
        if self.would_exceed_budget is not None and type(self.would_exceed_budget) is not bool:
            raise TypeError("budget verdict must be bool or None")
        expected_verdict = (
            Decimal(expected_exposure) / Decimal(100) > self.remaining_budget_usd
            if expected_exposure is not None and self.remaining_budget_usd is not None
            else None
        )
        if self.would_exceed_budget is not expected_verdict:
            raise ValueError("fallback plan budget verdict conflicts with peak exposure")


def resolve_fallback_plan(
    *,
    tier: str,
    configured_routes: tuple[ConfiguredFallbackRoute, ...],
    registered_providers: frozenset[str],
    seam_id: str,
    operation: str,
    bounded_usage: tuple[BoundedUsage, ...],
    remaining_budget_usd: Decimal | None,
    project: CostProjector,
    resolve_execution: ExecutionResolver,
) -> FallbackPlanProjection:
    """Project every route without reserving, dispatching, or mutating state."""
    _identity(tier, "tier")
    _identity(seam_id, "seam id")
    _identity(operation, "operation")
    if type(configured_routes) is not tuple or not 1 <= len(configured_routes) <= _MAX_ROUTES:
        raise ValueError("configured fallback chain must contain 1 to 16 routes")
    if type(registered_providers) is not frozenset or not all(
        type(provider) is str for provider in registered_providers
    ):
        raise TypeError("registered providers must be a frozenset of strings")
    if type(bounded_usage) is not tuple or not bounded_usage:
        raise ValueError("fallback plan requires bounded usage")
    if remaining_budget_usd is not None and (
        not isinstance(remaining_budget_usd, Decimal)
        or not remaining_budget_usd.is_finite()
        or remaining_budget_usd < 0
    ):
        raise ValueError("remaining budget must be a finite non-negative Decimal or None")
    identities = [(route.provider, route.model) for route in configured_routes]
    if len(identities) != len(set(identities)):
        raise ValueError("configured fallback routes must be unique")

    routes: list[FallbackPlanRoute] = []
    for index, configured in enumerate(configured_routes):
        if type(configured) is not ConfiguredFallbackRoute:
            raise TypeError("configured route has an invalid type")
        configured.__post_init__()
        request = CostProjectionRequest(
            seam_id=seam_id,
            provider=configured.provider,
            model=configured.model,
            operation=operation,
            bounded_usage=bounded_usage,
        )
        projection = project(request)
        if type(projection) is not CostProjection:
            raise TypeError("cost projector returned an invalid value")
        projection.__post_init__()
        if (
            projection.seam_id,
            projection.provider,
            projection.model,
            projection.operation,
            projection.bounded_usage,
        ) != (
            seam_id,
            configured.provider,
            configured.model,
            operation,
            bounded_usage,
        ):
            raise ValueError("cost projection differs from the requested fallback route")
        execution = resolve_execution(configured)
        if type(execution) is not FallbackExecutionAuthority:
            raise TypeError("execution resolver returned an invalid value")
        execution.__post_init__()
        routes.append(
            FallbackPlanRoute(
                fallback_index=index,
                provider=configured.provider,
                model=configured.model,
                registered=configured.provider in registered_providers,
                projection=projection,
                hard_ceiling_eligible=execution.hard_ceiling_eligible,
                execution_status=execution.execution_status,
            )
        )

    # This mirrors ResearchProviderGateway.dispatch_paid_fallbacks, whose
    # preflight rejects any disposition other than HOLD_ELIGIBLE.
    executable = all(
        route.registered
        and route.hard_ceiling_eligible
        and route.projection.disposition is ProjectionDisposition.HOLD_ELIGIBLE
        for route in routes
    )
    exposure = max(route.projection.reservation_cents for route in routes) if executable else None
    would_exceed = None
    if exposure is not None and remaining_budget_usd is not None:
        would_exceed = Decimal(exposure) / Decimal(100) > remaining_budget_usd
    return FallbackPlanProjection(
        tier=tier,
        routes=tuple(routes),
        status="executable" if executable else "blocked",
        maximum_chain_exposure_cents=exposure,
        remaining_budget_usd=remaining_budget_usd,
        would_exceed_budget=would_exceed,
    )


def _identity(value: object, name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_IDENTITY_CHARS
    ):
        raise ValueError(f"{name} must be a trimmed non-empty bounded string")
    return value


__all__ = [
    "ConfiguredFallbackRoute",
    "FallbackExecutionAuthority",
    "FallbackPlanProjection",
    "FallbackPlanRoute",
    "resolve_fallback_plan",
]
