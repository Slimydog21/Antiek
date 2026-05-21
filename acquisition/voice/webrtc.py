"""WebRTC capture scaffold for interview voice mode (Sprint 17 mainline).

Substrate-side handler that accepts WebRTC SDP offers, negotiates
a session, and streams the captured audio chunks to the Whisper
transcription dispatch tier. Per master-spec §11.5: ~3-5s round-trip
latency end-to-end with async voice; sync option (OpenAI Realtime
API) deferred to Sprint 23+ per §15.3.

Sprint 17 substrate-side scaffold. Browser-side capture component
lives at apps/reading/src/components/InterviewVoiceCapture.tsx
(operator-driven follow-on; needs MediaRecorder API + WebRTC peer
connection)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class WebRTCSessionHandle:
    """Substrate-side handle for an in-flight WebRTC interview session."""

    session_id: str
    interview_id: str
    informant_handle: Optional[str]
    started_at: str
    sdp_offer_received: bool = False
    sdp_answer_sent: bool = False


@dataclass
class WebRTCSessionRegistry:
    """In-memory registry of active WebRTC sessions. Production uses
    a Redis-backed registry; for Sprint 17 scaffold an in-memory
    dict suffices because there's one operator + one informant at a
    time."""

    sessions: dict[str, WebRTCSessionHandle] = field(default_factory=dict)

    def open_session(
        self,
        *,
        interview_id: str,
        informant_handle: Optional[str] = None,
    ) -> WebRTCSessionHandle:
        session = WebRTCSessionHandle(
            session_id=f"webrtc-{uuid.uuid4().hex[:12]}",
            interview_id=interview_id,
            informant_handle=informant_handle,
            started_at=_now_iso(),
        )
        self.sessions[session.session_id] = session
        return session

    def accept_offer(self, session_id: str, sdp_offer: str) -> str:
        """Process an SDP offer from the browser. Returns the SDP
        answer the browser will set on its peer connection.

        Sprint 17 stub: returns a placeholder. Real WebRTC negotiation
        requires aiortc or equivalent + ICE servers."""
        if session_id not in self.sessions:
            raise ValueError(f"unknown session {session_id!r}")
        # Stub: a real impl negotiates SDP via aiortc.RTCPeerConnection.
        return f"<sdp_answer_for_{session_id}_placeholder>"

    def end_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


# Module-level registry used by interfaces/research/api/app.py
# follow-on endpoints when the WebRTC bridge wires up.
default_registry = WebRTCSessionRegistry()


def get_default_registry() -> WebRTCSessionRegistry:
    return default_registry
