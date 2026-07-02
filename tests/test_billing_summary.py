"""Endpoint truth tests for billing summary (AGH SPR-02)."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from substrate.dispatch import reset_provider_registry
from substrate.event_log import emit_typed
from substrate.schemas import DispatchCallPayload


@pytest.fixture(autouse=True)
def _isolate_provider_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="billing-summary-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    for key in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "HERMES_API_KEY",
        "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _dispatch(
    investigation_id: str,
    *,
    cost_usd: float,
    input_tokens: int,
    output_tokens: int,
    prompt_hash: str,
) -> None:
    emit_typed(
        investigation_id,
        DispatchCallPayload(
            provider="deepseek",
            model="deepseek-v4-flash",
            tier="flash",
            target_role="decomposer",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=300,
            prompt_hash=prompt_hash,
            finish_reason="stop",
        ),
        role="dispatch",
    )


def test_billing_summary_scans_dispatch_calls_exactly(client):
    period = datetime.now(UTC).strftime("%Y-%m")
    _dispatch(
        "inv-billing-a",
        cost_usd=0.10,
        input_tokens=10,
        output_tokens=3,
        prompt_hash="a",
    )
    _dispatch(
        "inv-billing-b",
        cost_usd=0.25,
        input_tokens=20,
        output_tokens=7,
        prompt_hash="b",
    )

    response = client.get(f"/billing/summary/__operator__/{period}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["record_count"] == 2
    assert body["paid_private_token_cost_usd"] == "0.35"
    assert Decimal(body["paid_private_margin_usd"]) == Decimal("0.175")
    assert body["total_raw_usd"] == "0.35"
    assert Decimal(body["total_margin_usd"]) == Decimal("0.175")
    assert Decimal(body["total_billable_usd"]) == Decimal("0.525")
    assert body["free_tokens_consumed"] == 0


def test_billing_summary_period_bounds_accept_aware_runtime(client):
    period = datetime.now(UTC).strftime("%Y-%m")
    _dispatch(
        "inv-billing-aware",
        cost_usd=0.03,
        input_tokens=2,
        output_tokens=1,
        prompt_hash="aware",
    )

    response = client.get(f"/billing/summary/__operator__/{period}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["total_raw_usd"]) == Decimal("0.03")
