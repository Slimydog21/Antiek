"""SPR-02 authenticated owner and feedback isolation gates."""

from __future__ import annotations

import duckdb
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.auth import mint_magic_link_token

_SECRET = "spr02-auth-secret-" + "x" * 48
_EMAIL_A = "owner-a@example.test"
_EMAIL_B = "owner-b@example.test"


def _signed_client(monkeypatch, email: str) -> TestClient:
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    token = mint_magic_link_token(email)
    response = client.get(f"/auth/callback?token={token}", follow_redirects=False)
    assert response.status_code == 302
    assert "ANTIEK_SESSION" in response.cookies
    return client


def test_verified_magic_link_subjects_mint_distinct_durable_owners(
    monkeypatch, tmp_path
) -> None:
    db_path = tmp_path / "owners.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{_EMAIL_A},{_EMAIL_B}")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setattr("interfaces.research.api.auth.list_credentials", lambda: [object()])

    client_a = _signed_client(monkeypatch, _EMAIL_A)
    client_b = _signed_client(monkeypatch, _EMAIL_B)

    me_a = client_a.get("/auth/me")
    me_b = client_b.get("/auth/me")
    assert me_a.status_code == me_b.status_code == 200
    owner_a = me_a.json()["user_id"]
    owner_b = me_b.json()["user_id"]
    assert owner_a.startswith("user:magic_link:")
    assert owner_b.startswith("user:magic_link:")
    assert owner_a != owner_b

    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            "SELECT provider, subject, owner_user_id FROM auth_subjects "
            "ORDER BY subject"
        ).fetchall()
    assert rows == [
        ("magic_link", _EMAIL_A, owner_a),
        ("magic_link", _EMAIL_B, owner_b),
    ]

    # A repeated proof converges to the same durable owner.
    repeated = _signed_client(monkeypatch, _EMAIL_A).get("/auth/me")
    assert repeated.status_code == 200
    assert repeated.json()["user_id"] == owner_a
