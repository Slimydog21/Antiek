"""Anthropic (Claude) PKCE authorization-code OAuth — BYOT integration.

Self-contained PKCE authorization-code flow (RFC 7636 + RFC 6749 §4.1) against
Anthropic's Claude Code OAuth endpoints.  One server-side token row per user,
encrypted via the byok :mod:`~runtime.byok.store`.  No credential-pool
multi-process machinery — one artifact-locked refresher eliminates the race
class the pool exists to mitigate.

This flow mirrors the one used by the official Claude Code CLI
(``@anthropic-ai/claude-code``).  Unlike the OpenAI/Codex flow, the Anthropic
redirect target is Anthropic's *hosted* callback URL
(``https://console.anthropic.com/oauth/code/callback``), not a local loopback
server.  After the user signs in, Anthropic displays the authorization code on
the hosted callback page, and the user copies it back into the Antiek CLI.

MECHANISM
---------
1. ``generate_pkce_pair()`` → PKCE code_verifier + S256 code_challenge.
   The ``code_verifier`` is ALSO used as the ``state`` parameter (Claude Code
   convention), which simplifies the CSRF round-trip.
2. ``build_authorize_url()`` → user opens in browser, signs in to Anthropic,
   the hosted callback page displays the authorization code.
3. ``exchange_authorization_code()`` → JSON POST to the token endpoint with the
   authorization code and code_verifier.
4. ``refresh_anthropic_token()`` → JSON POST to the token endpoint.
5. Origin-pin validators reject anything that is not ``https`` + ``*.anthropic.com``.
6. ``expires_in`` drives expiry (Anthropic access tokens are opaque, not JWTs).

FAILURE TAXONOMY (BYOT UX states)
----------------------------------
- 403 → ``anthropic_tier_denied`` (terminal; suggest paste ``ANTHROPIC_API_KEY``).
- 400/401 (``invalid_grant`` / revoked / reused) → ``anthropic_relogin_required``
  (terminal; quarantine tokens, require re-onboard).
- 429/5xx → ``anthropic_transient`` (retry; never quarantine).

GO-LIVE PREREQUISITE
--------------------
This module reuses the Claude Code client_id registration
(``9d1c250a-e61b-44d9-88ed-5944d1962f5e``).  For a production deployment the
operator MUST register their own OAuth application at console.anthropic.com to
obtain a dedicated client_id and approved redirect URIs.  See
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

# ─── Anthropic OAuth constants (from Claude Code registration) ──────────────
ANTHROPIC_ISSUER: str = "https://console.anthropic.com"
ANTHROPIC_AUTHORIZE_URL: str = "https://claude.ai/oauth/authorize"
ANTHROPIC_TOKEN_URL: str = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_REDIRECT_URI: str = "https://console.anthropic.com/oauth/code/callback"
ANTHROPIC_OAUTH_CLIENT_ID: str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_SCOPE: str = "org:create_api_key user:profile user:inference"
ANTHROPIC_INFERENCE_BASE: str = "https://api.anthropic.com"

# Adaptive skew for token expiry.
_EXPIRY_SKEW_S: int = 30


# ─── Failure taxonomy ────────────────────────────────────────────────────────


class AnthropicAuthFailure(Enum):
    """BYOT UX failure states for Anthropic PKCE OAuth."""

    TIER_DENIED = "anthropic_tier_denied"  # 403 — terminal, suggest paste key
    RELOGIN_REQUIRED = "anthropic_relogin_required"  # 400/401 — quarantine
    TRANSIENT = "anthropic_transient"  # 429/5xx — retry


@dataclass(frozen=True)
class AnthropicAuthError(Exception):
    """Structured error from the authorization-code or refresh flow."""

    failure: AnthropicAuthFailure
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

    Uses 32 random bytes (per Claude Code convention) → base64url (no padding)
    verifier; SHA256(verifier) → base64url (no padding) challenge.
    """
    verifier_bytes = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")
    challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")
    return PkceCodes(code_verifier=code_verifier, code_challenge=code_challenge)


# ─── Data shapes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnthropicTokens:
    """Token set returned by authorization-code exchange or refresh.

    ``__repr__``/``__str__`` REDACT the access and refresh token material so
    the secret is never spilled into a log line, an exception traceback frame
    local, or an f-string.  Plaintext egress happens only through explicit field
    access on the way into the SecretBox-encrypted store.

    Anthropic access tokens are opaque (not JWTs), so ``expires_at`` is derived
    from ``expires_in`` rather than a JWT ``exp`` claim.  ``id_token`` is
    optional — the Claude Code flow does not consistently return one.
    """

    access_token: str
    refresh_token: str
    id_token: str | None
    expires_at: float  # unix timestamp (from expires_in, not JWT exp)

    def __repr__(self) -> str:  # secret hygiene — never echo token material
        return (
            "AnthropicTokens(access_token=<redacted>, refresh_token=<redacted>, "
            f"id_token={'<redacted>' if self.id_token is not None else None}, "
            f"expires_at={self.expires_at!r})"
        )


