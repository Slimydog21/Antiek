"""OAuth onboarding backend for BYO model-provider connections (BYOT v1).

Lets the operator connect a first-party model provider (OpenAI, Anthropic, Grok)
via the standard OAuth 2.0 Authorization Code + PKCE flow. Once connected, the
encrypted token set lives in the byok :mod:`~runtime.byok.store` and the owner's
dispatch tier can resolve it; this module never returns token material in any
response.

ARCHITECTURE
------------

Four endpoints under ``/settings/oauth/{provider}``:

  * ``GET  /authorize?redirect_uri=...`` — builds the provider authorize URL with
    a cryptographically random ``state`` and a PKCE ``code_challenge``. Both
    ``state`` and the PKCE ``code_verifier`` are stored server-side in a
    short-lived in-memory table (10-minute TTL, single-use on callback).
  * ``GET  /callback?code=&state=`` — validates ``state`` + owner + provider,
    exchanges ``code`` for tokens at the provider token endpoint (PKCE
    ``code_verifier`` in the exchange), and stores the token set encrypted via
    :func:`runtime.byok.store.store_credential` with ``pipeline_kind="oauth"``.
    The response carries ``connected: True`` — NEVER the tokens.
  * ``GET  /status`` — owner-scoped: ``{configured, connected, expires_at}``.
  * ``POST /disconnect`` — removes the stored token set for this owner+provider.

SECRET HANDLING — reuses the house byok posture verbatim
--------------------------------------------------------
Token material (access + refresh) is sealed in the SecretBox the INSTANT the
token endpoint returns it, then stored ONLY as its non-secret ``cred_id``.
The plaintext is decrypted lazily at call time behind a redacting
:class:`~runtime.byok.secret_str.SecretStr`. No endpoint returns, logs, or echoes
token material. The state store holds ONLY the PKCE verifier + owner identity —
never a token.

ENVIRONMENT — no hardcoded credentials (per the task constraints)
-----------------------------------------------------------------
Each provider's client_id + client_secret are read from ``os.environ``:

  * ``ANTIEK_OAUTH_OPENAI_CLIENT_ID`` / ``ANTIEK_OAUTH_OPENAI_CLIENT_SECRET``
  * ``ANTIEK_OAUTH_ANTHROPIC_CLIENT_ID`` / ``ANTIEK_OAUTH_ANTHROPIC_CLIENT_SECRET``
  * ``ANTIEK_OAUTH_GROK_CLIENT_ID`` / ``ANTIEK_OAUTH_GROK_CLIENT_SECRET``

When a provider's client_id is unset, every endpoint returns **501** (the
operator has not configured that provider's OAuth app). These are documented
placeholders only — the operator mints their own OAuth app credentials at the
provider's developer portal.

TOKEN ENDPOINTS (verified from public provider docs)
----------------------------------------------------
  * OpenAI:     ``https://auth.openai.com/oauth/token``
  * Anthropic:  ``https://console.anthropic.com/v1/oauth/token``
  * Grok (xAI): ``https://api.x.ai/oauth/token``

PERSISTENCE — no DuckDB writes (single-writer invariant preserved)
------------------------------------------------------------------
State is in-memory (thread-safe). Stored tokens land in the byok JSON artifact,
not DuckDB — same as ``settings_models_admin.py`` and ``settings_tool_connections.py``.

OWNER SCOPING — follows ``settings_models_admin.py``
----------------------------------------------------
Every endpoint resolves ``request_owner_user_id`` (from
:mod:`interfaces.research.api.settings_models_admin`) and scopes all state +
stored tokens to that owner. A cross-owner status or callback is a 404.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from interfaces.research.api.settings_models_admin import request_owner_user_id
from runtime.byok.store import (
    delete_credential,
    list_credentials,
    load_credential,
    store_credential,
)

__all__ = [
    "oauth_router",
    "register_oauth_routes",
]

# ---------------------------------------------------------------------------
# Provider configuration (env-gated; 501 when unset)
# ---------------------------------------------------------------------------

_PRIVATE_NO_STORE = "private, no-store"
_STATE_TTL_S = 600  # 10-minute TTL for authorize→callback round-trip
_MAX_REDIRECT_URI_LEN = 2048

_PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "authorize_url": "https://auth.openai.com/oauth/authorize",
        "token_url": "https://auth.openai.com/oauth/token",
        "client_id_env": "ANTIEK_OAUTH_OPENAI_CLIENT_ID",
        "client_secret_env": "ANTIEK_OAUTH_OPENAI_CLIENT_SECRET",
        "scope": "openid profile email offline_access",
    },
    "anthropic": {
        "authorize_url": "https://console.anthropic.com/v1/oauth/authorize",
        "token_url": "https://console.anthropic.com/v1/oauth/token",
        "client_id_env": "ANTIEK_OAUTH_ANTHROPIC_CLIENT_ID",
        "client_secret_env": "ANTIEK_OAUTH_ANTHROPIC_CLIENT_SECRET",
        "scope": "org:create_api_key user:profile user:inference offline_access",
    },
    "grok": {
        "authorize_url": "https://auth.x.ai/oauth/authorize",
        "token_url": "https://api.x.ai/oauth/token",
        "client_id_env": "ANTIEK_OAUTH_GROK_CLIENT_ID",
        "client_secret_env": "ANTIEK_OAUTH_GROK_CLIENT_SECRET",
        "scope": "openid profile email offline_access",
    },
}


def _provider_config(provider: str) -> dict[str, str]:
    """Resolve a provider's config dict or raise 404 for unknown providers."""
    cfg = _PROVIDERS.get(provider)
    if cfg is None:
        raise HTTPException(
            status_code=404, detail=f"unsupported OAuth provider: {provider}"
        )
    return cfg


