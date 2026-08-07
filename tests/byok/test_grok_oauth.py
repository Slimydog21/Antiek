"""Tests for Grok (xAI) device-code OAuth — all HTTP mocked, zero network.

Covers: device-code request → poll (pending then success), refresh form-POST
with token rotation, JWT exp parsing with skew, 403/400/401/429/5xx failure
taxonomy, origin-pin rejection, encrypted per-user storage, no token echo.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
import nacl.secret
import pytest

from runtime.byok.grok_oauth import (
    DeviceCodeGrant,
    GrokAuthError,
    GrokAuthFailure,
    XaiTokens,
    compute_expires_at,
    delete_grok_tokens,
    find_grok_cred_id,
    load_grok_tokens,
    poll_device_token,
    quarantine_grok_tokens,
    refresh_grok_token,
    request_device_code,
    store_grok_tokens,
    validate_inference_base_url,
    validate_oauth_endpoint,
)
from runtime.byok.store import list_credentials

_KEY = b"t" * nacl.secret.SecretBox.KEY_SIZE

# ─── helpers ─────────────────────────────────────────────────────────────────


def _make_jwt(claims: dict[str, Any]) -> str:
    """Build a minimal JWT (header.payload.) with the given claims."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}."


def _mock_handler(
    responses: list[tuple[int, dict[str, Any]]],
) -> httpx.MockTransport:
    """Return a transport that serves responses in order, last one repeating."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        idx = min(call_count, len(responses) - 1)
        call_count += 1
        status, body = responses[idx]
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _successful_tokens(access_exp: float | None = None) -> dict[str, Any]:
    exp = access_exp or (time.time() + 3600)
    return {
        "access_token": _make_jwt({"exp": exp, "sub": "user-123"}),
        "refresh_token": "rt-initial-abc",
        "id_token": _make_jwt({"sub": "user-123", "email": "u@test.com"}),
        "expires_in": 3600,
    }


# ─── Origin-pin validators ──────────────────────────────────────────────────


class TestOriginPin:
    def test_valid_x_ai_endpoint(self) -> None:
        assert validate_oauth_endpoint("https://auth.x.ai/oauth2/token") == (
            "https://auth.x.ai/oauth2/token"
        )

    def test_valid_subdomain(self) -> None:
        assert validate_oauth_endpoint("https://api.x.ai/v1") == "https://api.x.ai/v1"

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="must use https"):
            validate_oauth_endpoint("http://auth.x.ai/oauth2/token")

    def test_rejects_non_x_ai_host(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.x\.ai"):
            validate_oauth_endpoint("https://evil.com/oauth2/token")

    def test_rejects_similar_host(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.x\.ai"):
            validate_oauth_endpoint("https://auth-x.ai/oauth2/token")

    def test_inference_base_url_same_pin(self) -> None:
        assert validate_inference_base_url("https://api.x.ai/v1") == "https://api.x.ai/v1"

    def test_inference_rejects_non_x_ai(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.x\.ai"):
            validate_inference_base_url("https://openai.com/v1")


# ─── JWT exp parsing ─────────────────────────────────────────────────────────


class TestJwtExp:
    def test_parses_exp_claim(self) -> None:
        token = _make_jwt({"exp": 1700000000})
        assert compute_expires_at(token) == 1700000000 - 30

    def test_fallback_on_malformed_jwt(self) -> None:
        now = time.time()
        result = compute_expires_at("not-a-jwt", fallback_expires_in=600)
        assert abs(result - (now + 600 - 30)) < 2

    def test_fallback_on_missing_exp(self) -> None:
        token = _make_jwt({"sub": "user"})
        now = time.time()
        result = compute_expires_at(token, fallback_expires_in=120)
        assert abs(result - (now + 120 - 30)) < 2

    def test_skew_applied(self) -> None:
        token = _make_jwt({"exp": 1700000000})
        assert compute_expires_at(token) == 1700000000 - 30


# ─── request_device_code ────────────────────────────────────────────────────


class TestRequestDeviceCode:
    def test_success(self) -> None:
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "device_code": "dc-123",
                        "user_code": "ABCD-EFGH",
                        "verification_uri": "https://auth.x.ai/device",
                        "interval": 5,
                        "expires_in": 600,
                    },
                )
            ]
        )
        with httpx.Client(transport=transport) as client:
            grant = request_device_code(client=client)
        assert grant.device_code == "dc-123"
        assert grant.user_code == "ABCD-EFGH"
        assert grant.verification_uri == "https://auth.x.ai/device"
        assert grant.interval == 5
        assert grant.expires_in == 600

    def test_failure_classified(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "invalid_client", "error_description": "denied"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            request_device_code(client=client)
        assert exc_info.value.failure == GrokAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True


# ─── poll_device_token ──────────────────────────────────────────────────────


class TestPollDeviceToken:
    def test_pending_then_success(self) -> None:
        """authorization_pending → pending, then 200 with tokens."""
        exp = time.time() + 3600
        transport = _mock_handler(
            [
                (400, {"error": "authorization_pending"}),
                (
                    200,
                    {
                        "access_token": _make_jwt({"exp": exp}),
                        "refresh_token": "rt-poll-xyz",
                        "id_token": None,
                        "expires_in": 3600,
                    },
                ),
            ]
        )
        grant = DeviceCodeGrant(
            device_code="dc-abc",
            user_code="XXXX-YYYY",
            verification_uri="https://auth.x.ai/device",
            interval=0,  # no sleep in tests
            expires_in=600,
        )
        with httpx.Client(transport=transport) as client:
            tokens = poll_device_token(grant, client=client, now=time.time())
        assert tokens.refresh_token == "rt-poll-xyz"
        assert tokens.access_token.startswith("ey")

    def test_slow_down_increases_interval(self) -> None:
        exp = time.time() + 3600
        transport = _mock_handler(
            [
                (400, {"error": "slow_down"}),
                (400, {"error": "authorization_pending"}),
                (
                    200,
                    {
                        "access_token": _make_jwt({"exp": exp}),
                        "refresh_token": "rt-slow",
                        "expires_in": 3600,
                    },
                ),
            ]
        )
        grant = DeviceCodeGrant(
            device_code="dc-slow",
            user_code="ZZZZ-ZZZZ",
            verification_uri="https://auth.x.ai/device",
            interval=0,
            expires_in=600,
        )
        with httpx.Client(transport=transport) as client:
            tokens = poll_device_token(grant, client=client, now=time.time())
        assert tokens.refresh_token == "rt-slow"

    def test_expired_grant_raises_transient(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "authorization_pending"})]
        )
        grant = DeviceCodeGrant(
            device_code="dc-expired",
            user_code="EEEE-EEEE",
            verification_uri="https://auth.x.ai/device",
            interval=0,
            expires_in=0,  # already expired
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            poll_device_token(grant, client=client, now=time.time())
        assert exc_info.value.failure == GrokAuthFailure.TRANSIENT
        assert "expired" in exc_info.value.detail.lower()

    def test_403_during_poll_is_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "access_denied", "error_description": "tier"})]
        )
        grant = DeviceCodeGrant(
            device_code="dc-403",
            user_code="FFFF-FFFF",
            verification_uri="https://auth.x.ai/device",
            interval=0,
            expires_in=600,
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            poll_device_token(grant, client=client, now=time.time())
        assert exc_info.value.failure == GrokAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True

    def test_invalid_grant_is_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "revoked"})]
        )
        grant = DeviceCodeGrant(
            device_code="dc-revoked",
            user_code="GGGG-GGGG",
            verification_uri="https://auth.x.ai/device",
            interval=0,
            expires_in=600,
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            poll_device_token(grant, client=client, now=time.time())
        assert exc_info.value.failure == GrokAuthFailure.RELOGIN_REQUIRED


# ─── refresh_grok_token ─────────────────────────────────────────────────────


class TestRefreshGrokToken:
    def test_success_with_rotation(self) -> None:
        """Refresh returns new access + rotated refresh token."""
        exp = time.time() + 3600
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": _make_jwt({"exp": exp}),
                        "refresh_token": "rt-rotated-new",
                        "id_token": _make_jwt({"sub": "u"}),
                        "expires_in": 3600,
                    },
                )
            ]
        )
        with httpx.Client(transport=transport) as client:
            tokens = refresh_grok_token("rt-old-abc", client=client)
        assert tokens.refresh_token == "rt-rotated-new"
        assert tokens.access_token.startswith("ey")

    def test_preserves_refresh_when_server_omits_rotation(self) -> None:
        """If server doesn't return a new refresh_token, keep the old one."""
        exp = time.time() + 3600
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": _make_jwt({"exp": exp}),
                        "expires_in": 3600,
                        # no refresh_token in response
                    },
                )
            ]
        )
        with httpx.Client(transport=transport) as client:
            tokens = refresh_grok_token("rt-keep-me", client=client)
        assert tokens.refresh_token == "rt-keep-me"

    def test_403_is_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "forbidden", "error_description": "no access"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt-x", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TIER_DENIED

    def test_401_is_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "invalid_grant", "error_description": "revoked"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt-revoked", client=client)
        assert exc_info.value.failure == GrokAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True

    def test_400_invalid_grant_is_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt-bad", client=client)
        assert exc_info.value.failure == GrokAuthFailure.RELOGIN_REQUIRED

    def test_429_is_transient(self) -> None:
        transport = _mock_handler(
            [(429, {"error": "rate_limited", "error_description": "slow down"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt-rate", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TRANSIENT
        assert exc_info.value.terminal is False

    def test_500_is_transient(self) -> None:
        transport = _mock_handler(
            [(500, {"error": "server_error", "error_description": "oops"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt-500", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TRANSIENT


# ─── BYOK store integration ─────────────────────────────────────────────────


class TestStoreIntegration:
    def test_store_and_load_round_trip(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        exp = time.time() + 3600
        tokens = XaiTokens(
            access_token=_make_jwt({"exp": exp}),
            refresh_token="rt-store-test",
            id_token=_make_jwt({"sub": "user-1"}),
            expires_at=exp - 30,
        )
        cred_id = store_grok_tokens(
            tokens,
            "user-1",
            artifact_path=artifact,
            key_bytes=_KEY,
        )
        assert cred_id.startswith("cred-x-")

        loaded = load_grok_tokens(cred_id, artifact_path=artifact, key_bytes=_KEY)
        assert loaded.access_token == tokens.access_token
        assert loaded.refresh_token == "rt-store-test"
        assert loaded.id_token == tokens.id_token
        assert loaded.expires_at == tokens.expires_at

    def test_token_never_in_metadata(self, tmp_path: Any) -> None:
        """Metadata lists cred_id/handle/pipeline_kind but NEVER the token."""
        artifact = str(tmp_path / "creds.enc")
        tokens = XaiTokens(
            access_token="super-secret-at",
            refresh_token="super-secret-rt",
            id_token=None,
            expires_at=9999999999.0,
        )
        store_grok_tokens(tokens, "user-x", artifact_path=artifact, key_bytes=_KEY)
        metas = list_credentials(artifact_path=artifact)
        assert len(metas) == 1
        meta = metas[0]
        assert meta.pipeline_kind == "grok_oauth"
        assert meta.owner_user_id == "user-x"
        # The raw artifact must not contain the plaintext tokens.
        raw = (tmp_path / "creds.enc").read_text()
        assert "super-secret-at" not in raw
        assert "super-secret-rt" not in raw

    def test_find_grok_cred_id(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = XaiTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        cred_id = store_grok_tokens(
            tokens, "user-findme", artifact_path=artifact, key_bytes=_KEY
        )
        assert find_grok_cred_id("user-findme", artifact_path=artifact) == cred_id
        assert find_grok_cred_id("user-nobody", artifact_path=artifact) is None

    def test_delete_grok_tokens(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = XaiTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        cred_id = store_grok_tokens(
            tokens, "user-del", artifact_path=artifact, key_bytes=_KEY
        )
        assert delete_grok_tokens(cred_id, artifact_path=artifact) is True
        assert delete_grok_tokens(cred_id, artifact_path=artifact) is False
        assert find_grok_cred_id("user-del", artifact_path=artifact) is None

    def test_quarantine_deletes_user_tokens(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = XaiTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        store_grok_tokens(tokens, "user-q", artifact_path=artifact, key_bytes=_KEY)
        assert quarantine_grok_tokens("user-q", artifact_path=artifact) is True
        assert find_grok_cred_id("user-q", artifact_path=artifact) is None

    def test_quarantine_noop_when_absent(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        assert quarantine_grok_tokens("user-none", artifact_path=artifact) is False

    def test_users_are_isolated(self, tmp_path: Any) -> None:
        """User A's tokens are invisible/decoupled from user B's."""
        artifact = str(tmp_path / "creds.enc")
        tokens_a = XaiTokens(
            access_token="at-a", refresh_token="rt-a", id_token=None, expires_at=1.0
        )
        tokens_b = XaiTokens(
            access_token="at-b", refresh_token="rt-b", id_token=None, expires_at=2.0
        )
        cred_a = store_grok_tokens(
            tokens_a, "user-a", artifact_path=artifact, key_bytes=_KEY
        )
        cred_b = store_grok_tokens(
            tokens_b, "user-b", artifact_path=artifact, key_bytes=_KEY
        )
        loaded_a = load_grok_tokens(cred_a, artifact_path=artifact, key_bytes=_KEY)
        loaded_b = load_grok_tokens(cred_b, artifact_path=artifact, key_bytes=_KEY)
        assert loaded_a.access_token == "at-a"
        assert loaded_b.access_token == "at-b"

        # Deleting A doesn't affect B.
        delete_grok_tokens(cred_a, artifact_path=artifact)
        assert find_grok_cred_id("user-a", artifact_path=artifact) is None
        assert find_grok_cred_id("user-b", artifact_path=artifact) == cred_b


# ─── Failure taxonomy completeness ──────────────────────────────────────────


class TestFailureTaxonomy:
    def test_403_always_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "anything", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True
        assert "XAI_API_KEY" in exc_info.value.detail

    def test_400_invalid_grant_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt", client=client)
        assert exc_info.value.failure == GrokAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True
        assert "quarantine" in exc_info.value.detail.lower()

    def test_401_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "unauthorized", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt", client=client)
        assert exc_info.value.failure == GrokAuthFailure.RELOGIN_REQUIRED

    def test_429_transient(self) -> None:
        transport = _mock_handler(
            [(429, {"error": "rate_limit", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TRANSIENT
        assert exc_info.value.terminal is False

    def test_500_transient(self) -> None:
        transport = _mock_handler(
            [(500, {"error": "server_error", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TRANSIENT

    def test_502_transient(self) -> None:
        transport = _mock_handler(
            [(502, {"error": "bad_gateway", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(GrokAuthError) as exc_info:
            refresh_grok_token("rt", client=client)
        assert exc_info.value.failure == GrokAuthFailure.TRANSIENT
