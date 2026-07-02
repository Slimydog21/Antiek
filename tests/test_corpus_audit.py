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
    CHECK_PERSONAL_NONATTRIB,
    CHECK_PERSONAL_NOT_TRAINING,
    CHECK_SERVABLE_BASIS,
    CHECK_THIRD_PARTY_SERVABLE,
    _check_personal_not_in_training_impl,
    assert_no_content_class_bypass,
    run_audit,
    summarize_corpus,
)
from substrate.corpus_audit import (
    main as corpus_audit_main,
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


def test_servable_class_over_gated_basis_fails_check_b(db_path):
    """REAL-DATA proof for check (b) — no monkeypatch.

    Arm (b2) catches the §9.0 catastrophe arm (b1) is structurally blind to: a
    body that SHOULD be gated but was mislabeled with a SERVABLE content_class.
    The REAL serve path trusts the column and renders the full body; arm (b1)
    never selects the row because its class is ``public_domain``, not the gated
    one. We plant exactly that real row — servable class, GATED license_basis —
    and assert the audit fails (b) by cross-checking the served class against the
    classify()-written basis on the GENUINE serve projection (``serve_full_text``
    is NOT patched here). Removing the single defect (give the row a coherent
    public-domain basis OR move it to the gated class) makes (b) pass — proven by
    the sibling ``test_servable_class_coherent_basis_passes_check_b``."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # PLANT: a SERVABLE-classed doc whose basis says it is GATED. This is a
        # real corruption shape — a hand-stamped class, or a merge that copied a
        # servable class onto a gated body. The real serve path WILL render it.
        _insert_document(
            con,
            document_id="doc-mislabel",
            content_class="public_domain",  # servable class ...
            raw_text="IN-COPYRIGHT BODY THAT MUST NOT RENDER. " * 20,
            source_uri="https://doi.org/10.7/mislabel",
            title="Mislabelled Servable",
            metadata='{"doi": "10.7/mislabel"}',
        )
        _insert_book_asset(
            con,
            document_id="doc-mislabel",
            # ... but the classify()-written basis says GATED. Contradiction.
            license_basis="GATED: no positively-established redistribution license",
        )

    # No monkeypatch: the REAL serve_full_text renders this servable-classed
    # body, and check (b2) catches the class/basis contradiction on it.
    result = run_audit(db_path, include_binding=False)
    b = result.check(CHECK_GATED_LEAK)
    assert not b.ok, "the real serve path renders a mislabelled servable body"
    assert b.count >= 1
    assert any("doc-mislabel" in o for o in b.offending)
    # The mislabel is isolated to (b): basis is non-empty (so (a) is clean),
    # the body is real text (so (d) is clean), the DOI is unique (so (c) is clean).
    assert result.check(CHECK_SERVABLE_BASIS).ok
    assert result.check(CHECK_DEDUP).ok
    assert result.check(CHECK_EXTRACTION).ok
    assert result.check(CHECK_BUDGET).ok


def test_servable_class_coherent_basis_passes_check_b(db_path):
    """Removing the single defect — a coherent public-domain basis on the same
    servable row — makes check (b) pass. Proves (b2) bit on the class/basis
    CONTRADICTION, not merely on the presence of a servable doc with a body."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-mislabel",
            content_class="public_domain",
            raw_text="A genuinely public-domain body that may render. " * 20,
            source_uri="https://doi.org/10.7/coherent",
            title="Coherent Servable",
            metadata='{"doi": "10.7/coherent"}',
        )
        _insert_book_asset(
            con,
            document_id="doc-mislabel",
            license_basis="public_domain: Project Gutenberg; US public domain",  # coherent
        )
    result = run_audit(db_path, include_binding=False)
    assert result.check(CHECK_GATED_LEAK).ok
    assert result.ok


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
# (f) third-party-on-servable — Personal-Reading Lane (SPR-02) DB backstop.
#     A third-party document_type on a servable class without a basis FAILS (f);
#     the same row at personal_reading, OR a lawful servable book WITH a basis,
#     PASSES. This is the non-vacuity proof: the check BITES on the §9.0 leak and
#     does NOT false-positive the lawful SPR-04/SPR-05/SPR-07 open-content path.
# ---------------------------------------------------------------------------


