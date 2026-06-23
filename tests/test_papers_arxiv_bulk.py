"""Tests for the arXiv bulk-dataset mass path (SPR-07 M5b).

NO live HTTP and NO export-API call: discovery reads a fixture JSON-Lines
snapshot via the SPR-03 bulk reader. A CC-licensed paper -> servable; an arXiv
default-terms / unlicensed paper -> gated. Per-record license read.
"""

from __future__ import annotations

import io
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.client import ArxivPaper  # noqa: E402
from acquisition.papers import classify_paper, paper_candidate_ref  # noqa: E402
from acquisition.papers.arxiv_bulk import (  # noqa: E402
    bulk_records_from_path,
    iter_bulk_records,
    paper_to_record,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.dedup import KeyType, identity_key  # noqa: E402

_CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


def _snapshot_lines() -> str:
    import json

    records = [
        {
            "id": "2401.00001",
            "title": "A CC-BY arXiv Paper",
            "abstract": "Open arXiv paper.",
            "authors_parsed": [["Lovelace", "Ada", ""]],
            "categories": "cs.LG",
            "license": _CC_BY,
            "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 00:00:00 GMT"}],
            "doi": "10.1/cc-by-arxiv",
        },
        {
            "id": "2401.00002",
            "title": "A Default-Terms arXiv Paper",
            "abstract": "Default arXiv terms — author retains copyright.",
            "authors_parsed": [["Babbage", "Charles", ""]],
            "categories": "cs.LG",
            "license": _ARXIV_DEFAULT,
            "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 00:00:00 GMT"}],
        },
        {
            "id": "2401.00003",
            "title": "An Unlicensed arXiv Paper",
            "abstract": "No license declared.",
            "authors_parsed": [["Turing", "Alan", ""]],
            "categories": "cs.AI",
            "license": None,
            "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 00:00:00 GMT"}],
        },
    ]
    return "\n".join(json.dumps(r) for r in records) + "\n"


def test_bulk_cc_paper_servable_default_paper_gated():
    records = list(iter_bulk_records(io.StringIO(_snapshot_lines())))
    by_id = {r.arxiv_id: r for r in records}

    cc = classify_paper(by_id["2401.00001"])
    assert cc.content_class in SERVABLE_CONTENT_CLASSES
    assert cc.servable is True
    assert cc.serve_body is True

    default = classify_paper(by_id["2401.00002"])
    assert default.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert default.servable is False
    assert default.serve_body is False

    unlicensed = classify_paper(by_id["2401.00003"])
    assert unlicensed.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert unlicensed.servable is False


def test_bulk_per_record_license_read():
    """Each bulk record's license drives its own verdict — not a per-source
    'arXiv is open' assumption."""
    records = list(iter_bulk_records(io.StringIO(_snapshot_lines())))
    verdicts = {r.arxiv_id: classify_paper(r).servable for r in records}
    assert verdicts == {"2401.00001": True, "2401.00002": False, "2401.00003": False}


def test_bulk_servable_record_license_basis_is_source_specific():
    """G5: a servable arXiv-bulk record carries a non-empty basis naming the
    bulk source + the metadata license field."""
    records = list(iter_bulk_records(io.StringIO(_snapshot_lines())))
    cc = next(r for r in records if r.arxiv_id == "2401.00001")
    cls = classify_paper(cc)
    assert cls.servable is True
    assert cls.license_basis and cls.license_basis.strip()
    assert "arxiv_bulk" in cls.license_basis.lower()
    assert "bulk metadata license" in cls.license_basis.lower()


def test_bulk_records_from_path(tmp_path):
    snap = tmp_path / "snapshot.json"
    snap.write_text(_snapshot_lines(), encoding="utf-8")
    records = bulk_records_from_path(str(snap), category="cs.LG", limit=10)
    # category filter -> only the two cs.LG records
    assert {r.arxiv_id for r in records} == {"2401.00001", "2401.00002"}


def test_bulk_record_keyed_on_doi_then_arxiv():
    """DOI precedence over arXiv id when the snapshot carries a DOI; arXiv id
    otherwise."""
    rec_with_doi = list(iter_bulk_records(io.StringIO(_snapshot_lines())))[0]
    ikey = identity_key(paper_candidate_ref(rec_with_doi).identity_record())
    assert ikey.key_type is KeyType.DOI

    no_doi = paper_to_record(
        ArxivPaper(
            arxiv_id="2401.99999", version="v1", title="T", authors=["A"],
            abstract="a", categories=["cs.LG"], primary_category="cs.LG",
            published_at=None, updated_at=None,
            abs_url="https://arxiv.org/abs/2401.99999",
            pdf_url="https://arxiv.org/pdf/2401.99999",
            license_uri=_CC0, raw_id="2401.99999", metadata={},
        )
    )
    ikey2 = identity_key(paper_candidate_ref(no_doi).identity_record())
    assert ikey2.key_type is KeyType.ARXIV
    assert ikey2.key == "2401.99999"


def test_bulk_path_makes_no_export_api_call():
    """The mass path reads the snapshot only — it must not call the export
    endpoint. The module source carries no ``export.arxiv.org`` literal (G4 in
    code form), and discovery + fetch compose only the SPR-03 bulk reader +
    PDF-host fetch."""
    import acquisition.papers.arxiv_bulk as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "export.arxiv.org" not in src
    # The discovery surface composes the bulk reader, not the export search.
    assert "iter_bulk_candidates" in src
    assert "bulk_candidates_from_path" in src
    # No use of the export client's search/fetch_by_id entrypoints.
    assert "export/api/query" not in src.lower()
