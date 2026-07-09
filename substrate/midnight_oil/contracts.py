"""Midnight-oil no-spend preflight contract.

Midnight oil is the autonomous research-swarm mode. This module only validates
and plans the envelope: operator acknowledgement, time box, price ceiling,
route policy, source policy, and HTML artifact obligations. It never launches
agents, calls model providers, reserves budget, or performs retrieval.
"""

from __future__ import annotations

import math
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RouteMode = Literal["auto_quality", "auto_balanced", "auto_cost", "auto_latency", "manual"]
SourcePolicy = Literal["arxiv", "substack", "web", "operator_corpus"]
DeliverableKind = Literal["html_research_asset"]
MidnightOilRole = Literal["planner", "gatherer", "verifier", "synthesizer"]

_ROLE_ORDER: tuple[MidnightOilRole, ...] = ("planner", "gatherer", "verifier", "synthesizer")
_BUDGET_WEIGHTS: dict[MidnightOilRole, int] = {
    "planner": 15,
    "gatherer": 45,
    "verifier": 20,
    "synthesizer": 20,
}
_TIME_WEIGHTS: dict[MidnightOilRole, int] = {
    "planner": 15,
    "gatherer": 50,
    "verifier": 15,
    "synthesizer": 20,
}


class MidnightOilRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    work_minutes: int = Field(ge=15, le=720)
    price_ceiling_usd: float = Field(gt=0.0, le=10_000.0)
    route_mode: RouteMode = "auto_balanced"
    source_policy: list[SourcePolicy] = Field(min_length=1)
    deliverable: DeliverableKind = "html_research_asset"
    operator_acknowledged_spend: bool = False

    @model_validator(mode="after")
    def _source_policy_unique(self) -> MidnightOilRequest:
        if len(set(self.source_policy)) != len(self.source_policy):
            raise ValueError("source_policy entries must be unique")
        return self


class MidnightOilArtifactContract(BaseModel):
    final_format: Literal["html"] = "html"
    pdf_allowed: bool = False
    antiek_information_asset: bool = True
    twin_note_document_required: bool = True
    route_receipt_links_required: bool = True
    source_receipt_links_required: bool = True


class MidnightOilRolePlan(BaseModel):
    role: MidnightOilRole
    budget_usd: float = Field(ge=0.0)
    max_minutes: int = Field(ge=0)
    route_mode: RouteMode
    route_receipt_required: bool = True
    source_receipts_required: bool = True
    planned_route_receipt_id: str


