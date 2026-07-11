"""Pure tests for twin substrate search → merge compose."""

from __future__ import annotations

from substrate.twin_substrate_search_merge_compose import (
    compose_twin_substrate_search_merge,
    format_twin_substrate_search_merge_summary,
)

CORPUS = [
    {
        "twin_id": "twin-1",
        "parent_asset_id": "asset-1",
        "insights": ["scaling laws hold under compute-optimal regimes"],
        "questions": ["Does the law break at sparse models?"],
    },
    {
        "twin_id": "twin-2",
        "parent_asset_id": "asset-2",
        "insights": ["attention efficiency tradeoffs with scaling"],
        "questions": ["What is the scaling frontier?"],
    },
    {
        "twin_id": "twin-3",
        "parent_asset_id": "asset-3",
        "insights": ["unrelated gardening notes"],
        "questions": ["How wet should soil be?"],
    },
]


def test_search_merge_ready():
    c = compose_twin_substrate_search_merge(
        pack_id="pack-1",
        search_query="scaling laws",
        twin_records=CORPUS,
        operator_ack=True,
    )
    assert len(c.search.hits) >= 2
    assert c.merge is not None
    assert c.merge.merge_ready is True
    assert c.pack_ready is True
    assert c.remote_index_queried is False
    assert c.merge_executed is False
    assert c.twin_written is False
    assert c.store_mutated is False
    assert "merge_executed=false" in format_twin_substrate_search_merge_summary(c)
    assert c.to_dict()["merge_executed"] is False


def test_single_parent_hits():
    c = compose_twin_substrate_search_merge(
        pack_id="pack-2",
        search_query="gardening soil",
        twin_records=CORPUS,
        operator_ack=True,
    )
    assert len(c.search.hits) > 0
    assert c.merge is None
    assert c.pack_ready is True
    assert c.merge_executed is False


def test_no_hits():
    c = compose_twin_substrate_search_merge(
        pack_id="pack-3",
        search_query="zzzznonexistenttoken",
        twin_records=CORPUS,
        operator_ack=True,
    )
    assert len(c.search.hits) == 0
    assert c.merge is None
    assert c.pack_ready is False


def test_ack_false():
    c = compose_twin_substrate_search_merge(
        pack_id="pack-4",
        search_query="scaling",
        twin_records=CORPUS,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.merge_executed is False
    assert c.twin_written is False
