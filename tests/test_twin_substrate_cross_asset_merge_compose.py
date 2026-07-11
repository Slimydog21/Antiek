"""Pure tests for twin substrate cross-asset merge compose."""

from __future__ import annotations

import pytest

from substrate.twin_substrate_cross_asset_merge_compose import (
    TwinSubstrateCrossAssetMergeComposeError,
    compose_twin_substrate_cross_asset_merge,
)


def test_merge_ready_honesty():
    c = compose_twin_substrate_cross_asset_merge(
        pack_id="pack-1",
        operator_ack=True,
        slices=[
            {
                "parent_asset_id": "a1",
                "twin_asset_id": "t1",
                "insights": ["claim holds under noise"],
                "questions": ["what is the sample size?"],
            },
            {
                "parent_asset_id": "a2",
                "insights": ["routing cost is non-linear"],
                "questions": [],
            },
        ],
    )
    assert c.merge_ready is True
    assert c.parent_count == 2
    assert c.insight_count == 2
    assert c.question_count == 1
    assert c.merge_executed is False
    assert c.twin_written is False
    assert c.store_mutated is False
    d = c.to_dict()
    assert d["merge_executed"] is False
    assert d["twin_written"] is False


def test_not_ready_paths():
    no_ack = compose_twin_substrate_cross_asset_merge(
        pack_id="p",
        operator_ack=False,
        slices=[
            {"parent_asset_id": "a", "insights": ["x"], "questions": []},
            {"parent_asset_id": "b", "insights": [], "questions": ["y"]},
        ],
    )
    assert no_ack.merge_ready is False
    empty = compose_twin_substrate_cross_asset_merge(
        pack_id="p",
        operator_ack=True,
        slices=[
            {"parent_asset_id": "a", "insights": [], "questions": []},
            {"parent_asset_id": "b", "insights": [], "questions": []},
        ],
    )
    assert empty.merge_ready is False


def test_rejects_short_and_duplicate():
    with pytest.raises(TwinSubstrateCrossAssetMergeComposeError, match="at least 2"):
        compose_twin_substrate_cross_asset_merge(
            pack_id="p",
            operator_ack=True,
            slices=[{"parent_asset_id": "a", "insights": ["x"], "questions": []}],
        )
    with pytest.raises(TwinSubstrateCrossAssetMergeComposeError, match="duplicate"):
        compose_twin_substrate_cross_asset_merge(
            pack_id="p",
            operator_ack=True,
            slices=[
                {"parent_asset_id": "a", "insights": ["x"], "questions": []},
                {"parent_asset_id": "a", "insights": ["y"], "questions": []},
            ],
        )
