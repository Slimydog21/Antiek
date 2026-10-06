"""Account binding around WebAuthn verification, with unit verifier responses."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from substrate.auth import passkeys
from substrate.auth.accounts import (
    AccountStoreError,
    account_for_email,
    account_for_session,
    account_for_verified_email,
    account_registry_active,
    account_store_path,
    legacy_account_for_session,
)


@pytest.fixture
def stores(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(tmp_path / "accounts.json"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", "operator@example.test")
    alice = account_for_verified_email("alice@example.test")
    bob = account_for_verified_email("bob@example.test")
    return alice, bob, tmp_path


def _verifier(credential_id=b"local-public-credential"):
    return SimpleNamespace(
        credential_id=credential_id,
        credential_public_key=b"local-public-key",
        sign_count=0,
        credential_device_type=SimpleNamespace(value="multi_device"),
        credential_backed_up=True,
    )


def test_registration_binds_challenge_and_credential_to_same_subject(stores, monkeypatch):
    alice, bob, _root = stores
    calls = []
    monkeypatch.setattr(
        passkeys, "verify_registration_response", lambda **kw: calls.append(kw) or _verifier()
    )
    options = passkeys.registration_options(email=alice.email, user_id=alice.user_id)
    assert options["user"]["id"] == passkeys._b64(alice.user_id.encode())
    with pytest.raises(passkeys.PasskeyError, match="account"):
        passkeys.complete_registration(
            ceremony_id=options["ceremony_id"],
            credential={},
            label="Wrong account",
            user_id=bob.user_id,
        )
    assert not calls
    assert not passkeys.list_credentials()
    with pytest.raises(passkeys.PasskeyError, match="expired"):
        passkeys.complete_registration(
            ceremony_id=options["ceremony_id"],
            credential={},
            label="Replay",
            user_id=alice.user_id,
        )
    owned = passkeys.registration_options(email=alice.email, user_id=alice.user_id)
    record = passkeys.complete_registration(
        ceremony_id=owned["ceremony_id"],
        credential={},
        label="Alice",
        user_id=alice.user_id,
    )
    assert record.user_id == alice.user_id and record.email == alice.email
    assert passkeys.list_credentials() == [record]


def test_credential_cannot_be_rebound_or_deleted_by_other_account(stores, monkeypatch):
    alice, bob, _root = stores
    monkeypatch.setattr(passkeys, "verify_registration_response", lambda **kw: _verifier())
    first = passkeys.registration_options(email=alice.email, user_id=alice.user_id)
    record = passkeys.complete_registration(
        ceremony_id=first["ceremony_id"],
        credential={},
        label="Alice",
        user_id=alice.user_id,
    )
    second = passkeys.registration_options(email=bob.email, user_id=bob.user_id)
    with pytest.raises(passkeys.PasskeyError, match="different account"):
        passkeys.complete_registration(
            ceremony_id=second["ceremony_id"],
            credential={},
            label="Bob",
            user_id=bob.user_id,
        )
    assert not passkeys.delete_credential(record.credential_id, owner_ids=frozenset({bob.user_id}))
    assert passkeys.list_credentials() == [record]
    assert passkeys.delete_credential(record.credential_id, owner_ids=frozenset({alice.user_id}))


def test_authentication_keeps_stored_account_and_consumes_challenge(stores, monkeypatch):
    alice, _bob, _root = stores
    monkeypatch.setattr(passkeys, "verify_registration_response", lambda **kw: _verifier())
    begin = passkeys.registration_options(email=alice.email, user_id=alice.user_id)
    record = passkeys.complete_registration(
        ceremony_id=begin["ceremony_id"],
        credential={},
        label="Alice",
        user_id=alice.user_id,
    )
    monkeypatch.setattr(
        passkeys,
        "verify_authentication_response",
        lambda **kw: SimpleNamespace(
            new_sign_count=1,
            credential_device_type=SimpleNamespace(value="multi_device"),
            credential_backed_up=True,
        ),
    )
    options = passkeys.authentication_options()
    authenticated = passkeys.complete_authentication(
        ceremony_id=options["ceremony_id"],
        credential={"id": record.credential_id},
    )
    assert (authenticated.user_id, authenticated.email) == (alice.user_id, alice.email)
    assert authenticated.sign_count == 1
    with pytest.raises(passkeys.PasskeyError, match="expired"):
        passkeys.complete_authentication(
            ceremony_id=options["ceremony_id"],
            credential={"id": record.credential_id},
        )


def test_legacy_binding_requires_explicit_proof_and_cannot_transfer(stores, monkeypatch):
    alice, bob, root = stores
    assert legacy_account_for_session("operator@example.test") is None
    operator = account_for_verified_email(
        "operator@example.test",
        legacy_operator_email="operator@example.test",
    )
    assert legacy_account_for_session(operator.email) == operator
    assert operator.legacy_owner == "__operator__"
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", bob.email)
    assert legacy_account_for_session(operator.email) is None
    assert (
        account_for_verified_email(bob.email, legacy_operator_email=bob.email).legacy_owner is None
    )
    assert account_for_session(alice.user_id, bob.email) is None
    assert root.joinpath("accounts.json").stat().st_mode & 0o777 == 0o600


def test_corrupt_account_store_refuses_without_replacing_it(stores):
    _alice, _bob, root = stores
    store = root / "accounts.json"
    original = store.read_bytes()
    malformed = json.loads(original)
    malformed["accounts"][0]["user_id"] = "__operator__"
    bad = json.dumps(malformed).encode()
    store.write_bytes(bad)
    with pytest.raises(AccountStoreError):
        account_for_verified_email("another@example.test")
    assert store.read_bytes() == bad


def test_closing_signup_preserves_stored_public_subject_without_creating_unknown(stores, monkeypatch):
    alice, _bob, root = stores
    monkeypatch.delenv("ANTIEK_OPEN_SIGNUP", raising=False)
    original = root.joinpath("accounts.json").read_bytes()
    assert account_registry_active()
    assert account_for_email(alice.email) == alice
    assert account_for_session(alice.user_id, alice.email) == alice
    assert account_for_email("unknown@example.test") is None
    assert root.joinpath("accounts.json").read_bytes() == original


def test_concurrent_verified_account_creation_keeps_one_subject(stores):
    from concurrent.futures import ThreadPoolExecutor

    _alice, _bob, root = stores
    with ThreadPoolExecutor(max_workers=4) as workers:
        accounts = list(workers.map(account_for_verified_email, ["new@example.test"] * 8))
    assert all(account == accounts[0] for account in accounts)
    persisted = json.loads(root.joinpath("accounts.json").read_text())
    assert sum(row["email"] == "new@example.test" for row in persisted["accounts"]) == 1


def test_account_store_uses_the_hardened_writable_state_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTIEK_ACCOUNT_STORE", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "read-only-home"))
    state = tmp_path / "admitted-state"
    monkeypatch.setenv("ANTIEK_STATE_DIR", str(state))
    assert account_store_path() == state / "auth/accounts.json"
    account = account_for_verified_email("state-account@example.test")
    assert account_for_session(account.user_id, account.email) == account
    assert not (tmp_path / "read-only-home/auth/accounts.json").exists()
    configured = tmp_path / "explicit/accounts.json"
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(configured))
    assert account_store_path() == configured
