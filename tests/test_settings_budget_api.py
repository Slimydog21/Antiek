"""Settings SPR-01 — model inventory, budget honesty, prompt projection."""

from __future__ import annotations

from collections.abc import Iterator
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


def test_models_separates_boot_added_selected_and_cascade_authority(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from substrate.model_registration import (
        clear_decision_tree_selection,
        install_decision_tree_selection,
        register_operator_model,
    )

    clear_decision_tree_selection()
    try:
        monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-sentinel")
        monkeypatch.setenv("XIAOMI_API_KEY", "secret-xiaomi-sentinel")
        register_operator_model("local-choice", provider_id="xiaomi")
        install_decision_tree_selection(
            "local-choice", provider_id="xiaomi", ensure_registered=True
        )
        client.app.state.registered_providers = {"openai_chat", "xiaomi"}
        response = client.get("/settings/models")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert [row["research_tier"] for row in body["cascade_targets"]] == [
            "fast",
            "deep",
            "wrestle",
        ]
        assert [row["model_id"] for row in body["cascade_targets"]] == [
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
        ]
        added = next(
            row for row in body["operator_models"] if row["model_id"] == "local-choice"
        )
        assert added == {
            "model_id": "local-choice",
            "provider_id": "xiaomi",
            "state": "operator_added_unverified",
            "decision_tree_selected": True,
            "provider_adapter_boot_ready": True,
            "authority_scope": "process_global_operator_registry",
        }
        assert "secret-openai-sentinel" not in response.text
        assert "secret-xiaomi-sentinel" not in response.text
        assert "authorization" not in response.text.lower()
    finally:
        clear_decision_tree_selection()


def test_models_reports_cascade_unavailable_without_inventing_route(
    client: TestClient,
) -> None:
    client.app.state.registered_providers = {"zai", "deepseek"}
    body = client.get("/settings/models").json()
    assert all(row["state"] == "unavailable" for row in body["cascade_targets"])
    assert all(row["provider_id"] is None for row in body["cascade_targets"])
    assert all(row["model_id"] is None for row in body["cascade_targets"])


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
    assert any("unknown" in n.lower() for n in body["notes"])


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
                    "cached_input_per_mtok": 0.1,
                    "currency": "USD",
                    "billing_unit": "per_million_tokens",
                    "source_url": "https://provider.example/pricing",
                    "verified_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
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
    assert est.pricing_fingerprint
    assert est.pricing_source_url == "https://provider.example/pricing"
    # 1000 in * $1/M + 1000 out * $2/M = 0.003 base
    assert est.estimated_usd_low < 0.01

    conflict = estimate_prompt_cost(
        PromptCostEstimateRequest(
            tier="pro",
            provider="other-provider",
            model="other-model",
            input_chars=4000,
            expected_output_tokens=1000,
        ),
        budget=read_operator_budget(),
    )
    assert conflict.pricing_known is False
    assert conflict.estimated_usd_high is None
    assert any("does not match tier route" in note for note in conflict.notes)


def test_caddy_allowlist_includes_settings() -> None:
    caddy = Path("infrastructure/ansible/templates/Caddyfile.j2").read_text(
        encoding="utf-8"
    )
    assert "/settings*" in caddy
