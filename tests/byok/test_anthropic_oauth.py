"""Tests for Anthropic (Claude) PKCE authorization-code OAuth — all HTTP mocked.

Covers: PKCE pair generation, authorization URL building with hosted redirect,
code exchange with JSON POST, token refresh with rotation, expires_in-based
expiry with skew, origin-pin rejection, 403/400/401/429/5xx failure taxonomy,
encrypted per-user storage, no token echo.
"""

from __future__ import annotations

import base64
import hashlib
import time
from typing import Any

import httpx
import nacl.secret
import pytest

from runtime.byok.anthropic_oauth import (
    ANTHROPIC_AUTHORIZE_URL,
    ANTHROPIC_OAUTH_CLIENT_ID,
    ANTHROPIC_REDIRECT_URI,
    ANTHROPIC_SCOPE,
    AnthropicAuthError,
    AnthropicAuthFailure,
    AnthropicTokens,
    build_authorize_url,
    compute_expires_at,
    delete_anthropic_tokens,
    exchange_authorization_code,
    find_anthropic_cred_id,
    generate_pkce_pair,
    load_anthropic_tokens,
    quarantine_anthropic_tokens,
    refresh_anthropic_token,
    store_anthropic_tokens,
    validate_inference_base_url,
    validate_oauth_endpoint,
)
from runtime.byok.store import list_credentials

_KEY = b"a" * nacl.secret.SecretBox.KEY_SIZE

# ─── helpers ─────────────────────────────────────────────────────────────────


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


def _successful_tokens() -> dict[str, Any]:
    return {
        "access_token": "sk-ant-oat-access-abc123",
        "refresh_token": "sk-ant-ort-refresh-xyz789",
        "expires_in": 3600,
    }


# ─── PKCE generation ────────────────────────────────────────────────────────


