from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized


def _client(monkeypatch, tmp_path) -> tuple[TestClient, str]:
    db = str(tmp_path / "graph-explorer.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    ensure_initialized(db)
    with connect_write(db, purpose="test:seed-graph-explorer") as con:
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, author, source_tier, document_type, content_class) "
            "VALUES ('doc-public', 'Public paper', 'A. Researcher', 1, 'paper', 'public_domain'), "
            "('doc-private', 'Private book', 'B. Reader', 4, 'book', 'personal_reading')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, section_path, text) "
            "VALUES ('chunk-public', 'doc-public', 0, 'Results', 'Evidence supports graph reuse.'), "
            "('chunk-private', 'doc-private', 0, 'Chapter 2', 'Private source passage.')"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, degree_cached) "
            "VALUES ('insight-reuse', 'Cited reuse compounds knowledge', 'insight', 'depth', 3), "
            "('question-route', 'Which route should be chased next?', 'question', 'depth', 1), "
            "('mechanism-memory', 'Recursive memory', 'mechanism', 'cross_domain', 2)"
        )
        con.execute(
            "INSERT INTO edges "
            "(edge_id, source_node_id, target_node_id, relation, chunk_id, "
            "source_document_id, source_tier, extraction_confidence, graph_scope, "
            "investigation_id) VALUES "
            "('edge-public', 'insight-reuse', 'mechanism-memory', 'explains', "
            "'chunk-public', 'doc-public', 1, 0.94, 'depth', 'inv-1'), "
            "('edge-private', 'question-route', 'mechanism-memory', 'challenges', "
            "'chunk-private', 'doc-private', 4, 0.71, 'depth', 'inv-2')"
        )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app), db


def test_graph_explorer_returns_exact_nodes_edges_and_evidence(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    response = client.get(
        "/graph/explore",
        params={"q": "reuse", "node_type": "insight", "limit": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["read_only"] is True
    assert body["access_policy"] == "operator_only"
    assert body["view_format"] == "html"
    assert [node["node_id"] for node in body["nodes"]] == ["insight-reuse"]
    assert body["edges"][0]["edge_id"] == "edge-public"
    evidence = body["edges"][0]["evidence"]
    assert evidence["chunk_id"] == "chunk-public"
    assert evidence["chunk_text"] == "Evidence supports graph reuse."
    assert evidence["source_document_id"] == "doc-public"
    assert evidence["servable"] is True

    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == 3
        assert con.execute("SELECT count(*) FROM edges").fetchone()[0] == 2


def test_graph_explorer_filters_investigation_and_marks_restricted_evidence(
    monkeypatch, tmp_path
):
    client, _ = _client(monkeypatch, tmp_path)
    response = client.get(
        "/graph/explore",
        params={"investigation_id": "inv-2", "node_type": "question"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [node["node_id"] for node in body["nodes"]] == ["question-route"]
    assert [edge["edge_id"] for edge in body["edges"]] == ["edge-private"]
    evidence = body["edges"][0]["evidence"]
    assert evidence["content_class"] == "personal_reading"
    assert evidence["servable"] is False
    assert evidence["chunk_text"] == "Private source passage."


def test_graph_explorer_resolves_an_exact_node_id_without_label_search(
    monkeypatch, tmp_path
):
    client, _ = _client(monkeypatch, tmp_path)
    response = client.get(
        "/graph/explore",
        params={"node_id": "question-route"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == ""
    assert body["node_id"] == "question-route"
    assert [node["node_id"] for node in body["nodes"]] == ["question-route"]
    assert [edge["edge_id"] for edge in body["edges"]] == ["edge-private"]


def test_graph_explorer_rejects_blank_exact_node_id(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    response = client.get("/graph/explore", params={"node_id": "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == "node_id must not be blank"


def test_graph_explorer_uses_chunk_rights_bounds_preview_and_aligns_filters(
    monkeypatch, tmp_path
):
    client, db = _client(monkeypatch, tmp_path)
    with connect_write(db, purpose="test:harden-graph-explorer") as con:
        con.execute(
            "UPDATE chunks SET text = ? WHERE chunk_id = 'chunk-private'",
            ["p" * 1_300],
        )
        # Deliberately inconsistent legacy provenance: the chunk is authoritative
        # for its own text and rights; the edge's document pointer must not relabel it.
        con.execute(
            "UPDATE edges SET source_document_id = 'doc-public' "
            "WHERE edge_id = 'edge-private'"
        )

    response = client.get(
        "/graph/explore",
        params={
            "investigation_id": "inv-2",
            "graph_scope": "cross_domain",
            "node_type": "mechanism",
        },
    )
    assert response.status_code == 200
    assert response.json()["nodes"] == []

    evidence = client.get(
        "/graph/explore", params={"investigation_id": "inv-2"}
    ).json()["edges"][0]["evidence"]
    assert evidence["source_document_id"] == "doc-private"
    assert evidence["content_class"] == "personal_reading"
    assert len(evidence["chunk_text"]) == 1_200
    assert evidence["chunk_text"].endswith("…")


def test_graph_explorer_empty_state_and_bounds(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    empty = client.get("/graph/explore", params={"q": "no such node"})
    assert empty.status_code == 200
    assert empty.json()["nodes"] == []
    assert empty.json()["edges"] == []
    assert client.get("/graph/explore", params={"limit": 201}).status_code == 422
    assert client.get("/graph/explore", params={"q": "x" * 201}).status_code == 422
    assert (
        client.get("/graph/explore", params={"node_id": "x" * 257}).status_code
        == 422
    )
