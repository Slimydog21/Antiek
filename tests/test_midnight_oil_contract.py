"""Midnight-oil routing preflight contract tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from substrate.midnight_oil import (
    MidnightOilDispatchRequest,
    MidnightOilDryRunRequest,
    MidnightOilRequest,
    dispatch_midnight_oil,
    dry_run_midnight_oil,
    preflight_midnight_oil,
)


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
