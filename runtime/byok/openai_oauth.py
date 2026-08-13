"""OpenAI (ChatGPT) PKCE authorization-code OAuth — BYOT integration.

Self-contained PKCE authorization-code flow (RFC 7636 + RFC 6749 §4.1) against
``https://auth.openai.com`` as the Codex CLI public client.  One server-side
token row per user, encrypted via the byok :mod:`~runtime.byok.store`.  No
credential-pool multi-process machinery — one artifact-locked refresher
eliminates the race class the pool exists to mitigate.

This flow mirrors the one used by the official OpenAI Codex CLI (audited in
openai/codex ``codex-rs/login``).  The Codex CLI supports a device-code variant
for headless machines; this module implements the primary PKCE authorization-
code flow with a local loopback callback, which is what the operator's hosted
deployment would use.

MECHANISM
---------
1. ``generate_pkce_pair()`` → PKCE code_verifier + S256 code_challenge.
2. ``build_authorize_url()`` → user opens in browser, signs in to ChatGPT,
   browser redirects to ``http://localhost:<port>/auth/callback?code=…&state=…``.
3. ``exchange_authorization_code()`` → POST to the token endpoint with the
   authorization code and code_verifier.
4. ``refresh_openai_token()`` → pure form-POST to the token endpoint.
5. Origin-pin validators reject anything that is not ``https`` + ``*.openai.com``.
6. JWT ``exp`` claim (with adaptive skew) drives expiry, not ``expires_in``.

FAILURE TAXONOMY (BYOT UX states)
----------------------------------
- 403 → ``openai_tier_denied`` (terminal; suggest paste ``OPENAI_API_KEY``).
- 400/401 (``invalid_grant`` / revoked / reused) → ``openai_relogin_required``
  (terminal; quarantine tokens, require re-onboard).
- 429/5xx → ``openai_transient`` (retry; never quarantine).

GO-LIVE PREREQUISITE
--------------------
This module reuses the Codex CLI client_id registration
(``app_EMoamEEZ73f0CkXaXp7hrann``).  For a production deployment the operator
MUST register their own OAuth application at platform.openai.com to obtain a
dedicated client_id/client_secret and approved redirect URIs.  See
``docs/specs/byot-oauth-2026-08-12.md`` for the go-live checklist.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

# ─── OpenAI OAuth constants (from Codex CLI registration) ───────────────────
OPENAI_ISSUER: str = "https://auth.openai.com"
OPENAI_AUTHORIZE_URL: str = "https://auth.openai.com/oauth/authorize"
OPENAI_TOKEN_URL: str = "https://auth.openai.com/oauth/token"
OPENAI_REVOKE_URL: str = "https://auth.openai.com/oauth/revoke"
OPENAI_OAUTH_CLIENT_ID: str = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_SCOPE: str = (
    "openid profile email offline_access "
    "api.connectors.read api.connectors.invoke"
)
OPENAI_INFERENCE_BASE: str = "https://api.openai.com/v1"
OPENAI_DEFAULT_REDIRECT_PORT: int = 1455
OPENAI_FALLBACK_REDIRECT_PORT: int = 1457
OPENAI_REDIRECT_PATH: str = "/auth/callback"

# Adaptive skew for JWT expiry — clamp to avoid burning single-use refresh
# tokens on every request for ~15-min authorization-code JWTs.
_EXPIRY_SKEW_S: int = 30


# ─── Failure taxonomy ────────────────────────────────────────────────────────


class OpenAIAuthFailure(Enum):
    """BYOT UX failure states for OpenAI PKCE OAuth."""

    TIER_DENIED = "openai_tier_denied"  # 403 — terminal, suggest paste key
    RELOGIN_REQUIRED = "openai_relogin_required"  # 400/401 — quarantine
    TRANSIENT = "openai_transient"  # 429/5xx — retry


@dataclass(frozen=True)
class OpenAIAuthError(Exception):
    """Structured error from the authorization-code or refresh flow."""

    failure: OpenAIAuthFailure
    status_code: int
    detail: str
    terminal: bool = False

    def __str__(self) -> str:
        return self.detail


# ─── PKCE ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PkceCodes:
    """PKCE verifier + S256 challenge pair (RFC 7636).

    ``__repr__`` / ``__str__`` do NOT redact the verifier: the verifier is a
    nonce that is only useful together with a valid authorization code, and it
    must be visible to the caller to complete the token exchange.  The token
    material (access/refresh tokens) is what gets redacted, not PKCE codes.
    """

    code_verifier: str
    code_challenge: str


def generate_pkce_pair() -> PkceCodes:
    """Generate a cryptographically secure PKCE pair (S256).

    Matches the Codex CLI's ``generate_pkce()``: 64 random bytes → base64url
    (no padding) verifier; SHA256(verifier) → base64url (no padding) challenge.
    """
    verifier_bytes = secrets.token_bytes(64)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")
    challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")
    return PkceCodes(code_verifier=code_verifier, code_challenge=code_challenge)


def generate_state() -> str:
    """Generate a cryptographically random ``state`` parameter for CSRF protection."""
    return secrets.token_urlsafe(32)


def default_redirect_uri(port: int = OPENAI_DEFAULT_REDIRECT_PORT) -> str:
    """Build the default loopback redirect URI for the local callback server."""
    return f"http://localhost:{port}{OPENAI_REDIRECT_PATH}"


# ─── Data shapes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpenAiTokens:
    """Token set returned by authorization-code exchange or refresh.

    ``__repr__``/``__str__`` REDACT the access, refresh and id token material so
    the secret is never spilled into a log line, an exception traceback frame
    local, or an f-string.  Plaintext egress happens only through explicit field
    access on the way into the SecretBox-encrypted store.
    """

    access_token: str
    refresh_token: str
    id_token: str | None
    expires_at: float  # unix timestamp (from JWT exp, not expires_in)

    def __repr__(self) -> str:  # secret hygiene — never echo token material
        return (
            "OpenAiTokens(access_token=<redacted>, refresh_token=<redacted>, "
            f"id_token={'<redacted>' if self.id_token is not None else None}, "
            f"expires_at={self.expires_at!r})"
        )


# ─── Origin-pin validators ──────────────────────────────────────────────────


def validate_oauth_endpoint(url: str) -> str:
    """Validate that ``url`` is ``https`` and under ``*.openai.com``.

    Raises :class:`ValueError` on violation.  Returns the validated URL.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"OAuth endpoint must use https, got: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if not (hostname == "openai.com" or hostname.endswith(".openai.com")):
        raise ValueError(f"OAuth endpoint must be under *.openai.com, got: {hostname}")
    return url


