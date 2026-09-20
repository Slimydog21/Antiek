"""Link Monster — platform classification tests."""

from __future__ import annotations

import pytest

from acquisition.link_monster.platforms import classify, normalize_host


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc123DEFgh", "youtube"),
        ("https://youtu.be/abc123DEFgh", "youtube"),
        ("https://m.youtube.com/watch?v=abc123DEFgh", "youtube"),
        ("https://music.youtube.com/watch?v=abc123DEFgh", "youtube"),
        ("https://youtube.com/shorts/abc123DEFgh", "youtube"),
        ("https://x.com/someuser/status/1234567890", "x"),
        ("https://twitter.com/someuser/status/1234567890", "x"),
        ("https://mobile.twitter.com/someuser", "x"),
        ("https://www.instagram.com/reel/abc123/", "instagram"),
        ("https://instagr.am/p/abc123/", "instagram"),
        ("https://www.tiktok.com/@user/video/1234567890", "tiktok"),
        ("https://vm.tiktok.com/abcdef/", "tiktok"),
        ("https://vt.tiktok.com/abcdef/", "tiktok"),
        ("https://example.substack.com/p/hello-world", "substack"),
        ("https://substack.com/@someuser", "substack"),
        ("https://example.com/some/article", "generic"),
        ("https://news.ycombinator.com/item?id=1", "generic"),
        ("http://plain-http.example.com/x", "generic"),
    ],
)
def test_classify(url, expected):
    assert classify(url) == expected


def test_classify_rejects_non_http():
    for bad in ("file:///etc/passwd", "gopher://x", "ftp://x", "javascript:alert(1)", "", "not a url"):
        with pytest.raises(ValueError):
            classify(bad)


def test_normalize_host_strips_aliases():
    assert normalize_host("www.YouTube.com.") == "youtube.com"
    assert normalize_host("m.twitter.com") == "twitter.com"
    assert normalize_host("music.youtube.com") == "youtube.com"
    assert normalize_host("vm.tiktok.com") == "tiktok.com"
    assert normalize_host("example.com") == "example.com"


def test_classify_unknown_host_falls_to_generic():
    assert classify("https://some-random-site.example.net/page") == "generic"
