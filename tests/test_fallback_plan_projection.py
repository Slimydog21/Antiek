"""Pure contract tests for the operator-visible fallback plan."""

from __future__ import annotations

from decimal import Decimal

import pytest

from interfaces.research.api import settings_budget
from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)
from runtime.research_runner.provider_route_authority import RouteExecutionStatus
from substrate.dispatch.fallback_plan_projection import (
    ConfiguredFallbackRoute,
    FallbackExecutionAuthority,
    FallbackPlanProjection,
    resolve_fallback_plan,
)

_USAGE = (
    BoundedUsage(BillingUnit.INPUT_TOKEN, 1_000),
    BoundedUsage(BillingUnit.OUTPUT_TOKEN, 500),
)
_ROUTES = (
    ConfiguredFallbackRoute("primary", "model-a"),
    ConfiguredFallbackRoute("fallback", "model-b"),
)


def _project(cents: dict[tuple[str, str], int]):
    def project(request: CostProjectionRequest) -> CostProjection:
        reservation = cents[(request.provider, request.model)]
        input_rate = Decimal(reservation) / Decimal(100) / Decimal(1_000)
        return CostProjection(
            seam_id=request.seam_id,
            provider=request.provider,
            model=request.model,
            operation=request.operation,
            bounded_usage=request.bounded_usage,
            rates=(
                ProjectionRate(BillingUnit.INPUT_TOKEN, input_rate),
                ProjectionRate(BillingUnit.OUTPUT_TOKEN, Decimal(0)),
            ),
            rate_snapshot="qualified-v1",
            currency="USD",
            maximum_cost_usd=Decimal(reservation) / Decimal(100),
            reservation_cents=reservation,
            disposition=ProjectionDisposition.HOLD_ELIGIBLE,
        )

    return project


def _authority(route: ConfiguredFallbackRoute) -> FallbackExecutionAuthority:
    del route
    return FallbackExecutionAuthority(True, RouteExecutionStatus.EXECUTABLE)


def _resolve(**overrides: object) -> FallbackPlanProjection:
    kwargs = {
        "tier": "pro",
        "configured_routes": _ROUTES,
        "registered_providers": frozenset({"primary", "fallback"}),
        "seam_id": "user.prompt.generate",
        "operation": "generate",
        "bounded_usage": _USAGE,
        "remaining_budget_usd": Decimal("1.00"),
        "project": _project({("primary", "model-a"): 100, ("fallback", "model-b"): 60}),
        "resolve_execution": _authority,
    }
    kwargs.update(overrides)
    return resolve_fallback_plan(**kwargs)  # type: ignore[arg-type]


def test_executable_chain_exposure_is_maximum_reservation_not_sum() -> None:
    plan = _resolve(remaining_budget_usd=Decimal("1.00"))
    assert plan.status == "executable"
    assert plan.maximum_chain_exposure_cents == 100
    assert plan.maximum_chain_exposure_cents != 160
    assert plan.would_exceed_budget is False
    assert [route.fallback_index for route in plan.routes] == [0, 1]


def test_peak_exposure_uses_largest_fallback_and_exact_budget_boundary() -> None:
    plan = _resolve(
        project=_project({("primary", "model-a"): 60, ("fallback", "model-b"): 100}),
        remaining_budget_usd=Decimal("0.99"),
    )
    assert plan.maximum_chain_exposure_cents == 100
    assert plan.would_exceed_budget is True


def test_one_blocked_route_blocks_complete_chain_and_withholds_budget_verdict() -> None:
    def authority(route: ConfiguredFallbackRoute) -> FallbackExecutionAuthority:
        return (
            _authority(route)
            if route.provider == "primary"
            else FallbackExecutionAuthority(
                False,
                RouteExecutionStatus.BLOCKED_RECONCILIATION_UNPROVEN,
            )
        )

    plan = _resolve(resolve_execution=authority)
    assert plan.status == "blocked"
    assert plan.maximum_chain_exposure_cents is None
    assert plan.would_exceed_budget is None


def test_unregistered_route_blocks_complete_chain() -> None:
    plan = _resolve(registered_providers=frozenset({"primary"}))
    assert plan.status == "blocked"
    assert [route.registered for route in plan.routes] == [True, False]


def test_projector_receives_same_exact_workload_for_every_route() -> None:
    seen: list[CostProjectionRequest] = []
    projector = _project({("primary", "model-a"): 100, ("fallback", "model-b"): 60})

    def observe(request: CostProjectionRequest) -> CostProjection:
        seen.append(request)
        return projector(request)

    _resolve(project=observe)
    assert [(item.provider, item.model) for item in seen] == list(
        (route.provider, route.model) for route in _ROUTES
    )
    assert {item.seam_id for item in seen} == {"user.prompt.generate"}
    assert {item.operation for item in seen} == {"generate"}
    assert {item.bounded_usage for item in seen} == {_USAGE}


