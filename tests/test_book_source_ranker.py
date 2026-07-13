"""Tests for ``substrate.book_source_ranker`` — the acquisition source-ranking
substrate (book-purchase-transport spec invariant #3).

Each test isolates ONE precedence tier (DRM-free > cost-type > price >
provenance_strength > source_key) so the sort key is exercised independently,
plus the honest states (no candidates -> None recommended; all DRM-locked ->
honest fallback verdict) and the validation raises."""

from __future__ import annotations

import pytest

from substrate.book_source_ranker import (
    PROVENANCE_ORDER,
    SourceCandidate,
    SourceRankerError,
    rank_book_sources,
)

_BOOK = "book://antiek/9780000000001"


def _cand(
    source_key: str,
    *,
    cost_type: str = "purchase",
    price_usd_cents: int = 0,
    drm_free: bool = True,
    rights_basis: str = "purchase:owned",
    provenance_strength: str = "established",
) -> SourceCandidate:
    return SourceCandidate(
        source_key=source_key,
        cost_type=cost_type,
        price_usd_cents=price_usd_cents,
        drm_free=drm_free,
        rights_basis=rights_basis,
        provenance_strength=provenance_strength,
    )


def test_no_candidates_yields_none_recommended() -> None:
    report = rank_book_sources(_BOOK, [])

    assert report.verdict == "no_candidates"
    assert report.recommended_source is None
    assert report.ranked_sources == ()
    assert report.has_drm_free_option is False
    assert report.has_free_option is False
    assert report.all_drm_locked is False
    assert report.authority == "advisory"
    assert "no candidate" in " ".join(report.notes)


def test_single_free_drm_free_is_cleanest_path() -> None:
    cand = _cand("standard_ebooks", cost_type="free", price_usd_cents=0,
                 drm_free=True, rights_basis="public_domain:US-pre-1929")
    report = rank_book_sources(_BOOK, [cand])

    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "standard_ebooks"
    assert report.recommended_source.recommended is True
    assert report.recommended_source.rank == 0
    assert report.verdict == "free_drm_free_preferred"
    assert report.has_drm_free_option is True
    assert report.has_free_option is True
    assert report.all_drm_locked is False


def test_paid_drm_free_when_no_free_exists() -> None:
    cand = _cand("kobo", cost_type="purchase", price_usd_cents=999, drm_free=True)
    report = rank_book_sources(_BOOK, [cand])

    assert report.verdict == "paid_drm_free_preferred"
    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "kobo"
    assert report.has_free_option is False


def test_drm_free_dominates_cost_paid_portable_beats_free_locked() -> None:
    # the spec's HARD RULE: DRM-free dominates cost. a free-but-locked book you
    # cannot port ranks BELOW a paid-but-portable one.
    free_locked = _cand("kindle_unlimited", cost_type="free", price_usd_cents=0,
                        drm_free=False, rights_basis="subscription:lent")
    paid_portable = _cand("kobo", cost_type="purchase", price_usd_cents=999,
                          drm_free=True, rights_basis="purchase:owned")
    report = rank_book_sources(_BOOK, [free_locked, paid_portable])

    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "kobo"  # DRM-free wins despite cost
    assert report.ranked_sources[0].drm_free is True
    assert report.ranked_sources[1].drm_free is False
    assert report.all_drm_locked is False


def test_free_before_purchase_within_drm_free_band() -> None:
    free = _cand("standard_ebooks", cost_type="free", price_usd_cents=0,
                 drm_free=True, rights_basis="public_domain:US-pre-1929")
    paid = _cand("kobo", cost_type="purchase", price_usd_cents=999, drm_free=True)
    report = rank_book_sources(_BOOK, [paid, free])  # supply order reversed

    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "standard_ebooks"  # free first
    assert report.verdict == "free_drm_free_preferred"


def test_lower_price_wins_among_paid_drm_free() -> None:
    cheaper = _cand("kobo", cost_type="purchase", price_usd_cents=799, drm_free=True)
    pricier = _cand("google_play", cost_type="purchase", price_usd_cents=1299, drm_free=True)
    report = rank_book_sources(_BOOK, [pricier, cheaper])

    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "kobo"
    assert report.recommended_source.price_usd_cents == 799


def test_higher_provenance_strength_wins_at_equal_cost_and_drm() -> None:
    established = _cand("standard_ebooks", cost_type="free", price_usd_cents=0,
                        drm_free=True, provenance_strength="established",
                        rights_basis="public_domain:US-pre-1929")
    claimed = _cand("internet_archive", cost_type="free", price_usd_cents=0,
                    drm_free=True, provenance_strength="claimed",
                    rights_basis="open-access:claimed")
    report = rank_book_sources(_BOOK, [claimed, established])

    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "standard_ebooks"
    assert report.recommended_source.provenance_strength == "established"


