"""Magic-link auth — substrate primitives + API flow.

Covers:
- mint/verify round-trip for magic-link tokens
- tamper, wrong-secret, expired tokens are rejected
- mint/verify round-trip for session cookies
- ``POST /auth/request`` only sends for allowlisted emails but always
  returns 200 (enumeration guard)
- ``GET /auth/callback`` issues a session cookie on valid tokens,
  rejects invalid / expired ones, blocks open-redirects via ``next``
- Cookie path 1 in the middleware accepts a freshly-issued session
- The other auth paths (bearer, CF Access email) still work — the
  cookie path is additive, not destructive

No external email sender involved; the MockEmailProvider records the
outbound payload in-memory so tests can inspect the magic link
content if needed.
"""

from __future__ import annotations

import time
from html import escape
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from substrate.auth import (
    InvalidSessionCookie,
    InvalidToken,
    MockEmailProvider,
    TokenExpired,
    mint_magic_link_token,
    mint_session_cookie,
    verify_magic_link_token,
    verify_session_cookie,
)
from substrate.auth.magic_link import MAGIC_LINK_TTL_SECONDS

_OPERATOR = "ftn208@nyu.edu"
_OPERATOR_SECOND = "the@faisalnazer.com"
_MULTI_OPERATOR_ENV = f"{_OPERATOR},{_OPERATOR_SECOND}"
_SECRET = "test-secret-" + "x" * 48


# ── Substrate primitives ─────────────────────────────────────────────


