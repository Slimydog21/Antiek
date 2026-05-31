"""Bernays public-domain titles — the SERVABLE-lane proving ground (SPR-04).

Two titles, both genuinely US public domain, ingested through the EXISTING
curated servable-books path as ``content_class=public_domain``:

  * Crystallizing Public Opinion (1923) — Project Gutenberg #61364. PD because
    published pre-1929 (term expiry, renewal-irrelevant). Gutenberg asserts PD
    via its per-book ``copyright=false`` flag.
  * Propaganda (1928) — Internet Archive Public-Domain-Mark item. PD because it
    entered the US public domain on 2024-01-01 under the 95-year term. The
    archive item asserts PD via a "no known copyright restrictions" rights
    field.

The rights DECISION for both flows through the ONE
``acquisition.licenses_core.classify()`` chokepoint (via
``acquisition.books.public_domain.ingest_work``) off the source's positive PD
signal — never a hardcoded literal (rigor #2 / the corpus_audit BINDING). The
curated, precise term-reasoning ``license_basis`` is applied by
``_apply_curated_basis`` ONLY after the source's positive assertion, so a NULL
basis still skips (rigor #1).

Strategy: NO live HTTP. ``FakeSourceClient`` (from test_public_domain_ingest)
records canned Gutendex / archive.org JSON + canned PDF bytes; reportlab mints
real extractable PDFs so the FULL ingest path runs offline (read → chunk →
embed → graph write → §9.0 servable registration). Every claim is a DuckDB row
count or a returned serve field — no "looks correct" (rigor #3).

Anything requiring real network (fetching the live #61364 record / the live
archive item) is honestly ``prod-only skipped``, never silently passed.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from typing import Optional

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.public_domain import (  # noqa: E402
    archive_candidate,
    gutenberg_candidates,
    ingest_work,
)

# Reuse the offline harness the existing PD test built — do not re-invent it.
from tests.test_public_domain_ingest import (  # noqa: E402
    FakeSourceClient,
    _StubEmbedder,
    _gutendex_page,
    temp_substrate,  # noqa: F401  (pytest fixture, imported for use)
)

# Import the CLI module so its curated archive ids + the curated basis
# overrides are registered (the import side-effect registers
# CURATED_PD_BASIS_OVERRIDES). Tests reference its lists directly.
import tools.ingest_public_domain as cli  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — real extractable PDFs for the two titles + canned source records
# ---------------------------------------------------------------------------

# Gutenberg #61364 — Crystallizing Public Opinion (1923).
GUTENBERG_ID = 61364
_GUT_TXT_URL = f"https://www.gutenberg.org/ebooks/{GUTENBERG_ID}.txt.utf-8"

_CRYSTALLIZING_BODY = (
    "The public relations counsel is the agent who, working with modern media "
    "of communication and the group formations of society, brings an idea to "
    "the consciousness of the public. The systematic study of mass psychology "
    "revealed to students the potentialities of invisible government of society "
    "by manipulation of the motives which actuate man in the group. " * 12
)
_CRYSTALLIZING_TXT = (
    "﻿The Project Gutenberg eBook of Crystallizing Public Opinion\r\n\r\n"
    "This eBook is for the use of anyone anywhere in the United States and most\r\n"
    "other parts of the world at no cost and with almost no restrictions\r\n"
    "whatsoever.\r\n\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK CRYSTALLIZING PUBLIC OPINION ***\r\n\r\n"
    + _CRYSTALLIZING_BODY
    + "\r\n\r\n*** END OF THE PROJECT GUTENBERG EBOOK CRYSTALLIZING PUBLIC OPINION ***\r\n"
    "Trailing Gutenberg license boilerplate to be trimmed.\r\n"
).encode("utf-8")


# archive.org — Propaganda (1928). PDM rights, real extractable PDF.
ARCHIVE_ID = "propaganda_201804"
_ARCHIVE_META_URL = f"https://archive.org/metadata/{ARCHIVE_ID}"
_ARCHIVE_PDF_NAME = "propaganda.pdf"
_ARCHIVE_PDF_URL = f"https://archive.org/download/{ARCHIVE_ID}/{_ARCHIVE_PDF_NAME}"

_PROPAGANDA_BODY = (
    "The conscious and intelligent manipulation of the organized habits and "
    "opinions of the masses is an important element in democratic society. "
    "Those who manipulate this unseen mechanism of society constitute an "
    "invisible government which is the true ruling power of our country. " * 14
)


def _make_pdf(title: str, body: str, *, pages: int = 3) -> bytes:
    """A small but real multi-page PDF with extractable text + a title, so
    read_pdf/pypdf produces non-empty markdown above MIN_INGEST_WORD_COUNT."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title)
    for page in range(pages):
        text = c.beginText(72, 720)
        text.textLine(title)
        for i in range(36):
            text.textLine(f"Page {page + 1} line {i}: {body[:80]}")
        c.drawText(text)
        c.showPage()
    c.save()
    return buf.getvalue()


