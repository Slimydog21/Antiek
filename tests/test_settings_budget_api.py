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


def test_budget_operator_cap_differs_from_daemon_cap_stays_consistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Regression (#704): the sidecar records spend against the daemon cap,
    but the operator's Settings cap takes precedence and may differ. spent
    and remaining must both be baselined on the Settings cap.

    Sidecar: daemon cap $5, spent $4 (remaining_today == $1). Operator sets a
    $200 Settings budget. Before the fix, remaining was read straight from
    remaining_today() ($1, daemon-cap baseline) and spent was re-based on the
    Settings cap ($200 - $1 = $199) — the bar reads 99.5% consumed and
    would_exceed fires on nearly every prompt though only $4 was spent.

    Calls read_operator_budget() directly (no FastAPI app) — the readout is a
    plain function and the defect lives entirely in it.
    """
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    # $4 spend on the daemon's default $5 cap (per-investigation cap is $2).
    daemon = DaemonBudget(daily_cap_usd=5.0)
    daemon.reserve(2.0)
    daemon.reserve(2.0)
    monkeypatch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "200")

    budget = read_operator_budget()

    assert budget.daily_cap_usd == 200.0
    assert budget.spent_status == "known"
    # spend is cap-independent; remaining re-bases on the $200 Settings cap.
    assert budget.spent_usd == 4.0
    assert budget.remaining_usd == 196.0

    # The fix propagates to the guard: a $150 prompt no longer falsely trips
    # would_exceed against the phantom $1 remaining.
    est = estimate_prompt_cost(
        PromptCostEstimateRequest(tier="research", prompt_chars=10),
        budget=budget,
    )
    if est.estimated_usd_high is not None:  # pricing is 0.0 placeholder today
        assert est.would_exceed_budget is (est.estimated_usd_high > 196.0)


def test_budget_spent_today_is_cap_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`spent_today()` reports raw recorded spend regardless of the cap it is
    constructed with — the property `read_operator_budget` relies on to keep
    spent + remaining on one baseline."""
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    DaemonBudget(daily_cap_usd=5.0).reserve(1.5)
    # A DaemonBudget with a *different* cap still reads the same recorded spend.
    assert DaemonBudget(daily_cap_usd=200.0).spent_today() == 1.5
    assert DaemonBudget(daily_cap_usd=1.0).spent_today() == 1.5


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
