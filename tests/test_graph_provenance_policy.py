"""Ordinary synthetic decisions for graph source provenance."""

from __future__ import annotations

import json

import duckdb
import pytest

from substrate.graph.retrieval_gate import (
    non_privileged_edge_provenance_clause,
    non_privileged_node_provenance_clause,
)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE documents (document_id TEXT, content_class TEXT, owner_user_id TEXT)")
    connection.execute("CREATE TABLE chunks (chunk_id TEXT, document_id TEXT)")
    connection.execute("CREATE TABLE book_assets (document_id TEXT, taken_down BOOLEAN)")
    connection.execute("CREATE TABLE nodes (node_id TEXT, metadata TEXT, owner_user_id TEXT)")
    connection.execute("CREATE TABLE edges (edge_id TEXT, source_node_id TEXT, target_node_id TEXT, chunk_id TEXT, source_document_id TEXT, owner_user_id TEXT)")
    connection.executemany("INSERT INTO documents VALUES (?, ?, ?)", [
        ("public", "public_domain", "A"),
        ("privateA", "user_authored_private", "A"),
        ("privateB", "user_authored_private", "B"),
        ("restricted", "restricted_pending_opt_in", "A"),
        ("research", "research_only", "A"),
        ("unknown", "surprise", "A"),
        ("taken", "public_domain", "A"),
        ("null_class", None, "A"),
        ("legacy", "user_owned", "A"),
        ("contribution", "user_public_contribution", "B"),
        ("private_no_owner", "user_authored_private", None),
        ("private_blank_owner", "personal_reading", ""),
    ])
    connection.executemany("INSERT INTO chunks VALUES (?, ?)", [
        ("cp", "public"), ("ca", "privateA"), ("cb", "privateB"),
        ("cr", "research"),
    ])
    connection.execute("INSERT INTO book_assets VALUES ('taken', TRUE)")
    yield connection
    connection.close()


def _nodes(con, *, policy="attribution_eligible", owner=None):
    sql, params = non_privileged_node_provenance_clause(
        node_alias="n", policy_tag=policy, owner_user_id=owner
    )
    return {row[0] for row in con.execute(
        f"SELECT n.node_id FROM nodes n WHERE TRUE{sql}", params
    ).fetchall()}


def test_node_every_declared_reference_and_malformed_row_isolation(con):
    rows = [
        ("healthy", json.dumps({"chunk_id": "cp"}), None),
        ("mine", json.dumps({"source_chunk_ids": ["cp", "ca"]}), "A"),
        ("foreign_tail", json.dumps({"source_chunk_ids": ["cp", "cb"]}), None),
        ("mixed_forms", json.dumps({"source_document_id": "public", "source_chunk_ids": ["cb"]}), None),
        ("bad_json", "{invalid", None),
        ("scalar_json", '"text"', None),
        ("bad_array", json.dumps({"source_chunk_ids": "cp"}), None),
        ("bad_element", json.dumps({"source_chunk_ids": ["cp", 12]}), None),
        ("bad_direct", json.dumps({"chunk_id": 12}), None),
        ("dangling", json.dumps({"source_document_id": "absent"}), None),
        ("source_less", "{}", None),
        ("restricted", json.dumps({"source_document_id": "restricted"}), None),
        ("research", json.dumps({"source_document_id": "research"}), None),
        ("unknown", json.dumps({"source_document_id": "unknown"}), None),
        ("taken", json.dumps({"source_document_id": "taken"}), None),
    ]
    con.executemany("INSERT INTO nodes VALUES (?, ?, ?)", rows)
    assert _nodes(con) == {"healthy"}
    assert _nodes(con, policy="owner_scoped", owner="A") == {"healthy", "mine"}
    assert _nodes(con, policy="operator_only", owner="A") == {"healthy", "mine", "restricted", "research"}
    assert _nodes(con, policy="private_research", owner="A") == {"healthy", "mine", "restricted", "research"}
    assert _nodes(con, policy="unexpected", owner="A") == {"healthy"}
    assert "mine" not in _nodes(con, policy="owner_scoped", owner=" A ")


def test_node_legacy_public_and_mixed_private_source_matrix(con):
    con.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [
        ("null_class", json.dumps({"source_document_id": "null_class"}), None),
        ("legacy", json.dumps({"source_document_id": "legacy"}), None),
        ("contribution", json.dumps({"source_document_id": "contribution"}), None),
        ("missing_owner", json.dumps({"source_document_id": "private_no_owner"}), None),
        ("blank_owner", json.dumps({"source_document_id": "private_blank_owner"}), None),
        ("mixed_A_B", json.dumps({"source_chunk_ids": ["ca", "cb"]}), None),
    ])
    public = {"null_class", "legacy", "contribution"}
    for policy, owner in (
        ("attribution_eligible", None),
        ("owner_scoped", "A"),
        ("owner_scoped", "B"),
        ("operator_only", "A"),
        ("private_research", "B"),
    ):
        assert _nodes(con, policy=policy, owner=owner) == public