_PROPAGANDA_PDF = _make_pdf("Propaganda", _PROPAGANDA_BODY)


def _gutenberg_61364_book() -> dict:
    """Canned Gutendex record for #61364 with the per-book copyright=false PD
    assertion (the source's positive signal) + a plain-text format."""
    return {
        "id": GUTENBERG_ID,
        "title": "Crystallizing Public Opinion",
        "authors": [
            {"name": "Bernays, Edward L. (Edward Louis)", "birth_year": 1891, "death_year": 1995}
        ],
        "subjects": ["Public relations", "Public opinion"],
        "copyright": False,  # Gutenberg's explicit US-public-domain assertion
        "formats": {
            "text/plain; charset=utf-8": _GUT_TXT_URL,
            "text/html": f"https://www.gutenberg.org/ebooks/{GUTENBERG_ID}.html.images",
            "application/epub+zip": f"https://www.gutenberg.org/ebooks/{GUTENBERG_ID}.epub3.images",
        },
    }


def _archive_propaganda_meta(*, rights: str = "Public Domain Mark 1.0") -> dict:
    """Canned archive.org metadata for the Propaganda item with a PDM rights
    field (the source's positive signal) + a PDF file."""
    return {
        "metadata": {
            "title": "Propaganda",
            "creator": "Edward L. Bernays",
            "rights": rights,
            "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
        },
        "files": [{"name": _ARCHIVE_PDF_NAME}, {"name": "meta.xml"}],
    }


_GUTENDEX_URL = "https://gutendex.com/books"


def _both_clients(*, gut_book=None, arc_meta=None):
    """Build one FakeSourceClient serving BOTH the Gutendex page (for #61364)
    and the archive metadata + pdf (for Propaganda)."""
    book = gut_book or _gutenberg_61364_book()
    meta = arc_meta or _archive_propaganda_meta()
    return FakeSourceClient(
        json_by_url={
            _GUTENDEX_URL: _gutendex_page([book]),
            _ARCHIVE_META_URL: meta,
        },
        bytes_by_url={
            _GUT_TXT_URL: _CRYSTALLIZING_TXT,
            _ARCHIVE_PDF_URL: _PROPAGANDA_PDF,
        },
    )


def _ingest_both(db_path: str):
    """Ingest both Bernays PD titles through the curated path against ``db_path``.
    Returns (crystallizing_outcome, propaganda_outcome)."""
    client = _both_clients()
    (gut_work,) = gutenberg_candidates(client, ids=[GUTENBERG_ID], limit=1)
    arc_work = archive_candidate(client, ARCHIVE_ID)
    assert arc_work is not None, "archive PDM item must resolve to a candidate"
    o1 = ingest_work(gut_work, client, db_path=db_path, embedder=_StubEmbedder())
    o2 = ingest_work(arc_work, client, db_path=db_path, embedder=_StubEmbedder())
    return o1, o2


# ---------------------------------------------------------------------------
# M1 / M2: ingest both as servable public_domain with the precise basis
# ---------------------------------------------------------------------------


