"""Text-to-speech endpoint for voice replies (Read SPR-07).

Synthesizes an AI reply (a rabbit-hole answer, a note response) to spoken
audio on demand, so a reader who prefers audio hears the reply instead of
reading it. This is the ASYNC reply path — not the real-time talk-to-book
loop, which stays gated on speech round-trip latency (~3–5s today).

The synthesis is gated on the operator's OpenAI key (no key ⇒ 503), so it
never burns credits without an explicit key. The provider is the existing
``OpenAITTSProvider``; this router is the thin HTTP adapter.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    voice: str | None = None


def register_speech_routes(app: FastAPI) -> None:
    """Mount the TTS route. Mirrors the other register_*_routes helpers."""

    @app.post("/speech/tts", tags=["speech"])
    async def tts(req: TtsRequest) -> Response:
        from substrate.dispatch.providers.openai_tts import OpenAITTSProvider

        provider = OpenAITTSProvider()
        # synthesize() is a blocking httpx POST of up to 60 s. Inline in this
        # async def it parks the event loop of the single uvicorn worker, so
        # every other request waits on it. Hop it to a thread, the idiom
        # speak_routes._off_loop uses; exceptions re-raise here unchanged, so
        # the error mapping below is the same.
        try:
            audio = await asyncio.to_thread(provider.synthesize, req.text, voice=req.voice)
        except RuntimeError as exc:  # no API key
            raise HTTPException(status_code=503, detail=f"tts_unavailable: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=audio, media_type="audio/mpeg")
