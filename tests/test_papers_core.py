"""Tests for the CORE aggregator connector (SPR-07 M2).

NO live HTTP: CORE responses come from an ``httpx.MockTransport`` feed; the
classification comes from the real chokepoint. The asserted invariant:
  - a CORE OA record (CC-BY license) -> servable with a source-specific
    license_basis naming ``CORE work.license`` and the resolved license;
  - a CORE closed/unknown-license record -> restricted_pending_opt_in (gated),
    body NOT fetched-for-serving;
  - the content_class comes ONLY from the chokepoint (classify), never inline.
"""

from __future__ import annotations

import os
import sys

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.papers import classify_paper  # noqa: E402
from acquisition.papers.core import (  # noqa: E402
    parse_works_response,
    search_works,
    work_to_record,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)

_CC_BY = "https://creativecommons.org/licenses/by/4.0/"


def _payload() -> dict:
    return {
        "results": [
            {
                "id": "12345",
                "doi": "10.1234/oa-open",
                "title": "An Open Access Paper",
                "license": _CC_BY,
                "abstract": "We study open things.",
                "authors": [{"name": "Ada Lovelace"}],
                "downloadUrl": "https://core.ac.uk/download/12345.pdf",
            },
            {
                "id": "67890",
                "doi": "10.1234/closed",
                "title": "A Closed-License Paper",
                "license": None,  # CORE marks "open" but declares no license
                "abstract": "Reading allowed, redistribution not granted.",
                "authors": [{"name": "Charles Babbage"}],
                "downloadUrl": "https://core.ac.uk/download/67890.pdf",
            },
        ]
    }


def test_core_oa_record_is_servable_with_named_basis():
    records = parse_works_response(_payload())
    oa = next(r for r in records if r.doi == "10.1234/oa-open")
    cls = classify_paper(oa)
    assert cls.content_class in SERVABLE_CONTENT_CLASSES
    assert cls.servable is True
    assert cls.serve_body is True  # has a download URL -> body fetchable
    # Defensibility: the basis NAMES the source + the field it read.
    assert "core" in cls.license_basis.lower()
    assert "work.license" in cls.license_basis
    assert cls.license_basis.strip()


def test_core_closed_record_is_gated_body_not_served():
    records = parse_works_response(_payload())
    closed = next(r for r in records if r.doi == "10.1234/closed")
    cls = classify_paper(closed)
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.servable is False
    # A gated record's body is NEVER fetched-for-serving even though CORE
    # offered a download URL — serve_body is False because the class is gated.
    assert cls.serve_body is False


def test_core_per_record_license_read_not_assumed_open():
    """The two records share a source ('CORE') but split servable/gated on
    their PER-RECORD declared license — not a per-source 'CORE is open'
    assumption."""
    records = parse_works_response(_payload())
    verdicts = {r.doi: classify_paper(r).servable for r in records}
    assert verdicts["10.1234/oa-open"] is True
    assert verdicts["10.1234/closed"] is False


def test_search_works_uses_mock_transport_no_live_http():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "core.ac.uk" in str(request.url) or "example" in str(request.url)
        return httpx.Response(200, json=_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = search_works(
        query="open science", limit=5, client=client,
        base_url="https://api.core.ac.uk/v3/search/works",
    )
    assert len(records) == 2
    assert {r.doi for r in records} == {"10.1234/oa-open", "10.1234/closed"}


def test_core_servable_record_license_basis_is_source_specific():
    """G5: a servable CORE record carries a non-empty basis NAMING the source
    + the field that justified it (not a bare 'open')."""
    oa = next(r for r in parse_works_response(_payload()) if r.doi == "10.1234/oa-open")
    cls = classify_paper(oa)
    assert cls.servable is True
    assert cls.license_basis and cls.license_basis.strip()
    assert "core" in cls.license_basis.lower()
    assert "work.license" in cls.license_basis
    # Not a bare generic token.
    assert cls.license_basis.strip().lower() not in {"open", "oa", "cc-by"}


def test_core_record_keyed_on_doi_precedence():
    rec = work_to_record(
        {"id": "999", "doi": "10.5/aaa", "title": "T", "license": _CC_BY,
         "downloadUrl": "u"}
    )
    from acquisition.papers import paper_candidate_ref
    from substrate.dedup import KeyType, identity_key

    ikey = identity_key(paper_candidate_ref(rec).identity_record())
    assert ikey.key_type is KeyType.DOI
    assert ikey.key == "10.5/aaa"


def test_orchestrator_routes_core_oa_source_through_papers(monkeypatch, capsys):
    """`--source open_access --oa-source core --dry-run` routes through the
    papers package, classifies via the chokepoint, and prints per-record
    stable id + content_class + license_basis — no network, no writes."""
    import tools.run_corpus_ingest as orch

    records = parse_works_response(_payload())

    # Replace the network discovery with fixture records (no live HTTP).
    monkeypatch.setattr(
        orch, "_discover_paper_records",
        lambda **kw: records,
    )
    rc = orch.main([
        "--source", "open_access", "--oa-source", "core",
        "--oa-query", "x", "--limit", "5", "--dry-run",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    # Both records appear in the plan with their source-id basis; the OA one is
    # servable, the closed one gated — both printed, neither written (dry-run).
    assert "DRY RUN" in out
    assert "would ingest" in out
    assert "wrote nothing" in out
