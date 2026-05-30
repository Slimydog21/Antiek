"""Non-vacuous proof for the standing corpus audit (SPR-10 M3).

An assertion you have never seen fail is a comment, not a check. These tests
build a tiny TEMP DuckDB (the real schema, NEVER the prod DB), seed exactly ONE
violation of each class, run the audit, and assert it reports a FAILURE for that
class — and that a clean fixture PASSES all five. Each seeded-violation test is
written so that REMOVING its single planted defect makes the audit pass: the
clean baseline is asserted to pass in the same module, proving the check bites on
that defect and nothing else masks it.

THE BINDING gets the same treatment: the static detector is shown to BITE on a
planted ``content_class="..."`` literal in a fixture connector file and to PASS
on the cleaned tree (after ``ingest_work`` routes through classify()).

No live network. The DB tests seed a temp/in-memory DuckDB by hand. The budget
check injects a tiny ceiling governor to plant an over-budget corpus without a
100 GB file.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.corpus_audit import (
    CHECK_BUDGET,
    CHECK_DEDUP,
    CHECK_EXTRACTION,
    CHECK_GATED_LEAK,
    CHECK_SERVABLE_BASIS,
    assert_no_content_class_bypass,
    run_audit,
    summarize_corpus,
)
from substrate.graph.schema import init_database_at_path
from substrate.ingest_budget import BudgetGovernor


# ---------------------------------------------------------------------------
# Temp-DB seeding helpers — build a corpus row by row, no network, no prod DB.
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path():
    tmpdir = tempfile.mkdtemp(prefix="antiek-audit-test-")
    path = os.path.join(tmpdir, "graph.duckdb")
    init_database_at_path(path)
    yield path


def _insert_document(
    con,
    *,
    document_id,
    content_class,
    raw_text,
    source_uri="https://www.gutenberg.org/ebooks/1",
    title="A Work",
    author="An Author",
    metadata=None,
    document_type="book",
    source_tier=2,
):
    con.execute(
        """
        INSERT INTO documents
            (document_id, source_uri, title, author, source_tier,
             document_type, raw_text, content_class, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            document_id,
            source_uri,
            title,
            author,
            source_tier,
            document_type,
            raw_text,
            content_class,
            metadata,
        ],
    )


def _insert_book_asset(con, *, document_id, license_basis, taken_down=False):
    con.execute(
        """
        INSERT INTO book_assets (document_id, license_basis, taken_down)
        VALUES (?, ?, ?)
        """,
        [document_id, license_basis, taken_down],
    )


def _insert_chunk(con, *, chunk_id, document_id, text, index=0):
    con.execute(
        """
        INSERT INTO chunks (chunk_id, document_id, chunk_index, text)
        VALUES (?, ?, ?, ?)
        """,
        [chunk_id, document_id, index, text],
    )


# A body long enough to clear the dedup content-hash floor (MIN_CONTENT_HASH_CHARS
# = 200) so two distinct works key on distinct content hashes and never collide.
_BODY_A = (
    "On the natural rights of persons and the limits of state power, considered "
    "at length across many paragraphs of careful argument. " * 6
)
_BODY_B = (
    "Concerning the motion of the heavenly bodies and the laws that govern their "
    "orbits, examined with patient and deliberate reasoning throughout. " * 6
)


def _seed_clean_corpus(con):
    """A clean two-document corpus that passes all five checks: one servable
    public-domain book WITH a basis + non-empty body, one gated paper whose
    serve projection withholds its body. Distinct bodies -> distinct identity
    keys (no dedup collision). Both bodies non-empty and not HTML."""
    _insert_document(
        con,
        document_id="doc-book-aaaa",
        content_class="public_domain",
        raw_text=_BODY_A,
        source_uri="https://www.gutenberg.org/ebooks/1342",
        title="On Liberty",
    )
    _insert_book_asset(
        con,
        document_id="doc-book-aaaa",
        license_basis="public_domain: Project Gutenberg; US public domain",
    )
    _insert_chunk(con, chunk_id="chunk-aaaa-0", document_id="doc-book-aaaa", text=_BODY_A)

    _insert_document(
        con,
        document_id="doc-paper-bbbb",
        content_class="restricted_pending_opt_in",
        raw_text=_BODY_B,
        source_uri="https://doi.org/10.1/xyz",
        title="A Gated Paper",
        metadata='{"doi": "10.1/xyz"}',
    )
    _insert_book_asset(
        con,
        document_id="doc-paper-bbbb",
        license_basis="GATED: no positively-established redistribution license",
    )
    _insert_chunk(con, chunk_id="chunk-bbbb-0", document_id="doc-paper-bbbb", text=_BODY_B)


