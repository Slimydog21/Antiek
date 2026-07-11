"""The single Midnight Oil runner and its permanent synthetic oracle.

``execute_midnight_oil`` defaults to a deterministic, free, networkless
synthetic execution.  SPR-05 adds authorized budget decrement and SPR-06 is
the only operator-gated seam allowed to make ``live`` execution reachable.
"""

from __future__ import annotations

import hashlib
from html import escape
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from substrate.schemas import (
    RouteReceipt,
    RouteReceiptBudget,
    RouteReceiptCandidate,
    RouteReceiptSelection,
)

from .contracts import (
    MidnightOilAppliedRunReceipt,
    MidnightOilApprovalReceipt,
    MidnightOilLaunchPacket,
    MidnightOilRole,
    MidnightOilRolePlan,
    MidnightOilRunnerHandoff,
)
from .seams import MidnightOilSeams

_ROLES: tuple[MidnightOilRole, ...] = ("planner", "gatherer", "verifier", "synthesizer")


class MidnightOilExecutionRequest(BaseModel):
    launch_packet: MidnightOilLaunchPacket
    approval_receipt: MidnightOilApprovalReceipt
    runner_handoff: MidnightOilRunnerHandoff
    applied_run_receipt: MidnightOilAppliedRunReceipt
    role_plans: list[MidnightOilRolePlan] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _approved_lineage_is_complete(self) -> MidnightOilExecutionRequest:
        packet = self.launch_packet
        approval = self.approval_receipt
        handoff = self.runner_handoff
        applied = self.applied_run_receipt
        if approval.launch_packet_id != packet.packet_id or approval.run_id != packet.run_id:
            raise ValueError("approval_receipt must reference launch_packet")
        if handoff.launch_packet_id != packet.packet_id or handoff.run_id != packet.run_id:
            raise ValueError("runner_handoff must reference launch_packet")
        if handoff.approval_receipt_id != approval.receipt_id:
            raise ValueError("runner_handoff must reference approval_receipt")
        if applied.launch_packet_id != packet.packet_id or applied.run_id != packet.run_id:
            raise ValueError("applied_run_receipt must reference launch_packet")
        if applied.approval_receipt_id != approval.receipt_id:
            raise ValueError("applied_run_receipt must reference approval_receipt")
        if applied.runner_handoff_id != handoff.handoff_id:
            raise ValueError("applied_run_receipt must reference runner_handoff")
        if not approval.operator_acknowledged_spend:
            raise ValueError("approval_receipt must acknowledge spend")
        if (
            approval.approved_price_ceiling_usd != packet.price_ceiling_usd
            or approval.approved_work_minutes != packet.work_minutes
            or approval.approved_route_mode != packet.route_mode
            or approval.approved_source_policy != packet.source_policy
            or approval.approved_deliverable != packet.deliverable
            or approval.planned_budget_usd != packet.planned_budget_usd
            or approval.unallocated_budget_usd != packet.unallocated_budget_usd
        ):
            raise ValueError("approval_receipt must preserve launch_packet controls")
        if (
            handoff.approved_price_ceiling_usd != approval.approved_price_ceiling_usd
            or handoff.planned_budget_usd != approval.planned_budget_usd
            or handoff.unallocated_budget_usd != approval.unallocated_budget_usd
            or handoff.role_route_receipt_ids != packet.role_route_receipt_ids
            or handoff.prerequisite_receipt_ids != [packet.packet_id, approval.receipt_id]
            or not handoff.dispatch_ready
        ):
            raise ValueError("runner_handoff must preserve approved controls")
        if (
            applied.status != "planned_not_dispatched"
            or applied.planned_role_count != packet.role_count
            or applied.planned_budget_usd != approval.planned_budget_usd
            or applied.unallocated_budget_usd != approval.unallocated_budget_usd
        ):
            raise ValueError("applied_run_receipt must preserve approved plan")
        if packet.role_count != len(_ROLES):
            raise ValueError("launch_packet must plan four mock swarm roles")
        if tuple(plan.role for plan in self.role_plans) != _ROLES:
            raise ValueError(
                "role_plans must contain planner, gatherer, verifier, synthesizer in order"
            )
        route_ids = [plan.planned_route_receipt_id for plan in self.role_plans]
        if route_ids != packet.role_route_receipt_ids:
            raise ValueError("role_plans must match launch_packet route receipts")
        if route_ids != applied.planned_role_route_receipt_ids:
            raise ValueError("role_plans must match applied_run_receipt route receipts")
        if any(
            plan.route_mode != packet.route_mode
            or not plan.route_receipt_required
            or not plan.source_receipts_required
            for plan in self.role_plans
        ):
            raise ValueError("role_plans must preserve route and receipt controls")
        if round(sum(plan.budget_usd for plan in self.role_plans), 2) != packet.planned_budget_usd:
            raise ValueError("role plan budget must match launch_packet planned budget")
        if sum(plan.max_minutes for plan in self.role_plans) != packet.work_minutes:
            raise ValueError("role plan minutes must match launch_packet work minutes")
        if any(
            (
                packet.dispatch_allowed,
                packet.budget_reserved,
                packet.provider_calls_made,
                approval.dispatch_allowed,
                approval.budget_reserved,
                approval.provider_calls_made,
                handoff.dispatch_performed,
                handoff.budget_reserved,
                handoff.provider_calls_made,
                handoff.graph_mutated,
                applied.dispatch_performed,
                applied.budget_reserved,
                applied.provider_calls_made,
                applied.retrieval_performed,
                applied.graph_mutated,
                applied.final_artifact_created,
            )
        ):
            raise ValueError("mock execution requires a no-side-effect preflight lineage")
        return self


