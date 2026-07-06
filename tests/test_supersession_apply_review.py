"""apply_review tests (SPR-02 M3): the only edge-mutating path, one per decision.

Each decision is exercised on a fresh db seeded with one detected contradiction
(e-old @2020, e-new @2021). Asserts the exact edge effect, the candidate marked
reviewed, single-writer enforcement, and that a re-apply cannot double-mutate.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from middleware.supersession.apply import apply_review  # noqa: E402
from middleware.supersession.db import detect_recent  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.ops import insert_edge, insert_node  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        yield p


def _seed_and_detect(db_path):
    """Seed one contradiction and return its candidate_id."""
    with connect_write(db_path, purpose="test") as con:
        s = insert_node(con, canonical_label="S", node_type="entity",
                        graph_scope="depth", investigation_id="inv-1")
        t1 = insert_node(con, canonical_label="T1", node_type="entity",
                         graph_scope="depth", investigation_id="inv-1")
        t2 = insert_node(con, canonical_label="T2", node_type="entity",
                         graph_scope="depth", investigation_id="inv-1")
        for tgt, eid, vf in (
            (t1, "e-old", datetime(2020, 1, 1)),
            (t2, "e-new", datetime(2021, 1, 1)),
        ):
            insert_edge(con, source_node_id=s, target_node_id=tgt, relation="is",
                        source_tier=1, extraction_confidence=1.0, graph_scope="depth",
                        investigation_id="inv-1", edge_id=eid, valid_from=vf)
        written = detect_recent(con)
    assert len(written) == 1
    return written[0]


def _vu(con, eid):
    return con.execute(
        "SELECT valid_until FROM edges WHERE edge_id = ?", [eid]
    ).fetchone()[0]


def _superseded(con, eid):
    return con.execute(
        "SELECT superseded_by FROM edges WHERE edge_id = ?", [eid]
    ).fetchone()[0]


def _cand(con, cid):
    return con.execute(
        "SELECT status, decision, reviewer FROM supersession_candidates "
        "WHERE candidate_id = ?",
        [cid],
    ).fetchone()


def _edges(con):
    return con.execute("SELECT * FROM edges ORDER BY edge_id").fetchall()


def test_apply_supersession_closes_old_points_to_new(db_path):
    cid = _seed_and_detect(db_path)
    with connect_write(db_path, purpose="test") as con:
        apply_review(con, cid, "apply_supersession", "op", "reviewed it")
        assert _vu(con, "e-old") is not None
        assert _superseded(con, "e-old") == "e-new"
        assert _vu(con, "e-new") is None  # the surviving edge stays valid
        assert _cand(con, cid) == ("reviewed", "apply_supersession", "op")


def test_dismiss_new_closes_new_only(db_path):
    cid = _seed_and_detect(db_path)
    with connect_write(db_path, purpose="test") as con:
        apply_review(con, cid, "dismiss_new", "op")
        assert _vu(con, "e-new") is not None
        assert _vu(con, "e-old") is None
        assert _superseded(con, "e-new") is None
        assert _cand(con, cid)[0] == "reviewed"


def test_dismiss_old_closes_old_only(db_path):
    cid = _seed_and_detect(db_path)
    with connect_write(db_path, purpose="test") as con:
        apply_review(con, cid, "dismiss_old", "op")
        assert _vu(con, "e-old") is not None
        assert _vu(con, "e-new") is None
        assert _superseded(con, "e-old") is None  # dismissal, not supersession
        assert _cand(con, cid)[0] == "reviewed"


def test_coexist_leaves_edges_untouched(db_path):
    cid = _seed_and_detect(db_path)
    with connect_write(db_path, purpose="test") as con:
        before = _edges(con)
        apply_review(con, cid, "coexist", "op")
        after = _edges(con)
        assert before == after  # no edge mutation
        assert _cand(con, cid) == ("reviewed", "coexist", "op")


def test_requires_locked_connection(db_path):
    cid = _seed_and_detect(db_path)
    raw = duckdb.connect(db_path)
    try:
        with pytest.raises(TypeError):
            apply_review(raw, cid, "coexist", "op")
    finally:
        raw.close()


def test_reapply_raises_and_does_not_double_mutate(db_path):
    cid = _seed_and_detect(db_path)
    with connect_write(db_path, purpose="test") as con:
        apply_review(con, cid, "apply_supersession", "op")
        vu_first = _vu(con, "e-old")
        with pytest.raises(ValueError):
            apply_review(con, cid, "dismiss_new", "op")
        assert _vu(con, "e-old") == vu_first  # unchanged by the refused re-apply
        assert _vu(con, "e-new") is None       # never closed by the refused dismiss


def test_invalid_decision_raises(db_path):
    cid = _seed_and_detect(db_path)
    with connect_write(db_path, purpose="test") as con, pytest.raises(ValueError):
        apply_review(con, cid, "NOT_A_DECISION", "op")


def test_unknown_candidate_raises(db_path):
    with connect_write(db_path, purpose="test") as con, pytest.raises(ValueError):
        apply_review(con, "no-such-candidate", "coexist", "op")