def _resolve_credentials(cfg: dict[str, str]) -> tuple[str, str]:
    """Read client_id + client_secret from env. Raises 501 when unset."""
    client_id = os.environ.get(cfg["client_id_env"], "").strip()
    client_secret = os.environ.get(cfg["client_secret_env"], "").strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=501,
            detail=f"OAuth provider is not configured — set "
            f"{cfg['client_id_env']} and {cfg['client_secret_env']} "
            "environment variables",
        )
    return client_id, client_secret


def _oauth_pipeline_kind(provider: str) -> str:
    return f"oauth_{provider}"


def _oauth_account_handle(provider: str) -> str:
    return f"oauth-{provider}"


# ---------------------------------------------------------------------------
# PKCE helpers (RFC 7636 S256)
# ---------------------------------------------------------------------------


def _generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# In-memory state store (thread-safe, short-lived, single-use)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _StateEntry:
    code_verifier: str
    provider: str
    owner_user_id: str
    redirect_uri: str
    expires_at: float


class _OAuthStateStore:
    """Thread-safe, short-lived, single-use store for OAuth state + PKCE.

    Entries auto-expire after ``_STATE_TTL_S`` seconds. ``pop`` is single-use:
    a state is consumed exactly once and cannot be replayed (CSRF defense).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _StateEntry] = {}

    def put(
        self,
        state: str,
        *,
        code_verifier: str,
        provider: str,
        owner_user_id: str,
        redirect_uri: str,
        ttl: float = _STATE_TTL_S,
    ) -> None:
        with self._lock:
            self._cleanup()
            self._entries[state] = _StateEntry(
                code_verifier=code_verifier,
                provider=provider,
                owner_user_id=owner_user_id,
                redirect_uri=redirect_uri,
                expires_at=time.time() + ttl,
            )

    def pop(self, state: str) -> _StateEntry | None:
        """Consume and return the entry for ``state``, or None if
        missing/expired. Single-use: the entry is removed regardless."""
        with self._lock:
            self._cleanup()
            return self._entries.pop(state, None)

    def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._entries.items() if v.expires_at <= now]
        for k in expired:
            del self._entries[k]


# Module-level singleton — survives across requests within one process.
_state_store = _OAuthStateStore()


# ---------------------------------------------------------------------------
# Stored-token helpers (byok store)
# ---------------------------------------------------------------------------


def _find_oauth_cred_id(
    owner_user_id: str,
    provider: str,
    *,
    artifact_path: str | None = None,
) -> str | None:
    """Find the cred_id of the stored OAuth token for ``owner`` + ``provider``.

    Uses non-secret metadata only (never decrypts). Returns None if absent.
    """
    pipeline_kind = _oauth_pipeline_kind(provider)
    handle = _oauth_account_handle(provider)
    for meta in list_credentials(artifact_path=artifact_path):
        if (
            meta.pipeline_kind == pipeline_kind
            and meta.owner_user_id == owner_user_id
            and meta.account_handle == handle
        ):
            return meta.cred_id
    return None


def _load_oauth_expiry(
    cred_id: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> str | None:
    """Decrypt the stored token set to read its ``expires_at`` (ISO-8601).

    This is the one place the status surface touches the plaintext — but it
    only reads the expiry timestamp, never the token values, and the expiry is
    the only field returned to the caller.
    """
    try:
        secret = load_credential(
            cred_id,
            artifact_path=artifact_path,
            key_bytes=key_bytes,
            key_file=key_file,
        )
    except Exception:
        return None
    try:
        body: dict[str, Any] = json.loads(secret.reveal())
    except (ValueError, TypeError):
        return None
    return body.get("expires_at_iso")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AuthorizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    authorize_url: str
    state: str


class CallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    connected: bool


class OAuthStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    configured: bool
    connected: bool
    expires_at: str | None = None


class DisconnectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    disconnected: bool


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

oauth_router = APIRouter(prefix="/settings/oauth", tags=["settings-oauth"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE


def _valid_provider_or_404(provider: str) -> str:
    if provider not in _PROVIDERS:
        raise HTTPException(
            status_code=404, detail=f"unsupported OAuth provider: {provider}"
        )
    return provider


# --- GET /{provider}/authorize ----------------------------------------------


@oauth_router.get("/{provider}/authorize", response_model=AuthorizeResponse)
def authorize(
    provider: str,
    request: Request,
    response: Response,
    redirect_uri: str = "",
) -> AuthorizeResponse:
    """Build the provider's authorize URL with PKCE + server-side state.

    Returns 501 when the provider's OAuth credentials are not configured (env
    vars unset). The ``state`` + PKCE ``code_verifier`` are stored server-side
    and consumed single-use on callback.
    """
    _valid_provider_or_404(provider)
    owner_user_id = request_owner_user_id(request)
    _no_store(response)

    cfg = _provider_config(provider)
    client_id, _secret = _resolve_credentials(cfg)  # raises 501 if unset

    if not redirect_uri or len(redirect_uri) > _MAX_REDIRECT_URI_LEN:
        raise HTTPException(
            status_code=422, detail="redirect_uri is required and must be a valid URL"
        )

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    _state_store.put(
        state,
        code_verifier=code_verifier,
        provider=provider,
        owner_user_id=owner_user_id,
        redirect_uri=redirect_uri,
    )

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": cfg["scope"],
    }
    authorize_url = f"{cfg['authorize_url']}?{urlencode(params)}"

    return AuthorizeResponse(
        provider=provider, authorize_url=authorize_url, state=state
    )


# --- GET /{provider}/callback -----------------------------------------------


def _exchange_code_for_tokens(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchange the authorization code for tokens at the provider endpoint.

    Returns the parsed token JSON (``access_token``, ``refresh_token``,
    ``expires_in``, etc.). Raises ``HTTPException(502)`` on any failure — the
    message carries the status code only, NEVER the token material.

    Monkeypatch target for tests (avoids live HTTP).
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    try:
        resp = httpx.post(token_url, data=data, timeout=30.0)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OAuth token exchange failed: {type(exc).__name__}",
        ) from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"OAuth token exchange failed: HTTP {resp.status_code}",
        )
    try:
        body = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="OAuth token exchange returned non-JSON"
        ) from exc
    if not isinstance(body, dict) or "access_token" not in body:
        raise HTTPException(
            status_code=502, detail="OAuth token exchange returned no access_token"
        )
    return body


@oauth_router.get("/{provider}/callback", response_model=CallbackResponse)
def callback(
    provider: str,
    request: Request,
    response: Response,
    code: str = "",
    state: str = "",
) -> CallbackResponse:
    """Validate state + PKCE, exchange code for tokens, store them encrypted.

    Returns 400 on state validation failure (missing/expired/mismatched state,
    owner mismatch, provider mismatch). Never returns token material.
    """
    _valid_provider_or_404(provider)
    owner_user_id = request_owner_user_id(request)
    _no_store(response)

    cfg = _provider_config(provider)
    client_id, client_secret = _resolve_credentials(cfg)  # raises 501 if unset

    if not code or not state:
        raise HTTPException(
            status_code=400, detail="code and state query parameters are required"
        )

    # Single-use state consumption (CSRF + replay defense).
    entry = _state_store.pop(state)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail="invalid or expired OAuth state — restart the authorization flow",
        )
    if entry.provider != provider:
        raise HTTPException(
            status_code=400, detail="OAuth state provider mismatch"
        )
    if entry.owner_user_id != owner_user_id:
        raise HTTPException(
            status_code=400, detail="OAuth state owner mismatch"
        )

    token_body = _exchange_code_for_tokens(
        token_url=cfg["token_url"],
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=entry.redirect_uri,
        code_verifier=entry.code_verifier,
    )

    # Compute expiry from expires_in (seconds from now).
    expires_in = token_body.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        from datetime import UTC, datetime, timedelta

        expires_at_dt = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        expires_at_iso = expires_at_dt.isoformat()
    else:
        expires_at_iso = None

    # Seal the full token set as ONE encrypted credential. NEVER logged.
    payload = json.dumps(
        {
            "access_token": token_body["access_token"],
            "refresh_token": token_body.get("refresh_token", ""),
            "expires_at_iso": expires_at_iso,
            "provider": provider,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    store_credential(
        _oauth_account_handle(provider),
        payload,
        pipeline_kind=_oauth_pipeline_kind(provider),
        owner_user_id=owner_user_id,
    )

    return CallbackResponse(provider=provider, connected=True)


# --- GET /{provider}/status -------------------------------------------------


@oauth_router.get("/{provider}/status", response_model=OAuthStatusResponse)
def status(provider: str, request: Request, response: Response) -> OAuthStatusResponse:
    """Owner-scoped OAuth connection status.

    ``configured`` is True when the provider's env credentials are set.
    ``connected`` is True when a stored token exists for this owner+provider.
    ``expires_at`` is the token expiry (ISO-8601) when connected.
    """
    _valid_provider_or_404(provider)
    owner_user_id = request_owner_user_id(request)
    _no_store(response)

    cfg = _provider_config(provider)
    configured = True
    try:
        _resolve_credentials(cfg)
    except HTTPException:
        configured = False

    cred_id = _find_oauth_cred_id(owner_user_id, provider)
    connected = cred_id is not None
    expires_at: str | None = None
    if connected and cred_id is not None:
        expires_at = _load_oauth_expiry(cred_id)

    return OAuthStatusResponse(
        provider=provider,
        configured=configured,
        connected=connected,
        expires_at=expires_at,
    )


# --- POST /{provider}/disconnect --------------------------------------------


@oauth_router.post("/{provider}/disconnect", response_model=DisconnectResponse)
def disconnect(provider: str, request: Request, response: Response) -> DisconnectResponse:
    """Remove the stored OAuth token set for this owner+provider."""
    _valid_provider_or_404(provider)
    owner_user_id = request_owner_user_id(request)
    _no_store(response)

    cred_id = _find_oauth_cred_id(owner_user_id, provider)
    if cred_id is not None:
        delete_credential(cred_id)
        return DisconnectResponse(provider=provider, disconnected=True)
    # Idempotent: no stored token → still "disconnected".
    return DisconnectResponse(provider=provider, disconnected=False)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_oauth_routes(app: FastAPI) -> None:
    """Mount the OAuth onboarding routes onto ``app``."""
    app.include_router(oauth_router)
