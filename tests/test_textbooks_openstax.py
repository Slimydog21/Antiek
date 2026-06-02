"""OpenStax connector tests (SPR-05 M2) — CC-BY → servable.

NO live HTTP. Asserts the BINDING: content_class is derived via classify()
(SPR-02), a CC-BY book lands a servable class (one of SERVABLE_CONTENT_CLASSES)
with a non-empty license_basis that names the source + the resolved license,
and the ingest goes through ingest_servable_book -> register_book to a temp
substrate (real DuckDB row + derived servability).
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.licenses_core import classify
from acquisition.textbooks import openstax
from acquisition.textbooks._common import ingest_textbook
from substrate.constants import SERVABLE_CONTENT_CLASSES
from tests._textbook_fixtures import (  # noqa: F401  (temp_substrate fixture)
    FakeClient,
    StubEmbedder,
    make_pdf,
    temp_substrate,
)

_PDF = make_pdf(
    "University Physics Volume 1",
    "the SI unit of force is the newton and a body remains at rest unless acted upon",
)
_PDF_URL = "https://assets.openstax.org/university-physics-v1.pdf"

_CATALOG = {
    "items": [
        {
            "id": 30,
            "slug": "university-physics-volume-1",
            "title": "University Physics Volume 1",
            "authors": [{"value": {"name": "Ling, Sanny, Moebs"}}],
            "license": {
                "name": "Creative Commons Attribution License",
                "version": "4.0",
                "url": "https://creativecommons.org/licenses/by/4.0/",
            },
            "high_resolution_pdf_url": _PDF_URL,
            "subjects": ["Physics"],
            "print_isbn_13": "978-1-947172-20-3",
        }
    ]
}


def _client():
    return FakeClient(
        json_by_url={openstax.OPENSTAX_CATALOG_URL: _CATALOG},
        bytes_by_url={_PDF_URL: _PDF},
    )


def test_discover_lists_titles_with_license():
    works = openstax.discover(_client(), limit=5)
    assert len(works) == 1
    w = works[0]
    assert w.title == "University Physics Volume 1"
    assert w.declared_license == "https://creativecommons.org/licenses/by/4.0/"
    assert w.source == "openstax"
    assert w.download_url == _PDF_URL


def test_ccby_resolves_to_servable_class_via_classify():
    (w,) = openstax.discover(_client(), limit=5)
    # The connector derives content_class ONLY via classify() — assert the
    # chokepoint returns a servable class for the declared CC-BY string.
    result = w.classification()
    assert result.content_class in SERVABLE_CONTENT_CLASSES
    assert result.servable is True
    # Independent confirmation the connector did not bake in a class: feeding
    # the SAME declared license straight to classify() yields the same result.
    direct = classify(w.declared_license, {}, legitimate_source=True)
    assert direct.content_class == result.content_class
    # CC-BY is source_declared_open, NOT public_domain (it carries attribution).
    assert result.content_class == "source_declared_open"
    assert result.content_class != "public_domain"


def test_ccby_ingests_servable_with_source_named_basis(temp_substrate):
    (w,) = openstax.discover(_client(), limit=5)
    outcome = ingest_textbook(
        w, _client(), investigation_id="inv-test",
        db_path=temp_substrate["db_path"], embedder=StubEmbedder(),
    )
    assert outcome.ingested is True, outcome.skipped_reason
    assert outcome.content_class in SERVABLE_CONTENT_CLASSES
    assert outcome.servable_full_text is True
    assert outcome.servability == "source_declared_open"
    # license_basis names the resolved license; non-empty by construction.
    assert outcome.license_basis
    assert "CC BY" in outcome.license_basis
    assert "creativecommons.org/licenses/by/4.0" in outcome.license_basis

    # The book_assets row carries the basis (auditor reads "why servable?").
    import duckdb

    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        row = con.execute(
            "SELECT ba.license_basis, d.content_class "
            "FROM book_assets ba JOIN documents d USING (document_id) "
            "WHERE ba.document_id = ?",
            [outcome.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    stored_basis, content_class = row
    assert stored_basis and "CC BY" in stored_basis
    assert content_class == "source_declared_open"


def test_missing_license_routes_gated_not_servable(temp_substrate):
    # A catalog record with no license must NOT be rounded up to servable.
    catalog = {"items": [dict(_CATALOG["items"][0])]}
    catalog["items"][0] = {**catalog["items"][0]}
    catalog["items"][0].pop("license")
    client = FakeClient(
        json_by_url={openstax.OPENSTAX_CATALOG_URL: catalog},
        bytes_by_url={_PDF_URL: _PDF},
    )
    (w,) = openstax.discover(client, limit=5)
    assert w.declared_license is None
    result = w.classification()
    assert result.content_class == "restricted_pending_opt_in"
    assert result.servable is False
