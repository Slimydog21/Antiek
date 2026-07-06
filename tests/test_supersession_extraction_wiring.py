"""Detection-wiring tests (GF-5/GF-6 activation): the best-effort supersession
detection wired into the extraction write-path surfaces contradictions as review
candidates WITHOUT ever mutating an edge or breaking extraction.

Load-bearing invariants:
  1. Extraction reliability — a detection failure never propagates (empty batch,
     unknown edge id, or any detection error all degrade to "no candidate",
     never an exception out of the extraction path).
  2. Contradictions become candidates, not actions — detection writes
     supersession_candidates rows only; the edges table is byte-identical before
     and after. Only apply_review mutates an edge.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from processing.extraction.extract import _run_supersession_detection  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.ops import insert_edge, insert_node  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        yield p


def _seed_contradiction(p: str) -> str:
    """Seed S —is→ T1 (old) + S —is→ T2 (new); return the new edge_id."""
    with connect_write(p, purpose="test.seed") as con:
        s = insert_node(con, canonical_label="S", node_type="entity",
                        graph_scope="depth", investigation_id="inv-1")
        t1 = insert_node(con, canonical_label="T1", node_type="entity",
                         graph_scope="depth", investigation_id="inv-1")
        t2 = insert_node(con, canonical_label="T2", node_type="entity",
                         graph_scope="depth", investigation_id="inv-1")
        insert_edge(con, source_node_id=s, target_node_id=t1, relation="is",
                    source_tier=1, extraction_confidence=1.0,
                    graph_scope="depth", investigation_id="inv-1",
                    edge_id="e-old", valid_from=datetime(2020, 1, 1))
        insert_edge(con, source_node_id=s, target_node_id=t2, relation="is",
                    source_tier=1, extraction_confidence=1.0,
                    graph_scope="depth", investigation_id="inv-1",
                    edge_id="e-new", valid_from=datetime(2021, 1, 1))
    return "e-new"


def test_detection_writes_candidate_without_mutating_edges(db_path):
    new_edge_id = _seed_contradiction(db_path)
    with connect_write(db_path, purpose="test.snapshot") as con:
        before = con.execute("SELECT * FROM edges ORDER BY edge_id").fetchall()
    _run_supersession_detection(db_path, [new_edge_id])
    with connect_write(db_path, purpose="test.assert") as con:
        after = con.execute("SELECT * FROM edges ORDER BY edge_id").fetchall()
        rows = con.execute(
            "SELECT old_edge_id, new_edge_id, contradiction_type, status "
            "FROM supersession_candidates"
        ).fetchall()
    assert before == after  # invariant 2: no edge mutation
    assert rows == [("e-old", "e-new", "uncertainty", "open")]


def test_detection_is_noop_on_empty_batch(db_path):
    _run_supersession_detection(db_path, [])
    with connect_write(db_path, purpose="test.assert") as con:
        n = con.execute("SELECT count(*) FROM supersession_candidates").fetchone()[0]
    assert n == 0


def test_detection_never_raises_on_unknown_edge(db_path):
    # A bogus edge id must not propagate out of the extraction path.
    _run_supersession_detection(db_path, ["no-such-edge"])
    with connect_write(db_path, purpose="test.assert") as con:
        n = con.execute("SELECT count(*) FROM supersession_candidates").fetchone()[0]
    assert n == 0