def test_crystallizing_ingested_servable_public_domain(temp_substrate):
    """M1: #61364 ingests as content_class=public_domain via classify(), with
    the curated pre-1929 basis carried into book_assets.license_basis."""
    import duckdb

    client = _both_clients()
    (work,) = gutenberg_candidates(client, ids=[GUTENBERG_ID], limit=1)
    assert work.download_format == "text"
    assert work.source_uri == f"https://www.gutenberg.org/ebooks/{GUTENBERG_ID}"
    # The curated precise basis replaced the generic one (source asserted PD).
    assert "US PD pre-1929" in work.pd_basis
    assert "Project Gutenberg #61364" in work.pd_basis

    outcome = ingest_work(
        work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.servability == "public_domain"
    assert outcome.servable_full_text is True
    # doc id is the content-hash form (doc-book-<sha256[:16]>).
    from acquisition.books.public_domain import _to_pdf_bytes  # noqa: PLC0415
    from acquisition.books.adapter import book_doc_id  # noqa: PLC0415

    pdf_bytes = _to_pdf_bytes(_CRYSTALLIZING_TXT, work)
    assert outcome.document_id == book_doc_id(pdf_bytes)
    assert outcome.document_id.startswith("doc-book-")

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        content_class, license_basis = con.execute(
            "SELECT d.content_class, b.license_basis FROM documents d "
            "JOIN book_assets b ON d.document_id = b.document_id "
            "WHERE d.document_id = ?",
            [outcome.document_id],
        ).fetchone()
        (provenance,) = con.execute(
            "SELECT provenance FROM book_assets WHERE document_id = ?",
            [outcome.document_id],
        ).fetchone()
    finally:
        con.close()

    assert content_class == "public_domain"
    # The stamped basis is the classify() output (public_domain: <pd_basis>).
    assert license_basis and license_basis.strip()
    assert "US PD pre-1929" in license_basis
    assert "Project Gutenberg #61364" in license_basis
    assert "project gutenberg" in license_basis.lower()
    assert "public domain" in license_basis.lower()
    assert provenance == f"https://www.gutenberg.org/ebooks/{GUTENBERG_ID}"


def test_propaganda_ingested_servable_public_domain_via_archive_pdm(temp_substrate):
    """M2: the Propaganda archive item ingests as public_domain off its PDM
    rights field, with the 95-yr-term / 2024-01-01 basis."""
    import duckdb

    client = _both_clients()
    work = archive_candidate(client, ARCHIVE_ID)
    assert work is not None
    assert work.source == "archive_org"
    assert work.download_url.endswith(".pdf")
    assert work.source_uri == f"https://archive.org/details/{ARCHIVE_ID}"
    assert "95-yr term" in work.pd_basis
    assert "entered PD 2024-01-01" in work.pd_basis

    outcome = ingest_work(
        work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.servability == "public_domain"
    assert outcome.servable_full_text is True

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        content_class, license_basis = con.execute(
            "SELECT d.content_class, b.license_basis FROM documents d "
            "JOIN book_assets b ON d.document_id = b.document_id "
            "WHERE d.document_id = ?",
            [outcome.document_id],
        ).fetchone()
        (provenance,) = con.execute(
            "SELECT provenance FROM book_assets WHERE document_id = ?",
            [outcome.document_id],
        ).fetchone()
    finally:
        con.close()

    assert content_class == "public_domain"
    assert "US PD: 95-yr term; entered PD 2024-01-01" in license_basis
    assert "Internet Archive PDM (1928 first ed.)" in license_basis
    assert "public domain" in license_basis.lower()
    # The basis must NOT read as a GATED/circumvented basis (b2 cross-check).
    assert not license_basis.strip().lower().startswith("gated:")
    assert "skip: access was circumvented" not in license_basis.lower()
    assert provenance == f"https://archive.org/details/{ARCHIVE_ID}"


# ---------------------------------------------------------------------------
# M3: full-text serve  (gate: -k serve)
# ---------------------------------------------------------------------------


def test_serve_full_text_both_bernays_titles(temp_substrate):
    """Both titles return servable=True, non-empty full_text, snippet=None,
    reason='servable' on the PUBLIC serve path."""
    import duckdb

    from substrate.books.serve import serve_full_text

    o1, o2 = _ingest_both(temp_substrate["db_path"])
    assert o1.ingested and o2.ingested

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        for doc_id in (o1.document_id, o2.document_id):
            served = serve_full_text(con, doc_id)
            assert served.found is True
            assert served.servable is True, f"{doc_id} should be servable"
            assert served.full_text and served.full_text.strip(), (
                f"{doc_id} full_text must be non-empty"
            )
            assert served.snippet is None
            assert served.reason == "servable"
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M3: sha256 dedup — re-ingest is a true no-op on row count  (gate: -k dedup)
# ---------------------------------------------------------------------------


def test_reingest_is_noop_sha256_dedup(temp_substrate):
    """Re-ingesting the SAME source bytes leaves COUNT(*) WHERE document_id=?
    at 1 (the doc-book-<sha256[:16]> id + insert_document on_conflict='ignore'
    dedup). Assert the count is UNCHANGED, not merely 'ran twice'."""
    import duckdb

    o1, o2 = _ingest_both(temp_substrate["db_path"])

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (docs_after_first,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        per_doc_first = {
            doc_id: con.execute(
                "SELECT COUNT(*) FROM documents WHERE document_id = ?", [doc_id]
            ).fetchone()[0]
            for doc_id in (o1.document_id, o2.document_id)
        }
    finally:
        con.close()
    assert per_doc_first == {o1.document_id: 1, o2.document_id: 1}

    # Re-ingest the exact same bytes a second time.
    r1, r2 = _ingest_both(temp_substrate["db_path"])
    assert r1.document_id == o1.document_id
    assert r2.document_id == o2.document_id

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (docs_after_second,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        per_doc_second = {
            doc_id: con.execute(
                "SELECT COUNT(*) FROM documents WHERE document_id = ?", [doc_id]
            ).fetchone()[0]
            for doc_id in (o1.document_id, o2.document_id)
        }
        asset_counts = {
            doc_id: con.execute(
                "SELECT COUNT(*) FROM book_assets WHERE document_id = ?", [doc_id]
            ).fetchone()[0]
            for doc_id in (o1.document_id, o2.document_id)
        }
    finally:
        con.close()

    assert docs_after_second == docs_after_first  # zero documents added on re-run
    assert per_doc_second == {o1.document_id: 1, o2.document_id: 1}
    assert asset_counts == {o1.document_id: 1, o2.document_id: 1}


# ---------------------------------------------------------------------------
# M3: corpus_audit green  (gate: -k audit)
# ---------------------------------------------------------------------------


def test_corpus_audit_ok_after_ingest(temp_substrate):
    """run_audit(db).ok is True after ingest: servable_without_basis finds zero
    offenders (both carry a basis) and the BINDING assert_no_content_class_bypass
    passes (the rights decision routes through classify())."""
    from substrate.corpus_audit import (
        CHECK_SERVABLE_BASIS,
        assert_no_content_class_bypass,
        run_audit,
    )

    _ingest_both(temp_substrate["db_path"])

    result = run_audit(temp_substrate["db_path"])
    failed = [c.name for c in result.checks if not c.ok]
    assert result.ok is True, f"audit failed checks: {failed}"
    assert result.check(CHECK_SERVABLE_BASIS).ok is True
    assert result.check(CHECK_SERVABLE_BASIS).count == 0

    binding = assert_no_content_class_bypass()
    assert binding.ok is True, f"content_class bypass offenders: {binding.offending}"


# ---------------------------------------------------------------------------
# M3: denylist — exactly the two PD titles, zero in-copyright titles
#                (gate: -k denylist)
# ---------------------------------------------------------------------------

# The in-copyright Bernays catalogue — these MUST NEVER appear as public_domain.
_DENYLISTED_BERNAYS_TITLES = (
    "Public Relations",
    "The Engineering of Consent",
    "Biography of an Idea",
)


def test_no_in_copyright_bernays_title_present_as_pd(temp_substrate):
    """After ingest: exactly the two PD Bernays titles are public_domain, and
    ZERO denylisted (in-copyright) titles are present at that class. Counts both
    directions (rigor #3)."""
    import duckdb

    _ingest_both(temp_substrate["db_path"])

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        # The two PD titles are present as public_domain.
        pd_titles = {
            r[0]
            for r in con.execute(
                "SELECT title FROM documents WHERE content_class = 'public_domain'"
            ).fetchall()
        }
        # Zero denylisted in-copyright titles present at ALL (let alone as PD).
        denylisted_present = []
        for bad in _DENYLISTED_BERNAYS_TITLES:
            (n,) = con.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE content_class = 'public_domain' AND title LIKE ?",
                [f"%{bad}%"],
            ).fetchone()
            if n:
                denylisted_present.append((bad, n))
        # Total public_domain docs in this isolated DB == exactly 2 (the PD pair).
        (pd_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE content_class = 'public_domain'"
        ).fetchone()
    finally:
        con.close()

    assert "Crystallizing Public Opinion" in pd_titles
    assert "Propaganda" in pd_titles
    assert denylisted_present == [], (
        f"in-copyright Bernays title(s) present as public_domain: {denylisted_present}"
    )
    assert pd_count == 2, f"expected exactly 2 PD docs, found {pd_count}"


def test_denylisted_titles_are_documented_not_ingested():
    """The denylist note names each in-copyright title and refuses it. The
    connector never ingests one — there is no curated id/identifier for them."""
    note = os.path.join(_REPO, "docs", "decisions", "bernays_public_domain.md")
    assert os.path.exists(note), "denylist decision note must exist"
    text = open(note, encoding="utf-8").read()
    for bad in _DENYLISTED_BERNAYS_TITLES:
        assert bad in text, f"denylist note must name {bad!r}"
    # The 1945 renewal registration is the load-bearing evidence (rigor #5).
    assert "RE0000069553" in text
    assert "renewal-zone" in text
    # No denylisted title is wired into the curated ingest lists.
    joined_ids = " ".join(str(i) for i in cli.CURATED_GUTENBERG_IDS)
    joined_arc = " ".join(cli.CURATED_ARCHIVE_IDENTIFIERS)
    for bad in ("public_relations", "engineering_of_consent", "biography_of_an_idea"):
        assert bad not in joined_ids.lower()
        assert bad not in joined_arc.lower()


# ---------------------------------------------------------------------------
# Rigor #1 / #3 edge cases — deny-by-default still holds for these titles
# ---------------------------------------------------------------------------


def test_gutenberg_61364_with_null_basis_skips_never_serves(temp_substrate):
    """If Gutenberg's record did NOT assert PD (copyright=true), #61364 yields
    no candidate and is never ingested servable — the curated basis override
    does NOT manufacture PD (rigor #1)."""
    book = _gutenberg_61364_book()
    book["copyright"] = True  # source no longer asserts PD
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([book])},
    )
    works = gutenberg_candidates(client, ids=[GUTENBERG_ID], limit=1)
    assert works == [], "a copyright=true record must yield no PD candidate"


def test_archive_propaganda_copyright_asserting_item_skips(temp_substrate):
    """If the archive item asserts copyright (no PDM), it is denied by
    _archive_pd_basis and never becomes a servable candidate — the curated basis
    override does NOT rescue it (rigor #1 / #3)."""
    meta = _archive_propaganda_meta(rights="© 2018 reprint. All rights reserved.")
    client = FakeSourceClient(json_by_url={_ARCHIVE_META_URL: meta})
    assert archive_candidate(client, ARCHIVE_ID) is None


# ---------------------------------------------------------------------------
# Curated wiring — discover() resolves BOTH titles in one curated run
# ---------------------------------------------------------------------------


def test_curated_basis_applies_without_importing_the_cli():
    """SPR-04 sharpen (finding #3): the precise curated license_basis must be
    applied by the CONNECTOR alone — it must NOT depend on having imported
    ``tools.ingest_public_domain`` first.

    The earlier shape populated ``CURATED_PD_BASIS_OVERRIDES`` via an import-time
    side effect in the CLI module, so any caller that had not imported the CLI
    silently got the GENERIC per-source basis. This test runs a FRESH
    interpreter that imports ONLY ``acquisition.books.public_domain`` (never the
    CLI), resolves a Gutenberg candidate through a fake client, and asserts the
    curated 'US PD pre-1929' wording is present. If the coupling regressed, the
    subprocess would see the generic basis and exit non-zero — so this test
    BITES on exactly that defect.
    """
    import subprocess
    import textwrap

    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {_REPO!r})
        # Import ONLY the connector — NOT tools.ingest_public_domain.
        import acquisition.books.public_domain as pd
        assert "tools.ingest_public_domain" not in sys.modules, (
            "this test must prove the basis without the CLI imported"
        )
        # The curated override map must already be populated at the connector's
        # own import time (co-located), not awaiting a CLI side effect.
        assert "gutenberg:61364" in pd.CURATED_PD_BASIS_OVERRIDES, (
            "curated basis not co-located in the connector module"
        )

        class FakeClient:
            def get_json(self, url, params=None):
                return {{
                    "results": [{{
                        "id": {GUTENBERG_ID},
                        "title": "Crystallizing Public Opinion",
                        "authors": [{{"name": "Bernays, Edward L."}}],
                        "subjects": ["Public relations"],
                        "copyright": False,
                        "formats": {{"text/plain; charset=utf-8": {_GUT_TXT_URL!r}}},
                    }}],
                    "next": None,
                }}
            def get_bytes(self, url):
                raise AssertionError("discovery does not fetch bytes")

        (work,) = pd.gutenberg_candidates(FakeClient(), ids=[{GUTENBERG_ID}], limit=1)
        assert work.pd_basis is not None
        assert "US PD pre-1929" in work.pd_basis, work.pd_basis
        assert "Project Gutenberg #61364" in work.pd_basis, work.pd_basis
        # The generic-only basis would read like this — must NOT be what we got.
        assert "copyright=false flag (gutendex book id" not in work.pd_basis
        print("OK")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"connector-only curated basis failed:\nSTDOUT:{proc.stdout}\n"
        f"STDERR:{proc.stderr}"
    )
    assert "OK" in proc.stdout


