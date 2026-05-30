"""LibreTexts connector tests (SPR-05 M3) — per-item mixed CC, NC/ND routing.

NO live HTTP. LibreTexts mixes CC variants per item, so each item's declared
license is resolved INDIVIDUALLY through classify() (SPR-02). Asserts:
  * CC-BY-SA → servable (source_declared_open) with a correct license_basis;
  * CC-BY-NC and CC-BY-ND each route to EXACTLY the class classify() returns —
    and the test FAILS if either is classed public_domain (the rigor trap);
  * a no-license item routes to GATED_DEFAULT_CONTENT_CLASS, body withheld.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.licenses_core import classify
from acquisition.textbooks import libretexts
from acquisition.textbooks._common import ingest_textbook
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from tests._textbook_fixtures import (  # noqa: F401  (temp_substrate fixture)
    FakeClient,
    StubEmbedder,
    make_pdf,
    temp_substrate,
)

_PDF = make_pdf(
    "Organic Chemistry (LibreTexts)",
    "a nucleophile donates an electron pair to an electrophile forming a covalent bond",
)


def _item(page_id, title, license_url, *, pdf="https://chem.libretexts.org/x.pdf"):
    return {
        "id": page_id,
        "title": title,
        "author": "OpenStax / LibreTexts contributors",
        "licenseurl": license_url,
        "pdf_url": pdf,
        "url": f"https://chem.libretexts.org/{page_id}",
        "subjects": ["Chemistry"],
    }


_BY_SA = "https://creativecommons.org/licenses/by-sa/4.0/"
_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"
_BY_ND = "https://creativecommons.org/licenses/by-nd/4.0/"

_PAGE = {
    "items": [
        _item("byc", "Map: CC-BY-SA Chemistry", _BY_SA, pdf="https://chem.libretexts.org/sa.pdf"),
        _item("ncc", "Map: CC-BY-NC Chemistry", _BY_NC, pdf="https://chem.libretexts.org/nc.pdf"),
        _item("ndc", "Map: CC-BY-ND Chemistry", _BY_ND, pdf="https://chem.libretexts.org/nd.pdf"),
    ]
}

_BYTES = {
    "https://chem.libretexts.org/sa.pdf": _PDF,
    "https://chem.libretexts.org/nc.pdf": _PDF,
    "https://chem.libretexts.org/nd.pdf": _PDF,
}


def _client():
    return FakeClient(json_by_url={libretexts.LIBRETEXTS_CONTENT_URL: _PAGE},
                      bytes_by_url=_BYTES)


def _by_title(works, needle):
    return next(w for w in works if needle in w.title)


def test_discover_reads_per_item_license():
    works = libretexts.discover(_client(), limit=10)
    assert len(works) == 3
    assert _by_title(works, "CC-BY-SA").declared_license == _BY_SA
    assert _by_title(works, "CC-BY-NC").declared_license == _BY_NC
    assert _by_title(works, "CC-BY-ND").declared_license == _BY_ND


def test_ccbysa_ingests_servable(temp_substrate):
    w = _by_title(libretexts.discover(_client(), limit=10), "CC-BY-SA")
    outcome = ingest_textbook(
        w, _client(), investigation_id="inv-test",
        db_path=temp_substrate["db_path"], embedder=StubEmbedder(),
    )
    assert outcome.ingested is True, outcome.skipped_reason
    assert outcome.content_class in SERVABLE_CONTENT_CLASSES
    assert outcome.content_class == "source_declared_open"
    assert outcome.servable_full_text is True
    assert outcome.license_basis and "CC BY-SA" in outcome.license_basis


def test_ccbync_routes_to_classify_class_not_public_domain():
    w = _by_title(libretexts.discover(_client(), limit=10), "CC-BY-NC")
    result = w.classification()
    expected = classify(_BY_NC, {}, legitimate_source=True)
    # Route to EXACTLY whatever classify() returns — no baked-in assumption.
    assert result.content_class == expected.content_class
    # The rigor trap: NC must NEVER be flattened to public_domain.
    assert result.content_class != "public_domain"
    # Per the current SPR-02 map, NC gates (deny-by-default for commercial use).
    assert result.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert result.servable is False


def test_ccbynd_routes_to_classify_class_not_public_domain():
    w = _by_title(libretexts.discover(_client(), limit=10), "CC-BY-ND")
    result = w.classification()
    expected = classify(_BY_ND, {}, legitimate_source=True)
    assert result.content_class == expected.content_class
    assert result.content_class != "public_domain"
    assert result.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert result.servable is False


def test_no_license_routes_gated():
    item = {
        "id": "nolic",
        "title": "Map: undeclared-license Chemistry",
        "pdf_url": "https://chem.libretexts.org/nolic.pdf",
    }
    client = FakeClient(
        json_by_url={libretexts.LIBRETEXTS_CONTENT_URL: {"items": [item]}}
    )
    (w,) = libretexts.discover(client, limit=10)
    assert w.declared_license is None
    result = w.classification()
    assert result.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert result.servable is False


def test_ccbync_ingests_gated_body_withheld(temp_substrate):
    w = _by_title(libretexts.discover(_client(), limit=10), "CC-BY-NC")
    outcome = ingest_textbook(
        w, _client(), investigation_id="inv-test",
        db_path=temp_substrate["db_path"], embedder=StubEmbedder(),
    )
    # Gated works are still INGESTED (chunked/embedded) but never servable.
    assert outcome.ingested is True, outcome.skipped_reason
    assert outcome.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert outcome.servable_full_text is False
    assert outcome.servability == "gated_metadata_only"
