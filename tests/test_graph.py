"""Tests for substrate/graph/.

Three concerns, four test classes:

1. Schema — init_database creates the expected tables + indexes;
   re-running is idempotent; CHECK constraints reject bad values.
2. Ops — insert helpers commit rows AND emit typed events. Content-
   addressed ids are stable across calls.
3. Search — cosine similarity ranks chunks correctly; tier filter
   excludes higher-tier-number rows; with_edges joins surface
   attached edges + nodes.
4. Traverse — all four algorithms produce expected paths on a tiny
   hand-built graph; resolve_node finds by id / label / fuzzy.

Tests use a per-test tmp DuckDB file (NOT in-memory — db_lock requires
a real path for its sidecar flock). Each test gets a fresh
``init_database_at_path`` so there's zero cross-test state.
"""

from __future__ import annotations

import os
import sys

import duckdb
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from processing.embedding import embedding_provider_fingerprint  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.graph import (  # noqa: E402
    SCHEMA_TABLES,
    bfs_semantic_stop,
    content_addressed_id,
    cosine_similarity_sql,
    dfs_with_depth,
    init_database,
    init_database_at_path,
    insert_chunk,
    insert_document,
    insert_edge,
    insert_node,
    list_tables,
    resolve_node,
    search,
    search_nodes_by_label,
    shortest_path,
    top_n_paths,
    traverse,
)
from substrate.schemas import (  # noqa: E402
    Event,
    GraphEdgeInsertedPayload,
    GraphNodeInsertedPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "graph.duckdb")
    init_database_at_path(p)
    return p


class _StubEmbeddingModel:
    """Deterministic embedding stub. Maps each word to a fixed
    contribution vector so two strings with overlapping words score
    high on cosine similarity. dim=8 chosen so the SQL casts work
    cheaply."""

    dimension = 8

    def encode(self, text: str) -> list[float]:
        # Hash each lowercase word into a fixed dim slot.
        vec = [0.0] * self.dimension
        for word in text.lower().split():
            slot = sum(ord(c) for c in word) % self.dimension
            vec[slot] += 1.0
        # Avoid zero vectors (DuckDB cosine sim divides by zero).
        if not any(vec):
            vec[0] = 1.0
        return vec


class _OtherStubEmbeddingModel(_StubEmbeddingModel):
    pass


# ---------------------------------------------------------------------------
# 1. Schema
# ---------------------------------------------------------------------------


def test_init_database_creates_all_four_tables(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = list_tables(con)
        for expected in SCHEMA_TABLES:
            assert expected in tables, f"missing table {expected!r}; got {tables}"
    finally:
        con.close()


def test_init_database_is_idempotent(db_path):
    """Re-running init must not raise. CREATE IF NOT EXISTS handles
    every table + index."""
    init_database_at_path(db_path)
    init_database_at_path(db_path)
    init_database_at_path(db_path)


def test_init_database_rejects_non_locked_connection(tmp_path):
    """The only-writer invariant: init_database must run under
    runtime.db_lock.connect_write."""
    raw_con = duckdb.connect(str(tmp_path / "raw.duckdb"))
    with pytest.raises(TypeError, match="LockedConnection"):
        init_database(raw_con)
    raw_con.close()


def test_source_tier_check_constraint_rejects_out_of_range(db_path):
    con = connect_write(db_path, purpose="test")
    try:
        with pytest.raises(duckdb.Error):
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type) "
                "VALUES (?, ?, ?)",
                ["doc-bad", 7, "blog_post"],  # tier 7 violates BETWEEN 1 AND 5
            )
    finally:
        con.close()


def test_insert_chunk_records_embedding_metadata_when_provider_supplied(db_path):
    model = _StubEmbeddingModel()
    con = connect_write(db_path, purpose="test")
    try:
        insert_document(
            con,
            document_id="d-embed-meta",
            source_tier=1,
            document_type="white_paper",
        )
        chunk_id = insert_chunk(
            con,
            document_id="d-embed-meta",
            chunk_index=0,
            text="metadata pinned vector",
            embedding=model.encode("metadata pinned vector"),
            embedding_provider=model,
        )
        row = con.execute(
            "SELECT chunk_id, provider, model_name, dimension, fingerprint "
            "FROM embeddings_meta WHERE chunk_id = ?",
            [chunk_id],
        ).fetchone()
    finally:
        con.close()

    assert row == (
        chunk_id,
        "test_graph._StubEmbeddingModel",
        "_StubEmbeddingModel-dim-8",
        8,
        embedding_provider_fingerprint(model),
    )


