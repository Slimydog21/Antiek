"""Actual private middleware and HMAC controls; no production account or mail."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email
from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME, reset_auth_throttles
from substrate.auth import (
    MockEmailProvider,
    magic_link,
    mint_magic_link_token,
    mint_session_cookie,
)

ORIGINAL = "original@example.test"
INTERIM = "interim@example.test"
PREVIOUS_ORIGINAL = "previous-original@example.test"
SECRET = "private-legacy-continuity-control-" + "x" * 48
LegacyApi = tuple[FastAPI, MockEmailProvider, Path]


@pytest.fixture
def legacy_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> LegacyApi:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", ORIGINAL)
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", ORIGINAL)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "0")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(tmp_path / "accounts.json"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    for name in (
        "ANTIEK_OPERATOR_TOKEN", "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET",
        "ANTIEK_FRONTEND_BASE_URL", "ANTIEK_PUBLIC_BASE_URL", "ANTIEK_API_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    reset_auth_throttles()
    app = create_app(register_wrestling=False, register_providers=False)
    return app, sender, tmp_path


def claim_email(app: FastAPI, sender: MockEmailProvider, email: str) -> TestClient:
    client = TestClient(app)
    request = client.post("/auth/request", json={"email": email})
    assert request.status_code == 200
    assert sender.sent[-1].email.to == email
    code = sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
    payload = request.json()
    claimed = client.post("/auth/claim", json={
        "attempt_id": payload["attempt_id"], "claim_secret": payload["claim_secret"],
        "code": code,
    })
    assert claimed.status_code == 200
    assert claimed.json()["authenticated"] is True
    return client


def assert_unbound(client: TestClient, root: Path) -> None:
    assert client.get("/auth/me").status_code == 401
    assert not (root / "accounts.json").exists()


def test_existing_original_cookie_retains_real_private_notebook_and_canonical_subject(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, sender, root = legacy_api
    original = claim_email(app, sender, ORIGINAL)
    assert original.get("/auth/me").json()["user_id"] == "__operator__"
    assert not (root / "accounts.json").exists()
    created = original.post("/notebooks", json={"title": "Private continuity control"})
    assert created.status_code == 201
    notebook = created.json()["notebook_id"]
    assert original.post(f"/notebooks/{notebook}/blocks", json={
        "block_type": "prose",
        "content": {"type": "paragraph", "content": [{"type": "text", "text": "ORIGINAL_PRIVATE_BODY"}]},
    }).status_code == 201
    sent_before = len(sender.sent)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")

    identity = original.get("/auth/whoami")
    assert identity.status_code == 200
    assert identity.json()["user_id"] == derive_owner_from_verified_email(ORIGINAL)
    assert identity.json()["is_operator"] is True
    assert "operator" in identity.json()["scopes"]
    store = root / "accounts.json"
    assert store.stat().st_mode & 0o777 == 0o600
    assert json.loads(store.read_text())["accounts"] == [{
        "user_id": identity.json()["user_id"], "email": ORIGINAL, "legacy_owner": "__operator__",
    }]
    before = store.read_bytes()
    owned = original.get(f"/notebooks/{notebook}/content")
    assert owned.status_code == 200
    assert "ORIGINAL_PRIVATE_BODY" in owned.text
    assert original.get("/auth/me").json()["user_id"] == identity.json()["user_id"]
    assert store.read_bytes() == before
    assert len(sender.sent) == sent_before  # no new personal-address request for continuity

    ordinary = claim_email(app, sender, INTERIM)
    ordinary_identity = ordinary.get("/auth/whoami").json()
    assert ordinary_identity["user_id"] != identity.json()["user_id"]
    assert ordinary_identity["is_operator"] is False
    assert "operator" not in ordinary_identity["scopes"]
    denied = ordinary.get(f"/notebooks/{notebook}/content")
    assert denied.status_code == 403
    assert "ORIGINAL_PRIVATE_BODY" not in denied.text


def test_concurrent_existing_cookie_creates_one_locked_alias(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, sender, root = legacy_api
    original = claim_email(app, sender, ORIGINAL)
    cookie = original.cookies.get(SESSION_COOKIE_NAME)
    assert cookie
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")

    def read_subject(_index: int) -> str:
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE_NAME, cookie)
        response = client.get("/auth/me")
        assert response.status_code == 200
        return str(response.json()["user_id"])

    with ThreadPoolExecutor(max_workers=3) as pool:
        subjects = list(pool.map(read_subject, range(3)))
    assert subjects == [derive_owner_from_verified_email(ORIGINAL)] * 3
    assert len(json.loads((root / "accounts.json").read_text())["accounts"]) == 1


@pytest.mark.parametrize("case", [
    "tampered", "wrong-secret", "expired", "future", "wrong-subject",
    "callback-audience", "malformed", "missing-expiry", "other-lifetime",
])
def test_ineligible_cookie_never_bootstraps_alias(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    app, _sender, root = legacy_api
    cookie = mint_session_cookie(user_id="__operator__", email=ORIGINAL)
    if case == "tampered":
        payload, signature = cookie.split(".", 1)
        cookie = payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    elif case == "wrong-secret":
        monkeypatch.setenv("ANTIEK_AUTH_SECRET", "wrong-private-secret-" + "y" * 48)
        cookie = mint_session_cookie(user_id="__operator__", email=ORIGINAL)
        monkeypatch.setenv("ANTIEK_AUTH_SECRET", SECRET)
    elif case in {"expired", "future"}:
        issued = time.time() + (-31 * 86400 if case == "expired" else 120)
        monkeypatch.setattr(magic_link, "time", SimpleNamespace(time=lambda: issued))
        cookie = mint_session_cookie(user_id="__operator__", email=ORIGINAL)
        monkeypatch.setattr(magic_link, "time", time)
    elif case == "wrong-subject":
        cookie = mint_session_cookie(user_id="acct_unregistered", email=ORIGINAL)
    elif case == "callback-audience":
        cookie = mint_magic_link_token(ORIGINAL)
    elif case == "malformed":
        cookie = "not.a.session"
    elif case == "missing-expiry":
        cookie = magic_link._encode(magic_link._SESSION_AUDIENCE, {
            "user_id": "__operator__", "email": ORIGINAL, "iat": int(time.time()),
        })
    elif case == "other-lifetime":
        cookie = mint_session_cookie(user_id="__operator__", email=ORIGINAL, max_age_seconds=86400)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert_unbound(client, root)


@pytest.mark.parametrize("case", ["interim-allowlisted", "foreign-email", "no-binding", "removed-original"])
def test_cookie_requires_exact_original_binding_and_current_policy(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    app, _sender, root = legacy_api
    email = ORIGINAL
    if case == "interim-allowlisted":
        email = INTERIM
        monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ORIGINAL},{INTERIM}")
    elif case == "foreign-email":
        email = "foreign@example.test"
    elif case == "no-binding":
        monkeypatch.delenv("ANTIEK_LEGACY_OPERATOR_EMAIL")
    elif case == "removed-original":
        monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", INTERIM)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, mint_session_cookie(user_id="__operator__", email=email))
    assert_unbound(client, root)


def test_actual_dev_login_cookie_cannot_create_account_alias(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _sender, root = legacy_api
    token = "private-dev-route-control-" + "q" * 40
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", token)
    client = TestClient(app)
    issued = client.get("/auth/dev-login", params={"token": token}, follow_redirects=False)
    assert issued.status_code == 302
    assert SESSION_COOKIE_NAME in issued.cookies
    assert client.get("/auth/me").status_code == 200
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    assert_unbound(client, root)
    assert client.get("/auth/dev-login", params={"token": token}).status_code == 404


def test_configured_identity_and_bearer_are_not_bootstrap_proof(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _sender, root = legacy_api
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    anonymous = TestClient(app)
    assert anonymous.get("/auth/me", params={"email": ORIGINAL}).status_code == 401
    assert not (root / "accounts.json").exists()
    token = "private-service-bearer-control-" + "b" * 40
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", token)
    response = anonymous.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200  # preserve the existing service-token contract
    assert response.json()["user_id"] == "__operator__"
    assert not (root / "accounts.json").exists()


def test_original_cookie_does_not_rewrite_existing_unaliased_account(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, sender, root = legacy_api
    old = claim_email(app, sender, ORIGINAL)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    monkeypatch.delenv("ANTIEK_LEGACY_OPERATOR_EMAIL")
    current = claim_email(app, sender, ORIGINAL)
    store = root / "accounts.json"
    before = store.read_bytes()
    assert json.loads(before)["accounts"][0]["legacy_owner"] is None
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", ORIGINAL)
    assert old.get("/auth/me").status_code == 401
    assert store.read_bytes() == before
    assert current.get("/auth/me").json()["user_id"] == derive_owner_from_verified_email(ORIGINAL)


def test_original_cookie_cannot_rebind_previously_proven_other_alias(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, sender, root = legacy_api
    old = claim_email(app, sender, ORIGINAL)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ORIGINAL},{PREVIOUS_ORIGINAL}")
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", PREVIOUS_ORIGINAL)
    claim_email(app, sender, PREVIOUS_ORIGINAL)
    store = root / "accounts.json"
    before = store.read_bytes()
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", ORIGINAL)
    assert old.get("/auth/me").status_code == 401
    assert store.read_bytes() == before


def test_corrupt_store_is_not_overwritten_by_valid_original_cookie(
    legacy_api: LegacyApi, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, sender, root = legacy_api
    old = claim_email(app, sender, ORIGINAL)
    store = root / "accounts.json"
    store.write_text("not valid account storage")
    before = store.read_bytes()
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    assert old.get("/auth/me").status_code == 401
    assert store.read_bytes() == before
