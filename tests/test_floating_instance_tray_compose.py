"""Pure tests for floating instance tray compose."""

from __future__ import annotations

import pytest

from substrate.floating_instance_tray_compose import (
    FloatingInstanceTrayComposeError,
    compose_floating_instance_tray,
)

MEMBERS = [
    {
        "instance_id": "f1",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "live_dispatched": False,
        "merge_executed": False,
    },
    {
        "instance_id": "f2",
        "parent_asset_id": "asset-1",
        "status": "open",
        "live_dispatched": False,
        "merge_executed": False,
    },
    {
        "instance_id": "f3",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "live_dispatched": False,
        "merge_executed": False,
    },
]


def test_collective_pack():
    c = compose_floating_instance_tray(
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["f1", "f3"],
        action="collective_pack",
        operator_ack=True,
    )
    assert c.tray_ready is True
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.to_dict()["pack_dispatched"] is False


def test_full_merge_gates():
    no_ack = compose_floating_instance_tray(
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["f1"],
        action="full_merge_one",
        operator_ack=False,
    )
    assert no_ack.tray_ready is False
    ok = compose_floating_instance_tray(
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["f1"],
        action="full_merge_one",
        operator_ack=True,
    )
    assert ok.tray_ready is True
    assert ok.merge_executed is False


def test_rejects_cross_parent():
    with pytest.raises(FloatingInstanceTrayComposeError, match="parent_asset_id"):
        compose_floating_instance_tray(
            parent_asset_id="asset-1",
            members=[
                MEMBERS[0],
                {
                    "instance_id": "x",
                    "parent_asset_id": "other",
                    "status": "open",
                },
            ],
            selected_instance_ids=[],
            action="none",
            operator_ack=False,
        )