def test_node_type_check_constraint_rejects_unknown(db_path):
    con = connect_write(db_path, purpose="test")
    try:
        with pytest.raises(duckdb.Error):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, ?, ?)",
                ["n-bad", "X", "not_a_type", "cross_domain"],
            )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 2. Ops
# ---------------------------------------------------------------------------


def test_content_addressed_id_is_stable_and_unique():
    """Same input → same id; different inputs → different ids."""
    a1 = content_addressed_id("node", "PsiQuantum")
    a2 = content_addressed_id("node", "PsiQuantum")
    b = content_addressed_id("node", "Different")
    assert a1 == a2
    assert a1 != b
    assert a1.startswith("node-")


def test_insert_document_round_trips(db_path):
    con = connect_write(db_path, purpose="test")
    try:
        insert_document(
            con,
            document_id="doc-1",
            source_tier=2,
            document_type="peer_reviewed_paper",
            title="X causes Y",
        )
    finally:
        con.close()

    rcon = connect_read(db_path)
    try:
        row = rcon.execute(
            "SELECT document_id, source_tier, document_type, title FROM documents"
        ).fetchone()
        assert row == ("doc-1", 2, "peer_reviewed_paper", "X causes Y")
    finally:
        rcon.close()


def test_insert_node_emits_typed_event(db_path):
    con = connect_write(db_path, purpose="test")
    try:
        nid = insert_node(
            con,
            canonical_label="PsiQuantum",
            node_type="organization",
            graph_scope="cross_domain",
            investigation_id="inv-1",
            metadata={"sector": "quantum"},
        )
    finally:
        con.close()

    rows = trajectory("inv-1")
    assert len(rows) == 1
    event = Event.model_validate(rows[0])
    assert event.action_type == "graph.node.inserted"
    assert isinstance(event.payload, GraphNodeInsertedPayload)
    p = event.payload
    assert p.node_id == nid
    assert p.canonical_label == "PsiQuantum"
    assert p.node_type == "organization"
    assert p.graph_scope == "cross_domain"
    assert p.has_embedding is False
    assert event.role == "connector"


def test_insert_helpers_can_collect_payloads_without_direct_emission(db_path):
    payloads = []
    con = connect_write(db_path, purpose="test/event-sink")
    try:
        src = insert_node(
            con, canonical_label="A", node_type="entity",
            graph_scope="depth", investigation_id="inv-sink",
            event_sink=payloads.append,
        )
        tgt = insert_node(
            con, canonical_label="B", node_type="entity",
            graph_scope="depth", investigation_id="inv-sink",
            event_sink=payloads.append,
        )
        insert_edge(
            con, source_node_id=src, target_node_id=tgt, relation="depends_on",
            source_tier=2, extraction_confidence=0.8, graph_scope="depth",
            investigation_id="inv-sink", event_sink=payloads.append,
        )
    finally:
        con.close()

    assert [type(payload) for payload in payloads] == [
        GraphNodeInsertedPayload,
        GraphNodeInsertedPayload,
        GraphEdgeInsertedPayload,
    ]
    assert trajectory("inv-sink") == []


