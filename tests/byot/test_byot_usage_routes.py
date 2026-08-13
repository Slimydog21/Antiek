"""HTTP endpoint tests for BYOT usage/balance routes.

Verifies (TestClient, adapters mocked — no live net):
- GET /settings/usage returns the ledger snapshot for the session user only
- Setting a limit is reflected in the next snapshot
- GET /settings/balance/{id} returns the mocked adapter's normalized balance
- GET /settings/balance/{id} returns status=unavailable when the adapter degrades
- A cross-user api_key_id → 404
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.byot_usage_routes import (
    BalanceResponse,
    SetLimitResponse,
    UsageSnapshotResponse,
    register_byot_usage_routes,
)
from runtime.byok.secret_str import SecretStr
from substrate.byot_usage.balance.base import BalanceSnapshot
from substrate.byot_usage.ledger import ByotUsageLedger

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ledger(tmp_path: Path) -> ByotUsageLedger:
    """Fresh ledger backed by a temp SQLite file."""
    return ByotUsageLedger(tmp_path / "usage.sqlite3")


@pytest.fixture()
def app(ledger: ByotUsageLedger, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """FastAPI app with BYOT usage routes and mocked dependencies."""

    _app = FastAPI()
    register_byot_usage_routes(_app)

    # Auth middleware: set request.state.user_id for every request.
    @_app.middleware("http")
    async def _set_user(request: Request, call_next: Any) -> Any:  # noqa: ANN401
        request.state.user_id = "test-user"
        return await call_next(request)

    # Mock the ledger.
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._get_ledger",
        lambda: ledger,
    )

    # Mock the user-model registry.  Two records:
    #   "key-ds"  → cred_ref="cred-ds",  provider_catalog_id="deepseek", owner="test-user"
    #   "key-ki"  → cred_ref="cred-ki",  provider_catalog_id="kimi",     owner="test-user"
    #   "key-xu"  → cred_ref="cred-xu",  provider_catalog_id="openai",   owner="other-user"
    registry: dict[str, Any] = {
        "key-ds": SimpleNamespace(
            id="key-ds",
            owner_user_id="test-user",
            provider_catalog_id="deepseek",
            base_url="https://api.deepseek.com",
            cred_ref="cred-ds",
        ),
        "key-ki": SimpleNamespace(
            id="key-ki",
            owner_user_id="test-user",
            provider_catalog_id="kimi",
            base_url="https://api.moonshot.ai/v1",
            cred_ref="cred-ki",
        ),
        "key-xu": SimpleNamespace(
            id="key-xu",
            owner_user_id="other-user",
            provider_catalog_id="openai",
            base_url="https://api.openai.com/v1",
            cred_ref="cred-xu",
        ),
    }
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._load_registry",
        lambda: registry,
    )

    # Mock credential loading — return a dummy SecretStr.
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._load_key",
        lambda cred_ref: SecretStr(f"sk-test-{cred_ref}"),
    )

    return _app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /settings/usage
# ---------------------------------------------------------------------------


def test_usage_returns_empty_for_fresh_user(client: TestClient) -> None:
    response = client.get("/settings/usage")
    assert response.status_code == 200
    body = UsageSnapshotResponse.model_validate(response.json())
    assert body.count == 0
    assert body.keys == []


def test_usage_returns_ledger_snapshot(
    client: TestClient,
    ledger: ByotUsageLedger,
) -> None:
    ledger.record_settlement("key-ds", "test-user", 500, "a" * 64)
    ledger.set_limit("key-ds", "test-user", 1000)

    response = client.get("/settings/usage")
    assert response.status_code == 200
    body = UsageSnapshotResponse.model_validate(response.json())
    assert body.count == 1
    entry = body.keys[0]
    assert entry.api_key_id == "key-ds"
    assert entry.used_cents == 500
    assert entry.limit_cents == 1000
    assert entry.remaining_cents == 500


def test_usage_only_returns_session_users_keys(
    client: TestClient,
    ledger: ByotUsageLedger,
) -> None:
    ledger.record_settlement("key-ds", "test-user", 100, "a" * 64)
    ledger.record_settlement("key-xu", "other-user", 999, "b" * 64)

    response = client.get("/settings/usage")
    assert response.status_code == 200
    body = UsageSnapshotResponse.model_validate(response.json())
    assert body.count == 1
    assert body.keys[0].api_key_id == "key-ds"
    # other-user's key is invisible.
    assert all(k.api_key_id != "key-xu" for k in body.keys)


# ---------------------------------------------------------------------------
# POST /settings/usage/{api_key_id}/limit
# ---------------------------------------------------------------------------


def test_set_limit_creates_row_and_reflects_in_snapshot(
    client: TestClient,
    ledger: ByotUsageLedger,
) -> None:
    # No prior settlement — set_limit should still work (UPSERT).
    response = client.post(
        "/settings/usage/key-ds/limit",
        json={"limit_cents": 5000},
    )
    assert response.status_code == 200
    body = SetLimitResponse.model_validate(response.json())
    assert body.api_key_id == "key-ds"
    assert body.limit_cents == 5000
    assert body.used_cents == 0
    assert body.remaining_cents == 5000

    # Verify it shows up in the snapshot.
    snap = client.get("/settings/usage")
    assert snap.status_code == 200
    snap_body = UsageSnapshotResponse.model_validate(snap.json())
    assert snap_body.count == 1
    assert snap_body.keys[0].limit_cents == 5000


def test_set_limit_clear(client: TestClient, ledger: ByotUsageLedger) -> None:
    ledger.set_limit("key-ds", "test-user", 1000)

    response = client.post(
        "/settings/usage/key-ds/limit",
        json={"limit_cents": None},
    )
    assert response.status_code == 200
    body = SetLimitResponse.model_validate(response.json())
    assert body.limit_cents is None
    assert body.remaining_cents is None


def test_set_limit_cross_user_404(client: TestClient) -> None:
    """A key owned by another user returns 404."""
    response = client.post(
        "/settings/usage/key-xu/limit",
        json={"limit_cents": 1000},
    )
    assert response.status_code == 404


def test_set_limit_unknown_key_404(client: TestClient) -> None:
    response = client.post(
        "/settings/usage/nonexistent/limit",
        json={"limit_cents": 1000},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /settings/balance/{api_key_id}
# ---------------------------------------------------------------------------


def test_balance_returns_native_balance(
    client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mocked DeepSeek adapter returns a native balance snapshot."""

    def _mock_fetch_balance(*, catalog_id: str, **kwargs: Any) -> BalanceSnapshot:
        if catalog_id == "deepseek":
            return BalanceSnapshot(
                catalog_id="deepseek",
                kind="balance_native",
                balance_usd=42.50,
                granted_usd=40.00,
            )
        return BalanceSnapshot(catalog_id=catalog_id, kind="unavailable")

    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._fetch_balance",
        _mock_fetch_balance,
    )

    response = client.get("/settings/balance/key-ds")
    assert response.status_code == 200
    body = BalanceResponse.model_validate(response.json())
    assert body.api_key_id == "key-ds"
    assert body.catalog_id == "deepseek"
    assert body.kind == "balance_native"
    assert body.balance_usd == 42.50
    assert body.granted_usd == 40.00
    assert body.note is None


