"""Tests for ``POST /sources/ingest`` (Sprint 12).

The acquisition adapters all do network IO, so for the endpoint
tests we monkeypatch each adapter's entry point to return a
synthetic result. The helpers ``_detect_source_kind`` and
``_extract_arxiv_id`` are exercised directly.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.app import (
    _detect_source_kind,
    _extract_arxiv_id,
    create_app,
)

# ─────────────────────────────────────────────────────────────────────
# 1. Helpers — kind detection
# ─────────────────────────────────────────────────────────────────────


def test_detect_source_kind_arxiv():
    assert _detect_source_kind("https://arxiv.org/abs/2402.03300") == "arxiv"
    assert _detect_source_kind("https://arxiv.org/pdf/2402.03300v2") == "arxiv"


def test_detect_source_kind_youtube():
    assert _detect_source_kind("https://www.youtube.com/watch?v=abc") == "youtube"
    assert _detect_source_kind("https://youtu.be/dQw4w9WgXcQ") == "youtube"


def test_detect_source_kind_podcast():
    assert _detect_source_kind("https://feeds.example.com/show.rss") == "podcast"
    assert _detect_source_kind("https://feeds.example.com/show.xml") == "podcast"
    assert _detect_source_kind("https://example.com/podcast/feed") == "podcast"


def test_detect_source_kind_url_default():
    assert _detect_source_kind("https://example.com/post.html") == "url"


def test_detect_source_kind_explicit_overrides_auto():
    """Explicit kind must take precedence over URL heuristic."""
    assert _detect_source_kind("https://arxiv.org/abs/x", "url") == "url"
    assert _detect_source_kind("https://example.com/x", "youtube") == "youtube"


# ─────────────────────────────────────────────────────────────────────
# 2. arXiv id extraction
# ─────────────────────────────────────────────────────────────────────


def test_extract_arxiv_id_from_abs_url():
    assert _extract_arxiv_id("https://arxiv.org/abs/2402.03300") == "2402.03300"


def test_extract_arxiv_id_from_pdf_url():
    assert _extract_arxiv_id("https://arxiv.org/pdf/2402.03300") == "2402.03300"


def test_extract_arxiv_id_strips_version_suffix():
    assert _extract_arxiv_id("https://arxiv.org/abs/2402.03300v2") == "2402.03300"


def test_extract_arxiv_id_bare_id():
    assert _extract_arxiv_id("2402.03300") == "2402.03300"
    assert _extract_arxiv_id("2402.03300v3") == "2402.03300"


def test_extract_arxiv_id_invalid_url():
    assert _extract_arxiv_id("https://example.com/post") is None
    assert _extract_arxiv_id("not-an-arxiv-id") is None


# ─────────────────────────────────────────────────────────────────────
# 3. POST /sources/ingest — endpoint integration
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sources-ingest-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def test_ingest_youtube_endpoint_calls_adapter(monkeypatch, temp_substrate):
    """Endpoint must route youtube URLs to acquisition.youtube.ingest_youtube
    and surface the result in the response body."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        document_id: str = "doc-yt-abc"
        document_loaded_event_id: str = "evt-1"
        chunks_written: int = 5
        skipped_reason: str | None = None
        title: str = "Mock Video Title"
        chunk_ids: list = None
        node_ids: list = None

    import acquisition.youtube as _yt
    monkeypatch.setattr(_yt, "ingest_youtube", lambda *a, **kw: _R())

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["detected_kind"] == "youtube"
    assert body["document_id"] == "doc-yt-abc"
    assert body["chunks_written"] == 5
    assert body["title"] == "Mock Video Title"