def test_insert_edge_emits_typed_event(db_path):
    con = connect_write(db_path, purpose="test")
    try:
        # Need two nodes first.
        src = insert_node(
            con, canonical_label="A", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-edge",
        )
        tgt = insert_node(
            con, canonical_label="B", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-edge",
        )
        eid = insert_edge(
            con,
            source_node_id=src, target_node_id=tgt, relation="depends_on",
            source_tier=2, extraction_confidence=0.85,
            graph_scope="cross_domain", investigation_id="inv-edge",
        )
    finally:
        con.close()

    edge_events = [
        Event.model_validate(r)
        for r in trajectory("inv-edge")
        if r["action_type"] == "graph.edge.inserted"
    ]
    assert len(edge_events) == 1
    p = edge_events[0].payload
    assert isinstance(p, GraphEdgeInsertedPayload)
    assert p.edge_id == eid
    assert p.source_node_id == src
    assert p.target_node_id == tgt
    assert p.relation == "depends_on"
    assert p.source_tier == 2
    assert p.extraction_confidence == pytest.approx(0.85)
    assert p.graph_scope == "cross_domain"


def test_insert_edge_rejects_invalid_confidence(db_path):
    """The payload's Field(ge=0, le=1) rejects bad values BEFORE the DB
    write succeeds — defense in depth with the DB CHECK constraint."""
    con = connect_write(db_path, purpose="test")
    try:
        n = insert_node(
            con, canonical_label="A", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-bad",
        )
        with pytest.raises(duckdb.Error):
            insert_edge(
                con, source_node_id=n, target_node_id=n,
                relation="self", source_tier=2,
                extraction_confidence=1.5,  # > 1.0
                graph_scope="cross_domain", investigation_id="inv-bad",
            )
    finally:
        con.close()


def test_ops_require_locked_connection(tmp_path):
    raw_con = duckdb.connect(str(tmp_path / "raw.duckdb"))
    with pytest.raises(TypeError, match="LockedConnection"):
        insert_document(raw_con, document_id="d", source_tier=1, document_type="x")
    raw_con.close()


# ---------------------------------------------------------------------------
# 3. Search
# ---------------------------------------------------------------------------


def _seed_three_chunks(db_path: str, model: _StubEmbeddingModel) -> tuple[str, str, str]:
    """Seed: 3 docs at different tiers, each with one chunk + embedding.
    Returns the chunk ids in seed order."""
    con = connect_write(db_path, purpose="seed")
    try:
        # tier 1, query-relevant
        insert_document(
            con, document_id="d1", source_tier=1, document_type="sec_filing_10k",
            title="PsiQuantum 10-K", source_uri="file:///d1.pdf",
        )
        c1 = insert_chunk(
            con, document_id="d1", chunk_index=0,
            text="PsiQuantum reports photonic qubits with high fidelity",
            embedding=model.encode("PsiQuantum reports photonic qubits with high fidelity"),
            embedding_provider=model,
            token_count=12,
        )
        # tier 3, less query-relevant
        insert_document(
            con, document_id="d2", source_tier=3, document_type="white_paper",
            title="Quantum overview",
        )
        c2 = insert_chunk(
            con, document_id="d2", chunk_index=0,
            text="quantum computing has many approaches",
            embedding=model.encode("quantum computing has many approaches"),
            embedding_provider=model,
            token_count=6,
        )
        # tier 5, off-topic
        insert_document(
            con, document_id="d3", source_tier=5, document_type="social_post",
            title="Anonymous post",
        )
        c3 = insert_chunk(
            con, document_id="d3", chunk_index=0,
            text="weather is nice today",
            embedding=model.encode("weather is nice today"),
            embedding_provider=model,
            token_count=5,
        )
    finally:
        con.close()
    return c1, c2, c3


def test_search_ranks_relevant_chunk_first(db_path):
    model = _StubEmbeddingModel()
    _seed_three_chunks(db_path, model)

    con = connect_read(db_path)
    try:
        result = search(con, "PsiQuantum photonic qubits", model=model, top_k=3)
    finally:
        con.close()

    assert result["top_k"] == 3
    assert len(result["results"]) == 3
    # Top hit must be d1 (the chunk containing the exact query terms).
    titles = [r["document_title"] for r in result["results"]]
    assert titles[0] == "PsiQuantum 10-K"


def test_search_source_tier_max_excludes_lower_trust(db_path):
    model = _StubEmbeddingModel()
    _seed_three_chunks(db_path, model)

    con = connect_read(db_path)
    try:
        result = search(con, "quantum", model=model, top_k=10, source_tier_max=2)
    finally:
        con.close()

    # Only tier 1 should survive (no tier-2 documents in the seed).
    assert all(r["source_tier"] <= 2 for r in result["results"])
    assert len(result["results"]) == 1


