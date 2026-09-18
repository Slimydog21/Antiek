"""POST /api/ad/fills stays responsive under write-lock contention.

Cite: #3121 LazyRW coexist; #3153 Speak invite landing nonblock.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write


@pytest.fixture()
def isolated_client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-ad-fills-nb-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        from interfaces.research.api.app import create_app

        client = TestClient(create_app())
        yield client, db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _fill_body(window_id: str) -> dict:
    return {
        "window_id": window_id,
        "lens": "read",
        "positions": ["bottom"],
        "document_id": None,
        "page_index": None,
    }


def test_fills_replay_fast_while_writer_holds_lock(isolated_client):
    client, db = isolated_client
    first = client.post("/api/ad/fills", json=_fill_body("win:nb-replay"))
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["fills"][0]["revenue_usd_cents"] == 0
    assert first_body["fills"][0]["price_status"] == "unpriced"
    decision_id = first_body["fills"][0]["fill_decision_id"]

    release = threading.Event()
    held = threading.Event()

    def hold_writer():
        with connect_write(db, purpose="test:hold-for-fills", timeout_s=30) as con:
            con.execute("SELECT 1")
            held.set()
            release.wait(timeout=15)

    t = threading.Thread(target=hold_writer, daemon=True)
    t.start()
    assert held.wait(timeout=5)

    t0 = time.monotonic()
    second = client.post("/api/ad/fills", json=_fill_body("win:nb-replay"))
    elapsed = time.monotonic() - t0
    release.set()
    t.join(timeout=5)

    assert second.status_code == 200, second.text
    assert second.json()["fills"][0]["fill_decision_id"] == decision_id
    assert second.json()["fills"][0]["revenue_usd_cents"] == 0
    assert elapsed < 2.0, f"fills replay took {elapsed:.3f}s under writer hold"


def test_fills_new_returns_503_quickly_under_writer_hold(isolated_client):
    client, db = isolated_client

    release = threading.Event()
    held = threading.Event()

    def hold_writer():
        with connect_write(db, purpose="test:hold-for-fills-new", timeout_s=30) as con:
            con.execute("SELECT 1")
            held.set()
            release.wait(timeout=20)

    t = threading.Thread(target=hold_writer, daemon=True)
    t.start()
    assert held.wait(timeout=5)

    t0 = time.monotonic()
    resp = client.post("/api/ad/fills", json=_fill_body("win:nb-new-busy"))
    elapsed = time.monotonic() - t0
    release.set()
    t.join(timeout=5)

    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == "ad_fill_writer_busy"
    assert elapsed < 5.0, f"fills new-busy took {elapsed:.3f}s (expected ~2s cap)"


def test_lookup_fill_decision_read_path(isolated_client):
    from runtime.db_lock import connect_read, connect_write
    from substrate.ad_inventory.fill_decisions import (
        decide_fills,
        lookup_fill_decision,
    )

    _, db = isolated_client
    with connect_write(db, purpose="test:seed-fill", timeout_s=10) as con:
        decided = decide_fills(
            con,
            owner_user_id="__operator__",
            window_id="win:lookup",
            document_id=None,
            page_index=None,
            lens="read",
            positions=("bottom",),
            select_fills=lambda: [
                {
                    "position": "bottom",
                    "kind": "house",
                    "revenue_usd_cents": 0,
                    "ad": None,
                    "house": None,
                }
            ],
        )
    con_r = connect_read(db)
    try:
        found = lookup_fill_decision(
            con_r,
            owner_user_id="__operator__",
            window_id="win:lookup",
            document_id=None,
            page_index=None,
            lens="read",
            positions=("bottom",),
        )
    finally:
        con_r.close()
    assert found is not None
    assert found.decision_id == decided.decision_id
    assert found.replayed is True
    assert found.revenue_usd_cents == 0
