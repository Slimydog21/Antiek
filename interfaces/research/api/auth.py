"""Magic-link auth endpoints for Antiek.

PostHog-style: the platform owns its login surface. Cloudflare
Access is decommissioned at the runbook level (see
``infrastructure/runbooks/magic-link-auth.md``); the substrate
operates its own session cookies + email-delivered magic links.

Routes:

- ``POST /auth/request`` — body ``{"email": "..."}`` → mint an
  attempt, send the 4-digit code via the configured email provider,
  return ``{"sent": true, attempt_id, claim_secret}``. Always 200
  with the same shape even for non-allowlisted addresses, to avoid
  enumerating valid operators. The send (and the code) only ever
  happen for allowlisted emails; the code is NOT part of the API
  response, so typing it into the browser is real email-possession
  proof, not theater. Rate-limited per IP.
- ``GET /auth/callback?token=...&next=/`` — verify the token, set
  the session cookie, redirect to ``next`` (default ``/``).
- ``POST /auth/claim`` — body ``{"attempt_id, claim_secret}`` plus
  the optional ``code`` from the email. With a code: unlocks as soon
  as the code matches (single-device flow; 5 wrong tries invalidate
  the attempt; per-IP rate limit). Without a code: returns 202 until
  a second device approved via ``POST /auth/approve``, then 200.
- ``POST /auth/approve`` — mark an attempt approved (the device that
  clicked the email link). Requires an established session.
- ``POST /auth/logout`` — clear the cookie, 204.
- ``GET /auth/me`` — return the resolved session
  ``{user_id, email, auth_method}`` or 401 if no valid auth.

The middleware in ``app.py`` reads the same cookie name
``ANTIEK_SESSION``; this module's job is mint/clear, the
middleware's job is verify-on-every-request.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import threading
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode, urljoin

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator

from substrate.auth import (
    EmailDeliveryFailure,
    InvalidToken,
    OutboundEmail,
    PasskeyError,
    TokenExpired,
    authentication_options,
    complete_authentication,
    complete_registration,
    delete_credential,
    get_email_provider,
    list_credentials,
    mint_magic_link_token,
    mint_session_cookie,
    registration_options,
    verify_magic_link_token,
)

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
    avoid disclosing whether the email is allowlisted.

    ``device_code`` is deliberately NOT returned: the 4-digit code is
    the operator's email-possession proof, so it must only ever exist
    inside the delivered email. The browser learns it by the operator
    typing it, never from the API."""

    sent: bool = True
    attempt_id: str
    claim_secret: str


class AuthClaimPayload(BaseModel):
    attempt_id: str = Field(..., min_length=16, max_length=200)
    claim_secret: str = Field(..., min_length=16, max_length=200)
    # The 4-digit code from the email. Omit it to use the two-device
    # approval path (202 until POST /auth/approve); supply it for the
    # single-device "type the code" unlock.
    code: str | None = Field(default=None, min_length=4, max_length=4, pattern=r"^\d{4}$")


class AuthApprovePayload(BaseModel):
    attempt_id: str = Field(..., min_length=16, max_length=200)


class AuthMeResponse(BaseModel):
    """``GET /auth/me`` response."""

    user_id: str
    email: str | None
    auth_method: str


class PasskeyCeremonyPayload(BaseModel):
    ceremony_id: str = Field(..., min_length=16, max_length=200)
    credential: dict[str, Any]


class PasskeyRegistrationPayload(PasskeyCeremonyPayload):
    label: str = Field(default="My passkey", max_length=80)


class PasskeyStatusResponse(BaseModel):
    available: bool
    count: int | None = None


class _LoginAttempt:
    def __init__(self, *, email: str, claim_hash: str, next_path: str, device_code: str) -> None:
        self.email = email
        self.claim_hash = claim_hash
        self.next_path = next_path
        self.device_code = device_code
        self.created_at = time.time()
        self.approved = False
        self.claimed = False
        self.failed_code_attempts = 0


_ATTEMPT_TTL_SECONDS = 15 * 60
# A 4-digit code is 10,000 possibilities; without a failure cap an
# attacker who knows the operator's email could grind through them
# inside the 15-minute TTL. Five wrong tries invalidate the attempt.
_MAX_CODE_ATTEMPTS = 5
_attempts: dict[str, _LoginAttempt] = {}
_attempts_lock = threading.Lock()

# Per-IP sliding-window throttles for the two email-surface routes.
# In-process state is the honest deployment model here: the FastAPI
# service is pinned to one worker by the DuckDB single-writer
# invariant, so a process-local window is complete, not best-effort.
_REQUEST_RATE_LIMIT = 6    # POST /auth/request per minute per IP
_CLAIM_RATE_LIMIT = 30     # code-bearing POST /auth/claim per minute per IP
_THROTTLE_WINDOW_SECONDS = 60.0
_throttle: dict[str, list[float]] = {}
_throttle_lock = threading.Lock()


