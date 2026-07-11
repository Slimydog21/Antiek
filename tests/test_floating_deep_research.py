"""Hermetic tests for pure floating deep research."""

from __future__ import annotations

import pytest

from substrate.floating_deep_research import (
    FloatingDeepResearchError,
    mark_floating_completed,
    propose_collective_pack,
    propose_draft_merge,
    propose_full_merge,
    set_floating_view_mode,
    spawn_floating_from_highlight,
)


def test_spawn_honesty_flags() -> None:
    inst = spawn_floating_from_highlight(
        parent_asset_id="asset-1",
        highlight="scaling claim",
        gated=False,
    )
    d = inst.to_dict()
    assert d["live_dispatched"] is False
    assert d["merge_executed"] is False
    assert d["authority"] == "operator_spawn_only"
    assert d["status"] == "proposed"
    assert d["view_mode"] == "floating"


def test_rejects_gated() -> None:
    with pytest.raises(FloatingDeepResearchError, match="gated"):
        spawn_floating_from_highlight(
            parent_asset_id="a",
            highlight="secret",
            gated=True,
        )


def test_rejects_non_bool_gated() -> None:
    with pytest.raises(FloatingDeepResearchError, match="gated"):
        spawn_floating_from_highlight(
            parent_asset_id="a",
            highlight="h",
            gated="false",  # type: ignore[arg-type]
        )


def test_view_mode_and_complete() -> None:
    inst = spawn_floating_from_highlight(
        parent_asset_id="a",
        highlight="h",
        gated=False,
    )
    inst = set_floating_view_mode(inst, "fullscreen")
    assert inst.view_mode == "fullscreen"
    assert inst.status == "open"
    inst = mark_floating_completed(inst)
    assert inst.status == "completed"
    assert inst.live_dispatched is False


def test_draft_and_full_merge() -> None:
    inst = spawn_floating_from_highlight(
        parent_asset_id="a",
        highlight="h",
        gated=False,
    )
    draft = propose_draft_merge(inst)
    assert draft.merge_executed is False
    assert draft.operator_ack is False
    with pytest.raises(FloatingDeepResearchError, match="completed"):
        propose_full_merge(inst, operator_ack=True)
    done = mark_floating_completed(set_floating_view_mode(inst, "floating"))
    with pytest.raises(FloatingDeepResearchError, match="operator_ack"):
        propose_full_merge(done, operator_ack=False)
    full = propose_full_merge(done, operator_ack=True)
    assert full.merge_executed is False
    assert full.to_dict()["merge_executed"] is False


def test_collective_pack() -> None:
    a = mark_floating_completed(
        set_floating_view_mode(
            spawn_floating_from_highlight(
                parent_asset_id="p",
                highlight="one",
                gated=False,
            ),
            "floating",
        )
    )
    b = mark_floating_completed(
        set_floating_view_mode(
            spawn_floating_from_highlight(
                parent_asset_id="p",
                highlight="two different",
                gated=False,
            ),
            "floating",
        )
    )
    with pytest.raises(FloatingDeepResearchError, match="at least 2"):
        propose_collective_pack([a])
    pack = propose_collective_pack([a, b])
    assert pack.pack_dispatched is False
    assert pack.to_dict()["pack_dispatched"] is False
    assert len(pack.instance_ids) == 2


def test_cross_parent_pack_rejected() -> None:
    a = spawn_floating_from_highlight(
        parent_asset_id="p1", highlight="one", gated=False
    )
    b = spawn_floating_from_highlight(
        parent_asset_id="p2", highlight="two", gated=False
    )
    with pytest.raises(FloatingDeepResearchError, match="same parent"):
        propose_collective_pack([a, b])
