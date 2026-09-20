"""OYM P1 §5 — visible tiers (write half): GET/POST /settings/tier-overrides.

Covers: POST appends an override through the sanctioned writer and GET
round-trips it (set_by == the request owner id, original_tier == the
chunk's current tier), invalid tier 400, empty reason 400, unknown chunk
404 (both verbs), append-only history (two overrides both appear, newest
first), and the lock-timeout → 503 path (real flock contention, short
timeout via monkeypatch). The autouse store isolation fixture
(tests/conftest.py) points ANTIEK_DUCKDB_PATH at a tmp store, so nothing
here can touch the operator's real graph.
"""

from __future__ import annotations

import fcntl
import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    init_database_at_path,
    insert_chunk,
    insert_document,
)

_OWNER_DEFAULT = "__operator__"


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture
def client() -> TestClient:
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False)
    )


@pytest.fixture
def seeded_chunk(tmp_path, monkeypatch):
    """One document (tier 2) + one chunk in the isolated tmp store."""
    db = default_db_path()
    init_database_at_path(db)
    with connect_write(db, purpose="test-seed") as con:
        insert_document(
            con,
            document_id="doc-tiers",
            source_tier=2,
            document_type="white_paper",
            title="Tiered Paper",
            author="Grace Hopper",
        )
        insert_chunk(
            con,
            document_id="doc-tiers",
            chunk_index=0,
            text="The tier audit trail records every retiering decision.",
            section_path="§2",
            chunk_id="chunk-tiers-1",
        )
    return {"chunk_id": "chunk-tiers-1", "document_id": "doc-tiers", "db": db}


def _get(client: TestClient, chunk_id: str):
    return client.get(f"/settings/tier-overrides?chunk_id={chunk_id}")


# ── POST round-trip ──────────────────────────────────────────────────────


def test_post_writes_override_and_get_round_trips(client, seeded_chunk):
    r = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": seeded_chunk["chunk_id"],
            "override_tier": 4,
            "reason": "operator review: source provenance is thin",
        },
    )
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["chunk_id"] == "chunk-tiers-1"
    # original_tier == the chunk's current tier (its document's source_tier).
    assert row["original_tier"] == 2
    assert row["override_tier"] == 4
    assert row["reason"] == "operator review: source provenance is thin"
    # set_by == the request owner id (unauthenticated-local operator default).
    assert row["set_by"] == _OWNER_DEFAULT
    assert row["set_at"]

    r = _get(client, seeded_chunk["chunk_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chunk_id"] == "chunk-tiers-1"
    # The chunk's current tier rides along for context.
    assert body["current_original_tier"] == 2
    assert len(body["overrides"]) == 1
    assert body["overrides"][0] == row


def test_post_stamps_authenticated_owner(client, seeded_chunk, monkeypatch):
    """When the auth middleware resolves a real user id, set_by is that id
    (the API routes use request_owner_user_id, never a hardcoded owner)."""
    from substrate.multi_user.auth import UserClaims, operator_claims

    def _authenticated_claims() -> UserClaims:
        return UserClaims(
            user_id="user-42",
            email=None,
            scopes=frozenset({"operator", "private_research", "shared_substrate_write"}),
            issued_at=operator_claims().issued_at,
        )

    monkeypatch.setattr("substrate.multi_user.auth.operator_claims", _authenticated_claims)
    r = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": seeded_chunk["chunk_id"],
            "override_tier": 3,
            "reason": "mid-tier on follow-up verification",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["set_by"] == "user-42"


# ── Validation: 400s ─────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_tier", [0, 6, -1, 1.5, "3"])
def test_post_invalid_tier_returns_400(client, seeded_chunk, bad_tier):
    r = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": seeded_chunk["chunk_id"],
            "override_tier": bad_tier,
            "reason": "should not be recorded",
        },
    )
    assert r.status_code == 400, r.text
    assert "override_tier" in r.json()["detail"]


