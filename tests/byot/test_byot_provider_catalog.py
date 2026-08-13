from __future__ import annotations

from decimal import Decimal
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
from runtime.research_runner.protocol import BillingUnit
from runtime.research_runner.provider_route_authority import (
    ProviderRouteAuthorityResolver,
    RouteExecutionStatus,
)
from substrate.dispatch.router import reset_provider_registry

_EXPECTED_BASES = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "kimi": "https://api.moonshot.ai/v1",
    "zhipu_glm": "https://api.z.ai/api/paas/v4",
    "mimo": "https://api.mimo.xiaomi.com/v1",
    "xai": "https://api.x.ai/v1",
}

_EXPECTED_FIRST_PARTY = {
    ("openai", "gpt-5.6-sol"): ("openai_compat", "5", "30"),
    ("openai", "gpt-5.6-terra"): ("openai_compat", "2", "12"),
    ("openai", "gpt-5.6-luna"): ("openai_compat", "0.20", "1.20"),
    ("anthropic", "claude-opus-5"): ("anthropic", "5", "25"),
    ("anthropic", "claude-sonnet-5"): ("anthropic", "2", "10"),
    ("anthropic", "claude-haiku-4-5-20251001"): ("anthropic", "1", "5"),
}

# Authoritative provider pages checked 2026-08-12. These assertions pin the
# dated server snapshot as well as its rates so an undated/stale price table
# cannot silently replace the owner-facing ceiling catalog.
_EXPECTED_FIRST_PARTY_SOURCES = {
    "openai": "https://developers.openai.com/api/docs/models",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/models/overview",
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


def test_first_party_presets_pin_exact_kind_endpoint_path_and_prices() -> None:
    expected_routes = {
        "openai": ("https://api.openai.com", "/v1/chat/completions"),
        "anthropic": ("https://api.anthropic.com", "/v1/messages"),
    }
    for catalog_id, (endpoint, path) in expected_routes.items():
        preset = get_provider_preset(catalog_id)
        assert (preset.default_base_url, preset.chat_completions_path) == (endpoint, path)
        assert preset.pricing_source == _EXPECTED_FIRST_PARTY_SOURCES[catalog_id]
        for variant in preset.models:
            kind, input_per_million, output_per_million = _EXPECTED_FIRST_PARTY[
                (catalog_id, variant.model_id)
            ]
            assert preset.adapter_kind == kind
            assert variant.snapshot.endswith("2026-08-12")
            rates = {rate.unit: rate.usd_per_unit for rate in variant.rates}
            assert rates[BillingUnit.INPUT_TOKEN] * Decimal("1000000") == Decimal(
                input_per_million
            )
            assert rates[BillingUnit.OUTPUT_TOKEN] * Decimal("1000000") == Decimal(
                output_per_million
            )

            identity = next(
                entry.identity
                for entry in route_authority_catalog_entries()
                if entry.identity.model_id == variant.model_id
            )
            assert (identity.provider_kind, identity.endpoint) == (kind, endpoint)


def test_onboarding_catalog_endpoint_is_exact_stable_non_secret_projection() -> None:
    app = FastAPI()
    register_settings_budget_routes(app)
    with TestClient(app) as client:
        response = client.get("/settings/models/catalog")

    assert response.status_code == 200
    expected = {
        "providers": [
            {
                "catalog_id": preset.catalog_id,
                "display": preset.display,
                "provider_kind": preset.adapter_kind,
                "default_base_url": preset.default_base_url,
                "models": [
                    {
                        "id": model.model_id,
                        "label": model.label,
                        "snapshot": model.snapshot,
                    }
                    for model in preset.models
                ],
                "pricing_source": preset.pricing_source,
            }
            for preset in BYOT_PROVIDER_PRESETS
        ],
        "count": len(BYOT_PROVIDER_PRESETS),
    }
    assert response.json() == expected
    assert [row["catalog_id"] for row in response.json()["providers"]] == [
        preset.catalog_id for preset in BYOT_PROVIDER_PRESETS
    ]
    lowered = response.text.lower()
    assert all(secret_name not in lowered for secret_name in ("api_key", "cred_ref", "key_present"))


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
