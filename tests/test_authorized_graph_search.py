from __future__ import annotations

from runtime.db_lock import connect_read, connect_write
from substrate.graph.insight_question import promote_insight_authorized
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search_nodes_by_label_authorized
from substrate.graph.tenancy import (
    GraphTenancyState,
    transition_graph_tenancy_state,
)
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority


def test_authorized_search_composes_membership_with_public_rights(tmp_path, monkeypatch):
    events = tmp_path / "events"
    events.mkdir()
    database = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(database))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(database))
    alice = InvestigationAuthority("alice", "shared-display", root=events)
    bob = InvestigationAuthority("bob", "shared-display", root=events)
    initialize_composite_stream(alice)
    initialize_composite_stream(bob)

    alice_node = promote_insight_authorized(alice, text="Alice private node")
    bob_node = promote_insight_authorized(bob, text="Bob private node")
    with connect_write(str(database), purpose="test-authorized-search-fixture") as con:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_tier, document_type, content_class) VALUES "
            "('public-doc', 1, 'paper', 'public_domain'), "
            "('restricted-doc', 2, 'book', 'personal_reading')"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('public-node', 'Public corpus node', 'claim', 'depth'), "
            "('restricted-node', 'Restricted foreign node', 'claim', 'depth')"
        )
        con.execute(
            "INSERT INTO edges "
            "(edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES "
            "('public-edge', 'public-node', 'public-node', 'supports', "
            "'public-doc', 1, 0.9, 'depth'), "
            "('restricted-edge', 'restricted-node', 'restricted-node', 'supports', "
            "'restricted-doc', 2, 0.9, 'depth')"
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.COPYING,
            desired=GraphTenancyState.SHADOW,
        )
        # Shared mutable storage cannot redefine Alice's private view/search key.
        con.execute(
            "UPDATE nodes SET canonical_label = 'Globally changed label' "
            "WHERE node_id = ?",
            [alice_node],
        )

    con = connect_read(str(database))
    try:
        alice_rows = search_nodes_by_label_authorized(con, alice, "node", limit=20)
        bob_rows = search_nodes_by_label_authorized(con, bob, "node", limit=20)
        alice_original = search_nodes_by_label_authorized(con, alice, "Alice private")
    finally:
        con.close()

    alice_ids = {row["node_id"] for row in alice_rows}
    bob_ids = {row["node_id"] for row in bob_rows}
    assert alice_ids == {alice_node, "public-node"}
    assert bob_ids == {bob_node, "public-node"}
    assert "restricted-node" not in alice_ids | bob_ids
    assert alice_original == [
        {"node_id": alice_node, "node_type": "insight", "label": "Alice private node"}
    ]
