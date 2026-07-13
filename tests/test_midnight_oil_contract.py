"""Midnight-oil routing preflight contract tests."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from substrate.midnight_oil import (
    MidnightOilRequest,
    ResearchAcceptancePolicy,
    canonical_research_claim_id,
    canonical_source_receipt_id,
    normalize_research_paragraphs,
    preflight_midnight_oil,
    research_acceptance_policy_authority_fields,
    research_acceptance_policy_from_authority,
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


def test_acceptance_policy_survives_the_entire_preflight_chain() -> None:
    policy = ResearchAcceptancePolicy()
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Trace claims to canonical evidence.",
            work_minutes=60,
            price_ceiling_usd=5.0,
            source_policy=["operator_corpus"],
            acceptance_policy=policy,
            operator_acknowledged_spend=True,
        )
    )

    assert result.acceptance_policy == policy
    assert result.launch_packet is not None
    assert result.approval_receipt is not None
    assert result.runner_handoff is not None
    assert result.applied_run_receipt is not None
    assert result.launch_packet.acceptance_policy == policy
    assert result.approval_receipt.approved_acceptance_policy == policy
    assert result.runner_handoff.acceptance_policy == policy
    assert result.applied_run_receipt.acceptance_policy == policy

    policy_bearers = (
        MidnightOilRequest(
            goal="Trace claims to canonical evidence.",
            work_minutes=60,
            price_ceiling_usd=5.0,
            source_policy=["operator_corpus"],
            acceptance_policy=policy,
            operator_acknowledged_spend=True,
        ),
        result,
        result.launch_packet,
        result.approval_receipt,
        result.runner_handoff,
        result.applied_run_receipt,
    )
    for contract in policy_bearers:
        assert contract is not None
        round_tripped = type(contract).model_validate(contract.model_dump(mode="json"))
        assert round_tripped == contract


def test_unknown_acceptance_policy_version_fails_closed() -> None:
    with pytest.raises(ValidationError):
        MidnightOilRequest.model_validate(
            {
                "goal": "Reject unknown policy semantics.",
                "work_minutes": 60,
                "price_ceiling_usd": 5.0,
                "source_policy": ["operator_corpus"],
                "acceptance_policy": {"policy_version": 2},
            }
        )


def test_complete_policy_authority_round_trips_and_partial_authority_refuses() -> None:
    policy = ResearchAcceptancePolicy()
    authority = research_acceptance_policy_authority_fields(policy)

    assert research_acceptance_policy_from_authority(authority) == policy
    assert research_acceptance_policy_from_authority({}) is None
    authority.pop("acceptance_policy_legacy_rows")
    with pytest.raises(ValueError, match="incomplete"):
        research_acceptance_policy_from_authority(authority)


def test_paragraph_normalization_is_platform_stable() -> None:
    assert normalize_research_paragraphs("  first\r\n\r\n second\n \n\nthird  ") == (
        "first",
        "second",
        "third",
    )
    assert normalize_research_paragraphs(" \r\n ") == ()


def test_claim_identity_is_domain_separated_and_delimiter_safe() -> None:
    base = canonical_research_claim_id(
        job_id="job|a",
        step_key="step",
        claim_class="insight",
        ordinal=0,
        normalized_text="claim",
    )
    shifted = canonical_research_claim_id(
        job_id="job",
        step_key="a|step",
        claim_class="insight",
        ordinal=0,
        normalized_text="claim",
    )
    assert base != shifted
    assert len(base) == 64


def _independent_identity_digest(domain: str, fields: dict[str, object]) -> str:
    canonical = json.dumps(
        {"domain": domain, "schema_version": 1, **fields},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def test_claim_identity_matches_independent_canonical_unicode_vector() -> None:
    fields: dict[str, object] = {
        "job_id": "عمل|job",
        "step_key": "step:α",
        "claim_class": "output_paragraph",
        "ordinal": 7,
        "normalized_text": "Evidence | الدليل | café",
    }
    actual = canonical_research_claim_id(**fields)  # type: ignore[arg-type]
    expected = _independent_identity_digest("antiek.midnight_oil.claim", fields)
    wrong_domain = _independent_identity_digest(
        "antiek.midnight_oil.source_receipt", fields
    )

    assert actual == expected
    assert actual != wrong_domain


def test_source_receipt_identity_uses_only_authoritative_fields() -> None:
    fields = {
        "document_id": "document-1",
        "chunk_id": "chunk-1",
        "hash_scope": "retrieval_excerpt",
        "content_hash": "a" * 64,
        "canonical_url": "antiek://document/document-1#chunk=chunk-1",
    }
    actual = canonical_source_receipt_id(**fields)
    reordered = canonical_source_receipt_id(**dict(reversed(tuple(fields.items()))))
    expected = _independent_identity_digest(
        "antiek.midnight_oil.source_receipt", fields
    )
    with_display_metadata = _independent_identity_digest(
        "antiek.midnight_oil.source_receipt",
        {**fields, "title": "Display-only title"},
    )
    wrong_domain = _independent_identity_digest("antiek.midnight_oil.claim", fields)

    assert actual == reordered == expected
    assert actual != with_display_metadata
    assert actual != wrong_domain
