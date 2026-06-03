"""Loop 4 — Interview orchestrator (state-machine driven).

Conducts multi-turn AI interviews via the `interviewer` role. Differs
from Loops 1, 2, 3 because:
- conversational (multi-turn) rather than one-shot
- state-machine driven by interview_guide
- has memory across the conversation (long context, not per-turn dispatch)
- produces transcripts that flow into the substrate's note-taking

Per master-spec §11.3. Voice-mode WebRTC + TTS roundtrip wired
separately at `interfaces/research/api/interview_voice.py` (Sprint
17-18 follow-on).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC

# ---------------------------------------------------------------------------
# State machine types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterviewTurn:
    """One turn in an interview transcript. ``speaker`` is either
    ``"interviewer"`` (the AI) or ``"informant"`` (the human)."""

    turn_id: str
    speaker: str  # "interviewer" | "informant"
    text: str
    emitted_at: str  # ISO 8601


@dataclass
class InterviewState:
    """State machine for a single multi-turn interview session.

    The ``interview_guide`` carries must-cover questions and adaptive
    follow-up rules; the orchestrator tracks which questions have
    been asked, which follow-ups are open, and whether the
    conversation should wrap.
    """

    interview_id: str
    project_id: str
    informant_handle: str | None
    interview_guide: dict
    turns: list[InterviewTurn] = field(default_factory=list)
    must_cover_asked: set[str] = field(default_factory=set)
    status: str = "in_progress"  # | "completed" | "declined" | "incomplete"
    consent_recorded: bool = False

    def remaining_must_cover(self) -> list[dict]:
        """Must-cover questions from the guide that haven't been asked."""
        all_questions = self.interview_guide.get("must_cover", [])
        return [q for q in all_questions if q.get("id") not in self.must_cover_asked]


def start_interview(
    project_id: str,
    interview_guide: dict,
    informant_handle: str | None = None,
) -> InterviewState:
    """Initialize a new interview state. Caller is responsible for
    capturing consent before any turns are exchanged — orchestrator
    refuses to ``advance_interview`` until ``consent_recorded=True``."""
    return InterviewState(
        interview_id=f"interview-{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        informant_handle=informant_handle,
        interview_guide=interview_guide,
    )


# ---------------------------------------------------------------------------
# Turn-by-turn advance
# ---------------------------------------------------------------------------


class ConsentRequired(Exception):
    """Raised if advance_interview is called before consent is recorded."""


def advance_interview(
    state: InterviewState,
    informant_response: str | None = None,
    *,
    dispatch_fn=None,  # injection point for substrate.dispatch.dispatch
) -> InterviewState:
    """Advance the interview by one turn.

    Decision tree:
    1. If consent not yet recorded → raise ConsentRequired.
    2. If informant_response is provided → append as informant turn,
       check if the most-recent interviewer must-cover question is now
       answered (mark must_cover_asked), then either ask a follow-up
       on this thread OR pivot to the next must-cover question.
    3. If remaining_must_cover is empty AND no open follow-ups →
       mark status="completed" and emit a wrap turn.
    4. Otherwise compose next interviewer question via the
       `interviewer` role (dispatch_fn injected for testability).
    """
    if not state.consent_recorded:
        raise ConsentRequired(
            f"interview {state.interview_id} has no consent recorded; "
            "capture consent before advancing turns"
        )

    if informant_response is not None:
        state.turns.append(
            InterviewTurn(
                turn_id=f"turn-{uuid.uuid4().hex[:8]}",
                speaker="informant",
                text=informant_response,
                emitted_at=_now_iso(),
            )
        )

    if not state.remaining_must_cover() and not _has_open_followups(state):
        state.status = "completed"
        state.turns.append(
            InterviewTurn(
                turn_id=f"turn-{uuid.uuid4().hex[:8]}",
                speaker="interviewer",
                text=_wrap_message(),
                emitted_at=_now_iso(),
            )
        )
        return state

    # Compose the next interviewer question. Injection-friendly so tests
    # don't require a real dispatch path; production passes
    # substrate.dispatch.dispatch.
    if dispatch_fn is None:
        next_text = _stub_next_question(state)
    else:
        # The interviewer role gets the full transcript + interview_guide
        # in its context pack and produces the next question text.
        result = dispatch_fn(
            prompt=_compose_interviewer_prompt(state),
            role="interviewer",
            investigation_id=f"loop4-{state.interview_id}",
        )
        next_text = result.text if hasattr(result, "text") else str(result)

    state.turns.append(
        InterviewTurn(
            turn_id=f"turn-{uuid.uuid4().hex[:8]}",
            speaker="interviewer",
            text=next_text,
            emitted_at=_now_iso(),
        )
    )

    # Mark must-cover satisfaction heuristically: if the new question
    # is one of the must-cover entries (by id or text match), mark it.
    for q in state.remaining_must_cover():
        if q.get("id") and q["id"] in next_text:
            state.must_cover_asked.add(q["id"])
            break
        if q.get("text") and q["text"][:40] in next_text:
            state.must_cover_asked.add(q.get("id") or q["text"][:40])
            break

    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _has_open_followups(state: InterviewState) -> bool:
    """Heuristic: an interview has open follow-ups if the most recent
    informant turn introduced a new thread the interviewer hasn't
    explored. Real implementation lives in the interviewer role's
    parser; this stub returns False for the empty case."""
    return False


def _wrap_message() -> str:
    return (
        "Thank you for the time and detail you brought to this "
        "conversation. The transcript will feed into the project; "
        "I'll surface anything that needs your review back to you "
        "directly. Is there anything you'd like to add before we wrap?"
    )


def _stub_next_question(state: InterviewState) -> str:
    """Test-time stub when no dispatch_fn is injected."""
    remaining = state.remaining_must_cover()
    if remaining:
        q = remaining[0]
        return q.get("text") or f"[must-cover question {q.get('id')}]"
    return "[follow-up question — interviewer role would generate this]"


def _compose_interviewer_prompt(state: InterviewState) -> str:
    """Compose the interviewer-role prompt from the current state.
    Includes the interview_guide, the transcript so far, and the
    remaining must-cover items. Real role prompt lives at
    `roles/interviewer/prompt.py`; this composer builds the context
    pack."""
    transcript = "\n".join(
        f"{t.speaker.upper()}: {t.text}" for t in state.turns
    )
    return json.dumps(
        {
            "interview_guide": state.interview_guide,
            "transcript_so_far": transcript,
            "remaining_must_cover": state.remaining_must_cover(),
        },
        indent=2,
    )
