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
  happen for any valid email when signup is open, or an admitted existing
  account/operator when it is closed; the code is NOT part of the API
  response, so typing it into the browser is real email-possession
  proof, not theater. Rate-limited per IP and normalized email.
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

import asyncio
import hashlib
import html
import json
import logging
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
    InvalidToken,
    MockEmailProvider,
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
from substrate.auth.accounts import (
    AccountStoreError,
    account_for_email,
    account_for_session,
    account_for_verified_email,
    account_for_verified_legacy_passkey,
    account_registry_active,
    legacy_operator_email,
    open_signup_enabled,
)

from .operator_allowlist import operator_allowlist_from_env

_LOGGER = logging.getLogger(__name__)

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
        if not value.isascii():
            raise ValueError("email must use an ASCII address")
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
        self.callback_used = False
        self.callback_token_hash: str | None = None
        self.failed_code_attempts = 0


_ATTEMPT_TTL_SECONDS = 15 * 60
# A 4-digit code is 10,000 possibilities; without a failure cap an
# attacker who knows the operator's email could grind through them
# inside the 15-minute TTL. Five wrong tries invalidate the attempt.
_MAX_CODE_ATTEMPTS = 5
_attempts: dict[str, _LoginAttempt] = {}
_attempts_lock = threading.Lock()

# The per-attempt cap alone is reset by the attacker: POST /auth/request
# is open and mints a fresh attempt (fresh code, fresh counter) on demand,
# so five guesses per attempt grinds the 10,000 space in ~2,000 requests.
# Wrong codes are therefore also counted per EMAIL, across attempts, and
# the budget is cleared only by a proof the attacker cannot produce: the
# email link (/auth/callback) or a correct code. Never by time, never by a
# new attempt. Once spent, typed codes for that address are refused (even
# the right one); the email link and passkeys still sign in.
_MAX_CODE_FAILURES_PER_EMAIL = 10
_MAX_TRACKED_CODE_FAILURE_EMAILS = 1024
_code_failures: dict[str, int] = {}  # guarded by _attempts_lock

# Sliding-window throttles for request IPs, recipient emails and claim IPs.
# In-process state is the honest deployment model here: the FastAPI
# service is pinned to one worker by the DuckDB single-writer
# invariant, so a process-local window is complete, not best-effort.
_REQUEST_RATE_LIMIT = 6    # POST /auth/request per minute per IP
_REQUEST_EMAIL_RATE_LIMIT = 6  # POST /auth/request per minute across recipient IPs
_CLAIM_RATE_LIMIT = 30     # code-bearing POST /auth/claim per minute per IP
_THROTTLE_WINDOW_SECONDS = 60.0
_MAX_TRACKED_THROTTLE_KEYS = 4096
_throttle: dict[str, list[float]] = {}
_throttle_lock = threading.Lock()


def reset_auth_throttles() -> None:
    """Test seam: clear the in-process rate-limit windows and the
    per-email code-failure budgets."""
    with _throttle_lock:
        _throttle.clear()
    with _attempts_lock:
        _code_failures.clear()


def _record_code_failure(email: str, protected: frozenset[str]) -> None:
    """Spend one unit of ``email``'s code budget. Caller holds _attempts_lock.

    The registry is bounded, but eviction never drops an allowlisted
    address: evicting by age would let a caller clear the operator's count
    by spraying misses at throwaway emails.
    """
    if email not in _code_failures and len(_code_failures) >= _MAX_TRACKED_CODE_FAILURE_EMAILS:
        if account_registry_active():
            return  # New code entry is refused until mailbox proof frees capacity.
        for key in _code_failures:
            if key not in protected:
                del _code_failures[key]
                break
    _code_failures[email] = _code_failures.get(email, 0) + 1


