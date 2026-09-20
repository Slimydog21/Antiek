"""Own Your Mind P0 D1 — provenance explain endpoints.

Covers the three read-only explain surfaces:

- ``GET /claims/{claim_node_id}/explain`` — the claim node + its supporting
  edges + chunk excerpts + documents + chunk tier overrides.
- ``GET /syntheses/{synthesis_id}/explain`` — the same chain via the
  ``synthesis_substrate_manifest`` pins (document / chunk / node / edge).
- ``GET /docs/{document_id}/explain`` — reverse provenance: document →
  chunks → the edges (and their source nodes) that cite those chunks.

The store isolation comes from the suite-wide autouse fixture (tmp
ANTIEK_DUCKDB_PATH + schema template); each test seeds its own graph
through the substrate's sanctioned write funnel (``runtime.db_lock``
``connect_write`` + ``substrate.graph`` insert helpers), then reads the
endpoints through the FastAPI TestClient. Zero mutation endpoints — the
tests assert 404 (never store creation) for missing ids.
"""

from __future__ import annotations

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
    insert_edge,
    insert_node,
)

_LONG_CHUNK_TEXT = (
    "The quick brown fox jumps over the lazy dog. " * 30
)  # 540 chars — exercises the 500-char excerpt cap


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
def seeded_graph(tmp_path, monkeypatch):
    """Seed one document + chunk + claim/entity nodes + a supporting edge
    + a chunk tier override + one synthesis with all four manifest pin
    kinds. Returns the ids the tests assert against."""
    db = default_db_path()
    init_database_at_path(db)
    with connect_write(db, purpose="test-seed") as con:
        insert_document(
            con,
            document_id="doc-1",
            source_tier=1,
            document_type="white_paper",
            title="Provenance Paper",
            author="Ada Lovelace",
        )
        insert_chunk(
            con,
            document_id="doc-1",
            chunk_index=0,
            text=_LONG_CHUNK_TEXT,
            section_path="§2.1 Methods",
            chunk_id="chunk-1",
        )
        insert_node(
            con,
            canonical_label="Quantum claims coherence",
            node_type="claim",
            graph_scope="depth",
            investigation_id="inv-1",
            node_id="claim-1",
        )
        insert_node(
            con,
            canonical_label="Coherence",
            node_type="mechanism",
            graph_scope="depth",
            investigation_id="inv-1",
            node_id="ent-1",
        )
        insert_edge(
            con,
            source_node_id="claim-1",
            target_node_id="ent-1",
            relation="asserts",
            source_tier=1,
            extraction_confidence=0.92,
            graph_scope="depth",
            investigation_id="inv-1",
            chunk_id="chunk-1",
            source_document_id="doc-1",
        )
        con.execute(
            "INSERT INTO chunk_tier_overrides "
            "(chunk_id, original_tier, override_tier, reason, set_by) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                "chunk-1",
                2,
                1,
                "operator re-tiered after source verification",
                "operator",
            ],
        )
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, "
            "target_question, synthesis_timestamp, status, "
            "implicit_recommendation) VALUES (?, ?, ?, "
            "CURRENT_TIMESTAMP, 'passed', 'proceed')",
            ["syn-1", "inv-1", "Does coherence hold?"],
        )
        edge_id = con.execute("SELECT edge_id FROM edges LIMIT 1").fetchone()[0]
        con.execute(
            "INSERT INTO synthesis_substrate_manifest "
            "(synthesis_id, entity_kind, entity_id) VALUES "
            "('syn-1', 'document', 'doc-1'), ('syn-1', 'chunk', 'chunk-1'), "
            "('syn-1', 'node', 'claim-1'), ('syn-1', 'edge', ?)",
            [edge_id],
        )
    return {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "claim_node_id": "claim-1",
        "entity_node_id": "ent-1",
        "edge_id": edge_id,
        "synthesis_id": "syn-1",
        "db": db,
    }


# ── GET /claims/{claim_node_id}/explain ────────────────────────────────────


def test_claim_explain_returns_full_chain(client, seeded_graph):
    r = client.get(f"/claims/{seeded_graph['claim_node_id']}/explain")
    assert r.status_code == 200, r.text
    body = r.json()
    node = body["claim_node"]
    assert node["node_id"] == "claim-1"
    assert node["canonical_label"] == "Quantum claims coherence"
    assert node["node_type"] == "claim"
    assert node["graph_scope"] == "depth"
    assert node["created_at"]

    assert len(body["supporting_edges"]) == 1
    edge = body["supporting_edges"][0]
    assert edge["relation"] == "asserts"
    assert edge["chunk_id"] == "chunk-1"
    assert edge["document_id"] == "doc-1"
    assert edge["source_tier"] == 1
    assert edge["extraction_confidence"] == pytest.approx(0.92, abs=1e-6)

    assert len(body["chunks"]) == 1
    chunk = body["chunks"][0]
    assert chunk["chunk_id"] == "chunk-1"
    assert chunk["section_path"] == "§2.1 Methods"
    assert chunk["document_id"] == "doc-1"
    # Excerpt cap: 500 chars, never the full body.
    assert len(chunk["text"]) == 500
    assert chunk["text"] == _LONG_CHUNK_TEXT[:500]

    assert len(body["documents"]) == 1
    doc = body["documents"][0]
    assert doc["document_id"] == "doc-1"
    assert doc["title"] == "Provenance Paper"
    assert doc["author"] == "Ada Lovelace"
    assert doc["source_tier"] == 1
    assert doc["acquired_at"]

    assert len(body["chunk_tier_overrides"]) == 1
    override = body["chunk_tier_overrides"][0]
    assert override["set_by"] == "operator"
    assert override["reason"] == "operator re-tiered after source verification"
    assert override["set_at"]
    assert override["chunk_id"] == "chunk-1"
    assert override["original_tier"] == 2
    assert override["override_tier"] == 1


