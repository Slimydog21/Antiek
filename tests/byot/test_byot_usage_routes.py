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

import httpx
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
from substrate.byot_usage.balance.base import BalanceSnapshot, NativeBalance
from substrate.byot_usage.balance.deepseek import fetch_deepseek_balance
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
                native_balances=(
                    NativeBalance(currency="CNY", total="42.50", granted="40.00", topped_up="2.50"),
                    NativeBalance(currency="USD", total="1.25", granted="0.00", topped_up="1.25"),
                ),
                native_available=True,
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
    assert body.balance_usd is None
    assert body.granted_usd is None
    assert body.native_balances is not None
    assert body.native_available is True
    assert [(entry.currency, entry.total) for entry in body.native_balances] == [
        ("CNY", "42.50"), ("USD", "1.25"),
    ]
    assert body.note is None


def test_deepseek_provider_payload_crosses_adapter_and_route_without_usd_coercion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def provider_response(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "is_available": False,
            "balance_infos": [
                {"currency": "CNY", "total_balance": "42.5000", "granted_balance": "40.00", "topped_up_balance": "2.5000"},
                {"currency": "USD", "total_balance": "1.25", "granted_balance": "0.00", "topped_up_balance": "1.25"},
            ],
        })

    def fetch_from_mock_transport(*, catalog_id: str, key: SecretStr, base_url: str, **kwargs: Any) -> BalanceSnapshot:
        assert catalog_id == "deepseek"
        with httpx.Client(transport=httpx.MockTransport(provider_response)) as http:
            return fetch_deepseek_balance(key, base_url=base_url, http=http)

    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._fetch_balance",
        fetch_from_mock_transport,
    )
    response = client.get("/settings/balance/key-ds")
    assert response.status_code == 200
    body = BalanceResponse.model_validate(response.json())
    assert [(balance.currency, balance.total) for balance in body.native_balances or []] == [
        ("CNY", "42.5000"), ("USD", "1.25"),
    ]
    assert body.native_available is False
    assert body.balance_usd is None
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.deepseek.com/user/balance"
    assert requests[0].headers["Authorization"] == "Bearer sk-test-cred-ds"


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


def test_balance_does_not_echo_adapter_diagnostic_with_secret(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _mock_fetch_degrade(*, catalog_id: str, **kwargs: Any) -> BalanceSnapshot:
        return BalanceSnapshot(
            catalog_id=catalog_id,
            kind="unavailable",
            note="HTTP/parse error: sk-sensitive-test-key",
        )

    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._fetch_balance",
        _mock_fetch_degrade,
    )
    response = client.get("/settings/balance/key-ds")
    assert response.status_code == 200
    assert "sk-sensitive-test-key" not in response.text
    assert response.json()["note"] == "Provider balance unavailable."


@pytest.mark.parametrize("catalog_id", ["zhipu_glm", "mimo"])
def test_undocumented_native_balance_does_not_decrypt_or_call_provider(
    catalog_id: str,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._find_user_record",
        lambda api_key_id, owner_user_id: SimpleNamespace(
            provider_catalog_id=catalog_id,
            base_url="https://example.invalid/v1",
            cred_ref="must-not-load",
        ),
    )

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Undocumented balance path decrypted a key or called a provider")

    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._load_key", fail_if_called,
    )
    monkeypatch.setattr(
        "interfaces.research.api.byot_usage_routes._fetch_balance", fail_if_called,
    )

    response = client.get("/settings/balance/key-undocumented")
    assert response.status_code == 200
    body = BalanceResponse.model_validate(response.json())
    assert body.kind == "unavailable"
    assert body.balance_usd is None
    assert body.note == "Provider has not documented a native balance API."


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

    fresh = client.get("/settings/balance/key-oai")
    assert fresh.status_code == 200
    fresh_body = BalanceResponse.model_validate(fresh.json())
    assert fresh_body.kind == "spend_history"
    assert fresh_body.spend_usd is None
    assert fresh_body.note == "no usage recorded for this key"

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


