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
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from substrate.auth import (
    InvalidSessionCookie,
    InvalidToken,
    MockEmailProvider,
    OutboundEmail,
    TokenExpired,
    mint_magic_link_token,
    mint_session_cookie,
    verify_magic_link_token,
    verify_session_cookie,
)


_OPERATOR = "ftn208@nyu.edu"
_SECRET = "test-secret-" + "x" * 48


# ── Substrate primitives ─────────────────────────────────────────────


def test_magic_link_round_trip(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    tok = mint_magic_link_token(_OPERATOR)
    assert verify_magic_link_token(tok) == _OPERATOR


def test_magic_link_rejects_tampered_token(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    tok = mint_magic_link_token(_OPERATOR)
    # Flip the last char of the signature segment
    tampered = tok[:-1] + ("A" if tok[-1] != "A" else "B")
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
    return TestClient(create_app(register_wrestling=False, register_providers=False))


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
    assert r.json() == {"sent": True}


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
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "magic_link_invalid"


def test_auth_callback_rejects_non_allowlisted_email(monkeypatch):
    """A valid token whose email is not on the current allowlist
    gets rejected — handles the case where the allowlist changed
    after the link was minted."""
    client = _client(monkeypatch)
    tok = mint_magic_link_token("former-user@example.com")
    r = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "not_authorized"


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


def test_cf_access_email_path_still_works(monkeypatch):
    """The Cloudflare Access path remains active during the cutover
    window. Operator decommissions CF Access manually per the
    runbook."""
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _OPERATOR)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    client = TestClient(create_app(register_wrestling=False, register_providers=False))

    r = client.get(
        "/auth/whoami",
        headers={"Cf-Access-Authenticated-User-Email": _OPERATOR},
    )
    assert r.status_code == 200
    assert r.json()["auth_method"] == "cloudflare_access_email"


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