class MidnightOilLaunchPacket(BaseModel):
    packet_id: str
    run_id: str
    goal: str
    work_minutes: int
    price_ceiling_usd: float = Field(ge=0.0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    route_mode: RouteMode
    source_policy: list[SourcePolicy]
    deliverable: DeliverableKind
    artifact_contract: MidnightOilArtifactContract
    role_count: int = Field(ge=0)
    role_route_receipt_ids: list[str]
    source_receipts_required: bool = True
    route_receipts_required: bool = True
    dispatch_allowed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    launch_notes: list[str] = Field(default_factory=list)


class MidnightOilPreflight(BaseModel):
    accepted: bool
    denial_reason: str | None = None
    run_id: str | None = None
    goal: str
    work_minutes: int
    price_ceiling_usd: float
    route_mode: RouteMode
    source_policy: list[SourcePolicy]
    deliverable: DeliverableKind
    planned_budget_usd: float = Field(default=0.0, ge=0.0)
    unallocated_budget_usd: float = Field(default=0.0, ge=0.0)
    role_plans: list[MidnightOilRolePlan] = Field(default_factory=list)
    artifact_contract: MidnightOilArtifactContract = Field(
        default_factory=MidnightOilArtifactContract
    )
    launch_packet: MidnightOilLaunchPacket | None = None
    notes: list[str] = Field(default_factory=list)


def preflight_midnight_oil(req: MidnightOilRequest) -> MidnightOilPreflight:
    price_ceiling_usd = round(req.price_ceiling_usd, 2)
    if not req.operator_acknowledged_spend:
        return MidnightOilPreflight(
            accepted=False,
            denial_reason="operator_acknowledged_spend_required",
            goal=req.goal,
            work_minutes=req.work_minutes,
            price_ceiling_usd=price_ceiling_usd,
            route_mode=req.route_mode,
            source_policy=req.source_policy,
            deliverable=req.deliverable,
            planned_budget_usd=0.0,
            unallocated_budget_usd=price_ceiling_usd,
            notes=[
                "denied before dispatch: autonomous research requires explicit spend acknowledgement"
            ],
        )

    run_id = f"midnight-oil-{uuid.uuid4().hex[:12]}"
    role_plans = _role_plans(
        run_id=run_id,
        price_ceiling_usd=req.price_ceiling_usd,
        work_minutes=req.work_minutes,
        route_mode=req.route_mode,
    )
    planned_budget_usd = round(sum(plan.budget_usd for plan in role_plans), 2)
    return MidnightOilPreflight(
        accepted=True,
        run_id=run_id,
        goal=req.goal,
        work_minutes=req.work_minutes,
        price_ceiling_usd=price_ceiling_usd,
        route_mode=req.route_mode,
        source_policy=req.source_policy,
        deliverable=req.deliverable,
        planned_budget_usd=planned_budget_usd,
        unallocated_budget_usd=round(max(0.0, price_ceiling_usd - planned_budget_usd), 2),
        role_plans=role_plans,
        launch_packet=_launch_packet(
            run_id=run_id,
            req=req,
            price_ceiling_usd=price_ceiling_usd,
            planned_budget_usd=planned_budget_usd,
            unallocated_budget_usd=round(max(0.0, price_ceiling_usd - planned_budget_usd), 2),
            role_plans=role_plans,
        ),
        notes=[
            "preflight only: no agents launched, no budget reserved, no retrieval performed",
            "each future subagent must inherit the parent ceiling through this role allocation",
        ],
    )


def _role_plans(
    *,
    run_id: str,
    price_ceiling_usd: float,
    work_minutes: int,
    route_mode: RouteMode,
) -> list[MidnightOilRolePlan]:
    cents = max(1, math.floor(price_ceiling_usd * 100))
    allocated = 0
    plans: list[MidnightOilRolePlan] = []
    for index, role in enumerate(_ROLE_ORDER):
        if index == len(_ROLE_ORDER) - 1:
            role_cents = max(0, cents - allocated)
            role_minutes = max(0, work_minutes - sum(p.max_minutes for p in plans))
        else:
            role_cents = math.floor(cents * _BUDGET_WEIGHTS[role] / 100)
            allocated += role_cents
            role_minutes = max(1, math.floor(work_minutes * _TIME_WEIGHTS[role] / 100))
        plans.append(
            MidnightOilRolePlan(
                role=role,
                budget_usd=round(role_cents / 100, 2),
                max_minutes=role_minutes,
                route_mode=route_mode,
                planned_route_receipt_id=f"{run_id}-{role}-route-receipt",
            )
        )
    return plans


def _launch_packet(
    *,
    run_id: str,
    req: MidnightOilRequest,
    price_ceiling_usd: float,
    planned_budget_usd: float,
    unallocated_budget_usd: float,
    role_plans: list[MidnightOilRolePlan],
) -> MidnightOilLaunchPacket:
    artifact_contract = MidnightOilArtifactContract()
    return MidnightOilLaunchPacket(
        packet_id=f"{run_id}-launch-packet",
        run_id=run_id,
        goal=req.goal,
        work_minutes=req.work_minutes,
        price_ceiling_usd=price_ceiling_usd,
        planned_budget_usd=planned_budget_usd,
        unallocated_budget_usd=unallocated_budget_usd,
        route_mode=req.route_mode,
        source_policy=req.source_policy,
        deliverable=req.deliverable,
        artifact_contract=artifact_contract,
        role_count=len(role_plans),
        role_route_receipt_ids=[plan.planned_route_receipt_id for plan in role_plans],
        source_receipts_required=artifact_contract.source_receipt_links_required,
        route_receipts_required=artifact_contract.route_receipt_links_required,
        launch_notes=[
            "launch packet only: no agents dispatched",
            "no budget reserved and no provider calls made",
            "future runner must attach route and source receipts before final HTML asset",
        ],
    )