def test_balance_returns_unavailable_on_adapter_degrade(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the adapter degrades, kind=unavailable with a note."""

    def _mock_fetch_degrade(*, catalog_id: str, **kwargs: Any) -> BalanceSnapshot:
        return BalanceSnapshot(
            catalog_id=catalog_id,
            kind="unavailable",
            note="schema drift: KeyError: 'balance_infos'",
        )

    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._fetch_balance",
        _mock_fetch_degrade,
    )

    response = client.get("/settings/balance/key-ds")
    assert response.status_code == 200
    body = BalanceResponse.model_validate(response.json())
    assert body.kind == "unavailable"
    assert body.balance_usd is None
    assert "schema drift" in (body.note or "")


def test_balance_cross_user_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key owned by another user returns 404."""
    response = client.get("/settings/balance/key-xu")
    assert response.status_code == 404


def test_balance_unknown_key_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = client.get("/settings/balance/nonexistent")
    assert response.status_code == 404


def test_balance_returns_spend_history_fallback(
    client: TestClient,
    ledger: ByotUsageLedger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Providers without a native adapter fall back to spend-history."""

    # Don't mock _fetch_balance — let the real dispatch run, but mock the
    # registry to have an "openai" key (no native adapter → spend_history).
    registry: dict[str, Any] = {
        "key-oai": SimpleNamespace(
            id="key-oai",
            owner_user_id="test-user",
            provider_catalog_id="openai",
            base_url="https://api.openai.com/v1",
            cred_ref="cred-oai",
        ),
    }
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._load_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._load_key",
        lambda cred_ref: SecretStr(f"sk-test-{cred_ref}"),
    )

    # Seed some usage so spend_history has data.
    ledger.record_settlement("key-oai", "test-user", 250, "c" * 64)
    ledger.set_limit("key-oai", "test-user", 5000)

    response = client.get("/settings/balance/key-oai")
    assert response.status_code == 200
    body = BalanceResponse.model_validate(response.json())
    assert body.kind == "spend_history"
    assert body.spend_usd == 2.50
    assert body.budget_usd == 50.00


def test_balance_credential_load_failure_returns_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the credential can't be loaded, return unavailable."""

    def _fail_load(cred_ref: str) -> SecretStr:
        raise RuntimeError("credential not found")

    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._load_key",
        _fail_load,
    )

    response = client.get("/settings/balance/key-ds")
    assert response.status_code == 200
    body = BalanceResponse.model_validate(response.json())
    assert body.kind == "unavailable"
    assert "credential load failed" in (body.note or "")
