"""Midnight-oil routing preflight contract tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from substrate.midnight_oil import (
    MidnightOilActivationChecklistRequest,
    MidnightOilBudgetProviderAdapterPlanRequest,
    MidnightOilBudgetReservationRequest,
    MidnightOilControlLedgerAdapterPlanRequest,
    MidnightOilControlLedgerPersistenceApplyPlanRequest,
    MidnightOilControlLedgerPersistencePlanRequest,
    MidnightOilDispatchRequest,
    MidnightOilDryRunRequest,
    MidnightOilFinalArtifactAdapterPlanRequest,
    MidnightOilFinalArtifactRequest,
    MidnightOilGraphAdapterPlanRequest,
    MidnightOilGraphMutationRequest,
    MidnightOilLiveDispatchFinalEnablementApplyPlanRequest,
    MidnightOilLiveDispatchFinalEnablementPlanRequest,
    MidnightOilLiveRunActivationSettingsRequest,
    MidnightOilOperatorDispatchActivationReadinessPlanRequest,
    MidnightOilOperatorDispatchAdapterPlanRequest,
    MidnightOilProviderExecutorAdapterPlanRequest,
    MidnightOilProviderRouteRequest,
    MidnightOilRequest,
    MidnightOilRetrievalAdapterPlanRequest,
    MidnightOilRetrievalRequest,
    MidnightOilRunnerControlPlanRequest,
    MidnightOilRunnerReadinessRequest,
    activation_checklist_midnight_oil,
    budget_provider_adapter_plan_midnight_oil,
    budget_reservation_midnight_oil,
    control_ledger_adapter_plan_midnight_oil,
    control_ledger_persistence_apply_plan_midnight_oil,
    control_ledger_persistence_plan_midnight_oil,
    dispatch_midnight_oil,
    dry_run_midnight_oil,
    final_artifact_adapter_plan_midnight_oil,
    final_artifact_midnight_oil,
    graph_adapter_plan_midnight_oil,
    graph_mutation_midnight_oil,
    live_dispatch_final_enablement_apply_plan_midnight_oil,
    live_dispatch_final_enablement_plan_midnight_oil,
    live_run_activation_settings_midnight_oil,
    operator_dispatch_activation_readiness_plan_midnight_oil,
    operator_dispatch_adapter_plan_midnight_oil,
    preflight_midnight_oil,
    provider_executor_adapter_plan_midnight_oil,
    provider_route_midnight_oil,
    retrieval_adapter_plan_midnight_oil,
    retrieval_midnight_oil,
    runner_control_plan_midnight_oil,
    runner_readiness_midnight_oil,
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
    live_settings = live_run_activation_settings_midnight_oil(
        MidnightOilLiveRunActivationSettingsRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            requested_live_run_enabled=True,
            requested_price_ceiling_usd=preflight.approval_receipt.approved_price_ceiling_usd,
            requested_work_minutes=preflight.approval_receipt.approved_work_minutes,
        )
    )
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
            live_run_activation_settings_receipt=live_settings,
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
    graph = graph_mutation_midnight_oil(
        MidnightOilGraphMutationRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
            provider_route_receipt=provider_route,
            retrieval_receipt=retrieval,
        )
    )
    final_artifact = final_artifact_midnight_oil(
        MidnightOilFinalArtifactRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            dispatch_receipt=dispatch,
            activation_checklist_receipt=checklist,
            budget_reservation_receipt=reservation,
            provider_route_receipt=provider_route,
            retrieval_receipt=retrieval,
            graph_mutation_receipt=graph,
        )
    )
    return {
        "preflight": preflight,
        "live_settings": live_settings,
        "dispatch": dispatch,
        "checklist": checklist,
        "reservation": reservation,
        "provider_route": provider_route,
        "retrieval": retrieval,
        "graph": graph,
        "final_artifact": final_artifact,
    }


def _accepted_midnight_oil_adapter_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_gate_chain(goal=goal, source_policy=source_policy)
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=requested_control_scope,
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )
    retrieval_adapter_plan = retrieval_adapter_plan_midnight_oil(
        MidnightOilRetrievalAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
        )
    )
    graph_adapter_plan = graph_adapter_plan_midnight_oil(
        MidnightOilGraphAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
            retrieval_adapter_plan_receipt=retrieval_adapter_plan,
        )
    )
    return {
        **chain,
        "readiness": readiness,
        "control_plan": control_plan,
        "budget_adapter_plan": budget_adapter_plan,
        "provider_adapter_plan": provider_adapter_plan,
        "retrieval_adapter_plan": retrieval_adapter_plan,
        "graph_adapter_plan": graph_adapter_plan,
    }


def _accepted_midnight_oil_final_adapter_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_adapter_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    final_artifact_adapter_plan = final_artifact_adapter_plan_midnight_oil(
        MidnightOilFinalArtifactAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
        )
    )
    return {
        **chain,
        "final_artifact_adapter_plan": final_artifact_adapter_plan,
    }


def _accepted_midnight_oil_operator_adapter_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_final_adapter_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    operator_adapter_plan = operator_dispatch_adapter_plan_midnight_oil(
        MidnightOilOperatorDispatchAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
        )
    )
    return {
        **chain,
        "operator_adapter_plan": operator_adapter_plan,
    }


def _accepted_midnight_oil_control_ledger_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_operator_adapter_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    control_ledger_plan = control_ledger_adapter_plan_midnight_oil(
        MidnightOilControlLedgerAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
        )
    )
    return {
        **chain,
        "control_ledger_plan": control_ledger_plan,
    }


def _accepted_midnight_oil_control_ledger_persistence_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_control_ledger_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    control_ledger_persistence_plan = control_ledger_persistence_plan_midnight_oil(
        MidnightOilControlLedgerPersistencePlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
        )
    )
    return {
        **chain,
        "control_ledger_persistence_plan": control_ledger_persistence_plan,
    }


def _accepted_midnight_oil_control_ledger_persistence_apply_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_control_ledger_persistence_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    control_ledger_persistence_apply_plan = control_ledger_persistence_apply_plan_midnight_oil(
        MidnightOilControlLedgerPersistenceApplyPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain[
                "control_ledger_persistence_plan"
            ],
        )
    )
    return {
        **chain,
        "control_ledger_persistence_apply_plan": control_ledger_persistence_apply_plan,
    }


def _accepted_midnight_oil_operator_dispatch_activation_readiness_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_control_ledger_persistence_apply_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    operator_dispatch_activation_readiness_plan = (
        operator_dispatch_activation_readiness_plan_midnight_oil(
            MidnightOilOperatorDispatchActivationReadinessPlanRequest(
                launch_packet=preflight.launch_packet,
                approval_receipt=preflight.approval_receipt,
                runner_handoff=preflight.runner_handoff,
                runner_control_plan_receipt=chain["control_plan"],
                budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
                provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
                retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
                graph_adapter_plan_receipt=chain["graph_adapter_plan"],
                final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
                operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
                control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
                control_ledger_persistence_plan_receipt=chain[
                    "control_ledger_persistence_plan"
                ],
                control_ledger_persistence_apply_plan_receipt=chain[
                    "control_ledger_persistence_apply_plan"
                ],
            )
        )
    )
    return {
        **chain,
        "operator_dispatch_activation_readiness_plan": (
            operator_dispatch_activation_readiness_plan
        ),
    }


def _accepted_midnight_oil_live_dispatch_final_enablement_plan_chain(
    *,
    goal: str,
    source_policy: list[str],
    requested_control_scope: list[str],
) -> dict[str, object]:
    chain = _accepted_midnight_oil_operator_dispatch_activation_readiness_plan_chain(
        goal=goal,
        source_policy=source_policy,
        requested_control_scope=requested_control_scope,
    )
    preflight = chain["preflight"]
    final_enablement_plan = live_dispatch_final_enablement_plan_midnight_oil(
        MidnightOilLiveDispatchFinalEnablementPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain[
                "control_ledger_persistence_plan"
            ],
            control_ledger_persistence_apply_plan_receipt=chain[
                "control_ledger_persistence_apply_plan"
            ],
            operator_dispatch_activation_readiness_plan_receipt=chain[
                "operator_dispatch_activation_readiness_plan"
            ],
        )
    )
    return {
        **chain,
        "live_dispatch_final_enablement_plan": final_enablement_plan,
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


def test_live_run_activation_settings_blocks_live_execution_without_side_effects() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prepare live activation settings for a midnight oil run about turbofan durability.",
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "operator_corpus"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    receipt = live_run_activation_settings_midnight_oil(
        MidnightOilLiveRunActivationSettingsRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            requested_live_run_enabled=True,
            requested_price_ceiling_usd=20.0,
            requested_work_minutes=90,
        )
    )

    assert receipt.receipt_id == f"{preflight.run_id}-live-run-activation-settings"
    assert receipt.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert receipt.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert receipt.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert receipt.launch_packet_id == preflight.launch_packet.packet_id
    assert receipt.status == "blocked_live_run_activation_disabled"
    assert receipt.settings_scope == "midnight_oil_live_run_activation"
    assert receipt.requested_live_run_enabled is True
    assert receipt.requested_price_ceiling_usd == 20.0
    assert receipt.requested_work_minutes == 90
    assert receipt.approved_price_ceiling_usd == 25.0
    assert receipt.approved_work_minutes == 120
    assert "budget reservation provider" in receipt.missing_controls
    assert "final HTML artifact writer" in receipt.missing_controls
    assert receipt.blocker_reason == "live_run_activation_controls_missing"
    assert receipt.live_run_activation_allowed is False
    assert receipt.dispatch_allowed is False
    assert receipt.dispatch_performed is False
    assert receipt.budget_reserved is False
    assert receipt.provider_calls_made is False
    assert receipt.retrieval_performed is False
    assert receipt.graph_mutated is False
    assert receipt.final_artifact_created is False


def test_live_run_activation_settings_rejects_ceiling_above_approval() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Reject inflated activation settings for a midnight oil run.",
            work_minutes=60,
            price_ceiling_usd=10.0,
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )

    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    with pytest.raises(
        ValidationError,
        match="requested_price_ceiling_usd must not exceed approved ceiling",
    ):
        MidnightOilLiveRunActivationSettingsRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            requested_live_run_enabled=True,
            requested_price_ceiling_usd=10.01,
            requested_work_minutes=60,
        )


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
    live_settings_receipt = live_run_activation_settings_midnight_oil(
        MidnightOilLiveRunActivationSettingsRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            requested_live_run_enabled=True,
            requested_price_ceiling_usd=preflight.approval_receipt.approved_price_ceiling_usd,
            requested_work_minutes=preflight.approval_receipt.approved_work_minutes,
        )
    )

    checklist = activation_checklist_midnight_oil(
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=live_settings_receipt,
            dispatch_receipt=dispatch_receipt,
        )
    )

    assert checklist.receipt_id == f"{preflight.run_id}-activation-checklist"
    assert checklist.dispatch_receipt_id == dispatch_receipt.receipt_id
    assert checklist.live_run_activation_settings_receipt_id == live_settings_receipt.receipt_id
    assert checklist.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert checklist.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert checklist.approval_receipt_id == preflight.approval_receipt.receipt_id
    assert checklist.launch_packet_id == preflight.launch_packet.packet_id
    assert checklist.run_id == preflight.run_id
    assert checklist.status == "activation_blocked_controls_missing"
    assert "blocked dispatch receipt exists" in checklist.completed_items
    assert "blocked live-run activation settings receipt exists" in checklist.completed_items
    assert "operator live-run activation setting" not in checklist.missing_items
    assert "budget reservation provider" in checklist.missing_items
    assert "model/provider route executor" in checklist.missing_items
    assert checklist.dispatch_allowed is False
    assert checklist.budget_reservation_allowed is False
    assert checklist.provider_execution_allowed is False
    assert checklist.retrieval_allowed is False
    assert checklist.graph_mutation_allowed is False
    assert checklist.final_artifact_allowed is False
    assert "live execution remains blocked" in checklist.checklist_notes[0]


def test_activation_checklist_rejects_mismatched_live_settings_receipt_chain() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Reject mismatched activation settings for a midnight oil run about fleet renewal.",
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
    live_settings_receipt = live_run_activation_settings_midnight_oil(
        MidnightOilLiveRunActivationSettingsRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            requested_live_run_enabled=True,
            requested_price_ceiling_usd=preflight.approval_receipt.approved_price_ceiling_usd,
            requested_work_minutes=preflight.approval_receipt.approved_work_minutes,
        )
    )
    bad_settings = live_settings_receipt.model_copy(update={"applied_run_receipt_id": "wrong-applied"})

    with pytest.raises(
        ValidationError,
        match="live_run_activation_settings_receipt must reference applied_run_receipt",
    ):
        MidnightOilActivationChecklistRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=bad_settings,
            dispatch_receipt=dispatch_receipt,
        )


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


def test_final_artifact_gate_blocks_html_writer_without_side_effects() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Prepare final HTML artifact for a midnight oil run about turbofan durability.",
        source_policy=["arxiv", "operator_corpus"],
    )

    artifact = final_artifact_midnight_oil(
        MidnightOilFinalArtifactRequest(
            launch_packet=chain["preflight"].launch_packet,
            approval_receipt=chain["preflight"].approval_receipt,
            runner_handoff=chain["preflight"].runner_handoff,
            applied_run_receipt=chain["preflight"].applied_run_receipt,
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
        )
    )

    preflight = chain["preflight"]
    assert preflight.launch_packet is not None
    assert artifact.receipt_id == f"{preflight.run_id}-final-artifact"
    assert artifact.graph_mutation_receipt_id == chain["graph"].receipt_id
    assert artifact.retrieval_receipt_id == chain["retrieval"].receipt_id
    assert artifact.provider_route_receipt_id == chain["provider_route"].receipt_id
    assert artifact.budget_reservation_receipt_id == chain["reservation"].receipt_id
    assert artifact.activation_checklist_receipt_id == chain["checklist"].receipt_id
    assert artifact.dispatch_receipt_id == chain["dispatch"].receipt_id
    assert artifact.applied_run_receipt_id == preflight.applied_run_receipt.receipt_id
    assert artifact.launch_packet_id == preflight.launch_packet.packet_id
    assert artifact.status == "blocked_final_artifact_writer_disabled"
    assert artifact.planned_artifact_id == f"{preflight.run_id}-html-research-asset"
    assert artifact.planned_twin_note_document_id == f"{preflight.run_id}-twin-note-document"
    assert artifact.final_format == "html"
    assert artifact.pdf_allowed is False
    assert artifact.blocker_reason == "final_html_artifact_writer_missing"
    assert artifact.final_artifact_allowed is False
    assert artifact.final_artifact_created is False
    assert artifact.graph_mutated is False
    assert artifact.source_receipts_created is False
    assert artifact.retrieval_performed is False
    assert artifact.provider_calls_made is False
    assert artifact.budget_reserved is False
    assert artifact.dispatch_performed is False
    assert "final HTML artifact writer is not configured" in artifact.artifact_notes[0]


def test_final_artifact_gate_rejects_mismatched_graph_mutation_receipt_chain() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Prepare final HTML artifact for a midnight oil run about airline financing.",
        source_policy=["web"],
    )
    bad_graph = chain["graph"].model_copy(update={"retrieval_receipt_id": "wrong-retrieval"})

    with pytest.raises(
        ValidationError,
        match="graph_mutation_receipt must reference retrieval_receipt",
    ):
        MidnightOilFinalArtifactRequest(
            launch_packet=chain["preflight"].launch_packet,
            approval_receipt=chain["preflight"].approval_receipt,
            runner_handoff=chain["preflight"].runner_handoff,
            applied_run_receipt=chain["preflight"].applied_run_receipt,
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=bad_graph,
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


def test_midnight_oil_live_run_activation_settings_api_contract() -> None:
    from interfaces.research.api.app import create_app

    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Gate live activation settings for midnight oil widebody research.",
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
            "/research/midnight-oil/live-run-activation-settings",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "requested_live_run_enabled": True,
                "requested_price_ceiling_usd": 20.0,
                "requested_work_minutes": 90,
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["runner_handoff_id"] == preflight.runner_handoff.handoff_id
    assert body["approval_receipt_id"] == preflight.approval_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_live_run_activation_disabled"
    assert body["settings_scope"] == "midnight_oil_live_run_activation"
    assert body["requested_live_run_enabled"] is True
    assert body["requested_price_ceiling_usd"] == 20.0
    assert body["requested_work_minutes"] == 90
    assert body["approved_price_ceiling_usd"] == 25.0
    assert body["approved_work_minutes"] == 120
    assert "budget reservation provider" in body["missing_controls"]
    assert body["blocker_reason"] == "live_run_activation_controls_missing"
    assert body["live_run_activation_allowed"] is False
    assert body["dispatch_allowed"] is False
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
    live_settings_receipt = live_run_activation_settings_midnight_oil(
        MidnightOilLiveRunActivationSettingsRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            requested_live_run_enabled=True,
            requested_price_ceiling_usd=preflight.approval_receipt.approved_price_ceiling_usd,
            requested_work_minutes=preflight.approval_receipt.approved_work_minutes,
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
                "live_run_activation_settings_receipt": live_settings_receipt.model_dump(mode="json"),
                "dispatch_receipt": dispatch_receipt.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["dispatch_receipt_id"] == dispatch_receipt.receipt_id
    assert body["live_run_activation_settings_receipt_id"] == live_settings_receipt.receipt_id
    assert body["applied_run_receipt_id"] == preflight.applied_run_receipt.receipt_id
    assert body["runner_handoff_id"] == preflight.runner_handoff.handoff_id
    assert body["approval_receipt_id"] == preflight.approval_receipt.receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "activation_blocked_controls_missing"
    assert "blocked live-run activation settings receipt exists" in body["completed_items"]
    assert "operator live-run activation setting" not in body["missing_items"]
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


def test_midnight_oil_final_artifact_gate_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Gate midnight oil final artifact about widebody maintenance.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/final-artifact",
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
                "graph_mutation_receipt": chain["graph"].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["graph_mutation_receipt_id"] == chain["graph"].receipt_id
    assert body["retrieval_receipt_id"] == chain["retrieval"].receipt_id
    assert body["provider_route_receipt_id"] == chain["provider_route"].receipt_id
    assert body["budget_reservation_receipt_id"] == chain["reservation"].receipt_id
    assert body["activation_checklist_receipt_id"] == chain["checklist"].receipt_id
    assert body["dispatch_receipt_id"] == chain["dispatch"].receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_final_artifact_writer_disabled"
    assert body["planned_artifact_id"] == f"{preflight.run_id}-html-research-asset"
    assert body["planned_twin_note_document_id"] == f"{preflight.run_id}-twin-note-document"
    assert body["final_format"] == "html"
    assert body["pdf_allowed"] is False
    assert body["blocker_reason"] == "final_html_artifact_writer_missing"
    assert body["final_artifact_allowed"] is False
    assert body["final_artifact_created"] is False
    assert body["graph_mutated"] is False
    assert body["source_receipts_created"] is False
    assert body["retrieval_performed"] is False
    assert body["provider_calls_made"] is False
    assert body["budget_reserved"] is False
    assert body["dispatch_performed"] is False


def test_runner_readiness_blocks_live_run_after_full_no_spend_chain() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Review runner readiness for a midnight oil run about widebody maintenance.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]

    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )

    assert readiness.receipt_id == f"{preflight.run_id}-runner-readiness"
    assert readiness.final_artifact_receipt_id == chain["final_artifact"].receipt_id
    assert readiness.graph_mutation_receipt_id == chain["graph"].receipt_id
    assert readiness.live_run_activation_settings_receipt_id == chain["live_settings"].receipt_id
    assert readiness.activation_checklist_receipt_id == chain["checklist"].receipt_id
    assert readiness.status == "blocked_runner_readiness_controls_missing"
    assert chain["live_settings"].receipt_id in readiness.completed_receipt_ids
    assert chain["final_artifact"].receipt_id in readiness.completed_receipt_ids
    assert "budget reservation provider" in readiness.remaining_blockers
    assert "operator live-run dispatch enablement" in readiness.remaining_blockers
    assert readiness.blocker_reason == "runner_readiness_controls_missing"
    assert readiness.live_run_allowed is False
    assert readiness.dispatch_allowed is False
    assert readiness.budget_reservation_allowed is False
    assert readiness.provider_execution_allowed is False
    assert readiness.retrieval_allowed is False
    assert readiness.graph_mutation_allowed is False
    assert readiness.final_artifact_allowed is False
    assert readiness.dispatch_performed is False
    assert readiness.budget_reserved is False
    assert readiness.provider_calls_made is False
    assert readiness.retrieval_performed is False
    assert readiness.graph_mutated is False
    assert readiness.final_artifact_created is False
    assert "full no-spend receipt chain" in readiness.readiness_notes[0]


def test_runner_readiness_rejects_unlinked_live_settings_checklist() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Reject readiness when activation checklist is not linked to live settings.",
        source_policy=["web"],
    )
    preflight = chain["preflight"]
    bad_checklist = chain["checklist"].model_copy(
        update={"live_run_activation_settings_receipt_id": "wrong-settings"}
    )

    with pytest.raises(
        ValidationError,
        match="activation_checklist_receipt must reference live_run_activation_settings_receipt",
    ):
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=bad_checklist,
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )


def test_midnight_oil_runner_readiness_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Gate midnight oil runner readiness about widebody maintenance.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/runner-readiness",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "applied_run_receipt": preflight.applied_run_receipt.model_dump(mode="json"),
                "live_run_activation_settings_receipt": chain["live_settings"].model_dump(mode="json"),
                "dispatch_receipt": chain["dispatch"].model_dump(mode="json"),
                "activation_checklist_receipt": chain["checklist"].model_dump(mode="json"),
                "budget_reservation_receipt": chain["reservation"].model_dump(mode="json"),
                "provider_route_receipt": chain["provider_route"].model_dump(mode="json"),
                "retrieval_receipt": chain["retrieval"].model_dump(mode="json"),
                "graph_mutation_receipt": chain["graph"].model_dump(mode="json"),
                "final_artifact_receipt": chain["final_artifact"].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["final_artifact_receipt_id"] == chain["final_artifact"].receipt_id
    assert body["graph_mutation_receipt_id"] == chain["graph"].receipt_id
    assert body["retrieval_receipt_id"] == chain["retrieval"].receipt_id
    assert body["provider_route_receipt_id"] == chain["provider_route"].receipt_id
    assert body["budget_reservation_receipt_id"] == chain["reservation"].receipt_id
    assert body["activation_checklist_receipt_id"] == chain["checklist"].receipt_id
    assert body["live_run_activation_settings_receipt_id"] == chain["live_settings"].receipt_id
    assert body["launch_packet_id"] == preflight.launch_packet.packet_id
    assert body["status"] == "blocked_runner_readiness_controls_missing"
    assert chain["final_artifact"].receipt_id in body["completed_receipt_ids"]
    assert "final HTML artifact writer" in body["remaining_blockers"]
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["budget_reservation_allowed"] is False
    assert body["provider_execution_allowed"] is False
    assert body["retrieval_allowed"] is False
    assert body["graph_mutation_allowed"] is False
    assert body["final_artifact_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_runner_control_plan_records_missing_implementation_requirements() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Plan controls for a midnight oil run about widebody maintenance.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )

    plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
        )
    )

    assert plan.receipt_id == f"{preflight.run_id}-runner-control-plan"
    assert plan.runner_readiness_receipt_id == readiness.receipt_id
    assert plan.runner_handoff_id == preflight.runner_handoff.handoff_id
    assert plan.status == "blocked_runner_controls_unimplemented"
    assert plan.requested_control_scope == plan.required_control_order
    assert len(plan.implementation_requirements) == 6
    assert plan.implementation_requirements[0].control_key == "budget_reservation_provider"
    assert plan.implementation_requirements[0].blocker == "budget reservation provider"
    assert "budget provider adapter" in plan.implementation_requirements[0].required_artifact
    assert all(req.implementation_status == "missing" for req in plan.implementation_requirements)
    assert all(req.live_enablement_allowed is False for req in plan.implementation_requirements)
    assert "final HTML artifact writer" in plan.remaining_blockers
    assert plan.blocker_reason == "runner_controls_unimplemented"
    assert plan.live_run_allowed is False
    assert plan.dispatch_allowed is False
    assert plan.budget_reservation_allowed is False
    assert plan.provider_execution_allowed is False
    assert plan.retrieval_allowed is False
    assert plan.graph_mutation_allowed is False
    assert plan.final_artifact_allowed is False
    assert plan.dispatch_performed is False
    assert plan.budget_reserved is False
    assert plan.provider_calls_made is False
    assert plan.retrieval_performed is False
    assert plan.graph_mutated is False
    assert plan.final_artifact_created is False
    assert "implementation requirements are recorded" in plan.control_plan_notes[0]


def test_runner_control_plan_rejects_readiness_that_allows_live_run() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Reject control plan when readiness allows live execution.",
        source_policy=["web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    ).model_copy(update={"live_run_allowed": True})

    with pytest.raises(ValidationError, match="runner_readiness_receipt must not allow live run"):
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
        )


def test_midnight_oil_runner_control_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Gate midnight oil runner controls about widebody maintenance.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/runner-control-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_readiness_receipt": readiness.model_dump(mode="json"),
                "requested_control_scope": [
                    "budget_reservation_provider",
                    "operator_live_dispatch_enablement",
                ],
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-runner-control-plan"
    assert body["runner_readiness_receipt_id"] == readiness.receipt_id
    assert body["status"] == "blocked_runner_controls_unimplemented"
    assert body["requested_control_scope"] == [
        "budget_reservation_provider",
        "operator_live_dispatch_enablement",
    ]
    assert body["required_control_order"] == [
        "budget_reservation_provider",
        "model_provider_route_executor",
        "retrieval_executor_source_receipts",
        "graph_mutation_writer",
        "final_html_artifact_writer",
        "operator_live_dispatch_enablement",
    ]
    assert [item["control_key"] for item in body["implementation_requirements"]] == [
        "budget_reservation_provider",
        "operator_live_dispatch_enablement",
    ]
    assert body["implementation_requirements"][0]["implementation_status"] == "missing"
    assert body["implementation_requirements"][0]["live_enablement_allowed"] is False
    assert "budget reservation provider" in body["remaining_blockers"]
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["budget_reservation_allowed"] is False
    assert body["provider_execution_allowed"] is False
    assert body["retrieval_allowed"] is False
    assert body["graph_mutation_allowed"] is False
    assert body["final_artifact_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_budget_provider_adapter_plan_records_disabled_adapter_requirements() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Plan a budget provider adapter for a midnight oil widebody run.",
        source_policy=["arxiv", "substack"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=["budget_reservation_provider"],
        )
    )

    adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )

    assert adapter_plan.receipt_id == f"{preflight.run_id}-budget-provider-adapter-plan"
    assert adapter_plan.runner_control_plan_receipt_id == control_plan.receipt_id
    assert adapter_plan.runner_readiness_receipt_id == readiness.receipt_id
    assert adapter_plan.status == "blocked_budget_provider_adapter_unimplemented"
    assert adapter_plan.adapter_key == "budget_reservation_provider"
    assert adapter_plan.planned_adapter_id == f"{preflight.run_id}-budget-provider-adapter"
    assert adapter_plan.planned_ledger_id == f"{preflight.run_id}-budget-reservation-ledger"
    assert preflight.launch_packet.packet_id in adapter_plan.idempotency_key
    assert preflight.approval_receipt.receipt_id in adapter_plan.idempotency_key
    assert adapter_plan.approved_price_ceiling_usd == preflight.price_ceiling_usd
    assert adapter_plan.planned_budget_usd == preflight.planned_budget_usd
    assert "approved price ceiling" in adapter_plan.required_invariants[0]
    assert "reservation_id" in adapter_plan.required_ledger_fields
    assert "released_at" in adapter_plan.required_ledger_fields
    assert adapter_plan.blocker_reason == "budget_provider_adapter_unimplemented"
    assert adapter_plan.budget_reservation_allowed is False
    assert adapter_plan.budget_reserved is False
    assert adapter_plan.live_run_allowed is False
    assert adapter_plan.dispatch_allowed is False
    assert adapter_plan.provider_execution_allowed is False
    assert adapter_plan.retrieval_allowed is False
    assert adapter_plan.graph_mutation_allowed is False
    assert adapter_plan.final_artifact_allowed is False
    assert adapter_plan.dispatch_performed is False
    assert adapter_plan.provider_calls_made is False
    assert adapter_plan.retrieval_performed is False
    assert adapter_plan.graph_mutated is False
    assert adapter_plan.final_artifact_created is False
    assert "no reservation provider is configured" in adapter_plan.adapter_plan_notes[0]


def test_budget_provider_adapter_plan_rejects_control_plan_without_budget_provider() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Reject a budget adapter plan when budget provider was not requested.",
        source_policy=["web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=["operator_live_dispatch_enablement"],
        )
    )

    with pytest.raises(
        ValidationError,
        match="runner_control_plan_receipt must request budget_reservation_provider",
    ):
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )


def test_midnight_oil_budget_provider_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Expose budget provider adapter planning over the API.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=["budget_reservation_provider"],
        )
    )

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/budget-provider-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": control_plan.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-budget-provider-adapter-plan"
    assert body["runner_control_plan_receipt_id"] == control_plan.receipt_id
    assert body["runner_readiness_receipt_id"] == readiness.receipt_id
    assert body["status"] == "blocked_budget_provider_adapter_unimplemented"
    assert body["adapter_key"] == "budget_reservation_provider"
    assert body["planned_adapter_id"] == f"{preflight.run_id}-budget-provider-adapter"
    assert body["planned_ledger_id"] == f"{preflight.run_id}-budget-reservation-ledger"
    assert body["approved_price_ceiling_usd"] == preflight.price_ceiling_usd
    assert body["planned_budget_usd"] == preflight.planned_budget_usd
    assert "idempotency_key" in body
    assert "status" in body["required_ledger_fields"]
    assert body["blocker_reason"] == "budget_provider_adapter_unimplemented"
    assert body["budget_reservation_allowed"] is False
    assert body["budget_reserved"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["provider_execution_allowed"] is False
    assert body["retrieval_allowed"] is False
    assert body["graph_mutation_allowed"] is False
    assert body["final_artifact_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_provider_executor_adapter_plan_records_disabled_route_requirements() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Plan a provider executor adapter for a midnight oil widebody run.",
        source_policy=["arxiv", "substack"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )

    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )

    assert provider_adapter_plan.receipt_id == f"{preflight.run_id}-provider-executor-adapter-plan"
    assert provider_adapter_plan.runner_control_plan_receipt_id == control_plan.receipt_id
    assert provider_adapter_plan.budget_provider_adapter_plan_receipt_id == budget_adapter_plan.receipt_id
    assert provider_adapter_plan.runner_readiness_receipt_id == readiness.receipt_id
    assert provider_adapter_plan.status == "blocked_provider_executor_adapter_unimplemented"
    assert provider_adapter_plan.adapter_key == "model_provider_route_executor"
    assert provider_adapter_plan.planned_executor_id == f"{preflight.run_id}-provider-executor-adapter"
    assert provider_adapter_plan.planned_route_ledger_id == f"{preflight.run_id}-provider-route-ledger"
    assert provider_adapter_plan.planned_role_route_receipt_ids == preflight.launch_packet.role_route_receipt_ids
    assert provider_adapter_plan.requested_route_count == preflight.launch_packet.role_count
    assert provider_adapter_plan.route_mode == preflight.route_mode
    assert provider_adapter_plan.provider_policy == "operator_configured_models_only"
    assert "active budget reservation" in provider_adapter_plan.required_invariants[0]
    assert "route_receipt_id" in provider_adapter_plan.required_route_receipt_fields
    assert "budget_reservation_id" in provider_adapter_plan.required_route_receipt_fields
    assert provider_adapter_plan.blocker_reason == "provider_executor_adapter_unimplemented"
    assert provider_adapter_plan.provider_execution_allowed is False
    assert provider_adapter_plan.provider_calls_made is False
    assert provider_adapter_plan.live_run_allowed is False
    assert provider_adapter_plan.dispatch_allowed is False
    assert provider_adapter_plan.budget_reservation_allowed is False
    assert provider_adapter_plan.budget_reserved is False
    assert provider_adapter_plan.retrieval_allowed is False
    assert provider_adapter_plan.graph_mutation_allowed is False
    assert provider_adapter_plan.final_artifact_allowed is False
    assert provider_adapter_plan.dispatch_performed is False
    assert provider_adapter_plan.retrieval_performed is False
    assert provider_adapter_plan.graph_mutated is False
    assert provider_adapter_plan.final_artifact_created is False
    assert "no model/provider executor is configured" in provider_adapter_plan.adapter_plan_notes[0]


def test_provider_executor_adapter_plan_rejects_control_plan_without_provider_executor() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Reject provider adapter planning when provider executor was not requested.",
        source_policy=["web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=["budget_reservation_provider"],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )

    with pytest.raises(
        ValidationError,
        match="runner_control_plan_receipt must request model_provider_route_executor",
    ):
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )


def test_midnight_oil_provider_executor_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Expose provider executor adapter planning over the API.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/provider-executor-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": control_plan.model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": budget_adapter_plan.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-provider-executor-adapter-plan"
    assert body["runner_control_plan_receipt_id"] == control_plan.receipt_id
    assert body["budget_provider_adapter_plan_receipt_id"] == budget_adapter_plan.receipt_id
    assert body["runner_readiness_receipt_id"] == readiness.receipt_id
    assert body["status"] == "blocked_provider_executor_adapter_unimplemented"
    assert body["adapter_key"] == "model_provider_route_executor"
    assert body["planned_executor_id"] == f"{preflight.run_id}-provider-executor-adapter"
    assert body["planned_route_ledger_id"] == f"{preflight.run_id}-provider-route-ledger"
    assert body["planned_role_route_receipt_ids"] == preflight.launch_packet.role_route_receipt_ids
    assert body["requested_route_count"] == preflight.launch_packet.role_count
    assert body["route_mode"] == preflight.route_mode
    assert body["provider_policy"] == "operator_configured_models_only"
    assert "provider" in body["required_route_receipt_fields"]
    assert "budget_reservation_id" in body["required_route_receipt_fields"]
    assert body["blocker_reason"] == "provider_executor_adapter_unimplemented"
    assert body["provider_execution_allowed"] is False
    assert body["provider_calls_made"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["budget_reservation_allowed"] is False
    assert body["budget_reserved"] is False
    assert body["retrieval_allowed"] is False
    assert body["graph_mutation_allowed"] is False
    assert body["final_artifact_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["retrieval_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_retrieval_adapter_plan_records_disabled_source_receipt_requirements() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Plan a retrieval adapter for a midnight oil source-heavy run.",
        source_policy=["arxiv", "substack", "operator_corpus"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
                "retrieval_executor_source_receipts",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )

    retrieval_adapter_plan = retrieval_adapter_plan_midnight_oil(
        MidnightOilRetrievalAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
        )
    )

    assert retrieval_adapter_plan.receipt_id == f"{preflight.run_id}-retrieval-adapter-plan"
    assert retrieval_adapter_plan.runner_control_plan_receipt_id == control_plan.receipt_id
    assert retrieval_adapter_plan.budget_provider_adapter_plan_receipt_id == (
        budget_adapter_plan.receipt_id
    )
    assert retrieval_adapter_plan.provider_executor_adapter_plan_receipt_id == (
        provider_adapter_plan.receipt_id
    )
    assert retrieval_adapter_plan.runner_readiness_receipt_id == readiness.receipt_id
    assert retrieval_adapter_plan.status == "blocked_retrieval_adapter_unimplemented"
    assert retrieval_adapter_plan.adapter_key == "retrieval_executor_source_receipts"
    assert retrieval_adapter_plan.planned_executor_id == f"{preflight.run_id}-retrieval-adapter"
    assert retrieval_adapter_plan.planned_source_ledger_id == (
        f"{preflight.run_id}-source-receipt-ledger"
    )
    assert retrieval_adapter_plan.planned_source_policy == preflight.source_policy
    assert retrieval_adapter_plan.planned_source_receipt_ids == [
        f"{preflight.run_id}-arxiv-source-receipt",
        f"{preflight.run_id}-substack-source-receipt",
        f"{preflight.run_id}-operator_corpus-source-receipt",
    ]
    assert retrieval_adapter_plan.requested_source_count == 3
    assert "source receipt" in retrieval_adapter_plan.required_invariants[1]
    assert "source_uri" in retrieval_adapter_plan.required_source_receipt_fields
    assert "content_digest" in retrieval_adapter_plan.required_source_receipt_fields
    assert retrieval_adapter_plan.blocker_reason == "retrieval_adapter_unimplemented"
    assert retrieval_adapter_plan.retrieval_allowed is False
    assert retrieval_adapter_plan.retrieval_performed is False
    assert retrieval_adapter_plan.source_receipts_created is False
    assert retrieval_adapter_plan.provider_execution_allowed is False
    assert retrieval_adapter_plan.provider_calls_made is False
    assert retrieval_adapter_plan.live_run_allowed is False
    assert retrieval_adapter_plan.dispatch_allowed is False
    assert retrieval_adapter_plan.budget_reservation_allowed is False
    assert retrieval_adapter_plan.budget_reserved is False
    assert retrieval_adapter_plan.graph_mutation_allowed is False
    assert retrieval_adapter_plan.final_artifact_allowed is False
    assert retrieval_adapter_plan.dispatch_performed is False
    assert retrieval_adapter_plan.graph_mutated is False
    assert retrieval_adapter_plan.final_artifact_created is False
    assert "no source connector is configured" in retrieval_adapter_plan.adapter_plan_notes[0]


def test_retrieval_adapter_plan_rejects_control_plan_without_retrieval_scope() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Reject retrieval adapter planning when retrieval controls were not requested.",
        source_policy=["web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )

    with pytest.raises(
        ValidationError,
        match="runner_control_plan_receipt must request retrieval_executor_source_receipts",
    ):
        MidnightOilRetrievalAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
        )


def test_midnight_oil_retrieval_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Expose retrieval adapter planning over the API.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
                "retrieval_executor_source_receipts",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/retrieval-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": control_plan.model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": budget_adapter_plan.model_dump(
                    mode="json"
                ),
                "provider_executor_adapter_plan_receipt": provider_adapter_plan.model_dump(
                    mode="json"
                ),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-retrieval-adapter-plan"
    assert body["runner_control_plan_receipt_id"] == control_plan.receipt_id
    assert body["budget_provider_adapter_plan_receipt_id"] == budget_adapter_plan.receipt_id
    assert body["provider_executor_adapter_plan_receipt_id"] == provider_adapter_plan.receipt_id
    assert body["runner_readiness_receipt_id"] == readiness.receipt_id
    assert body["status"] == "blocked_retrieval_adapter_unimplemented"
    assert body["adapter_key"] == "retrieval_executor_source_receipts"
    assert body["planned_executor_id"] == f"{preflight.run_id}-retrieval-adapter"
    assert body["planned_source_ledger_id"] == f"{preflight.run_id}-source-receipt-ledger"
    assert body["planned_source_policy"] == preflight.source_policy
    assert body["requested_source_count"] == 2
    assert "source_uri" in body["required_source_receipt_fields"]
    assert "availability_status" in body["required_source_receipt_fields"]
    assert body["blocker_reason"] == "retrieval_adapter_unimplemented"
    assert body["retrieval_allowed"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["provider_execution_allowed"] is False
    assert body["provider_calls_made"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["budget_reservation_allowed"] is False
    assert body["budget_reserved"] is False
    assert body["graph_mutation_allowed"] is False
    assert body["final_artifact_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_graph_adapter_plan_records_disabled_graph_requirements() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Plan a graph adapter for a midnight oil source graph.",
        source_policy=["arxiv", "web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
                "retrieval_executor_source_receipts",
                "graph_mutation_writer",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )
    retrieval_adapter_plan = retrieval_adapter_plan_midnight_oil(
        MidnightOilRetrievalAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
        )
    )

    graph_adapter_plan = graph_adapter_plan_midnight_oil(
        MidnightOilGraphAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
            retrieval_adapter_plan_receipt=retrieval_adapter_plan,
        )
    )

    assert graph_adapter_plan.receipt_id == f"{preflight.run_id}-graph-adapter-plan"
    assert graph_adapter_plan.retrieval_adapter_plan_receipt_id == retrieval_adapter_plan.receipt_id
    assert graph_adapter_plan.status == "blocked_graph_adapter_unimplemented"
    assert graph_adapter_plan.adapter_key == "graph_mutation_writer"
    assert graph_adapter_plan.planned_writer_id == f"{preflight.run_id}-graph-adapter"
    assert graph_adapter_plan.planned_graph_ledger_id == f"{preflight.run_id}-graph-mutation-ledger"
    assert graph_adapter_plan.planned_graph_node_ids == [
        f"{preflight.run_id}-run-node",
        f"{preflight.run_id}-arxiv-source-node",
        f"{preflight.run_id}-web-source-node",
    ]
    assert graph_adapter_plan.planned_graph_edge_ids == [
        f"{preflight.run_id}-arxiv-cites-edge",
        f"{preflight.run_id}-web-cites-edge",
    ]
    assert "source receipts" in graph_adapter_plan.required_invariants[0]
    assert "node_ids" in graph_adapter_plan.required_graph_receipt_fields
    assert "source_receipt_ids" in graph_adapter_plan.required_graph_receipt_fields
    assert graph_adapter_plan.blocker_reason == "graph_adapter_unimplemented"
    assert graph_adapter_plan.graph_mutation_allowed is False
    assert graph_adapter_plan.graph_mutated is False
    assert graph_adapter_plan.source_receipts_created is False
    assert graph_adapter_plan.retrieval_allowed is False
    assert graph_adapter_plan.retrieval_performed is False
    assert graph_adapter_plan.provider_execution_allowed is False
    assert graph_adapter_plan.provider_calls_made is False
    assert graph_adapter_plan.live_run_allowed is False
    assert graph_adapter_plan.dispatch_allowed is False
    assert graph_adapter_plan.budget_reservation_allowed is False
    assert graph_adapter_plan.budget_reserved is False
    assert graph_adapter_plan.final_artifact_allowed is False
    assert graph_adapter_plan.dispatch_performed is False
    assert graph_adapter_plan.final_artifact_created is False
    assert "no graph writer is configured" in graph_adapter_plan.adapter_plan_notes[0]


def test_graph_adapter_plan_rejects_control_plan_without_graph_scope() -> None:
    chain = _accepted_midnight_oil_gate_chain(
        goal="Reject graph adapter planning when graph controls were not requested.",
        source_policy=["web"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
                "retrieval_executor_source_receipts",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )
    retrieval_adapter_plan = retrieval_adapter_plan_midnight_oil(
        MidnightOilRetrievalAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
        )
    )

    with pytest.raises(
        ValidationError,
        match="runner_control_plan_receipt must request graph_mutation_writer",
    ):
        MidnightOilGraphAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
            retrieval_adapter_plan_receipt=retrieval_adapter_plan,
        )


def test_midnight_oil_graph_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_gate_chain(
        goal="Expose graph adapter planning over the API.",
        source_policy=["arxiv", "substack"],
    )
    preflight = chain["preflight"]
    readiness = runner_readiness_midnight_oil(
        MidnightOilRunnerReadinessRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            live_run_activation_settings_receipt=chain["live_settings"],
            dispatch_receipt=chain["dispatch"],
            activation_checklist_receipt=chain["checklist"],
            budget_reservation_receipt=chain["reservation"],
            provider_route_receipt=chain["provider_route"],
            retrieval_receipt=chain["retrieval"],
            graph_mutation_receipt=chain["graph"],
            final_artifact_receipt=chain["final_artifact"],
        )
    )
    control_plan = runner_control_plan_midnight_oil(
        MidnightOilRunnerControlPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_readiness_receipt=readiness,
            requested_control_scope=[
                "budget_reservation_provider",
                "model_provider_route_executor",
                "retrieval_executor_source_receipts",
                "graph_mutation_writer",
            ],
        )
    )
    budget_adapter_plan = budget_provider_adapter_plan_midnight_oil(
        MidnightOilBudgetProviderAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
        )
    )
    provider_adapter_plan = provider_executor_adapter_plan_midnight_oil(
        MidnightOilProviderExecutorAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
        )
    )
    retrieval_adapter_plan = retrieval_adapter_plan_midnight_oil(
        MidnightOilRetrievalAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=control_plan,
            budget_provider_adapter_plan_receipt=budget_adapter_plan,
            provider_executor_adapter_plan_receipt=provider_adapter_plan,
        )
    )

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/graph-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": control_plan.model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": budget_adapter_plan.model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": provider_adapter_plan.model_dump(
                    mode="json"
                ),
                "retrieval_adapter_plan_receipt": retrieval_adapter_plan.model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-graph-adapter-plan"
    assert body["retrieval_adapter_plan_receipt_id"] == retrieval_adapter_plan.receipt_id
    assert body["status"] == "blocked_graph_adapter_unimplemented"
    assert body["adapter_key"] == "graph_mutation_writer"
    assert body["planned_writer_id"] == f"{preflight.run_id}-graph-adapter"
    assert body["planned_graph_ledger_id"] == f"{preflight.run_id}-graph-mutation-ledger"
    assert "node_ids" in body["required_graph_receipt_fields"]
    assert "route_receipt_ids" in body["required_graph_receipt_fields"]
    assert body["blocker_reason"] == "graph_adapter_unimplemented"
    assert body["graph_mutation_allowed"] is False
    assert body["graph_mutated"] is False
    assert body["source_receipts_created"] is False
    assert body["retrieval_performed"] is False
    assert body["provider_calls_made"] is False
    assert body["budget_reserved"] is False
    assert body["dispatch_performed"] is False
    assert body["final_artifact_created"] is False


def test_final_artifact_adapter_plan_records_disabled_html_requirements() -> None:
    chain = _accepted_midnight_oil_adapter_plan_chain(
        goal="Plan a final HTML artifact adapter for a midnight oil report.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
        ],
    )
    preflight = chain["preflight"]

    final_adapter_plan = final_artifact_adapter_plan_midnight_oil(
        MidnightOilFinalArtifactAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
        )
    )

    assert final_adapter_plan.receipt_id == f"{preflight.run_id}-final-artifact-adapter-plan"
    assert final_adapter_plan.graph_adapter_plan_receipt_id == (
        chain["graph_adapter_plan"].receipt_id
    )
    assert final_adapter_plan.status == "blocked_final_artifact_adapter_unimplemented"
    assert final_adapter_plan.adapter_key == "final_html_artifact_writer"
    assert final_adapter_plan.planned_writer_id == (
        f"{preflight.run_id}-final-html-artifact-writer"
    )
    assert final_adapter_plan.planned_artifact_ledger_id == (
        f"{preflight.run_id}-artifact-receipt-ledger"
    )
    assert final_adapter_plan.planned_artifact_id == f"{preflight.run_id}-html-research-asset"
    assert final_adapter_plan.planned_twin_note_document_id == (
        f"{preflight.run_id}-twin-note-document"
    )
    assert final_adapter_plan.final_format == "html"
    assert final_adapter_plan.pdf_allowed is False
    assert "route, source, and graph receipts" in final_adapter_plan.required_invariants[0]
    assert "artifact_receipt_id" in final_adapter_plan.required_artifact_receipt_fields
    assert "twin_note_document_id" in final_adapter_plan.required_artifact_receipt_fields
    assert "graph_receipt_id" in final_adapter_plan.required_artifact_receipt_fields
    assert final_adapter_plan.blocker_reason == "final_artifact_adapter_unimplemented"
    assert final_adapter_plan.final_artifact_allowed is False
    assert final_adapter_plan.final_artifact_created is False
    assert final_adapter_plan.graph_mutation_allowed is False
    assert final_adapter_plan.graph_mutated is False
    assert final_adapter_plan.source_receipts_created is False
    assert final_adapter_plan.retrieval_allowed is False
    assert final_adapter_plan.retrieval_performed is False
    assert final_adapter_plan.provider_execution_allowed is False
    assert final_adapter_plan.provider_calls_made is False
    assert final_adapter_plan.live_run_allowed is False
    assert final_adapter_plan.dispatch_allowed is False
    assert final_adapter_plan.budget_reservation_allowed is False
    assert final_adapter_plan.budget_reserved is False
    assert final_adapter_plan.dispatch_performed is False
    assert "no HTML asset writer is configured" in final_adapter_plan.adapter_plan_notes[0]


def test_final_artifact_adapter_plan_rejects_control_plan_without_final_scope() -> None:
    chain = _accepted_midnight_oil_adapter_plan_chain(
        goal="Reject final artifact adapter planning when final writer controls were not requested.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
        ],
    )
    preflight = chain["preflight"]

    with pytest.raises(
        ValidationError,
        match="runner_control_plan_receipt must request final_html_artifact_writer",
    ):
        MidnightOilFinalArtifactAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
        )


def test_midnight_oil_final_artifact_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_adapter_plan_chain(
        goal="Expose final HTML artifact adapter planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
        ],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/final-artifact-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-final-artifact-adapter-plan"
    assert body["graph_adapter_plan_receipt_id"] == chain["graph_adapter_plan"].receipt_id
    assert body["status"] == "blocked_final_artifact_adapter_unimplemented"
    assert body["adapter_key"] == "final_html_artifact_writer"
    assert body["planned_writer_id"] == f"{preflight.run_id}-final-html-artifact-writer"
    assert body["planned_artifact_ledger_id"] == f"{preflight.run_id}-artifact-receipt-ledger"
    assert body["planned_artifact_id"] == f"{preflight.run_id}-html-research-asset"
    assert body["planned_twin_note_document_id"] == f"{preflight.run_id}-twin-note-document"
    assert body["final_format"] == "html"
    assert body["pdf_allowed"] is False
    assert "artifact_receipt_id" in body["required_artifact_receipt_fields"]
    assert "route_receipt_ids" in body["required_artifact_receipt_fields"]
    assert "source_receipt_ids" in body["required_artifact_receipt_fields"]
    assert body["blocker_reason"] == "final_artifact_adapter_unimplemented"
    assert body["final_artifact_allowed"] is False
    assert body["final_artifact_created"] is False
    assert body["graph_mutated"] is False
    assert body["source_receipts_created"] is False
    assert body["retrieval_performed"] is False
    assert body["provider_calls_made"] is False
    assert body["budget_reserved"] is False
    assert body["dispatch_performed"] is False


def test_operator_dispatch_adapter_plan_records_disabled_dispatch_controls() -> None:
    chain = _accepted_midnight_oil_final_adapter_plan_chain(
        goal="Plan operator live dispatch controls for a midnight oil run.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    operator_adapter_plan = operator_dispatch_adapter_plan_midnight_oil(
        MidnightOilOperatorDispatchAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
        )
    )

    assert operator_adapter_plan.receipt_id == f"{preflight.run_id}-operator-dispatch-adapter-plan"
    assert operator_adapter_plan.final_artifact_adapter_plan_receipt_id == (
        chain["final_artifact_adapter_plan"].receipt_id
    )
    assert operator_adapter_plan.status == "blocked_operator_dispatch_adapter_unimplemented"
    assert operator_adapter_plan.adapter_key == "operator_live_dispatch_enablement"
    assert operator_adapter_plan.planned_setting_id == (
        f"{preflight.run_id}-operator-live-dispatch-setting"
    )
    assert operator_adapter_plan.planned_control_ledger_id == (
        f"{preflight.run_id}-operator-dispatch-control-ledger"
    )
    assert "explicit operator toggle" in operator_adapter_plan.required_invariants[1]
    assert "operator_dispatch_setting_id" in operator_adapter_plan.required_dispatch_enablement_fields
    assert "rollback_receipt_id" in operator_adapter_plan.required_dispatch_enablement_fields
    assert operator_adapter_plan.blocker_reason == "operator_dispatch_adapter_unimplemented"
    assert operator_adapter_plan.operator_dispatch_allowed is False
    assert operator_adapter_plan.operator_live_dispatch_enabled is False
    assert operator_adapter_plan.live_run_allowed is False
    assert operator_adapter_plan.dispatch_allowed is False
    assert operator_adapter_plan.dispatch_performed is False
    assert operator_adapter_plan.budget_reservation_allowed is False
    assert operator_adapter_plan.budget_reserved is False
    assert operator_adapter_plan.provider_execution_allowed is False
    assert operator_adapter_plan.provider_calls_made is False
    assert operator_adapter_plan.retrieval_allowed is False
    assert operator_adapter_plan.retrieval_performed is False
    assert operator_adapter_plan.source_receipts_created is False
    assert operator_adapter_plan.graph_mutation_allowed is False
    assert operator_adapter_plan.graph_mutated is False
    assert operator_adapter_plan.final_artifact_allowed is False
    assert operator_adapter_plan.final_artifact_created is False
    assert "no live dispatch setting is persisted" in operator_adapter_plan.adapter_plan_notes[0]


def test_operator_dispatch_adapter_plan_rejects_control_plan_without_operator_scope() -> None:
    chain = _accepted_midnight_oil_final_adapter_plan_chain(
        goal="Reject operator dispatch planning when operator controls were not requested.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
        ],
    )
    preflight = chain["preflight"]

    with pytest.raises(
        ValidationError,
        match="runner_control_plan_receipt must request operator_live_dispatch_enablement",
    ):
        MidnightOilOperatorDispatchAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
        )


def test_midnight_oil_operator_dispatch_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_final_adapter_plan_chain(
        goal="Expose operator dispatch adapter planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/operator-dispatch-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-operator-dispatch-adapter-plan"
    assert body["final_artifact_adapter_plan_receipt_id"] == (
        chain["final_artifact_adapter_plan"].receipt_id
    )
    assert body["status"] == "blocked_operator_dispatch_adapter_unimplemented"
    assert body["adapter_key"] == "operator_live_dispatch_enablement"
    assert body["planned_setting_id"] == f"{preflight.run_id}-operator-live-dispatch-setting"
    assert body["planned_control_ledger_id"] == (
        f"{preflight.run_id}-operator-dispatch-control-ledger"
    )
    assert "approved_price_ceiling_usd" in body["required_dispatch_enablement_fields"]
    assert "enabled_by_operator_id" in body["required_dispatch_enablement_fields"]
    assert body["blocker_reason"] == "operator_dispatch_adapter_unimplemented"
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_live_dispatch_final_enablement_apply_plan_records_disabled_requirements() -> None:
    chain = _accepted_midnight_oil_live_dispatch_final_enablement_plan_chain(
        goal="Plan final live dispatch enablement apply requirements.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    final_plan = chain["live_dispatch_final_enablement_plan"]

    apply_plan = live_dispatch_final_enablement_apply_plan_midnight_oil(
        MidnightOilLiveDispatchFinalEnablementApplyPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
            control_ledger_persistence_apply_plan_receipt=chain[
                "control_ledger_persistence_apply_plan"
            ],
            operator_dispatch_activation_readiness_plan_receipt=chain[
                "operator_dispatch_activation_readiness_plan"
            ],
            live_dispatch_final_enablement_plan_receipt=final_plan,
        )
    )

    assert apply_plan.receipt_id == (
        f"{preflight.run_id}-live-dispatch-final-enablement-apply-plan"
    )
    assert apply_plan.live_dispatch_final_enablement_plan_receipt_id == final_plan.receipt_id
    assert apply_plan.status == (
        "blocked_live_dispatch_final_enablement_apply_unimplemented"
    )
    assert apply_plan.adapter_key == "live_dispatch_final_enablement_apply"
    assert apply_plan.planned_live_dispatch_receipt_id == (
        final_plan.planned_live_dispatch_receipt_id
    )
    assert apply_plan.planned_runner_dispatch_id == final_plan.planned_runner_dispatch_id
    assert apply_plan.planned_apply_receipt_id == (
        f"{preflight.run_id}-live-dispatch-final-enable-apply-receipt"
    )
    assert apply_plan.planned_idempotency_key == (
        f"{preflight.run_id}-live-dispatch-final-enable-idempotency-key"
    )
    assert apply_plan.planned_repository_id == (
        chain["control_ledger_persistence_apply_plan"].planned_repository_id
    )
    assert apply_plan.planned_transaction_id == (
        f"{preflight.run_id}-live-dispatch-final-enable-transaction"
    )
    assert "dispatch idempotency repository" in apply_plan.apply_blockers
    assert "idempotency_key" in apply_plan.required_apply_receipt_fields
    assert "apply planner must require an activation-ready receipt" in (
        apply_plan.required_apply_invariants[0]
    )
    assert apply_plan.blocker_reason == (
        "live_dispatch_final_enablement_apply_unimplemented"
    )
    assert apply_plan.final_enablement_apply_allowed is False
    assert apply_plan.final_enablement_allowed is False
    assert apply_plan.live_dispatch_enabled is False
    assert apply_plan.live_dispatch_ready is False
    assert apply_plan.activation_readiness_allowed is False
    assert apply_plan.activation_ready is False
    assert apply_plan.transaction_opened is False
    assert apply_plan.transaction_committed is False
    assert apply_plan.setting_persisted is False
    assert apply_plan.control_ledger_written is False
    assert apply_plan.audit_log_written is False
    assert apply_plan.rollback_receipt_created is False
    assert apply_plan.operator_dispatch_allowed is False
    assert apply_plan.operator_live_dispatch_enabled is False
    assert apply_plan.live_run_allowed is False
    assert apply_plan.dispatch_allowed is False
    assert apply_plan.dispatch_performed is False
    assert apply_plan.budget_reservation_allowed is False
    assert apply_plan.budget_reserved is False
    assert apply_plan.provider_execution_allowed is False
    assert apply_plan.provider_calls_made is False
    assert apply_plan.retrieval_allowed is False
    assert apply_plan.retrieval_performed is False
    assert apply_plan.source_receipts_created is False
    assert apply_plan.graph_mutation_allowed is False
    assert apply_plan.graph_mutated is False
    assert apply_plan.final_artifact_allowed is False
    assert apply_plan.final_artifact_created is False
    assert "no transaction is opened" in apply_plan.adapter_plan_notes[0]


def test_live_dispatch_final_enablement_apply_plan_rejects_ready_final_plan() -> None:
    chain = _accepted_midnight_oil_live_dispatch_final_enablement_plan_chain(
        goal="Reject ready final enablement receipts before apply planning.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    bad_final_plan = chain["live_dispatch_final_enablement_plan"].model_copy(
        update={"live_dispatch_ready": True}
    )

    with pytest.raises(
        ValidationError,
        match="live_dispatch_final_enablement_plan_receipt must not enable live dispatch",
    ):
        MidnightOilLiveDispatchFinalEnablementApplyPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
            control_ledger_persistence_apply_plan_receipt=chain[
                "control_ledger_persistence_apply_plan"
            ],
            operator_dispatch_activation_readiness_plan_receipt=chain[
                "operator_dispatch_activation_readiness_plan"
            ],
            live_dispatch_final_enablement_plan_receipt=bad_final_plan,
        )


def test_midnight_oil_live_dispatch_final_enablement_apply_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_live_dispatch_final_enablement_plan_chain(
        goal="Expose live dispatch final enablement apply planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    final_plan = chain["live_dispatch_final_enablement_plan"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/live-dispatch-final-enablement-apply-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_adapter_plan_receipt": chain[
                    "operator_adapter_plan"
                ].model_dump(mode="json"),
                "control_ledger_adapter_plan_receipt": chain[
                    "control_ledger_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_plan_receipt": chain[
                    "control_ledger_persistence_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_apply_plan_receipt": chain[
                    "control_ledger_persistence_apply_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_activation_readiness_plan_receipt": chain[
                    "operator_dispatch_activation_readiness_plan"
                ].model_dump(mode="json"),
                "live_dispatch_final_enablement_plan_receipt": final_plan.model_dump(
                    mode="json"
                ),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == (
        f"{preflight.run_id}-live-dispatch-final-enablement-apply-plan"
    )
    assert body["live_dispatch_final_enablement_plan_receipt_id"] == final_plan.receipt_id
    assert body["status"] == "blocked_live_dispatch_final_enablement_apply_unimplemented"
    assert body["adapter_key"] == "live_dispatch_final_enablement_apply"
    assert body["planned_live_dispatch_receipt_id"] == (
        final_plan.planned_live_dispatch_receipt_id
    )
    assert body["planned_runner_dispatch_id"] == final_plan.planned_runner_dispatch_id
    assert body["planned_apply_receipt_id"] == (
        f"{preflight.run_id}-live-dispatch-final-enable-apply-receipt"
    )
    assert body["planned_idempotency_key"] == (
        f"{preflight.run_id}-live-dispatch-final-enable-idempotency-key"
    )
    assert "dispatch idempotency repository" in body["apply_blockers"]
    assert "idempotency_key" in body["required_apply_receipt_fields"]
    assert body["blocker_reason"] == (
        "live_dispatch_final_enablement_apply_unimplemented"
    )
    assert body["final_enablement_apply_allowed"] is False
    assert body["final_enablement_allowed"] is False
    assert body["live_dispatch_enabled"] is False
    assert body["live_dispatch_ready"] is False
    assert body["activation_ready"] is False
    assert body["transaction_opened"] is False
    assert body["transaction_committed"] is False
    assert body["setting_persisted"] is False
    assert body["control_ledger_written"] is False
    assert body["audit_log_written"] is False
    assert body["rollback_receipt_created"] is False
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_live_dispatch_final_enablement_plan_records_disabled_requirements() -> None:
    chain = _accepted_midnight_oil_operator_dispatch_activation_readiness_plan_chain(
        goal="Plan final live dispatch enablement after activation readiness planning.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    readiness_plan = chain["operator_dispatch_activation_readiness_plan"]

    final_plan = live_dispatch_final_enablement_plan_midnight_oil(
        MidnightOilLiveDispatchFinalEnablementPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
            control_ledger_persistence_apply_plan_receipt=chain[
                "control_ledger_persistence_apply_plan"
            ],
            operator_dispatch_activation_readiness_plan_receipt=readiness_plan,
        )
    )

    assert final_plan.receipt_id == f"{preflight.run_id}-live-dispatch-final-enablement-plan"
    assert final_plan.operator_dispatch_activation_readiness_plan_receipt_id == (
        readiness_plan.receipt_id
    )
    assert final_plan.status == "blocked_live_dispatch_final_enablement_unimplemented"
    assert final_plan.adapter_key == "live_dispatch_final_enablement"
    assert final_plan.planned_activation_readiness_receipt_id == (
        readiness_plan.planned_activation_readiness_receipt_id
    )
    assert final_plan.planned_dispatch_enablement_id == (
        readiness_plan.planned_dispatch_enablement_id
    )
    assert final_plan.planned_live_dispatch_receipt_id == (
        f"{preflight.run_id}-live-dispatch-final-enable-receipt"
    )
    assert final_plan.planned_runner_dispatch_id == (
        f"{preflight.run_id}-midnight-oil-runner-dispatch"
    )
    assert "live dispatch final enablement implementation" in final_plan.readiness_blockers
    assert "live_dispatch_receipt_id" in final_plan.required_enablement_receipt_fields
    assert "runner_dispatch_id" in final_plan.required_enablement_receipt_fields
    assert "final enablement must require an activation readiness receipt" in (
        final_plan.required_enablement_invariants[0]
    )
    assert final_plan.blocker_reason == "live_dispatch_final_enablement_unimplemented"
    assert final_plan.final_enablement_allowed is False
    assert final_plan.live_dispatch_enabled is False
    assert final_plan.live_dispatch_ready is False
    assert final_plan.activation_readiness_allowed is False
    assert final_plan.activation_ready is False
    assert final_plan.transaction_opened is False
    assert final_plan.transaction_committed is False
    assert final_plan.setting_persisted is False
    assert final_plan.control_ledger_written is False
    assert final_plan.audit_log_written is False
    assert final_plan.rollback_receipt_created is False
    assert final_plan.operator_dispatch_allowed is False
    assert final_plan.operator_live_dispatch_enabled is False
    assert final_plan.live_run_allowed is False
    assert final_plan.dispatch_allowed is False
    assert final_plan.dispatch_performed is False
    assert final_plan.budget_reservation_allowed is False
    assert final_plan.budget_reserved is False
    assert final_plan.provider_execution_allowed is False
    assert final_plan.provider_calls_made is False
    assert final_plan.retrieval_allowed is False
    assert final_plan.retrieval_performed is False
    assert final_plan.source_receipts_created is False
    assert final_plan.graph_mutation_allowed is False
    assert final_plan.graph_mutated is False
    assert final_plan.final_artifact_allowed is False
    assert final_plan.final_artifact_created is False
    assert "no enablement is granted" in final_plan.adapter_plan_notes[0]


def test_live_dispatch_final_enablement_plan_rejects_ready_activation_receipt() -> None:
    chain = _accepted_midnight_oil_operator_dispatch_activation_readiness_plan_chain(
        goal="Reject activation-ready receipts before final live dispatch enablement planning.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    bad_readiness_plan = chain["operator_dispatch_activation_readiness_plan"].model_copy(
        update={"activation_ready": True}
    )

    with pytest.raises(
        ValidationError,
        match="operator_dispatch_activation_readiness_plan_receipt must not be activation ready",
    ):
        MidnightOilLiveDispatchFinalEnablementPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
            control_ledger_persistence_apply_plan_receipt=chain[
                "control_ledger_persistence_apply_plan"
            ],
            operator_dispatch_activation_readiness_plan_receipt=bad_readiness_plan,
        )


def test_midnight_oil_live_dispatch_final_enablement_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_operator_dispatch_activation_readiness_plan_chain(
        goal="Expose live dispatch final enablement planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    readiness_plan = chain["operator_dispatch_activation_readiness_plan"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/live-dispatch-final-enablement-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_adapter_plan_receipt": chain[
                    "operator_adapter_plan"
                ].model_dump(mode="json"),
                "control_ledger_adapter_plan_receipt": chain[
                    "control_ledger_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_plan_receipt": chain[
                    "control_ledger_persistence_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_apply_plan_receipt": chain[
                    "control_ledger_persistence_apply_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_activation_readiness_plan_receipt": (
                    readiness_plan.model_dump(mode="json")
                ),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-live-dispatch-final-enablement-plan"
    assert body["operator_dispatch_activation_readiness_plan_receipt_id"] == (
        readiness_plan.receipt_id
    )
    assert body["status"] == "blocked_live_dispatch_final_enablement_unimplemented"
    assert body["adapter_key"] == "live_dispatch_final_enablement"
    assert body["planned_activation_readiness_receipt_id"] == (
        readiness_plan.planned_activation_readiness_receipt_id
    )
    assert body["planned_dispatch_enablement_id"] == (
        readiness_plan.planned_dispatch_enablement_id
    )
    assert body["planned_live_dispatch_receipt_id"] == (
        f"{preflight.run_id}-live-dispatch-final-enable-receipt"
    )
    assert body["planned_runner_dispatch_id"] == (
        f"{preflight.run_id}-midnight-oil-runner-dispatch"
    )
    assert "live dispatch final enablement implementation" in body["readiness_blockers"]
    assert "live_dispatch_receipt_id" in body["required_enablement_receipt_fields"]
    assert body["blocker_reason"] == "live_dispatch_final_enablement_unimplemented"
    assert body["final_enablement_allowed"] is False
    assert body["live_dispatch_enabled"] is False
    assert body["live_dispatch_ready"] is False
    assert body["activation_readiness_allowed"] is False
    assert body["activation_ready"] is False
    assert body["transaction_opened"] is False
    assert body["transaction_committed"] is False
    assert body["setting_persisted"] is False
    assert body["control_ledger_written"] is False
    assert body["audit_log_written"] is False
    assert body["rollback_receipt_created"] is False
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_control_ledger_adapter_plan_records_disabled_persistence_requirements() -> None:
    chain = _accepted_midnight_oil_operator_adapter_plan_chain(
        goal="Plan durable operator control ledger controls for a midnight oil run.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    control_ledger_plan = control_ledger_adapter_plan_midnight_oil(
        MidnightOilControlLedgerAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
        )
    )

    assert control_ledger_plan.receipt_id == f"{preflight.run_id}-control-ledger-adapter-plan"
    assert control_ledger_plan.operator_dispatch_adapter_plan_receipt_id == (
        chain["operator_adapter_plan"].receipt_id
    )
    assert control_ledger_plan.status == "blocked_control_ledger_adapter_unimplemented"
    assert control_ledger_plan.adapter_key == "operator_dispatch_control_ledger"
    assert control_ledger_plan.planned_setting_id == (
        chain["operator_adapter_plan"].planned_setting_id
    )
    assert control_ledger_plan.planned_control_ledger_id == (
        chain["operator_adapter_plan"].planned_control_ledger_id
    )
    assert control_ledger_plan.planned_audit_log_id == (
        f"{preflight.run_id}-operator-dispatch-audit-log"
    )
    assert control_ledger_plan.planned_rollback_receipt_id == (
        f"{preflight.run_id}-operator-dispatch-rollback-receipt"
    )
    assert "persist exactly one enablement row" in control_ledger_plan.required_invariants[0]
    assert "control_ledger_id" in control_ledger_plan.required_control_ledger_fields
    assert "audit_log_id" in control_ledger_plan.required_control_ledger_fields
    assert "rollback_receipt_id" in control_ledger_plan.required_control_ledger_fields
    assert "rolled_back_at" in control_ledger_plan.required_rollback_receipt_fields
    assert control_ledger_plan.blocker_reason == "control_ledger_adapter_unimplemented"
    assert control_ledger_plan.control_ledger_persistence_allowed is False
    assert control_ledger_plan.control_ledger_written is False
    assert control_ledger_plan.audit_log_written is False
    assert control_ledger_plan.rollback_receipt_created is False
    assert control_ledger_plan.operator_dispatch_allowed is False
    assert control_ledger_plan.operator_live_dispatch_enabled is False
    assert control_ledger_plan.live_run_allowed is False
    assert control_ledger_plan.dispatch_allowed is False
    assert control_ledger_plan.dispatch_performed is False
    assert control_ledger_plan.budget_reservation_allowed is False
    assert control_ledger_plan.budget_reserved is False
    assert control_ledger_plan.provider_execution_allowed is False
    assert control_ledger_plan.provider_calls_made is False
    assert control_ledger_plan.retrieval_allowed is False
    assert control_ledger_plan.retrieval_performed is False
    assert control_ledger_plan.source_receipts_created is False
    assert control_ledger_plan.graph_mutation_allowed is False
    assert control_ledger_plan.graph_mutated is False
    assert control_ledger_plan.final_artifact_allowed is False
    assert control_ledger_plan.final_artifact_created is False
    assert "no operator setting or ledger row is persisted" in control_ledger_plan.adapter_plan_notes[0]


def test_control_ledger_adapter_plan_rejects_mismatched_operator_dispatch_receipt() -> None:
    chain = _accepted_midnight_oil_operator_adapter_plan_chain(
        goal="Reject mismatched operator dispatch receipt before control ledger planning.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    bad_operator_adapter = chain["operator_adapter_plan"].model_copy(
        update={"final_artifact_adapter_plan_receipt_id": "wrong-final-adapter-plan"}
    )

    with pytest.raises(
        ValidationError,
        match="operator_dispatch_adapter_plan_receipt must reference final_artifact_adapter_plan_receipt",
    ):
        MidnightOilControlLedgerAdapterPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=bad_operator_adapter,
        )


def test_midnight_oil_control_ledger_adapter_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_operator_adapter_plan_chain(
        goal="Expose control ledger adapter planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/control-ledger-adapter-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_adapter_plan_receipt": chain[
                    "operator_adapter_plan"
                ].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-control-ledger-adapter-plan"
    assert body["operator_dispatch_adapter_plan_receipt_id"] == (
        chain["operator_adapter_plan"].receipt_id
    )
    assert body["status"] == "blocked_control_ledger_adapter_unimplemented"
    assert body["adapter_key"] == "operator_dispatch_control_ledger"
    assert body["planned_setting_id"] == chain["operator_adapter_plan"].planned_setting_id
    assert body["planned_control_ledger_id"] == (
        chain["operator_adapter_plan"].planned_control_ledger_id
    )
    assert body["planned_audit_log_id"] == f"{preflight.run_id}-operator-dispatch-audit-log"
    assert body["planned_rollback_receipt_id"] == (
        f"{preflight.run_id}-operator-dispatch-rollback-receipt"
    )
    assert "enabled_by_operator_id" in body["required_control_ledger_fields"]
    assert "rollback_receipt_id" in body["required_control_ledger_fields"]
    assert "rolled_back_by_operator_id" in body["required_rollback_receipt_fields"]
    assert body["blocker_reason"] == "control_ledger_adapter_unimplemented"
    assert body["control_ledger_persistence_allowed"] is False
    assert body["control_ledger_written"] is False
    assert body["audit_log_written"] is False
    assert body["rollback_receipt_created"] is False
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_control_ledger_persistence_plan_records_disabled_repository_requirements() -> None:
    chain = _accepted_midnight_oil_control_ledger_plan_chain(
        goal="Plan persistence implementation for the midnight oil operator control ledger.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    persistence_plan = control_ledger_persistence_plan_midnight_oil(
        MidnightOilControlLedgerPersistencePlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
        )
    )

    assert persistence_plan.receipt_id == f"{preflight.run_id}-control-ledger-persistence-plan"
    assert persistence_plan.control_ledger_adapter_plan_receipt_id == (
        chain["control_ledger_plan"].receipt_id
    )
    assert persistence_plan.operator_dispatch_adapter_plan_receipt_id == (
        chain["operator_adapter_plan"].receipt_id
    )
    assert persistence_plan.status == "blocked_control_ledger_persistence_unimplemented"
    assert persistence_plan.adapter_key == "operator_dispatch_control_ledger_persistence"
    assert persistence_plan.planned_repository_id == (
        f"{preflight.run_id}-operator-dispatch-control-repository"
    )
    assert persistence_plan.planned_transaction_id == (
        f"{preflight.run_id}-operator-dispatch-control-transaction"
    )
    assert persistence_plan.planned_setting_id == chain["control_ledger_plan"].planned_setting_id
    assert persistence_plan.planned_control_ledger_id == (
        chain["control_ledger_plan"].planned_control_ledger_id
    )
    assert "operator_dispatch_settings" in persistence_plan.required_storage_tables
    assert "operator_dispatch_audit_log" in persistence_plan.required_storage_tables
    assert "write setting, ledger, audit, and rollback rows" in (
        persistence_plan.required_transaction_invariants[0]
    )
    assert "transaction_id" in persistence_plan.required_apply_fields
    assert "content_digest" in persistence_plan.required_apply_fields
    assert persistence_plan.blocker_reason == "control_ledger_persistence_unimplemented"
    assert persistence_plan.persistence_adapter_allowed is False
    assert persistence_plan.control_ledger_persistence_allowed is False
    assert persistence_plan.control_ledger_written is False
    assert persistence_plan.audit_log_written is False
    assert persistence_plan.rollback_receipt_created is False
    assert persistence_plan.operator_dispatch_allowed is False
    assert persistence_plan.operator_live_dispatch_enabled is False
    assert persistence_plan.live_run_allowed is False
    assert persistence_plan.dispatch_allowed is False
    assert persistence_plan.dispatch_performed is False
    assert persistence_plan.budget_reservation_allowed is False
    assert persistence_plan.budget_reserved is False
    assert persistence_plan.provider_execution_allowed is False
    assert persistence_plan.provider_calls_made is False
    assert persistence_plan.retrieval_allowed is False
    assert persistence_plan.retrieval_performed is False
    assert persistence_plan.source_receipts_created is False
    assert persistence_plan.graph_mutation_allowed is False
    assert persistence_plan.graph_mutated is False
    assert persistence_plan.final_artifact_allowed is False
    assert persistence_plan.final_artifact_created is False
    assert "no repository transaction is opened" in persistence_plan.adapter_plan_notes[0]


def test_control_ledger_persistence_plan_rejects_written_control_ledger_receipt() -> None:
    chain = _accepted_midnight_oil_control_ledger_plan_chain(
        goal="Reject already-written control ledger before persistence planning.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    bad_control_ledger = chain["control_ledger_plan"].model_copy(
        update={"control_ledger_written": True}
    )

    with pytest.raises(
        ValidationError,
        match="control_ledger_adapter_plan_receipt must not write ledger",
    ):
        MidnightOilControlLedgerPersistencePlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=bad_control_ledger,
        )


def test_midnight_oil_control_ledger_persistence_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_control_ledger_plan_chain(
        goal="Expose control ledger persistence planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/control-ledger-persistence-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_adapter_plan_receipt": chain[
                    "operator_adapter_plan"
                ].model_dump(mode="json"),
                "control_ledger_adapter_plan_receipt": chain[
                    "control_ledger_plan"
                ].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-control-ledger-persistence-plan"
    assert body["control_ledger_adapter_plan_receipt_id"] == (
        chain["control_ledger_plan"].receipt_id
    )
    assert body["status"] == "blocked_control_ledger_persistence_unimplemented"
    assert body["adapter_key"] == "operator_dispatch_control_ledger_persistence"
    assert body["planned_repository_id"] == (
        f"{preflight.run_id}-operator-dispatch-control-repository"
    )
    assert body["planned_transaction_id"] == (
        f"{preflight.run_id}-operator-dispatch-control-transaction"
    )
    assert "operator_dispatch_rollback_receipts" in body["required_storage_tables"]
    assert "idempotency_key" in body["required_apply_fields"]
    assert "content_digest" in body["required_apply_fields"]
    assert body["blocker_reason"] == "control_ledger_persistence_unimplemented"
    assert body["persistence_adapter_allowed"] is False
    assert body["control_ledger_persistence_allowed"] is False
    assert body["control_ledger_written"] is False
    assert body["audit_log_written"] is False
    assert body["rollback_receipt_created"] is False
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_control_ledger_persistence_apply_plan_records_disabled_commit_requirements() -> None:
    chain = _accepted_midnight_oil_control_ledger_persistence_plan_chain(
        goal="Plan the disabled commit receipt for the midnight oil operator control ledger.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    apply_plan = control_ledger_persistence_apply_plan_midnight_oil(
        MidnightOilControlLedgerPersistenceApplyPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
        )
    )

    assert apply_plan.receipt_id == f"{preflight.run_id}-control-ledger-persistence-apply-plan"
    assert apply_plan.control_ledger_persistence_plan_receipt_id == (
        chain["control_ledger_persistence_plan"].receipt_id
    )
    assert apply_plan.control_ledger_adapter_plan_receipt_id == (
        chain["control_ledger_plan"].receipt_id
    )
    assert apply_plan.status == "blocked_control_ledger_persistence_apply_unimplemented"
    assert apply_plan.adapter_key == "operator_dispatch_control_ledger_persistence_apply"
    assert apply_plan.planned_repository_id == (
        chain["control_ledger_persistence_plan"].planned_repository_id
    )
    assert apply_plan.planned_transaction_id == (
        chain["control_ledger_persistence_plan"].planned_transaction_id
    )
    assert apply_plan.planned_commit_receipt_id == (
        f"{preflight.run_id}-operator-dispatch-control-commit-receipt"
    )
    assert apply_plan.planned_content_digest == (
        f"{preflight.run_id}-operator-dispatch-control-persistence-content-digest"
    )
    assert apply_plan.planned_setting_id == (
        chain["control_ledger_persistence_plan"].planned_setting_id
    )
    assert "commit receipt before operator live dispatch" in (
        apply_plan.required_commit_invariants[2]
    )
    assert "commit_receipt_id" in apply_plan.required_commit_receipt_fields
    assert "transaction_committed" in apply_plan.required_commit_receipt_fields
    assert apply_plan.blocker_reason == "control_ledger_persistence_apply_unimplemented"
    assert apply_plan.transaction_opened is False
    assert apply_plan.transaction_committed is False
    assert apply_plan.setting_persisted is False
    assert apply_plan.control_ledger_persistence_allowed is False
    assert apply_plan.control_ledger_written is False
    assert apply_plan.audit_log_written is False
    assert apply_plan.rollback_receipt_created is False
    assert apply_plan.operator_dispatch_allowed is False
    assert apply_plan.operator_live_dispatch_enabled is False
    assert apply_plan.live_run_allowed is False
    assert apply_plan.dispatch_allowed is False
    assert apply_plan.dispatch_performed is False
    assert apply_plan.budget_reservation_allowed is False
    assert apply_plan.budget_reserved is False
    assert apply_plan.provider_execution_allowed is False
    assert apply_plan.provider_calls_made is False
    assert apply_plan.retrieval_allowed is False
    assert apply_plan.retrieval_performed is False
    assert apply_plan.source_receipts_created is False
    assert apply_plan.graph_mutation_allowed is False
    assert apply_plan.graph_mutated is False
    assert apply_plan.final_artifact_allowed is False
    assert apply_plan.final_artifact_created is False
    assert "no repository transaction is opened or committed" in apply_plan.adapter_plan_notes[0]


def test_control_ledger_persistence_apply_plan_rejects_written_persistence_plan() -> None:
    chain = _accepted_midnight_oil_control_ledger_persistence_plan_chain(
        goal="Reject already-written ledger rows before persistence apply planning.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    bad_persistence_plan = chain["control_ledger_persistence_plan"].model_copy(
        update={"control_ledger_written": True}
    )

    with pytest.raises(
        ValidationError,
        match="control_ledger_persistence_plan_receipt must not write ledger",
    ):
        MidnightOilControlLedgerPersistenceApplyPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=bad_persistence_plan,
        )


def test_midnight_oil_control_ledger_persistence_apply_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_control_ledger_persistence_plan_chain(
        goal="Expose control ledger persistence apply planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/control-ledger-persistence-apply-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_adapter_plan_receipt": chain[
                    "operator_adapter_plan"
                ].model_dump(mode="json"),
                "control_ledger_adapter_plan_receipt": chain[
                    "control_ledger_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_plan_receipt": chain[
                    "control_ledger_persistence_plan"
                ].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == f"{preflight.run_id}-control-ledger-persistence-apply-plan"
    assert body["control_ledger_persistence_plan_receipt_id"] == (
        chain["control_ledger_persistence_plan"].receipt_id
    )
    assert body["status"] == "blocked_control_ledger_persistence_apply_unimplemented"
    assert body["adapter_key"] == "operator_dispatch_control_ledger_persistence_apply"
    assert body["planned_repository_id"] == (
        chain["control_ledger_persistence_plan"].planned_repository_id
    )
    assert body["planned_transaction_id"] == (
        chain["control_ledger_persistence_plan"].planned_transaction_id
    )
    assert body["planned_commit_receipt_id"] == (
        f"{preflight.run_id}-operator-dispatch-control-commit-receipt"
    )
    assert "commit_receipt_id" in body["required_commit_receipt_fields"]
    assert "transaction_committed" in body["required_commit_receipt_fields"]
    assert body["blocker_reason"] == "control_ledger_persistence_apply_unimplemented"
    assert body["transaction_opened"] is False
    assert body["transaction_committed"] is False
    assert body["setting_persisted"] is False
    assert body["control_ledger_persistence_allowed"] is False
    assert body["control_ledger_written"] is False
    assert body["audit_log_written"] is False
    assert body["rollback_receipt_created"] is False
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False


def test_operator_dispatch_activation_readiness_plan_records_disabled_requirements() -> None:
    chain = _accepted_midnight_oil_control_ledger_persistence_apply_plan_chain(
        goal="Plan operator dispatch activation readiness after persistence apply planning.",
        source_policy=["arxiv", "web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    readiness_plan = operator_dispatch_activation_readiness_plan_midnight_oil(
        MidnightOilOperatorDispatchActivationReadinessPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
            control_ledger_persistence_apply_plan_receipt=chain[
                "control_ledger_persistence_apply_plan"
            ],
        )
    )

    assert readiness_plan.receipt_id == (
        f"{preflight.run_id}-operator-dispatch-activation-readiness-plan"
    )
    assert readiness_plan.control_ledger_persistence_apply_plan_receipt_id == (
        chain["control_ledger_persistence_apply_plan"].receipt_id
    )
    assert readiness_plan.status == (
        "blocked_operator_dispatch_activation_readiness_unimplemented"
    )
    assert readiness_plan.adapter_key == "operator_dispatch_activation_readiness"
    assert readiness_plan.planned_commit_receipt_id == (
        chain["control_ledger_persistence_apply_plan"].planned_commit_receipt_id
    )
    assert readiness_plan.planned_activation_readiness_receipt_id == (
        f"{preflight.run_id}-operator-dispatch-activation-readiness-receipt"
    )
    assert readiness_plan.planned_dispatch_enablement_id == (
        f"{preflight.run_id}-operator-dispatch-live-enable-activation"
    )
    assert readiness_plan.planned_repository_id == (
        chain["control_ledger_persistence_apply_plan"].planned_repository_id
    )
    assert readiness_plan.planned_transaction_id == (
        chain["control_ledger_persistence_apply_plan"].planned_transaction_id
    )
    assert "committed control ledger persistence receipt" in readiness_plan.readiness_blockers
    assert "activation_readiness_receipt_id" in (
        readiness_plan.required_activation_receipt_fields
    )
    assert "activation readiness must require a committed control ledger" in (
        readiness_plan.required_activation_invariants[0]
    )
    assert readiness_plan.blocker_reason == (
        "operator_dispatch_activation_readiness_unimplemented"
    )
    assert readiness_plan.activation_readiness_allowed is False
    assert readiness_plan.activation_ready is False
    assert readiness_plan.transaction_opened is False
    assert readiness_plan.transaction_committed is False
    assert readiness_plan.setting_persisted is False
    assert readiness_plan.control_ledger_written is False
    assert readiness_plan.audit_log_written is False
    assert readiness_plan.rollback_receipt_created is False
    assert readiness_plan.operator_dispatch_allowed is False
    assert readiness_plan.operator_live_dispatch_enabled is False
    assert readiness_plan.live_run_allowed is False
    assert readiness_plan.dispatch_allowed is False
    assert readiness_plan.dispatch_performed is False
    assert readiness_plan.budget_reservation_allowed is False
    assert readiness_plan.budget_reserved is False
    assert readiness_plan.provider_execution_allowed is False
    assert readiness_plan.provider_calls_made is False
    assert readiness_plan.retrieval_allowed is False
    assert readiness_plan.retrieval_performed is False
    assert readiness_plan.source_receipts_created is False
    assert readiness_plan.graph_mutation_allowed is False
    assert readiness_plan.graph_mutated is False
    assert readiness_plan.final_artifact_allowed is False
    assert readiness_plan.final_artifact_created is False
    assert "no live dispatch readiness is granted" in readiness_plan.adapter_plan_notes[0]


def test_operator_dispatch_activation_readiness_plan_rejects_committed_apply_plan() -> None:
    chain = _accepted_midnight_oil_control_ledger_persistence_apply_plan_chain(
        goal="Reject committed persistence apply plans before activation readiness planning.",
        source_policy=["web"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]
    bad_apply_plan = chain["control_ledger_persistence_apply_plan"].model_copy(
        update={"transaction_committed": True}
    )

    with pytest.raises(
        ValidationError,
        match="control_ledger_persistence_apply_plan_receipt must not commit transaction",
    ):
        MidnightOilOperatorDispatchActivationReadinessPlanRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            runner_control_plan_receipt=chain["control_plan"],
            budget_provider_adapter_plan_receipt=chain["budget_adapter_plan"],
            provider_executor_adapter_plan_receipt=chain["provider_adapter_plan"],
            retrieval_adapter_plan_receipt=chain["retrieval_adapter_plan"],
            graph_adapter_plan_receipt=chain["graph_adapter_plan"],
            final_artifact_adapter_plan_receipt=chain["final_artifact_adapter_plan"],
            operator_dispatch_adapter_plan_receipt=chain["operator_adapter_plan"],
            control_ledger_adapter_plan_receipt=chain["control_ledger_plan"],
            control_ledger_persistence_plan_receipt=chain["control_ledger_persistence_plan"],
            control_ledger_persistence_apply_plan_receipt=bad_apply_plan,
        )


def test_midnight_oil_operator_dispatch_activation_readiness_plan_api_contract() -> None:
    from interfaces.research.api.app import create_app

    chain = _accepted_midnight_oil_control_ledger_persistence_apply_plan_chain(
        goal="Expose operator dispatch activation readiness planning over the API.",
        source_policy=["arxiv", "substack"],
        requested_control_scope=[
            "budget_reservation_provider",
            "model_provider_route_executor",
            "retrieval_executor_source_receipts",
            "graph_mutation_writer",
            "final_html_artifact_writer",
            "operator_live_dispatch_enablement",
        ],
    )
    preflight = chain["preflight"]

    with TestClient(create_app()) as client:
        r = client.post(
            "/research/midnight-oil/operator-dispatch-activation-readiness-plan",
            json={
                "launch_packet": preflight.launch_packet.model_dump(mode="json"),
                "approval_receipt": preflight.approval_receipt.model_dump(mode="json"),
                "runner_handoff": preflight.runner_handoff.model_dump(mode="json"),
                "runner_control_plan_receipt": chain["control_plan"].model_dump(mode="json"),
                "budget_provider_adapter_plan_receipt": chain[
                    "budget_adapter_plan"
                ].model_dump(mode="json"),
                "provider_executor_adapter_plan_receipt": chain[
                    "provider_adapter_plan"
                ].model_dump(mode="json"),
                "retrieval_adapter_plan_receipt": chain[
                    "retrieval_adapter_plan"
                ].model_dump(mode="json"),
                "graph_adapter_plan_receipt": chain["graph_adapter_plan"].model_dump(
                    mode="json"
                ),
                "final_artifact_adapter_plan_receipt": chain[
                    "final_artifact_adapter_plan"
                ].model_dump(mode="json"),
                "operator_dispatch_adapter_plan_receipt": chain[
                    "operator_adapter_plan"
                ].model_dump(mode="json"),
                "control_ledger_adapter_plan_receipt": chain[
                    "control_ledger_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_plan_receipt": chain[
                    "control_ledger_persistence_plan"
                ].model_dump(mode="json"),
                "control_ledger_persistence_apply_plan_receipt": chain[
                    "control_ledger_persistence_apply_plan"
                ].model_dump(mode="json"),
            },
        )

    assert r.status_code == 200
    body = r.json()
    assert body["receipt_id"] == (
        f"{preflight.run_id}-operator-dispatch-activation-readiness-plan"
    )
    assert body["control_ledger_persistence_apply_plan_receipt_id"] == (
        chain["control_ledger_persistence_apply_plan"].receipt_id
    )
    assert body["status"] == "blocked_operator_dispatch_activation_readiness_unimplemented"
    assert body["adapter_key"] == "operator_dispatch_activation_readiness"
    assert body["planned_commit_receipt_id"] == (
        chain["control_ledger_persistence_apply_plan"].planned_commit_receipt_id
    )
    assert body["planned_activation_readiness_receipt_id"] == (
        f"{preflight.run_id}-operator-dispatch-activation-readiness-receipt"
    )
    assert "committed control ledger persistence receipt" in body["readiness_blockers"]
    assert "activation_readiness_receipt_id" in body["required_activation_receipt_fields"]
    assert body["blocker_reason"] == "operator_dispatch_activation_readiness_unimplemented"
    assert body["activation_readiness_allowed"] is False
    assert body["activation_ready"] is False
    assert body["transaction_opened"] is False
    assert body["transaction_committed"] is False
    assert body["setting_persisted"] is False
    assert body["control_ledger_written"] is False
    assert body["audit_log_written"] is False
    assert body["rollback_receipt_created"] is False
    assert body["operator_dispatch_allowed"] is False
    assert body["operator_live_dispatch_enabled"] is False
    assert body["live_run_allowed"] is False
    assert body["dispatch_allowed"] is False
    assert body["dispatch_performed"] is False
    assert body["budget_reserved"] is False
    assert body["provider_calls_made"] is False
    assert body["retrieval_performed"] is False
    assert body["source_receipts_created"] is False
    assert body["graph_mutated"] is False
    assert body["final_artifact_created"] is False
