"""Typed-code sign-in: the lockout must hold across attempts, and a code
can only ever mint a session for an allowlisted address.

Two audit findings (wave 4, cluster auth), both reproduced on main before
the fix landed:

C01. ``_MAX_CODE_ATTEMPTS`` was counted on one ``_LoginAttempt``, and the
fifth miss deleted only that attempt. ``POST /auth/request`` is an open
path that mints a fresh attempt (fresh 4-digit code, fresh counter) for
any caller, so the lockout's reset was produced by the attacker: five
guesses per attempt, ~2,000 attempts per expected success, and the audit
harness took over a full operator session after 459 attempts without ever
reading the mailbox. The budget now lives on the EMAIL and is cleared only
by a proof the attacker cannot produce.

C02. ``/auth/claim`` never checked the allowlist. It minted an operator
session for whatever email the attempt carried, and the middleware
accepted any signed cookie when ``ANTIEK_OPERATOR_EMAIL`` was empty
(bearer-token + auth-secret deployments), so brute-forcing a code for
``attacker@evil.test`` — whose email is never even sent — was a takeover.

These tests read the email-only device code straight from the server's
attempt registry where a brute-forcer would have to guess it: that stands
in for "the attacker eventually guesses right" without 2,000 round trips.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from interfaces.research.api import auth as auth_module
from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME, reset_auth_throttles
from substrate.auth import MockEmailProvider, mint_session_cookie

_OPERATOR = "ftn208@nyu.edu"
_ATTACKER = "attacker@evil.test"
_SECRET = "test-secret-" + "x" * 48
_DEV_TOKEN = "dev-login-" + "q" * 40


@pytest.fixture
def sender(monkeypatch: pytest.MonkeyPatch) -> MockEmailProvider:
    provider = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: provider)
    return provider


def _app_client(monkeypatch: pytest.MonkeyPatch, *, operator_email: str | None) -> TestClient:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    if operator_email is None:
        # The bearer-token + auth-secret deployment with no email allowlist:
        # enforcement is ON (the token), but nobody is an operator by email.
        monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
        monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "machine-token-" + "m" * 32)
    else:
        monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", operator_email)
        monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [object()])
    reset_auth_throttles()
    return TestClient(create_app(register_wrestling=False, register_providers=False))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, sender: MockEmailProvider) -> Iterator[TestClient]:
    yield _app_client(monkeypatch, operator_email=_OPERATOR)
    reset_auth_throttles()


def _request(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/auth/request", json={"email": email})
    assert r.status_code == 200, r.text
    return r.json()


def _server_code(attempt_id: str) -> str:
    """The device code the server holds — the value a brute-forcer is guessing."""
    return auth_module._attempts[attempt_id].device_code


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10000:04d}"


def _claim(client: TestClient, requested: dict[str, str], code: str):
    return client.post(
        "/auth/claim",
        json={
            "attempt_id": requested["attempt_id"],
            "claim_secret": requested["claim_secret"],
            "code": code,
        },
    )


def _burn_attempt(client: TestClient, email: str) -> None:
    """One full attempt of wrong guesses, ending in the per-attempt lock."""
    requested = _request(client, email)
    wrong = _wrong(_server_code(requested["attempt_id"]))
    for _ in range(auth_module._MAX_CODE_ATTEMPTS - 1):
        assert _claim(client, requested, wrong).status_code == 400
    locked = _claim(client, requested, wrong)
    assert locked.status_code == 410
    assert locked.json()["detail"]["code"] == "login_attempt_locked"


def _clear_ip_windows() -> None:
    """Clear only the per-IP windows, as waiting a minute (or a second IP)
    would — the per-email failure budget must survive it."""
    with auth_module._throttle_lock:
        auth_module._throttle.clear()


# ── C01: the lockout is per email, not per attempt ───────────────────


def test_fresh_attempt_does_not_reset_the_code_failure_budget(client: TestClient) -> None:
    """The attacker's loop: burn an attempt, mint a new one, keep guessing.
    Once the per-email budget is spent, even the RIGHT code on a brand-new
    attempt must not sign in — otherwise the lockout is theatre."""
    for _ in range(2):
        _burn_attempt(client, _OPERATOR)

    fresh = _request(client, _OPERATOR)
    lucky = _claim(client, fresh, _server_code(fresh["attempt_id"]))
    assert lucky.status_code == 429, lucky.text
    assert lucky.json()["detail"]["code"] == "code_entry_locked"
    assert SESSION_COOKIE_NAME not in lucky.cookies
    assert client.get("/auth/whoami").status_code == 401


def test_budget_counts_misses_across_attempts_not_per_attempt(client: TestClient) -> None:
    """Misses spread thinly over many attempts (never tripping the
    per-attempt lock) still spend the same email budget."""
    # Ten misses: the per-email budget may be no larger than two attempts'
    # worth, or a patient caller gets the per-attempt cap back for free.
    for _ in range(10):
        requested = _request(client, _OPERATOR)
        assert _claim(client, requested, _wrong(_server_code(requested["attempt_id"]))).status_code == 400
        _clear_ip_windows()

    fresh = _request(client, _OPERATOR)
    lucky = _claim(client, fresh, _server_code(fresh["attempt_id"]))
    assert lucky.status_code == 429, lucky.text
    assert SESSION_COOKIE_NAME not in lucky.cookies


def test_email_link_proof_reopens_code_entry(client: TestClient, sender: MockEmailProvider) -> None:
    """The lock closes only the brute-forceable channel. Clicking the link
    in the email proves mailbox possession, which the attacker cannot do,
    and that proof is what clears the budget."""
    for _ in range(2):
        _burn_attempt(client, _OPERATOR)

    _request(client, _OPERATOR)
    link = next(p.strip() for p in sender.sent[-1].email.text_body.split() if "/auth/callback?" in p)
    parsed = urlparse(link)
    assert client.get(f"{parsed.path}?{parsed.query}", follow_redirects=False).status_code == 302
    client.cookies.clear()

    fresh = _request(client, _OPERATOR)
    ok = _claim(client, fresh, _server_code(fresh["attempt_id"]))
    assert ok.status_code == 200, ok.text
    assert SESSION_COOKIE_NAME in ok.cookies


# ── C02: a code only ever signs in an allowlisted address ────────────


def test_claim_refuses_non_allowlisted_email_even_with_the_right_code(
    client: TestClient, sender: MockEmailProvider,
) -> None:
    requested = _request(client, _ATTACKER)
    assert sender.sent == []  # nobody was emailed; the code exists only server-side
    r = _claim(client, requested, _server_code(requested["attempt_id"]))
    assert r.status_code != 200, r.text
    assert SESSION_COOKIE_NAME not in r.cookies
    # Indistinguishable from a wrong code: no allowlist oracle.
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_code"


def test_empty_allowlist_claim_cannot_mint_an_operator_session(
    monkeypatch: pytest.MonkeyPatch, sender: MockEmailProvider,
) -> None:
    """The deployment from the finding: auth secret + bearer token, no
    operator email. The claim must not return a session at all."""
    c = _app_client(monkeypatch, operator_email=None)
    assert c.get("/auth/whoami").status_code == 401
    requested = _request(c, _ATTACKER)
    r = _claim(c, requested, _server_code(requested["attempt_id"]))
    assert r.status_code != 200, r.text
    assert SESSION_COOKIE_NAME not in r.cookies
    assert c.get("/auth/whoami").status_code == 401
    reset_auth_throttles()


def test_empty_allowlist_middleware_rejects_any_signed_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allowlist over denylist: with no operator email configured there is
    no email a session cookie can prove, so the cookie path admits nobody.
    The bearer token stays the way in."""
    c = _app_client(monkeypatch, operator_email=None)
    c.cookies.set(SESSION_COOKIE_NAME, mint_session_cookie(user_id="__operator__", email=_ATTACKER))
    assert c.get("/auth/whoami").status_code == 401
    c.cookies.clear()
    bearer = c.get(
        "/auth/whoami",
        headers={"Authorization": "Bearer machine-token-" + "m" * 32},
    )
    assert bearer.status_code == 200


def test_empty_allowlist_websocket_rejects_any_signed_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _app_client(monkeypatch, operator_email=None)
    c.cookies.set(SESSION_COOKIE_NAME, mint_session_cookie(user_id="__operator__", email=_ATTACKER))
    with pytest.raises(WebSocketDisconnect) as excinfo, c.websocket_connect("/ws/events"):
        pass
    assert excinfo.value.code == 1008


def test_dev_login_refuses_rather_than_minting_a_dead_cookie_without_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dev-login used to fall back to email ``__operator__`` when the
    allowlist was empty — a cookie only the fail-open middleware accepted.
    With the cookie path closed there, it refuses loudly like passkey
    login does instead of handing out a session that cannot work."""
    c = _app_client(monkeypatch, operator_email=None)
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _DEV_TOKEN)
    r = c.get(f"/auth/dev-login?token={_DEV_TOKEN}", follow_redirects=False)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "operator_email_missing"
    assert SESSION_COOKIE_NAME not in r.cookies
