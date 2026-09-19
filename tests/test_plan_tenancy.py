from __future__ import annotations

from roles.cascade_planner.tenancy import (
    approve_plan_authorized,
    claim_plan_launch_authorized,
    is_plan_launch_claim_authorized,
    load_plan_authorized,
    save_plan_authorized,
)
from roles.cascade_planner.tree_contract import PlanNode, PlanTree
from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority


class _Embedding:
    dimension = 4

    def encode(self, _text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


def test_same_raw_plan_id_is_composite_and_session_identity_cannot_collide(
    tmp_path, monkeypatch
):
    events = tmp_path / "events"
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    ensure_initialized(db)
    alice = InvestigationAuthority("alice", "shared-plan", events)
    bob = InvestigationAuthority("bob", "shared-plan", events)
    initialize_composite_stream(alice)
    initialize_composite_stream(bob)

    def tree(owner: str) -> PlanTree:
        return PlanTree(
            PlanNode(
                "Same research problem",
                children=[PlanNode(f"Private leaf for {owner}")],
            )
        )

    con = connect_write(db, purpose="test_plan_tenancy")
    try:
        save_plan_authorized(con, alice, tree("alice"), embedding_provider=_Embedding())
        save_plan_authorized(con, bob, tree("bob"), embedding_provider=_Embedding())
        alice_tree = load_plan_authorized(con, alice)
        bob_tree = load_plan_authorized(con, bob)
        rows = con.execute(
            "SELECT plan_id, account_digest, investigation_digest "
            "FROM cascade_plan_authority WHERE plan_id = 'shared-plan'"
        ).fetchall()
    finally:
        con.close()

    assert alice_tree is not None and bob_tree is not None
    assert alice_tree.leaves[0].question == "Private leaf for alice"
    assert bob_tree.leaves[0].question == "Private leaf for bob"
    assert len(rows) == 2
    assert len({row[1] for row in rows}) == 2
    assert len({(row[1], row[2]) for row in rows}) == 2
    assert f"session-{alice.stream_key[:40]}" != f"session-{bob.stream_key[:40]}"


def test_launch_claim_freezes_approved_version_across_later_edit(tmp_path, monkeypatch):
    events = tmp_path / "events"
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    ensure_initialized(db)
    plan = InvestigationAuthority("alice", "plan-one", events)
    launch = InvestigationAuthority("alice", "session-one", events)
    initialize_composite_stream(plan)
    initialize_composite_stream(launch)
    original = PlanTree(PlanNode("Problem", children=[PlanNode("Approved leaf")]))

    con = connect_write(db, purpose="test_launch_claim")
    try:
        save_plan_authorized(con, plan, original, embedding_provider=_Embedding())
        approve_plan_authorized(
            con, plan, approver="alice", embedding_provider=_Embedding()
        )
        claimed = claim_plan_launch_authorized(con, plan, launch)
        edited = load_plan_authorized(con, plan)
        assert edited is not None
        assert edited.reword(edited.leaves[0].local_id, "Later edit")
        save_plan_authorized(con, plan, edited, embedding_provider=_Embedding())
        row = con.execute(
            "SELECT plan_version, tree_json FROM cascade_plan_launch_authority "
            "WHERE account_digest = ? AND launch_investigation_digest = ?",
            [plan.account_digest, launch.investigation_digest],
        ).fetchone()
        claim_valid = is_plan_launch_claim_authorized(con, plan, launch)
    finally:
        con.close()

    assert claimed.approval.is_launchable
    assert claim_valid is True
    assert row is not None and row[0] == claimed.approval.plan_version
    assert "Approved leaf" in row[1]
    assert "Later edit" not in row[1]
