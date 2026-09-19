from __future__ import annotations

import pytest

from roles.note_taker.distill_query import distillation_for_authorized
from runtime.db_lock import connect_write
from substrate.graph.insight_question import (
    promote_insight_authorized,
    promote_question_authorized,
)
from substrate.graph.ops import insert_edge_authorized
from substrate.graph.schema import init_database_at_path
from substrate.graph.tenancy import (
    GraphAuthorityConflict,
    GraphTenancyState,
    transition_graph_tenancy_state,
)
from substrate.investigation_streams import (
    InvestigationStreamUnbound,
    initialize_composite_stream,
)
from substrate.investigation_tenancy import InvestigationAuthority


@pytest.fixture
def graph_environment(tmp_path, monkeypatch):
    events = tmp_path / "events"
    events.mkdir()
    database = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(database))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(database))
    return events, database


def _enable_scoped_reads(database) -> None:
    with connect_write(str(database), purpose="test-enable-graph-shadow") as con:
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


def test_same_display_accounts_receive_disjoint_authorized_distillations(
    graph_environment,
):
    events, database = graph_environment
    alice = InvestigationAuthority("alice", "shared-display", root=events)
    bob = InvestigationAuthority("bob", "shared-display", root=events)
    initialize_composite_stream(alice)
    initialize_composite_stream(bob)

    shared_node_alice = promote_insight_authorized(
        alice,
        text="Identical private insight.",
        confidence="high",
        source_document_id="alice-private-source",
    )
    alice_only = promote_question_authorized(
        alice, text="What remains private to Alice?"
    )
    shared_node_bob = promote_insight_authorized(
        bob,
        text="Identical private insight.",
        confidence="low",
        source_document_id="bob-private-source",
    )
    bob_only = promote_question_authorized(bob, text="What remains private to Bob?")

    assert shared_node_alice == shared_node_bob
    with pytest.raises(GraphAuthorityConflict, match="state denies"):
        distillation_for_authorized(alice, db_path=str(database))
    _enable_scoped_reads(database)
    alice_view = distillation_for_authorized(alice, db_path=str(database))
    bob_view = distillation_for_authorized(bob, db_path=str(database))
    assert [node.node_id for node in alice_view.insights] == [shared_node_alice]
    assert [node.node_id for node in bob_view.insights] == [shared_node_bob]
    assert alice_view.insights[0].confidence == "high"
    assert alice_view.insights[0].source_document_id == "alice-private-source"
    assert bob_view.insights[0].confidence == "low"
    assert bob_view.insights[0].source_document_id == "bob-private-source"
    assert [node.node_id for node in alice_view.questions] == [alice_only]
    assert [node.node_id for node in bob_view.questions] == [bob_only]
    assert [node.text for node in alice_view.questions] == [
        "What remains private to Alice?"
    ]
    assert [node.text for node in bob_view.questions] == [
        "What remains private to Bob?"
    ]


def test_authorized_promotion_rejects_scalar_investigation_override(graph_environment):
    events, _database = graph_environment
    authority = InvestigationAuthority("alice", "expected", root=events)
    initialize_composite_stream(authority)

    with pytest.raises(TypeError, match="derives investigation_id"):
        promote_insight_authorized(
            authority,
            text="Cannot override authority.",
            investigation_id="foreign",
        )


def test_authorized_promotion_writes_disjoint_exact_provenance_edges(
    graph_environment,
):
    events, database = graph_environment
    alice = InvestigationAuthority("alice", "shared-display", root=events)
    bob = InvestigationAuthority("bob", "shared-display", root=events)
    initialize_composite_stream(alice)
    initialize_composite_stream(bob)
    with connect_write(str(database), purpose="test-seed-shared-claim") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('claim-public', 'Public claim', 'claim', 'depth')"
        )

    alice_node = promote_insight_authorized(
        alice, text="Same grounded insight.", supported_by=["claim-public"]
    )
    bob_node = promote_insight_authorized(
        bob, text="Same grounded insight.", supported_by=["claim-public"]
    )
    assert alice_node == bob_node

    con = connect_write(str(database), purpose="test-exact-edge-proof")
    try:
        rows = con.execute(
            "SELECT edge_id, account_digest, investigation_digest "
            "FROM edges WHERE source_node_id = ? ORDER BY account_digest",
            [alice_node],
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] != rows[1][0]
        assert {(row[1], row[2]) for row in rows} == {
            (alice.account_digest, alice.investigation_digest),
            (bob.account_digest, bob.investigation_digest),
        }

        alice_edge = next(row[0] for row in rows if row[1] == alice.account_digest)
        assert (
            insert_edge_authorized(
                con,
                alice,
                source_node_id=alice_node,
                target_node_id="claim-public",
                relation="supported_by",
                source_tier=3,
                extraction_confidence=0.5,
                graph_scope="depth",
                edge_id=alice_edge,
                on_conflict="ignore",
            )
            == alice_edge
        )
        with pytest.raises(GraphAuthorityConflict, match="replay conflicts"):
            insert_edge_authorized(
                con,
                alice,
                source_node_id=alice_node,
                target_node_id="claim-public",
                relation="supported_by",
                source_tier=3,
                extraction_confidence=0.9,
                graph_scope="depth",
                edge_id=alice_edge,
                on_conflict="ignore",
            )
    finally:
        con.close()


def test_authorized_promotion_requires_allocated_event_authority(graph_environment):
    events, _database = graph_environment
    authority = InvestigationAuthority("alice", "unbound", root=events)

    with pytest.raises(InvestigationStreamUnbound):
        promote_question_authorized(authority, text="Must not mutate the graph.")


def test_authorized_distillation_fails_closed_without_graph_allocation(
    graph_environment,
):
    events, database = graph_environment
    authority = InvestigationAuthority("alice", "events-only", root=events)
    initialize_composite_stream(authority)

    with pytest.raises(GraphAuthorityConflict, match="manifest"):
        distillation_for_authorized(authority, db_path=str(database))