def _edges(con, *, policy="attribution_eligible", owner=None):
    sql, params = non_privileged_edge_provenance_clause(
        edge_alias="e", policy_tag=policy, owner_user_id=owner
    )
    return {row[0] for row in con.execute(
        f"SELECT e.edge_id FROM edges e WHERE TRUE{sql}", params
    ).fetchall()}


def test_independent_edge_document_and_chunk_source_matrix(con):
    cases = [
        ("doc_public", None, "public"),
        ("chunk_public", "cp", None),
        ("doc_private_A", None, "privateA"),
        ("chunk_private_B", "cb", None),
        ("doc_restricted", None, "restricted"),
        ("chunk_research", "cr", None),
    ]
    for edge_id, chunk_id, document_id in cases:
        left, right = f"{edge_id}_left", f"{edge_id}_right"
        con.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [
            (left, json.dumps({"source_document_id": "public"}), None),
            (right, json.dumps({"source_document_id": "public"}), None),
        ])
        con.execute(
            "INSERT INTO edges VALUES (?, ?, ?, ?, ?, NULL)",
            [edge_id, left, right, chunk_id, document_id],
        )
    public = {"doc_public", "chunk_public"}
    assert _edges(con) == public
    assert _edges(con, policy="owner_scoped", owner="A") == public | {"doc_private_A"}
    assert _edges(con, policy="owner_scoped", owner="B") == public | {"chunk_private_B"}
    licensed = {"doc_restricted", "chunk_research"}
    assert _edges(con, policy="operator_only", owner="A") == public | licensed | {"doc_private_A"}
    assert _edges(con, policy="private_research", owner="B") == public | licensed | {"chunk_private_B"}


def test_incident_edge_both_sources_and_edge_own_policy(con):
    con.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [
        ("a", json.dumps({"chunk_id": "cp"}), None),
        ("b", json.dumps({"source_document_id": "public"}), None),
    ])
    con.execute("INSERT INTO edges VALUES ('e', 'a', 'b', 'ca', 'public', NULL)")
    assert _nodes(con) == set()
    assert _nodes(con, policy="owner_scoped", owner="A") == {"a", "b"}
    sql, params = non_privileged_edge_provenance_clause(
        edge_alias="e", policy_tag="owner_scoped", owner_user_id="A"
    )
    assert con.execute(f"SELECT e.edge_id FROM edges e WHERE TRUE{sql}", params).fetchall() == [("e",)]
    con.execute("UPDATE edges SET source_document_id='privateB' WHERE edge_id='e'")
    assert con.execute(f"SELECT e.edge_id FROM edges e WHERE TRUE{sql}", params).fetchall() == []


def test_edge_owner_and_both_endpoints(con):
    con.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [
        ("left", json.dumps({"source_document_id": "public"}), None),
        ("right", json.dumps({"source_document_id": "public"}), "B"),
    ])
    con.execute("INSERT INTO edges VALUES ('e', 'left', 'right', NULL, 'public', 'A')")
    sql, params = non_privileged_edge_provenance_clause(
        edge_alias="e", policy_tag="owner_scoped", owner_user_id="A"
    )
    assert con.execute(f"SELECT e.edge_id FROM edges e WHERE TRUE{sql}", params).fetchall() == []
    con.execute("UPDATE nodes SET owner_user_id='A' WHERE node_id='right'")
    assert con.execute(f"SELECT e.edge_id FROM edges e WHERE TRUE{sql}", params).fetchall() == [("e",)]
    con.execute("UPDATE edges SET owner_user_id='B' WHERE edge_id='e'")
    assert con.execute(f"SELECT e.edge_id FROM edges e WHERE TRUE{sql}", params).fetchall() == []


def test_static_alias_validation():
    for alias in ("n;DROP", "", "a.b", "td", "pa04_edge", "pa04_ref", "pa04_source_node"):
        with pytest.raises(ValueError):
            non_privileged_node_provenance_clause(node_alias=alias, owner_user_id=None)
        with pytest.raises(ValueError):
            non_privileged_edge_provenance_clause(edge_alias=alias, owner_user_id=None)


def test_alternate_static_alias(con):
    con.execute("INSERT INTO nodes VALUES ('visible', ?, NULL)", [json.dumps({"chunk_id": "cp"})])
    sql, params = non_privileged_node_provenance_clause(node_alias="other_node", owner_user_id=None)
    assert con.execute(
        f"SELECT other_node.node_id FROM nodes other_node WHERE TRUE{sql}", params
    ).fetchall() == [("visible",)]
    con.execute("INSERT INTO edges VALUES ('edge', 'visible', 'visible', NULL, 'public', NULL)")
    edge_sql, edge_params = non_privileged_edge_provenance_clause(
        edge_alias="other_edge", owner_user_id=None
    )
    assert con.execute(
        f"SELECT other_edge.edge_id FROM edges other_edge WHERE TRUE{edge_sql}", edge_params
    ).fetchall() == [("edge",)]
