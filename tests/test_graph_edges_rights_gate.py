"""§9.0 rights gate on the with_edges serve path (#206 regression guard).

The node-label leak: ``search(with_edges=True)`` attaches the edges sourced
from each returned chunk plus the nodes those edges connect, via
``_fetch_edges_and_nodes``. That path returned each endpoint's
``canonical_label`` with NO §9.0 gate — unlike the chunk query and
``node_matches`` (``search_nodes_by_label``), both gated by
``non_privileged_node_provenance_clause`` (#202).

A public-provenance chunk (which a non-privileged caller IS allowed to see) can
have an edge to a node whose provenance is ``personal_reading``/restricted
(semantic dedup lets a public insight attach to a surviving personal node). So
serving that endpoint's label on the non-privileged path leaked the personal
headline to a sub-LLM. This is the residual leak #202 deferred to "SPR-02".

The fix threads ``policy_tag`` into ``_fetch_edges_and_nodes`` and gates BOTH
endpoint nodes (n1, n2) with the canonical clause (most-restrictive-wins +
fail-closed on unresolved provenance). An edge is withheld if either endpoint is
gated — serving either endpoint's label would leak.

These tests prove: (1) the non-privileged path WITHHOLDS a personal-provenance
node + its edge (leak closed); (2) the privileged (owner) path still sees it
(byte-identity — the owner reads own content); (3) a public-provenance node is
served on the non-privileged path unchanged (no over-exclusion of public value).
"""

from __future__ import annotations

import json

import duckdb
import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import PRIVILEGED_POLICY_TAGS, search

_PUB = "public body text public domain quantum photonic"
_PRIV = "private personal reading body text secret headline"


def _seed_graph(db_path: str, emb: HashEmbedding) -> None:
    con = connect_write(db_path, purpose="seed-edges-rights-gate")
    try:
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
            ["doc-pub", "public doc"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "token_count, embedding) VALUES (?, ?, 0, ?, ?, ?)",
            ["chunk-pub", "doc-pub", _PUB, max(1, len(_PUB) // 4), emb.encode(_PUB)],
        )
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', 'personal_reading')",
            ["doc-priv", "private doc"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "token_count, embedding) VALUES (?, ?, 0, ?, ?, ?)",
            ["chunk-priv", "doc-priv", _PRIV, max(1, len(_PRIV) // 4), emb.encode(_PRIV)],
        )
        # A node whose provenance resolves to PERSONAL_READING via its metadata
        # chunk_id (the real leak vector: the label is personal-only).
        con.execute(
            "INSERT INTO nodes (node_id, node_type, canonical_label, graph_scope, "
            "metadata) VALUES (?, ?, ?, ?, ?)",
            ["node-priv", "insight", "SECRET-PERSONAL-READING-HEADLINE", "depth",
             json.dumps({"chunk_id": "chunk-priv"})],
        )
        con.execute(
            "INSERT INTO nodes (node_id, node_type, canonical_label, graph_scope) "
            "VALUES (?, ?, ?, ?)",
            ["node-pub", "claim", "public claim", "depth"],
        )
        # A public-provenance edge (sourced from the public chunk) connecting to
        # the personal-provenance node — the edge a non-privileged caller reaches
        # via the public chunk it IS allowed to see.
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, chunk_id, source_tier, extraction_confidence, "
            "graph_scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["edge-1", "node-pub", "node-priv", "supported_by", "doc-pub",
             "chunk-pub", 1, 0.9, "depth"],
        )
        # A second public node + a public-only edge: the realistic topology where
        # a public node is also connected to OTHER public nodes (so it survives the
        # gate via its public edge neighborhood, not only the gated one).
        con.execute(
            "INSERT INTO nodes (node_id, node_type, canonical_label, graph_scope) "
            "VALUES (?, ?, ?, ?)",
            ["node-pub2", "claim", "public claim two", "depth"],
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, chunk_id, source_tier, extraction_confidence, "
            "graph_scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["edge-2", "node-pub", "node-pub2", "related_to", "doc-pub",
             "chunk-pub", 1, 0.8, "depth"],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def _edge_and_node_labels(result: dict) -> list[str]:
    labels: list[str] = []
    for item in result.get("results", []):
        for e in item.get("edges", []):
            labels.append(e.get("source", {}).get("label", ""))
            labels.append(e.get("target", {}).get("label", ""))
        for n in item.get("nodes", []):
            labels.append(n.get("label", ""))
    return [label for label in labels if label]


@pytest.fixture
def emb() -> HashEmbedding:
    return HashEmbedding()


@pytest.fixture
def db(emb, tmp_path) -> str:
    p = str(tmp_path / "edges-rights.duckdb")
    init_database_at_path(p)
    _seed_graph(p, emb)
    return p


def _has_secret(labels: list[str]) -> bool:
    return any("SECRET-PERSONAL" in label for label in labels)


def test_non_privileged_path_withholds_personal_provenance_node(db, emb) -> None:
    """The leak: a non-privileged caller searching the public chunk must NOT
    see the personal-provenance node's label via the edges/nodes payload."""
    con = duckdb.connect(db, read_only=True)
    try:
        result = search(con, "public domain quantum", model=emb, top_k=5,
                        with_edges=True, policy_tag="attribution_eligible")
    finally:
        con.close()
    # the public chunk is served (the caller is allowed to see it)...
    assert len(result["results"]) >= 1
    # ...but the personal-provenance endpoint node + its edge are withheld.
    assert not _has_secret(_edge_and_node_labels(result)), (
        "§9.0 leak via the with_edges path: a non-privileged caller saw a "
        "personal_provenance node label (#206 regressed)"
    )


def test_privileged_owner_path_still_sees_personal_node(db, emb) -> None:
    """Byte-identity: the owner (privileged policy_tag) still sees own
    personal-provenance content via the edges path — the gate widens nothing
    publicly and hides nothing from the owner."""
    con = duckdb.connect(db, read_only=True)
    try:
        result = search(con, "public domain quantum", model=emb, top_k=5,
                        with_edges=True, policy_tag=next(iter(PRIVILEGED_POLICY_TAGS)))
    finally:
        con.close()
    assert _has_secret(_edge_and_node_labels(result)), (
        "owner regression: the privileged path must still serve the owner's own "
        "personal-provenance node via the edges path"
    )


def test_non_privileged_path_serves_public_provenance_node(db, emb) -> None:
    """No over-exclusion: a public-provenance node is served on the non-
    privileged path unchanged (the gate hides only gated content)."""
    con = duckdb.connect(db, read_only=True)
    try:
        result = search(con, "public domain quantum", model=emb, top_k=5,
                        with_edges=True, policy_tag="attribution_eligible")
    finally:
        con.close()
    labels = _edge_and_node_labels(result)
    # The realistic topology: a public node connected to OTHER public nodes
    # survives the gate via its public edge neighborhood — public value is
    # served, not over-excluded. (A public node whose ONLY edge touches a gated
    # node is withheld with that edge — a rare, acceptable over-exclusion per
    # the §9.0 contract, which prioritizes no-leak over no-over-exclusion.)
    assert "public claim two" in labels, (
        "over-exclusion: a public node on a public-only edge should be served "
        "on the non-privileged path"
    )