def reset_auth_throttles() -> None:
    """Test seam: clear the in-process rate-limit windows."""
    with _throttle_lock:
        _throttle.clear()


def _throttled(key: str, limit: int) -> bool:
    """Record one hit for ``key``; True when the caller is over limit."""
    now = time.monotonic()
    with _throttle_lock:
        hits = [t for t in _throttle.setdefault(key, []) if now - t < _THROTTLE_WINDOW_SECONDS]
        if len(hits) >= limit:
            _throttle[key] = hits
            return True
        hits.append(now)
        _throttle[key] = hits
        return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _digest_claim(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _new_attempt(*, email: str, next_path: str) -> tuple[str, str, str]:
    attempt_id = secrets.token_urlsafe(24)
    claim_secret = secrets.token_urlsafe(32)
    device_code = f"{secrets.randbelow(10000):04d}"
    now = time.time()
    with _attempts_lock:
        for key, attempt in list(_attempts.items()):
            if now - attempt.created_at > _ATTEMPT_TTL_SECONDS:
                del _attempts[key]
        # Bounded registry: a hostile caller cannot grow memory
        # without bound by minting attempts (each mint is already
        # per-IP throttled; this caps the aggregate too).
        while len(_attempts) >= 512:
            oldest_key = min(_attempts, key=lambda k: _attempts[k].created_at)
            del _attempts[oldest_key]
        _attempts[attempt_id] = _LoginAttempt(
            email=email,
            claim_hash=_digest_claim(claim_secret),
            next_path=next_path,
            device_code=device_code,
        )
    return attempt_id, claim_secret, device_code


# ── Helpers ──────────────────────────────────────────────────────────


def _allowlist() -> frozenset[str]:
    """Comma-separated list in ``ANTIEK_OPERATOR_EMAIL``.

    Empty set means deny magic-link sends until the operator configures
    the env var.
    """
    return operator_allowlist_from_env()


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


def _build_magic_link(token: str, next_path: str, attempt_id: str | None = None) -> str:
    params = {"token": token, "next": next_path or "/"}
    if attempt_id:
        params["attempt"] = attempt_id
    qs = urlencode(params)
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


def _format_magic_link_email(*, email: str, link: str, device_code: str) -> OutboundEmail:
    text = (
        "Your Antiek sign-in code\n"
        "\n"
        f"  {device_code}\n"
        "\n"
        "Type it into the Antiek sign-in screen where you started.\n"
        "Or open the link below to approve the sign-in from this device\n"
        "instead. The code and link expire in 15 minutes.\n"
        "\n"
        f"  {link}\n"
        "\n"
        "If you did not request this, ignore this email — no action will\n"
        "be taken.\n"
        "\n"
        "Antiek\n"
    )
    safe_link = html.escape(link, quote=True)
    html_body = f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;background:#f4f6f8;color:#172033;font-family:Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#ffffff;border:1px solid #d7dce2;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="padding:18px 24px;background:#172033;color:#ffffff;font-size:12px;font-weight:700;letter-spacing:1.4px;">
                ANTIEK / ACCESS DESK
              </td>
            </tr>
            <tr>
              <td style="padding:30px 24px 12px;">
                <div style="font-size:13px;color:#667085;margin-bottom:8px;">YOUR ANTIEK SIGN-IN CODE</div>
                <div style="font-family:'Courier New',monospace;font-size:42px;font-weight:700;letter-spacing:10px;color:#172033;">{device_code}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:10px 24px 28px;font-size:16px;line-height:1.55;color:#344054;">
                Type this code into the Antiek sign-in screen where you started.
                Prefer approving from here instead? Open the link below on this device.
              </td>
            </tr>
            <tr>
              <td style="padding:0 24px 30px;">
                <a href="{safe_link}" style="display:block;background:#f5c451;color:#172033;text-align:center;text-decoration:none;font-size:16px;font-weight:700;padding:15px 20px;border-radius:8px;">Review sign-in</a>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 24px;border-top:1px solid #eaecf0;font-size:12px;line-height:1.5;color:#667085;">
                This link expires in 15 minutes. If the button does not open, copy this address into your browser:<br>
                <span style="word-break:break-all;color:#475467;">{safe_link}</span>
              </td>
            </tr>
          </table>
          <div style="max-width:520px;padding:16px 8px;font-size:12px;line-height:1.5;color:#667085;">
            If you did not request this, ignore the message. Nothing will be unlocked.
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    return OutboundEmail(
        to=email,
        subject=f"Antiek sign-in · {device_code}",
        text_body=text,
        html_body=html_body,
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
    async def auth_request(payload: AuthRequestPayload, request: Request) -> AuthRequestResponse:
        if _throttled(f"request:{_client_ip(request)}", _REQUEST_RATE_LIMIT):
            raise HTTPException(
                status_code=429,
                detail={"code": "rate_limited", "message": "Too many sign-in requests. Wait a minute and try again."},
            )
        email = payload.email.strip().lower()
        next_path = payload.next if _is_safe_relative(payload.next) else "/"
        allowlist = _resolve_allowlist()
        attempt_id, claim_secret, device_code = _new_attempt(email=email, next_path=next_path)
        if email in allowlist:
            token = mint_magic_link_token(email)
            link = _build_magic_link(token, next_path, attempt_id)
            provider = get_email_provider()
            try:
                provider.send(
                    _format_magic_link_email(
                        email=email,
                        link=link,
                        device_code=device_code,
                    )
                )
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
        # device_code never leaves the server — the email is its only
        # channel, so typing it is genuine email-possession proof.
        return AuthRequestResponse(
            sent=True,
            attempt_id=attempt_id,
            claim_secret=claim_secret,
        )

    @app.get("/auth/callback", tags=["auth"])
    async def auth_callback(token: str, next: str = "/", attempt: str | None = None) -> Response:
        redirect_url = _resolve_redirect(next)
        try:
            email = verify_magic_link_token(token)
        except TokenExpired:
            return _redirect_login_error(error_code="magic_link_expired", next_path=next)
        except InvalidToken:
            return _redirect_login_error(error_code="magic_link_invalid", next_path=next)
        if email not in _resolve_allowlist():
            # Defensive: token was valid but the allowlist changed
            # between request and click. Reject without leaking which
            # case we're in.
            return _redirect_login_error(error_code="not_authorized", next_path=next)
        cookie = mint_session_cookie(
            user_id="__operator__",
            email=email,
        )
        # The first successful email proof is also the passkey bootstrap.
        # Keep the original destination, but pause on Login long enough to
        # create the device credential that makes future email unnecessary.
        if attempt:
            with _attempts_lock:
                pending = _attempts.get(attempt)
                valid_attempt = bool(
                    pending
                    and pending.email == email
                    and time.time() - pending.created_at <= _ATTEMPT_TTL_SECONDS
                )
                device_code = pending.device_code if valid_attempt and pending else ""
            if valid_attempt:
                redirect_url = _resolve_redirect(
                    f"/login?{urlencode({'approve': attempt, 'code': device_code})}"
                )
        elif not list_credentials():
            safe_next = next if _is_safe_relative(next) else "/"
            redirect_url = _resolve_redirect(
                f"/login?{urlencode({'setup': 'passkey', 'next': safe_next})}"
            )
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=cookie,
            max_age=60 * 60 * 24 * 30,  # 30 days
            **_cookie_kwargs(),
        )
        return response

    @app.post("/auth/approve", tags=["auth"])
    async def auth_approve(payload: AuthApprovePayload, request: Request) -> Response:
        email = getattr(request.state, "user_email", None)
        with _attempts_lock:
            pending = _attempts.get(payload.attempt_id)
            if (
                not email
                or not pending
                or pending.email != email
                or time.time() - pending.created_at > _ATTEMPT_TTL_SECONDS
            ):
                raise HTTPException(
                    status_code=410,
                    detail={"code": "login_attempt_expired", "message": "This sign-in request has expired."},
                )
            pending.approved = True
        return Response(status_code=204)

    @app.post("/auth/claim", tags=["auth"])
    async def auth_claim(payload: AuthClaimPayload, request: Request) -> Response:
        # Only code-bearing claims are rate-limited. The two-device
        # approval poll (claim without a code) is the operator's own
        # page polling every 1.8s — throttling it would break the
        # auto-open UX; it also carries no brute-force surface.
        if payload.code is not None and _throttled(f"claim:{_client_ip(request)}", _CLAIM_RATE_LIMIT):
            raise HTTPException(
                status_code=429,
                detail={"code": "rate_limited", "message": "Too many unlock attempts. Wait a minute and try again."},
            )
        with _attempts_lock:
            pending = _attempts.get(payload.attempt_id)
            valid_secret = bool(
                pending
                and secrets.compare_digest(pending.claim_hash, _digest_claim(payload.claim_secret))
            )
            if not pending or not valid_secret or time.time() - pending.created_at > _ATTEMPT_TTL_SECONDS:
                raise HTTPException(status_code=410, detail={"code": "login_attempt_expired", "message": "This sign-in request has expired."})
            if payload.code is not None:
                # Single-device flow: the typed code from the email is
                # the possession proof. Wrong tries are counted; the
                # whole attempt dies after five so a 10,000-space code
                # cannot be ground through inside its 15-minute TTL.
                code_ok = secrets.compare_digest(payload.code, pending.device_code)
                if not code_ok:
                    pending.failed_code_attempts += 1
                    if pending.failed_code_attempts >= _MAX_CODE_ATTEMPTS:
                        del _attempts[payload.attempt_id]
                        raise HTTPException(
                            status_code=410,
                            detail={"code": "login_attempt_locked", "message": "Too many wrong codes. Request a new sign-in."},
                        )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "invalid_code",
                            "message": "That code didn't match. Check the email and try again.",
                            "remaining_attempts": _MAX_CODE_ATTEMPTS - pending.failed_code_attempts,
                        },
                    )
                pending.failed_code_attempts = 0
            elif not pending.approved:
                # Two-device flow: keep waiting until the email-click
                # device approves (POST /auth/approve).
                return Response(status_code=202)
            if pending.claimed:
                raise HTTPException(status_code=410, detail={"code": "login_attempt_claimed", "message": "This sign-in request was already used."})
            pending.claimed = True
            email = pending.email
            next_path = pending.next_path
        cookie = mint_session_cookie(user_id="__operator__", email=email)
        response = Response(
            content=json.dumps({"authenticated": True, "setup_passkey": not bool(list_credentials()), "next": next_path}),
            media_type="application/json",
        )
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=cookie,
            max_age=60 * 60 * 24 * 30,
            **_cookie_kwargs(),
        )
        return response

    @app.get(
        "/auth/passkey/status",
        response_model=PasskeyStatusResponse,
        tags=["auth"],
    )
    async def auth_passkey_status(request: Request) -> PasskeyStatusResponse:
        credentials = list_credentials()
        # A logged-out browser only needs the branch bit to choose its primary
        # action.  Credential counts are account metadata, so return them only
        # to an established session.
        authenticated = bool(getattr(request.state, "user_id", None))
        return PasskeyStatusResponse(
            available=bool(credentials),
            count=len(credentials) if authenticated else None,
        )

    @app.post("/auth/passkey/login/options", tags=["auth"])
    async def auth_passkey_login_options() -> dict[str, Any]:
        if not list_credentials():
            raise HTTPException(
                status_code=404,
                detail={"code": "passkey_not_configured", "message": "No passkey is set up yet."},
            )
        return authentication_options()

    @app.post("/auth/passkey/login/verify", tags=["auth"])
    async def auth_passkey_login_verify(payload: PasskeyCeremonyPayload) -> Response:
        try:
            complete_authentication(
                ceremony_id=payload.ceremony_id,
                credential=payload.credential,
            )
        except PasskeyError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "passkey_verification_failed", "message": str(exc)},
            ) from exc
        allow = sorted(_resolve_allowlist())
        if not allow:
            raise HTTPException(
                status_code=503,
                detail={"code": "operator_email_missing", "message": "Operator email is not configured."},
            )
        cookie = mint_session_cookie(user_id="__operator__", email=allow[0])
        response = Response(status_code=204)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=cookie,
            max_age=60 * 60 * 24 * 30,
            **_cookie_kwargs(),
        )
        return response

    @app.post("/auth/passkey/register/options", tags=["auth"])
    async def auth_passkey_register_options(request: Request) -> dict[str, Any]:
        email = getattr(request.state, "user_email", None)
        if not email:
            allow = sorted(_resolve_allowlist())
            email = allow[0] if allow else "operator@antiek.ai"
        return registration_options(email=email)

    @app.post("/auth/passkey/register/verify", tags=["auth"])
    async def auth_passkey_register_verify(payload: PasskeyRegistrationPayload) -> dict[str, Any]:
        try:
            credential = complete_registration(
                ceremony_id=payload.ceremony_id,
                credential=payload.credential,
                label=payload.label,
            )
        except PasskeyError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "passkey_registration_failed", "message": str(exc)},
            ) from exc
        return {
            "registered": True,
            "label": credential.label,
            "backed_up": credential.backed_up,
        }

    @app.get("/auth/passkeys", tags=["auth"])
    async def auth_passkeys() -> dict[str, Any]:
        return {
            "passkeys": [
                {
                    "id": item.credential_id,
                    "label": item.label,
                    "backed_up": item.backed_up,
                    "created_at": item.created_at,
                    "last_used_at": item.last_used_at,
                }
                for item in list_credentials()
            ]
        }

    @app.delete("/auth/passkeys/{credential_id}", status_code=204, tags=["auth"])
    async def auth_passkey_delete(credential_id: str) -> Response:
        if not delete_credential(credential_id):
            raise HTTPException(status_code=404, detail="Passkey not found")
        return Response(status_code=204)

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