def test_third_party_servable_without_basis_fails_check_f(db_path):
    """A web_article that slipped onto the servable 'user_owned' class with no
    license_basis is the exact §9.0 leak the connector lane prevents. The check
    must FAIL on it and name the offender's document_id."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # PLANT: a third-party web_article on a SERVABLE class with NO basis.
        # (This is what the OLD schema default 'user_owned' produced before the
        # lane — a third-party essay eligible for public full-text serving.)
        _insert_document(
            con,
            document_id="doc-web-leak",
            content_class="user_owned",  # servable + no book_assets basis row
            raw_text=_BODY_A + " a leaked third-party essay tail zzz",
            source_uri="https://paulgraham.com/essay.html",
            title="A Third-Party Essay",
            document_type="web_article",
        )
        # No _insert_book_asset -> license_basis is NULL (the LEFT JOIN miss).

    result = run_audit(db_path, include_binding=False)
    f = result.check(CHECK_THIRD_PARTY_SERVABLE)
    assert not f.ok, "a servable third-party web_article with no basis must fail (f)"
    assert f.count == 1
    assert any("doc-web-leak" in o for o in f.offending)
    assert not result.ok
    # The leak is isolated to (f): the body is real (so (d) clean), the content
    # hash is unique (so (c) clean). Check (a) ALSO bites here — a servable row
    # with no basis is a servable-without-basis offender too — which is correct:
    # the lane leak is a strict subset of the servable-basis invariant, and BOTH
    # arms refusing is the belt-and-suspenders design, not a double-count bug.
    assert not result.check(CHECK_SERVABLE_BASIS).ok
    assert result.check(CHECK_DEDUP).ok
    assert result.check(CHECK_EXTRACTION).ok


def test_third_party_on_personal_reading_passes_check_f(db_path):
    """Removing the single defect — the SAME third-party row at the lane class
    personal_reading — makes (f) pass. Proves (f) bit on the SERVABLE class, not
    on the mere presence of a third-party document."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-web-ok",
            content_class="personal_reading",  # the lane: NOT in SERVABLE set
            raw_text=_BODY_A + " a lawfully-laned third-party essay tail zzz",
            source_uri="https://paulgraham.com/essay.html",
            title="A Third-Party Essay (laned)",
            document_type="web_article",
        )
        # personal_reading needs no book_assets basis — it is never served.
    result = run_audit(db_path, include_binding=False)
    assert result.check(CHECK_THIRD_PARTY_SERVABLE).ok
    assert result.ok


