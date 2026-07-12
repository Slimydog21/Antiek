"""Durable multi-user account and revocable session authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from substrate.auth.account_store import SqliteAuthStore


def test_concurrent_first_login_resolves_one_stable_user(tmp_path):
    path = tmp_path / "auth.sqlite3"

    def create() -> str:
        return SqliteAuthStore(path).get_or_create_user("Alice@Example.com").user_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _index: create(), range(24)))
    assert len(set(ids)) == 1
    assert ids[0].startswith("usr_")
    assert "alice" not in ids[0]


def test_distinct_emails_receive_distinct_opaque_ids(tmp_path):
    store = SqliteAuthStore(tmp_path / "auth.sqlite3")
    alice = store.get_or_create_user("alice@example.com")
    bob = store.get_or_create_user("bob@example.com")
    assert alice.user_id != bob.user_id
    assert alice.role == bob.role == "user"
    assert alice.status == bob.status == "active"


def test_magic_link_nonce_consumes_exactly_once(tmp_path):
    store = SqliteAuthStore(tmp_path / "auth.sqlite3")
    store.register_magic_link(email="alice@example.com", nonce="n" * 24, expires_at=200)
    assert store.consume_magic_link(
        email="alice@example.com", nonce="n" * 24, now=100
    )
    assert not store.consume_magic_link(
        email="alice@example.com", nonce="n" * 24, now=101
    )
    assert not store.consume_magic_link(
        email="bob@example.com", nonce="n" * 24, now=100
    )


def test_magic_link_rate_limits_email_and_client_atomically(tmp_path):
    store = SqliteAuthStore(tmp_path / "auth.sqlite3")
    for _ in range(3):
        assert store.allow_magic_link_request(
            email="alice@example.com", client_key="client-a", now=100
        )
    assert not store.allow_magic_link_request(
        email="alice@example.com", client_key="client-a", now=100
    )
    assert store.allow_magic_link_request(
        email="alice@example.com", client_key="client-a", now=3700
    )


def test_session_revocation_and_account_disable_are_immediate(tmp_path):
    store = SqliteAuthStore(tmp_path / "auth.sqlite3")
    account = store.get_or_create_user("alice@example.com")
    sid = store.create_session(
        user_id=account.user_id, email=account.email, ttl_seconds=3600
    )
    assert store.validate_session(
        session_id=sid, user_id=account.user_id, email=account.email
    ) == account
    assert store.revoke_session(sid)
    assert store.validate_session(
        session_id=sid, user_id=account.user_id, email=account.email
    ) is None

    sid2 = store.create_session(
        user_id=account.user_id, email=account.email, ttl_seconds=3600
    )
    store.set_status(account.user_id, "disabled")
    assert store.validate_session(
        session_id=sid2, user_id=account.user_id, email=account.email
    ) is None


def test_session_binding_rejects_user_or_email_drift(tmp_path):
    store = SqliteAuthStore(tmp_path / "auth.sqlite3")
    account = store.get_or_create_user("alice@example.com")
    sid = store.create_session(
        user_id=account.user_id, email=account.email, ttl_seconds=3600
    )
    assert store.validate_session(
        session_id=sid, user_id="usr_wrong", email=account.email
    ) is None
    assert store.validate_session(
        session_id=sid, user_id=account.user_id, email="other@example.com"
    ) is None
