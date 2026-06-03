"""Speak SPR-11 — the Biography TEMPLATE composition tests.

A biography is a TEMPLATE composing Research + Write + Speak over the ONE
graph, NOT a fifth product and NOT a fifth graph (master-spec §16). These
tests are the executable form of that decision:

  • test_biography_creates_no_new_store — THE §16 ONE-GRAPH GUARD. Named
    explicitly so a future refactor that smuggled in a separate biography
    store/graph would FAIL it. Asserts mechanically (not by code review)
    that composing a biography creates NO new DB table — in particular no
    `biography_*` table — and routes only through the shared substrate +
    the shared event funnel.
  • the three surfaces resolve to ONE identity (the investigation_id);
  • rigor #3 edge cases: empty Research, empty Speak, no research yet.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.event_log.events import trajectory
from substrate.graph.schema import init_database
from substrate.speak import biography_composition as bc
from substrate.speak.events import SPEAK_BIOGRAPHY_COMPOSED
from substrate.speak.schema import ensure_speak_schema


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-bio-comp-test-")
    events_dir = os.path.join(tmpdir, "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="bio_comp_test_setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path, events_dir


def _con(db):
    return connect_write(db, purpose="bio_comp_test")


def _all_tables(con) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main'"
    ).fetchall()
    return {r[0] for r in rows}


# ── THE ONE-GRAPH GUARD (the hardest invariant) ─────────────────────────────


def test_biography_creates_no_new_store(env):
    """§16 ONE-GRAPH GUARD. Composing a biography must NOT instantiate a
    separate biography store/graph/table. It routes through the shared
    substrate (the existing tables + the shared event funnel) only.

    This is the executable form of the template-not-silo decision
    (docs/decisions/spr-11-biography-template-not-graph.md). If a future
    change adds a `biography_*` table (or any new store) to hold the
    composition, this test FAILS — which is exactly where the reversal of
    the decision must surface.
    """
    db, _events_dir = env
    with _con(db) as con:
        before = _all_tables(con)
        comp = bc.create_biography(
            con, investigation_id="inv-bio-guard", subject_name="Grandma"
        )
        after = _all_tables(con)

    # 1. No new table of ANY kind was created by composing a biography.
    new_tables = after - before
    assert new_tables == set(), (
        f"composing a biography created new store(s): {new_tables}. A biography "
        "is a TEMPLATE over the existing tables, not a new store (§16)."
    )

    # 2. Specifically, NO biography_* table exists anywhere.
    assert not any(t.startswith("biography") for t in after), (
        "a biography_* table exists — the template-not-silo decision is violated."
    )

    # 3. The composition is held in the SHARED event funnel, not a store: the
    #    speak.biography.composed event lands in the investigation's trajectory
    #    (keyed on the investigation_id — the one-graph identity), carrying the
    #    three surface ids.
    events = trajectory("inv-bio-guard")
    composed = [e for e in events if e.get("action_type") == SPEAK_BIOGRAPHY_COMPOSED]
    assert len(composed) == 1, "exactly one composition link event expected in the shared log"
    payload = composed[0]["payload"]
    assert payload["investigation_id"] == "inv-bio-guard"
    assert payload["deliverable_id"] == comp.deliverable_id
    assert payload["project_id"] == comp.project_id


def test_three_surfaces_resolve_to_one_graph_identity(env):
    """The Research folder, the Write deliverable, and the Speak project all
    resolve to ONE identity (the investigation_id): the Write deliverable's
    research link == the investigation_id, and the Speak project is linked to
    the same composition (the shared event)."""
    db, _events_dir = env
    with _con(db) as con:
        comp = bc.create_biography(
            con, investigation_id="inv-one", subject_name="Dad"
        )
        # Write resolves to the same identity: investigation_root_id == investigation_id.
        root = con.execute(
            "SELECT investigation_root_id FROM deliverables WHERE deliverable_id = ?",
            [comp.deliverable_id],
        ).fetchone()[0]
        assert root == "inv-one" == comp.investigation_id

        # The Speak project is a real interview_projects + speak_projects row.
        proj = con.execute(
            "SELECT p.project_id FROM speak_projects p "
            "JOIN interview_projects ip ON ip.project_id = p.project_id "
            "WHERE p.project_id = ?",
            [comp.project_id],
        ).fetchone()
        assert proj is not None and proj[0] == comp.project_id

    # The composition event ties the Speak project to the SAME investigation id.
    events = trajectory("inv-one")
    composed = next(e for e in events if e.get("action_type") == SPEAK_BIOGRAPHY_COMPOSED)
    assert composed["payload"]["project_id"] == comp.project_id


def test_biography_requires_an_investigation(env):
    """A biography must thread on a real Research folder identity — the
    composition refuses an empty investigation_id rather than minting a
    second, orphan identity."""
    db, _ = env
    with _con(db) as con, pytest.raises(ValueError):
        bc.create_biography(con, investigation_id="", subject_name="X")


# ── rigor #3 — edge cases ────────────────────────────────────────────────────


def test_brand_new_biography_composes_empty_but_ready(env):
    """Edge case (a) + (c): a brand-new biography has NO interviews and NO
    research run yet. The composition still provisions the Write deliverable +
    the Speak project (empty-but-ready, not broken) and adds no claims; the
    Research folder is empty by construction (create_biography runs no research,
    it only references the investigation id)."""
    db, _ = env
    with _con(db) as con:
        comp = bc.create_biography(
            con, investigation_id="inv-empty", subject_name="Maria"
        )
        # Write scaffold present.
        assert con.execute(
            "SELECT count(*) FROM deliverables WHERE deliverable_id = ?",
            [comp.deliverable_id],
        ).fetchone()[0] == 1
        # Speak project present and EMPTY (no interviews/voices yet) — ready,
        # not broken.
        assert con.execute(
            "SELECT count(*) FROM interviews WHERE project_id = ?",
            [comp.project_id],
        ).fetchone()[0] == 0
        # The composition itself added no claims to the project either —
        # empty-but-ready, not broken.
        assert con.execute(
            "SELECT count(*) FROM speak_claims WHERE project_id = ?",
            [comp.project_id],
        ).fetchone()[0] == 0
        # The Research folder is empty BY CONSTRUCTION: create_biography only
        # references the investigation id (the shared identity) and runs no
        # research, so there is no research content yet — empty-but-present.
