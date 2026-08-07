from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes
from runtime.research_runner.byot_provider_catalog import (
    BYOT_PROVIDER_PRESETS,
    get_provider_preset,
    route_authority_catalog_entries,
)
from runtime.research_runner.provider_route_authority import (
    ProviderRouteAuthorityResolver,
    RouteExecutionStatus,
)
from substrate.dispatch.router import reset_provider_registry

_EXPECTED_BASES = {
    "deepseek": "https://api.deepseek.com",
    "kimi": "https://api.moonshot.ai/v1",
    "zhipu_glm": "https://api.z.ai/api/paas/v4",
    "mimo": "https://api.mimo.xiaomi.com/v1",
    "xai": "https://api.x.ai/v1",
}


def test_presets_have_exact_positive_price_rows() -> None:
    assert {preset.catalog_id: preset.default_base_url for preset in BYOT_PROVIDER_PRESETS} == (
        _EXPECTED_BASES
    )
    deepseek = get_provider_preset("deepseek")
    assert {variant.model_id for variant in deepseek.models} == {
        "deepseek-chat",
        "deepseek-reasoner",
    }

    entries = route_authority_catalog_entries()
    assert len(entries) == sum(len(preset.models) for preset in BYOT_PROVIDER_PRESETS)
    resolver = ProviderRouteAuthorityResolver(entries)
    for entry in entries:
        authority = resolver.resolve(entry.identity, provider_id="test-user-provider")
        assert authority.pricing_status == "known"
        assert authority.rate_snapshot == entry.cost.snapshot
        assert authority.execution_status is not RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING
        assert all(rate.usd_per_unit > 0 for rate in entry.cost.rates)


def test_preset_user_key_is_registered_route_eligible_and_priced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    reset_provider_registry()
    app = FastAPI()
    register_settings_budget_routes(app)
    with TestClient(app) as client:
        response = client.post(
            "/settings/models/user",
            json={
                "provider_kind": "openai_compat",
                "provider_catalog_id": "deepseek",
                "model_id": "deepseek-chat",
                "display_name": "Preset DeepSeek",
                "api_key": "sk-test-only-preset-key-abcdefghijklmnopqrstuvwxyz",
            },
        )
        assert response.status_code == 201
        row = response.json()
        assert row["base_url"] == "https://api.deepseek.com"
        assert row["provider_catalog_id"] == "deepseek"
        assert row["route_eligible"] is True
        assert row["pricing_status"] == "known"
        assert row["execution_status"] == "blocked_idempotency_unproven"
        assert row["rate_snapshot"] == "deepseek-v4-flash-2026-08-spec"

        custom = client.post(
            "/settings/models/user",
            json={
                "provider_kind": "openai_compat",
                "model_id": "deepseek-chat",
                "display_name": "Custom Exact Endpoint",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test-only-custom-key-abcdefghijklmnopqrstuvwxyz",
            },
        )
        assert custom.status_code == 201
        assert custom.json()["pricing_status"] == "unknown"
        assert custom.json()["execution_status"] == "blocked_unknown_pricing"
    reset_provider_registry()
