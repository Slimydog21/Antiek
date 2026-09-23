"""Citation resolution and visibility for the in-process MCP handler."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.antiek_memory.__main__ import _make_handlers


@pytest.fixture()
def cite_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "memory.duckdb")
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="test_cite_source_seed") as con:
        for document_id, content_class, owner, ip_holder_id in (
            ("doc-pd", "public_domain", "user-a", "pub-2"),
            ("doc-r", "restricted_pending_opt_in", "user-a", "pub-1"),
            ("doc-null", None, "user-a", None),
            ("doc-b", "user_owned", "user-b", None),
        ):
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, owner_user_id, content_class, ip_holder_id) "
                "VALUES (?, ?, 1, 'article', ?, ?, ?)",
                [document_id, f"Title {document_id}", owner, content_class, ip_holder_id],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text) VALUES (?, ?, 0, 'Section 1', 'source text')",
                [document_id.replace("doc-", "chunk-"), document_id],
            )
        for node_id, label, metadata in (
            ("claim-pd", "Public claim", {"chunk_id": "chunk-pd"}),
            ("claim-r", "Restricted claim", {"chunk_id": "chunk-r"}),
            ("claim-edge", "Edge claim", None),
            ("claim-document", "Document claim", None),
        ):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, "
                "graph_scope, metadata) VALUES (?, ?, 'claim', 'depth', ?)",
                [node_id, label, json.dumps(metadata) if metadata else None],
            )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('entity-pd', 'Public entity', 'entity', 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, "
            "relation, chunk_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('edge-pd', 'claim-edge', 'entity-pd', 'supports', "
            "'chunk-pd', 1, 0.9, 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, "
            "relation, source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('edge-document', 'claim-document', 'entity-pd', 'supports', "
            "'doc-pd', 1, 0.9, 'depth')"
        )
        notebooks: tuple[tuple[str, str, str, str | None, str], ...] = (
            ("nb-pub", "Public notebook", "user_public_contribution", "doc-pd", "note-pub"),
            ("nb-priv", "Private notebook", "user_owned", None, "note-priv"),
            # A public note that cites another user's private document.
            ("nb-pub-on-priv", "Public on private", "user_public_contribution",
             "doc-b", "note-pub-on-priv"),
        )
        for notebook_id, title, content_class, notebook_document, block_id in notebooks:
            con.execute(
                "INSERT INTO notebooks (notebook_id, title, owner_user_id, "
                "content_class, document_id) VALUES (?, ?, 'user-b', ?, ?)",
                [notebook_id, title, content_class, notebook_document],
            )
            con.execute(
                "INSERT INTO notebook_blocks (block_id, notebook_id, block_index, "
                "block_type, content_json) VALUES (?, ?, 0, 'note', '{}')",
                [block_id, notebook_id],
            )
    handlers, _ = _make_handlers(db_path)
    return handlers["cite_source"]


def _body(result: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(result.content[0]["text"])
    return body


def test_chunk_and_document_citations(cite_source: Any) -> None:
    public = cite_source({"id": "chunk-pd"})
    assert public.is_error is False
    assert _body(public) == {
        "id_type": "chunk", "id": "chunk-pd", "chunk_id": "chunk-pd",
        "document_id": "doc-pd", "title": "Title doc-pd", "source_tier": 1,
        "author": None, "section_path": "Section 1", "ip_holder_id": "pub-2",
        "servable": True, "servability": None,
    }

    restricted = cite_source({"id": "chunk-r"})
    assert restricted.is_error is False
    assert _body(restricted)["ip_holder_id"] is None
    assert _body(restricted)["servable"] is False
    assert _body(restricted)["servability"] == "restricted"

    restricted_document = cite_source({"id": "doc-r", "id_type": "document"})
    assert restricted_document.is_error is False
    assert _body(restricted_document)["document_id"] == "doc-r"
    assert _body(restricted_document)["chunk_id"] is None
    assert _body(restricted_document)["ip_holder_id"] is None

    public_document = cite_source({"id": "doc-pd", "id_type": "document"})
    assert public_document.is_error is False
    assert _body(public_document)["ip_holder_id"] == "pub-2"
    assert _body(public_document)["section_path"] is None


def test_claim_citations_use_canonical_node_gate(cite_source: Any) -> None:
    claim = cite_source({"id": "claim-pd", "id_type": "claim"})
    assert claim.is_error is False
    assert _body(claim)["claim_id"] == "claim-pd"
    assert _body(claim)["claim_text"] == "Public claim"
    assert _body(claim)["chunk_id"] == "chunk-pd"
    assert _body(claim)["document_id"] == "doc-pd"

    edge_claim = cite_source({"id": "claim-edge", "id_type": "claim"})
    assert edge_claim.is_error is False
    assert _body(edge_claim)["chunk_id"] == "chunk-pd"

    document_claim = cite_source({"id": "claim-document", "id_type": "claim"})
    assert document_claim.is_error is False
    assert _body(document_claim)["document_id"] == "doc-pd"
    assert _body(document_claim)["chunk_id"] is None

    restricted = cite_source({"id": "claim-r", "id_type": "claim"})
    assert restricted.is_error is True
    assert _body(restricted) == {"error": "not found"}


def test_note_visibility_and_document_metadata(cite_source: Any) -> None:
    public = cite_source({"id": "note-pub", "id_type": "note"})
    assert public.is_error is False
    assert _body(public)["note_id"] == "note-pub"
    assert _body(public)["notebook_id"] == "nb-pub"
    assert _body(public)["notebook_title"] == "Public notebook"
    assert _body(public)["document_id"] == "doc-pd"

    private = cite_source({"id": "note-priv", "id_type": "note"})
    assert private.is_error is True
    assert _body(private) == {"error": "not found"}
    owned = cite_source(
        {"id": "note-priv", "id_type": "note"}, auth_context={"user_id": "user-b"}
    )
    assert owned.is_error is False
    assert _body(owned)["notebook_id"] == "nb-priv"
    assert _body(owned)["document_id"] is None

    # The note is public, the document it points at is not: the note still
    # resolves, the private document's identity and metadata do not leave.
    on_private = cite_source({"id": "note-pub-on-priv", "id_type": "note"})
    assert on_private.is_error is False
    body = _body(on_private)
    assert body["notebook_id"] == "nb-pub-on-priv"
    assert body["document_id"] is None
    assert body["title"] is None


def test_document_visibility_and_validation(cite_source: Any) -> None:
    missing = cite_source({"id": "missing"})
    private = cite_source({"id": "chunk-b"})
    assert private.is_error is True
    assert private.content == missing.content
    private_document = cite_source({"id": "doc-b", "id_type": "document"})
    assert private_document.is_error is True
    assert private_document.content == missing.content

    owned = cite_source({"id": "chunk-b"}, auth_context={"user_id": "user-b"})
    assert owned.is_error is False
    assert _body(owned)["document_id"] == "doc-b"

    legacy = cite_source({"id": "chunk-null"})
    assert legacy.is_error is False
    assert _body(legacy)["document_id"] == "doc-null"

    for args in ({"id": "chunk-pd", "id_type": "banana"}, {"id": "  "}):
        result = cite_source(args)
        assert result.is_error is True
        assert "error" in _body(result)
