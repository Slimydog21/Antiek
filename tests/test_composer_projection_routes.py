"""HTTP trust-boundary tests for the composer model projection route."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.composer_projection_routes import (
    read_composer_projection_budget,
    register_composer_projection_routes,
)
from interfaces.research.api.settings_budget import BudgetResponse
from runtime.research_runner.protocol import (
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)
from substrate.dispatch.advisory_decision import DecisionCandidate


def _budget(cap: float | None, spent: float | None) -> BudgetResponse:
    if spent is None:
        remaining = None
        status = "unknown"
    else:
        remaining = None if cap is None else max(0.0, cap - spent)
        status = "known"
    return BudgetResponse(
        daily_cap_usd=cap,
        spent_usd=spent,
        remaining_usd=remaining,
        spent_status=status,
        cap_env=None,
    )


def _request(*, choice: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "task": "deep_research",
        "bounded_usage": [
            {"unit": "input_token", "maximum": 1_000},
            {"unit": "output_token", "maximum": 500},
        ],
        "choice": choice,
    }


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.state.registered_providers = {
        "deepseek",
        "xiaomi",
        "zai",
        "zai_reasoning",
    }
    app.dependency_overrides[read_composer_projection_budget] = lambda: _budget(10.0, 1.0)
    register_composer_projection_routes(app)
    return TestClient(app)


def test_budget_read_from_request_scoped_dependency(client: TestClient) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: _budget(10.0, 3.0)
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["budget"] == {"daily_cap_usd": 10.0, "spent_usd": 3.0}
    assert body["remaining_usd"] == pytest.approx(7.0)


def test_unknown_spend_is_never_fabricated_as_zero(client: TestClient) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: _budget(10.0, None)
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["budget"]["spent_usd"] is None
    assert body["remaining_usd"] is None
    assert body["would_exceed_budget"] is None


def test_signed_budget_overrun_remains_valid_at_composer_boundary(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: BudgetResponse(
        daily_cap_usd=2.0,
        spent_usd=4.0,
        remaining_usd=-2.0,
        spent_status="known",
        cap_env="ANTIEK_OPERATOR_BUDGET_USD",
        reserved_estimated_usd=4.0,
        spend_basis="reserved_estimate",
        enforcement_cap_usd=5.0,
        caps_aligned=False,
        over_budget=True,
        over_budget_usd=2.0,
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["budget"] == {"daily_cap_usd": 2.0, "spent_usd": 4.0}
    assert body["remaining_usd"] == 0.0
    assert body["would_exceed_budget"] is None


def test_candidates_come_from_server_state_not_request_body(client: TestClient) -> None:
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["authority"] == "advisory_explanatory"
    assert body["ranked_candidates"]
    assert {(row["provider"], row["model"]) for row in body["ranked_candidates"]} <= {
        ("zai", "glm-5.2"),
        ("zai_reasoning", "glm-5.2"),
    }
    assert len({(row["provider"], row["model"]) for row in body["ranked_candidates"]}) == len(
        body["ranked_candidates"]
    )
    plan = body["fallback_plan"]
    assert plan["authority"] == "advisory_fallback_plan"
    assert plan["status"] == "blocked"
    assert plan["maximum_chain_exposure_cents"] is None
    assert plan["would_exceed_budget"] is None
    assert [
        (route["fallback_index"], route["provider"], route["model"])
        for route in plan["routes"]
    ] == [
        (0, "zai", "glm-5.2"),
        (1, "deepseek", "deepseek-v4-pro"),
        (2, "xiaomi", "mimo-v2.5-pro"),
    ]
    assert all(not route["hard_ceiling_eligible"] for route in plan["routes"])
    assert {
        route["execution_status"] for route in plan["routes"]
    } == {"blocked_selection_authority"}


def test_client_candidate_claims_are_rejected(client: TestClient) -> None:
    payload = _request()
    payload["candidates"] = [
        {
            "tier": "forged",
            "provider": "attacker",
            "model": "free-best-model",
            "ready": True,
            "estimated_usd_low": 0,
            "estimated_usd_high": 0,
            "benchmark_score": 1,
            "benchmark_samples": 1_000_000,
        }
    ]
    response = client.post("/settings/composer-projection/resolve", json=payload)
    assert response.status_code == 422


def test_raw_benchmark_is_ranked_once_after_route_deduplication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def candidates(*args: object, **kwargs: object) -> tuple[DecisionCandidate, ...]:
        shared = {
            "provider": "zai",
            "model": "glm-5.2",
            "ready": True,
            "estimated_usd_low": 0.1,
            "estimated_usd_high": 0.2,
            "would_exceed_budget": False,
            "benchmark_samples": 40,
        }
        return (
            DecisionCandidate(tier="flash", benchmark_score=0.31, **shared),
            DecisionCandidate(tier="pro", benchmark_score=0.83, **shared),
        )

    monkeypatch.setattr(
        "interfaces.research.api.composer_projection_routes.build_model_decision_candidates",
        candidates,
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 200
    assert response.json()["ranked_candidates"] == [
        {
            "rank": 1,
            "tier": "pro",
            "provider": "zai",
            "model": "glm-5.2",
            "quality_score": 0.83,
            "quality_basis": "measured",
            "eligible": True,
            "pricing_status": "known",
            "estimated_usd_low": 0.1,
            "estimated_usd_high": 0.2,
        }
    ]


def test_curated_default_has_no_fabricated_explicit_choice(client: TestClient) -> None:
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 200
    body = response.json()
    assert body["chosen_provider"] is None
    assert body["chosen_model"] is None
    assert body["chosen_projection"] is None
    assert any("curated default" in note for note in body["notes"])


def test_unknown_choice_is_a_value_free_client_error(client: TestClient) -> None:
    response = client.post(
        "/settings/composer-projection/resolve",
        json=_request(choice={"provider": "attacker", "model": "forged"}),
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "chosen model route is unavailable"}


@pytest.mark.parametrize(
    "bounded_usage",
    [
        [],
        [
            {"unit": "input_token", "maximum": 1},
            {"unit": "input_token", "maximum": 2},
        ],
        [{"unit": "gigawatt", "maximum": 1}],
        [{"unit": "input_token", "maximum": 2_500_001}],
        [{"unit": "output_token", "maximum": 1_000_001}],
        [{"unit": "call", "maximum": -1}],
        [{"unit": "call", "maximum": 10_000_001}],
        [{"unit": "call", "maximum": True}],
        [{"unit": "call", "maximum": "1"}],
        [{"unit": "call", "maximum": 0}],
    ],
)
def test_bounded_usage_schema_fails_closed(
    client: TestClient, bounded_usage: list[dict[str, object]]
) -> None:
    payload = _request()
    payload["bounded_usage"] = bounded_usage
    response = client.post("/settings/composer-projection/resolve", json=payload)
    assert response.status_code == 422


def test_extra_request_fields_are_rejected(client: TestClient) -> None:
    payload = _request()
    payload["rogue_field"] = "inject"
    response = client.post("/settings/composer-projection/resolve", json=payload)
    assert response.status_code == 422


def test_invalid_budget_object_is_a_value_free_service_error(client: TestClient) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: SimpleNamespace(
        daily_cap_usd=10.0,
        spent_usd=1.0,
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 503
    assert response.json() == {"detail": "composer model decision source is unavailable"}


def test_non_finite_budget_is_a_value_free_service_error(client: TestClient) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: (
        BudgetResponse.model_construct(
            daily_cap_usd=float("nan"),
            spent_usd=1.0,
            remaining_usd=float("nan"),
            spent_status="known",
            cap_env=None,
        )
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 503
    assert "nan" not in response.text.lower()


def test_non_finite_unknown_budget_is_also_rejected(client: TestClient) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: (
        BudgetResponse.model_construct(
            daily_cap_usd=float("inf"),
            spent_usd=None,
            remaining_usd=None,
            spent_status="unknown",
            cap_env=None,
        )
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 503
    assert "inf" not in response.text.lower()


def test_inconsistent_budget_snapshot_is_rejected(client: TestClient) -> None:
    client.app.dependency_overrides[read_composer_projection_budget] = lambda: BudgetResponse(
        daily_cap_usd=10.0,
        spent_usd=2.0,
        remaining_usd=9.0,
        spent_status="known",
        cap_env=None,
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 503


def test_server_decision_failure_does_not_leak_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise ValueError("secret-provider-key-and-rate")

    monkeypatch.setattr(
        "interfaces.research.api.composer_projection_routes.build_model_decision_candidates",
        fail,
    )
    response = client.post("/settings/composer-projection/resolve", json=_request())
    assert response.status_code == 503
    assert "secret-provider-key-and-rate" not in response.text


def test_projection_unavailability_fails_visibly_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(request: CostProjectionRequest) -> CostProjection:
        raise OSError("catalog temporarily unavailable")

    monkeypatch.setattr(
        "interfaces.research.api.composer_projection_routes.project_cascade_cost",
        unavailable,
    )
    response = client.post(
        "/settings/composer-projection/resolve",
        json=_request(choice={"provider": "zai", "model": "glm-5.2"}),
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "composer fallback plan could not be resolved"
    }
    assert "catalog temporarily unavailable" not in response.text


def test_unexpected_projector_fault_propagates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(request: CostProjectionRequest) -> CostProjection:
        raise RuntimeError("unexpected projector defect")

    monkeypatch.setattr(
        "interfaces.research.api.composer_projection_routes.project_cascade_cost",
        broken,
    )
    with pytest.raises(RuntimeError, match="unexpected projector defect"):
        client.post(
            "/settings/composer-projection/resolve",
            json=_request(choice={"provider": "zai", "model": "glm-5.2"}),
        )


def test_decimal_projection_is_serialized_exactly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tiny = Decimal("1e-1000")

    def project(request: CostProjectionRequest) -> CostProjection:
        return CostProjection(
            seam_id=request.seam_id,
            provider=request.provider,
            model=request.model,
            operation=request.operation,
            bounded_usage=request.bounded_usage,
            rates=(
                ProjectionRate(
                    unit=request.bounded_usage[0].unit,
                    usd_per_unit=tiny,
                ),
            ),
            rate_snapshot="exact-test-rate",
            currency="USD",
            maximum_cost_usd=tiny,
            reservation_cents=1,
            disposition=ProjectionDisposition.HOLD_ELIGIBLE,
        )

    monkeypatch.setattr(
        "interfaces.research.api.composer_projection_routes.project_cascade_cost",
        project,
    )
    payload = _request(choice={"provider": "zai", "model": "glm-5.2"})
    payload["bounded_usage"] = [{"unit": "input_token", "maximum": 1}]
    response = client.post("/settings/composer-projection/resolve", json=payload)
    assert response.status_code == 200
    chosen = response.json()["chosen_projection"]
    assert chosen["maximum_cost_usd"] == "1E-1000"
    assert chosen["reservation_cents"] == 1
