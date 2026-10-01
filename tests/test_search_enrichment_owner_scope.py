"""Fixed-candidate graph enrichment and active VSS SQL-path owner decisions."""

from __future__ import annotations

import json
from typing import Any

import duckdb
import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph import retrieval_gate
from substrate.graph.retrieval_substrate import DuckDbVssSubstrate
from substrate.graph.schema import init_database
from substrate.graph.search import _fetch_edges_and_nodes

OWNER_A = "acct_synthetic_a"
OWNER_B = "acct_synthetic_b"


class FixedModel:
    dimension = 2

    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0]


@pytest.fixture
def graph(tmp_path) -> str:
    path = str(tmp_path / "enrichment.duckdb")
    con = connect_write(path, purpose="c1-core-synthetic-seed")
    try:
        init_database(con)
        con.execute("ALTER TABLE chunks ADD COLUMN embedding_vss FLOAT[2]")
        con.executemany(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "title, content_class, owner_user_id) VALUES (?, 1, 'paper', ?, ?, ?)",
            [
                ("doc-public", "Public", "public_domain", "__operator__"),
                ("doc-licensed", "Licensed", "opt_in_licensed", "__operator__"),
                ("doc-own-a", "Own A", "user_authored_private", OWNER_A),
                ("doc-own-b", "Own B", "user_authored_private", OWNER_B),
                ("doc-unknown", "Unknown", "unregistered_class", "__operator__"),
                ("doc-taken", "Taken", "restricted_pending_opt_in", "__operator__"),
            ],
        )
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down, "
            "pre_takedown_content_class) VALUES "
            "('doc-taken', TRUE, 'public_domain')"
        )
        con.executemany(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "token_count, embedding, embedding_vss) VALUES (?, ?, 0, ?, 2, ?, ?)",
            [
                ("chunk-public", "doc-public", "Quantum public passage", [1.0, 0.0], [1.0, 0.0]),
                ("chunk-own-a", "doc-own-a", "Quantum own A passage", [1.0, 0.0], [1.0, 0.0]),
                ("chunk-own-b", "doc-own-b", "Quantum own B passage", [1.0, 0.0], [1.0, 0.0]),
            ],
        )
        nodes = [
            ("node-public", "Quantum public label", "doc-public", None),
            ("node-licensed", "Quantum licensed label", "doc-licensed", None),
            ("node-a-left", "A supporting endpoint", "doc-public", None),
            ("node-own-a", "Quantum own A label", "doc-own-a", OWNER_A),
            ("node-b-left", "B supporting endpoint", "doc-public", None),
            ("node-own-b", "Quantum own B label", "doc-own-b", OWNER_B),
            ("node-taken-left", "Taken left", "doc-public", None),
            ("node-taken-right", "Taken right", "doc-public", None),
        ]
        nodes.extend(
            (f"node-unknown-{i:02d}-{side}", f"Unknown {i} {side}", "doc-public", None)
            for i in range(25) for side in ("left", "right")
        )
        con.executemany(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata, owner_user_id) VALUES (?, ?, 'claim', 'depth', ?, ?)",
            [
                (node_id, label, json.dumps({"source_document_id": source}), owner)
                for node_id, label, source, owner in nodes
            ],
        )
        edges = [
            ("edge-public", "node-public", "node-licensed", "doc-public", None),
            ("edge-licensed", "node-public", "node-licensed", "doc-licensed", None),
            ("edge-no-doc", "node-public", "node-licensed", None, None),
            ("edge-owned-only-a", "node-public", "node-licensed", "doc-public", OWNER_A),
            ("edge-own-source-a", "node-a-left", "node-own-a", "doc-own-a", OWNER_A),
            ("edge-own-endpoint-a", "node-a-left", "node-own-a", "doc-public", OWNER_A),
            ("edge-foreign-source-b", "node-b-left", "node-own-b", "doc-own-b", OWNER_B),
            ("edge-foreign-endpoint-b", "node-b-left", "node-own-b", "doc-public", OWNER_B),
            ("edge-taken", "node-taken-left", "node-taken-right", "doc-taken", None),
        ]
        edges.extend(
            (f"edge-unknown-{i:02d}", f"node-unknown-{i:02d}-left",
             f"node-unknown-{i:02d}-right", "doc-unknown", None)
            for i in range(25)
        )
        con.executemany(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "graph_scope, owner_user_id) VALUES (?, ?, ?, 'corroborates', "
            "'chunk-public', ?, 1, 0.8, 'depth', ?)",
            edges,
        )
    finally:
        con.close()
    return path


