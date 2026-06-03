"""Tests for acquisition/voice/ (Sprint 13).

Strategy:
- Inject a ``StubTranscriber`` for the whisper path; no network IO.
- For ingest, use a temp DuckDB + temp event log via the fixture.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.voice import (
    Transcript,
    ingest_voice_note,
    transcribe_and_ingest,
    voice_note_doc_id,
)

# ─────────────────────────────────────────────────────────────────────
# Fixtures + helpers
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-voice-test-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


class StubTranscriber:
    """Test Transcriber that returns a fixed transcript."""

    def __init__(
        self, *, text: str, duration_seconds: float = 60.0,
        language: str = "en",
    ) -> None:
        self.text = text
        self.duration_seconds = duration_seconds
        self.language = language
        self.calls: list[bytes] = []

    def transcribe(
        self, audio_bytes: bytes, *, filename: str,
        language: str | None = None,
    ) -> Transcript:
        self.calls.append(audio_bytes)
        return Transcript(
            text=self.text,
            language=language or self.language,
            duration_seconds=self.duration_seconds,
            model="stub-whisper",
        )


_LONG_TRANSCRIPT = (
    "I want to think about how the substrate's recursive note-taking "
    "behavior actually compounds. The naive view is that each step "
    "adds linear value. But the actual mechanism is multiplicative: "
    "every new insight reweights every prior insight's salience. "
)


# ─────────────────────────────────────────────────────────────────────
# 1. Doc-id helper
# ─────────────────────────────────────────────────────────────────────


def test_voice_note_doc_id_stable():
    t = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
    a = voice_note_doc_id("__operator__", t)
    b = voice_note_doc_id("__operator__", t)
    assert a == b
    assert a.startswith("doc-vn-")


def test_voice_note_doc_id_distinct_per_timestamp():
    t1 = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
    t2 = datetime(2026, 5, 18, 14, 31, tzinfo=UTC)
    assert voice_note_doc_id("op", t1) != voice_note_doc_id("op", t2)


def test_voice_note_doc_id_empty_operator_raises():
    t = datetime(2026, 5, 18, tzinfo=UTC)
    with pytest.raises(ValueError):
        voice_note_doc_id("", t)


# ─────────────────────────────────────────────────────────────────────
# 2. ingest_voice_note
# ─────────────────────────────────────────────────────────────────────


def test_ingest_writes_document_and_chunks(temp_substrate):
    import duckdb
    r = ingest_voice_note(
        _LONG_TRANSCRIPT,
        investigation_id="inv-voice-test",
        recorded_at=datetime(2026, 5, 18, 14, 30, tzinfo=UTC),
        duration_seconds=90.0,
        language="en",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason is None
    assert r.chunks_written >= 1
    assert r.document_loaded_event_id is not None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
        (doc_type,) = con.execute(
            "SELECT document_type FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == r.chunks_written
    assert doc_type == "voice_note"


def test_ingest_low_word_count_skipped(temp_substrate):
    r = ingest_voice_note(
        "Too short.",
        investigation_id="inv-voice-test",
        recorded_at=datetime(2026, 5, 18, tzinfo=UTC),
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason == "low_word_count"
    assert r.chunks_written == 0


def test_ingest_idempotent_on_same_timestamp(temp_substrate):
    import duckdb
    when = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
    r1 = ingest_voice_note(
        _LONG_TRANSCRIPT,
        investigation_id="inv-voice-test",
        recorded_at=when,
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    r2 = ingest_voice_note(
        _LONG_TRANSCRIPT,
        investigation_id="inv-voice-test",
        recorded_at=when,
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r1.document_id == r2.document_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1


def test_ingest_default_title_from_timestamp(temp_substrate):
    when = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
    r = ingest_voice_note(
        _LONG_TRANSCRIPT,
        investigation_id="inv-voice-test",
        recorded_at=when,
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.title == "Voice note 2026-05-18 14:30"


def test_ingest_explicit_title_used(temp_substrate):
    r = ingest_voice_note(
        _LONG_TRANSCRIPT,
        investigation_id="inv-voice-test",
        title="My research thought",
        recorded_at=datetime(2026, 5, 18, tzinfo=UTC),
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.title == "My research thought"


# ─────────────────────────────────────────────────────────────────────
# 3. transcribe_and_ingest (end-to-end with stub)
# ─────────────────────────────────────────────────────────────────────


def test_transcribe_and_ingest_chains(temp_substrate):
    stub = StubTranscriber(text=_LONG_TRANSCRIPT, duration_seconds=120.0)
    r = transcribe_and_ingest(
        b"fake-audio-bytes",
        filename="note.wav",
        investigation_id="inv-voice-test",
        transcriber=stub,
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason is None
    assert r.transcript_text == _LONG_TRANSCRIPT
    assert r.duration_seconds == 120.0
    # Stub was called with our audio bytes
    assert len(stub.calls) == 1
    assert stub.calls[0] == b"fake-audio-bytes"


def test_transcribe_and_ingest_propagates_language(temp_substrate):
    stub = StubTranscriber(
        text=_LONG_TRANSCRIPT, duration_seconds=60.0, language="es",
    )
    r = transcribe_and_ingest(
        b"audio",
        filename="note.wav",
        investigation_id="inv-voice-test",
        language="es",
        transcriber=stub,
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    import duckdb
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (raw_metadata,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    import json
    metadata = json.loads(raw_metadata)
    assert metadata["language"] == "es"