def test_every_curated_archive_id_has_a_registered_basis():
    """SPR-04 sharpen: every id in ``CURATED_ARCHIVE_IDENTIFIERS`` must have a
    precise basis registered in the connector's override map, so a future edit
    that adds an archive id without a basis fails loudly (the CLI import guard)
    rather than silently stamping the generic per-source basis."""
    from acquisition.books.public_domain import CURATED_PD_BASIS_OVERRIDES

    for arc_id in cli.CURATED_ARCHIVE_IDENTIFIERS:
        key = f"archive:{arc_id}"
        assert key in CURATED_PD_BASIS_OVERRIDES, (
            f"curated archive id {arc_id!r} has no precise license_basis"
        )
        assert "public domain" in CURATED_PD_BASIS_OVERRIDES[key].lower()


def test_dead_archive_identifier_drops_safely_deny_by_default():
    """SPR-04 sharpen (finding #1): if the named archive identifier is DEAD
    (live metadata response is empty {}), ``archive_candidate`` returns None and
    the item is dropped — NO infringing data can land. This models the real
    failure mode the unverified id carries: a silent ABSENCE of Propaganda,
    never an unsafe ingest."""
    # An empty metadata document is exactly what archive.org returns for a
    # non-existent identifier (verified: GET /metadata/<dead-id> -> {}).
    client = FakeSourceClient(json_by_url={_ARCHIVE_META_URL: {}})
    assert archive_candidate(client, ARCHIVE_ID) is None


