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


def test_write_sprint_3_block_repository_folders_is_live() -> None:
    assert lock.resolve_write_sprint(3).slug == "block-repository-folders"
    assert lock.resolve_write_sprint(3).status == "live"


def test_write_sprint_4_structured_block_editor_is_live() -> None:
    assert lock.resolve_write_sprint(4).slug == "structured-block-editor"
    assert lock.resolve_write_sprint(4).status == "live"


def test_write_sprint_5_brainstorm_interview_is_live() -> None:
    assert lock.resolve_write_sprint(5).slug == "brainstorm-interview"
    assert lock.resolve_write_sprint(5).status == "live"


def test_write_sprint_6_draft_generation_style_is_live() -> None:
    assert lock.resolve_write_sprint(6).slug == "draft-generation-style"
    assert lock.resolve_write_sprint(6).status == "live"


def test_write_sprint_7_trace_to_source_is_live() -> None:
    assert lock.resolve_write_sprint(7).slug == "trace-to-source"
    assert lock.resolve_write_sprint(7).status == "live"


def test_write_sprint_8_pre_outline_freeform_is_live() -> None:
    assert lock.resolve_write_sprint(8).slug == "pre-outline-freeform"
    assert lock.resolve_write_sprint(8).status == "live"


def test_write_sprint_9_style_conditioning_is_live() -> None:
    assert lock.resolve_write_sprint(9).slug == "style-conditioning"
    assert lock.resolve_write_sprint(9).status == "live"


def test_all_write_sprints_are_live() -> None:
    assert {lock.resolve_write_sprint(n).status for n in range(1, 10)} == {"live"}


def test_roadmap_consumes_write_sprint_status_and_focus_advances() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert by_id["write:1"].status.value == "live"
    assert by_id["write:2"].status.value == "live"
    assert by_id["write:3"].status.value == "live"
    assert by_id["write:4"].status.value == "live"
    assert by_id["write:5"].status.value == "live"
    assert by_id["write:6"].status.value == "live"
    assert by_id["write:7"].status.value == "live"
    assert by_id["write:8"].status.value == "live"
    assert by_id["write:9"].status.value == "live"
    assert roadmap.execution_focus() is not None
    assert roadmap.execution_focus().node_id == "speak:7"


def test_write_lock_version_present() -> None:
    assert isinstance(lock.WRITE_LOCK_VERSION, int) and lock.WRITE_LOCK_VERSION >= 9
