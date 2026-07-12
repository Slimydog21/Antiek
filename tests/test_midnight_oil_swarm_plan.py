from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest
from pydantic import ValidationError

from interfaces.research.api.midnight_oil_routes import (
    _config as _consent_config,
)
from interfaces.research.api.midnight_oil_routes import (
    _owner_payload,
)
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.midnight_oil.job import MidnightOilJob
from substrate.midnight_oil.job_store import OperationState, OwnerJob
from substrate.midnight_oil.swarm_plan import (
    SwarmLivePlan,
    SwarmRole,
    build_stage_plan,
    build_swarm_live_plan,
)


class _VerifiedProvider:
    name = "verified"
    idempotency_guaranteed = True

    def call(self, **kwargs: object) -> object:
        raise AssertionError("plan construction must not call the provider")

    def call_idempotent(self, **kwargs: object) -> object:
        raise AssertionError("plan construction must not call the provider")

    def normalize_usage(self, raw_usage: dict[str, object]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0)


def _job(*, goals: tuple[str, ...] = ("g0", "g1"), fanout: int = 2) -> MidnightOilJob:
    return MidnightOilJob(
        job_id="job",
        goals=goals,
        duration_minutes=30,
        model_id="model",
        recommended_price_ceiling_usd=10.0,
        status="approved",
        fanout_depth=fanout,
    )


def _config() -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=1.0, output_per_mtok=2.0)
    tiers: dict[str, TierConfig] = {}
    roles: dict[str, str] = {}
    for index, role in enumerate(("planner", "gatherer", "verifier", "synthesizer")):
        name = f"{role}-tier"
        roles[role] = name
        tiers[name] = TierConfig(
            name=name,
            provider="verified",
            model="model",
            max_tokens=100 + index,
            temperature=0.2,
            context_budget_tokens=2048 + index,
            pricing=pricing,
        )
    return DispatchConfig(role_tiers=roles, tiers=tiers)


@pytest.fixture(autouse=True)
def _provider_registry() -> Generator[None]:
    reset_provider_registry()
    register_provider(_VerifiedProvider())  # type: ignore[arg-type]
    yield
    reset_provider_registry()


def test_swarm_plan_signs_every_role_and_exact_fixed_topology_cost() -> None:
    plan = build_swarm_live_plan(_job(), config=_config())

    assert tuple(row.role for row in plan.roles) == (
        "planner",
        "gatherer",
        "verifier",
        "synthesizer",
    )
    assert all(row.allowed_routes == ("verified/model",) for row in plan.roles)
    assert all(row.max_prompt_bytes == row.max_input_tokens * 4 for row in plan.roles)
    per_goal = (
        plan.role("planner").projected_max_cents
        + 2 * plan.role("gatherer").projected_max_cents
        + plan.role("verifier").projected_max_cents
        + plan.role("synthesizer").projected_max_cents
    )
    assert plan.projected_total_cents == 2 * per_goal


def test_missing_or_unverified_role_cannot_create_authority() -> None:
    config = _config()
    without_verifier = DispatchConfig(
        role_tiers={key: value for key, value in config.role_tiers.items() if key != "verifier"},
        tiers=config.tiers,
    )
    with pytest.raises(ValueError, match="verifier route is not configured"):
        build_swarm_live_plan(_job(), config=without_verifier)

    reset_provider_registry()
    with pytest.raises(ValueError, match="planner lacks a verified"):
        build_swarm_live_plan(_job(), config=config)


def test_swarm_hash_rejects_any_role_authority_tamper() -> None:
    plan = build_swarm_live_plan(_job(), config=_config())
    payload = plan.model_dump(mode="python")
    payload["roles"][0]["max_output_tokens"] += 1

    with pytest.raises(ValidationError, match="role plan hash conflicts"):
        SwarmLivePlan.model_validate(payload)


def test_stage_plan_has_exact_causal_shape_and_signed_role_hashes() -> None:
    swarm = build_swarm_live_plan(_job(goals=("goal",), fanout=3), config=_config())
    plan = build_stage_plan(
        swarm,
        operation_id="operation",
        job_id="job",
        approved_ceiling_cents=swarm.projected_total_cents,
    )

    assert [row.kind for row in plan.stages] == [
        "planner",
        "gather",
        "gather",
        "gather",
        "verifier",
        "synthesizer",
    ]
    planner, *middle, synthesizer = plan.stages
    gathers = middle[:3]
    verifier = middle[3]
    assert all(row.predecessor_stage_keys == (planner.stage_key,) for row in gathers)
    assert verifier.predecessor_stage_keys == tuple(row.stage_key for row in gathers)
    assert synthesizer.predecessor_stage_keys == (verifier.stage_key,)
    assert all(
        row.route_plan_sha256
        == swarm.role(cast(SwarmRole, row.router_role)).plan_hash
        for row in plan.stages
    )


def test_stage_plan_rejects_ceiling_below_whole_signed_topology() -> None:
    swarm = build_swarm_live_plan(_job(), config=_config())
    with pytest.raises(ValueError, match="cannot cover"):
        build_stage_plan(
            swarm,
            operation_id="operation",
            job_id="job",
            approved_ceiling_cents=swarm.projected_total_cents - 1,
        )


def test_closed_owner_payload_roundtrips_swarm_and_rejects_mixed_authority() -> None:
    job = _job(goals=("goal",), fanout=2)
    job = MidnightOilJob(**{**job.__dict__, "asset_id": "asset"})
    swarm = build_swarm_live_plan(job, config=_config())
    payload = _owner_payload(job, swarm_plan=swarm)
    row = OwnerJob(
        owner_user_id="owner",
        job_id=job.job_id,
        state_version=0,
        approved_ceiling_cents=None,
        consent_receipt_id=None,
        consent_config_hash=None,
        consent_issued_at_ms=None,
        consent_expires_at_ms=None,
        consent_claimed_at_ms=None,
        operation_id=None,
        operation_state=OperationState.NONE,
        dispatch_started_at_ms=None,
        dispatched_at_ms=None,
        completed_at_ms=None,
        payload=payload,
    )
    assert _consent_config(row).live_execution_plan_hash == swarm.plan_hash

    mixed = dict(payload)
    mixed["live_plan_hash"] = "0" * 64
    with pytest.raises(ValueError, match="mixes legacy and swarm"):
        _consent_config(OwnerJob(**{**row.__dict__, "payload": mixed}))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("goals", ["goal", "extra"], "job goals"),
        ("fanout_depth", 3, "job fanout"),
        ("model_id", "unsigned-model", "selected model"),
    ],
)
def test_swarm_authority_must_match_owner_topology_and_model(
    field: str, value: object, message: str
) -> None:
    job = _job(goals=("goal",), fanout=2)
    job = MidnightOilJob(**{**job.__dict__, "asset_id": "asset"})
    swarm = build_swarm_live_plan(job, config=_config())
    payload = _owner_payload(job, swarm_plan=swarm)
    payload[field] = value
    row = OwnerJob(
        owner_user_id="owner",
        job_id=job.job_id,
        state_version=0,
        approved_ceiling_cents=None,
        consent_receipt_id=None,
        consent_config_hash=None,
        consent_issued_at_ms=None,
        consent_expires_at_ms=None,
        consent_claimed_at_ms=None,
        operation_id=None,
        operation_state=OperationState.NONE,
        dispatch_started_at_ms=None,
        dispatched_at_ms=None,
        completed_at_ms=None,
        payload=payload,
    )
    with pytest.raises(ValueError, match=message):
        _consent_config(row)
