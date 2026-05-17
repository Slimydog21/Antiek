"""Tests for middleware/backtest/ scaffolding (Sprint 5 day 2-3).

Coverage:

1. Pure projections turn DB-row tuples into dataclass records.
2. ``build_report`` assembles a ``BacktestReport`` with derived
   convenience counts.
3. ``backtest()`` raises ``NotImplementedError`` until the DB layer
   migrates — explicit safety so it can't be silently called against
   a half-built substrate.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.backtest import (  # noqa: E402
    ArchivedSynthesis,
    BacktestReport,
    ChunkTierChange,
    SupersededEdge,
    backtest,
    build_report,
    project_chunk_tier_changes,
    project_superseded_edges,
)


# ---------------------------------------------------------------------------
# 1. Pure row-tuple projections
# ---------------------------------------------------------------------------


def test_project_superseded_edges_handles_full_row():
    rows = [
        ("edge-1", "edge-2", "2026-01-05T00:00:00Z", "n-a", "n-b", "supports"),
        ("edge-3", None, "2026-02-01T00:00:00Z", "n-c", "n-d", "contradicts"),
    ]
    out = project_superseded_edges(rows)
    assert len(out) == 2
    assert out[0] == SupersededEdge(
        edge_id="edge-1", superseded_by="edge-2",
        valid_until="2026-01-05T00:00:00Z",
        source="n-a", target="n-b", relation="supports",
    )
    assert out[1].superseded_by is None


def test_project_chunk_tier_changes_handles_full_row():
    rows = [
        ("chunk-7", 1, 3, "newer source supersedes", "2026-03-01T00:00:00Z"),
    ]
    out = project_chunk_tier_changes(rows)
    assert out[0] == ChunkTierChange(
        chunk_id="chunk-7", original_tier=1, override_tier=3,
        reason="newer source supersedes", set_at="2026-03-01T00:00:00Z",
    )


def test_projections_return_empty_tuple_for_empty_input():
    assert project_superseded_edges([]) == ()
    assert project_chunk_tier_changes([]) == ()


# ---------------------------------------------------------------------------
# 2. build_report assembly
# ---------------------------------------------------------------------------


def test_build_report_assembles_full_shape():
    archive = ArchivedSynthesis(
        synthesis_id="syn-1",
        synthesis_timestamp="2026-01-01T00:00:00Z",
        target_question="will X succeed?",
        status="passed",
        implicit_recommendation="proceed",
        substrate_manifest={"edge": ["e-1"], "chunk": ["c-1"]},
        substrate_manifest_counts={
            "document": 4, "chunk": 12, "node": 8, "edge": 6,
        },
    )
    superseded = (
        SupersededEdge(
            edge_id="e-1", superseded_by="e-9",
            valid_until="2026-02-01T00:00:00Z",
            source="n-a", target="n-b", relation="supports",
        ),
    )
    demoted = (
        ChunkTierChange(
            chunk_id="c-1", original_tier=1, override_tier=3,
            reason="rebuttal landed", set_at="2026-03-01T00:00:00Z",
        ),
    )
    report = build_report(
        archive=archive,
        added_edges_since=5, superseded_edges_since=1,
        cited_edges_now_superseded=superseded,
        chunks_retired_downward=demoted,
        outcomes=[{"outcome_id": "o-1", "observer": "Faisal"}],
    )
    assert isinstance(report, BacktestReport)
    assert report.synthesis_id == "syn-1"
    assert report.added_edges_since == 5
    assert report.load_bearing_edges_invalidated == 1
    assert report.cited_chunks_demoted == 1
    assert report.outcomes_recorded == 1
    assert report.substrate_manifest_counts["chunk"] == 12


def test_build_report_zero_counts_when_nothing_changed():
    archive = ArchivedSynthesis(
        synthesis_id="s", synthesis_timestamp="t", target_question="q",
        status="passed", implicit_recommendation=None,
    )
    report = build_report(
        archive=archive,
        added_edges_since=0, superseded_edges_since=0,
        cited_edges_now_superseded=(),
        chunks_retired_downward=(),
        outcomes=[],
    )
    assert report.load_bearing_edges_invalidated == 0
    assert report.cited_chunks_demoted == 0
    assert report.outcomes_recorded == 0


# ---------------------------------------------------------------------------
# 3. backtest() entry point is wired (Sprint 10 day 4-5).
#    End-to-end DB tests live in tests/test_backtest_db.py.
# ---------------------------------------------------------------------------


def test_backtest_unknown_synthesis_raises_key_error():
    """Calling backtest with an unknown synthesis_id surfaces a
    KeyError so the operator sees the failure rather than getting
    an empty report."""
    import duckdb
    import tempfile, os
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "x.duckdb")
    init_database_at_path(db)
    con = duckdb.connect(db, read_only=True)
    try:
        with pytest.raises(KeyError, match="syn-unknown"):
            backtest(con, "syn-unknown")
    finally:
        con.close()