def test_search_rejects_mismatched_embedding_metadata(db_path):
    model = _StubEmbeddingModel()
    _seed_three_chunks(db_path, model)

    con = connect_read(db_path)
    try:
        with pytest.raises(ValueError, match="Stored chunk embeddings are pinned"):
            search(con, "PsiQuantum photonic qubits", model=_OtherStubEmbeddingModel())
    finally:
        con.close()


def test_search_with_edges_attaches_edges_and_nodes(db_path):
    model = _StubEmbeddingModel()
    c1, _, _ = _seed_three_chunks(db_path, model)

    con = connect_write(db_path, purpose="seed_graph")
    try:
        n1 = insert_node(
            con, canonical_label="PsiQuantum", node_type="organization",
            graph_scope="cross_domain", investigation_id="seed",
        )
        n2 = insert_node(
            con, canonical_label="photon", node_type="entity",
            graph_scope="cross_domain", investigation_id="seed",
        )
        insert_edge(
            con, source_node_id=n1, target_node_id=n2,
            relation="uses", source_tier=1, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="seed",
            chunk_id=c1, source_document_id="d1",
        )
    finally:
        con.close()

    con = connect_read(db_path)
    try:
        result = search(con, "PsiQuantum photonic", model=model, top_k=1, with_edges=True)
    finally:
        con.close()

    item = result["results"][0]
    assert "edges" in item
    assert "nodes" in item
    assert any(e["relation"] == "uses" for e in item["edges"])
    labels = {n["label"] for n in item["nodes"]}
    assert {"PsiQuantum", "photon"} <= labels


def test_render_subgraph_block_surfaces_edge_ids_for_the_role(db_path, monkeypatch):
    """GPW SPR-02 keystone: the orchestrator's subgraph_block renderer turns
    the sub-question's graph neighborhood into a block the evidence-retriever
    role can read + cite — replacing the '(subgraph search not yet wired)'
    placeholder. Proves a REAL seeded edge (with its edge_id) reaches the block."""
    from orchestration.loop_one.orchestrator import (
        _render_subgraph_block_for_sub_question,
    )

    model = _StubEmbeddingModel()
    c1, _, _ = _seed_three_chunks(db_path, model)
    con = connect_write(db_path, purpose="seed_graph")
    try:
        n1 = insert_node(
            con, canonical_label="PsiQuantum", node_type="organization",
            graph_scope="cross_domain", investigation_id="seed",
        )
        n2 = insert_node(
            con, canonical_label="photon", node_type="entity",
            graph_scope="cross_domain", investigation_id="seed",
        )
        eid = insert_edge(
            con, source_node_id=n1, target_node_id=n2,
            relation="uses", source_tier=1, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="seed",
            chunk_id=c1, source_document_id="d1",
        )
    finally:
        con.close()

    # Point the helper's internal default_db_path() + embedder at the fixtures.
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    import processing.embedding.embed as _embmod
    monkeypatch.setattr(_embmod, "default_embedding_provider", lambda: model)

    block = _render_subgraph_block_for_sub_question("PsiQuantum photonic", top_k=1)

    assert "(subgraph search not yet wired)" not in block  # placeholder gone
    assert eid in block                                    # the citable edge_id is present
    assert "PsiQuantum --[uses]--> photon" in block        # the relation is rendered
    assert "## Nodes" in block and "photon" in block


def test_render_subgraph_block_empty_graph_degrades_cleanly(db_path, monkeypatch):
    """No graph edges -> a labelled note, never a crash (best-effort, additive)."""
    from orchestration.loop_one.orchestrator import (
        _render_subgraph_block_for_sub_question,
    )

    model = _StubEmbeddingModel()
    _seed_three_chunks(db_path, model)  # chunks but NO edges
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    import processing.embedding.embed as _embmod
    monkeypatch.setattr(_embmod, "default_embedding_provider", lambda: model)

    block = _render_subgraph_block_for_sub_question("PsiQuantum photonic", top_k=1)
    assert block == "(no knowledge-graph edges for this sub-question)"


