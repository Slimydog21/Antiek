"""Tests for the frozen Write sprint-lock."""

from __future__ import annotations

import pytest

from substrate.contracts import write_sprint_lock as lock
from substrate.coordination.roadmap import build_roadmap


def test_all_write_sprints_resolve() -> None:
    for n in range(1, 10):
        d = lock.resolve_write_sprint(n)
        assert d.sprint == n
        assert d.slug and d.deliverable


def test_out_of_range_raises() -> None:
    with pytest.raises(KeyError, match="not in the frozen sprint-lock"):
        lock.resolve_write_sprint(99)


def test_write_sprint_1_outline_block_model_is_live() -> None:
    assert lock.resolve_write_sprint(1).slug == "outline-block-model"
    assert lock.resolve_write_sprint(1).status == "live"


def test_write_sprint_2_edit_trajectory_capture_is_live() -> None:
    assert lock.resolve_write_sprint(2).slug == "edit-trajectory-capture"
    assert lock.resolve_write_sprint(2).status == "live"


def test_remaining_write_sprints_stay_planned_until_promoted() -> None:
    assert {lock.resolve_write_sprint(n).status for n in range(3, 10)} == {"planned"}


def test_roadmap_consumes_write_sprint_status_and_focus_advances() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert by_id["write:1"].status.value == "live"
    assert by_id["write:2"].status.value == "live"
    assert by_id["write:3"].status.value == "planned"
    assert roadmap.execution_focus() is not None
    assert roadmap.execution_focus().node_id == "write:3"


def test_write_lock_version_present() -> None:
    assert isinstance(lock.WRITE_LOCK_VERSION, int) and lock.WRITE_LOCK_VERSION >= 2
