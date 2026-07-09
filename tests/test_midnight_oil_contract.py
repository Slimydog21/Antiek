"""Midnight-oil routing preflight contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from substrate.midnight_oil import MidnightOilRequest, preflight_midnight_oil


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
    assert body["artifact_contract"]["final_format"] == "html"
    assert len(body["role_plans"]) == 4