def test_lawful_servable_book_passes_check_f(db_path):
    """A SERVABLE book WITH a license_basis (the SPR-04 Bernays / public-domain
    path) must NOT be flagged by (f): it is not a third-party document_type AND
    it carries a basis. Proves (f) does not false-positive the lawful corpus —
    the clean two-doc corpus already has exactly such a servable book, so a
    bare clean corpus passing (f) is itself this assertion."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # An additional servable third-party row WITH a real basis — the lawful
        # SPR-05/SPR-07 exception (a PG public-domain text via the urls
        # connector, a CC-BY transcript). This MUST pass (f) because the basis
        # is present, even though its document_type is third-party.
        _insert_document(
            con,
            document_id="doc-web-pd",
            content_class="public_domain",  # servable, but ...
            raw_text=_BODY_B + " a genuinely public-domain web text tail yyy",
            source_uri="https://www.gutenberg.org/ebooks/55555",
            title="A Public-Domain Essay via urls",
            document_type="web_article",  # third-party type ...
        )
        _insert_book_asset(
            con,
            document_id="doc-web-pd",
            # ... WITH a real positive basis -> NOT a (f) offender.
            license_basis="public_domain: Project Gutenberg; US public domain",
        )
    result = run_audit(db_path, include_binding=False)
    assert result.check(CHECK_THIRD_PARTY_SERVABLE).ok, (
        "a servable third-party doc WITH a real basis is the lawful open-content "
        "exception and must NOT be flagged"
    )
    assert result.ok


def test_third_party_servable_empty_string_basis_fails_check_f(db_path):
    """SHARPEN (sprint #3.iii): the EMPTY/whitespace-basis branch must bite too.

    ``test_third_party_servable_without_basis_fails_check_f`` covers only the
    LEFT-JOIN-miss path (no ``book_assets`` row at all -> ``license_basis IS
    NULL``). But the check's ``WHERE`` has a SECOND no-basis arm —
    ``TRIM(b.license_basis) = ''`` — for a row that DOES have a ``book_assets``
    record whose basis is blank/whitespace (an empty extraction, a placeholder
    a future writer left). Without this test, a refactor that dropped the
    ``TRIM(...) = ''`` clause and kept only ``IS NULL`` would leave every other
    (f) test green while silently re-opening the leak for a present-but-blank
    basis. This is the seeded proof that the check bites on exactly that one
    defect: a third-party ``video_transcript`` on a servable class with a
    PRESENT-but-whitespace ``license_basis`` MUST fail (f) and name the
    offender. It mirrors ``_check_servable_basis``'s identical empty-basis
    treatment, so the third-party arm cannot silently desync from the book
    arm's blank-basis handling."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-yt-blankbasis",
            content_class="user_owned",  # servable ...
            raw_text=_BODY_A + " a transcript with a blank placeholder basis qqq",
            source_uri="https://www.youtube.com/watch?v=blank0001",
            title="A Transcript With A Blank Basis",
            document_type="video_transcript",  # third-party type ...
        )
        # ... WITH a book_assets row present but the basis whitespace-only:
        # this is the TRIM(...) = '' arm, NOT the IS NULL (LEFT-JOIN-miss) arm.
        _insert_book_asset(
            con, document_id="doc-yt-blankbasis", license_basis="   "
        )
    result = run_audit(db_path, include_binding=False)
    f = result.check(CHECK_THIRD_PARTY_SERVABLE)
    assert not f.ok, (
        "a servable third-party row with a PRESENT-but-blank license_basis must "
        "fail (f) via the TRIM(...) = '' arm, not only the IS NULL arm"
    )
    assert f.count == 1
    assert any("doc-yt-blankbasis" in o for o in f.offending)
    assert not result.ok
    # And (a) agrees for the same reason — a servable row with a blank basis is a
    # servable-without-basis offender under both invariants (belt-and-suspenders).
    assert not result.check(CHECK_SERVABLE_BASIS).ok


# ---------------------------------------------------------------------------
# M4a — the bypass-scanner now covers the web family (urls/youtube/twitter/
# substack). A planted content_class="..." literal under one of the new dirs
# must make the scan BITE; the constant-based M1-M3 edits must NOT.
# ---------------------------------------------------------------------------


def test_binding_detector_bites_on_literal_under_web_family():
    """A planted ``content_class="user_owned"`` literal under acquisition/urls/
    (a NEW _BINDING_DIR this sprint added) makes the scan return ok=False and
    name the path:line — proving the extended coverage bites."""
    tmp = tempfile.mkdtemp(prefix="antiek-binding-web-")
    _write_fixture_connector(
        tmp, "urls", "leaky_url_connector.py",
        '''
        """A future urls connector that re-introduces the literal anti-pattern."""
        def ingest(con):
            return insert_document(con, document_type="web_article",
                                   content_class="user_owned")
        ''',
    )
    r = assert_no_content_class_bypass(root=tmp)
    assert not r.ok
    assert any(
        "leaky_url_connector.py" in o and "user_owned" in o for o in r.offending
    )


def test_binding_detector_clean_on_constant_web_connectors():
    """The REAL integrated tree — whose urls/youtube/twitter adapters now pass
    PERSONAL_READING_CONTENT_CLASS (an imported ast.Name, not a literal) — keeps
    the binding scan green, AND the new dirs are actually walked (files_scanned
    grew to include them)."""
    r = assert_no_content_class_bypass()
    assert r.ok, r.offending
    # The web-family dirs are now in scope: the scan walks more files than the
    # original four-dir set would (urls/youtube/twitter each contribute >=1 .py).
    assert r.files_scanned > 0


