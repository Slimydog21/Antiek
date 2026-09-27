"""Signed subject sessions preserve the existing per-person acct_ owner bytes."""

from __future__ import annotations

import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from interfaces.research.api.account_memory_identity import (
    derive_owner_from_verified_email as api_derive_owner,
)
from interfaces.research.api.account_memory_identity import distinct_signed_owner
from interfaces.research.api.app import create_app
from interfaces.research.api.settings_models_admin import request_owner_user_id
from runtime.db_lock import connect_write
from substrate.auth.email_provider import MockEmailProvider
from substrate.auth.magic_link import mint_magic_link_token
from substrate.auth.magic_link import mint_session_cookie as mint_raw_cookie
from substrate.multi_user import auth as subject_auth
from substrate.multi_user.auth import (
    AuthError,
    AuthSubjectConflict,
    ensure_auth_subjects_schema,
    mint_session_cookie,
    resolve_authenticated_principal,
    subject_owner_id,
)

ALICE = "alice@example.test"
BOB = "bob@example.test"
SECRET = "namespace-synthetic-" + "x" * 48


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db = str(tmp_path / "subjects.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ALICE},{BOB}")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    for key in (
        "ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET", "ANTIEK_DEV_LOGIN_TOKEN", "TURBOPUFFER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    from interfaces.research.api.auth import reset_auth_throttles

    reset_auth_throttles()
    return db


def _client() -> TestClient:
    app = create_app(register_wrestling=False, register_providers=False)

    @app.get("/_test/namespace-owner")
    def owner_probe(request: Request) -> dict[str, object]:
        principal = resolve_authenticated_principal(request)
        return {
            "principal": principal.owner_user_id,
            "middleware": getattr(request.state, "user_id", None),
            "verified_attached": getattr(request.state, "verified_principal", None) == principal,
            "memory_owner": distinct_signed_owner(request),
            "settings_owner": request_owner_user_id(request),
        }

    return TestClient(app, raise_server_exceptions=False)


def _callback(client: TestClient, email: str):
    token = mint_magic_link_token(email)
    return client.get(f"/auth/callback?token={token}", follow_redirects=False)


def test_mounted_callback_preserves_acct_owner_and_consumers(auth_env):
    expected = {email: api_derive_owner(email) for email in (ALICE, BOB)}
    assert all(expected.values()) and expected[ALICE] != expected[BOB]
    for email in (ALICE, BOB):
        client = _client()
        response = _callback(client, email)
        assert response.status_code == 302
        assert "ANTIEK_SESSION" in response.cookies
        assert client.get("/auth/me").json()["user_id"] == expected[email]
        assert client.get("/_test/namespace-owner").json() == {
            "principal": expected[email],
            "middleware": expected[email],
            "verified_attached": True,
            "memory_owner": expected[email],
            "settings_owner": expected[email],
        }
    with duckdb.connect(auth_env, read_only=True) as con:
        rows = con.execute(
            "SELECT provider,subject,owner_user_id FROM auth_subjects ORDER BY subject"
        ).fetchall()
    assert rows == [
        ("magic_link", ALICE, expected[ALICE]),
        ("magic_link", BOB, expected[BOB]),
    ]
    repeated = _client()
    assert _callback(repeated, ALICE).status_code == 302
    assert repeated.get("/_test/namespace-owner").json()["principal"] == expected[ALICE]


def test_core_bytes_and_api_reexport_keep_b41_contract():
    from substrate.owner_identity import derive_owner_from_verified_email as core_derive

    assert api_derive_owner is core_derive
    assert core_derive(" Alice@Example.Test ") == "acct_69b1145a03334875161ea18c1373b570"
    assert core_derive("straße@example.test") == core_derive("strasse@example.test")
    for invalid in (None, 1, "", "not-an-email", "@example.test", "alice@", "a@b@c", "a" * 321 + "@x"):
        assert core_derive(invalid) is None
    with pytest.raises(AuthError):
        subject_owner_id("magic_link", "straße@example.test")
    with pytest.raises(AuthError):
        subject_owner_id("magic_link", "a" * 250 + "@example.test")


@pytest.mark.parametrize("order", ("core_first", "api_first"))
def test_pure_core_import_order_has_no_api_cycle(order, tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = (
        "from substrate.owner_identity import derive_owner_from_verified_email as core; "
        "from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email as api; "
        "from substrate.multi_user.auth import subject_owner_id"
        if order == "core_first"
        else "from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email as api; "
        "from substrate.multi_user.auth import subject_owner_id; "
        "from substrate.owner_identity import derive_owner_from_verified_email as core"
    )
    script += "; assert api is core; assert subject_owner_id('magic_link', 'Alice@Example.Test') == core('Alice@Example.Test')"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(root),
        "HOME": str(tmp_path),
        "ANTIEK_HOME": str(tmp_path / "home"),
        "ANTIEK_DUCKDB_PATH": str(tmp_path / "subjects.duckdb"),
        "ANTIEK_RESEARCH_EVENTS_DIR": str(tmp_path / "events"),
        "ANTIEK_PASSKEY_STORE": str(tmp_path / "passkeys.json"),
        "ANTIEK_EMAIL_PROVIDER": "mock",
        "ANTIEK_VSS_ALLOW_INSTALL": "0",
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=root, env=env,
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]


def test_mounted_code_claim_preserves_acct_owner(auth_env, monkeypatch):
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    client = _client()
    requested = client.post("/auth/request", json={"email": ALICE, "next": "/"})
    assert requested.status_code == 200
    assert len(sender.sent) == 1
    code = sender.sent[0].email.subject.rsplit("·", 1)[-1].strip()
    claim = client.post(
        "/auth/claim",
        json={
            "attempt_id": requested.json()["attempt_id"],
            "claim_secret": requested.json()["claim_secret"],
            "code": code,
        },
    )
    assert claim.status_code == 200
    assert "ANTIEK_SESSION" in claim.cookies
    expected = api_derive_owner(ALICE)
    assert client.get("/_test/namespace-owner").json() == {
        "principal": expected,
        "middleware": expected,
        "verified_attached": True,
        "memory_owner": expected,
        "settings_owner": expected,
    }
    with duckdb.connect(auth_env, read_only=True) as con:
        assert con.execute(
            "SELECT provider,subject,owner_user_id FROM auth_subjects"
        ).fetchall() == [("magic_link", ALICE, expected)]


def test_old_user_mapping_refuses_without_overwrite_or_cookie(auth_env):
    old_owner = "user:magic_link:" + sha256(ALICE.encode("ascii")).hexdigest()[:32]
    with connect_write(auth_env, purpose="namespace-old-row", keepalive_s=0) as con:
        ensure_auth_subjects_schema(con)
        con.execute(
            "INSERT INTO auth_subjects VALUES (?, ?, ?, now(), now())",
            ["magic_link", ALICE, old_owner],
        )
    with pytest.raises(AuthSubjectConflict):
        mint_session_cookie("magic_link", ALICE, ALICE)
    old_cookie = mint_raw_cookie(
        user_id=old_owner, email=ALICE, provider="magic_link", subject=ALICE
    )
    with pytest.raises(AuthError):
        resolve_authenticated_principal(SimpleNamespace(cookies={"ANTIEK_SESSION": old_cookie}))
    client = _client()
    response = _callback(client, ALICE)
    assert response.status_code == 500  # Existing route has no typed HTTP mapping.
    assert "ANTIEK_SESSION" not in response.cookies
    with duckdb.connect(auth_env, read_only=True) as con:
        assert con.execute("SELECT owner_user_id FROM auth_subjects").fetchall() == [(old_owner,)]


def test_forced_ascii_unique_owner_collision_rolls_back(auth_env, monkeypatch):
    # Both subjects are admitted ASCII. The forced collision tests DB UNIQUE
    # mechanics, not Unicode admission (D2 currently rejects Unicode subjects).
    expected = api_derive_owner(ALICE)
    monkeypatch.setattr(subject_auth, "derive_owner_from_verified_email", lambda _: expected)
    mint_session_cookie("magic_link", ALICE, ALICE)
    with pytest.raises(AuthSubjectConflict):
        mint_session_cookie("magic_link", BOB, BOB)
    with duckdb.connect(auth_env, read_only=True) as con:
        assert con.execute(
            "SELECT subject,owner_user_id FROM auth_subjects"
        ).fetchall() == [(ALICE, expected)]


def test_missing_tampered_map_and_raw_legacy_cookie_are_not_principal(auth_env):
    cookie = mint_session_cookie("magic_link", ALICE, ALICE)
    request = SimpleNamespace(cookies={"ANTIEK_SESSION": cookie})
    assert resolve_authenticated_principal(request).owner_user_id == api_derive_owner(ALICE)
    with connect_write(auth_env, purpose="namespace-tampered-row", keepalive_s=0) as con:
        con.execute(
            "UPDATE auth_subjects SET owner_user_id='different-owner' WHERE subject=?", [ALICE]
        )
    with pytest.raises(AuthError):
        resolve_authenticated_principal(request)
    with connect_write(auth_env, purpose="namespace-missing-row", keepalive_s=0) as con:
        con.execute("DELETE FROM auth_subjects WHERE subject=?", [ALICE])
    with pytest.raises(AuthError):
        resolve_authenticated_principal(request)
    raw = mint_raw_cookie(user_id=api_derive_owner(ALICE), email=ALICE)
    with pytest.raises(AuthError):
        resolve_authenticated_principal(SimpleNamespace(cookies={"ANTIEK_SESSION": raw}))
