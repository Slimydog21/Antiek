"""Tests for the OAuth onboarding backend (BYOT v1).

Coverage:
  (a) authorize returns 501 when the provider's env credentials are unset.
  (b) authorize builds a valid PKCE URL with state when credentials ARE set.
  (c) callback rejects an invalid/expired/missing state (400).
  (d) callback succeeds with a mocked token exchange and stores the token.
  (e) status is owner-scoped — user-a's connection is invisible to user-b.
  (f) disconnect removes the stored token.
  (g) secret hygiene — no token material in any response body.

All offline: byok artifact/key-file redirected to tmp, token exchange
monkeypatched (no network).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.oauth_routes import (  # noqa: E402
    _state_store,
    register_oauth_routes,
)


# ---------------------------------------------------------------------------
# App + fixtures
# ---------------------------------------------------------------------------


def _fresh_app() -> FastAPI:
    """Build a minimal app with only the OAuth router + a test middleware
    that sets request.state.user_id from the ``X-Test-Owner`` header (default
    ``__operator__``). This mirrors how settings_models_admin falls back."""
    app = FastAPI()

    @app.middleware("http")
    async def _set_test_owner(request: Request, call_next):
        request.state.user_id = request.headers.get("X-Test-Owner", "__operator__")
        response = await call_next(request)
        return response

    register_oauth_routes(app)
    return app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    # Clear any OAuth env vars so the 501 test is deterministic.
    for key in list(os.environ):
        if key.startswith("ANTIEK_OAUTH_"):
            monkeypatch.delenv(key, raising=False)
    return tmp_path


@pytest.fixture
def client(env: Path) -> Iterator[TestClient]:
    with TestClient(_fresh_app()) as c:
        yield c


@pytest.fixture
def configured_env(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the OpenAI OAuth env vars (placeholders only — never real secrets)."""
    monkeypatch.setenv("ANTIEK_OAUTH_OPENAI_CLIENT_ID", "test-openai-client-id")
    monkeypatch.setenv("ANTIEK_OAUTH_OPENAI_CLIENT_SECRET", "test-openai-client-secret")


@pytest.fixture
def configured_client(configured_env: Path) -> Iterator[TestClient]:
    with TestClient(_fresh_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# (a) authorize 501 when env unset
# ---------------------------------------------------------------------------


def test_authorize_501_when_env_unset(client: TestClient) -> None:
    r = client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    assert r.status_code == 501
    assert "not configured" in r.json()["detail"].lower()


def test_authorize_501_for_anthropic_when_env_unset(client: TestClient) -> None:
    r = client.get(
        "/settings/oauth/anthropic/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    assert r.status_code == 501


def test_authorize_404_for_unknown_provider(client: TestClient) -> None:
    r = client.get(
        "/settings/oauth/unknown/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# (b) authorize builds a valid PKCE URL with state when configured
# ---------------------------------------------------------------------------


def test_authorize_returns_url_with_state(configured_client: TestClient) -> None:
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "openai"
    assert "state" in body and len(body["state"]) > 16
    url = body["authorize_url"]
    assert "https://auth.openai.com/oauth/authorize" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "client_id=test-openai-client-id" in url
    # No secrets in the URL
    assert "secret" not in url.lower()


# ---------------------------------------------------------------------------
# (c) callback state validation failure
# ---------------------------------------------------------------------------


def test_callback_rejects_missing_state(configured_client: TestClient) -> None:
    r = configured_client.get("/settings/oauth/openai/callback", params={"code": "abc"})
    assert r.status_code == 400


def test_callback_rejects_invalid_state(configured_client: TestClient) -> None:
    r = configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": "abc", "state": "nonexistent-state"},
    )
    assert r.status_code == 400
    assert "state" in r.json()["detail"].lower()


def test_callback_rejects_state_owner_mismatch(configured_client: TestClient) -> None:
    # Authorize as user-a.
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
        headers={"X-Test-Owner": "user-a"},
    )
    assert r.status_code == 200
    state = r.json()["state"]

    # Callback as user-b → owner mismatch.
    r2 = configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": "fake-code", "state": state},
        headers={"X-Test-Owner": "user-b"},
    )
    assert r2.status_code == 400
    assert "owner" in r2.json()["detail"].lower()


def test_callback_rejects_provider_mismatch(
    configured_client: TestClient, monkeypatch
) -> None:
    # Authorize as openai.
    monkeypatch.setenv("ANTIEK_OAUTH_ANTHROPIC_CLIENT_ID", "test-anthropic-id")
    monkeypatch.setenv("ANTIEK_OAUTH_ANTHROPIC_CLIENT_SECRET", "test-anthropic-secret")
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    assert r.status_code == 200
    state = r.json()["state"]

    # Callback at anthropic endpoint with openai's state.
    r2 = configured_client.get(
        "/settings/oauth/anthropic/callback",
        params={"code": "fake-code", "state": state},
    )
    assert r2.status_code == 400


def test_callback_state_is_single_use(configured_client: TestClient, monkeypatch) -> None:
    # Mock the token exchange so callback can succeed.
    monkeypatch.setattr(
        "interfaces.research.api.oauth_routes._exchange_code_for_tokens",
        lambda **kw: {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
    )
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    state = r.json()["state"]
    code = "valid-code"

    # First callback succeeds.
    r1 = configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": code, "state": state},
    )
    assert r1.status_code == 200
    assert r1.json()["connected"] is True

    # Second callback with the same state → rejected (single-use).
    r2 = configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": code, "state": state},
    )
    assert r2.status_code == 400


