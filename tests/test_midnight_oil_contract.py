"""Midnight-oil routing preflight contract tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from substrate.midnight_oil import (
    MidnightOilActivationChecklistRequest,
    MidnightOilBudgetReservationRequest,
    MidnightOilDispatchRequest,
    MidnightOilDryRunRequest,
    MidnightOilGraphMutationRequest,
    MidnightOilProviderRouteRequest,
    MidnightOilRequest,
    MidnightOilRetrievalRequest,
    activation_checklist_midnight_oil,
    budget_reservation_midnight_oil,
    dispatch_midnight_oil,
    dry_run_midnight_oil,
    graph_mutation_midnight_oil,
    preflight_midnight_oil,
    provider_route_midnight_oil,
    retrieval_midnight_oil,
)


def _accepted_midnight_oil_gate_chain(
    *,
    goal: str,
    source_policy: list[str],
) -> dict[str, object]:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal=goal,
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=source_policy,
            operator_acknowledged_spend=True,
        )
    )
    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch,
            activation_checklist_receipt=checklist,
        )
    )
    provider_route = provider_route_midnight_oil(
        MidnightOilProviderRouteRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
        )
    )
    retrieval = retrieval_midnight_oil(
        MidnightOilRetrievalRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
            provider_route_receipt=provider_route,
        )
    )
    return {
        "preflight": preflight,
        "dispatch": dispatch,
        "checklist": checklist,
        "reservation": reservation,
        "provider_route": provider_route,
        "retrieval": retrieval,
    }


def test_no_ack_request_is_denied_before_dispatch() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Explain widebody engine supply-chain bottlenecks.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            source_policy=["arxiv", "web", "operator_corpus"],
            operator_acknowledged_spend=False,
        )
    )

    assert result.accepted is False
    assert result.denial_reason == "operator_acknowledged_spend_required"
    assert result.run_id is None
    assert result.role_plans == []
    assert result.planned_budget_usd == 0.0
    assert result.unallocated_budget_usd == 25.0
    assert result.launch_packet is None
    assert result.approval_receipt is None
    assert result.runner_handoff is None
    assert result.applied_run_receipt is None
    assert "denied before dispatch" in result.notes[0]


def test_budget_allocation_sums_never_exceed_parent_ceiling() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Map the aircraft leasing market after interest-rate shocks.",
            work_minutes=90,
            price_ceiling_usd=10.03,
            route_mode="auto_cost",
            source_policy=["substack", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.accepted is True
    assert result.planned_budget_usd <= result.price_ceiling_usd
    assert result.unallocated_budget_usd == round(result.price_ceiling_usd - result.planned_budget_usd, 2)
    assert {plan.role for plan in result.role_plans} == {
        "planner",
        "gatherer",
        "verifier",
        "synthesizer",
    }
    assert sum(plan.max_minutes for plan in result.role_plans) == 90
    assert all(plan.route_mode == "auto_cost" for plan in result.role_plans)


def test_rounding_buffer_is_reported_as_unallocated_budget() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Map avionics certification bottlenecks.",
            work_minutes=90,
            price_ceiling_usd=10.039,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.price_ceiling_usd == 10.04
    assert result.planned_budget_usd == 10.03
    assert result.unallocated_budget_usd == 0.01


def test_mock_role_plan_requires_route_and_source_receipts() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Research whether composite aircraft repair is capacity constrained.",
            work_minutes=45,
            price_ceiling_usd=3.25,
            source_policy=["arxiv"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.accepted is True
    assert len(result.role_plans) == 4
    assert all(plan.route_receipt_required for plan in result.role_plans)
    assert all(plan.source_receipts_required for plan in result.role_plans)
    assert all(plan.planned_route_receipt_id.startswith(result.run_id or "") for plan in result.role_plans)


def test_accepted_preflight_emits_no_dispatch_launch_packet() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Research whether composite aircraft repair is capacity constrained.",
            work_minutes=45,
            price_ceiling_usd=3.25,
            route_mode="auto_latency",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.accepted is True
    assert result.launch_packet is not None
    packet = result.launch_packet
    assert packet.packet_id == f"{result.run_id}-launch-packet"
    assert packet.run_id == result.run_id
    assert packet.goal == result.goal
    assert packet.work_minutes == result.work_minutes
    assert packet.price_ceiling_usd == result.price_ceiling_usd
    assert packet.planned_budget_usd == result.planned_budget_usd
    assert packet.unallocated_budget_usd == result.unallocated_budget_usd
    assert packet.route_mode == "auto_latency"
    assert packet.source_policy == ["arxiv", "operator_corpus"]
    assert packet.deliverable == "html_research_asset"
    assert packet.artifact_contract.final_format == "html"
    assert packet.artifact_contract.pdf_allowed is False
    assert packet.role_count == len(result.role_plans)
    assert packet.role_route_receipt_ids == [
        plan.planned_route_receipt_id for plan in result.role_plans
    ]
    assert packet.source_receipts_required is True
    assert packet.route_receipts_required is True
    assert packet.dispatch_allowed is False
    assert packet.budget_reserved is False
    assert packet.provider_calls_made is False
    assert "no agents dispatched" in packet.launch_notes[0]


def test_accepted_preflight_emits_operator_approval_receipt_bound_to_launch_packet() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Compare aircraft engine maintenance capacity constraints.",
            work_minutes=75,
            price_ceiling_usd=8.5,
            route_mode="auto_quality",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.launch_packet is not None
    assert result.approval_receipt is not None
    receipt = result.approval_receipt
    packet = result.launch_packet
    assert receipt.receipt_id == f"{result.run_id}-approval-receipt"
    assert receipt.launch_packet_id == packet.packet_id
    assert receipt.run_id == result.run_id
    assert receipt.operator_acknowledged_spend is True
    assert receipt.approved_price_ceiling_usd == result.price_ceiling_usd
    assert receipt.approved_work_minutes == result.work_minutes
    assert receipt.approved_route_mode == result.route_mode
    assert receipt.approved_source_policy == result.source_policy
    assert receipt.approved_deliverable == "html_research_asset"
    assert receipt.planned_budget_usd == result.planned_budget_usd
    assert receipt.unallocated_budget_usd == result.unallocated_budget_usd
    assert receipt.approval_scope == "preflight_launch_packet_only"
    assert receipt.runner_apply_required is True
    assert receipt.dispatch_allowed is False
    assert receipt.budget_reserved is False
    assert receipt.provider_calls_made is False
    assert "runner apply is still required" in receipt.receipt_notes[1]


def test_accepted_preflight_emits_runner_apply_handoff_without_side_effects() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Plan a midnight oil research run about airline fleet renewal.",
            work_minutes=180,
            price_ceiling_usd=40.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "substack", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.launch_packet is not None
    assert result.approval_receipt is not None
    assert result.runner_handoff is not None
    handoff = result.runner_handoff
    packet = result.launch_packet
    receipt = result.approval_receipt
    assert handoff.handoff_id == f"{result.run_id}-runner-handoff"
    assert handoff.approval_receipt_id == receipt.receipt_id
    assert handoff.launch_packet_id == packet.packet_id
    assert handoff.run_id == result.run_id
    assert handoff.status == "ready_for_runner_apply"
    assert handoff.approved_price_ceiling_usd == receipt.approved_price_ceiling_usd
    assert handoff.planned_budget_usd == receipt.planned_budget_usd
    assert handoff.unallocated_budget_usd == receipt.unallocated_budget_usd
    assert handoff.role_route_receipt_ids == packet.role_route_receipt_ids
    assert handoff.prerequisite_receipt_ids == [packet.packet_id, receipt.receipt_id]
    assert handoff.dispatch_ready is True
    assert handoff.dispatch_performed is False
    assert handoff.budget_reserved is False
    assert handoff.provider_calls_made is False
    assert handoff.graph_mutated is False
    assert "ready for a future dispatcher" in handoff.handoff_notes[0]


def test_accepted_preflight_emits_dry_applied_run_receipt_without_side_effects() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare a midnight oil run about regional jet supply chains.",
            work_minutes=240,
            price_ceiling_usd=64.0,
            route_mode="auto_quality",
            source_policy=["arxiv", "substack", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.launch_packet is not None
    assert result.approval_receipt is not None
    assert result.runner_handoff is not None
    assert result.applied_run_receipt is not None
    applied = result.applied_run_receipt
    assert applied.receipt_id == f"{result.run_id}-applied-run-receipt"
    assert applied.runner_handoff_id == result.runner_handoff.handoff_id
    assert applied.approval_receipt_id == result.approval_receipt.receipt_id
    assert applied.launch_packet_id == result.launch_packet.packet_id
    assert applied.run_id == result.run_id
    assert applied.status == "planned_not_dispatched"
    assert applied.planned_role_count == len(result.role_plans)
    assert applied.planned_budget_usd == result.planned_budget_usd
    assert applied.unallocated_budget_usd == result.unallocated_budget_usd
    assert applied.planned_role_route_receipt_ids == result.runner_handoff.role_route_receipt_ids
    assert applied.dispatch_performed is False
    assert applied.budget_reserved is False
    assert applied.provider_calls_made is False
    assert applied.retrieval_performed is False
    assert applied.graph_mutated is False
    assert applied.final_artifact_created is False
    assert "no autonomous agents dispatched" in applied.applied_notes[0]


def test_dry_run_endpoint_contract_consumes_matching_receipt_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Dry-run a midnight oil plan about turbofan maintenance backlogs.",
            work_minutes=90,
            price_ceiling_usd=14.0,
            route_mode="auto_cost",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    dry_run = dry_run_midnight_oil(
        MidnightOilDryRunRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
        )
    )

    assert dry_run.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert dry_run.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert dry_run.launch_packet_id == preflight.launch_packet.packet_id
    assert dry_run.status == "planned_not_dispatched"
    assert dry_run.dispatch_performed is False
    assert dry_run.budget_reserved is False
    assert dry_run.provider_calls_made is False
    assert dry_run.retrieval_performed is False
    assert dry_run.graph_mutated is False
    assert dry_run.final_artifact_created is False


def test_dry_run_rejects_mismatched_receipt_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Dry-run a midnight oil plan about airport slot constraints.",
            work_minutes=90,
            price_ceiling_usd=14.0,
            route_mode="auto_cost",
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    bad_handoff = preflight.runner_handoff.model_copy(update={"launch_packet_id": "wrong-packet"})

    with pytest.raises(ValidationError, match="runner_handoff must reference launch_packet"):
        MidnightOilDryRunRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=bad_handoff,
        )


def test_dispatch_gate_returns_blocked_receipt_without_side_effects() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare a live-dispatch gate for a midnight oil run about turbofan durability.",
            work_minutes=150,
            price_ceiling_usd=22.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )

    assert receipt.receipt_id == f"{preflight.run_id}-dispatch-receipt"
    assert receipt.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert receipt.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert receipt.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert receipt.launch_packet_id == preflight.launch_packet.packet_id
    assert receipt.run_id == preflight.run_id
    assert receipt.status == "blocked_live_dispatch_disabled"
    assert receipt.live_dispatch_requested is True
    assert receipt.blocker_reason == "live_dispatch_disabled"
    assert receipt.dispatch_allowed is False
    assert receipt.dispatch_performed is False
    assert receipt.budget_reserved is False
    assert receipt.provider_calls_made is False
    assert receipt.retrieval_performed is False
    assert receipt.graph_mutated is False
    assert receipt.final_artifact_created is False
    assert "autonomous runner execution is disabled" in receipt.dispatch_notes[0]


def test_dispatch_gate_rejects_mismatched_applied_receipt_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare a live-dispatch gate for a midnight oil run about airline financing.",
            work_minutes=120,
            price_ceiling_usd=18.0,
            route_mode="auto_cost",
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    bad_applied = preflight.applied_run_receipt.model_copy(
        update={"runner_handoff_id": "wrong-handoff"}
    )

    with pytest.raises(ValidationError, match="applied_run_receipt must reference runner_handoff"):
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=bad_applied,
        )


def test_activation_checklist_reports_missing_live_controls_without_side_effects() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare an activation checklist for a midnight oil run about turbofan durability.",
            work_minutes=150,
            price_ceiling_usd=22.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )

    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )

    assert checklist.receipt_id == f"{preflight.run_id}-activation-checklist"
    assert checklist.dispatch_receipt_id == dispatch_receipt.receipt_id
    assert checklist.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert checklist.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert checklist.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert checklist.launch_packet_id == preflight.launch_packet.packet_id
    assert checklist.run_id == preflight.run_id
    assert checklist.status == "activation_blocked_controls_missing"
    assert "blocked dispatch receipt exists" in checklist.completed_items
    assert "budget reservation provider" in checklist.missing_items
    assert "model/provider route executor" in checklist.missing_items
    assert checklist.dispatch_allowed is False
    assert checklist.budget_reservation_allowed is False
    assert checklist.provider_execution_allowed is False
    assert checklist.retrieval_allowed is False
    assert checklist.graph_mutation_allowed is False
    assert checklist.final_artifact_allowed is False
    assert "live execution remains blocked" in checklist.checklist_notes[0]


def test_activation_checklist_rejects_mismatched_dispatch_receipt_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare an activation checklist for a midnight oil run about airline financing.",
            work_minutes=120,
            price_ceiling_usd=18.0,
            route_mode="auto_cost",
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    bad_dispatch = dispatch_receipt.model_copy(update={"applied_run_receipt_id": "wrong-applied"})

    with pytest.raises(ValidationError, match="dispatch_receipt must reference applied_run_receipt"):
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=bad_dispatch,
        )


def test_budget_reservation_gate_blocks_reservation_without_side_effects() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare budget reservation for a midnight oil run about turbofan durability.",
            work_minutes=150,
            price_ceiling_usd=22.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )

    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )

    assert reservation.receipt_id == f"{preflight.run_id}-budget-reservation"
    assert reservation.activation_checklist_receipt_id == checklist.receipt_id
    assert reservation.dispatch_receipt_id == dispatch_receipt.receipt_id
    assert reservation.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert reservation.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert reservation.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert reservation.launch_packet_id == preflight.launch_packet.packet_id
    assert reservation.run_id == preflight.run_id
    assert reservation.status == "blocked_budget_reservation_disabled"
    assert reservation.requested_reservation_usd == preflight.planned_budget_usd
    assert reservation.approved_price_ceiling_usd == preflight.price_ceiling_usd
    assert reservation.blocker_reason == "budget_reservation_provider_missing"
    assert reservation.budget_reservation_allowed is False
    assert reservation.budget_reserved is False
    assert reservation.provider_calls_made is False
    assert reservation.dispatch_performed is False
    assert reservation.retrieval_performed is False
    assert reservation.graph_mutated is False
    assert reservation.final_artifact_created is False
    assert "reservation provider is not configured" in reservation.reservation_notes[0]


def test_budget_reservation_gate_rejects_mismatched_activation_receipt_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare budget reservation for a midnight oil run about airline financing.",
            work_minutes=120,
            price_ceiling_usd=18.0,
            route_mode="auto_cost",
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    bad_checklist = checklist.model_copy(update={"dispatch_receipt_id": "wrong-dispatch"})

    with pytest.raises(
        ValidationError,
        match="activation_checklist_receipt must reference dispatch_receipt",
    ):
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=bad_checklist,
        )


def test_provider_route_gate_blocks_provider_execution_without_side_effects() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare provider routing for a midnight oil run about turbofan durability.",
            work_minutes=150,
            price_ceiling_usd=22.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )

    provider_route = provider_route_midnight_oil(
        MidnightOilProviderRouteRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
        )
    )

    assert provider_route.receipt_id == f"{preflight.run_id}-provider-route"
    assert provider_route.budget_reservation_receipt_id == reservation.receipt_id
    assert provider_route.activation_checklist_receipt_id == checklist.receipt_id
    assert provider_route.dispatch_receipt_id == dispatch_receipt.receipt_id
    assert provider_route.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert provider_route.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert provider_route.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert provider_route.launch_packet_id == preflight.launch_packet.packet_id
    assert provider_route.run_id == preflight.run_id
    assert provider_route.status == "blocked_provider_route_executor_disabled"
    assert provider_route.requested_route_count == len(preflight.role_plans)
    assert provider_route.planned_role_route_receipt_ids == preflight.launch_packet.role_route_receipt_ids
    assert provider_route.blocker_reason == "provider_route_executor_missing"
    assert provider_route.route_executor_allowed is False
    assert provider_route.provider_execution_allowed is False
    assert provider_route.provider_calls_made is False
    assert provider_route.budget_reserved is False
    assert provider_route.dispatch_performed is False
    assert provider_route.retrieval_performed is False
    assert provider_route.graph_mutated is False
    assert provider_route.final_artifact_created is False
    assert "model/provider route executor is not configured" in provider_route.provider_route_notes[0]


def test_provider_route_gate_rejects_mismatched_budget_reservation_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare provider routing for a midnight oil run about airline financing.",
            work_minutes=120,
            price_ceiling_usd=18.0,
            route_mode="auto_cost",
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )
    bad_reservation = reservation.model_copy(
        update={"activation_checklist_receipt_id": "wrong-checklist"}
    )

    with pytest.raises(
        ValidationError,
        match="budget_reservation_receipt must reference activation_checklist_receipt",
    ):
        MidnightOilProviderRouteRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=bad_reservation,
        )


def test_retrieval_gate_blocks_source_fetch_without_side_effects() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare retrieval for a midnight oil run about turbofan durability.",
            work_minutes=150,
            price_ceiling_usd=22.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )
    provider_route = provider_route_midnight_oil(
        MidnightOilProviderRouteRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
        )
    )

    retrieval = retrieval_midnight_oil(
        MidnightOilRetrievalRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
            provider_route_receipt=provider_route,
        )
    )

    assert retrieval.receipt_id == f"{preflight.run_id}-retrieval"
    assert retrieval.provider_route_receipt_id == provider_route.receipt_id
    assert retrieval.budget_reservation_receipt_id == reservation.receipt_id
    assert retrieval.activation_checklist_receipt_id == checklist.receipt_id
    assert retrieval.dispatch_receipt_id == dispatch_receipt.receipt_id
    assert retrieval.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert retrieval.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert retrieval.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert retrieval.launch_packet_id == preflight.launch_packet.packet_id
    assert retrieval.run_id == preflight.run_id
    assert retrieval.status == "blocked_retrieval_executor_disabled"
    assert retrieval.planned_source_policy == ["arxiv", "operator_corpus"]
    assert retrieval.planned_source_receipt_ids == [
        f"{preflight.run_id}-arxiv-source-receipt",
        f"{preflight.run_id}-operator_corpus-source-receipt",
    ]
    assert retrieval.blocker_reason == "retrieval_executor_missing"
    assert retrieval.retrieval_allowed is False
    assert retrieval.source_receipts_created is False
    assert retrieval.retrieval_performed is False
    assert retrieval.provider_calls_made is False
    assert retrieval.budget_reserved is False
    assert retrieval.dispatch_performed is False
    assert retrieval.graph_mutated is False
    assert retrieval.final_artifact_created is False
    assert "retrieval executor and source receipt writer" in retrieval.retrieval_notes[0]


def test_retrieval_gate_rejects_mismatched_provider_route_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare retrieval for a midnight oil run about airline financing.",
            work_minutes=120,
            price_ceiling_usd=18.0,
            route_mode="auto_cost",
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )
    provider_route = provider_route_midnight_oil(
        MidnightOilProviderRouteRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
        )
    )
    bad_provider_route = provider_route.model_copy(
        update={"budget_reservation_receipt_id": "wrong-budget-reservation"}
    )

    with pytest.raises(
        ValidationError,
        match="provider_route_receipt must reference budget_reservation_receipt",
    ):
        MidnightOilRetrievalRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
            provider_route_receipt=bad_provider_route,
        )


def test_graph_mutation_gate_blocks_graph_write_without_side_effects() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Prepare graph mutation for a midnight oil run about turbofan durability.",
        source_policy=["arxiv", "operator_corpus"],
    )

    graph = graph_mutation_midnight_oil(
        MidnightOilGraphMutationRequest(
            launch_packet=chain["preflight"].launch_packet,
            approval_receipt=chain["preflight"].approval_receipt,
            runner_handoff=chain["preflight"].runner_handoff,
            applied_run_receipt=chain["preflight"].applied_run_receipt,
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
        )
    )

    preflight = chain["preflight"]
    assert preflight.launch_packet is not None
    assert graph.receipt_id == f"{preflight.run_id}-graph-mutation"
    assert graph.retrieval_receipt_id == chain["retrieval"].receipt_id
    assert graph.provider_route_receipt_id == chain["provider_route"].receipt_id
    assert graph.budget_reservation_receipt_id == chain["reservation"].receipt_id
    assert graph.activation_checklist_receipt_id == chain["checklist"].receipt_id
    assert graph.dispatch_receipt_id == chain["dispatch"].receipt_id
    assert graph.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert graph.launch_packet_id == preflight.launch_packet.packet_id
    assert graph.status == "blocked_graph_mutation_disabled"
    assert graph.planned_graph_node_ids == [
        f"{preflight.run_id}-run-node",
        f"{preflight.run_id}-arxiv-source-node",
        f"{preflight.run_id}-operator_corpus-source-node",
    ]
    assert graph.planned_graph_edge_ids == [
        f"{preflight.run_id}-arxiv-source-edge",
        f"{preflight.run_id}-operator_corpus-source-edge",
    ]
    assert graph.blocker_reason == "graph_mutation_writer_missing"
    assert graph.graph_mutation_allowed is False
    assert graph.graph_mutated is False
    assert graph.source_receipts_created is False
    assert graph.retrieval_performed is False
    assert graph.provider_calls_made is False
    assert graph.budget_reserved is False
    assert graph.dispatch_performed is False
    assert graph.final_artifact_created is False
    assert "graph writer is not configured" in graph.graph_notes[0]


def test_graph_mutation_gate_rejects_mismatched_retrieval_receipt_chain() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Prepare graph mutation for a midnight oil run about airline financing.",
        source_policy=["web"],
    )
    bad_retrieval = chain["retrieval"].model_copy(
        update={"provider_route_receipt_id": "wrong-provider-route"}
    )

    with pytest.raises(
        ValidationError,
        match="retrieval_receipt must reference provider_route_receipt",
    ):
        MidnightOilGraphMutationRequest(
            launch_packet=chain["preflight"].launch_packet,
            approval_receipt=chain["preflight"].approval_receipt,
            runner_handoff=chain["preflight"].runner_handoff,
            applied_run_receipt=chain["preflight"].applied_run_receipt,
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=bad_retrieval,
        )


def test_final_artifact_contract_is_html_not_pdf_with_twin_note() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Explain lithium supply-chain chokepoints.",
            work_minutes=60,
            price_ceiling_usd=5.0,
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert result.artifact_contract.final_format == "html"
    assert result.artifact_contract.pdf_allowed is False
    assert result.artifact_contract.antiek_information_asset is True
    assert result.artifact_contract.twin_note_document_required is True
    assert result.artifact_contract.source_receipt_links_required is True
    assert result.artifact_contract.route_receipt_links_required is True


def test_midnight_oil_preflight_api_contract() -> None:
    from interfaces.research.api.app import create_app

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/preflight",
            json={
                "goal": "Explain the aircraft supply-chain bottleneck for widebody engines.",
                "work_minutes": 120,
                "price_ceiling_usd": 25.0,
                "route_mode": "auto_balanced",
                "source_policy": ["arxiv", "substack", "web", "operator_corpus"],
                "deliverable": "html_research_asset",
                "operator_acknowledged_spend": True,
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["planned_budget_usd"] == 25.0
    assert body["unallocated_budget_usd"] == 0.0
    assert body["launch_packet"]["packet_id"].endswith("-launch-packet")
    assert body["launch_packet"]["dispatch_allowed"] is False
    assert body["launch_packet"]["budget_reserved"] is False
    assert body["launch_packet"]["provider_calls_made"] is False
    assert body["launch_packet"]["role_route_receipt_ids"] == [
        plan["planned_route_receipt_id"] for plan in body["role_plans"]
    ]
    assert body["approval_receipt"]["launch_packet_id"] == body["launch_packet"]["packet_id"]
    assert body["approval_receipt"]["approved_price_ceiling_usd"] == body["price_ceiling_usd"]
    assert body["approval_receipt"]["runner_apply_required"] is True
    assert body["approval_receipt"]["dispatch_allowed"] is False
    assert body["approval_receipt"]["budget_reserved"] is False
    assert body["approval_receipt"]["provider_calls_made"] is False
    assert body["runner_handoff"]["approval_receipt_id"] == body["approval_receipt"]["receipt_id"]
    assert body["runner_handoff"]["launch_packet_id"] == body["launch_packet"]["packet_id"]
    assert body["runner_handoff"]["status"] == "ready_for_runner_apply"
    assert body["runner_handoff"]["dispatch_ready"] is True
    assert body["runner_handoff"]["dispatch_performed"] is False
    assert body["runner_handoff"]["budget_reserved"] is False
    assert body["runner_handoff"]["provider_calls_made"] is False
    assert body["runner_handoff"]["graph_mutated"] is False
    assert body["applied_run_receipt"]["runner_handoff_id"] == body["runner_handoff"]["handoff_id"]
    assert body["applied_run_receipt"]["approval_receipt_id"] == body["approval_receipt"]["receipt_id"]
    assert body["applied_run_receipt"]["launch_packet_id"] == body["launch_packet"]["packet_id"]
    assert body["applied_run_receipt"]["status"] == "planned_not_dispatched"
    assert body["applied_run_receipt"]["planned_role_count"] == 4
    assert body["applied_run_receipt"]["dispatch_performed"] is False
    assert body["applied_run_receipt"]["budget_reserved"] is False
    assert body["applied_run_receipt"]["provider_calls_made"] is False
    assert body["applied_run_receipt"]["retrieval_performed"] is False
    assert body["applied_run_receipt"]["graph_mutated"] is False
    assert body["applied_run_receipt"]["final_artifact_created"] is False
    assert body["artifact_contract"]["final_format"] == "html"
    assert len(body["role_plans"]) == 4


def test_midnight_oil_dry_run_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Dry-run a midnight oil plan about widebody engine maintenance.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/dry-run",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["runner_handoff_id"] == preflight.runner_handoff.handoff_id
    assert body["approval_receipt_id"] == preflight.approval_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "planned_not_dispatched"
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_midnight_oil_dispatch_gate_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Gate a midnight oil dispatch plan about widebody maintenance.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/dispatch",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "live_dispatch_requested": True,
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["runner_handoff_id"] == preflight.runner_handoff.handoff_id
    assert body["approval_receipt_id"] == preflight.approval_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_live_dispatch_disabled"
    assert body["live_dispatch_requested"] is True
    assert body["blocker_reason"] == "live_dispatch_disabled"
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_midnight_oil_activation_checklist_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Gate a midnight oil activation checklist about widebody maintenance.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/activation-checklist",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "dispatch_receipt": dispatch_receipt.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["dispatch_receipt_id"] == dispatch_receipt.receipt_id
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["runner_handoff_id"] == preflight.runner_handoff.handoff_id
    assert body["approval_receipt_id"] == preflight.approval_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "activation_blocked_controls_missing"
    assert "operator live-run activation setting" in body["missing_items"]
    assert "final HTML artifact writer" in body["missing_items"]
    assert body["dispatch_allowed"] is False
    assert body["budget_reservation_allowed"] is False
    assert body["provider_execution_allowed"] is False
    assert body["retrieval_allowed"] is False
    assert body["graph_mutation_allowed"] is False
    assert body["final_artifact_allowed"] is False


def test_midnight_oil_budget_reservation_gate_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Gate midnight oil budget reservation about widebody maintenance.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/budget-reservation",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "dispatch_receipt": dispatch_receipt.model_dump(mode="json"),
                "activation_checklist_receipt": checklist.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["activation_checklist_receipt_id"] == checklist.receipt_id
    assert body["dispatch_receipt_id"] == dispatch_receipt.receipt_id
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_budget_reservation_disabled"
    assert body["requested_reservation_usd"] == preflight.planned_budget_usd
    assert body["blocker_reason"] == "budget_reservation_provider_missing"
    assert body["budget_reservation_allowed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["dispatch_performed"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_midnight_oil_provider_route_gate_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Gate midnight oil provider routing about widebody maintenance.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )
    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/provider-route",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "dispatch_receipt": dispatch_receipt.model_dump(mode="json"),
                "activation_checklist_receipt": checklist.model_dump(mode="json"),
                "budget_reservation_receipt": reservation.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["budget_reservation_receipt_id"] == reservation.receipt_id
    assert body["activation_checklist_receipt_id"] == checklist.receipt_id
    assert body["dispatch_receipt_id"] == dispatch_receipt.receipt_id
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_provider_route_executor_disabled"
    assert body["requested_route_count"] == len(preflight.role_plans)
    assert body["planned_role_route_receipt_ids"] == preflight.launch_packet.role_route_receipt_ids
    assert body["blocker_reason"] == "provider_route_executor_missing"
    assert body["route_executor_allowed"] is False
    assert body["provider_execution_allowed"] is False
    assert body["provider_calls_made"] is False
    assert body["budget_reserved"] is False
    assert body["dispatch_performed"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_midnight_oil_retrieval_gate_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Gate midnight oil retrieval about widebody maintenance.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    dispatch_receipt = dispatch_midnight_oil(
        MidnightOilDispatchRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_dispatch_requested=True,
        )
    )
    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )
    reservation = budget_reservation_midnight_oil(
        MidnightOilBudgetReservationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
        )
    )
    provider_route = provider_route_midnight_oil(
        MidnightOilProviderRouteRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch_receipt,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
        )
    )
    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/retrieval",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "dispatch_receipt": dispatch_receipt.model_dump(mode="json"),
                "activation_checklist_receipt": checklist.model_dump(mode="json"),
                "budget_reservation_receipt": reservation.model_dump(mode="json"),
                "provider_route_receipt": provider_route.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["provider_route_receipt_id"] == provider_route.receipt_id
    assert body["budget_reservation_receipt_id"] == reservation.receipt_id
    assert body["activation_checklist_receipt_id"] == checklist.receipt_id
    assert body["dispatch_receipt_id"] == dispatch_receipt.receipt_id
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_retrieval_executor_disabled"
    assert body["planned_source_policy"] == ["arxiv", "web"]
    assert body["planned_source_receipt_ids"] == [
        f"{preflight.run_id}-arxiv-source-receipt",
        f"{preflight.run_id}-web-source-receipt",
    ]
    assert body["blocker_reason"] == "retrieval_executor_missing"
    assert body["retrieval_allowed"] is False
    assert body["source_receipts_created"] is False
    assert body["retrieval_performed"] is False
    assert body["provider_calls_made"] is False
    assert body["budget_reserved"] is False
    assert body["dispatch_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_midnight_oil_graph_mutation_gate_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Gate midnight oil graph mutation about widebody maintenance.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/graph-mutation",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "dispatch_receipt": chain["dispatch"].model_dump(mode="json"),
                "activation_checklist_receipt": chain["checklist"].model_dump(mode="json"),
                "budget_reservation_receipt": chain["reservation"].model_dump(mode="json"),
                "provider_route_receipt": chain["provider_route"].model_dump(mode="json"),
                "retrieval_receipt": chain["retrieval"].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["retrieval_receipt_id"] == chain["retrieval"].receipt_id
    assert body["provider_route_receipt_id"] == chain["provider_route"].receipt_id
    assert body["budget_reservation_receipt_id"] == chain["reservation"].receipt_id
    assert body["activation_checklist_receipt_id"] == chain["checklist"].receipt_id
    assert body["dispatch_receipt_id"] == chain["dispatch"].receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_graph_mutation_disabled"
    assert body["planned_graph_node_ids"] == [
        f"{preflight.run_id}-run-node",
        f"{preflight.run_id}-arxiv-source-node",
        f"{preflight.run_id}-web-source-node",
    ]
    assert body["planned_graph_edge_ids"] == [
        f"{preflight.run_id}-arxiv-source-edge",
        f"{preflight.run_id}-web-source-edge",
    ]
    assert body["blocker_reason"] == "graph_mutation_writer_missing"
    assert body["graph_mutation_allowed"] is False
    assert body["graph_mutated"] is False
    assert body["source_receipts_created"] is False
    assert body["retrieval_performed"] is False
    assert body["provider_calls_made"] is False
    assert body["budget_reserved"] is False
    assert body["dispatch_performed"] is False
    assert body["final_artifact_created"] is False