def test_projection_identity_mismatch_fails_complete_plan_closed() -> None:
    valid = _project({("primary", "model-a"): 100, ("fallback", "model-b"): 60})

    def mismatched(request: CostProjectionRequest) -> CostProjection:
        projected = valid(request)
        if request.provider == "fallback":
            return CostProjection(
                seam_id=projected.seam_id,
                provider="other",
                model=projected.model,
                operation=projected.operation,
                bounded_usage=projected.bounded_usage,
                rates=projected.rates,
                rate_snapshot=projected.rate_snapshot,
                currency=projected.currency,
                maximum_cost_usd=projected.maximum_cost_usd,
                reservation_cents=projected.reservation_cents,
                disposition=projected.disposition,
            )
        return projected

    with pytest.raises(ValueError, match="differs"):
        _resolve(project=mismatched)


def test_duplicate_and_oversized_chains_are_refused_before_projection() -> None:
    calls = 0

    def never(request: CostProjectionRequest) -> CostProjection:
        nonlocal calls
        calls += 1
        return _project({(request.provider, request.model): 1})(request)

    duplicate = (_ROUTES[0], _ROUTES[0])
    with pytest.raises(ValueError, match="unique"):
        _resolve(configured_routes=duplicate, project=never)
    with pytest.raises(ValueError, match="1 to 16"):
        _resolve(
            configured_routes=tuple(
                ConfiguredFallbackRoute(f"provider-{index}", f"model-{index}")
                for index in range(17)
            ),
            project=never,
        )
    assert calls == 0


def test_unknown_budget_stays_unknown_for_executable_chain() -> None:
    plan = _resolve(remaining_budget_usd=None)
    assert plan.maximum_chain_exposure_cents == 100
    assert plan.would_exceed_budget is None


def test_zero_cost_receipt_is_not_mislabeled_as_paid_fallback_execution() -> None:
    def zero_cost(request: CostProjectionRequest) -> CostProjection:
        return CostProjection(
            seam_id=request.seam_id,
            provider=request.provider,
            model=request.model,
            operation=request.operation,
            bounded_usage=request.bounded_usage,
            rates=tuple(ProjectionRate(item.unit, Decimal(0)) for item in request.bounded_usage),
            rate_snapshot="local-zero-v1",
            currency="USD",
            maximum_cost_usd=Decimal(0),
            reservation_cents=0,
            disposition=ProjectionDisposition.ZERO_COST_RECEIPT,
        )

    plan = _resolve(project=zero_cost)
    assert plan.status == "blocked"
    assert plan.maximum_chain_exposure_cents is None
    assert plan.would_exceed_budget is None


def test_strict_config_reader_preserves_server_owned_route_order() -> None:
    assert settings_budget.configured_tier_fallback_routes("pro") == (
        ("zai", "glm-5.2"),
        ("deepseek", "deepseek-v4-pro"),
        ("xiaomi", "mimo-v2.5-pro"),
    )


def test_strict_config_reader_rejects_cycle_malformed_fallback_and_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cyclic = {"provider": "a", "model": "one"}
    cyclic["fallback"] = cyclic
    monkeypatch.setattr(
        settings_budget,
        "_load_dispatch_config",
        lambda: {"tiers": {"pro": cyclic}},
    )
    with pytest.raises(ValueError, match="cyclic"):
        settings_budget.configured_tier_fallback_routes("pro")

    malformed = {"provider": "a", "model": "one", "fallback": []}
    monkeypatch.setattr(
        settings_budget,
        "_load_dispatch_config",
        lambda: {"tiers": {"pro": malformed}},
    )
    with pytest.raises(ValueError, match="object"):
        settings_budget.configured_tier_fallback_routes("pro")

    root: dict[str, object] = {"provider": "p-0", "model": "m-0"}
    cursor = root
    for index in range(1, 17):
        child: dict[str, object] = {
            "provider": f"p-{index}",
            "model": f"m-{index}",
        }
        cursor["fallback"] = child
        cursor = child
    monkeypatch.setattr(
        settings_budget,
        "_load_dispatch_config",
        lambda: {"tiers": {"pro": root}},
    )
    with pytest.raises(ValueError, match="depth"):
        settings_budget.configured_tier_fallback_routes("pro")
