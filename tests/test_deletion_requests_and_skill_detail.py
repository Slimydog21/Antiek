"""Trust-center deletion-request + skill rule detail endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.multi_user import (
    encode_verified_claims_header,
    sign_verified_claims_header,
)


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-del-rq-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


def _external_headers(
    monkeypatch,
    *,
    sub: str,
    scopes: list[str] | None = None,
) -> dict[str, str]:
    secret = "trusted-hop-secret"
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_VENDOR", "supabase")
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_HEADER_SECRET", secret)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    encoded = encode_verified_claims_header({
        "sub": sub,
        "email": f"{sub}@example.com",
        "app_metadata": {"antiek_scopes": scopes or ["private_research"]},
    })
    signature = sign_verified_claims_header(
        vendor="supabase",
        encoded_claims=encoded,
        secret=secret,
    )
    return {
        "X-Antiek-Verified-Claims": encoded,
        "X-Antiek-Verified-Claims-Signature": signature,
    }


# ── Skill rule detail endpoint ─────────────────────────────────────


def test_skill_rule_detail_404_when_missing(isolated_db):
    client = _client()
    resp = client.get("/skill-rules/does-not-exist")
    assert resp.status_code == 404


def test_skill_rule_detail_returns_seeded_rule(isolated_db):
    from runtime.db_lock import connect_write
    from substrate.multi_user.skill_propagation import (
        SkillRuleDigest,
        propagate_to_shared_substrate,
    )

    digest = SkillRuleDigest(
        rule_id="skill-detail-1",
        rule_text="Tier-1 sources include Lukin lab",
        rule_kind="source_tier_rule",
        domain="quantum",
        epsilon_budget_consumed=0.03,
        source_user_count=4,
        confidence="moderate",
    )
    with connect_write(isolated_db, purpose="test:seed_skill") as con:
        propagate_to_shared_substrate(con, digest)

    client = _client()
    resp = client.get("/skill-rules/skill-detail-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rule_id"] == "skill-detail-1"
    assert body["rule_text"] == "Tier-1 sources include Lukin lab"
    assert body["domain"] == "quantum"
    assert body["source_user_count"] == 4
    assert body["confidence"] == "moderate"


# ── Deletion request POST ──────────────────────────────────────────


def test_post_deletion_request_creates_pending_record(isolated_db):
    client = _client()
    resp = client.post(
        "/trust-center/deletion-requests",
        json={"reason": "moving to a different platform"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["user_id"] == "__operator__"
    assert body["reason"] == "moving to a different platform"
    assert body["cancellation_window_days"] == 7
    assert body["deletion_sla_days"] == 30
    assert body["request_id"].startswith("del-")


# ── Deletion request GET listing ──────────────────────────────────


def test_list_deletion_requests_returns_users_own(isolated_db):
    client = _client()
    client.post(
        "/trust-center/deletion-requests", json={"reason": "test 1"},
    )
    client.post(
        "/trust-center/deletion-requests", json={"reason": "test 2"},
    )
    resp = client.get("/trust-center/deletion-requests")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["requests"]) == 2
    # Newest first.
    assert body["requests"][0]["reason"] in {"test 1", "test 2"}
    for r in body["requests"]:
        assert r["status"] == "pending"
        assert r["user_id"] == "__operator__"


# ── Deletion request CANCEL ───────────────────────────────────────


def test_cancel_pending_deletion(isolated_db):
    client = _client()
    create = client.post(
        "/trust-center/deletion-requests", json={"reason": "test"},
    )
    request_id = create.json()["request_id"]
    resp = client.post(
        f"/trust-center/deletion-requests/{request_id}/cancel",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["request_id"] == request_id


def test_cancel_missing_request_returns_404(isolated_db):
    client = _client()
    resp = client.post(
        "/trust-center/deletion-requests/does-not-exist/cancel",
    )
    assert resp.status_code == 404


def test_cancel_already_cancelled_returns_409(isolated_db):
    client = _client()
    create = client.post(
        "/trust-center/deletion-requests", json={"reason": "test"},
    )
    request_id = create.json()["request_id"]
    client.post(f"/trust-center/deletion-requests/{request_id}/cancel")
    # Second cancel attempt → 409 with wrong_status code.
    resp = client.post(
        f"/trust-center/deletion-requests/{request_id}/cancel",
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "wrong_status"


# ── Cross-user isolation ───────────────────────────────────────────


def test_cannot_cancel_other_users_request(isolated_db, monkeypatch):
    """A user other than the originator can't cancel."""
    from runtime.db_lock import connect_write

    # Seed a deletion request for a non-operator user directly.
    other_request_id = "del-otheruser1234"
    with connect_write(
        isolated_db, purpose="test:seed_del_req",
    ) as con:
        con.execute(
            "INSERT INTO deletion_requests "
            "(request_id, user_id, status, reason) "
            "VALUES (?, ?, 'pending', ?)",
            [other_request_id, "some-other-user", "test"],
        )

    client = _client()
    # The default test client's user_id is __operator__.
    resp = client.post(
        f"/trust-center/deletion-requests/{other_request_id}/cancel",
    )
    assert resp.status_code == 403


def test_external_user_deletion_requests_are_scoped_to_claims_user(
    isolated_db, monkeypatch,
):
    client = _client()
    user_a = _external_headers(monkeypatch, sub="reader-a")
    create = client.post(
        "/trust-center/deletion-requests",
        json={"reason": "privacy export complete"},
        headers=user_a,
    )
    assert create.status_code == 201
    request_id = create.json()["request_id"]
    assert create.json()["user_id"] == "supabase:reader-a"

    listed = client.get("/trust-center/deletion-requests", headers=user_a)
    assert listed.status_code == 200
    assert [r["request_id"] for r in listed.json()["requests"]] == [request_id]

    user_b = _external_headers(monkeypatch, sub="reader-b")
    listed_b = client.get("/trust-center/deletion-requests", headers=user_b)
    assert listed_b.status_code == 200
    assert listed_b.json()["requests"] == []

    forbidden = client.post(
        f"/trust-center/deletion-requests/{request_id}/cancel",
        headers=user_b,
    )
    assert forbidden.status_code == 403

    cancelled = client.post(
        f"/trust-center/deletion-requests/{request_id}/cancel",
        headers=user_a,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
