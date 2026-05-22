"""Voice-note audio-blob store (2026-05-22 follow-up).

SPR-05's handoff named the gap: Sprint 13 stored voice-note transcripts
but not audio bytes. The substrate has no audio column on ``documents``;
adding one would put multi-MB blobs in DuckDB rows (the wrong shape).
Adding a separate audio table reinvents what filesystem layout already
gives us.

Mirror the SPR-09 / raw_bytes_store pattern:
``~/.antiek/audio/<voice_note_id>.<ext>``. Keyed by voice_note_id
because it's already unique and stable across the lifetime of a voice
note. No content-addressing here — audio bytes have a 1:1 with their
voice note (unlike PDFs which can be re-imported by multiple users);
the simplicity of ``voice_note_id → path`` is correct.

Used by:
- POST /api/voice/anchor handler: writes the audio_b64 bytes through
  ``store_audio()`` and stamps the resulting path into the voice note
  document's metadata. The metadata field
  ``content_json.audio_blob_path`` is the canonical reference (SPR-09
  / SPR-10 already look there).
- GET /api/voice/anchor/{anchor_id}/audio handler: looks up the voice
  note via the anchor, reads the path from metadata, streams the
  bytes. Replaces SPR-05's 501-with-an-honest-error stub.
- SPR-10 sidecar writer: ``build_sidecar_input_for_document`` reads
  the path to bundle audio in shareable sidecars.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)


def _resolve_root() -> Path:
    env = os.environ.get("ANTIEK_HOME")
    if env:
        return Path(env).expanduser() / "audio"
    return Path.home() / ".antiek" / "audio"


def store_audio(
    *,
    voice_note_id: str,
    audio_bytes: bytes,
    ext: str = "opus",
) -> str:
    """Persist audio bytes for a voice note. Returns the absolute path
    written.

    Idempotent: if the path exists with identical bytes, no rewrite. If
    it exists with different bytes (e.g., re-recording the same voice
    note id), overwrites — the voice_note_id is the source of truth.

    ``ext`` defaults to ``opus`` because that's what MediaRecorder
    produces by default in modern browsers; the SPR-05 recorder
    doesn't transcode. If a future recorder produces ``webm`` or
    ``mp3`` the caller passes a different ext.
    """
    if not voice_note_id or "/" in voice_note_id or "\\" in voice_note_id:
        raise ValueError(
            f"store_audio: voice_note_id must be a non-empty "
            f"path-safe string; got {voice_note_id!r}"
        )
    root = _resolve_root()
    root.mkdir(parents=True, exist_ok=True)
    ext = ext.lstrip(".") or "bin"
    path = root / f"{voice_note_id}.{ext}"
    if path.exists() and path.read_bytes() == audio_bytes:
        return str(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(audio_bytes)
    os.replace(tmp, path)
    return str(path)


def store_audio_b64(
    *,
    voice_note_id: str,
    audio_b64: str,
    ext: str = "opus",
) -> str:
    """Convenience wrapper: decode base64, store, return path. The
    SPR-05 wire contract sends base64-encoded audio in the POST body,
    so the FastAPI handler calls this variant directly."""
    if not audio_b64:
        raise ValueError("store_audio_b64: audio_b64 must not be empty")
    raw = base64.b64decode(audio_b64)
    return store_audio(voice_note_id=voice_note_id, audio_bytes=raw, ext=ext)


def load_audio(path: str) -> bytes:
    """Read audio bytes from the store. Raises ``FileNotFoundError`` if
    the path no longer exists (the audio store has no integrity check
    because the source-of-truth is the voice_note_id → path mapping,
    not a hash). Callers that need provenance check the voice_note
    document's metadata for the path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    return p.read_bytes()


def path_for(voice_note_id: str, *, ext: str = "opus") -> str:
    """Inverse of ``store_audio``: compute the canonical path for a
    voice_note_id without checking existence."""
    ext = ext.lstrip(".") or "bin"
    return str(_resolve_root() / f"{voice_note_id}.{ext}")


def exists(voice_note_id: str, *, ext: str = "opus") -> bool:
    """True iff audio is stored for this voice_note_id at the canonical
    extension. The voice-anchor restore path uses this to decide
    whether to ship audio in a sidecar."""
    return Path(path_for(voice_note_id, ext=ext)).exists()


__all__ = [
    "exists",
    "load_audio",
    "path_for",
    "store_audio",
    "store_audio_b64",
]
