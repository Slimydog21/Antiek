"""HathiTrust connector tests (SPR-06 M5). No live network.

pd/pdus -> servable; ic/icus/und/unknown -> gated/skip (never servable).
"""

from __future__ import annotations

import pytest

from acquisition.books import hathitrust as ht
from acquisition.books.pd_connector_base import classify_and_ingest

from .conftest import (
    FakeFetcher,
    StubEmbedder,
    book_asset_row,
    count_servable_book_assets,
    make_pdf,
)

_PDF = make_pdf("A Hathi Book", "the body text of a digitized volume goes here")


def _bib_record(record_id, *, rights, htid="uc1.b000001", isbns=None, oclcs=None):
    return {
        "records": {
            record_id: {
                "title": "A Hathi Book",
                "isbns": isbns or [],
                "oclcs": oclcs or [],
            }
        },
        "items": [{"htid": htid, "rightsCode": rights, "fromRecord": record_id}],
    }


def _fetcher_for(record_id, record, *, htid="uc1.b000001"):
    return FakeFetcher(
        json_by_url={
            f"{ht.BIB_API_BASE}/recordnumber/{record_id}.json": record
        },
        bytes_by_url={f"{ht.PT_DOWNLOAD_BASE}?id={htid}": _PDF},
    )


# ---------------------------------------------------------------------------
# rights_code mapping (G3 keyword: rights_code)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["pd", "pdus", "pdus-land"])
def test_rights_code_pd_pdus_servable(temp_substrate, code):
    record_id = "100000001"
    record = _bib_record(record_id, rights=code)
    fetcher = _fetcher_for(record_id, record)
    (cand,) = ht.discover(fetcher, record_ids=[record_id], limit=1)
    # Assert classify()'s ACTUAL return, not a connector-side boolean: the
    # content_class + license_basis + ingest verdict all come from the SPR-02
    # chokepoint, and the basis NAMES the source + the resolved rights field.
    decision = cand.classification()
    assert decision.servable is True
    assert decision.content_class == "public_domain"
    assert decision.ingest is True
    assert decision.license_basis.startswith("public_domain:")
    assert f"HathiTrust rights={code}" in decision.license_basis

    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.servable is True
    # The row echoes the gate's verdict verbatim — an auditor reads "why
    # servable?" off this single row.
    assert outcome.content_class == decision.content_class
    assert outcome.license_basis == decision.license_basis
    cc, basis, _ = book_asset_row(temp_substrate["db_path"], outcome.document_id)
    assert cc == "public_domain"
    assert basis == decision.license_basis
    assert basis and f"rights={code}" in basis


@pytest.mark.parametrize("code", ["ic", "icus", "und"])
def test_rights_code_in_copyright_and_undetermined_gated(temp_substrate, code):
    record_id = "200000002"
    record = _bib_record(record_id, rights=code)
    fetcher = _fetcher_for(record_id, record)
    (cand,) = ht.discover(fetcher, record_ids=[record_id], limit=1)
    decision = cand.classification()
    assert decision.servable is False
    assert decision.content_class == "restricted_pending_opt_in"

    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is False
    assert outcome.content_class == "restricted_pending_opt_in"
    assert count_servable_book_assets(temp_substrate["db_path"]) == 0


def test_rights_code_unknown_is_gated_never_servable():
    """An UNRECOGNIZED rights code is treated as undetermined -> gated, never
    rounded up to servable (deny-by-default)."""
    uri, signal = ht.hathi_rights_input("some-new-code-we-dont-know")
    assert uri is None and signal is None


def test_rights_code_mapping_function_is_explicit():
    """pd/pdus/pdus-land map to a positive signal; everything else to
    (None, None). pdus-land is a real HathiTrust public-domain-in-US code
    (land-grant digitization) — recognized as PD because the US is the serving
    jurisdiction; never left in a non-PD documentation set that the verdict
    would have to consult."""
    assert ht.hathi_rights_input("pd")[1] == "HathiTrust rights=pd"
    assert ht.hathi_rights_input("pdus")[1] == "HathiTrust rights=pdus"
    assert ht.hathi_rights_input("pdus-land")[1] == "HathiTrust rights=pdus-land"
    # Case/whitespace-insensitive: a code arriving upper-cased still resolves.
    assert ht.hathi_rights_input("  PDUS-LAND ")[1] == "HathiTrust rights=pdus-land"
    for code in ("ic", "icus", "und", "", None):
        assert ht.hathi_rights_input(code) == (None, None)
    # The documented non-PD set contains only real restriction codes and is
    # never consulted for the verdict (deny-by-default off the PD set alone),
    # so no genuinely-PD code is mislabeled as restricted.
    assert ht._NON_PD_RIGHTS_CODES.isdisjoint(ht._PD_RIGHTS_CODES)
    assert "pdus-land" in ht._PD_RIGHTS_CODES


# ---------------------------------------------------------------------------
# discover + dedup identity
# ---------------------------------------------------------------------------


def test_discover_returns_n_candidates():
    record_id = "300000003"
    record = _bib_record(record_id, rights="pd")
    fetcher = _fetcher_for(record_id, record)
    cands = ht.discover(fetcher, record_ids=[record_id], limit=5)
    assert len(cands) == 1
    assert cands[0].source == "hathitrust"
    assert cands[0].source_id.startswith("hathitrust:")


def test_isbn_drives_dedup_identity_when_present():
    record_id = "400000004"
    record = _bib_record(record_id, rights="pd", isbns=["9780131103627"])
    fetcher = _fetcher_for(record_id, record)
    (cand,) = ht.discover(fetcher, record_ids=[record_id], limit=1)
    assert cand.isbn == "9780131103627"


def test_license_basis_names_rights_code(temp_substrate):
    record_id = "500000005"
    record = _bib_record(record_id, rights="pdus")
    fetcher = _fetcher_for(record_id, record)
    (cand,) = ht.discover(fetcher, record_ids=[record_id], limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is True
    assert outcome.license_basis and "rights=pdus" in outcome.license_basis
