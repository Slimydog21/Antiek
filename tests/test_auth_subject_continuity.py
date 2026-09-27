"""A passkey is a factor for one existing, verified magic-link account."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import cbor2
import duckdb
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.auth import mint_magic_link_token
from substrate.auth.magic_link import mint_session_cookie as mint_raw_cookie
from substrate.auth.passkeys import (
    PasskeyError,
    PasskeySubjectBinding,
    complete_registration,
    delete_bound_credential,
    list_credentials,
    registration_options,
)
from substrate.multi_user.auth import AuthError, subject_owner_id

ALICE = "alice@example.test"
BOB = "bob@example.test"
RP = "localhost"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db = tmp_path / "subjects.duckdb"
    store = tmp_path / "passkeys.json"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(store))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-passkey-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ALICE},{BOB}")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", RP)
    monkeypatch.setenv("ANTIEK_WEBAUTHN_ORIGINS", ORIGIN)
    for name in ("ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    return db, store


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _client_data(kind: str, challenge: str, origin: str = ORIGIN) -> bytes:
    return json.dumps(
        {"type": kind, "challenge": challenge, "origin": origin},
        separators=(",", ":"),
    ).encode()


def _attestation(
    options: dict, credential_id: bytes, private_key, *,
    origin: str = ORIGIN, flags: int = 0x45,
) -> dict:
    numbers = private_key.public_key().public_numbers()
    cose = cbor2.dumps({
        1: 2, 3: -7, -1: 1,
        -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big"),
    })
    auth_data = (
        hashlib.sha256(RP.encode()).digest() + bytes([flags]) + bytes(4)
        + bytes(16) + len(credential_id).to_bytes(2, "big") + credential_id + cose
    )
    attestation = cbor2.dumps({"fmt": "none", "authData": auth_data, "attStmt": {}})
    return {
        "id": _b64(credential_id), "rawId": _b64(credential_id), "type": "public-key",
        "response": {
            "clientDataJSON": _b64(_client_data("webauthn.create", options["challenge"], origin)),
            "attestationObject": _b64(attestation),
            "transports": ["internal"],
        },
    }


def _assertion(
    options: dict, credential_id: bytes, private_key, *, count: int = 1,
    flags: int = 0x05, origin: str = ORIGIN, tamper_signature: bool = False,
) -> dict:
    auth_data = hashlib.sha256(RP.encode()).digest() + bytes([flags]) + count.to_bytes(4, "big")
    client_data = _client_data("webauthn.get", options["challenge"], origin)
    signature = private_key.sign(
        auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()),
    )
    if tamper_signature:
        signature = signature[:-1] + bytes([signature[-1] ^ 1])
    return {
        "id": _b64(credential_id), "rawId": _b64(credential_id), "type": "public-key",
        "response": {
            "clientDataJSON": _b64(client_data),
            "authenticatorData": _b64(auth_data),
            "signature": _b64(signature),
        },
    }


def _app_client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _email_login(client: TestClient, email: str) -> None:
    response = client.get(
        f"/auth/callback?token={mint_magic_link_token(email)}", follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert client.get("/auth/me").json()["user_id"] == subject_owner_id("magic_link", email)


def _register(client: TestClient, name: str) -> tuple[bytes, object, dict]:
    options_response = client.post("/auth/passkey/register/options")
    assert options_response.status_code == 200, options_response.text
    options = options_response.json()
    credential_id = f"synthetic-{name}".encode()
    private_key = ec.generate_private_key(ec.SECP256R1())
    verify = client.post(
        "/auth/passkey/register/verify",
        json={
            "ceremony_id": options["ceremony_id"],
            "credential": _attestation(options, credential_id, private_key),
            "label": f"{name} key",
        },
    )
    assert verify.status_code == 200, verify.text
    return credential_id, private_key, options


def _passkey_login(client: TestClient, credential_id: bytes, private_key, *, count: int = 1):
    options_response = client.post("/auth/passkey/login/options")
    assert options_response.status_code == 200, options_response.text
    options = options_response.json()
    return client.post(
        "/auth/passkey/login/verify",
        json={
            "ceremony_id": options["ceremony_id"],
            "credential": _assertion(options, credential_id, private_key, count=count),
        },
    )


def test_real_webauthn_email_passkey_relogin_keeps_two_distinct_owners(auth_env):
    db, store = auth_env
    app = create_app(register_wrestling=False, register_providers=False)
    alice = TestClient(app)
    bob = TestClient(app)
    assert alice.get("/auth/passkey/status").json() == {"available": False, "count": None}

    _email_login(alice, ALICE)
    alice_id, alice_key, _ = _register(alice, "alice")
    alice_options = alice.post("/auth/passkey/register/options").json()
    assert {_unb64(item["id"]) for item in alice_options["excludeCredentials"]} == {alice_id}
    assert alice.get("/auth/passkey/status").json() == {"available": True, "count": 1}

    _email_login(bob, BOB)
    bob_before = bob.post("/auth/passkey/register/options").json()
    assert bob_before["excludeCredentials"] == []
    bob_id, bob_key, _ = _register(bob, "bob")
    bob_options = bob.post("/auth/passkey/register/options").json()
    assert {_unb64(item["id"]) for item in bob_options["excludeCredentials"]} == {bob_id}
    assert {_unb64(item["id"]) for item in alice.post("/auth/passkey/register/options").json()["excludeCredentials"]} == {alice_id}
    assert bob.get("/auth/passkey/status").json() == {"available": True, "count": 1}
    assert TestClient(app).get("/auth/passkey/status").json() == {"available": True, "count": None}

    assert bob.delete(f"/auth/passkeys/{_b64(alice_id)}").status_code == 404
    assert {row["id"] for row in bob.get("/auth/passkeys").json()["passkeys"]} == {_b64(bob_id)}
    assert {row["id"] for row in alice.get("/auth/passkeys").json()["passkeys"]} == {_b64(alice_id)}
    assert alice.post("/auth/logout").status_code == 204
    assert bob.post("/auth/logout").status_code == 204

    assert _passkey_login(bob, bob_id, bob_key).status_code == 204
    assert bob.get("/auth/me").json()["user_id"] == subject_owner_id("magic_link", BOB)
    assert _passkey_login(alice, alice_id, alice_key).status_code == 204
    assert alice.get("/auth/me").json()["user_id"] == subject_owner_id("magic_link", ALICE)
    _email_login(alice, ALICE)
    _email_login(bob, BOB)
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute(
            "SELECT subject,owner_user_id FROM auth_subjects ORDER BY subject"
        ).fetchall() == [
            (ALICE, subject_owner_id("magic_link", ALICE)),
            (BOB, subject_owner_id("magic_link", BOB)),
        ]
    payload = json.loads(store.read_text())
    assert payload["version"] == 2
    assert len(payload["credentials"]) == 2
    assert {row["binding"]["owner_user_id"] for row in payload["credentials"]} == {
        subject_owner_id("magic_link", ALICE), subject_owner_id("magic_link", BOB),
    }
    assert all(row["sign_count"] == 1 for row in payload["credentials"])


def test_registration_account_switch_and_duplicate_id_refuse_without_overwrite(auth_env):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    alice_options = client.post("/auth/passkey/register/options").json()
    alice_key = ec.generate_private_key(ec.SECP256R1())
    _email_login(client, BOB)
    switched = client.post(
        "/auth/passkey/register/verify",
        json={
            "ceremony_id": alice_options["ceremony_id"],
            "credential": _attestation(alice_options, b"shared-id", alice_key),
            "label": "wrong account",
        },
    )
    assert switched.status_code == 400
    assert not store.exists()

    _email_login(client, ALICE)
    alice_id, _key, _ = _register(client, "same-id")
    before = store.read_bytes()
    _email_login(client, BOB)
    options = client.post("/auth/passkey/register/options").json()
    assert options["excludeCredentials"] == []
    duplicate = client.post(
        "/auth/passkey/register/verify",
        json={
            "ceremony_id": options["ceremony_id"],
            "credential": _attestation(
                options, alice_id, ec.generate_private_key(ec.SECP256R1()),
            ),
            "label": "duplicate",
        },
    )
    assert duplicate.status_code == 400
    assert store.read_bytes() == before


def test_unbound_v1_inventory_and_malformed_store_fail_closed(auth_env):
    _db, store = auth_env
    old_id = _b64(b"old-unbound-key")
    old = {
        "credential_id": old_id, "public_key": _b64(b"old-public-key"),
        "sign_count": 0, "transports": ["internal"], "device_type": "single_device",
        "backed_up": False, "label": "Legacy", "created_at": 1, "last_used_at": None,
    }
    store.write_text(json.dumps({"version": 1, "credentials": [old]}))
    assert list_credentials()[0].binding is None
    client = _app_client()
    assert client.get("/auth/passkey/status").json() == {"available": False, "count": None}
    assert client.post("/auth/passkey/login/options").status_code == 404
    _email_login(client, ALICE)
    assert client.post("/auth/passkey/register/options").json()["excludeCredentials"] == []
    _register(client, "new")
    payload = json.loads(store.read_text())
    assert payload["version"] == 2
    assert next(item for item in payload["credentials"] if item["credential_id"] == old_id)["binding"] is None
    options = client.post("/auth/passkey/login/options").json()
    refused = client.post(
        "/auth/passkey/login/verify",
        json={"ceremony_id": options["ceremony_id"], "credential": {"id": old_id}},
    )
    assert refused.status_code == 400
    for invalid in (
        {"version": 3, "credentials": []},
        {"version": 2, "credentials": [{**old, "binding": {"provider": "magic_link"}}]},
        {"version": 2, "credentials": [{**old, "binding": None}] * 2},
        [],
    ):
        store.write_text(json.dumps(invalid))
        before = store.read_bytes()
        with pytest.raises(PasskeyError):
            list_credentials()
        assert store.read_bytes() == before


def test_missing_subject_row_refuses_after_real_assertion_without_recreation(auth_env):
    db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    credential_id, key, _ = _register(client, "orphan")
    with duckdb.connect(str(db)) as con:
        con.execute("DELETE FROM auth_subjects WHERE subject=?", [ALICE])
    assert client.post("/auth/logout").status_code == 204
    response = _passkey_login(client, credential_id, key)
    assert response.status_code == 400
    assert "ANTIEK_SESSION" not in response.cookies
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("SELECT COUNT(*) FROM auth_subjects").fetchone()[0] == 0
    assert json.loads(store.read_text())["credentials"][0]["sign_count"] == 1


def test_conflicting_subject_row_refuses_without_rebinding(auth_env):
    db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    credential_id, key, _ = _register(client, "conflict")
    foreign_owner = subject_owner_id("magic_link", BOB)
    with duckdb.connect(str(db)) as con:
        con.execute(
            "UPDATE auth_subjects SET owner_user_id=? WHERE subject=?",
            [foreign_owner, ALICE],
        )
    assert client.post("/auth/logout").status_code == 204
    response = _passkey_login(client, credential_id, key)
    assert response.status_code == 400
    assert "ANTIEK_SESSION" not in response.cookies
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute(
            "SELECT owner_user_id FROM auth_subjects WHERE subject=?", [ALICE],
        ).fetchone()[0] == foreign_owner
    assert json.loads(store.read_text())["credentials"][0]["binding"]["owner_user_id"] == (
        subject_owner_id("magic_link", ALICE)
    )


def test_real_assertion_rejections_and_zero_counter(auth_env, monkeypatch):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    credential_id, key, _ = _register(client, "tamper")
    assert client.post("/auth/logout").status_code == 204
    cases = (
        {"origin": "http://wrong.localhost:5173"},
        {"flags": 0x01},
        {"tamper_signature": True},
    )
    for variation in cases:
        options = client.post("/auth/passkey/login/options").json()
        response = client.post(
            "/auth/passkey/login/verify",
            json={
                "ceremony_id": options["ceremony_id"],
                "credential": _assertion(options, credential_id, key, **variation),
            },
        )
        assert response.status_code == 400
        assert "ANTIEK_SESSION" not in response.cookies
    options = client.post("/auth/passkey/login/options").json()
    wrong = {**options, "challenge": _b64(b"wrong-challenge")}
    assert client.post(
        "/auth/passkey/login/verify",
        json={"ceremony_id": options["ceremony_id"], "credential": _assertion(wrong, credential_id, key)},
    ).status_code == 400
    options = client.post("/auth/passkey/login/options").json()
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", "other.localhost")
    assert client.post(
        "/auth/passkey/login/verify",
        json={"ceremony_id": options["ceremony_id"], "credential": _assertion(options, credential_id, key)},
    ).status_code == 400
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", RP)
    assert json.loads(store.read_text())["credentials"][0]["sign_count"] == 0

    assert _passkey_login(client, credential_id, key).status_code == 204
    assert client.post("/auth/logout").status_code == 204
    assert _passkey_login(client, credential_id, key, count=1).status_code == 400
    assert json.loads(store.read_text())["credentials"][0]["sign_count"] == 1

    # A different authenticator that always reports zero follows WebAuthn's
    # documented zero-counter rule, with a fresh one-shot challenge each time.
    _email_login(client, ALICE)
    zero_id, zero_key, _ = _register(client, "zero")
    assert client.post("/auth/logout").status_code == 204
    assert _passkey_login(client, zero_id, zero_key, count=0).status_code == 204
    assert client.post("/auth/logout").status_code == 204
    assert _passkey_login(client, zero_id, zero_key, count=0).status_code == 204


def test_registration_rejects_invalid_ceremony_without_store_write(auth_env, monkeypatch):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    for variation in (
        {"origin": "http://wrong.localhost:5173"},
        {"flags": 0x41},  # UP without UV
    ):
        options = client.post("/auth/passkey/register/options").json()
        response = client.post(
            "/auth/passkey/register/verify",
            json={
                "ceremony_id": options["ceremony_id"],
                "credential": _attestation(
                    options, b"invalid-registration", ec.generate_private_key(ec.SECP256R1()),
                    **variation,
                ),
                "label": "Invalid",
            },
        )
        assert response.status_code == 400
        assert not store.exists()
    options = client.post("/auth/passkey/register/options").json()
    wrong = {**options, "challenge": _b64(b"wrong-challenge")}
    response = client.post(
        "/auth/passkey/register/verify",
        json={
            "ceremony_id": options["ceremony_id"],
            "credential": _attestation(
                wrong, b"invalid-challenge", ec.generate_private_key(ec.SECP256R1()),
            ),
            "label": "Invalid",
        },
    )
    assert response.status_code == 400
    assert not store.exists()
    options = client.post("/auth/passkey/register/options").json()
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", "other.localhost")
    response = client.post(
        "/auth/passkey/register/verify",
        json={
            "ceremony_id": options["ceremony_id"],
            "credential": _attestation(
                options, b"invalid-rp", ec.generate_private_key(ec.SECP256R1()),
            ),
            "label": "Invalid",
        },
    )
    assert response.status_code == 400
    assert not store.exists()


def test_counter_write_failure_keeps_session_closed_and_nested_binding_typed(
    auth_env, monkeypatch,
):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    credential_id, key, _ = _register(client, "write-failure")
    assert client.post("/auth/logout").status_code == 204
    before = store.read_bytes()
    monkeypatch.setattr(
        "substrate.auth.passkeys.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("synthetic pre-replace failure")),
    )
    options = client.post("/auth/passkey/login/options").json()
    with pytest.raises(OSError, match="synthetic pre-replace failure"):
        client.post(
            "/auth/passkey/login/verify",
            json={
                "ceremony_id": options["ceremony_id"],
                "credential": _assertion(options, credential_id, key),
            },
        )
    assert store.read_bytes() == before
    assert client.get("/auth/me").status_code != 200
    assert "ANTIEK_SESSION" not in client.cookies
    assert isinstance(list_credentials()[0].binding, PasskeySubjectBinding)


def test_counter_directory_fsync_failure_returns_no_session_and_allows_replaced_counter(
    auth_env, monkeypatch,
):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    credential_id, key, _ = _register(client, "directory-fsync-failure")
    assert client.post("/auth/logout").status_code == 204
    before = json.loads(store.read_text())
    real_fsync = os.fsync

    def fail_directory_fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic post-replace directory fsync failure")
        real_fsync(fd)

    monkeypatch.setattr("substrate.auth.passkeys.os.fsync", fail_directory_fsync)
    options = client.post("/auth/passkey/login/options").json()
    with pytest.raises(OSError, match="post-replace directory fsync failure"):
        client.post(
            "/auth/passkey/login/verify",
            json={
                "ceremony_id": options["ceremony_id"],
                "credential": _assertion(options, credential_id, key),
            },
        )
    after = json.loads(store.read_text())
    assert after["credentials"][0]["sign_count"] == 1
    assert before["credentials"][0]["sign_count"] == 0
    assert client.get("/auth/me").status_code != 200
    assert "ANTIEK_SESSION" not in client.cookies
    assert isinstance(list_credentials()[0].binding, PasskeySubjectBinding)


def test_owner_checked_delete_serializes_a_concurrent_registration_update(
    auth_env, monkeypatch,
):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    deleting_id, _key, _ = _register(client, "delete-target")
    preserved_id, _key, _ = _register(client, "preserved")
    binding = PasskeySubjectBinding("magic_link", ALICE, subject_owner_id("magic_link", ALICE))
    options = registration_options(binding=binding)

    def verified_registration(**_):
        return SimpleNamespace(
            credential_id=b"concurrent-legitimate-update",
            credential_public_key=b"synthetic-public-key",
            sign_count=0,
            credential_device_type=SimpleNamespace(value="single_device"),
            credential_backed_up=False,
        )

    monkeypatch.setattr(
        "substrate.auth.passkeys.verify_registration_response", verified_registration,
    )
    import substrate.auth.passkeys as passkeys

    original_read = passkeys._read_credentials_unlocked
    original_write = passkeys._write_credentials_unlocked
    deleting_read_entered = threading.Event()
    release_deleting_read = threading.Event()
    updater_attempted_lock = threading.Event()
    updating_read_entered = threading.Event()
    delete_result: list[bool] = []
    update_result: list[object] = []
    writes_inside_lock: list[str] = []
    read_windows: list[tuple[str, int]] = []
    write_windows: list[tuple[str, int]] = []
    failures: list[BaseException] = []
    delete_thread_id: list[int] = []

    class TrackingLock:
        def __init__(self):
            self._lock = threading.Lock()
            self._state_lock = threading.Lock()
            self._owner: str | None = None
            self._generation = 0
            self.acquisitions: list[tuple[str, int]] = []

        def __enter__(self):
            name = threading.current_thread().name
            if name == "credential-updater":
                updater_attempted_lock.set()
            if not self._lock.acquire(timeout=3):
                raise TimeoutError(f"{name} could not acquire the credential store lock")
            with self._state_lock:
                assert self._owner is None
                self._generation += 1
                self._owner = name
                self.acquisitions.append((name, self._generation))
            return self

        def __exit__(self, *_):
            with self._state_lock:
                assert self._owner == threading.current_thread().name
                self._owner = None
                self._lock.release()

        def active_generation(self) -> int:
            with self._state_lock:
                assert self._owner == threading.current_thread().name
                return self._generation

    tracking_lock = TrackingLock()
    monkeypatch.setattr(passkeys, "_store_lock", tracking_lock)

    def controlled_read():
        name = threading.current_thread().name
        generation = tracking_lock.active_generation()
        read_windows.append((name, generation))
        if threading.get_ident() == delete_thread_id[0]:
            assert name == "credential-deleter"
            deleting_read_entered.set()
            if not release_deleting_read.wait(timeout=3):
                raise AssertionError("deletion read was not released")
        else:
            assert name == "credential-updater"
            updating_read_entered.set()
        return original_read()

    def controlled_write(credentials):
        name = threading.current_thread().name
        generation = tracking_lock.active_generation()
        writes_inside_lock.append(name)
        write_windows.append((name, generation))
        return original_write(credentials)

    monkeypatch.setattr(passkeys, "_read_credentials_unlocked", controlled_read)
    monkeypatch.setattr(passkeys, "_write_credentials_unlocked", controlled_write)

    def delete_target():
        delete_thread_id.append(threading.get_ident())
        try:
            delete_result.append(delete_bound_credential(_b64(deleting_id), binding.owner_user_id))
        except BaseException as exc:
            failures.append(exc)

    def add_legitimate_credential():
        try:
            update_result.append(complete_registration(
                ceremony_id=options["ceremony_id"],
                credential={"response": {"transports": ["internal"]}},
                label="Concurrent update",
                binding=binding,
            ))
        except BaseException as exc:
            failures.append(exc)

    deleter = threading.Thread(
        target=delete_target, name="credential-deleter", daemon=True,
    )
    updater = threading.Thread(
        target=add_legitimate_credential, name="credential-updater", daemon=True,
    )
    deleter.start()
    try:
        assert deleting_read_entered.wait(timeout=3)
        updater.start()
        assert updater_attempted_lock.wait(timeout=3)
        assert not updating_read_entered.is_set()
    finally:
        release_deleting_read.set()
        deleter.join(timeout=5)
        if updater.ident is not None:
            updater.join(timeout=5)
        for worker in (deleter, updater):
            if worker.is_alive():
                worker.join(timeout=1)

    assert not deleter.is_alive() and not updater.is_alive()
    assert not failures
    assert delete_result == [True]
    assert len(update_result) == 1
    assert updating_read_entered.is_set()
    assert tracking_lock.acquisitions == [
        ("credential-deleter", 1), ("credential-updater", 2),
    ]
    assert writes_inside_lock == ["credential-deleter", "credential-updater"]
    assert read_windows == [
        ("credential-deleter", 1), ("credential-updater", 2),
    ]
    assert write_windows == [
        ("credential-deleter", 1), ("credential-updater", 2),
    ]
    payload = json.loads(store.read_text())
    assert {item["credential_id"] for item in payload["credentials"]} == {
        _b64(preserved_id), "Y29uY3VycmVudC1sZWdpdGltYXRlLXVwZGF0ZQ",
    }


def test_registration_pre_replace_failure_preserves_existing_store(auth_env, monkeypatch):
    _db, store = auth_env
    client = _app_client()
    _email_login(client, ALICE)
    _register(client, "existing")
    before = store.read_bytes()
    options = client.post("/auth/passkey/register/options").json()
    monkeypatch.setattr(
        "substrate.auth.passkeys.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("synthetic pre-replace failure")),
    )
    with pytest.raises(OSError, match="synthetic pre-replace failure"):
        client.post(
            "/auth/passkey/register/verify",
            json={
                "ceremony_id": options["ceremony_id"],
                "credential": _attestation(
                    options, b"failed-write", ec.generate_private_key(ec.SECP256R1()),
                ),
                "label": "Failed write",
            },
        )
    assert store.read_bytes() == before


def test_unreadable_store_is_typed_refusal(auth_env):
    _db, store = auth_env
    store.mkdir()
    with pytest.raises(PasskeyError, match="unreadable"):
        list_credentials()


def test_legacy_and_machine_auth_cannot_register_and_status_ignores_empty_allowlist(
    auth_env, monkeypatch,
):
    client = _app_client()
    _email_login(client, ALICE)
    _register(client, "bound")
    legacy = mint_raw_cookie(user_id="__operator__", email=ALICE)
    client.cookies.set("ANTIEK_SESSION", legacy)
    assert client.post("/auth/passkey/register/options").status_code == 403
    client.cookies.clear()
    assert client.post("/auth/passkey/register/options").status_code == 401
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "synthetic-machine-token")
    assert client.post(
        "/auth/passkey/register/options",
        headers={"Authorization": "Bearer synthetic-machine-token"},
    ).status_code == 403
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "")
    assert client.get("/auth/passkey/status").json() == {"available": False, "count": None}
    assert client.post("/auth/passkey/login/options").status_code == 404


@pytest.mark.parametrize("order", ("passkeys_first", "multi_user_first"))
def test_binding_import_orders_execute_canonical_validation(auth_env, tmp_path, order):
    root = Path(__file__).resolve().parents[1]
    imports = (
        "from substrate.auth.passkeys import PasskeySubjectBinding,registration_options; "
        "from substrate.multi_user.auth import subject_owner_id"
        if order == "passkeys_first" else
        "from substrate.multi_user.auth import subject_owner_id; "
        "from substrate.auth.passkeys import PasskeySubjectBinding,registration_options"
    )
    program = (
        imports + "; s='alice@example.test'; "
        "b=PasskeySubjectBinding('magic_link',s,subject_owner_id('magic_link',s)); "
        "assert registration_options(binding=b)['ceremony_id']"
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(root),
        "HOME": str(tmp_path),
        "ANTIEK_DUCKDB_PATH": str(tmp_path / "subjects.duckdb"),
        "ANTIEK_RESEARCH_EVENTS_DIR": str(tmp_path / "events"),
        "ANTIEK_HOME": str(tmp_path / "antiek-home"),
        "ANTIEK_EMAIL_PROVIDER": "mock",
        "ANTIEK_PASSKEY_STORE": str(tmp_path / "passkeys.json"),
        "ANTIEK_WEBAUTHN_RP_ID": RP,
        "ANTIEK_WEBAUTHN_ORIGINS": ORIGIN,
    }
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=root, env=env,
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr[-300:]


def test_passkey_mint_does_not_create_missing_subject_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    db = tmp_path / "subjects.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-passkey-" + "x" * 48)

    from substrate.multi_user.auth import mint_existing_magic_link_session
    from substrate.owner_identity import derive_owner_from_verified_email

    with pytest.raises(AuthError):
        mint_existing_magic_link_session(
            subject="alice@example.test",
            expected_owner_user_id=derive_owner_from_verified_email("alice@example.test"),
        )
    with duckdb.connect(str(db)) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name='auth_subjects'"
        ).fetchone()[0] == 0
