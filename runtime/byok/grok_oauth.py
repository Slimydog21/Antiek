"""Grok (xAI) device-code OAuth onboarding — BYOT integration.

Self-contained device-code trio (RFC 8628) against ``https://auth.x.ai`` as the
``grok-cli`` public client.  One server-side token row per user, encrypted via
the byok :mod:`~runtime.byok.store`.  No credential-pool multi-process
machinery — one artifact-locked refresher eliminates the race class the pool
exists to mitigate.

MECHANISM
---------
1. ``request_device_code()`` → POST to the device-authorization endpoint.
2. User visits ``verification_uri``, enters ``user_code``.
3. ``poll_device_token()`` → polls the token endpoint, handling
   ``authorization_pending`` / ``slow_down``.
4. ``refresh_grok_token()`` → pure form-POST to the discovered token endpoint.
5. Origin-pin validators reject anything that is not ``https`` + ``*.x.ai``.
6. JWT ``exp`` claim (with adaptive skew) drives expiry, not ``expires_in``.

FAILURE TAXONOMY (BYOT UX states)
----------------------------------
- 403 → ``grok_tier_denied`` (terminal; suggest paste ``XAI_API_KEY``).
- 400/401 (``invalid_grant`` / revoked / reused) → ``grok_relogin_required``
  (terminal; quarantine tokens, require re-onboard).
- 429/5xx → ``grok_transient`` (retry; never quarantine).

CLIENT-IMPERSONATION FLAG
--------------------------
This module reuses the ``grok-cli`` client_id registration (``b1a00492-...``).
xAI can 403-tier-gate this at will.  The paste-a-key (``XAI_API_KEY``) path is
always the recommended fallback.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlparse

import httpx

# ─── xAI OAuth constants (from grok-cli registration) ───────────────────────
XAI_ISSUER: str = "https://auth.x.ai"
XAI_DISCOVERY: str = "https://auth.x.ai/.well-known/openid-configuration"
XAI_DEVICE_CODE_URL: str = "https://auth.x.ai/oauth2/device/code"
XAI_TOKEN_URL: str = "https://auth.x.ai/oauth2/token"
XAI_OAUTH_CLIENT_ID: str = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_SCOPE: str = "openid profile email offline_access grok-cli:access api:access"
XAI_INFERENCE_BASE: str = "https://api.x.ai/v1"

# Default poll interval from the RFC; server may override via ``interval``.
_DEFAULT_POLL_INTERVAL_S: int = 5
# Adaptive skew for JWT expiry — clamp to avoid burning single-use refresh
# tokens on every request for ~15-min device-code JWTs.
_EXPIRY_SKEW_S: int = 30
# Maximum device-code poll duration (the grant's ``expires_in``).
_MAX_DEVICE_CODE_LIFETIME_S: int = 600


# ─── Failure taxonomy ────────────────────────────────────────────────────────


class GrokAuthFailure(Enum):
    """BYOT UX failure states for Grok device-code OAuth."""

    TIER_DENIED = "grok_tier_denied"  # 403 — terminal, suggest paste key
    RELOGIN_REQUIRED = "grok_relogin_required"  # 400/401 — quarantine
    TRANSIENT = "grok_transient"  # 429/5xx — retry


@dataclass(frozen=True)
class GrokAuthError(Exception):
    """Structured error from the device-code or refresh flow."""

    failure: GrokAuthFailure
    status_code: int
    detail: str
    terminal: bool = False

    def __str__(self) -> str:
        return self.detail


# ─── Data shapes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeviceCodeGrant:
    """Response from the device-authorization endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int


@dataclass(frozen=True)
class XaiTokens:
    """Token set returned by device-code poll or refresh."""

    access_token: str
    refresh_token: str
    id_token: str | None
    expires_at: float  # unix timestamp (from JWT exp, not expires_in)


# ─── Origin-pin validators ──────────────────────────────────────────────────