def test_render_subgraph_block_withholds_free_text_insight_labels(db_path, monkeypatch):
    """§9.0 guard (adversarial-review-driven): a free-text node label (an
    ``insight`` node whose canonical_label IS a distilled sentence, possibly
    from a personal_reading source reached via a cross-rights duplicate_of edge)
    must NOT be reproduced in the subgraph block — it is withheld and referenced
    by id. Canonical entity labels still surface. Closes the leak path the
    edge/node read cannot gate (nodes carry no rights provenance)."""
    from orchestration.loop_one.orchestrator import (
        _render_subgraph_block_for_sub_question,
    )

    model = _StubEmbeddingModel()
    c1, _, _ = _seed_three_chunks(db_path, model)
    secret = "PRIVATE INSIGHT: the fabricator yield collapses above 40 qubits"
    con = connect_write(db_path, purpose="seed_graph")
    try:
        org = insert_node(
            con, canonical_label="PsiQuantum", node_type="organization",
            graph_scope="cross_domain", investigation_id="seed",
        )
        # A free-text INSIGHT node — the leak vector.
        ins = insert_node(
            con, canonical_label=secret, node_type="insight",
            graph_scope="cross_domain", investigation_id="seed",
        )
        insert_edge(
            con, source_node_id=org, target_node_id=ins,
            relation="yields_insight", source_tier=1, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="seed",
            chunk_id=c1, source_document_id="d1",
        )
    finally:
        con.close()

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    import processing.embedding.embed as _embmod
    monkeypatch.setattr(_embmod, "default_embedding_provider", lambda: model)

    block = _render_subgraph_block_for_sub_question("PsiQuantum photonic", top_k=1)

    assert secret not in block                # the free-text insight is WITHHELD
    assert "text withheld (§9.0)" in block     # and marked as such
    assert "PsiQuantum" in block               # canonical entity label still surfaces
    assert "yields_insight" in block           # the relation (structure) still surfaces


def test_search_node_label_ilike(db_path):
    con = connect_write(db_path, purpose="seed")
    try:
        insert_node(
            con, canonical_label="PsiQuantum Inc",
            node_type="organization", graph_scope="cross_domain",
            investigation_id="seed",
        )
    finally:
        con.close()

    con = connect_read(db_path)
    try:
        # This node is seeded with no provenance (no chunk/document, no edge).
        # SPR-01 gate: the non-privileged serve path fails such a node CLOSED,
        # so this ILIKE-mechanic assertion runs on the owner (operator_only)
        # path, where every labeled node is returned. The §9.0 serve-path
        # exclusion is proven in tests/test_serve_node_gate.py.
        rows = search_nodes_by_label(
            con, "psiQuantum", limit=5, policy_tag="operator_only",
        )
    finally:
        con.close()
    assert rows and rows[0]["label"] == "PsiQuantum Inc"


def test_search_top_k_below_1_raises(db_path):
    model = _StubEmbeddingModel()
    con = connect_read(db_path)
    try:
        with pytest.raises(ValueError, match="top_k"):
            search(con, "x", model=model, top_k=0)
    finally:
        con.close()


def test_cosine_similarity_sql_emits_castable_expression(db_path):
    """The SQL expression must parse + execute against a real
    embedding column."""
    model = _StubEmbeddingModel()
    _seed_three_chunks(db_path, model)
    expr = cosine_similarity_sql("c.embedding", model.encode("quantum"), model.dimension)
    con = connect_read(db_path)
    try:
        rows = con.execute(
            f"SELECT {expr} AS sim FROM chunks c WHERE c.embedding IS NOT NULL"
        ).fetchall()
    finally:
        con.close()
    assert len(rows) >= 1
    assert all(-1.0001 <= float(r[0]) <= 1.0001 for r in rows)


# ---------------------------------------------------------------------------
# 4. Traverse
# ---------------------------------------------------------------------------


