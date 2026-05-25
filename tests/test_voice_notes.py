"""Read SPR-06 — voice notes (backend): transcription, the corrected-
transcript honesty guard, distillation into anchored insight/question
nodes, and voice provenance. ASR + distillation are stubbed (no live
Whisper / LLM).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from acquisition.voice.client import Transcript
from roles.note_taker.parser import ExtractedNote
from substrate.books.voice_note import (
    UnconfirmedTranscript,
    distill_voice_note,
    transcribe_voice_note,
)

# ── stubs ───────────────────────────────────────────────────────────


class _OkTranscriber:
    def transcribe(self, audio_bytes, *, filename, language=None):
        return Transcript(text="the mind is not a vessel", language="en",
                          duration_seconds=2.0, model="stub")


class _FailingTranscriber:
    def transcribe(self, audio_bytes, *, filename, language=None):
        raise RuntimeError("whisper 429 rate limited")


class _StubDistiller:
    """Echoes the transcript into one insight note, threading the
    source_event_ids it was given (so we can assert anchoring)."""

    def __init__(self):
        self.seen_text = None
        self.seen_sources = None

    def distill(self, text, *, source_event_ids):
        self.seen_text = text
        self.seen_sources = source_event_ids
        return [
            ExtractedNote(
                note_id="note-1", text=f"insight: {text}",
                confidence="moderate", source_event_ids=source_event_ids,
            )
        ]


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-voice-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))


# ── M2: transcription + ASR failure handling ───────────────────────


def test_transcription_ok():
    out = transcribe_voice_note(b"audio", transcriber=_OkTranscriber())
    assert out.ok
    assert out.transcript.text == "the mind is not a vessel"
    assert out.error is None


def test_asr_failure_surfaced_not_raised():
    out = transcribe_voice_note(b"audio", transcriber=_FailingTranscriber())
    assert out.ok is False
    assert out.transcript is None
    assert "429" in out.error  # surfaced for retry, never a crash


# ── M3 + rigor #1: distill only from a CONFIRMED transcript ─────────


def test_distill_refuses_unconfirmed_transcript():
    with pytest.raises(UnconfirmedTranscript):
        distill_voice_note(
            document_id="doc-book-1", page_index=4,
            transcript_text="raw uncertain ASR output",
            distiller=_StubDistiller(), investigation_id="inv-1",
            confirmed=False,
        )


def test_distill_confirmed_transcript_yields_anchored_notes():
    distiller = _StubDistiller()
    result = distill_voice_note(
        document_id="doc-book-1", page_index=4,
        transcript_text="the corrected text",
        distiller=distiller, investigation_id="inv-1",
        audio_ref="blob://audio-123", confirmed=True,
        capture_event_id="cap-1",
    )
    # Distilled from the corrected text, not a raw transcript.
    assert distiller.seen_text == "the corrected text"
    # Anchored: the capture event id threads into the note's provenance.
    assert distiller.seen_sources == ("cap-1",)
    assert result.notes[0].source_event_ids == ("cap-1",)
    # M4: voice provenance on the result.
    assert result.source == "voice"
    assert result.audio_ref == "blob://audio-123"
    assert result.page_index == 4
    assert result.document_id == "doc-book-1"
    assert result.transcript_text == "the corrected text"


def test_distill_emits_note_emerged_events():
    from substrate.event_log import trajectory

    result = distill_voice_note(
        document_id="doc-book-1", page_index=0,
        transcript_text="confirmed", distiller=_StubDistiller(),
        investigation_id="inv-voice", confirmed=True,
    )
    assert len(result.emitted_event_ids) == 1
    events = trajectory("inv-voice")
    note_events = [e for e in events if e.get("action_type") == "note.emerged"]
    assert len(note_events) == 1
    assert note_events[0]["document_id"] == "doc-book-1"
    assert note_events[0]["payload"]["note_text"].startswith("insight:")
    assert note_events[0]["role"] == "read/voice_note"


def _client():
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    return TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))


def test_voice_note_endpoint_refuses_unconfirmed_transcript():
    """The /books/{id}/voice-note endpoint enforces the corrected-
    transcript guard: an unconfirmed transcript is refused (400) before
    any distillation/LLM dispatch."""
    resp = _client().post(
        "/books/doc-1/voice-note",
        json={
            "page_index": 0, "transcript": "raw ASR output",
            "confirmed": False, "investigation_id": "inv-1",
        },
    )
    assert resp.status_code == 400
    assert "unconfirmed_transcript" in resp.json()["detail"]


def test_transcribe_endpoint_503_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = _client().post(
        "/voice/transcribe", content=b"fake-audio-bytes",
        headers={"Content-Type": "audio/webm"},
    )
    assert resp.status_code == 503
    assert "transcription_unavailable" in resp.json()["detail"]


def test_transcribe_endpoint_400_on_empty_audio():
    resp = _client().post("/voice/transcribe", content=b"", headers={"Content-Type": "audio/webm"})
    assert resp.status_code == 400


def test_distill_can_skip_emission():
    """emit=False distills without writing events — for a preview the user
    hasn't committed yet."""
    result = distill_voice_note(
        document_id="d", page_index=0, transcript_text="x",
        distiller=_StubDistiller(), investigation_id="inv-2",
        confirmed=True, emit=False,
    )
    assert result.notes  # notes produced
    assert result.emitted_event_ids == []  # but nothing emitted
