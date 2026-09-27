"""Passkey store and route boundary regressions.

Browser authenticators are platform APIs and belong in Playwright coverage.
These tests bite on Antiek's load-bearing server behavior: one-shot ceremony
consumption, public-key persistence, logged-out login routes, protected
registration routes, and session issuance only after verification.
"""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from substrate.auth import mint_magic_link_token
from substrate.auth.passkeys import (
    PasskeyError,
    PasskeySubjectBinding,
    complete_registration,
    list_credentials,
    registration_options,
)
from substrate.multi_user.auth import mint_session_cookie, subject_owner_id

_EMAIL = "operator@example.com"
_SECRET = "passkey-tests-" + "x" * 48


def _binding() -> PasskeySubjectBinding:
    return PasskeySubjectBinding("magic_link", _EMAIL, subject_owner_id("magic_link", _EMAIL))


@pytest.fixture(autouse=True)
def _isolated_auth_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "subjects.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))


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

    options = registration_options(binding=_binding())
    record = complete_registration(
        ceremony_id=options["ceremony_id"],
        credential={"response": {"transports": ["internal", "hybrid"]}},
        label="Faisal's iPad",
        binding=_binding(),
    )

    assert record.label == "Faisal's iPad"
    assert record.public_key != "public-key-only"
    assert record.backed_up is True
    assert store.stat().st_mode & 0o777 == 0o600
    assert list_credentials() == [record]
    assert record.binding == _binding()
    payload = json.loads(store.read_text())
    assert "private" not in json.dumps(payload).lower()

    with pytest.raises(PasskeyError, match="expired"):
        complete_registration(
            ceremony_id=options["ceremony_id"],
            credential={"response": {}},
            label="Replay",
            binding=_binding(),
        )


def test_concurrent_same_credential_registration_persists_exactly_one_record(
    monkeypatch, tmp_path,
):
    """Mock-verifier persistence race; WebAuthn proof is covered by route journeys."""
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setenv("ANTIEK_WEBAUTHN_ORIGINS", "http://localhost:5173")
    barrier = threading.Barrier(2)

    def verify_registration_response(**_):
        barrier.wait(timeout=3)
        return SimpleNamespace(
            credential_id=b"one-shared-synthetic-id",
            credential_public_key=b"synthetic-public-key",
            sign_count=0,
            credential_device_type=SimpleNamespace(value="single_device"),
            credential_backed_up=False,
        )

    monkeypatch.setattr(
        "substrate.auth.passkeys.verify_registration_response", verify_registration_response,
    )
    import substrate.auth.passkeys as passkeys

    class BoundedStoreLock:
        def __init__(self):
            self._lock = threading.Lock()

        def __enter__(self):
            if not self._lock.acquire(timeout=3):
                raise TimeoutError("registration worker could not acquire the store lock")
            return self

        def __exit__(self, *_):
            self._lock.release()

    monkeypatch.setattr(passkeys, "_store_lock", BoundedStoreLock())
    ceremonies = [registration_options(binding=_binding()) for _ in range(2)]
    results: list[object] = []
    failures: list[BaseException] = []

    def register(ceremony_id: str) -> None:
        try:
            results.append(complete_registration(
                ceremony_id=ceremony_id,
                credential={"response": {"transports": ["internal"]}},
                label="Synthetic key",
                binding=_binding(),
            ))
        except BaseException as exc:
            failures.append(exc)

    threads = [
        threading.Thread(target=register, args=(item["ceremony_id"],), daemon=True)
        for item in ceremonies
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)
    finally:
        if any(thread.is_alive() for thread in threads):
            barrier.abort()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(timeout=8)
        assert all(not thread.is_alive() for thread in threads)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 1
    assert len(failures) == 1 and isinstance(failures[0], PasskeyError)
    payload = json.loads((tmp_path / "passkeys.json").read_text())
    assert payload["version"] == 2
    assert len(payload["credentials"]) == 1
    assert payload["credentials"][0]["credential_id"] == "b25lLXNoYXJlZC1zeW50aGV0aWMtaWQ"


def test_logged_out_passkey_login_issues_session_only_after_verification(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "subjects.duckdb"))
    sentinel = SimpleNamespace(label="This Mac", binding=_binding())
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
    mint_session_cookie("magic_link", _EMAIL, _EMAIL)

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
        lambda *, binding: {
            "challenge": "abc", "ceremony_id": "r" * 24, "email": binding.subject,
        },
    )
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [])
    client = _client(monkeypatch)

    logged_out = client.post("/auth/passkey/register/options")
    assert logged_out.status_code == 401

    token = mint_magic_link_token(_EMAIL)
    assert client.get(f"/auth/callback?token={token}", follow_redirects=False).status_code == 302
    authenticated = client.post("/auth/passkey/register/options")
    assert authenticated.status_code == 200
    assert authenticated.json()["email"] == _EMAIL


def test_passkey_status_exposes_only_availability_to_logged_out_browser(monkeypatch):
    monkeypatch.setattr(
        "interfaces.research.api.auth.list_credentials",
        lambda: [SimpleNamespace(binding=_binding()), SimpleNamespace(binding=None)],
    )
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
        binding=_binding(),
    )
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [first])
    deleted: list[str] = []
    monkeypatch.setattr(
        "interfaces.research.api.auth.delete_bound_credential",
        lambda credential_id, owner: deleted.append(credential_id) or (
            credential_id == "first-key" and owner == _binding().owner_user_id
        ),
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
