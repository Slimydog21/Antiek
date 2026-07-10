"""Passkey store and route boundary regressions.

Browser authenticators are platform APIs and belong in Playwright coverage.
These tests bite on Antiek's load-bearing server behavior: one-shot ceremony
consumption, public-key persistence, logged-out login routes, protected
registration routes, and session issuance only after verification.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from substrate.auth import mint_magic_link_token
from substrate.auth.passkeys import (
    PasskeyError,
    complete_registration,
    list_credentials,
    registration_options,
)

_EMAIL = "operator@example.com"
_SECRET = "passkey-tests-" + "x" * 48


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def test_registration_persists_public_credential_and_consumes_challenge(monkeypatch, tmp_path):
    store = tmp_path / "auth" / "passkeys.json"
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(store))
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setenv("ANTIEK_WEBAUTHN_ORIGINS", "http://localhost:5173")
    monkeypatch.setattr(
        "substrate.auth.passkeys.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"credential-id",
            credential_public_key=b"public-key-only",
            sign_count=0,
            credential_device_type=SimpleNamespace(value="multi_device"),
            credential_backed_up=True,
        ),
    )

    options = registration_options(email=_EMAIL)
    record = complete_registration(
        ceremony_id=options["ceremony_id"],
        credential={"response": {"transports": ["internal", "hybrid"]}},
        label="Faisal's iPad",
    )

    assert record.label == "Faisal's iPad"
    assert record.public_key != "public-key-only"
    assert record.backed_up is True
    assert store.stat().st_mode & 0o777 == 0o600
    assert list_credentials() == [record]
    payload = json.loads(store.read_text())
    assert "private" not in json.dumps(payload).lower()

    with pytest.raises(PasskeyError, match="expired"):
        complete_registration(
            ceremony_id=options["ceremony_id"],
            credential={"response": {}},
            label="Replay",
        )


def test_logged_out_passkey_login_issues_session_only_after_verification(monkeypatch):
    sentinel = SimpleNamespace(label="This Mac")
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [sentinel])
    monkeypatch.setattr(
        "interfaces.research.api.auth.authentication_options",
        lambda: {"challenge": "abc", "ceremony_id": "c" * 24},
    )
    verified: list[str] = []
    monkeypatch.setattr(
        "interfaces.research.api.auth.complete_authentication",
        lambda *, ceremony_id, credential: verified.append(ceremony_id) or sentinel,
    )
    client = _client(monkeypatch)

    begin = client.post("/auth/passkey/login/options")
    assert begin.status_code == 200
    assert SESSION_COOKIE_NAME not in begin.cookies

    finish = client.post(
        "/auth/passkey/login/verify",
        json={"ceremony_id": "c" * 24, "credential": {"id": "credential"}},
    )
    assert finish.status_code == 204
    assert verified == ["c" * 24]
    assert SESSION_COOKIE_NAME in finish.cookies
    assert client.get("/auth/whoami").status_code == 200


def test_passkey_registration_requires_existing_operator_session(monkeypatch):
    monkeypatch.setattr(
        "interfaces.research.api.auth.registration_options",
        lambda *, email: {"challenge": "abc", "ceremony_id": "r" * 24, "email": email},
    )
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [object()])
    client = _client(monkeypatch)

    logged_out = client.post("/auth/passkey/register/options")
    assert logged_out.status_code == 401

    token = mint_magic_link_token(_EMAIL)
    assert client.get(f"/auth/callback?token={token}", follow_redirects=False).status_code == 302
    authenticated = client.post("/auth/passkey/register/options")
    assert authenticated.status_code == 200
    assert authenticated.json()["email"] == _EMAIL


def test_passkey_status_exposes_only_availability_to_logged_out_browser(monkeypatch):
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [object(), object()])
    client = _client(monkeypatch)
    response = client.get("/auth/passkey/status")
    assert response.status_code == 200
    assert response.json() == {"available": True, "count": None}


def test_passkey_management_routes_are_protected_and_delete_exact_key(monkeypatch):
    first = SimpleNamespace(
        credential_id="first-key",
        label="This iPad",
        backed_up=True,
        created_at=1,
        last_used_at=None,
    )
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [first])
    deleted: list[str] = []
    monkeypatch.setattr(
        "interfaces.research.api.auth.delete_credential",
        lambda credential_id: deleted.append(credential_id) or credential_id == "first-key",
    )
    client = _client(monkeypatch)

    assert client.get("/auth/passkeys").status_code == 401
    assert client.delete("/auth/passkeys/first-key").status_code == 401

    token = mint_magic_link_token(_EMAIL)
    client.get(f"/auth/callback?token={token}", follow_redirects=False)
    listing = client.get("/auth/passkeys")
    assert listing.status_code == 200
    assert listing.json()["passkeys"][0]["label"] == "This iPad"
    assert client.delete("/auth/passkeys/first-key").status_code == 204
    assert deleted == ["first-key"]