def test_claim_explain_404_for_unknown_node(client):
    r = client.get("/claims/does-not-exist/explain")
    assert r.status_code == 404


# ── GET /syntheses/{synthesis_id}/explain ──────────────────────────────────


def test_synthesis_explain_resolves_manifest_pins(client, seeded_graph):
    r = client.get(f"/syntheses/{seeded_graph['synthesis_id']}/explain")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["synthesis_id"] == "syn-1"
    pins = body["pins"]
    # Every entity_kind the manifest CHECK allows is present as a key.
    assert set(pins) == {"document", "chunk", "node", "edge"}

    assert len(pins["document"]) == 1
    assert pins["document"][0]["document"]["title"] == "Provenance Paper"

    assert len(pins["chunk"]) == 1
    assert pins["chunk"][0]["chunk"]["chunk_id"] == "chunk-1"
    assert pins["chunk"][0]["documents"][0]["document_id"] == "doc-1"

    assert len(pins["node"]) == 1
    node_pin = pins["node"][0]
    assert node_pin["claim_node"]["canonical_label"] == "Quantum claims coherence"
    assert node_pin["supporting_edges"][0]["relation"] == "asserts"
    assert node_pin["chunks"][0]["chunk_id"] == "chunk-1"

    assert len(pins["edge"]) == 1
    edge_pin = pins["edge"][0]
    assert edge_pin["edge"]["edge_id"] == seeded_graph["edge_id"]
    assert edge_pin["chunks"][0]["chunk_id"] == "chunk-1"
    assert edge_pin["documents"][0]["document_id"] == "doc-1"


def test_synthesis_explain_404_for_unknown_synthesis(client):
    r = client.get("/syntheses/does-not-exist/explain")
    assert r.status_code == 404


def test_synthesis_explain_with_zero_pins_is_honest_empty(client, seeded_graph):
    """A synthesis with no manifest rows returns an empty pins map, never a
    fabricated chain."""
    from runtime.db_lock import connect_write

    db = seeded_graph["db"]
    with connect_write(db, purpose="test-seed") as con:
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, "
            "target_question, synthesis_timestamp, status, "
            "implicit_recommendation) VALUES ('syn-empty', 'inv-2', "
            "'Unpinned question?', CURRENT_TIMESTAMP, 'draft', 'undetermined')"
        )
    r = client.get("/syntheses/syn-empty/explain")
    assert r.status_code == 200
    body = r.json()
    assert body["synthesis_id"] == "syn-empty"
    assert all(pins == [] for pins in body["pins"].values())


# ── GET /docs/{document_id}/explain ────────────────────────────────────────


def test_document_explain_reverse_provenance(client, seeded_graph):
    r = client.get(f"/docs/{seeded_graph['document_id']}/explain")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["title"] == "Provenance Paper"
    assert body["document"]["author"] == "Ada Lovelace"
    assert body["document"]["source_tier"] == 1
    assert body["document"]["acquired_at"]

    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["chunk_id"] == "chunk-1"
    assert body["chunks"][0]["section_path"] == "§2.1 Methods"
    assert len(body["chunks"][0]["text"]) == 500

    assert len(body["citing_edges"]) == 1
    citing = body["citing_edges"][0]
    assert citing["source_node_id"] == "claim-1"
    assert citing["relation"] == "asserts"
    assert citing["chunk_id"] == "chunk-1"
    assert citing["source_tier"] == 1
    assert citing["extraction_confidence"] == pytest.approx(0.92, abs=1e-6)

    assert len(body["citing_nodes"]) == 1
    assert body["citing_nodes"][0]["canonical_label"] == "Quantum claims coherence"
    assert body["citing_nodes"][0]["node_type"] == "claim"

    assert len(body["chunk_tier_overrides"]) == 1
    assert body["chunk_tier_overrides"][0]["set_by"] == "operator"


def test_document_explain_404_for_unknown_document(client):
    r = client.get("/docs/does-not-exist/explain")
    assert r.status_code == 404


# ── Read-only discipline ───────────────────────────────────────────────────


def test_explain_404_never_creates_a_store(tmp_path, monkeypatch, client):
    """A GET against a missing store must 404, never initialize the DB
    (the read-only P0 principle: no write side effects on read surfaces)."""
    missing = str(tmp_path / "never" / "created.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", missing)
    assert client.get("/claims/x/explain").status_code == 404
    assert client.get("/syntheses/x/explain").status_code == 404
    assert client.get("/docs/x/explain").status_code == 404
    assert not os.path.exists(missing)