# ---------------------------------------------------------------------------
# M6 — the new check rides run_audit's verdict + the CLI exit code, so CI and
# the corpus-mass-ingest runbook hard-block a planted third-party-on-servable
# violation. (substrate/legal_gate/ is a registry URL/author denylist — it does
# NOT call run_audit, so there is no hardcoded check allowlist that could drop
# this check; the run_audit + CLI surface IS the gate. Documented in handoff.)
# ---------------------------------------------------------------------------


def test_check_rides_run_audit_verdict(db_path):
    """CHECK_THIRD_PARTY_SERVABLE is collected in run_audit(...).checks and folds
    into the overall verdict — so the CI pytest path exercises it, not skips."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
    result = run_audit(db_path, include_binding=False)
    names = [c.name for c in result.checks]
    assert CHECK_THIRD_PARTY_SERVABLE in names
    # On the clean corpus the check passes and does not drag the verdict down.
    assert result.check(CHECK_THIRD_PARTY_SERVABLE).ok
    assert result.ok


def test_cli_exits_nonzero_on_planted_third_party_servable(db_path, capsys):
    """The corpus_audit CLI (python -m substrate.corpus_audit --db-path <db>)
    must exit NON-ZERO when a third-party doc sits on a servable class with no
    basis — preserving the runbook/CI hard-block. include_binding defaults True
    in the CLI; the binding is clean on the live tree, so the non-zero exit is
    attributable to the planted (f) violation (asserted via the JSON output)."""
    import json as _json

    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-web-cli-leak",
            content_class="user_owned",
            raw_text=_BODY_A + " cli-planted leaked third-party essay tail qqq",
            source_uri="https://example.com/leak.html",
            title="CLI Leak Essay",
            document_type="web_article",
        )

    rc = corpus_audit_main(["--db-path", db_path, "--json"])
    assert rc == 1, "CLI must exit non-zero on a planted third-party-servable leak"
    out = capsys.readouterr().out
    payload = _json.loads(out)
    by_name = {c["name"]: c for c in payload["checks"]}
    assert CHECK_THIRD_PARTY_SERVABLE in by_name
    assert by_name[CHECK_THIRD_PARTY_SERVABLE]["ok"] is False
    assert any("doc-web-cli-leak" in o for o in by_name[CHECK_THIRD_PARTY_SERVABLE]["offending"])


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
# SPR-10 M1.b — personal_reading non-attributable + not-public-graph.
#   A personal_reading row that the REAL is_attribution_eligible predicate would
#   deem eligible (a desynced lane), OR membership of personal_reading in the
#   public-graph set, FAILS the check. A correctly-laned personal_reading row
#   PASSES. Composes the SPR-01 eligibility/attribution sets — no re-listing.
# ---------------------------------------------------------------------------


def test_personal_reading_nonattributable_passes_clean(db_path):
    """A correctly-laned personal_reading document is non-attributable and absent
    from the public graph — the check PASSES on it (the clean-corpus baseline for
    the lane: this is the property the whole lane exists to hold)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # A lawfully-laned third-party reading: personal_reading, no basis needed
        # (it is never served), document_type web_article.
        _insert_document(
            con,
            document_id="doc-pr-clean",
            content_class="personal_reading",
            raw_text=_BODY_A + " a personal-reading essay the owner fetched zzz",
            source_uri="https://paulgraham.com/clean.html",
            title="A Personal Reading",
            document_type="web_article",
        )
    result = run_audit(db_path, include_binding=False)
    n = result.check(CHECK_PERSONAL_NONATTRIB)
    assert n.ok, n.detail
    assert result.ok