# ---------------------------------------------------------------------------
# Baseline — the clean fixture PASSES all five.
# ---------------------------------------------------------------------------


def test_clean_corpus_passes_all_five(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
    result = run_audit(db_path, include_binding=False)
    assert result.ok, [
        (c.name, c.detail, c.offending) for c in result.failed_checks
    ]
    for name in (
        CHECK_SERVABLE_BASIS,
        CHECK_GATED_LEAK,
        CHECK_DEDUP,
        CHECK_EXTRACTION,
        CHECK_BUDGET,
    ):
        assert result.check(name).ok


# ---------------------------------------------------------------------------
# (a) servable-without-basis — FAILS check (a), passes the rest.
# ---------------------------------------------------------------------------


def test_servable_without_basis_fails_check_a(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # PLANT: a servable public-domain book whose license_basis is empty.
        _insert_document(
            con,
            document_id="doc-book-noviol",
            content_class="public_domain",
            raw_text=_BODY_A + " distinct tail to vary the content hash zzz",
            source_uri="https://www.gutenberg.org/ebooks/999",
            title="Unbasised Servable",
        )
        _insert_book_asset(
            con, document_id="doc-book-noviol", license_basis=""  # the single defect
        )
        _insert_chunk(
            con, chunk_id="chunk-noviol-0", document_id="doc-book-noviol",
            text=_BODY_A,
        )

    result = run_audit(db_path, include_binding=False)
    assert not result.ok
    a = result.check(CHECK_SERVABLE_BASIS)
    assert not a.ok
    assert a.count == 1
    assert any("doc-book-noviol" in o for o in a.offending)
    # ONLY check (a) failed — the planted defect is isolated.
    assert result.check(CHECK_GATED_LEAK).ok
    assert result.check(CHECK_DEDUP).ok
    assert result.check(CHECK_EXTRACTION).ok
    assert result.check(CHECK_BUDGET).ok


def test_servable_with_basis_passes_check_a(db_path):
    """Removing the single planted defect (give the same servable book a basis)
    makes the audit pass — proving check (a) bit on the missing basis."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-book-noviol",
            content_class="public_domain",
            raw_text=_BODY_A + " distinct tail to vary the content hash zzz",
            source_uri="https://www.gutenberg.org/ebooks/999",
            title="Basised Servable",
        )
        _insert_book_asset(
            con, document_id="doc-book-noviol",
            license_basis="public_domain: a real basis",  # defect removed
        )
        _insert_chunk(
            con, chunk_id="chunk-noviol-0", document_id="doc-book-noviol", text=_BODY_A,
        )
    result = run_audit(db_path, include_binding=False)
    assert result.check(CHECK_SERVABLE_BASIS).ok
    assert result.ok


# ---------------------------------------------------------------------------
# (b) gated-leak — a gated body renders on the serve projection. FAILS (b).
# ---------------------------------------------------------------------------


def test_gated_doc_renders_full_text_fails_check_b(db_path, monkeypatch):
    """A genuinely gated doc whose serve projection renders full text fails (b).

    Check (b) trusts the serve PATH, not the column — that is the whole point of
    asserting against ``serve_full_text`` rather than ``content_class != gated``.
    We confirm the corpus is CLEAN under the REAL serve projection (so the only
    defect is the planted one), then plant a serve-PATH regression: a
    ``serve_full_text`` that renders a gated body's full text. A column-only
    check would still pass (the row is still ``restricted_pending_opt_in``); the
    serve-path check catches that the body now renders, which is the exact drift
    this check exists to find."""
    import substrate.corpus_audit as audit_mod
    from substrate.books.serve import serve_full_text as real_serve

    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-gated-leak",
            content_class="restricted_pending_opt_in",
            raw_text="GATED FULL BODY THAT MUST NOT RENDER. " * 20,
            source_uri="https://doi.org/10.1/gl",
            title="Gated Work",
            metadata='{"doi": "10.1/gl"}',
        )
        _insert_book_asset(
            con, document_id="doc-gated-leak", license_basis="GATED: pending opt-in",
        )

    # The corpus is CLEAN under the REAL serve projection — the defect is ONLY
    # the planted serve-path regression below.
    clean = run_audit(db_path, include_binding=False)
    assert clean.check(CHECK_GATED_LEAK).ok, "baseline must be clean before planting"

    # PLANT the single defect: a serve-path regression that renders the gated
    # body's full text (e.g. a future bug that bypassed the deny-by-default gate).
    from dataclasses import replace

    def _leaky_serve(con, document_id):
        result = real_serve(con, document_id)
        if document_id == "doc-gated-leak":
            # Simulate the leak: the serve path returns full text + servable=True.
            return replace(result, servable=True, full_text="GATED FULL BODY LEAKED")
        return result

    monkeypatch.setattr(audit_mod, "serve_full_text", _leaky_serve)

    result = run_audit(db_path, include_binding=False)
    b = result.check(CHECK_GATED_LEAK)
    assert not b.ok
    assert b.count >= 1
    assert any("doc-gated-leak" in o for o in b.offending)


# ---------------------------------------------------------------------------
# (c) dedup — two distinct docs share one DOI. FAILS (c).
# ---------------------------------------------------------------------------


def test_duplicate_doi_fails_check_c(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # PLANT: two distinct documents carrying the SAME DOI (a merge that
        # copied a row, or a connector that minted a second id for one work).
        for did, title in (("doc-dup-1", "Paper One"), ("doc-dup-2", "Paper Two")):
            _insert_document(
                con,
                document_id=did,
                content_class="restricted_pending_opt_in",
                raw_text=_BODY_B + f" {did} tail",
                source_uri="https://doi.org/10.9/shared",
                title=title,
                metadata='{"doi": "10.9/shared-dup"}',  # same DOI on both
            )
            _insert_book_asset(con, document_id=did, license_basis="GATED")

    result = run_audit(db_path, include_binding=False)
    c = result.check(CHECK_DEDUP)
    assert not c.ok
    assert c.count == 1
    assert any("10.9/shared-dup" in o for o in c.offending)
    # Only dedup failed.
    assert result.check(CHECK_SERVABLE_BASIS).ok
    assert result.check(CHECK_GATED_LEAK).ok
    assert result.check(CHECK_EXTRACTION).ok
    assert result.check(CHECK_BUDGET).ok


def test_distinct_doi_passes_check_c(db_path):
    """Removing the defect (give the two docs distinct DOIs) passes (c)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        for did, doi in (("doc-dup-1", "10.9/a"), ("doc-dup-2", "10.9/b")):
            _insert_document(
                con,
                document_id=did,
                content_class="restricted_pending_opt_in",
                raw_text=_BODY_B + f" {did} tail",
                source_uri="https://doi.org/" + doi,
                title="Paper",
                metadata='{"doi": "%s"}' % doi,  # distinct DOIs
            )
            _insert_book_asset(con, document_id=did, license_basis="GATED")
    result = run_audit(db_path, include_binding=False)
    assert result.check(CHECK_DEDUP).ok
    assert result.ok


# ---------------------------------------------------------------------------
# (d) extraction — HTML-as-body + empty body. FAILS (d).
# ---------------------------------------------------------------------------


def test_html_as_body_fails_check_d(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # PLANT: an HTML landing page mis-stored as a body (head is <!DO...).
        _insert_document(
            con,
            document_id="doc-html",
            content_class="public_domain",
            raw_text="<!DOCTYPE html>\n<html><body>not a real body</body></html>",
            source_uri="https://www.gutenberg.org/ebooks/777",
            title="HTML Body",
        )
        _insert_book_asset(
            con, document_id="doc-html", license_basis="public_domain: basis",
        )
    result = run_audit(db_path, include_binding=False)
    d = result.check(CHECK_EXTRACTION)
    assert not d.ok
    assert any("doc-html" in o and "html-as-body" in o for o in d.offending)


def test_empty_body_fails_check_d(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # PLANT: a document row with a whitespace-only (empty) body.
        _insert_document(
            con,
            document_id="doc-empty",
            content_class="public_domain",
            raw_text="   \n  ",
            source_uri="https://www.gutenberg.org/ebooks/778",
            title="Empty Body",
        )
        _insert_book_asset(
            con, document_id="doc-empty", license_basis="public_domain: basis",
        )
    result = run_audit(db_path, include_binding=False)
    d = result.check(CHECK_EXTRACTION)
    assert not d.ok
    assert any("doc-empty" in o and "empty body" in o for o in d.offending)


def test_clean_body_passes_check_d(db_path):
    """Removing the defect (a real extractable body) passes (d)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-good",
            content_class="public_domain",
            raw_text=_BODY_A + " a genuinely extracted clean body tail",
            source_uri="https://www.gutenberg.org/ebooks/779",
            title="Clean Body",
        )
        _insert_book_asset(
            con, document_id="doc-good", license_basis="public_domain: basis",
        )
    result = run_audit(db_path, include_binding=False)
    assert result.check(CHECK_EXTRACTION).ok
    assert result.ok


# ---------------------------------------------------------------------------
# (e) budget — corpus one over the SPR-09 ceiling. FAILS (e).
# ---------------------------------------------------------------------------


def test_over_budget_fails_check_e(db_path):
    """Plant an over-budget corpus by injecting a governor whose DB-size hard
    ceiling is below the seeded DB's actual size. Composes the SPR-09
    BudgetGovernor (no re-derived ceiling); the only thing varied is the ceiling
    number, which is what 'one over the ceiling' means."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)

    actual_size = os.path.getsize(db_path)
    # Hard ceiling ONE byte below the real DB size -> the corpus is over budget.
    tiny_governor = BudgetGovernor(
        db_path=db_path,
        hard_db_size_bytes=actual_size - 1,
        soft_db_size_bytes=actual_size - 2,
    )
    result = run_audit(db_path, governor=tiny_governor, include_binding=False)
    e = result.check(CHECK_BUDGET)
    assert not e.ok
    assert e.count == 1
    # Only budget failed.
    assert result.check(CHECK_SERVABLE_BASIS).ok
    assert result.check(CHECK_GATED_LEAK).ok
    assert result.check(CHECK_DEDUP).ok
    assert result.check(CHECK_EXTRACTION).ok


def test_within_budget_passes_check_e(db_path):
    """Removing the defect (a ceiling above the DB size) passes (e)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
    actual_size = os.path.getsize(db_path)
    ample_governor = BudgetGovernor(
        db_path=db_path,
        hard_db_size_bytes=actual_size * 1000,
        soft_db_size_bytes=actual_size * 900,
    )
    result = run_audit(db_path, governor=ample_governor, include_binding=False)
    assert result.check(CHECK_BUDGET).ok
    assert result.ok


# ---------------------------------------------------------------------------
# THE BINDING — the static detector bites on a planted literal + passes clean.
# ---------------------------------------------------------------------------


def _write_fixture_connector(base, sub, name, body):
    sub_dir = os.path.join(base, sub)
    os.makedirs(sub_dir, exist_ok=True)
    path = os.path.join(sub_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))
    return path


def test_binding_detector_bites_on_planted_literal():
    """The detector flags a planted ``content_class="..."`` literal in a fixture
    connector — mirroring the live public_domain.py:673 leak it caught before the
    SPR-10 fix."""
    tmp = tempfile.mkdtemp(prefix="antiek-binding-bad-")
    _write_fixture_connector(
        tmp, "books", "leaky_connector.py",
        '''
        """A connector that bypasses classify() — the retired anti-pattern."""
        def ingest(adapter):
            return adapter.ingest_servable_book(content_class="public_domain")
        ''',
    )
    r = assert_no_content_class_bypass(root=tmp)
    assert not r.ok
    assert any("leaky_connector.py" in o and "public_domain" in o for o in r.offending)


def test_binding_detector_passes_on_clean_tree():
    """A connector that FORWARDS a classify()-derived content_class is clean —
    the allowed pattern. Also asserts the empty-string skip-outcome marker and a
    docstring mention are NOT flagged."""
    tmp = tempfile.mkdtemp(prefix="antiek-binding-good-")
    _write_fixture_connector(
        tmp, "books", "clean_connector.py",
        '''
        """The retired pattern was content_class="public_domain"; we forward now."""
        def ingest(adapter, decision):
            # forward a classify()-derived value (allowed)
            skip = make_outcome(content_class="")  # empty skip-marker (allowed)
            return adapter.ingest_servable_book(
                content_class=decision.content_class,  # forward (allowed)
            )
        ''',
    )
    r = assert_no_content_class_bypass(root=tmp)
    assert r.ok, r.offending


def test_binding_passes_on_live_tree_after_fix():
    """On the real integrated tree, AFTER routing ingest_work through classify(),
    the binding assertion is green with ZERO code-literal offenders (docstring /
    .md mentions are structurally immune)."""
    r = assert_no_content_class_bypass()
    assert r.ok, r.offending
    assert r.files_scanned > 0


def test_binding_folds_into_run_audit(db_path):
    """run_audit(include_binding=True) folds the static BINDING result into the
    overall verdict, so the merge step gets both gates in one call. On the clean
    tree + clean corpus the whole audit (incl. binding) passes."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
    result = run_audit(db_path, include_binding=True)
    assert result.check("content_class_binding").ok
    assert result.ok


# ---------------------------------------------------------------------------
# Dashboard — reads read-only, reuses the AuditResult verdict (one source).
# ---------------------------------------------------------------------------


def test_summary_reports_real_state_and_audit_verdict(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
    result = run_audit(db_path, include_binding=False)
    summary = summarize_corpus(db_path, audit=result)
    assert summary.total_docs == 2
    assert summary.servable_docs == 1
    assert summary.gated_docs == 1
    assert summary.total_chunks == 2
    assert summary.db_size_bytes > 0
    # The verdict line is the SAME object the audit returned (one source).
    assert summary.verdict_ok is result.ok
    rendered = summary.render()
    assert "servable / gated: 1 / 1" in rendered
    assert "PASS" in rendered
