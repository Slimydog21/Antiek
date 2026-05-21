"""Loop 4 — Interview orchestrator tests (Sprint 17, master-spec §11.3)."""

from __future__ import annotations

import pytest

from orchestration.interview import (
    InterviewState,
    advance_interview,
    start_interview,
)
from orchestration.interview.orchestrator import ConsentRequired


def test_start_interview_creates_in_progress_state():
    state = start_interview(
        project_id="proj-biography-dad",
        interview_guide={
            "must_cover": [
                {"id": "q1", "text": "What's your earliest childhood memory?"},
                {"id": "q2", "text": "Tell me about your parents."},
            ],
        },
        informant_handle="uncle-fawzi",
    )
    assert state.interview_id.startswith("interview-")
    assert state.project_id == "proj-biography-dad"
    assert state.status == "in_progress"
    assert state.turns == []
    assert state.consent_recorded is False


def test_advance_raises_without_consent():
    state = start_interview("proj-x", {"must_cover": []})
    with pytest.raises(ConsentRequired):
        advance_interview(state, informant_response="Hi")


def test_advance_first_turn_emits_must_cover_question():
    state = start_interview(
        "proj-x",
        {
            "must_cover": [
                {"id": "q1", "text": "What's your earliest memory?"},
            ],
        },
    )
    state.consent_recorded = True
    new_state = advance_interview(state)
    assert len(new_state.turns) == 1
    assert new_state.turns[0].speaker == "interviewer"
    assert "earliest memory" in new_state.turns[0].text


def test_advance_completes_when_all_must_cover_asked():
    state = start_interview("proj-x", {"must_cover": []})
    state.consent_recorded = True
    new_state = advance_interview(state, informant_response="That's all I have")
    assert new_state.status == "completed"
    assert any(t.speaker == "interviewer" and "Thank you" in t.text for t in new_state.turns)


def test_remaining_must_cover_filters_asked():
    state = InterviewState(
        interview_id="interview-test",
        project_id="proj-x",
        informant_handle=None,
        interview_guide={
            "must_cover": [
                {"id": "q1", "text": "A?"},
                {"id": "q2", "text": "B?"},
                {"id": "q3", "text": "C?"},
            ],
        },
        must_cover_asked={"q1"},
    )
    remaining_ids = [q["id"] for q in state.remaining_must_cover()]
    assert remaining_ids == ["q2", "q3"]


def test_informant_response_appended_before_next_question():
    state = start_interview(
        "proj-x",
        {
            "must_cover": [
                {"id": "q1", "text": "What's your earliest memory?"},
                {"id": "q2", "text": "Tell me about your parents."},
            ],
        },
    )
    state.consent_recorded = True
    state = advance_interview(state)  # ask q1
    state = advance_interview(state, informant_response="I remember the kitchen at age 4.")
    speakers = [t.speaker for t in state.turns]
    # Pattern: interviewer (q1) → informant (response) → interviewer (q2)
    assert speakers[:3] == ["interviewer", "informant", "interviewer"]
