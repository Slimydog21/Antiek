"""TipTap ↔ notebook_blocks codec + PUT /notebooks/{id}/content."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.graph.schema import init_database_at_path
from substrate.notebooks.tiptap_codec import compose, decompose


def test_decompose_empty_doc():
    blocks = decompose({"type": "doc", "content": []})
    assert blocks == []


def test_decompose_pure_prose():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]},
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "h"}]},
        ],
    }
    blocks = decompose(doc)
    assert [b.block_type for b in blocks] == ["prose", "prose"]
    assert all(b.ref_id is None for b in blocks)


def test_decompose_substrate_citation_blocks():
    doc = {
        "type": "doc",
        "content": [
            {"type": "claim_card", "attrs": {"claim_id": "c-123", "investigation_id": "i-1"}},
            {"type": "region_embed", "attrs": {"document_id": "d-9", "page": 4}},
            {"type": "note_block", "attrs": {"note_id": "n-5"}},
            {"type": "cross_doc_link", "attrs": {"source_document_id": "d-1", "target_document_id": "d-2"}},
        ],
    }
    blocks = decompose(doc)
    assert [b.block_type for b in blocks] == [
        "claim_card", "region_embed", "note", "cross_doc_link",
    ]
    assert [b.ref_id for b in blocks] == ["c-123", "d-9", "n-5", "d-1"]


def test_round_trip_preserves_doc():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "intro"}]},
            {"type": "claim_card", "attrs": {"claim_id": "c-42", "investigation_id": "i-1"}},
            {"type": "paragraph", "content": [{"type": "text", "text": "outro"}]},
        ],
    }
    blocks = decompose(doc)
    rebuilt = compose([
        {"content_json": b.content_json} for b in blocks
    ])
    assert rebuilt == doc


def test_decompose_rejects_malformed():
    with pytest.raises(ValueError):
        decompose("not an object")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        decompose({"type": "not_doc", "content": []})
    with pytest.raises(ValueError):
        decompose({"type": "doc", "content": "not a list"})


def test_compose_synthesises_placeholder_for_missing_content_json():
    doc = compose([{"content_json": None}])
    assert doc["type"] == "doc"
    assert len(doc["content"]) == 1
    assert doc["content"][0]["type"] == "paragraph"


def test_compose_parses_json_string_content():
    """When DuckDB rehydrates content_json as a string, compose
    accepts it and parses on the way out."""
    import json

    block_content = {"type": "paragraph", "content": [{"type": "text", "text": "x"}]}
    doc = compose([{"content_json": json.dumps(block_content)}])
    assert doc["content"][0] == block_content


# ── API endpoint ─────────────────────────────────────────────────────


def _client():
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _use_temp_graph_db(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "test.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    init_database_at_path(db_path)


def test_put_content_replaces_existing_blocks(tmp_path, monkeypatch):
    """Atomic-replace removes old blocks and inserts the new ones in
    order. The notebook's block list reflects the new content."""
    _use_temp_graph_db(tmp_path, monkeypatch)
    client = _client()

    # Create notebook + seed one block via the existing append endpoint
    r = client.post("/notebooks", json={"title": "T", "investigation_id": None})
    assert r.status_code == 201, r.text
    nb_id = r.json()["notebook_id"]
    r = client.post(
        f"/notebooks/{nb_id}/blocks",
        json={"block_type": "prose", "content": {"text": "old"}},
    )
    assert r.status_code == 201, r.text

    # PUT content with a TipTap doc containing two blocks
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "new"}]},
            {"type": "claim_card", "attrs": {"claim_id": "c-1"}},
        ],
    }
    r = client.put(f"/notebooks/{nb_id}/content", json={"doc": doc})
    assert r.status_code == 200, r.text
    blocks = r.json()["blocks"]
    assert len(blocks) == 2
    assert blocks[0]["block_type"] == "prose"
    assert blocks[1]["block_type"] == "claim_card"
    assert blocks[1]["ref_id"] == "c-1"


def test_put_content_unknown_notebook_404(tmp_path, monkeypatch):
    _use_temp_graph_db(tmp_path, monkeypatch)
    client = _client()
    r = client.put(
        "/notebooks/does-not-exist/content",
        json={"doc": {"type": "doc", "content": []}},
    )
    assert r.status_code == 404


def test_put_content_malformed_doc_422(tmp_path, monkeypatch):
    _use_temp_graph_db(tmp_path, monkeypatch)
    client = _client()
    r = client.post("/notebooks", json={"title": "T"})
    nb_id = r.json()["notebook_id"]
    r = client.put(
        f"/notebooks/{nb_id}/content",
        json={"doc": {"type": "not_a_doc"}},
    )
    assert r.status_code == 422


def test_save_by_doc_creates_bound_notebook_and_decomposes_tiptap(tmp_path, monkeypatch):
    _use_temp_graph_db(tmp_path, monkeypatch)
    client = _client()
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "note"}]},
            {"type": "claim_card", "attrs": {"claim_id": "claim-1"}},
        ],
    }
    r = client.post(
        "/notebooks/by-doc/doc-1/save",
        json={
            "notebook_id": "nb-doc-1",
            "content_json": doc,
            "blocks": [],
            "save_kind": "explicit",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notebook_id"] == "nb-doc-1"
    assert body["document_id"] == "doc-1"
    assert body["content_json"] == doc
    assert [b["block_type"] for b in body["blocks"]] == ["prose", "claim_card"]
    assert body["blocks"][1]["ref_id"] == "claim-1"

    listing = client.get("/notebooks", params={"document_id": "doc-1"}).json()
    assert [nb["notebook_id"] for nb in listing["notebooks"]] == ["nb-doc-1"]


def test_save_by_doc_rejects_cross_document_notebook_reuse(tmp_path, monkeypatch):
    _use_temp_graph_db(tmp_path, monkeypatch)
    client = _client()
    payload = {
        "notebook_id": "nb-shared",
        "content_json": {"type": "doc", "content": []},
        "blocks": [],
        "save_kind": "autosave",
    }
    first = client.post("/notebooks/by-doc/doc-a/save", json=payload)
    assert first.status_code == 200, first.text
    second = client.post("/notebooks/by-doc/doc-b/save", json=payload)
    assert second.status_code == 409