class MidnightOilRoleOutput(BaseModel):
    role: MidnightOilRole
    status: Literal["synthetic_complete"] = "synthetic_complete"
    execution_mode: Literal["synthetic_no_provider"] = "synthetic_no_provider"
    route_receipt: RouteReceipt
    source_receipt_ids: list[str] = Field(default_factory=list)
    output_summary: str


class MidnightOilExecutionReceipt(BaseModel):
    receipt_id: str
    run_id: str
    launch_packet_id: str
    approval_receipt_id: str
    runner_handoff_id: str
    applied_run_receipt_id: str
    status: Literal["mock_completed"] = "mock_completed"
    synthetic: Literal[True] = True
    goal_fingerprint: str
    role_outputs: list[MidnightOilRoleOutput]
    html_information_asset: str
    twin_note_html: str
    actual_cost_usd: float = Field(default=0.0, ge=0.0)
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    execution_mode: Literal["synthetic", "live"] = "synthetic"
    persisted: bool = False
    notes: list[str]

    @model_validator(mode="after")
    def _synthetic_execution_cannot_claim_effects(self) -> MidnightOilExecutionReceipt:
        if self.execution_mode == "synthetic" and (
            self.actual_cost_usd != 0.0
            or any(
                (
                    self.dispatch_performed,
                    self.budget_reserved,
                    self.provider_calls_made,
                    self.retrieval_performed,
                    self.graph_mutated,
                    self.final_artifact_created,
                    self.persisted,
                )
            )
        ):
            raise ValueError("synthetic execution cannot claim side effects or persistence")
        return self


def execute_midnight_oil(
    req: MidnightOilExecutionRequest,
    seams: MidnightOilSeams | None = None,
) -> MidnightOilExecutionReceipt:
    # Construct the inert bundle so this function has one stable DI seam for
    # SPR-06. Synthetic mode deliberately never invokes an adapter.
    if seams is None:
        seams = MidnightOilSeams()
    run_id = req.launch_packet.run_id
    role_outputs = [
        MidnightOilRoleOutput(
            role=plan.role,
            route_receipt=_mock_route_receipt(plan=plan),
            output_summary=f"Synthetic {plan.role} stage completed without external execution.",
        )
        for plan in req.role_plans
    ]
    goal_fingerprint = hashlib.sha256(req.launch_packet.goal.encode()).hexdigest()
    route_links = "".join(
        f"<li><code>{escape(output.route_receipt.route_receipt_id)}</code> - {output.role}</li>"
        for output in role_outputs
    )
    information_asset = (
        '<article data-antiek-asset="information" data-execution="synthetic">'
        "<header><h1>Midnight Oil execution preview</h1>"
        '<p role="status">Synthetic preview. No research or provider calls were performed.</p></header>'
        f"<section><h2>Research goal fingerprint</h2><code>{goal_fingerprint}</code></section>"
        f"<section><h2>Route receipts</h2><ul>{route_links}</ul></section>"
        "<section><h2>Result</h2><p>This preview validates the approved swarm, routing, HTML, and twin-note contracts only.</p></section>"
        "</article>"
    )
    twin_note = (
        '<aside data-antiek-asset="twin-note" data-execution="synthetic">'
        "<h1>Midnight Oil twin note preview</h1>"
        f"<p>Goal fingerprint: <code>{goal_fingerprint}</code></p>"
        "<h2>Questions for live research</h2><ul>"
        "<li>Which claims require primary-source evidence?</li>"
        "<li>Which competing explanations should the verifier test?</li>"
        "</ul><p>No insights are asserted because retrieval did not run.</p></aside>"
    )
    return MidnightOilExecutionReceipt(
        receipt_id=f"{run_id}-mock-execution",
        run_id=run_id,
        launch_packet_id=req.launch_packet.packet_id,
        approval_receipt_id=req.approval_receipt.receipt_id,
        runner_handoff_id=req.runner_handoff.handoff_id,
        applied_run_receipt_id=req.applied_run_receipt.receipt_id,
        goal_fingerprint=goal_fingerprint,
        role_outputs=role_outputs,
        html_information_asset=information_asset,
        twin_note_html=twin_note,
        notes=[
            "deterministic mock execution only",
            "route receipts use the canonical dispatch schema but identify a non-provider mock route",
            "HTML is returned in-memory and is not persisted, published, or written to the graph",
        ],
    )


def _mock_route_receipt(*, plan: MidnightOilRolePlan) -> RouteReceipt:
    candidate = RouteReceiptCandidate(
        provider="none",
        model="no-provider",
        tier="synthetic",
        fallback_chain_index=0,
        pricing_known=True,
        estimated_cost_usd_low=0.0,
        estimated_cost_usd_high=0.0,
    )
    return RouteReceipt(
        route_receipt_id=plan.planned_route_receipt_id,
        task_kind=f"midnight_oil_{plan.role}",
        objective="balanced",
        candidate_models=(candidate,),
        selected=RouteReceiptSelection(
            provider=candidate.provider,
            model=candidate.model,
            tier=candidate.tier,
            fallback_chain_index=0,
            reason_code="synthetic_no_provider",
            pricing_known=True,
        ),
        budget=RouteReceiptBudget(
            cap_usd=plan.budget_usd,
            remaining_before_usd=plan.budget_usd,
            projected_cost_usd_low=0.0,
            projected_cost_usd_high=0.0,
            actual_cost_usd=0.0,
            would_exceed_budget=False,
        ),
    )
