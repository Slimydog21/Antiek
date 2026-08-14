"""Link Monster — digest orchestrator tests.

The extraction ladder is exercised with httpx MockTransport (no
network) and a monkeypatched youtube client (no yt-dlp). The SSRF
guard's DNS check is bypassed for the fake public hosts via
``_host_is_safe``; the guard's own behavior is covered in
``test_link_monster_fetchguard.py``.
"""

from __future__ import annotations

import httpx
import pytest

from acquisition.link_monster.digest import digest_url
from acquisition.link_monster.fetchguard import UnsafeUrlError

_ARTICLE_HTML = b"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Fallback Title</title>
<meta property="og:title" content="OG Title">
<meta property="og:description" content="OG description here">
<meta property="og:image" content="https://img.example.com/cover.jpg">
<meta property="og:site_name" content="Example Site">
<meta property="article:published_time" content="2026-08-01T12:00:00Z">
<meta name="author" content="Jane Researcher">
<link rel="canonical" href="https://www.example.com/post/1">
</head><body>
<article>
<h1>OG Title</h1>
<p>This is a substantive article body with enough words to clear the
chunker's minimum. It discusses knowledge graphs, provenance, and the
value of compounding notes. Every sentence adds real content so the
DOM rung treats this as a meal, not a snack.</p>
<p>More paragraphs follow, because the extractor requires a reasonable
volume of text before it will produce markdown at all. This second
paragraph exists purely to satisfy that threshold honestly.</p>
</article>
</body></html>"""


@pytest.fixture
def safe_public(monkeypatch):
    """Let fake public hosts through the DNS check (guard logic itself
    is tested separately against IP literals)."""
    monkeypatch.setattr(
        "acquisition.link_monster.fetchguard._host_is_safe", lambda h: True
    )


def _oembed_json(title: str, author: str, thumb: str) -> bytes:
    import json

    return json.dumps(
        {
            "provider_name": "YouTube",
            "title": title,
            "author_name": author,
            "author_url": "https://youtube.com/@author",
            "thumbnail_url": thumb,
            "html": "<blockquote>embed</blockquote>",
        }
    ).encode()


def test_digest_generic_article_ladder(safe_public):
    """Generic page: oEmbed absent → OG found → DOM text → meal."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "publish.twitter.com":
            return httpx.Response(404)
        if req.url.host == "www.example.com":
            return httpx.Response(
                200, content=_ARTICLE_HTML,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    res = digest_url("https://www.example.com/post/1", client=client)
    d = res.digest
    assert d.platform == "generic"
    assert d.title == "OG Title"
    assert d.author == "Jane Researcher"
    assert d.site_name == "Example Site"
    assert d.thumbnail_url == "https://img.example.com/cover.jpg"
    assert d.outcome == "meal"
    assert d.text is not None and d.text.word_count > 10
    assert d.provenance.get("text") == "dom"
    assert d.provenance.get("title") == "og"
    assert d.provenance.get("oembed") == "none"
    assert d.artifacts["images"] == 1
    assert d.artifacts["text_chars"] > 0


def test_digest_youtube_oembed_plus_deep(monkeypatch, safe_public):
    """YouTube: oEmbed gives metadata; the deep client adds video info
    + timed transcript (monkeypatched — no yt-dlp, no network)."""
    from types import SimpleNamespace

    def fake_youtube_fetch(video_id, *, want_transcript=True):
        return SimpleNamespace(
            video_id=video_id,
            title="Deep Title",
            channel="Deep Channel",
            duration_seconds=125,
            upload_date=None,
            description="desc",
            transcript=[
                SimpleNamespace(start_seconds=0.0, duration_seconds=10.0, text="First sentence of the transcript."),
                SimpleNamespace(start_seconds=10.0, duration_seconds=10.0, text="Second sentence with more content here."),
            ],
            transcript_source="youtube",
            watch_url=f"https://www.youtube.com/watch?v={video_id}",
            caption_kind="auto",
        )

    monkeypatch.setattr("acquisition.youtube.client.fetch", fake_youtube_fetch)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "www.youtube.com":
            return httpx.Response(
                200, content=_oembed_json("OG Title", "Deep Author", "https://img.youtube.com/x/hq.jpg"),
                headers={"content-type": "application/json"},
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    res = digest_url("https://www.youtube.com/watch?v=abc123DEFgh", client=client)
    d = res.digest
    assert d.platform == "youtube"
    assert d.video is not None and d.video.video_id == "abc123DEFgh"
    assert d.video.duration_seconds == 125
    assert d.video.channel == "Deep Channel"
    assert d.transcript is not None and d.transcript.source == "youtube"
    assert d.transcript.chars > 0
    assert d.outcome == "meal"
    assert d.artifacts["videos"] == 1
    assert d.artifacts["transcript_chars"] > 0


def test_digest_youtube_deep_failure_degrades(safe_public):
    """yt-dlp absent/failing → metadata-only snack, never a raise."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "www.youtube.com":
            return httpx.Response(
                200, content=_oembed_json("Only Title", "Author", "https://img.youtube.com/x/hq.jpg"),
                headers={"content-type": "application/json"},
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    res = digest_url("https://www.youtube.com/watch?v=abc123DEFgh", client=client)
    d = res.digest
    assert d.title == "Only Title"
    assert d.transcript is None or d.transcript.chars == 0
    assert d.outcome == "snack"


def test_digest_ssrf_blocked():
    with pytest.raises(UnsafeUrlError) as ei:
        digest_url("http://127.0.0.1:8001/health")
    assert ei.value.reason == "ssrf_blocked"


def test_digest_invalid_url():
    with pytest.raises(ValueError):
        digest_url("file:///etc/passwd")
