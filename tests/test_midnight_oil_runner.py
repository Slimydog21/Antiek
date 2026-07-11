from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from interfaces.research.api.app import create_app
from substrate.midnight_oil import (
    MidnightOilExecutionReceipt,
    MidnightOilExecutionRequest,
    MidnightOilRequest,
    execute_midnight_oil,
    preflight_midnight_oil,
)


def _accepted_preflight(*, goal: str = "Map the evidence for widebody engine bottlenecks."):
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal=goal,
            work_minutes=120,
            price_ceiling_usd=25.0,
            route_mode="auto_balanced",
            source_policy=["arxiv", "substack", "web"],
            operator_acknowledged_spend=True,
        )
    )
    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    return preflight


def _request(preflight) -> MidnightOilExecutionRequest:
    return MidnightOilExecutionRequest(
        launch_packet=preflight.launch_packet,
        approval_receipt=preflight.approval_receipt,
        runner_handoff=preflight.runner_handoff,
        applied_run_receipt=preflight.applied_run_receipt,
        role_plans=preflight.role_plans,
    )


def test_synthetic_execution_emits_canonical_zero_cost_receipts_and_html_twins() -> None:
    preflight = _accepted_preflight(goal="Compare <engine> evidence & counterclaims.")

    receipt = execute_midnight_oil(_request(preflight))

    assert receipt.status == "mock_completed"
    assert receipt.synthetic is True
    assert receipt.execution_mode == "synthetic"
    assert [output.role for output in receipt.role_outputs] == [
        "planner",
        "gatherer",
        "verifier",
        "synthesizer",
    ]
    assert len({output.route_receipt.route_receipt_id for output in receipt.role_outputs}) == 4
    for output in receipt.role_outputs:
        assert (
            output.route_receipt.route_receipt_id in preflight.launch_packet.role_route_receipt_ids
        )
        assert output.execution_mode == "synthetic_no_provider"
        assert output.route_receipt.selected.provider == "none"
        assert output.route_receipt.selected.model == "no-provider"
        assert output.route_receipt.selected.reason_code == "synthetic_no_provider"
        assert output.route_receipt.budget is not None
        assert output.route_receipt.budget.actual_cost_usd == 0.0
        assert output.source_receipt_ids == []
    assert 'data-antiek-asset="information"' in receipt.html_information_asset
    assert 'data-antiek-asset="twin-note"' in receipt.twin_note_html
    assert (
        "Compare &lt;engine&gt; evidence &amp; counterclaims." not in receipt.html_information_asset
    )
    assert receipt.goal_fingerprint in receipt.html_information_asset
    assert "No insights are asserted because retrieval did not run." in receipt.twin_note_html
    assert receipt.actual_cost_usd == 0.0
    assert receipt.dispatch_performed is False
    assert receipt.budget_reserved is False
    assert receipt.provider_calls_made is False
    assert receipt.retrieval_performed is False
    assert receipt.graph_mutated is False
    assert receipt.final_artifact_created is False
    assert receipt.persisted is False


def test_synthetic_execution_rejects_route_lineage_drift() -> None:
    preflight = _accepted_preflight()
    role_plans = list(preflight.role_plans)
    role_plans[0] = role_plans[0].model_copy(update={"planned_route_receipt_id": "wrong"})

    with pytest.raises(ValidationError, match="role_plans must match launch_packet route receipts"):
        MidnightOilExecutionRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            role_plans=role_plans,
        )


def test_synthetic_execution_rejects_unacknowledged_or_drifted_approval() -> None:
    preflight = _accepted_preflight()
    bad_approval = preflight.approval_receipt.model_copy(
        update={"operator_acknowledged_spend": False}
    )

    with pytest.raises(ValidationError, match="approval_receipt must acknowledge spend"):
        MidnightOilExecutionRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=bad_approval,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            role_plans=preflight.role_plans,
        )


def test_synthetic_execution_never_reflects_free_form_goal_text() -> None:
    preflight = _accepted_preflight(
        goal="Compare engine evidence with api_key=sk-test-secret and sk-ABCDEF123456."
    )

    receipt = execute_midnight_oil(_request(preflight))

    assert "sk-test-secret" not in receipt.html_information_asset
    assert "sk-ABCDEF123456" not in receipt.twin_note_html
    assert receipt.goal_fingerprint in receipt.html_information_asset


def test_synthetic_execution_api_contract() -> None:
    preflight = _accepted_preflight()

    with TestClient(create_app()) as client:
        response = client.post(
            "/research/midnight-oil/execute",
            json=_request(preflight).model_dump(mode="json"),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == preflight.run_id
    assert body["status"] == "mock_completed"
    assert [output["role"] for output in body["role_outputs"]] == [
        "planner",
        "gatherer",
        "verifier",
        "synthesizer",
    ]
    assert body["actual_cost_usd"] == 0.0
    assert body["provider_calls_made"] is False


def test_synthetic_receipt_rejects_claimed_side_effect() -> None:
    preflight = _accepted_preflight()
    valid = execute_midnight_oil(_request(preflight))

    with pytest.raises(ValidationError, match="cannot claim side effects"):
        MidnightOilExecutionReceipt.model_validate({**valid.model_dump(), "graph_mutated": True})

    with pytest.raises(ValidationError, match="cannot claim side effects"):
        MidnightOilExecutionReceipt.model_validate({**valid.model_dump(), "persisted": True})


def test_synthetic_execution_rejects_minute_conservation_drift() -> None:
    preflight = _accepted_preflight()
    role_plans = list(preflight.role_plans)
    role_plans[-1] = role_plans[-1].model_copy(
        update={"max_minutes": role_plans[-1].max_minutes + 1}
    )

    with pytest.raises(ValidationError, match="role plan minutes"):
        MidnightOilExecutionRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            role_plans=role_plans,
        )


def test_synthetic_execution_rejects_budget_conservation_drift() -> None:
    preflight = _accepted_preflight()
    role_plans = list(preflight.role_plans)
    role_plans[-1] = role_plans[-1].model_copy(
        update={"budget_usd": role_plans[-1].budget_usd + 0.01}
    )

    with pytest.raises(ValidationError, match="role plan budget"):
        MidnightOilExecutionRequest(
            launch_packet=preflight.launch_packet,
            approval_receipt=preflight.approval_receipt,
            runner_handoff=preflight.runner_handoff,
            applied_run_receipt=preflight.applied_run_receipt,
            role_plans=role_plans,
        )


def test_synthetic_receipt_rejects_nonzero_cost() -> None:
    preflight = _accepted_preflight()
    valid = execute_midnight_oil(_request(preflight))

    with pytest.raises(ValidationError, match="cannot claim side effects"):
        MidnightOilExecutionReceipt.model_validate(
            {**valid.model_dump(), "actual_cost_usd": 0.01}
        )
