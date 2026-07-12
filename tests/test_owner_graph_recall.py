"""Owner-native graph read routing, recall, and non-disclosure proof."""

from __future__ import annotations

import contextlib
import importlib
from pathlib import Path

from processing.embedding import HashEmbedding
from runtime.db_lock import connect_write
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.graph.personal_recall import (
    get_owner_node,
    recall_owner_nodes,
    recall_personal_nodes,
)
from substrate.graph.schema import init_database
from substrate.graph_per_user.runtime import (
    existing_owner_graph_db_path,
    owner_graph_db_path,
    owner_graph_readiness,
)


def _seed_owner(owner: str, text: str, *, question: bool = False) -> str:
    path = owner_graph_db_path(owner)
    con = connect_write(path, purpose="test_owner_recall_seed")
    try:
        init_database(con)
        promote = promote_question if question else promote_insight
        return promote(
            text=text,
            investigation_id=f"inv-{owner}",
            embedding_provider=HashEmbedding(),
            con=con,
            emit_events=False,
        )
    finally:
        con.close()


def test_unmaterialized_read_is_empty_and_side_effect_free(monkeypatch, tmp_path):
    root = tmp_path / "owners"
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(root))
    expected = Path(owner_graph_db_path("alice", create_parent=False))
    assert existing_owner_graph_db_path("alice") is None
    assert recall_owner_nodes("alice", "leak canary", model=HashEmbedding()) == []
    assert not expected.exists()
    assert not root.exists()
    ready = owner_graph_readiness("alice")
    assert ready["owner_graph_scope"] == "unmaterialized"
    assert ready["materialized"] is False
    assert len(str(ready["graph_path_sha256"])) == 64
    assert not root.exists()


def test_identical_owner_queries_cannot_cross_graphs(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    alice_id = _seed_owner("alice", "Photonic interconnects reduce mesh latency")
    bob_id = _seed_owner("bob", "Protein folding reveals catalytic structure")

    alice = recall_owner_nodes(
        "alice", "photonic mesh latency", model=HashEmbedding(), top_k=4
    )
    bob = recall_owner_nodes(
        "bob", "photonic mesh latency", model=HashEmbedding(), top_k=4
    )
    assert [row["note_id"] for row in alice] == [alice_id]
    assert all(row["note_id"] != alice_id for row in bob)
    assert all("Photonic" not in row["note_text"] for row in bob)
    assert get_owner_node("alice", alice_id)["label"].startswith("Photonic")  # type: ignore[index]
    assert get_owner_node("bob", alice_id) is None
    assert bob_id != alice_id


def test_semantic_and_lexical_hits_dedupe_by_node(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    node_id = _seed_owner("alice", "Recursive questions sharpen research synthesis")
    hits = recall_owner_nodes(
        "alice", "recursive research questions", model=HashEmbedding(), top_k=8
    )
    assert [hit["note_id"] for hit in hits].count(node_id) == 1
    assert hits[0]["knowledge_scope"] == "personal_owner"
    assert hits[0]["source_event_ids"] == []
    assert hits[0]["source_node_ids"] == [node_id]


def test_incompatible_node_embedding_uses_only_lexical_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    path = owner_graph_db_path("alice")
    con = connect_write(path, purpose="test_incompatible_owner_vector")
    try:
        init_database(con)
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, embedding, graph_scope, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                "insight-incompatible",
                "Quasar spectroscopy calibration",
                "insight",
                [1.0, 0.0],
                "depth",
                '{"embedding_fingerprint":"different-space"}',
            ],
        )
    finally:
        con.close()
    hits = recall_personal_nodes(
        path, "quasar calibration", model=HashEmbedding(), top_k=4
    )
    assert [hit["note_id"] for hit in hits] == ["insight-incompatible"]
    assert hits[0]["confidence"] <= 0.79


