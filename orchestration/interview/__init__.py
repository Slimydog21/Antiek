"""Loop 4 — Interview orchestration (master-spec §11.3).

Conducts multi-turn AI interviews via the `interviewer` role. State-
machine driven by an `interview_guide` carrying must-cover questions
and adaptive follow-ups. Persists transcripts continuously; transcripts
feed back into the substrate's note-taking pipeline as a new ingested
source.

Sprint 17 ship: orchestrator skeleton + state machine. Voice-mode
WebRTC + streaming Whisper + TTS roundtrip lands in Sprint 17-18
follow-on per master-spec §11.7 sequence.
"""

from .orchestrator import (
    InterviewState,
    InterviewTurn,
    advance_interview,
    start_interview,
)

__all__ = [
    "InterviewState",
    "InterviewTurn",
    "advance_interview",
    "start_interview",
]
