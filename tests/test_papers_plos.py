"""Tests for the PLOS connector (SPR-07 M5a).

NO live HTTP: PLOS solr responses come from an ``httpx.MockTransport`` feed.

PLOS is uniformly CC-BY, but the servable class STILL flows through the
chokepoint (classify) — the connector records the catalog CC-BY as the declared
license and hands it to classify, never stamping a content_class directly. The
license_basis names the PLOS catalog CC-BY basis.
"""

from __future__ import annotations

import os
import sys

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import acquisition.papers._pipeline as pipeline  # noqa: E402
from acquisition.papers import classify_paper  # noqa: E402
from acquisition.papers.plos import (  # noqa: E402
    PLOS_CATALOG_LICENSE_URI,
    article_to_record,
    parse_search_response,
    search_articles,
)
from substrate.constants import SERVABLE_CONTENT_CLASSES  # noqa: E402


def _payload() -> dict:
    return {
        "response": {
            "docs": [
                {
                    "id": "10.1371/journal.pone.0000001",
                    "title_display": ["A PLOS ONE Article"],
                    "abstract": ["A clean open-access body."],
                    "author_display": ["Marie Curie", "Pierre Curie"],
                    "journal": "PLOS ONE",
                    "publication_date": "2024-03-01T00:00:00Z",
                },
                {
                    "id": "10.1371/journal.pbio.0000002",
                    "title_display": ["A PLOS Biology Article"],
                    "abstract": ["Another open body."],
                    "author_display": ["Rosalind Franklin"],
                    "journal": "PLOS Biology",
                },
            ]
        }
    }


def test_plos_article_is_servable_with_catalog_basis():
    records = parse_search_response(_payload())
    rec = records[0]
    cls = classify_paper(rec)
    assert cls.content_class in SERVABLE_CONTENT_CLASSES
    assert cls.servable is True
    assert cls.serve_body is True
    # Defensibility: the basis names the PLOS catalog CC-BY.
    assert "plos" in cls.license_basis.lower()
    assert "catalog cc-by" in cls.license_basis.lower()
    assert cls.license_basis.strip()


def test_plos_classification_goes_through_chokepoint_not_bypassed(monkeypatch):
    """PLOS does NOT stamp content_class directly — it routes through classify.
    We assert by spying on the chokepoint: classify_paper must call
    licenses_core.classify exactly once for a PLOS record."""
    import acquisition.licenses_core as lc

    calls = {"n": 0, "licenses": []}
    real_classify = lc.classify

    def _spy(license, source_declaration, *, legitimate_source):
        calls["n"] += 1
        calls["licenses"].append(license)
        return real_classify(license, source_declaration, legitimate_source=legitimate_source)

    # classify_paper calls the symbol imported into _pipeline, so patch there.
    monkeypatch.setattr(pipeline, "classify", _spy)

    rec = parse_search_response(_payload())[0]
    cls = classify_paper(rec)
    assert calls["n"] == 1
    # The license string handed to the chokepoint was the catalog CC-BY URI —
    # PLOS did not bypass classification by assigning a class itself.
    assert calls["licenses"][0] == PLOS_CATALOG_LICENSE_URI
    assert cls.servable is True


def test_plos_record_carries_catalog_license_string():
    rec = article_to_record(_payload()["response"]["docs"][0])
    # The connector records the catalog license as a STRING for classify; it
    # does not set a content_class field (there is none on the record).
    assert rec.license == PLOS_CATALOG_LICENSE_URI
    assert rec.doi == "10.1371/journal.pone.0000001"
    assert rec.title == "A PLOS ONE Article"
    assert not hasattr(rec, "content_class")


def test_plos_servable_record_license_basis_names_catalog():
    """G5: a servable PLOS article's basis names the PLOS catalog CC-BY — the
    defensible per-source basis the sprint permits, still via the chokepoint."""
    rec = parse_search_response(_payload())[0]
    cls = classify_paper(rec)
    assert cls.servable is True
    assert cls.license_basis and cls.license_basis.strip()
    assert "plos" in cls.license_basis.lower()
    assert "catalog cc-by" in cls.license_basis.lower()


def test_search_articles_mock_transport_no_live_http():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = search_articles(
        query="genome", limit=5, client=client,
        base_url="https://api.plos.org/search",
    )
    assert len(records) == 2
    assert all(r.license == PLOS_CATALOG_LICENSE_URI for r in records)
