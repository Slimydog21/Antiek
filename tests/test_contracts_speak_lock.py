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


def test_speak_sprint_4_compounding_interviewer_is_live() -> None:
    assert lock.resolve_speak_sprint(4).slug == "compounding-interviewer"
    assert lock.resolve_speak_sprint(4).status == "live"


def test_speak_sprint_5_cross_interviewee_verification_is_live() -> None:
    assert lock.resolve_speak_sprint(5).slug == "cross-interviewee-verification"
    assert lock.resolve_speak_sprint(5).status == "live"


def test_speak_sprint_6_contributor_economics_is_live() -> None:
    assert lock.resolve_speak_sprint(6).slug == "contributor-economics"
    assert lock.resolve_speak_sprint(6).status == "live"


def test_speak_sprint_7_economics_matrix_is_live() -> None:
    assert lock.resolve_speak_sprint(7).slug == "economics-matrix"
    assert lock.resolve_speak_sprint(7).status == "live"


def test_speak_sprint_8_biography_authoring_is_live() -> None:
    assert lock.resolve_speak_sprint(8).slug == "biography-authoring"
    assert lock.resolve_speak_sprint(8).status == "live"


def test_speak_sprint_9_publishing_physical_is_live() -> None:
    assert lock.resolve_speak_sprint(9).slug == "publishing-physical"
    assert lock.resolve_speak_sprint(9).status == "live"


def test_all_speak_sprints_are_live() -> None:
    assert {lock.resolve_speak_sprint(n).status for n in range(1, 10)} == {"live"}


def test_roadmap_consumes_speak_sprint_status_and_focus_advances() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert by_id["speak:1"].status.value == "live"
    assert by_id["speak:2"].status.value == "live"
    assert by_id["speak:3"].status.value == "live"
    assert by_id["speak:4"].status.value == "live"
    assert by_id["speak:5"].status.value == "live"
    assert by_id["speak:6"].status.value == "live"
    assert by_id["speak:7"].status.value == "live"
    assert by_id["speak:8"].status.value == "live"
    assert by_id["speak:9"].status.value == "live"
    assert roadmap.execution_focus() is not None
    assert roadmap.execution_focus().node_id == "unified:6"


def test_speak_lock_version_present() -> None:
    assert isinstance(lock.SPEAK_LOCK_VERSION, int) and lock.SPEAK_LOCK_VERSION >= 9
