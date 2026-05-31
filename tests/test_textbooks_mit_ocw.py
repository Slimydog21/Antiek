"""MIT OCW connector tests (SPR-05 M5) — CC-BY-NC-SA → SPR-02-dictated class.

NO live HTTP. MIT OCW is uniformly CC-BY-NC-SA — the canonical NC test. The
connector reads the declared license and routes it through classify() (SPR-02),
obeying whatever class comes back. Asserts:
  * the resolved content_class is EXACTLY what classify() returns for NC-SA, and
    is NEVER public_domain;
  * if SPR-02 maps NC-SA servable, the work is servable; if gated, the body is
    withheld — whichever classify() actually returns (no hardcoded assumption);
  * the license_basis names MIT OCW + CC-BY-NC-SA.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.licenses_core import classify
from acquisition.textbooks import mit_ocw
from acquisition.textbooks._common import ingest_textbook
from substrate.books.servability import is_servable_full_text, servability_of
from substrate.constants import SERVABLE_CONTENT_CLASSES
from tests._textbook_fixtures import (  # noqa: F401  (temp_substrate fixture)
    FakeClient,
    StubEmbedder,
    make_pdf,
    temp_substrate,
)

_PDF = make_pdf(
    "18.06 Linear Algebra Lecture Notes",
    "the column space of a matrix is the span of its column vectors in R^m",
)
_PDF_URL = "https://ocw.mit.edu/courses/18-06/lecture-notes.pdf"
_BY_NC_SA = "https://creativecommons.org/licenses/by-nc-sa/4.0/"

_SEARCH = {
    "results": [
        {
            "id": "18-06-linear-algebra-spring-2010",
            "title": "18.06 Linear Algebra",
            "instructors": ["Gilbert Strang"],
            "license": _BY_NC_SA,
            "pdf_url": _PDF_URL,
            "topics": ["Mathematics", "Linear Algebra"],
            "url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/",
        }
    ]
}


def _client():
    return FakeClient(
        json_by_url={mit_ocw.MIT_OCW_SEARCH_URL: _SEARCH},
        bytes_by_url={_PDF_URL: _PDF},
    )


def test_discover_reads_ccbyncsa_license():
    works = mit_ocw.discover(_client(), limit=5)
    assert len(works) == 1
    w = works[0]
    assert w.source == "mit_ocw"
    assert w.declared_license == _BY_NC_SA


def test_ncsa_routes_to_classify_class_not_public_domain():
    (w,) = mit_ocw.discover(_client(), limit=5)
    result = w.classification()
    # Route to EXACTLY whatever classify() returns for NC-SA — no baked-in
    # expectation, so this stays correct if the operator changes the NC policy.
    expected = classify(_BY_NC_SA, dict(w.source_declaration), legitimate_source=True)
    assert result.content_class == expected.content_class
    # The load-bearing NC proof: NC-SA is NEVER flattened to public_domain.
    assert result.content_class != "public_domain"


def test_ncsa_servable_iff_classify_says_so(temp_substrate):
    (w,) = mit_ocw.discover(_client(), limit=5)
    result = w.classification()
    outcome = ingest_textbook(
        w, _client(), investigation_id="inv-test",
        db_path=temp_substrate["db_path"], embedder=StubEmbedder(),
    )
    assert outcome.ingested is True, outcome.skipped_reason
    # The class stored is exactly classify()'s; servability is DERIVED from it.
    assert outcome.content_class == result.content_class
    expected_servable = result.content_class in SERVABLE_CONTENT_CLASSES
    assert outcome.servable_full_text is expected_servable
    # And it agrees with the substrate's own projection of that class.
    status = servability_of(outcome.content_class, taken_down=False)
    assert is_servable_full_text(status) is expected_servable


def test_license_basis_names_mit_ocw_and_ccbyncsa():
    (w,) = mit_ocw.discover(_client(), limit=5)
    result = w.classification()
    # The basis names the resolved license; for the gated NC-SA branch it leads
    # with WHY it's gated and cites the CC-BY-NC-SA URI.
    assert result.license_basis
    assert "by-nc-sa" in result.license_basis.lower()
    # The connector stamps MIT OCW as provenance on the asset (source named).
    assert w.source == "mit_ocw"
    assert "ocw.mit.edu" in w.source_uri
