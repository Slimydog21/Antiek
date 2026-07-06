"""Detector tests (SPR-02 M2): contradictions become candidates, never edge mutations.

The load-bearing assertion is that ``detect_recent`` / ``detect_for_edge`` leave
the ``edges`` table byte-identical — the "contradictions become tasks, not
actions" posture, checked mechanically rather than trusted.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from middleware.supersession.db import (  # noqa: E402
    classify_contradiction,
    detect_for_edge,
    detect_recent,
)
from middleware.supersession.supersession import (  # noqa: E402
    DEFAULT_UNCLASSIFIED_VERDICT,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.ops import insert_edge, insert_node  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        yield p


def _seed_nodes(con):
    s = insert_node(con, canonical_label="S", node_type="entity",
                    graph_scope="depth", investigation_id="inv-1")
    t1 = insert_node(con, canonical_label="T1", node_type="entity",
                     graph_scope="depth", investigation_id="inv-1")
    t2 = insert_node(con, canonical_label="T2", node_type="entity",
                     graph_scope="depth", investigation_id="inv-1")
    return s, t1, t2


def _edge(con, src, tgt, eid, vf):
    return insert_edge(
        con, source_node_id=src, target_node_id=tgt, relation="is",
        source_tier=1, extraction_confidence=1.0, graph_scope="depth",
        investigation_id="inv-1", edge_id=eid, valid_from=vf,
    )


def _edges(con):
    return con.execute("SELECT * FROM edges ORDER BY edge_id").fetchall()


def test_contradiction_becomes_one_candidate_no_edge_mutation(db_path):
    with connect_write(db_path, purpose="test") as con:
        s, t1, t2 = _seed_nodes(con)
        _edge(con, s, t1, "e-old", datetime(2020, 1, 1))
        _edge(con, s, t2, "e-new", datetime(2021, 1, 1))
        before = _edges(con)
        written = detect_recent(con)
        after = _edges(con)
        rows = con.execute(
            "SELECT old_edge_id, new_edge_id, contradiction_type, status "
            "FROM supersession_candidates"
        ).fetchall()
    assert len(written) == 1
    assert before == after  # THE no-auto-mutation invariant, mechanically checked
    assert rows == [("e-old", "e-new", "uncertainty", "open")]


def test_detect_is_idempotent_on_the_pair(db_path):
    with connect_write(db_path, purpose="test") as con:
        s, t1, t2 = _seed_nodes(con)
        _edge(con, s, t1, "e-old", datetime(2020, 1, 1))
        _edge(con, s, t2, "e-new", datetime(2021, 1, 1))
        first = detect_recent(con)
        second = detect_recent(con)
    assert len(first) == 1
    assert second == []  # open candidate already exists → no duplicate


def test_no_candidate_when_conflicting_edge_is_closed(db_path):
    with connect_write(db_path, purpose="test") as con:
        s, t1, t2 = _seed_nodes(con)
        _edge(con, s, t1, "e-1", datetime(2020, 1, 1))
        _edge(con, s, t2, "e-2", datetime(2021, 1, 1))
        con.execute(
            "UPDATE edges SET valid_until = ? WHERE edge_id = 'e-2'",
            [datetime.now(UTC)],
        )
        written = detect_recent(con)
    assert written == []  # e-2 is no longer valid → no live contradiction


def test_detect_for_edge_scopes_to_one_edge(db_path):
    with connect_write(db_path, purpose="test") as con:
        s, t1, t2 = _seed_nodes(con)
        _edge(con, s, t1, "e-old", datetime(2020, 1, 1))
        _edge(con, s, t2, "e-new", datetime(2021, 1, 1))
        cid = detect_for_edge(con, "e-new")
        n = con.execute(
            "SELECT count(*) FROM supersession_candidates"
        ).fetchone()[0]
    assert cid is not None
    assert n == 1


def test_classify_default_is_uncertainty():
    v = classify_contradiction("a", "b")
    assert v is DEFAULT_UNCLASSIFIED_VERDICT
    assert v.contradiction_type == "uncertainty"


def test_detect_requires_locked_connection(db_path):
    raw = duckdb.connect(db_path)
    try:
        with pytest.raises(TypeError):
            detect_recent(raw)
    finally:
        raw.close()
