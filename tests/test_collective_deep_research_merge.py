"""Hermetic tests for pure collective analysis merge."""

from __future__ import annotations

import pytest

from substrate.collective_deep_research_merge import (
    CollectiveAnalysisMergeError,
    propose_collective_analysis_merge,
)

BASE = [
    {
        "instance_id": "fdr_1",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "findings": ["claim A holds"],
    },
    {
        "instance_id": "fdr_2",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "findings": ["claim B needs counterexample"],
    },
]


def test_draft_never_writes() -> None:
    intent = propose_collective_analysis_merge(
        BASE, kind="draft_analysis", operator_ack=False
    )
    assert intent.analysis_written is False
    assert intent.to_dict()["analysis_written"] is False
    assert len(intent.instance_ids) == 2
    assert len(intent.findings) == 2


def test_full_requires_ack_and_completed() -> None:
    with pytest.raises(CollectiveAnalysisMergeError, match="operator_ack"):
        propose_collective_analysis_merge(
            BASE, kind="full_analysis", operator_ack=False
        )
    openish = [dict(BASE[0], status="open"), BASE[1]]
    with pytest.raises(CollectiveAnalysisMergeError, match="completed"):
        propose_collective_analysis_merge(
            openish, kind="full_analysis", operator_ack=True
        )
    intent = propose_collective_analysis_merge(
        BASE, kind="full_analysis", operator_ack=True
    )
    assert intent.analysis_written is False
    assert intent.operator_ack is True


def test_same_parent_and_min_two() -> None:
    with pytest.raises(CollectiveAnalysisMergeError, match="at least 2"):
        propose_collective_analysis_merge(
            [BASE[0]], kind="draft_analysis", operator_ack=False
        )
    with pytest.raises(CollectiveAnalysisMergeError, match="same parent"):
        propose_collective_analysis_merge(
            [BASE[0], dict(BASE[1], parent_asset_id="other")],
            kind="draft_analysis",
            operator_ack=False,
        )


def test_no_invent_findings() -> None:
    intent = propose_collective_analysis_merge(
        [
            {
                "instance_id": "a",
                "parent_asset_id": "p",
                "status": "completed",
            },
            {
                "instance_id": "b",
                "parent_asset_id": "p",
                "status": "completed",
            },
        ],
        kind="draft_analysis",
        operator_ack=False,
    )
    assert intent.findings == ()
    assert any("no invent" in n for n in intent.notes)
