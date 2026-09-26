"""The bulk cursor is a versioned part of the exported graph database."""

from __future__ import annotations

from datetime import date, datetime

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph import schema


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    schema.init_database_at_path(path)
    return path


def _row(**changes):
    row = {
        "stream_id": "arxiv_bulk",
        "cursor_schema_version": 1,
        "parser_version": 1,
        "generation_id": "generation-1",
        "source_sha256": "a" * 64,
        "source_size_bytes": 100,
        "source_format": "jsonl",
        "source_encoding": "utf-8",
        "source_path": "/snapshot/arxiv.jsonl",
        "mode": "incremental",
        "tail_enabled": True,
        "from_date": None,
        "until_date": None,
        "metadata_prefix": "arXiv",
        "phase": "bulk",
        "next_byte_offset": 0,
        "physical_line_count": 0,
        "selected_record_count": 0,
        "bulk_t1_events": 0,
        "bulk_t2_events": 0,
        "bulk_t3_events": 0,
        "bulk_ambiguous_events": 0,
        "bulk_deleted_events": 0,
        "bulk_max_datestamp": None,
        "completed_high_water": None,
        "completed_generation_id": None,
        "completed_at": None,
        "completed_bulk_sha256": None,
        "completed_tail_bound": None,
        "completed_census_json": None,
    }
    row.update(changes)
    return row


def _insert(con, **changes):
    row = _row(**changes)
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    con.execute(
        f"INSERT INTO arxiv_bulk_progress ({columns}) VALUES ({placeholders})",
        list(row.values()),
    )


def test_table_is_registered_and_repeated_init_keeps_cursor(db_path):
    assert "arxiv_bulk_progress" in schema.SCHEMA_TABLES
    with connect_write(db_path, purpose="test_arxiv_progress") as con:
        _insert(con, next_byte_offset=42, physical_line_count=2, bulk_t3_events=1)
        schema.init_database(con)
        assert con.execute(
            "SELECT next_byte_offset, physical_line_count, bulk_t3_events "
            "FROM arxiv_bulk_progress"
        ).fetchone() == (42, 2, 1)
        progress = schema.load_arxiv_bulk_progress(con)
        assert progress is not None
        assert progress["next_byte_offset"] == 42


def test_boundary_reader_rejects_unknown_version_and_bad_event_provenance(db_path):
    with connect_write(db_path, purpose="test_arxiv_progress") as con:
        assert schema.load_arxiv_bulk_progress(con) is None
        _insert(con)
        persisted = schema.load_arxiv_bulk_progress(con)
        assert persisted is not None
        with pytest.raises(schema.SchemaCorruptionError, match="unknown cursor"):
            schema.decode_arxiv_bulk_progress_row(
                {**persisted, "cursor_schema_version": 2}
            )
        with pytest.raises(schema.SchemaCorruptionError, match="source digest"):
            schema.decode_arxiv_bulk_progress_row(
                {**persisted, "source_sha256": "f" * 63}
            )
        with pytest.raises(schema.SchemaCorruptionError, match="incomplete prior"):
            schema.decode_arxiv_bulk_progress_row(
                {**persisted, "completed_at": datetime(2025, 1, 2)}
            )


def test_boundary_reader_refuses_malformed_census_json(db_path):
    with connect_write(db_path, purpose="test_arxiv_progress") as con:
        _insert(
            con,
            phase="complete",
            next_byte_offset=100,
            completed_generation_id="generation-1",
            completed_at=datetime(2025, 1, 2),
            completed_bulk_sha256="a" * 64,
            completed_census_json="{malformed}",
        )
        with pytest.raises(schema.SchemaCorruptionError, match="event census JSON"):
            schema.load_arxiv_bulk_progress(con)


@pytest.mark.parametrize(
    "bad",
    [
        {"cursor_schema_version": 2},
        {"parser_version": 2},
        {"source_sha256": "a" * 63},
        {"source_size_bytes": -1},
        {"source_format": "gzip"},
        {"source_encoding": "latin-1"},
        {"mode": "oai"},
        {"phase": "unknown"},
        {"next_byte_offset": -1},
        {"next_byte_offset": 101},
        {"physical_line_count": -1},
        {"selected_record_count": -1},
        {"bulk_t1_events": -1},
        {"from_date": date(2025, 1, 2), "until_date": date(2025, 1, 1)},
        {"completed_generation_id": "old"},
        {"phase": "complete"},
        {"phase": "tail", "next_byte_offset": 99},
    ],
)
def test_malformed_progress_refused_by_database(db_path, bad):
    with (
        connect_write(db_path, purpose="test_arxiv_progress") as con,
        pytest.raises(duckdb.ConstraintException),
    ):
        _insert(con, **bad)


def test_completed_generation_survives_new_bulk_generation(db_path):
    completed = {
        "completed_high_water": date(2025, 1, 1),
        "completed_generation_id": "generation-1",
        "completed_at": datetime(2025, 1, 2),
        "completed_bulk_sha256": "a" * 64,
        "completed_tail_bound": date(2025, 1, 1),
        "completed_census_json": '{"kind":"event_counts"}',
    }
    with connect_write(db_path, purpose="test_arxiv_progress") as con:
        _insert(con, phase="complete", next_byte_offset=100, **completed)
        con.execute(
            "UPDATE arxiv_bulk_progress SET generation_id = 'generation-2', "
            "phase = 'bulk', source_sha256 = ?, next_byte_offset = 0, "
            "physical_line_count = 0, selected_record_count = 0",
            ["b" * 64],
        )
        assert con.execute(
            "SELECT completed_generation_id, completed_high_water, phase "
            "FROM arxiv_bulk_progress"
        ).fetchone() == ("generation-1", date(2025, 1, 1), "bulk")


def test_in_progress_generation_cannot_reuse_completed_identity(db_path):
    completed = {
        "completed_generation_id": "generation-1",
        "completed_at": datetime(2025, 1, 2),
        "completed_bulk_sha256": "a" * 64,
        "completed_census_json": '{"kind":"event_counts"}',
    }
    with (
        connect_write(db_path, purpose="test_arxiv_progress") as con,
        pytest.raises(duckdb.ConstraintException),
    ):
        _insert(con, phase="bulk", **completed)


def test_populated_wrong_shape_fails_closed(db_path):
    with connect_write(db_path, purpose="test_arxiv_progress") as con:
        con.execute("DROP TABLE arxiv_bulk_progress")
        con.execute("CREATE TABLE arxiv_bulk_progress (stream_id VARCHAR PRIMARY KEY)")
        con.execute("INSERT INTO arxiv_bulk_progress VALUES ('arxiv_bulk')")
        with pytest.raises(schema.SchemaCorruptionError, match="populated partial V22"):
            schema.init_database(con)
