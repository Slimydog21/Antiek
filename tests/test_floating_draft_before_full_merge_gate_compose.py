"""Pure tests for floating draft-before-full-merge gate."""

from __future__ import annotations

import pytest

from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
    format_floating_draft_before_full_merge_gate_summary,
)


def test_draft_only_ready():
    c = compose_floating_draft_before_full_merge_gate(
        session_id="sess-1",
        parent_asset_id="asset-1",
        parent_excerpt="<p>Parent body</p>",
        sources=[
            {
                "instance_id": "float-1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "highlight": "key claim",
                "findings": ["evidence A"],
            }
        ],
        stage="draft_only",
        operator_ack=True,
    )
    assert c.draft.draft_ready is True
    assert c.tray is not None and c.tray.tray_ready is True
    assert c.gate_ready is True
    assert c.full_merge_intent_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert "merge_executed=false" in format_floating_draft_before_full_merge_gate_summary(
        c
    )
    assert c.to_dict()["draft_written"] is False


def test_draft_only_multi_source():
    c = compose_floating_draft_before_full_merge_gate(
        session_id="sess-2",
        parent_asset_id="asset-1",
        sources=[
            {
                "instance_id": "a",
                "parent_asset_id": "asset-1",
                "status": "open",
                "highlight": "h1",
            },
            {
                "instance_id": "b",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["f2"],
            },
        ],
        stage="draft_only",
        operator_ack=True,
    )
    assert c.draft.draft_ready is True
    assert c.tray is None
    assert c.gate_ready is True
    assert c.merge_executed is False


def test_promote_requires_full_ack():
    c = compose_floating_draft_before_full_merge_gate(
        session_id="sess-3",
        parent_asset_id="asset-1",
        sources=[
            {
                "instance_id": "float-1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["done"],
            }
        ],
        stage="promote_full_merge",
        operator_ack=True,
        full_merge_ack=False,
    )
    assert c.draft.draft_ready is True
    assert c.full_merge_intent_ready is False
    assert c.gate_ready is False
    assert c.merge_executed is False


def test_promote_ready():
    c = compose_floating_draft_before_full_merge_gate(
        session_id="sess-4",
        parent_asset_id="asset-1",
        parent_excerpt="parent",
        sources=[
            {
                "instance_id": "float-1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "highlight": "claim",
                "findings": ["f1"],
            }
        ],
        stage="promote_full_merge",
        operator_ack=True,
        full_merge_ack=True,
    )
    assert c.full_merge_intent_ready is True
    assert c.gate_ready is True
    assert c.tray is not None and c.tray.action == "full_merge_one"
    assert c.merge_executed is False
    assert c.draft_written is False


def test_promote_blocked_open():
    c = compose_floating_draft_before_full_merge_gate(
        session_id="sess-5",
        parent_asset_id="asset-1",
        sources=[
            {
                "instance_id": "float-1",
                "parent_asset_id": "asset-1",
                "status": "open",
                "highlight": "still open",
            }
        ],
        stage="promote_full_merge",
        operator_ack=True,
        full_merge_ack=True,
    )
    assert c.full_merge_intent_ready is False
    assert c.gate_ready is False
    assert c.merge_executed is False


def test_draft_without_ack():
    c = compose_floating_draft_before_full_merge_gate(
        session_id="sess-6",
        parent_asset_id="asset-1",
        sources=[
            {
                "instance_id": "float-1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["f"],
            }
        ],
        stage="draft_only",
        operator_ack=False,
    )
    assert c.draft.draft_ready is True
    assert c.gate_ready is False
    assert c.draft_written is False


def test_promote_requires_boolean_full_ack():
    with pytest.raises(
        FloatingDraftBeforeFullMergeGateComposeError, match="full_merge_ack"
    ):
        compose_floating_draft_before_full_merge_gate(
            session_id="s",
            parent_asset_id="a",
            sources=[
                {
                    "instance_id": "i",
                    "parent_asset_id": "a",
                    "status": "completed",
                    "findings": ["f"],
                }
            ],
            stage="promote_full_merge",
            operator_ack=True,
        )
