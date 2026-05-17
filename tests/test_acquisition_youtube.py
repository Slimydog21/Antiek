"""Tests for acquisition/youtube/ (Sprint 12).

Strategy: youtube-transcript-api + yt-dlp both make network calls;
substrate tests stay offline. We monkeypatch the fetch + transcript
functions inside the client module, then exercise the adapter
end-to-end against a temp substrate.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import List

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.youtube import (
    TranscriptSegment,
    YouTubeVideo,
    ingest_youtube,
    parse_video_id,
    youtube_doc_id,
)
from acquisition.youtube.adapter import (
    _format_timestamp,
    _group_transcript_into_chunks,
)


# ── 1. parse_video_id ──────────────────────────────────────────────


def test_parse_video_id_bare():
    assert parse_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_parse_video_id_watch_url():
    assert (
        parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s")
        == "dQw4w9WgXcQ"
    )


def test_parse_video_id_shortlink():
    assert parse_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_parse_video_id_embed():
    assert (
        parse_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_parse_video_id_invalid():
    assert parse_video_id("not a youtube url") is None
    assert parse_video_id("https://example.com") is None


# ── 2. Doc id ──────────────────────────────────────────────────────


def test_youtube_doc_id_format():
    assert youtube_doc_id("dQw4w9WgXcQ") == "doc-yt-dQw4w9WgXcQ"


def test_youtube_doc_id_empty_raises():
    with pytest.raises(ValueError):
        youtube_doc_id("")


# ── 3. Timestamp formatting ────────────────────────────────────────


def test_format_timestamp_zero():
    assert _format_timestamp(0) == "00:00:00"


def test_format_timestamp_under_hour():
    assert _format_timestamp(125.5) == "00:02:05"


def test_format_timestamp_over_hour():
    assert _format_timestamp(3725) == "01:02:05"


# ── 4. Transcript segmentation ─────────────────────────────────────


def test_segmentation_one_chunk_when_under_target():
    segs = [
        TranscriptSegment(text="hello world", start_seconds=0.0, duration_seconds=2.0),
        TranscriptSegment(text="more text here", start_seconds=2.0, duration_seconds=2.0),
    ]
    chunks = _group_transcript_into_chunks(segs, target_words=250)
    assert len(chunks) == 1
    assert "hello world" in chunks[0].text
    assert chunks[0].section.startswith("Timestamp: 00:00:00")


def test_segmentation_splits_at_target():
    # 60 segments of 5 words = 300 words; target 100 → 3 chunks
    segs = [
        TranscriptSegment(
            text="word1 word2 word3 word4 word5",
            start_seconds=float(i * 2),
            duration_seconds=2.0,
        )
        for i in range(60)
    ]
    chunks = _group_transcript_into_chunks(segs, target_words=100)
    assert len(chunks) == 3


def test_segmentation_empty_returns_empty():
    assert _group_transcript_into_chunks([], target_words=100) == []


# ── 5. End-to-end adapter via injected video record ────────────────


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-yt-test-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


class _StubEmbedder:
    def encode(self, text: str) -> List[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def _fake_video(transcript_segments: int = 30) -> YouTubeVideo:
    segs = [
        TranscriptSegment(
            text=f"This is transcript segment number {i} with some real content.",
            start_seconds=float(i * 5),
            duration_seconds=5.0,
        )
        for i in range(transcript_segments)
    ]
    return YouTubeVideo(
        video_id="aaaaaaaaaaa",
        title="Test Video on Phased Array Radar",
        channel="Test Channel",
        duration_seconds=transcript_segments * 5,
        upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        description="A test video about radar concepts.",
        transcript=segs,
        transcript_source="youtube",
        watch_url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
    )


def test_ingest_writes_documents_chunks_nodes(temp_substrate):
    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
    )
    assert res.skipped_reason is None
    assert res.document_id == "doc-yt-aaaaaaaaaaa"
    assert res.document_loaded_event_id is not None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == res.chunks_written
    assert chunk_count >= 1


def test_ingest_low_word_count_skipped(temp_substrate):
    """Tiny video should skip graph writes."""
    tiny = YouTubeVideo(
        video_id="bbbbbbbbbbb",
        title="Tiny",
        channel="C",
        duration_seconds=5,
        upload_date=None,
        description="",
        transcript=[
            TranscriptSegment(text="one two", start_seconds=0.0, duration_seconds=1.0),
        ],
        transcript_source="youtube",
        watch_url="https://www.youtube.com/watch?v=bbbbbbbbbbb",
    )
    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=tiny,
    )
    assert res.skipped_reason == "low_word_count"
    assert res.chunks_written == 0


def test_ingest_timestamp_section_paths(temp_substrate):
    """Chunk section_paths must encode timestamp ranges."""
    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
    )
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        sections = con.execute(
            "SELECT section_path FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [res.document_id],
        ).fetchall()
    finally:
        con.close()
    assert all(
        s[0] and s[0].startswith("Timestamp: ") for s in sections
    ), sections


def test_ingest_idempotent_on_rows(temp_substrate):
    """Re-ingest of the same video → no new rows, second event still fires."""
    import duckdb

    video = _fake_video(30)
    r1 = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=video,
    )
    r2 = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=video,
    )
    assert r1.document_id == r2.document_id
    assert r1.chunk_ids == r2.chunk_ids
    assert r1.document_loaded_event_id != r2.document_loaded_event_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
