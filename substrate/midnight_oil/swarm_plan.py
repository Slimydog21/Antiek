"""Signed per-role route/cost authority for the Midnight Oil live swarm."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.dispatch import DispatchConfig, TierConfig, get_provider

from .job import MidnightOilJob
from .live import OPERATOR_CORPUS_POLICY, _dispatch_config_hash, _route_max_cents
from .spend_consent import MAX_CEILING_CENTS
from .stages import (
    StagePlan,
    StagePlanItem,
    provider_effect_key,
    stage_key,
    stage_plan_hash,
)

SwarmRole = Literal["planner", "gatherer", "verifier", "synthesizer"]
_ROLE_ORDER: tuple[SwarmRole, ...] = (
    "planner",
    "gatherer",
    "verifier",
    "synthesizer",
)
_PLAN_DOMAIN = b"antiek.midnight-oil.swarm-live-plan.v1\x00"
_ROLE_DOMAIN = b"antiek.midnight-oil.swarm-role-plan.v1\x00"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RoleDispatchPlan(_Closed):
    role: SwarmRole
    allowed_routes: tuple[str, ...] = Field(min_length=1, max_length=16)
    projected_max_cents: int = Field(ge=1, le=1_000_000_000)
    dispatch_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_input_tokens: int = Field(ge=256, le=2_500_000)
    max_prompt_bytes: int = Field(ge=1_024, le=10_000_000)
    max_output_tokens: int = Field(ge=1, le=1_000_000)
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical(self) -> RoleDispatchPlan:
        if any(not route or "/" not in route or len(route) > 512 for route in self.allowed_routes):
            raise ValueError("role plan routes are invalid")
        if len(set(self.allowed_routes)) != len(self.allowed_routes):
            raise ValueError("role plan routes must be unique")
        if self.plan_hash != role_dispatch_plan_hash(
            role=self.role,
            allowed_routes=self.allowed_routes,
            projected_max_cents=self.projected_max_cents,
            dispatch_config_sha256=self.dispatch_config_sha256,
            max_input_tokens=self.max_input_tokens,
            max_prompt_bytes=self.max_prompt_bytes,
            max_output_tokens=self.max_output_tokens,
        ):
            raise ValueError("role plan hash conflicts with canonical authority")
        return self


class SwarmLivePlan(_Closed):
    schema_version: Literal[1] = 1
    goals_count: int = Field(ge=1, le=64)
    gather_per_goal: int = Field(ge=1, le=64)
    source_policy: tuple[Literal["operator_corpus"], ...] = ("operator_corpus",)
    roles: tuple[RoleDispatchPlan, ...] = Field(min_length=4, max_length=4)
    projected_total_cents: int = Field(ge=1, le=MAX_CEILING_CENTS)
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical(self) -> SwarmLivePlan:
        if tuple(role.role for role in self.roles) != _ROLE_ORDER:
            raise ValueError("swarm plan requires every role in canonical order")
        expected_total = self.goals_count * (
            self.roles[0].projected_max_cents
            + self.gather_per_goal * self.roles[1].projected_max_cents
            + self.roles[2].projected_max_cents
            + self.roles[3].projected_max_cents
        )
        if self.projected_total_cents != expected_total:
            raise ValueError("swarm projected total conflicts with fixed topology")
        if self.plan_hash != swarm_live_plan_hash(
            goals_count=self.goals_count,
            gather_per_goal=self.gather_per_goal,
            source_policy=self.source_policy,
            roles=self.roles,
            projected_total_cents=self.projected_total_cents,
        ):
            raise ValueError("swarm plan hash conflicts with canonical authority")
        return self

    def role(self, name: SwarmRole) -> RoleDispatchPlan:
        return next(role for role in self.roles if role.role == name)


def build_swarm_live_plan(
    job: MidnightOilJob, *, config: DispatchConfig | None = None
) -> SwarmLivePlan:
    config = config or DispatchConfig.from_yaml(
        Path(__file__).parents[1] / "dispatch" / "config.yaml"
    )
    roles = tuple(_build_role_plan(role, config) for role in _ROLE_ORDER)
    synthesizer = roles[-1]
    if job.model_id is not None and job.model_id not in {
        route.split("/", 1)[1] for route in synthesizer.allowed_routes
    }:
        raise ValueError("selected model is outside the synthesizer route authority")
    total = len(job.goals) * (
        roles[0].projected_max_cents
        + job.fanout_depth * roles[1].projected_max_cents
        + roles[2].projected_max_cents
        + roles[3].projected_max_cents
    )
    if OPERATOR_CORPUS_POLICY != "operator_corpus":
        raise ValueError("operator corpus policy constant drifted")
    source_policy: tuple[Literal["operator_corpus"], ...] = ("operator_corpus",)
    return SwarmLivePlan(
        goals_count=len(job.goals),
        gather_per_goal=job.fanout_depth,
        roles=roles,
        projected_total_cents=total,
        plan_hash=swarm_live_plan_hash(
            goals_count=len(job.goals),
            gather_per_goal=job.fanout_depth,
            source_policy=source_policy,
            roles=roles,
            projected_total_cents=total,
        ),
    )


def build_stage_plan(
    swarm: SwarmLivePlan,
    *,
    operation_id: str,
    job_id: str,
    approved_ceiling_cents: int,
) -> StagePlan:
    if approved_ceiling_cents < swarm.projected_total_cents:
        raise ValueError("approved ceiling cannot cover the signed swarm topology")
    stages: list[StagePlanItem] = []
    for goal in range(swarm.goals_count):
        planner = _stage_item(swarm, operation_id, len(stages), goal, "planner", None, None, ())
        stages.append(planner)
        gathers = tuple(
            _stage_item(
                swarm,
                operation_id,
                len(stages) + shard,
                goal,
                "gather",
                shard,
                swarm.gather_per_goal,
                (planner.stage_key,),
            )
            for shard in range(swarm.gather_per_goal)
        )
        stages.extend(gathers)
        verifier = _stage_item(
            swarm,
            operation_id,
            len(stages),
            goal,
            "verifier",
            None,
            None,
            tuple(row.stage_key for row in gathers),
        )
        stages.append(verifier)
        stages.append(
            _stage_item(
                swarm,
                operation_id,
                len(stages),
                goal,
                "synthesizer",
                None,
                None,
                (verifier.stage_key,),
            )
        )
    rows = tuple(stages)
    return StagePlan(
        operation_id=operation_id,
        job_id=job_id,
        approved_ceiling_cents=approved_ceiling_cents,
        stages=rows,
        plan_hash=stage_plan_hash(
            operation_id=operation_id,
            job_id=job_id,
            approved_ceiling_cents=approved_ceiling_cents,
            stages=rows,
        ),
    )


def _build_role_plan(role: SwarmRole, config: DispatchConfig) -> RoleDispatchPlan:
    tier_name = config.role_tiers.get(role)
    if tier_name is None or tier_name not in config.tiers:
        raise ValueError(f"{role} route is not configured")
    root = config.tiers[tier_name]
    routes: list[str] = []
    maxima: list[int] = []
    tier: TierConfig | None = root
    while tier is not None:
        if tier.provider and tier.model:
            try:
                provider = get_provider(tier.provider)
            except KeyError:
                provider = None
            if provider is not None and bool(getattr(provider, "idempotency_guaranteed", False)):
                routes.append(f"{tier.provider}/{tier.model}")
                # Provider pricing is per token. The legacy helper's parameter
                # name says bytes, but its arithmetic consumes a token count.
                maxima.append(_route_max_cents(tier, max_input_bytes=root.context_budget_tokens))
        tier = tier.fallback
    if not routes:
        raise ValueError(f"{role} lacks a verified idempotent provider route")
    allowed_routes = tuple(routes)
    projected_max_cents = max(maxima)
    dispatch_config_sha256 = _dispatch_config_hash(root)
    max_input_tokens = root.context_budget_tokens
    # UTF-8 can require four bytes per Unicode scalar. Sign a distinct,
    # conservative prompt transport cap instead of conflating its unit
    # with the token-priced context window.
    max_prompt_bytes = min(10_000_000, root.context_budget_tokens * 4)
    max_output_tokens = root.max_tokens
    return RoleDispatchPlan(
        role=role,
        allowed_routes=allowed_routes,
        projected_max_cents=projected_max_cents,
        dispatch_config_sha256=dispatch_config_sha256,
        max_input_tokens=max_input_tokens,
        max_prompt_bytes=max_prompt_bytes,
        max_output_tokens=max_output_tokens,
        plan_hash=role_dispatch_plan_hash(
            role=role,
            allowed_routes=allowed_routes,
            projected_max_cents=projected_max_cents,
            dispatch_config_sha256=dispatch_config_sha256,
            max_input_tokens=max_input_tokens,
            max_prompt_bytes=max_prompt_bytes,
            max_output_tokens=max_output_tokens,
        ),
    )


def _stage_item(
    swarm: SwarmLivePlan,
    operation_id: str,
    ordinal: int,
    goal: int,
    kind: Literal["planner", "gather", "verifier", "synthesizer"],
    shard: int | None,
    shard_count: int | None,
    predecessors: tuple[str, ...],
) -> StagePlanItem:
    role: SwarmRole = "gatherer" if kind == "gather" else kind
    authority = swarm.role(role)
    key = stage_key(operation_id=operation_id, goal_index=goal, kind=kind, shard_index=shard)
    return StagePlanItem(
        ordinal=ordinal,
        kind=kind,
        goal_index=goal,
        shard_index=shard,
        shard_count=shard_count,
        predecessor_stage_keys=predecessors,
        router_role=role,
        route_plan_sha256=authority.plan_hash,
        projected_max_cents=authority.projected_max_cents,
        stage_key=key,
        provider_effect_key=provider_effect_key(key),
    )


def role_dispatch_plan_hash(**fields: object) -> str:
    return hashlib.sha256(_ROLE_DOMAIN + _canonical(fields)).hexdigest()


def swarm_live_plan_hash(**fields: object) -> str:
    material = dict(fields)
    roles = material.get("roles")
    if isinstance(roles, tuple):
        material["roles"] = [
            role.model_dump(mode="json") if isinstance(role, RoleDispatchPlan) else role
            for role in roles
        ]
    return hashlib.sha256(_PLAN_DOMAIN + _canonical(material)).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


__all__ = [
    "RoleDispatchPlan",
    "SwarmLivePlan",
    "build_stage_plan",
    "build_swarm_live_plan",
    "role_dispatch_plan_hash",
    "swarm_live_plan_hash",
]
