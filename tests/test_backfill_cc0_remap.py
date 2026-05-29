"""Tests for tools/backfill_cc0_remap.py against a synthetic DuckDB.

Seeds three documents mis-classified as ``opt_in_licensed``:
  * one with a CC0 license_basis        -> must remap to public_domain
  * one with a CC-BY license_basis       -> must remap to source_declared_open
  * one genuine §9.10 publisher claim    -> must STAY opt_in_licensed

Asserts the dry-run counts, the --apply effect, the untouched genuine claim,
and idempotency (a second --apply is a no-op). No prod DB is touched; the tool
runs through the single-writer ``connect_write`` lock the rest of the substrate
uses.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402
from tools import backfill_cc0_remap  # noqa: E402


@pytest.fixture
def seeded_db():
    """A synthetic graph DB with three opt_in_licensed docs + their book_assets
    license_basis rows. Returns the db_path."""
    tmp = tempfile.mkdtemp(prefix="antiek-cc0-backfill-")
    db_path = os.path.join(tmp, "graph.duckdb")
    con = connect_write(db_path, purpose="cc0-backfill-test-init")
    try:
        init_database(con)
        # Three documents, all currently (wrongly) opt_in_licensed.
        rows = [
            # (document_id, license_basis, expected_after)
            ("doc-cc0", "CC0 1.0 (public-domain dedication) "
                        "(http://creativecommons.org/publicdomain/zero/1.0/)",
             "public_domain"),
            ("doc-ccby", "CC BY (https://creativecommons.org/licenses/by/4.0/)",
             "source_declared_open"),
            ("doc-ccbysa", "CC BY-SA (https://creativecommons.org/licenses/by-sa/4.0/)",
             "source_declared_open"),
            # A genuine §9.10 publisher opt-in — NO CC marker. Must stay put.
            ("doc-publisher", "Publisher opted in via §9.10 (MIT Press claim)",
             "opt_in_licensed"),
        ]
        for document_id, basis, _expected in rows:
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class) VALUES (?, 2, 'book', 'opt_in_licensed')",
                [document_id],
            )
            con.execute(
                "INSERT INTO book_assets (document_id, license_basis) VALUES (?, ?)",
                [document_id, basis],
            )
    finally:
        con.close()
    return db_path


def _classes(db_path):
    con = connect_read(db_path)
    try:
        return {
            doc_id: cc
            for (doc_id, cc) in con.execute(
                "SELECT document_id, content_class FROM documents"
            ).fetchall()
        }
    finally:
        con.close()


def test_dry_run_reports_correct_counts_and_writes_nothing(seeded_db):
    before = _classes(seeded_db)
    plan = backfill_cc0_remap.run(seeded_db, apply=False)
    assert plan.total_opt_in == 4
    assert plan.to_public_domain == 1          # doc-cc0
    assert plan.to_source_declared_open == 2   # doc-ccby + doc-ccbysa
    assert plan.left_opt_in == 1               # doc-publisher
    assert plan.total_remapped == 3
    # Dry run wrote nothing.
    assert _classes(seeded_db) == before


def test_apply_reclassifies_cc_rows_and_leaves_genuine_publisher(seeded_db):
    backfill_cc0_remap.run(seeded_db, apply=True)
    after = _classes(seeded_db)
    assert after["doc-cc0"] == "public_domain"
    assert after["doc-ccby"] == "source_declared_open"
    assert after["doc-ccbysa"] == "source_declared_open"
    # The genuine §9.10 publisher claim is untouched.
    assert after["doc-publisher"] == "opt_in_licensed"


def test_second_apply_is_idempotent_noop(seeded_db):
    backfill_cc0_remap.run(seeded_db, apply=True)
    after_first = _classes(seeded_db)
    plan2 = backfill_cc0_remap.run(seeded_db, apply=True)
    # Nothing left to remap: the only opt_in_licensed row is the genuine claim,
    # which carries no CC marker.
    assert plan2.total_opt_in == 1
    assert plan2.left_opt_in == 1
    assert plan2.total_remapped == 0
    assert _classes(seeded_db) == after_first


def test_genuine_publisher_with_non_cc_licenses_path_stays_opt_in(seeded_db):
    """A genuine §9.10 publisher claim whose provenance string happens to carry a
    NON-Creative-Commons ``licenses/by`` path must NOT be swept into
    source_declared_open. The markers are domain-qualified
    (``creativecommons.org/licenses/by``) precisely so a publisher's own
    ``acme.com/licenses/by-special-deal`` URL — or the words "by permission" —
    cannot false-positive a real opt-in into the un-claimed open class."""
    con = connect_write(seeded_db, purpose="cc0-backfill-test-fp")
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "content_class) VALUES ('doc-trap', 2, 'book', 'opt_in_licensed')"
        )
        con.execute(
            "INSERT INTO book_assets (document_id, license_basis) VALUES (?, ?)",
            [
                "doc-trap",
                # Publisher's own portal path + "by permission" prose: contains the
                # bare substring "licenses/by" and " by " but NO creativecommons.org
                # URL and no "CC BY" / "CC0" token.
                "Publisher opted in via §9.10; redistribution by permission "
                "(see https://acme.com/licenses/by-special-deal)",
            ],
        )
    finally:
        con.close()

    plan = backfill_cc0_remap.run(seeded_db, apply=True)
    # doc-trap is examined but left alone; the three genuine CC rows still remap.
    assert plan.to_public_domain == 1
    assert plan.to_source_declared_open == 2
    after = _classes(seeded_db)
    assert after["doc-trap"] == "opt_in_licensed"
    assert after["doc-publisher"] == "opt_in_licensed"


def test_cli_dry_run_then_apply(seeded_db, capsys):
    rc = backfill_cc0_remap.main(["--db-path", seeded_db])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    # Still opt_in_licensed after a dry-run.
    assert _classes(seeded_db)["doc-cc0"] == "opt_in_licensed"

    rc = backfill_cc0_remap.main(["--db-path", seeded_db, "--apply"])
    assert rc == 0
    assert "APPLIED" in capsys.readouterr().out
    assert _classes(seeded_db)["doc-cc0"] == "public_domain"


def test_cli_rejects_prod_db(monkeypatch, capsys):
    from substrate.graph import default_db_path

    rc = backfill_cc0_remap.main(["--db-path", default_db_path(), "--apply"])
    assert rc == 2
    assert "prod" in capsys.readouterr().err.lower()