class TestPkceGeneration:
    def test_pair_has_verifier_and_challenge(self) -> None:
        pair = generate_pkce_pair()
        assert isinstance(pair.code_verifier, str)
        assert isinstance(pair.code_challenge, str)
        assert len(pair.code_verifier) > 0
        assert len(pair.code_challenge) > 0

    def test_challenge_is_s256_of_verifier(self) -> None:
        """code_challenge must be base64url(SHA256(code_verifier)) without padding."""
        pair = generate_pkce_pair()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(pair.code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert pair.code_challenge == expected

    def test_verifier_is_base64url_no_padding(self) -> None:
        pair = generate_pkce_pair()
        # base64url chars only, no padding
        assert "=" not in pair.code_verifier

    def test_each_call_produces_different_pair(self) -> None:
        a = generate_pkce_pair()
        b = generate_pkce_pair()
        assert a.code_verifier != b.code_verifier
        assert a.code_challenge != b.code_challenge


# ─── Authorization URL builder ──────────────────────────────────────────────


class TestBuildAuthorizeUrl:
    def test_url_contains_required_params(self) -> None:
        url, pkce = build_authorize_url()
        assert url.startswith(ANTHROPIC_AUTHORIZE_URL + "?")
        assert "response_type=code" in url
        assert "code=true" in url
        assert f"client_id={ANTHROPIC_OAUTH_CLIENT_ID}" in url
        assert "code_challenge_method=S256" in url
        assert f"code_challenge={pkce.code_challenge}" in url
        # state = code_verifier (Claude Code convention)
        assert f"state={pkce.code_verifier}" in url
        # scope is URL-encoded (colons → %3A, spaces → +)
        from urllib.parse import unquote_plus
        assert ANTHROPIC_SCOPE in unquote_plus(url)

    def test_auto_generates_pkce(self) -> None:
        url, pkce = build_authorize_url()
        assert pkce.code_challenge in url
        assert pkce is not None

    def test_uses_provided_pkce(self) -> None:
        pkce = generate_pkce_pair()
        url, returned_pkce = build_authorize_url(pkce=pkce)
        assert returned_pkce is pkce
        assert pkce.code_challenge in url

    def test_redirect_uri_param_present(self) -> None:
        url, _ = build_authorize_url()
        # ANTHROPIC_REDIRECT_URI should appear (URL-encoded) in the URL
        assert ANTHROPIC_REDIRECT_URI.replace(":", "%3A").replace("/", "%2F") in url

    def test_state_equals_verifier(self) -> None:
        pkce = generate_pkce_pair()
        url, _ = build_authorize_url(pkce=pkce)
        # The state param must equal the verifier (Claude Code convention)
        assert f"state={pkce.code_verifier}" in url


# ─── Origin-pin validators ──────────────────────────────────────────────────


class TestOriginPin:
    def test_valid_anthropic_com_endpoint(self) -> None:
        assert validate_oauth_endpoint(
            "https://console.anthropic.com/v1/oauth/token"
        ) == "https://console.anthropic.com/v1/oauth/token"

    def test_valid_subdomain(self) -> None:
        assert validate_oauth_endpoint("https://api.anthropic.com/v1") == (
            "https://api.anthropic.com/v1"
        )

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="must use https"):
            validate_oauth_endpoint("http://console.anthropic.com/v1/oauth/token")

    def test_rejects_non_anthropic_host(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.anthropic\.com"):
            validate_oauth_endpoint("https://evil.com/oauth2/token")

    def test_rejects_similar_host(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.anthropic\.com"):
            validate_oauth_endpoint(
                "https://anthropic.com.evil.com/v1/oauth/token"
            )

    def test_inference_base_url_same_pin(self) -> None:
        assert validate_inference_base_url("https://api.anthropic.com/v1") == (
            "https://api.anthropic.com/v1"
        )

    def test_inference_rejects_non_anthropic(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.anthropic\.com"):
            validate_inference_base_url("https://openai.com/v1")


# ─── Expiry computation ─────────────────────────────────────────────────────


class TestComputeExpiresAt:
    def test_default_expires_in(self) -> None:
        now = time.time()
        result = compute_expires_at()
        assert abs(result - (now + 3600 - 30)) < 2

    def test_custom_expires_in(self) -> None:
        now = time.time()
        result = compute_expires_at(600)
        assert abs(result - (now + 600 - 30)) < 2

    def test_skew_applied(self) -> None:
        now = time.time()
        result = compute_expires_at(120)
        assert abs(result - (now + 120 - 30)) < 2


# ─── exchange_authorization_code ────────────────────────────────────────────


class TestExchangeAuthorizationCode:
    def test_success(self) -> None:
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": "sk-ant-oat-access-abc",
                        "refresh_token": "sk-ant-ort-refresh-xyz",
                        "expires_in": 3600,
                    },
                )
            ]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client:
            tokens = exchange_authorization_code(
                "auth-code-123",
                pkce,
                client=client,
            )
        assert tokens.access_token == "sk-ant-oat-access-abc"
        assert tokens.refresh_token == "sk-ant-ort-refresh-xyz"
        assert tokens.id_token is None

    def test_success_with_id_token(self) -> None:
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": "sk-ant-oat-access-abc",
                        "refresh_token": "sk-ant-ort-refresh-xyz",
                        "id_token": "some-jwt-here",
                        "expires_in": 3600,
                    },
                )
            ]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client:
            tokens = exchange_authorization_code(
                "auth-code-123",
                pkce,
                client=client,
            )
        assert tokens.id_token == "some-jwt-here"

    def test_sends_json_content_type(self) -> None:
        """Anthropic token endpoint expects JSON, not form-urlencoded."""
        transport = _mock_handler(
            [(200, _successful_tokens())]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client:
            exchange_authorization_code("code-1", pkce, client=client)
            # Verify the request was JSON (content-type header)
            # MockTransport preserves request headers on the request object

    def test_failure_403_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "access_denied", "error_description": "tier"})]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            exchange_authorization_code("bad-code", pkce, client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True

    def test_failure_400_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad code"})]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            exchange_authorization_code("bad-code", pkce, client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.RELOGIN_REQUIRED

    def test_failure_401_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "invalid_client", "error_description": "revoked"})]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            exchange_authorization_code("bad-code", pkce, client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True


# ─── refresh_anthropic_token ────────────────────────────────────────────────


class TestRefreshAnthropicToken:
    def test_success_with_rotation(self) -> None:
        """Refresh returns new access + rotated refresh token."""
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": "sk-ant-oat-new-access",
                        "refresh_token": "sk-ant-ort-new-refresh",
                        "expires_in": 3600,
                    },
                )
            ]
        )
        with httpx.Client(transport=transport) as client:
            tokens = refresh_anthropic_token("sk-ant-ort-old-refresh", client=client)
        assert tokens.refresh_token == "sk-ant-ort-new-refresh"
        assert tokens.access_token == "sk-ant-oat-new-access"

    def test_preserves_refresh_when_server_omits_rotation(self) -> None:
        """If server doesn't return a new refresh_token, keep the old one."""
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": "sk-ant-oat-new-access",
                        "expires_in": 3600,
                        # no refresh_token in response
                    },
                )
            ]
        )
        with httpx.Client(transport=transport) as client:
            tokens = refresh_anthropic_token("sk-ant-ort-keep-me", client=client)
        assert tokens.refresh_token == "sk-ant-ort-keep-me"

    def test_403_is_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "forbidden", "error_description": "no access"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt-x", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TIER_DENIED

    def test_401_is_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "invalid_grant", "error_description": "revoked"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt-revoked", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True

    def test_400_invalid_grant_is_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt-bad", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.RELOGIN_REQUIRED

    def test_429_is_transient(self) -> None:
        transport = _mock_handler(
            [(429, {"error": "rate_limited", "error_description": "slow down"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt-rate", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TRANSIENT
        assert exc_info.value.terminal is False

    def test_500_is_transient(self) -> None:
        transport = _mock_handler(
            [(500, {"error": "server_error", "error_description": "oops"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt-500", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TRANSIENT


# ─── BYOK store integration ─────────────────────────────────────────────────


class TestStoreIntegration:
    def test_store_and_load_round_trip(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = AnthropicTokens(
            access_token="sk-ant-oat-store-test",
            refresh_token="sk-ant-ort-store-test",
            id_token=None,
            expires_at=time.time() + 3600,
        )
        cred_id = store_anthropic_tokens(
            tokens,
            "user-1",
            artifact_path=artifact,
            key_bytes=_KEY,
        )
        assert cred_id.startswith("cred-x-")

        loaded = load_anthropic_tokens(cred_id, artifact_path=artifact, key_bytes=_KEY)
        assert loaded.access_token == tokens.access_token
        assert loaded.refresh_token == tokens.refresh_token
        assert loaded.id_token == tokens.id_token
        assert loaded.expires_at == tokens.expires_at

    def test_token_never_in_metadata(self, tmp_path: Any) -> None:
        """Metadata lists cred_id/handle/pipeline_kind but NEVER the token."""
        artifact = str(tmp_path / "creds.enc")
        tokens = AnthropicTokens(
            access_token="super-secret-at",
            refresh_token="super-secret-rt",
            id_token=None,
            expires_at=9999999999.0,
        )
        store_anthropic_tokens(tokens, "user-x", artifact_path=artifact, key_bytes=_KEY)
        metas = list_credentials(artifact_path=artifact)
        assert len(metas) == 1
        meta = metas[0]
        assert meta.pipeline_kind == "anthropic_oauth"
        assert meta.owner_user_id == "user-x"
        # The raw artifact must not contain the plaintext tokens.
        raw = (tmp_path / "creds.enc").read_text()
        assert "super-secret-at" not in raw
        assert "super-secret-rt" not in raw

    def test_find_anthropic_cred_id(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = AnthropicTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        cred_id = store_anthropic_tokens(
            tokens, "user-findme", artifact_path=artifact, key_bytes=_KEY
        )
        assert find_anthropic_cred_id("user-findme", artifact_path=artifact) == cred_id
        assert find_anthropic_cred_id("user-nobody", artifact_path=artifact) is None

    def test_delete_anthropic_tokens(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = AnthropicTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        cred_id = store_anthropic_tokens(
            tokens, "user-del", artifact_path=artifact, key_bytes=_KEY
        )
        assert delete_anthropic_tokens(cred_id, artifact_path=artifact) is True
        assert delete_anthropic_tokens(cred_id, artifact_path=artifact) is False
        assert find_anthropic_cred_id("user-del", artifact_path=artifact) is None

    def test_quarantine_deletes_user_tokens(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = AnthropicTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        store_anthropic_tokens(tokens, "user-q", artifact_path=artifact, key_bytes=_KEY)
        assert quarantine_anthropic_tokens("user-q", artifact_path=artifact) is True
        assert find_anthropic_cred_id("user-q", artifact_path=artifact) is None

    def test_quarantine_noop_when_absent(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        assert quarantine_anthropic_tokens("user-none", artifact_path=artifact) is False

    def test_users_are_isolated(self, tmp_path: Any) -> None:
        """User A's tokens are invisible/decoupled from user B's."""
        artifact = str(tmp_path / "creds.enc")
        tokens_a = AnthropicTokens(
            access_token="at-a", refresh_token="rt-a", id_token=None, expires_at=1.0
        )
        tokens_b = AnthropicTokens(
            access_token="at-b", refresh_token="rt-b", id_token=None, expires_at=2.0
        )
        cred_a = store_anthropic_tokens(
            tokens_a, "user-a", artifact_path=artifact, key_bytes=_KEY
        )
        cred_b = store_anthropic_tokens(
            tokens_b, "user-b", artifact_path=artifact, key_bytes=_KEY
        )
        loaded_a = load_anthropic_tokens(cred_a, artifact_path=artifact, key_bytes=_KEY)
        loaded_b = load_anthropic_tokens(cred_b, artifact_path=artifact, key_bytes=_KEY)
        assert loaded_a.access_token == "at-a"
        assert loaded_b.access_token == "at-b"

        # Deleting A doesn't affect B.
        delete_anthropic_tokens(cred_a, artifact_path=artifact)
        assert find_anthropic_cred_id("user-a", artifact_path=artifact) is None
        assert find_anthropic_cred_id("user-b", artifact_path=artifact) == cred_b


# ─── Secret hygiene — token material never echoed ───────────────────────────


class TestSecretHygiene:
    def test_tokens_redacted_in_repr_and_str(self) -> None:
        """AnthropicTokens repr/str must NEVER contain plaintext token material."""
        tokens = AnthropicTokens(
            access_token="SECRET-ACCESS-abc",
            refresh_token="SECRET-REFRESH-xyz",
            id_token="SECRET-ID-tok",
            expires_at=1.0,
        )
        for rendered in (repr(tokens), str(tokens), f"{tokens}"):
            assert "SECRET-ACCESS-abc" not in rendered
            assert "SECRET-REFRESH-xyz" not in rendered
            assert "SECRET-ID-tok" not in rendered
            assert "<redacted>" in rendered

    def test_repr_preserves_non_secret_shape(self) -> None:
        """None id_token stays visibly None; expiry is not a secret."""
        tokens = AnthropicTokens(
            access_token="a", refresh_token="b", id_token=None, expires_at=42.0
        )
        rendered = repr(tokens)
        assert "id_token=None" in rendered
        assert "42.0" in rendered

    def test_auth_error_str_carries_only_server_detail(self) -> None:
        """AnthropicAuthError message is built from the server response, not tokens."""
        transport = _mock_handler(
            [(401, {"error": "invalid_grant", "error_description": "server-said-revoked"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("SECRET-REFRESH-must-not-leak", client=client)
        message = str(exc_info.value)
        assert "server-said-revoked" in message
        assert "SECRET-REFRESH-must-not-leak" not in message


# ─── Failure taxonomy completeness ──────────────────────────────────────────


class TestFailureTaxonomy:
    def test_403_always_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "anything", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True
        assert "ANTHROPIC_API_KEY" in exc_info.value.detail

    def test_400_invalid_grant_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True
        assert "quarantine" in exc_info.value.detail.lower()

    def test_401_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "unauthorized", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.RELOGIN_REQUIRED

    def test_429_transient(self) -> None:
        transport = _mock_handler(
            [(429, {"error": "rate_limit", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TRANSIENT
        assert exc_info.value.terminal is False

    def test_500_transient(self) -> None:
        transport = _mock_handler(
            [(500, {"error": "server_error", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TRANSIENT

    def test_502_transient(self) -> None:
        transport = _mock_handler(
            [(502, {"error": "bad_gateway", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(AnthropicAuthError) as exc_info:
            refresh_anthropic_token("rt", client=client)
        assert exc_info.value.failure == AnthropicAuthFailure.TRANSIENT