class RecordingConnection:
    def __init__(self, con: Any):
        self.con = con
        self.edge_sql = ""
        self.edge_params: list[Any] = []

    def execute(self, sql: str, params: list[Any] | None = None):
        if "FROM edges e" in sql:
            self.edge_sql = sql
            self.edge_params = list(params or [])
        return self.con.execute(sql, params or [])


def _edge_ids(con: Any, owner: str | None) -> tuple[set[str], set[str], RecordingConnection]:
    recording = RecordingConnection(con)
    edges, nodes = _fetch_edges_and_nodes(
        recording, "chunk-public", policy_tag="owner_scoped", owner_user_id=owner,
    )
    edge_ids = {edge["edge_id"] for edge in edges}
    node_ids = {node["node_id"] for node in nodes}
    assert {edge["source"]["id"] for edge in edges} <= node_ids
    assert {edge["target"]["id"] for edge in edges} <= node_ids
    assert all(edge["relation"] == "corroborates" for edge in edges)
    return edge_ids, node_ids, recording


def test_edge_enrichment_filters_own_sources_and_endpoints_before_limit(graph):
    con = connect_read(graph)
    try:
        public, public_nodes, _ = _edge_ids(con, None)
        a, a_nodes, recording = _edge_ids(con, OWNER_A)
        b, b_nodes, _ = _edge_ids(con, OWNER_B)
        malformed, _, _ = _edge_ids(con, f" {OWNER_A} ")
    finally:
        con.close()
    shared = {"edge-public", "edge-licensed", "edge-no-doc"}
    assert public == shared
    assert public_nodes == {"node-public", "node-licensed"}
    assert a == shared | {
        "edge-owned-only-a", "edge-own-source-a", "edge-own-endpoint-a",
    }
    assert a_nodes == public_nodes | {"node-a-left", "node-own-a"}
    assert b == shared | {"edge-foreign-source-b", "edge-foreign-endpoint-b"}
    assert b_nodes == public_nodes | {"node-b-left", "node-own-b"}
    assert malformed == shared
    assert len(a) < 20  # 25 denied rows cannot consume the SQL limit.

    edge_sql, edge_params = retrieval_gate.non_privileged_edge_provenance_clause(
        edge_alias="e", policy_tag="owner_scoped", owner_user_id=OWNER_A,
    )
    g1_sql, g1_params = retrieval_gate.non_privileged_node_provenance_clause(
        node_alias="n1", policy_tag="owner_scoped", owner_user_id=OWNER_A,
    )
    g2_sql, g2_params = retrieval_gate.non_privileged_node_provenance_clause(
        node_alias="n2", policy_tag="owner_scoped", owner_user_id=OWNER_A,
    )
    o1_sql, o1_params = retrieval_gate.node_owner_sql_clause(
        node_alias="n1", owner_user_id=OWNER_A,
    )
    o2_sql, o2_params = retrieval_gate.node_owner_sql_clause(
        node_alias="n2", owner_user_id=OWNER_A,
    )
    assert f"WHERE e.chunk_id = ?{g1_sql}{g2_sql}{o1_sql}{o2_sql}{edge_sql}" in recording.edge_sql
    assert recording.edge_sql.index(edge_sql) < recording.edge_sql.index("LIMIT 20")
    assert recording.edge_params == [
        "chunk-public", *g1_params, *g2_params, *o1_params, *o2_params, *edge_params,
    ]


