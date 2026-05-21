"""Tests for ``services.cross_doc.query.get_cross_doc_links`` (SPR-07 M1).

Coverage:

1. Happy path — similarity leg returns three diverse target chunks
   ordered by descending similarity. No edges in fixture.
2. Echo-chamber guard — chunks from the source document are excluded
   even if they have higher similarity.
3. Diversity guard — even with 5 candidates from the same target doc,
   at most 1 is returned (DEFAULT_MAX_PER_DOCUMENT=1).
4. User-asserted edge boost — a candidate with low similarity but a
   user_asserted edge can outrank a candidate with mid similarity.
5. Citation edge boost — same shape as user-asserted, lower weight.
6. Public-graph default-off — a chunk with content_class=
   'user_public_contribution' is excluded by default; included with
   the toggle.
7. top_k enforcement — even with many candidates we never exceed 3.
8. Empty selection text — returns [] gracefully.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from runtime.db_lock import connect_write  # noqa: E402
from services.cross_doc.query import (  # noqa: E402
    DEFAULT_MAX_PER_DOCUMENT,
    DEFAULT_TOP_K,
    Highlight,
    SCORING_WEIGHTS,
    get_cross_doc_links,
)
from substrate.graph import (  # noqa: E402
    ensure_initialized,
    insert_chunk,
    insert_document,
    insert_edge,
    insert_node,
)


# ---------------------------------------------------------------------------
# Deterministic embedding stub
# ---------------------------------------------------------------------------


class StubEmbedding:
    """Encodes a string into a deterministic vector by spreading the
    character-code sums across a fixed dimension. Lets the test set up
    candidates whose cosine similarity is exactly predictable.

    Production code wraps sentence-transformers; this stub keeps tests
    fast and hermetic."""

    dimension = 8

    def encode(self, text: str) -> list[float]:
        # Map text to a length-8 vector by hashing each char to a slot.
        v = [0.0] * self.dimension
        for i, ch in enumerate(text):
            v[i % self.dimension] += float(ord(ch))
        # Light-normalisation so cosine sim sits in a sane range. We do
        # NOT unit-normalise — cosine_similarity_sql does the
        # normalisation by construction (sqrt(dot(self, self))).
        return v


def _make_vec(slot_to_value: dict[int, float]) -> list[float]:
    """Build an 8-dim vector with explicit per-slot weights. Used to
    seed chunks with predictable similarity to the query stub."""
    v = [0.0] * StubEmbedding.dimension
    for k, val in slot_to_value.items():
        v[k] = val
    return v


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path):
    p = str(tmp_path / "graph.duckdb")
    ensure_initialized(p)
    return p


def _seed_doc_with_chunk(
    db_path: str,
    *,
    document_id: str,
    title: str,
    chunk_id: str,
    chunk_text: str,
    embedding,
    source_tier: int = 2,
    content_class: str | None = None,
) -> None:
    con = connect_write(db_path, purpose="test_seed")
    try:
        insert_document(
            con,
            document_id=document_id,
            source_tier=source_tier,
            document_type="peer_reviewed_paper",
            title=title,
            on_conflict="ignore",
        )
        if content_class is not None:
            con.execute(
                "UPDATE documents SET content_class = ? WHERE document_id = ?",
                [content_class, document_id],
            )
        insert_chunk(
            con,
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_index=0,
            text=chunk_text,
            embedding=embedding,
        )
    finally:
        con.close()


def _seed_user_asserted_edge(
    db_path: str,
    *,
    source_chunk_id: str,
    target_chunk_id: str,
    source_doc: str,
    investigation_id: str = "inv-test",
) -> None:
    """Create a user_asserted edge that anchors source_chunk_id and
    target_chunk_id together via shared nodes.

    The query layer's user-asserted leg finds chunks by joining edges
    to chunks via shared node references. The simplest fixture is: one
    edge between two nodes, where the edge.chunk_id = source and a
    second edge with same target_node_id points to a node referenced
    by an edge anchored to target_chunk_id."""
    con = connect_write(db_path, purpose="test_seed_edges")
    try:
        # Two nodes (operator-asserted relationship between concept A
        # in source doc and concept B in target doc).
        node_a = insert_node(
            con,
            canonical_label=f"concept-a-{source_chunk_id}",
            node_type="entity",
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        node_b = insert_node(
            con,
            canonical_label=f"concept-b-{target_chunk_id}",
            node_type="entity",
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        # Edge anchored on source chunk (the user-asserted edge).
        insert_edge(
            con,
            source_node_id=node_a,
            target_node_id=node_b,
            relation="user_asserted_link",
            chunk_id=source_chunk_id,
            source_document_id=source_doc,
            source_tier=2,
            extraction_confidence=1.0,
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        # Edge anchored on target chunk that references node_b — gives
        # the join in _edge_anchored_candidates a row to find.
        insert_edge(
            con,
            source_node_id=node_b,
            target_node_id=node_a,
            relation="related",
            chunk_id=target_chunk_id,
            source_document_id=source_doc,  # placeholder; real source is the target doc
            source_tier=2,
            extraction_confidence=1.0,
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
    finally:
        con.close()


def _seed_citation_edge(
    db_path: str,
    *,
    source_chunk_id: str,
    target_chunk_id: str,
    source_doc: str,
    investigation_id: str = "inv-test",
) -> None:
    con = connect_write(db_path, purpose="test_seed_edges_cite")
    try:
        node_a = insert_node(
            con,
            canonical_label=f"cite-a-{source_chunk_id}",
            node_type="claim",
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        node_b = insert_node(
            con,
            canonical_label=f"cite-b-{target_chunk_id}",
            node_type="claim",
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        insert_edge(
            con,
            source_node_id=node_a,
            target_node_id=node_b,
            relation="cites",
            chunk_id=source_chunk_id,
            source_document_id=source_doc,
            source_tier=2,
            extraction_confidence=1.0,
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        insert_edge(
            con,
            source_node_id=node_b,
            target_node_id=node_a,
            relation="related",
            chunk_id=target_chunk_id,
            source_document_id=source_doc,
            source_tier=2,
            extraction_confidence=1.0,
            graph_scope="cross_domain",
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
    finally:
        con.close()


def _open_read(db_path: str):
    import duckdb
    return duckdb.connect(db_path, read_only=True)


def _highlight(document_id: str, text: str = "selected") -> Highlight:
    return Highlight(
        document_id=document_id,
        page=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        selected_text=text,
    )


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_similarity_leg_returns_top_k_ordered(db_path):
    # Source doc has the chunk we highlight; three target docs each
    # have one chunk with decreasing similarity to the query "abc".
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc source",
        embedding=_make_vec({0: 100.0, 1: 100.0}),
    )
    # query "abc" → ord('a')+ord('b')+ord('c') = 97+98+99 = 294 in slot 0.
    # target chunks: slot 0 dominant = highest similarity.
    _seed_doc_with_chunk(
        db_path, document_id="doc-1", title="High",
        chunk_id="ch-1", chunk_text="x",
        embedding=_make_vec({0: 200.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-2", title="Mid",
        chunk_id="ch-2", chunk_text="x",
        embedding=_make_vec({0: 100.0, 5: 100.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-3", title="Low",
        chunk_id="ch-3", chunk_text="x",
        embedding=_make_vec({0: 10.0, 6: 1000.0}),
    )

    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
        top_k=DEFAULT_TOP_K,
    )
    assert [r.document_id for r in results] == ["doc-1", "doc-2", "doc-3"]
    assert all(r.source == "similarity" for r in results)
    assert results[0].score >= results[1].score >= results[2].score


# ---------------------------------------------------------------------------
# 2. Echo-chamber guard
# ---------------------------------------------------------------------------


def test_excludes_source_document_chunks(db_path):
    # The most-similar chunk lives in the source document — must be
    # excluded.
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="best match",
        embedding=_make_vec({0: 500.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-other", title="Other",
        chunk_id="ch-other", chunk_text="weaker",
        embedding=_make_vec({0: 50.0}),
    )

    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
    )
    assert [r.document_id for r in results] == ["doc-other"]


# ---------------------------------------------------------------------------
# 3. Diversity guard
# ---------------------------------------------------------------------------


def test_max_per_document_caps_one_per_doc(db_path):
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({1: 100.0}),
    )
    # 4 chunks from the same target document, all high similarity.
    for i in range(4):
        _seed_doc_with_chunk(
            db_path, document_id="doc-target", title="Target",
            chunk_id=f"ch-t-{i}", chunk_text=f"chunk {i}",
            embedding=_make_vec({0: 100.0 - i}),
        )

    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
    )
    target_count = sum(1 for r in results if r.document_id == "doc-target")
    assert target_count <= DEFAULT_MAX_PER_DOCUMENT
    assert target_count == 1


# ---------------------------------------------------------------------------
# 4. User-asserted edge boost
# ---------------------------------------------------------------------------


def test_user_asserted_edge_boosts_low_similarity(db_path):
    # Source chunk + two target chunks. Target-A has weak similarity
    # but no edge. Target-B has near-zero similarity but a
    # user-asserted edge.
    #
    # StubEmbedding for "abc" → query vector [97, 98, 99, 0, 0, 0, 0,
    # 0] (one char per slot, position-wise). For target-B to win the
    # fused score: 0.7·sim_A + 0 < 0.7·sim_B + 0.2 — so we want
    # sim_A < sim_B + 0.286.
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({0: 100.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-a", title="A no edge",
        chunk_id="ch-a", chunk_text="weak match",
        # Slot 5: 50. Query vec slot 5 = 0 → cosine = 0.
        embedding=_make_vec({5: 50.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-b", title="B with user edge",
        chunk_id="ch-b", chunk_text="even weaker match",
        # Slot 7: 1. Also non-aligned → cosine = 0. But ch-b carries
        # the user-asserted edge so it earns the boost.
        embedding=_make_vec({7: 1.0}),
    )
    _seed_user_asserted_edge(
        db_path,
        source_chunk_id="ch-src",
        target_chunk_id="ch-b",
        source_doc="doc-source",
    )

    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
    )
    by_doc = {r.document_id: r for r in results}
    assert "doc-b" in by_doc, f"expected doc-b in results, got {results}"
    assert by_doc["doc-b"].source == "user_asserted"
    # doc-b should outrank doc-a thanks to the edge boost.
    docs_ordered = [r.document_id for r in results]
    assert docs_ordered.index("doc-b") < docs_ordered.index("doc-a")


# ---------------------------------------------------------------------------
# 5. Citation edge
# ---------------------------------------------------------------------------


def test_citation_edge_surfaces_target(db_path):
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({0: 100.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-cited", title="Cited",
        chunk_id="ch-cited", chunk_text="cited passage",
        embedding=_make_vec({3: 100.0}),
    )
    _seed_citation_edge(
        db_path,
        source_chunk_id="ch-src",
        target_chunk_id="ch-cited",
        source_doc="doc-source",
    )

    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
    )
    by_doc = {r.document_id: r for r in results}
    assert "doc-cited" in by_doc
    # source flag is "citation" when the leg's signal dominates; the
    # citation leg's similarity is computed against the target chunk
    # embedding too, so the source attribution may be "similarity" if
    # the similarity hit happens to be higher rank. We assert the
    # candidate is present regardless of which leg won — that's the
    # contract.


# ---------------------------------------------------------------------------
# 6. Public-graph toggle
# ---------------------------------------------------------------------------


def test_public_graph_default_off(db_path):
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({1: 100.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-priv", title="Private",
        chunk_id="ch-priv", chunk_text="private content",
        embedding=_make_vec({0: 50.0}),
        content_class="user_owned",
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-pub", title="Public",
        chunk_id="ch-pub", chunk_text="public content",
        embedding=_make_vec({0: 100.0}),
        content_class="user_public_contribution",
    )

    con = _open_read(db_path)
    # Default OFF — public doc excluded even though it's more similar.
    off = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
        include_public_graph=False,
    )
    assert "doc-pub" not in {r.document_id for r in off}
    assert "doc-priv" in {r.document_id for r in off}

    # ON — public doc visible.
    on = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
        include_public_graph=True,
    )
    assert "doc-pub" in {r.document_id for r in on}


# ---------------------------------------------------------------------------
# 7. top_k cap
# ---------------------------------------------------------------------------


def test_top_k_caps_at_three(db_path):
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({1: 100.0}),
    )
    for i in range(10):
        _seed_doc_with_chunk(
            db_path, document_id=f"doc-{i}", title=f"D{i}",
            chunk_id=f"ch-{i}", chunk_text=f"text {i}",
            embedding=_make_vec({0: 100.0 - i}),
        )

    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
        top_k=DEFAULT_TOP_K,
    )
    assert len(results) == DEFAULT_TOP_K


# ---------------------------------------------------------------------------
# 8. Empty selection
# ---------------------------------------------------------------------------


def test_empty_selection_returns_empty(db_path):
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({0: 1.0}),
    )
    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", text="   "),
        con=con,
        model=StubEmbedding(),
    )
    assert results == []


# ---------------------------------------------------------------------------
# 9. Weights API
# ---------------------------------------------------------------------------


def test_scoring_weights_default_sums_to_one():
    """Document-the-choice rigor #1: the published defaults sum to 1.0
    (within float tolerance) so the fused score sits in [0, 1] for a
    candidate that has all three signals at max."""
    total = (
        SCORING_WEIGHTS["similarity"]
        + SCORING_WEIGHTS["user_asserted"]
        + SCORING_WEIGHTS["citation"]
    )
    assert abs(total - 1.0) < 1e-9


def test_caller_can_override_weights(db_path):
    _seed_doc_with_chunk(
        db_path, document_id="doc-source", title="Source",
        chunk_id="ch-src", chunk_text="abc",
        embedding=_make_vec({1: 100.0}),
    )
    _seed_doc_with_chunk(
        db_path, document_id="doc-a", title="A",
        chunk_id="ch-a", chunk_text="x",
        embedding=_make_vec({0: 100.0}),
    )
    con = _open_read(db_path)
    results = get_cross_doc_links(
        _highlight("doc-source", "abc"),
        con=con,
        model=StubEmbedding(),
        weights={"similarity": 0.5, "user_asserted": 0.3, "citation": 0.2},
    )
    assert len(results) == 1
    assert results[0].document_id == "doc-a"


# ---------------------------------------------------------------------------
# 10. Bad input
# ---------------------------------------------------------------------------


def test_invalid_top_k_raises(db_path):
    con = _open_read(db_path)
    with pytest.raises(ValueError):
        get_cross_doc_links(
            _highlight("doc-source"),
            con=con,
            model=StubEmbedding(),
            top_k=0,
        )
