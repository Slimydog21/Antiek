"""Cross-investigation outcomes listing tests."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-outcomes-recent-")
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


def _seed_synthesis(db_path: str, synthesis_id: str) -> None:
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="test:seed_synthesis") as con:
        con.execute(
            "INSERT INTO syntheses ("
            "synthesis_id, target_question, synthesis_timestamp, "
            "status, implicit_recommendation"
            ") VALUES (?, ?, CURRENT_TIMESTAMP, 'draft', 'undetermined')",
            [synthesis_id, "test question"],
        )


def _record_outcome(client: TestClient, synthesis_id: str, observer: str = "__operator__"):
    client.post(
        "/outcomes",
        json={
            "synthesis_id": synthesis_id,
            "observer": observer,
            "thesis_outcomes": [
                {"thesis_claim": "x", "outcome": "confirmed", "evidence": ""},
            ],
        },
    )


def test_recent_outcomes_empty(isolated_db):
    client = _client()
    resp = client.get("/outcomes")
    assert resp.status_code == 200
    assert resp.json() == {"outcomes": []}


def test_recent_outcomes_lists_newest_first(isolated_db):
    client = _client()
    synth_ids = [f"syn-{uuid.uuid4().hex[:10]}" for _ in range(3)]
    for sid in synth_ids:
        _seed_synthesis(isolated_db, sid)
        _record_outcome(client, sid)

    resp = client.get("/outcomes")
    body = resp.json()
    assert len(body["outcomes"]) == 3
    # Newest first contract.
    timestamps = [r["observed_at"] for r in body["outcomes"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_recent_outcomes_respects_limit(isolated_db):
    client = _client()
    for i in range(5):
        sid = f"syn-{i}-{uuid.uuid4().hex[:6]}"
        _seed_synthesis(isolated_db, sid)
        _record_outcome(client, sid)
    resp = client.get("/outcomes?limit=2")
    body = resp.json()
    assert len(body["outcomes"]) == 2


def test_recent_outcomes_filters_by_observer(isolated_db):
    """observer query param scopes to one observer's grading history."""
    client = _client()
    sid_a = f"syn-{uuid.uuid4().hex[:10]}"
    sid_b = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, sid_a)
    _seed_synthesis(isolated_db, sid_b)
    _record_outcome(client, sid_a, observer="alice")
    _record_outcome(client, sid_b, observer="bob")

    resp = client.get("/outcomes?observer=alice")
    body = resp.json()
    assert len(body["outcomes"]) == 1
    assert body["outcomes"][0]["observer"] == "alice"
    assert body["outcomes"][0]["synthesis_id"] == sid_a


def test_recent_outcomes_returns_empty_when_no_match(isolated_db):
    client = _client()
    sid = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, sid)
    _record_outcome(client, sid, observer="someone")
    resp = client.get("/outcomes?observer=nobody")
    assert resp.json() == {"outcomes": []}
