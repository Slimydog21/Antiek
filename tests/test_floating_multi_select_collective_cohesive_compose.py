"""Pure tests for floating multi-select collective cohesive compose."""

from __future__ import annotations

import pytest

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
    format_floating_multi_select_collective_cohesive_summary,
)

BASE_MEMBERS = [
    {
        "instance_id": "inst-a",
        "parent_asset_id": "asset-1",
        "status": "open",
        "highlight": "scaling laws claim",
        "prior_prompt": "What evidence supports the claim?",
        "context": ["card-a"],
    },
    {
        "instance_id": "inst-b",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "highlight": "counter-evidence",
        "findings": ["finding-b1"],
    },
    {
        "instance_id": "inst-c",
        "parent_asset_id": "asset-1",
        "status": "proposed",
        "highlight": "third angle",
    },
]


def test_cohesive_prompt_ready():
    c = compose_floating_multi_select_collective_cohesive(
        session_id="sess-1",
        parent_asset_id="asset-1",
        members=BASE_MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize A and B as one unit",
        operator_ack=True,
        extra_context=["operator note"],
    )
    assert c.tray.tray_ready is True
    assert c.cohesive is not None and c.cohesive.pack_ready is True
    assert c.cohesive.member_count == 2
    assert c.analysis is None
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.analysis_written is False
    assert c.to_dict()["live_dispatched"] is False
    assert "pack_dispatched=false" in format_floating_multi_select_collective_cohesive_summary(
        c
    )


def test_collective_pack_ready():
    c = compose_floating_multi_select_collective_cohesive(
        session_id="sess-2",
        parent_asset_id="asset-1",
        members=BASE_MEMBERS,
        selected_instance_ids=["inst-a", "inst-b", "inst-c"],
        pack_mode="collective_pack",
        cohesive_prompt="Run as pack",
        operator_ack=True,
    )
    assert c.tray.action == "collective_pack"
    assert c.tray.selected_count == 3
    assert c.cohesive is None
    assert c.pack_ready is True
    assert c.live_dispatched is False


def test_cohesive_plus_analysis_draft():
    c = compose_floating_multi_select_collective_cohesive(
        session_id="sess-3",
        parent_asset_id="asset-1",
        members=BASE_MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_plus_analysis",
        cohesive_prompt="Merge findings into draft analysis",
        operator_ack=True,
        analysis_kind="draft_analysis",
        extra_findings=["operator synthesis note"],
    )
    assert c.cohesive is not None and c.cohesive.pack_ready is True
    assert c.analysis is not None
    assert c.analysis.kind == "draft_analysis"
    assert c.analysis.analysis_written is False
    assert c.analysis_written is False
    assert c.pack_ready is True


def test_full_analysis_blocked_until_completed():
    c = compose_floating_multi_select_collective_cohesive(
        session_id="sess-4",
        parent_asset_id="asset-1",
        members=BASE_MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_plus_analysis",
        cohesive_prompt="Full merge analysis",
        operator_ack=True,
        analysis_kind="full_analysis",
    )
    assert c.analysis is None
    assert c.pack_ready is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False


def test_full_analysis_ready():
    members = [
        {
            "instance_id": "x",
            "parent_asset_id": "p",
            "status": "completed",
            "findings": ["fx"],
        },
        {
            "instance_id": "y",
            "parent_asset_id": "p",
            "status": "completed",
            "findings": ["fy"],
        },
    ]
    c = compose_floating_multi_select_collective_cohesive(
        session_id="sess-5",
        parent_asset_id="p",
        members=members,
        selected_instance_ids=["x", "y"],
        pack_mode="cohesive_plus_analysis",
        cohesive_prompt="Full unit analysis",
        operator_ack=True,
        analysis_kind="full_analysis",
    )
    assert c.pack_ready is True
    assert c.analysis is not None
    assert c.analysis.kind == "full_analysis"
    assert c.analysis_written is False
    assert c.live_dispatched is False


def test_ack_false_blocks():
    c = compose_floating_multi_select_collective_cohesive(
        session_id="sess-6",
        parent_asset_id="asset-1",
        members=BASE_MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Need ack",
        operator_ack=False,
    )
    assert c.tray.tray_ready is False
    assert c.pack_ready is False
    assert c.live_dispatched is False


def test_rejects_single_select():
    with pytest.raises(
        FloatingMultiSelectCollectiveCohesiveComposeError, match="at least 2"
    ):
        compose_floating_multi_select_collective_cohesive(
            session_id="s",
            parent_asset_id="asset-1",
            members=BASE_MEMBERS,
            selected_instance_ids=["inst-a"],
            pack_mode="cohesive_prompt",
            cohesive_prompt="solo",
            operator_ack=True,
        )