def test_verified_operator_sessions_keep_models_usage_and_balance_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared storage sentinel must resolve to a distinct payer per signed person."""
    from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email
    from interfaces.research.api.app import create_app
    from substrate.auth.magic_link import mint_session_cookie
    from substrate.dispatch.router import reset_provider_registry

    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-only-auth-secret-at-least-32-bytes")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "user-a@example.test,user-b@example.test")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    monkeypatch.setattr("interfaces.research.api.byot_usage_routes._get_ledger", lambda: ledger)
    balance_calls: list[tuple[str, str]] = []

    def _offline_balance(*, catalog_id: str, api_key_id: str, owner_user_id: str, **_: Any) -> BalanceSnapshot:
        balance_calls.append((api_key_id, owner_user_id))
        return BalanceSnapshot(catalog_id=catalog_id, kind="unavailable")

    monkeypatch.setattr("interfaces.research.api.byot_usage_routes._fetch_balance", _offline_balance)
    cookies = {
        name: {"ANTIEK_SESSION": mint_session_cookie(user_id="__operator__", email=f"{name}@example.test")}
        for name in ("user-a", "user-b")
    }
    owners = {
        name: derive_owner_from_verified_email(f"{name}@example.test")
        for name in cookies
    }
    assert owners["user-a"] and owners["user-b"] and owners["user-a"] != owners["user-b"]
    body = {
        "provider_kind": "openai_compat",
        "provider_catalog_id": "deepseek",
        "model_id": "deepseek-chat",
        "display_name": "My DeepSeek",
    }
    reset_provider_registry()
    try:
        with TestClient(create_app(register_wrestling=False, register_providers=False)) as signed:
            created = {
                name: signed.post(
                    "/settings/models/user",
                    json={**body, "api_key": f"sk-test-only-{name}-abcdefghijklmnopqrstuvwxyz"},
                    cookies=cookies[name],
                )
                for name in cookies
            }
            assert all(response.status_code == 201 for response in created.values())
            ids = {name: response.json()["id"] for name, response in created.items()}
            assert ids["user-a"] != ids["user-b"]

            ledger.record_settlement(ids["user-a"], owners["user-a"], 125, "a" * 64)
            ledger.record_settlement(ids["user-b"], owners["user-b"], 375, "b" * 64)
            assert signed.post(
                f"/settings/usage/{ids['user-a']}/limit",
                json={"limit_cents": 1000}, cookies=cookies["user-a"],
            ).status_code == 200
            assert signed.post(
                f"/settings/usage/{ids['user-a']}/limit",
                json={"limit_cents": 1}, cookies=cookies["user-b"],
            ).status_code == 404
            assert signed.post(
                f"/settings/usage/{ids['user-b']}/limit",
                json={"limit_cents": 1}, cookies=cookies["user-a"],
            ).status_code == 404

            for name, expected_cents in (("user-a", 125), ("user-b", 375)):
                snapshot = signed.get("/settings/usage", cookies=cookies[name])
                assert snapshot.status_code == 200
                assert [(row["api_key_id"], row["used_cents"]) for row in snapshot.json()["keys"]] == [
                    (ids[name], expected_cents),
                ]
                if name == "user-a":
                    assert snapshot.json()["keys"][0]["limit_cents"] == 1000

            choice = {
                "authority": "user_model",
                "provider_id": ids["user-a"],
                "model_id": "deepseek-chat",
            }
            assert signed.post(
                "/settings/models/user/resolve", json=choice, cookies=cookies["user-b"],
            ).status_code == 409
            assert signed.get(
                f"/settings/balance/{ids['user-a']}", cookies=cookies["user-b"],
            ).status_code == 404
            assert signed.get(
                f"/settings/balance/{ids['user-b']}", cookies=cookies["user-a"],
            ).status_code == 404
            assert balance_calls == []
            own_balance = signed.get(
                f"/settings/balance/{ids['user-a']}", cookies=cookies["user-a"],
            )
            assert own_balance.status_code == 200
            assert balance_calls == [(ids["user-a"], owners["user-a"])]
    finally:
        reset_provider_registry()
