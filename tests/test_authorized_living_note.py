from __future__ import annotations

import pytest

from roles.note_taker.distill_query import distillation_for_authorized
from roles.note_taker.living_note import (
    apply_refinement_authorized,
    challenge_note_authorized,
)
from runtime.db_lock import connect_read, connect_write
from substrate.event_log import trajectory_authorized
from substrate.graph.insight_question import promote_insight_authorized
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search_nodes_by_label_authorized
from substrate.graph.tenancy import GraphTenancyState, transition_graph_tenancy_state
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority


def _shadow(database) -> None:
    with connect_write(str(database), purpose="test-authorized-living-shadow") as con:
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


def test_refinement_is_copy_on_membership_and_sequence_deterministic(
    tmp_path, monkeypatch
):
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
    node_id = promote_insight_authorized(
        alice, text="Shared original note", source_document_id="alice-doc"
    )
    assert (
        promote_insight_authorized(
            bob, text="Shared original note", source_document_id="bob-doc"
        )
        == node_id
    )
    _shadow(database)

    winner = apply_refinement_authorized(
        alice, node_id, "Alice refined note", seq=10
    )
    loser = apply_refinement_authorized(
        alice, node_id, "Alice stale attempt", seq=9
    )
    foreign = apply_refinement_authorized(
        bob, "alice-only-node", "Must not appear", seq=11
    )
    assert winner.applied is True
    assert loser.superseded is True
    assert foreign.applied is False
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    with pytest.raises(RuntimeError, match="event persistence is disabled"):
        apply_refinement_authorized(
            alice, node_id, "Must roll back without audit", seq=20
        )
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED")

    alice_view = distillation_for_authorized(alice, db_path=str(database))
    bob_view = distillation_for_authorized(bob, db_path=str(database))
    assert alice_view.insights[0].text == "Alice refined note"
    assert alice_view.insights[0].refinement_count == 1
    assert bob_view.insights[0].text == "Shared original note"
    assert bob_view.insights[0].refinement_count == 0

    con = connect_read(str(database))
    try:
        assert con.execute(
            "SELECT canonical_label FROM nodes WHERE node_id = ?", [node_id]
        ).fetchone() == ("Shared original note",)
        assert search_nodes_by_label_authorized(con, alice, "Alice refined") == [
            {"node_id": node_id, "node_type": "insight", "label": "Alice refined note"}
        ]
        assert search_nodes_by_label_authorized(con, bob, "Alice refined") == []
    finally:
        con.close()
    assert [
        row["action_type"]
        for row in trajectory_authorized(alice)
        if row["action_type"] == "note.refined"
    ] == ["note.refined", "note.refined"]
    assert not any(
        row["action_type"] == "note.refined" for row in trajectory_authorized(bob)
    )


def test_unresolved_challenge_creates_only_authorized_question_and_edge(
    tmp_path, monkeypatch
):
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
    node_id = promote_insight_authorized(
        alice, text="Alice note", source_document_id="alice-doc"
    )
    promote_insight_authorized(
        bob, text="Bob note", source_document_id="bob-doc"
    )
    _shadow(database)

    result = challenge_note_authorized(
        alice,
        node_id,
        "What evidence would reverse this?",
        resolver=lambda _current, _challenge: None,
        seq=12,
    )
    assert result.escalated is True
    alice_view = distillation_for_authorized(alice, db_path=str(database))
    bob_view = distillation_for_authorized(bob, db_path=str(database))
    assert [question.node_id for question in alice_view.questions] == [
        result.escalated_question_id
    ]
    assert alice_view.questions[0].escalated is True
    assert bob_view.questions == []

    con = connect_read(str(database))
    try:
        edge = con.execute(
            "SELECT account_digest, investigation_digest FROM edges "
            "WHERE source_node_id = ? AND relation = 'asks_about'",
            [result.escalated_question_id],
        ).fetchone()
    finally:
        con.close()
    assert edge == (alice.account_digest, alice.investigation_digest)
