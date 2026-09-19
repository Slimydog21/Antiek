from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from interfaces.research.api.synthesis_artifact import (
    resolve_synthesis_export_for_account,
)
from middleware.archive import (
    ArchiveInputs,
    SynthesisArchiveConflict,
    archive_synthesis_authorized,
    authorized_synthesis_id,
    load_synthesis_authorized,
)
from middleware.backtest.analysis import backtest_authorized
from middleware.backtest.db import load_outcomes_for_synthesis_authorized
from middleware.outcomes import record_outcome_payload_authorized
from runtime.db_lock import connect_read, connect_write
from substrate.attribution import compute_attribution_for_synthesis_authorized
from substrate.graph.insight_question import promote_insight_authorized
from substrate.graph.ops import insert_edge_authorized
from substrate.graph.schema import init_database_at_path
from substrate.graph.tenancy import GraphTenancyState, transition_graph_tenancy_state
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import account_policy_authority
from substrate.synthesis_event_outbox import reconcile_synthesis_events
from substrate.write.promote_context import (
    InvestigationPromotionRefusal,
    promote_investigation_to_deliverable_authorized,
)


def _inputs(**changes):
    values = {
        "target_question": "What is defensible?",
        "synthesis_timestamp": datetime(2026, 7, 15, tzinfo=UTC),
        "status": "passed",
        "implicit_recommendation": "proceed",
        "thesis_text": "A scoped synthesis.",
    }
    values.update(changes)
    return ArchiveInputs(**values)


