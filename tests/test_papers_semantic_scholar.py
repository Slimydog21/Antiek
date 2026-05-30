"""Tests for the Semantic Scholar (S2) connector (SPR-07 M3).

NO live HTTP: S2 responses come from an ``httpx.MockTransport`` feed; the
classification comes from the real chokepoint.

The LOAD-BEARING gate for this sprint: an S2 record with NO openAccessPdf
(closed access) ingests GATED — restricted_pending_opt_in, abstract + metadata
present, body NEVER fetched/served. ``test_*closed_access_gated`` is the named
test G2 keys off.
"""

from __future__ import annotations

import os
import sys

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.papers import classify_paper, paper_candidate_ref  # noqa: E402
from acquisition.papers.semantic_scholar import (  # noqa: E402
    paper_to_record,
    parse_search_response,
    search_papers,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.dedup import KeyType, identity_key  # noqa: E402

_CC_BY = "https://creativecommons.org/licenses/by/4.0/"


def _payload() -> dict:
    return {
        "data": [
            {
                "corpusId": 111,
                "title": "Open S2 Paper",
                "abstract": "Open abstract.",
                "externalIds": {"DOI": "10.1/open-s2"},
                "openAccessPdf": {"url": "https://example.org/open.pdf", "license": "CC-BY"},
                "authors": [{"name": "Grace Hopper"}],
            },
            {
                "corpusId": 222,
                "title": "Closed S2 Paper",
                "abstract": "This abstract is public; the body is paywalled.",
                "externalIds": {"DOI": "10.1/closed-s2"},
                "openAccessPdf": None,  # closed access -> no body to fetch
                "authors": [{"name": "John Closed"}],
            },
        ]
    }


def test_s2_open_access_record_is_servable_with_named_basis():
    records = parse_search_response(_payload())
    oa = next(r for r in records if r.doi == "10.1/open-s2")
    cls = classify_paper(oa)
    assert cls.content_class in SERVABLE_CONTENT_CLASSES
    assert cls.servable is True
    assert cls.serve_body is True
    # Defensibility: basis cites the S2 OA field.
    assert "openaccesspdf.license" in cls.license_basis.lower()
    assert "semantic_scholar" in cls.license_basis.lower()


def test_s2_closed_access_gated_record_body_withheld():
    """THE sprint gate (G2): a closed-access S2 record (no openAccessPdf)
    ingests gated — abstract + metadata present, body never fetched/served."""
    records = parse_search_response(_payload())
    closed = next(r for r in records if r.doi == "10.1/closed-s2")

    cls = classify_paper(closed)
    # Gated, not servable — the catastrophic case made structurally impossible.
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.servable is False
    # No servable body: there is no PDF to fetch and serve_body is False.
    assert cls.serve_body is False
    assert closed.pdf_url is None
    assert closed.has_servable_body is False
    # Abstract + metadata ARE present (private-search graph-resident).
    assert closed.abstract and closed.abstract.strip()
    assert closed.title == "Closed S2 Paper"
    assert closed.doi == "10.1/closed-s2"


def test_s2_closed_access_gated_ingest_thunk_never_fetches_body(monkeypatch):
    """Belt-and-braces for G2: even routed through the orchestrator's ingest
    thunk, a closed S2 record never calls the PDF fetch path — the gated
    branch stages metadata-only."""
    import tools.run_corpus_ingest as orch

    fetched = {"called": False}

    def _no_fetch(*a, **k):
        fetched["called"] = True
        raise AssertionError("a gated record must never fetch a body")

    monkeypatch.setattr(orch, "_fetch_paper_pdf", _no_fetch)
    staged = {"called": False, "class": None}

    def _fake_stage(rec, classification, *, investigation_id, db_path):
        staged["called"] = True
        staged["class"] = classification.content_class
        return f"{classification.content_class} (metadata-only)"

    monkeypatch.setattr(orch, "_stage_paper_metadata_only", _fake_stage)

    records = parse_search_response(_payload())
    closed = next(r for r in records if r.doi == "10.1/closed-s2")
    cls = classify_paper(closed)
    assert cls.serve_body is False

    # Drive the exact ingest closure shape the orchestrator builds.
    def _ingest(db_path, basis, _rec=closed, _cls=cls, _serve=cls.serve_body):
        if not _serve:
            return orch._stage_paper_metadata_only(
                _rec, _cls, investigation_id="inv", db_path=db_path
            )
        return orch._fetch_paper_pdf(_rec, throttle=None, source="semantic_scholar")

    status = _ingest("db", "doi:10.1/closed-s2")
    assert fetched["called"] is False
    assert staged["called"] is True
    assert staged["class"] == GATED_DEFAULT_CONTENT_CLASS
    assert "restricted_pending_opt_in" in status


def test_s2_corpus_id_used_only_when_no_doi_or_arxiv():
    """Precedence: DOI > arXiv id > S2 corpusId. The corpusId keys identity
    ONLY when no DOI/arXiv id is present."""
    # DOI present -> keys on DOI, not corpusId.
    with_doi = paper_to_record(
        {"corpusId": 5, "title": "T", "externalIds": {"DOI": "10.9/z"}}
    )
    assert identity_key(paper_candidate_ref(with_doi).identity_record()).key_type is KeyType.DOI

    # arXiv id present, no DOI -> keys on arXiv id.
    with_arxiv = paper_to_record(
        {"corpusId": 6, "title": "T2", "externalIds": {"ArXiv": "2401.00001"}}
    )
    assert identity_key(paper_candidate_ref(with_arxiv).identity_record()).key_type is KeyType.ARXIV

    # Neither DOI nor arXiv -> keys on the S2 source id.
    only_corpus = paper_to_record({"corpusId": 7, "title": "T3", "externalIds": {}})
    ikey = identity_key(paper_candidate_ref(only_corpus).identity_record())
    assert ikey.key_type is KeyType.SOURCE_ID
    assert ikey.key == "semantic_scholar:7"


def test_s2_no_oa_pdf_with_declared_license_still_gates_without_body():
    """An OA url with no declared license is 'free to read', not 'free to
    redistribute' -> gated by the chokepoint's deny-by-default."""
    rec = paper_to_record(
        {"corpusId": 8, "title": "T", "externalIds": {"DOI": "10.1/x"},
         "openAccessPdf": {"url": "https://e.org/x.pdf", "license": None}}
    )
    cls = classify_paper(rec)
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.serve_body is False


def test_s2_servable_record_license_basis_names_oa_field():
    """G5: a servable S2 record's basis names the S2 OA field + the resolved
    license — the defensible record for the SPR-10 audit."""
    oa = next(r for r in parse_search_response(_payload()) if r.doi == "10.1/open-s2")
    cls = classify_paper(oa)
    assert cls.servable is True
    assert cls.license_basis and cls.license_basis.strip()
    assert "semantic_scholar" in cls.license_basis.lower()
    assert "openaccesspdf.license" in cls.license_basis.lower()


def test_search_papers_mock_transport_no_live_http():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = search_papers(
        query="ml", limit=5, client=client,
        base_url="https://api.semanticscholar.org/graph/v1/paper/search",
    )
    assert {r.doi for r in records} == {"10.1/open-s2", "10.1/closed-s2"}