# ─── Origin-pin validators ──────────────────────────────────────────────────


def validate_oauth_endpoint(url: str) -> str:
    """Validate that ``url`` is ``https`` and under ``*.anthropic.com``.

    Raises :class:`ValueError` on violation.  Returns the validated URL.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"OAuth endpoint must use https, got: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if not (
        hostname == "anthropic.com" or hostname.endswith(".anthropic.com")
    ):
        raise ValueError(
            f"OAuth endpoint must be under *.anthropic.com, got: {hostname}"
        )
    return url


def validate_inference_base_url(url: str) -> str:
    """Validate that ``url`` is ``https`` and under ``*.anthropic.com``.

    Same pin as :func:`validate_oauth_endpoint` — the inference base URL must
    also be origin-pinned.
    """
    return validate_oauth_endpoint(url)


# ─── Expiry computation ─────────────────────────────────────────────────────


def compute_expires_at(expires_in: int = 3600) -> float:
    """Compute the expiry unix timestamp from ``expires_in``.

    Anthropic access tokens are opaque (not JWTs), so there is no ``exp`` claim
    to parse.  Applies adaptive skew to avoid burning single-use refresh tokens
    per request.
    """
    return time.time() + expires_in - _EXPIRY_SKEW_S


# ─── Failure classification ─────────────────────────────────────────────────


def _classify_failure(status_code: int, body: dict[str, Any]) -> AnthropicAuthError:
    """Map an HTTP error response to the BYOT failure taxonomy."""
    error_str = body.get("error", "")
    detail = body.get("error_description", body.get("message", str(body)))

    if status_code == 403:
        return AnthropicAuthError(
            failure=AnthropicAuthFailure.TIER_DENIED,
            status_code=status_code,
            detail=f"Anthropic tier denied (403): {detail}. "
            "Your plan may not be entitled to API access — "
            "paste an ANTHROPIC_API_KEY instead.",
            terminal=True,
        )
    if status_code in (400, 401) or error_str == "invalid_grant":
        return AnthropicAuthError(
            failure=AnthropicAuthFailure.RELOGIN_REQUIRED,
            status_code=status_code,
            detail=f"Anthropic auth invalid ({status_code}): {detail}. "
            "Credential quarantined — re-onboard required.",
            terminal=True,
        )
    # 429 or 5xx → transient
    return AnthropicAuthError(
        failure=AnthropicAuthFailure.TRANSIENT,
        status_code=status_code,
        detail=f"Anthropic transient error ({status_code}): {detail}",
        terminal=False,
    )


# ─── Authorization URL builder ──────────────────────────────────────────────


def build_authorize_url(
    *,
    pkce: PkceCodes | None = None,
    authorize_url: str = ANTHROPIC_AUTHORIZE_URL,
    redirect_uri: str = ANTHROPIC_REDIRECT_URI,
    client_id: str = ANTHROPIC_OAUTH_CLIENT_ID,
    scope: str = ANTHROPIC_SCOPE,
) -> tuple[str, PkceCodes]:
    """Build the authorization URL for the user to open in a browser.

    Generates a PKCE pair if not provided.  Returns a tuple of
    ``(authorize_url, pkce_pair)`` — the caller MUST retain the PKCE pair to
    complete the token exchange after the user copies back the authorization
    code.

    Per Claude Code convention, the ``code_verifier`` is also used as the
    ``state`` parameter (CSRF protection).  The redirect target is Anthropic's
    hosted callback page; the authorization code is displayed there for manual
    copy-back to the CLI.
    """
    if pkce is None:
        pkce = generate_pkce_pair()
    params = urlencode(
        {
            "code": "true",
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": "S256",
            "state": pkce.code_verifier,
        }
    )
    return f"{authorize_url}?{params}", pkce


# ─── Token exchange ─────────────────────────────────────────────────────────


def exchange_authorization_code(
    code: str,
    pkce: PkceCodes,
    *,
    redirect_uri: str = ANTHROPIC_REDIRECT_URI,
    client: httpx.Client | None = None,
    token_url: str = ANTHROPIC_TOKEN_URL,
    client_id: str = ANTHROPIC_OAUTH_CLIENT_ID,
) -> AnthropicTokens:
    """Exchange an authorization code for Anthropic tokens via a JSON POST.

    The PKCE ``code_verifier`` MUST match the ``code_challenge`` sent in the
    authorize request.  The ``redirect_uri`` MUST match the one used in the
    authorize request.

    Anthropic's token endpoint expects ``Content-Type: application/json`` (not
    form-urlencoded), matching the Claude Code flow.

    Raises :class:`AnthropicAuthError` on failure.
    """
    validate_oauth_endpoint(token_url)
    http = client or httpx.Client(timeout=30.0)
    own_client = client is None
    try:
        resp = http.post(
            token_url,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": pkce.code_verifier,
                "state": pkce.code_verifier,
            },
            headers={"User-Agent": "anthropic"},
        )
        if resp.status_code != 200:
            raise _classify_failure(resp.status_code, resp.json())
        body = resp.json()
        access_token = body["access_token"]
        refresh_token = body["refresh_token"]
        return AnthropicTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=body.get("id_token"),
            expires_at=compute_expires_at(body.get("expires_in", 3600)),
        )
    finally:
        if own_client:
            http.close()


# ─── Token refresh ──────────────────────────────────────────────────────────


def refresh_anthropic_token(
    refresh_token: str,
    *,
    client: httpx.Client | None = None,
    token_url: str = ANTHROPIC_TOKEN_URL,
    client_id: str = ANTHROPIC_OAUTH_CLIENT_ID,
) -> AnthropicTokens:
    """Refresh an Anthropic OAuth token via a JSON POST.

    The refresh token may be rotated by the server.  The caller must persist
    BOTH the new access and new refresh tokens in one atomic write.

    Raises :class:`AnthropicAuthError` on failure.
    """
    validate_oauth_endpoint(token_url)
    http = client or httpx.Client(timeout=30.0)
    own_client = client is None
    try:
        resp = http.post(
            token_url,
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            headers={"User-Agent": "anthropic"},
        )
        if resp.status_code != 200:
            raise _classify_failure(resp.status_code, resp.json())
        body = resp.json()
        access_token = body["access_token"]
        new_refresh = body.get("refresh_token", refresh_token)
        return AnthropicTokens(
            access_token=access_token,
            refresh_token=new_refresh,
            id_token=body.get("id_token"),
            expires_at=compute_expires_at(body.get("expires_in", 3600)),
        )
    finally:
        if own_client:
            http.close()


# ─── BYOK store integration ─────────────────────────────────────────────────

_PIPELINE_KIND = "anthropic_oauth"
_ACCOUNT_HANDLE = "anthropic"


def store_anthropic_tokens(
    tokens: AnthropicTokens,
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


def load_anthropic_tokens(
    cred_id: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> AnthropicTokens:
    """Load and decrypt a stored Anthropic token set.

    Returns :class:`AnthropicTokens`.  Raises ``KeyError`` if ``cred_id`` is
    unknown.
    """
    from runtime.byok.store import load_credential

    secret = load_credential(
        cred_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
    )
    body: dict[str, Any] = json.loads(secret.reveal())
    return AnthropicTokens(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        id_token=body.get("id_token"),
        expires_at=float(body["expires_at"]),
    )


def find_anthropic_cred_id(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> str | None:
    """Find the ``cred_id`` of the stored Anthropic token for ``owner_user_id``.

    Returns ``None`` if no Anthropic credential exists for this user.
    """
    from runtime.byok.store import list_credentials

    for meta in list_credentials(artifact_path=artifact_path):
        if (
            meta.pipeline_kind == _PIPELINE_KIND
            and meta.owner_user_id == owner_user_id
        ):
            return meta.cred_id
    return None


def delete_anthropic_tokens(
    cred_id: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    """Delete a stored Anthropic token set.  Returns ``True`` if present."""
    from runtime.byok.store import delete_credential

    return delete_credential(cred_id, artifact_path=artifact_path)


def quarantine_anthropic_tokens(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    """Quarantine (delete) a user's stored Anthropic tokens after auth failure.

    Called when the server returns 400/401 (invalid_grant).  Returns ``True``
    if tokens were present and deleted.
    """
    cred_id = find_anthropic_cred_id(owner_user_id, artifact_path=artifact_path)
    if cred_id is None:
        return False
    return delete_anthropic_tokens(cred_id, artifact_path=artifact_path)


__all__ = [
    "ANTHROPIC_AUTHORIZE_URL",
    "ANTHROPIC_INFERENCE_BASE",
    "ANTHROPIC_ISSUER",
    "ANTHROPIC_OAUTH_CLIENT_ID",
    "ANTHROPIC_REDIRECT_URI",
    "ANTHROPIC_SCOPE",
    "ANTHROPIC_TOKEN_URL",
    "AnthropicAuthError",
    "AnthropicAuthFailure",
    "AnthropicTokens",
    "PkceCodes",
    "build_authorize_url",
    "compute_expires_at",
    "delete_anthropic_tokens",
    "exchange_authorization_code",
    "find_anthropic_cred_id",
    "generate_pkce_pair",
    "load_anthropic_tokens",
    "quarantine_anthropic_tokens",
    "refresh_anthropic_token",
    "store_anthropic_tokens",
    "validate_inference_base_url",
    "validate_oauth_endpoint",
]
