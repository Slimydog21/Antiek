"""Documents listing endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-docs-listing-")
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


def _seed_document(
    db_path: str,
    *,
    document_id: str,
    source_tier: int = 3,
    investigation_id: str | None = None,
    title: str | None = None,
):
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="test:seed_doc") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, source_uri, "
            "title, investigation_id"
            ") VALUES (?, ?, 'pdf', 'file:///test.pdf', ?, ?)",
            [document_id, source_tier, title or "untitled", investigation_id],
        )


# ── Empty state ───────────────────────────────────────────────────


def test_documents_listing_empty(isolated_db):
    client = _client()
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == {"documents": []}


# ── Listing returns seeded rows ───────────────────────────────────


def test_documents_listing_returns_rows(isolated_db):
    _seed_document(isolated_db, document_id="doc-1", source_tier=1)
    _seed_document(isolated_db, document_id="doc-2", source_tier=3)
    client = _client()
    resp = client.get("/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["documents"]) == 2


# ── Filter by source_tier ─────────────────────────────────────────


def test_documents_listing_filter_by_tier(isolated_db):
    _seed_document(isolated_db, document_id="t1", source_tier=1)
    _seed_document(isolated_db, document_id="t3", source_tier=3)
    _seed_document(isolated_db, document_id="t1b", source_tier=1)
    client = _client()
    resp = client.get("/documents?source_tier=1")
    body = resp.json()
    assert len(body["documents"]) == 2
    for d in body["documents"]:
        assert d["source_tier"] == 1


# ── Filter by investigation ──────────────────────────────────────


def test_documents_listing_filter_by_investigation(isolated_db):
    _seed_document(isolated_db, document_id="d-A", investigation_id="inv-A")
    _seed_document(isolated_db, document_id="d-B", investigation_id="inv-B")
    client = _client()
    resp = client.get("/documents?investigation_id=inv-A")
    body = resp.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["document_id"] == "d-A"


# ── Limit ──────────────────────────────────────────────────────────


def test_documents_listing_respects_limit(isolated_db):
    for i in range(5):
        _seed_document(isolated_db, document_id=f"d-{i}")
    client = _client()
    resp = client.get("/documents?limit=2")
    body = resp.json()
    assert len(body["documents"]) == 2


# ── Tier validation ──────────────────────────────────────────────


def test_documents_listing_rejects_invalid_tier(isolated_db):
    client = _client()
    resp = client.get("/documents?source_tier=99")
    assert resp.status_code == 422
