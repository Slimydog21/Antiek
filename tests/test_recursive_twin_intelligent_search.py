"""Hermetic tests for pure twin intelligent search."""

from __future__ import annotations

import pytest

from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    search_twin_substrate,
)

CORPUS = [
    {
        "twin_id": "t1",
        "parent_asset_id": "a1",
        "insights": ["scaling laws hold under compute constraints"],
        "questions": ["what is the counterexample?"],
        "source_label": "arxiv-paper",
    },
    {
        "twin_id": "t2",
        "parent_asset_id": "a2",
        "insights": ["market structure differs from scaling"],
        "questions": ["how does regulation change the story?"],
    },
    {
        "twin_id": "t3",
        "parent_asset_id": "a3",
        "insights": ["unrelated note about cooking"],
        "questions": ["what spice pairs with thyme?"],
    },
]


def test_finds_overlaps() -> None:
    r = search_twin_substrate(query="scaling compute", records=CORPUS)
    assert r.remote_index_queried is False
    assert r.to_dict()["remote_index_queried"] is False
    assert len(r.hits) >= 1
    assert r.hits[0].twin_id == "t1"
    assert "insights" in r.hits[0].matched_fields


def test_empty_corpus() -> None:
    r = search_twin_substrate(query="scaling", records=[])
    assert r.hits == ()
    assert r.remote_index_queried is False


def test_rejects_empty_query() -> None:
    with pytest.raises(TwinIntelligentSearchError, match="query"):
        search_twin_substrate(query="  ", records=CORPUS)


def test_rejects_short_tokens() -> None:
    with pytest.raises(TwinIntelligentSearchError, match="token"):
        search_twin_substrate(query="a b", records=CORPUS)


def test_no_invent_unrelated() -> None:
    r = search_twin_substrate(
        query="quantum entanglement teleportation", records=CORPUS
    )
    assert r.hits == ()


def test_limit() -> None:
    r = search_twin_substrate(
        query="scaling market regulation", records=CORPUS, limit=1
    )
    assert len(r.hits) <= 1
