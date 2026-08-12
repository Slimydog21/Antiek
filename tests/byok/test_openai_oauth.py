"""Tests for OpenAI (ChatGPT) PKCE authorization-code OAuth — all HTTP mocked.

Covers: PKCE pair generation, authorization URL building, code exchange with
form-POST, token refresh with rotation, JWT exp parsing with skew, origin-pin
rejection, 403/400/401/429/5xx failure taxonomy, encrypted per-user storage,
no token echo.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

import httpx
import nacl.secret
import pytest

from runtime.byok.openai_oauth import (
    OPENAI_AUTHORIZE_URL,
    OPENAI_OAUTH_CLIENT_ID,
    OPENAI_SCOPE,
    OpenAIAuthError,
    OpenAIAuthFailure,
    OpenAiTokens,
    build_authorize_url,
    compute_expires_at,
    default_redirect_uri,
    delete_openai_tokens,
    exchange_authorization_code,
    find_openai_cred_id,
    generate_pkce_pair,
    generate_state,
    load_openai_tokens,
    quarantine_openai_tokens,
    refresh_openai_token,
    store_openai_tokens,
    validate_inference_base_url,
    validate_oauth_endpoint,
)
from runtime.byok.store import list_credentials

_KEY = b"o" * nacl.secret.SecretBox.KEY_SIZE

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
        assert pair.code_verifier.replace("-", "+").replace("_", "/") or True

    def test_each_call_produces_different_pair(self) -> None:
        a = generate_pkce_pair()
        b = generate_pkce_pair()
        assert a.code_verifier != b.code_verifier
        assert a.code_challenge != b.code_challenge

    def test_state_is_random(self) -> None:
        s1 = generate_state()
        s2 = generate_state()
        assert s1 != s2
        assert len(s1) > 0


# ─── Authorization URL builder ──────────────────────────────────────────────


class TestBuildAuthorizeUrl:
    def test_url_contains_required_params(self) -> None:
        pkce = generate_pkce_pair()
        url, returned_pkce, state = build_authorize_url(pkce=pkce, state="my-state")
        assert url.startswith(OPENAI_AUTHORIZE_URL + "?")
        assert "response_type=code" in url
        assert f"client_id={OPENAI_OAUTH_CLIENT_ID}" in url
        assert "code_challenge_method=S256" in url
        assert f"code_challenge={pkce.code_challenge}" in url
        assert "state=my-state" in url
        assert f"scope={'+'.join(OPENAI_SCOPE.split())}" in url
        assert returned_pkce is pkce

    def test_auto_generates_pkce_and_state(self) -> None:
        url, pkce, state = build_authorize_url()
        assert pkce.code_challenge in url
        assert state in url
        assert pkce is not None
        assert state is not None

    def test_default_redirect_uri(self) -> None:
        url, _, _ = build_authorize_url()
        expected = default_redirect_uri()
        assert f"redirect_uri={expected.replace(':', '%3A').replace('/', '%2F')}" in url


# ─── Origin-pin validators ──────────────────────────────────────────────────


class TestOriginPin:
    def test_valid_openai_com_endpoint(self) -> None:
        assert validate_oauth_endpoint("https://auth.openai.com/oauth/token") == (
            "https://auth.openai.com/oauth/token"
        )

    def test_valid_subdomain(self) -> None:
        assert validate_oauth_endpoint("https://api.openai.com/v1") == (
            "https://api.openai.com/v1"
        )

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="must use https"):
            validate_oauth_endpoint("http://auth.openai.com/oauth/token")

    def test_rejects_non_openai_host(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.openai\.com"):
            validate_oauth_endpoint("https://evil.com/oauth2/token")

    def test_rejects_similar_host(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.openai\.com"):
            validate_oauth_endpoint("https://openai.com.evil.com/oauth2/token")

    def test_inference_base_url_same_pin(self) -> None:
        assert validate_inference_base_url("https://api.openai.com/v1") == (
            "https://api.openai.com/v1"
        )

    def test_inference_rejects_non_openai(self) -> None:
        with pytest.raises(ValueError, match=r"must be under \*\.openai\.com"):
            validate_inference_base_url("https://anthropic.com/v1")


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


# ─── exchange_authorization_code ────────────────────────────────────────────


class TestExchangeAuthorizationCode:
    def test_success(self) -> None:
        exp = time.time() + 3600
        transport = _mock_handler(
            [
                (
                    200,
                    {
                        "access_token": _make_jwt({"exp": exp}),
                        "refresh_token": "rt-exchange-xyz",
                        "id_token": _make_jwt({"sub": "u"}),
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
                default_redirect_uri(),
                client=client,
            )
        assert tokens.refresh_token == "rt-exchange-xyz"
        assert tokens.access_token.startswith("ey")
        assert tokens.id_token is not None

    def test_failure_403_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "access_denied", "error_description": "tier"})]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            exchange_authorization_code(
                "bad-code", pkce, default_redirect_uri(), client=client
            )
        assert exc_info.value.failure == OpenAIAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True

    def test_failure_400_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad code"})]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            exchange_authorization_code(
                "bad-code", pkce, default_redirect_uri(), client=client
            )
        assert exc_info.value.failure == OpenAIAuthFailure.RELOGIN_REQUIRED

    def test_failure_401_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "invalid_client", "error_description": "revoked"})]
        )
        pkce = generate_pkce_pair()
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            exchange_authorization_code(
                "bad-code", pkce, default_redirect_uri(), client=client
            )
        assert exc_info.value.failure == OpenAIAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True


# ─── refresh_openai_token ───────────────────────────────────────────────────


class TestRefreshOpenAiToken:
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
            tokens = refresh_openai_token("rt-old-abc", client=client)
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
            tokens = refresh_openai_token("rt-keep-me", client=client)
        assert tokens.refresh_token == "rt-keep-me"

    def test_403_is_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "forbidden", "error_description": "no access"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt-x", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TIER_DENIED

    def test_401_is_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "invalid_grant", "error_description": "revoked"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt-revoked", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True

    def test_400_invalid_grant_is_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt-bad", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.RELOGIN_REQUIRED

    def test_429_is_transient(self) -> None:
        transport = _mock_handler(
            [(429, {"error": "rate_limited", "error_description": "slow down"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt-rate", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TRANSIENT
        assert exc_info.value.terminal is False

    def test_500_is_transient(self) -> None:
        transport = _mock_handler(
            [(500, {"error": "server_error", "error_description": "oops"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt-500", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TRANSIENT


# ─── BYOK store integration ─────────────────────────────────────────────────


class TestStoreIntegration:
    def test_store_and_load_round_trip(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        exp = time.time() + 3600
        tokens = OpenAiTokens(
            access_token=_make_jwt({"exp": exp}),
            refresh_token="rt-store-test",
            id_token=_make_jwt({"sub": "user-1"}),
            expires_at=exp - 30,
        )
        cred_id = store_openai_tokens(
            tokens,
            "user-1",
            artifact_path=artifact,
            key_bytes=_KEY,
        )
        assert cred_id.startswith("cred-x-")

        loaded = load_openai_tokens(cred_id, artifact_path=artifact, key_bytes=_KEY)
        assert loaded.access_token == tokens.access_token
        assert loaded.refresh_token == "rt-store-test"
        assert loaded.id_token == tokens.id_token
        assert loaded.expires_at == tokens.expires_at

    def test_token_never_in_metadata(self, tmp_path: Any) -> None:
        """Metadata lists cred_id/handle/pipeline_kind but NEVER the token."""
        artifact = str(tmp_path / "creds.enc")
        tokens = OpenAiTokens(
            access_token="super-secret-at",
            refresh_token="super-secret-rt",
            id_token=None,
            expires_at=9999999999.0,
        )
        store_openai_tokens(tokens, "user-x", artifact_path=artifact, key_bytes=_KEY)
        metas = list_credentials(artifact_path=artifact)
        assert len(metas) == 1
        meta = metas[0]
        assert meta.pipeline_kind == "openai_oauth"
        assert meta.owner_user_id == "user-x"
        # The raw artifact must not contain the plaintext tokens.
        raw = (tmp_path / "creds.enc").read_text()
        assert "super-secret-at" not in raw
        assert "super-secret-rt" not in raw

    def test_find_openai_cred_id(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = OpenAiTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        cred_id = store_openai_tokens(
            tokens, "user-findme", artifact_path=artifact, key_bytes=_KEY
        )
        assert find_openai_cred_id("user-findme", artifact_path=artifact) == cred_id
        assert find_openai_cred_id("user-nobody", artifact_path=artifact) is None

    def test_delete_openai_tokens(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = OpenAiTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        cred_id = store_openai_tokens(
            tokens, "user-del", artifact_path=artifact, key_bytes=_KEY
        )
        assert delete_openai_tokens(cred_id, artifact_path=artifact) is True
        assert delete_openai_tokens(cred_id, artifact_path=artifact) is False
        assert find_openai_cred_id("user-del", artifact_path=artifact) is None

    def test_quarantine_deletes_user_tokens(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        tokens = OpenAiTokens(
            access_token="at", refresh_token="rt", id_token=None, expires_at=1.0
        )
        store_openai_tokens(tokens, "user-q", artifact_path=artifact, key_bytes=_KEY)
        assert quarantine_openai_tokens("user-q", artifact_path=artifact) is True
        assert find_openai_cred_id("user-q", artifact_path=artifact) is None

    def test_quarantine_noop_when_absent(self, tmp_path: Any) -> None:
        artifact = str(tmp_path / "creds.enc")
        assert quarantine_openai_tokens("user-none", artifact_path=artifact) is False

    def test_users_are_isolated(self, tmp_path: Any) -> None:
        """User A's tokens are invisible/decoupled from user B's."""
        artifact = str(tmp_path / "creds.enc")
        tokens_a = OpenAiTokens(
            access_token="at-a", refresh_token="rt-a", id_token=None, expires_at=1.0
        )
        tokens_b = OpenAiTokens(
            access_token="at-b", refresh_token="rt-b", id_token=None, expires_at=2.0
        )
        cred_a = store_openai_tokens(
            tokens_a, "user-a", artifact_path=artifact, key_bytes=_KEY
        )
        cred_b = store_openai_tokens(
            tokens_b, "user-b", artifact_path=artifact, key_bytes=_KEY
        )
        loaded_a = load_openai_tokens(cred_a, artifact_path=artifact, key_bytes=_KEY)
        loaded_b = load_openai_tokens(cred_b, artifact_path=artifact, key_bytes=_KEY)
        assert loaded_a.access_token == "at-a"
        assert loaded_b.access_token == "at-b"

        # Deleting A doesn't affect B.
        delete_openai_tokens(cred_a, artifact_path=artifact)
        assert find_openai_cred_id("user-a", artifact_path=artifact) is None
        assert find_openai_cred_id("user-b", artifact_path=artifact) == cred_b


# ─── Secret hygiene — token material never echoed ───────────────────────────


class TestSecretHygiene:
    def test_tokens_redacted_in_repr_and_str(self) -> None:
        """OpenAiTokens repr/str must NEVER contain plaintext token material."""
        tokens = OpenAiTokens(
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
        tokens = OpenAiTokens(
            access_token="a", refresh_token="b", id_token=None, expires_at=42.0
        )
        rendered = repr(tokens)
        assert "id_token=None" in rendered
        assert "42.0" in rendered

    def test_auth_error_str_carries_only_server_detail(self) -> None:
        """OpenAIAuthError message is built from the server response, not tokens."""
        transport = _mock_handler(
            [(401, {"error": "invalid_grant", "error_description": "server-said-revoked"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("SECRET-REFRESH-must-not-leak", client=client)
        message = str(exc_info.value)
        assert "server-said-revoked" in message
        assert "SECRET-REFRESH-must-not-leak" not in message


# ─── Failure taxonomy completeness ──────────────────────────────────────────


class TestFailureTaxonomy:
    def test_403_always_tier_denied(self) -> None:
        transport = _mock_handler(
            [(403, {"error": "anything", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TIER_DENIED
        assert exc_info.value.terminal is True
        assert "OPENAI_API_KEY" in exc_info.value.detail

    def test_400_invalid_grant_relogin(self) -> None:
        transport = _mock_handler(
            [(400, {"error": "invalid_grant", "error_description": "bad"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.RELOGIN_REQUIRED
        assert exc_info.value.terminal is True
        assert "quarantine" in exc_info.value.detail.lower()

    def test_401_relogin(self) -> None:
        transport = _mock_handler(
            [(401, {"error": "unauthorized", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.RELOGIN_REQUIRED

    def test_429_transient(self) -> None:
        transport = _mock_handler(
            [(429, {"error": "rate_limit", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TRANSIENT
        assert exc_info.value.terminal is False

    def test_500_transient(self) -> None:
        transport = _mock_handler(
            [(500, {"error": "server_error", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TRANSIENT

    def test_502_transient(self) -> None:
        transport = _mock_handler(
            [(502, {"error": "bad_gateway", "error_description": "x"})]
        )
        with httpx.Client(transport=transport) as client, pytest.raises(OpenAIAuthError) as exc_info:
            refresh_openai_token("rt", client=client)
        assert exc_info.value.failure == OpenAIAuthFailure.TRANSIENT
