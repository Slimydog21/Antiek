"""Settings SPR-01 — model inventory, budget honesty, prompt projection."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import (
    PromptCostEstimateRequest,
    estimate_prompt_cost,
    read_operator_budget,
)
from orchestration.continuous.budget import DaemonBudget


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Isolate daemon budget sidecar under tmp.
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.delenv("ANTIEK_OPERATOR_BUDGET_USD", raising=False)
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    monkeypatch.delenv("ANTIEK_BENCH_REPORT_PATH", raising=False)
    from interfaces.research.api.app import create_app

    app = create_app()
    # Simulate a registered provider set without full provider bootstrap.
    app.state.registered_providers = {"zai", "deepseek"}
    with TestClient(app) as c:
        yield c


def test_models_lists_registered_and_configured(client: TestClient) -> None:
    r = client.get("/settings/models")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 2
    ids = {m["provider_id"] for m in body["models"]}
    assert "zai" in ids
    assert "deepseek" in ids
    zai = next(m for m in body["models"] if m["provider_id"] == "zai")
    assert zai["ready"] is True
    assert isinstance(zai["tier_bindings"], list)


def test_budget_default_cap_with_missing_sidecar_keeps_spend_unknown(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    r = client.get("/settings/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["daily_cap_usd"] == 5.0
    assert body["spent_status"] == "unknown"
    assert body["spent_usd"] is None
    assert body["remaining_usd"] is None
    assert any("sidecar missing" in note for note in body["notes"])


def test_budget_default_cap_with_known_spend_sidecar(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    DaemonBudget(daily_cap_usd=5.0).reserve(1.25)
    r = client.get("/settings/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["daily_cap_usd"] == 5.0
    assert body["spent_status"] == "known"
    assert body["spent_usd"] == 1.25
    assert body["remaining_usd"] == 3.75
    # Honesty: same number is labeled reserved estimate, not settled cost.
    assert body["reserved_estimated_usd"] == 1.25
    assert body["spend_basis"] == "reserved_estimate"
    assert body["over_budget"] is False
    assert any("reserved" in n.lower() for n in body["notes"])


def test_budget_operator_env_cap(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "12.5")
    r = client.get("/settings/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["daily_cap_usd"] == 12.5
    assert body["cap_env"] == "ANTIEK_OPERATOR_BUDGET_USD"
    # Operator display cap differs from daemon default enforcement ($5).
    assert body["enforcement_cap_usd"] == 5.0
    assert body["caps_aligned"] is False
    assert any("differs from enforcement" in n for n in body["notes"])


def test_budget_operator_cap_differs_from_daemon_cap_stays_consistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Regression (#704 + #715 residual): spent + remaining share Settings baseline.

    Sidecar: daemon cap $5, reserved $4. Operator Settings cap $200.
    Pre-fix bug: remaining came from remaining_today() ($1) and spent was
    re-based as $200 - $1 = $199 (bar shows ~100% used). Fix: reserved=$4,
    remaining=$196 on the Settings cap.
    """
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    DaemonBudget(daily_cap_usd=5.0).reserve(2.0)
    DaemonBudget(daily_cap_usd=5.0).reserve(2.0)
    monkeypatch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "200")

    budget = read_operator_budget()

    assert budget.daily_cap_usd == 200.0
    assert budget.spent_status == "known"
    assert budget.spent_usd == 4.0
    assert budget.reserved_estimated_usd == 4.0
    assert budget.remaining_usd == 196.0
    assert budget.spend_basis == "reserved_estimate"
    assert budget.enforcement_cap_usd == 5.0
    assert budget.caps_aligned is False
    assert budget.over_budget is False
    # Pre-fix failure mode must not reappear.
    assert budget.spent_usd != 199.0
    assert budget.remaining_usd != 1.0