def test_personal_reading_attributable_fails_check_personal_nonattrib(db_path, monkeypatch):
    """PLANT the single defect: the lane desyncs — personal_reading is dropped
    from NON_ATTRIBUTABLE_CONTENT_CLASSES so the REAL is_attribution_eligible
    predicate would now deem a personal_reading row attribution-eligible (the
    §9.0 leak: the owner's private reading entering an ad-attribution split). The
    check must FAIL and name the offending personal_reading document_id. Removing
    the defect (the un-monkeypatched clean test above) makes it pass — proving the
    check bites on the desync, not on the mere presence of a personal_reading row.

    We monkeypatch the IMPORTED predicate's source set rather than hand-stamping a
    column, because the defect this check exists to catch is exactly a lane-set
    misconfiguration: a future edit that removed personal_reading from the
    non-attributable set. The audit reads is_attribution_eligible LIVE, so the
    desync surfaces through the real predicate."""
    import substrate.collective_graph.eligibility as elig

    # The desync: personal_reading no longer non-attributable. The predicate then
    # falls through to the claim-gate + quality-gate branches; with the audit's
    # PASS_PUBLIC probe + no claim-gate membership, it returns True — the leak.
    patched = frozenset(elig.NON_ATTRIBUTABLE_CONTENT_CLASSES - {"personal_reading"})
    monkeypatch.setattr(elig, "NON_ATTRIBUTABLE_CONTENT_CLASSES", patched)

    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-pr-leak",
            content_class="personal_reading",
            raw_text=_BODY_A + " a personal reading that a desync would expose qqq",
            source_uri="https://paulgraham.com/leak.html",
            title="A Personal Reading (desynced)",
            document_type="web_article",
        )
    result = run_audit(db_path, include_binding=False)
    n = result.check(CHECK_PERSONAL_NONATTRIB)
    assert not n.ok, "a personal_reading row the predicate deems eligible must fail"
    assert n.count == 1
    assert any("doc-pr-leak" in o for o in n.offending)
    assert not result.ok
    # Isolated: the row carries a real body (so (d) clean), unique hash (so (c)
    # clean), and is not on a servable class (so (a)/(f) clean).
    assert result.check(CHECK_SERVABLE_BASIS).ok
    assert result.check(CHECK_THIRD_PARTY_SERVABLE).ok
    assert result.check(CHECK_DEDUP).ok
    assert result.check(CHECK_EXTRACTION).ok


