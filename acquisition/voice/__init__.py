"""Voice note acquisition — Sprint 13.

Operator-records-something-into-the-mic flow.

Surface:

- ``client.transcribe_audio(audio_bytes, *, filename, language=None)``
  — sends audio to the OpenAI Whisper API and returns the transcript.
  Stubbed in tests via the ``transcriber`` injection point.
- ``adapter.ingest_voice_note(transcript, *, investigation_id, ...)``
  — writes a ``document_kind: voice_note`` row + chunks + nodes,
  emits ``document.loaded``. Used after a successful transcription.
- ``adapter.transcribe_and_ingest(audio_bytes, *, filename, ...)``
  — convenience wrapper for the operator end-to-end flow.
"""

from .adapter import (
    IngestVoiceNoteResult,
    ingest_voice_note,
    transcribe_and_ingest,
    voice_note_doc_id,
)
from .client import (
    Transcriber,
    Transcript,
    WhisperTranscriber,
    transcribe_audio,
)

__all__ = [
    "IngestVoiceNoteResult",
    "Transcriber",
    "Transcript",
    "WhisperTranscriber",
    "ingest_voice_note",
    "transcribe_and_ingest",
    "transcribe_audio",
    "voice_note_doc_id",
]
