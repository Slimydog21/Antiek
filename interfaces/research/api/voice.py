"""Voice-note region anchor HTTP API (SPR-05 / M3).

FastAPI route handlers for:

  POST /api/voice/anchor — save a voice note + anchor in one tx.
  GET  /api/voice/anchor/{anchor_id}/audio — fetch audio bytes
        (returns 501 today — audio-blob storage doesn't exist yet
        per SPR-05's surfaced substrate gap).

TS client uses ``apps/reading/api/voice/anchor.ts`` against these paths.

The substrate-side ``services.voice.anchor_service.save_anchored_voice_note``
takes a transcript + bbox + page + duration. The TS client today sends
audio bytes via MediaRecorder + a transcript (whatever the Sprint-13
ASR pipeline produced). The audio bytes have nowhere to land — Sprint-13
stored only transcripts. The audio_b64 field is accepted for forward
compatibility but currently ignored, with a header response flag noting
so. When audio-blob storage lands, the handler will write the bytes
through a new substrate writer; the contract on this wire is unchanged.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.voice import anchor_service  # noqa: E402

_log = logging.getLogger(__name__)


class BBoxModel(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class AnchorRequest(BaseModel):
    """Body for ``POST /api/voice/anchor``."""

    document_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1, default="__operator__")
    page: int = Field(ge=0)
    bbox: BBoxModel
    transcript: str = Field(default="")
    duration_seconds: float = Field(ge=0.0, default=0.0)
    language: Optional[str] = None
    title: Optional[str] = None
    # Forward-compatibility — audio bytes have no storage today.
    audio_b64: Optional[str] = None


class AnchorResponse(BaseModel):
    voice_note_id: str
    anchor_id: str
    chunk_id: Optional[str] = None
    audio_stored: bool = False
    audio_storage_note: Optional[str] = None


def register_voice_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
) -> None:
    """Mount voice-anchor routes on ``app``."""

    @app.post(
        "/api/voice/anchor",
        response_model=AnchorResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["voice"],
    )
    async def post_voice_anchor(
        request: Request, body: AnchorRequest,
    ) -> AnchorResponse:
        if body.audio_b64:
            _log.info(
                "voice/anchor: audio_b64 received (len=%d) but discarded; "
                "audio-blob storage gap is documented in SPR-05 handoff.",
                len(body.audio_b64),
            )

        try:
            result = anchor_service.save_anchored_voice_note(
                transcript=body.transcript,
                document_id=body.document_id,
                page=body.page,
                bbox={
                    "x0": body.bbox.x0, "y0": body.bbox.y0,
                    "x1": body.bbox.x1, "y1": body.bbox.y1,
                },
                operator_id=body.user_id,
                duration_seconds=body.duration_seconds,
                language=body.language,
                title=body.title,
                db_path=db_path,
            )
        except anchor_service.SaveAnchoredVoiceNoteError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "voice_anchor_save_failed",
                        "message": str(exc),
                    },
                },
            ) from exc

        chunk_id = getattr(result.anchor, "chunk_id", None)
        audio_note = (
            "audio bytes were not stored — substrate audio-blob storage "
            "does not yet exist (SPR-05 surfaced gap). Transcript saved."
            if body.audio_b64 else None
        )
        return AnchorResponse(
            voice_note_id=result.voice_note_id,
            anchor_id=result.anchor.anchor_id,
            chunk_id=chunk_id,
            audio_stored=False,
            audio_storage_note=audio_note,
        )

    @app.get(
        "/api/voice/anchor/{anchor_id}/audio",
        tags=["voice"],
    )
    async def get_voice_anchor_audio(anchor_id: str):
        raise HTTPException(
            status_code=501,
            detail={
                "error": {
                    "code": "audio_storage_not_implemented",
                    "message": (
                        f"Voice-note audio-blob storage is not yet wired "
                        f"into the substrate. Anchor {anchor_id} exists "
                        f"but raw audio bytes are not retrievable. "
                        f"See SPR-05 handoff."
                    ),
                },
            },
        )
