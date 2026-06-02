"""Tests for acquisition/podcasts/ (Sprint 12).

Strategy: mock RSS feed XML via httpx.MockTransport for the client
fetch path; for the adapter, inject Podcast + Episode dataclasses
directly with transcript_override to bypass HTTP entirely.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.podcasts import (
    Episode,
    Podcast,
    fetch_feed,
    ingest_podcast_episode,
    podcast_doc_id,
)
from acquisition.podcasts.client import (
    _clean_srt,
    _clean_vtt,
    _parse_duration,
)

# ─────────────────────────────────────────────────────────────────────
# Fixtures + helpers
# ─────────────────────────────────────────────────────────────────────


_RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>Phased Array Weekly</title>
    <itunes:author>Antiek Test Network</itunes:author>
    <description>A test feed for podcast ingestion.</description>
    <language>en-us</language>
    <item>
      <title>Episode 1: Direct-path interference suppression</title>
      <guid>ep-1-dpi-suppression</guid>
      <description>A deep dive into adaptive filtering for DPI suppression.</description>
      <pubDate>Mon, 12 May 2026 10:00:00 +0000</pubDate>
      <link>https://podcast.example/ep1</link>
      <enclosure url="https://podcast.example/ep1.mp3" type="audio/mpeg" length="12345" />
      <itunes:duration>01:23:45</itunes:duration>
      <podcast:transcript url="https://podcast.example/ep1.txt" type="text/plain" />
    </item>
    <item>
      <title>Episode 2: Phased array fundamentals</title>
      <guid>ep-2-phased-array</guid>
      <description>Antenna design tradeoffs for steerable arrays.</description>
      <pubDate>Mon, 5 May 2026 10:00:00 +0000</pubDate>
      <link>https://podcast.example/ep2</link>
      <enclosure url="https://podcast.example/ep2.mp3" type="audio/mpeg" length="9876" />
      <itunes:duration>45:30</itunes:duration>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-pod-test-")
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


# ─────────────────────────────────────────────────────────────────────
# 1. Helpers
# ─────────────────────────────────────────────────────────────────────


def test_podcast_doc_id_stable():
    a = podcast_doc_id("ep-1-dpi-suppression")
    b = podcast_doc_id("ep-1-dpi-suppression")
    assert a == b
    assert a.startswith("doc-pod-")


def test_podcast_doc_id_differs():
    assert podcast_doc_id("ep-1") != podcast_doc_id("ep-2")


def test_podcast_doc_id_empty_raises():
    with pytest.raises(ValueError):
        podcast_doc_id("")


def test_parse_duration_hms():
    assert _parse_duration({"itunes_duration": "01:23:45"}) == 3600 + 23 * 60 + 45


def test_parse_duration_ms():
    assert _parse_duration({"itunes_duration": "45:30"}) == 45 * 60 + 30


def test_parse_duration_bare_seconds():
    assert _parse_duration({"itunes_duration": "120"}) == 120


def test_parse_duration_missing_returns_zero():
    assert _parse_duration({}) == 0


# ─────────────────────────────────────────────────────────────────────
# 2. Transcript-format cleaners
# ─────────────────────────────────────────────────────────────────────


def test_clean_vtt_strips_header_and_timestamps():
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:05.000\n"
        "Hello and welcome.\n\n"
        "00:00:05.000 --> 00:00:10.000\n"
        "Today we discuss radar.\n"
    )
    result = _clean_vtt(vtt)
    assert "WEBVTT" not in result
    assert "-->" not in result
    assert "Hello and welcome." in result
    assert "Today we discuss radar." in result


def test_clean_srt_strips_cue_numbers_and_timestamps():
    srt = (
        "1\n"
        "00:00:00,000 --> 00:00:05,000\n"
        "Hello and welcome.\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:10,000\n"
        "Today we discuss radar.\n"
    )
    result = _clean_srt(srt)
    assert "-->" not in result
    assert "Hello and welcome." in result
    assert "Today we discuss radar." in result


# ─────────────────────────────────────────────────────────────────────
# 3. RSS feed fetch via mock transport
# ─────────────────────────────────────────────────────────────────────


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_fetch_feed_parses_channel_metadata():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_RSS_SAMPLE)
    podcast = fetch_feed("https://example/feed.rss", client=_mock_client(handler))
    assert podcast.title == "Phased Array Weekly"
    assert podcast.author == "Antiek Test Network"
    assert podcast.language == "en-us"
    assert len(podcast.episodes) == 2


def test_fetch_feed_episode_details():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_RSS_SAMPLE)
    podcast = fetch_feed("https://example/feed.rss", client=_mock_client(handler))
    ep1 = podcast.episodes[0]
    assert ep1.title == "Episode 1: Direct-path interference suppression"
    assert ep1.episode_id == "ep-1-dpi-suppression"
    assert ep1.audio_url == "https://podcast.example/ep1.mp3"
    assert ep1.transcript_url == "https://podcast.example/ep1.txt"
    assert ep1.duration_seconds == 3600 + 23 * 60 + 45


def test_fetch_feed_episode_without_transcript():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_RSS_SAMPLE)
    podcast = fetch_feed("https://example/feed.rss", client=_mock_client(handler))
    ep2 = podcast.episodes[1]
    assert ep2.transcript_url is None
    assert ep2.audio_url == "https://podcast.example/ep2.mp3"
    assert ep2.duration_seconds == 45 * 60 + 30


def test_fetch_feed_max_episodes_caps():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_RSS_SAMPLE)
    podcast = fetch_feed(
        "https://example/feed.rss", max_episodes=1, client=_mock_client(handler),
    )
    assert len(podcast.episodes) == 1


# ─────────────────────────────────────────────────────────────────────
# 4. End-to-end adapter via injected transcript
# ─────────────────────────────────────────────────────────────────────


def _fake_podcast() -> Podcast:
    return Podcast(
        feed_url="https://example/feed.rss",
        title="Phased Array Weekly",
        author="Antiek Test Network",
        description="Test feed.",
        language="en-us",
    )


def _fake_episode() -> Episode:
    return Episode(
        episode_id="ep-1-dpi-suppression",
        title="Episode 1: DPI suppression",
        description="A deep dive on adaptive filtering.",
        published_at=datetime(2026, 5, 12, tzinfo=UTC),
        duration_seconds=3600,
        audio_url="https://podcast.example/ep1.mp3",
        transcript_url="https://podcast.example/ep1.txt",
        episode_url="https://podcast.example/ep1",
    )


_LONG_TRANSCRIPT = (
    "Welcome to the show. Today we will discuss adaptive filtering for "
    "direct-path interference suppression in passive bistatic radar. "
    * 30
)


def test_ingest_episode_writes_documents_chunks_nodes(temp_substrate):
    import duckdb

    r = ingest_podcast_episode(
        _fake_podcast(),
        _fake_episode(),
        investigation_id="inv-pod-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        transcript_override=_LONG_TRANSCRIPT,
    )
    assert r.skipped_reason is None
    assert r.document_id == podcast_doc_id("ep-1-dpi-suppression")
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
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == r.chunks_written
    assert chunk_count >= 1


def test_ingest_episode_no_transcript_skipped(temp_substrate):
    ep = Episode(
        episode_id="ep-no-trans",
        title="No-Transcript Episode",
        description="A short description.",
        published_at=None,
        duration_seconds=0,
        audio_url="https://podcast.example/no-trans.mp3",
        transcript_url=None,  # no transcript advertised
        episode_url="https://podcast.example/no-trans",
    )
    r = ingest_podcast_episode(
        _fake_podcast(), ep,
        investigation_id="inv-pod-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason == "no_transcript"
    assert r.chunks_written == 0


def test_ingest_episode_low_word_count_skipped(temp_substrate):
    r = ingest_podcast_episode(
        _fake_podcast(),
        _fake_episode(),
        investigation_id="inv-pod-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        transcript_override="too short",
    )
    assert r.skipped_reason == "low_word_count"


def test_ingest_episode_idempotent_on_rows(temp_substrate):
    import duckdb

    podcast = _fake_podcast()
    ep = _fake_episode()
    r1 = ingest_podcast_episode(
        podcast, ep,
        investigation_id="inv-pod-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        transcript_override=_LONG_TRANSCRIPT,
    )
    r2 = ingest_podcast_episode(
        podcast, ep,
        investigation_id="inv-pod-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        transcript_override=_LONG_TRANSCRIPT,
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
