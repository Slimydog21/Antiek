"""Tests for the frozen Speak sprint-lock."""

from __future__ import annotations

import pytest

from substrate.contracts import speak_sprint_lock as lock
from substrate.coordination.roadmap import build_roadmap


def test_all_speak_sprints_resolve() -> None:
    for n in range(1, 10):
        d = lock.resolve_speak_sprint(n)
        assert d.sprint == n
        assert d.slug and d.deliverable


def test_out_of_range_raises() -> None:
    with pytest.raises(KeyError, match="not in the frozen sprint-lock"):
        lock.resolve_speak_sprint(99)


def test_speak_sprint_1_consent_rights_gate_is_live() -> None:
    assert lock.resolve_speak_sprint(1).slug == "consent-rights-gate"
    assert lock.resolve_speak_sprint(1).status == "live"


def test_speak_sprint_2_async_voice_interview_is_live() -> None:
    assert lock.resolve_speak_sprint(2).slug == "async-voice-interview"
    assert lock.resolve_speak_sprint(2).status == "live"


def test_speak_sprint_3_project_invitations_is_live() -> None:
    assert lock.resolve_speak_sprint(3).slug == "project-invitations"
    assert lock.resolve_speak_sprint(3).status == "live"


def test_remaining_speak_sprints_stay_planned_until_promoted() -> None:
    assert {lock.resolve_speak_sprint(n).status for n in range(4, 10)} == {"planned"}


def test_roadmap_consumes_speak_sprint_status_and_focus_advances() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert by_id["speak:1"].status.value == "live"
    assert by_id["speak:2"].status.value == "live"
    assert by_id["speak:3"].status.value == "live"
    for n in range(4, 10):
        assert by_id[f"speak:{n}"].status.value == "planned"
    assert roadmap.execution_focus() is not None
    assert roadmap.execution_focus().node_id == "speak:4"


def test_speak_lock_version_present() -> None:
    assert isinstance(lock.SPEAK_LOCK_VERSION, int) and lock.SPEAK_LOCK_VERSION >= 3
