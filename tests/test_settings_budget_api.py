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
from substrate.antiek_bench import run_mock_weekly_scorecard


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
    assert any("placeholder" in n.lower() or "0.0" in n for n in body["notes"])


def test_antiek_bench_latest_returns_unavailable_before_scorecard(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_BENCH_DIR", str(tmp_path / "bench"))
    r = client.get("/settings/antiek-bench/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["best_by_task_class"] == []
    assert any("no Antiek-bench scorecard" in note for note in body["notes"])


def test_antiek_bench_latest_shows_best_model_by_task_class(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench_dir = tmp_path / "bench"
    monkeypatch.setenv("ANTIEK_BENCH_DIR", str(bench_dir))
    run_mock_weekly_scorecard(base_dir=bench_dir, week_id="2026-W28")

    r = client.get("/settings/antiek-bench/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["week_id"] == "2026-W28"
    task_classes = {row["task_class"] for row in body["best_by_task_class"]}
    assert {"research_question", "reading_highlight"} <= task_classes
    assert all(row["provider"] and row["model"] for row in body["best_by_task_class"])


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


def test_route_projection_auto_cost_selects_cheapest_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interfaces.research.api.settings_budget as sb

    fake: dict[str, Any] = {
        "tiers": {
            "pro": {
                "provider": "premium",
                "model": "quality",
                "pricing": {"input_per_mtok": 10.0, "output_per_mtok": 10.0},
                "fallback": {
                    "provider": "cheap",
                    "model": "fast",
                    "pricing": {"input_per_mtok": 1.0, "output_per_mtok": 1.0},
                },
            }
        }
    }
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: fake)

    est = estimate_prompt_cost(
        PromptCostEstimateRequest(
            task_kind="research_question",
            role="synthesizer",
            tier="pro",
            route_mode="auto_cost",
            prompt_chars=4000,
            expected_output_tokens=1000,
        )
    )

    assert est.selected_candidate is not None
    assert est.selected_candidate.provider == "cheap"
    assert est.selected_candidate.fallback_chain_index == 1
    assert est.provider == "cheap"
    assert len(est.candidates) == 2


def test_route_projection_unknown_pricing_has_no_false_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interfaces.research.api.settings_budget as sb

    fake: dict[str, Any] = {
        "tiers": {
            "pro": {
                "provider": "unknown",
                "model": "mystery",
                "pricing": {"input_per_mtok": 0.0, "output_per_mtok": 0.0},
            }
        }
    }
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: fake)

    est = estimate_prompt_cost(
        PromptCostEstimateRequest(
            task_kind="synthesis",
            role="synthesizer",
            tier="pro",
            route_mode="auto_balanced",
            prompt_chars=4000,
            expected_output_tokens=1000,
        )
    )

    assert est.pricing_known is False
    assert est.estimated_usd_low is None
    assert est.would_exceed_budget is None
    assert est.selected_candidate is not None
    assert est.selected_candidate.pricing_known is False


def test_route_projection_manual_model_bypasses_advisor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interfaces.research.api.settings_budget as sb

    fake: dict[str, Any] = {
        "tiers": {
            "pro": {
                "provider": "premium",
                "model": "quality",
                "pricing": {"input_per_mtok": 10.0, "output_per_mtok": 10.0},
                "fallback": {
                    "provider": "cheap",
                    "model": "fast",
                    "pricing": {"input_per_mtok": 1.0, "output_per_mtok": 1.0},
                },
            }
        }
    }
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: fake)

    est = estimate_prompt_cost(
        PromptCostEstimateRequest(
            tier="pro",
            route_mode="manual",
            manual_provider="premium",
            manual_model="quality",
            prompt_chars=4000,
            expected_output_tokens=1000,
        )
    )

    assert est.selected_candidate is not None
    assert est.selected_candidate.provider == "premium"
    assert est.selected_candidate.selection_reason == "manual"


def test_route_projection_cache_warm_candidate_can_beat_cheaper_cold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interfaces.research.api.settings_budget as sb

    fake: dict[str, Any] = {
        "tiers": {
            "pro": {
                "provider": "cached-premium",
                "model": "quality",
                "pricing": {
                    "input_per_mtok": 4.0,
                    "cached_input_per_mtok": 0.1,
                    "output_per_mtok": 1.0,
                },
                "fallback": {
                    "provider": "cold-cheap",
                    "model": "fast",
                    "pricing": {
                        "input_per_mtok": 1.0,
                        "cached_input_per_mtok": 0.0,
                        "output_per_mtok": 1.0,
                    },
                },
            }
        }
    }
    monkeypatch.setattr(sb, "_load_dispatch_config", lambda: fake)

    est = estimate_prompt_cost(
        PromptCostEstimateRequest(
            tier="pro",
            route_mode="auto_cost",
            prompt_chars=40_000,
            expected_output_tokens=100,
            session_cache_key="read-session-1",
        )
    )

    assert est.selected_candidate is not None
    assert est.selected_candidate.provider == "cached-premium"
    assert est.selected_candidate.cache_status == "warm"
    cold = next(c for c in est.candidates if c.provider == "cold-cheap")
    assert cold.cache_status == "cold"


def test_caddy_allowlist_includes_settings() -> None:
    caddy = Path("infrastructure/ansible/templates/Caddyfile.j2").read_text(
        encoding="utf-8"
    )
    assert "/settings*" in caddy
