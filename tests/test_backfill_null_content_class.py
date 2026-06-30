"""Tests for the ASR SR-06 NULL content_class backfill operator tool."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    PERSONAL_READING_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
)
from substrate.graph.schema import init_database  # noqa: E402
from tools import backfill_null_content_class as bnc  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_events(monkeypatch):
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")


@pytest.fixture
def seeded_db():
    tmp = tempfile.mkdtemp(prefix="antiek-null-cc-backfill-")
    db_path = os.path.join(tmp, "graph.duckdb")
    with connect_write(db_path, purpose="null-cc-backfill-test-init") as con:
        init_database(con)
        rows = [
            (
                "doc-web-null",
                "web_article",
                "https://example.com/post",
                None,
                {"source": "urls"},
                None,
            ),
            (
                "doc-arxiv-open",
                "academic_paper",
                "https://arxiv.org/abs/2401.00001",
                None,
                {
                    "source": "arxiv_oai_pmh",
                    "arxiv_id": "2401.00001",
                    "license_content_class": SOURCE_DECLARED_OPEN_CONTENT_CLASS,
                },
                None,
            ),
            (
                "doc-arxiv-gated",
                "academic_paper",
                "https://arxiv.org/abs/2401.00002",
                None,
                {
                    "source": "arxiv_oai_pmh",
                    "arxiv_id": "2401.00002",
                    "rights_tier": "T3",
                },
                None,
            ),
            (
                "doc-book-cc0",
                "book",
                "file:///tmp/book.txt",
                None,
                {},
                "CC0 1.0 (public-domain dedication)",
            ),
            (
                "doc-unknown",
                "paper",
                "file:///tmp/unknown.pdf",
                None,
                {},
                None,
            ),
            (
                "doc-already-classed",
                "web_article",
                "https://example.com/already",
                PERSONAL_READING_CONTENT_CLASS,
                {},
                None,
            ),
        ]
        for document_id, document_type, source_uri, content_class, metadata, basis in rows:
            con.execute(
                "INSERT INTO documents (document_id, source_uri, source_tier, "
                "document_type, content_class, metadata, raw_text) "
                "VALUES (?, ?, 2, ?, ?, ?, ?)",
                [
                    document_id,
                    source_uri,
                    document_type,
                    content_class,
                    json.dumps(metadata),
                    f"Body for {document_id}. " * 4,
                ],
            )
            if basis is not None:
                con.execute(
                    "INSERT INTO book_assets (document_id, license_basis) VALUES (?, ?)",
                    [document_id, basis],
                )
    return db_path


def _rows(db_path):
    with connect_read(db_path) as con:
        return {
            doc_id: (cc, json.loads(meta) if meta else {})
            for doc_id, cc, meta in con.execute(
                "SELECT document_id, content_class, metadata FROM documents"
            ).fetchall()
        }


def test_dry_run_classifies_deterministic_rows_and_writes_nothing(seeded_db):
    before = _rows(seeded_db)

    plan = bnc.run(seeded_db)

    assert plan.total_null == 5
    assert plan.planned == 4
    assert plan.unresolved == 1
    assert plan.unresolved_document_ids == ("doc-unknown",)
    assert dict(plan.by_target) == {
        GATED_DEFAULT_CONTENT_CLASS: 1,
        PERSONAL_READING_CONTENT_CLASS: 1,
        SOURCE_DECLARED_OPEN_CONTENT_CLASS: 1,
        "public_domain": 1,
    }
    assert _rows(seeded_db) == before


def test_apply_refuses_unresolved_rows_without_explicit_gated_floor(seeded_db):
    before = _rows(seeded_db)

    with pytest.raises(RuntimeError, match="unresolved"):
        bnc.run(seeded_db, apply=True)

    assert _rows(seeded_db) == before


def test_arxiv_t2_t3_rights_tier_overrides_stale_metadata_class(seeded_db):
    with connect_write(seeded_db, purpose="null-cc-backfill-stale-arxiv") as con:
        con.execute(
            "INSERT INTO documents (document_id, source_uri, source_tier, "
            "document_type, content_class, metadata, raw_text) "
            "VALUES (?, ?, 2, ?, NULL, ?, ?)",
            [
                "doc-arxiv-stale-open",
                "https://arxiv.org/abs/2401.99999",
                "academic_paper",
                json.dumps(
                    {
                        "source": "arxiv_oai_pmh",
                        "arxiv_id": "2401.99999",
                        "rights_tier": "T3",
                        "license_content_class": SOURCE_DECLARED_OPEN_CONTENT_CLASS,
                    }
                ),
                "Body for stale arxiv metadata. " * 4,
            ],
        )

    bnc.run(seeded_db, apply=True, allow_unresolved_to_gated=True)

    assert _rows(seeded_db)["doc-arxiv-stale-open"][0] == GATED_DEFAULT_CONTENT_CLASS


def test_apply_moves_all_null_rows_when_unresolved_floor_is_allowed(seeded_db):
    plan = bnc.run(seeded_db, apply=True, allow_unresolved_to_gated=True)

    assert plan.total_null == 5
    rows = _rows(seeded_db)
    assert rows["doc-web-null"][0] == PERSONAL_READING_CONTENT_CLASS
    assert rows["doc-arxiv-open"][0] == SOURCE_DECLARED_OPEN_CONTENT_CLASS
    assert rows["doc-arxiv-gated"][0] == GATED_DEFAULT_CONTENT_CLASS
    assert rows["doc-book-cc0"][0] == "public_domain"
    assert rows["doc-unknown"][0] == GATED_DEFAULT_CONTENT_CLASS
    assert rows["doc-already-classed"][0] == PERSONAL_READING_CONTENT_CLASS

    for doc_id in (
        "doc-web-null",
        "doc-arxiv-open",
        "doc-arxiv-gated",
        "doc-book-cc0",
        "doc-unknown",
    ):
        meta = rows[doc_id][1]
        assert meta[bnc.TARGET_KEY] == rows[doc_id][0]
        assert meta[bnc.BACKFILLED_AT_KEY].endswith("Z")
    assert rows["doc-unknown"][1][bnc.REASON_KEY] == "unresolved_to_gated_floor"


def test_second_apply_is_idempotent_after_nulls_are_backfilled(seeded_db):
    bnc.run(seeded_db, apply=True, allow_unresolved_to_gated=True)

    plan2 = bnc.run(seeded_db, apply=True)

    assert plan2.total_null == 0
    assert plan2.planned == 0
    assert plan2.unresolved == 0


def test_apply_routes_content_class_changes_through_gate_helper(seeded_db, monkeypatch):
    calls = []
    real = bnc.update_document_gate_columns

    def _spy(con, document_id, **kwargs):
        calls.append((document_id, kwargs))
        return real(con, document_id, **kwargs)

    monkeypatch.setattr(bnc, "update_document_gate_columns", _spy)
    bnc.run(seeded_db, apply=True, allow_unresolved_to_gated=True)

    assert {doc_id for doc_id, _kwargs in calls} == {
        "doc-web-null",
        "doc-arxiv-open",
        "doc-arxiv-gated",
        "doc-book-cc0",
        "doc-unknown",
    }
    assert all(kwargs["set_content_class"] is True for _doc_id, kwargs in calls)


def test_cli_dry_run_apply_refusal_and_explicit_floor(seeded_db, capsys):
    assert bnc.main(["--db-path", seeded_db]) == 0
    assert "DRY RUN" in capsys.readouterr().out

    assert bnc.main(["--db-path", seeded_db, "--apply"]) == 1
    assert "unresolved" in capsys.readouterr().err

    assert (
        bnc.main(
            [
                "--db-path",
                seeded_db,
                "--apply",
                "--allow-unresolved-to-gated",
            ]
        )
        == 0
    )
    assert "APPLIED" in capsys.readouterr().out
    assert _rows(seeded_db)["doc-unknown"][0] == GATED_DEFAULT_CONTENT_CLASS


def test_cli_rejects_prod_db(capsys):
    from substrate.graph import default_db_path

    rc = bnc.main(["--db-path", default_db_path(), "--apply"])

    assert rc == 2
    assert "prod" in capsys.readouterr().err.lower()


def test_apply_emits_event(seeded_db, tmp_path, monkeypatch):
    from substrate.event_log.events import trajectory

    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.delenv("ANTIEK_RESEARCH_EVENTS_DIR", raising=False)

    bnc.run(seeded_db, apply=True, allow_unresolved_to_gated=True)

    events = trajectory("corpus-backfill-null-content-class")
    backfill_events = [
        e for e in events if e.get("action_type") == bnc.BACKFILL_ACTION_TYPE
    ]
    assert len(backfill_events) == 1
    payload = backfill_events[0]["payload"]
    assert payload["operation"] == "apply"
    assert payload["rows"] == 5
    assert payload["total_null"] == 5
    assert payload["unresolved"] == 1
