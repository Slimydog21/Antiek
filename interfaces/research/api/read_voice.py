"""Voice-note capture endpoints for the reader (Read SPR-06 last-mile).

Two endpoints close the voice-note loop the reader UI drives:

  POST /voice/transcribe          audio bytes → transcript (Whisper)
  POST /books/{id}/voice-note     confirmed transcript → distilled notes

The substrate already owns the hard parts (``substrate/books/voice_note``:
transcription wrapper, the corrected-transcript guard, distillation +
provenance). These endpoints are the thin HTTP surface + the real
note-taker distiller wired through the dispatch router.

Both are gated: transcription needs the operator OpenAI key (503 without
it — never a silent failure), and distillation refuses an unconfirmed
transcript (400) so a misheard ASR line never becomes a confident insight.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from roles.note_taker import NOTE_TAKER_SYSTEM_PROMPT, parse_notes_response
from roles.note_taker.parser import ExtractedNote
from substrate.dispatch import ProviderError, dispatch


class DispatchNoteDistiller:
    """Distills a transcript into ExtractedNotes by dispatching the
    note_taker role through the real dispatch router. Implements the
    ``substrate.books.voice_note.NoteDistiller`` protocol. The transcript
    is the content the role distils; the role's own JSON contract caps
    the note count and shape (``parse_notes_response``)."""

    def __init__(self, investigation_id: str):
        self.investigation_id = investigation_id

    def distill(self, text: str, *, source_event_ids: tuple[str, ...]) -> list[ExtractedNote]:
        prompt = (
            NOTE_TAKER_SYSTEM_PROMPT
            + "\n\nThe following is a reader's spoken note about a book "
            "passage, transcribed and confirmed by the reader:\n\n"
            + text
            + "\n\nNow produce the JSON object."
        )
        result = dispatch(prompt, "note_taker", investigation_id=self.investigation_id)
        notes = parse_notes_response(result.text)
        # Thread the capture-event provenance onto each note.
        if source_event_ids:
            notes = [
                ExtractedNote(
                    note_id=n.note_id,
                    text=n.text,
                    confidence=n.confidence,
                    source_event_ids=source_event_ids,
                )
                for n in notes
            ]
        return notes


class TranscribeResponse(BaseModel):
    transcript: str
    language: str | None = None
    duration_seconds: float = 0.0


class VoiceNoteRequest(BaseModel):
    page_index: int = Field(ge=0)
    transcript: str = Field(min_length=1)
    audio_ref: str | None = None
    # The reader MUST confirm/correct the transcript before distillation.
    confirmed: bool = False
    investigation_id: str = Field(min_length=1, max_length=128)


class VoiceNoteResponseModel(BaseModel):
    voice_note_id: str
    document_id: str
    page_index: int
    note_count: int
    notes: list[str]
    emitted_event_ids: list[str]


def register_read_voice_routes(app: FastAPI) -> None:
    """Mount the reader voice-note routes."""

    @app.post("/voice/transcribe", response_model=TranscribeResponse, tags=["voice"])
    async def transcribe(request: Request) -> TranscribeResponse:
        """Transcribe a captured audio blob (raw request body, e.g.
        ``audio/webm``). Gated on the operator key — 503 if Whisper is
        unavailable, so the reader can retry rather than see a crash."""
        from substrate.books.voice_note import transcribe_voice_note

        audio = await request.body()
        if not audio:
            raise HTTPException(status_code=400, detail="empty_audio")
        outcome = transcribe_voice_note(audio, filename="voice-note.webm")
        if not outcome.ok:
            raise HTTPException(status_code=503, detail=f"transcription_unavailable: {outcome.error}")
        t = outcome.transcript
        assert t is not None
        return TranscribeResponse(
            transcript=t.text, language=t.language, duration_seconds=t.duration_seconds
        )

    @app.post(
        "/books/{document_id}/voice-note",
        response_model=VoiceNoteResponseModel,
        status_code=201,
        tags=["voice"],
    )
    async def create_voice_note(document_id: str, req: VoiceNoteRequest) -> VoiceNoteResponseModel:
        """Distill a CONFIRMED transcript into insight/question notes
        anchored to a book page. Refuses an unconfirmed transcript (the
        rigor-#1 guard) and a missing distiller (503)."""
        from substrate.books.voice_note import UnconfirmedTranscript, distill_voice_note

        try:
            result = distill_voice_note(
                document_id=document_id,
                page_index=req.page_index,
                transcript_text=req.transcript,
                distiller=DispatchNoteDistiller(req.investigation_id),
                investigation_id=req.investigation_id,
                audio_ref=req.audio_ref,
                confirmed=req.confirmed,
            )
        except UnconfirmedTranscript as exc:
            raise HTTPException(status_code=400, detail=f"unconfirmed_transcript: {exc}") from exc
        except (ProviderError, KeyError) as exc:
            raise HTTPException(status_code=503, detail=f"distiller_unavailable: {exc}") from exc

        return VoiceNoteResponseModel(
            voice_note_id=result.voice_note_id,
            document_id=result.document_id,
            page_index=result.page_index,
            note_count=len(result.notes),
            notes=[n.text for n in result.notes],
            emitted_event_ids=result.emitted_event_ids,
        )