def test_run_corpus_ingest_does_not_pull_archive_identifiers():
    """SPR-04 sharpen (finding #2): the canonical SPR-08 orchestrator
    ``tools/run_corpus_ingest.py`` reads CURATED_GUTENBERG_IDS but has NO
    archive discovery surface — it must NOT reference CURATED_ARCHIVE_IDENTIFIERS
    or archive_candidate. Propaganda (an archive id) lands ONLY via the
    ``ingest_public_domain --curated`` CLI; this documents that wiring boundary
    in an executable assertion so the docs note + code agree."""
    src = open(
        os.path.join(_REPO, "tools", "run_corpus_ingest.py"), encoding="utf-8"
    ).read()
    assert "CURATED_GUTENBERG_IDS" in src, (
        "orchestrator should land the curated Gutenberg titles"
    )
    assert "CURATED_ARCHIVE_IDENTIFIERS" not in src, (
        "orchestrator must NOT silently iterate archive identifiers; if this "
        "changes, update docs/decisions/bernays_public_domain.md § 'How each "
        "title is ingested'"
    )
    # The docs note must carry the wiring boundary so the operator runs the
    # right command in the SPR-08 window.
    note = open(
        os.path.join(_REPO, "docs", "decisions", "bernays_public_domain.md"),
        encoding="utf-8",
    ).read()
    assert "How each title is ingested" in note
    assert "run_corpus_ingest" in note


def test_curated_discover_resolves_both_bernays_titles():
    """A curated run resolves the Gutenberg curated ids (incl. #61364) PLUS the
    curated archive identifiers (Propaganda), each PD-gated by the source."""
    client = _both_clients()
    works = cli.discover(
        client,
        subject=None,
        search=None,
        ids=None,
        curated=True,
        limit=5,
    )
    titles = {w.title for w in works}
    assert "Crystallizing Public Opinion" in titles
    assert "Propaganda" in titles
    # Every resolved work carries a positive PD basis (deny-by-default holds).
    assert all(w.pd_basis for w in works)


# ---------------------------------------------------------------------------
# Prod-only: live network ingest (honest skip — never silently passed)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="prod-only: fetches the LIVE Gutenberg #61364 record + the LIVE "
    "archive.org Propaganda item over the network; the offline tests above "
    "prove the ingest/serve/audit/dedup behaviour with FakeSourceClient. A "
    "real corpus ingest run is operator-window work (SPR-08), not CI."
)
def test_live_network_ingest_bernays_titles():  # pragma: no cover
    raise AssertionError("prod-only; intentionally skipped in CI")
