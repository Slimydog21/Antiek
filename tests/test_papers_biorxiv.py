"""Tests for the bioRxiv / medRxiv connector (SPR-07 M4).

NO live HTTP: details come from an ``httpx.MockTransport`` feed.

The rigor-#3 invariant: per-record author-chosen license, NEVER a per-source
"preprint server => open" assumption. A CC-BY preprint -> servable; a "no-reuse"
preprint -> gated, body withheld. The dedup key is the preprint DOI.
"""

from __future__ import annotations

import os
import sys

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.papers import classify_paper, paper_candidate_ref  # noqa: E402
from acquisition.papers.biorxiv import (  # noqa: E402
    detail_to_record,
    fetch_details,
    parse_details_response,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.dedup import KeyType, identity_key  # noqa: E402


def _payload() -> dict:
    return {
        "collection": [
            {
                "doi": "10.1101/2024.01.01.000001",
                "title": "An Open Preprint",
                "abstract": "Open preprint abstract.",
                "license": "cc_by",  # author chose CC-BY
                "version": "1",
                "authors": "Ada Lovelace; Alan Turing",
                "category": "neuroscience",
            },
            {
                "doi": "10.1101/2024.01.02.000002",
                "title": "A No-Reuse Preprint",
                "abstract": "All rights reserved by the authors.",
                "license": "no-reuse",  # author forbade reuse
                "version": "1",
                "authors": "John Doe",
                "category": "genomics",
            },
            {
                "doi": "10.1101/2024.01.03.000003",
                "title": "A Non-Commercial Preprint",
                "abstract": "NC preprint.",
                "license": "cc_by_nc",  # NC -> gated per chokepoint policy
                "version": "2",
                "authors": "Jane Roe",
            },
        ]
    }


def test_biorxiv_cc_by_preprint_is_servable():
    records = parse_details_response(_payload(), server="biorxiv")
    cc = next(r for r in records if r.doi.endswith("000001"))
    cls = classify_paper(cc)
    assert cls.content_class in SERVABLE_CONTENT_CLASSES
    assert cls.servable is True
    assert cls.serve_body is True
    assert "biorxiv" in cls.license_basis.lower()
    assert ".license" in cls.license_basis  # names the field it read


def test_biorxiv_no_reuse_preprint_is_gated_body_withheld():
    records = parse_details_response(_payload(), server="biorxiv")
    nr = next(r for r in records if r.doi.endswith("000002"))
    cls = classify_paper(nr)
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.servable is False
    # Even though biorxiv offers a PDF host, a no-reuse body is never served.
    assert cls.serve_body is False


def test_biorxiv_nc_preprint_is_gated():
    records = parse_details_response(_payload(), server="biorxiv")
    nc = next(r for r in records if r.doi.endswith("000003"))
    cls = classify_paper(nc)
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.servable is False


def test_biorxiv_license_is_per_record_not_per_source():
    """Three preprints from the SAME server split servable/gated on their
    PER-RECORD license — proving no 'server => open' assumption."""
    records = parse_details_response(_payload(), server="biorxiv")
    verdicts = {r.doi[-6:]: classify_paper(r).servable for r in records}
    assert verdicts == {"000001": True, "000002": False, "000003": False}


def test_biorxiv_dedup_key_is_preprint_doi():
    rec = detail_to_record(
        {"doi": "10.1101/2024.05.05.123456", "title": "T", "license": "cc_by"},
        server="biorxiv",
    )
    ikey = identity_key(paper_candidate_ref(rec).identity_record())
    assert ikey.key_type is KeyType.DOI
    assert ikey.key == "10.1101/2024.05.05.123456"


def test_biorxiv_preprint_and_journal_doi_collapse_when_both_seen():
    """A preprint (preprint DOI) and its published version (journal DOI) are
    the same work; SPR-04 collapses them when a source surfaces the SAME DOI on
    both. Documented at the precedence level available: the dedup ladder keys
    on the shared DOI, so two records carrying one DOI collapse to one."""
    from acquisition.corpus_quality import dedup_candidates

    preprint = detail_to_record(
        {"doi": "10.1101/preprint.1", "title": "Same Work", "license": "cc_by"},
        server="biorxiv",
    )
    # A second source surfaces the SAME paper under the SAME DOI -> collapses.
    from acquisition.papers.core import work_to_record

    published = work_to_record(
        {"id": "p1", "doi": "10.1101/preprint.1", "title": "Same Work",
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "downloadUrl": "u"}
    )
    refs = [paper_candidate_ref(preprint), paper_candidate_ref(published)]
    result = dedup_candidates(refs)
    assert len(result.kept) == 1


def test_biorxiv_servable_record_license_basis_is_source_specific():
    """G5: a servable bioRxiv preprint carries a non-empty basis naming the
    server source + the license field."""
    cc = next(r for r in parse_details_response(_payload(), server="biorxiv")
              if r.doi.endswith("000001"))
    cls = classify_paper(cc)
    assert cls.servable is True
    assert cls.license_basis and cls.license_basis.strip()
    assert "biorxiv" in cls.license_basis.lower()
    assert ".license" in cls.license_basis


def test_fetch_details_mock_transport_both_servers():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = fetch_details(
        server="both", limit=10, client=client,
        base_url="https://api.biorxiv.org/details",
    )
    # both servers queried -> 3 records each -> 6 total
    assert len(records) == 6
    assert {r.source for r in records} == {"biorxiv", "medrxiv"}