def _seed_chain_graph(db_path: str) -> tuple[str, str, str]:
    """Seed a 3-node chain: A —[r1]→ B —[r2]→ C.

    Returns the node ids."""
    con = connect_write(db_path, purpose="seed_chain")
    try:
        a = insert_node(
            con, canonical_label="A", node_type="entity",
            graph_scope="cross_domain", investigation_id="seed",
        )
        b = insert_node(
            con, canonical_label="B", node_type="entity",
            graph_scope="cross_domain", investigation_id="seed",
        )
        c = insert_node(
            con, canonical_label="C", node_type="entity",
            graph_scope="cross_domain", investigation_id="seed",
        )
        insert_edge(
            con, source_node_id=a, target_node_id=b,
            relation="r1", source_tier=2, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="seed",
        )
        insert_edge(
            con, source_node_id=b, target_node_id=c,
            relation="r2", source_tier=2, extraction_confidence=0.8,
            graph_scope="cross_domain", investigation_id="seed",
        )
    finally:
        con.close()
    return a, b, c


def test_resolve_node_by_id(db_path):
    a, _, _ = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        assert resolve_node(con, a) == a
    finally:
        con.close()


def test_resolve_node_by_label(db_path):
    a, _, _ = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        assert resolve_node(con, "A") == a
    finally:
        con.close()


def test_resolve_node_fuzzy_ilike(db_path):
    a, _, _ = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        # Lower-case partial match — falls through to the ILIKE branch.
        # "a" matches "A" via ILIKE. Test that the fuzzy path works.
        assert resolve_node(con, "a") == a
    finally:
        con.close()


def test_resolve_node_unknown_raises(db_path):
    con = connect_read(db_path)
    try:
        with pytest.raises(ValueError, match="not found"):
            resolve_node(con, "nonexistent_xyz")
    finally:
        con.close()


def test_shortest_path_finds_2_hop(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        paths = shortest_path(con, a, c, max_depth=5, min_confidence=0.0)
    finally:
        con.close()
    assert len(paths) == 1
    p = paths[0]
    assert p["depth"] == 2
    assert p["path_nodes"][0] == a
    assert p["path_nodes"][-1] == c
    assert p["path_relations"] == ["r1", "r2"]


def test_top_n_paths_returns_up_to_n(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        paths = top_n_paths(con, a, c, n=3, max_depth=5, min_confidence=0.0)
    finally:
        con.close()
    assert 1 <= len(paths) <= 3
    assert all(p["depth"] >= 2 for p in paths)


def test_dfs_with_depth_finds_path(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        paths = dfs_with_depth(con, a, c, depth_limit=5, min_confidence=0.0)
    finally:
        con.close()
    assert any(p["depth"] == 2 for p in paths)


def test_bfs_semantic_stop_through_waypoint(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        paths = bfs_semantic_stop(
            con, a, c, "B", max_depth=4, min_confidence=0.0,
        )
    finally:
        con.close()
    assert paths
    assert all("waypoint" in p and p["waypoint"] == "B" for p in paths)


def test_traverse_dispatcher_picks_algorithm(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        result = traverse(
            con, source=a, target=c, algorithm="shortest_path",
            depth=5, min_confidence=0.0, normalize_degree=False,
        )
    finally:
        con.close()
    assert result["algorithm"] == "shortest_path"
    assert result["path_count"] == 1
    assert result["source"]["label"] == "A"
    assert result["target"]["label"] == "C"
    # node_labels resolved for the returned path
    assert result["paths"][0]["node_labels"] == ["A", "B", "C"]


def test_traverse_bfs_semantic_stop_requires_waypoint(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        with pytest.raises(ValueError, match="waypoint"):
            traverse(con, source=a, target=c, algorithm="bfs_semantic_stop")
    finally:
        con.close()


def test_min_confidence_filters_low_confidence_edges(db_path):
    a, _, c = _seed_chain_graph(db_path)
    con = connect_read(db_path)
    try:
        # Both seed edges have confidence 0.9 and 0.8. min=0.85 excludes
        # the second edge → no full A→C path.
        paths = shortest_path(con, a, c, max_depth=5, min_confidence=0.85)
    finally:
        con.close()
    assert paths == []
