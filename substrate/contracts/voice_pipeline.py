"""Voice-pipeline contract — the seam-#2 resolution (single voice owner).

Owned by **``acquisition/voice/``**. This is the single owner of the
capture → ASR → distill pipeline: ``WhisperTranscriber`` + ``transcribe_audio``
(capture/ASR), ``webrtc.py`` (browser capture), and ``ingest_voice_note()``
(distill → a ``document_type='voice_note'`` document + chunks + nodes, emitting
``document.loaded``). Two workflows *call* it — Read SPR-06 (record a voice
note while reading) and Speak SPR-02 (async voice interview) — and **neither
builds a parallel pipeline.** The decision is recorded in
``docs/decisions/tech-stack-ledger.md``; this contract makes it enforceable.

The collision the four product specs left open: Read SPR-06's own spec page
says "build the capture→ASR→distill pipeline as a reusable service" — phrasing
that invites a *second* owner. The master spec demotes that to "call the
existing service," and the ledger names ``acquisition/voice/`` the sole owner.
Two pipelines would drift and double the maintenance surface for no benefit.

The load-bearing, greppable invariant: **exactly one module defines
``ingest_voice_note`` (``acquisition/voice/adapter.py``), and it is the only
producer of ``document_type='voice_note'`` documents.** A second definition, or
any other module inserting a voice-note document, is the fork this contract
forbids — ``tests/test_seam_voice_single_owner.py`` greps for it and fails.

This is a ``Protocol`` (a behavioral shape — ingest a transcript, return a
result with the new document id), not a Pydantic data model, so it is excluded
from TS codegen. It pins the *call surface* the two consuming workflows compose
against, so neither needs to know how the owner distills — only how to call it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# The owning package, stated as a constant so a guard test (and a future
# maintainer) can assert ownership in one place. The single producer of
# voice-note documents lives here and nowhere else.
VOICE_PIPELINE_OWNER: str = "acquisition/voice/"

# The document_type the owner stamps on every voice-note document. The
# single-owner invariant is: only the owner produces documents of this type.
VOICE_NOTE_DOCUMENT_TYPE: str = "voice_note"

# The single producing function. A second definition anywhere is a fork.
VOICE_INGEST_FUNCTION: str = "ingest_voice_note"


@runtime_checkable
class VoicePipelineContract(Protocol):
    """The call surface a workflow uses to turn a voice transcript into a
    substrate document — owned by ``acquisition/voice/``. Read SPR-06 and
    Speak SPR-02 compose against this; they do not re-implement it.

    The method name and the new-document-id return are the committed seam; the
    distillation internals (chunking, embedding, node extraction) belong to the
    owner and are intentionally not part of the contract a caller depends on."""

    def ingest_voice_note(
        self,
        transcript: str,
        *,
        investigation_id: str,
    ) -> object:
        """Distill a transcript into a ``document_type='voice_note'`` document
        (+ chunks + nodes) and return a result carrying the new ``document_id``.
        The single sanctioned producer of voice-note documents."""
        ...
