"""services.voice — transactional voice-note + anchor save.

This package wraps the Sprint 13 voice-note ingest path
(``acquisition.voice.ingest_voice_note``) and the SPR-02 anchor
write (``substrate.voice.anchor_api.create_anchor``) into a single
atomic operation. See ``anchor_service.py`` for the public surface.
"""

from .anchor_service import (  # noqa: F401
    AnchorSaveResult,
    SaveAnchoredVoiceNoteError,
    save_anchored_voice_note,
)