def test_ingest_youtube_skipped_when_no_chunks(monkeypatch, temp_substrate):
    """Skipped_reason from the adapter must round-trip into the response."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        document_id: str = "doc-yt-abc"
        document_loaded_event_id: str = "evt-1"
        chunks_written: int = 0
        skipped_reason: str = "no_transcript"
        title: str = "No-Transcript Video"
        chunk_ids: list = None
        node_ids: list = None

    import acquisition.youtube as _yt
    monkeypatch.setattr(_yt, "ingest_youtube", lambda *a, **kw: _R())

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://youtube.com/watch?v=x"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "skipped"
    assert body["skipped_reason"] == "no_transcript"


def test_ingest_podcast_endpoint_aggregates_episodes(monkeypatch, temp_substrate):
    """Podcast ingest must report episodes_processed + episodes_ingested
    as the sum across the feed."""
    from dataclasses import dataclass

    @dataclass
    class _Ep:
        document_id: str
        episode_id: str
        chunks_written: int
        skipped_reason: str | None
        title: str
        chunk_ids: list = None
        node_ids: list = None
        document_loaded_event_id: str = "evt-pod"

    results = [
        _Ep("doc-pod-1", "ep-1", 12, None, "Ep 1"),
        _Ep("doc-pod-2", "ep-2", 0, "no_transcript", "Ep 2"),
        _Ep("doc-pod-3", "ep-3", 8, None, "Ep 3"),
    ]
    import acquisition.podcasts as _pod
    monkeypatch.setattr(_pod, "ingest_feed", lambda *a, **kw: results)

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://feeds.example.com/show.rss", "max_episodes": 5},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["detected_kind"] == "podcast"
    assert body["episodes_processed"] == 3
    assert body["episodes_ingested"] == 2
    assert body["chunks_written"] == 20  # 12 + 0 + 8


def test_ingest_url_endpoint_default(monkeypatch, temp_substrate):
    """URLs that don't match a known kind fall through to acquisition.urls."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        document_id: str = "doc-url-abc"
        document_loaded_event_id: str = "evt-url"
        chunks_written: int = 3
        skipped_reason: str | None = None
        title: str = "Generic Article"
        chunk_ids: list = None
        node_ids: list = None

    import acquisition.urls as _urls
    monkeypatch.setattr(_urls, "ingest_url", lambda *a, **kw: _R())

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://example.com/article"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["detected_kind"] == "url"
    assert body["document_id"] == "doc-url-abc"


def test_ingest_arxiv_invalid_id_returns_error(monkeypatch, temp_substrate):
    """An arxiv-looking URL we cannot parse must round-trip as an
    error response, not a 500."""
    # Force a URL that pattern-matches arxiv but yields no id.
    # NOTE: ``interfaces.research.api.__init__`` re-exports ``app`` (the
    # FastAPI instance), so the dotted import resolves to that, not the
    # submodule. Reach into ``sys.modules`` to get the submodule itself.
    _app_mod = sys.modules["interfaces.research.api.app"]
    monkeypatch.setattr(_app_mod, "_extract_arxiv_id", lambda u: None)

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://arxiv.org/abs/garbage"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "error"
    assert body["detected_kind"] == "arxiv"
    assert "arXiv id" in (body["error_message"] or "")


def test_ingest_with_explicit_kind_overrides_detection(monkeypatch, temp_substrate):
    """Operator can force the adapter choice via ``kind``."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        document_id: str = "doc-url-forced"
        document_loaded_event_id: str = "evt"
        chunks_written: int = 1
        skipped_reason: str | None = None
        title: str = "Forced URL"
        chunk_ids: list = None
        node_ids: list = None

    import acquisition.urls as _urls
    monkeypatch.setattr(_urls, "ingest_url", lambda *a, **kw: _R())

    client = _client(temp_substrate)
    # An arxiv URL forced to be ingested as a plain URL
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://arxiv.org/abs/2402.03300", "kind": "url"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["detected_kind"] == "url"
    assert body["document_id"] == "doc-url-forced"


def test_ingest_short_url_validation_error(temp_substrate):
    """Pydantic min_length should reject obviously bogus URLs."""
    client = _client(temp_substrate)
    resp = client.post("/sources/ingest", json={"url": "x"})
    assert resp.status_code == 422
