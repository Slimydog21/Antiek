"""Transactional voice-note + anchor save (SPR-05 M3).

This module wraps the Sprint 13 voice-note ingest path and the SPR-02
anchor primitive into one atomic operation. The contract surfaced by
SPR-05's HTML spec, M3:

    "Inside a single transaction: insert voice_notes row, insert
     voice_note_anchor row, commit. Transaction rollback on any error."

What "voice_note row" means in Antiek
─────────────────────────────────────
Voice notes are NOT rows in a ``voice_notes`` table. Per Sprint 13
(see ``acquisition/voice/adapter.py``), a voice note is a row in
``documents`` with ``document_type='voice_note'``. The SPR-02 anchor
schema makes this explicit — the anchor's ``voice_note_id`` FK
targets ``documents(document_id)``.

The atomic boundary
───────────────────
The critical invariant is: the user MUST NOT see an anchor with no
voice note OR a voice note (document row) with a missing anchor
when they asked for an anchored save. We achieve this by writing
BOTH rows inside the same ``connect_write`` LockedConnection,
explicitly opening a transaction with BEGIN, and on any exception
inside the block issuing ROLLBACK before re-raising.

What lives OUTSIDE the transaction
──────────────────────────────────
Chunking / embedding / node creation / event emission. These are
the "rich ingest" side-effects of Sprint 13's ``ingest_voice_note``;
they are valuable but not load-bearing for the user-visible
contract. We perform them best-effort AFTER the atomic save
commits. A failure in this post-commit phase leaves a voice_note
document + anchor without chunks/nodes — which is fine: a
subsequent re-ingest of the same voice note (idempotent via
``voice_note_doc_id``) can fill them in.

Concurrency
───────────
The DuckDB unique constraint on ``voice_note_anchor.voice_note_id``
is the source of truth. Two simultaneous saves for the same voice
note → one wins, the other raises ``duckdb.ConstraintException``;
the caller (the FastAPI handler) maps that to HTTP 409.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Repo root on path for direct invocation (tests + uvicorn).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from acquisition.voice.adapter import (  # noqa: E402
    DEFAULT_VOICE_SOURCE_TIER,
    voice_note_doc_id,
)
from runtime.db_lock import LockedConnection, connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402
from substrate.voice.anchor_api import (  # noqa: E402
    BBox,
    VoiceNoteAnchor,
    create_anchor,
)


# ─────────────────────────────────────────────────────────────────────
# Public surface
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnchorSaveResult:
    """Outcome of a successful transactional save.

    ``voice_note_id`` is the ``document_id`` of the new voice_note
    row in ``documents``. ``anchor`` is the freshly-inserted SPR-02
    anchor (same shape ``substrate.voice.anchor_api.create_anchor``
    returns).
    """

    voice_note_id: str
    anchor: VoiceNoteAnchor


class SaveAnchoredVoiceNoteError(Exception):
    """Raised when the transactional save fails for any reason.

    Wraps the underlying exception so the caller (FastAPI handler)
    can decide HTTP status without unwrapping DuckDB-specific
    types. The original is preserved as ``__cause__``.
    """


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────


def _stable_voice_note_id(
    *, operator_id: str, recorded_at: datetime,
) -> str:
    """Same algorithm as ``acquisition.voice.adapter.voice_note_doc_id``.

    Re-exported here so callers can pre-compute the id (e.g. for
    idempotency keys) without importing from acquisition.
    """
    return voice_note_doc_id(operator_id, recorded_at)


def _insert_voice_note_document(
    con: LockedConnection,
    *,
    voice_note_id: str,
    operator_id: str,
    recorded_at: datetime,
    duration_seconds: float,
    transcript: str,
    title: Optional[str],
    language: Optional[str],
    source_tier: int,
) -> None:
    """Write the voice_note row into ``documents``.

    Mirrors what ``acquisition.voice.adapter.ingest_voice_note``
    writes into the documents table, but only the row insert — no
    chunks, no embeddings, no event emit. Those happen outside
    this transaction (see module docstring).

    Idempotent via the graph-ops ``on_conflict='ignore'`` path: if a
    voice note row with this id already exists (e.g. operator
    records-and-saves twice with the same operator_id +
    recorded_at), the second attempt is a no-op on the documents
    side. The anchor insert still runs — the SPR-02 unique
    constraint on ``voice_note_anchor.voice_note_id`` is what
    enforces 1:1 in that case.
    """
    auto_title = title or (
        f"Voice note {recorded_at.strftime('%Y-%m-%d %H:%M')}"
    )
    # Render a minimal markdown body for the documents.raw_text
    # column. We keep the shape identical to
    # acquisition.voice.adapter so the optional post-commit rich-
    # ingest can re-process the same content idempotently.
    body_lines = [
        f"# {auto_title}",
        "",
        f"**Recorded:** {recorded_at.isoformat()}",
    ]
    if duration_seconds:
        m, s = divmod(int(round(duration_seconds)), 60)
        body_lines.append(f"**Duration:** {m:02d}:{s:02d}")
    if language:
        body_lines.append(f"**Language:** {language}")
    body_lines.append("")
    body_lines.append("## Transcript")
    body_lines.append("")
    body_lines.append(transcript.strip())
    raw_text = "\n".join(body_lines)
    insert_document(
        con,
        document_id=voice_note_id,
        source_tier=int(source_tier),
        document_type="voice_note",
        source_uri=None,
        title=auto_title,
        author=operator_id,
        published_at=recorded_at,
        investigation_id=None,
        raw_text=raw_text,
        metadata={
            "operator_id": operator_id,
            "duration_seconds": duration_seconds,
            "language": language,
            "transcription_source": "whisper",
            "recorded_at": recorded_at.isoformat(),
        },
        on_conflict="ignore",
    )


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def save_anchored_voice_note(
    *,
    transcript: str,
    document_id: str,
    page: int,
    bbox: BBox,
    operator_id: str = "__operator__",
    recorded_at: Optional[datetime] = None,
    duration_seconds: float = 0.0,
    language: Optional[str] = None,
    title: Optional[str] = None,
    source_tier: int = DEFAULT_VOICE_SOURCE_TIER,
    db_path: Optional[str] = None,
    voice_note_id: Optional[str] = None,
) -> AnchorSaveResult:
    """Write a voice note + its anchor in one DuckDB transaction.

    Either both rows commit or neither does. If the anchor insert
    fails (FK violation, unique constraint, anything), we ROLLBACK
    before re-raising — no orphan voice_note row is left behind.

    Args:
      transcript: The transcribed voice note text. Empty strings
        are accepted but produce a low-utility document.
      document_id: The SOURCE document the user anchored to (i.e.
        the PDF they were reading).
      page: 0-indexed page number on the source document.
      bbox: PDF user-space bounding box. Must be non-degenerate.
      operator_id: Defaults to the single-operator constant.
      recorded_at: Defaults to now (UTC).
      duration_seconds: Audio duration; informational.
      language: Optional language code; informational.
      title: Optional human-readable title; defaults to a
        timestamp-based label.
      source_tier: Defaults to operator-tier (2).
      db_path: Optional DB override; mostly for tests.
      voice_note_id: Optional override of the voice-note's
        ``document_id``. Defaults to the stable
        ``voice_note_doc_id(operator_id, recorded_at)``.

    Returns:
      ``AnchorSaveResult`` with the voice_note_id + the freshly
      inserted ``VoiceNoteAnchor``.

    Raises:
      SaveAnchoredVoiceNoteError: any underlying exception. The
        original is in ``__cause__``. The DB has been rolled back.
    """
    when = recorded_at or datetime.now(timezone.utc)
    vid = voice_note_id or _stable_voice_note_id(
        operator_id=operator_id, recorded_at=when,
    )
    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    try:
        with connect_write(
            resolved_db_path, purpose="services/voice/save_anchor",
        ) as con:
            # Explicit transaction. DuckDB defaults to autocommit
            # per statement; BEGIN groups our two writes.
            con.execute("BEGIN")
            try:
                _insert_voice_note_document(
                    con,
                    voice_note_id=vid,
                    operator_id=operator_id,
                    recorded_at=when,
                    duration_seconds=duration_seconds,
                    transcript=transcript,
                    title=title,
                    language=language,
                    source_tier=source_tier,
                )
                anchor = create_anchor(
                    con,
                    voice_note_id=vid,
                    document_id=document_id,
                    page=page,
                    bbox=bbox,
                )
                con.execute("COMMIT")
            except Exception:
                # ROLLBACK is best-effort — if it itself raises
                # (e.g. the connection is already broken), we
                # still surface the original exception via the
                # outer try/except below.
                try:
                    con.execute("ROLLBACK")
                except Exception:  # pragma: no cover — defensive
                    pass
                raise
    except Exception as exc:  # noqa: BLE001 — wrap for caller
        raise SaveAnchoredVoiceNoteError(
            f"failed to save anchored voice note: {exc}"
        ) from exc

    return AnchorSaveResult(voice_note_id=vid, anchor=anchor)