def test_budget_signed_remaining_exposes_overrun_magnitude(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When reserved exceeds the display cap, remaining is negative (not clamped)."""
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    # Reserve $4 against daemon $5, then tighten Settings to $2.
    DaemonBudget(daily_cap_usd=5.0).reserve(2.0)
    DaemonBudget(daily_cap_usd=5.0).reserve(2.0)
    monkeypatch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "2")

    budget = read_operator_budget()

    assert budget.reserved_estimated_usd == 4.0
    assert budget.remaining_usd == -2.0  # signed, not max(0, ...)
    assert budget.over_budget is True
    assert any("over display budget" in n for n in budget.notes)


def test_budget_sidecar_read_does_not_require_budget_py_mutation() -> None:
    """§7.4 tripwire: this residual must not edit orchestration/continuous/budget.py."""
    budget_mod = Path("orchestration/continuous/budget.py").read_text(encoding="utf-8")
    # Guard: residual must not add spent_today() (the #715 placement that tripped CI).
    assert "def spent_today" not in budget_mod


def test_prompt_cost_estimate_pricing_placeholder_is_null(client: TestClient) -> None:
    # Current dispatch config uses 0.0 placeholder rates — must NOT invent $.
    r = client.post(
        "/settings/prompt-cost-estimate",
        json={
            "tier": "pro",
            "input_chars": 4000,
            "expected_output_tokens": 500,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pricing_known"] is False
    assert body["estimated_usd_low"] is None
    assert body["estimated_usd_high"] is None
    assert any("placeholder" in n.lower() or "0.0" in n for n in body["notes"])


def test_model_decision_uses_server_inventory_and_honest_static_basis(
    client: TestClient,
) -> None:
    response = client.post(
        "/settings/model-decision",
        json={"task": "deep_research", "input_chars": 4000, "expected_output_tokens": 500},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authority"] == "advisory"
    assert body["recommended_tier"] is None
    assert body["benchmark_status"] == "unavailable"
    assert body["candidates"]
    assert all(row["eligible"] is False for row in body["candidates"])
    assert all(row["quality_basis"] == "static_prior" for row in body["candidates"])
    assert all(row["estimated_usd_high"] is None for row in body["candidates"])


def test_model_decision_prefers_valid_server_owned_benchmark(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "bench.json"
    generated_at = datetime.now(UTC).isoformat()
    report.write_text(
        json.dumps(
            {
                "schema_version": "antiek.model-bench.v1",
                "generated_at": generated_at,
                "measurements": [
                    {
                        "task": "writing",
                        "tier": "flash",
                        "provider": "zai",
                        "model": "glm-5.2",
                        "score": 1.0,
                        "samples": 40,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    response = client.post("/settings/model-decision", json={"task": "writing"})
    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_status"] == "measured"
    assert datetime.fromisoformat(body["benchmark_generated_at"]) == datetime.fromisoformat(
        generated_at
    )
    assert body["recommended_tier"] is None
    assert body["candidates"][0]["quality_basis"] == "measured"
    assert body["candidates"][0]["benchmark_samples"] == 40


def test_model_decision_uses_first_registered_fallback_route(
    client: TestClient,
) -> None:
    client.app.state.registered_providers = {"deepseek"}
    body = client.post("/settings/model-decision", json={"task": "general"}).json()
    assert body["recommended_tier"] is None
    candidate = next(row for row in body["candidates"] if row["tier"] == "pro")
    assert candidate["ready"] is True
    assert candidate["provider"] == "deepseek"
    assert candidate["model"] == "deepseek-v4-pro"
    assert candidate["estimated_usd_high"] is None
    assert candidate["eligible"] is False


def test_model_decision_prices_the_selected_fallback_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interfaces.research.api.settings_budget as sb

    fake: dict[str, Any] = {
        "tiers": {
            "pro": {
                "provider": "primary",
                "model": "primary-model",
                "pricing": {"input_per_mtok": 100.0, "output_per_mtok": 100.0},
                "fallback": {
                    "provider": "fallback",
                    "model": "fallback-model",
                    "pricing": {"input_per_mtok": 1.0, "output_per_mtok": 2.0},
                },
            }
        }
    }
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: fake)
    monkeypatch.setattr(
        sb,
        "read_operator_budget",
        lambda: sb.BudgetResponse(
            daily_cap_usd=5.0,
            spent_usd=1.0,
            remaining_usd=4.0,
            spent_status="known",
            cap_env=None,
            notes=[],
        ),
    )
    client.app.state.registered_providers = {"fallback"}
    body = client.post(
        "/settings/model-decision",
        json={"task": "general", "input_chars": 4000, "expected_output_tokens": 1000},
    ).json()
    candidate = body["candidates"][0]
    assert candidate["provider"] == "fallback"
    assert candidate["model"] == "fallback-model"
    assert candidate["estimated_usd_high"] == pytest.approx(0.0036)
    assert candidate["eligible"] is True
    assert body["recommended_tier"] == "pro"


def test_model_decision_bounds_cyclic_fallback_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interfaces.research.api.settings_budget as sb

    route: dict[str, Any] = {"provider": "missing", "model": "model"}
    route["fallback"] = route
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: {"tiers": {"pro": route}})
    client.app.state.registered_providers = {"other"}
    response = client.post("/settings/model-decision", json={"task": "general"})
    assert response.status_code == 200
    assert response.json()["candidates"][0]["ready"] is False


def test_model_decision_does_not_label_nonmatching_report_as_measured(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "bench-nonmatching.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "antiek.model-bench.v1",
                "generated_at": datetime.now(UTC).isoformat(),
                "measurements": [
                    {
                        "task": "writing",
                        "tier": "flash",
                        "provider": "zai",
                        "model": "retired-model",
                        "score": 0.99,
                        "samples": 40,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    body = client.post("/settings/model-decision", json={"task": "writing"}).json()
    assert body["benchmark_status"] == "unavailable"
    assert body["benchmark_generated_at"] is None
    assert all(row["quality_basis"] == "static_prior" for row in body["candidates"])
    assert any("no matching measurement" in note for note in body["notes"])


def test_model_decision_rejects_client_supplied_inventory(client: TestClient) -> None:
    response = client.post(
        "/settings/model-decision",
        json={
            "task": "general",
            "models": [{"provider": "attacker", "model": "free", "score": 1}],
        },
    )
    assert response.status_code == 422


def test_model_decision_rejects_duplicate_benchmark_routes(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurement = {
        "task": "general",
        "tier": "pro",
        "provider": "zai",
        "model": "glm-5.2",
        "score": 0.9,
        "samples": 10,
    }
    report = tmp_path / "bench-duplicates.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "antiek.model-bench.v1",
                "generated_at": datetime.now(UTC).isoformat(),
                "measurements": [measurement, measurement],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    body = client.post("/settings/model-decision", json={"task": "general"}).json()
    assert body["benchmark_status"] == "unavailable"
    assert any("failed validation" in note for note in body["notes"])


@pytest.mark.parametrize("age", [timedelta(days=9), timedelta(minutes=-6)])
def test_model_decision_ignores_stale_or_future_benchmark(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    age: timedelta,
) -> None:
    report = tmp_path / "bench-invalid-time.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "antiek.model-bench.v1",
                "generated_at": (datetime.now(UTC) - age).isoformat(),
                "measurements": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    body = client.post("/settings/model-decision", json={"task": "general"}).json()
    assert body["benchmark_status"] == "unavailable"
    assert any("stale" in note or "future-dated" in note for note in body["notes"])


def test_estimate_with_synthetic_pricing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Unit-level: inject a fake config path via monkeypatch of loader.
    import interfaces.research.api.settings_budget as sb

    fake: dict[str, Any] = {
        "tiers": {
            "pro": {
                "provider": "zai",
                "model": "glm-5.2",
                "pricing": {
                    "input_per_mtok": 1.0,
                    "output_per_mtok": 2.0,
                },
            }
        }
    }
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: fake)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    est = estimate_prompt_cost(
        PromptCostEstimateRequest(
            tier="pro",
            input_chars=4000,  # ~1000 tokens
            expected_output_tokens=1000,
        ),
        budget=read_operator_budget(),
    )
    assert est.pricing_known is True
    assert est.estimated_usd_low is not None
    assert est.estimated_usd_high is not None
    assert est.estimated_usd_high >= est.estimated_usd_low
    # 1000 in * $1/M + 1000 out * $2/M = 0.003 base
    assert est.estimated_usd_low < 0.01


def test_caddy_allowlist_includes_settings() -> None:
    caddy = Path("infrastructure/ansible/templates/Caddyfile.j2").read_text(
        encoding="utf-8"
    )
    assert "/settings*" in caddy
