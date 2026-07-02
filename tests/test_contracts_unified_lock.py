"""Tests for the frozen Antiek-Unified sprint-lock."""

from __future__ import annotations

import pytest

from substrate.contracts import unified_sprint_lock as lock
from substrate.coordination.roadmap import build_roadmap


def test_all_unified_sprints_resolve() -> None:
    for n in range(1, 9):
        d = lock.resolve_unified_sprint(n)
        assert d.sprint == n
        assert d.slug and d.deliverable


def test_out_of_range_raises() -> None:
    with pytest.raises(KeyError, match="not in the frozen sprint-lock"):
        lock.resolve_unified_sprint(99)


def test_unified_sprint_1_substrate_contract_and_lock_is_live() -> None:
    assert lock.resolve_unified_sprint(1).slug == "substrate-contract-and-lock"
    assert lock.resolve_unified_sprint(1).status == "live"


def test_unified_sprint_2_remote_exec_fanout_is_live() -> None:
    assert lock.resolve_unified_sprint(2).slug == "remote-exec-fanout"
    assert lock.resolve_unified_sprint(2).status == "live"


def test_unified_sprint_3_seams_and_collisions_is_live() -> None:
    assert lock.resolve_unified_sprint(3).slug == "seams-and-collisions"
    assert lock.resolve_unified_sprint(3).status == "live"


def test_unified_sprint_4_navigation_ia_taxonomy_is_live() -> None:
    assert lock.resolve_unified_sprint(4).slug == "navigation-ia-taxonomy"
    assert lock.resolve_unified_sprint(4).status == "live"


def test_remaining_unified_sprints_stay_planned_until_promoted() -> None:
    assert {lock.resolve_unified_sprint(n).status for n in range(5, 9)} == {"planned"}


def test_roadmap_consumes_unified_sprint_status_and_focus_advances() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert by_id["unified:1"].status.value == "live"
    assert by_id["unified:2"].status.value == "live"
    assert by_id["unified:3"].status.value == "live"
    assert by_id["unified:4"].status.value == "live"
    for n in range(5, 9):
        assert by_id[f"unified:{n}"].status.value == "planned"
    assert roadmap.execution_focus() is not None
    assert roadmap.execution_focus().node_id == "unified:5"


def test_unified_lock_version_present() -> None:
    assert isinstance(lock.UNIFIED_LOCK_VERSION, int) and lock.UNIFIED_LOCK_VERSION >= 4