def test_unrelated_semantic_nodes_do_not_spend_prompt_context(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    _seed_owner("alice", "volcanic basalt crystallization")
    hits = recall_owner_nodes(
        "alice", "quantum photonic routing", model=HashEmbedding(), top_k=8
    )
    assert hits == []


def test_thought_partner_fuses_public_corpus_with_only_request_owner_memory(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    from processing.embedding import _reset_default_provider

    _reset_default_provider()
    alice_id = _seed_owner("alice", "Photonic memory belongs only to Alice")
    _seed_owner("bob", "Photonic memory belongs only to Bob")

    search_mod = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", HashEmbedding)
    monkeypatch.setattr(
        search_mod,
        "search",
        lambda *_args, **_kwargs: {
            "results": [
                {
                    "chunk_id": "public-chunk",
                    "chunk_text": "Shared public photonics evidence",
                    "document_id": "public-doc",
                    "similarity": 0.66,
                }
            ],
            "node_matches": [],
        },
    )

    @contextlib.contextmanager
    def _canonical_read(_path):
        yield object()

    monkeypatch.setattr("runtime.db_lock.connect_read", _canonical_read)
    monkeypatch.setattr("substrate.graph.default_db_path", lambda: "/canonical")

    from interfaces.research.api.app import _retrieve_thought_partner_context

    alice = _retrieve_thought_partner_context(
        "photonic memory", "attribution_eligible", owner_id="alice", top_k=8
    )
    bob = _retrieve_thought_partner_context(
        "photonic memory", "attribution_eligible", owner_id="bob", top_k=8
    )
    assert any(row["note_id"] == "public-chunk" for row in alice)
    assert any(row["note_id"] == alice_id for row in alice)
    assert all(row["note_id"] != alice_id for row in bob)
    assert {row["knowledge_scope"] for row in alice} == {
        "canonical_corpus",
        "personal_owner",
    }


def test_context_picker_resolves_personal_insight_without_canonical_fallback(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    alice_id = _seed_owner("alice", "Alice explicit private insight")
    from interfaces.research.api.app import ContextItem, _compose_context

    monkeypatch.setattr("substrate.graph.default_db_path", lambda: "/absent-canonical")
    response = _compose_context(
        [ContextItem(kind="insight", id=alice_id)], owner=False, owner_id="alice"
    )
    assert "Alice explicit private insight" in response.system_context
    assert response.missing == []

    foreign = _compose_context(
        [ContextItem(kind="insight", id=alice_id)], owner=False, owner_id="bob"
    )
    assert foreign.system_context == ""
    assert foreign.missing == [alice_id]


def test_thought_partner_personal_recall_survives_absent_canonical_graph(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    from processing.embedding import _reset_default_provider

    _reset_default_provider()
    alice_id = _seed_owner("alice", "Private catalyst memory survives alone")

    def _absent_canonical(_path):
        raise FileNotFoundError("canonical graph absent")

    monkeypatch.setattr("runtime.db_lock.connect_read", _absent_canonical)
    from interfaces.research.api.app import _retrieve_thought_partner_context

    notes = _retrieve_thought_partner_context(
        "private catalyst memory",
        "attribution_eligible",
        owner_id="alice",
        top_k=4,
    )
    assert [row["note_id"] for row in notes] == [alice_id]
    assert notes[0]["knowledge_scope"] == "personal_owner"


def test_corrupt_personal_graph_does_not_suppress_public_recall(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    corrupt = Path(owner_graph_db_path("alice"))
    corrupt.write_text("not duckdb", encoding="utf-8")

    search_mod = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", HashEmbedding)
    monkeypatch.setattr(
        search_mod,
        "search",
        lambda *_args, **_kwargs: {
            "results": [{
                "chunk_id": "public-only",
                "chunk_text": "Public context remains available",
                "document_id": "public-doc",
                "similarity": 0.5,
            }],
            "node_matches": [],
        },
    )

    @contextlib.contextmanager
    def _canonical_read(_path):
        yield object()

    monkeypatch.setattr("runtime.db_lock.connect_read", _canonical_read)
    from interfaces.research.api.app import _retrieve_thought_partner_context

    notes = _retrieve_thought_partner_context(
        "public context", "attribution_eligible", owner_id="alice"
    )
    assert [row["note_id"] for row in notes] == ["public-only"]