def test_dangling_edge_source_is_withheld_in_disposable_permissive_catalog():
    # The canonical edges table has a source-document FK, so an otherwise
    # complete disposable read schema is needed to exercise a legacy dangling
    # pointer without changing product schema or disabling constraints.
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE documents (document_id TEXT, content_class TEXT, owner_user_id TEXT)")
        con.execute("CREATE TABLE chunks (chunk_id TEXT, document_id TEXT)")
        con.execute("CREATE TABLE book_assets (document_id TEXT, taken_down BOOLEAN)")
        con.execute("CREATE TABLE nodes (node_id TEXT, node_type TEXT, canonical_label TEXT, metadata TEXT, owner_user_id TEXT)")
        con.execute(
            "CREATE TABLE edges (edge_id TEXT, source_node_id TEXT, target_node_id TEXT, "
            "relation TEXT, extraction_confidence FLOAT, source_tier INTEGER, "
            "chunk_id TEXT, source_document_id TEXT, owner_user_id TEXT)"
        )
        con.execute("INSERT INTO documents VALUES ('doc-public', 'public_domain', '__operator__')")
        con.execute("INSERT INTO chunks VALUES ('chunk-public', 'doc-public')")
        con.executemany("INSERT INTO nodes VALUES (?, 'claim', ?, ?, NULL)", [
            ("good-left", "Good left", json.dumps({"source_document_id": "doc-public"})),
            ("good-right", "Good right", json.dumps({"source_document_id": "doc-public"})),
            ("bad-left", "Bad left", json.dumps({"source_document_id": "doc-public"})),
            ("bad-right", "Bad right", json.dumps({"source_document_id": "doc-public"})),
        ])
        con.executemany(
            "INSERT INTO edges VALUES (?, ?, ?, 'relates', 0.7, 1, "
            "'chunk-public', ?, NULL)",
            [
                ("edge-good", "good-left", "good-right", "doc-public"),
                ("edge-dangling", "bad-left", "bad-right", "doc-absent"),
            ],
        )
        edges, nodes = _fetch_edges_and_nodes(con, "chunk-public")
        assert {edge["edge_id"] for edge in edges} == {"edge-good"}
        assert {node["node_id"] for node in nodes} == {"good-left", "good-right"}
    finally:
        con.close()


@pytest.mark.parametrize("owner,policy,expected", [
    (None, "owner_scoped", {"Quantum public label", "Quantum licensed label"}),
    (OWNER_A, "owner_scoped", {"Quantum public label", "Quantum licensed label", "Quantum own A label"}),
    (OWNER_B, "owner_scoped", {"Quantum public label", "Quantum licensed label", "Quantum own B label"}),
    (OWNER_A, "attribution_eligible", {"Quantum public label", "Quantum licensed label"}),
])
def test_active_vss_sql_path_forwards_owner_to_node_matches(graph, owner, policy, expected):
    con = connect_read(graph)
    try:
        # vss_active selects the active SQL branch against a sized array column;
        # this fixture does not install an extension or build a native HNSW index.
        substrate = DuckDbVssSubstrate(con, model=FixedModel(), vss_active=True)
        result = substrate._vss_query(
            "Quantum", top_k=10, source_tier_max=None, document_ids=None,
            policy_tag=policy, owner_user_id=owner,
            query_vector=FixedModel().encode("Quantum"),
        )
    finally:
        con.close()
    labels = {row["label"] for row in result["node_matches"]}
    docs = {row["document_id"] for row in result["results"]}
    assert labels == expected
    assert "doc-public" in docs
    assert ("doc-own-a" in docs) == (owner == OWNER_A and policy == "owner_scoped")
    assert ("doc-own-b" in docs) == (owner == OWNER_B and policy == "owner_scoped")