def validate_inference_base_url(url: str) -> str:
    """Validate that ``url`` is ``https`` and under ``*.openai.com``.

    Same pin as :func:`validate_oauth_endpoint` — the inference base URL must
    also be origin-pinned.
    """
    return validate_oauth_endpoint(url)


# ─── JWT exp parsing ─────────────────────────────────────────────────────────


def _parse_jwt_exp(token: str) -> float | None:
    """Extract the ``exp`` claim from a JWT without signature verification.

    Returns the unix timestamp, or ``None`` if the JWT is malformed or lacks
    ``exp``.  This is used only for *expiry scheduling*, not for security
    decisions — the server is the authority.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return None
    # Pad the payload for base64url decoding.
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        claims: dict[str, Any] = json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError):
        return None
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return float(exp)


def compute_expires_at(access_token: str, fallback_expires_in: int = 3600) -> float:
    """Compute the expiry unix timestamp from the JWT ``exp`` claim.

    Falls back to ``fallback_expires_in`` seconds from now if the JWT is
    unreadable.  Applies adaptive skew to avoid burning single-use refresh
    tokens per request.
    """
    exp = _parse_jwt_exp(access_token)
    if exp is not None:
        return exp - _EXPIRY_SKEW_S
    return time.time() + fallback_expires_in - _EXPIRY_SKEW_S


# ─── Failure classification ─────────────────────────────────────────────────


def _classify_failure(status_code: int, body: dict[str, Any]) -> OpenAIAuthError:
    """Map an HTTP error response to the BYOT failure taxonomy."""
    error_str = body.get("error", "")
    detail = body.get("error_description", body.get("message", str(body)))

    if status_code == 403:
        return OpenAIAuthError(
            failure=OpenAIAuthFailure.TIER_DENIED,
            status_code=status_code,
            detail=f"OpenAI tier denied (403): {detail}. "
            "Your plan may not be entitled to API access — "
            "paste an OPENAI_API_KEY instead.",
            terminal=True,
        )
    if status_code in (400, 401) or error_str == "invalid_grant":
        return OpenAIAuthError(
            failure=OpenAIAuthFailure.RELOGIN_REQUIRED,
            status_code=status_code,
            detail=f"OpenAI auth invalid ({status_code}): {detail}. "
            "Credential quarantined — re-onboard required.",
            terminal=True,
        )
    # 429 or 5xx → transient
    return OpenAIAuthError(
        failure=OpenAIAuthFailure.TRANSIENT,
        status_code=status_code,
        detail=f"OpenAI transient error ({status_code}): {detail}",
        terminal=False,
    )


# ─── Authorization URL builder ──────────────────────────────────────────────


def build_authorize_url(
    *,
    redirect_uri: str | None = None,
    pkce: PkceCodes | None = None,
    state: str | None = None,
    authorize_url: str = OPENAI_AUTHORIZE_URL,
    client_id: str = OPENAI_OAUTH_CLIENT_ID,
    scope: str = OPENAI_SCOPE,
) -> tuple[str, PkceCodes, str]:
    """Build the authorization URL for the user to open in a browser.

    Generates PKCE pair and state if not provided.  Returns a tuple of
    ``(authorize_url, pkce_pair, state)`` — the caller MUST retain the PKCE
    pair and state to complete the token exchange after the callback.

    The redirect URI defaults to ``http://localhost:<DEFAULT_PORT>/auth/callback``
    (the loopback callback that the local server listens on).
    """
    if pkce is None:
        pkce = generate_pkce_pair()
    if state is None:
        state = generate_state()
    if redirect_uri is None:
        redirect_uri = default_redirect_uri()
    params = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return f"{authorize_url}?{params}", pkce, state


# ─── Token exchange ─────────────────────────────────────────────────────────


def exchange_authorization_code(
    code: str,
    pkce: PkceCodes,
    redirect_uri: str,
    *,
    client: httpx.Client | None = None,
    token_url: str = OPENAI_TOKEN_URL,
    client_id: str = OPENAI_OAUTH_CLIENT_ID,
) -> OpenAiTokens:
    """Exchange an authorization code for OpenAI tokens via a form-POST.

    The PKCE ``code_verifier`` MUST match the ``code_challenge`` sent in the
    authorize request.  The ``redirect_uri`` MUST match the one used in the
    authorize request.

    Raises :class:`OpenAIAuthError` on failure.
    """
    validate_oauth_endpoint(token_url)
    http = client or httpx.Client(timeout=30.0)
    own_client = client is None
    try:
        resp = http.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": pkce.code_verifier,
            },
        )
        if resp.status_code != 200:
            raise _classify_failure(resp.status_code, resp.json())
        body = resp.json()
        access_token = body["access_token"]
        refresh_token = body["refresh_token"]
        return OpenAiTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=body.get("id_token"),
            expires_at=compute_expires_at(
                access_token,
                fallback_expires_in=body.get("expires_in", 3600),
            ),
        )
    finally:
        if own_client:
            http.close()


# ─── Token refresh ──────────────────────────────────────────────────────────


def refresh_openai_token(
    refresh_token: str,
    *,
    client: httpx.Client | None = None,
    token_url: str = OPENAI_TOKEN_URL,
    client_id: str = OPENAI_OAUTH_CLIENT_ID,
) -> OpenAiTokens:
    """Refresh an OpenAI OAuth token via a pure form-POST.

    The refresh token may be rotated by the server.  The caller must persist
    BOTH the new access and new refresh tokens in one atomic write.

    Raises :class:`OpenAIAuthError` on failure.
    """
    validate_oauth_endpoint(token_url)
    http = client or httpx.Client(timeout=30.0)
    own_client = client is None
    try:
        resp = http.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
        )
        if resp.status_code != 200:
            raise _classify_failure(resp.status_code, resp.json())
        body = resp.json()
        access_token = body["access_token"]
        new_refresh = body.get("refresh_token", refresh_token)
        return OpenAiTokens(
            access_token=access_token,
            refresh_token=new_refresh,
            id_token=body.get("id_token"),
            expires_at=compute_expires_at(
                access_token,
                fallback_expires_in=body.get("expires_in", 3600),
            ),
        )
    finally:
        if own_client:
            http.close()


# ─── BYOK store integration ─────────────────────────────────────────────────

_PIPELINE_KIND = "openai_oauth"
_ACCOUNT_HANDLE = "openai"


def store_openai_tokens(
    tokens: OpenAiTokens,
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> str:
    """Store the full token set as ONE encrypted credential in the byok store.

    Serializes ``(access_token, refresh_token, id_token, expires_at)`` as JSON
    and encrypts via :func:`~runtime.byok.store.store_credential`.  Returns the
    ``cred_id``.  The plaintext tokens are never logged or echoed.
    """
    from runtime.byok.store import store_credential

    payload = json.dumps(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "id_token": tokens.id_token,
            "expires_at": tokens.expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return store_credential(
        _ACCOUNT_HANDLE,
        payload,
        pipeline_kind=_PIPELINE_KIND,
        owner_user_id=owner_user_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
    )


def load_openai_tokens(
    cred_id: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> OpenAiTokens:
    """Load and decrypt a stored OpenAI token set.

    Returns :class:`OpenAiTokens`.  Raises ``KeyError`` if ``cred_id`` is unknown.
    """
    from runtime.byok.store import load_credential

    secret = load_credential(
        cred_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
    )
    body: dict[str, Any] = json.loads(secret.reveal())
    return OpenAiTokens(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        id_token=body.get("id_token"),
        expires_at=float(body["expires_at"]),
    )


def find_openai_cred_id(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> str | None:
    """Find the ``cred_id`` of the stored OpenAI token for ``owner_user_id``.

    Returns ``None`` if no OpenAI credential exists for this user.
    """
    from runtime.byok.store import list_credentials

    for meta in list_credentials(artifact_path=artifact_path):
        if (
            meta.pipeline_kind == _PIPELINE_KIND
            and meta.owner_user_id == owner_user_id
        ):
            return meta.cred_id
    return None


def delete_openai_tokens(
    cred_id: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    """Delete a stored OpenAI token set.  Returns ``True`` if present."""
    from runtime.byok.store import delete_credential

    return delete_credential(cred_id, artifact_path=artifact_path)


def quarantine_openai_tokens(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    """Quarantine (delete) a user's stored OpenAI tokens after auth failure.

    Called when the server returns 400/401 (invalid_grant).  Returns ``True``
    if tokens were present and deleted.
    """
    cred_id = find_openai_cred_id(owner_user_id, artifact_path=artifact_path)
    if cred_id is None:
        return False
    return delete_openai_tokens(cred_id, artifact_path=artifact_path)


__all__ = [
    "OPENAI_AUTHORIZE_URL",
    "OPENAI_DEFAULT_REDIRECT_PORT",
    "OPENAI_FALLBACK_REDIRECT_PORT",
    "OPENAI_INFERENCE_BASE",
    "OPENAI_ISSUER",
    "OPENAI_OAUTH_CLIENT_ID",
    "OPENAI_REDIRECT_PATH",
    "OPENAI_REVOKE_URL",
    "OPENAI_SCOPE",
    "OPENAI_TOKEN_URL",
    "OpenAIAuthError",
    "OpenAIAuthFailure",
    "OpenAiTokens",
    "PkceCodes",
    "build_authorize_url",
    "compute_expires_at",
    "default_redirect_uri",
    "delete_openai_tokens",
    "exchange_authorization_code",
    "find_openai_cred_id",
    "generate_pkce_pair",
    "generate_state",
    "load_openai_tokens",
    "quarantine_openai_tokens",
    "refresh_openai_token",
    "store_openai_tokens",
    "validate_inference_base_url",
    "validate_oauth_endpoint",
]
