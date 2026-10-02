"""Equivalence gate for the batched bulk persist path.

The bulk sync's per-record UPDATE pays DuckDB plan-time foreign-key constraint
binding once per statement (~100 ms/statement on the production catalog, whose
stored FK constraints cost ~11-12 ms per plan each). The batched sibling issues
ONE update and ONE insert statement per slice. This test proves the batched
path lands exactly the state the per-record path lands: per-record
insert-vs-update branching, the content_class gated floor surviving updates,
tombstone refusal, ip_holder resolution, and the inserted/updated tallies.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from acquisition.arxiv.bulk import BulkOaiLine
from acquisition.arxiv.oai_persist import (
    persist_oai_record,
    persist_oai_records_batched,
)
from runtime.db_lock import connect_read, connect_write
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph import ensure_initialized
from substrate.schemas.documents import ArxivOaiRecord
from tools.arxiv_bulk_resume import commit_bulk_slice

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_NONEXCLUSIVE = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


def _seed_holder(db_path: str) -> None:
    """One holder whose domain matches arxiv.org, so both paths exercise
    resolve-and-apply and the ip_holder_id write, not just the None path."""
    with connect_write(db_path, purpose="test-seed", keepalive_s=0) as con:
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, status, metadata) "
            "VALUES ('holder-arxiv', 'arXiv', 'claimed', ?)",
            [json.dumps({"domains": ["arxiv.org"]})],
        )


def _seed_existing(db_path: str) -> None:
    with connect_write(db_path, purpose="test-seed", keepalive_s=0) as con:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_uri, title, source_tier, document_type, metadata, content_class) "
            "VALUES (?, ?, ?, 3, 'academic_paper', ?, ?)",
            [
                "doc-arxiv-2401.00001",
                "https://arxiv.org/abs/2401.00001",
                "Old title",
                '{"source": "seed"}',
                GATED_DEFAULT_CONTENT_CLASS,
            ],
        )


def _records() -> list[ArxivOaiRecord]:
    return [
        ArxivOaiRecord(
            arxiv_id="2401.00001",
            datestamp="2026-01-01",
            license_uri=_ARXIV_NONEXCLUSIVE,
            title="Updated title",
            categories=("cs.AI",),
        ),  # exists -> update branch; content_class must keep its floor
        ArxivOaiRecord(
            arxiv_id="2401.00002",
            datestamp="2026-01-01",
            license_uri=_CC_BY,
            title="Brand new paper",
            categories=("cs.AI",),
        ),  # new id -> insert branch
        ArxivOaiRecord(
            arxiv_id="2401.00003",
            datestamp="2026-01-01",
            license_uri=None,
            title="Gated paper",
            categories=("cs.LG",),
        ),  # new id, no license -> insert branch, ambiguous census class
        ArxivOaiRecord(
            arxiv_id="2401.00002",
            datestamp="2026-01-02",
            license_uri=_CC_BY,
            title="Same id again",
            categories=("cs.AI",),
        ),  # duplicate id inside one batch -> insert-then-update semantics
    ]


def _run_per_record(db_path: str, records: list[ArxivOaiRecord]) -> tuple[int, int]:
    inserted = updated = 0
    with (
        connect_write(db_path, purpose="test-per-record", keepalive_s=0) as con,
        con.transaction(),
    ):
        for record in records:
            if persist_oai_record(con, record):
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def _run_batched(db_path: str, records: list[ArxivOaiRecord]) -> tuple[int, int]:
    with (
        connect_write(db_path, purpose="test-batched", keepalive_s=0) as con,
        con.transaction(),
    ):
        return persist_oai_records_batched(con, records)


def _snapshot(db_path: str) -> list[tuple[object, ...]]:
    with connect_read(db_path) as con:
        return con.execute(
            "SELECT document_id, title, source_uri, metadata, source_tier, "
            "document_type, content_class, ip_holder_id "
            "FROM documents ORDER BY document_id"
        ).fetchall()


def test_batched_persist_lands_the_same_state_as_per_record(tmp_path):
    records = _records()
    per = str(tmp_path / "per.duckdb")
    bat = str(tmp_path / "bat.duckdb")
    for path in (per, bat):
        ensure_initialized(path)
        _seed_holder(path)
        _seed_existing(path)

    inserted_per, updated_per = _run_per_record(per, records)
    inserted_bat, updated_bat = _run_batched(bat, records)

    assert (inserted_bat, updated_bat) == (inserted_per, updated_per)
    assert (inserted_bat, updated_bat) == (2, 2)
    assert _snapshot(bat) == _snapshot(per)

    snap = _snapshot(bat)
    updated_row = next(row for row in snap if row[0] == "doc-arxiv-2401.00001")
    assert updated_row[1] == "Updated title"
    assert updated_row[2] == "https://arxiv.org/abs/2401.00001"
    assert updated_row[6] == GATED_DEFAULT_CONTENT_CLASS
    assert updated_row[7] == "holder-arxiv"
    duplicate_row = next(row for row in snap if row[0] == "doc-arxiv-2401.00002")
    assert duplicate_row[1] == "Same id again"
    assert duplicate_row[7] == "holder-arxiv"


def test_batched_persist_refuses_tombstones_like_the_per_record_path(tmp_path):
    db = str(tmp_path / "t.duckdb")
    ensure_initialized(db)
    tombstone = ArxivOaiRecord(
        arxiv_id="2401.00009",
        datestamp="2026-01-01",
        license_uri=None,
        title=None,
        deleted=True,
    )
    with (
        connect_write(db, purpose="test-batched", keepalive_s=0) as con,
        pytest.raises(ValueError, match="tombstone"),
    ):
        persist_oai_records_batched(con, [tombstone])
    with (
        connect_write(db, purpose="test-per-record", keepalive_s=0) as con,
        pytest.raises(ValueError, match="tombstone"),
    ):
        persist_oai_record(con, tombstone)
    with connect_read(db) as con:
        count = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    assert count == 0


def _slice_progress() -> dict[str, object]:
    return {
        "stream_id": "arxiv_bulk",
        "cursor_schema_version": 1,
        "parser_version": 1,
        "generation_id": "g-" + "b" * 60,
        "source_sha256": "c" * 64,
        "source_size_bytes": 4_500_000_000,
        "source_format": "jsonl",
        "source_encoding": "utf-8",
        "source_path": "/home/antiek/.antiek/arxiv-metadata-oai-snapshot.json",
        "mode": "backfill",
        "tail_enabled": True,
        "from_date": None,
        "until_date": None,
        "metadata_prefix": "arxiv",
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


def test_commit_bulk_slice_skips_tombstones_and_keeps_the_tally(tmp_path):
    db = str(tmp_path / "g.duckdb")
    ensure_initialized(db)
    lines = [
        BulkOaiLine(
            record=ArxivOaiRecord(
                arxiv_id="2401.00011",
                datestamp="2026-01-01",
                license_uri=_CC_BY,
                title="Live paper",
            ),
            end_offset=100,
            line_number=1,
        ),
        BulkOaiLine(
            record=ArxivOaiRecord(
                arxiv_id="2401.00012",
                datestamp="2026-01-01",
                license_uri=None,
                deleted=True,
            ),
            end_offset=200,
            line_number=2,
        ),
    ]
    consumed, next_progress, tally = commit_bulk_slice(
        db,
        lines,
        _slice_progress(),
        max_lock_s=0,
        max_high_water_date=date(2030, 1, 1),
    )
    assert consumed == 2
    assert tally == {"inserted": 1, "updated": 0, "skipped_deleted": 1}
    assert next_progress["bulk_deleted_events"] == 1
    assert next_progress["bulk_t1_events"] == 1
    assert next_progress["physical_line_count"] == 2
    with connect_read(db) as con:
        rows = con.execute("SELECT document_id FROM documents ORDER BY document_id").fetchall()
    assert [row[0] for row in rows] == ["doc-arxiv-2401.00011"]