def test_magic_link_round_trip(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    tok = mint_magic_link_token(_OPERATOR)
    assert verify_magic_link_token(tok) == _OPERATOR


def test_magic_link_rejects_tampered_token(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    tok = mint_magic_link_token(_OPERATOR)
    # Tamper a char at the START of the signature segment. Flipping the LAST
    # b64url char can be a no-op — base64 boundary bits alias to the same decoded
    # bytes — which made this test intermittently DID-NOT-RAISE in CI. The first
    # signature char encodes the leading 6 bits of byte 0, so a different char
    # always changes the MAC: a guaranteed-rejected tamper.
    payload_b64, sig_b64 = tok.split(".", 1)
    flipped_sig = ("A" if sig_b64[0] != "A" else "B") + sig_b64[1:]
    tampered = f"{payload_b64}.{flipped_sig}"
    with pytest.raises(InvalidToken):
        verify_magic_link_token(tampered)


def test_magic_link_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    tok = mint_magic_link_token(_OPERATOR)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "different-" + "y" * 48)
    with pytest.raises(InvalidToken):
        verify_magic_link_token(tok)


def test_magic_link_expires(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    tok = mint_magic_link_token(_OPERATOR)
    with pytest.raises(TokenExpired):
        verify_magic_link_token(tok, max_age_seconds=-1)


def test_session_cookie_round_trip(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    cookie = mint_session_cookie(user_id="__operator__", email=_OPERATOR)
    claims = verify_session_cookie(cookie)
    assert claims.user_id == "__operator__"
    assert claims.email == _OPERATOR
    assert claims.issued_at <= int(time.time())


def test_session_cookie_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    cookie = mint_session_cookie(user_id="__operator__", email=_OPERATOR)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "different-" + "z" * 48)
    with pytest.raises(InvalidSessionCookie):
        verify_session_cookie(cookie)


# ── API flow ─────────────────────────────────────────────────────────


def _client(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _OPERATOR)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    # Existing magic-link contract tests model a device that has already
    # completed passkey onboarding. First-run redirection has its own test.
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [object()])
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def test_first_magic_link_bootstraps_passkey_before_original_destination(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [])
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(f"/auth/callback?token={tok}&next=/notebooks", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("/login?")
    query = parse_qs(urlparse(location).query)
    assert query == {"setup": ["passkey"], "next": ["/notebooks"]}
    assert SESSION_COOKIE_NAME in r.cookies


def test_auth_request_non_allowlisted_silent(monkeypatch):
    """A non-allowlisted email gets 200 sent:true (enumeration guard)
    but no email is actually sent."""
    monkeypatch.setattr(
        "interfaces.research.api.auth.get_email_provider",
        lambda: MockEmailProvider(log_to_stdout=False),
    )
    client = _client(monkeypatch)
    r = client.post("/auth/request", json={"email": "intruder@example.com"})
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert len(r.json()["attempt_id"]) >= 16
    assert len(r.json()["claim_secret"]) >= 16
    assert len(r.json()["device_code"]) == 4


def test_auth_request_allowlisted_sends_email(monkeypatch):
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr(
        "interfaces.research.api.auth.get_email_provider",
        lambda: sender,
    )
    client = _client(monkeypatch)
    r = client.post("/auth/request", json={"email": _OPERATOR})
    assert r.status_code == 200
    assert len(sender.sent) == 1
    assert sender.sent[0].email.to == _OPERATOR
    assert "/auth/callback?token=" in sender.sent[0].email.text_body


def test_auth_email_has_explicit_html_action_and_matching_code(monkeypatch):
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr(
        "interfaces.research.api.auth.get_email_provider",
        lambda: sender,
    )
    client = _client(monkeypatch)

    requested = client.post("/auth/request", json={"email": _OPERATOR}).json()
    email = sender.sent[0].email
    link = next(
        part.strip()
        for part in email.text_body.split()
        if "/auth/callback?" in part
    )

    assert email.subject.endswith(requested["device_code"])
    assert requested["device_code"] in email.text_body
    assert email.html_body is not None
    assert requested["device_code"] in email.html_body
    assert f'href="{escape(link, quote=True)}"' in email.html_body
    assert ">Review sign-in</a>" in email.html_body


def test_phone_approval_unlocks_original_browser(monkeypatch):
    """The email may be opened on a phone; the requesting browser claims its own session."""
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    client = _client(monkeypatch)
    requested = client.post("/auth/request", json={"email": _OPERATOR, "next": "/notebooks"}).json()

    link = next(part.strip() for part in sender.sent[0].email.text_body.split() if "/auth/callback?" in part)
    parsed_link = urlparse(link)
    callback = client.get(f"{parsed_link.path}?{parsed_link.query}", follow_redirects=False)
    assert callback.status_code == 302
    assert "approve=" in callback.headers["location"]
    assert f"code={requested['device_code']}" in callback.headers["location"]

    approved = client.post("/auth/approve", json={"attempt_id": requested["attempt_id"]})
    assert approved.status_code == 204

    client.cookies.clear()  # the callback cookie belongs to the phone, not this browser
    claimed = client.post(
        "/auth/claim",
        json={"attempt_id": requested["attempt_id"], "claim_secret": requested["claim_secret"]},
    )
    assert claimed.status_code == 200
    assert claimed.json() == {"authenticated": True, "setup_passkey": False, "next": "/notebooks"}
    assert SESSION_COOKIE_NAME in claimed.cookies

    replay = client.post(
        "/auth/claim",
        json={"attempt_id": requested["attempt_id"], "claim_secret": requested["claim_secret"]},
    )
    assert replay.status_code == 410


def test_handoff_cannot_be_approved_without_mailbox_session(monkeypatch):
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    client = _client(monkeypatch)
    requested = client.post("/auth/request", json={"email": _OPERATOR}).json()

    attempted = client.post("/auth/approve", json={"attempt_id": requested["attempt_id"]})
    assert attempted.status_code == 401
    pending = client.post(
        "/auth/claim",
        json={"attempt_id": requested["attempt_id"], "claim_secret": requested["claim_secret"]},
    )
    assert pending.status_code == 202


def test_auth_request_rejects_malformed_email(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/auth/request", json={"email": "not-an-email"})
    assert r.status_code == 422


def test_auth_callback_happy_path_sets_cookie(monkeypatch):
    client = _client(monkeypatch)
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(f"/auth/callback?token={tok}&next=/inv/abc", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/inv/abc"
    assert SESSION_COOKIE_NAME in r.cookies


def test_auth_callback_blocks_open_redirect(monkeypatch):
    client = _client(monkeypatch)
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(
        f"/auth/callback?token={tok}&next=https://evil.example.com",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/"  # falls back to safe default


def test_auth_callback_rejects_bad_token(monkeypatch):
    client = _client(monkeypatch)
    r = client.get("/auth/callback?token=garbage", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.headers["location"]
    assert "error=magic_link_invalid" in r.headers["location"]


def test_auth_callback_expired_redirects_to_login(monkeypatch):
    """Expired magic links redirect to Login with magic_link_expired, not JSON 400."""
    client = _client(monkeypatch)
    now = int(time.time())
    expired_at = now - MAGIC_LINK_TTL_SECONDS - 60
    monkeypatch.setattr("substrate.auth.magic_link.time.time", lambda: expired_at)
    tok = mint_magic_link_token(_OPERATOR)
    monkeypatch.setattr("substrate.auth.magic_link.time.time", lambda: now)
    r = client.get(f"/auth/callback?token={tok}&next=/inv/abc", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert "login" in loc
    assert "error=magic_link_expired" in loc


def test_auth_callback_error_redirect_blocks_open_redirect_next(monkeypatch):
    """Error redirects sanitize ``next`` — external URLs cannot ride on bad tokens."""
    client = _client(monkeypatch)
    r = client.get(
        "/auth/callback?token=garbage&next=https://evil.com",
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers["location"]
    assert "login" in loc
    assert "error=magic_link_invalid" in loc
    assert "evil.com" not in loc
    assert "next=%2F" in loc or "next=/" in loc


def test_auth_callback_rejects_non_allowlisted_email(monkeypatch):
    """A valid token whose email is not on the current allowlist
    gets rejected — handles the case where the allowlist changed
    after the link was minted."""
    client = _client(monkeypatch)
    tok = mint_magic_link_token("former-user@example.com")
    r = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
    assert r.status_code == 302
    assert "error=not_authorized" in r.headers["location"]


def test_session_cookie_authorizes_middleware(monkeypatch):
    """After /auth/callback issues a cookie, /auth/whoami (which the
    middleware protects) returns the cookie identity."""
    client = _client(monkeypatch)
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
    assert r.status_code == 302

    r2 = client.get("/auth/whoami")
    assert r2.status_code == 200
    assert r2.json()["auth_method"] == "antiek_session_cookie"


def test_multi_email_allowlist_middleware_accepts_both_operators(monkeypatch):
    """Comma-separated ANTIEK_OPERATOR_EMAIL: callback + middleware must
    accept each listed address (SPR-06 OPS-MIDDLEWARE-COMMA)."""
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _MULTI_OPERATOR_ENV)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))

    for email in (_OPERATOR, _OPERATOR_SECOND):
        tok = mint_magic_link_token(email)
        r = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
        assert r.status_code == 302, email
        assert SESSION_COOKIE_NAME in r.cookies, email

        r2 = client.get("/auth/whoami")
        assert r2.status_code == 200, email
        assert r2.json()["auth_method"] == "antiek_session_cookie"


def test_logout_clears_cookie(monkeypatch):
    client = _client(monkeypatch)
    tok = mint_magic_link_token(_OPERATOR)
    client.get(f"/auth/callback?token={tok}", follow_redirects=False)

    r = client.post("/auth/logout")
    assert r.status_code == 204

    # Subsequent request without cookie hits 401
    fresh = TestClient(create_app(register_wrestling=False, register_providers=False))
    r2 = fresh.get("/auth/whoami")
    assert r2.status_code == 401


def test_bearer_path_still_works_when_secret_set(monkeypatch):
    """Adding the cookie path must not break the existing bearer
    path. Multi-path additive guarantee from app.py."""
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _OPERATOR)
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "machine-token")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    client = TestClient(create_app(register_wrestling=False, register_providers=False))

    r = client.get(
        "/auth/whoami",
        headers={"Authorization": "Bearer machine-token"},
    )
    assert r.status_code == 200
    assert r.json()["auth_method"] == "bearer_token"


def test_cf_access_email_header_cannot_replace_signed_session(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _OPERATOR)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    client = TestClient(create_app(register_wrestling=False, register_providers=False))

    r = client.get(
        "/auth/whoami",
        headers={"Cf-Access-Authenticated-User-Email": _OPERATOR},
    )
    assert r.status_code == 401


def test_email_provider_factory_default_mock(monkeypatch):
    """Default ANTIEK_EMAIL_PROVIDER → mock; setting to resend
    selects ResendEmailProvider."""
    monkeypatch.delenv("ANTIEK_EMAIL_PROVIDER", raising=False)
    from substrate.auth import get_email_provider
    assert get_email_provider().name == "mock"

    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "resend")
    assert get_email_provider().name == "resend"


def test_cross_origin_callback_redirects_to_frontend(monkeypatch):
    """When ANTIEK_FRONTEND_BASE_URL is set, the callback redirect
    is absolute to the frontend host so the browser lands on Pages
    with the cookie set (cross-origin deployment)."""
    monkeypatch.setenv("ANTIEK_FRONTEND_BASE_URL", "https://antiek.ai")
    client = _client(monkeypatch)
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(f"/auth/callback?token={tok}&next=/notebooks", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://antiek.ai/notebooks"


def test_public_base_url_drives_absolute_redirect(monkeypatch):
    """Lived bug: with only ANTIEK_PUBLIC_BASE_URL=https://antiek.ai
    set (the runbook's single-host config) and no
    ANTIEK_FRONTEND_BASE_URL, the callback used to emit a relative
    ``Location: /`` — which the browser resolved against the API
    origin, landing the operator on api.antiek.ai instead of the app.
    The redirect must be absolute to the public app host."""
    monkeypatch.setenv("ANTIEK_PUBLIC_BASE_URL", "https://antiek.ai")
    monkeypatch.delenv("ANTIEK_FRONTEND_BASE_URL", raising=False)
    client = _client(monkeypatch)
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(f"/auth/callback?token={tok}&next=/notebooks", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://antiek.ai/notebooks"


def test_cookie_domain_set_when_env_configured(monkeypatch):
    """ANTIEK_COOKIE_DOMAIN=.antiek.ai is what lets the cookie cross
    from api.antiek.ai to antiek.ai on the same parent domain."""
    monkeypatch.setenv("ANTIEK_COOKIE_DOMAIN", ".antiek.ai")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "")
    client = _client(monkeypatch)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")  # so TestClient receives it
    tok = mint_magic_link_token(_OPERATOR)
    r = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
    assert r.status_code == 302
    set_cookie = r.headers.get("set-cookie", "")
    assert "Domain=.antiek.ai" in set_cookie


def test_magic_link_uses_api_base_when_set(monkeypatch):
    """ANTIEK_API_BASE_URL points the magic link at the FastAPI host
    even when ANTIEK_PUBLIC_BASE_URL is the frontend."""
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr(
        "interfaces.research.api.auth.get_email_provider",
        lambda: sender,
    )
    monkeypatch.setenv("ANTIEK_API_BASE_URL", "https://api.antiek.ai")
    monkeypatch.setenv("ANTIEK_PUBLIC_BASE_URL", "https://antiek.ai")
    client = _client(monkeypatch)
    r = client.post("/auth/request", json={"email": _OPERATOR})
    assert r.status_code == 200
    body = sender.sent[0].email.text_body
    import re

    m = re.search(r"https://[^\s]+", body)
    assert m
    assert m.group(0).startswith("https://api.antiek.ai/auth/callback")


def test_magic_link_url_carries_safe_next(monkeypatch):
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr(
        "interfaces.research.api.auth.get_email_provider",
        lambda: sender,
    )
    client = _client(monkeypatch)
    r = client.post(
        "/auth/request",
        json={"email": _OPERATOR, "next": "/notebooks"},
    )
    assert r.status_code == 200
    body = sender.sent[0].email.text_body
    # Extract the link
    import re

    m = re.search(r"https://[^\s]+", body)
    assert m
    url = urlparse(m.group(0))
    qs = parse_qs(url.query)
    assert qs.get("next") == ["/notebooks"]


# ── Dev-login (temporary agent / computer-use access) ─────────────────


_DEV_TOKEN = "dev-login-" + "q" * 40


def test_dev_login_disabled_returns_404(monkeypatch):
    """Without ANTIEK_DEV_LOGIN_TOKEN the route is invisible — 404 even
    for a syntactically valid request. A probe can't tell the feature
    exists on a box that hasn't opted in."""
    client = _client(monkeypatch)
    monkeypatch.delenv("ANTIEK_DEV_LOGIN_TOKEN", raising=False)
    r = client.get(f"/auth/dev-login?token={_DEV_TOKEN}", follow_redirects=False)
    assert r.status_code == 404
    assert SESSION_COOKIE_NAME not in r.cookies


def test_dev_login_wrong_token_returns_404(monkeypatch):
    """Feature on, wrong token: same 404 as feature-off — no oracle that
    distinguishes "wrong token" from "feature disabled"."""
    client = _client(monkeypatch)
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _DEV_TOKEN)
    r = client.get("/auth/dev-login?token=not-the-token", follow_redirects=False)
    assert r.status_code == 404
    assert SESSION_COOKIE_NAME not in r.cookies


def test_dev_login_missing_token_returns_404(monkeypatch):
    """Feature on, no token query param at all: still 404."""
    client = _client(monkeypatch)
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _DEV_TOKEN)
    r = client.get("/auth/dev-login", follow_redirects=False)
    assert r.status_code == 404


def test_dev_login_requires_auth_secret(monkeypatch):
    """The minted cookie is only verifiable when ANTIEK_AUTH_SECRET is
    set, so the route 404s without it rather than minting a dead cookie
    (or 500ing)."""
    client = _client(monkeypatch)
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _DEV_TOKEN)
    monkeypatch.delenv("ANTIEK_AUTH_SECRET", raising=False)
    r = client.get(f"/auth/dev-login?token={_DEV_TOKEN}", follow_redirects=False)
    assert r.status_code == 404


def test_dev_login_happy_path_sets_cookie_and_authorizes(monkeypatch):
    """Correct token: 302 + session cookie, and the cookie carries the
    operator identity so the middleware-protected /auth/whoami accepts
    it via the existing antiek_session_cookie path — unchanged."""
    client = _client(monkeypatch)
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _DEV_TOKEN)
    r = client.get(f"/auth/dev-login?token={_DEV_TOKEN}", follow_redirects=False)
    assert r.status_code == 302
    assert SESSION_COOKIE_NAME in r.cookies

    r2 = client.get("/auth/whoami")
    assert r2.status_code == 200
    assert r2.json()["auth_method"] == "antiek_session_cookie"


def test_dev_login_blocks_open_redirect(monkeypatch):
    """A malicious ``next`` can't bounce the browser off-origin after the
    cookie is set — same open-redirect guard as /auth/callback."""
    client = _client(monkeypatch)
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _DEV_TOKEN)
    r = client.get(
        f"/auth/dev-login?token={_DEV_TOKEN}&next=//evil.example.com/x",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "evil.example.com" not in r.headers["location"]