def validate_oauth_endpoint(url: str) -> str:
    """Validate that ``url`` is ``https`` and under ``*.x.ai``.

    Raises :class:`ValueError` on violation.  Returns the validated URL.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"OAuth endpoint must use https, got: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if not (hostname == "x.ai" or hostname.endswith(".x.ai")):
        raise ValueError(f"OAuth endpoint must be under *.x.ai, got: {hostname}")
    return url


def validate_inference_base_url(url: str) -> str:
    """Validate that ``url`` is ``https`` and under ``*.x.ai``.

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


def _classify_failure(status_code: int, body: dict[str, Any]) -> GrokAuthError:
    """Map an HTTP error response to the BYOT failure taxonomy."""
    error_str = body.get("error", "")
    detail = body.get("error_description", body.get("message", str(body)))

    if status_code == 403:
        return GrokAuthError(
            failure=GrokAuthFailure.TIER_DENIED,
            status_code=status_code,
            detail=f"xAI tier denied (403): {detail}. "
            "Your plan may not be entitled to API access — "
            "paste an XAI_API_KEY instead.",
            terminal=True,
        )
    if status_code in (400, 401) or error_str == "invalid_grant":
        return GrokAuthError(
            failure=GrokAuthFailure.RELOGIN_REQUIRED,
            status_code=status_code,
            detail=f"xAI auth invalid ({status_code}): {detail}. "
            "Credential quarantined — re-onboard required.",
            terminal=True,
        )
    # 429 or 5xx → transient
    return GrokAuthError(
        failure=GrokAuthFailure.TRANSIENT,
        status_code=status_code,
        detail=f"xAI transient error ({status_code}): {detail}",
        terminal=False,
    )


# ─── Device-code flow ───────────────────────────────────────────────────────


def request_device_code(
    *,
    client: httpx.Client | None = None,
    device_code_url: str = XAI_DEVICE_CODE_URL,
    client_id: str = XAI_OAUTH_CLIENT_ID,
    scope: str = XAI_SCOPE,
) -> DeviceCodeGrant:
    """Request a device-authorization grant from xAI.

    Returns a :class:`DeviceCodeGrant` with the ``device_code``, ``user_code``,
    ``verification_uri``, poll ``interval``, and ``expires_in``.

    Raises :class:`GrokAuthError` on HTTP failure.
    """
    validate_oauth_endpoint(device_code_url)
    http = client or httpx.Client(timeout=30.0)
    own_client = client is None
    try:
        resp = http.post(
            device_code_url,
            data={
                "client_id": client_id,
                "scope": scope,
            },
        )
        if resp.status_code != 200:
            raise _classify_failure(resp.status_code, resp.json())
        body = resp.json()
        return DeviceCodeGrant(
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            interval=body.get("interval", _DEFAULT_POLL_INTERVAL_S),
            expires_in=body.get("expires_in", _MAX_DEVICE_CODE_LIFETIME_S),
        )
    finally:
        if own_client:
            http.close()


def poll_device_token(
    grant: DeviceCodeGrant,
    *,
    client: httpx.Client | None = None,
    token_url: str = XAI_TOKEN_URL,
    client_id: str = XAI_OAUTH_CLIENT_ID,
    now: float | None = None,
) -> XaiTokens:
    """Poll the token endpoint until the user approves or the grant expires.

    Handles ``authorization_pending`` and ``slow_down`` per RFC 8628 §3.5.
    Returns :class:`XaiTokens` on success.

    Raises :class:`GrokAuthError` on failure or timeout.
    """
    validate_oauth_endpoint(token_url)
    http = client or httpx.Client(timeout=30.0)
    own_client = client is None
    try:
        deadline = (now or time.time()) + grant.expires_in
        interval = grant.interval
        while True:
            current = time.time()
            if current >= deadline:
                raise GrokAuthError(
                    failure=GrokAuthFailure.TRANSIENT,
                    status_code=0,
                    detail="Device code grant expired — request a new code.",
                    terminal=False,
                )
            resp = http.post(
                token_url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": grant.device_code,
                    "client_id": client_id,
                },
            )
            if resp.status_code == 200:
                body = resp.json()
                access_token = body["access_token"]
                refresh_token = body["refresh_token"]
                return XaiTokens(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    id_token=body.get("id_token"),
                    expires_at=compute_expires_at(
                        access_token,
                        fallback_expires_in=body.get("expires_in", 3600),
                    ),
                )
            body = resp.json()
            error = body.get("error", "")
            if error == "authorization_pending":
                time.sleep(interval)
                continue
            if error == "slow_down":
                interval += 5
                time.sleep(interval)
                continue
            # Any other error is terminal for this poll attempt.
            raise _classify_failure(resp.status_code, body)
    finally:
        if own_client:
            http.close()


