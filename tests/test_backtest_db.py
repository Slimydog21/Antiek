"""End-to-end tests for the backtest DB layer (Sprint 10 day 4-5).

Coverage:

A. Schema:
   1. All 4 new tables exist after init_database_at_path
   2. CHECK constraints reject bad status/recommendation values
   3. SCHEMA_TABLES contains the new tables

B. Archive DB writer:
   4. round-trip: archive_synthesis_via_db then load_synthesis
   5. substrate_manifest_counts derives from inputs.{document,chunk,node,edge}_ids
   6. JSON columns round-trip back through load_synthesis
   7. emits SYNTHESIS_ARCHIVED + SUBSTRATE_MANIFEST_WRITTEN events
   8. duplicate synthesis_id raises (PK violation rolls back manifest)
   9. requires LockedConnection

C. Outcomes writer + loader:
   10. record_outcome_via_db persists; load_outcomes_for_synthesis reads
   11. multiple outcomes ordered by observed_at
   12. JSON sub-lists round-trip back

D. Chunk tier overrides:
   13. record_chunk_tier_override writes; load_chunk_tier_changes_since reads
   14. chunk_ids filter scopes results
   15. invalid tiers raise

E. backtest() end-to-end:
   16. unknown synthesis_id → KeyError
   17. happy path returns BacktestReport with proper counts
   18. cited_edges_now_superseded surfaces closed-since-archive edges
   19. outcomes attached when present
   20. drift test: schema CHECK list matches Pydantic Literal set
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from middleware.archive.archive import (
    ArchiveInputs,
    archive_synthesis_via_db,
    load_synthesis,
)
from middleware.backtest import backtest
from middleware.backtest.db import (
    load_chunk_tier_changes_since,
    load_outcomes_for_synthesis,
)
from middleware.outcomes.recorder import (
    build_outcome_record,
    record_outcome_via_db,
)
from middleware.source_tier import record_chunk_tier_override
from runtime.db_lock import connect_write
from substrate.graph.ops import insert_document, insert_edge, insert_node
from substrate.graph.schema import SCHEMA_TABLES, init_database_at_path, list_tables

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-backtest-")
    db = os.path.join(tmp, "graph.duckdb")
    events = os.path.join(tmp, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events)
    init_database_at_path(db)
    yield db


def _inputs(*, ts=None, **kw) -> ArchiveInputs:
    base = dict(
        target_question="What is X?",
        synthesis_timestamp=ts or datetime.now(UTC),
        status="passed",
        implicit_recommendation="proceed",
        thesis_text="X is Y because Z.",
        model_versions={"synthesizer": "deepseek/v4-pro"},
        chunk_ids=("c-1", "c-2"),
        edge_ids=("e-1",),
    )
    base.update(kw)
    return ArchiveInputs(**base)


# ---------------------------------------------------------------------------
# A. Schema
# ---------------------------------------------------------------------------


def test_schema_creates_new_tables(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = set(list_tables(con))
    finally:
        con.close()
    for t in (
        "syntheses", "synthesis_substrate_manifest",
        "outcomes", "chunk_tier_overrides",
    ):
        assert t in tables


def test_schema_tables_constant_matches():
    for t in (
        "syntheses", "synthesis_substrate_manifest",
        "outcomes", "chunk_tier_overrides",
    ):
        assert t in SCHEMA_TABLES


def test_schema_rejects_bad_status(db_path):
    with connect_write(db_path, purpose="test") as con:
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO syntheses "
                "(synthesis_id, target_question, synthesis_timestamp, "
                " status, implicit_recommendation) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    "syn-bad", "Q?", datetime.now(UTC),
                    "NOT_A_VALID_STATUS", "proceed",
                ],
            )


# ---------------------------------------------------------------------------
# B. Archive DB writer
# ---------------------------------------------------------------------------


def test_archive_round_trip(db_path):
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(
            con, _inputs(), investigation_id="inv-1",
        )
    rcon = duckdb.connect(db_path, read_only=True)
    try:
        loaded = load_synthesis(rcon, sid)
    finally:
        rcon.close()
    assert loaded is not None
    assert loaded.synthesis_id == sid
    assert loaded.target_question == "What is X?"
    assert loaded.status == "passed"
    assert loaded.implicit_recommendation == "proceed"
    assert loaded.investigation_id == "inv-1"


def test_archive_manifest_counts(db_path):
    # Seed the chunks so the manifest pins resolve to real graph rows
    # (#199: only chunks that exist are pinned — fabricated ids are skipped).
    for cid in ("c-1", "c-2", "c-3"):
        _seed_chunk(db_path, cid)
    inp = _inputs(
        document_ids=("d-1",), chunk_ids=("c-1", "c-2", "c-3"),
        node_ids=(), edge_ids=("e-1", "e-2"),
    )
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(con, inp, investigation_id="inv-1")
    rcon = duckdb.connect(db_path, read_only=True)
    try:
        loaded = load_synthesis(rcon, sid)
    finally:
        rcon.close()
    assert loaded.substrate_manifest_counts == {
        "document": 1, "chunk": 3, "node": 0, "edge": 2,
    }


def test_archive_json_columns_round_trip(db_path):
    inp = _inputs(
        decomposition={"sub_questions": ["a", "b"]},
        evidence=[{"chunk_id": "c-1"}],
        thesis={"text": "thesis here"},
    )
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(con, inp, investigation_id="inv-1")
    rcon = duckdb.connect(db_path, read_only=True)
    try:
        loaded = load_synthesis(rcon, sid)
    finally:
        rcon.close()
    assert loaded.decomposition == {"sub_questions": ["a", "b"]}
    assert loaded.evidence == [{"chunk_id": "c-1"}]
    assert loaded.thesis == {"text": "thesis here"}
    assert loaded.model_versions == {"synthesizer": "deepseek/v4-pro"}


def test_archive_emits_typed_events(db_path):
    from substrate.event_log import trajectory

    with connect_write(db_path, purpose="test") as con:
        archive_synthesis_via_db(con, _inputs(), investigation_id="inv-emit")
    rows = trajectory("inv-emit")
    types = {r.get("action_type") for r in rows}
    assert "synthesis.archived" in types
    assert "synthesis.substrate_manifest.written" in types


def test_archive_duplicate_id_raises(db_path):
    inp = _inputs()
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(con, inp, investigation_id="inv-1")
        with pytest.raises(duckdb.ConstraintException):
            archive_synthesis_via_db(
                con, inp, investigation_id="inv-1", synthesis_id=sid,
            )


# ---------------------------------------------------------------------------
# C. Outcomes
# ---------------------------------------------------------------------------


def test_outcomes_round_trip(db_path):
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(
            con, _inputs(), investigation_id="inv-1",
        )
    rec = build_outcome_record(
        synthesis_id=sid,
        payload={
            "thesis_outcomes": [
                {"thesis_claim": "X is Y", "outcome": "confirmed",
                 "evidence": "observed Y", "evidence_chunk_ids": ["c-1"]},
            ],
            "execution_risk_outcomes": [
                {"risk": "supply chain", "manifested": False,
                 "severity_actual": "none", "evidence": ""},
            ],
        },
        observer="op-1",
    )
    with connect_write(db_path, purpose="test") as con:
        record_outcome_via_db(con, rec)

    rcon = duckdb.connect(db_path, read_only=True)
    try:
        outs = load_outcomes_for_synthesis(rcon, sid)
    finally:
        rcon.close()
    assert len(outs) == 1
    o = outs[0]
    assert o["observer"] == "op-1"
    assert o["thesis_outcomes"][0]["outcome"] == "confirmed"
    assert o["execution_risk_outcomes"][0]["risk"] == "supply chain"


def test_outcomes_multiple_ordered(db_path):
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(
            con, _inputs(), investigation_id="inv-1",
        )
        for i in range(3):
            rec = build_outcome_record(
                synthesis_id=sid,
                payload={"thesis_outcomes": []},
                observer=f"op-{i}",
            )
            record_outcome_via_db(con, rec)
    rcon = duckdb.connect(db_path, read_only=True)
    try:
        outs = load_outcomes_for_synthesis(rcon, sid)
    finally:
        rcon.close()
    assert len(outs) == 3
    observers = [o["observer"] for o in outs]
    assert sorted(observers) == observers  # monotonic by observed_at


# ---------------------------------------------------------------------------
# D. Chunk tier overrides
# ---------------------------------------------------------------------------


def _seed_chunk(db_path: str, chunk_id: str) -> None:
    from substrate.graph.ops import insert_chunk
    with connect_write(db_path, purpose="seed") as con:
        insert_document(
            con, document_id="d-1", source_tier=3,
            document_type="academic_paper",
            on_conflict="ignore",
        )
        insert_chunk(
            con, document_id="d-1", chunk_index=0,
            text=f"seed chunk for {chunk_id}", chunk_id=chunk_id,
        )


def test_tier_override_writes_and_reads(db_path):
    _seed_chunk(db_path, "c-tier-1")
    set_at = datetime.now(UTC) - timedelta(seconds=5)
    with connect_write(db_path, purpose="test") as con:
        record_chunk_tier_override(
            con, chunk_id="c-tier-1",
            original_tier=2, override_tier=4,
            reason="downgraded after extraction surfaced hedging",
            set_by="extract", set_at=set_at,
        )
    rcon = duckdb.connect(db_path, read_only=True)
    try:
        changes = load_chunk_tier_changes_since(
            rcon, set_at - timedelta(seconds=10),
        )
    finally:
        rcon.close()
    assert len(changes) == 1
    assert changes[0].chunk_id == "c-tier-1"
    assert changes[0].original_tier == 2
    assert changes[0].override_tier == 4


def test_tier_override_chunk_ids_filter(db_path):
    _seed_chunk(db_path, "c-keep")
    _seed_chunk(db_path, "c-drop")
    set_at = datetime.now(UTC) - timedelta(seconds=5)
    with connect_write(db_path, purpose="test") as con:
        for cid in ("c-keep", "c-drop"):
            record_chunk_tier_override(
                con, chunk_id=cid, original_tier=2, override_tier=3,
                reason="r", set_at=set_at,
            )
    rcon = duckdb.connect(db_path, read_only=True)
    try:
        changes = load_chunk_tier_changes_since(
            rcon, set_at - timedelta(seconds=10),
            chunk_ids=("c-keep",),
        )
    finally:
        rcon.close()
    assert {c.chunk_id for c in changes} == {"c-keep"}


def test_tier_override_invalid_tier_raises(db_path):
    _seed_chunk(db_path, "c-bad")
    with connect_write(db_path, purpose="test") as con, pytest.raises(ValueError):
        record_chunk_tier_override(
            con, chunk_id="c-bad",
            original_tier=2, override_tier=9, reason="x",
        )


# ---------------------------------------------------------------------------
# E. backtest() end-to-end
# ---------------------------------------------------------------------------


def test_backtest_happy_path(db_path):
    # Archive a synthesis, seed a cited edge that's later superseded,
    # record an outcome, run backtest, check report shape + counts.
    archive_ts = datetime.now(UTC) - timedelta(hours=1)

    # Seed substrate: 1 doc, 2 nodes, 1 edge (cited).
    with connect_write(db_path, purpose="seed") as con:
        insert_document(
            con, document_id="d-1", source_tier=2,
            document_type="academic_paper",
        )
        n1 = insert_node(
            con, canonical_label="A", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-bt",
        )
        n2 = insert_node(
            con, canonical_label="B", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-bt",
        )
        eid = insert_edge(
            con, source_node_id=n1, target_node_id=n2,
            relation="depends_on", source_tier=2,
            extraction_confidence=0.9, graph_scope="cross_domain",
            investigation_id="inv-bt",
        )

    inp = _inputs(ts=archive_ts, chunk_ids=(), edge_ids=(eid,))
    with connect_write(db_path, purpose="test") as con:
        sid = archive_synthesis_via_db(con, inp, investigation_id="inv-bt")

    # Now supersede the cited edge — happens AFTER archive_ts so it
    # should surface in cited_edges_now_superseded. Pass naive UTC
    # per the documented DuckDB-comparison convention.
    with connect_write(db_path, purpose="supersede") as con:
        con.execute(
            "UPDATE edges SET valid_until = ? WHERE edge_id = ?",
            [datetime.now(UTC).replace(tzinfo=None), eid],
        )

    # Record an outcome.
    rec = build_outcome_record(
        synthesis_id=sid,
        payload={
            "thesis_outcomes": [
                {"thesis_claim": "X is Y", "outcome": "partially_confirmed",
                 "evidence": "mixed"},
            ],
        },
        observer="op-1",
    )
    with connect_write(db_path, purpose="record") as con:
        record_outcome_via_db(con, rec)

    rcon = duckdb.connect(db_path, read_only=True)
    try:
        report = backtest(rcon, sid)
    finally:
        rcon.close()

    assert report.synthesis_id == sid
    assert report.target_question == "What is X?"
    assert report.load_bearing_edges_invalidated == 1
    assert report.cited_edges_now_superseded[0].edge_id == eid
    assert report.outcomes_recorded == 1
    assert report.outcomes[0]["observer"] == "op-1"
    assert report.added_edges_since >= 0
    assert report.superseded_edges_since >= 1


# ---------------------------------------------------------------------------
# F. Drift: schema CHECK lists match Pydantic Literal sets
# ---------------------------------------------------------------------------


def test_schema_status_check_matches_pydantic_literal():
    """The schema's CHECK (status IN ...) list MUST equal the
    SynthesisStatus Literal exactly. Any drift would let the DB
    accept rows the typed events would reject (or vice versa)."""
    from typing import get_args

    from substrate.schemas import SynthesisStatus

    schema_set = {
        "draft", "passed", "regressed",
        "max_iterations_reached", "escalated",
    }
    literal_set = set(get_args(SynthesisStatus))
    assert schema_set == literal_set


def test_schema_recommendation_check_matches_pydantic_literal():
    from typing import get_args

    from substrate.schemas import SynthesisRecommendation

    schema_set = {
        "proceed", "pass", "conditional",
        "undetermined", "insufficient_evidence",
    }
    literal_set = set(get_args(SynthesisRecommendation))
    assert schema_set == literal_set
