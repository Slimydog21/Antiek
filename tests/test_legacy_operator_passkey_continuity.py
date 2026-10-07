"""Legacy alias admission through the real stored-key WebAuthn verifier.

The private key is generated in memory for an isolated test authenticator.
Neither complete_authentication nor the library verifier is replaced.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import cbor2
import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Request

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from substrate.auth import accounts, passkeys, verify_session_cookie

_ORIGINAL = "original@example.test"
_INTERIM = "dedicated-test@example.test"
_RP = "antiek.test"
_ORIGIN = "https://antiek.test"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@dataclass
class StoredAuthenticator:
    private_key: ec.EllipticCurvePrivateKey
    credential_id: bytes
    account_store: Path
    passkey_store: Path

    def assertion(
        self, options: dict[str, Any], *, counter: int = 1,
        origin: str = _ORIGIN, rp_id: str = _RP, flags: int = 0x05,
        challenge: str | None = None,
    ) -> dict[str, Any]:
        client_data = json.dumps({
            "type": "webauthn.get", "challenge": challenge or options["challenge"],
            "origin": origin, "crossOrigin": False,
        }, separators=(",", ":")).encode()
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + counter.to_bytes(4, "big")
        signature = self.private_key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": _b64(self.credential_id), "rawId": _b64(self.credential_id), "type": "public-key",
            "response": {
                "clientDataJSON": _b64(client_data), "authenticatorData": _b64(auth_data),
                "signature": _b64(signature), "userHandle": None,
            },
            "clientExtensionResults": {},
        }

    def store_identity(self, *, user_id: str = "__operator__", email: str | None = None) -> None:
        numbers = self.private_key.public_key().public_numbers()
        public_key = cbor2.dumps({
            1: 2, 3: -7, -1: 1,
            -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big"),
        })
        self.passkey_store.write_text(json.dumps({"version": 1, "credentials": [{
            "credential_id": _b64(self.credential_id), "public_key": _b64(public_key),
            "sign_count": 0, "transports": ["internal"], "device_type": "single_device",
            "backed_up": False, "label": "Isolated test authenticator", "created_at": 1,
            "last_used_at": None, "user_id": user_id, "email": email,
        }]}))
        self.passkey_store.chmod(0o600)


@pytest.fixture
def authenticator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> StoredAuthenticator:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "isolated-webauthn-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _ORIGINAL)
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", _ORIGINAL)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(tmp_path / "accounts.json"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", _RP)
    monkeypatch.setenv("ANTIEK_WEBAUTHN_ORIGINS", _ORIGIN)
    for name in ("ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    record = StoredAuthenticator(ec.generate_private_key(ec.SECP256R1()), b"isolated-original-key",
                                 tmp_path / "accounts.json", tmp_path / "passkeys.json")
    record.store_identity()
    return record


@pytest.fixture
async def client(authenticator: StoredAuthenticator):
    app = create_app(register_wrestling=False, register_providers=False)

    @app.get("/test/verified-owner")
    async def owner_state(request: Request) -> dict[str, Any]:
        snapshot = {name: getattr(request.state, name, None) for name in (
            "user_id", "account_subject", "private_owner_user_id", "legacy_owner_user_id",
        )}
        snapshot["scopes"] = sorted(request.state.scopes)
        return snapshot

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as value:
        yield value


async def _options(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.post("/auth/passkey/login/options")
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME not in response.cookies
    return response.json()


async def _finish(
    client: httpx.AsyncClient, options: dict[str, Any], assertion: dict[str, Any],
) -> httpx.Response:
    return await client.post("/auth/passkey/login/verify", json={
        "ceremony_id": options["ceremony_id"], "credential": assertion,
    })


@pytest.mark.parametrize("stored_email", [None, _ORIGINAL, _ORIGINAL.upper()])
async def test_real_verified_legacy_key_creates_one_stable_original_alias(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, stored_email: str | None,
):
    authenticator.store_identity(email=stored_email)
    options = await _options(client)
    assert not authenticator.account_store.exists()
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 204
    claims = verify_session_cookie(response.cookies[SESSION_COOKIE_NAME])
    account = accounts.legacy_account_for_session(_ORIGINAL)
    assert account is not None and claims.user_id == account.user_id
    assert claims.user_id.startswith("acct_") and claims.email == _ORIGINAL
    assert account.legacy_owner == "__operator__"
    assert authenticator.account_store.stat().st_mode & 0o777 == 0o600
    assert passkeys.list_credentials()[0].sign_count == 1
    assert passkeys.list_credentials()[0].user_id == "__operator__"
    owner = await client.get("/test/verified-owner")
    assert owner.status_code == 200
    assert owner.json() == {
        "user_id": account.user_id, "account_subject": account.user_id,
        "private_owner_user_id": "__operator__", "legacy_owner_user_id": "__operator__",
        "scopes": ["operator", "private_research", "shared_substrate_write"],
    }
    unchanged = authenticator.account_store.read_bytes()
    second = await _options(client)
    assert (await _finish(client, second, authenticator.assertion(second, counter=2))).status_code == 204
    assert authenticator.account_store.read_bytes() == unchanged
    assert len(json.loads(unchanged)["accounts"]) == 1


async def test_verified_original_key_bootstraps_before_public_signup_enable(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ANTIEK_OPEN_SIGNUP")
    assert not accounts.account_registry_active()
    options = await _options(client)
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 204
    assert accounts.account_registry_active()
    me = await client.get("/auth/me")
    assert me.status_code == 200 and me.json()["user_id"].startswith("acct_")


@pytest.mark.parametrize("fault", [
    "signature", "signed_foreign_key", "challenge", "origin", "rp", "uv", "presence", "id", "type",
])
async def test_invalid_real_ceremony_never_creates_alias_or_advances_stored_key(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, fault: str,
):
    options = await _options(client)
    overrides: dict[str, Any] = {
        "challenge": {"challenge": _b64(b"wrong-challenge")},
        "origin": {"origin": "https://foreign.test"}, "rp": {"rp_id": "foreign.test"},
        "uv": {"flags": 0x01}, "presence": {"flags": 0x04},
    }.get(fault, {})
    assertion = authenticator.assertion(options, **overrides)
    if fault == "signature":
        assertion["response"]["signature"] = _b64(b"invalid-signature")
    elif fault == "signed_foreign_key":
        response_data = assertion["response"]
        auth_data = base64.urlsafe_b64decode(response_data["authenticatorData"] + "==")
        client_data = base64.urlsafe_b64decode(response_data["clientDataJSON"] + "==")
        foreign_key = ec.generate_private_key(ec.SECP256R1())
        response_data["signature"] = _b64(foreign_key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()),
        ))
    elif fault == "id":
        assertion["id"] = assertion["rawId"] = _b64(b"unregistered-key")
    elif fault == "type":
        assertion["type"] = "not-a-public-key"
    before = authenticator.passkey_store.read_bytes()
    response = await _finish(client, options, assertion)
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert not authenticator.account_store.exists()
    assert authenticator.passkey_store.read_bytes() == before
    # Even a bad assertion consumes the genuine challenge.
    assert (await _finish(client, options, authenticator.assertion(options))).status_code == 400
    assert not authenticator.account_store.exists()


async def test_replay_and_counter_reuse_refuse_without_account_or_key_changes(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient,
):
    options = await _options(client)
    assertion = authenticator.assertion(options)
    assert (await _finish(client, options, assertion)).status_code == 204
    account_bytes, key_bytes = authenticator.account_store.read_bytes(), authenticator.passkey_store.read_bytes()
    replay = await _finish(client, options, assertion)
    assert replay.status_code == 400 and SESSION_COOKIE_NAME not in replay.cookies
    fresh = await _options(client)
    stale_counter = await _finish(client, fresh, authenticator.assertion(fresh, counter=1))
    assert stale_counter.status_code == 400 and SESSION_COOKIE_NAME not in stale_counter.cookies
    assert authenticator.account_store.read_bytes() == account_bytes
    assert authenticator.passkey_store.read_bytes() == key_bytes


async def test_expired_ceremony_refuses_real_signature_without_alias(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient,
):
    options = await _options(client)
    with passkeys._ceremony_lock:
        ceremony = passkeys._ceremonies[options["ceremony_id"]]
        passkeys._ceremonies[options["ceremony_id"]] = replace(ceremony, expires_at=0)
    before = authenticator.passkey_store.read_bytes()
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert not authenticator.account_store.exists() and authenticator.passkey_store.read_bytes() == before


@pytest.mark.parametrize("policy", [
    "missing_binding", "wrong_allowlist", "stored_interim_email", "stored_foreign_email", "malformed_stored_email",
])
async def test_verified_legacy_key_requires_exact_original_policy_and_stored_email(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, policy: str,
):
    if policy == "missing_binding":
        monkeypatch.delenv("ANTIEK_LEGACY_OPERATOR_EMAIL")
    elif policy == "wrong_allowlist":
        monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _INTERIM)
    elif policy == "malformed_stored_email":
        payload = json.loads(authenticator.passkey_store.read_bytes())
        payload["credentials"][0]["email"] = 7
        authenticator.passkey_store.write_text(json.dumps(payload))
    else:
        authenticator.store_identity(email=_INTERIM if policy == "stored_interim_email" else "foreign@example.test")
    options = await _options(client)
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert not authenticator.account_store.exists()
    # The cryptographic proof was real; policy rejection must not undo the authenticator counter.
    assert passkeys.list_credentials()[0].sign_count == 1


@pytest.mark.parametrize("conflict", ["original_without_alias", "foreign_alias", "corrupt_store"])
async def test_verified_legacy_key_cannot_rebind_or_overwrite_existing_accounts(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, conflict: str,
):
    if conflict == "original_without_alias":
        accounts.account_for_verified_email(_ORIGINAL)
    elif conflict == "foreign_alias":
        accounts.account_for_verified_email("foreign@example.test", legacy_operator_email="foreign@example.test")
    else:
        authenticator.account_store.write_bytes(b'{"version":1,"accounts":"unreadable"}')
    unchanged = authenticator.account_store.read_bytes()
    options = await _options(client)
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert authenticator.account_store.read_bytes() == unchanged


async def test_alias_storage_failure_never_falls_back_to_shared_operator(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ANTIEK_OPEN_SIGNUP")

    def refuse_write(*args: Any) -> None:
        raise OSError("isolated write refusal")

    monkeypatch.setattr(accounts, "_write", refuse_write)
    options = await _options(client)
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert not authenticator.account_store.exists()


async def test_canonical_account_key_stays_canonical_without_legacy_alias(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient,
):
    alice = accounts.account_for_verified_email("alice@example.test")
    unchanged = authenticator.account_store.read_bytes()
    authenticator.store_identity(user_id=alice.user_id, email=alice.email)
    options = await _options(client)
    response = await _finish(client, options, authenticator.assertion(options))
    assert response.status_code == 204
    claims = verify_session_cookie(response.cookies[SESSION_COOKIE_NAME])
    assert (claims.user_id, claims.email) == (alice.user_id, alice.email)
    assert authenticator.account_store.read_bytes() == unchanged
    assert accounts.legacy_account_for_session(_ORIGINAL) is None
    assert (await client.get("/test/verified-owner")).status_code == 403


async def test_unknown_canonical_key_cannot_be_upgraded_to_legacy_owner(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient,
):
    authenticator.store_identity(user_id="acct_" + "0" * 32, email=_ORIGINAL)
    options = await _options(client)
    assertion = authenticator.assertion(options)
    assertion.update(user_id="__operator__", email=_ORIGINAL)
    response = await _finish(client, options, assertion)
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert not authenticator.account_store.exists()


async def test_config_and_bearer_alone_cannot_enroll_an_original_account(
    authenticator: StoredAuthenticator, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "isolated-bearer-not-passkey-proof")
    options = await _options(client)
    before = authenticator.passkey_store.read_bytes()
    response = await client.post("/auth/passkey/login/verify", headers={
        "Authorization": "Bearer isolated-bearer-not-passkey-proof",
    }, json={"ceremony_id": options["ceremony_id"], "credential": {"id": _b64(authenticator.credential_id)}})
    assert response.status_code == 400 and SESSION_COOKIE_NAME not in response.cookies
    assert not authenticator.account_store.exists() and authenticator.passkey_store.read_bytes() == before