def test_personal_reading_public_serve_leak_fails_check_personal_nonattrib(
    db_path, monkeypatch
):
    """SHARPEN (arm 3 — the READ-SIDE lane invariant). PLANT the single defect: the
    PUBLIC serve projection renders a personal_reading body to a NON-owner — the
    §9.0 read-side catastrophe. The check must FAIL on the standing DB pass alone
    (not only the runbook's manual step) and name the offending document_id.

    This proves arm 3 is INDEPENDENTLY load-bearing: the set-based arms (1 + 2) are
    still correct here — personal_reading is non-attributable and not in the public
    graph — so a check that only replayed the two set predicates would stay GREEN
    while the serve path leaks the full body. Only a check that exercises the REAL
    serve chokepoint catches this, which is exactly what arm 3 adds.

    We monkeypatch the serve chokepoint as the corpus_audit module binds it
    (``corpus_audit.serve_full_text``) to simulate a future serve-path regression
    (an edit that added personal_reading to the public full-body branch, or flipped
    the owner default). The audit calls that bound name LIVE, so the regression
    surfaces through the real call site arm 3 uses — not a stubbed column.

    Isolation: the planted serve-path regression flips ONLY the personal-nonattrib
    check; every other corpus check stays green (the leak is not a servable-basis,
    dedup, extraction, or gated-leak failure — the gated-leak check is structurally
    blind to personal_reading)."""
    import substrate.corpus_audit as audit_mod
    from substrate.books.serve import ServeResult

    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-pr-serveleak",
            content_class="personal_reading",
            raw_text=_BODY_A + " owner-private reading the public must never see kkk",
            source_uri="https://paulgraham.com/essay.html",
            title="A Personal Reading",
            document_type="web_article",
        )

    # Sanity: with the REAL serve path, arm 3 passes — the public path withholds
    # the personal_reading body (this is the clean baseline the defect is removed
    # against, proving the check bites on the leak and not on the row's presence).
    assert run_audit(db_path, include_binding=False).check(CHECK_PERSONAL_NONATTRIB).ok

    real_serve = audit_mod.serve_full_text

    def _leaky_serve(con, document_id, *, owner=False):
        served = real_serve(con, document_id, owner=owner)
        # The regression: the PUBLIC (owner=False) path now renders the full
        # personal_reading body — the exact §9.0 read-side leak arm 3 guards.
        if served.servability is not None and not owner:
            row = con.execute(
                "SELECT content_class, raw_text FROM documents WHERE document_id = ?",
                [document_id],
            ).fetchone()
            if row and row[0] == "personal_reading":
                return ServeResult(
                    document_id=document_id,
                    found=True,
                    servability=served.servability,
                    servable=True,
                    full_text=row[1],
                    snippet=None,
                    title=served.title,
                    author=served.author,
                    reason="REGRESSION_personal_reading_public_full_body",
                )
        return served

    monkeypatch.setattr(audit_mod, "serve_full_text", _leaky_serve)

    result = run_audit(db_path, include_binding=False)
    n = result.check(CHECK_PERSONAL_NONATTRIB)
    assert not n.ok, "a public serve leak of a personal_reading body must fail arm 3"
    assert n.count == 1
    assert any("doc-pr-serveleak" in o for o in n.offending)
    assert any("serve" in o for o in n.offending)
    assert not result.ok
    # Exactly ONE check failed — the personal-nonattrib one (arm 3). The serve-path
    # regression does not falsely flip any other corpus check.
    assert {c.name for c in result.failed_checks} == {CHECK_PERSONAL_NONATTRIB}


# ---------------------------------------------------------------------------
# SPR-10 M1.c — personal_reading never in a training/RL export (forward-guard).
#   NON-VACUITY (rigor #1): the test materializes a fixture export TABLE
#   populated from documents, points the check at it, plants ONE personal_reading
#   row, asserts FAIL; removes that row, asserts PASS. Proves the check is
#   falsifiable, not trivially always-green over a non-existent table.
# ---------------------------------------------------------------------------


def test_personal_not_training_forward_guard_passes_when_no_export(db_path):
    """With the default (empty) TRAINING_EXPORT_TABLES — the origin/main reality
    where no training/RL export builder exists — the check is honestly clean and
    its detail SAYS it is a forward-guard (not a silent always-green)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        _insert_document(
            con,
            document_id="doc-pr-c",
            content_class="personal_reading",
            raw_text=_BODY_A + " personal reading present but no export exists yyy",
            source_uri="https://example.com/pr.html",
            title="Personal Reading",
            document_type="web_article",
        )
    result = run_audit(db_path, include_binding=False)
    c = result.check(CHECK_PERSONAL_NOT_TRAINING)
    assert c.ok
    # Honest about WHY it is clean — it guards a not-yet-existent export surface.
    assert "forward-guard" in c.detail
    assert result.ok


def test_personal_not_training_bites_on_planted_export_row(db_path):
    """NON-VACUITY proof. Materialize a fixture export table populated from
    documents, plant ONE personal_reading row into it, point the check at that
    table via the injectable impl seam, and assert it FAILS naming the offender.
    Then DELETE that row and assert it PASSES — proving the check bites on a real
    planted export row, not on a non-existent table."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        # A real personal_reading document in the corpus ...
        _insert_document(
            con,
            document_id="doc-pr-export",
            content_class="personal_reading",
            raw_text=_BODY_A + " the owner's private reading that MUST NOT train www",
            source_uri="https://paulgraham.com/private.html",
            title="A Private Reading",
            document_type="web_article",
        )
        # ... and a servable public-domain doc that legitimately MAY train.
        _insert_document(
            con,
            document_id="doc-pd-export",
            content_class="public_domain",
            raw_text=_BODY_B + " a public-domain text that may legitimately train vvv",
            source_uri="https://www.gutenberg.org/ebooks/4242",
            title="A Trainable PD Text",
        )
        _insert_book_asset(
            con, document_id="doc-pd-export",
            license_basis="public_domain: Project Gutenberg; US public domain",
        )
        # The FIXTURE export table — a documents-derived training/RL selection. It
        # naively selected ALL documents (the exact bug the check guards against):
        # it carries the personal_reading row it must not.
        con.execute(
            """
            CREATE TABLE training_export_fixture AS
            SELECT document_id, raw_text FROM documents
            """
        )

    # Point the check at the fixture export surface (the injectable impl seam —
    # mirrors how a real builder would add its table name to TRAINING_EXPORT_TABLES).
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        biting = _check_personal_not_in_training_impl(con, ("training_export_fixture",))
    finally:
        con.close()
    assert not biting.ok, "a personal_reading row in the export must FAIL the check"
    assert biting.count == 1
    assert any("doc-pr-export" in o for o in biting.offending)
    # The servable PD row in the SAME export is NOT flagged — only personal_reading.
    assert not any("doc-pd-export" in o for o in biting.offending)

    # REMOVE the single defect — delete the personal_reading row from the export —
    # and the check PASSES, proving it bit on that row, not on the table existing.
    with connect_write(db_path, purpose="test-seed") as con:
        con.execute(
            "DELETE FROM training_export_fixture WHERE document_id = ?",
            ["doc-pr-export"],
        )
    con = connect_read(db_path)
    try:
        clean = _check_personal_not_in_training_impl(con, ("training_export_fixture",))
    finally:
        con.close()
    assert clean.ok, "with the personal_reading row removed the export is clean"