def _throttled(key: str, limit: int) -> bool:
    """Record one hit for ``key``; True when the caller is over limit."""
    now = time.monotonic()
    with _throttle_lock:
        hits = [t for t in _throttle.get(key, []) if now - t < _THROTTLE_WINDOW_SECONDS]
        if key not in _throttle and len(_throttle) >= _MAX_TRACKED_THROTTLE_KEYS:
            # Reclaim only expired windows. Evicting an active recipient
            # would let sprayed addresses renew another inbox's send budget.
            expired = [
                tracked for tracked, timestamps in _throttle.items()
                if not timestamps or now - timestamps[-1] >= _THROTTLE_WINDOW_SECONDS
            ]
            for tracked in expired:
                del _throttle[tracked]
            if len(_throttle) >= _MAX_TRACKED_THROTTLE_KEYS:
                return True
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

    async def _email_allowed(email: str) -> bool:
        if email in _resolve_allowlist() or open_signup_enabled():
            return True
        if not account_registry_active():
            return False
        try:
            return await asyncio.to_thread(account_for_email, email) is not None
        except AccountStoreError:
            return False

    async def _session_subject(email: str) -> str:
        if not account_registry_active():
            if email not in _resolve_allowlist():
                raise HTTPException(status_code=410, detail="login_attempt_expired")
            return "__operator__"
        legacy = legacy_operator_email() if email in _resolve_allowlist() else None
        try:
            account = await asyncio.to_thread(
                account_for_verified_email, email, legacy_operator_email=legacy,
            )
        except AccountStoreError:
            raise HTTPException(status_code=503, detail="account_storage_unavailable") from None
        return account.user_id

    def _credential_owners(request: Request) -> frozenset[str]:
        subject = getattr(request.state, "user_id", None)
        if not isinstance(subject, str) or not subject:
            raise HTTPException(status_code=401, detail="authenticated_account_required")
        owners = {subject}
        legacy = getattr(request.state, "legacy_owner_user_id", None)
        if isinstance(legacy, str):
            owners.add(legacy)
        return frozenset(owners)

    def _credentials_for(request: Request) -> list[Any]:
        credentials = list_credentials()
        if not account_registry_active():
            return credentials
        owners = _credential_owners(request)
        return [item for item in credentials if item.user_id in owners]

    @app.post(
        "/auth/request",
        response_model=AuthRequestResponse,
        tags=["auth"],
    )
    async def auth_request(payload: AuthRequestPayload, request: Request) -> AuthRequestResponse:
        email = payload.email
        if _throttled(f"request:{_client_ip(request)}", _REQUEST_RATE_LIMIT) or _throttled(
            f"request-email:{_digest_claim(email)}", _REQUEST_EMAIL_RATE_LIMIT,
        ):
            raise HTTPException(
                status_code=429,
                detail={"code": "rate_limited", "message": "Too many sign-in requests. Wait a minute and try again."},
                headers={"Retry-After": "60"},
            )
        next_path = payload.next if _is_safe_relative(payload.next) else "/"
        attempt_id, claim_secret, device_code = _new_attempt(email=email, next_path=next_path)
        if await _email_allowed(email):
            # Token creation, link construction and delivery can each fail.
            # Keep their response identical to an ineligible address so a
            # provider or key failure cannot reveal account membership.
            # Log only the failure type, never the address or login proof.
            try:
                token = (
                    mint_magic_link_token(email, attempt_id=attempt_id)
                    if account_registry_active() else mint_magic_link_token(email)
                )
                with _attempts_lock:
                    pending = _attempts.get(attempt_id)
                    if pending is not None:
                        pending.callback_token_hash = _digest_claim(token)
                link = _build_magic_link(token, next_path, attempt_id)
                provider = get_email_provider()
                if account_registry_active() and isinstance(provider, MockEmailProvider):
                    # A mock sender is not an inbox. Never expose public login
                    # proofs through its default stdout development logger.
                    provider.log_to_stdout = False
                await asyncio.to_thread(
                    provider.send,
                    _format_magic_link_email(
                        email=email,
                        link=link,
                        device_code=device_code,
                    )
                )
            except Exception as exc:  # noqa: BLE001 -- see below, the breadth IS the fix
                # BROAD ON PURPOSE, and this is the third iteration on this one branch.
                #
                # v1 returned 503 for an allowlisted address and 200 otherwise: a membership
                # oracle in the status code. v2 replaced the 503 with a fall-through and
                # guarded only `provider.send()`, leaving three calls that run exclusively for
                # allowlisted addresses able to raise a 500 nobody else sees. v3 catches
                # `EmailDeliveryFailure` and STILL leaked, because the failure that actually
                # happens in practice -- a provider that is not configured -- raises a
                # config error, not a delivery error. My own test caught that.
                #
                # The property is not "handle the exception this layer defines". It is
                # "nothing reachable only by an allowlisted address may change the response".
                # Catching narrowly cannot express that, because the set of possible failures
                # is owned by everything downstream. So the breadth is the specification:
                # log the type, return what everyone else gets.
                _LOGGER.warning("Sign-in email dispatch failed (%s)", type(exc).__name__)
        # The status and body shape do not disclose allowlist membership.
        # Synchronous delivery can still differ in latency; this is not a
        # constant-time endpoint.
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
        if not await _email_allowed(email):
            # Defensive: token was valid but the allowlist changed
            # between request and click. Reject without leaking which
            # case we're in.
            return _redirect_login_error(error_code="not_authorized", next_path=next)
        # Mailbox possession proven: the attacker cannot produce this, so
        # it (not time, not a fresh attempt) is what reopens code entry.
        with _attempts_lock:
            if account_registry_active():
                pending = _attempts.get(attempt or "")
                if (
                    pending is None or pending.email != email or pending.claimed
                    or pending.callback_used
                    or pending.callback_token_hash is None
                    or not secrets.compare_digest(pending.callback_token_hash, _digest_claim(token))
                    or time.time() - pending.created_at > _ATTEMPT_TTL_SECONDS
                ):
                    return _redirect_login_error(error_code="magic_link_invalid", next_path=next)
                pending.callback_used = True
            _code_failures.pop(email, None)
        cookie = mint_session_cookie(
            user_id=await _session_subject(email),
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
        allowlist = _resolve_allowlist()
        with _attempts_lock:
            candidate = _attempts.get(payload.attempt_id)
            candidate_email = candidate.email if candidate is not None else None
        email_allowed = await _email_allowed(candidate_email) if candidate_email else False
        with _attempts_lock:
            pending = _attempts.get(payload.attempt_id)
            valid_secret = bool(
                pending
                and secrets.compare_digest(pending.claim_hash, _digest_claim(payload.claim_secret))
            )
            if not pending or not valid_secret or time.time() - pending.created_at > _ATTEMPT_TTL_SECONDS:
                raise HTTPException(status_code=410, detail={"code": "login_attempt_expired", "message": "This sign-in request has expired."})
            if pending.claimed:
                raise HTTPException(status_code=410, detail={"code": "login_attempt_claimed", "message": "This sign-in request was already used."})
            if payload.code is not None:
                # Single-device flow: the typed code from the email is
                # the possession proof. Wrong tries are counted; the
                # whole attempt dies after five so a 10,000-space code
                # cannot be ground through inside its 15-minute TTL.
                if (
                    _code_failures.get(pending.email, 0) >= _MAX_CODE_FAILURES_PER_EMAIL
                    or (account_registry_active() and pending.email not in _code_failures
                        and len(_code_failures) >= _MAX_TRACKED_CODE_FAILURE_EMAILS)
                ):
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "code": "code_entry_locked",
                            "message": "Too many wrong codes for this address. Sign in with the link in the email instead.",
                        },
                    )
                # A non-allowlisted address never matches, so it fails
                # exactly like a wrong code: no allowlist oracle here.
                code_ok = (
                    secrets.compare_digest(payload.code, pending.device_code)
                    and email_allowed
                )
                if not code_ok:
                    pending.failed_code_attempts += 1
                    _record_code_failure(pending.email, allowlist)
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
                _code_failures.pop(pending.email, None)
            elif not pending.approved:
                # Two-device flow: keep waiting until the email-click
                # device approves (POST /auth/approve).
                return Response(status_code=202)
            if not email_allowed:
                # Approval proves mailbox possession, not current sign-in
                # eligibility or an operator role.
                raise HTTPException(status_code=410, detail={"code": "login_attempt_expired", "message": "This sign-in request has expired."})
            pending.claimed = True
            email = pending.email
            next_path = pending.next_path
        subject = await _session_subject(email)
        cookie = mint_session_cookie(user_id=subject, email=email)
        credentials = list_credentials()
        if account_registry_active():
            credentials = [item for item in credentials if item.user_id == subject]
        response = Response(
            content=json.dumps({"authenticated": True, "setup_passkey": not bool(credentials), "next": next_path}),
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
        # A logged-out browser only needs the branch bit to choose its primary
        # action.  Credential counts are account metadata, so return them only
        # to an established session.
        authenticated = bool(getattr(request.state, "user_id", None))
        account_mode = account_registry_active()
        if account_mode and not authenticated:
            # Advertise the sign-in capability, not another account's inventory.
            return PasskeyStatusResponse(available=True, count=None)
        credentials = list_credentials()
        if account_mode:
            subject = getattr(request.state, "user_id", None)
            credentials = [item for item in credentials if item.user_id == subject]
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
            credential = complete_authentication(
                ceremony_id=payload.ceremony_id,
                credential=payload.credential,
            )
        except PasskeyError as exc:
            # ONE message for every PasskeyError. `substrate/auth/passkeys.py:298-313` raises
            # "This passkey is not registered with Antiek." for a missing candidate and
            # "Antiek could not verify that passkey." for a stored one with invalid proof, and
            # publishing `str(exc)` answered "is this credential registered?" for anyone who
            # supplied an id. Measured: a synthetic stored credential and an unregistered id
            # returned different text, both 400. The cause is logged, where it is useful, and
            # not published, where it is not.
            _LOGGER.warning("passkey verification failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "passkey_verification_failed",
                    "message": "Antiek could not verify that passkey. Try again.",
                },
            ) from exc
        retained_email = legacy_operator_email()
        if credential.user_id == "__operator__" and retained_email is not None:
            try:
                account = await asyncio.to_thread(
                    account_for_verified_legacy_passkey,
                    credential,
                    operator_emails=_resolve_allowlist(),
                )
            except AccountStoreError:
                account = None
            if account is None:
                raise HTTPException(status_code=400, detail="passkey_verification_failed")
            subject, email = account.user_id, account.email
        elif account_registry_active():
            try:
                if credential.user_id == "__operator__":
                    account = None
                elif isinstance(credential.email, str):
                    account = await asyncio.to_thread(
                        account_for_session, credential.user_id, credential.email,
                    )
                else:
                    account = None
            except AccountStoreError:
                account = None
            if account is None:
                raise HTTPException(status_code=400, detail="passkey_verification_failed")
            subject, email = account.user_id, account.email
        else:
            allow = sorted(_resolve_allowlist())
            if not allow:
                raise HTTPException(
                    status_code=503,
                    detail={"code": "operator_email_missing", "message": "Operator email is not configured."},
                )
            if credential.user_id == "__operator__":
                retained = legacy_operator_email()
                if retained is not None and retained in allow:
                    email = retained
                elif len(allow) == 1:
                    email = allow[0]
                else:
                    raise HTTPException(status_code=503, detail="legacy_passkey_identity_unbound")
                subject = "__operator__"
            else:
                # Disabling signup must never upgrade an existing public
                # credential to the operator or borrow the operator's keys.
                if credential.email is None or credential.email not in allow:
                    raise HTTPException(status_code=400, detail="passkey_verification_failed")
                try:
                    account = await asyncio.to_thread(
                        account_for_session, credential.user_id, credential.email,
                    )
                except AccountStoreError:
                    account = None
                if account is None:
                    raise HTTPException(status_code=400, detail="passkey_verification_failed")
                subject, email = account.user_id, account.email
        cookie = mint_session_cookie(user_id=subject, email=email)
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
        if account_registry_active():
            _credential_owners(request)
            return registration_options(email=email, user_id=request.state.user_id)
        return registration_options(email=email)

    @app.post("/auth/passkey/register/verify", tags=["auth"])
    async def auth_passkey_register_verify(payload: PasskeyRegistrationPayload, request: Request) -> dict[str, Any]:
        try:
            kwargs = {"user_id": request.state.user_id} if account_registry_active() else {}
            if account_registry_active():
                _credential_owners(request)
            credential = complete_registration(
                ceremony_id=payload.ceremony_id,
                credential=payload.credential,
                label=payload.label,
                **kwargs,
            )
        except PasskeyError as exc:
            # The SAME boundary as verification, and my first attempt at this fixed only that
            # one. The property is not "the verification route does not leak" -- it is that no
            # passkey route answers whether a credential id is known, and this handler publishes
            # the same `str(exc)` from the same exception family. Found by reading main rather
            # than my own branch, which is where the miss had been hiding.
            _LOGGER.warning("passkey registration failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "passkey_registration_failed",
                    "message": "Antiek could not register that passkey. Try again.",
                },
            ) from exc
        return {
            "registered": True,
            "label": credential.label,
            "backed_up": credential.backed_up,
        }

    @app.get("/auth/passkeys", tags=["auth"])
    async def auth_passkeys(request: Request) -> dict[str, Any]:
        return {
            "passkeys": [
                {
                    "id": item.credential_id,
                    "label": item.label,
                    "backed_up": item.backed_up,
                    "created_at": item.created_at,
                    "last_used_at": item.last_used_at,
                }
                for item in _credentials_for(request)
            ]
        }

    @app.delete("/auth/passkeys/{credential_id}", status_code=204, tags=["auth"])
    async def auth_passkey_delete(credential_id: str, request: Request) -> Response:
        owners = _credential_owners(request) if account_registry_active() else None
        deleted = (
            delete_credential(credential_id, owner_ids=owners)
            if owners is not None else delete_credential(credential_id)
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Passkey not found")
        return Response(status_code=204)

    @app.get("/auth/dev-login", tags=["auth"])
    async def auth_dev_login(token: str = "", next: str = "/") -> Response:
        if account_registry_active():
            # An issued-account service requires mailbox/passkey proof,
            # including when signup is subsequently closed.
            raise HTTPException(status_code=404, detail="Not Found")
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
        if not token or not secrets.compare_digest(
            token.strip().encode("utf-8"), configured.encode("utf-8")
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        # Mint under the operator identity so the existing cookie path in
        # the middleware (which checks cookie-email == ANTIEK_OPERATOR_EMAIL)
        # accepts the resulting session unchanged. Single-operator
        # invariant — same assumption the magic-link path already makes.
        allow = sorted(_resolve_allowlist())
        if not allow:
            # The middleware admits a session cookie only for an
            # allowlisted email, so without one this would mint a dead
            # cookie. Refuse loudly, as passkey login does.
            raise HTTPException(
                status_code=503,
                detail={"code": "operator_email_missing", "message": "Operator email is not configured."},
            )
        cookie = mint_session_cookie(
            user_id="__operator__",
            email=allow[0],
            max_age_seconds=_DEV_LOGIN_SESSION_MAX_AGE,
        )
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
