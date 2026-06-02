"""Speak SPR-04 M5 — capture interview trajectories for a gated RL-tuned
interviewer.

The RL-tuned interviewer (one that LEARNS to ask better questions) is
deferred to the Loop-3/G8 track. This module does the half that is safe
now: CAPTURE the interview trajectories in the existing harvest format,
so when the gate opens there is training data. It does NOT train, and a
training/harvest attempt is refused unless the operator has explicitly
unlocked Loop 3 (``ANTIEK_LOOP3_UNLOCKED=1``).

Capture (recording) is always allowed; harvesting to prime-rl format is
gated — ``harvest_trajectory_for_prime_rl`` calls ``check_unlocked``
first. The split is deliberate: 'we recorded what happened' is not
'we authorized training'.
"""

from __future__ import annotations

from substrate.loop_3.trajectory_harvest import HarvestedTrajectory, harvest_trajectory_for_prime_rl

from .async_interview import resume


def capture_trajectory(db_path: str, interview_id: str) -> list[dict]:
    """Shape an interview's turns into harvestable trajectory events.

    Each interviewer utterance is a role-driven 'decision' (an action);
    the prior informant turn is its observation. Always allowed — this
    is recording, not training. Returns events in the shape
    ``harvest_trajectory_for_prime_rl`` consumes (action_type ending in
    '.delivered', role='interviewer')."""
    session = resume(db_path, interview_id)
    events: list[dict] = []
    for turn in session.turns:
        if turn.get("role") == "interviewer":
            events.append({
                "action_type": "interview.turn.delivered",
                "role": "interviewer",
                "payload": {
                    "text": turn.get("text", ""),
                    "question_id": turn.get("question_id"),
                    "follow_up_for_prior_turn": turn.get("follow_up_for_prior_turn", False),
                },
            })
        else:
            events.append({
                "action_type": "interview.turn.recorded",
                "role": "informant",
                "payload": {"text": turn.get("text", ""),
                            "question_id": turn.get("question_id")},
            })
    return events


def harvest_for_rl(db_path: str, interview_id: str) -> HarvestedTrajectory:
    """Attempt to harvest an interview to prime-rl training format.

    Gated: raises ``Loop3UnlockRequired`` unless the operator has set
    ``ANTIEK_LOOP3_UNLOCKED=1`` (G8). This is the 'training attempt' the
    SPR-04 no-training-gate test exercises — capture works, harvest is
    refused until unlock."""
    events = capture_trajectory(db_path, interview_id)
    return harvest_trajectory_for_prime_rl(
        trajectory_events=events,
        investigation_id=f"speak-interview-{interview_id}",
        role_filter="interviewer",
    )
