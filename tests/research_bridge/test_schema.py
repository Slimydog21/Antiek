"""Schema-application tests for substrate/research_bridge.

These test the lowest-level invariants: the SQL applies cleanly, the
expected tables exist with the expected columns, and re-applying the
schema is a no-op.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.research_bridge.schema import (
    init_research_bridge,
    init_research_bridge_at_path,
    list_research_bridge_tables,
)


def test_init_creates_expected_tables(tmp_db_with_bridge: Path) -> None:
    import duckdb

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        tables = set(list_research_bridge_tables(con))
    finally:
        con.close()

    assert tables == {
        "research_pastes",
        "research_paste_events",
        "research_paste_open_questions",
        "research_paste_insights",
        "research_paste_extractions",
        "research_gap_runs",
        "research_gap_clusters",
        "research_gap_cluster_questions",
        "research_gap_prompts",
        "research_gap_prompt_answers",
        "research_gap_prompt_signals",
    }


def test_init_is_idempotent(tmp_db_with_bridge: Path) -> None:
    """Re-applying the schema on an already-initialized DB is a no-op."""
    init_research_bridge_at_path(str(tmp_db_with_bridge))
    init_research_bridge_at_path(str(tmp_db_with_bridge))

    import duckdb

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        tables = set(list_research_bridge_tables(con))
    finally:
        con.close()

    assert tables == {
        "research_pastes",
        "research_paste_events",
        "research_paste_open_questions",
        "research_paste_insights",
        "research_paste_extractions",
        "research_gap_runs",
        "research_gap_clusters",
        "research_gap_cluster_questions",
        "research_gap_prompts",
        "research_gap_prompt_answers",
        "research_gap_prompt_signals",
    }


def test_init_requires_locked_connection(tmp_path: Path) -> None:
    """init_research_bridge refuses a raw DuckDB connection."""
    import duckdb

    db = tmp_path / "raw.duckdb"
    raw_con = duckdb.connect(str(db))
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            init_research_bridge(raw_con)  # type: ignore[arg-type]
    finally:
        raw_con.close()


def test_research_pastes_columns(tmp_db_with_bridge: Path) -> None:
    """The columns we depend on are present with sensible types."""
    import duckdb

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        rows = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'research_pastes' ORDER BY ordinal_position"
        ).fetchall()
    finally:
        con.close()

    cols = {name: typ for name, typ in rows}
    expected = {
        "document_id", "source", "source_confidence", "raw_sha256",
        "paste_byte_length", "parser_version", "operator_label",
        "session_id", "pasted_at",
    }
    assert expected.issubset(cols.keys()), (
        f"missing columns: {expected - cols.keys()}"
    )


def test_research_paste_events_columns(tmp_db_with_bridge: Path) -> None:
    import duckdb

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        rows = con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'research_paste_events' ORDER BY ordinal_position"
        ).fetchall()
    finally:
        con.close()

    cols = {r[0] for r in rows}
    assert {
        "event_id", "document_id", "occurred_at", "paste_byte_length",
        "raw_sha256", "source", "call_site",
    }.issubset(cols)


def test_research_paste_open_questions_columns(tmp_db_with_bridge: Path) -> None:
    import duckdb

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        rows = con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'research_paste_open_questions' "
            "ORDER BY ordinal_position"
        ).fetchall()
    finally:
        con.close()

    cols = {r[0] for r in rows}
    assert {
        "question_id", "document_id", "summary", "quote",
        "quote_start_offset", "quote_end_offset", "llm_confidence",
        "extractor_version", "model_id", "extracted_at",
    }.issubset(cols)
