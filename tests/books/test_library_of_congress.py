"""Library of Congress connector tests (SPR-06 M5). No live network."""

from __future__ import annotations

from acquisition.books import library_of_congress as loc
from acquisition.books.pd_connector_base import classify_and_ingest

from .conftest import (
    FakeFetcher,
    StubEmbedder,
    book_asset_row,
    count_servable_book_assets,
    make_pdf,
)

_PDF = make_pdf("A LoC Pamphlet", "the digitized text of a public-domain pamphlet")


def _loc_item(item_id, *, rights, pdf="https://tile.loc.gov/storage/item.pdf", lccn=None):
    item = {
        "id": item_id,
        "url": f"https://www.loc.gov/item/{item_id}/",
        "title": "A LoC Pamphlet",
        "rights": rights,
        "resources": [{"pdf": pdf}],
    }
    if lccn:
        item["number_lccn"] = [lccn]
    return item


def _fetcher_for(items, *, collection="selected-digitized-books"):
    url = f"{loc.LOC_SEARCH_BASE}/collections/{collection}/"
    bytes_by_url = {}
    for it in items:
        for res in it.get("resources", []):
            if res.get("pdf"):
                bytes_by_url[res["pdf"]] = _PDF
    return FakeFetcher(
        json_by_url={url: {"results": items}}, bytes_by_url=bytes_by_url
    )


def test_discover_returns_n_candidates():
    items = [_loc_item("p1", rights="No known copyright restrictions", lccn="12345678")]
    fetcher = _fetcher_for(items)
    cands = loc.discover(fetcher, limit=5)
    assert len(cands) == 1
    assert cands[0].source == "library_of_congress"
    assert cands[0].source_id == "library_of_congress:12345678"


def test_pd_rights_statement_ingests_servable_with_basis(temp_substrate):
    items = [_loc_item("p1", rights="No known copyright restrictions", lccn="12345678")]
    fetcher = _fetcher_for(items)
    (cand,) = loc.discover(fetcher, limit=1)
    # PD established from the rights statement, not assumed.
    assert cand.pd_signal and "rights statement" in cand.pd_signal.lower()

    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.content_class == "public_domain"
    assert outcome.servable is True
    cc, basis, _ = book_asset_row(temp_substrate["db_path"], outcome.document_id)
    assert cc == "public_domain"
    assert basis and "Library of Congress" in basis


def test_pd_mark_url_ingests_servable(temp_substrate):
    items = [_loc_item(
        "p2",
        rights="https://creativecommons.org/publicdomain/mark/1.0/",
        lccn="99999999",
    )]
    fetcher = _fetcher_for(items)
    (cand,) = loc.discover(fetcher, limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is True
    assert outcome.content_class == "public_domain"


def test_unclear_rights_item_is_gated_not_servable(temp_substrate):
    """A non-PD / unclear LoC item is gated or skipped (M5 AC)."""
    items = [_loc_item("p3", rights="Rights restricted; permission required", lccn="11112222")]
    fetcher = _fetcher_for(items)
    (cand,) = loc.discover(fetcher, limit=1)
    assert cand.license_uri is None and cand.pd_signal is None
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is False
    assert outcome.content_class == "restricted_pending_opt_in"
    assert count_servable_book_assets(temp_substrate["db_path"]) == 0


def test_blank_rights_item_is_gated(temp_substrate):
    items = [_loc_item("p4", rights="", lccn="33334444")]
    fetcher = _fetcher_for(items)
    (cand,) = loc.discover(fetcher, limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is False
    assert count_servable_book_assets(temp_substrate["db_path"]) == 0


def test_copyright_claim_rights_is_gated():
    uri, signal = loc.loc_rights_input({"rights": "© 1998 The Author. All rights reserved."})
    assert uri is None and signal is None


def test_license_basis_naming_for_servable(temp_substrate):
    items = [_loc_item("p5", rights="Public domain", lccn="55556666")]
    fetcher = _fetcher_for(items)
    (cand,) = loc.discover(fetcher, limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is True
    assert outcome.license_basis and "Library of Congress" in outcome.license_basis
