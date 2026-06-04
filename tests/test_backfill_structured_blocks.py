"""Backfill / compat tests for pre-SPR-02 documents (SPR-02 M5).

The M5 gates: a document ingested BEFORE this sprint (stored as flat cleaned
text, structured_blocks NULL) opens as a model after the backfill (M1 extractor
applied to its stored text, NO re-fetch); the upgrade is idempotent (a second
run is a no-op); it is logged (the report); and there is no data loss (raw_text
and rights columns are preserved untouched).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.contracts.document_model import Document
from substrate.graph import ensure_initialized
from substrate.graph.backfill_structured_blocks import (
    BackfillReport,
    backfill_structured_blocks,
)
from substrate.graph.ops import insert_document


@pytest.fixture
def db_path():
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr02-backfill-")
    path = os.path.join(tmpdir, "graph.duckdb")
    ensure_initialized(path)
    yield path


_LEGACY_MD = "# Legacy Title\n\nA paragraph of stored cleaned text.\n\nAnother paragraph.\n"


def _insert_legacy_doc(db_path: str, doc_id: str, *, raw_text: str | None = _LEGACY_MD):
    """Insert a document WITHOUT structured_blocks (a pre-SPR-02 row)."""
    with connect_write(db_path, purpose="test.seed") as con:
        insert_document(
            con,
            document_id=doc_id,
            source_tier=4,
            document_type="web_article",  # third-party → content_class stamped
            raw_text=raw_text,
            title="Legacy Title",
            source_uri="https://example.com/legacy",
        )


def _read(db_path: str, doc_id: str):
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(
            "SELECT raw_text, structured_blocks, content_class "
            "FROM documents WHERE document_id = ?",
            [doc_id],
        ).fetchone()
    finally:
        con.close()


def test_backfill_upgrades_pre_existing_doc_to_model(db_path):
    _insert_legacy_doc(db_path, "doc-legacy-1")
    # Before: structured_blocks is NULL.
    assert _read(db_path, "doc-legacy-1")[1] is None

    report = backfill_structured_blocks(db_path)
    assert isinstance(report, BackfillReport)
    assert report.upgraded == 1

    # After: structured_blocks deserializes to a real model with the legacy text.
    raw_text, sb, content_class = _read(db_path, "doc-legacy-1")
    assert sb is not None
    doc = Document.model_validate_json(sb)
    kinds = {b.type for b in doc.blocks}
    assert "heading" in kinds and "paragraph" in kinds
    # No data loss: raw_text + rights preserved.
    assert raw_text == _LEGACY_MD
    assert content_class == "personal_reading"  # rights NOT re-stamped/lost


def test_backfill_is_idempotent_second_run_is_noop(db_path):
    _insert_legacy_doc(db_path, "doc-legacy-2")
    first = backfill_structured_blocks(db_path)
    assert first.upgraded == 1
    sb_after_first = _read(db_path, "doc-legacy-2")[1]

    second = backfill_structured_blocks(db_path)
    assert second.upgraded == 0  # no-op
    assert second.candidates == 0
    assert second.already_upgraded == 1
    # Same model produced (deterministic) — byte-identical.
    assert _read(db_path, "doc-legacy-2")[1] == sb_after_first


def test_backfill_does_not_refetch(db_path):
    """The upgrade reads STORED text only — no network. (Proven structurally:
    the backfill module imports no fetcher; here we assert it upgrades a doc
    whose source_uri points nowhere reachable, succeeding from stored text.)"""
    _insert_legacy_doc(db_path, "doc-legacy-3")
    report = backfill_structured_blocks(db_path)
    assert report.upgraded == 1


def test_dry_run_reports_without_writing(db_path):
    _insert_legacy_doc(db_path, "doc-legacy-4")
    report = backfill_structured_blocks(db_path, dry_run=True)
    assert report.dry_run is True
    assert report.candidates == 1
    assert report.upgraded == 1  # would-upgrade count
    # But nothing was actually written.
    assert _read(db_path, "doc-legacy-4")[1] is None


def test_backfill_skips_null_text_rows_not_candidates(db_path):
    """A row with NULL raw_text is not a backfill candidate at all (the WHERE
    clause filters it) — there is nothing to upgrade from, so it is left NULL."""
    _insert_legacy_doc(db_path, "doc-null-text", raw_text=None)
    report = backfill_structured_blocks(db_path)
    assert report.upgraded == 0
    assert report.candidates == 0  # NULL raw_text → not a candidate
    assert _read(db_path, "doc-null-text")[1] is None


def test_backfill_skips_whitespace_only_text(db_path):
    """A row whose raw_text is whitespace-only IS a candidate (raw_text NOT
    NULL) but has nothing real to upgrade — counted in skipped_empty_text and
    left NULL, never written as an empty model."""
    _insert_legacy_doc(db_path, "doc-ws-text", raw_text="   \n  \n")
    report = backfill_structured_blocks(db_path)
    assert report.upgraded == 0
    assert report.candidates == 1
    assert report.skipped_empty_text == 1
    assert _read(db_path, "doc-ws-text")[1] is None


def test_report_is_json_serializable(db_path):
    """The 'logged' requirement — the report renders to JSON for stdout."""
    import json

    _insert_legacy_doc(db_path, "doc-legacy-5")
    report = backfill_structured_blocks(db_path)
    blob = json.dumps(report.as_dict())
    assert "upgraded" in blob
