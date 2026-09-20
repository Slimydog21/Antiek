"""Voice notes — capture → transcribe → distill, anchored to a book
reading locator (Read SPR-06, backend).

Reuses the existing voice + note-taker substrate rather than inventing a
parallel path: ``acquisition.voice`` transcribes (Whisper), and the
note-taker distills a transcript into ``ExtractedNote`` insight/question
nodes (``note.emerged``). What this module adds is Read-specific:

- the voice note is anchored to a **book reading locator** (the
  ``page_index`` of SPR-01's ``book_assets``), so a distilled insight
  knows which page it came from;
- **voice provenance** — source = voice, plus the audio reference and the
  transcript — rides on the returned :class:`VoiceNoteResult`;
- the **corrected-transcript guard** (rigor #1): you cannot distill an
  unconfirmed transcript. ASR mishears accents, jargon, and names; turning
  a misheard sentence into a confident insight is the failure this guard
  forbids. The reading surface shows the transcript, the user confirms or
  corrects it, and only the confirmed text is distilled.

Transcription and distillation are both injected (Protocols), exactly as
``substrate/graph/search.py`` injects its embedding model — production
passes ``WhisperTranscriber`` + the note-taker dispatch; tests pass stubs,
so this module is testable with no live ASR or LLM.

Question-shaped distilled notes (and a question-shaped transcript when
no note ends with ``?``) also emit ``question.identified`` so they land
in watch-for-later / Surface E park → Thought Partner discuss (Anti-Ek
voice→park→TP residual). The reading UI seeds the TP bus with the
SERVABLE reading mount after save.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from acquisition.voice.client import Transcriber, Transcript, transcribe_audio
from roles.note_taker.parser import ExtractedNote
from substrate.event_log import emit_typed
from substrate.schemas.events import NoteEmergedPayload, QuestionIdentifiedPayload


class UnconfirmedTranscript(RuntimeError):
    """Raised when distillation is attempted on a transcript the user has
    not confirmed/corrected. The honesty guard (rigor #1): don't turn a
    misheard transcript into a confident insight."""


class NoteDistiller(Protocol):
    """Turns transcript text into ExtractedNotes. Production wraps a
    note-taker role dispatch; tests pass a deterministic stub. Kept a
    Protocol so this module never hard-depends on the LLM router."""

    def distill(self, text: str, *, source_event_ids: tuple[str, ...]) -> list[ExtractedNote]: ...


@dataclass(frozen=True)
class TranscriptionOutcome:
    """Result of transcribing captured audio. Exactly one of
    ``transcript`` / ``error`` is set — ASR failure is surfaced as a
    value, never raised through to crash the reader (rigor: ASR failure
    handled, never silently dropped)."""

    transcript: Transcript | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.transcript is not None


@dataclass(frozen=True)
class VoiceNoteResult:
    """A distilled voice note with its provenance. The distilled
    ``notes`` are emitted as ordinary ``note.emerged`` events (so they
    flow into the graph like any insight); this record carries the
    Read-surface provenance that ties each note back to the page it was
    spoken at, the audio, and the transcript.

    Question-shaped notes also emit ``question.identified`` (parked for
    watch-for-later / Surface E). ``parked_question_ids`` / ``_texts``
    list those parks in order — empty when nothing looked like a question.
    """

    voice_note_id: str
    document_id: str
    page_index: int
    source: str  # always "voice"
    audio_ref: str | None
    transcript_text: str
    notes: list[ExtractedNote]
    emitted_event_ids: list[str] = field(default_factory=list)
    parked_question_ids: list[str] = field(default_factory=list)
    parked_question_texts: list[str] = field(default_factory=list)


def transcribe_voice_note(
    audio_bytes: bytes,
    *,
    filename: str = "voice-note.webm",
    language: str | None = None,
    transcriber: Transcriber | None = None,
) -> TranscriptionOutcome:
    """Transcribe captured audio via the existing Whisper path. ASR
    failures (network, quota, bad audio) are caught and returned as
    ``error`` so the reader can offer retry — never a crash."""
    try:
        transcript = transcribe_audio(
            audio_bytes, filename=filename, language=language, transcriber=transcriber
        )
    except Exception as exc:  # ASR is fallible; surface, don't crash.
        return TranscriptionOutcome(transcript=None, error=f"{type(exc).__name__}: {exc}")
    return TranscriptionOutcome(transcript=transcript, error=None)



_QUESTION_STARTERS = frozenset({
    "what", "why", "how", "when", "where", "which", "who", "whose", "whom",
    "is", "are", "can", "could", "should", "would", "do", "does", "did",
    "will", "won't", "isn't", "aren't",
})


def looks_like_question(text: str) -> bool:
    """Honest park heuristic — not an LLM classifier.

    True when the text ends with ``?`` or opens with a common interrogative.
    Used to decide which distilled voice notes become watch-for-later parks.
    """
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith("?"):
        return True
    first = t.split()[0].lower().rstrip(":,;")
    return first in _QUESTION_STARTERS


def _park_anchor_region(page_index: int) -> str:
    """Book reading locator as the question's anchor (page index, 0-based)."""
    return f"book_page:{page_index}"


def distill_voice_note(
    *,
    document_id: str,
    page_index: int,
    transcript_text: str,
    distiller: NoteDistiller,
    investigation_id: str,
    audio_ref: str | None = None,
    confirmed: bool,
    capture_event_id: str | None = None,
    emit: bool = True,
) -> VoiceNoteResult:
    """Distill a CONFIRMED transcript into insight/question notes anchored
    to a book reading locator, emitting ``note.emerged`` for each.

    ``confirmed`` MUST be True — it asserts the user reviewed/corrected the
    transcript. Passing False raises :class:`UnconfirmedTranscript`; we do
    not distill text the user hasn't verified (rigor #1).

    ``capture_event_id``, when provided, is threaded into each note's
    ``source_event_ids`` so the note traces back to the voice-capture
    event (and thus the locator) through the event graph.
    """
    if not confirmed:
        raise UnconfirmedTranscript(
            "refusing to distill an unconfirmed transcript — show it to the "
            "user and distill only the corrected text (Read SPR-06 rigor #1)"
        )
    voice_note_id = f"vnote-{uuid.uuid4().hex[:12]}"
    source_ids: tuple[str, ...] = (capture_event_id,) if capture_event_id else ()
    notes = distiller.distill(transcript_text, source_event_ids=source_ids)

    emitted: list[str] = []
    parked_ids: list[str] = []
    parked_texts: list[str] = []
    if emit:
        for note in notes:
            event_id = emit_typed(
                investigation_id,
                NoteEmergedPayload(
                    note_id=note.note_id,
                    note_text=note.text,
                    source_event_ids=list(note.source_event_ids),
                    confidence=note.confidence,
                ),
                document_id=document_id,
                role="read/voice_note",
                policy_id="read/books/voice_note",
            )
            if event_id:
                emitted.append(event_id)

        # Park question-shaped notes into watch-for-later (Surface E SoT =
        # question.identified). Dual structure: event log parks; TP seed is UI.
        candidates: list[str] = [
            n.text.strip() for n in notes if looks_like_question(n.text)
        ]
        if not candidates and looks_like_question(transcript_text):
            candidates = [transcript_text.strip()]
        for qtext in candidates:
            qid = f"q-voice-{uuid.uuid4().hex[:12]}"
            q_event = emit_typed(
                investigation_id,
                QuestionIdentifiedPayload(
                    question_id=qid,
                    question_text=qtext,
                    anchor_region_id=_park_anchor_region(page_index),
                ),
                document_id=document_id,
                role="read/voice_note",
                policy_id="read/books/voice_note",
            )
            if q_event:
                emitted.append(q_event)
                parked_ids.append(qid)
                parked_texts.append(qtext)

    return VoiceNoteResult(
        voice_note_id=voice_note_id,
        document_id=document_id,
        page_index=page_index,
        source="voice",
        audio_ref=audio_ref,
        transcript_text=transcript_text,
        notes=list(notes),
        emitted_event_ids=emitted,
        parked_question_ids=parked_ids,
        parked_question_texts=parked_texts,
    )
