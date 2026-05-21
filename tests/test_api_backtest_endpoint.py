"""Backtest report endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-backtest-")
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


def test_backtest_missing_synthesis_returns_404(isolated_db):
    client = _client()
    resp = client.get("/backtest/does-not-exist")
    assert resp.status_code == 404


def test_backtest_existing_synthesis_returns_report(isolated_db):
    """An existing synthesis row (even without explicit archive
    events) yields a report — counters report 0 across the board
    because nothing has changed since it landed."""
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:seed_syn") as con:
        con.execute(
            "INSERT INTO syntheses ("
            "synthesis_id, target_question, synthesis_timestamp, "
            "status, implicit_recommendation"
            ") VALUES ('syn-fresh', 'test', CURRENT_TIMESTAMP, "
            "'draft', 'undetermined')",
        )
    client = _client()
    resp = client.get("/backtest/syn-fresh")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["synthesis_id"] == "syn-fresh"
    assert body["target_question"] == "test"
    # Fresh synthesis with no diffs since → zero counters.
    assert body["added_edges_since"] == 0
    assert body["superseded_edges_since"] == 0
    assert body["cited_edges_now_superseded_count"] == 0
    assert body["chunks_retired_downward_count"] == 0
    assert body["outcomes_recorded"] == 0