def test_personal_not_training_unguardable_export_without_document_id(db_path):
    """An export surface with NO document_id column is reported as un-guardable
    (an honest FAIL), never silently passed — the check refuses to pretend it can
    guard a table it cannot join back to documents. This is the intellectual-
    honesty edge: a green check over an un-joinable export would be a lie."""
    with connect_write(db_path, purpose="test-seed") as con:
        _seed_clean_corpus(con)
        con.execute("CREATE TABLE bad_export AS SELECT raw_text FROM documents")
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        r = _check_personal_not_in_training_impl(con, ("bad_export",))
    finally:
        con.close()
    assert not r.ok
    assert any("un-guardable" in o for o in r.offending)


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


# ---------------------------------------------------------------------------
# _pass_public_probe — the attribution-eligibility misconfiguration probe.
# Regression for the F821 undefined-name defect: ``QualityGateResult`` was used
# as the return annotation but imported only inside the function body, so the
# annotation was an unresolvable string (a latent NameError under
# ``get_type_hints``). The import is now module-level. These tests prove the
# annotation resolves AND the probe mints a valid PASS_PUBLIC result — remove
# the module-level import and both fail.
# ---------------------------------------------------------------------------


def test_pass_public_probe_annotation_is_resolvable():
    """``get_type_hints`` must resolve the return annotation to
    ``QualityGateResult``. Before the fix the annotation referenced a name that
    was only imported inside the function body, so introspection raised
    ``NameError`` — this test fails (errors) without the module-level import."""
    import typing

    from substrate import corpus_audit

    hints = typing.get_type_hints(corpus_audit._pass_public_probe)
    resolved = hints.get("return")
    assert resolved is not None, "return annotation is missing"
    assert resolved.__name__ == "QualityGateResult"


def test_pass_public_probe_mints_pass_public_with_no_checks():
    """The probe is a fixture for the real attribution-eligibility predicate: a
    minimal PASS_PUBLIC result with no checks, so ``is_attribution_eligible``
    reads it as eligible IF (and only if) ``personal_reading`` were wrongly
    dropped from the non-attributable set."""
    from substrate.corpus_audit import _pass_public_probe
    from substrate.quality_gate import QualityGateVerdict

    result = _pass_public_probe()
    assert result.verdict is QualityGateVerdict.PASS_PUBLIC
    assert result.checks == ()