def test_source_key_is_deterministic_tiebreak() -> None:
    a = _cand("alpha_store", cost_type="purchase", price_usd_cents=999, drm_free=True)
    b = _cand("beta_store", cost_type="purchase", price_usd_cents=999, drm_free=True)
    report = rank_book_sources(_BOOK, [b, a])

    assert [s.source_key for s in report.ranked_sources] == ["alpha_store", "beta_store"]
    assert report.ranked_sources[0].rank == 0
    assert report.ranked_sources[1].rank == 1
    assert report.ranked_sources[0].recommended is True
    assert report.ranked_sources[1].recommended is False


def test_only_drm_locked_surfaces_honest_fallback() -> None:
    locked_a = _cand("kindle", cost_type="purchase", price_usd_cents=999,
                     drm_free=False, rights_basis="purchase:owned")
    locked_b = _cand("adobe_adept", cost_type="purchase", price_usd_cents=1299,
                     drm_free=False, rights_basis="purchase:owned")
    report = rank_book_sources(_BOOK, [locked_a, locked_b])

    assert report.all_drm_locked is True
    assert report.has_drm_free_option is False
    assert report.verdict == "only_drm_locked"
    assert report.recommended_source is not None
    assert report.recommended_source.source_key == "kindle"  # cheaper locked ranks first
    assert "refuses to port" in " ".join(report.notes)


def test_full_precedence_chain_drm_then_cost_then_price() -> None:
    # a locked free source, a free drm-free, a cheap paid drm-free, a pricey paid drm-free
    locked_free = _cand("kindle_unlimited", cost_type="free", price_usd_cents=0,
                        drm_free=False, rights_basis="subscription:lent")
    free_pd = _cand("standard_ebooks", cost_type="free", price_usd_cents=0,
                    drm_free=True, rights_basis="public_domain:US-pre-1929")
    cheap_paid = _cand("kobo", cost_type="purchase", price_usd_cents=799, drm_free=True)
    pricey_paid = _cand("google_play", cost_type="purchase", price_usd_cents=1299, drm_free=True)
    report = rank_book_sources(_BOOK, [pricey_paid, locked_free, cheap_paid, free_pd])

    order = [s.source_key for s in report.ranked_sources]
    assert order == ["standard_ebooks", "kobo", "google_play", "kindle_unlimited"]
    assert report.verdict == "free_drm_free_preferred"


def test_ranking_is_deterministic_across_calls() -> None:
    cands = [
        _cand("zeta", cost_type="purchase", price_usd_cents=500, drm_free=True,
              provenance_strength="claimed"),
        _cand("alpha", cost_type="free", price_usd_cents=0, drm_free=True,
              provenance_strength="established"),
        _cand("mid", cost_type="purchase", price_usd_cents=300, drm_free=True,
              provenance_strength="established"),
    ]
    r1 = rank_book_sources(_BOOK, cands)
    r2 = rank_book_sources(_BOOK, cands)
    assert [s.source_key for s in r1.ranked_sources] == [s.source_key for s in r2.ranked_sources]


def test_validation_empty_book_id_raises() -> None:
    with pytest.raises(SourceRankerError):
        rank_book_sources("", [_cand("kobo")])


def test_validation_empty_source_key_raises() -> None:
    with pytest.raises(SourceRankerError):
        rank_book_sources(_BOOK, [_cand("", cost_type="free")])


def test_validation_negative_price_raises() -> None:
    with pytest.raises(SourceRankerError):
        rank_book_sources(_BOOK, [_cand("kobo", price_usd_cents=-1)])


def test_validation_unknown_cost_type_raises() -> None:
    with pytest.raises(SourceRankerError):
        rank_book_sources(_BOOK, [_cand("kobo", cost_type="barter")])


def test_validation_unknown_provenance_strength_raises() -> None:
    with pytest.raises(SourceRankerError):
        rank_book_sources(_BOOK, [_cand("kobo", provenance_strength="maybe")])


def test_validation_empty_rights_basis_raises() -> None:
    bad = SourceCandidate(
        source_key="kobo", cost_type="purchase", price_usd_cents=999,
        drm_free=True, rights_basis="", provenance_strength="established",
    )
    with pytest.raises(SourceRankerError):
        rank_book_sources(_BOOK, [bad])


def test_provenance_order_contract() -> None:
    # the ordinal contract: established > claimed > unknown (higher = stronger)
    assert PROVENANCE_ORDER["established"] > PROVENANCE_ORDER["claimed"]
    assert PROVENANCE_ORDER["claimed"] > PROVENANCE_ORDER["unknown"]
    assert len(PROVENANCE_ORDER) == 3
