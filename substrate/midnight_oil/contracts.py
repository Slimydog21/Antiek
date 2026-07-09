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
RunnerControlKey = Literal[
    "budget_reservation_provider",
    "model_provider_route_executor",
    "retrieval_executor_source_receipts",
    "graph_mutation_writer",
    "final_html_artifact_writer",
    "operator_live_dispatch_enablement",
]

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
_RUNNER_CONTROL_ORDER: tuple[RunnerControlKey, ...] = (
    "budget_reservation_provider",
    "model_provider_route_executor",
    "retrieval_executor_source_receipts",
    "graph_mutation_writer",
    "final_html_artifact_writer",
    "operator_live_dispatch_enablement",
)
_RUNNER_CONTROL_BLOCKERS: dict[RunnerControlKey, str] = {
    "budget_reservation_provider": "budget reservation provider",
    "model_provider_route_executor": "model/provider route executor",
    "retrieval_executor_source_receipts": "retrieval executor with source receipts",
    "graph_mutation_writer": "graph mutation writer",
    "final_html_artifact_writer": "final HTML artifact writer",
    "operator_live_dispatch_enablement": "operator live-run dispatch enablement",
}
_RUNNER_CONTROL_ARTIFACTS: dict[RunnerControlKey, str] = {
    "budget_reservation_provider": "budget provider adapter and reservation ledger",
    "model_provider_route_executor": "model/provider route executor with per-role receipts",
    "retrieval_executor_source_receipts": "source connector executor with arXiv/Substack/web/operator corpus receipts",
    "graph_mutation_writer": "knowledge graph mutation writer with idempotent node and edge writes",
    "final_html_artifact_writer": "HTML research asset and twin-note writer",
    "operator_live_dispatch_enablement": "operator-controlled live dispatch setting with budget ceiling enforcement",
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


class MidnightOilLiveRunActivationSettingsRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    requested_live_run_enabled: bool = False
    requested_price_ceiling_usd: float = Field(gt=0.0, le=10_000.0)
    requested_work_minutes: int = Field(ge=15, le=720)

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilLiveRunActivationSettingsRequest:
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
        if self.approval_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("approval_receipt run_id must match launch_packet")
        if self.runner_handoff.run_id != self.launch_packet.run_id:
            raise ValueError("runner_handoff run_id must match launch_packet")
        if self.applied_run_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("applied_run_receipt run_id must match launch_packet")
        if self.requested_price_ceiling_usd > self.approval_receipt.approved_price_ceiling_usd:
            raise ValueError("requested_price_ceiling_usd must not exceed approved ceiling")
        if self.requested_work_minutes > self.approval_receipt.approved_work_minutes:
            raise ValueError("requested_work_minutes must not exceed approved work minutes")
        if self.runner_handoff.dispatch_performed or self.applied_run_receipt.dispatch_performed:
            raise ValueError("receipt chain must not dispatch")
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


class MidnightOilLiveRunActivationSettingsReceipt(BaseModel):
    receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_live_run_activation_disabled"] = (
        "blocked_live_run_activation_disabled"
    )
    settings_scope: Literal["midnight_oil_live_run_activation"] = (
        "midnight_oil_live_run_activation"
    )
    requested_live_run_enabled: bool = False
    requested_price_ceiling_usd: float = Field(ge=0.0)
    requested_work_minutes: int = Field(ge=0)
    approved_price_ceiling_usd: float = Field(ge=0.0)
    approved_work_minutes: int = Field(ge=0)
    missing_controls: list[str]
    blocker_reason: Literal["live_run_activation_controls_missing"] = (
        "live_run_activation_controls_missing"
    )
    live_run_activation_allowed: bool = False
    dispatch_allowed: bool = False
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    settings_notes: list[str] = Field(default_factory=list)


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
    live_run_activation_settings_receipt: MidnightOilLiveRunActivationSettingsReceipt | None = None
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
        if self.live_run_activation_settings_receipt is not None:
            settings = self.live_run_activation_settings_receipt
            if settings.launch_packet_id != self.launch_packet.packet_id:
                raise ValueError("live_run_activation_settings_receipt must reference launch_packet")
            if settings.approval_receipt_id != self.approval_receipt.receipt_id:
                raise ValueError("live_run_activation_settings_receipt must reference approval_receipt")
            if settings.runner_handoff_id != self.runner_handoff.handoff_id:
                raise ValueError("live_run_activation_settings_receipt must reference runner_handoff")
            if settings.applied_run_receipt_id != self.applied_run_receipt.receipt_id:
                raise ValueError("live_run_activation_settings_receipt must reference applied_run_receipt")
            if settings.run_id != self.launch_packet.run_id:
                raise ValueError("live_run_activation_settings_receipt run_id must match launch_packet")
            if settings.status != "blocked_live_run_activation_disabled":
                raise ValueError(
                    "live_run_activation_settings_receipt must be blocked_live_run_activation_disabled"
                )
            if settings.live_run_activation_allowed:
                raise ValueError("live_run_activation_settings_receipt must not allow live activation")
            if settings.dispatch_allowed or settings.dispatch_performed:
                raise ValueError("live_run_activation_settings_receipt must not dispatch")
            if settings.budget_reserved:
                raise ValueError("live_run_activation_settings_receipt must not reserve budget")
            if settings.provider_calls_made:
                raise ValueError("live_run_activation_settings_receipt must not include provider calls")
            if settings.retrieval_performed:
                raise ValueError("live_run_activation_settings_receipt must not perform retrieval")
            if settings.graph_mutated:
                raise ValueError("live_run_activation_settings_receipt must not mutate graph")
            if settings.final_artifact_created:
                raise ValueError("live_run_activation_settings_receipt must not create final artifact")
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
    live_run_activation_settings_receipt_id: str | None = None
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


class MidnightOilBudgetReservationRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    dispatch_receipt: MidnightOilDispatchReceipt
    activation_checklist_receipt: MidnightOilActivationChecklistReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilBudgetReservationRequest:
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
        if self.activation_checklist_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("activation_checklist_receipt must reference launch_packet")
        if self.activation_checklist_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference approval_receipt")
        if self.activation_checklist_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("activation_checklist_receipt must reference runner_handoff")
        if (
            self.activation_checklist_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("activation_checklist_receipt must reference applied_run_receipt")
        if self.activation_checklist_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference dispatch_receipt")
        if self.activation_checklist_receipt.status != "activation_blocked_controls_missing":
            raise ValueError("activation_checklist_receipt must be activation_blocked_controls_missing")
        if self.activation_checklist_receipt.budget_reservation_allowed:
            raise ValueError("activation_checklist_receipt must not allow budget reservation")
        if self.dispatch_receipt.budget_reserved or self.applied_run_receipt.budget_reserved:
            raise ValueError("receipt chain must not already reserve budget")
        if self.dispatch_receipt.provider_calls_made or self.applied_run_receipt.provider_calls_made:
            raise ValueError("receipt chain must not include provider calls")
        if self.dispatch_receipt.dispatch_performed or self.applied_run_receipt.dispatch_performed:
            raise ValueError("receipt chain must not dispatch")
        if self.dispatch_receipt.graph_mutated or self.applied_run_receipt.graph_mutated:
            raise ValueError("receipt chain must not mutate graph")
        return self


class MidnightOilBudgetReservationReceipt(BaseModel):
    receipt_id: str
    activation_checklist_receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_budget_reservation_disabled"] = "blocked_budget_reservation_disabled"
    requested_reservation_usd: float = Field(ge=0.0)
    approved_price_ceiling_usd: float = Field(ge=0.0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    blocker_reason: Literal["budget_reservation_provider_missing"] = (
        "budget_reservation_provider_missing"
    )
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    dispatch_performed: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    reservation_notes: list[str] = Field(default_factory=list)


class MidnightOilProviderRouteRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    dispatch_receipt: MidnightOilDispatchReceipt
    activation_checklist_receipt: MidnightOilActivationChecklistReceipt
    budget_reservation_receipt: MidnightOilBudgetReservationReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilProviderRouteRequest:
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
        if self.activation_checklist_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("activation_checklist_receipt must reference launch_packet")
        if self.activation_checklist_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference approval_receipt")
        if self.activation_checklist_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("activation_checklist_receipt must reference runner_handoff")
        if (
            self.activation_checklist_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("activation_checklist_receipt must reference applied_run_receipt")
        if self.activation_checklist_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference dispatch_receipt")
        if self.activation_checklist_receipt.status != "activation_blocked_controls_missing":
            raise ValueError("activation_checklist_receipt must be activation_blocked_controls_missing")
        if self.activation_checklist_receipt.provider_execution_allowed:
            raise ValueError("activation_checklist_receipt must not allow provider execution")
        if self.budget_reservation_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("budget_reservation_receipt must reference launch_packet")
        if self.budget_reservation_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("budget_reservation_receipt must reference approval_receipt")
        if self.budget_reservation_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("budget_reservation_receipt must reference runner_handoff")
        if (
            self.budget_reservation_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("budget_reservation_receipt must reference applied_run_receipt")
        if self.budget_reservation_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("budget_reservation_receipt must reference dispatch_receipt")
        if (
            self.budget_reservation_receipt.activation_checklist_receipt_id
            != self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError(
                "budget_reservation_receipt must reference activation_checklist_receipt"
            )
        if self.budget_reservation_receipt.status != "blocked_budget_reservation_disabled":
            raise ValueError("budget_reservation_receipt must be blocked_budget_reservation_disabled")
        if self.dispatch_receipt.dispatch_performed or self.applied_run_receipt.dispatch_performed:
            raise ValueError("receipt chain must not dispatch")
        if self.dispatch_receipt.budget_reserved or self.applied_run_receipt.budget_reserved:
            raise ValueError("receipt chain must not already reserve budget")
        if self.dispatch_receipt.provider_calls_made or self.applied_run_receipt.provider_calls_made:
            raise ValueError("receipt chain must not include provider calls")
        if self.dispatch_receipt.retrieval_performed or self.applied_run_receipt.retrieval_performed:
            raise ValueError("receipt chain must not perform retrieval")
        if self.dispatch_receipt.graph_mutated or self.applied_run_receipt.graph_mutated:
            raise ValueError("receipt chain must not mutate graph")
        if (
            self.dispatch_receipt.final_artifact_created
            or self.applied_run_receipt.final_artifact_created
        ):
            raise ValueError("receipt chain must not create final artifact")
        if self.budget_reservation_receipt.budget_reserved:
            raise ValueError("budget_reservation_receipt must not reserve budget")
        if self.budget_reservation_receipt.provider_calls_made:
            raise ValueError("budget_reservation_receipt must not include provider calls")
        if self.budget_reservation_receipt.retrieval_performed:
            raise ValueError("budget_reservation_receipt must not perform retrieval")
        if self.budget_reservation_receipt.graph_mutated:
            raise ValueError("budget_reservation_receipt must not mutate graph")
        if self.budget_reservation_receipt.final_artifact_created:
            raise ValueError("budget_reservation_receipt must not create final artifact")
        return self


class MidnightOilProviderRouteReceipt(BaseModel):
    receipt_id: str
    budget_reservation_receipt_id: str
    activation_checklist_receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_provider_route_executor_disabled"] = (
        "blocked_provider_route_executor_disabled"
    )
    requested_route_count: int = Field(ge=0)
    planned_role_route_receipt_ids: list[str]
    blocker_reason: Literal["provider_route_executor_missing"] = (
        "provider_route_executor_missing"
    )
    route_executor_allowed: bool = False
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    budget_reserved: bool = False
    dispatch_performed: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    provider_route_notes: list[str] = Field(default_factory=list)


class MidnightOilRetrievalRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    dispatch_receipt: MidnightOilDispatchReceipt
    activation_checklist_receipt: MidnightOilActivationChecklistReceipt
    budget_reservation_receipt: MidnightOilBudgetReservationReceipt
    provider_route_receipt: MidnightOilProviderRouteReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilRetrievalRequest:
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
        if self.activation_checklist_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("activation_checklist_receipt must reference launch_packet")
        if self.activation_checklist_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference approval_receipt")
        if self.activation_checklist_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("activation_checklist_receipt must reference runner_handoff")
        if (
            self.activation_checklist_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("activation_checklist_receipt must reference applied_run_receipt")
        if self.activation_checklist_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference dispatch_receipt")
        if self.activation_checklist_receipt.status != "activation_blocked_controls_missing":
            raise ValueError("activation_checklist_receipt must be activation_blocked_controls_missing")
        if self.activation_checklist_receipt.retrieval_allowed:
            raise ValueError("activation_checklist_receipt must not allow retrieval")
        if self.budget_reservation_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("budget_reservation_receipt must reference launch_packet")
        if self.budget_reservation_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("budget_reservation_receipt must reference approval_receipt")
        if self.budget_reservation_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("budget_reservation_receipt must reference runner_handoff")
        if (
            self.budget_reservation_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("budget_reservation_receipt must reference applied_run_receipt")
        if self.budget_reservation_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("budget_reservation_receipt must reference dispatch_receipt")
        if (
            self.budget_reservation_receipt.activation_checklist_receipt_id
            != self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError(
                "budget_reservation_receipt must reference activation_checklist_receipt"
            )
        if self.provider_route_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("provider_route_receipt must reference launch_packet")
        if self.provider_route_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("provider_route_receipt must reference approval_receipt")
        if self.provider_route_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("provider_route_receipt must reference runner_handoff")
        if self.provider_route_receipt.applied_run_receipt_id != self.applied_run_receipt.receipt_id:
            raise ValueError("provider_route_receipt must reference applied_run_receipt")
        if self.provider_route_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("provider_route_receipt must reference dispatch_receipt")
        if (
            self.provider_route_receipt.activation_checklist_receipt_id
            != self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError("provider_route_receipt must reference activation_checklist_receipt")
        if (
            self.provider_route_receipt.budget_reservation_receipt_id
            != self.budget_reservation_receipt.receipt_id
        ):
            raise ValueError("provider_route_receipt must reference budget_reservation_receipt")
        if self.provider_route_receipt.status != "blocked_provider_route_executor_disabled":
            raise ValueError("provider_route_receipt must be blocked_provider_route_executor_disabled")
        if self.provider_route_receipt.provider_calls_made:
            raise ValueError("provider_route_receipt must not include provider calls")
        if self.provider_route_receipt.retrieval_performed:
            raise ValueError("provider_route_receipt must not perform retrieval")
        if self.provider_route_receipt.graph_mutated:
            raise ValueError("provider_route_receipt must not mutate graph")
        if self.provider_route_receipt.final_artifact_created:
            raise ValueError("provider_route_receipt must not create final artifact")
        if (
            self.dispatch_receipt.dispatch_performed
            or self.applied_run_receipt.dispatch_performed
            or self.budget_reservation_receipt.dispatch_performed
            or self.provider_route_receipt.dispatch_performed
        ):
            raise ValueError("receipt chain must not dispatch")
        if (
            self.dispatch_receipt.budget_reserved
            or self.applied_run_receipt.budget_reserved
            or self.budget_reservation_receipt.budget_reserved
            or self.provider_route_receipt.budget_reserved
        ):
            raise ValueError("receipt chain must not reserve budget")
        if (
            self.dispatch_receipt.provider_calls_made
            or self.applied_run_receipt.provider_calls_made
            or self.budget_reservation_receipt.provider_calls_made
            or self.provider_route_receipt.provider_calls_made
        ):
            raise ValueError("receipt chain must not include provider calls")
        if (
            self.dispatch_receipt.retrieval_performed
            or self.applied_run_receipt.retrieval_performed
            or self.budget_reservation_receipt.retrieval_performed
            or self.provider_route_receipt.retrieval_performed
        ):
            raise ValueError("receipt chain must not perform retrieval")
        if (
            self.dispatch_receipt.graph_mutated
            or self.applied_run_receipt.graph_mutated
            or self.budget_reservation_receipt.graph_mutated
            or self.provider_route_receipt.graph_mutated
        ):
            raise ValueError("receipt chain must not mutate graph")
        if (
            self.dispatch_receipt.final_artifact_created
            or self.applied_run_receipt.final_artifact_created
            or self.budget_reservation_receipt.final_artifact_created
            or self.provider_route_receipt.final_artifact_created
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilRetrievalReceipt(BaseModel):
    receipt_id: str
    provider_route_receipt_id: str
    budget_reservation_receipt_id: str
    activation_checklist_receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_retrieval_executor_disabled"] = (
        "blocked_retrieval_executor_disabled"
    )
    planned_source_policy: list[SourcePolicy]
    planned_source_receipt_ids: list[str]
    blocker_reason: Literal["retrieval_executor_missing"] = "retrieval_executor_missing"
    retrieval_allowed: bool = False
    source_receipts_created: bool = False
    retrieval_performed: bool = False
    provider_calls_made: bool = False
    budget_reserved: bool = False
    dispatch_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    retrieval_notes: list[str] = Field(default_factory=list)


class MidnightOilGraphMutationRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    dispatch_receipt: MidnightOilDispatchReceipt
    activation_checklist_receipt: MidnightOilActivationChecklistReceipt
    budget_reservation_receipt: MidnightOilBudgetReservationReceipt
    provider_route_receipt: MidnightOilProviderRouteReceipt
    retrieval_receipt: MidnightOilRetrievalReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilGraphMutationRequest:
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
        if self.activation_checklist_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("activation_checklist_receipt must reference launch_packet")
        if self.activation_checklist_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference approval_receipt")
        if self.activation_checklist_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("activation_checklist_receipt must reference runner_handoff")
        if (
            self.activation_checklist_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("activation_checklist_receipt must reference applied_run_receipt")
        if self.activation_checklist_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("activation_checklist_receipt must reference dispatch_receipt")
        if self.activation_checklist_receipt.status != "activation_blocked_controls_missing":
            raise ValueError("activation_checklist_receipt must be activation_blocked_controls_missing")
        if self.activation_checklist_receipt.graph_mutation_allowed:
            raise ValueError("activation_checklist_receipt must not allow graph mutation")
        if self.budget_reservation_receipt.activation_checklist_receipt_id != (
            self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError(
                "budget_reservation_receipt must reference activation_checklist_receipt"
            )
        if self.provider_route_receipt.budget_reservation_receipt_id != (
            self.budget_reservation_receipt.receipt_id
        ):
            raise ValueError("provider_route_receipt must reference budget_reservation_receipt")
        if self.retrieval_receipt.provider_route_receipt_id != self.provider_route_receipt.receipt_id:
            raise ValueError("retrieval_receipt must reference provider_route_receipt")
        if (
            self.retrieval_receipt.budget_reservation_receipt_id
            != self.budget_reservation_receipt.receipt_id
        ):
            raise ValueError("retrieval_receipt must reference budget_reservation_receipt")
        if (
            self.retrieval_receipt.activation_checklist_receipt_id
            != self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError("retrieval_receipt must reference activation_checklist_receipt")
        if self.retrieval_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("retrieval_receipt must reference dispatch_receipt")
        if self.retrieval_receipt.applied_run_receipt_id != self.applied_run_receipt.receipt_id:
            raise ValueError("retrieval_receipt must reference applied_run_receipt")
        if self.retrieval_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("retrieval_receipt must reference runner_handoff")
        if self.retrieval_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("retrieval_receipt must reference approval_receipt")
        if self.retrieval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("retrieval_receipt must reference launch_packet")
        if self.retrieval_receipt.status != "blocked_retrieval_executor_disabled":
            raise ValueError("retrieval_receipt must be blocked_retrieval_executor_disabled")
        if self.retrieval_receipt.graph_mutated:
            raise ValueError("retrieval_receipt must not mutate graph")
        if self.retrieval_receipt.final_artifact_created:
            raise ValueError("retrieval_receipt must not create final artifact")
        if self.retrieval_receipt.source_receipts_created:
            raise ValueError("retrieval_receipt must not create source receipts")
        if self.retrieval_receipt.retrieval_performed:
            raise ValueError("retrieval_receipt must not perform retrieval")
        if (
            self.dispatch_receipt.dispatch_performed
            or self.applied_run_receipt.dispatch_performed
            or self.budget_reservation_receipt.dispatch_performed
            or self.provider_route_receipt.dispatch_performed
            or self.retrieval_receipt.dispatch_performed
        ):
            raise ValueError("receipt chain must not dispatch")
        if (
            self.dispatch_receipt.budget_reserved
            or self.applied_run_receipt.budget_reserved
            or self.budget_reservation_receipt.budget_reserved
            or self.provider_route_receipt.budget_reserved
            or self.retrieval_receipt.budget_reserved
        ):
            raise ValueError("receipt chain must not reserve budget")
        if (
            self.dispatch_receipt.provider_calls_made
            or self.applied_run_receipt.provider_calls_made
            or self.budget_reservation_receipt.provider_calls_made
            or self.provider_route_receipt.provider_calls_made
            or self.retrieval_receipt.provider_calls_made
        ):
            raise ValueError("receipt chain must not include provider calls")
        if (
            self.dispatch_receipt.graph_mutated
            or self.applied_run_receipt.graph_mutated
            or self.budget_reservation_receipt.graph_mutated
            or self.provider_route_receipt.graph_mutated
            or self.retrieval_receipt.graph_mutated
        ):
            raise ValueError("receipt chain must not mutate graph")
        if (
            self.dispatch_receipt.final_artifact_created
            or self.applied_run_receipt.final_artifact_created
            or self.budget_reservation_receipt.final_artifact_created
            or self.provider_route_receipt.final_artifact_created
            or self.retrieval_receipt.final_artifact_created
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilGraphMutationReceipt(BaseModel):
    receipt_id: str
    retrieval_receipt_id: str
    provider_route_receipt_id: str
    budget_reservation_receipt_id: str
    activation_checklist_receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_graph_mutation_disabled"] = "blocked_graph_mutation_disabled"
    planned_graph_node_ids: list[str]
    planned_graph_edge_ids: list[str]
    blocker_reason: Literal["graph_mutation_writer_missing"] = "graph_mutation_writer_missing"
    graph_mutation_allowed: bool = False
    graph_mutated: bool = False
    source_receipts_created: bool = False
    retrieval_performed: bool = False
    provider_calls_made: bool = False
    budget_reserved: bool = False
    dispatch_performed: bool = False
    final_artifact_created: bool = False
    graph_notes: list[str] = Field(default_factory=list)


class MidnightOilFinalArtifactRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    dispatch_receipt: MidnightOilDispatchReceipt
    activation_checklist_receipt: MidnightOilActivationChecklistReceipt
    budget_reservation_receipt: MidnightOilBudgetReservationReceipt
    provider_route_receipt: MidnightOilProviderRouteReceipt
    retrieval_receipt: MidnightOilRetrievalReceipt
    graph_mutation_receipt: MidnightOilGraphMutationReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilFinalArtifactRequest:
        MidnightOilGraphMutationRequest(
            launch_packet=self.launch_packet,
            approval_receipt=self.approval_receipt,
            runner_handoff=self.runner_handoff,
            applied_run_receipt=self.applied_run_receipt,
            dispatch_receipt=self.dispatch_receipt,
            activation_checklist_receipt=self.activation_checklist_receipt,
            budget_reservation_receipt=self.budget_reservation_receipt,
            provider_route_receipt=self.provider_route_receipt,
            retrieval_receipt=self.retrieval_receipt,
        )
        if self.activation_checklist_receipt.final_artifact_allowed:
            raise ValueError("activation_checklist_receipt must not allow final artifact")
        if self.graph_mutation_receipt.retrieval_receipt_id != self.retrieval_receipt.receipt_id:
            raise ValueError("graph_mutation_receipt must reference retrieval_receipt")
        if (
            self.graph_mutation_receipt.provider_route_receipt_id
            != self.provider_route_receipt.receipt_id
        ):
            raise ValueError("graph_mutation_receipt must reference provider_route_receipt")
        if (
            self.graph_mutation_receipt.budget_reservation_receipt_id
            != self.budget_reservation_receipt.receipt_id
        ):
            raise ValueError("graph_mutation_receipt must reference budget_reservation_receipt")
        if (
            self.graph_mutation_receipt.activation_checklist_receipt_id
            != self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError("graph_mutation_receipt must reference activation_checklist_receipt")
        if self.graph_mutation_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("graph_mutation_receipt must reference dispatch_receipt")
        if (
            self.graph_mutation_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("graph_mutation_receipt must reference applied_run_receipt")
        if self.graph_mutation_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("graph_mutation_receipt must reference runner_handoff")
        if self.graph_mutation_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("graph_mutation_receipt must reference approval_receipt")
        if self.graph_mutation_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("graph_mutation_receipt must reference launch_packet")
        if self.graph_mutation_receipt.status != "blocked_graph_mutation_disabled":
            raise ValueError("graph_mutation_receipt must be blocked_graph_mutation_disabled")
        if self.graph_mutation_receipt.graph_mutation_allowed:
            raise ValueError("graph_mutation_receipt must not allow graph mutation")
        if self.graph_mutation_receipt.graph_mutated:
            raise ValueError("graph_mutation_receipt must not mutate graph")
        if self.graph_mutation_receipt.source_receipts_created:
            raise ValueError("graph_mutation_receipt must not create source receipts")
        if self.graph_mutation_receipt.retrieval_performed:
            raise ValueError("graph_mutation_receipt must not perform retrieval")
        if self.graph_mutation_receipt.provider_calls_made:
            raise ValueError("graph_mutation_receipt must not include provider calls")
        if self.graph_mutation_receipt.budget_reserved:
            raise ValueError("graph_mutation_receipt must not reserve budget")
        if self.graph_mutation_receipt.dispatch_performed:
            raise ValueError("graph_mutation_receipt must not dispatch")
        if self.graph_mutation_receipt.final_artifact_created:
            raise ValueError("graph_mutation_receipt must not create final artifact")
        return self


class MidnightOilFinalArtifactReceipt(BaseModel):
    receipt_id: str
    graph_mutation_receipt_id: str
    retrieval_receipt_id: str
    provider_route_receipt_id: str
    budget_reservation_receipt_id: str
    activation_checklist_receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_final_artifact_writer_disabled"] = (
        "blocked_final_artifact_writer_disabled"
    )
    planned_artifact_id: str
    planned_twin_note_document_id: str
    final_format: Literal["html"] = "html"
    pdf_allowed: bool = False
    blocker_reason: Literal["final_html_artifact_writer_missing"] = (
        "final_html_artifact_writer_missing"
    )
    final_artifact_allowed: bool = False
    final_artifact_created: bool = False
    graph_mutated: bool = False
    source_receipts_created: bool = False
    retrieval_performed: bool = False
    provider_calls_made: bool = False
    budget_reserved: bool = False
    dispatch_performed: bool = False
    artifact_notes: list[str] = Field(default_factory=list)


class MidnightOilRunnerReadinessRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    live_run_activation_settings_receipt: MidnightOilLiveRunActivationSettingsReceipt
    dispatch_receipt: MidnightOilDispatchReceipt
    activation_checklist_receipt: MidnightOilActivationChecklistReceipt
    budget_reservation_receipt: MidnightOilBudgetReservationReceipt
    provider_route_receipt: MidnightOilProviderRouteReceipt
    retrieval_receipt: MidnightOilRetrievalReceipt
    graph_mutation_receipt: MidnightOilGraphMutationReceipt
    final_artifact_receipt: MidnightOilFinalArtifactReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilRunnerReadinessRequest:
        MidnightOilActivationChecklistRequest(
            launch_packet=self.launch_packet,
            approval_receipt=self.approval_receipt,
            runner_handoff=self.runner_handoff,
            applied_run_receipt=self.applied_run_receipt,
            live_run_activation_settings_receipt=self.live_run_activation_settings_receipt,
            dispatch_receipt=self.dispatch_receipt,
        )
        MidnightOilFinalArtifactRequest(
            launch_packet=self.launch_packet,
            approval_receipt=self.approval_receipt,
            runner_handoff=self.runner_handoff,
            applied_run_receipt=self.applied_run_receipt,
            dispatch_receipt=self.dispatch_receipt,
            activation_checklist_receipt=self.activation_checklist_receipt,
            budget_reservation_receipt=self.budget_reservation_receipt,
            provider_route_receipt=self.provider_route_receipt,
            retrieval_receipt=self.retrieval_receipt,
            graph_mutation_receipt=self.graph_mutation_receipt,
        )
        if (
            self.activation_checklist_receipt.live_run_activation_settings_receipt_id
            != self.live_run_activation_settings_receipt.receipt_id
        ):
            raise ValueError(
                "activation_checklist_receipt must reference live_run_activation_settings_receipt"
            )
        if self.final_artifact_receipt.graph_mutation_receipt_id != self.graph_mutation_receipt.receipt_id:
            raise ValueError("final_artifact_receipt must reference graph_mutation_receipt")
        if self.final_artifact_receipt.retrieval_receipt_id != self.retrieval_receipt.receipt_id:
            raise ValueError("final_artifact_receipt must reference retrieval_receipt")
        if (
            self.final_artifact_receipt.provider_route_receipt_id
            != self.provider_route_receipt.receipt_id
        ):
            raise ValueError("final_artifact_receipt must reference provider_route_receipt")
        if (
            self.final_artifact_receipt.budget_reservation_receipt_id
            != self.budget_reservation_receipt.receipt_id
        ):
            raise ValueError("final_artifact_receipt must reference budget_reservation_receipt")
        if (
            self.final_artifact_receipt.activation_checklist_receipt_id
            != self.activation_checklist_receipt.receipt_id
        ):
            raise ValueError("final_artifact_receipt must reference activation_checklist_receipt")
        if self.final_artifact_receipt.dispatch_receipt_id != self.dispatch_receipt.receipt_id:
            raise ValueError("final_artifact_receipt must reference dispatch_receipt")
        if (
            self.final_artifact_receipt.applied_run_receipt_id
            != self.applied_run_receipt.receipt_id
        ):
            raise ValueError("final_artifact_receipt must reference applied_run_receipt")
        if self.final_artifact_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("final_artifact_receipt must reference runner_handoff")
        if self.final_artifact_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("final_artifact_receipt must reference approval_receipt")
        if self.final_artifact_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("final_artifact_receipt must reference launch_packet")
        if self.final_artifact_receipt.status != "blocked_final_artifact_writer_disabled":
            raise ValueError("final_artifact_receipt must be blocked_final_artifact_writer_disabled")
        if self.final_artifact_receipt.final_artifact_allowed:
            raise ValueError("final_artifact_receipt must not allow final artifact")
        if self.final_artifact_receipt.final_artifact_created:
            raise ValueError("final_artifact_receipt must not create final artifact")
        if self.final_artifact_receipt.graph_mutated:
            raise ValueError("final_artifact_receipt must not mutate graph")
        if self.final_artifact_receipt.source_receipts_created:
            raise ValueError("final_artifact_receipt must not create source receipts")
        if self.final_artifact_receipt.retrieval_performed:
            raise ValueError("final_artifact_receipt must not perform retrieval")
        if self.final_artifact_receipt.provider_calls_made:
            raise ValueError("final_artifact_receipt must not include provider calls")
        if self.final_artifact_receipt.budget_reserved:
            raise ValueError("final_artifact_receipt must not reserve budget")
        if self.final_artifact_receipt.dispatch_performed:
            raise ValueError("final_artifact_receipt must not dispatch")
        return self


class MidnightOilRunnerReadinessReceipt(BaseModel):
    receipt_id: str
    final_artifact_receipt_id: str
    graph_mutation_receipt_id: str
    retrieval_receipt_id: str
    provider_route_receipt_id: str
    budget_reservation_receipt_id: str
    activation_checklist_receipt_id: str
    live_run_activation_settings_receipt_id: str
    dispatch_receipt_id: str
    applied_run_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_runner_readiness_controls_missing"] = (
        "blocked_runner_readiness_controls_missing"
    )
    completed_receipt_ids: list[str]
    remaining_blockers: list[str]
    blocker_reason: Literal["runner_readiness_controls_missing"] = (
        "runner_readiness_controls_missing"
    )
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    provider_execution_allowed: bool = False
    retrieval_allowed: bool = False
    graph_mutation_allowed: bool = False
    final_artifact_allowed: bool = False
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    readiness_notes: list[str] = Field(default_factory=list)


class MidnightOilRunnerControlRequirement(BaseModel):
    control_key: RunnerControlKey
    blocker: str
    required_artifact: str
    implementation_status: Literal["missing"] = "missing"
    live_enablement_allowed: bool = False


class MidnightOilRunnerControlPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_readiness_receipt: MidnightOilRunnerReadinessReceipt
    requested_control_scope: list[RunnerControlKey] = Field(default_factory=list)

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilRunnerControlPlanRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.runner_readiness_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_readiness_receipt must reference launch_packet")
        if self.runner_readiness_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_readiness_receipt must reference approval_receipt")
        if self.runner_readiness_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("runner_readiness_receipt must reference runner_handoff")
        if self.runner_readiness_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("runner_readiness_receipt run_id must match launch_packet")
        if self.runner_readiness_receipt.status != "blocked_runner_readiness_controls_missing":
            raise ValueError("runner_readiness_receipt must be blocked_runner_readiness_controls_missing")
        if self.runner_readiness_receipt.live_run_allowed:
            raise ValueError("runner_readiness_receipt must not allow live run")
        if self.runner_readiness_receipt.dispatch_allowed or self.runner_readiness_receipt.dispatch_performed:
            raise ValueError("runner_readiness_receipt must not dispatch")
        if (
            self.runner_readiness_receipt.budget_reservation_allowed
            or self.runner_readiness_receipt.budget_reserved
        ):
            raise ValueError("runner_readiness_receipt must not reserve budget")
        if (
            self.runner_readiness_receipt.provider_execution_allowed
            or self.runner_readiness_receipt.provider_calls_made
        ):
            raise ValueError("runner_readiness_receipt must not include provider calls")
        if self.runner_readiness_receipt.retrieval_allowed or self.runner_readiness_receipt.retrieval_performed:
            raise ValueError("runner_readiness_receipt must not perform retrieval")
        if (
            self.runner_readiness_receipt.graph_mutation_allowed
            or self.runner_readiness_receipt.graph_mutated
        ):
            raise ValueError("runner_readiness_receipt must not mutate graph")
        if (
            self.runner_readiness_receipt.final_artifact_allowed
            or self.runner_readiness_receipt.final_artifact_created
        ):
            raise ValueError("runner_readiness_receipt must not create final artifact")
        if not self.requested_control_scope:
            self.requested_control_scope = list(_RUNNER_CONTROL_ORDER)
        if len(set(self.requested_control_scope)) != len(self.requested_control_scope):
            raise ValueError("requested_control_scope must not contain duplicates")
        return self


class MidnightOilRunnerControlPlanReceipt(BaseModel):
    receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_runner_controls_unimplemented"] = (
        "blocked_runner_controls_unimplemented"
    )
    requested_control_scope: list[RunnerControlKey]
    required_control_order: list[RunnerControlKey]
    implementation_requirements: list[MidnightOilRunnerControlRequirement]
    remaining_blockers: list[str]
    blocker_reason: Literal["runner_controls_unimplemented"] = "runner_controls_unimplemented"
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    provider_execution_allowed: bool = False
    retrieval_allowed: bool = False
    graph_mutation_allowed: bool = False
    final_artifact_allowed: bool = False
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    control_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilBudgetProviderAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilBudgetProviderAdapterPlanRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.runner_control_plan_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_control_plan_receipt must reference launch_packet")
        if (
            self.runner_control_plan_receipt.approval_receipt_id
            != self.approval_receipt.receipt_id
        ):
            raise ValueError("runner_control_plan_receipt must reference approval_receipt")
        if self.runner_control_plan_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("runner_control_plan_receipt must reference runner_handoff")
        if self.runner_control_plan_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("runner_control_plan_receipt run_id must match launch_packet")
        if self.runner_control_plan_receipt.status != "blocked_runner_controls_unimplemented":
            raise ValueError("runner_control_plan_receipt must be blocked_runner_controls_unimplemented")
        if "budget_reservation_provider" not in (
            self.runner_control_plan_receipt.requested_control_scope
        ):
            raise ValueError("runner_control_plan_receipt must request budget_reservation_provider")
        if self.runner_control_plan_receipt.live_run_allowed:
            raise ValueError("runner_control_plan_receipt must not allow live run")
        if (
            self.runner_control_plan_receipt.dispatch_allowed
            or self.runner_control_plan_receipt.dispatch_performed
        ):
            raise ValueError("runner_control_plan_receipt must not dispatch")
        if (
            self.runner_control_plan_receipt.budget_reservation_allowed
            or self.runner_control_plan_receipt.budget_reserved
        ):
            raise ValueError("runner_control_plan_receipt must not reserve budget")
        if (
            self.runner_control_plan_receipt.provider_execution_allowed
            or self.runner_control_plan_receipt.provider_calls_made
        ):
            raise ValueError("runner_control_plan_receipt must not include provider calls")
        if (
            self.runner_control_plan_receipt.retrieval_allowed
            or self.runner_control_plan_receipt.retrieval_performed
        ):
            raise ValueError("runner_control_plan_receipt must not perform retrieval")
        if (
            self.runner_control_plan_receipt.graph_mutation_allowed
            or self.runner_control_plan_receipt.graph_mutated
        ):
            raise ValueError("runner_control_plan_receipt must not mutate graph")
        if (
            self.runner_control_plan_receipt.final_artifact_allowed
            or self.runner_control_plan_receipt.final_artifact_created
        ):
            raise ValueError("runner_control_plan_receipt must not create final artifact")
        return self


class MidnightOilBudgetProviderAdapterPlanReceipt(BaseModel):
    receipt_id: str
    runner_control_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_budget_provider_adapter_unimplemented"] = (
        "blocked_budget_provider_adapter_unimplemented"
    )
    adapter_key: Literal["budget_reservation_provider"] = "budget_reservation_provider"
    planned_adapter_id: str
    planned_ledger_id: str
    idempotency_key: str
    approved_price_ceiling_usd: float = Field(ge=0.0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    required_invariants: list[str]
    required_ledger_fields: list[str]
    blocker_reason: Literal["budget_provider_adapter_unimplemented"] = (
        "budget_provider_adapter_unimplemented"
    )
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    provider_execution_allowed: bool = False
    retrieval_allowed: bool = False
    graph_mutation_allowed: bool = False
    final_artifact_allowed: bool = False
    dispatch_performed: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilProviderExecutorAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt
    budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilProviderExecutorAdapterPlanRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.runner_control_plan_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_control_plan_receipt must reference launch_packet")
        if self.runner_control_plan_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_control_plan_receipt must reference approval_receipt")
        if self.runner_control_plan_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("runner_control_plan_receipt must reference runner_handoff")
        if self.runner_control_plan_receipt.status != "blocked_runner_controls_unimplemented":
            raise ValueError("runner_control_plan_receipt must be blocked_runner_controls_unimplemented")
        if "model_provider_route_executor" not in (
            self.runner_control_plan_receipt.requested_control_scope
        ):
            raise ValueError("runner_control_plan_receipt must request model_provider_route_executor")
        if (
            self.budget_provider_adapter_plan_receipt.launch_packet_id
            != self.launch_packet.packet_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference launch_packet")
        if (
            self.budget_provider_adapter_plan_receipt.approval_receipt_id
            != self.approval_receipt.receipt_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference approval_receipt")
        if (
            self.budget_provider_adapter_plan_receipt.runner_handoff_id
            != self.runner_handoff.handoff_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference runner_handoff")
        if (
            self.budget_provider_adapter_plan_receipt.runner_control_plan_receipt_id
            != self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference runner_control_plan_receipt")
        if (
            self.budget_provider_adapter_plan_receipt.status
            != "blocked_budget_provider_adapter_unimplemented"
        ):
            raise ValueError(
                "budget_provider_adapter_plan_receipt must be blocked_budget_provider_adapter_unimplemented"
            )
        if (
            self.runner_control_plan_receipt.live_run_allowed
            or self.budget_provider_adapter_plan_receipt.live_run_allowed
        ):
            raise ValueError("receipt chain must not allow live run")
        if (
            self.runner_control_plan_receipt.dispatch_allowed
            or self.runner_control_plan_receipt.dispatch_performed
            or self.budget_provider_adapter_plan_receipt.dispatch_allowed
            or self.budget_provider_adapter_plan_receipt.dispatch_performed
        ):
            raise ValueError("receipt chain must not dispatch")
        if (
            self.runner_control_plan_receipt.budget_reservation_allowed
            or self.runner_control_plan_receipt.budget_reserved
            or self.budget_provider_adapter_plan_receipt.budget_reservation_allowed
            or self.budget_provider_adapter_plan_receipt.budget_reserved
        ):
            raise ValueError("receipt chain must not reserve budget")
        if (
            self.runner_control_plan_receipt.provider_execution_allowed
            or self.runner_control_plan_receipt.provider_calls_made
            or self.budget_provider_adapter_plan_receipt.provider_execution_allowed
            or self.budget_provider_adapter_plan_receipt.provider_calls_made
        ):
            raise ValueError("receipt chain must not include provider calls")
        if (
            self.runner_control_plan_receipt.retrieval_allowed
            or self.runner_control_plan_receipt.retrieval_performed
            or self.budget_provider_adapter_plan_receipt.retrieval_allowed
            or self.budget_provider_adapter_plan_receipt.retrieval_performed
        ):
            raise ValueError("receipt chain must not perform retrieval")
        if (
            self.runner_control_plan_receipt.graph_mutation_allowed
            or self.runner_control_plan_receipt.graph_mutated
            or self.budget_provider_adapter_plan_receipt.graph_mutation_allowed
            or self.budget_provider_adapter_plan_receipt.graph_mutated
        ):
            raise ValueError("receipt chain must not mutate graph")
        if (
            self.runner_control_plan_receipt.final_artifact_allowed
            or self.runner_control_plan_receipt.final_artifact_created
            or self.budget_provider_adapter_plan_receipt.final_artifact_allowed
            or self.budget_provider_adapter_plan_receipt.final_artifact_created
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilProviderExecutorAdapterPlanReceipt(BaseModel):
    receipt_id: str
    runner_control_plan_receipt_id: str
    budget_provider_adapter_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_provider_executor_adapter_unimplemented"] = (
        "blocked_provider_executor_adapter_unimplemented"
    )
    adapter_key: Literal["model_provider_route_executor"] = "model_provider_route_executor"
    planned_executor_id: str
    planned_route_ledger_id: str
    planned_role_route_receipt_ids: list[str]
    requested_route_count: int = Field(ge=0)
    route_mode: RouteMode
    provider_policy: Literal["operator_configured_models_only"] = "operator_configured_models_only"
    required_invariants: list[str]
    required_route_receipt_fields: list[str]
    blocker_reason: Literal["provider_executor_adapter_unimplemented"] = (
        "provider_executor_adapter_unimplemented"
    )
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    retrieval_allowed: bool = False
    graph_mutation_allowed: bool = False
    final_artifact_allowed: bool = False
    dispatch_performed: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilRetrievalAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt
    budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt
    provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilRetrievalAdapterPlanRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.runner_control_plan_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_control_plan_receipt must reference launch_packet")
        if self.runner_control_plan_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_control_plan_receipt must reference approval_receipt")
        if self.runner_control_plan_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("runner_control_plan_receipt must reference runner_handoff")
        if self.runner_control_plan_receipt.status != "blocked_runner_controls_unimplemented":
            raise ValueError("runner_control_plan_receipt must be blocked_runner_controls_unimplemented")
        if "retrieval_executor_source_receipts" not in (
            self.runner_control_plan_receipt.requested_control_scope
        ):
            raise ValueError(
                "runner_control_plan_receipt must request retrieval_executor_source_receipts"
            )
        if (
            self.budget_provider_adapter_plan_receipt.launch_packet_id
            != self.launch_packet.packet_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference launch_packet")
        if (
            self.budget_provider_adapter_plan_receipt.approval_receipt_id
            != self.approval_receipt.receipt_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference approval_receipt")
        if (
            self.budget_provider_adapter_plan_receipt.runner_handoff_id
            != self.runner_handoff.handoff_id
        ):
            raise ValueError("budget_provider_adapter_plan_receipt must reference runner_handoff")
        if (
            self.budget_provider_adapter_plan_receipt.runner_control_plan_receipt_id
            != self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError(
                "budget_provider_adapter_plan_receipt must reference runner_control_plan_receipt"
            )
        if (
            self.budget_provider_adapter_plan_receipt.status
            != "blocked_budget_provider_adapter_unimplemented"
        ):
            raise ValueError(
                "budget_provider_adapter_plan_receipt must be blocked_budget_provider_adapter_unimplemented"
            )
        if (
            self.provider_executor_adapter_plan_receipt.launch_packet_id
            != self.launch_packet.packet_id
        ):
            raise ValueError("provider_executor_adapter_plan_receipt must reference launch_packet")
        if (
            self.provider_executor_adapter_plan_receipt.approval_receipt_id
            != self.approval_receipt.receipt_id
        ):
            raise ValueError("provider_executor_adapter_plan_receipt must reference approval_receipt")
        if (
            self.provider_executor_adapter_plan_receipt.runner_handoff_id
            != self.runner_handoff.handoff_id
        ):
            raise ValueError("provider_executor_adapter_plan_receipt must reference runner_handoff")
        if (
            self.provider_executor_adapter_plan_receipt.runner_control_plan_receipt_id
            != self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError(
                "provider_executor_adapter_plan_receipt must reference runner_control_plan_receipt"
            )
        if (
            self.provider_executor_adapter_plan_receipt.budget_provider_adapter_plan_receipt_id
            != self.budget_provider_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "provider_executor_adapter_plan_receipt must reference budget_provider_adapter_plan_receipt"
            )
        if (
            self.provider_executor_adapter_plan_receipt.status
            != "blocked_provider_executor_adapter_unimplemented"
        ):
            raise ValueError(
                "provider_executor_adapter_plan_receipt must be blocked_provider_executor_adapter_unimplemented"
            )
        if (
            self.runner_control_plan_receipt.live_run_allowed
            or self.budget_provider_adapter_plan_receipt.live_run_allowed
            or self.provider_executor_adapter_plan_receipt.live_run_allowed
        ):
            raise ValueError("receipt chain must not allow live run")
        if (
            self.runner_control_plan_receipt.dispatch_allowed
            or self.runner_control_plan_receipt.dispatch_performed
            or self.budget_provider_adapter_plan_receipt.dispatch_allowed
            or self.budget_provider_adapter_plan_receipt.dispatch_performed
            or self.provider_executor_adapter_plan_receipt.dispatch_allowed
            or self.provider_executor_adapter_plan_receipt.dispatch_performed
        ):
            raise ValueError("receipt chain must not dispatch")
        if (
            self.runner_control_plan_receipt.budget_reservation_allowed
            or self.runner_control_plan_receipt.budget_reserved
            or self.budget_provider_adapter_plan_receipt.budget_reservation_allowed
            or self.budget_provider_adapter_plan_receipt.budget_reserved
            or self.provider_executor_adapter_plan_receipt.budget_reservation_allowed
            or self.provider_executor_adapter_plan_receipt.budget_reserved
        ):
            raise ValueError("receipt chain must not reserve budget")
        if (
            self.runner_control_plan_receipt.provider_execution_allowed
            or self.runner_control_plan_receipt.provider_calls_made
            or self.budget_provider_adapter_plan_receipt.provider_execution_allowed
            or self.budget_provider_adapter_plan_receipt.provider_calls_made
            or self.provider_executor_adapter_plan_receipt.provider_execution_allowed
            or self.provider_executor_adapter_plan_receipt.provider_calls_made
        ):
            raise ValueError("receipt chain must not include provider calls")
        if (
            self.runner_control_plan_receipt.retrieval_allowed
            or self.runner_control_plan_receipt.retrieval_performed
            or self.budget_provider_adapter_plan_receipt.retrieval_allowed
            or self.budget_provider_adapter_plan_receipt.retrieval_performed
            or self.provider_executor_adapter_plan_receipt.retrieval_allowed
            or self.provider_executor_adapter_plan_receipt.retrieval_performed
        ):
            raise ValueError("receipt chain must not perform retrieval")
        if (
            self.runner_control_plan_receipt.graph_mutation_allowed
            or self.runner_control_plan_receipt.graph_mutated
            or self.budget_provider_adapter_plan_receipt.graph_mutation_allowed
            or self.budget_provider_adapter_plan_receipt.graph_mutated
            or self.provider_executor_adapter_plan_receipt.graph_mutation_allowed
            or self.provider_executor_adapter_plan_receipt.graph_mutated
        ):
            raise ValueError("receipt chain must not mutate graph")
        if (
            self.runner_control_plan_receipt.final_artifact_allowed
            or self.runner_control_plan_receipt.final_artifact_created
            or self.budget_provider_adapter_plan_receipt.final_artifact_allowed
            or self.budget_provider_adapter_plan_receipt.final_artifact_created
            or self.provider_executor_adapter_plan_receipt.final_artifact_allowed
            or self.provider_executor_adapter_plan_receipt.final_artifact_created
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilRetrievalAdapterPlanReceipt(BaseModel):
    receipt_id: str
    runner_control_plan_receipt_id: str
    budget_provider_adapter_plan_receipt_id: str
    provider_executor_adapter_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_retrieval_adapter_unimplemented"] = (
        "blocked_retrieval_adapter_unimplemented"
    )
    adapter_key: Literal["retrieval_executor_source_receipts"] = (
        "retrieval_executor_source_receipts"
    )
    planned_executor_id: str
    planned_source_ledger_id: str
    planned_source_policy: list[SourcePolicy]
    planned_source_receipt_ids: list[str]
    requested_source_count: int = Field(ge=0)
    required_invariants: list[str]
    required_source_receipt_fields: list[str]
    blocker_reason: Literal["retrieval_adapter_unimplemented"] = (
        "retrieval_adapter_unimplemented"
    )
    retrieval_allowed: bool = False
    retrieval_performed: bool = False
    source_receipts_created: bool = False
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    graph_mutation_allowed: bool = False
    final_artifact_allowed: bool = False
    dispatch_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilGraphAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt
    budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt
    provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt
    retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilGraphAdapterPlanRequest:
        if self.approval_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if self.runner_handoff.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if self.runner_handoff.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if self.runner_control_plan_receipt.launch_packet_id != self.launch_packet.packet_id:
            raise ValueError("runner_control_plan_receipt must reference launch_packet")
        if self.runner_control_plan_receipt.approval_receipt_id != self.approval_receipt.receipt_id:
            raise ValueError("runner_control_plan_receipt must reference approval_receipt")
        if self.runner_control_plan_receipt.runner_handoff_id != self.runner_handoff.handoff_id:
            raise ValueError("runner_control_plan_receipt must reference runner_handoff")
        if self.runner_control_plan_receipt.status != "blocked_runner_controls_unimplemented":
            raise ValueError("runner_control_plan_receipt must be blocked_runner_controls_unimplemented")
        if "graph_mutation_writer" not in self.runner_control_plan_receipt.requested_control_scope:
            raise ValueError("runner_control_plan_receipt must request graph_mutation_writer")
        if (
            self.budget_provider_adapter_plan_receipt.runner_control_plan_receipt_id
            != self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError(
                "budget_provider_adapter_plan_receipt must reference runner_control_plan_receipt"
            )
        if (
            self.budget_provider_adapter_plan_receipt.status
            != "blocked_budget_provider_adapter_unimplemented"
        ):
            raise ValueError(
                "budget_provider_adapter_plan_receipt must be blocked_budget_provider_adapter_unimplemented"
            )
        if (
            self.provider_executor_adapter_plan_receipt.budget_provider_adapter_plan_receipt_id
            != self.budget_provider_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "provider_executor_adapter_plan_receipt must reference budget_provider_adapter_plan_receipt"
            )
        if (
            self.provider_executor_adapter_plan_receipt.status
            != "blocked_provider_executor_adapter_unimplemented"
        ):
            raise ValueError(
                "provider_executor_adapter_plan_receipt must be blocked_provider_executor_adapter_unimplemented"
            )
        if (
            self.retrieval_adapter_plan_receipt.provider_executor_adapter_plan_receipt_id
            != self.provider_executor_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "retrieval_adapter_plan_receipt must reference provider_executor_adapter_plan_receipt"
            )
        if (
            self.retrieval_adapter_plan_receipt.budget_provider_adapter_plan_receipt_id
            != self.budget_provider_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "retrieval_adapter_plan_receipt must reference budget_provider_adapter_plan_receipt"
            )
        if (
            self.retrieval_adapter_plan_receipt.runner_control_plan_receipt_id
            != self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError(
                "retrieval_adapter_plan_receipt must reference runner_control_plan_receipt"
            )
        if self.retrieval_adapter_plan_receipt.status != "blocked_retrieval_adapter_unimplemented":
            raise ValueError(
                "retrieval_adapter_plan_receipt must be blocked_retrieval_adapter_unimplemented"
            )
        receipts = (
            self.runner_control_plan_receipt,
            self.budget_provider_adapter_plan_receipt,
            self.provider_executor_adapter_plan_receipt,
            self.retrieval_adapter_plan_receipt,
        )
        if any(receipt.live_run_allowed for receipt in receipts):
            raise ValueError("receipt chain must not allow live run")
        if any(receipt.dispatch_allowed or receipt.dispatch_performed for receipt in receipts):
            raise ValueError("receipt chain must not dispatch")
        if any(
            receipt.budget_reservation_allowed or receipt.budget_reserved for receipt in receipts
        ):
            raise ValueError("receipt chain must not reserve budget")
        if any(
            receipt.provider_execution_allowed or receipt.provider_calls_made
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not include provider calls")
        if any(receipt.retrieval_allowed or receipt.retrieval_performed for receipt in receipts):
            raise ValueError("receipt chain must not perform retrieval")
        if self.retrieval_adapter_plan_receipt.source_receipts_created:
            raise ValueError("receipt chain must not create source receipts")
        if any(receipt.graph_mutation_allowed or receipt.graph_mutated for receipt in receipts):
            raise ValueError("receipt chain must not mutate graph")
        if any(
            receipt.final_artifact_allowed or receipt.final_artifact_created
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilGraphAdapterPlanReceipt(BaseModel):
    receipt_id: str
    runner_control_plan_receipt_id: str
    budget_provider_adapter_plan_receipt_id: str
    provider_executor_adapter_plan_receipt_id: str
    retrieval_adapter_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_graph_adapter_unimplemented"] = (
        "blocked_graph_adapter_unimplemented"
    )
    adapter_key: Literal["graph_mutation_writer"] = "graph_mutation_writer"
    planned_writer_id: str
    planned_graph_ledger_id: str
    planned_graph_node_ids: list[str]
    planned_graph_edge_ids: list[str]
    required_invariants: list[str]
    required_graph_receipt_fields: list[str]
    blocker_reason: Literal["graph_adapter_unimplemented"] = "graph_adapter_unimplemented"
    graph_mutation_allowed: bool = False
    graph_mutated: bool = False
    source_receipts_created: bool = False
    retrieval_allowed: bool = False
    retrieval_performed: bool = False
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    final_artifact_allowed: bool = False
    dispatch_performed: bool = False
    final_artifact_created: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilFinalArtifactAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt
    budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt
    provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt
    retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt
    graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilFinalArtifactAdapterPlanRequest:
        MidnightOilGraphAdapterPlanRequest(
            launch_packet=self.launch_packet,
            approval_receipt=self.approval_receipt,
            runner_handoff=self.runner_handoff,
            runner_control_plan_receipt=self.runner_control_plan_receipt,
            budget_provider_adapter_plan_receipt=self.budget_provider_adapter_plan_receipt,
            provider_executor_adapter_plan_receipt=self.provider_executor_adapter_plan_receipt,
            retrieval_adapter_plan_receipt=self.retrieval_adapter_plan_receipt,
        )
        if "final_html_artifact_writer" not in (
            self.runner_control_plan_receipt.requested_control_scope
        ):
            raise ValueError("runner_control_plan_receipt must request final_html_artifact_writer")
        if self.graph_adapter_plan_receipt.runner_control_plan_receipt_id != (
            self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError("graph_adapter_plan_receipt must reference runner_control_plan_receipt")
        if self.graph_adapter_plan_receipt.budget_provider_adapter_plan_receipt_id != (
            self.budget_provider_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "graph_adapter_plan_receipt must reference budget_provider_adapter_plan_receipt"
            )
        if self.graph_adapter_plan_receipt.provider_executor_adapter_plan_receipt_id != (
            self.provider_executor_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "graph_adapter_plan_receipt must reference provider_executor_adapter_plan_receipt"
            )
        if (
            self.graph_adapter_plan_receipt.retrieval_adapter_plan_receipt_id
            != self.retrieval_adapter_plan_receipt.receipt_id
        ):
            raise ValueError("graph_adapter_plan_receipt must reference retrieval_adapter_plan_receipt")
        if self.graph_adapter_plan_receipt.status != "blocked_graph_adapter_unimplemented":
            raise ValueError("graph_adapter_plan_receipt must be blocked_graph_adapter_unimplemented")
        if self.launch_packet.artifact_contract.final_format != "html":
            raise ValueError("launch_packet artifact contract must require html")
        if self.launch_packet.artifact_contract.pdf_allowed:
            raise ValueError("launch_packet artifact contract must not allow pdf")
        receipts = (
            self.runner_control_plan_receipt,
            self.budget_provider_adapter_plan_receipt,
            self.provider_executor_adapter_plan_receipt,
            self.retrieval_adapter_plan_receipt,
            self.graph_adapter_plan_receipt,
        )
        if any(receipt.live_run_allowed for receipt in receipts):
            raise ValueError("receipt chain must not allow live run")
        if any(receipt.dispatch_allowed or receipt.dispatch_performed for receipt in receipts):
            raise ValueError("receipt chain must not dispatch")
        if any(
            receipt.budget_reservation_allowed or receipt.budget_reserved for receipt in receipts
        ):
            raise ValueError("receipt chain must not reserve budget")
        if any(
            receipt.provider_execution_allowed or receipt.provider_calls_made
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not include provider calls")
        if any(receipt.retrieval_allowed or receipt.retrieval_performed for receipt in receipts):
            raise ValueError("receipt chain must not perform retrieval")
        if (
            self.retrieval_adapter_plan_receipt.source_receipts_created
            or self.graph_adapter_plan_receipt.source_receipts_created
        ):
            raise ValueError("receipt chain must not create source receipts")
        if any(receipt.graph_mutation_allowed or receipt.graph_mutated for receipt in receipts):
            raise ValueError("receipt chain must not mutate graph")
        if any(
            receipt.final_artifact_allowed or receipt.final_artifact_created
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilFinalArtifactAdapterPlanReceipt(BaseModel):
    receipt_id: str
    runner_control_plan_receipt_id: str
    budget_provider_adapter_plan_receipt_id: str
    provider_executor_adapter_plan_receipt_id: str
    retrieval_adapter_plan_receipt_id: str
    graph_adapter_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_final_artifact_adapter_unimplemented"] = (
        "blocked_final_artifact_adapter_unimplemented"
    )
    adapter_key: Literal["final_html_artifact_writer"] = "final_html_artifact_writer"
    planned_writer_id: str
    planned_artifact_ledger_id: str
    planned_artifact_id: str
    planned_twin_note_document_id: str
    final_format: Literal["html"] = "html"
    pdf_allowed: bool = False
    required_invariants: list[str]
    required_artifact_receipt_fields: list[str]
    blocker_reason: Literal["final_artifact_adapter_unimplemented"] = (
        "final_artifact_adapter_unimplemented"
    )
    final_artifact_allowed: bool = False
    final_artifact_created: bool = False
    graph_mutation_allowed: bool = False
    graph_mutated: bool = False
    source_receipts_created: bool = False
    retrieval_allowed: bool = False
    retrieval_performed: bool = False
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    dispatch_performed: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilOperatorDispatchAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt
    budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt
    provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt
    retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt
    graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt
    final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilOperatorDispatchAdapterPlanRequest:
        MidnightOilFinalArtifactAdapterPlanRequest(
            launch_packet=self.launch_packet,
            approval_receipt=self.approval_receipt,
            runner_handoff=self.runner_handoff,
            runner_control_plan_receipt=self.runner_control_plan_receipt,
            budget_provider_adapter_plan_receipt=self.budget_provider_adapter_plan_receipt,
            provider_executor_adapter_plan_receipt=self.provider_executor_adapter_plan_receipt,
            retrieval_adapter_plan_receipt=self.retrieval_adapter_plan_receipt,
            graph_adapter_plan_receipt=self.graph_adapter_plan_receipt,
        )
        if "operator_live_dispatch_enablement" not in (
            self.runner_control_plan_receipt.requested_control_scope
        ):
            raise ValueError(
                "runner_control_plan_receipt must request operator_live_dispatch_enablement"
            )
        if self.final_artifact_adapter_plan_receipt.runner_control_plan_receipt_id != (
            self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError(
                "final_artifact_adapter_plan_receipt must reference runner_control_plan_receipt"
            )
        if self.final_artifact_adapter_plan_receipt.budget_provider_adapter_plan_receipt_id != (
            self.budget_provider_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "final_artifact_adapter_plan_receipt must reference budget_provider_adapter_plan_receipt"
            )
        if self.final_artifact_adapter_plan_receipt.provider_executor_adapter_plan_receipt_id != (
            self.provider_executor_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "final_artifact_adapter_plan_receipt must reference provider_executor_adapter_plan_receipt"
            )
        if self.final_artifact_adapter_plan_receipt.retrieval_adapter_plan_receipt_id != (
            self.retrieval_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "final_artifact_adapter_plan_receipt must reference retrieval_adapter_plan_receipt"
            )
        if self.final_artifact_adapter_plan_receipt.graph_adapter_plan_receipt_id != (
            self.graph_adapter_plan_receipt.receipt_id
        ):
            raise ValueError("final_artifact_adapter_plan_receipt must reference graph_adapter_plan_receipt")
        if (
            self.final_artifact_adapter_plan_receipt.status
            != "blocked_final_artifact_adapter_unimplemented"
        ):
            raise ValueError(
                "final_artifact_adapter_plan_receipt must be blocked_final_artifact_adapter_unimplemented"
            )
        receipts = (
            self.runner_control_plan_receipt,
            self.budget_provider_adapter_plan_receipt,
            self.provider_executor_adapter_plan_receipt,
            self.retrieval_adapter_plan_receipt,
            self.graph_adapter_plan_receipt,
            self.final_artifact_adapter_plan_receipt,
        )
        if any(receipt.live_run_allowed for receipt in receipts):
            raise ValueError("receipt chain must not allow live run")
        if any(receipt.dispatch_allowed or receipt.dispatch_performed for receipt in receipts):
            raise ValueError("receipt chain must not dispatch")
        if any(
            receipt.budget_reservation_allowed or receipt.budget_reserved for receipt in receipts
        ):
            raise ValueError("receipt chain must not reserve budget")
        if any(
            receipt.provider_execution_allowed or receipt.provider_calls_made
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not include provider calls")
        if any(receipt.retrieval_allowed or receipt.retrieval_performed for receipt in receipts):
            raise ValueError("receipt chain must not perform retrieval")
        if (
            self.retrieval_adapter_plan_receipt.source_receipts_created
            or self.graph_adapter_plan_receipt.source_receipts_created
            or self.final_artifact_adapter_plan_receipt.source_receipts_created
        ):
            raise ValueError("receipt chain must not create source receipts")
        if any(receipt.graph_mutation_allowed or receipt.graph_mutated for receipt in receipts):
            raise ValueError("receipt chain must not mutate graph")
        if any(
            receipt.final_artifact_allowed or receipt.final_artifact_created
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not create final artifact")
        return self


class MidnightOilOperatorDispatchAdapterPlanReceipt(BaseModel):
    receipt_id: str
    runner_control_plan_receipt_id: str
    budget_provider_adapter_plan_receipt_id: str
    provider_executor_adapter_plan_receipt_id: str
    retrieval_adapter_plan_receipt_id: str
    graph_adapter_plan_receipt_id: str
    final_artifact_adapter_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_operator_dispatch_adapter_unimplemented"] = (
        "blocked_operator_dispatch_adapter_unimplemented"
    )
    adapter_key: Literal["operator_live_dispatch_enablement"] = (
        "operator_live_dispatch_enablement"
    )
    planned_setting_id: str
    planned_control_ledger_id: str
    required_invariants: list[str]
    required_dispatch_enablement_fields: list[str]
    blocker_reason: Literal["operator_dispatch_adapter_unimplemented"] = (
        "operator_dispatch_adapter_unimplemented"
    )
    operator_dispatch_allowed: bool = False
    operator_live_dispatch_enabled: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    dispatch_performed: bool = False
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    retrieval_allowed: bool = False
    retrieval_performed: bool = False
    source_receipts_created: bool = False
    graph_mutation_allowed: bool = False
    graph_mutated: bool = False
    final_artifact_allowed: bool = False
    final_artifact_created: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


class MidnightOilControlLedgerAdapterPlanRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt
    budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt
    provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt
    retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt
    graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt
    final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt
    operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt

    @model_validator(mode="after")
    def _receipt_chain_matches(self) -> MidnightOilControlLedgerAdapterPlanRequest:
        MidnightOilOperatorDispatchAdapterPlanRequest(
            launch_packet=self.launch_packet,
            approval_receipt=self.approval_receipt,
            runner_handoff=self.runner_handoff,
            runner_control_plan_receipt=self.runner_control_plan_receipt,
            budget_provider_adapter_plan_receipt=self.budget_provider_adapter_plan_receipt,
            provider_executor_adapter_plan_receipt=self.provider_executor_adapter_plan_receipt,
            retrieval_adapter_plan_receipt=self.retrieval_adapter_plan_receipt,
            graph_adapter_plan_receipt=self.graph_adapter_plan_receipt,
            final_artifact_adapter_plan_receipt=self.final_artifact_adapter_plan_receipt,
        )
        if (
            self.operator_dispatch_adapter_plan_receipt.runner_control_plan_receipt_id
            != self.runner_control_plan_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference runner_control_plan_receipt"
            )
        if self.operator_dispatch_adapter_plan_receipt.run_id != self.launch_packet.run_id:
            raise ValueError("operator_dispatch_adapter_plan_receipt must reference launch run")
        if (
            self.operator_dispatch_adapter_plan_receipt.launch_packet_id
            != self.launch_packet.packet_id
        ):
            raise ValueError("operator_dispatch_adapter_plan_receipt must reference launch_packet")
        if (
            self.operator_dispatch_adapter_plan_receipt.approval_receipt_id
            != self.approval_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference approval_receipt"
            )
        if (
            self.operator_dispatch_adapter_plan_receipt.runner_handoff_id
            != self.runner_handoff.handoff_id
        ):
            raise ValueError("operator_dispatch_adapter_plan_receipt must reference runner_handoff")
        if self.operator_dispatch_adapter_plan_receipt.budget_provider_adapter_plan_receipt_id != (
            self.budget_provider_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference budget_provider_adapter_plan_receipt"
            )
        if (
            self.operator_dispatch_adapter_plan_receipt.provider_executor_adapter_plan_receipt_id
            != self.provider_executor_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference provider_executor_adapter_plan_receipt"
            )
        if self.operator_dispatch_adapter_plan_receipt.retrieval_adapter_plan_receipt_id != (
            self.retrieval_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference retrieval_adapter_plan_receipt"
            )
        if self.operator_dispatch_adapter_plan_receipt.graph_adapter_plan_receipt_id != (
            self.graph_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference graph_adapter_plan_receipt"
            )
        if (
            self.operator_dispatch_adapter_plan_receipt.final_artifact_adapter_plan_receipt_id
            != self.final_artifact_adapter_plan_receipt.receipt_id
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must reference final_artifact_adapter_plan_receipt"
            )
        if (
            self.operator_dispatch_adapter_plan_receipt.status
            != "blocked_operator_dispatch_adapter_unimplemented"
        ):
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must be blocked_operator_dispatch_adapter_unimplemented"
            )
        receipts = (
            self.runner_control_plan_receipt,
            self.budget_provider_adapter_plan_receipt,
            self.provider_executor_adapter_plan_receipt,
            self.retrieval_adapter_plan_receipt,
            self.graph_adapter_plan_receipt,
            self.final_artifact_adapter_plan_receipt,
            self.operator_dispatch_adapter_plan_receipt,
        )
        if any(receipt.live_run_allowed for receipt in receipts):
            raise ValueError("receipt chain must not allow live run")
        if any(receipt.dispatch_allowed or receipt.dispatch_performed for receipt in receipts):
            raise ValueError("receipt chain must not dispatch")
        if any(
            receipt.budget_reservation_allowed or receipt.budget_reserved for receipt in receipts
        ):
            raise ValueError("receipt chain must not reserve budget")
        if any(
            receipt.provider_execution_allowed or receipt.provider_calls_made
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not include provider calls")
        if any(receipt.retrieval_allowed or receipt.retrieval_performed for receipt in receipts):
            raise ValueError("receipt chain must not perform retrieval")
        if (
            self.retrieval_adapter_plan_receipt.source_receipts_created
            or self.graph_adapter_plan_receipt.source_receipts_created
            or self.final_artifact_adapter_plan_receipt.source_receipts_created
            or self.operator_dispatch_adapter_plan_receipt.source_receipts_created
        ):
            raise ValueError("receipt chain must not create source receipts")
        if any(receipt.graph_mutation_allowed or receipt.graph_mutated for receipt in receipts):
            raise ValueError("receipt chain must not mutate graph")
        if any(
            receipt.final_artifact_allowed or receipt.final_artifact_created
            for receipt in receipts
        ):
            raise ValueError("receipt chain must not create final artifact")
        if self.operator_dispatch_adapter_plan_receipt.operator_dispatch_allowed:
            raise ValueError("operator_dispatch_adapter_plan_receipt must not allow dispatch")
        if self.operator_dispatch_adapter_plan_receipt.operator_live_dispatch_enabled:
            raise ValueError(
                "operator_dispatch_adapter_plan_receipt must not enable live dispatch"
            )
        return self


class MidnightOilControlLedgerAdapterPlanReceipt(BaseModel):
    receipt_id: str
    operator_dispatch_adapter_plan_receipt_id: str
    runner_control_plan_receipt_id: str
    budget_provider_adapter_plan_receipt_id: str
    provider_executor_adapter_plan_receipt_id: str
    retrieval_adapter_plan_receipt_id: str
    graph_adapter_plan_receipt_id: str
    final_artifact_adapter_plan_receipt_id: str
    runner_readiness_receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    status: Literal["blocked_control_ledger_adapter_unimplemented"] = (
        "blocked_control_ledger_adapter_unimplemented"
    )
    adapter_key: Literal["operator_dispatch_control_ledger"] = (
        "operator_dispatch_control_ledger"
    )
    planned_setting_id: str
    planned_control_ledger_id: str
    planned_audit_log_id: str
    planned_rollback_receipt_id: str
    required_invariants: list[str]
    required_control_ledger_fields: list[str]
    required_rollback_receipt_fields: list[str]
    blocker_reason: Literal["control_ledger_adapter_unimplemented"] = (
        "control_ledger_adapter_unimplemented"
    )
    control_ledger_persistence_allowed: bool = False
    control_ledger_written: bool = False
    audit_log_written: bool = False
    rollback_receipt_created: bool = False
    operator_dispatch_allowed: bool = False
    operator_live_dispatch_enabled: bool = False
    live_run_allowed: bool = False
    dispatch_allowed: bool = False
    dispatch_performed: bool = False
    budget_reservation_allowed: bool = False
    budget_reserved: bool = False
    provider_execution_allowed: bool = False
    provider_calls_made: bool = False
    retrieval_allowed: bool = False
    retrieval_performed: bool = False
    source_receipts_created: bool = False
    graph_mutation_allowed: bool = False
    graph_mutated: bool = False
    final_artifact_allowed: bool = False
    final_artifact_created: bool = False
    adapter_plan_notes: list[str] = Field(default_factory=list)


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


def live_run_activation_settings_midnight_oil(
    req: MidnightOilLiveRunActivationSettingsRequest,
) -> MidnightOilLiveRunActivationSettingsReceipt:
    missing_controls = [
        "operator live-run activation setting persistence",
        "budget reservation provider",
        "model/provider route executor",
        "retrieval executor with source receipts",
        "graph mutation writer",
        "final HTML artifact writer",
    ]
    return MidnightOilLiveRunActivationSettingsReceipt(
        receipt_id=f"{req.launch_packet.run_id}-live-run-activation-settings",
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        requested_live_run_enabled=req.requested_live_run_enabled,
        requested_price_ceiling_usd=round(req.requested_price_ceiling_usd, 2),
        requested_work_minutes=req.requested_work_minutes,
        approved_price_ceiling_usd=req.approval_receipt.approved_price_ceiling_usd,
        approved_work_minutes=req.approval_receipt.approved_work_minutes,
        missing_controls=missing_controls,
        live_run_activation_allowed=False,
        dispatch_allowed=False,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        settings_notes=[
            "live-run activation settings gate only: live execution remains disabled",
            "operator intent is recorded without dispatch, budget reservation, provider call, retrieval, graph mutation, or artifact write",
            "future runner must replace this blocked receipt after every missing control is configured",
        ],
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
    completed_items = [
        "operator acknowledged spend ceiling for preflight",
        "launch packet exists",
        "approval receipt exists",
        "runner handoff exists",
        "applied run receipt exists",
        "blocked dispatch receipt exists",
    ]
    missing_items = [
        "operator live-run activation setting",
        "budget reservation provider",
        "model/provider route executor",
        "retrieval executor with source receipts",
        "graph mutation writer",
        "final HTML artifact writer",
    ]
    if req.live_run_activation_settings_receipt is not None:
        completed_items.append("blocked live-run activation settings receipt exists")
        missing_items.remove("operator live-run activation setting")

    return MidnightOilActivationChecklistReceipt(
        receipt_id=f"{req.launch_packet.run_id}-activation-checklist",
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        live_run_activation_settings_receipt_id=(
            req.live_run_activation_settings_receipt.receipt_id
            if req.live_run_activation_settings_receipt is not None
            else None
        ),
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        completed_items=completed_items,
        missing_items=missing_items,
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


def budget_reservation_midnight_oil(
    req: MidnightOilBudgetReservationRequest,
) -> MidnightOilBudgetReservationReceipt:
    return MidnightOilBudgetReservationReceipt(
        receipt_id=f"{req.launch_packet.run_id}-budget-reservation",
        activation_checklist_receipt_id=req.activation_checklist_receipt.receipt_id,
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        requested_reservation_usd=req.approval_receipt.planned_budget_usd,
        approved_price_ceiling_usd=req.approval_receipt.approved_price_ceiling_usd,
        planned_budget_usd=req.approval_receipt.planned_budget_usd,
        unallocated_budget_usd=req.approval_receipt.unallocated_budget_usd,
        budget_reservation_allowed=False,
        budget_reserved=False,
        provider_calls_made=False,
        dispatch_performed=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        reservation_notes=[
            "budget reservation gate only: reservation provider is not configured",
            "no budget reserved, provider call, dispatch, retrieval, graph mutation, or artifact write",
            "future live runner must replace this blocked receipt after settings-backed controls",
        ],
    )


def provider_route_midnight_oil(
    req: MidnightOilProviderRouteRequest,
) -> MidnightOilProviderRouteReceipt:
    return MidnightOilProviderRouteReceipt(
        receipt_id=f"{req.launch_packet.run_id}-provider-route",
        budget_reservation_receipt_id=req.budget_reservation_receipt.receipt_id,
        activation_checklist_receipt_id=req.activation_checklist_receipt.receipt_id,
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        requested_route_count=req.launch_packet.role_count,
        planned_role_route_receipt_ids=req.launch_packet.role_route_receipt_ids,
        route_executor_allowed=False,
        provider_execution_allowed=False,
        provider_calls_made=False,
        budget_reserved=False,
        dispatch_performed=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        provider_route_notes=[
            "provider route gate only: model/provider route executor is not configured",
            "no provider call, dispatch, retrieval, graph mutation, or artifact write",
            "future live runner must replace this blocked receipt after budget and provider controls",
        ],
    )


def retrieval_midnight_oil(req: MidnightOilRetrievalRequest) -> MidnightOilRetrievalReceipt:
    return MidnightOilRetrievalReceipt(
        receipt_id=f"{req.launch_packet.run_id}-retrieval",
        provider_route_receipt_id=req.provider_route_receipt.receipt_id,
        budget_reservation_receipt_id=req.budget_reservation_receipt.receipt_id,
        activation_checklist_receipt_id=req.activation_checklist_receipt.receipt_id,
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        planned_source_policy=req.launch_packet.source_policy,
        planned_source_receipt_ids=[
            f"{req.launch_packet.run_id}-{source}-source-receipt"
            for source in req.launch_packet.source_policy
        ],
        retrieval_allowed=False,
        source_receipts_created=False,
        retrieval_performed=False,
        provider_calls_made=False,
        budget_reserved=False,
        dispatch_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        retrieval_notes=[
            "retrieval gate only: retrieval executor and source receipt writer are not configured",
            "no source receipt created, retrieval performed, graph mutation, or artifact write",
            "future live runner must replace this blocked receipt after source connector controls",
        ],
    )


def graph_mutation_midnight_oil(
    req: MidnightOilGraphMutationRequest,
) -> MidnightOilGraphMutationReceipt:
    planned_graph_node_ids = [
        f"{req.launch_packet.run_id}-run-node",
        *[
            f"{req.launch_packet.run_id}-{source}-source-node"
            for source in req.launch_packet.source_policy
        ],
    ]
    planned_graph_edge_ids = [
        f"{req.launch_packet.run_id}-{source}-source-edge"
        for source in req.launch_packet.source_policy
    ]
    return MidnightOilGraphMutationReceipt(
        receipt_id=f"{req.launch_packet.run_id}-graph-mutation",
        retrieval_receipt_id=req.retrieval_receipt.receipt_id,
        provider_route_receipt_id=req.provider_route_receipt.receipt_id,
        budget_reservation_receipt_id=req.budget_reservation_receipt.receipt_id,
        activation_checklist_receipt_id=req.activation_checklist_receipt.receipt_id,
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        planned_graph_node_ids=planned_graph_node_ids,
        planned_graph_edge_ids=planned_graph_edge_ids,
        graph_mutation_allowed=False,
        graph_mutated=False,
        source_receipts_created=False,
        retrieval_performed=False,
        provider_calls_made=False,
        budget_reserved=False,
        dispatch_performed=False,
        final_artifact_created=False,
        graph_notes=[
            "graph mutation gate only: graph writer is not configured",
            "no graph node, graph edge, source receipt, retrieval, or artifact write",
            "future live runner must replace this blocked receipt after graph writer controls",
        ],
    )


def final_artifact_midnight_oil(
    req: MidnightOilFinalArtifactRequest,
) -> MidnightOilFinalArtifactReceipt:
    return MidnightOilFinalArtifactReceipt(
        receipt_id=f"{req.launch_packet.run_id}-final-artifact",
        graph_mutation_receipt_id=req.graph_mutation_receipt.receipt_id,
        retrieval_receipt_id=req.retrieval_receipt.receipt_id,
        provider_route_receipt_id=req.provider_route_receipt.receipt_id,
        budget_reservation_receipt_id=req.budget_reservation_receipt.receipt_id,
        activation_checklist_receipt_id=req.activation_checklist_receipt.receipt_id,
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        planned_artifact_id=f"{req.launch_packet.run_id}-html-research-asset",
        planned_twin_note_document_id=f"{req.launch_packet.run_id}-twin-note-document",
        final_format="html",
        pdf_allowed=False,
        final_artifact_allowed=False,
        final_artifact_created=False,
        graph_mutated=False,
        source_receipts_created=False,
        retrieval_performed=False,
        provider_calls_made=False,
        budget_reserved=False,
        dispatch_performed=False,
        artifact_notes=[
            "final artifact gate only: final HTML artifact writer is not configured",
            "no HTML asset, twin note document, graph write, source receipt, retrieval, or provider call",
            "future live runner must replace this blocked receipt after artifact writer controls",
        ],
    )


def runner_readiness_midnight_oil(
    req: MidnightOilRunnerReadinessRequest,
) -> MidnightOilRunnerReadinessReceipt:
    completed_receipt_ids = [
        req.launch_packet.packet_id,
        req.approval_receipt.receipt_id,
        req.runner_handoff.handoff_id,
        req.applied_run_receipt.receipt_id,
        req.live_run_activation_settings_receipt.receipt_id,
        req.dispatch_receipt.receipt_id,
        req.activation_checklist_receipt.receipt_id,
        req.budget_reservation_receipt.receipt_id,
        req.provider_route_receipt.receipt_id,
        req.retrieval_receipt.receipt_id,
        req.graph_mutation_receipt.receipt_id,
        req.final_artifact_receipt.receipt_id,
    ]
    remaining_blockers = [
        "budget reservation provider",
        "model/provider route executor",
        "retrieval executor with source receipts",
        "graph mutation writer",
        "final HTML artifact writer",
        "operator live-run dispatch enablement",
    ]
    return MidnightOilRunnerReadinessReceipt(
        receipt_id=f"{req.launch_packet.run_id}-runner-readiness",
        final_artifact_receipt_id=req.final_artifact_receipt.receipt_id,
        graph_mutation_receipt_id=req.graph_mutation_receipt.receipt_id,
        retrieval_receipt_id=req.retrieval_receipt.receipt_id,
        provider_route_receipt_id=req.provider_route_receipt.receipt_id,
        budget_reservation_receipt_id=req.budget_reservation_receipt.receipt_id,
        activation_checklist_receipt_id=req.activation_checklist_receipt.receipt_id,
        live_run_activation_settings_receipt_id=(
            req.live_run_activation_settings_receipt.receipt_id
        ),
        dispatch_receipt_id=req.dispatch_receipt.receipt_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        completed_receipt_ids=completed_receipt_ids,
        remaining_blockers=remaining_blockers,
        live_run_allowed=False,
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        provider_execution_allowed=False,
        retrieval_allowed=False,
        graph_mutation_allowed=False,
        final_artifact_allowed=False,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        readiness_notes=[
            "runner readiness gate only: full no-spend receipt chain has been reviewed",
            "live autonomous execution remains blocked until every remaining blocker is replaced by an enabled control",
            "no dispatch, budget reservation, provider call, retrieval, graph mutation, or artifact write is performed",
        ],
    )


def runner_control_plan_midnight_oil(
    req: MidnightOilRunnerControlPlanRequest,
) -> MidnightOilRunnerControlPlanReceipt:
    requirements = [
        MidnightOilRunnerControlRequirement(
            control_key=control_key,
            blocker=_RUNNER_CONTROL_BLOCKERS[control_key],
            required_artifact=_RUNNER_CONTROL_ARTIFACTS[control_key],
        )
        for control_key in req.requested_control_scope
    ]
    return MidnightOilRunnerControlPlanReceipt(
        receipt_id=f"{req.launch_packet.run_id}-runner-control-plan",
        runner_readiness_receipt_id=req.runner_readiness_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=req.launch_packet.run_id,
        requested_control_scope=req.requested_control_scope,
        required_control_order=list(_RUNNER_CONTROL_ORDER),
        implementation_requirements=requirements,
        remaining_blockers=req.runner_readiness_receipt.remaining_blockers,
        live_run_allowed=False,
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        provider_execution_allowed=False,
        retrieval_allowed=False,
        graph_mutation_allowed=False,
        final_artifact_allowed=False,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        control_plan_notes=[
            "runner control plan only: implementation requirements are recorded without enabling live execution",
            "every requested control remains missing until replaced by a concrete provider, executor, writer, or operator setting",
            "no dispatch, budget reservation, provider call, retrieval, graph mutation, or artifact write is performed",
        ],
    )


def budget_provider_adapter_plan_midnight_oil(
    req: MidnightOilBudgetProviderAdapterPlanRequest,
) -> MidnightOilBudgetProviderAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    return MidnightOilBudgetProviderAdapterPlanReceipt(
        receipt_id=f"{run_id}-budget-provider-adapter-plan",
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_adapter_id=f"{run_id}-budget-provider-adapter",
        planned_ledger_id=f"{run_id}-budget-reservation-ledger",
        idempotency_key=(
            f"{req.launch_packet.packet_id}:"
            f"{req.approval_receipt.receipt_id}:budget_reservation_provider"
        ),
        approved_price_ceiling_usd=req.approval_receipt.approved_price_ceiling_usd,
        planned_budget_usd=req.approval_receipt.planned_budget_usd,
        unallocated_budget_usd=req.approval_receipt.unallocated_budget_usd,
        required_invariants=[
            "adapter must reject reservations above the approved price ceiling",
            "adapter must be idempotent for the same launch packet and approval receipt",
            "adapter must write a durable ledger row before any provider execution can proceed",
            "adapter must expose an explicit release path for cancelled or failed live runs",
            "adapter must remain disabled until operator live-run controls and credentials are present",
        ],
        required_ledger_fields=[
            "reservation_id",
            "run_id",
            "launch_packet_id",
            "approval_receipt_id",
            "approved_price_ceiling_usd",
            "planned_budget_usd",
            "reserved_budget_usd",
            "idempotency_key",
            "status",
            "created_at",
            "released_at",
        ],
        budget_reservation_allowed=False,
        budget_reserved=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        provider_execution_allowed=False,
        retrieval_allowed=False,
        graph_mutation_allowed=False,
        final_artifact_allowed=False,
        dispatch_performed=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        adapter_plan_notes=[
            "budget provider adapter plan only: no reservation provider is configured or invoked",
            "this receipt documents invariants and ledger fields required before live budget holds",
            "no dispatch, budget reservation, provider call, retrieval, graph mutation, or artifact write is performed",
        ],
    )


def provider_executor_adapter_plan_midnight_oil(
    req: MidnightOilProviderExecutorAdapterPlanRequest,
) -> MidnightOilProviderExecutorAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    return MidnightOilProviderExecutorAdapterPlanReceipt(
        receipt_id=f"{run_id}-provider-executor-adapter-plan",
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        budget_provider_adapter_plan_receipt_id=(
            req.budget_provider_adapter_plan_receipt.receipt_id
        ),
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_executor_id=f"{run_id}-provider-executor-adapter",
        planned_route_ledger_id=f"{run_id}-provider-route-ledger",
        planned_role_route_receipt_ids=req.launch_packet.role_route_receipt_ids,
        requested_route_count=req.launch_packet.role_count,
        route_mode=req.launch_packet.route_mode,
        required_invariants=[
            "executor must require an active budget reservation before any provider call",
            "executor must create a route receipt for every planned role before execution",
            "executor must enforce the operator-approved route mode and source policy",
            "executor must record model, provider, estimated cost, and fallback rationale per role",
            "executor must remain disabled until provider credentials and operator live-run controls are present",
        ],
        required_route_receipt_fields=[
            "route_receipt_id",
            "run_id",
            "role",
            "route_mode",
            "provider",
            "model",
            "estimated_cost_usd",
            "budget_reservation_id",
            "fallback_chain",
            "created_at",
        ],
        provider_execution_allowed=False,
        provider_calls_made=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        budget_reserved=False,
        retrieval_allowed=False,
        graph_mutation_allowed=False,
        final_artifact_allowed=False,
        dispatch_performed=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        adapter_plan_notes=[
            "provider executor adapter plan only: no model/provider executor is configured or invoked",
            "this receipt documents route receipt invariants required before provider execution",
            "no dispatch, budget reservation, provider call, retrieval, graph mutation, or artifact write is performed",
        ],
    )


def retrieval_adapter_plan_midnight_oil(
    req: MidnightOilRetrievalAdapterPlanRequest,
) -> MidnightOilRetrievalAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    return MidnightOilRetrievalAdapterPlanReceipt(
        receipt_id=f"{run_id}-retrieval-adapter-plan",
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        budget_provider_adapter_plan_receipt_id=(
            req.budget_provider_adapter_plan_receipt.receipt_id
        ),
        provider_executor_adapter_plan_receipt_id=(
            req.provider_executor_adapter_plan_receipt.receipt_id
        ),
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_executor_id=f"{run_id}-retrieval-adapter",
        planned_source_ledger_id=f"{run_id}-source-receipt-ledger",
        planned_source_policy=req.launch_packet.source_policy,
        planned_source_receipt_ids=[
            f"{run_id}-{source}-source-receipt" for source in req.launch_packet.source_policy
        ],
        requested_source_count=len(req.launch_packet.source_policy),
        required_invariants=[
            "retrieval adapter must require provider route receipts before source access",
            "retrieval adapter must create a source receipt for every approved source policy entry",
            "retrieval adapter must preserve source URL, title, author, retrieval time, and license metadata",
            "retrieval adapter must mark unavailable sources without fabricating content",
            "retrieval adapter must remain disabled until source connectors and operator live-run controls are present",
        ],
        required_source_receipt_fields=[
            "source_receipt_id",
            "run_id",
            "source_policy",
            "source_uri",
            "title",
            "author",
            "retrieved_at",
            "license",
            "content_digest",
            "availability_status",
        ],
        retrieval_allowed=False,
        retrieval_performed=False,
        source_receipts_created=False,
        provider_execution_allowed=False,
        provider_calls_made=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        budget_reserved=False,
        graph_mutation_allowed=False,
        final_artifact_allowed=False,
        dispatch_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        adapter_plan_notes=[
            "retrieval adapter plan only: no source connector is configured or invoked",
            "this receipt documents source receipt invariants required before retrieval execution",
            "no dispatch, budget reservation, provider call, retrieval, graph mutation, or artifact write is performed",
        ],
    )


def graph_adapter_plan_midnight_oil(
    req: MidnightOilGraphAdapterPlanRequest,
) -> MidnightOilGraphAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    planned_graph_node_ids = [
        f"{run_id}-run-node",
        *[f"{run_id}-{source}-source-node" for source in req.launch_packet.source_policy],
    ]
    planned_graph_edge_ids = [
        f"{run_id}-{source}-cites-edge" for source in req.launch_packet.source_policy
    ]
    return MidnightOilGraphAdapterPlanReceipt(
        receipt_id=f"{run_id}-graph-adapter-plan",
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        budget_provider_adapter_plan_receipt_id=(
            req.budget_provider_adapter_plan_receipt.receipt_id
        ),
        provider_executor_adapter_plan_receipt_id=(
            req.provider_executor_adapter_plan_receipt.receipt_id
        ),
        retrieval_adapter_plan_receipt_id=req.retrieval_adapter_plan_receipt.receipt_id,
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_writer_id=f"{run_id}-graph-adapter",
        planned_graph_ledger_id=f"{run_id}-graph-mutation-ledger",
        planned_graph_node_ids=planned_graph_node_ids,
        planned_graph_edge_ids=planned_graph_edge_ids,
        required_invariants=[
            "graph adapter must require source receipts before any graph write",
            "graph adapter must write idempotent nodes and edges keyed by run and source receipt",
            "graph adapter must preserve provenance links to route and source receipts",
            "graph adapter must reject graph writes without an approved HTML asset contract",
            "graph adapter must remain disabled until graph storage credentials and live-run controls are present",
        ],
        required_graph_receipt_fields=[
            "graph_receipt_id",
            "run_id",
            "node_ids",
            "edge_ids",
            "source_receipt_ids",
            "route_receipt_ids",
            "content_digest",
            "idempotency_key",
            "created_at",
        ],
        graph_mutation_allowed=False,
        graph_mutated=False,
        source_receipts_created=False,
        retrieval_allowed=False,
        retrieval_performed=False,
        provider_execution_allowed=False,
        provider_calls_made=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        budget_reserved=False,
        final_artifact_allowed=False,
        dispatch_performed=False,
        final_artifact_created=False,
        adapter_plan_notes=[
            "graph adapter plan only: no graph writer is configured or invoked",
            "this receipt documents graph mutation invariants required before graph writes",
            "no dispatch, budget reservation, provider call, retrieval, source receipt, graph mutation, or artifact write is performed",
        ],
    )


def final_artifact_adapter_plan_midnight_oil(
    req: MidnightOilFinalArtifactAdapterPlanRequest,
) -> MidnightOilFinalArtifactAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    return MidnightOilFinalArtifactAdapterPlanReceipt(
        receipt_id=f"{run_id}-final-artifact-adapter-plan",
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        budget_provider_adapter_plan_receipt_id=(
            req.budget_provider_adapter_plan_receipt.receipt_id
        ),
        provider_executor_adapter_plan_receipt_id=(
            req.provider_executor_adapter_plan_receipt.receipt_id
        ),
        retrieval_adapter_plan_receipt_id=req.retrieval_adapter_plan_receipt.receipt_id,
        graph_adapter_plan_receipt_id=req.graph_adapter_plan_receipt.receipt_id,
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_writer_id=f"{run_id}-final-html-artifact-writer",
        planned_artifact_ledger_id=f"{run_id}-artifact-receipt-ledger",
        planned_artifact_id=f"{run_id}-html-research-asset",
        planned_twin_note_document_id=f"{run_id}-twin-note-document",
        final_format="html",
        pdf_allowed=False,
        required_invariants=[
            "final artifact adapter must require route, source, and graph receipts before writing HTML",
            "final artifact adapter must create an Antiek information asset and twin-note document atomically",
            "final artifact adapter must preserve provenance links to launch, approval, route, source, and graph receipts",
            "final artifact adapter must reject PDF output and non-HTML final formats",
            "final artifact adapter must remain disabled until artifact storage credentials and live-run controls are present",
        ],
        required_artifact_receipt_fields=[
            "artifact_receipt_id",
            "run_id",
            "artifact_id",
            "twin_note_document_id",
            "final_format",
            "route_receipt_ids",
            "source_receipt_ids",
            "graph_receipt_id",
            "content_digest",
            "created_at",
        ],
        final_artifact_allowed=False,
        final_artifact_created=False,
        graph_mutation_allowed=False,
        graph_mutated=False,
        source_receipts_created=False,
        retrieval_allowed=False,
        retrieval_performed=False,
        provider_execution_allowed=False,
        provider_calls_made=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        budget_reservation_allowed=False,
        budget_reserved=False,
        dispatch_performed=False,
        adapter_plan_notes=[
            "final artifact adapter plan only: no HTML asset writer is configured or invoked",
            "this receipt documents final HTML artifact and twin-note receipt invariants required before artifact writes",
            "no dispatch, budget reservation, provider call, retrieval, source receipt, graph mutation, or artifact write is performed",
        ],
    )


def operator_dispatch_adapter_plan_midnight_oil(
    req: MidnightOilOperatorDispatchAdapterPlanRequest,
) -> MidnightOilOperatorDispatchAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    return MidnightOilOperatorDispatchAdapterPlanReceipt(
        receipt_id=f"{run_id}-operator-dispatch-adapter-plan",
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        budget_provider_adapter_plan_receipt_id=(
            req.budget_provider_adapter_plan_receipt.receipt_id
        ),
        provider_executor_adapter_plan_receipt_id=(
            req.provider_executor_adapter_plan_receipt.receipt_id
        ),
        retrieval_adapter_plan_receipt_id=req.retrieval_adapter_plan_receipt.receipt_id,
        graph_adapter_plan_receipt_id=req.graph_adapter_plan_receipt.receipt_id,
        final_artifact_adapter_plan_receipt_id=(
            req.final_artifact_adapter_plan_receipt.receipt_id
        ),
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_setting_id=f"{run_id}-operator-live-dispatch-setting",
        planned_control_ledger_id=f"{run_id}-operator-dispatch-control-ledger",
        required_invariants=[
            "operator dispatch adapter must require every implementation adapter plan before live enablement",
            "operator dispatch adapter must require an explicit operator toggle for the approved run id",
            "operator dispatch adapter must enforce the approved price ceiling and work-minute ceiling before dispatch",
            "operator dispatch adapter must write a durable control ledger row before live dispatch can proceed",
            "operator dispatch adapter must remain disabled until persistence, audit, and rollback controls are present",
        ],
        required_dispatch_enablement_fields=[
            "operator_dispatch_setting_id",
            "run_id",
            "approval_receipt_id",
            "approved_price_ceiling_usd",
            "approved_work_minutes",
            "enabled_by_operator_id",
            "enabled_at",
            "expires_at",
            "idempotency_key",
            "rollback_receipt_id",
        ],
        operator_dispatch_allowed=False,
        operator_live_dispatch_enabled=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        dispatch_performed=False,
        budget_reservation_allowed=False,
        budget_reserved=False,
        provider_execution_allowed=False,
        provider_calls_made=False,
        retrieval_allowed=False,
        retrieval_performed=False,
        source_receipts_created=False,
        graph_mutation_allowed=False,
        graph_mutated=False,
        final_artifact_allowed=False,
        final_artifact_created=False,
        adapter_plan_notes=[
            "operator dispatch adapter plan only: no live dispatch setting is persisted or enabled",
            "this receipt documents operator live-dispatch controls required before autonomous execution can be enabled",
            "no dispatch, budget reservation, provider call, retrieval, source receipt, graph mutation, or artifact write is performed",
        ],
    )


def control_ledger_adapter_plan_midnight_oil(
    req: MidnightOilControlLedgerAdapterPlanRequest,
) -> MidnightOilControlLedgerAdapterPlanReceipt:
    run_id = req.launch_packet.run_id
    return MidnightOilControlLedgerAdapterPlanReceipt(
        receipt_id=f"{run_id}-control-ledger-adapter-plan",
        operator_dispatch_adapter_plan_receipt_id=(
            req.operator_dispatch_adapter_plan_receipt.receipt_id
        ),
        runner_control_plan_receipt_id=req.runner_control_plan_receipt.receipt_id,
        budget_provider_adapter_plan_receipt_id=(
            req.budget_provider_adapter_plan_receipt.receipt_id
        ),
        provider_executor_adapter_plan_receipt_id=(
            req.provider_executor_adapter_plan_receipt.receipt_id
        ),
        retrieval_adapter_plan_receipt_id=req.retrieval_adapter_plan_receipt.receipt_id,
        graph_adapter_plan_receipt_id=req.graph_adapter_plan_receipt.receipt_id,
        final_artifact_adapter_plan_receipt_id=(
            req.final_artifact_adapter_plan_receipt.receipt_id
        ),
        runner_readiness_receipt_id=(
            req.runner_control_plan_receipt.runner_readiness_receipt_id
        ),
        runner_handoff_id=req.runner_handoff.handoff_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        launch_packet_id=req.launch_packet.packet_id,
        run_id=run_id,
        planned_setting_id=req.operator_dispatch_adapter_plan_receipt.planned_setting_id,
        planned_control_ledger_id=(
            req.operator_dispatch_adapter_plan_receipt.planned_control_ledger_id
        ),
        planned_audit_log_id=f"{run_id}-operator-dispatch-audit-log",
        planned_rollback_receipt_id=f"{run_id}-operator-dispatch-rollback-receipt",
        required_invariants=[
            "control ledger adapter must persist exactly one enablement row per approved run id and idempotency key",
            "control ledger adapter must bind the row to the launch packet, approval receipt, and operator setting",
            "control ledger adapter must record approval ceiling, work-minute ceiling, enabled_by, enabled_at, and expiry before dispatch",
            "control ledger adapter must write an audit log row and rollback receipt before live dispatch can be enabled",
            "control ledger adapter must remain disabled until durable persistence, audit, and rollback storage are configured",
        ],
        required_control_ledger_fields=[
            "control_ledger_id",
            "operator_dispatch_setting_id",
            "run_id",
            "launch_packet_id",
            "approval_receipt_id",
            "approved_price_ceiling_usd",
            "approved_work_minutes",
            "enabled_by_operator_id",
            "enabled_at",
            "expires_at",
            "idempotency_key",
            "audit_log_id",
            "rollback_receipt_id",
            "created_at",
        ],
        required_rollback_receipt_fields=[
            "rollback_receipt_id",
            "control_ledger_id",
            "operator_dispatch_setting_id",
            "run_id",
            "previous_enabled_state",
            "rollback_reason",
            "rolled_back_by_operator_id",
            "rolled_back_at",
        ],
        control_ledger_persistence_allowed=False,
        control_ledger_written=False,
        audit_log_written=False,
        rollback_receipt_created=False,
        operator_dispatch_allowed=False,
        operator_live_dispatch_enabled=False,
        live_run_allowed=False,
        dispatch_allowed=False,
        dispatch_performed=False,
        budget_reservation_allowed=False,
        budget_reserved=False,
        provider_execution_allowed=False,
        provider_calls_made=False,
        retrieval_allowed=False,
        retrieval_performed=False,
        source_receipts_created=False,
        graph_mutation_allowed=False,
        graph_mutated=False,
        final_artifact_allowed=False,
        final_artifact_created=False,
        adapter_plan_notes=[
            "control ledger adapter plan only: no operator setting or ledger row is persisted",
            "this receipt documents durable enablement, audit, idempotency, and rollback requirements before live dispatch can be enabled",
            "no dispatch, budget reservation, provider call, retrieval, source receipt, graph mutation, or artifact write is performed",
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
