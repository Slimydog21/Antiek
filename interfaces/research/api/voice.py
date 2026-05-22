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
from services.voice.audio_store import (  # noqa: E402
    exists as audio_exists,
    load_audio,
    path_for as audio_path_for,
    store_audio_b64,
)

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
        # Compute voice_note_id deterministically BEFORE calling save
        # so we can store the audio bytes at the canonical path AND
        # pass that path back into the documents-row insert, in one
        # commit. ``_stable_voice_note_id`` is the same algorithm
        # save_anchored_voice_note uses; the deterministic match means
        # the audio file and the document row reference each other.
        from datetime import datetime as _dt, timezone as _tz
        recorded_at = _dt.now(_tz.utc)
        voice_note_id = anchor_service._stable_voice_note_id(
            operator_id=body.user_id, recorded_at=recorded_at,
        )

        # Store audio FIRST so the path is known by the time the
        # documents row gets the metadata stamp. Failure here is
        # non-fatal — the document + anchor still save with
        # audio_blob_path=None.
        audio_blob_path: Optional[str] = None
        audio_stored = False
        audio_note: Optional[str] = None
        if body.audio_b64:
            try:
                audio_blob_path = store_audio_b64(
                    voice_note_id=voice_note_id,
                    audio_b64=body.audio_b64,
                    ext="opus",
                )
                audio_stored = True
                audio_note = audio_blob_path
                _log.info(
                    "voice/anchor: stored audio for %s at %s",
                    voice_note_id, audio_blob_path,
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "voice/anchor: audio store failed (%s); transcript "
                    "saved without audio.", exc,
                )
                audio_note = f"audio_store_failed: {exc}"

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
                recorded_at=recorded_at,
                duration_seconds=body.duration_seconds,
                language=body.language,
                title=body.title,
                db_path=db_path,
                voice_note_id=voice_note_id,
                audio_blob_path=audio_blob_path,
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
        return AnchorResponse(
            voice_note_id=result.voice_note_id,
            anchor_id=result.anchor.anchor_id,
            chunk_id=chunk_id,
            audio_stored=audio_stored,
            audio_storage_note=audio_note,
        )

    @app.get(
        "/api/voice/anchor/{anchor_id}/audio",
        tags=["voice"],
    )
    async def get_voice_anchor_audio(anchor_id: str):
        """Serve the raw audio bytes for the voice note anchored at
        ``anchor_id``. Reads from the audio-blob store landed
        2026-05-22; replaces the SPR-05 501 stub.

        Resolution path:
          1. anchor_id → voice_note_anchor row → voice_note_id
          2. voice_note_id → path via audio_store.path_for
          3. Stream the bytes back as audio/ogg (opus container)
        """
        from substrate.voice.anchor_api import get_anchor_by_id
        anchor = get_anchor_by_id(anchor_id, db_path=db_path)
        if anchor is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "anchor_not_found", "message": anchor_id}},
            )
        voice_note_id = anchor.voice_note_id
        if not audio_exists(voice_note_id):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "audio_not_stored",
                        "message": (
                            f"Anchor {anchor_id} exists but its voice note "
                            f"{voice_note_id} has no stored audio bytes "
                            "(transcript-only save, pre-2026-05-22 import, "
                            "or audio_store write failure at record-time)."
                        ),
                    },
                },
            )
        path = audio_path_for(voice_note_id)
        from fastapi.responses import Response as FastResponse
        return FastResponse(
            content=load_audio(path),
            media_type="audio/ogg",
            headers={
                "Content-Disposition": f'inline; filename="{voice_note_id}.opus"',
            },
        )
