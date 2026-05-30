"""Internet Archive connector tests (SPR-06 M4). No live network.

The decisive tests are the NEGATIVE ones: an IA item WITHOUT established PD
status must produce zero servable book_asset rows (deny-by-default).
"""

from __future__ import annotations

from acquisition.books import internet_archive as ia
from acquisition.books.pd_connector_base import classify_and_ingest

from .conftest import (
    FakeFetcher,
    StubEmbedder,
    book_asset_row,
    count_servable_book_assets,
    make_pdf,
)

_PDF = make_pdf("Walden", "I went to the woods because I wished to live deliberately")


def _search_response(identifiers):
    return {"response": {"docs": [{"identifier": i} for i in identifiers]}}


def _metadata(identifier, meta, *, with_pdf=True):
    files = [{"name": f"{identifier}.pdf"}] if with_pdf else [{"name": "meta.xml"}]
    return {"metadata": meta, "files": files}


def _fetcher_for(identifiers, metas, *, query=None):
    """Build a FakeFetcher for the layer-1 search + per-item metadata calls."""
    # The search URL carries params, but FakeFetcher keys on URL only, so the
    # advancedsearch URL is the same regardless of params.
    json_by_url = {ia.ADVANCEDSEARCH_URL: _search_response(identifiers)}
    bytes_by_url = {}
    for ident in identifiers:
        json_by_url[f"{ia.METADATA_BASE}/{ident}"] = metas[ident]
        bytes_by_url[f"{ia.DOWNLOAD_BASE}/{ident}/{ident}.pdf"] = _PDF
    return FakeFetcher(json_by_url=json_by_url, bytes_by_url=bytes_by_url)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


def test_discover_returns_candidates_with_two_layer_filter():
    ident = "waldenpd"
    metas = {ident: _metadata(ident, {
        "title": "Walden",
        "creator": "Henry David Thoreau",
        "possible-copyright-status": "NOT_IN_COPYRIGHT",
    })}
    fetcher = _fetcher_for([ident], metas)
    cands = ia.discover(fetcher, limit=5)
    assert len(cands) == 1
    # Layer 1 (search) AND layer 2 (per-item metadata) both ran.
    assert ia.ADVANCEDSEARCH_URL in fetcher.json_calls
    assert f"{ia.METADATA_BASE}/{ident}" in fetcher.json_calls


def test_discovery_query_carries_not_in_copyright_filter():
    """Layer-1: the discovery query is constrained to NOT_IN_COPYRIGHT."""
    assert "NOT_IN_COPYRIGHT" in ia.PD_QUERY_FILTER


# ---------------------------------------------------------------------------
# established PD -> servable
# ---------------------------------------------------------------------------


def test_established_pd_status_ingests_servable_with_field_basis(temp_substrate):
    ident = "waldenpd"
    metas = {ident: _metadata(ident, {
        "title": "Walden",
        "creator": "Henry David Thoreau",
        "possible-copyright-status": "NOT_IN_COPYRIGHT",
    })}
    fetcher = _fetcher_for([ident], metas)
    (cand,) = ia.discover(fetcher, limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.content_class == "public_domain"
    assert outcome.servable is True
    cc, basis, _ = book_asset_row(temp_substrate["db_path"], outcome.document_id)
    assert cc == "public_domain"
    # license_basis quotes the exact IA field that established PD.
    assert basis and "NOT_IN_COPYRIGHT" in basis


def test_pd_licenseurl_mark_ingests_servable(temp_substrate):
    ident = "cc0item"
    metas = {ident: _metadata(ident, {
        "title": "A CC0 work",
        "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
    })}
    fetcher = _fetcher_for([ident], metas)
    (cand,) = ia.discover(fetcher, limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is True
    assert outcome.content_class == "public_domain"


# ---------------------------------------------------------------------------
# NOT established PD -> gated, never servable (the centerpiece, G2 keywords)
# ---------------------------------------------------------------------------


def test_item_without_pd_status_is_gated_not_servable(temp_substrate):
    """An IA item with NO copyright flag is undetermined -> gated
    restricted_pending_opt_in, zero servable book_asset (deny-by-default)."""
    ident = "mysterytext"
    metas = {ident: _metadata(ident, {
        "title": "Some Scanned Book",
        "creator": "Unknown",
        # No copyright-status, no licenseurl, no rights field at all.
    })}
    fetcher = _fetcher_for([ident], metas)
    (cand,) = ia.discover(fetcher, limit=1)
    assert cand.license_uri is None and cand.pd_signal is None

    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    # The work is ingested (legitimate source) but GATED — body withheld.
    assert outcome.content_class == "restricted_pending_opt_in"
    assert outcome.servable is False
    assert count_servable_book_assets(temp_substrate["db_path"]) == 0


def test_not_pd_in_copyright_item_is_gated(temp_substrate):
    """An item whose rights explicitly assert copyright is gated, not PD —
    even though IA's 'free' framing is tempting (fairness #2 steelman broken)."""
    ident = "incopyrighttext"
    metas = {ident: _metadata(ident, {
        "title": "Modern Bestseller",
        "rights": "All rights reserved",
        "possible-copyright-status": "IN_COPYRIGHT",
    })}
    fetcher = _fetcher_for([ident], metas)
    (cand,) = ia.discover(fetcher, limit=1)
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is False
    assert outcome.content_class == "restricted_pending_opt_in"
    assert count_servable_book_assets(temp_substrate["db_path"]) == 0


def test_negated_public_domain_is_undetermined_gated():
    """'NOT in the public domain' must not be accepted on the PD substring."""
    uri, signal = ia.ia_rights_input(
        {"rights": "This work is NOT in the public domain"}
    )
    assert uri is None and signal is None


def test_copyright_claim_with_pd_token_is_gated():
    """©+year alongside a PD token denies PD (the higher-cost false positive)."""
    uri, signal = ia.ia_rights_input(
        {"rights": "© 2021 Penguin. Public domain text reproduced."}
    )
    assert uri is None and signal is None


def test_two_layer_per_item_recheck_catches_mistagged_search_result(temp_substrate):
    """Defence in depth: a discovery query can return a stale/mis-tagged record,
    so the per-item layer-2 re-check re-runs the rights mapping on the item's
    OWN metadata. Here layer-1 surfaced an id, but the item's real metadata has
    no PD status -> the candidate is gated, never servable."""
    ident = "mistagged"
    # The search returned it (layer 1), but the item metadata establishes no PD.
    metas = {ident: _metadata(ident, {"title": "Mistagged", "rights": ""})}
    fetcher = _fetcher_for([ident], metas)
    (cand,) = ia.discover(fetcher, limit=1)
    # Layer-2 re-check ran on the item's own metadata.
    assert f"{ia.METADATA_BASE}/{ident}" in fetcher.json_calls
    assert cand.license_uri is None and cand.pd_signal is None
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.servable is False
    assert count_servable_book_assets(temp_substrate["db_path"]) == 0
