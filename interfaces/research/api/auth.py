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
from typing import Optional, Sequence
from urllib.parse import urlencode, urljoin

import re

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator

from substrate.auth import (
    EmailDeliveryFailure,
    InvalidToken,
    OutboundEmail,
    TokenExpired,
    get_email_provider,
    mint_magic_link_token,
    mint_session_cookie,
    verify_magic_link_token,
)


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
    email: Optional[str]
    auth_method: str


# ── Helpers ──────────────────────────────────────────────────────────


def _allowlist() -> frozenset[str]:
    """Comma-separated list in ``ANTIEK_OPERATOR_EMAIL`` (single
    email today; multi-user later). Falls back to the empty set,
    which means "deny everything" — the operator must configure the
    env var before the login flow can succeed."""
    raw = os.environ.get("ANTIEK_OPERATOR_EMAIL", "").strip()
    if not raw:
        return frozenset()
    return frozenset(
        part.strip().lower() for part in raw.split(",") if part.strip()
    )


def _public_base_url() -> str:
    return os.environ.get("ANTIEK_PUBLIC_BASE_URL", _DEFAULT_PUBLIC_BASE).rstrip("/") + "/"


def _build_magic_link(token: str, next_path: str) -> str:
    qs = urlencode({"token": token, "next": next_path or "/"})
    return urljoin(_public_base_url(), f"auth/callback?{qs}")


def _is_safe_relative(path: str) -> bool:
    """Only accept same-origin relative redirects. Protects against
    open-redirect to attacker-controlled URLs piggybacking on a
    legitimate magic link."""
    if not path:
        return False
    if path.startswith("//"):
        return False
    return path.startswith("/")


def _cookie_kwargs() -> dict:
    """HttpOnly + Secure + SameSite=Lax. ``Secure`` is unconditional
    on production; tests work because the test client doesn't
    enforce the flag."""
    secure = os.environ.get("ANTIEK_COOKIE_INSECURE", "").strip() != "1"
    return dict(
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


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


# ── Registration ─────────────────────────────────────────────────────


def register_auth_routes(
    app: FastAPI,
    *,
    extra_allowlist: Optional[Sequence[str]] = None,
) -> None:
    """Mount the four auth routes onto ``app``.

    ``extra_allowlist`` is an injection seam for tests; production
    reads the allowlist from ``ANTIEK_OPERATOR_EMAIL`` only.
    """

    extra = frozenset(e.strip().lower() for e in (extra_allowlist or ()) if e.strip())

    def _resolve_allowlist() -> frozenset[str]:
        return _allowlist() | extra

    @app.post(
        "/auth/request",
        response_model=AuthRequestResponse,
        tags=["auth"],
    )
    async def auth_request(payload: AuthRequestPayload) -> AuthRequestResponse:
        email = payload.email.strip().lower()
        next_path = payload.next if _is_safe_relative(payload.next) else "/"
        allowlist = _resolve_allowlist()
        if email in allowlist:
            token = mint_magic_link_token(email)
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
        next_path = next if _is_safe_relative(next) else "/"
        try:
            email = verify_magic_link_token(token)
        except TokenExpired:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "magic_link_expired",
                        "message": "This sign-in link expired. Request a new one.",
                    }
                },
            )
        except InvalidToken:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "magic_link_invalid",
                        "message": "This sign-in link is not valid.",
                    }
                },
            )
        if email not in _resolve_allowlist():
            # Defensive: token was valid but the allowlist changed
            # between request and click. Reject without leaking which
            # case we're in.
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "not_authorized",
                        "message": "This email is not authorized for Antiek.",
                    }
                },
            )
        cookie = mint_session_cookie(
            user_id="__operator__",
            email=email,
        )
        response = RedirectResponse(url=next_path, status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=cookie,
            max_age=60 * 60 * 24 * 30,  # 30 days
            **_cookie_kwargs(),
        )
        return response

    @app.post("/auth/logout", tags=["auth"])
    async def auth_logout() -> Response:
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
        return AuthMeResponse(user_id=user_id, email=email, auth_method=method)
