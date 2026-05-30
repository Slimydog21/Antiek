"""DOAB/OAPEN connector tests (SPR-05 M4) — per-book license + landing-page reject.

NO live HTTP. Asserts:
  * per-book license read from DOAB metadata, resolved via classify() (SPR-02):
    a CC-BY book is servable with a license_basis; an NC book gates;
  * a fetched URL whose bytes start b'<!DO' (an HTML landing page served where a
    PDF was expected) is REJECTED by the SPR-03 extraction-quality gate inside
    ingest_textbook — NOT ingested as a book body (the 6/15-OA-landing-pages
    lesson). This is the ``-k landing`` gate.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.licenses_core import classify
from acquisition.textbooks import doab
from acquisition.textbooks._common import ingest_textbook
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from tests._textbook_fixtures import (  # noqa: F401  (temp_substrate fixture)
    HTML_LANDING_PAGE,
    FakeClient,
    StubEmbedder,
    make_pdf,
    temp_substrate,
)

_PDF = make_pdf(
    "Open Access Economics",
    "supply and demand equilibrate at the price where quantity supplied equals demanded",
)

_BY = "https://creativecommons.org/licenses/by/4.0/"
_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"

_CC_BY_PDF = "https://library.oapen.org/bitstream/ccby-economics.pdf"
_NC_PDF = "https://library.oapen.org/bitstream/nc-handbook.pdf"
_LANDING_PDF = "https://library.oapen.org/bitstream/landing-page.pdf"


def _record(handle, title, license_url, pdf):
    return {
        "handle": handle,
        "metadata": [
            {"key": "dc.title", "value": title},
            {"key": "dc.contributor.author", "value": "An Author"},
            {"key": "dc.rights.uri", "value": license_url},
            {"key": "dc.identifier.uri", "value": f"https://directory.doabooks.org/handle/{handle}"},
            {"key": "dc.publisher", "value": "Open Book Publishers"},
        ],
        "bitstreams": [
            {"name": "book.pdf", "format": "application/pdf", "retrieveLink": pdf}
        ],
    }


_SEARCH = [
    _record("20.500/1", "Open Access Economics", _BY, _CC_BY_PDF),
    _record("20.500/2", "NC Handbook of Policy", _BY_NC, _NC_PDF),
    _record("20.500/3", "Landing Page Trap", _BY, _LANDING_PDF),
]

_BYTES = {
    _CC_BY_PDF: _PDF,
    _NC_PDF: _PDF,
    _LANDING_PDF: HTML_LANDING_PAGE,  # an HTML landing page, NOT a PDF
}


def _client():
    return FakeClient(json_by_url={doab.DOAB_SEARCH_URL: _SEARCH}, bytes_by_url=_BYTES)


def _by_title(works, needle):
    return next(w for w in works if needle in w.title)


def test_discover_reads_per_book_license():
    works = doab.discover(_client(), limit=10)
    assert len(works) == 3
    assert _by_title(works, "Economics").declared_license == _BY
    assert _by_title(works, "NC Handbook").declared_license == _BY_NC


def test_ccby_book_servable_with_basis(temp_substrate):
    w = _by_title(doab.discover(_client(), limit=10), "Economics")
    outcome = ingest_textbook(
        w, _client(), investigation_id="inv-test",
        db_path=temp_substrate["db_path"], embedder=StubEmbedder(),
    )
    assert outcome.ingested is True, outcome.skipped_reason
    assert outcome.content_class in SERVABLE_CONTENT_CLASSES
    assert outcome.servable_full_text is True
    assert outcome.license_basis and "CC BY" in outcome.license_basis


def test_nc_book_routes_per_classify_not_public_domain():
    w = _by_title(doab.discover(_client(), limit=10), "NC Handbook")
    result = w.classification()
    assert result.content_class == classify(_BY_NC, {}, legitimate_source=True).content_class
    assert result.content_class != "public_domain"
    assert result.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert result.servable is False


def test_html_landing_page_rejected_by_extraction_gate(temp_substrate):
    """The ``-k landing`` gate: bytes starting b'<!DO' are rejected by the
    SPR-03 extraction-quality gate, NOT ingested as a book body."""
    w = _by_title(doab.discover(_client(), limit=10), "Landing Page Trap")
    # Sanity: the fixture body really is an HTML landing page.
    assert _BYTES[w.download_url].startswith(b"<!DO")
    outcome = ingest_textbook(
        w, _client(), investigation_id="inv-test",
        db_path=temp_substrate["db_path"], embedder=StubEmbedder(),
    )
    assert outcome.ingested is False
    assert outcome.skipped_reason is not None
    assert outcome.skipped_reason.startswith("not_a_pdf")
    assert outcome.document_id is None

    # Nothing was written to the substrate for the landing page. The rejection
    # happens BEFORE any write, so the DB file itself may never be created — an
    # even stronger proof. If it was created (e.g. by a prior servable item in
    # the same run), assert book_assets carries no row for this work.
    import os as _os

    import duckdb

    if not _os.path.exists(temp_substrate["db_path"]):
        return  # no DB file => the landing page wrote nothing at all.
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "book_assets" in tables:
            count = con.execute("SELECT count(*) FROM book_assets").fetchone()[0]
            assert count == 0
    finally:
        con.close()