def refresh_grok_token(
    refresh_token: str,
    *,
    client: httpx.Client | None = None,
    token_url: str = XAI_TOKEN_URL,
    client_id: str = XAI_OAUTH_CLIENT_ID,
) -> XaiTokens:
    """Refresh an xAI OAuth token via a pure form-POST.

    The refresh token is single-use — the server rotates it.  The caller must
    persist BOTH the new access and new refresh tokens in one atomic write.

    Raises :class:`GrokAuthError` on failure.
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
        return XaiTokens(
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

_PIPELINE_KIND = "grok_oauth"
_ACCOUNT_HANDLE = "grok-xai"


def store_grok_tokens(
    tokens: XaiTokens,
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


def load_grok_tokens(
    cred_id: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> XaiTokens:
    """Load and decrypt a stored Grok token set.

    Returns :class:`XaiTokens`.  Raises ``KeyError`` if ``cred_id`` is unknown.
    """
    from runtime.byok.store import load_credential

    secret = load_credential(
        cred_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
    )
    body: dict[str, Any] = json.loads(secret.reveal())
    return XaiTokens(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        id_token=body.get("id_token"),
        expires_at=float(body["expires_at"]),
    )


def find_grok_cred_id(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> str | None:
    """Find the ``cred_id`` of the stored Grok token for ``owner_user_id``.

    Returns ``None`` if no Grok credential exists for this user.
    """
    from runtime.byok.store import list_credentials

    for meta in list_credentials(artifact_path=artifact_path):
        if (
            meta.pipeline_kind == _PIPELINE_KIND
            and meta.owner_user_id == owner_user_id
        ):
            return meta.cred_id
    return None


def delete_grok_tokens(
    cred_id: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    """Delete a stored Grok token set.  Returns ``True`` if present."""
    from runtime.byok.store import delete_credential

    return delete_credential(cred_id, artifact_path=artifact_path)


# ─── Quarantine (re-login required) ─────────────────────────────────────────


def quarantine_grok_tokens(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    """Quarantine (delete) a user's stored Grok tokens after auth failure.

    Called when the server returns 400/401 (invalid_grant).  Returns ``True``
    if tokens were present and deleted.
    """
    cred_id = find_grok_cred_id(owner_user_id, artifact_path=artifact_path)
    if cred_id is None:
        return False
    return delete_grok_tokens(cred_id, artifact_path=artifact_path)


__all__ = [
    "DeviceCodeGrant",
    "GrokAuthError",
    "GrokAuthFailure",
    "XAI_DEVICE_CODE_URL",
    "XAI_DISCOVERY",
    "XAI_INFERENCE_BASE",
    "XAI_ISSUER",
    "XAI_OAUTH_CLIENT_ID",
    "XAI_SCOPE",
    "XAI_TOKEN_URL",
    "XaiTokens",
    "compute_expires_at",
    "delete_grok_tokens",
    "find_grok_cred_id",
    "load_grok_tokens",
    "quarantine_grok_tokens",
    "refresh_grok_token",
    "request_device_code",
    "poll_device_token",
    "store_grok_tokens",
    "validate_inference_base_url",
    "validate_oauth_endpoint",
]