def test_post_empty_reason_returns_400(client, seeded_chunk):
    for reason in ["", "   "]:
        r = client.post(
            "/settings/tier-overrides",
            json={
                "chunk_id": seeded_chunk["chunk_id"],
                "override_tier": 4,
                "reason": reason,
            },
        )
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert "reason" in detail.lower()
        assert "audit" in detail.lower()


def test_post_overlong_reason_returns_400(client, seeded_chunk):
    r = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": seeded_chunk["chunk_id"],
            "override_tier": 4,
            "reason": "x" * 2049,
        },
    )
    assert r.status_code == 400, r.text
    assert "2048" in r.json()["detail"]


# ── 404s ─────────────────────────────────────────────────────────────────


def test_post_unknown_chunk_returns_404(client, seeded_chunk):
    r = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": "chunk-does-not-exist",
            "override_tier": 4,
            "reason": "cannot retier a chunk that is not in the graph",
        },
    )
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"]


def test_get_unknown_chunk_returns_404(client, seeded_chunk):
    r = _get(client, "chunk-does-not-exist")
    assert r.status_code == 404, r.text


def test_get_missing_store_returns_404_and_never_creates(tmp_path, monkeypatch, client):
    """A GET against a missing store must 404, never initialize the DB
    (the P0 read-only principle: no write side effects on read surfaces)."""
    missing = str(tmp_path / "never" / "created.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", missing)
    assert _get(client, "chunk-x").status_code == 404
    assert (
        client.post(
            "/settings/tier-overrides",
            json={"chunk_id": "chunk-x", "override_tier": 3, "reason": "x"},
        ).status_code
        == 404
    )
    assert not os.path.exists(missing)


# ── Append-only audit ────────────────────────────────────────────────────


def test_overrides_are_append_only_newest_first(client, seeded_chunk):
    first = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": seeded_chunk["chunk_id"],
            "override_tier": 4,
            "reason": "first demotion",
        },
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/settings/tier-overrides",
        json={
            "chunk_id": seeded_chunk["chunk_id"],
            "override_tier": 5,
            "reason": "second demotion after source vanished",
        },
    )
    assert second.status_code == 200, second.text

    r = _get(client, seeded_chunk["chunk_id"])
    assert r.status_code == 200, r.text
    overrides = r.json()["overrides"]
    assert len(overrides) == 2
    # Newest first: the second write is the newest row.
    assert overrides[0]["override_tier"] == 5
    assert overrides[1]["override_tier"] == 4
    # Both rows kept their own original_tier snapshot (tier at write time).
    assert overrides[0]["original_tier"] == 2
    assert overrides[1]["original_tier"] == 2
    # Each entry carries its own reason + owner — the audit is per-entry.
    assert overrides[0]["reason"] == "second demotion after source vanished"
    assert overrides[1]["reason"] == "first demotion"
    assert {o["set_by"] for o in overrides} == {_OWNER_DEFAULT}


# ── Lock contention → 503 ────────────────────────────────────────────────


def test_post_lock_timeout_returns_503(client, seeded_chunk, monkeypatch):
    """Hold the real exclusive flock on the sidecar lock file, shrink the
    endpoint's wait window, and assert the honest 503 — no fabricated row."""
    import interfaces.research.api.settings_tiers as settings_tiers

    monkeypatch.setattr(settings_tiers, "_LOCK_TIMEOUT_S", 0.2)
    lock_path = seeded_chunk["db"] + ".write.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        r = client.post(
            "/settings/tier-overrides",
            json={
                "chunk_id": seeded_chunk["chunk_id"],
                "override_tier": 4,
                "reason": "should time out, not be recorded",
            },
        )
        assert r.status_code == 503, r.text
        assert "unavailable" in r.json()["detail"]
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    # Nothing was recorded while the writer was blocked.
    r = _get(client, seeded_chunk["chunk_id"])
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] == []


def test_get_never_needs_the_write_lock(client, seeded_chunk):
    """Reads go through connect_read — no flock, so a held write lock
    must not block or fail the GET."""
    lock_path = seeded_chunk["db"] + ".write.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        r = _get(client, seeded_chunk["chunk_id"])
        assert r.status_code == 200, r.text
        assert r.json()["current_original_tier"] == 2
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
