"""Tests for tools.license_library — the D3 license-the-library CLI.

Exercises the discovery, dry-run (no-write), apply (flip content_class), and
idempotency paths against an isolated graph DB. The single-writer
``connect_write`` lock and the sanctioned ``update_document_gate_columns``
mutator are the load-bearing invariants; these tests confirm the CLI threads
them correctly and never mutates in dry-run.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from tools.license_library import discover_unlicensed, license_documents, main


@pytest.fixture
def db() -> str:
    tmp = tempfile.mkdtemp(prefix="antiek-license-lib-")
    db_path = os.path.join(tmp, "graph.duckdb")
    con = connect_write(db_path, purpose="license-lib-test")
    init_database(con)
    # Two unlicensed tier=2 books + one already-licensed doc.
    insert_document(con, document_id="doc-book-a", source_tier=2, document_type="book")
    insert_document(con, document_id="doc-book-b", source_tier=2, document_type="book")
    insert_document(
        con, document_id="doc-licensed", source_tier=2, document_type="book",
    )
    from substrate.graph.ops import update_document_gate_columns
    update_document_gate_columns(
        con, "doc-licensed", content_class="user_owned", set_content_class=True
    )
    con.close()
    return db_path


def _content_class(db_path: str, document_id: str) -> str | None:
    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return None if row is None or row[0] is None else str(row[0])


def test_discover_finds_only_unlicensed(db: str) -> None:
    found = discover_unlicensed(db, target_class="user_owned", source_tier=2, document_id=None)
    ids = {d for d, _ in found}
    assert ids == {"doc-book-a", "doc-book-b"}
    assert all(cur is None for _, cur in found)


def test_dry_run_writes_nothing(db: str) -> None:
    results = license_documents(
        db, ["doc-book-a", "doc-book-b"], content_class="user_owned",
        ip_holder_id=None, purpose="test", apply=False,
    )
    assert all(status == "planned" for _, status, _ in results)
    assert _content_class(db, "doc-book-a") is None
    assert _content_class(db, "doc-book-b") is None


def test_apply_flips_content_class(db: str) -> None:
    results = license_documents(
        db, ["doc-book-a", "doc-book-b"], content_class="user_owned",
        ip_holder_id=None, purpose="test", apply=True,
    )
    assert {s for _, s, _ in results} == {"licensed"}
    assert _content_class(db, "doc-book-a") == "user_owned"
    assert _content_class(db, "doc-book-b") == "user_owned"
    assert _content_class(db, "doc-licensed") == "user_owned"  # untouched, already licensed


def test_apply_is_idempotent(db: str) -> None:
    license_documents(
        db, ["doc-book-a", "doc-book-b"], content_class="user_owned",
        ip_holder_id=None, purpose="test", apply=True,
    )
    # After licensing, discovery finds nothing below target.
    found = discover_unlicensed(db, target_class="user_owned", source_tier=2, document_id=None)
    assert found == []


def test_main_dry_run_exit_zero_no_mutation(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--db-path", db, "--source-tier", "2"])
    assert rc == 0
    assert "DRY-RUN" in capsys.readouterr().out
    assert _content_class(db, "doc-book-a") is None


def test_source_tier_filter_excludes_other_tiers(db: str) -> None:
    # Add a tier=4 unlicensed doc; it must NOT appear under --source-tier 2.
    con = connect_write(db, purpose="seed-tier4")
    insert_document(con, document_id="doc-tier4", source_tier=4, document_type="book")
    con.close()
    found = discover_unlicensed(db, target_class="user_owned", source_tier=2, document_id=None)
    assert "doc-tier4" not in {d for d, _ in found}