# ---------------------------------------------------------------------------
# (d) callback succeeds with mocked token exchange
# ---------------------------------------------------------------------------


def test_callback_success_stores_token(
    configured_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "interfaces.research.api.oauth_routes._exchange_code_for_tokens",
        lambda **kw: {
            "access_token": "super-secret-access-token",
            "refresh_token": "super-secret-refresh-token",
            "expires_in": 3600,
        },
    )
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
        headers={"X-Test-Owner": "user-a"},
    )
    assert r.status_code == 200
    state = r.json()["state"]

    r2 = configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": "the-code", "state": state},
        headers={"X-Test-Owner": "user-a"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["provider"] == "openai"
    assert body["connected"] is True
    # NEVER return token material.
    assert "access_token" not in json.dumps(body)
    assert "refresh_token" not in json.dumps(body)


# ---------------------------------------------------------------------------
# (e) status is owner-scoped
# ---------------------------------------------------------------------------


def test_status_owner_scoped(configured_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "interfaces.research.api.oauth_routes._exchange_code_for_tokens",
        lambda **kw: {
            "access_token": "tok-a",
            "refresh_token": "ref-a",
            "expires_in": 3600,
        },
    )
    # Connect as user-a.
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
        headers={"X-Test-Owner": "user-a"},
    )
    state = r.json()["state"]
    configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": "code", "state": state},
        headers={"X-Test-Owner": "user-a"},
    )

    # user-a sees connected.
    s_a = configured_client.get(
        "/settings/oauth/openai/status", headers={"X-Test-Owner": "user-a"}
    )
    assert s_a.status_code == 200
    assert s_a.json()["connected"] is True
    assert s_a.json()["expires_at"] is not None

    # user-b does NOT see user-a's connection.
    s_b = configured_client.get(
        "/settings/oauth/openai/status", headers={"X-Test-Owner": "user-b"}
    )
    assert s_b.status_code == 200
    assert s_b.json()["connected"] is False


def test_status_configured_false_when_env_unset(client: TestClient) -> None:
    r = client.get("/settings/oauth/openai/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["connected"] is False


def test_status_configured_true_when_env_set(configured_client: TestClient) -> None:
    r = configured_client.get("/settings/oauth/openai/status")
    assert r.status_code == 200
    assert r.json()["configured"] is True


# ---------------------------------------------------------------------------
# (f) disconnect
# ---------------------------------------------------------------------------


def test_disconnect_removes_token(configured_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "interfaces.research.api.oauth_routes._exchange_code_for_tokens",
        lambda **kw: {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
    )
    # Connect.
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    state = r.json()["state"]
    configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": "code", "state": state},
    )
    assert configured_client.get("/settings/oauth/openai/status").json()["connected"] is True

    # Disconnect.
    d = configured_client.post("/settings/oauth/openai/disconnect")
    assert d.status_code == 200
    assert d.json()["disconnected"] is True

    # Status reflects disconnection.
    s = configured_client.get("/settings/oauth/openai/status")
    assert s.json()["connected"] is False


def test_disconnect_is_idempotent(configured_client: TestClient) -> None:
    d = configured_client.post("/settings/oauth/openai/disconnect")
    assert d.status_code == 200
    assert d.json()["disconnected"] is False


# ---------------------------------------------------------------------------
# (g) Secret hygiene — no token material leaks
# ---------------------------------------------------------------------------


def test_no_token_material_in_any_response(configured_client: TestClient, monkeypatch) -> None:
    access = "LEAK_CANARY_ACCESS_TOKEN_xyz"
    refresh = "LEAK_CANARY_REFRESH_TOKEN_xyz"
    monkeypatch.setattr(
        "interfaces.research.api.oauth_routes._exchange_code_for_tokens",
        lambda **kw: {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": 3600,
        },
    )
    r = configured_client.get(
        "/settings/oauth/openai/authorize",
        params={"redirect_uri": "https://example.test/callback"},
    )
    state = r.json()["state"]

    r2 = configured_client.get(
        "/settings/oauth/openai/callback",
        params={"code": "code", "state": state},
    )
    r3 = configured_client.get("/settings/oauth/openai/status")
    r4 = configured_client.post("/settings/oauth/openai/disconnect")

    for resp in [r2, r3, r4]:
        body = resp.text
        assert access not in body, f"access token leaked in {resp.url}"
        assert refresh not in body, f"refresh token leaked in {resp.url}"


# ---------------------------------------------------------------------------
# State store unit tests
# ---------------------------------------------------------------------------


def test_state_store_expiry(monkeypatch) -> None:
    import time as _time
    from interfaces.research.api.oauth_routes import _OAuthStateStore

    store = _OAuthStateStore()
    fake_now = [1000.0]
    monkeypatch.setattr(_time, "time", lambda: fake_now[0])
    store.put("s1", code_verifier="v1", provider="openai", owner_user_id="u1",
              redirect_uri="https://x.test/cb")
    assert store.pop("s1") is not None
    # Already consumed.
    assert store.pop("s1") is None

    store.put("s2", code_verifier="v2", provider="openai", owner_user_id="u1",
              redirect_uri="https://x.test/cb", ttl=10)
    fake_now[0] += 11  # expired
    assert store.pop("s2") is None

