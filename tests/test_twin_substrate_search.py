"""Tests for substrate/twin_note_taker/search.py — twin-substrate retrieval."""

from __future__ import annotations

import pytest

from substrate.twin_note_taker.search import (
    TwinIndex,
    TwinSearchError,
    TwinSearchHit,
    TwinSearchRecord,
    search_twins,
)


def _rec(rid: str, asset: str, kind: str, text: str, prov=()) -> TwinSearchRecord:
    return TwinSearchRecord(
        asset_id=asset, record_id=rid, kind=kind, text=text, provenance=tuple(prov)
    )


# ---------------------------------------------------------------------------
# honesty: empty query / empty index -> empty hits
# ---------------------------------------------------------------------------


def test_empty_query_returns_nothing():
    idx = TwinIndex.build([_rec("r1", "a1", "insight", "transformers beat rnns")])
    assert search_twins(idx, "") == []
    assert search_twins(idx, "   ") == []
    assert search_twins(idx, "!!!") == []  # no tokens


def test_empty_index_returns_nothing():
    idx = TwinIndex.build([])
    assert search_twins(idx, "anything") == []


def test_limit_zero_or_negative_returns_nothing():
    idx = TwinIndex.build([_rec("r1", "a1", "insight", "transformers")])
    assert search_twins(idx, "transformers", limit=0) == []
    assert search_twins(idx, "transformers", limit=-1) == []


# ---------------------------------------------------------------------------
# honesty: only matching records score > 0
# ---------------------------------------------------------------------------


def test_only_matching_records_returned():
    idx = TwinIndex.build(
        [
            _rec("r1", "a1", "insight", "transformers are powerful"),
            _rec("r2", "a1", "question", "what is the weather"),
        ]
    )
    hits = search_twins(idx, "transformers")
    assert len(hits) == 1
    assert hits[0].record.record_id == "r1"


def test_no_overlap_returns_empty():
    idx = TwinIndex.build([_rec("r1", "a1", "insight", "alpha beta")])
    assert search_twins(idx, "gamma delta") == []


# ---------------------------------------------------------------------------
# scoring is transparent + auditable
# ---------------------------------------------------------------------------


def test_hit_carries_matched_terms_and_frequency():
    idx = TwinIndex.build(
        [_rec("r1", "a1", "insight", "transformers transformers attention")]
    )
    hits = search_twins(idx, "transformers")
    assert len(hits) == 1
    assert "transformers" in hits[0].matched_terms
    assert hits[0].term_frequency["transformers"] == 2
    assert hits[0].score > 0


def test_rare_term_outranks_common_term():
    # 'rare' appears in 1 record; 'common' in 3 — a doc with the rare term
    # should score higher than one with only the common term (idf weighting).
    recs = [
        _rec("r1", "a", "insight", "rare common"),
        _rec("r2", "a", "insight", "common"),
        _rec("r3", "a", "insight", "common"),
        _rec("r4", "a", "insight", "common"),
    ]
    idx = TwinIndex.build(recs)
    hits = search_twins(idx, "rare common")
    assert hits[0].record.record_id == "r1"


def test_score_descending_then_record_id_tiebreak():
    recs = [
        _rec("zzz", "a", "insight", "term term term"),  # tf=3
        _rec("aaa", "a", "insight", "term term term"),  # tf=3, same score → id tiebreak
    ]
    idx = TwinIndex.build(recs)
    hits = search_twins(idx, "term")
    assert [h.record.record_id for h in hits] == ["aaa", "zzz"]


def test_limit_caps_results():
    recs = [_rec(f"r{i}", "a", "insight", f"term payload{i}") for i in range(5)]
    idx = TwinIndex.build(recs)
    assert len(search_twins(idx, "term", limit=3)) == 3


# ---------------------------------------------------------------------------
# kind filter
# ---------------------------------------------------------------------------


def test_kind_filter_restricts():
    idx = TwinIndex.build(
        [
            _rec("r1", "a1", "insight", "transformers"),
            _rec("r2", "a1", "question", "transformers?"),
        ]
    )
    hits = search_twins(idx, "transformers", kind_filter="insight")
    assert len(hits) == 1
    assert hits[0].record.kind == "insight"


def test_kind_filter_none_searches_all():
    idx = TwinIndex.build(
        [
            _rec("r1", "a1", "insight", "transformers"),
            _rec("r2", "a1", "question", "transformers?"),
        ]
    )
    assert len(search_twins(idx, "transformers", kind_filter=None)) == 2


def test_kind_filter_unknown_returns_empty():
    idx = TwinIndex.build([_rec("r1", "a1", "insight", "x")])
    assert search_twins(idx, "x", kind_filter="bogus") == []


# ---------------------------------------------------------------------------
# provenance carried through
# ---------------------------------------------------------------------------


def test_provenance_carried_through():
    rec = _rec("r1", "asset-7", "insight", "deep insight", prov=("asset-7", "role:note_taker", "ev-3"))
    idx = TwinIndex.build([rec])
    hits = search_twins(idx, "insight")
    assert hits[0].record.provenance == ("asset-7", "role:note_taker", "ev-3")
    assert hits[0].record.asset_id == "asset-7"


# ---------------------------------------------------------------------------
# validation + duplicate detection
# ---------------------------------------------------------------------------


def test_invalid_kind_rejected():
    with pytest.raises(TwinSearchError):
        TwinSearchRecord(asset_id="a", record_id="r", kind="bogus", text="x")


def test_empty_record_id_rejected():
    with pytest.raises(TwinSearchError):
        TwinSearchRecord(asset_id="a", record_id="  ", kind="insight", text="x")


def test_duplicate_record_id_rejected():
    with pytest.raises(TwinSearchError):
        TwinIndex.build(
            [
                _rec("dup", "a", "insight", "one"),
                _rec("dup", "a", "insight", "two"),
            ]
        )


# ---------------------------------------------------------------------------
# purity + determinism
# ---------------------------------------------------------------------------


def test_index_size():
    idx = TwinIndex.build([_rec(f"r{i}", "a", "insight", f"t{i}") for i in range(3)])
    assert idx.size == 3


def test_search_is_pure_idempotent():
    idx = TwinIndex.build(
        [_rec("r1", "a", "insight", "transformers attention mechanism")]
    )
    a = search_twins(idx, "transformers attention")
    b = search_twins(idx, "transformers attention")
    assert a == b


def test_multi_term_query_matches_intersection_and_union():
    # a record with ONE of two query terms still matches (union), scored lower
    recs = [
        _rec("r1", "a", "insight", "transformers attention"),  # both terms
        _rec("r2", "a", "insight", "transformers only"),       # one term
    ]
    idx = TwinIndex.build(recs)
    hits = search_twins(idx, "transformers attention")
    ids = [h.record.record_id for h in hits]
    assert ids == ["r1", "r2"]
    assert hits[0].score > hits[1].score  # both-terms outranks one-term


def test_hit_is_frozen_value():
    idx = TwinIndex.build([_rec("r1", "a", "insight", "transformers")])
    hits = search_twins(idx, "transformers")
    assert isinstance(hits[0], TwinSearchHit)
    assert isinstance(hits[0].matched_terms, tuple)
