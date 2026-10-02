"""Cooperative persistence-cost admission and atomic physical-prefix controls."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import date

import pytest

from acquisition.arxiv import oai_persist
from acquisition.arxiv.adapter import arxiv_doc_id
from acquisition.arxiv.bulk import BulkOaiLine
from runtime.db_lock import connect_read, connect_write
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph import ensure_initialized
from substrate.graph.schema import load_arxiv_bulk_progress
from substrate.schemas.documents import ArxivOaiRecord
from tools import arxiv_bulk_resume as resume


def _progress() -> dict[str, object]:
    return {
        "stream_id": "arxiv_bulk",
        "cursor_schema_version": 1,
        "parser_version": 1,
        "generation_id": "g-" + "b" * 60,
        "source_sha256": "c" * 64,
        "source_size_bytes": 100_000,
        "source_format": "jsonl",
        "source_encoding": "utf-8",
        "source_path": "/synthetic/arxiv-snapshot.jsonl",
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


def _record(index: int, *, stamp: str = "2026-01-02", deleted: bool = False):
    return ArxivOaiRecord(
        arxiv_id=f"2401.{index:05d}",
        title=None if deleted else f"Synthetic paper {index}",
        datestamp=stamp,
        license_uri=None if deleted else "http://creativecommons.org/licenses/by/4.0/",
        deleted=deleted,
    )


def _lines(records, *, offset=0):
    return [
        BulkOaiLine(record=record, end_offset=offset + index * 100, line_number=index)
        for index, record in enumerate(records, start=1)
    ]


def _initialize(db_path: str, progress: dict[str, object]) -> None:
    ensure_initialized(db_path)
    with (
        connect_write(db_path, purpose="test-prefix-seed", keepalive_s=0) as con,
        con.transaction(),
    ):
        resume.save_progress(con, progress)


def _stored(db_path: str):
    with connect_read(db_path) as con:
        progress = load_arxiv_bulk_progress(con)
        count = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    return progress, count


def _seed_existing_documents(db_path: str) -> None:
    with (
        connect_write(db_path, purpose="test-prefix-existing-documents", keepalive_s=0) as con,
        con.transaction(),
    ):
        for holder, domain in (("retained-holder", "example.test"), ("arxiv-holder", "arxiv.org")):
            con.execute(
                "INSERT INTO ip_holders (ip_holder_id, display_name, status, metadata) "
                "VALUES (?, ?, 'claimed', ?)",
                [holder, holder, json.dumps({"domains": [domain]})],
            )
        for index, holder in ((0, "retained-holder"), (1, None)):
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_uri, title, author, acquired_at, source_tier, "
                "document_type, raw_text, metadata, owner_user_id, content_class, ip_holder_id) "
                "VALUES (?, ?, 'Synthetic prior title', 'Synthetic prior author', "
                "TIMESTAMP '2020-01-01 00:00:00', 5, 'synthetic_prior', 'Synthetic prior body', "
                "?, 'synthetic-owner', 'user_public_contribution', ?)",
                [
                    arxiv_doc_id(_record(index).arxiv_id),
                    "https://example.test/prior", '{"prior":true}', holder,
                ],
            )


def _catalog_snapshot(db_path: str):
    with connect_read(db_path) as con:
        return (
            con.execute("SELECT * FROM documents ORDER BY document_id").fetchall(),
            con.execute("SELECT * FROM ip_holders ORDER BY ip_holder_id").fetchall(),
            con.execute("SELECT * FROM arxiv_bulk_progress ORDER BY stream_id").fetchall(),
        )


def _comparable_documents(db_path: str):
    with connect_read(db_path) as con:
        return con.execute(
            "SELECT document_id, title, source_uri, metadata, source_tier, document_type, "
            "content_class, ip_holder_id, author, raw_text, owner_user_id "
            "FROM documents ORDER BY document_id"
        ).fetchall()


def _charge_persistence_time(monkeypatch):
    """Actual DB persistence with controlled elapsed cost, not a latency claim."""
    clock = [0.0]
    batches: list[int] = []
    real = resume.persist_oai_records_batched

    def persist(con, records):
        result = real(con, records)
        if records:
            batches.append(len(records))
            clock[0] += 0.6
        return result

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(resume, "persist_oai_records_batched", persist)
    return batches


@pytest.mark.parametrize(
    ("budget", "expected_consumed", "expected_batches"),
    [(1.0, 64, [32, 32]), (0.00001, 32, [32]), (0.0, 96, [96])],
    ids=["persistence-cost-stops-next-admission", "tiny-positive-progress", "disabled-one-batch"],
)
def test_budget_counts_actual_persistence_before_admitting_more_lines(
    tmp_path, monkeypatch, budget, expected_consumed, expected_batches,
):
    db_path = str(tmp_path / "prefix.duckdb")
    original = _progress()
    _initialize(db_path, original)
    batches = _charge_persistence_time(monkeypatch)
    consumed, next_progress, tally = resume.commit_bulk_slice(
        db_path, _lines([_record(index) for index in range(96)]), original,
        max_lock_s=budget, max_high_water_date=date(2030, 1, 1),
    )
    assert consumed == expected_consumed
    assert batches == expected_batches
    assert tally == {"inserted": consumed, "updated": 0, "skipped_deleted": 0}
    assert original == _progress()
    assert next_progress["next_byte_offset"] == consumed * 100
    assert next_progress["physical_line_count"] == consumed
    assert next_progress["selected_record_count"] == consumed
    assert next_progress["bulk_t1_events"] == consumed
    stored, count = _stored(db_path)
    assert count == consumed
    assert all(stored[key] == value for key, value in next_progress.items())


def test_physical_prefix_includes_filtered_lines_and_tombstones_not_suffix_dates(
    tmp_path, monkeypatch,
):
    db_path = str(tmp_path / "mixed.duckdb")
    original = _progress()
    _initialize(db_path, original)
    batches = _charge_persistence_time(monkeypatch)
    records = [
        None,
        _record(100, stamp="2026-01-03", deleted=True),
        _record(0, stamp="2031-01-01"),
        *[_record(index) for index in range(1, 32)],
        _record(101, stamp="2026-05-01", deleted=True),
        _record(99, stamp="2026-05-01"),
    ]
    consumed, next_progress, tally = resume.commit_bulk_slice(
        db_path, _lines(records), original,
        max_lock_s=0.1, max_high_water_date=date(2030, 1, 1),
    )
    assert consumed == 34
    assert batches == [32]
    assert tally == {"inserted": 32, "updated": 0, "skipped_deleted": 1}
    assert next_progress["next_byte_offset"] == 3400
    assert next_progress["physical_line_count"] == 34
    assert next_progress["selected_record_count"] == 33
    assert next_progress["bulk_deleted_events"] == 1
    assert next_progress["bulk_t1_events"] == 32
    assert next_progress["bulk_max_datestamp"] == date(2026, 1, 3)
    assert original == _progress()
    stored, count = _stored(db_path)
    assert count == 32
    assert all(stored[key] == value for key, value in next_progress.items())


@pytest.mark.parametrize("failure_at", ["second-persistence-batch", "resolver", "cursor-save"])
@pytest.mark.parametrize("seeded", [False, True], ids=["empty-catalog", "prior-documents-and-cursor"])
def test_documents_and_original_cursor_roll_back_as_one_slice(
    tmp_path, monkeypatch, failure_at, seeded,
):
    db_path = str(tmp_path / "rollback.duckdb")
    original = _progress()
    if seeded:
        original.update({
            "next_byte_offset": 500,
            "physical_line_count": 5,
            "selected_record_count": 4,
            "bulk_t1_events": 3,
            "bulk_deleted_events": 1,
            "bulk_max_datestamp": date(2025, 1, 1),
        })
    _initialize(db_path, original)
    if seeded:
        _seed_existing_documents(db_path)
    original_copy = dict(original)
    before = _catalog_snapshot(db_path)
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    if failure_at == "second-persistence-batch":
        real = resume.persist_oai_records_batched
        calls = 0

        def fail_after_second_batch(con, records):
            nonlocal calls
            result = real(con, records)
            if records:
                calls += 1
                if calls == 2:
                    raise RuntimeError("synthetic slice failure")
            return result

        monkeypatch.setattr(resume, "persist_oai_records_batched", fail_after_second_batch)
    elif failure_at == "resolver":
        real_resolve = oai_persist.resolve_and_apply
        calls = 0

        def fail_after_resolution(con, *, document_id, source_uri):
            nonlocal calls
            result = real_resolve(con, document_id=document_id, source_uri=source_uri)
            calls += 1
            if calls == 33:
                raise RuntimeError("synthetic slice failure")
            return result

        monkeypatch.setattr(oai_persist, "resolve_and_apply", fail_after_resolution)
    else:
        real_save = resume.save_progress

        def fail_cursor_save(con, progress):
            real_save(con, progress)
            raise RuntimeError("synthetic slice failure")

        monkeypatch.setattr(resume, "save_progress", fail_cursor_save)

    with pytest.raises(RuntimeError, match="synthetic slice failure"):
        resume.commit_bulk_slice(
            db_path,
            _lines([_record(index) for index in range(96)], offset=original["next_byte_offset"]),
            original,
            max_lock_s=10.0, max_high_water_date=date(2030, 1, 1),
        )
    assert original == original_copy
    stored, count = _stored(db_path)
    assert count == (2 if seeded else 0)
    assert all(stored[key] == value for key, value in original.items())
    assert _catalog_snapshot(db_path) == before


@pytest.mark.parametrize("deleted", [False, True], ids=["filtered-only", "tombstones-only"])
@pytest.mark.parametrize("budget", [1.0, 0.0], ids=["budgeted", "disabled"])
def test_non_live_physical_lines_also_check_before_admission(
    tmp_path, monkeypatch, deleted, budget,
):
    db_path = str(tmp_path / "non-live.duckdb")
    original = _progress()
    _initialize(db_path, original)
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    class CostedIteration(list):
        def __iter__(self):
            for line in super().__iter__():
                clock[0] += 0.6
                yield line

    lines = CostedIteration(_lines([
        _record(index, deleted=True) if deleted else None
        for index in range(4)
    ]))
    consumed, next_progress, tally = resume.commit_bulk_slice(
        db_path, lines, original,
        max_lock_s=budget, max_high_water_date=date(2030, 1, 1),
    )
    expected = 1 if budget else 4
    assert consumed == expected
    assert next_progress["physical_line_count"] == expected
    assert next_progress["next_byte_offset"] == expected * 100
    assert next_progress["selected_record_count"] == (expected if deleted else 0)
    assert tally == {"inserted": 0, "updated": 0, "skipped_deleted": expected if deleted else 0}
    stored, count = _stored(db_path)
    assert count == 0
    assert all(stored[key] == value for key, value in next_progress.items())
    assert original == _progress()


def test_empty_input_keeps_original_progress_without_a_write_lease(monkeypatch):
    original = _progress()

    def forbid_write(*args, **kwargs):
        raise AssertionError("empty input must not acquire a write lease")

    monkeypatch.setattr(resume, "connect_write", forbid_write)
    consumed, next_progress, tally = resume.commit_bulk_slice(
        "/synthetic/never-open.duckdb", [], original,
        max_lock_s=1.0, max_high_water_date=date(2030, 1, 1),
    )
    assert consumed == 0
    assert next_progress is original
    assert tally == {"inserted": 0, "updated": 0, "skipped_deleted": 0}


@pytest.mark.parametrize("seeded", [False, True], ids=["initially-absent", "mixed-existing-attribution"])
def test_duplicate_events_cross_batch_and_slice_boundaries_without_losing_receipts(
    tmp_path, monkeypatch, seeded,
):
    reference = str(tmp_path / "reference.duckdb")
    sliced = str(tmp_path / "sliced.duckdb")
    original = _progress()
    for db_path in (reference, sliced):
        _initialize(db_path, original)
        if seeded:
            _seed_existing_documents(db_path)

    records = [replace(_record(index % 3), title=f"Synthetic event {index}") for index in range(100)]
    resolution_calls = []
    real_resolve = oai_persist.resolve_and_apply

    def observe_resolution(con, *, document_id, source_uri):
        resolution_calls.append((document_id, source_uri))
        return real_resolve(con, document_id=document_id, source_uri=source_uri)

    monkeypatch.setattr(oai_persist, "resolve_and_apply", observe_resolution)
    inserted = updated = 0
    with (
        connect_write(reference, purpose="test-prefix-per-record-reference", keepalive_s=0) as con,
        con.transaction(),
    ):
        for record in records:
            if oai_persist.persist_oai_record(con, record):
                inserted += 1
            else:
                updated += 1
    expected_counts = (1, 99) if seeded else (3, 97)
    assert (inserted, updated) == expected_counts
    reference_calls = list(resolution_calls)
    resolution_calls.clear()

    batches = _charge_persistence_time(monkeypatch)
    lines = _lines(records)
    consumed, next_progress, first = resume.commit_bulk_slice(
        sliced, lines, original,
        max_lock_s=1.0, max_high_water_date=date(2030, 1, 1),
    )
    assert consumed == 64
    assert first == {"inserted": expected_counts[0], "updated": 64 - expected_counts[0], "skipped_deleted": 0}
    stored, count = _stored(sliced)
    assert count == 3
    assert stored["next_byte_offset"] == 6400
    assert stored["physical_line_count"] == stored["selected_record_count"] == 64

    remaining, final_progress, second = resume.commit_bulk_slice(
        sliced, lines[consumed:], next_progress,
        max_lock_s=1.0, max_high_water_date=date(2030, 1, 1),
    )
    assert remaining == 36
    assert second == {"inserted": 0, "updated": 36, "skipped_deleted": 0}
    assert batches == [32, 32, 32, 4]
    assert (first["inserted"] + second["inserted"], first["updated"] + second["updated"]) == expected_counts
    assert final_progress["next_byte_offset"] == 10_000
    assert final_progress["physical_line_count"] == final_progress["selected_record_count"] == 100
    assert final_progress["bulk_t1_events"] == 100
    assert final_progress["bulk_max_datestamp"] == date(2026, 1, 2)
    stored, count = _stored(sliced)
    assert count == 3
    assert all(stored[key] == value for key, value in final_progress.items())
    assert original == _progress()
    assert next_progress["physical_line_count"] == 64
    assert resolution_calls == reference_calls == [
        (arxiv_doc_id(record.arxiv_id), f"https://arxiv.org/abs/{record.arxiv_id}")
        for record in records
    ]
    assert _comparable_documents(sliced) == _comparable_documents(reference)
    expected_classes = (
        ["user_public_contribution"] * 2 + [GATED_DEFAULT_CONTENT_CLASS]
        if seeded else [GATED_DEFAULT_CONTENT_CLASS] * 3
    )
    assert [row[6] for row in _comparable_documents(sliced)] == expected_classes
    if seeded:
        rows = _comparable_documents(sliced)
        assert [row[7] for row in rows] == ["retained-holder", "arxiv-holder", "arxiv-holder"]
        assert all(row[4:6] == (5, "synthetic_prior") for row in rows[:2])
        assert all(
            row[8:] == ("Synthetic prior author", "Synthetic prior body", "synthetic-owner")
            for row in rows[:2]
        )
        with connect_read(sliced) as con:
            prior_dates = con.execute(
                "SELECT acquired_at = TIMESTAMP '2020-01-01 00:00:00' "
                "FROM documents WHERE document_id IN (?, ?) ORDER BY document_id",
                [arxiv_doc_id(_record(index).arxiv_id) for index in (0, 1)],
            ).fetchall()
        assert prior_dates == [(True,), (True,)]


@pytest.mark.parametrize("boundary", ["after-successful-commit", "after-successful-lease-exit"])
def test_post_commit_error_withholds_ack_but_does_not_invent_rollback(
    tmp_path, monkeypatch, boundary,
):
    """Injected post-boundary errors, not native COMMIT/close failure proof."""
    db_path = str(tmp_path / "post-commit.duckdb")
    original = _progress()
    _initialize(db_path, original)
    real_write = resume.connect_write
    boundaries = []
    write_calls = []

    @contextmanager
    def fail_after_real_boundary(path, *, purpose, keepalive_s):
        write_calls.append((path, purpose, keepalive_s))
        with real_write(path, purpose=purpose, keepalive_s=keepalive_s) as con:
            if boundary == "after-successful-commit":
                class CommittedThenRaises:
                    def execute(self, *args, **kwargs):
                        return con.execute(*args, **kwargs)

                    @contextmanager
                    def transaction(self):
                        with con.transaction():
                            yield con
                        boundaries.append("actual-transaction-returned")
                        raise RuntimeError("controlled post-boundary error")

                yield CommittedThenRaises()
            else:
                yield con
        boundaries.append("actual-write-context-returned")
        raise RuntimeError("controlled post-boundary error")

    monkeypatch.setattr(resume, "connect_write", fail_after_real_boundary)
    acknowledgements = []
    with pytest.raises(RuntimeError, match="controlled post-boundary error"):
        acknowledgements.append(resume.commit_bulk_slice(
            db_path, _lines([_record(index) for index in range(8)]), original,
            max_lock_s=0.0, max_high_water_date=date(2030, 1, 1),
        ))
    assert acknowledgements == []
    assert write_calls == [(db_path, "arxiv_bulk_slice", 0)]
    assert boundaries == [
        "actual-transaction-returned" if boundary == "after-successful-commit"
        else "actual-write-context-returned",
    ]
    assert original == _progress()
    stored, count = _stored(db_path)
    assert count == 8
    assert stored["next_byte_offset"] == 800
    assert stored["physical_line_count"] == stored["selected_record_count"] == 8
    assert stored["bulk_t1_events"] == 8
