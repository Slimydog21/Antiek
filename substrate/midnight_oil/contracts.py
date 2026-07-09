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


class MidnightOilApprovalReceipt(BaseModel):
    receipt_id: str
    launch_packet_id: str
    run_id: str
    operator_acknowledged_spend: bool = True
    approved_price_ceiling_usd: float = Field(ge=0.0)
    approved_work_minutes: int = Field(ge=0)
    approved_route_mode: RouteMode
    approved_source_policy: list[SourcePolicy]
    approved_deliverable: DeliverableKind
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    approval_scope: Literal["preflight_launch_packet_only"] = "preflight_launch_packet_only"
    runner_apply_required: bool = True
    dispatch_allowed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    receipt_notes: list[str] = Field(default_factory=list)


class MidnightOilRunnerHandoff(BaseModel):
    handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["ready_for_runner_apply"] = "ready_for_runner_apply"
    approved_price_ceiling_usd: float = Field(ge=0.0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    role_route_receipt_ids: list[str]
    prerequisite_receipt_ids: list[str]
    dispatch_ready: bool = True
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    graph_mutated: bool = False
    handoff_notes: list[str] = Field(default_factory=list)


class MidnightOilAppliedRunReceipt(BaseModel):
    receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["planned_not_dispatched"] = "planned_not_dispatched"
    planned_role_count: int = Field(ge=0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    planned_role_route_receipt_ids: list[str]
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    applied_notes: list[str] = Field(default_factory=list)


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
    approval_receipt: MidnightOilApprovalReceipt | None = None
    runner_handoff: MidnightOilRunnerHandoff | None = None
    applied_run_receipt: MidnightOilAppliedRunReceipt | None = None
    notes: list[str] = Field(default_factory=list)


class MidnightOilDryRunRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilDryRunRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.runner_handoff.run_id != self.launch_packet.run_id:
            raise ValueError("runner_handoff run_id must match launch_packet")
        if self.approval_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("approval_receipt run_id must match launch_packet")
        if self.runner_handoff.dispatch_performed:
            raise ValueError("runner_handoff must not already be dispatched")
        if self.runner_handoff.budget_reserved:
            raise ValueError("runner_handoff must not reserve budget")
        if self.runner_handoff.provider_calls_made:
            raise ValueError("runner_handoff must not include provider calls")
        if self.runner_handoff.graph_mutated:
            raise ValueError("runner_handoff must not mutate graph")
        return self


class MidnightOilDispatchRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    live_dispatch_requested: bool = False

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilDispatchRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.applied_run_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("applied_run_receipt must reference launch_packet")
        if self.applied_run_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("applied_run_receipt must reference approval_receipt")
        if self.applied_run_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("applied_run_receipt must reference runner_handoff")
        if self.runner_handoff.run_id != self.launch_packet.run_id:
            raise ValueError("runner_handoff run_id must match launch_packet")
        if self.approval_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("approval_receipt run_id must match launch_packet")
        if self.applied_run_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("applied_run_receipt run_id must match launch_packet")
        if self.applied_run_receipt.status != "planned_not_dispatched":
            raise ValueError("applied_run_receipt must be planned_not_dispatched")
        if self.runner_handoff.dispatch_performed or self.applied_run_receipt.dispatch_performed:
            raise ValueError("receipt chain must not already be dispatched")
        if self.runner_handoff.budget_reserved or self.applied_run_receipt.budget_reserved:
            raise ValueError("receipt chain must not reserve budget")
        if self.runner_handoff.provider_calls_made or self.applied_run_receipt.provider_calls_made:
            raise ValueError("receipt chain must not include provider calls")
        if self.runner_handoff.graph_mutated or self.applied_run_receipt.graph_mutated:
            raise ValueError("receipt chain must not mutate graph")
        if self.applied_run_receipt.retrieval_performed:
            raise ValueError("applied_run_receipt must not perform retrieval")
        if self.applied_run_receipt.final_artifact_created:
            raise ValueError("applied_run_receipt must not create final artifact")
        return self


class MidnightOilDispatchReceipt(BaseModel):
    receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_live_dispatch_disabled"] = "blocked_live_dispatch_disabled"
    live_dispatch_requested: bool = False
    blocker_reason: Literal["live_dispatch_disabled"] = "live_dispatch_disabled"
    dispatch_allowed: bool = False
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    dispatch_notes: list[str] = Field(default_factory=list)


class MidnightOilActivationChecklistRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    dispatch_receipt: MidnightOilDispatchReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilActivationChecklistRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.applied_run_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("applied_run_receipt must reference launch_packet")
        if self.applied_run_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("applied_run_receipt must reference approval_receipt")
        if self.applied_run_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("applied_run_receipt must reference runner_handoff")
        if self.dispatch_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("dispatch_receipt must reference launch_packet")
        if self.dispatch_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("dispatch_receipt must reference approval_receipt")
        if self.dispatch_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("dispatch_receipt must reference runner_handoff")
        if self.dispatch_receipt.applied_run_receipt_id != self.applied_run_receipt.receipt_id:
            raise ValueError("dispatch_receipt must reference applied_run_receipt")
        if self.dispatch_receipt.status != "blocked_live_dispatch_disabled":
            raise ValueError("dispatch_receipt must be blocked_live_dispatch_disabled")
        if self.dispatch_receipt.dispatch_performed:
            raise ValueError("dispatch_receipt must not dispatch")
        if self.dispatch_receipt.budget_reserved:
            raise ValueError("dispatch_receipt must not reserve budget")
        if self.dispatch_receipt.provider_calls_made:
            raise ValueError("dispatch_receipt must not include provider calls")
        if self.dispatch_receipt.retrieval_performed:
            raise ValueError("dispatch_receipt must not perform retrieval")
        if self.dispatch_receipt.graph_mutated:
            raise ValueError("dispatch_receipt must not mutate graph")
        if self.dispatch_receipt.final_artifact_created:
            raise ValueError("dispatch_receipt must not create final artifact")
        return self


class MidnightOilActivationChecklistReceipt(BaseModel):
    receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["activation_blocked_controls_missing"] = "activation_blocked_controls_missing"
    completed_items: list[str]
    missing_items: list[str]
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    provider_execution_allowed: bool = False
    retrieval_allowed: bool = False
    graph_mutation_allowed: bool = False
    final_artifact_allowed: bool = False
    checklist_notes: list[str] = Field(default_factory=list)


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
    unallocated_budget_usd = round(max(0.0, price_ceiling_usd - planned_budget_usd), 2)
    launch_packet = _launch_packet(
        run_id=run_id,
        req=req,
        price_ceiling_usd=price_ceiling_usd,
        planned_budget_usd=planned_budget_usd,
        unallocated_budget_usd=unallocated_budget_usd,
        role_plans=role_plans,
    )
    approval_receipt = _approval_receipt(
        launch_packet=launch_packet,
        operator_acknowledged_spend=req.operator_acknowledged_spend,
    )
    runner_handoff = _runner_handoff(
        launch_packet=launch_packet,
        approval_receipt=approval_receipt,
    )
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
        unallocated_budget_usd=unallocated_budget_usd,
        role_plans=role_plans,
        launch_packet=launch_packet,
        approval_receipt=approval_receipt,
        runner_handoff=runner_handoff,
        applied_run_receipt=_applied_run_receipt(
            launch_packet=launch_packet,
            approval_receipt=approval_receipt,
            runner_handoff=runner_handoff,
        ),
        notes=[
            "preflight only: no agents launched, no budget reserved, no retrieval performed",
            "each future subagent must inherit the parent ceiling through this role allocation",
        ],
    )


def dry_run_midnight_oil(req: MidnightOilDryRunRequest) -> MidnightOilAppliedRunReceipt:
    return _applied_run_receipt(
        launch_packet=req.launch_packet,
        approval_receipt=req.approval_receipt,
        runner_handoff=req.runner_handoff,
    )


def dispatch_midnight_oil(req: MidnightOilDispatchRequest) -> MidnightOilDispatchReceipt:
    return MidnightOilDispatchReceipt(
        receipt_id=f"{req.launch_packet.run_id}-dispatch-receipt",
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        live_dispatch_requested=req.live_dispatch_requested,
        dispatch_allowed=False,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        dispatch_notes=[
            "live dispatch gate only: autonomous runner execution is disabled",
            "no budget reserved, provider calls made, retrieval performed, or graph mutation",
            "future live runner must replace this blocked receipt after operator-enabled controls",
        ],
    )


def activation_checklist_midnight_oil(
    req: MidnightOilActivationChecklistRequest,
) -> MidnightOilActivationChecklistReceipt:
    return MidnightOilActivationChecklistReceipt(
        receipt_id=f"{req.launch_packet.run_id}-activation-checklist",
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        completed_items=[
            "operator acknowledged spend ceiling for preflight",
            "launch packet exists",
            "approval receipt exists",
            "runner handoff exists",
            "applied run receipt exists",
            "blocked dispatch receipt exists",
        ],
        missing_items=[
            "operator live-run activation setting",
            "budget reservation provider",
            "model/provider route executor",
            "retrieval executor with source receipts",
            "graph mutation writer",
            "final HTML artifact writer",
        ],
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        provider_execution_allowed=False,
        retrieval_allowed=False,
        graph_mutation_allowed=False,
        final_artifact_allowed=False,
        checklist_notes=[
            "activation checklist only: live execution remains blocked",
            "no budget reservation, provider call, retrieval, graph mutation, or artifact write is allowed",
            "future live runner must satisfy every missing item before replacing this receipt",
        ],
    )


def _applied_run_receipt(
    *,
    launch_packet: MidnightOilLaunchPacket,
    approval_receipt: MidnightOilApprovalReceipt,
    runner_handoff: MidnightOilRunnerHandoff,
) -> MidnightOilAppliedRunReceipt:
    return MidnightOilAppliedRunReceipt(
        receipt_id=f"{launch_packet.run_id}-applied-run-receipt",
        runner_handoff_id=runner_handoff.handoff_id,
        approval_receipt_id=approval_receipt.receipt_id,
        launch_packet_id=launch_packet.packet_id,
        run_id=launch_packet.run_id,
        planned_role_count=launch_packet.role_count,
        planned_budget_usd=approval_receipt.planned_budget_usd,
        unallocated_budget_usd=approval_receipt.unallocated_budget_usd,
        planned_role_route_receipt_ids=runner_handoff.role_route_receipt_ids,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        applied_notes=[
            "dry applied run receipt only: no autonomous agents dispatched",
            "no budget reserved, provider calls made, retrieval performed, or graph mutation",
            "future live runner must replace this with a dispatch receipt before work starts",
        ],
    )


def _runner_handoff(
    *,
    launch_packet: MidnightOilLaunchPacket,
    approval_receipt: MidnightOilApprovalReceipt,
) -> MidnightOilRunnerHandoff:
    return MidnightOilRunnerHandoff(
        handoff_id=f"{launch_packet.run_id}-runner-handoff",
        approval_receipt_id=approval_receipt.receipt_id,
        launch_packet_id=launch_packet.packet_id,
        run_id=launch_packet.run_id,
        approved_price_ceiling_usd=approval_receipt.approved_price_ceiling_usd,
        planned_budget_usd=approval_receipt.planned_budget_usd,
        unallocated_budget_usd=approval_receipt.unallocated_budget_usd,
        role_route_receipt_ids=launch_packet.role_route_receipt_ids,
        prerequisite_receipt_ids=[launch_packet.packet_id, approval_receipt.receipt_id],
        dispatch_ready=True,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        graph_mutated=False,
        handoff_notes=[
            "runner apply handoff only: ready for a future dispatcher",
            "no agents dispatched, no budget reserved, no provider calls made",
            "future runner must convert this handoff into an applied run receipt",
        ],
    )


def _approval_receipt(
    *,
    launch_packet: MidnightOilLaunchPacket,
    operator_acknowledged_spend: bool,
) -> MidnightOilApprovalReceipt:
    return MidnightOilApprovalReceipt(
        receipt_id=f"{launch_packet.run_id}-approval-receipt",
        launch_packet_id=launch_packet.packet_id,
        run_id=launch_packet.run_id,
        operator_acknowledged_spend=operator_acknowledged_spend,
        approved_price_ceiling_usd=launch_packet.price_ceiling_usd,
        approved_work_minutes=launch_packet.work_minutes,
        approved_route_mode=launch_packet.route_mode,
        approved_source_policy=launch_packet.source_policy,
        approved_deliverable=launch_packet.deliverable,
        planned_budget_usd=launch_packet.planned_budget_usd,
        unallocated_budget_usd=launch_packet.unallocated_budget_usd,
        dispatch_allowed=launch_packet.dispatch_allowed,
        budget_reserved=launch_packet.budget_reserved,
        provider_calls_made=launch_packet.provider_calls_made,
        receipt_notes=[
            "operator approved the ceiling for this launch packet only",
            "runner apply is still required before any dispatch or budget reservation",
            "no provider calls or graph mutations were performed by this receipt",
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