@pytest.fixture
def synthesis_environment(tmp_path, monkeypatch):
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
    with connect_write(str(database), purpose="test-authorized-synthesis-fixture") as con:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_tier, document_type, content_class, owner_user_id, "
            "raw_text) VALUES "
            "('public-doc', 1, 'paper', 'public_domain', '__operator__', 'public'), "
            "('alice-doc', 2, 'book', 'user_owned', 'alice', 'alice'), "
            "('bob-doc', 2, 'book', 'user_owned', 'bob', 'bob')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) VALUES "
            "('public-chunk', 'public-doc', 0, 'public'), "
            "('alice-chunk', 'alice-doc', 0, 'alice'), "
            "('bob-chunk', 'bob-doc', 0, 'bob')"
        )
        for authority, document_id, chunk_id, text in (
            (alice, "public-doc", "public-chunk", "public"),
            (alice, "alice-doc", "alice-chunk", "alice"),
            (bob, "public-doc", "public-chunk", "public"),
            (bob, "bob-doc", "bob-chunk", "bob"),
        ):
            digest = hashlib.sha256(text.encode()).hexdigest()
            receipt = admit_staged_document(
                con,
                account_policy_authority(authority),
                investigation_digest=authority.investigation_digest,
                document_id=document_id,
                provenance_class="internal_operator",
                content_sha256=digest,
                at=datetime.now(UTC),
            )
            con.execute(
                "INSERT INTO legal_chunk_admissions "
                "(receipt_id, chunk_id, document_id, chunk_index, section_path, "
                "token_count, text_sha256) VALUES (?, ?, ?, 0, NULL, 0, ?)",
                [receipt.receipt_id, chunk_id, document_id, digest],
            )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('public-node', 'Public node', 'claim', 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('public-edge', 'public-node', 'public-node', 'supports', "
            "'public-doc', 1, 0.9, 'depth')"
        )
    alice_node = promote_insight_authorized(
        alice, text="Alice private synthesis node", source_document_id="alice-doc"
    )
    bob_node = promote_insight_authorized(
        bob, text="Bob private synthesis node", source_document_id="bob-doc"
    )
    with connect_write(str(database), purpose="test-authorized-synthesis-edges") as con:
        alice_edge = insert_edge_authorized(
            con,
            alice,
            source_node_id=alice_node,
            target_node_id=alice_node,
            relation="supports",
            source_tier=2,
            extraction_confidence=0.8,
            graph_scope="depth",
            source_document_id="alice-doc",
        )
        bob_edge = insert_edge_authorized(
            con,
            bob,
            source_node_id=bob_node,
            target_node_id=bob_node,
            relation="supports",
            source_tier=2,
            extraction_confidence=0.8,
            graph_scope="depth",
            source_document_id="bob-doc",
        )
    return database, alice, bob, alice_node, bob_node, alice_edge, bob_edge


def test_authorized_archive_scopes_identity_manifest_replay_and_load(
    synthesis_environment,
):
    database, alice, bob, alice_node, bob_node, alice_edge, bob_edge = (
        synthesis_environment
    )
    requested = _inputs(
        thesis={
            "thesis_components": [
                {
                    "claim": "Only admitted chunks may receive attribution.",
                    "confidence": "high",
                    "supporting_chunk_ids": [
                        "public-chunk",
                        "alice-chunk",
                        "bob-chunk",
                    ],
                }
            ]
        },
        document_ids=("public-doc", "alice-doc", "bob-doc"),
        chunk_ids=("public-chunk", "alice-chunk", "bob-chunk"),
        node_ids=("public-node", alice_node, bob_node),
        edge_ids=("public-edge", alice_edge, bob_edge),
    )
    with connect_write(str(database), purpose="test-authorized-synthesis-archive") as con:
        alice_id = archive_synthesis_authorized(
            con, alice, requested, logical_key="terminal"
        )
        assert (
            archive_synthesis_authorized(con, alice, requested, logical_key="terminal")
            == alice_id
        )
        bob_id = archive_synthesis_authorized(
            con, bob, _inputs(), logical_key="terminal"
        )
        assert alice_id != bob_id
        assert alice_id == authorized_synthesis_id(alice, "terminal")
        with pytest.raises(SynthesisArchiveConflict, match="different content"):
            archive_synthesis_authorized(
                con,
                alice,
                _inputs(target_question="Changed replay"),
                logical_key="terminal",
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


    con = connect_read(str(database))
    try:
        loaded = load_synthesis_authorized(con, alice, alice_id)
        assert loaded is not None
        assert loaded.substrate_manifest == {
            "document": ["alice-doc", "public-doc"],
            "chunk": ["alice-chunk", "public-chunk"],
            "node": [alice_node, "public-node"],
            "edge": [alice_edge, "public-edge"],
        }
        assert load_synthesis_authorized(con, alice, bob_id) is None
        assert load_synthesis_authorized(con, bob, alice_id) is None
        assert load_synthesis_authorized(con, bob, "syn-does-not-exist") is None
    finally:
        con.close()

    assert (
        resolve_synthesis_export_for_account(
            alice_id, "alice", db_path=str(database)
        )
        is not None
    )
    assert (
        resolve_synthesis_export_for_account(
            alice_id, "bob", db_path=str(database)
        )
        is None
    )
    with connect_write(str(database), purpose="test-authorized-outcome") as con:
        assert (
            record_outcome_payload_authorized(
                con,
                alice,
                outcome_id="out-alice",
                synthesis_id=alice_id,
                observer="alice",
                thesis_outcomes=[{"kind": "validated"}],
                falsification_outcomes=[],
                execution_risk_outcomes=[],
                decision_alignment=None,
                notes="Alice-owned grade",
            )
            == "out-alice"
        )
        with pytest.raises(KeyError, match="not found"):
            record_outcome_payload_authorized(
                con,
                bob,
                outcome_id="out-bob-foreign",
                synthesis_id=alice_id,
                observer="bob",
                thesis_outcomes=[],
                falsification_outcomes=[],
                execution_risk_outcomes=[],
                decision_alignment=None,
                notes=None,
            )
    con = connect_read(str(database))
    try:
        outcomes = load_outcomes_for_synthesis_authorized(con, alice, alice_id)
        assert [outcome["outcome_id"] for outcome in outcomes] == ["out-alice"]
        assert backtest_authorized(con, alice, alice_id).outcomes_recorded == 1
        with pytest.raises(KeyError, match="not found"):
            load_outcomes_for_synthesis_authorized(con, bob, alice_id)
        with pytest.raises(KeyError, match="not found"):
            backtest_authorized(con, bob, alice_id)
    finally:
        con.close()
    attribution = compute_attribution_for_synthesis_authorized(
        alice, alice_id, db_path=str(database)
    )
    assert set(attribution.option_a.shares) == {"public-doc", "alice-doc"}
    with connect_write(str(database), purpose="test-authorized-chunk-drift") as con:
        con.execute(
            "UPDATE chunks SET text = 'tampered after admission' "
            "WHERE chunk_id = 'alice-chunk'"
        )
        drift_id = archive_synthesis_authorized(
            con, alice, requested, logical_key="post-drift"
        )
    con = connect_read(str(database))
    try:
        drifted = load_synthesis_authorized(con, alice, drift_id)
        assert drifted is not None
        assert "alice-chunk" not in drifted.substrate_manifest["chunk"]
    finally:
        con.close()
    attribution_after_drift = compute_attribution_for_synthesis_authorized(
        alice, alice_id, db_path=str(database)
    )
    assert "alice-doc" not in attribution_after_drift.option_a.shares
    with pytest.raises(ValueError, match="not found"):
        compute_attribution_for_synthesis_authorized(
            bob, alice_id, db_path=str(database)
        )
    with connect_write(str(database), purpose="test-authorized-write-promotion") as con:
        bob_promotion = promote_investigation_to_deliverable_authorized(
            con, bob, deliverable_kind="research_memo"
        )
        assert isinstance(bob_promotion, InvestigationPromotionRefusal)
        assert bob_promotion.synthesis_id == bob_id
        promoted = promote_investigation_to_deliverable_authorized(
            con, alice, deliverable_kind="research_memo"
        )
        assert promoted is not None
        assert promoted.synthesis_id == drift_id
        assert set(
            row[0]
            for row in con.execute(
                "SELECT node_id FROM outline_blocks "
                "WHERE section_id = ? ORDER BY node_id",
                [promoted.section_id],
            ).fetchall()
        ) == {alice_node, "public-node"}


def test_authorized_archive_replay_binds_source_coverage(synthesis_environment):
    database, alice, *_rest = synthesis_environment
    coverage = {
        "schema_version": 1,
        "pack_schema_version": 2,
        "pack_content_hash": "a" * 64,
        "gather_plan_fingerprint": "b" * 64,
        "coverage": {
            "mode": "authorized_multi_source",
            "evidence_complete": True,
            "partial": False,
            "partial_leaf_investigation_ids": [],
            "sources": [
                {"source": source, "succeeded_leaves": 1, "total_leaves": 1}
                for source in ("exa", "parallel", "arxiv", "substack")
            ],
            "leaves": [{
                "investigation_id": "leaf",
                "sources": [
                    {"source": source, "status": "succeeded", "document_count": 1}
                    for source in ("exa", "parallel", "arxiv", "substack")
                ],
            }],
        },
    }
    inputs = _inputs(substrate=coverage)
    with connect_write(str(database), purpose="test-coverage-archive") as con:
        synthesis_id = archive_synthesis_authorized(
            con, alice, inputs, logical_key="coverage"
        )
        assert archive_synthesis_authorized(
            con, alice, inputs, logical_key="coverage"
        ) == synthesis_id
        changed = {**coverage, "pack_content_hash": "c" * 64}
        with pytest.raises(SynthesisArchiveConflict, match="different content"):
            archive_synthesis_authorized(
                con, alice, _inputs(substrate=changed), logical_key="coverage"
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
        loaded = load_synthesis_authorized(con, alice, synthesis_id)
    assert loaded is not None
    assert loaded.substrate == coverage


def test_disabled_event_persistence_rejects_before_archive_mutation(
    synthesis_environment, monkeypatch
):
    database, alice, *_rest = synthesis_environment
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    with connect_write(str(database), purpose="test-disabled-synthesis-events") as con:
        before = con.execute("SELECT count(*) FROM syntheses").fetchone()[0]
        with pytest.raises(RuntimeError, match="event persistence is disabled"):
            archive_synthesis_authorized(
                con, alice, _inputs(), logical_key="disabled-events"
            )
        after = con.execute("SELECT count(*) FROM syntheses").fetchone()[0]
        assert after == before


def test_archive_outbox_recovers_append_failure_without_duplicate_events(
    synthesis_environment, monkeypatch
):
    database, alice, bob, *_rest = synthesis_environment
    import substrate.synthesis_event_outbox as outbox

    original_append = outbox.append_event_once_authorized

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("simulated event store outage")

    monkeypatch.setattr(outbox, "append_event_once_authorized", fail_append)
    with connect_write(str(database), purpose="test-outbox-stage") as con:
        synthesis_id = archive_synthesis_authorized(
            con, alice, _inputs(), logical_key="outbox-recovery"
        )
        assert con.execute(
            "SELECT count(*) FROM syntheses WHERE synthesis_id = ?",
            [synthesis_id],
        ).fetchone() == (1,)
        assert con.execute(
            "SELECT delivery_state, count(*) FROM synthesis_event_outbox "
            "WHERE synthesis_id = ? GROUP BY delivery_state",
            [synthesis_id],
        ).fetchall() == [("pending", 2)]
        assert reconcile_synthesis_events(con, bob).attempted == 0

    monkeypatch.setattr(outbox, "append_event_once_authorized", original_append)
    with connect_write(str(database), purpose="test-outbox-reconcile") as con:
        result = reconcile_synthesis_events(con, alice)
        assert result.delivered == 2
        assert result.pending == 0
        assert reconcile_synthesis_events(con, alice).delivered == 0

    from substrate.event_log import trajectory_authorized

    rows = [
        row
        for row in trajectory_authorized(alice)
        if row.get("synthesis_id") == synthesis_id
    ]
    assert [row["action_type"] for row in rows] == [
        "synthesis.archived",
        "synthesis.substrate_manifest.written",
    ]


def test_pre_outbox_complete_archive_replay_adopts_existing_events(
    synthesis_environment,
):
    database, alice, *_rest = synthesis_environment
    inputs = _inputs()
    with connect_write(str(database), purpose="test-pre-outbox-archive") as con:
        synthesis_id = archive_synthesis_authorized(
            con, alice, inputs, logical_key="pre-outbox"
        )
        con.execute(
            "DELETE FROM synthesis_event_outbox WHERE synthesis_id = ?",
            [synthesis_id],
        )
        assert archive_synthesis_authorized(
            con, alice, inputs, logical_key="pre-outbox"
        ) == synthesis_id
        assert con.execute(
            "SELECT count(*) FROM synthesis_event_outbox WHERE synthesis_id = ?",
            [synthesis_id],
        ).fetchone() == (0,)

    from substrate.event_log import trajectory_authorized

    rows = [
        row
        for row in trajectory_authorized(alice)
        if row.get("synthesis_id") == synthesis_id
    ]
    assert len(rows) == 2


def test_writing_promotion_outbox_recovers_without_duplicate_events(
    synthesis_environment, monkeypatch
):
    database, alice, _bob, alice_node, *_rest = synthesis_environment
    import substrate.synthesis_event_outbox as outbox

    with connect_write(str(database), purpose="test-writing-outbox-archive") as con:
        synthesis_id = archive_synthesis_authorized(
            con,
            alice,
            _inputs(node_ids=("public-node", alice_node)),
            logical_key="writing-outbox-recovery",
        )

    original_append = outbox.append_event_once_authorized

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("simulated event store outage")

    monkeypatch.setattr(outbox, "append_event_once_authorized", fail_append)
    with connect_write(str(database), purpose="test-writing-outbox-stage") as con:
        promoted = promote_investigation_to_deliverable_authorized(
            con, alice, deliverable_kind="research_memo"
        )
        assert promoted is not None
        assert promoted.synthesis_id == synthesis_id
        assert con.execute(
            "SELECT delivery_state, count(*) FROM synthesis_event_outbox "
            "WHERE synthesis_id = ? AND event_json LIKE '%outline_block.placed%' "
            "GROUP BY delivery_state",
            [synthesis_id],
        ).fetchall() == [("pending", 2)]

    monkeypatch.setattr(outbox, "append_event_once_authorized", original_append)
    with connect_write(str(database), purpose="test-writing-outbox-reconcile") as con:
        assert reconcile_synthesis_events(con, alice).delivered == 2
        replay = promote_investigation_to_deliverable_authorized(
            con, alice, deliverable_kind="research_memo"
        )
        assert replay is not None
        assert replay.deliverable_id == promoted.deliverable_id
        assert reconcile_synthesis_events(con, alice).delivered == 0

    from substrate.event_log import trajectory_authorized

    rows = [
        row
        for row in trajectory_authorized(alice)
        if row.get("action_type") == "outline_block.placed"
        and row.get("synthesis_id") == synthesis_id
    ]
    assert len(rows) == 2


def test_outbox_quarantines_poison_intent_and_continues(
    synthesis_environment,
):
    database, alice, *_rest = synthesis_environment
    with connect_write(str(database), purpose="test-poison-outbox-stage") as con:
        synthesis_id = archive_synthesis_authorized(
            con, alice, _inputs(), logical_key="poison-recovery"
        )
        con.execute(
            "UPDATE synthesis_event_outbox SET event_fingerprint = 'corrupt' "
            "WHERE synthesis_id = ? AND sequence_no = 1",
            [synthesis_id],
        )
        con.execute(
            "UPDATE synthesis_event_outbox SET delivery_state = 'pending', "
            "delivered_at = NULL WHERE synthesis_id = ?",
            [synthesis_id],
        )
        result = reconcile_synthesis_events(con, alice)
        assert result.delivered == 1
        assert result.pending == 0
        assert con.execute(
            "SELECT terminal_failure, last_error_code FROM synthesis_event_outbox "
            "WHERE synthesis_id = ? AND sequence_no = 1",
            [synthesis_id],
        ).fetchone() == (True, "event_persistence_failed")


def test_disabled_event_persistence_rejects_before_writing_mutation(
    synthesis_environment, monkeypatch
):
    database, alice, _bob, alice_node, *_rest = synthesis_environment
    with connect_write(str(database), purpose="test-disabled-writing-archive") as con:
        archive_synthesis_authorized(
            con,
            alice,
            _inputs(node_ids=(alice_node,)),
            logical_key="disabled-writing",
        )
        before = con.execute("SELECT count(*) FROM deliverables").fetchone()[0]
        monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
        with pytest.raises(RuntimeError, match="event persistence is disabled"):
            promote_investigation_to_deliverable_authorized(
                con, alice, deliverable_kind="research_memo"
            )
        assert con.execute("SELECT count(*) FROM deliverables").fetchone()[0] == before
