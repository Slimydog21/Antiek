"""Magic-link auth endpoints for Antiek.

PostHog-style: the platform owns its login surface. Cloudflare
Access is decommissioned at the runbook level (see
``infrastructure/runbooks/magic-link-auth.md``); the substrate
operates its own session cookies + email-delivered magic links.

Four routes:

- ``POST /auth/request`` — body ``{"email": "..."}`` → mint a
  magic-link token, send via the configured email provider,
  return ``{"sent": true}``. Always returns 200 with ``sent: true``
  even for non-allowlisted addresses, to avoid enumerating valid
  operators via timing or response shape. The send only actually
  happens for allowlisted emails.
- ``GET /auth/callback?token=...&next=/`` — verify the token, set
  the session cookie, redirect to ``next`` (default ``/``).
- ``POST /auth/logout`` — clear the cookie, 204.
- ``GET /auth/me`` — return the resolved session
  ``{user_id, email, auth_method}`` or 401 if no valid auth.

The middleware in ``app.py`` reads the same cookie name
``ANTIEK_SESSION``; this module's job is mint/clear, the
middleware's job is verify-on-every-request.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode, urljoin

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator

from substrate.auth import (
    EmailDeliveryFailure,
    InvalidToken,
    OutboundEmail,
    SqliteAuthStore,
    TokenExpired,
    get_email_provider,
    mint_magic_link_token,
    mint_session_cookie,
    verify_magic_link_claims,
    verify_session_cookie,
)
from substrate.auth.magic_link import MAGIC_LINK_TTL_SECONDS, SESSION_TTL_SECONDS

from .operator_allowlist import operator_allowlist_from_env

SESSION_COOKIE_NAME = "ANTIEK_SESSION"

_DEFAULT_PUBLIC_BASE = "https://antiek.ai"

# Inline RFC-5322-ish email shape check. Strict-validation isn't the
# job (Resend will reject malformed addresses); shape-rejection here
# just keeps obvious garbage out of the email queue.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Request/response models ──────────────────────────────────────────


class AuthRequestPayload(BaseModel):
    """``POST /auth/request`` body."""

    email: str = Field(..., min_length=3, max_length=320)
    next: str = Field(default="/", description="Relative path to redirect to after callback")

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValueError("email does not look like an address")
        return normalized


class AuthRequestResponse(BaseModel):
    """``POST /auth/request`` response — always ``sent: true`` to
    avoid disclosing whether the email is allowlisted."""

    sent: bool = True


class AuthMeResponse(BaseModel):
    """``GET /auth/me`` response."""

    user_id: str
    email: str | None
    auth_method: str
    scopes: list[str] = Field(default_factory=list)
    is_operator: bool = False


# ── Helpers ──────────────────────────────────────────────────────────


def _api_base_url() -> str:
    """Where the magic-link click lands (the FastAPI host). The
    callback handler is server-side, so the link must point at the
    API origin even when the frontend lives on a different host."""
    return os.environ.get(
        "ANTIEK_API_BASE_URL",
        os.environ.get("ANTIEK_PUBLIC_BASE_URL", _DEFAULT_PUBLIC_BASE),
    ).rstrip("/") + "/"


def _frontend_base_url() -> str:
    """Where the API redirects after setting the session cookie.

    The callback runs server-side on the API origin (api.antiek.ai). A
    relative ``Location: /`` resolves against *that* origin, so the
    browser would land on api.antiek.ai — the FastAPI host, not the app.
    To send the user to the Pages frontend we must emit an absolute URL.

    Resolution order:
      1. ``ANTIEK_FRONTEND_BASE_URL`` — explicit override.
      2. ``ANTIEK_PUBLIC_BASE_URL`` — the canonical app origin the
         runbook already sets (``https://antiek.ai``). This is the
         common single-host config; without it the post-login redirect
         landed on the API host (the lived bug).
      3. ``""`` — genuine same-origin / local dev (no public host
         configured): fall back to a relative redirect.
    """
    raw = (
        os.environ.get("ANTIEK_FRONTEND_BASE_URL", "").strip()
        or os.environ.get("ANTIEK_PUBLIC_BASE_URL", "").strip()
    )
    return raw.rstrip("/") if raw else ""


def _build_magic_link(token: str, next_path: str) -> str:
    qs = urlencode({"token": token, "next": next_path or "/"})
    return urljoin(_api_base_url(), f"auth/callback?{qs}")


def _is_safe_relative(path: str) -> bool:
    """Only accept same-origin relative redirects. Protects against
    open-redirect to attacker-controlled URLs piggybacking on a
    legitimate magic link."""
    if not path:
        return False
    if path.startswith("//"):
        return False
    return path.startswith("/")


def _resolve_redirect(next_path: str) -> str:
    """Compute the final redirect URL after a successful callback.

    If ``ANTIEK_FRONTEND_BASE_URL`` is set (cross-origin deployment:
    Pages on antiek.ai, API on api.antiek.ai), prefix ``next_path``
    with that host so the browser lands on the frontend with the
    cookie already set (via Domain=.antiek.ai). Otherwise relative.
    """
    safe = next_path if _is_safe_relative(next_path) else "/"
    fe = _frontend_base_url()
    return f"{fe}{safe}" if fe else safe


def _redirect_login_error(*, error_code: str, next_path: str = "/") -> RedirectResponse:
    """Send the browser to the frontend Login surface with a closed error enum.

    Email magic links land on the API host; JSON error bodies are hostile
    to operators. When a frontend base is configured, redirect there.
    Otherwise fall back to a relative ``/login`` (same-origin dev).
    """
    safe_next = next_path if _is_safe_relative(next_path) else "/"
    qs = urlencode({"error": error_code, "next": safe_next})
    fe = _frontend_base_url()
    target = f"{fe}/login?{qs}" if fe else f"/login?{qs}"
    return RedirectResponse(url=target, status_code=302)


def _cookie_kwargs() -> dict[str, Any]:
    """HttpOnly + Secure + SameSite=Lax. ``Secure`` is unconditional
    on production; tests work because the test client doesn't
    enforce the flag. ``Domain`` is set in cross-origin deployments
    so the cookie is visible to both Pages (antiek.ai) and the API
    (api.antiek.ai)."""
    secure = os.environ.get("ANTIEK_COOKIE_INSECURE", "").strip() != "1"
    kwargs: dict[str, Any] = dict(
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    domain = os.environ.get("ANTIEK_COOKIE_DOMAIN", "").strip()
    if domain:
        kwargs["domain"] = domain
    return kwargs


def _format_magic_link_email(*, email: str, link: str) -> OutboundEmail:
    text = (
        "Sign in to Antiek\n"
        "\n"
        f"Click the link below to sign in. The link expires in 15 minutes.\n"
        "\n"
        f"  {link}\n"
        "\n"
        "If you did not request this, ignore this email — no action will\n"
        "be taken.\n"
        "\n"
        "— Antiek\n"
    )
    return OutboundEmail(
        to=email,
        subject="Sign in to Antiek",
        text_body=text,
    )


# ── Dev-login (temporary agent / computer-use access) ─────────────────
# A single env-gated token that lets a browser-driving agent (Codex /
# Hermes computer-use) acquire an operator session by navigating to ONE
# URL — no inbox round-trip, no header injection. The magic-link path
# needs an email click; a Bearer token needs a header the browser can't
# attach to a page load; this fills the gap for computer-use agents that
# only know how to visit a URL and click.
#
# Disabled by default: the route 404s unless BOTH ``ANTIEK_DEV_LOGIN_TOKEN``
# and ``ANTIEK_AUTH_SECRET`` are set, so it is invisible (not merely
# forbidden) on any box that hasn't opted in. Kill it by unsetting the
# token var — no redeploy needed — or rotate its value to invalidate a
# leaked link.
#
# Scope: this grants FULL operator access. It is a development /
# verification convenience, NOT the scoped read-only public API (that is
# the later, separate build). Treat the token like a password; rotate it
# after a verification session. Rationale + reconsider-if:
# docs/decisions/agent-dev-login.md.

_DEV_LOGIN_TOKEN_ENV = "ANTIEK_DEV_LOGIN_TOKEN"
# Shorter-lived than the 30-day magic-link session: a dev grant should
# age out on its own even if the operator forgets to unset the token.
_DEV_LOGIN_SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _dev_login_token() -> str:
    """The configured dev-login token, or ``""`` when the feature is off."""
    return os.environ.get(_DEV_LOGIN_TOKEN_ENV, "").strip()


# ── Registration ─────────────────────────────────────────────────────


def register_auth_routes(
    app: FastAPI,
    *,
    extra_allowlist: Sequence[str] | None = None,
    account_store: SqliteAuthStore | None = None,
    auth_environ: Mapping[str, str] | None = None,
) -> None:
    """Mount the four auth routes onto ``app``.

    ``extra_allowlist`` is an injection seam for tests; production
    reads the allowlist from ``ANTIEK_OPERATOR_EMAIL`` only.
    """

    extra = frozenset(e.strip().lower() for e in (extra_allowlist or ()) if e.strip())
    environment = os.environ if auth_environ is None else auth_environ
    multi_user_enabled = environment.get("ANTIEK_MULTI_USER_AUTH", "").strip() == "1"
    if multi_user_enabled and account_store is None:
        account_store = SqliteAuthStore()

    def _resolve_allowlist() -> frozenset[str]:
        return operator_allowlist_from_env(environ=environment) | extra

    def _user_allowlist() -> frozenset[str]:
        return frozenset(
            part.strip().lower()
            for part in environment.get("ANTIEK_USER_EMAIL", "").split(",")
            if part.strip()
        )

    def _user_email_authorized(email: str) -> bool:
        if email in _resolve_allowlist():
            return True
        if not multi_user_enabled or account_store is None:
            return False
        existing = account_store.get_by_email(email)
        if existing is not None:
            return existing.status == "active"
        mode = environment.get("ANTIEK_AUTH_REGISTRATION_MODE", "operator_only").strip()
        return mode == "open" or (mode == "allowlist" and email in _user_allowlist())

    @app.post(
        "/auth/request",
        response_model=AuthRequestResponse,
        tags=["auth"],
    )
    async def auth_request(
        request: Request, payload: AuthRequestPayload
    ) -> AuthRequestResponse:
        email = payload.email.strip().lower()
        next_path = payload.next if _is_safe_relative(payload.next) else "/"
        rate_allowed = (
            account_store.allow_magic_link_request(
                email=email,
                client_key=(request.client.host if request.client else "unknown"),
            )
            if multi_user_enabled and account_store is not None
            else True
        )
        if rate_allowed and _user_email_authorized(email):
            nonce = secrets.token_urlsafe(24)
            if multi_user_enabled and account_store is not None:
                account_store.register_magic_link(
                    email=email,
                    nonce=nonce,
                    expires_at=int(time.time()) + MAGIC_LINK_TTL_SECONDS,
                )
            token = mint_magic_link_token(email, nonce=nonce)
            link = _build_magic_link(token, next_path)
            provider = get_email_provider()
            try:
                provider.send(_format_magic_link_email(email=email, link=link))
            except EmailDeliveryFailure as exc:
                # Distinguish "we tried and the provider broke" from
                # "you're not allowlisted" via a 503 — gives the
                # operator a real signal when their email config is
                # broken instead of silently swallowing the failure.
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "email_delivery_failed",
                        "message": str(exc),
                    },
                ) from exc
        # Non-allowlisted: silently no-op. Constant-time-ish: the
        # branch difference is unavoidable but the response is
        # identical, which is what enumeration protection turns on.
        return AuthRequestResponse(sent=True)

    @app.get("/auth/callback", tags=["auth"])
    async def auth_callback(token: str, next: str = "/") -> Response:
        redirect_url = _resolve_redirect(next)
        try:
            link_claims = verify_magic_link_claims(token)
            email = link_claims.email
        except TokenExpired:
            return _redirect_login_error(error_code="magic_link_expired", next_path=next)
        except InvalidToken:
            return _redirect_login_error(error_code="magic_link_invalid", next_path=next)
        if not _user_email_authorized(email):
            # Defensive: token was valid but the allowlist changed
            # between request and click. Reject without leaking which
            # case we're in.
            return _redirect_login_error(error_code="not_authorized", next_path=next)
        if multi_user_enabled and account_store is not None:
            if not account_store.consume_magic_link(
                email=email, nonce=link_claims.nonce
            ):
                return _redirect_login_error(
                    error_code="magic_link_invalid", next_path=next
                )
            if email in _resolve_allowlist():
                user_id = "__operator__"
            else:
                account = account_store.get_or_create_user(email)
                if account.status != "active":
                    return _redirect_login_error(
                        error_code="not_authorized", next_path=next
                    )
                user_id = account.user_id
            session_id = account_store.create_session(
                user_id=user_id, email=email, ttl_seconds=SESSION_TTL_SECONDS
            )
            cookie = mint_session_cookie(
                user_id=user_id, email=email, session_id=session_id
            )
        else:
            cookie = mint_session_cookie(user_id="__operator__", email=email)
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=cookie,
            max_age=60 * 60 * 24 * 30,  # 30 days
            **_cookie_kwargs(),
        )
        return response

    @app.get("/auth/dev-login", tags=["auth"])
    async def auth_dev_login(token: str = "", next: str = "/") -> Response:
        # Disabled unless the operator opted in by setting both the
        # dev-login token AND the auth secret (the secret is what makes
        # the minted cookie verifiable by the middleware). 404 — not
        # 401/403 — so the route is indistinguishable from "does not
        # exist" to anyone probing a box that hasn't opted in.
        configured = _dev_login_token()
        secret_set = bool(os.environ.get("ANTIEK_AUTH_SECRET", "").strip())
        if not configured or not secret_set:
            raise HTTPException(status_code=404, detail="Not Found")
        # Constant-time compare; an empty/incorrect token is also a 404 so
        # a probe can't distinguish "feature off" from "wrong token".
        if not token or not secrets.compare_digest(token.strip(), configured):
            raise HTTPException(status_code=404, detail="Not Found")
        # Mint under the operator identity so the existing cookie path in
        # the middleware (which checks cookie-email == ANTIEK_OPERATOR_EMAIL)
        # accepts the resulting session unchanged. Single-operator
        # invariant — same assumption the magic-link path already makes.
        allow = sorted(_resolve_allowlist())
        email = allow[0] if allow else "__operator__"
        if multi_user_enabled and account_store is not None:
            session_id = account_store.create_session(
                user_id="__operator__",
                email=email,
                ttl_seconds=_DEV_LOGIN_SESSION_MAX_AGE,
            )
            cookie = mint_session_cookie(
                user_id="__operator__",
                email=email,
                session_id=session_id,
            )
        else:
            cookie = mint_session_cookie(user_id="__operator__", email=email)
        response = RedirectResponse(url=_resolve_redirect(next), status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=cookie,
            max_age=_DEV_LOGIN_SESSION_MAX_AGE,
            **_cookie_kwargs(),
        )
        return response

    @app.post("/auth/logout", tags=["auth"])
    async def auth_logout(request: Request) -> Response:
        if multi_user_enabled and account_store is not None:
            cookie_value = request.cookies.get(SESSION_COOKIE_NAME, "")
            if cookie_value:
                try:
                    session_claims = verify_session_cookie(cookie_value)
                    if session_claims.session_id:
                        account_store.revoke_session(session_claims.session_id)
                except Exception:
                    pass
        response = Response(status_code=204)
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            **_cookie_kwargs(),
        )
        return response

    @app.get("/auth/me", response_model=AuthMeResponse, tags=["auth"])
    async def auth_me(request: Request) -> AuthMeResponse:
        # The middleware populates request.state on every request. If
        # we got here on the session-cookie path it has user_id+email
        # attached; if the middleware is bypassed (no auth env), we
        # still get the static operator identity.
        user_id = getattr(request.state, "user_id", None) or "__operator__"
        email = getattr(request.state, "user_email", None)
        method = getattr(request.state, "auth_method", "unauthenticated_local")
        scopes = sorted(getattr(request.state, "scopes", frozenset()))
        return AuthMeResponse(
            user_id=user_id,
            email=email,
            auth_method=method,
            scopes=scopes,
            is_operator="operator" in scopes,
        )
